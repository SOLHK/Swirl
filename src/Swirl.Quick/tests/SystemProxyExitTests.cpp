#include "SystemProxyExitFixture.h"
#include "SwirlBuildIdentity.h"
#include "engine/SystemProxySession.h"
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QFile>
#include <QJsonDocument>
#include <QLocalSocket>
#include <QNetworkProxy>
#include <QProcess>
#include <QProcessEnvironment>
#include <QSaveFile>
#include <QScopeGuard>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include <QTest>
#include <QtEndian>
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winhttp.h>

namespace {
QJsonObject winHttpSnapshot() {
    WINHTTP_PROXY_INFO info{};
    const bool ok=WinHttpGetDefaultProxyConfiguration(&info);
    const auto release=qScopeGuard([&]{
        if(info.lpszProxy)GlobalFree(info.lpszProxy);
        if(info.lpszProxyBypass)GlobalFree(info.lpszProxyBypass);
    });
    if(!ok)return {};
    return {{"accessType",double(info.dwAccessType)},
        {"proxyPresent",info.lpszProxy!=nullptr},
        {"proxy",QString::fromWCharArray(info.lpszProxy?info.lpszProxy:L"")},
        {"bypassPresent",info.lpszProxyBypass!=nullptr},
        {"bypass",QString::fromWCharArray(info.lpszProxyBypass?info.lpszProxyBypass:L"")}};
}
QJsonObject configuredProxy(QJsonObject value,int flags,const QString &server,const QString &pac,const QString &bypass) {
    value.insert("flags",flags);value.insert("server",server);value.insert("pac",pac);value.insert("bypass",bypass);
    auto registry=value.value("registry").toObject();
    QByteArray enabled(4,Qt::Uninitialized);qToLittleEndian<quint32>((flags&2)!=0,enabled.data());
    registry.insert("ProxyEnable",QJsonObject{{"present",true},{"type",4},{"data",QString::fromLatin1(enabled.toBase64())}});
    const QString values[]={server,bypass,pac};
    const char *names[]={"ProxyServer","ProxyOverride","AutoConfigURL"};
    for(int index=0;index<3;++index){
        // Native takeover writes an explicit empty REG_SZ for AutoConfigURL.
        // Absence is a different raw registry state and must not be substituted.
        const QByteArray bytes(reinterpret_cast<const char *>(values[index].utf16()),(values[index].size()+1)*2);
        registry.insert(names[index],QJsonObject{{"present",true},{"type",1},{"data",QString::fromLatin1(bytes.toBase64())}});
    }
    value.insert("registry",registry);return value;
}
QJsonObject readReceipt(const QString &path) {
    QFile file(path);
    if(!file.open(QIODevice::ReadOnly)||file.size()>65536)return {};
    return QJsonDocument::fromJson(file.readAll()).object();
}
bool writeReceipt(const QString &path,const QJsonObject &report) {
    QSaveFile file(path);file.setDirectWriteFallback(false);
    const auto bytes=QJsonDocument(report).toJson();
    return file.open(QIODevice::WriteOnly)&&file.write(bytes)==bytes.size()&&file.commit();
}
bool preserveEvidence(const QString &root,const QString &tag,const QJsonObject &result) {
    const auto evidence=qEnvironmentVariable("SWIRL_SYSTEM_PROXY_EXIT_EVIDENCE");
    if(evidence.isEmpty())return true;
    if(!QDir().mkpath(evidence))return false;
    for(const auto &entry:QList<QPair<QString,QString>>{
        {SwirlSystemProxyExit::readyPath(root),tag+"-ready.json"},
        {SwirlSystemProxyExit::finalPath(root),tag+"-final.json"}}){
        if(!QFile::exists(entry.first))continue;
        const auto destination=QDir(evidence).filePath(entry.second);
        QFile::remove(destination);
        if(!QFile::copy(entry.first,destination))return false;
    }
    return writeReceipt(QDir(evidence).filePath(tag+"-result.json"),result);
}
bool requestWindowClose(const QString &root) {
    QLocalSocket socket;socket.connectToServer(SwirlSystemProxyExit::controlName(root));
    if(!socket.waitForConnected(1000))return false;
    if(socket.write("CLOSE\n")!=6)return false;
    socket.flush();
    if(socket.bytesToWrite()&&!socket.waitForBytesWritten(1000))return false;
    QByteArray response;
    const bool received=QTest::qWaitFor([&]{response+=socket.readAll();return response.size()>=8;},1500);
    return received&&response==QByteArray("CLOSING\n");
}
bool connectTcp(QTcpSocket &socket,quint16 port) {
    socket.setProxy(QNetworkProxy::NoProxy);socket.connectToHost(QHostAddress::LocalHost,port);
    const bool finished=QTest::qWaitFor([&]{return socket.state()==QAbstractSocket::ConnectedState||socket.state()==QAbstractSocket::UnconnectedState;},3000);
    return finished&&socket.state()==QAbstractSocket::ConnectedState;
}
QByteArray readBytes(QTcpSocket &socket,qsizetype count) {
    QByteArray bytes;
    if(!QTest::qWaitFor([&]{bytes+=socket.read(qMax<qsizetype>(0,count-bytes.size()));return bytes.size()==count||socket.state()==QAbstractSocket::UnconnectedState;},3000))return {};
    return bytes;
}
bool readHttpReply(QTcpSocket &socket,const QByteArray &body) {
    QByteArray response;
    const bool closed=QTest::qWaitFor([&]{response+=socket.readAll();return socket.state()==QAbstractSocket::UnconnectedState;},5000);
    return closed&&response.startsWith("HTTP/1.1 200 OK\r\n")
        &&response.contains("\r\n\r\n")&&response.endsWith("\r\n\r\n"+body);
}
bool httpRoundTrip(quint16 proxyPort,quint16 originPort) {
    QTcpSocket socket;if(!connectTcp(socket,proxyPort))return false;
    const auto authority=QByteArray("127.0.0.1:")+QByteArray::number(originPort);
    socket.write("GET http://"+authority+"/http-check HTTP/1.1\r\nHost: "+authority+"\r\nConnection: close\r\n\r\n");
    return readHttpReply(socket,"swirl-native-exit-http");
}
bool socksRoundTrip(quint16 proxyPort,quint16 originPort) {
    QTcpSocket socket;if(!connectTcp(socket,proxyPort))return false;
    socket.write(QByteArray::fromHex("050100"));
    if(readBytes(socket,2)!=QByteArray::fromHex("0500"))return false;
    auto connect=QByteArray::fromHex("050100017f000001");
    connect.append(char(originPort>>8));connect.append(char(originPort&255));socket.write(connect);
    const auto reply=readBytes(socket,10);
    if(reply.size()!=10||reply.first(4)!=QByteArray::fromHex("05000001"))return false;
    socket.write("GET /socks-check HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
    return readHttpReply(socket,"swirl-native-exit-socks");
}
struct ListenerProbe {
    bool terminalObserved=false;
    bool connected=false;
    bool errorObserved=false;
    QAbstractSocket::SocketError signalError=QAbstractSocket::UnknownSocketError;
    QAbstractSocket::SocketState socketState=QAbstractSocket::UnconnectedState;
    QAbstractSocket::SocketError socketError=QAbstractSocket::UnknownSocketError;
    qint64 elapsedMs=0;
    bool refused() const {
        return terminalObserved&&!connected&&errorObserved
            &&signalError==QAbstractSocket::ConnectionRefusedError
            &&socketState==QAbstractSocket::UnconnectedState
            &&socketError==QAbstractSocket::ConnectionRefusedError;
    }
    QJsonObject report() const {
        const QString outcome=refused()?QStringLiteral("refused"):
            connected?QStringLiteral("connected"):
            !terminalObserved?QStringLiteral("deadline"):
            errorObserved?QStringLiteral("error"):QStringLiteral("unknown");
        return {{"deadline_ms",3000},{"terminal_observed",terminalObserved},
            {"connected",connected},{"error_observed",errorObserved},
            {"signal_error",int(signalError)},{"socket_state",int(socketState)},
            {"socket_error",int(socketError)},{"elapsed_ms",double(elapsedMs)},
            {"refused",refused()},{"outcome",outcome}};
    }
};
ListenerProbe probeListener(quint16 port) {
    ListenerProbe probe;
    QTcpSocket socket;socket.setProxy(QNetworkProxy::NoProxy);
    QObject::connect(&socket,&QTcpSocket::connected,&socket,[&]{probe.connected=true;});
    QObject::connect(&socket,&QTcpSocket::errorOccurred,&socket,[&](QAbstractSocket::SocketError error){
        probe.errorObserved=true;probe.signalError=error;
    });
    QElapsedTimer elapsed;elapsed.start();
    socket.connectToHost(QHostAddress::LocalHost,port);
    // Windows can complete a refused loopback connection after SYN retries.
    // Observe the actual terminal event within the same finite budget used
    // for successful test connections; elapsed time is never proof of closure.
    probe.terminalObserved=QTest::qWaitFor([&]{return probe.connected
        ||(probe.errorObserved&&socket.state()==QAbstractSocket::UnconnectedState);},3000);
    probe.elapsedMs=elapsed.elapsed();probe.socketState=socket.state();probe.socketError=socket.error();
    return probe;
}
QJsonObject legacyListenerProbe(quint16 port) {
    QTcpSocket socket;socket.setProxy(QNetworkProxy::NoProxy);
    QElapsedTimer elapsed;elapsed.start();
    socket.connectToHost(QHostAddress::LocalHost,port);
    // Preserve the exact previous predicate as a measurement on a known
    // closed control port. Future Windows versions may complete it promptly.
    const bool finished=QTest::qWaitFor([&]{return socket.state()==QAbstractSocket::ConnectedState||socket.state()==QAbstractSocket::UnconnectedState;},1500);
    const bool refused=finished&&socket.state()==QAbstractSocket::UnconnectedState&&socket.error()==QAbstractSocket::ConnectionRefusedError;
    return {{"deadline_ms",1500},{"finished",finished},{"socket_state",int(socket.state())},
        {"socket_error",int(socket.error())},{"elapsed_ms",double(elapsed.elapsed())},{"predicate_result",refused}};
}
}

class SystemProxyExitTests final : public QObject {
    Q_OBJECT
    QJsonObject m_winHttpBefore;
    bool m_orphanOwner=false;
private slots:
    void init() {
        QVERIFY2(!m_orphanOwner,"A previous application owner is still alive; no further native proxy mutation is allowed.");
        m_winHttpBefore=winHttpSnapshot();
        QVERIFY2(!m_winHttpBefore.isEmpty(),"The read-only machine WinHTTP snapshot failed.");
    }
    void cleanup() {
        if(m_winHttpBefore.isEmpty())return;
        const auto after=winHttpSnapshot();
        QVERIFY2(!after.isEmpty()&&after==m_winHttpBefore,"The application exit changed machine-wide WinHTTP settings; private values omitted.");
    }
    void ownedSnapshotDistinguishesEmptyPacFromAbsentRegistry() {
        const auto owned=configuredProxy({},3,QStringLiteral("127.0.0.1:65009"),{},QStringLiteral("<local>"));
        const auto registry=owned.value("registry").toObject();
        const auto pac=registry.value("AutoConfigURL").toObject();
        QVERIFY2(pac.value("present").isBool()&&pac.value("present").toBool(),
                 "Owned empty PAC must remain a present registry value.");
        QCOMPARE(pac.value("type").toInt(),int(REG_SZ));
        QCOMPARE(QByteArray::fromBase64(pac.value("data").toString().toLatin1()),QByteArray(2,'\0'));
        auto absent=owned;auto absentRegistry=registry;
        absentRegistry.insert("AutoConfigURL",QJsonObject{{"present",false}});
        absent.insert("registry",absentRegistry);
        QVERIFY2(owned!=absent,"Exact snapshot equality must distinguish an empty REG_SZ from an absent PAC value.");
    }
    void listenerProbeDistinguishesClosedAndLivePorts() {
        QJsonObject report{{"schema",1},{"source_sha",QStringLiteral(SWIRL_SOURCE_SHA)},{"success",false}};
        bool completed=false;
        const auto preserve=qScopeGuard([&]{
            report.insert("success",completed&&!QTest::currentTestFailed());
            const auto evidence=qEnvironmentVariable("SWIRL_SYSTEM_PROXY_EXIT_EVIDENCE");
            if(!evidence.isEmpty()&&(!QDir().mkpath(evidence)
                ||!writeReceipt(QDir(evidence).filePath("listener-probe-controls.json"),report)))
                QTest::qFail("Could not preserve safe closed/live listener probe controls.",__FILE__,__LINE__);
        });
        QTcpServer closed;closed.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(closed.listen(QHostAddress::LocalHost));
        const auto closedPort=closed.serverPort();closed.close();QVERIFY(!closed.isListening());
        report.insert("legacy",QJsonObject{{"closed",legacyListenerProbe(closedPort)}});
        const auto closedProbe=probeListener(closedPort);
        QJsonObject current{{"closed",closedProbe.report()}};report.insert("current",current);
        QVERIFY2(closedProbe.refused(),"A known-closed control port must produce an explicit connection refusal.");

        QTcpServer live;live.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(live.listen(QHostAddress::LocalHost));
        const auto liveProbe=probeListener(live.serverPort());
        current.insert("live",liveProbe.report());report.insert("current",current);
        QVERIFY2(liveProbe.terminalObserved&&liveProbe.connected,"The live control must produce an observed connection.");
        QVERIFY2(!liveProbe.refused(),"A live listener must never be accepted as closed.");
        completed=true;
    }
    void normalApplicationExitRestoresOwnedProxy_data() {
        QTest::addColumn<int>("flags");QTest::addColumn<bool>("externalEdit");
        QTest::newRow("pac-only")<<5<<false;
        QTest::newRow("manual-and-pac")<<7<<false;
        QTest::newRow("pac-only-external-edit")<<5<<true;
        QTest::newRow("manual-and-pac-external-edit")<<7<<true;
    }
    void normalApplicationExitRestoresOwnedProxy() {
        QFETCH(int,flags);QFETCH(bool,externalEdit);
        const auto original=SystemProxySession::snapshot();
        QVERIFY2(!original.isEmpty(),"Could not read the original native proxy snapshot.");
        QTemporaryDir root;QVERIFY(root.isValid());
        QProcess child;
        const auto journal=root.filePath("data/system-proxy.dpapi");
        const QString tag=QString::fromLatin1(QTest::currentDataTag());
        QJsonObject result{{"schema",1},{"source_sha",QStringLiteral(SWIRL_SOURCE_SHA)},
            {"data_tag",tag},{"flags",flags},{"external_edit",externalEdit},{"success",false}};
        bool completed=false;
        const auto restore=qScopeGuard([&]{
            // Close the actual app first, including on an assertion failure.
            // Never race a still-running owner by restoring the runner early.
            if(child.state()!=QProcess::NotRunning){
                requestWindowClose(root.path());
                if(!QTest::qWaitFor([&]{return child.state()==QProcess::NotRunning;},5000)){
                    child.kill();child.waitForFinished(3000);
                }
            }
            const bool stopped=child.state()==QProcess::NotRunning;
            result.insert("child_stopped",stopped);
            if(!stopped){
                // Preserve the encrypted recovery journal for its still-live
                // owner/guard. Neither this row nor a later row may overwrite
                // native settings while that owner could still write them.
                m_orphanOwner=true;root.setAutoRemove(false);
                result.insert("runner_original_restored",false);
                QTest::qFail("Could not stop the application owner; original native state was not written over a live owner.",__FILE__,__LINE__);
                if(!preserveEvidence(root.path(),tag,result))
                    QTest::qFail("Could not preserve safe failure receipts.",__FILE__,__LINE__);
                return;
            }
            if(QFile::exists(journal))SystemProxySession::recover(journal,nullptr,true);
            const bool restored=SystemProxySession::apply(original)&&SystemProxySession::snapshot()==original;
            result.insert("runner_original_restored",restored);
            if(!restored)QTest::qFail("Could not restore the disposable runner's original native proxy; private values omitted.",__FILE__,__LINE__);
            const auto winHttpAfter=winHttpSnapshot();
            const bool winHttpUnchanged=!winHttpAfter.isEmpty()&&winHttpAfter==m_winHttpBefore;
            result.insert("winhttp_unchanged",winHttpUnchanged);
            result.insert("success",completed&&restored&&winHttpUnchanged&&!QTest::currentTestFailed());
            result.insert("child_exit_code",child.exitCode());
            result.insert("child_normal_exit",child.exitStatus()==QProcess::NormalExit);
            if(!preserveEvidence(root.path(),tag,result))
                QTest::qFail("Could not preserve the safe proxy-exit receipts and result.",__FILE__,__LINE__);
        });

        const QString pac=QStringLiteral("http://127.0.0.1:65010/swirl-exit-fixture.pac?revision=before");
        const QString bypass=QStringLiteral("localhost;*.swirl-exit.invalid;10.42.*;[::1];<local>");
        const auto fixture=configuredProxy(original,flags,QStringLiteral("127.0.0.1:65009"),pac,bypass);
        QVERIFY2(SystemProxySession::apply(fixture),"The synthetic PAC/bypass fixture could not be applied.");
        QVERIFY2(SystemProxySession::snapshot()==fixture,"The synthetic PAC/bypass fixture was not applied exactly.");

        QTcpServer origin;origin.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(origin.listen(QHostAddress::LocalHost));
        int httpRequests=0,socksRequests=0;
        connect(&origin,&QTcpServer::newConnection,&origin,[&]{
            while(auto *socket=origin.nextPendingConnection()){
                connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
                const auto respond=[&,socket]{
                    if(socket->property("answered").toBool())return;
                    const auto bytes=socket->property("request").toByteArray()+socket->readAll();
                    if(bytes.size()>8192){socket->abort();return;}
                    socket->setProperty("request",bytes);
                    if(!bytes.contains("\r\n\r\n"))return;
                    QByteArray body;
                    if(bytes.startsWith("GET /http-check HTTP/1.1\r\n")){++httpRequests;body="swirl-native-exit-http";}
                    else if(bytes.startsWith("GET /socks-check HTTP/1.1\r\n")){++socksRequests;body="swirl-native-exit-socks";}
                    else {socket->abort();return;}
                    socket->setProperty("answered",true);
                    socket->write("HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: "+QByteArray::number(body.size())+"\r\n\r\n"+body);
                    socket->disconnectFromHost();
                };
                connect(socket,&QTcpSocket::readyRead,socket,respond);
                if(socket->bytesAvailable())respond();
            }
        });
        const auto executable=QDir(QCoreApplication::applicationDirPath()).filePath("Swirl.exe");
        QVERIFY2(QFileInfo(executable).isFile(),"The separately built full Swirl application is missing.");
        auto environment=QProcessEnvironment::systemEnvironment();
        environment.insert("SWIRL_SYSTEM_PROXY_TEST","1");
        environment.insert("SWIRL_LIFECYCLE_SYSTEM_PROXY","1");
        environment.insert("SWIRL_LIFECYCLE_ENGINE","rust");
        environment.insert("SWIRL_TEST_ROOT",root.path());
        child.setProcessEnvironment(environment);child.setProgram(executable);
        child.setArguments({"--lifecycle-test"});child.setWorkingDirectory(root.path());
        child.start();QVERIFY2(child.waitForStarted(3000),"The full Swirl lifecycle application did not start.");
        const auto pid=child.processId();
        QJsonObject ready;
        const bool announced=QTest::qWaitFor([&]{
            ready=readReceipt(SwirlSystemProxyExit::readyPath(root.path()));
            return !ready.isEmpty()||child.state()==QProcess::NotRunning;
        },15000);
        QVERIFY2(announced&&!ready.isEmpty(),"The full application did not acquire native system proxy with a healthy Rust listener.");
        QCOMPARE(ready.value("source_sha").toString(),QStringLiteral(SWIRL_SOURCE_SHA));
        QCOMPARE(ready.value("phase").toString(),QStringLiteral("ready"));
        QCOMPARE(qint64(ready.value("pid").toDouble()),pid);
        QCOMPARE(qint64(ready.value("runtime_pid").toDouble()),pid);
        for(const auto *key:{"native_backend","ready","runtime_alive","runtime_healthy","proxy_owned","proxy_enabled",
                             "native_listener_matches_rust","saved_applied_policy_matches","guard_acknowledged"})
            QVERIFY2(ready.value(key).isBool()&&ready.value(key).toBool(),key);
        QVERIFY(ready.value("fixture_failed").isBool()&&!ready.value("fixture_failed").toBool());
        const int port=ready.value("rust_port").toInt();QVERIFY(port>0&&port<=65535);
        result.insert("runtime_port",port);result.insert("pid",double(pid));
        const auto owned=SystemProxySession::snapshot();
        const auto expectedOwned=configuredProxy(owned,3,QStringLiteral("127.0.0.1:%1").arg(port),{},owned.value("bypass").toString());
        QVERIFY2(!owned.isEmpty()&&owned==expectedOwned,"WinINET and the raw registry do not both point to the real Rust listener.");
        const auto winHttpDuring=winHttpSnapshot();
        QVERIFY2(!winHttpDuring.isEmpty()&&winHttpDuring==m_winHttpBefore,"Native takeover modified machine WinHTTP; private values omitted.");
        QVERIFY2(httpRoundTrip(quint16(port),origin.serverPort()),"The system-proxy port did not relay the actual HTTP fixture through Rust.");
        QCOMPARE(httpRequests,1);result.insert("http_roundtrip",true);
        QVERIFY2(socksRoundTrip(quint16(port),origin.serverPort()),"The same system-proxy port did not relay the actual SOCKS5 fixture through Rust.");
        QCOMPARE(socksRequests,1);result.insert("socks5_roundtrip",true);
        QVERIFY2(child.state()==QProcess::Running,"The owning application exited before the close request.");

        auto expectedAfterExit=fixture;
        if(externalEdit){
            expectedAfterExit=configuredProxy(original,flags,QStringLiteral("127.0.0.1:65011"),
                QStringLiteral("http://127.0.0.1:65012/external-edit.pac?revision=after"),
                QStringLiteral("localhost;*.later-exit.invalid;10.43.*;[::1];<local>"));
            QVERIFY2(SystemProxySession::apply(expectedAfterExit),"The simulated later application's proxy change failed.");
            QVERIFY2(SystemProxySession::snapshot()==expectedAfterExit,"The later application's exact proxy edit was not retained.");
        }
        QVERIFY2(requestWindowClose(root.path()),"The full application's normal window-close command was not acknowledged.");
        QVERIFY2(QTest::qWaitFor([&]{return child.state()==QProcess::NotRunning;},10000),"Normal application shutdown did not complete.");
        QCOMPARE(child.exitStatus(),QProcess::NormalExit);QCOMPARE(child.exitCode(),0);
        const auto final=readReceipt(SwirlSystemProxyExit::finalPath(root.path()));
        QVERIFY2(!final.isEmpty(),"The full application did not publish its before-process-exit receipt.");
        QCOMPARE(final.value("source_sha").toString(),QStringLiteral(SWIRL_SOURCE_SHA));
        QCOMPARE(final.value("phase").toString(),QStringLiteral("final"));
        QCOMPARE(qint64(final.value("pid").toDouble()),pid);
        for(const auto *key:{"native_backend","ready","close_requested","shutdown_coordinator_completed","runtime_stopped","journal_absent","native_snapshot_readable"})
            QVERIFY2(final.value(key).isBool()&&final.value(key).toBool(),key);
        for(const auto *key:{"fixture_failed","proxy_owned","proxy_busy"})
            QVERIFY2(final.value(key).isBool()&&!final.value(key).toBool(),key);
        if(!externalEdit){
            for(const auto *key:{"release_finished","release_succeeded","release_while_runtime_alive","snapshot_restored_at_release","journal_absent_at_release","snapshot_restored_before_exit"})
                QVERIFY2(final.value(key).isBool()&&final.value(key).toBool(),key);
        }else QVERIFY(final.value("snapshot_restored_before_exit").isBool()&&!final.value("snapshot_restored_before_exit").toBool());
        QVERIFY2(SystemProxySession::snapshot()==expectedAfterExit,"Normal exit did not preserve the exact required PAC/bypass and raw registry snapshot; private values omitted.");
        result.insert("exact_exit_snapshot",true);
        QTRY_VERIFY_WITH_TIMEOUT(!QFile::exists(journal)&&QDir(root.filePath("data")).entryList({"system-proxy.dpapi.*.ready"},QDir::Files).isEmpty(),5000);
        result.insert("journal_and_guard_markers_removed",true);
        const auto listenerProbe=probeListener(quint16(port));result.insert("listener_probe",listenerProbe.report());
        QVERIFY2(listenerProbe.refused(),"The post-exit listener probe did not confirm explicit TCP refusal; see its numeric receipt.");
        result.insert("listener_closed",true);
        completed=true;
    }
};

int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);app.setApplicationName("SwirlProxyExitTests");app.setOrganizationName("SOLHK");
    if(qEnvironmentVariable("SWIRL_SYSTEM_PROXY_TEST")!=QStringLiteral("1")){
        qCritical("Native application proxy-exit tests require an explicitly opted-in disposable Windows runner.");return 2;
    }
    SystemProxyExitTests tests;return QTest::qExec(&tests,argc,argv);
}
#include "SystemProxyExitTests.moc"
