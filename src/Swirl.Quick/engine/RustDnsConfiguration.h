#pragma once
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSet>
#include <QUrl>
#include <QVariantMap>

// Conversion only: no DNS queries, system configuration changes or GUI changes.
// Network execution and TLS authentication belong to the Rust resolver.
namespace SwirlRustDns {
inline bool usableAddress(const QHostAddress &address) {
    return !address.isNull() && address.scopeId().isEmpty() && !address.isMulticast()
        && address != QHostAddress(QHostAddress::AnyIPv4)
        && address != QHostAddress(QHostAddress::AnyIPv6);
}
inline QString endpoint(const QHostAddress &address, int port) {
    const auto host = address.toString();
    return (address.protocol() == QAbstractSocket::IPv6Protocol ? "[" + host + "]" : host)
        + ":" + QString::number(port);
}
inline QString configuration(const QVariantMap &input, QJsonObject *output) {
    const auto dns = QJsonObject::fromVariantMap(input);
    const auto invalid = [] {
        return QString("Rust DNS 支持系统解析、自定义 IP DNS、精确映射和严格 DoT；配置含无效或尚未支持的选项。");
    };
    for (auto it = dns.begin(); it != dns.end(); ++it)
        if (!QStringList{"mode", "servers", "encrypted", "hosts", "useHosts", "respectRules"}.contains(it.key()))
            return invalid();
    if (dns.contains("mode") && (!dns.value("mode").isDouble()
        || (dns.value("mode").toDouble() != 0 && dns.value("mode").toDouble() != 2)))
        return invalid();
    const bool custom = dns.value("mode").toInt() == 2;
    for (const auto &key : QStringList{"servers", "encrypted"})
        if (dns.contains(key) && !dns.value(key).isString()) return invalid();
    const auto encrypted = dns.value("encrypted").toString().trimmed();
    const auto rawServers = dns.value("servers").toString();
    // Bootstrap via traditional DNS and mixed system/custom mode are separate
    // future stages. Never silently query an application target in plaintext.
    if (!encrypted.isEmpty() && (custom || !rawServers.trimmed().isEmpty()))
        return "Rust DoT 此阶段请使用系统模式、留空传统服务器，并用显式 IP 或精确本地映射指定 DoT 端点。";
    if (!custom && !rawServers.trimmed().isEmpty()) return invalid();
    QJsonArray servers;
    QSet<QString> serverSet;
    if (custom) {
        for (const auto &part : rawServers.split(',')) {
            QHostAddress address;
            if (!address.setAddress(part.trimmed()) || !usableAddress(address)) return invalid();
            const auto value = address.toString();
            if (serverSet.contains(value)) return invalid();
            serverSet.insert(value);
            servers.append(endpoint(address, 53));
        }
        if (servers.isEmpty() || servers.size() > 4) return invalid();
    }
    for (const auto &key : QStringList{"useHosts", "respectRules"})
        if (dns.contains(key) && !dns.value(key).isBool()) return invalid();
    // Only pure OS lookup cannot independently disable the OS hosts file.
    if (!custom && encrypted.isEmpty() && dns.contains("useHosts") && !dns.value("useHosts").toBool())
        return invalid();
    if (dns.contains("hosts") && !dns.value("hosts").isArray()) return invalid();
    const auto hosts = dns.value("hosts").toArray();
    if (hosts.size() > 512) return invalid();
    QSet<QString> seen;
    QJsonArray mapped;
    const QRegularExpression hostPattern("^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$");
    for (const auto &value : hosts) {
        if (!value.isObject()) return invalid();
        const auto row = value.toObject();
        for (auto it = row.begin(); it != row.end(); ++it)
            if (!QStringList{"id", "name", "value", "server", "comment"}.contains(it.key())) return invalid();
        for (const auto &key : QStringList{"id", "server", "comment"})
            if (row.contains(key) && !row.value(key).isNull() && !row.value(key).isString()) return invalid();
        if (!row.value("server").toString().isEmpty() || !row.value("name").isString() || !row.value("value").isString())
            return invalid();
        const auto name = row.value("name").toString().toLower();
        QHostAddress address;
        if (name.size() > 253 || !hostPattern.match(name).hasMatch() || !QHostAddress(name).isNull()
            || seen.contains(name) || !address.setAddress(row.value("value").toString()) || !address.scopeId().isEmpty())
            return invalid();
        seen.insert(name);
        mapped.append(QJsonObject{{"name", name}, {"address", address.toString()}});
    }
    QJsonArray tlsServers;
    if (!encrypted.isEmpty()) {
        // Restrict the literal syntax before QUrl normalizes it. Reject userinfo,
        // percent escapes, paths and query options rather than silently stripping.
        const QRegularExpression syntax("^tls://(?:\\[[0-9A-Fa-f:]+\\]|[A-Za-z0-9.-]+)(?::[0-9]{1,5})?/?$");
        const QUrl url(encrypted, QUrl::StrictMode);
        if (encrypted.size() > 1024 || !syntax.match(encrypted).hasMatch()
            || !url.isValid() || url.scheme() != "tls" || !url.userInfo().isEmpty()
            || url.hasQuery() || url.hasFragment() || (!url.path().isEmpty() && url.path() != "/"))
            return invalid();
        const auto name = url.host().toLower();
        const int port = url.port(853);
        if (port < 1 || port > 65535 || name.size() > 253 || name.isEmpty()) return invalid();
        QHostAddress address;
        if (!address.setAddress(name)) {
            if (!hostPattern.match(name).hasMatch()) return invalid();
            for (const auto &row : mapped) {
                const auto host = row.toObject();
                if (host.value("name").toString() == name)
                    address.setAddress(host.value("address").toString());
            }
            if (address.isNull())
                return "Rust DoT 服务器域名需要精确本地 IP 映射；未使用系统 DNS 引导或明文回退。";
        }
        if (!usableAddress(address)) return invalid();
        tlsServers.append(QJsonObject{
            {"address", endpoint(address, port)},
            {"tls", QJsonObject{{"server_name", name}, {"alpn", QJsonArray{"dot"}}}}
        });
    }
    QJsonObject result{{"hosts", mapped}, {"force_proxy_hosts", dns.value("respectRules").toBool()},
        {"servers", servers}, {"use_system_hosts", !dns.contains("useHosts") || dns.value("useHosts").toBool()}};
    // Leave legacy JSON unchanged when the new feature is inactive.
    if (!tlsServers.isEmpty()) result["tls_servers"] = tlsServers;
    *output = result;
    return {};
}
}
