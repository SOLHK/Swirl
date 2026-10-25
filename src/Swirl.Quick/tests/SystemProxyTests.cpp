#include "engine/SystemProxySession.h"
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
#ifdef Q_OS_WIN
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
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
}

class ProxyTests : public QObject {
    Q_OBJECT
private slots:
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
        QCOMPARE(SystemProxySession::snapshot(),original);
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
        QCOMPARE(SystemProxySession::snapshot(),original);QVERIFY(!QFile::exists(journal));
        otherProcess.unlock();completed.clear();
        QVERIFY(proxy.requestEnable(listener.serverPort(),QCoreApplication::applicationPid()));
        QTRY_COMPARE_WITH_TIMEOUT(completed.count(),1,5000);
        QVERIFY2(completed.first().at(1).toBool(),qPrintable(proxy.error()));QVERIFY(proxy.owned());
        QVERIFY(proxy.diagnosticState().value("guardAcknowledged").toBool());
        proxy.disable();QTRY_VERIFY_WITH_TIMEOUT(!proxy.busy()&&!proxy.owned(),5000);
        QCOMPARE(SystemProxySession::snapshot(),original);
    }
    void explicitOffDisablesExternalAndOwnedProxy() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        QTemporaryDir temp;QTcpServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));
        const auto external=configuredProxy(original,7,"127.0.0.1:65006","http://127.0.0.1:65007/test.pac");
        QString error;QVERIFY2(SystemProxySession::apply(external,&error),qPrintable(error));
        QCOMPARE(SystemProxySession::snapshot(),external);
        SystemProxySession proxy(nullptr,temp.filePath("explicit-off.dpapi"));
        proxy.refresh();QVERIFY(proxy.systemEnabled());QVERIFY(!proxy.owned());
        QVERIFY2(proxy.turnOffSystemProxy(),qPrintable(proxy.error()));
        QVERIFY(!proxy.systemEnabled());QVERIFY(!proxy.owned());
        const auto off=SystemProxySession::snapshot();
        QCOMPARE(off.value("flags").toInt(),1);QVERIFY(off.value("pac").toString().isEmpty());
        QVERIFY(!off.value("registry").toObject().value("AutoConfigURL").toObject().value("present").toBool());
        const auto pacOnly=configuredProxy(external,5,"127.0.0.1:65006","http://127.0.0.1:65007/test.pac");
        QVERIFY2(SystemProxySession::apply(pacOnly,&error),qPrintable(error));QCOMPARE(SystemProxySession::snapshot(),pacOnly);proxy.refresh();QVERIFY(proxy.systemEnabled());
        QVERIFY(proxy.turnOffSystemProxy());QVERIFY(!proxy.systemEnabled());
        const auto automatic=configuredProxy(external,9,"127.0.0.1:65006");
        QVERIFY2(SystemProxySession::apply(automatic,&error),qPrintable(error));QCOMPARE(SystemProxySession::snapshot(),automatic);proxy.refresh();QVERIFY(proxy.systemEnabled());
        QVERIFY(proxy.turnOffSystemProxy());QVERIFY(!proxy.systemEnabled());
        QVERIFY(SystemProxySession::apply(external));
        QVERIFY(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()));
        QVERIFY(proxy.systemEnabled());QVERIFY(proxy.owned());
        QVERIFY2(proxy.turnOffSystemProxy(),qPrintable(proxy.error()));
        QVERIFY(!proxy.systemEnabled());QVERIFY(!proxy.owned());QVERIFY(!proxy.enabled());
        QVERIFY(!QFile::exists(temp.filePath("explicit-off.dpapi")));
        QVERIFY(proxy.disable()); // Exit/release cannot restore the old external proxy.
        QCOMPARE(SystemProxySession::snapshot(),off);
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
        // Verify both WinINET options and the registry view read by native
        // clients. Windows may reflect a registry edit in WinINET immediately.
        QSettings internet(QStringLiteral("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings"),QSettings::NativeFormat);
        internet.sync();
        QCOMPARE(internet.value("ProxyEnable").toInt(),1);
        QCOMPARE(internet.value("ProxyServer").toString(),QStringLiteral("127.0.0.1:%1").arg(server.serverPort()));
        QCOMPARE(internet.value("ProxyOverride").toString(),SystemProxySession::snapshot().value("bypass").toString());
        QFile encrypted(journal);QVERIFY(encrypted.open(QIODevice::ReadOnly));
        QVERIFY(!encrypted.readAll().contains("127.0.0.1"));encrypted.close();
        QVERIFY(proxy.disable());QCOMPARE(SystemProxySession::snapshot(),original);
        QVERIFY(proxy.enable(server.serverPort(),QCoreApplication::applicationPid()));
        const auto external=configuredProxy(original,3,"127.0.0.1:65001");
        QString error;QVERIFY2(SystemProxySession::apply(external,&error),qPrintable(error));
        QVERIFY(proxy.disable());QCOMPARE(SystemProxySession::snapshot(),external);
        QVERIFY(SystemProxySession::apply(original));
        QVERIFY(!proxy.enable(0,0));QCOMPARE(SystemProxySession::snapshot(),original);
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
        QTRY_COMPARE_WITH_TIMEOUT(SystemProxySession::snapshot(),original,5000);
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
        QCOMPARE(internet.value("ProxyServer").toString(),QStringLiteral("127.0.0.1:65002"));
        const auto actualServer=external.value("registry").toObject().value("ProxyServer");
        const auto expectedServer=configuredProxy(original,3,"127.0.0.1:65002").value("registry").toObject().value("ProxyServer");
        QCOMPARE(actualServer,expectedServer);QVERIFY(actualServer!=owned.value("registry").toObject().value("ProxyServer"));
        proxy.refresh();QVERIFY(!proxy.owned());QVERIFY(!proxy.enabled());
        QVERIFY(proxy.disable());QCOMPARE(SystemProxySession::snapshot(),external);
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
        QVERIFY(proxy.disable());QCOMPARE(SystemProxySession::snapshot(),distinct);
    }
    void malformedRegistryDoesNotMutateSettings() {
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        auto invalid=original;invalid.insert("server","127.0.0.1:65004");invalid.insert("registry",QJsonObject{});
        QString error;QVERIFY(!SystemProxySession::apply(invalid,&error));QVERIFY(!error.isEmpty());
        QCOMPARE(SystemProxySession::snapshot(),original);
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
        QCOMPARE(SystemProxySession::snapshot(),original);
    }
    void legacyJournalRecoveryPreservesRegistry() {
#ifdef Q_OS_WIN
        const auto original=SystemProxySession::snapshot();QVERIFY(!original.isEmpty());
        struct Restore {QJsonObject value;~Restore(){SystemProxySession::apply(value);}} restore{original};
        const auto applied=configuredProxy(original,3,"127.0.0.1:65005");
        QString error;QVERIFY2(SystemProxySession::apply(applied,&error),qPrintable(error));
        QCOMPARE(SystemProxySession::snapshot(),applied);
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
        QCOMPARE(SystemProxySession::snapshot(),applied);QVERIFY(QFile::exists(journal));
        QVERIFY2(SystemProxySession::apply(original,&error),qPrintable(error));
        QVERIFY(SystemProxySession::recover(journal,&error,false));
        QCOMPARE(SystemProxySession::snapshot(),original);QVERIFY(!QFile::exists(journal));
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
        QCOMPARE(SystemProxySession::snapshot(),original);QVERIFY(!QFile::exists(journal));
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
        QTRY_COMPARE_WITH_TIMEOUT(SystemProxySession::snapshot(),original,5000);
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
