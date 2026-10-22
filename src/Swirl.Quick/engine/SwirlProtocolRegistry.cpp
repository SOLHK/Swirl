#include "SwirlProtocolRegistry.h"
#include "RustCoreEngine.h"
QString SwirlProtocolRegistry::nativeNodeReason(const ProxyNode &node){
    EngineStartOptions o;o.routingMode="global";o.nodes={node};o.selectedNodeId=node.id;
    QJsonObject ignored;return RustCoreEngine::configuration(o,&ignored);
}
QString SwirlProtocolRegistry::nativeSessionReason(const EngineStartOptions &o){
    QJsonObject ignored;return RustCoreEngine::configuration(o,&ignored);
}
QVariantMap SwirlProtocolRegistry::describe(const ProxyNode &n){
    const auto reason=nativeNodeReason(n);
    return {{"native",reason.isEmpty()},{"compatible",false},{"engine",reason.isEmpty()?QStringLiteral("Swirl Rust 原生"):QStringLiteral("Rust 尚未支持")},{"reason",reason},{"tested",false}};
}
