#include "NativeTunRecovery.h"
#include "engine/NativeTunBrokerClient.h"
#include <QJsonObject>
#include <QScopeGuard>
#include <QUuid>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

namespace {
constexpr auto MarkerKey = L"Software\\SOLHK\\Swirl\\NativeTun";
constexpr auto MarkerValue = L"recoveryPending";
bool registryError(QString *error, const char *stage, LSTATUS status) {
    if (error) *error = QStringLiteral("%1 (Windows %2)").arg(QString::fromLatin1(stage)).arg(status);
    return false;
}
bool recoveryPending(bool *pending, QString *error) {
    *pending = false;
    HKEY key = nullptr;
    const auto opened = RegOpenKeyExW(HKEY_CURRENT_USER, MarkerKey, 0, KEY_QUERY_VALUE | KEY_WOW64_32KEY, &key);
    if (opened == ERROR_FILE_NOT_FOUND) return true;
    if (opened != ERROR_SUCCESS) return registryError(error, "TunRecoveryMarkerRead", opened);
    const auto close = qScopeGuard([&] { RegCloseKey(key); });
    DWORD type = 0, value = 0, bytes = sizeof(value);
    const auto queried = RegQueryValueExW(key, MarkerValue, nullptr, &type, reinterpret_cast<BYTE *>(&value), &bytes);
    if (queried == ERROR_FILE_NOT_FOUND) return true;
    if (queried != ERROR_SUCCESS) return registryError(error, "TunRecoveryMarkerRead", queried);
    if (type != REG_DWORD || bytes != sizeof(value) || value > 1)
        return registryError(error, "TunRecoveryMarkerInvalid", ERROR_INVALID_DATA);
    *pending = value == 1;
    return true;
}
}
#endif

bool setNativeTunRecoveryPending(bool pending, QString *error) {
    if (error) error->clear();
#ifdef Q_OS_WIN
    HKEY key = nullptr;
    const auto opened = pending
        ? RegCreateKeyExW(HKEY_CURRENT_USER, MarkerKey, 0, nullptr, REG_OPTION_NON_VOLATILE,
            KEY_QUERY_VALUE | KEY_SET_VALUE | KEY_WOW64_32KEY, nullptr, &key, nullptr)
        : RegOpenKeyExW(HKEY_CURRENT_USER, MarkerKey, 0, KEY_QUERY_VALUE | KEY_SET_VALUE | KEY_WOW64_32KEY, &key);
    if (!pending && opened == ERROR_FILE_NOT_FOUND) return true;
    if (opened != ERROR_SUCCESS) return registryError(error, "TunRecoveryMarkerWrite", opened);
    const auto close = qScopeGuard([&] { RegCloseKey(key); });
    const DWORD value = pending ? 1 : 0;
    const auto written = RegSetValueExW(key, MarkerValue, 0, REG_DWORD, reinterpret_cast<const BYTE *>(&value), sizeof(value));
    if (written != ERROR_SUCCESS) return registryError(error, "TunRecoveryMarkerWrite", written);
    const auto flushed = RegFlushKey(key);
    return flushed == ERROR_SUCCESS || registryError(error, "TunRecoveryMarkerFlush", flushed);
#else
    Q_UNUSED(pending);
    if (error) *error = QStringLiteral("TunWindowsRequired");
    return false;
#endif
}

int recoverNativeTunForMaintenance(QString *error) {
    if (error) error->clear();
#ifdef Q_OS_WIN
    bool pending = false;
    if (!recoveryPending(&pending, error)) return 2;
    // Ordinary installs and previously confirmed sessions never request UAC.
    if (!pending) return 0;
    NativeTunBrokerClient broker;
    if (!broker.launch(error)) return 2;
    const auto id = QUuid::createUuid().toString(QUuid::WithoutBraces);
    const auto response = broker.command({{"native_tun_schema", 1}, {"op", "native_tun_recover"}, {"request_id", id}});
    const auto owners = response.value("active_owners");
    const bool recovered = response.value("ok") == QJsonValue(true) &&
        response.value("native_tun_schema") == QJsonValue(1) && response.value("request_id") == QJsonValue(id) &&
        response.value("state") == QJsonValue("recovered") && owners == QJsonValue(0);
    QString closeError;
    const bool closed = broker.close(&closeError);
    if (!recovered || !closed) {
        if (error) *error = !closed ? closeError : QStringLiteral("TunRecoveryUnconfirmed");
        return 2;
    }
    return setNativeTunRecoveryPending(false, error) ? 0 : 2;
#else
    if (error) *error = QStringLiteral("TunWindowsRequired");
    return 2;
#endif
}
