#include "engine/SystemProxySession.h"
#include "engine/RustCoreEngine.h"
#include "network/HttpRequestPolicy.h"
#include <QCoreApplication>
#include <QTest>
#include <QTemporaryDir>
#include <QTcpServer>
#include <QProcess>
#include <QFile>
#include <QJsonDocument>
#include <QSettings>
#include <QtEndian>
#include <QLockFile>
#include <QSignalSpy>
#include <QDir>
#include <QScopeGuard>
#include <QJsonArray>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QNetworkRequest>
#include <QTcpSocket>
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <winhttp.h>
#endif

namespace {
QJsonObject configuredProxy(QJsonObject value,int flags,const QString &server,const QString &pac={}) {
    value.insert("flags",flags);value.insert("server",server);value.insert("pac",pac);
    auto registry=value.value("registry").toObject();
    QByteArray enabled(4,Qt::Uninitialized);qToLittleEndian<quint32>((flags&2)!=0,enabled.data());
    registry.insert("ProxyEnable",QJsonObject{{"present",true},{"type",4},{"data",QString::fromLatin1(enabled.toBase64())}});
    const QString strings[]={server,value.value("bypass").toString(),pac};
    const char *keys[]={"ProxyServer","ProxyOverride","AutoConfigURL"};
    for(int i=0;i<3;++i) {
        if(i==2&&strings[i].isEmpty()){registry.insert(keys[i],QJsonObject{{"present",false}});continue;}
        const QByteArray bytes(reinterpret_cast<const char *>(strings[i].utf16()),(strings[i].size()+1)*2);
        registry.insert(keys[i],QJsonObject{{"present",true},{"type",1},{"data",QString::fromLatin1(bytes.toBase64())}});
    }
    value.insert("registry",registry);return value;
}
#ifdef Q_OS_WIN
QJsonObject winHttpDefaultSnapshot(QString *error) {
    WINHTTP_PROXY_INFO info{};
    const bool queried=WinHttpGetDefaultProxyConfiguration(&info);
    const auto code=queried?ERROR_SUCCESS:GetLastError();
    const auto release=qScopeGuard([&] {
        if(info.lpszProxy)GlobalFree(info.lpszProxy);
        if(info.lpszProxyBypass)GlobalFree(info.lpszProxyBypass);
    });
    if(!queried) {
        if(error)*error=QStringLiteral("WinHTTP default proxy query failed (Windows error %1).").arg(code);
        return {};
    }
    // This is the machine WinHTTP default, not the current user's WinINET
    // settings. Keep exact strings and nullness in memory only; never emit
    // these snapshots in QTest diagnostics or its XML report.
    return {{"accessType",double(info.dwAccessType)},
        {"proxyPresent",info.lpszProxy!=nullptr},
        {"proxy",QString::fromWCharArray(info.lpszProxy?info.lpszProxy:L"")},
        {"bypassPresent",info.lpszProxyBypass!=nullptr},
        {"bypass",QString::fromWCharArray(info.lpszProxyBypass?info.lpszProxyBypass:L"")}};
}
#endif
}

class ProxyTests : public QObject {
    Q_OBJECT
    QJsonObject m_winHttpBefore;
private slots:
    void init() {
        QString error;m_winHttpBefore=winHttpDefaultSnapshot(&error);
        QVERIFY2(!m_winHttpBefore.isEmpty(),qPrintable(error));
    }
    void cleanup() {
        if(m_winHttpBefore.isEmpty())return; // An init query failure is already recorded.
        QString error;const auto after=winHttpDefaultSnapshot(&error);
        QVERIFY2(!after.isEmpty(),qPrintable(error));
        // Boolean comparison avoids printing original proxy credentials or
        // private bypass values if an unrelated regression changes WinHTTP.
        QVERIFY2(after==m_winHttpBefore,"The native proxy operation changed machine-wide WinHTTP settings.");
    }
    void takeoverRestoresPacAndCustomBypass_data() {
        QTest::addColumn<int>("flags");
        QTest::newRow("pac-only")<<5;
        QTest::newRow("manual-and-pac")<<7;
    }
    void takeoverRestoresPacAndCustomBypass() {
        QFETCH(int,flags);
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        const auto restore=qScopeGuard([&] {
            // Run even after a failed assertion, after the session/guard have
            // released the fixture. Never log the runner's original settings.
            if(!SystemProxySession::apply(original)||SystemProxySession::snapshot()!=original)
                QTest::qFail("Could not restore the disposable runner's original proxy configuration.",__FILE__,__LINE__);
        });
        QTemporaryDir temp;QVERIFY(temp.isValid());
        QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        const QString pac=QStringLiteral("http://127.0.0.1:65010/swirl-fixture.pac?revision=before-takeover");
        const QString bypass=QStringLiteral("localhost;*.swirl-proxy.invalid;10.42.*;[::1];<local>");
        auto fixture=original;fixture.insert("bypass",bypass);
        fixture=configuredProxy(fixture,flags,QStringLiteral("127.0.0.1:65009"),pac);
        QString error;QVERIFY2(SystemProxySession::apply(fixture,&error),qPrintable(error));
        QVERIFY2(SystemProxySession::snapshot()==fixture,"The nonempty PAC/bypass fixture was not applied exactly.");
        const auto journal=temp.filePath("pac-bypass.dpapi");SystemProxySession proxy(nullptr,journal);
        QVERIFY(proxy.requestEnable(listener.serverPort(),QCoreApplication::applicationPid()));
        QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy(),5000);
        QVERIFY2(proxy.owned()&&proxy.enabled(),qPrintable(proxy.error()));
        const auto owned=SystemProxySession::snapshot();
        QCOMPARE(owned.value("flags").toInt(),3);
        QVERIFY2(owned.value("server").toString()==QStringLiteral("127.0.0.1:%1").arg(listener.serverPort()),"The owned proxy does not point to the expected loopback listener.");
        QVERIFY(owned.value("pac").toString().isEmpty());
        QVERIFY(owned.value("bypass").toString()!=bypass);
        QVERIFY(proxy.diagnosticState().value("guardAcknowledged").toBool());
        QFile encrypted(journal);QVERIFY(encrypted.open(QIODevice::ReadOnly));
        const auto protectedRecord=encrypted.readAll();encrypted.close();
        QVERIFY(!protectedRecord.isEmpty());
        QVERIFY(!protectedRecord.contains(pac.toUtf8()));
        QVERIFY(!protectedRecord.contains(bypass.toUtf8()));
        const auto diagnostic=QJsonDocument(QJsonObject::fromVariantMap(proxy.diagnosticState())).toJson();
        QVERIFY(!diagnostic.contains(pac.toUtf8()));
        QVERIFY(!diagnostic.contains(bypass.toUtf8()));
        const auto winHttpDuring=winHttpDefaultSnapshot(&error);
        QVERIFY2(!winHttpDuring.isEmpty(),qPrintable(error));
        QVERIFY2(winHttpDuring==m_winHttpBefore,"Taking over WinINET also changed machine-wide WinHTTP settings.");
        proxy.disable();QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy()&&!proxy.owned(),5000);
        QVERIFY2(proxy.error().isEmpty(),qPrintable(proxy.error()));
        // Equality includes WinINET flags/server/PAC/bypass and the presence,
        // registry types and exact bytes of all four stored registry values.
        QVERIFY2(SystemProxySession::snapshot()==fixture,"Releasing Swirl did not restore the original PAC/bypass configuration exactly.");
        QTRY_VERIFY_WITH_TIMEOUT(!QFile::exists(journal)&&QDir(temp.path()).entryList({"*.ready"},QDir::Files).isEmpty(),5000);
    }
    void takeoverUsesActualRustCoreListenerAndRestoresExactly() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        const auto restore=qScopeGuard([&] {
            // This native suite only runs on explicitly opted-in disposable
            // runners. Restore their exact snapshot even after an early failure.
            if(!SystemProxySession::apply(original)||SystemProxySession::snapshot()!=original)
                QTest::qFail("Could not restore the disposable runner's original proxy configuration.",__FILE__,__LINE__);
        });
        QTemporaryDir temp;QVERIFY(temp.isValid());
        int originRequests=0;
        const QByteArray body("native-system-proxy-rust-v2");
        QTcpServer origin;origin.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(origin.listen(QHostAddress::LocalHost));
        QObject::connect(&origin,&QTcpServer::newConnection,&origin,[&] {
            while(auto *socket=origin.nextPendingConnection()) {
                QObject::connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
                QObject::connect(socket,&QTcpSocket::readyRead,socket,[&,socket] {
                    const auto request=socket->property("request").toByteArray()+socket->readAll();
                    if(request.size()>16384){socket->abort();return;}
                    socket->setProperty("request",request);
                    if(!request.contains("\r\n\r\n")||socket->property("answered").toBool())return;
                    socket->setProperty("answered",true);
                    if(!request.startsWith("GET /native-rust-proxy HTTP/1.1\r\n")){socket->abort();return;}
                    ++originRequests;
                    socket->write("HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: "+QByteArray::number(body.size())+"\r\n\r\n"+body);
                    socket->disconnectFromHost();
                });
            }
        });
        QTcpServer reservation;reservation.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(reservation.listen(QHostAddress::LocalHost));
        const auto requestedPort=reservation.serverPort();reservation.close();
        EngineStartOptions options;options.proxyPort=requestedPort;
        options.policyDocument={{"schema",2},{"mode","direct"},
            {"default_policy",QJsonObject{{"id","policy:default"},{"target",QJsonObject{{"kind","unconfigured"}}}}},
            {"service_policies",QJsonArray{}},{"groups",QJsonArray{}},{"explicit_direct_rules",QJsonArray{}},
            {"custom_rules",QJsonArray{}},{"missing_targets",QJsonArray{}}};
        options.configurationStoreId="40000000-0000-4000-8000-000000000071";
        options.configurationRevision="1";options.configurationRequestId="50000000-0000-4000-8000-000000000071";
        RustCoreEngine engine;engine.start(options);
        QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
        QCOMPARE(engine.status().controlEndpoint,QStringLiteral("in-process://SwirlRust/v2"));
        QCOMPARE(engine.status().proxyPort,int(requestedPort));
        const auto journal=temp.filePath("native-rust.dpapi");SystemProxySession proxy(nullptr,journal);
        QVERIFY(proxy.requestEnable(engine.status().proxyPort,engine.status().processId));
        QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy(),5000);
        QVERIFY2(proxy.owned()&&proxy.enabled(),qPrintable(proxy.error()));
        // Derive the endpoint from the actual native readback, then use that
        // endpoint for both wire protocols. The reserved proxy port has no Qt
        // listener: only the production Rust DLL can serve these requests.
        const auto owned=SystemProxySession::snapshot();
        const auto address=owned.value("server").toString();
        QVERIFY2(address==QStringLiteral("127.0.0.1:%1").arg(requestedPort),"Native proxy does not reference the real Rust listener; raw settings omitted.");
        QCOMPARE(owned.value("flags").toInt(),3);
        QSettings internet(QStringLiteral("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"),QSettings::NativeFormat);
        internet.sync();
        QCOMPARE(internet.value("ProxyEnable").toInt(),1);
        QVERIFY2(internet.value("ProxyServer").toString()==address,"Native and registry listener identities differ; raw settings omitted.");
        const auto endpoint=QUrl(QStringLiteral("http://")+address);
        QVERIFY(endpoint.isValid());QCOMPARE(endpoint.host(),QStringLiteral("127.0.0.1"));
        QCOMPARE(endpoint.port(),engine.status().proxyPort);
        const auto url=QUrl(QStringLiteral("http://127.0.0.1:%1/native-rust-proxy").arg(origin.serverPort()));
        for(const auto type:{QNetworkProxy::HttpProxy,QNetworkProxy::Socks5Proxy}) {
            QNetworkAccessManager client;
            // Explicitly use the observed native endpoint because a loopback
            // fixture is intentionally covered by Windows's local bypass list.
            client.setProxy(QNetworkProxy(type,endpoint.host(),quint16(endpoint.port())));
            QNetworkRequest request(url);SwirlNetwork::applyHttp1OnlyPolicy(request);
            request.setTransferTimeout(4000);request.setRawHeader("Connection","close");
            auto *reply=client.get(request);
            QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);
            QCOMPARE(reply->error(),QNetworkReply::NoError);
            QCOMPARE(reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt(),200);
            QCOMPARE(reply->readAll(),body);
        }
        QCOMPARE(originRequests,2);
        QVERIFY(QTest::qWaitFor([&] {
            engine.refresh();const auto connections=engine.status().connections;
            if(connections.size()!=2)return false;
            for(const auto &entry:connections)if(!entry.toMap().value("closed").toBool())return false;
            return true;
        },5000));
        QVERIFY(engine.status().rustAccepted>=2);QCOMPARE(engine.status().rustFailed,0);
        QVERIFY(engine.status().uploadTotal>0);QVERIFY(engine.status().downloadTotal>0);
        QString error;const auto winHttpDuring=winHttpDefaultSnapshot(&error);
        QVERIFY2(!winHttpDuring.isEmpty(),qPrintable(error));
        QVERIFY2(winHttpDuring==m_winHttpBefore,"The real Rust proxy takeover changed machine-wide WinHTTP settings.");
        proxy.disable();QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy()&&!proxy.owned(),5000);
        QVERIFY2(SystemProxySession::snapshot()==original,"The real Rust session did not restore the exact original settings; raw settings omitted.");
        QTRY_VERIFY_WITH_TIMEOUT(!QFile::exists(journal)&&QDir(temp.path()).entryList({"*.ready"},QDir::Files).isEmpty(),5000);
        engine.stop();QVERIFY(!engine.status().processAlive);
        QTcpServer released;released.setProxy(QNetworkProxy::NoProxy);
        QVERIFY2(released.listen(QHostAddress::LocalHost,requestedPort),"The real Rust proxy listener was not released.");
    }
    void lateAcknowledgementFromReleasedGuardCannotReplaceTheNextSession() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        const auto journal=temp.filePath("late-guard.dpapi");SystemProxySession proxy(nullptr,journal);
        QVERIFY(proxy.requestEnable(listener.serverPort(),QCoreApplication::applicationPid()));
        QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy()&&proxy.owned(),5000);
        const auto firstFiles=QDir(temp.path()).entryList({"*.ready"},QDir::Files);QCOMPARE(firstFiles.size(),1);
        const auto oldPath=temp.filePath(firstFiles.first());QFile first(oldPath);QVERIFY(first.open(QIODevice::ReadOnly));
        const auto oldAcknowledgement=first.readAll();first.close();QVERIFY(!oldAcknowledgement.isEmpty());
        proxy.disable();QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy()&&!proxy.owned(),5000);
        QTRY_VERIFY_WITH_TIMEOUT(!QFile::exists(oldPath),5000);
        QVERIFY(proxy.requestEnable(listener.serverPort(),QCoreApplication::applicationPid()));
        QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy()&&proxy.owned(),5000);
        const auto nextFiles=QDir(temp.path()).entryList({"*.ready"},QDir::Files);QCOMPARE(nextFiles.size(),1);
        QVERIFY(temp.filePath(nextFiles.first())!=oldPath);
        // Reproduce the write of an old guard resuming after the new guard has
        // acknowledged. The current session must retain its own readiness.
        QFile late(oldPath);QVERIFY(late.open(QIODevice::WriteOnly));QCOMPARE(late.write(oldAcknowledgement),oldAcknowledgement.size());late.close();
        QVERIFY(proxy.diagnosticState().value("guardAcknowledged").toBool());
        proxy.disable();QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy()&&!proxy.owned(),5000);
        QVERIFY2(SystemProxySession::snapshot()==original,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
    }
    void asynchronousTakeoverYieldsDuringJournalContentionAndCancelsSafely() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        const auto journal=temp.filePath("async-proxy.dpapi");SystemProxySession proxy(nullptr,journal);
        QLockFile otherProcess(journal+".lock");QVERIFY(otherProcess.tryLock(0));
        QSignalSpy completed(&proxy,&SystemProxySession::enableFinished);
        QVERIFY(proxy.requestEnable(listener.serverPort(),QCoreApplication::applicationPid()));
        bool cancelledByEvent=false;QTimer::singleShot(75,&proxy,[&]{cancelledByEvent=true;proxy.disable();});
        QTRY_COMPARE_WITH_TIMEOUT(completed.count(),1,1500);
        QVERIFY(cancelledByEvent);QVERIFY(!completed.first().at(1).toBool());QVERIFY(!proxy.busy());
        QVERIFY2(SystemProxySession::snapshot()==original,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");QVERIFY(!QFile::exists(journal));
        otherProcess.unlock();completed.clear();
        QVERIFY(proxy.requestEnable(listener.serverPort(),QCoreApplication::applicationPid()));
        QTRY_COMPARE_WITH_TIMEOUT(completed.count(),1,5000);
        QVERIFY2(completed.first().at(1).toBool(),qPrintable(proxy.error()));QVERIFY(proxy.owned());
        QVERIFY(proxy.diagnosticState().value("guardAcknowledged").toBool());
        proxy.disable();QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy()&&!proxy.owned(),5000);
        QVERIFY2(SystemProxySession::snapshot()==original,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
    }
    void explicitOffDisablesExternalAndOwnedProxy() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        const auto external=configuredProxy(original,7,"127.0.0.1:65006","http://127.0.0.1:65007/test.pac");
        QString error;QVERIFY2(SystemProxySession::apply(external,&error),qPrintable(error));
        QVERIFY2(SystemProxySession::snapshot()==external,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
        SystemProxySession proxy(nullptr,temp.filePath("explicit-off.dpapi"));
        proxy.refresh();QVERIFY(proxy.systemEnabled());QVERIFY(!proxy.owned());
        QVERIFY2(proxy.turnOffSystemProxy(),qPrintable(proxy.error()));
        QVERIFY(!proxy.systemEnabled());QVERIFY(!proxy.owned());
        const auto off=SystemProxySession::snapshot();
        QCOMPARE(off.value("flags").toInt(),1);QVERIFY(off.value("pac").toString().isEmpty());
        QVERIFY(!off.value("registry").toObject().value("AutoConfigURL").toObject().value("present").toBool());
        const auto pacOnly=configuredProxy(external,5,"127.0.0.1:65006","http://127.0.0.1:65007/test.pac");
        QVERIFY2(SystemProxySession::apply(pacOnly,&error),qPrintable(error));QVERIFY2(SystemProxySession::snapshot()==pacOnly,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");proxy.refresh();QVERIFY(proxy.systemEnabled());
        QVERIFY(proxy.turnOffSystemProxy());QVERIFY(!proxy.systemEnabled());
        const auto automatic=configuredProxy(external,9,"127.0.0.1:65006");
        QVERIFY2(SystemProxySession::apply(automatic,&error),qPrintable(error));QVERIFY2(SystemProxySession::snapshot()==automatic,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");proxy.refresh();QVERIFY(proxy.systemEnabled());
        QVERIFY(proxy.turnOffSystemProxy());QVERIFY(!proxy.systemEnabled());
        QVERIFY(SystemProxySession::apply(external));
        QVERIFY(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()));
        QVERIFY(proxy.systemEnabled());QVERIFY(proxy.owned());
        QVERIFY2(proxy.turnOffSystemProxy(),qPrintable(proxy.error()));
        QVERIFY(!proxy.systemEnabled());QVERIFY(!proxy.owned());QVERIFY(!proxy.enabled());
        QVERIFY(!QFile::exists(temp.filePath("explicit-off.dpapi")));
        QVERIFY(proxy.disable()); // Exit/release cannot restore the old external proxy.
        QVERIFY2(SystemProxySession::snapshot()==off,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
    }
    void currentUserRecovery() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        // Restore the user's real settings even when an assertion terminates a
        // test early. These tests never touch WinHTTP, DNS, route or VPN state.
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QVERIFY(temp.isValid());
        QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        const auto journal=temp.filePath("proxy.dpapi");
        SystemProxySession proxy(nullptr,journal);
        QVERIFY2(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()),qPrintable(proxy.error()));
        QVERIFY(proxy.enabled());QVERIFY(proxy.owned());
        QVERIFY2(proxy.error().isEmpty(),qPrintable(proxy.error()));
        // Verify both WinINET options and the registry view read by native
        // clients. Windows may reflect a registry edit in WinINET immediately.
        QSettings internet(QStringLiteral("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"),QSettings::NativeFormat);
        internet.sync();
        QCOMPARE(internet.value("ProxyEnable").toInt(),1);
        QVERIFY2(internet.value("ProxyServer").toString()==QStringLiteral("127.0.0.1:%1").arg(server.serverPort()),"Registry proxy does not match the intended fixture listener; raw value omitted.");
        QVERIFY2(internet.value("ProxyOverride").toString()==SystemProxySession::snapshot().value("bypass").toString(),"Registry and WinINET bypass values differ; raw values are intentionally omitted.");
        QFile encrypted(journal);QVERIFY(encrypted.open(QIODevice::ReadOnly));
        QVERIFY(!encrypted.readAll().contains("127.0.0.1"));encrypted.close();
        proxy.disable();
        QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy()&&!proxy.owned(),5000);
        QVERIFY2(proxy.error().isEmpty(),qPrintable(proxy.error()));
        QVERIFY2(SystemProxySession::snapshot()==original,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
        QVERIFY(!QFile::exists(journal));
        QVERIFY2(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()),qPrintable(proxy.error()));
        QVERIFY2(proxy.error().isEmpty(),qPrintable(proxy.error()));
        const auto external=configuredProxy(original,3,"127.0.0.1:65001");
        QString error;QVERIFY2(SystemProxySession::apply(external,&error),qPrintable(error));
        QLockFile releaseLock(journal+".lock");
        QVERIFY(releaseLock.tryLock(1000));
        QSignalSpy released(&proxy,&SystemProxySession::releaseFinished);
        QVERIFY(!proxy.disable());
        QVERIFY(proxy.busy());
        QCOMPARE(released.count(),0);
        releaseLock.unlock();
        QTRY_COMPARE_WITH_TIMEOUT(released.count(),1,5000);
        QVERIFY2(released.first().at(0).toBool(),qPrintable(proxy.error()));
        QVERIFY(!proxy.busy());QVERIFY(!proxy.owned());
        QVERIFY2(SystemProxySession::snapshot()==external,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
        QTRY_VERIFY_WITH_TIMEOUT(!QFile::exists(journal)&&QDir(temp.path()).entryList({"*.ready"},QDir::Files).isEmpty(),5000);
        QVERIFY(SystemProxySession::apply(original));
        QVERIFY(!proxy.enable(0,0));QVERIFY2(SystemProxySession::snapshot()==original,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
    }
    void abruptOwnerExit() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QVERIFY(temp.isValid());
        QProcess child;child.setProgram(QCoreApplication::applicationFilePath());
        child.setArguments({"--crash-fixture",temp.filePath("proxy.dpapi")});
        child.start();QVERIFY(child.waitForStarted(3000));
        QVERIFY(child.waitForReadyRead(5000));QCOMPARE(child.readAllStandardOutput().trimmed(),QByteArray("enabled"));
        QVERIFY(SystemProxySession::snapshot()!=original);
        child.kill();QVERIFY(child.waitForFinished(3000));
        QTRY_VERIFY_WITH_TIMEOUT(SystemProxySession::snapshot()==original,5000);
        QTRY_VERIFY_WITH_TIMEOUT(!QFile::exists(temp.filePath("proxy.dpapi")),5000);
    }
    void registryOnlyExternalEdit() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        const auto journal=temp.filePath("registry-proxy.dpapi");
        SystemProxySession proxy(nullptr,journal);QVERIFY(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()));
        const auto owned=SystemProxySession::snapshot();
        QSettings internet(QStringLiteral("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"),QSettings::NativeFormat);
        internet.setValue("ProxyServer","127.0.0.1:65002");internet.sync();
        QCOMPARE(internet.status(),QSettings::NoError);
        const auto external=SystemProxySession::snapshot();
        QVERIFY2(internet.value("ProxyServer").toString()==QStringLiteral("127.0.0.1:65002"),"Registry did not retain the fixture external edit; raw value omitted.");
        const auto actualServer=external.value("registry").toObject().value("ProxyServer");
        const auto expectedServer=configuredProxy(original,3,"127.0.0.1:65002").value("registry").toObject().value("ProxyServer");
        QVERIFY2(actualServer==expectedServer,"Registry proxy bytes differ from the expected fixture; raw values omitted.");QVERIFY(actualServer!=owned.value("registry").toObject().value("ProxyServer"));
        proxy.refresh();QVERIFY(!proxy.owned());QVERIFY(!proxy.enabled());
        QVERIFY(proxy.disable());QVERIFY2(SystemProxySession::snapshot()==external,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
        QVERIFY(!QFile::exists(journal));
    }
    void restoreDistinctStoresAndAbsentValues() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QSettings internet(QStringLiteral("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"),QSettings::NativeFormat);
        internet.setValue("ProxyServer","127.0.0.1:65003");
        internet.setValue("ProxyEnable",0);internet.remove("ProxyOverride");internet.remove("AutoConfigURL");internet.sync();
        const auto distinct=SystemProxySession::snapshot();
        QCOMPARE(distinct.value("registry").toObject().value("AutoConfigURL").toObject().value("present").toBool(),false);
        QTemporaryDir temp;QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        SystemProxySession proxy(nullptr,temp.filePath("distinct.dpapi"));
        QVERIFY(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()));
        QVERIFY(proxy.disable());QVERIFY2(SystemProxySession::snapshot()==distinct,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
    }
    void malformedRegistryDoesNotMutateSettings() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        auto invalid=original;invalid.insert("server","127.0.0.1:65004");invalid.insert("registry",QJsonObject{});
        QString error;QVERIFY(!SystemProxySession::apply(invalid,&error));QVERIFY(!error.isEmpty());
        QVERIFY2(SystemProxySession::snapshot()==original,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
    }
    void inconsistentRepresentationsCannotLeavePartialSettings() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        auto inconsistent=original;
        inconsistent.insert("flags",original.value("flags").toInt()^2);
        inconsistent.insert("server","127.0.0.1:65008");
        // Retain the old registry deliberately. A rejected write must not leave
        // WinINET's manual bit changed while its other view retains old values.
        QString error;QVERIFY(!SystemProxySession::apply(inconsistent,&error));QVERIFY(!error.isEmpty());
        QVERIFY2(SystemProxySession::snapshot()==original,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
    }
    void legacyJournalRecoveryPreservesRegistry() {
#ifdef Q_OS_WIN
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        const auto applied=configuredProxy(original,3,"127.0.0.1:65005");
        QString error;QVERIFY2(SystemProxySession::apply(applied,&error),qPrintable(error));
        QVERIFY2(SystemProxySession::snapshot()==applied,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");
        auto legacyOriginal=original;legacyOriginal.remove("registry");
        auto legacyApplied=applied;legacyApplied.remove("registry");
        QJsonObject record{{"schema",1},{"original",legacyOriginal},{"applied",legacyApplied}};
        auto plain=QJsonDocument(record).toJson(QJsonDocument::Compact);QByteArray entropy("Swirl.SystemProxy.v1");
        DATA_BLOB input{DWORD(plain.size()),reinterpret_cast<BYTE *>(plain.data())};
        DATA_BLOB context{DWORD(entropy.size()),reinterpret_cast<BYTE *>(entropy.data())},encrypted{};
        QVERIFY(CryptProtectData(&input,L"legacy test",&context,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&encrypted));
        const QByteArray bytes(reinterpret_cast<const char *>(encrypted.pbData),encrypted.cbData);
        SecureZeroMemory(encrypted.pbData,encrypted.cbData);LocalFree(encrypted.pbData);
        QTemporaryDir temp;const auto journal=temp.filePath("legacy.dpapi");
        QFile file(journal);QVERIFY(file.open(QIODevice::WriteOnly));QCOMPARE(file.write(bytes),bytes.size());file.close();
        // Schema 1 never recorded ownership/original bytes of the registry.
        // It cannot safely restore different native fields on Windows where
        // those fields alias the registry. Keep the journal and exact settings.
        QVERIFY(!SystemProxySession::recover(journal,&error,false));QVERIFY(!error.isEmpty());
        QVERIFY2(SystemProxySession::snapshot()==applied,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");QVERIFY(QFile::exists(journal));
        QVERIFY2(SystemProxySession::apply(original,&error),qPrintable(error));
        QVERIFY(SystemProxySession::recover(journal,&error,false));
        QVERIFY2(SystemProxySession::snapshot()==original,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");QVERIFY(!QFile::exists(journal));
        // An already-restored legacy record may also be cleaned without taking
        // ownership of or rewriting its unrecorded registry representation.
        record.insert("applied",legacyOriginal);
        plain=QJsonDocument(record).toJson(QJsonDocument::Compact);
        input={DWORD(plain.size()),reinterpret_cast<BYTE *>(plain.data())};encrypted={};
        QVERIFY(CryptProtectData(&input,L"legacy test",&context,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&encrypted));
        const QByteArray sameBytes(reinterpret_cast<const char *>(encrypted.pbData),encrypted.cbData);
        SecureZeroMemory(encrypted.pbData,encrypted.cbData);LocalFree(encrypted.pbData);
        QVERIFY(file.open(QIODevice::WriteOnly));QCOMPARE(file.write(sameBytes),sameBytes.size());file.close();
        QVERIFY(SystemProxySession::recover(journal,&error,false));
        QVERIFY2(SystemProxySession::snapshot()==original,"Proxy snapshot differs; raw proxy/PAC/bypass values are intentionally omitted.");QVERIFY(!QFile::exists(journal));
#endif
    }
    void abruptEngineExit() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost,0));
        QProcess engine;engine.setProgram(QCoreApplication::applicationFilePath());engine.setArguments({"--engine-fixture"});
        engine.start();QVERIFY(engine.waitForStarted(3000));
        SystemProxySession proxy(nullptr,temp.filePath("engine-proxy.dpapi"));
        QVERIFY(proxy.enable(listener.serverPort(),engine.processId()));
        engine.kill();QVERIFY(engine.waitForFinished(3000));
        QTRY_VERIFY_WITH_TIMEOUT(SystemProxySession::snapshot()==original,5000);
        proxy.refresh();QVERIFY(!proxy.owned());QVERIFY(!proxy.enabled());
    }
};
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);app.setApplicationName("SwirlProxyTests");app.setOrganizationName("SOLHK");
    if(qEnvironmentVariable("SWIRL_SYSTEM_PROXY_TEST")!=QStringLiteral("1")){
        qCritical("System proxy mutation tests require an explicitly opted-in disposable Windows runner.");return 2;
    }
    if(app.arguments().contains("--engine-fixture"))return app.exec();
    if(app.arguments().contains("--crash-fixture")) {
        QTcpServer server;if(!server.listen(QHostAddress::LocalHost,0))return 2;
        SystemProxySession proxy(nullptr,app.arguments().last());
        if(!proxy.enable(server.serverPort(),app.applicationPid()))return 3;
        std::fputs("enabled\n",stdout);std::fflush(stdout);return app.exec();
    }
    ProxyTests tests;return QTest::qExec(&tests,argc,argv);
}
#include "SystemProxyTests.moc"
