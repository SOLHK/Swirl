#include "engine/SystemProxySession.h"
#include "engine/SystemProxyState.h"

#include <QFile>
#include <QJsonDocument>
#include <QTemporaryDir>
#include <QTest>
#include <QtEndian>
#include <QUuid>
#include <QElapsedTimer>
#include <QSignalSpy>
#include "PolicySystemProxyBackend.h"

namespace {
QJsonObject registryFlag(quint32 flag) {
    QByteArray bytes(4, Qt::Uninitialized);
    qToLittleEndian(flag, bytes.data());
    return {{"present", true}, {"type", 4}, {"data", QString::fromLatin1(bytes.toBase64())}};
}
QJsonObject fixture(int flags, const QJsonObject &registry) {
    return {{"flags", flags}, {"server", "fixture-secret@private.example:1080"},
            {"bypass", "private-bypass.example"}, {"pac", "https://private-pac.example/token"},
            {"registry", QJsonObject{{"ProxyEnable", registry}, {"ProxyServer", "fixture-secret"}}}};
}
class DeferredProxyBackend final : public SystemProxySession::Backend {
public:
    PolicySystemProxyBackend memory;
    bool ready=false,externalChanged=false;
    int preparations=0,cancellations=0;
    State refresh() override {return memory.refresh();}
    State enable(int port,qint64 pid) override {return memory.enable(port,pid);}
    State disable() override {return memory.disable();}
    Preparation prepareEnable(int,qint64,QString *error) override {
        ++preparations;
        if(externalChanged){*error=QStringLiteral("External proxy changed during guard preparation");return Preparation::Failed;}
        return ready?Preparation::Ready:Preparation::Pending;
    }
    void cancelEnable() override {++cancellations;}
};
}

class SystemProxyStateTests : public QObject {
    Q_OBJECT
private slots:
    void guardReadinessWaitKeepsTheEventLoopResponsive() {
        auto backend=std::make_unique<DeferredProxyBackend>();auto *adapter=backend.get();
        SystemProxySession proxy(nullptr,{},std::move(backend));QSignalSpy completed(&proxy,&SystemProxySession::enableFinished);
        QElapsedTimer clock;clock.start();qint64 previous=0,maxGap=0;int beats=0;QTimer heartbeat;
        heartbeat.setInterval(10);connect(&heartbeat,&QTimer::timeout,this,[&]{const auto now=clock.elapsed();maxGap=qMax(maxGap,now-previous);previous=now;++beats;});heartbeat.start();
        const auto request=proxy.requestEnable(12345,1);QVERIFY(request);QVERIFY(proxy.busy());QVERIFY(!proxy.owned());
        QTimer::singleShot(350,&proxy,[adapter]{adapter->ready=true;});
        QTRY_COMPARE_WITH_TIMEOUT(completed.count(),1,3000);
        QVERIFY(completed.first().at(1).toBool());QVERIFY(proxy.owned());QVERIFY(!proxy.busy());
        QVERIFY2(beats>=10,"Readiness waiting must return to the Qt event loop");
        QVERIFY2(maxGap<500,qPrintable(QStringLiteral("GUI heartbeat stalled for %1 ms").arg(maxGap)));
        qInfo("Proxy readiness heartbeat: samples=%d maximum_gap_ms=%lld elapsed_ms=%lld",beats,static_cast<long long>(maxGap),static_cast<long long>(clock.elapsed()));
        QCOMPARE(adapter->memory.enableCalls,1);QVERIFY(proxy.disable());QVERIFY(adapter->memory.current().systemEnabled);
    }
    void guardTimeoutPreservesExternalProxyAndContinuesDispatching() {
        auto backend=std::make_unique<DeferredProxyBackend>();auto *adapter=backend.get();
        SystemProxySession proxy(nullptr,{},std::move(backend));QSignalSpy completed(&proxy,&SystemProxySession::enableFinished);
        QElapsedTimer clock;clock.start();int beats=0;QTimer heartbeat;heartbeat.setInterval(10);connect(&heartbeat,&QTimer::timeout,this,[&]{++beats;});heartbeat.start();
        QVERIFY(proxy.requestEnable(12345,1));QTRY_COMPARE_WITH_TIMEOUT(completed.count(),1,4000);
        QVERIFY(!completed.first().at(1).toBool());QVERIFY(!proxy.busy());QVERIFY(!proxy.owned());QVERIFY(proxy.systemEnabled());
        QCOMPARE(adapter->memory.enableCalls,0);QVERIFY(adapter->cancellations>0);QVERIFY(!proxy.error().isEmpty());
        QVERIFY(clock.elapsed()>=1800);QVERIFY(beats>=50);
        qInfo("Proxy timeout heartbeat: samples=%d elapsed_ms=%lld",beats,static_cast<long long>(clock.elapsed()));
    }
    void cancellationAndLateReadinessCannotAcquireAnOldRequest() {
        auto backend=std::make_unique<DeferredProxyBackend>();auto *adapter=backend.get();
        SystemProxySession proxy(nullptr,{},std::move(backend));QSignalSpy completed(&proxy,&SystemProxySession::enableFinished);
        const auto oldRequest=proxy.requestEnable(12345,1);QTRY_VERIFY(adapter->preparations>0);
        QVERIFY(proxy.disable());QVERIFY(!proxy.busy());adapter->ready=true;QTest::qWait(60);
        QCOMPARE(adapter->memory.enableCalls,0);QVERIFY(!proxy.owned());QCOMPARE(completed.count(),1);
        QCOMPARE(completed.first().at(0).toULongLong(),oldRequest);QVERIFY(!completed.first().at(1).toBool());
        const auto next=proxy.requestEnable(12346,2);QVERIFY(next!=oldRequest);QTRY_VERIFY(proxy.owned());
        QCOMPARE(adapter->memory.enableCalls,1);QCOMPARE(adapter->memory.lastPort,12346);QCOMPARE(adapter->memory.lastPid,qint64(2));
    }
    void staleEngineGenerationAndExternalChangesNeverReachTheWrite() {
        for(const bool external:{false,true}) {
            auto backend=std::make_unique<DeferredProxyBackend>();auto *adapter=backend.get();
            SystemProxySession proxy(nullptr,{},std::move(backend));QSignalSpy completed(&proxy,&SystemProxySession::enableFinished);bool valid=true;
            QVERIFY(proxy.requestEnable(12345,1,[&]{return valid;}));QTRY_VERIFY(adapter->preparations>0);
            if(external)adapter->externalChanged=true;else valid=false;
            adapter->ready=true;QTRY_COMPARE(completed.count(),1);
            QVERIFY(!completed.first().at(1).toBool());QCOMPARE(adapter->memory.enableCalls,0);
            QVERIFY(!proxy.owned());QVERIFY(proxy.systemEnabled());QVERIFY(!proxy.error().isEmpty());
        }
    }
    void configuredProxyModes_data() {
        QTest::addColumn<int>("flags");QTest::addColumn<bool>("enabled");
        QTest::newRow("direct")<<1<<false;
        QTest::newRow("manual")<<3<<true;
        QTest::newRow("pac-url")<<5<<true;
        QTest::newRow("automatic-detection")<<9<<true;
        QTest::newRow("manual-and-automatic")<<11<<true;
    }
    void configuredProxyModes() {
        QFETCH(int,flags);QFETCH(bool,enabled);
        QCOMPARE(SystemProxyState::configuredEnabled(fixture(flags,registryFlag(0))),enabled);
    }
    void invalidAutomaticConfigurationIsNotInferred() {
        auto raw=fixture(5,registryFlag(0));raw.remove("pac");
        QVERIFY(!SystemProxyState::configuredEnabled(raw));
        raw["flags"]=QStringLiteral("9");QVERIFY(!SystemProxyState::configuredEnabled(raw));
        raw["flags"]=1e20;QVERIFY(!SystemProxyState::configuredEnabled(raw));
        raw=fixture(1,registryFlag(1));QVERIFY(SystemProxyState::configuredEnabled(raw));
    }
    void manualStores_data() {
        QTest::addColumn<int>("flags");
        QTest::addColumn<quint32>("nativeFlag");
        QTest::addColumn<bool>("winInet");
        QTest::addColumn<bool>("native");
        QTest::newRow("both-disabled") << 1 << quint32(0) << false << false;
        QTest::newRow("native-only-enabled") << 1 << quint32(1) << false << true;
        QTest::newRow("wininet-only-enabled") << 3 << quint32(0) << true << false;
        QTest::newRow("both-enabled") << 3 << quint32(1) << true << true;
        QTest::newRow("pac-is-not-manual") << 5 << quint32(0) << false << false;
        QTest::newRow("auto-detect-is-not-manual") << 9 << quint32(0) << false << false;
        QTest::newRow("native-nonzero-dword") << 1 << quint32(0x10000000) << false << true;
    }
    void manualStores() {
        QFETCH(int, flags);QFETCH(quint32, nativeFlag);QFETCH(bool, winInet);QFETCH(bool, native);
        const auto raw = fixture(flags, registryFlag(nativeFlag));
        const auto state = SystemProxyState::inspect(raw);
        QVERIFY(state.winInet.isValid());QVERIFY(state.registry.isValid());
        QCOMPARE(state.winInet.toBool(), winInet);QCOMPARE(state.registry.toBool(), native);
        QCOMPARE(state.enabled(), winInet || native);QCOMPARE(state.differs(), winInet != native);
        const auto diagnostics = state.diagnostics();
        QVERIFY(diagnostics.value("known").toBool());
        QCOMPARE(diagnostics.value("stateDiffers").toBool(), winInet != native);
        QCOMPARE(diagnostics.value("registryValuePresent").toBool(), true);
        const auto json = QJsonDocument(QJsonObject::fromVariantMap(diagnostics)).toJson();
        for (const auto *secret : {"fixture-secret", "private.example", "private-bypass", "private-pac", "ProxyServer", "data"})
            QVERIFY(!json.contains(secret));
        QCOMPARE(raw, fixture(flags, registryFlag(nativeFlag)));
    }
    void unknownRegistryValues_data() {
        QTest::addColumn<QJsonObject>("value");
        QTest::newRow("missing") << QJsonObject{};
        QTest::newRow("absent") << QJsonObject{{"present", false}};
        QTest::newRow("untyped-presence") << QJsonObject{{"present", "true"}, {"type", 4}, {"data", "AQAAAA=="}};
        QTest::newRow("wrong-type") << QJsonObject{{"present", true}, {"type", 1}, {"data", "AQAAAA=="}};
        QTest::newRow("string-type") << QJsonObject{{"present", true}, {"type", "4"}, {"data", "AQAAAA=="}};
        QTest::newRow("fractional-type") << QJsonObject{{"present", true}, {"type", 4.5}, {"data", "AQAAAA=="}};
        QTest::newRow("null-data") << QJsonObject{{"present", true}, {"type", 4}, {"data", QJsonValue::Null}};
        QTest::newRow("short-dword") << QJsonObject{{"present", true}, {"type", 4}, {"data", "AQAA"}};
        QTest::newRow("long-dword") << QJsonObject{{"present", true}, {"type", 4}, {"data", "AQAAAAAAAAA="}};
        QTest::newRow("invalid-base64") << QJsonObject{{"present", true}, {"type", 4}, {"data", "#######="}};
        QTest::newRow("noncanonical-base64") << QJsonObject{{"present", true}, {"type", 4}, {"data", "AQAAAB=="}};
        QTest::newRow("absent-with-stale-bytes") << QJsonObject{{"present", false}, {"type", 4}, {"data", "AQAAAA=="}};
    }
    void unknownRegistryValues() {
        QFETCH(QJsonObject, value);
        const auto state = SystemProxyState::inspect(fixture(1, value));
        QVERIFY(state.winInet.isValid());QVERIFY(!state.registry.isValid());
        QVERIFY(!state.differs());QVERIFY(!state.enabled());
        QVERIFY(!state.diagnostics().value("registryManualProxy").isValid());
    }
    void unknownSnapshotRemainsUnknown() {
        const auto state = SystemProxyState::inspect({});
        QVERIFY(!state.winInet.isValid());QVERIFY(!state.registry.isValid());
        QVERIFY(!state.registryValuePresent.isValid());
        QVERIFY(!state.diagnostics().value("known").toBool());
        for (const auto &flags : {QJsonValue("3"), QJsonValue(3.5), QJsonValue(-1), QJsonValue(4294967296.0), QJsonValue(QJsonValue::Null)}) {
            auto raw = fixture(1, registryFlag(1));raw.insert("flags", flags);
            const auto invalid = SystemProxyState::inspect(raw);
            QVERIFY(!invalid.winInet.isValid());QVERIFY(!invalid.differs());
            QVERIFY(invalid.registry.toBool());QVERIFY(invalid.enabled());
        }
    }
    void liveDiagnosticIsReadOnly() {
        const auto before = SystemProxySession::snapshot();
        QTemporaryDir temp;QVERIFY(temp.isValid());
        const auto journal = temp.filePath("read-only.dpapi");
        SystemProxySession proxy(nullptr, journal);
        const auto state = proxy.diagnosticState();
        for (const auto *key : {"server", "pac", "bypass", "registry"}) QVERIFY(!state.contains(key));
        QVERIFY(!state.value("owned").toBool());QVERIFY(!state.value("recoveryJournalPresent").toBool());
        QVERIFY(!state.value("guardAcknowledged").toBool());QVERIFY(!QFile::exists(journal));
        if (before.isEmpty()) {
            QVERIFY(!state.value("known").toBool());QVERIFY(!state.value("winInetManualProxy").isValid());
            QVERIFY(!state.value("registryManualProxy").isValid());QVERIFY(!state.value("readError").toString().isEmpty());
            QCOMPARE(proxy.stateReadError(), state.value("readError").toString());
        } else {
            const auto expected = SystemProxyState::inspect(before);
            QCOMPARE(proxy.systemEnabled(), SystemProxyState::configuredEnabled(before));QCOMPARE(proxy.stateDiffers(), expected.differs());
            QCOMPARE(state.value("winInetManualProxy"), expected.winInet);
            QCOMPARE(state.value("registryManualProxy"), expected.registry);
            QVERIFY(state.value("readError").toString().isEmpty());
        }
        QCOMPARE(SystemProxySession::snapshot(), before);
    }
#ifdef Q_OS_WIN
    void nativeRegistryReaderUsesIsolatedFixture() {
        // A unique volatile key only. No RegOverridePredefKey, InternetSetOption
        // or write to the real Internet Settings key is performed by this test.
        const auto path = QStringLiteral("Software\\SwirlProxyStateFixture-%1").arg(QUuid::createUuid().toString(QUuid::Id128));
        struct FixtureKey {
            QString path;HKEY key{};bool created = false;
            ~FixtureKey() {
                if (key) RegCloseKey(key);
                if (created) RegDeleteTreeW(HKEY_CURRENT_USER, reinterpret_cast<const wchar_t *>(path.utf16()));
            }
        } fixtureKey{path};
        DWORD disposition = 0;
        QCOMPARE(RegCreateKeyExW(HKEY_CURRENT_USER, reinterpret_cast<const wchar_t *>(path.utf16()), 0, nullptr,
                                 REG_OPTION_VOLATILE, KEY_QUERY_VALUE | KEY_SET_VALUE, nullptr, &fixtureKey.key, &disposition), LONG(ERROR_SUCCESS));
        fixtureKey.created = disposition == REG_CREATED_NEW_KEY;
        QVERIFY(fixtureKey.created);
        const auto read = [&] { return SystemProxyState::readRegistry(HKEY_CURRENT_USER, reinterpret_cast<const wchar_t *>(path.utf16())); };
        const auto missing = read();QCOMPARE(missing.size(), 4);
        QCOMPARE(missing.value("ProxyEnable").toObject().value("present").toBool(), false);
        const QString server = QStringLiteral("fixture-user:fixture-password@private.example:1080");
        QCOMPARE(RegSetValueExW(fixtureKey.key, L"ProxyServer", 0, REG_SZ,
                               reinterpret_cast<const BYTE *>(server.utf16()), DWORD((server.size() + 1) * sizeof(wchar_t))), LONG(ERROR_SUCCESS));
        for (const DWORD value : {DWORD(0), DWORD(1)}) {
            QCOMPARE(RegSetValueExW(fixtureKey.key, L"ProxyEnable", 0, REG_DWORD,
                                   reinterpret_cast<const BYTE *>(&value), sizeof(value)), LONG(ERROR_SUCCESS));
            const auto registry = read();
            const auto raw = QJsonObject{{"flags", 1}, {"registry", registry}};
            const auto state = SystemProxyState::inspect(raw);
            QVERIFY(state.registry.isValid());QCOMPARE(state.registry.toBool(), value != 0);
            QCOMPARE(state.enabled(), value != 0);QCOMPARE(state.differs(), value != 0);
            const auto json = QJsonDocument(QJsonObject::fromVariantMap(state.diagnostics())).toJson();
            QVERIFY(!json.contains("fixture-user"));QVERIFY(!json.contains("fixture-password"));
            QCOMPARE(read(), registry);
        }
        const wchar_t malformed[] = L"1";
        QCOMPARE(RegSetValueExW(fixtureKey.key, L"ProxyEnable", 0, REG_SZ,
                               reinterpret_cast<const BYTE *>(malformed), sizeof(malformed)), LONG(ERROR_SUCCESS));
        QVERIFY(!SystemProxyState::inspect({{"flags", 1}, {"registry", read()}}).registry.isValid());
        QCOMPARE(RegDeleteValueW(fixtureKey.key, L"ProxyEnable"), LONG(ERROR_SUCCESS));
        QVERIFY(!SystemProxyState::inspect({{"flags", 1}, {"registry", read()}}).registry.isValid());
        const QByteArray excessive(65537, 'x');
        QCOMPARE(RegSetValueExW(fixtureKey.key, L"ProxyServer", 0, REG_BINARY,
                               reinterpret_cast<const BYTE *>(excessive.constData()), DWORD(excessive.size())), LONG(ERROR_SUCCESS));
        QString error;
        QVERIFY(SystemProxyState::readRegistry(HKEY_CURRENT_USER, reinterpret_cast<const wchar_t *>(path.utf16()), &error).isEmpty());
        QVERIFY(!error.isEmpty());QVERIFY(!error.contains(path));
    }
#endif
};

QTEST_GUILESS_MAIN(SystemProxyStateTests)
#include "SystemProxyStateTests.moc"
