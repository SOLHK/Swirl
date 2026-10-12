#include "ProxyNode.h"
#include <QHostAddress>
#include <QRegularExpression>
#include <QUrl>
#include <QUuid>
#include <QJsonArray>
#include <QJsonDocument>
#include <functional>

static bool safeParameters(const QJsonValue &value,int depth,int &budget) {
    if(depth>32 || --budget<0)return false;
    if(value.isArray()){for(const auto &entry:value.toArray())if(!safeParameters(entry,depth+1,budget))return false;}
    if(value.isObject()){
        const auto object=value.toObject();
        for(auto it=object.begin();it!=object.end();++it){
            const auto key=it.key().toLower();
            if(key.endsWith("-path") || key.endsWith("-file") || key.endsWith("-dir") ||
                QStringList{"interface-name","routing-mark","iproute2-table-index","auto-route","script","command","planet","listeners","mapped-listeners","primary-port","secondary-port","enable-exit-node","proxy-networks"}.contains(key))return false;
            if(key=="skip-cert-verify" && it.value().toVariant().toBool())return false;
            if(!safeParameters(it.value(),depth+1,budget))return false;
        }
    }
    return true;
}

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
    int budget=10000;
    if(QJsonDocument(n.parameters).toJson(QJsonDocument::Compact).size()>256*1024 || !safeParameters(n.parameters,0,budget))return QStringLiteral("扩展选项超出安全范围：不允许本地文件、系统网络设置、额外监听、脚本或关闭证书验证。");
    if(n.protocol=="ssh" && !n.parameters.value("private-key").toString().isEmpty() && !n.parameters.value("private-key").toString().contains("PRIVATE KEY"))return QStringLiteral("SSH 私钥须为内嵌 PEM，不能引用本地文件。");
    for(const auto &key:QStringList{"certificate","ca","cert"}) {
        const auto value=n.parameters.value(key).toString();
        if(!value.isEmpty() && !value.contains("-----BEGIN "))return QStringLiteral("证书须为内嵌 PEM，不能引用本地文件。");
    }
    const auto privateKey=n.parameters.value("private-key").toString();
    if(!privateKey.isEmpty() && n.protocol!="wireguard" && n.protocol!="masque" && !privateKey.contains("PRIVATE KEY"))return QStringLiteral("客户端私钥须为内嵌 PEM，不能引用本地文件。");
    if (QUuid(n.id).isNull()) return QStringLiteral("节点标识无效。");
    if (n.name.trimmed().isEmpty() || n.name.size() > 128 || n.name.contains(QRegularExpression("[\\x00-\\x1f]")))
        return QStringLiteral("节点名称不能为空、超过 128 字符或包含控制字符。");
    if (!protocols().contains(n.protocol)) return QStringLiteral("固定版本引擎不支持此节点协议。");
    const bool peerTransport=QStringList{"wireguard","tailscale","zerotier","easytier","openvpn"}.contains(n.protocol);
    const bool portRange=(n.protocol=="mieru" && !n.parameters.value("port-range").toString().isEmpty()) ||
        (QStringList{"hysteria","hysteria2"}.contains(n.protocol) && !n.parameters.value("ports").toString().isEmpty());
    if ((!peerTransport || !n.host.isEmpty()) && (!validHost(n.host) || (n.port == 0 && !portRange))) return QStringLiteral("服务器应为有效 IP 或域名，端口必须在 1–65535 之间。");
    if (n.password.size() > 4096 || n.username.size() > 255) return QStringLiteral("凭据长度超过支持范围。");
    if (n.protocol == "socks5" && (n.username.toUtf8().size()>255 || n.password.toUtf8().size()>255)) return QStringLiteral("SOCKS5 凭据不能超过 255 字节。");
    if (n.protocol == "socks5" && (n.username.isEmpty() != n.password.isEmpty())) return QStringLiteral("SOCKS5 用户名与密码须同时填写或同时留空。");
    if (QStringList{"ss","ssr","trojan","anytls","mieru"}.contains(n.protocol) && n.password.isEmpty()) return QStringLiteral("此协议必须填写密码。");
    if ((n.protocol=="vmess" || n.protocol=="vless") && QUuid(n.parameters.value("uuid").toString()).isNull()) return QStringLiteral("此协议需要有效 UUID。");
    if (n.protocol == "ss" && n.cipher.isEmpty()) return QStringLiteral("Shadowsocks 加密方式不能为空；具体算法由引擎校验。");
    if(n.protocol=="snell" && n.parameters.value("psk").toString().isEmpty())return QStringLiteral("Snell 需要在扩展选项中填写 psk。");
    if(n.protocol=="sudoku" && n.parameters.value("key").toString().isEmpty())return QStringLiteral("Sudoku 需要在扩展选项中填写 key。");
    if (!n.serverName.isEmpty() && !validHost(n.serverName)) return QStringLiteral("TLS 服务器名称（SNI）无效。");
    return {};
}
QStringList ProxyNode::protocols() {
    // Exactly the outbound transports in the pinned Mihomo v1.19.32 parser.
    // direct/dns/reject/rematch are routing actions, not remote node protocols.
    return {"socks5","ss","trojan","http","ssr","vmess","vless","snell","hysteria","hysteria2",
        "wireguard","tuic","shadowquic","gost-relay","ssh","mieru","anytls","sudoku","masque",
        "trusttunnel","openvpn","tailscale","zerotier","easytier"};
}
QVariantMap ProxyNode::publicInfo() const {
    return {{"id",id},{"name",name},{"protocol",protocol},{"host",host},{"port",port},
        {"cipher",cipher},{"serverName",serverName},{"sourceId",sourceId},{"hasCredentials",!password.isEmpty() || !parameters.isEmpty()}};
}
