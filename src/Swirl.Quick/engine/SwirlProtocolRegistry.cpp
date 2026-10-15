#include "SwirlProtocolRegistry.h"
#include <QSet>
#include <QJsonArray>
#include <QSslSocket>
QString SwirlProtocolRegistry::nativeNodeReason(const ProxyNode &node){
    if(!node.conversionIssues.isEmpty())return QStringLiteral("存在未映射的订阅选项，不能安全执行。");
    if(!QStringList{"http","socks5","trojan"}.contains(node.protocol))return QStringLiteral("此协议的原生实现研发中，继续使用 Mihomo。");
    const QSet<QString> allowed{"tls","udp","sni","servername","alpn","skip-cert-verify"};
    for(auto it=node.parameters.begin();it!=node.parameters.end();++it)if(!allowed.contains(it.key()))return QStringLiteral("此节点含原生尚未验证的传输或扩展选项，使用 Mihomo。");
    for(const auto &key:QStringList{"tls","udp","skip-cert-verify"})if(node.parameters.contains(key)&&!node.parameters.value(key).isBool())return QStringLiteral("原生协议布尔选项类型无效，交由兼容引擎校验。");
    for(const auto &key:QStringList{"sni","servername"})if(node.parameters.contains(key)&&(!node.parameters.value(key).isString()||node.parameters.value(key).toString()!=node.serverName))return QStringLiteral("TLS 服务器名称与归一化字段不一致，交由兼容引擎校验。");
    if(node.protocol=="trojan"&&node.parameters.contains("tls")&&!node.parameters.value("tls").toBool())return QStringLiteral("原生 Trojan 必须使用 TLS。");
    if(node.parameters.contains("alpn")){
        const auto value=node.parameters.value("alpn");if(!value.isArray()||value.toArray().size()>16)return QStringLiteral("原生 ALPN 格式无效。");
        for(const auto &v:value.toArray())if(!v.isString()||v.toString().toUtf8().isEmpty()||v.toString().toUtf8().size()>255)return QStringLiteral("原生 ALPN 项目无效。");
    }
    if(node.parameters.value("udp").toBool())return QStringLiteral("UDP Relay 尚未原生实现，保留 Mihomo UDP 能力。");
    if(node.parameters.value("skip-cert-verify").toBool())return QStringLiteral("原生 TLS 不允许关闭证书验证。");
    if((node.protocol=="trojan"||node.parameters.value("tls").toBool())&&!QSslSocket::supportsSsl())return QStringLiteral("当前 TLS 后端不可用。");
    return ProxyNode::validate(node);
}
QString SwirlProtocolRegistry::nativeSessionReason(const EngineStartOptions &o){
    if(o.preferCompatibility)return QStringLiteral("用户选择优先使用 Mihomo 兼容引擎；保持相同节点与网络配置。");
    if(o.tunEnabled||o.gatewayForwarding||o.allowLan||o.meteredNetwork)return QStringLiteral("TUN、网关、LAN 或进程计费策略继续由 Mihomo 执行。");
    if(!o.dnsConfig.isEmpty()||!o.customRules.isEmpty()||!o.customGroups.isEmpty())return QStringLiteral("自定义 DNS、规则及策略组继续由 Mihomo 执行。");
    if(o.routingMode=="rule"&&o.smartRouting&&!o.directSession)return QStringLiteral("国内外 MRS 分流继续由 Mihomo 执行；全局基础代理可使用原生引擎。");
    if(o.routingMode!="rule"&&o.routingMode!="global"&&o.routingMode!="direct")return QStringLiteral("出站模式无效。");
    if(o.directSession||o.routingMode=="direct")return {};
    for(const auto &n:o.nodes)if(n.id==o.selectedNodeId)return nativeNodeReason(n);
    return QStringLiteral("未选择可执行节点。");
}
QVariantMap SwirlProtocolRegistry::describe(const ProxyNode &n){
    const auto reason=nativeNodeReason(n);const bool compatible=ProxyNode::protocols().contains(n.protocol)&&n.conversionIssues.isEmpty();
    return {{"native",reason.isEmpty()},{"compatible",compatible},{"engine",reason.isEmpty()?QStringLiteral("Swirl 原生（TCP）"):compatible?QStringLiteral("Mihomo 兼容"):QStringLiteral("尚未支持")},{"reason",reason},{"tested",false}};
}
