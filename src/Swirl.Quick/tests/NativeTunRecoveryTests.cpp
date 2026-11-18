#include "app/NativeTunRecovery.h"
#include "engine/RustCoreEngine.h"
#include "engine/ThreadedEngine.h"
#include <QScopeGuard>
#include <QUuid>
#include <QtTest>

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <sddl.h>

namespace {
constexpr auto MarkerKey = L"Software\\SOLHK\\Swirl\\NativeTun";
constexpr auto MarkerValue = L"recoveryPending";

QByteArray dwordBytes(DWORD value) {
    return QByteArray(reinterpret_cast<const char *>(&value), sizeof(value));
}

EngineStartOptions probeOptions(bool physical) {
    EngineStartOptions options;
    options.proxyPort = 0;
    options.internalProbeListener = true;
    options.internalProbePhysicalEgress = physical;
    options.directSession = true;
    options.routingMode = QStringLiteral("direct");
    return options;
}
}

class NativeTunRecoveryTests final : public QObject {
    Q_OBJECT
    HKEY m_userRoot = nullptr;
    HKEY m_fixtureRoot = nullptr;
    QString m_fixturePath;
    bool m_overridden = false;

    LSTATUS createMarker(HKEY *key) {
        return RegCreateKeyExW(HKEY_CURRENT_USER, MarkerKey, 0, nullptr,
            REG_OPTION_VOLATILE, KEY_ALL_ACCESS | KEY_WOW64_32KEY, nullptr, key, nullptr);
    }

private slots:
    void init() {
        // The override is confined to this GUI-less test process. Keep an
        // unredirected handle so cleanup never depends on the override.
        QCOMPARE(RegOpenCurrentUser(KEY_ALL_ACCESS | KEY_WOW64_32KEY, &m_userRoot), LSTATUS(ERROR_SUCCESS));
        m_fixturePath = QStringLiteral("Software\\SwirlNativeTunRecoveryTests-") +
            QUuid::createUuid().toString(QUuid::WithoutBraces);
        QCOMPARE(RegCreateKeyExW(m_userRoot, reinterpret_cast<LPCWSTR>(m_fixturePath.utf16()),
            0, nullptr, REG_OPTION_VOLATILE, KEY_ALL_ACCESS | KEY_WOW64_32KEY,
            nullptr, &m_fixtureRoot, nullptr), LSTATUS(ERROR_SUCCESS));
        const auto result = RegOverridePredefKey(HKEY_CURRENT_USER, m_fixtureRoot);
        m_overridden = result == ERROR_SUCCESS;
        QCOMPARE(result, LSTATUS(ERROR_SUCCESS));
    }

    void cleanup() {
        const auto restored = m_overridden ? RegOverridePredefKey(HKEY_CURRENT_USER, nullptr) : ERROR_SUCCESS;
        m_overridden = false;
        if (m_fixtureRoot) RegCloseKey(m_fixtureRoot);
        m_fixtureRoot = nullptr;
        const auto removed = m_userRoot && !m_fixturePath.isEmpty()
            ? RegDeleteTreeW(m_userRoot, reinterpret_cast<LPCWSTR>(m_fixturePath.utf16())) : ERROR_SUCCESS;
        if (m_userRoot) RegCloseKey(m_userRoot);
        m_userRoot = nullptr;
        m_fixturePath.clear();
        QCOMPARE(restored, LSTATUS(ERROR_SUCCESS));
        QVERIFY(removed == ERROR_SUCCESS || removed == ERROR_FILE_NOT_FOUND);
    }

    void absentKeyAndValueAreClearWithoutCreatingAnything() {
        QString error = QStringLiteral("old error");
        QCOMPARE(nativeTunRecoveryState(&error), NativeTunRecoveryState::Clear);
        QVERIFY(error.isEmpty());
        HKEY absent = nullptr;
        QCOMPARE(RegOpenKeyExW(HKEY_CURRENT_USER, MarkerKey, 0,
            KEY_QUERY_VALUE | KEY_WOW64_32KEY, &absent), LSTATUS(ERROR_FILE_NOT_FOUND));
        QCOMPARE(absent, HKEY(nullptr));
        QCOMPARE(recoverNativeTunForMaintenance(&error), 0);
        QVERIFY(error.isEmpty());

        HKEY key = nullptr;
        QCOMPARE(createMarker(&key), LSTATUS(ERROR_SUCCESS));
        const auto close = qScopeGuard([&] { RegCloseKey(key); });
        QCOMPARE(nativeTunRecoveryState(&error), NativeTunRecoveryState::Clear);
        DWORD bytes = 0;
        QCOMPARE(RegQueryValueExW(key, MarkerValue, nullptr, nullptr, nullptr, &bytes), LSTATUS(ERROR_FILE_NOT_FOUND));
    }

    void pendingAndConfirmedClearHaveStrictDwordValues() {
        // Production writes keep their durable policy. A volatile test parent
        // needs an explicitly volatile fixture key before writing its values.
        HKEY key = nullptr;
        QCOMPARE(createMarker(&key), LSTATUS(ERROR_SUCCESS));
        const auto close = qScopeGuard([&] { RegCloseKey(key); });
        QString error;
        QVERIFY(setNativeTunRecoveryPending(true, &error));
        QVERIFY(error.isEmpty());
        QCOMPARE(nativeTunRecoveryState(&error), NativeTunRecoveryState::Pending);
        // Repeated observation does not clear or acknowledge an old owner.
        QCOMPARE(nativeTunRecoveryState(), NativeTunRecoveryState::Pending);
        DWORD type = 0, value = 0, bytes = sizeof(value);
        QCOMPARE(RegQueryValueExW(key, MarkerValue, nullptr, &type,
            reinterpret_cast<BYTE *>(&value), &bytes), LSTATUS(ERROR_SUCCESS));
        QCOMPARE(type, DWORD(REG_DWORD));
        QCOMPARE(bytes, DWORD(sizeof(DWORD)));
        QCOMPARE(value, DWORD(1));

        QVERIFY(setNativeTunRecoveryPending(false, &error));
        QCOMPARE(nativeTunRecoveryState(&error), NativeTunRecoveryState::Clear);
        QVERIFY(error.isEmpty());
        bytes = sizeof(value);
        QCOMPARE(RegQueryValueExW(key, MarkerValue, nullptr, &type,
            reinterpret_cast<BYTE *>(&value), &bytes), LSTATUS(ERROR_SUCCESS));
        QCOMPARE(type, DWORD(REG_DWORD));
        QCOMPARE(bytes, DWORD(sizeof(DWORD)));
        QCOMPARE(value, DWORD(0));
    }

    void malformedMarkerIsUnknownAndMaintenanceDoesNotProceed_data() {
        QTest::addColumn<quint32>("type");
        QTest::addColumn<QByteArray>("raw");
        const wchar_t text[] = L"1";
        const quint64 wide = 1;
        QTest::newRow("string") << quint32(REG_SZ) << QByteArray(reinterpret_cast<const char *>(text), sizeof(text));
        QTest::newRow("binary") << quint32(REG_BINARY) << dwordBytes(1);
        QTest::newRow("qword") << quint32(REG_QWORD) << QByteArray(reinterpret_cast<const char *>(&wide), sizeof(wide));
        QTest::newRow("dword-zero-bytes") << quint32(REG_DWORD) << QByteArray();
        QTest::newRow("dword-short") << quint32(REG_DWORD) << QByteArray(1, '\1');
        QTest::newRow("dword-long") << quint32(REG_DWORD) << QByteArray(8, '\0');
        QTest::newRow("dword-two") << quint32(REG_DWORD) << dwordBytes(2);
        QTest::newRow("dword-max") << quint32(REG_DWORD) << dwordBytes(MAXDWORD);
    }

    void malformedMarkerIsUnknownAndMaintenanceDoesNotProceed() {
        QFETCH(quint32, type);
        QFETCH(QByteArray, raw);
        HKEY key = nullptr;
        QCOMPARE(createMarker(&key), LSTATUS(ERROR_SUCCESS));
        const auto close = qScopeGuard([&] { RegCloseKey(key); });
        QCOMPARE(RegSetValueExW(key, MarkerValue, 0, DWORD(type),
            reinterpret_cast<const BYTE *>(raw.constData()), DWORD(raw.size())), LSTATUS(ERROR_SUCCESS));
        QString error;
        QCOMPARE(nativeTunRecoveryState(&error), NativeTunRecoveryState::Unknown);
        QVERIFY(error.startsWith(QStringLiteral("TunRecoveryMarker")));
        const auto queryError = error;
        QCOMPARE(recoverNativeTunForMaintenance(&error), 2);
        // The exact query error proves the maintenance guard returns before
        // broker.launch(), whose errors belong to the TunBroker namespace.
        QCOMPARE(error, queryError);
        DWORD actualType = 0, bytes = 64;
        QByteArray actual(int(bytes), Qt::Uninitialized);
        QCOMPARE(RegQueryValueExW(key, MarkerValue, nullptr, &actualType,
            reinterpret_cast<BYTE *>(actual.data()), &bytes), LSTATUS(ERROR_SUCCESS));
        actual.resize(bytes);
        QCOMPARE(actualType, DWORD(type));
        QCOMPARE(actual, raw);
    }

    void accessDeniedIsUnknownAndMaintenanceDoesNotProceed() {
        HKEY key = nullptr;
        QCOMPARE(createMarker(&key), LSTATUS(ERROR_SUCCESS));
        const auto close = qScopeGuard([&] { RegCloseKey(key); });
        const DWORD value = 1;
        QCOMPARE(RegSetValueExW(key, MarkerValue, 0, REG_DWORD,
            reinterpret_cast<const BYTE *>(&value), sizeof(value)), LSTATUS(ERROR_SUCCESS));
        DWORD securityBytes = 0;
        QCOMPARE(RegGetKeySecurity(key, DACL_SECURITY_INFORMATION, nullptr, &securityBytes), LSTATUS(ERROR_INSUFFICIENT_BUFFER));
        QByteArray originalSecurity(int(securityBytes), Qt::Uninitialized);
        QCOMPARE(RegGetKeySecurity(key, DACL_SECURITY_INFORMATION,
            reinterpret_cast<PSECURITY_DESCRIPTOR>(originalSecurity.data()), &securityBytes), LSTATUS(ERROR_SUCCESS));
        PSECURITY_DESCRIPTOR denied = nullptr;
        QVERIFY(ConvertStringSecurityDescriptorToSecurityDescriptorW(
            L"D:P(D;;0x00000001;;;WD)(A;;KA;;;WD)", SDDL_REVISION_1, &denied, nullptr));
        const auto freeDenied = qScopeGuard([&] { LocalFree(denied); });
        const auto restore = qScopeGuard([&] {
            RegSetKeySecurity(key, DACL_SECURITY_INFORMATION,
                reinterpret_cast<PSECURITY_DESCRIPTOR>(originalSecurity.data()));
        });
        QCOMPARE(RegSetKeySecurity(key, DACL_SECURITY_INFORMATION, denied), LSTATUS(ERROR_SUCCESS));
        HKEY unreadable = nullptr;
        QCOMPARE(RegOpenKeyExW(HKEY_CURRENT_USER, MarkerKey, 0,
            KEY_QUERY_VALUE | KEY_WOW64_32KEY, &unreadable), LSTATUS(ERROR_ACCESS_DENIED));
        QString error;
        QCOMPARE(nativeTunRecoveryState(&error), NativeTunRecoveryState::Unknown);
        QVERIFY(error.startsWith(QStringLiteral("TunRecoveryMarkerRead")));
        const auto queryError = error;
        QCOMPARE(recoverNativeTunForMaintenance(&error), 2);
        QCOMPARE(error, queryError);
        QCOMPARE(RegSetKeySecurity(key, DACL_SECURITY_INFORMATION,
            reinterpret_cast<PSECURITY_DESCRIPTOR>(originalSecurity.data())), LSTATUS(ERROR_SUCCESS));
    }

    void facadeReportsRecoveryStateImmediately_data() {
        QTest::addColumn<quint32>("value");
        QTest::newRow("clear") << quint32(0);
        QTest::newRow("pending") << quint32(1);
        QTest::newRow("unknown") << quint32(2);
    }

    void facadeReportsRecoveryStateImmediately() {
        QFETCH(quint32, value);
        HKEY key = nullptr;
        QCOMPARE(createMarker(&key), LSTATUS(ERROR_SUCCESS));
        const auto close = qScopeGuard([&] { RegCloseKey(key); });
        const DWORD marker = value;
        QCOMPARE(RegSetValueExW(key, MarkerValue, 0, REG_DWORD,
            reinterpret_cast<const BYTE *>(&marker), sizeof(marker)), LSTATUS(ERROR_SUCCESS));
        ThreadedEngine facade;
        // No event processing or wait: callers can connect or probe directly
        // after construction, before the network worker posts any snapshot.
        const auto status = facade.status();
        const bool required = value != 0;
        QCOMPARE(status.tunRecoveryRequired, required);
        QCOMPARE(status.tunCapturePossible, required);
        QCOMPARE(status.state, required ? ProxyEngine::State::Failed : ProxyEngine::State::Stopped);
        QCOMPARE(status.error, required ? ProxyEngine::Error::OwnershipFailed : ProxyEngine::Error::None);
    }

    void inheritedPendingMarkerRejectsOrdinaryWorkerWithoutClearingOrRecovering() {
        HKEY key = nullptr;QCOMPARE(createMarker(&key), LSTATUS(ERROR_SUCCESS));RegCloseKey(key);
        QVERIFY(setNativeTunRecoveryPending(true));
        {
            RustCoreEngine worker;
            worker.start(probeOptions(false));
            QVERIFY(!worker.status().processAlive);
            QVERIFY(!worker.status().apiHealthy);
            QVERIFY(worker.status().tunRecoveryRequired);
            worker.stop();
            QVERIFY(worker.status().tunRecoveryRequired);
            QCOMPARE(nativeTunRecoveryState(), NativeTunRecoveryState::Pending);
        }
        QCOMPARE(nativeTunRecoveryState(), NativeTunRecoveryState::Pending);
    }

    void trustedPhysicalWorkerRetainsTheOtherSessionsPendingMarker() {
        HKEY key = nullptr;QCOMPARE(createMarker(&key), LSTATUS(ERROR_SUCCESS));RegCloseKey(key);
        QVERIFY(setNativeTunRecoveryPending(true));
        {
            RustCoreEngine worker;
            worker.start(probeOptions(true));
            QVERIFY2(worker.status().processAlive, qPrintable(worker.status().message));
            QVERIFY2(worker.status().apiHealthy, qPrintable(worker.status().message));
            QCOMPARE(nativeTunRecoveryState(), NativeTunRecoveryState::Pending);
            worker.stop();
            QVERIFY(!worker.status().processAlive);
            QCOMPARE(nativeTunRecoveryState(), NativeTunRecoveryState::Pending);
        }
        QCOMPARE(nativeTunRecoveryState(), NativeTunRecoveryState::Pending);
    }

    void unknownMarkerRejectsEvenTrustedPhysicalWorkerWithoutClearingOrRecovering() {
        HKEY key = nullptr;
        QCOMPARE(createMarker(&key), LSTATUS(ERROR_SUCCESS));
        const auto close = qScopeGuard([&] { RegCloseKey(key); });
        const DWORD invalid = 2;
        QCOMPARE(RegSetValueExW(key, MarkerValue, 0, REG_DWORD,
            reinterpret_cast<const BYTE *>(&invalid), sizeof(invalid)), LSTATUS(ERROR_SUCCESS));
        {
            RustCoreEngine worker;
            worker.start(probeOptions(true));
            QVERIFY(!worker.status().processAlive);
            QVERIFY(!worker.status().apiHealthy);
            QVERIFY(worker.status().tunRecoveryRequired);
            worker.stop();
            QCOMPARE(nativeTunRecoveryState(), NativeTunRecoveryState::Unknown);
        }
        QCOMPARE(nativeTunRecoveryState(), NativeTunRecoveryState::Unknown);
    }
};

QTEST_GUILESS_MAIN(NativeTunRecoveryTests)
#include "NativeTunRecoveryTests.moc"
