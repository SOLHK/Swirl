#include "ProxyNode.h"
#include "NodeRegion.h"
#include <QHostAddress>
#include <QRegularExpression>
#include <QUrl>
#include <QUuid>
#include <QJsonArray>
#include <QJsonDocument>
#include "SwirlProtocolRegistry.h"
#include <functional>

static QString parameterSafetyError(const QJsonValue &value,int depth,int &budget) {
    if(depth>32 || --budget<0)return QStringLiteral("扩展选项嵌套过深或数量超过安全上限。");
    if(value.isArray()){for(const auto &entry:value.toArray()){const auto error=parameterSafetyError(entry,depth+1,budget);if(!error.isEmpty())return error;}}
    if(value.isObject()){
        const auto object=value.toObject();
        for(auto it=object.begin();it!=object.end();++it){
            const auto key=it.key().toLower();
            // Do not echo arbitrary keys or values: both can contain private
            // source data. Fixed schema names and fixed suffixes are safe.
            if(key.endsWith("-path") || key.endsWith("-file") || key.endsWith("-dir"))
                return QStringLiteral("扩展选项含本地文件路径字段（*-path、*-file 或 *-dir）；订阅不能访问本机文件。");
            if(QStringList{"interface-name","routing-mark","iproute2-table-index","auto-route","script","command","planet","listeners","mapped-listeners","primary-port","secondary-port","enable-exit-node","proxy-networks"}.contains(key))
                return QStringLiteral("扩展选项 %1 不允许由订阅设置（本地文件、脚本、系统网络或额外监听）。").arg(key);
            if(key=="skip-cert-verify"){
                if(!it.value().isBool())return QStringLiteral("skip-cert-verify 必须为布尔值 false；不能使用字符串或其它类型。");
                if(it.value().toBool())return QStringLiteral("skip-cert-verify=true 请求关闭 TLS 证书验证，已拒绝。请使用证书验证开启的订阅配置。");
            }
            const auto error=parameterSafetyError(it.value(),depth+1,budget);if(!error.isEmpty())return error;
        }
    }
    return {};
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
    if(n.providerAlias.size()>128||n.providerAlias.contains(QRegularExpression("[\\x00-\\x1f]")))
        return QStringLiteral("订阅节点别名超过 128 字符或含控制字符。");
    if (n.isXray()) {
        // Invalid/unsupported imported nodes are safe data and remain visible.
        // Execution always replays the original document through Rust; these
        // presence/budget checks grant no runtime permission.
        if (QUuid(n.id).isNull() || n.name.trimmed().isEmpty() || n.name.size() > 128 ||
            n.name.contains(QRegularExpression("[\\x00-\\x1f]"))) return QStringLiteral("JSON 节点标识或名称无效。");
        if (n.sourceDocument.isEmpty() || n.sourceDocument.size() > 4 * 1024 * 1024 ||
            n.sourceNodeIndex < 0 || n.sourceNodeIndex >= 2000 || n.conversionIssues.size() > 64 ||
            n.runtimeIssues.size() > 64 || n.importSource.size() > 128)
            return QStringLiteral("JSON 节点缺少有界原始配置；请重新导入。");
        return {};
    }
    if(QJsonDocument(n.originalConfiguration).toJson(QJsonDocument::Compact).size()>256*1024||n.conversionIssues.size()>32||n.sourceFormat.size()>128)return QStringLiteral("订阅原始差异超过保存上限。");
    int budget=10000;
    if(QJsonDocument(n.parameters).toJson(QJsonDocument::Compact).size()>256*1024)return QStringLiteral("扩展选项超过 256 KiB 安全上限。");
    const auto safetyError=parameterSafetyError(n.parameters,0,budget);if(!safetyError.isEmpty())return safetyError;
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
    bool supportedProtocol=protocols().contains(n.protocol);
    // This is a preservation/validation catalog, not execution capability.
    // RustCoreEngine and SwirlProtocolRegistry decide which nodes can run.
    supportedProtocol=supportedProtocol||n.protocol=="socks4"||n.protocol=="socks4a";
    if (!supportedProtocol) return QStringLiteral("此节点协议不在可保存的数据格式目录中。");
    const bool peerTransport=QStringList{"wireguard","tailscale","zerotier","easytier","openvpn"}.contains(n.protocol);
    const bool portRange=(n.protocol=="mieru" && !n.parameters.value("port-range").toString().isEmpty()) ||
        (QStringList{"hysteria","hysteria2"}.contains(n.protocol) && !n.parameters.value("ports").toString().isEmpty());
    if ((!peerTransport || !n.host.isEmpty()) && (!validHost(n.host) || (n.port == 0 && !portRange))) return QStringLiteral("服务器应为有效 IP 或域名，端口必须在 1–65535 之间。");
    if (n.password.size() > 4096 || n.username.size() > 255) return QStringLiteral("凭据长度超过支持范围。");
    if (n.protocol == "socks5" && (n.username.toUtf8().size()>255 || n.password.toUtf8().size()>255)) return QStringLiteral("SOCKS5 凭据不能超过 255 字节。");
    if (n.protocol == "socks5" && (n.username.isEmpty() != n.password.isEmpty())) return QStringLiteral("SOCKS5 用户名与密码须同时填写或同时留空。");
    if (n.protocol == "socks4" || n.protocol == "socks4a") {
        if(!n.password.isEmpty())return QStringLiteral("SOCKS4/4a 不支持密码认证；用户名仅映射 USERID。");
        if(n.username.toUtf8().size()>255||n.username.contains(QRegularExpression("[\\x00-\\x1f\\x7f-\\x9f]")))return QStringLiteral("SOCKS4 USERID 不能超过 255 字节或包含控制字符。");
    }
    if (QStringList{"ss","ssr","trojan","anytls","mieru"}.contains(n.protocol) && n.password.isEmpty()) return QStringLiteral("此协议必须填写密码。");
    if ((n.protocol=="vmess" || n.protocol=="vless") && QUuid(n.parameters.value("uuid").toString()).isNull()) return QStringLiteral("此协议需要有效 UUID。");
    if (n.protocol == "ss" && n.cipher.isEmpty()) return QStringLiteral("Shadowsocks 加密方式不能为空；具体算法由引擎校验。");
    if(n.protocol=="snell" && n.parameters.value("psk").toString().isEmpty())return QStringLiteral("Snell 需要在扩展选项中填写 psk。");
    if(n.protocol=="sudoku" && n.parameters.value("key").toString().isEmpty())return QStringLiteral("Sudoku 需要在扩展选项中填写 key。");
    if (!n.serverName.isEmpty() && !validHost(n.serverName)) return QStringLiteral("TLS 服务器名称（SNI）无效。");
    return {};
}
QStringList ProxyNode::protocols() {
    // Historical imported protocol catalog; it must not claim runtime support.
    // direct/dns/reject/rematch are routing actions, not remote node protocols.
    return {"socks5","ss","trojan","http","ssr","vmess","vless","snell","hysteria","hysteria2",
        "wireguard","tuic","shadowquic","gost-relay","ssh","mieru","anytls","sudoku","masque",
        "trusttunnel","openvpn","tailscale","zerotier","easytier"};
}
QVariantMap ProxyNode::publicInfo() const {
    const auto region=NodeRegion::fromName(name);
    const auto capability=SwirlProtocolRegistry::describe(*this);
    const QHash<QString,QString> protocolLabels{{"ss","Shadowsocks"},{"socks4","SOCKS4"},{"socks4a","SOCKS4a"},{"socks5","SOCKS5"},{"vmess","VMess"},{"vless","VLESS"},{"trojan","Trojan"},{"http","HTTP"}};
    const QHash<QString,QString> transportLabels{{"tcp","TCP"},{"web_socket","WebSocket"},{"grpc","gRPC"},{"http2","HTTP/2"},{"http_upgrade","HTTPUpgrade"},{"xhttp","XHTTP"}};
    const QHash<QString,QString> securityLabels{{"none",QStringLiteral("无 TLS")},{"tls","TLS"},{"reality","REALITY"}};
    const QHash<QString,QString> origins{{"file",QStringLiteral("JSON 文件")},{"text",QStringLiteral("JSON 文本")},{"clipboard",QStringLiteral("剪贴板 JSON")},{"url",QStringLiteral("HTTPS JSON URL")},{"subscription",QStringLiteral("JSON 订阅")}};
    const auto parameterLabel=parameterState=="valid"?QStringLiteral("参数有效"):parameterState=="invalid"?QStringLiteral("参数无效"):QStringLiteral("参数待验证");
    const auto executable=capability.value("native").toBool();
    const auto state=isXray()?QStringLiteral("JSON 已解析 · %1 · %2 · 未验证业务流量").arg(parameterLabel,executable?QStringLiteral("Rust 可执行"):QStringLiteral("Rust 不可执行")):
        conversionIssues.isEmpty()?QStringLiteral("已解析 · 待联网测试"):QStringLiteral("已解析 · 含未支持选项");
    const auto origin=origins.value(importSource,QStringLiteral("JSON 配置"));
    QStringList normalizationNotes;
    if(originalConfiguration.value("_swirl-default-client-fingerprint").toBool())normalizationNotes.append(QStringLiteral("源配置未指定 Reality 指纹；保留历史归一化标记，Rust 拒绝推断执行。"));
    if(certificateVerificationEnforced)normalizationNotes.append(QStringLiteral("源订阅请求跳过 Trojan 证书验证；Swirl 已保持证书验证开启。证书不可信、过期或名称不匹配仍会连接失败，原始参数已加密保留。"));
    if(executable&&parameters.value("tfo")==QJsonValue(true))normalizationNotes.append(QStringLiteral("TCP Fast Open 为可选加速项；当前使用普通 TCP，原始参数已保留，证书验证要求不变。"));
    return {{"id",id},{"name",name},{"protocol",protocol},{"host",host},{"port",port},
        {"protocolLabel",protocolLabels.value(protocol,protocol.toUpper())},
        {"regionCode",region.code},{"regionName",region.name},
        {"cipher",cipher},{"serverName",serverName},{"sourceId",sourceId},{"sourceFormat",sourceFormat},
        {"configurationState",state},{"jsonParsed",isXray()},
        {"parameterState",parameterState},{"parameterLabel",parameterLabel},
        {"transportType",transportType},{"transportLabel",transportLabels.value(transportType,QStringLiteral("未知传输"))},
        {"securityType",securityType},{"securityLabel",securityLabels.value(securityType,QStringLiteral("未知安全类型"))},
        {"visionEnabled",isXray()&&parameters.value("authentication").toObject().value("flow").toString()=="xtls-rprx-vision"},
        {"importSource",importSource},{"sourceLabel",isXray()?origin+(sourceFingerprint.isEmpty()?QString():QStringLiteral(" · ")+sourceFingerprint.left(12)):sourceFormat},
        {"nativeExecutable",executable},{"networkVerified",false},{"unsupportedReason",capability.value("reason")},
        {"conversionIssues",conversionIssues},{"capability",capability},
        {"normalizationNotes",normalizationNotes.join('\n')},
        {"hasCredentials",!password.isEmpty() || !parameters.isEmpty()}};
}
