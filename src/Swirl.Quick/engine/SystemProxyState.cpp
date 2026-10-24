#include "SystemProxyState.h"

#include <QtEndian>
#include <limits>

namespace SystemProxyState {
ManualProxy inspect(const QJsonObject &snapshot) {
    ManualProxy state;
    const auto flags = snapshot.value("flags");
    const double number = flags.toDouble(-1);
    if (flags.isDouble() && number >= 0 && number <= std::numeric_limits<quint32>::max()
        && number == double(quint32(number)))
        state.winInet = (quint32(number) & 2u) != 0; // PROXY_TYPE_PROXY

    const auto value = snapshot.value("registry").toObject().value("ProxyEnable").toObject();
    if (value.value("present").isBool())
        state.registryValuePresent = value.value("present").toBool();
    // REG_DWORD is exactly four little-endian bytes. Missing or malformed
    // values are unknown, not a fabricated disabled/enabled result.
    if (state.registryValuePresent.toBool() && value.value("type").isDouble()
        && value.value("type").toDouble() == 4 && value.value("data").isString()) {
        const auto encoded = value.value("data").toString();
        if (encoded.size() == 8) {
            const auto bytes = QByteArray::fromBase64(encoded.toLatin1());
            if (bytes.size() == 4 && QString::fromLatin1(bytes.toBase64()) == encoded)
                state.registry = qFromLittleEndian<quint32>(bytes.constData()) != 0;
        }
    }
    return state;
}

bool configuredEnabled(const QJsonObject &snapshot) {
    const auto manual=inspect(snapshot);
    if(manual.enabled())return true;
    if(!manual.winInet.isValid())return false;
    const auto flags=quint32(snapshot.value("flags").toDouble());
    return (flags&8u)!=0||((flags&4u)!=0&&!snapshot.value("pac").toString().isEmpty());
}

QVariantMap ManualProxy::diagnostics() const {
    // An allowlist: never copy server/PAC/bypass addresses or registry bytes.
    return {{"known", winInet.isValid()}, {"winInetManualProxy", winInet},
            {"registryManualProxy", registry}, {"registryValuePresent", registryValuePresent},
            {"stateDiffers", differs()}};
}

#ifdef Q_OS_WIN
QJsonObject readRegistry(HKEY root, const wchar_t *subKey, QString *error) {
    constexpr const wchar_t *names[] = {L"ProxyEnable", L"ProxyServer", L"ProxyOverride", L"AutoConfigURL"};
    constexpr const char *keys[] = {"ProxyEnable", "ProxyServer", "ProxyOverride", "AutoConfigURL"};
    HKEY key{};
    auto status = RegOpenKeyExW(root, subKey, 0, KEY_QUERY_VALUE, &key);
    if (status != ERROR_SUCCESS) {
        SetLastError(status);
        if (error) *error = QStringLiteral("无法读取当前用户代理注册表（错误 %1）。").arg(status);
        return {};
    }
    QJsonObject result;
    for (int i = 0; i < 4; ++i) {
        DWORD type = 0, size = 0;
        status = RegQueryValueExW(key, names[i], nullptr, &type, nullptr, &size);
        if (status == ERROR_FILE_NOT_FOUND) {
            result.insert(keys[i], QJsonObject{{"present", false}});
            continue;
        }
        if (status != ERROR_SUCCESS || size > 65536) {
            RegCloseKey(key);
            if (error) *error = QStringLiteral("无法安全读取代理注册表值。");
            return {};
        }
        QByteArray bytes(size, Qt::Uninitialized);
        status = RegQueryValueExW(key, names[i], nullptr, &type,
                                 reinterpret_cast<BYTE *>(bytes.data()), &size);
        if (status != ERROR_SUCCESS) {
            RegCloseKey(key);
            if (error) *error = QStringLiteral("代理注册表值在读取时发生变化。");
            return {};
        }
        bytes.resize(size);
        result.insert(keys[i], QJsonObject{{"present", true}, {"type", double(type)},
                                          {"data", QString::fromLatin1(bytes.toBase64())}});
    }
    RegCloseKey(key);
    return result;
}
#endif
}
