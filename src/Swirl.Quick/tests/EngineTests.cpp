#include "engine/MihomoAdapter.h"
#include "engine/EngineController.h"
#include "LoopbackPortLease.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QSettings>
#include <QSignalSpy>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <QTest>
#include <QSettings>
#include "app/StoragePaths.h"
#include <QTcpSocket>
#ifdef Q_OS_WIN
#include <windows.h>
#endif

class EngineTests : public QObject {
    Q_OBJECT
    EngineStartOptions options() {
        EngineStartOptions result;
        result.executablePath = QCoreApplication::applicationDirPath() + "/SwirlEngineFixture.exe";
#ifndef Q_OS_WIN
        result.executablePath.chop(4);
#endif
        QFile file(result.executablePath);
        if (!file.open(QIODevice::ReadOnly)) return result;
        QCryptographicHash hash(QCryptographicHash::Sha256); hash.addData(&file);
        result.expectedSha256 = hash.result().toHex(); result.expectedVersion = "vfixture";
        LoopbackPortLease ports;
        if (!ports.reserve()) {
            QTest::qFail(qPrintable(ports.errorString()), __FILE__, __LINE__);
            result.controlPort = 0;
            return result;
        }
        result.controlPort = ports.controlPort();
        result.proxyPort = ports.proxyPort();
        result.startupTimeoutMs = 2500; result.requestTimeoutMs = 150; result.healthIntervalMs = 100;
        return result;
    }
    static bool processExists(qint64 pid) {
#ifdef Q_OS_WIN
        HANDLE process = OpenProcess(SYNCHRONIZE, FALSE, DWORD(pid));
        if (!process) return false;
        const bool exists = WaitForSingleObject(process, 0) == WAIT_TIMEOUT;
        CloseHandle(process); return exists;
#else
        Q_UNUSED(pid); return false;
#endif
    }
    static bool terminateOwned(qint64 pid) {
#ifdef Q_OS_WIN
        HANDLE process = OpenProcess(PROCESS_TERMINATE, FALSE, DWORD(pid));
        if (!process) return false;
        const bool result = TerminateProcess(process, 42); CloseHandle(process); return result;
#else
        Q_UNUSED(pid); return false;
#endif
    }
    static QVariantMap systemProxy() {
        QVariantMap result;
#ifdef Q_OS_WIN
        QSettings settings("HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings", QSettings::NativeFormat);
        for (const auto &key : {"ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL"}) result.insert(key, settings.value(key));
#endif
        return result;
    }
    static void writeControl(const QString &path, const QByteArray &value) {
        QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly)); QCOMPARE(file.write(value), qint64(value.size()));
    }
private slots:
    void mixedPortLeaseReservesAndReleasesBothTransports() {
        LoopbackPortLease ports;
        QVERIFY2(ports.reserve(), qPrintable(ports.errorString()));
        QVERIFY(ports.proxyPort() > 0);
        QVERIFY(ports.controlPort() > 0);
        QVERIFY(ports.proxyPort() != ports.controlPort());
        QUdpSocket conflict;
        conflict.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(!conflict.bind(QHostAddress::LocalHost, ports.proxyPort(), QUdpSocket::DontShareAddress));
        ports.release();
        QTcpServer tcp, controller;
        tcp.setProxy(QNetworkProxy::NoProxy);
        controller.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(tcp.listen(QHostAddress::LocalHost, ports.proxyPort()));
        QVERIFY(controller.listen(QHostAddress::LocalHost, ports.controlPort()));
        QVERIFY(conflict.bind(QHostAddress::LocalHost, ports.proxyPort(), QUdpSocket::DontShareAddress));
    }
    void occupiedMixedUdpPortIsRejectedWithoutStarting() {
        auto config = options();
        config.directSession = true;
        QUdpSocket occupied;
        occupied.setProxy(QNetworkProxy::NoProxy);
        QVERIFY(occupied.bind(QHostAddress::LocalHost, config.proxyPort, QUdpSocket::DontShareAddress));
        MihomoAdapter engine;
        engine.start(config);
        QCOMPARE(engine.status().error, ProxyEngine::Error::PortConflict);
        QVERIFY(!engine.status().processAlive);
        QCOMPARE(occupied.state(), QAbstractSocket::BoundState);
    }
    void startupReadinessDoesNotWaitForSteadyHealthCadence(){
        QTemporaryDir temporary;const auto control=temporary.filePath("control");
        writeControl(control,"timeout");qputenv("SWIRL_FIXTURE_CONTROL",control.toUtf8());
        auto config=options();config.startupTimeoutMs=2500;config.healthIntervalMs=10000;
        QTimer::singleShot(450,this,[control]{writeControl(control,"");});
        MihomoAdapter engine;QElapsedTimer elapsed;elapsed.start();engine.start(config);
        QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,3000);
        QVERIFY(elapsed.elapsed()<config.startupTimeoutMs);
        QCOMPARE(engine.status().state,ProxyEngine::State::Running);
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
    }
    void loginHandshakeLogRetainsReasonWithoutBreakingTunnel(){
        qputenv("SWIRL_FIXTURE_MODE","login-tls-eof");
        auto config=options();config.directSession=true;
        MihomoAdapter engine;QSignalSpy diagnostics(&engine,&ProxyEngine::diagnostic);engine.start(config);
        QTRY_VERIFY2_WITH_TIMEOUT(engine.status().apiHealthy,qPrintable(engine.status().message),5000);const auto pid=engine.status().processId;
        QTcpSocket tunnel;tunnel.setProxy(QNetworkProxy::NoProxy);tunnel.connectToHost(QHostAddress::LocalHost,quint16(config.proxyPort));
        QTRY_COMPARE_WITH_TIMEOUT(tunnel.state(),QAbstractSocket::ConnectedState,2000);
        QTRY_VERIFY_WITH_TIMEOUT(std::any_of(diagnostics.cbegin(),diagnostics.cend(),[](const auto &row){return row.at(1).toString()=="TLSFailure";}),3000);
        for(const auto &row:diagnostics)if(row.at(1).toString()=="TLSFailure") {
            const auto message=row.at(2).toString();QVERIFY(message.contains("EOF"));QVERIFY(message.contains("auth.openai.com:443"));
            for(const auto &secret:{"PRIVATE-SECRET","PRIVATE-RULE","private-node","NODE-DNS-TLS","192.168","5678"})QVERIFY2(!message.contains(secret),secret);
        }
        tunnel.write("ongoing-stream");QTRY_COMPARE_WITH_TIMEOUT(tunnel.bytesAvailable(),qint64(14),2000);QCOMPARE(tunnel.readAll(),QByteArray("ongoing-stream"));
        QCOMPARE(engine.status().processId,pid);QVERIFY(engine.status().apiHealthy);QVERIFY(processExists(pid));
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
    }
    void routingResponseFailurePreservesProcess_data(){
        QTest::addColumn<QByteArray>("failure");QTest::addColumn<QString>("actual");
        QTest::newRow("applied-but-response-lost")<<QByteArray("patch-apply-drop")<<QString("global");
        QTest::newRow("rejected-keeps-old-mode")<<QByteArray("patch-reject")<<QString("rule");
    }
    void routingResponseFailurePreservesProcess(){
        QFETCH(QByteArray,failure);QFETCH(QString,actual);
        QTemporaryDir temporary;const auto control=temporary.filePath("control");qputenv("SWIRL_FIXTURE_CONTROL",control.toUtf8());
        auto o=options();o.directSession=true;
        MihomoAdapter engine;engine.start(o);QTRY_VERIFY2_WITH_TIMEOUT(engine.status().apiHealthy,qPrintable(engine.status().message),5000);const auto pid=engine.status().processId;
        QFile file(control);QVERIFY(file.open(QIODevice::WriteOnly));file.write(failure);file.close();
        engine.setRoutingMode("global");
        QTRY_VERIFY_WITH_TIMEOUT(!engine.status().routingBusy&&engine.status().apiHealthy,5000);
        QCOMPARE(engine.status().processId,pid);QVERIFY(processExists(pid));QCOMPARE(engine.status().mode,actual);
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);qunsetenv("SWIRL_FIXTURE_CONTROL");
    }

    void initTestCase() { QStandardPaths::setTestModeEnabled(true);SwirlPaths::initializeTestStorage();QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation)); }
    void cleanup() { qunsetenv("SWIRL_FIXTURE_MODE"); qunsetenv("SWIRL_FIXTURE_CONTROL"); }
    void networkPreferencesValidateAndPersist() {
        QTemporaryDir directory;const auto store=directory.filePath("nodes.dpapi");
        EngineController controller(std::make_unique<MihomoAdapter>(),nullptr,store);
        QVERIFY(!controller.configureDns({{"mode",2},{"servers","127.0.0.1\nproxies: []"}}));
        QVERIFY(!controller.configureDns({{"mode",2},{"servers",""}}));
        QVERIFY(!controller.configureDns({{"mode",0},{"encrypted","http://insecure.test/dns"}}));
        QVERIFY(!controller.configureDns({{"mode",0},{"hosts",QVariantList{QVariantMap{{"name","valid.test"},{"value","not-an-ip"}}}}}));
        const QVariantMap dns{{"mode",2},{"servers","127.0.0.1,::1"},{"encrypted","https://example.test/dns-query"},{"useHosts",false},{"hosts",QVariantList{QVariantMap{{"name","fixture.test"},{"value","127.0.0.1"}}}}};
        QVERIFY(controller.configureDns(dns));
        QVERIFY(!controller.configureLan("bad:username","long-enough"));QVERIFY(!controller.configureLan("swirl","short"));
        QVERIFY(controller.configureLan("swirl","swirl-test-password"));QVERIFY(controller.lanConfigured());
        QFile networkStore(store);QVERIFY(networkStore.open(QIODevice::ReadOnly));QVERIFY(!networkStore.readAll().contains("swirl-test-password"));networkStore.close();
        QVERIFY(!controller.saveRoutingRule("DOMAIN-SUFFIX","test\nMATCH,REJECT","DIRECT"));
        QVERIFY(!controller.saveRoutingRule("IP-CIDR","not-a-subnet","DIRECT"));
        QVERIFY(!controller.saveRoutingRule("DOMAIN","fixture.test","missing-group"));
        QVERIFY(controller.savePolicyGroup("Local","select",{"DIRECT"}));
        QVERIFY(!controller.savePolicyGroup("bad,group","select",{"DIRECT"}));
        QVERIFY(!controller.savePolicyGroup(" group ","select",{"DIRECT"}));
        QVERIFY(!controller.configureMeteredAllowlist({"chrome.exe),(MATCH,REJECT"}));
        QVERIFY(controller.configureMeteredAllowlist({"chrome.exe","CHROME.exe","curl.exe"}));
        QCOMPARE(controller.meteredAllowlist().size(),2);
        QVERIFY(controller.saveRoutingRule("DOMAIN","fixture.test","Local"));
        const auto ruleCount=controller.routingRules().size();
        QVERIFY(controller.saveRoutingRule("DOMAIN-SUFFIX","edited.fixture.test","Local",0));
        QCOMPARE(controller.routingRules().size(),ruleCount);
        QVERIFY(!controller.saveRoutingRule("DOMAIN","invalid.fixture.test","DIRECT",99));
        QCOMPARE(controller.routingRules().first().toMap().value("policy").toString(),QStringLiteral("Local"));
        QCOMPARE(controller.routingRules().first().toMap().value("pattern").toString(),QStringLiteral("edited.fixture.test"));
        QVERIFY(!controller.removePolicyGroup("Local"));
        EngineController restored(std::make_unique<MihomoAdapter>(),nullptr,store);
        QCOMPARE(restored.dnsConfiguration().value("servers").toString(),QStringLiteral("127.0.0.1,::1"));
        QCOMPARE(restored.dnsConfiguration().value("hosts").toList().size(),1);
        QCOMPARE(restored.policyGroups().size(),1);
        QCOMPARE(restored.routingRules().first().toMap().value("policy").toString(),QStringLiteral("Local"));
        QCOMPARE(restored.routingRules().first().toMap().value("pattern").toString(),QStringLiteral("edited.fixture.test"));
        QVERIFY(restored.removeRoutingRule(0));QVERIFY(restored.removePolicyGroup("Local"));
    }
    void missingAndTampered() {
        MihomoAdapter engine;
        auto config = options(); config.executablePath += ".missing";
        engine.start(config);
        QCOMPARE(engine.status().error, ProxyEngine::Error::MissingExecutable);
        QVERIFY(engine.status().message.contains(config.executablePath)); QVERIFY(!engine.status().processAlive);
        config = options(); config.expectedSha256 = QByteArray(64, '0'); engine.start(config);
        QCOMPARE(engine.status().error, ProxyEngine::Error::IntegrityMismatch); QVERIFY(!engine.status().processAlive);
    }
    void invalidOptions() {
        MihomoAdapter engine; auto config = options(); config.executablePath = "relative.exe";
        engine.start(config); QCOMPARE(engine.status().error, ProxyEngine::Error::InvalidOptions);
        config = options(); config.controlPort = 0; engine.start(config);
        QCOMPARE(engine.status().error, ProxyEngine::Error::InvalidOptions);
    }
    void invalidExecutable() {
        QTemporaryDir temp; QVERIFY(temp.isValid());
        const auto path = temp.filePath("invalid.exe"); writeControl(path, "not an executable");
        auto config = options(); config.executablePath = path;
        config.expectedSha256 = QCryptographicHash::hash("not an executable", QCryptographicHash::Sha256).toHex();
        MihomoAdapter engine; engine.start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().error, ProxyEngine::Error::ProcessStartFailed, 5000);
        QVERIFY(!engine.status().processAlive);
    }
    void portConflict() {
        QTcpServer occupied; QVERIFY(occupied.listen(QHostAddress::AnyIPv4, 0));
        auto config = options(); config.controlPort = occupied.serverPort();
        MihomoAdapter engine; engine.start(config);
        QCOMPARE(engine.status().error, ProxyEngine::Error::PortConflict); QVERIFY(!engine.status().processAlive);
        QVERIFY(occupied.isListening());
    }
    void healthyApiWithoutMixedListenerNeverBecomesReady() {
        qputenv("SWIRL_FIXTURE_MODE","no-mixed-listener");
        auto config=options();config.directSession=true;config.startupTimeoutMs=1200;
        MihomoAdapter engine;bool reportedReady=false;
        connect(&engine,&ProxyEngine::statusChanged,&engine,[&]{
            reportedReady=reportedReady || engine.status().state==ProxyEngine::State::Running;
        });
        engine.start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Failed,4000);
        QCOMPARE(engine.status().error,ProxyEngine::Error::StartupTimeout);
        QVERIFY(!reportedReady);QVERIFY(!engine.status().apiHealthy);
        QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,3000);
    }
    void failures_data() {
        QTest::addColumn<QByteArray>("mode"); QTest::addColumn<int>("error");
        QTest::newRow("config-rejected") << QByteArray("config-error") << int(ProxyEngine::Error::ConfigurationFailed);
        QTest::newRow("exit-at-start") << QByteArray("start-exit") << int(ProxyEngine::Error::UnexpectedExit);
        QTest::newRow("version-hangs") << QByteArray("hang-version") << int(ProxyEngine::Error::StartupTimeout);
        QTest::newRow("api-not-listening") << QByteArray("no-api") << int(ProxyEngine::Error::StartupTimeout);
        QTest::newRow("api-unauthorized") << QByteArray("auth") << int(ProxyEngine::Error::StartupTimeout);
        QTest::newRow("malformed-json") << QByteArray("bad-json") << int(ProxyEngine::Error::StartupTimeout);
        QTest::newRow("mismatched-api-version") << QByteArray("wrong-version") << int(ProxyEngine::Error::StartupTimeout);
        QTest::newRow("unsafe-runtime") << QByteArray("unsafe") << int(ProxyEngine::Error::ConfigurationFailed);
    }
    void failures() {
        QFETCH(QByteArray, mode); QFETCH(int, error); qputenv("SWIRL_FIXTURE_MODE", mode);
        auto config = options(); config.startupTimeoutMs = 1200;
        MihomoAdapter engine; engine.start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Failed, 5000);
        QCOMPARE(int(engine.status().error), error);
        QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive, 3000);
        QVERIFY(!engine.status().apiHealthy);
    }
    void lifecycleAndCleanup() {
        const auto proxyBefore = systemProxy();
        MihomoAdapter engine; const auto config = options(); QSignalSpy spy(&engine, &ProxyEngine::statusChanged);
        for (int i = 0; i < 8; ++i) {
            engine.start(config); engine.start(config);
            QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Running, 5000);
            QVERIFY(engine.status().processAlive); QVERIFY(engine.status().apiHealthy);
            const auto pid = engine.status().processId; QVERIFY(pid > 0);
            engine.start(config); QCOMPARE(engine.status().processId, pid);
            QCOMPARE(engine.status().version, QString("vfixture"));
            const auto configPath = engine.status().configPath;
            QFile file(configPath); QVERIFY(file.open(QIODevice::ReadOnly));
            const auto contents = file.readAll(); file.close();
            QVERIFY(contents.contains("tun:\n  enable: false")); QVERIFY(contents.contains("dns:\n  enable: false"));
            QVERIFY(contents.contains("external-controller: '127.0.0.1:"));
            QVERIFY(engine.configurationSummary().contains("已隐藏"));
            engine.stop(); engine.stop();
            QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Stopped, 4000);
            QVERIFY(!engine.status().processAlive); QVERIFY(!engine.status().apiHealthy);
            QVERIFY(!QFile::exists(configPath)); QVERIFY(!processExists(pid));
        }
        QVERIFY(spy.count() >= 32); QCOMPARE(systemProxy(), proxyBefore);
    }
    void healthFailureAndRecovery() {
        QTemporaryDir temp; QVERIFY(temp.isValid()); const auto control = temp.filePath("control");
        writeControl(control, "ok"); qputenv("SWIRL_FIXTURE_CONTROL", control.toUtf8());
        auto config=options();config.directSession=true;
        MihomoAdapter engine; engine.start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Running, 5000);
        const auto pid = engine.status().processId;
        QTcpSocket tunnel;tunnel.setProxy(QNetworkProxy::NoProxy);
        tunnel.connectToHost(QHostAddress::LocalHost,config.proxyPort);
        QTRY_COMPARE_WITH_TIMEOUT(tunnel.state(),QAbstractSocket::ConnectedState,2000);
        for (const auto &mode : {QByteArray("timeout"), QByteArray("auth"), QByteArray("bad-json"), QByteArray("oversize")}) {
            writeControl(control, mode);
            QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Degraded, 3000);
            QVERIFY(engine.status().processAlive); QVERIFY(!engine.status().apiHealthy); QCOMPARE(engine.status().processId, pid);
            const auto marker=QByteArray("healthy-tunnel-")+mode;
            tunnel.write(marker);QByteArray received;
            QTRY_VERIFY_WITH_TIMEOUT((received+=tunnel.readAll())==marker,2000);
            QVERIFY(!engine.status().message.isEmpty());
            if (mode == "auth") QCOMPARE(engine.status().error, ProxyEngine::Error::AuthenticationFailed);
            if (mode == "bad-json") QCOMPARE(engine.status().error, ProxyEngine::Error::InvalidResponse);
            writeControl(control, "ok");
            QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Running, 3000);
            QVERIFY(engine.status().apiHealthy); QVERIFY(engine.status().message.isEmpty());
            QCOMPARE(tunnel.state(),QAbstractSocket::ConnectedState);
        }
        engine.stop(); QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Stopped, 4000);
    }
    void unexpectedExitAndDestructor() {
#ifndef Q_OS_WIN
        QSKIP("Windows ownership test");
#else
        auto engine = std::make_unique<MihomoAdapter>(); const auto config = options(); engine->start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine->status().state, ProxyEngine::State::Running, 5000);
        QVERIFY(terminateOwned(engine->status().processId));
        QTRY_COMPARE_WITH_TIMEOUT(engine->status().state, ProxyEngine::State::Failed, 4000);
        QCOMPARE(engine->status().error, ProxyEngine::Error::UnexpectedExit); QVERIFY(!engine->status().apiHealthy);
        engine->start(config); QTRY_COMPARE_WITH_TIMEOUT(engine->status().state, ProxyEngine::State::Running, 5000);
        const auto pid = engine->status().processId; engine.reset(); QVERIFY(!processExists(pid));
#endif
    }
    void stopDuringValidation() {
        qputenv("SWIRL_FIXTURE_MODE", "hang-version");
        MihomoAdapter engine; auto config = options(); engine.start(config); engine.stop();
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Stopped, 4000);
        qunsetenv("SWIRL_FIXTURE_MODE"); engine.start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Running, 5000);
        engine.stop(); QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Stopped, 4000);
    }
    void executablePathWithSpacesAndMetacharacters() {
        QTemporaryDir temp; QVERIFY(temp.isValid());
        auto config = options(); const auto relocated = temp.filePath(QStringLiteral("engine & 空格.exe"));
        QVERIFY(QFile::copy(config.executablePath, relocated)); config.executablePath = relocated;
        MihomoAdapter engine; engine.start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Running, 5000);
        engine.stop(); QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Stopped, 4000);
    }
    void abruptHostExitReapsJob() {
#ifndef Q_OS_WIN
        QSKIP("Windows atomic job ownership test");
#else
        QTemporaryDir temp; QVERIFY(temp.isValid()); const auto pidFile = temp.filePath("pid.txt");
        QProcess host;
        host.start(QCoreApplication::applicationFilePath(), {"--ownership-host", pidFile});
        QVERIFY(host.waitForStarted(3000));
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(pidFile), 3000);
        QFile file(pidFile); QVERIFY(file.open(QIODevice::ReadOnly)); const auto pid = file.readAll().toLongLong(); file.close();
        QVERIFY(pid > 0); QVERIFY(processExists(pid));
        host.kill(); QVERIFY(host.waitForFinished(3000));
        QTRY_VERIFY_WITH_TIMEOUT(!processExists(pid), 3000);
#endif
    }
    void realEngine() {
        if (!qEnvironmentVariableIsSet("SWIRL_REAL_ENGINE_TEST")) QSKIP("Opt-in real Mihomo integration; run CTest swirl-engine-real");
        QFile manifest(QString::fromUtf8(SWIRL_TEST_MANIFEST)); QVERIFY(manifest.open(QIODevice::ReadOnly));
        const auto object = QJsonDocument::fromJson(manifest.readAll()).object();
        auto config = options(); config.executablePath = QCoreApplication::applicationDirPath() + "/core/mihomo.exe";
        config.expectedVersion = object.value("version").toString();
        config.expectedSha256 = object.value("executableSha256").toString().toLatin1(); config.startupTimeoutMs = 15000;
        const auto proxyBefore = systemProxy();
        MihomoAdapter engine;
        for (int i = 0; i < 5; ++i) {
            engine.start(config);
            QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Running, 16000);
            QVERIFY(engine.status().apiHealthy); QVERIFY(engine.status().processAlive);
            QCOMPARE(engine.status().version, config.expectedVersion); QCOMPARE(engine.status().mode, QString("direct"));
            if (i == 0) {
                QNetworkAccessManager client; client.setProxy(QNetworkProxy::NoProxy);
                auto *reply = client.get(QNetworkRequest(QUrl(engine.status().controlEndpoint + "/version")));
                QSignalSpy complete(reply, &QNetworkReply::finished);
                QVERIFY(complete.wait(3000));
                QCOMPARE(reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt(), 401);
                reply->deleteLater();
            }
            const auto pid = engine.status().processId; const auto path = engine.status().configPath;
            if (i == 2) {
#ifdef Q_OS_WIN
                QVERIFY(terminateOwned(pid)); QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Failed, 4000);
                QCOMPARE(engine.status().error, ProxyEngine::Error::UnexpectedExit);
#endif
            }
            engine.stop(); QTRY_COMPARE_WITH_TIMEOUT(engine.status().state, ProxyEngine::State::Stopped, 4000);
            QVERIFY(!processExists(pid)); QVERIFY(!QFile::exists(path));
        }
        QCOMPARE(systemProxy(), proxyBefore);
    }
};
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    if (app.arguments().contains("--ownership-host")) {
        OwnedProcess child;
        if (!child.ownershipReady()) return 2;
        child.start(QCoreApplication::applicationDirPath() + "/SwirlEngineFixture.exe", {"--idle"});
        if (!child.waitForStarted(3000)) return 3;
        QFile pidFile(app.arguments().last());
        if (!pidFile.open(QIODevice::WriteOnly)) return 4;
        pidFile.write(QByteArray::number(child.processId())); pidFile.close();
        return app.exec();
    }
    EngineTests tests;
    return QTest::qExec(&tests, argc, argv);
}
#include "EngineTests.moc"
