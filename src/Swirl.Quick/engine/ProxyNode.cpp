#include "ProxyNode.h"
#include <QHostAddress>
#include <QRegularExpression>
#include <QUrl>
#include <QUuid>

static bool validHost(const QString &host) {
    QHostAddress address;
    if (address.setAddress(host)) return true;
    const auto ascii = QString::fromLatin1(QUrl::toAce(host));
    static const QRegularExpression dns(QStringLiteral("^(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?$"));
    if (!dns.match(ascii).hasMatch()) return false;
    for (const auto &label : ascii.split('.'))
        if (label.isEmpty() || label.size() > 63 || label.startsWith('-') || label.endsWith('-')) return false;
    return true;
}
QString ProxyNode::validate(const ProxyNode &n) {
    if (QUuid(n.id).isNull()) return QStringLiteral("节点标识无效。");
    if (n.name.trimmed().isEmpty() || n.name.size() > 128 || n.name.contains(QRegularExpression("[\\x00-\\x1f]")))
        return QStringLiteral("节点名称不能为空、超过 128 字符或包含控制字符。");
    if (!validHost(n.host) || n.port == 0) return QStringLiteral("服务器应为有效 IP 或域名，端口必须在 1–65535 之间。");
    if (n.protocol != "socks5" && n.protocol != "ss" && n.protocol != "trojan") return QStringLiteral("当前只支持 SOCKS5、Shadowsocks 和 Trojan。");
    if (n.password.size() > 4096 || n.username.size() > 255) return QStringLiteral("凭据长度超过支持范围。");
    if (n.protocol == "socks5" && (n.username.toUtf8().size()>255 || n.password.toUtf8().size()>255)) return QStringLiteral("SOCKS5 凭据不能超过 255 字节。");
    if (n.protocol == "socks5" && (n.username.isEmpty() != n.password.isEmpty())) return QStringLiteral("SOCKS5 用户名与密码须同时填写或同时留空。");
    if (n.protocol != "socks5" && n.password.isEmpty()) return QStringLiteral("此协议必须填写密码。");
    if (n.protocol == "ss" && !QStringList{"aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305"}.contains(n.cipher))
        return QStringLiteral("Shadowsocks 加密方式暂不支持。");
    if (!n.serverName.isEmpty() && !validHost(n.serverName)) return QStringLiteral("TLS 服务器名称（SNI）无效。");
    return {};
}
QVariantMap ProxyNode::publicInfo() const {
    return {{"id",id},{"name",name},{"protocol",protocol},{"host",host},{"port",port},
        {"cipher",cipher},{"serverName",serverName},{"hasCredentials",!password.isEmpty()}};
}
