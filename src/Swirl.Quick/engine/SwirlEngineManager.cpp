#include "SwirlEngineManager.h"
#include "SwirlProtocolRegistry.h"
#include <QTimer>
#include <QUuid>

SwirlEngineManager::SwirlEngineManager(QObject *parent):ProxyEngine(parent){
    for(ProxyEngine *engine:{static_cast<ProxyEngine *>(&m_native),static_cast<ProxyEngine *>(&m_compatibility)}){
        connect(engine,&ProxyEngine::statusChanged,this,[this,engine]{changed(engine);});
        connect(engine,&ProxyEngine::diagnostic,this,[this,engine](const QString &module,const QString &code,const QString &message){
            emit diagnostic(module,code,message);
            const QStringList transportFailures{"TlsVerificationFailed","UpstreamAuthenticationRejected","UpstreamAuthenticationFailed","UpstreamConnectRejected","UpstreamHandshakeClosed","UpstreamConnectionRefused","UpstreamNetworkError","DnsLookupFailed","ConnectionTimeout"};
            if(engine==m_active&&engine==&m_native&&transportFailures.contains(code))fallback(code);
        });
    }
}
void SwirlEngineManager::start(const EngineStartOptions &options){
    ++m_generation;m_options=options;m_fallback=false;m_probe=QUrl();
    m_reason=SwirlProtocolRegistry::nativeSessionReason(options);
    activate(m_reason.isEmpty()?static_cast<ProxyEngine *>(&m_native):static_cast<ProxyEngine *>(&m_compatibility));
}
SwirlEngineManager::~SwirlEngineManager(){m_native.disconnect(this);m_compatibility.disconnect(this);m_native.stop();m_compatibility.stop();}
void SwirlEngineManager::activate(ProxyEngine *target){
    m_pending=target;m_transition=true;
    if(m_active&&m_active->status().state!=State::Stopped){m_active->stop();return;}
    m_active=target;m_pending=nullptr;m_transition=false;m_session=QUuid::createUuid().toString(QUuid::WithoutBraces);
    m_active->start(m_options);
}
void SwirlEngineManager::changed(ProxyEngine *engine){
    if(engine!=m_active)return;
    if(m_transition){
        if(engine->status().state==State::Stopped&&m_pending){auto target=m_pending;m_pending=nullptr;m_transition=false;m_active=target;m_session=QUuid::createUuid().toString(QUuid::WithoutBraces);m_active->start(m_options);}
        emit statusChanged();return;
    }
    const auto actual=engine->status();
    if(!actual.nodeBusy&&!actual.selectedNodeId.isEmpty())m_options.selectedNodeId=actual.selectedNodeId;
    emit statusChanged();
    if(m_active==&m_compatibility&&m_fallback&&!m_probe.isEmpty()&&engine->status().state==State::Running){auto url=m_probe;m_probe=QUrl();m_active->probeNode(url);}
    else if(m_active==&m_native&&engine->status().requestState==RequestState::Failed)fallback("NativeProbeFailed");
}
void SwirlEngineManager::fallback(const QString &code){
    if(m_fallback||m_transition||m_active!=&m_native||m_options.directSession||m_options.routingMode=="direct")return;
    if(m_native.activeStreamCount()>0){
        m_reason=QStringLiteral("本次新连接失败（%1）；其他已建立连接继续运行。需要兼容引擎时请手动断开重连。").arg(code);
        emit diagnostic("EngineManager","FallbackDeferredToPreserveStreams",m_reason);return;
    }
    m_fallback=true;m_reason=QStringLiteral("原生连接失败（%1），已用同一节点重试 Mihomo；未切换直连。").arg(code);
    const auto generation=m_generation;
    QTimer::singleShot(0,this,[this,generation]{
        if(generation!=m_generation||m_active!=&m_native)return;
        // A different handshake may have completed since fallback was queued.
        if(m_native.activeStreamCount()>0){m_fallback=false;m_reason="兼容引擎切换已延后，以保留刚建立的连接。";emit diagnostic("EngineManager","FallbackDeferredToPreserveStreams",m_reason);return;}
        emit diagnostic("EngineManager","CompatibilityFallback",m_reason);activate(&m_compatibility);
    });
}
void SwirlEngineManager::stop(){++m_generation;m_pending=nullptr;m_transition=false;m_probe=QUrl();if(m_active)m_active->stop();else emit statusChanged();}
void SwirlEngineManager::refresh(){if(m_active)m_active->refresh();}
void SwirlEngineManager::selectNode(const QString &id){
    auto options=m_options;options.selectedNodeId=id;options.directSession=false;
    if(m_active==&m_compatibility&&!m_transition&&m_active->status().processAlive){m_options=options;m_active->selectNode(id);return;}
    const auto reason=SwirlProtocolRegistry::nativeSessionReason(options);
    if(m_active==&m_native&&!m_transition&&reason.isEmpty()&&m_active->status().processAlive){m_options=options;m_active->selectNode(id);return;}
    if(m_active==&m_native&&m_native.activeStreamCount()>0){m_reason="所选节点需要切换引擎；为保留现有连接，请手动断开后连接该节点。";emit diagnostic("EngineManager","EngineSwitchRequiresReconnect",m_reason);emit statusChanged();return;}
    start(options);
}
void SwirlEngineManager::setRoutingMode(const QString &mode){
    auto options=m_options;options.routingMode=mode;
    if(m_active==&m_compatibility&&!m_transition&&m_active->status().processAlive){m_options=options;m_active->setRoutingMode(mode);return;}
    const auto reason=SwirlProtocolRegistry::nativeSessionReason(options);
    if(m_active==&m_native&&!m_transition&&reason.isEmpty()&&m_active->status().processAlive){m_options=options;m_active->setRoutingMode(mode);return;}
    if(m_active==&m_native&&m_native.activeStreamCount()>0){m_reason="新路由模式需要切换引擎；为保留现有连接，请手动断开重连。";emit diagnostic("EngineManager","RoutingSwitchRequiresReconnect",m_reason);emit statusChanged();return;}
    start(options);
}
void SwirlEngineManager::probeNode(const QUrl &url){m_probe=url;if(m_active)m_active->probeNode(url);}
ProxyEngine::Status SwirlEngineManager::status()const{
    auto status=m_active?m_active->status():Status{};status.engineReason=m_reason;
    if(m_active==&m_native){status.engineName="Swirl 原生";status.engineKind="native";}
    else {status.engineName="Mihomo 兼容";status.engineKind="compatibility";status.sessionId=m_session;}
    if(m_transition){status.state=State::Starting;status.apiHealthy=false;status.nodeBusy=true;status.message="正在切换代理引擎…";}
    return status;
}
QString SwirlEngineManager::configurationSummary()const{return m_active?m_active->configurationSummary():QStringLiteral("Swirl 原生 / Mihomo 兼容：根据节点及会话能力自动选择。");}
QVariantList SwirlEngineManager::routingRules()const{return m_active?m_active->routingRules():QVariantList{};}
