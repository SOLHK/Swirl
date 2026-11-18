#include "network/LanFirewall.h"
#include "network/LanProxySession.h"
#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QSignalSpy>
#include <QSemaphore>
#include <atomic>
#include <QTemporaryDir>
#include <QtTest>

namespace {
QJsonObject configuration() {
    return {{"listen_ip", "192.168.50.1"}, {"http_port", 7899}, {"socks_port", 7899},
        {"udp_port_start", 7900}, {"udp_port_end", 7915}, {"allowed_cidrs", QJsonArray{"192.168.50.0/24"}},
        {"auth", QJsonObject{{"username", "swirl"}, {"password", "test-only-secret-1234"}}},
        {"max_connections", 128}, {"max_connections_per_client", 16},
        {"auth_failures_per_minute", 10}, {"idle_timeout_secs", 300}};
}
QJsonObject journal() {
    const QString session(32, 'a');
    const auto application = QDir::fromNativeSeparators(QFileInfo(QCoreApplication::applicationFilePath()).absoluteFilePath());
    QJsonObject result{{"schema", 1}, {"session", session}, {"application", application}, {"owner_pid", 17},
        {"owner_creation", "123456789"}, {"listen_ip", "192.168.50.1"}, {"prefix", 24}, {"interface_index", 5},
        {"interface_guid", "{1d8782d0-0119-451d-8e7b-b3f4fdafdf35}"}, {"interface_name", "LAN Test"},
        {"profile", 2}, {"phase", "active"}, {"host_addresses", QJsonArray{"127.0.0.1", "192.168.50.1"}}};
    QJsonArray rules;
    for (int i = 0; i < 2; ++i) rules.append(QJsonObject{
        {"name", "SwirlLan-" + session + (i ? "-udp" : "-tcp")}, {"description", "Swirl native LAN session " + session},
        {"group", "Swirl LAN " + session}, {"application", application.toLower()}, {"local_addresses", "192.168.50.1"},
        {"remote_addresses", "192.168.50.0/24"}, {"local_ports", i ? "7900-7915" : "7899"},
        {"remote_ports", "*"}, {"interface_types", "All"}, {"service", ""}, {"interfaces", QJsonArray{"LAN Test"}},
        {"profiles", 2}, {"protocol", i ? 17 : 6}, {"direction", 1}, {"action", 1}, {"enabled", true}, {"edge_traversal", false}});
    result.insert("rules", rules); return result;
}
class StoppedEngine : public ProxyEngine {
public:
    Status current;
    int starts = 0, stops = 0, commands = 0;
    void start(const EngineStartOptions &) override { ++starts; }
    void stop() override { ++stops; }
    void refresh() override {}
    void selectNode(const QString &) override {}
    void probeNode(const QUrl &) override {}
    void lanCommand(const QJsonObject &) override { ++commands; }
    Status status() const override { return current; }
    QString configurationSummary() const override { return {}; }
};

class ReplyEngine final : public StoppedEngine {
public:
    bool startAccepted=true,stopAccepted=true,holdReply=false;
    ReplyEngine(){current.processAlive=true;current.apiHealthy=true;current.state=State::Running;}
    void lanCommand(const QJsonObject &request) override {
        ++commands;const auto op=request.value("op").toString();
        const bool accepted=op=="lan_start"?startAccepted:stopAccepted;
        if(accepted)current.allowLan=op=="lan_start";
        current.lan={{"running",current.allowLan}};
        emit statusChanged();
        if(!holdReply)emit lanCommandFinished(request.value("request_id").toString(),{{"ok",accepted},{"code",accepted?"Ok":"InjectedFailure"},{"lan",current.lan}});
    }
};
class FaultBackend final : public LanProxySession::Backend {
public:
    std::atomic_bool present{false},entered{false},holdPreparation{false},failPreparation{false},failCleanup{false};
    std::atomic_int preparations{0},cleanups{0};
    QSemaphore gate;
    LanFirewall::Result prepare(const QString &,const QJsonObject &config) override {
        ++preparations;entered.store(true);
        if(holdPreparation.load()&&!gate.tryAcquire(1,2000))return {false,"InjectedPreparationTimeout",{},{}};
        if(failPreparation.load())return {false,"InjectedPreparationFailure",{},{}};
        present.store(true);return {true,{},journal(),config};
    }
    LanFirewall::Result verify(const QJsonObject &record) override {return {true,{},record,{}};}
    LanFirewall::Result recover(const QString &,const QString &session,bool dead) override {
        ++cleanups;
        if(!dead&&session!=journal().value("session").toString())return {false,"InjectedOwnershipMismatch",journal(),{}};
        if(failCleanup.load())return {false,"InjectedExternalChange",journal(),{}};
        present.store(false);return {true,{},journal(),{}};
    }
    bool journalExists(const QString &) const override {return present.load();}
};
}

class LanProxyTests final : public QObject {
    Q_OBJECT
private slots:
    void listenerConfigurationRejectsPublicWildcardAndIpv6() {
        for (const auto &address : {"0.0.0.0", "::", "::1", "fe80::1", "fc00::1", "127.0.0.1", "100.64.0.1", "169.254.1.1", "8.8.8.8", ""}) {
            auto value = configuration(); value.insert("listen_ip", address); QString error;
            QVERIFY2(!LanFirewall::validateConfiguration(value, nullptr, &error), address); QVERIFY(!error.isEmpty());
        }
        QJsonObject normalized;
        QVERIFY(LanFirewall::validateConfiguration(configuration(), &normalized));
        QCOMPARE(normalized.value("listen_ip").toString(), QString("192.168.50.1"));
    }
    void authenticationAndBoundsFailClosed() {
        for (const auto &password : {"", "short", "password\r\n:12345"}) {
            auto value = configuration(); value.insert("auth", QJsonObject{{"username", "swirl"}, {"password", password}});
            QVERIFY(!LanFirewall::validateConfiguration(value, nullptr));
        }
        const QList<QPair<QString, QJsonValue>> invalid{{"http_port", 0}, {"socks_port", 65536}, {"http_port", 10.5},
            {"udp_port_end", 7964}, {"udp_port_end", 7899}, {"max_connections", 257},
            {"max_connections_per_client", 65}, {"auth_failures_per_minute", 21}, {"idle_timeout_secs", 59}};
        for (const auto &pair : invalid) { auto value = configuration(); value.insert(pair.first, pair.second); QVERIFY(!LanFirewall::validateConfiguration(value, nullptr)); }
        auto value = configuration(); value.insert("max_connections", 2); QVERIFY(!LanFirewall::validateConfiguration(value, nullptr));
        value = configuration(); value.insert("skip_authentication", true); QVERIFY(!LanFirewall::validateConfiguration(value, nullptr));
    }
    void clientAclCannotCoverPublicSpace() {
        for (const auto &range : {"0.0.0.0/0", "10.0.0.0/7", "172.16.0.0/8", "192.168.0.0/8", "127.0.0.0/8", "8.8.8.8/32", "::/0", "LocalSubnet"}) {
            auto value = configuration(); value.insert("allowed_cidrs", QJsonArray{range}); QVERIFY2(!LanFirewall::validateConfiguration(value, nullptr), range);
        }
        auto value = configuration(); value.insert("allowed_cidrs", QJsonArray{}); QVERIFY(!LanFirewall::validateConfiguration(value, nullptr));
        value.insert("allowed_cidrs", QJsonArray{"192.168.50.1/24", "192.168.50.0/24"}); QJsonObject normalized;
        QVERIFY(LanFirewall::validateConfiguration(value, &normalized));
        QCOMPARE(normalized.value("allowed_cidrs").toArray(), QJsonArray{"192.168.50.0/24"});
    }
    void recoveryRequiresExactOwnershipAndScope() {
        QVERIFY(LanFirewall::validateJournal(journal()));
        const QList<QPair<QString, QJsonValue>> changes{{"name", "OtherApplicationRule"}, {"application", "/other/program.exe"},
            {"local_addresses", "*"}, {"remote_addresses", "0.0.0.0/0"}, {"remote_addresses", "192.168.0.0/16"},
            {"local_ports", "65536"}, {"profiles", 7}, {"interfaces", QJsonArray{}}, {"edge_traversal", true},
            {"enabled", false}, {"direction", 2}, {"direction", 1.5}, {"protocol", 6.5}, {"protocol", 256}};
        for (const auto &change : changes) {
            auto value = journal(); auto rules = value.value("rules").toArray(); auto first = rules[0].toObject();
            first.insert(change.first, change.second); rules[0] = first; value.insert("rules", rules);
            QVERIFY2(!LanFirewall::validateJournal(value), qPrintable(change.first));
        }
        auto value = journal(); value.insert("owner_pid", 0); QVERIFY(!LanFirewall::validateJournal(value));
        value = journal(); value.insert("phase", "foreign"); QVERIFY(!LanFirewall::validateJournal(value));
        value = journal(); value.insert("profile", 2.5); QVERIFY(!LanFirewall::validateJournal(value));
        value = journal(); value.insert("host_addresses", QJsonArray{"127.0.0.1"}); QVERIFY(!LanFirewall::validateJournal(value));
        value = journal(); value.insert("extra_privileged_option", true); QVERIFY(!LanFirewall::validateJournal(value));
        value = journal(); auto rules = value.value("rules").toArray(); auto udp = rules[1].toObject();
        udp.insert("local_ports", "7900-8000"); rules[1] = udp; value.insert("rules", rules); QVERIFY(!LanFirewall::validateJournal(value));
    }
    void hostInventoryProtectsIpv6AndRejectsAmbiguousEntries() {
        auto value = journal();
        value.insert("host_addresses", QJsonArray{"127.0.0.1", "192.168.50.1", "2001:db8::12", "fe80::1"});
        QVERIFY(LanFirewall::validateJournal(value));
        value.insert("host_addresses", QJsonArray{"192.168.50.1", "fe80::1%5"});
        QVERIFY(!LanFirewall::validateJournal(value));
        value.insert("host_addresses", QJsonArray{"192.168.50.1", "192.168.50.1"});
        QVERIFY(!LanFirewall::validateJournal(value));
    }
    void lostCommandReceiptsHaveBoundedRecoveryAndNeverFakeStoppedStatus() {
        QTemporaryDir temporary; ReplyEngine engine; engine.holdReply = true;
        auto backend = std::make_shared<FaultBackend>();
        LanProxySession session(&engine, temporary.filePath("session.dpapi"), nullptr, backend);
        QVERIFY(session.start(configuration()));
        QTRY_COMPARE(session.phase(), QString("starting_listener"));
        QVERIFY(engine.current.allowLan);
        auto *deadline = session.findChild<QTimer *>("lanCommandDeadline");
        QVERIFY(deadline);
        // The real timer drives this same transition. Invoke its signal rather
        // than spending twenty seconds waiting inside an isolated fault test.
        engine.stopAccepted = false;
        QVERIFY(QMetaObject::invokeMethod(deadline, "timeout", Qt::DirectConnection));
        QCOMPARE(session.phase(), QString("stopping_listener"));
        QCOMPARE(engine.commands, 2);
        QVERIFY(QMetaObject::invokeMethod(deadline, "timeout", Qt::DirectConnection));
        QTRY_COMPARE(session.phase(), QString("idle"));
        QCOMPARE(backend->cleanups.load(), 1);
        QVERIFY(engine.current.allowLan);
        QVERIFY(!session.error().isEmpty());
        QCOMPARE(engine.stops, 0);
    }
    void stoppedRuntimeCancellationNeverMutatesSystemOrCore() {
        QTemporaryDir temporary; QVERIFY(temporary.isValid()); StoppedEngine engine;
        const auto path = temporary.filePath("session.dpapi"); LanProxySession session(&engine, path);
        QSignalSpy changes(&session, &LanProxySession::changed);
        QVERIFY(session.start(configuration())); QCOMPARE(session.phase(), QString("waiting_core")); QVERIFY(session.busy());
        QVERIFY(session.stop()); QCOMPARE(session.phase(), QString("idle")); QVERIFY(!session.busy());
        QCOMPARE(engine.starts, 0); QCOMPARE(engine.stops, 0); QCOMPARE(engine.commands, 0);
        QVERIFY(!QFileInfo::exists(path)); QVERIFY(changes.count() >= 2);
    }
    void listenerReceiptsOwnRunningStateAndMainRuntimeSurvives() {
        QTemporaryDir temporary;QVERIFY(temporary.isValid());ReplyEngine engine;auto backend=std::make_shared<FaultBackend>();
        LanProxySession session(&engine,temporary.filePath("session.dpapi"),nullptr,backend);
        QVERIFY(session.start(configuration()));QCOMPARE(session.phase(),QString("preparing_firewall"));QVERIFY(!engine.current.allowLan);
        QTRY_COMPARE(session.phase(),QString("running"));QVERIFY(engine.current.allowLan);QCOMPARE(backend->preparations.load(),1);
        QVERIFY(session.stop());QTRY_COMPARE(session.phase(),QString("idle"));QVERIFY(!engine.current.allowLan);
        QCOMPARE(engine.commands,2);QCOMPARE(engine.starts,0);QCOMPARE(engine.stops,0);
        QVERIFY(engine.current.processAlive);QVERIFY(engine.current.apiHealthy);QCOMPARE(backend->cleanups.load(),1);QVERIFY(!session.recoveryNeeded());
    }
    void refusedListenerRollsBackOnlyPreparedFirewall() {
        QTemporaryDir temporary;ReplyEngine engine;engine.startAccepted=false;auto backend=std::make_shared<FaultBackend>();
        LanProxySession session(&engine,temporary.filePath("session.dpapi"),nullptr,backend);
        QVERIFY(session.start(configuration()));QTRY_COMPARE(session.phase(),QString("idle"));
        QCOMPARE(engine.commands,1);QCOMPARE(engine.stops,0);QCOMPARE(backend->cleanups.load(),1);QVERIFY(!session.error().isEmpty());QVERIFY(!session.recoveryNeeded());
    }
    void cancellationDuringFirewallPreparationNeverStartsListener() {
        QTemporaryDir temporary;ReplyEngine engine;auto backend=std::make_shared<FaultBackend>();backend->holdPreparation.store(true);
        LanProxySession session(&engine,temporary.filePath("session.dpapi"),nullptr,backend);
        QVERIFY(session.start(configuration()));QTRY_VERIFY(backend->entered.load());QVERIFY(session.stop());
        backend->gate.release();QTRY_COMPARE(session.phase(),QString("idle"));
        QCOMPARE(engine.commands,0);QCOMPARE(engine.stops,0);QCOMPARE(backend->cleanups.load(),1);QVERIFY(!session.recoveryNeeded());
    }
    void mainRuntimeStopRecoversEvenWhenItsEpochDropsTheLanReply() {
        QTemporaryDir temporary;ReplyEngine engine;engine.holdReply=true;auto backend=std::make_shared<FaultBackend>();
        LanProxySession session(&engine,temporary.filePath("session.dpapi"),nullptr,backend);
        QVERIFY(session.start(configuration()));QTRY_COMPARE(session.phase(),QString("starting_listener"));
        QVERIFY(session.stop());QCOMPARE(session.phase(),QString("starting_listener"));
        engine.current.state=ProxyEngine::State::Stopped;engine.current.processAlive=false;
        engine.current.apiHealthy=false;engine.current.allowLan=false;emit engine.statusChanged();
        QTRY_COMPARE(session.phase(),QString("idle"));QCOMPARE(backend->cleanups.load(),1);QVERIFY(!session.recoveryNeeded());
        QCOMPARE(engine.commands,1);QCOMPARE(engine.stops,0);
    }
    void failedStopOrExternalRuleEditCannotBecomeFalseSuccess() {
        QTemporaryDir temporary;ReplyEngine engine;auto backend=std::make_shared<FaultBackend>();
        LanProxySession session(&engine,temporary.filePath("session.dpapi"),nullptr,backend);
        QVERIFY(session.start(configuration()));QTRY_COMPARE(session.phase(),QString("running"));
        engine.stopAccepted=false;backend->failCleanup.store(true);QVERIFY(session.stop());QTRY_COMPARE(session.phase(),QString("idle"));
        QVERIFY(engine.current.allowLan);QVERIFY(session.recoveryNeeded());QVERIFY(session.error().contains("InjectedExternalChange"));
        QVERIFY(!session.start(configuration()));QVERIFY(engine.current.processAlive);QCOMPARE(engine.stops,0);
        engine.stopAccepted=true;backend->failCleanup.store(false);QVERIFY(session.stop());QTRY_COMPARE(session.phase(),QString("idle"));
        QVERIFY(!engine.current.allowLan);QVERIFY(!session.recoveryNeeded());
    }
    void badConfigurationAndPendingRecoveryNeverOpenListeners() {
        QTemporaryDir temporary; QVERIFY(temporary.isValid()); StoppedEngine engine;
        const auto path = temporary.filePath("session.dpapi"); LanProxySession session(&engine, path);
        auto invalid = configuration(); invalid.insert("listen_ip", "0.0.0.0"); QVERIFY(!session.start(invalid));
        QVERIFY(!QFileInfo::exists(path));
        QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly)); QCOMPARE(file.write("tampered-recovery"), qint64(17)); file.close();
        QVERIFY(!session.start(configuration())); QVERIFY(session.recoveryNeeded());
        QCOMPARE(engine.starts, 0); QCOMPARE(engine.stops, 0); QCOMPARE(engine.commands, 0);
        const auto recovered = LanFirewall::recover(path); QVERIFY(!recovered.ok); QVERIFY(QFileInfo::exists(path));
        QVERIFY(file.open(QIODevice::ReadOnly)); QCOMPARE(file.readAll(), QByteArray("tampered-recovery"));
    }
};

QTEST_GUILESS_MAIN(LanProxyTests)
#include "LanProxyTests.moc"
