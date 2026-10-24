#include "EngineController.h"
#include <QCoreApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaEnum>
#include <QTimer>
#include <QTcpSocket>
#include <QNetworkProxy>
#include <QSettings>
#include <QJsonArray>
#include <QSaveFile>
#include <QScopedValueRollback>
#include <QHostAddress>
#include <QRegularExpression>
#include <QNetworkInterface>
#include <QFutureWatcher>
#include <QPromise>
#include <QThreadPool>
#include "RustCoreEngine.h"
#include "RustCoreLibrary.h"
#include "RustDnsConfiguration.h"
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif

namespace {
bool projectSubscriptionProfile(const QJsonObject &configuration,const QString &format,QVariantMap *projected,QString *error,bool *safeNodeFallback=nullptr,bool *hasSemantics=nullptr) {
    if(safeNodeFallback)*safeNodeFallback=false;
    if(hasSemantics)*hasSemantics=true;
    auto &library=RustCoreLibrary::instance();
    if(!library.load()||!library.importProfile()) {
        *error=QStringLiteral("Rust 完整配置接口不可用；请安装内核与应用匹配的完整版本。");return false;
    }
    auto bytes=QJsonDocument(QJsonObject{{"format",format},{"configuration",configuration}}).toJson(QJsonDocument::Compact);
    constexpr qsizetype Maximum=4*1024*1024;
    if(bytes.size()>Maximum){bytes.fill('\0');*error=QStringLiteral("完整配置超过 Rust 校验上限。");return false;}
    const auto call=library.importProfile();const auto *input=reinterpret_cast<const unsigned char *>(bytes.constData());
    const auto required=call(input,size_t(bytes.size()),nullptr,0);
    if(required<=0||required>Maximum){bytes.fill('\0');*error=QStringLiteral("Rust 完整配置校验返回无效长度。");return false;}
    QByteArray response(required,Qt::Uninitialized);
    const auto count=call(input,size_t(bytes.size()),reinterpret_cast<unsigned char *>(response.data()),size_t(response.size()));bytes.fill('\0');
    if(count!=required){response.fill('\0');*error=QStringLiteral("Rust 完整配置校验响应不完整。");return false;}
    QJsonParseError parseError;const auto document=QJsonDocument::fromJson(response,&parseError);response.fill('\0');
    if(parseError.error!=QJsonParseError::NoError||!document.isObject()||document.object().value("schema").toInt()!=1) {
        *error=QStringLiteral("Rust 完整配置校验响应无效。");return false;
    }
    const auto result=document.object();
    if(safeNodeFallback)*safeNodeFallback=result.value("safe_node_fallback")==QJsonValue(true);
    if(!result.value("ok").toBool()) {
        const auto code=result.value("error").toString(),field=result.value("field").toString();
        const auto safeCode=QRegularExpression("^[A-Za-z][A-Za-z0-9]{0,127}$").match(code).hasMatch()?code:QStringLiteral("ProfileInvalid");
        const auto safeField=QRegularExpression("^[A-Za-z][A-Za-z0-9_.\\[\\]-]{0,95}$").match(field).hasMatch()?field:QStringLiteral("configuration");
        *error=QStringLiteral("Rust 完整配置校验失败：%1（%2）；旧节点与网络配置保持不变。").arg(safeCode,safeField);return false;
    }
    if(!result.value("configuration").isObject()){*error=QStringLiteral("Rust 未返回完整配置投影。");return false;}
    if(hasSemantics)*hasSemantics=result.value("has_profile_semantics")!=QJsonValue(false);
    *projected=result.value("configuration").toObject().toVariantMap();return true;
}
QString profileMetadataNotice(const QJsonObject &metadata) {
    QStringList notices;
    if(metadata.value("managedConfig").isObject())notices.append(QStringLiteral("原配置的托管地址已保留，不会另行下载；更新使用本订阅在 Swirl 中保存的地址和周期。"));
    if(!metadata.value("preservedGeneral").toArray().isEmpty())notices.append(QStringLiteral("原客户端的界面、日志或连通性检测设置已保留，不会改写 Swirl 的对应设置。"));
    return notices.join(' ');
}
QJsonObject recordSubscriptionOutcome(QJsonObject snapshot,const QString &sourceId,const QString &format,const QString &mode,const QString &notice,const QJsonObject &metadata={},const QJsonObject &preservedConfiguration={}) {
    if(sourceId.isEmpty())return snapshot;
    if(snapshot.isEmpty())snapshot.insert("schema",1);
    auto outcomes=snapshot.value("subscriptionImportResults").toObject();
    auto outcome=QJsonObject{{"mode",mode},{"format",format},{"notice",notice},{"metadata",metadata}};
    // Incompatible/metadata-only profiles are inert private data. Preserve
    // them in the bounded encrypted catalog for diagnostics or future mapping;
    // never feed these retained bytes back into the active Core configuration.
    if(!preservedConfiguration.isEmpty())outcome.insert("preservedConfiguration",preservedConfiguration);
    outcomes.insert(sourceId,outcome);
    snapshot.insert("subscriptionImportResults",outcomes);return snapshot;
}
QStringList routingRuleFields(const QString &rule) {
    auto fields=rule.split(',');
    for(auto &field:fields)field=field.trimmed();
    return fields;
}
int routingRuleTargetIndex(const QStringList &fields) {
    return fields.value(0)=="MATCH"?1:2;
}
bool destinationCidrRule(const QString &type) {
    return type=="IP-CIDR"||type=="IP-CIDR6";
}
QByteArray protectLanPassword(const QByteArray &input,bool decrypt) {
#ifdef Q_OS_WIN
    DATA_BLOB source{DWORD(input.size()),reinterpret_cast<BYTE *>(const_cast<char *>(input.constData()))},result{};
    const bool ok=decrypt?CryptUnprotectData(&source,nullptr,nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&result)
        :CryptProtectData(&source,L"Swirl LAN authentication",nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&result);
    if(!ok)return {};
    QByteArray bytes(reinterpret_cast<char *>(result.pbData),result.cbData);SecureZeroMemory(result.pbData,result.cbData);LocalFree(result.pbData);return bytes;
#else
    Q_UNUSED(input);Q_UNUSED(decrypt);return {};
#endif
}
}
EngineController::EngineController(std::unique_ptr<ProxyEngine> engine, QObject *parent, QString storePath,bool realAcceptance)
    // Runtime acceptance counts explicit requests. Its own periodic probes
    // would add unrelated Rust connections and corrupt per-request deltas.
    : QObject(parent), m_engine(std::move(engine)), m_store(storePath),m_imports(&m_store,this),m_telemetry(storePath.isEmpty()?QString():storePath+".telemetry",storePath.isEmpty()&&!realAcceptance) {
    const auto retainedNodeConfiguration=[this](const QString &sourceId,bool nodesOnly) {
        auto retained=m_store.networkConfiguration();
        if(nodesOnly && !sourceId.isEmpty() && retained.contains("importedConfiguration") &&
           retained.value("importedConfiguration").toObject().value("sourceId").toString()==sourceId) {
            auto provenance=retained.value("importedConfiguration").toObject();
            provenance.insert("policyRetainedAfterNodesOnlyRefresh",true);
            retained.insert("importedConfiguration",provenance);
        }
        return retained;
    };
    m_imports.setAsyncConfigurationApplier([this,retainedNodeConfiguration](const NodeImporter::Result &result,const QString &sourceId,bool nodesOnly,
                                                  NodeImportService::ApplyCompletion completion,QString *error) {
        if(result.format!="xray-v2ray-json" || !result.configuration.isEmpty()) {
            *error=QStringLiteral("此异步入口仅接受经过严格校验的 JSON 节点。");return false;
        }
        NodeStore::ImportPlan plan;
        if(!m_store.prepareImport(result.nodes,sourceId,&plan)){*error=m_store.error();return false;}
#ifdef SWIRL_USE_RUST_CORE
        const auto nodes=plan.nodes();QVariantMap canonical;
        if(!validateNetworkConfiguration(networkConfigurationSnapshot(),&canonical,&nodes)){*error=m_networkError;return false;}
#endif
        auto retained=retainedNodeConfiguration(sourceId,nodesOnly||m_imports.automaticImport());
        if(m_imports.automaticImport())retained=recordSubscriptionOutcome(retained,sourceId,result.format,"nodes",{});
        if(!m_store.commitImportAsync(plan,retained,std::move(completion))){*error=m_store.error();return false;}
        return true;
    });
    m_imports.setConfigurationApplier([this,retainedNodeConfiguration](const NodeImporter::Result &result,const QString &sourceId,bool nodesOnly,QString *error) {
        const auto &configuration=result.configuration;
        const bool automatic=m_imports.automaticImport();
        auto importNodes=[&](const QString &mode,const QString &notice,const QJsonObject &metadata=QJsonObject{}) {
            NodeStore::ImportPlan plan;
            if(!m_store.prepareImport(result.nodes,sourceId,&plan)){*error=m_store.error();return false;}
            const auto nodes=plan.nodes();QVariantMap canonical;
            if(!validateNetworkConfiguration(networkConfigurationSnapshot(),&canonical,&nodes)){*error=m_networkError;return false;}
            auto retained=retainedNodeConfiguration(sourceId,nodesOnly||automatic);
            if(automatic)retained=recordSubscriptionOutcome(retained,sourceId,result.format,mode,notice,metadata,result.configuration);
            if(!m_store.commitImport(plan,retained)){*error=m_store.error();return false;}
            if(automatic)m_imports.setImportOutcome(mode,notice);
            return true;
        };
        if(nodesOnly || result.configuration.isEmpty())return importNodes("nodes",{});
        if(result.configurationFormat!="clash"&&result.configurationFormat!="sing-box"&&(result.configurationFormat!="ini"||configuration.isEmpty())) {
            *error=QStringLiteral("此格式的完整配置尚未映射；未应用节点或全局配置，原有设置保持不变。");return false;
        }
        QVariantMap input;bool safeNodeFallback=false,hasSemantics=true;
        if(!projectSubscriptionProfile(configuration,result.configurationFormat,&input,error,&safeNodeFallback,&hasSemantics)) {
            if(!automatic||!safeNodeFallback)return false;
            auto reason=*error;reason.remove(QStringLiteral("；旧节点与网络配置保持不变。"));
            const auto notice=QStringLiteral("检测到不兼容配置，未应用本次 DNS、规则与策略组；有效节点已保留。%1").arg(reason);
            error->clear();return importNodes("nodes-with-warning",notice);
        }
        const auto metadata=QJsonObject::fromVariantMap(input.take("importMetadata").toMap());
        if(automatic&&!hasSemantics)return importNodes("nodes",profileMetadataNotice(metadata),metadata);
        if(!metadata.isEmpty())input.insert("importMetadata",metadata.toVariantMap());
        bool candidateValidationFailed=false;
        if(!importNodesAndConfiguration(result.nodes,sourceId,input,result.configuration,result.configurationFormat,&candidateValidationFailed)) {
            if(automatic&&safeNodeFallback&&candidateValidationFailed) {
                return importNodes("nodes-with-warning",QStringLiteral("ProfileNativeValidationUnsupported：本次 DNS、规则或策略参数无法由内核执行，未应用；有效节点已保留，继续使用现有 Swirl 网络配置。"));
            }
            *error=m_networkError;return false;
        }
        if(automatic)m_imports.setImportOutcome("full",profileMetadataNotice(metadata));
        return true;
    });
    connect(m_engine.get(),&ProxyEngine::statusChanged,this,[this]{
        const QScopedValueRollback ingesting(m_ingestingEngineStatus,true);
        m_telemetry.ingest(m_engine->status());
    });
    connect(&m_telemetry,&TelemetryService::changed,this,[this]{if(!m_ingestingEngineStatus)emit statusChanged();});
    connect(&m_telemetry,&TelemetryService::nativeProbeRequested,this,[this](const QUrl &url,quint64 tag){if(!m_shuttingDown)m_engine->probeNodeTagged(url,tag);});
    connect(m_engine.get(),&ProxyEngine::probeRequestRejected,&m_telemetry,&TelemetryService::rejectNativeProbe);
    connect(&m_tests,&NodeTestService::changed,this,&EngineController::nodesChanged);
    connect(m_engine.get(),&ProxyEngine::diagnostic,this,&EngineController::diagnostic);
    connect(m_engine.get(),&ProxyEngine::diagnostic,this,[this](const QString &module,const QString &code,const QString &message){
        if(module=="SwirlRust"&&(code=="SelectionUnsupported"||code=="SelectionFailed"))rollbackPendingSelection(message);
        if(module=="SwirlRust"&&(code=="RoutingUnsupported"||code=="RoutingFailed")){
            m_routingError=message;const auto actual=m_engine->status().mode;
            if(!actual.isEmpty()&&actual!=m_options.routingMode){m_options.routingMode=actual;m_options.directSession=actual=="direct";QSettings().setValue("Proxy/routingMode",actual);}
            emit statusChanged();
        }
    });
    connect(this,&EngineController::diagnostic,&m_diagnostics,[this](const QString &module,const QString &code,const QString &message){m_diagnostics.noteEvent(module+" / "+code,message);});
    // The encrypted node snapshot is authoritative after the first migration.
    // Read legacy settings only when no embedded network snapshot exists.
    auto configuration=m_store.networkConfiguration();
    QFile networkFile(m_store.filePath()+".network.json");
    if(configuration.isEmpty() && networkFile.open(QIODevice::ReadOnly)&&networkFile.size()<=1024*1024)
        configuration=QJsonDocument::fromJson(networkFile.readAll()).object();
    if(!configuration.isEmpty()) {
        if(configuration.value("schema").toInt()==1) {
            m_options.tunEnabled=configuration.value("tun").toBool(false);
            m_options.meteredNetwork=configuration.value("metered").toBool(false);
            m_options.meteredAllowlist=configuration.value("meteredAllowlist").toVariant().toStringList();
            m_tunBeforeMetered=configuration.value("tunBeforeMetered").toBool(false);
            m_modeBeforeMetered=configuration.value("modeBeforeMetered").toString("rule");
            m_options.lanUsername=configuration.value("lanUsername").toString();
            m_options.lanPassword=QString::fromUtf8(protectLanPassword(QByteArray::fromBase64(configuration.value("lanPasswordProtected").toString().toLatin1()),true));
            m_options.allowLan=configuration.value("allowLan").toBool(false)&&lanConfigured();
            m_options.dnsConfig=configuration.value("dns").toObject().toVariantMap();
            for(const auto &rule:configuration.value("rules").toArray())m_options.customRules.append(rule.toString());
            m_options.customGroups=configuration.value("groups").toArray().toVariantList();
        } else m_networkError=QStringLiteral("网络配置文件格式无效，未加载。");
    }
    m_nativeDocumentRouting=configuration.value("nativeDocumentRouting").toBool(false);
    m_smartRoutingEligible=storePath.isEmpty()||realAcceptance;
    updateRoutingFlags();
    connect(&m_systemProxy,&SystemProxySession::changed,this,[this] {
        if(!m_systemProxy.owned()&&!m_systemProxy.error().isEmpty())m_proxyRequested=false;
        const auto state=m_systemProxy.owned()?(m_systemProxy.enabled()?QStringLiteral("Swirl 已接管 Windows 系统代理"):QStringLiteral("接管状态未确认，恢复快照已保留")):QStringLiteral("Swirl 未接管 Windows 系统代理");
        if(state!=m_previousProxyState){m_previousProxyState=state;m_diagnostics.noteEvent(QStringLiteral("Windows 系统代理"),state);}
    });
    QSettings settings;
    // Retired engine preferences remain on disk for data preservation, but
    // never influence this Rust-only runtime or prevent its startup.
    m_options.routingMode=settings.value("Proxy/routingMode","rule").toString();
    if(m_options.routingMode!="rule"&&m_options.routingMode!="global"&&m_options.routingMode!="direct")m_options.routingMode="rule";
    if(m_options.meteredNetwork)m_options.routingMode="rule";
    connect(m_engine.get(),&ProxyEngine::statusChanged,this,[this] {
        const auto s=m_engine->status();
        if(!m_pendingSelection.isEmpty()) {
            if(s.processAlive&&s.apiHealthy&&s.selectedNodeId==m_pendingSelection) {
                m_options.selectedNodeId=m_pendingSelection;m_options.directSession=false;
                m_pendingSelection.clear();m_previousSelection.clear();emit selectionChanged();
            }else if(s.state==ProxyEngine::State::Failed)rollbackPendingSelection(QStringLiteral("节点切换未完成，保留原选择。"));
        }
        if(m_meteredPending && s.state==ProxyEngine::State::Running && s.tunEnabled)m_meteredPending=false;
        if(m_meteredPending && s.state==ProxyEngine::State::Failed){
            m_meteredPending=false;m_options.meteredNetwork=false;
            m_options.tunEnabled=m_meteredOldTun;m_options.routingMode=m_meteredOldMode;
            m_routingError=QStringLiteral("计费模式未生效：")+s.message;saveNetworkConfiguration();
        }
        m_diagnostics.setProxyPort(s.processAlive?s.proxyPort:0);
        if(s.state!=m_previousEngineState){
            if(s.state==ProxyEngine::State::Degraded)m_diagnostics.noteEvent(QStringLiteral("控制接口异常"),QStringLiteral("控制接口采样暂时失败；保留现有数据隧道与系统代理。"));
            else if(s.state==ProxyEngine::State::Failed)m_diagnostics.noteEvent(QStringLiteral("Swirl 引擎异常"),s.message);
            m_previousEngineState=s.state;
        }
        m_imports.setDownloadProxy(s.processAlive&&(s.state==ProxyEngine::State::Running||s.state==ProxyEngine::State::Degraded)?s.proxyPort:0);
        if(s.state==ProxyEngine::State::Stopping||s.state==ProxyEngine::State::Stopped||s.state==ProxyEngine::State::Failed) {
            m_systemProxy.disable();
            if(s.state==ProxyEngine::State::Failed)m_proxyRequested=false;
        } else if(s.state==ProxyEngine::State::Running&&s.apiHealthy&&m_proxyRequested&&!m_systemProxy.owned()&&!m_proxyChecking)setSystemProxy(true);
    });
    if(m_options.tunEnabled)m_routingError=QStringLiteral("已保存的增强模式配置尚不受 Rust Core 支持；请明确关闭后再连接。配置保持原值。");
    connect(m_engine.get(), &ProxyEngine::statusChanged, this, &EngineController::statusChanged);
    m_options.nodes=m_store.nodes();
    connect(&m_store,&NodeStore::changed,this,[this]{
        const auto nodes=m_store.nodes();QSet<QString> present,removed,removedNames;
        for(const auto &node:nodes)present.insert(node.id);
        for(const auto &node:m_options.nodes)if(!present.contains(node.id)){removed.insert(node.id);removedNames.insert(node.name);}
        const auto status=m_engine->status();
        bool invalidated=removed.contains(status.selectedNodeId)||removed.contains(m_options.selectedNodeId)||
            (!status.selectedNodeId.isEmpty()&&!present.contains(status.selectedNodeId))||
            (!m_pendingSelection.isEmpty()&&!present.contains(m_pendingSelection));
        for(const auto &entry:m_options.customGroups)for(const auto &member:entry.toMap().value("proxies").toStringList())
            invalidated=invalidated||removed.contains(member);
        for(const auto &node:m_options.nodes)invalidated=invalidated||removedNames.contains(node.parameters.value("dialer-proxy").toString());
        for(const auto &rule:m_options.customRules){const auto fields=routingRuleFields(rule);invalidated=invalidated||removed.contains(fields.value(routingRuleTargetIndex(fields)));}
        if(invalidated&&(m_connectionRequested||status.processAlive||busy())) {
            // Revocation closes the Rust snapshot before it can continue using
            // deleted credentials. Do not roll back a pending choice to a node
            // that has just been removed, or automatically pick another exit.
            m_pendingSelection.clear();m_previousSelection.clear();stop();
            m_nodeError=QStringLiteral("正在使用的节点或策略依赖已删除；相应连接已停止，请重新选择节点。");
            emit diagnostic("EngineController","NodeSourceRevoked",m_nodeError);
        }
        if(!m_connectionRequested) {
            m_options.nodes=nodes;m_options.selectedNodeId=m_store.selectedId();
            const auto configuration=m_store.networkConfiguration();
            if(!removed.isEmpty()&&configuration.value("schema").toInt()==1) {
                m_options.customRules.clear();for(const auto &rule:configuration.value("rules").toArray())m_options.customRules.append(rule.toString());
                m_options.customGroups=configuration.value("groups").toArray().toVariantList();
                m_nativeDocumentRouting=configuration.value("nativeDocumentRouting").toBool(false);updateRoutingFlags();
            }
            emit optionsChanged();
        }
        m_tests.invalidateResults();emit nodesChanged();emit nodeCatalogChanged();
    });
    connect(&m_store,&NodeStore::selectionChanged,this,&EngineController::selectionChanged);
    connect(this,&EngineController::nodesChanged,this,&EngineController::selectionChanged);
    connect(&m_imports,&NodeImportService::changed,this,&EngineController::statusChanged);
    connect(&m_imports,&NodeImportService::nodesApplied,this,[this]{
        // A background subscription refresh must not interrupt live Codex/WS
        // streams. The current immutable engine snapshot lives until reconnect.
        if(m_connectionRequested && (processAlive() || busy())) {
            const auto active=m_engine->status().selectedNodeId;bool retained=false;
            for(const auto &node:m_store.nodes())if(node.id==active){retained=true;break;}
            if(retained) {
                m_nodeError=QStringLiteral("节点库已更新；当前连接继续使用启动时配置。新增节点与凭据更新在手动断开重连后生效。");
                emit diagnostic("EngineController","SubscriptionUpdateDeferred",m_nodeError);
            }
        }
        emit nodesChanged();
    });
    const auto nodePresentation=[this] {
        const auto nodeStatus=m_engine->status();
        // Rust node rows show the dedicated NodeTestService measurement, never
        // the current session's full request latency or byte counters.
        return QVariantList{int(nodeStatus.state),nodeStatus.selectedNodeId,int(nodeStatus.nodeHealth),int(nodeStatus.requestState),nodeStatus.processAlive,nodeStatus.apiHealthy,nodeStatus.directSession,nodeStatus.nodeBusy,m_connectionRequested,m_options.selectedNodeId};
    };
    m_previousNodePresentation=nodePresentation();
    connect(m_engine.get(),&ProxyEngine::statusChanged,this,[this,nodePresentation] {
        const auto presentation=nodePresentation();
        if(presentation!=m_previousNodePresentation){m_previousNodePresentation=presentation;emit nodesChanged();}
        if (!m_shuttingDown && m_restartPending && m_engine->status().state==ProxyEngine::State::Stopped) {
            m_restartPending=false;
            QTimer::singleShot(0,this,[this]{if(!m_shuttingDown && m_connectionRequested && (!m_options.selectedNodeId.isEmpty()||m_options.directSession))m_engine->start(m_options);});
        }
    });
    connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, this,[this]{shutdown();});
    auto *interfaces=new QTimer(this);interfaces->setInterval(15000);
    connect(interfaces,&QTimer::timeout,this,&EngineController::refreshLanAddresses);interfaces->start();
    QTimer::singleShot(0,this,&EngineController::refreshLanAddresses);
}
void EngineController::updateRoutingFlags() {
    m_options.smartRouting=m_smartRoutingEligible&&!m_nativeDocumentRouting&&m_options.customRules.isEmpty();
    m_options.nativePrivateRouting=m_smartRoutingEligible&&!m_nativeDocumentRouting&&!m_options.customRules.isEmpty();
}
QString EngineController::engineIdentityLabel() const {
    const auto status=m_engine->status();
    QString identity;
    if(status.processAlive) {
        identity=status.engineKind==QStringLiteral("rust")?QStringLiteral("Swirl"):QStringLiteral("未知内核");
    } else identity=QStringLiteral("Swirl");
    const auto version=QCoreApplication::applicationVersion();
    return version.isEmpty()?identity:identity+QStringLiteral(" · v")+version;
}
bool EngineController::prepareRealAcceptance() {
    if(processAlive()||busy())return false;
    // Test-only caller: select a supported route before starting the engine.
    // Do not write QSettings, touch the system proxy, or inherit a saved TUN.
    m_options.routingMode="global";
    m_options.smartRouting=false;
    m_options.nativePrivateRouting=false;
    m_options.tunEnabled=false;
    m_options.meteredNetwork=false;
    m_options.allowLan=false;
    emit statusChanged();
    return true;
}
QString EngineController::stateText() const {
    switch (m_engine->status().state) {
    case ProxyEngine::State::Stopped: return QStringLiteral("已停止");
    case ProxyEngine::State::Validating: return QStringLiteral("正在校验");
    case ProxyEngine::State::Starting: return QStringLiteral("正在启动 Rust Core");
    case ProxyEngine::State::Running: return QStringLiteral("Rust Core 运行中");
    case ProxyEngine::State::Degraded: return QStringLiteral("Rust Core 状态异常");
    case ProxyEngine::State::Stopping: return QStringLiteral("正在停止");
    case ProxyEngine::State::Failed: return QStringLiteral("引擎异常");
    }
    return {};
}
QString EngineController::errorCode() const {
    return QString::fromLatin1(QMetaEnum::fromType<ProxyEngine::Error>().valueToKey(int(m_engine->status().error)));
}
bool EngineController::busy() const {
    const auto state = m_engine->status().state;
    return state == ProxyEngine::State::Validating || state == ProxyEngine::State::Starting || state == ProxyEngine::State::Stopping;
}
void EngineController::start() { if(canStart())startConfiguredSession(); }
void EngineController::stop() { rollbackPendingSelection(QStringLiteral("节点切换已取消，保留原选择。"));m_diagnostics.noteEvent(QStringLiteral("Swirl 操作"),QStringLiteral("用户停止引擎，现有本机代理连接将关闭。"));m_proxyRequested=false;m_systemProxy.disable(); m_connectionRequested=false;m_restartPending=false; m_options.selectedNodeId.clear();m_options.directSession=false; m_engine->stop(); }
void EngineController::shutdown() {
    if(m_shuttingDown)return;
    rollbackPendingSelection(QStringLiteral("节点切换已取消，保留原选择。"));
    m_shuttingDown=true;m_connectionRequested=false;m_restartPending=false;m_proxyRequested=false;
    m_imports.shutdown();m_tests.cancel();m_systemProxy.disable();m_engine->stop();
}
void EngineController::refresh() { m_engine->refresh(); }

QVariantList EngineController::nodes() const {
    auto rows=m_store.publicRows(); const auto status=m_engine->status();
    for (auto &value : rows) {
        auto row=value.toMap(); const bool active=processAlive() && row.value("id").toString()==status.selectedNodeId;
        row.insert("address",row.value("host").toString().isEmpty()?QStringLiteral("协议扩展配置"):row.value("host").toString()+":"+row.value("port").toString());
        const auto id=row.value("id").toString();
        row.insert("nodeReference",NodeTestService::nodeReference(id));
        row.insert("connectionState",nodeConnectionState(id));
        row.insert("networkVerified",active&&m_connectionRequested&&m_options.selectedNodeId==id&&status.requestState==ProxyEngine::RequestState::Succeeded&&status.nodeHealth!=ProxyEngine::NodeHealth::Unavailable&&status.state!=ProxyEngine::State::Failed);
        const auto measured=m_tests.result(id);
        QString nodeStatus=QStringLiteral("未测试");
        if(m_tests.testing(id))nodeStatus=QStringLiteral("测试中");
        else if(!measured.isEmpty())nodeStatus=measured.value("success").toBool()?QStringLiteral("可用"):
            measured.value("error").toString().contains("timeout",Qt::CaseInsensitive)||measured.value("error").toString().contains(QStringLiteral("超时"))?QStringLiteral("超时"):QStringLiteral("测试失败");
        const auto connection=row.value("connectionState").toString();
        if(connection!=QStringLiteral("未连接"))nodeStatus=connection;
        row.insert("status",nodeStatus);
        row.insert("testAvailable",!m_tests.testing(id)&&measured.value("success").toBool());
#ifdef SWIRL_USE_RUST_CORE
        row.insert("latency",QStringLiteral("—"));
#else
        row.insert("latency",active && status.latencyMs>=0?QString::number(status.latencyMs):QStringLiteral("—"));
#endif
        if(!measured.isEmpty()){
            const auto timing=measured.value(measured.value("metricType")==QStringLiteral("http_headers")?"outboundConnectMs":"latency");
            bool valid=false;const auto elapsed=timing.toLongLong(&valid);
            row.insert("latency",measured.value("success").toBool()&&valid&&elapsed>=0?QString::number(elapsed):QStringLiteral("失败"));
            row.insert("testHttp",measured.value("http"));row.insert("testError",measured.value("error"));
        }
        value=row;
    }
    return rows;
}
QVariantList EngineController::nodeDiagnosticRows() const {
    QVariantList result;
    for(const auto &value:nodes()) {
        const auto row=value.toMap();const auto measured=m_tests.result(row.value("id").toString());
        // A stable opaque reference links the visible node, its result and log.
        // Never export names, endpoints, IDs, credentials or source parameters.
        result.append(QVariantMap{{"nodeReference",row.value("nodeReference")},{"protocol",row.value("protocol")},
            {"imported",true},{"executable",row.value("nativeExecutable")},{"connectionState",row.value("connectionState")},
            {"requestVerified",row.value("networkVerified")},{"tested",!measured.isEmpty()},
            {"testSucceeded",measured.value("success",false)},{"phase",measured.value("phase")},
            {"failureCode",measured.value("failureCode")},{"httpStatus",measured.value("http")},
            {"outboundConnectMs",measured.value("outboundConnectMs",-1)},{"originTlsMs",measured.value("originTlsMs",-1)},
            {"testedAt",measured.value("time")}});
    }
    return result;
}
QString EngineController::nodeConnectionState(const QString &id) const {
    if(id.isEmpty()||!m_connectionRequested||m_options.selectedNodeId!=id)return QStringLiteral("未连接");
    const auto status=m_engine->status();const bool active=processAlive()&&status.selectedNodeId==id;
    if(status.state==ProxyEngine::State::Failed||status.requestState==ProxyEngine::RequestState::Failed||status.nodeHealth==ProxyEngine::NodeHealth::Unavailable)return QStringLiteral("连接失败");
    if(active&&status.requestState==ProxyEngine::RequestState::Succeeded)return QStringLiteral("已连接");
    if(busy()||status.nodeBusy)return QStringLiteral("正在连接");
    return active?QStringLiteral("会话就绪 · 未验证"):QStringLiteral("未连接");
}
QString EngineController::selectedNodeName() const {
    for (const auto &n:m_store.nodes()) if(n.id==m_store.selectedId())return n.name;
    return QStringLiteral("未选择节点");
}
QString EngineController::nodeStateText() const {
    if (connected()&&m_engine->status().directSession)return QStringLiteral("直接连接");
    return nodeConnectionState(activeNodeId());
}
QString EngineController::requestStateText() const {
    const auto s=m_engine->status();
    if(!s.nodeMessage.isEmpty())return s.nodeMessage;
    switch(s.requestState) {
    case ProxyEngine::RequestState::NotTested:return QStringLiteral("尚未发起实际请求");
    case ProxyEngine::RequestState::InProgress:return QStringLiteral("正在通过本机代理请求");
    case ProxyEngine::RequestState::Succeeded:return QStringLiteral("实际请求成功");
    case ProxyEngine::RequestState::Failed:return QStringLiteral("实际请求失败");
    }
    return {};
}
void EngineController::setProxyPort(int port) { if(canStart() && port>0 && port<=65535){m_options.proxyPort=quint16(port);emit optionsChanged();} }
bool EngineController::saveNode(const QVariantMap &input) {
    if(processAlive() || busy() || m_imports.busy()) { m_nodeError=QStringLiteral("请先断开引擎并等待导入完成，再编辑节点。");emit nodesChanged();return false; }
    m_nodeError.clear(); const bool ok=m_store.saveNode(input);emit nodesChanged();return ok;
}
bool EngineController::deleteNode(const QString &id) {
    if(processAlive() || busy() || m_imports.busy()){m_nodeError=QStringLiteral("请先断开引擎并等待导入完成，再删除节点。");emit nodesChanged();return false;}
    m_nodeError.clear();const bool ok=m_store.removeNode(id);emit nodesChanged();return ok;
}
bool EngineController::chooseNode(const QString &id) {
    if(m_shuttingDown)return false;
    if(nodeBusy())return false;
    if(processAlive()&&!activeNodeId().isEmpty()&&!apiHealthy()){m_nodeError=QStringLiteral("控制接口未就绪，不能切换节点。");emit selectionChanged();return false;}
    const bool active=processAlive()&&!activeNodeId().isEmpty();
    if(active&&id.isEmpty()){m_nodeError=QStringLiteral("连接期间不能清空节点选择；请先断开连接。");emit selectionChanged();return false;}
    if(!id.isEmpty()) {
        // A running session owns its original node snapshot. A refreshed or
        // newly imported node only becomes eligible after an explicit reconnect.
        auto candidate=active?m_options:EngineStartOptions{};
        if(!active){candidate.nodes=m_store.nodes();candidate.routingMode="global";}
        candidate.selectedNodeId=id;candidate.directSession=false;
        // DIRECT bypasses node translation for traffic, but a saved selection
        // must still be eligible when the user later leaves explicit DIRECT.
        if(candidate.routingMode=="direct")candidate.routingMode="global";
        QJsonObject configuration;const auto reason=RustCoreEngine::configuration(candidate,&configuration);
        if(!reason.isEmpty()){m_nodeError=reason;emit selectionChanged();return false;}
    }
    if(active&&activeNodeId()!=id){
        m_previousSelection=activeNodeId();m_pendingSelection=id;
    }
    m_nodeError.clear();const bool ok=m_store.select(id);
    if(!ok){m_pendingSelection.clear();m_previousSelection.clear();}
    if(ok&&active&&activeNodeId()!=id){
        m_engine->selectNode(id);
    }
    emit selectionChanged();emit statusChanged();return ok&&m_store.selectedId()==id;
}
void EngineController::rollbackPendingSelection(const QString &reason) {
    if(m_pendingSelection.isEmpty())return;
    const auto previous=m_previousSelection;m_pendingSelection.clear();m_previousSelection.clear();
    m_nodeError=m_store.select(previous)?reason:QStringLiteral("节点切换失败，原出口保持运行；无法恢复保存的选择：")+m_store.error();
    emit selectionChanged();emit statusChanged();
}
void EngineController::connectNode(const QString &id) {
    if(m_shuttingDown)return;
    if(id.isEmpty()){if(!nodeBusy())startConfiguredSession();return;}
    if(nodeBusy() || !chooseNode(id))return;
    if(processAlive() && !activeNodeId().isEmpty())return;
    // Selection checks node eligibility in isolation. Starting a session must
    // also check the user's actual routing and network options before changing
    // engine state. Do not silently replace saved rule mode with global mode.
    auto candidate=m_options;
    candidate.nodes=m_store.nodes();candidate.selectedNodeId=id;candidate.directSession=false;
    QJsonObject configuration;
    m_nodeError=RustCoreEngine::configuration(candidate,&configuration);
    if(!m_nodeError.isEmpty()){
        m_connectionRequested=false;emit selectionChanged();emit statusChanged();return;
    }
    m_connectionRequested=true;
    m_options.nodes=m_store.nodes();m_options.selectedNodeId=id;m_options.directSession=false;
    if(processAlive()){m_restartPending=true;m_engine->stop();}
    else m_engine->start(m_options);
}
void EngineController::startConfiguredSession() {
    if(m_shuttingDown)return;
    // An absent/deleted subscription selection is not authorization to bypass
    // proxies. DIRECT is an explicit routing mode, never the empty-ID default.
    if(m_store.selectedId().isEmpty()&&m_options.routingMode!="direct") {
        m_nodeError=QStringLiteral("未选择可用节点；请选择节点或明确启用直接连接模式。未自动切换 DIRECT。");emit selectionChanged();emit statusChanged();return;
    }
    auto candidate=m_options;
    candidate.nodes=m_store.nodes();candidate.selectedNodeId=m_store.selectedId();
    candidate.directSession=candidate.routingMode=="direct";
    QJsonObject configuration;
    const auto reason=RustCoreEngine::configuration(candidate,&configuration);
    if(!reason.isEmpty()){
        m_nodeError=reason;emit selectionChanged();emit statusChanged();return;
    }
    m_nodeError.clear();
    m_connectionRequested=true;
    m_options.nodes=m_store.nodes();m_options.selectedNodeId=m_store.selectedId();
    m_options.directSession=m_options.routingMode=="direct";
    if(processAlive()){m_systemProxy.disable();m_restartPending=true;m_engine->stop();}
    else m_engine->start(m_options);
    emit statusChanged();
}
void EngineController::testNode(const QUrl &url) { if(!nodeBusy())m_engine->probeNode(url); }
void EngineController::testAllNodes(const QUrl &url) { if(m_shuttingDown)return; auto options=m_options;options.nodes=m_store.nodes();QStringList ids;for(const auto &node:options.nodes)ids.append(node.id);m_tests.start(options,ids,url); }
void EngineController::testSelectedNode(const QString &id,const QUrl &url) { if(m_shuttingDown)return; auto options=m_options;options.nodes=m_store.nodes();m_tests.start(options,{id},url); }
void EngineController::disconnectNode() { stop(); }

void EngineController::setRoutingMode(const QString &mode) {
    if(mode!="rule"&&mode!="global"&&mode!="direct")return;
    if(m_options.meteredNetwork&&mode!="rule"){m_routingError=QStringLiteral("请先关闭计费网络模式，再更改出站模式。");emit statusChanged();return;}
    if(busy()||routingBusy()||nodeBusy()||(processAlive()&&!connected())) {
        m_routingError=QStringLiteral("请等待当前操作完成，并连接节点后再切换运行模式。");emit statusChanged();return;
    }
    if(processAlive()){
        auto candidate=m_options;candidate.routingMode=mode;candidate.directSession=mode=="direct";
        candidate.nodes=m_store.nodes();candidate.selectedNodeId=m_store.selectedId();
        QJsonObject configuration;const auto reason=RustCoreEngine::configuration(candidate,&configuration);
        if(!reason.isEmpty()){m_routingError=reason;emit statusChanged();return;}
    }
    m_routingError.clear();m_options.routingMode=mode;
    m_options.directSession=mode=="direct";
    QSettings().setValue("Proxy/routingMode",mode);
    if(processAlive())m_engine->setRoutingMode(mode);
    emit statusChanged();
}
void EngineController::setSystemProxy(bool enabled) {
    if(m_shuttingDown)return;
    m_diagnostics.noteEvent(QStringLiteral("Swirl 操作"),enabled?QStringLiteral("用户请求启用系统代理。"):QStringLiteral("用户请求释放系统代理并恢复原设置。"));
    m_routingError.clear();m_proxyRequested=enabled;
    if(!enabled){m_systemProxy.disable();emit statusChanged();return;}
    if(m_systemProxy.owned()||m_proxyChecking)return;
    const auto s=m_engine->status();
    if(!s.processAlive&&!busy()&&!m_imports.busy()){
        startConfiguredSession();
        if(!processAlive()&&!busy()){
            m_proxyRequested=false;m_routingError=m_nodeError;emit statusChanged();
        }
        return;
    }
    if(!s.processAlive||!s.apiHealthy||s.proxyPort<1||(!s.directSession&&s.selectedNodeId.isEmpty())||s.nodeHealth==ProxyEngine::NodeHealth::Unavailable){
        m_proxyRequested=false;m_routingError=QStringLiteral("请先连接可用节点，并等待引擎与控制接口健康。");emit statusChanged();return;}
    m_proxyChecking=true;emit statusChanged();
    auto socket=new QTcpSocket(this);socket->setProxy(QNetworkProxy::NoProxy);
    auto timer=new QTimer(socket);timer->setSingleShot(true);timer->start(1500);
    connect(socket,&QTcpSocket::connected,this,[this,socket,timer,s] {
        timer->stop();m_proxyChecking=false;socket->deleteLater();
        const auto now=m_engine->status();
        if(m_proxyRequested&&now.processAlive&&now.apiHealthy&&now.processId==s.processId&&now.proxyPort==s.proxyPort) {
            const auto port=m_captureProxyPort>0?m_captureProxyPort:s.proxyPort;
            // The capture relay is also a Swirl-owned loopback endpoint. Do
            // not rediscover it as an external proxy after the core stops.
            m_imports.rememberOwnedProxyPort(port);
            if(!m_systemProxy.enable(port,s.processId))m_proxyRequested=false;
        }
        emit statusChanged();
    });
    const auto failed=[this,socket,timer] {if(!m_proxyChecking)return;timer->stop();m_proxyChecking=false;m_proxyRequested=false;
        m_routingError=QStringLiteral("本机代理端口未监听，未修改 Windows 系统代理。");socket->deleteLater();emit statusChanged();};
    connect(timer,&QTimer::timeout,this,failed);
    connect(socket,&QTcpSocket::errorOccurred,this,[failed](QAbstractSocket::SocketError){failed();});
    socket->connectToHost(QHostAddress::LocalHost,quint16(m_captureProxyPort>0?m_captureProxyPort:s.proxyPort));
}
void EngineController::toggleSystemProxy() {
    if(m_shuttingDown||systemProxyBusy())return;
    m_systemProxy.refresh();
    if(!m_systemProxy.stateReadError().isEmpty())return;
    if(m_systemProxy.systemEnabled()||m_systemProxy.owned()) {
        m_proxyRequested=false;m_routingError.clear();
        m_diagnostics.noteEvent(QStringLiteral("Swirl 操作"),QStringLiteral("用户请求关闭 Windows 系统代理。"));
        m_systemProxy.turnOffSystemProxy();emit statusChanged();
    } else {
        setSystemProxy(true);
        if(!processAlive()&&!busy()&&!m_nodeError.isEmpty()) {
            m_proxyRequested=false;m_routingError=m_nodeError;emit statusChanged();
        }
    }
}
QString EngineController::proxyEnvironmentAdvice() const {
    return QStringLiteral("从新的 PowerShell 会话启动支持代理变量的应用：\n"
        "$env:HTTP_PROXY='http://127.0.0.1:%1'\n$env:HTTPS_PROXY='http://127.0.0.1:%1'\n"
        "$env:ALL_PROXY='http://127.0.0.1:%1'\n$env:NO_PROXY='localhost,127.0.0.1,::1'\n"
        "Codex 是否读取系统代理或这些变量取决于具体版本。完全退出后从该会话重新启动，已有进程不会自动继承。"
        "当前 Rust Core 构建不提供 TUN；忽略代理设置的应用无法通过本页接入。"
        "本页只提供建议，不写入环境变量、.codex 配置文件或密钥。").arg(m_options.proxyPort);
}

bool EngineController::networkEditAllowed() {
    if(m_moduleOverlayActive){m_networkError=QStringLiteral("请先停用已启用的配置模块，再编辑基础网络配置。");emit optionsChanged();return false;}
    if(!canStart()){m_networkError=QStringLiteral("请先断开引擎，再修改 DNS、规则或策略组。");emit optionsChanged();return false;}
    m_networkError.clear();return true;
}

QVariantMap EngineController::networkConfigurationSnapshot() const {return {{"dns",m_options.dnsConfig},{"rules",m_options.customRules},{"groups",m_options.customGroups}};}
bool EngineController::validateNetworkConfiguration(const QVariantMap &input,QVariantMap *canonical,const QList<ProxyNode> *candidateNodes) {
    for(const auto &key:input.keys())if(!QStringList{"dns","rules","groups"}.contains(key)){m_networkError=QStringLiteral("不支持的配置覆盖字段：")+key;emit optionsChanged();return false;}
    const auto reject=[&](const QString &message){m_networkError=message;emit optionsChanged();return false;};
    if(input.contains("dns")&&!QJsonValue::fromVariant(input.value("dns")).isObject())return reject(QStringLiteral("DNS 配置必须为对象。"));
    if(input.contains("groups")&&!QJsonValue::fromVariant(input.value("groups")).isArray())return reject(QStringLiteral("策略组必须为数组。"));
    QStringList rules;
    if(input.contains("rules")) {
        const auto raw=QJsonValue::fromVariant(input.value("rules"));if(!raw.isArray())return reject(QStringLiteral("规则必须为字符串数组。"));
        for(const auto &rule:raw.toArray()){if(!rule.isString())return reject(QStringLiteral("规则必须为字符串。"));rules.append(rule.toString());}
    }
    const auto dns=input.value("dns").toMap();const auto groups=input.value("groups").toList();
    const auto error=RustCoreEngine::validateNetworkConfiguration(candidateNodes?*candidateNodes:m_store.nodes(),dns,rules,groups);
    if(!error.isEmpty())return reject(error);
    if(canonical)*canonical={{"dns",dns},{"rules",rules},{"groups",groups}};m_networkError.clear();return true;
}

bool EngineController::replaceNetworkConfiguration(const QVariantMap &input) {
    if(!canStart()){m_networkError=QStringLiteral("请先断开引擎，再应用或停用配置覆盖。");emit optionsChanged();return false;}
    QVariantMap canonical;if(!validateNetworkConfiguration(input,&canonical))return false;const auto previous=networkConfigurationSnapshot();
    m_options.dnsConfig=canonical.value("dns").toMap();m_options.customRules=canonical.value("rules").toStringList();m_options.customGroups=canonical.value("groups").toList();
    if(saveNetworkConfiguration()){updateRoutingFlags();return true;}m_options.dnsConfig=previous.value("dns").toMap();m_options.customRules=previous.value("rules").toStringList();m_options.customGroups=previous.value("groups").toList();emit optionsChanged();return false;
}
QJsonObject EngineController::serializedNetworkConfiguration() {
    const auto protectedPassword=m_options.lanPassword.isEmpty()?QByteArray():protectLanPassword(m_options.lanPassword.toUtf8(),false);
    if(!m_options.lanPassword.isEmpty()&&protectedPassword.isEmpty()){m_networkError=QStringLiteral("无法加密局域网代理密码。");return {};}
    auto snapshot=QJsonObject{{"schema",1},{"metered",m_options.meteredNetwork},{"meteredAllowlist",QJsonArray::fromStringList(m_options.meteredAllowlist)},{"tunBeforeMetered",m_tunBeforeMetered},{"modeBeforeMetered",m_modeBeforeMetered},{"allowLan",m_options.allowLan},{"lanUsername",m_options.lanUsername},{"lanPasswordProtected",QString::fromLatin1(protectedPassword.toBase64())},{"tun",m_options.tunEnabled},{"dns",QJsonObject::fromVariantMap(m_options.dnsConfig)},
        {"rules",QJsonArray::fromStringList(m_options.customRules)},{"groups",QJsonArray::fromVariantList(m_options.customGroups)}};
    if(m_nativeDocumentRouting)snapshot.insert("nativeDocumentRouting",true);
    const auto original=m_store.networkConfiguration().value("importedConfiguration");
    if(!original.isUndefined())snapshot.insert("importedConfiguration",original);
    const auto outcomes=m_store.networkConfiguration().value("subscriptionImportResults");
    if(outcomes.isObject())snapshot.insert("subscriptionImportResults",outcomes);
    return snapshot;
}
bool EngineController::saveNetworkConfiguration() {
    const auto snapshot=serializedNetworkConfiguration();
    if(snapshot.isEmpty() || !m_store.saveNetworkConfiguration(snapshot)) {
        if(!snapshot.isEmpty())m_networkError=m_store.error();emit optionsChanged();return false;
    }
    emit optionsChanged();emit statusChanged();return true;
}
bool EngineController::commitRoutingConfiguration(const QStringList &rules,const QVariantList &groups) {
    const auto error=RustCoreEngine::validateNetworkConfiguration(m_store.nodes(),m_options.dnsConfig,rules,groups,m_smartRoutingEligible&&!m_nativeDocumentRouting&&!rules.isEmpty());
    if(!error.isEmpty()){m_networkError=error;emit optionsChanged();return false;}
    if(rules==m_options.customRules&&groups==m_options.customGroups){emit optionsChanged();return true;}
    // Validate and durably save the candidate before publishing it to QML.
    // A failed QSaveFile commit must not expose even a transient edited state.
    auto snapshot=serializedNetworkConfiguration();
    if(snapshot.isEmpty()){emit optionsChanged();return false;}
    snapshot["rules"]=QJsonArray::fromStringList(rules);
    snapshot["groups"]=QJsonArray::fromVariantList(groups);
    if(!m_store.saveNetworkConfiguration(snapshot)){m_networkError=m_store.error();emit optionsChanged();return false;}
    m_options.customRules=rules;m_options.customGroups=groups;updateRoutingFlags();
    emit optionsChanged();emit statusChanged();return true;
}
bool EngineController::importNodesAndConfiguration(const QList<ProxyNode> &incoming,const QString &sourceId,const QVariantMap &input,const QJsonObject &original,const QString &sourceFormat,bool *candidateValidationFailed) {
    if(candidateValidationFailed)*candidateValidationFailed=false;
    // Only this owner may apply while its importer is busy. Existing active
    // sessions and module overlays must never be reconfigured underneath them.
    if(m_shuttingDown || busy() || processAlive() || m_moduleOverlayActive) {
        m_networkError=QStringLiteral("请先断开引擎并停用模块，再导入完整网络配置。");return false;
    }
    NodeStore::ImportPlan plan;
    if(!m_store.prepareImport(incoming,sourceId,&plan)){m_networkError=m_store.error();return false;}
    // Only this validation phase may be reduced to nodes after Rust has
    // separately audited the entire original. Busy/ownership/store/I/O errors
    // must never be mistaken for compatibility errors or trigger a second save.
    if(candidateValidationFailed)*candidateValidationFailed=true;
    auto mapped=input;
    const auto importMetadata=QJsonObject::fromVariantMap(mapped.take("importMetadata").toMap());
    // A subscription profile without DNS instructions must not erase the
    // user's secure resolver/hosts configuration and fall back to the system.
    if(!mapped.contains("dns"))mapped["dns"]=m_options.dnsConfig;
    // Refreshing the same provider retains a valid manual choice. A different
    // provider (or an unowned pasted document) cannot inherit another profile's
    // selection merely by using the same group name.
    QHash<QString,QString> previousChoices;
    const auto previousOwner=m_store.networkConfiguration().value("importedConfiguration").toObject().value("sourceId").toString();
    if(!sourceId.isEmpty() && previousOwner==sourceId)for(const auto &entry:m_options.customGroups) {
        const auto group=entry.toMap();const auto members=group.value("proxies").toStringList();
        if(group.value("type").toString()=="select" && !members.isEmpty())
            previousChoices.insert(group.value("name").toString(),group.value("default-selected",members.first()).toString());
    }
    QVariantList groups;const auto names=plan.nameToId();
    for(auto it=names.cbegin();it!=names.cend();++it)if(it.value().isEmpty()) {
        m_networkError=QStringLiteral("完整配置按名称引用了歧义节点；请为不同节点设置不同名称。旧节点与网络配置保持不变。");return false;
    }
    QSet<QString> groupNames;for(const auto &entry:input.value("groups").toList())groupNames.insert(entry.toMap().value("name").toString());
    for(const auto &reserved:QStringList{"DIRECT","REJECT","SWIRL","GLOBAL"})if(names.contains(reserved)) {
        m_networkError=QStringLiteral("节点名称与保留策略名称冲突；未应用配置。");return false;
    }
    for(const auto &entry:input.value("groups").toList()) {
        auto group=entry.toMap();
        if(names.contains(group.value("name").toString())){m_networkError=QStringLiteral("节点与策略组名称冲突；未应用配置。");return false;}
        const auto raw=QJsonValue::fromVariant(group.value("proxies"));
        if(!raw.isArray()){m_networkError=QStringLiteral("策略组成员必须为字符串数组。");return false;}
        QStringList members;
        for(const auto &value:raw.toArray()) {
            if(!value.isString()){m_networkError=QStringLiteral("策略组成员必须为字符串。");return false;}
            const auto name=value.toString();
            if(!names.contains(name)&&!groupNames.contains(name)&&name!="DIRECT"&&name!="REJECT") {
                m_networkError=QStringLiteral("完整订阅引用了文档外的节点或策略；未应用配置。");return false;
            }
            members.append(names.value(name,name));
        }
        group["proxies"]=members;
        if(group.contains("default-selected")) {
            if(group.value("default-selected").metaType().id()!=QMetaType::QString){m_networkError=QStringLiteral("默认策略必须为字符串。");return false;}
            const auto name=group.value("default-selected").toString();
            if(!raw.toArray().contains(QJsonValue(name))){m_networkError=QStringLiteral("默认策略必须使用文档中声明的成员名称。");return false;}
            group["default-selected"]=names.value(name,name);
        }else if(group.value("type").toString()=="select") {
            const auto previous=previousChoices.value(group.value("name").toString());
            if(!previous.isEmpty() && members.contains(previous) && previous!=members.first())group["default-selected"]=previous;
        }
        groups.append(group);
    }
    if(input.contains("groups")) {
        if(!QJsonValue::fromVariant(input.value("groups")).isArray()){m_networkError=QStringLiteral("策略组必须为数组。");return false;}
        mapped["groups"]=groups;
    }
    // Resolve only this document's node names to final persisted UUIDs. Never
    // accept arbitrary stored UUIDs/names or the editor's SWIRL alias from a
    // document: those could select a node belonging to a different provider.
    const auto rawRules=QJsonValue::fromVariant(input.value("rules"));
    if(rawRules.isArray()) {
        QJsonArray rules;
        for(const auto &value:rawRules.toArray()) {
            if(!value.isString()){rules.append(value);continue;} // Shared validator reports the type error.
            auto parts=routingRuleFields(value.toString());const auto targetIndex=routingRuleTargetIndex(parts);
            const auto target=parts.value(targetIndex);
            if(names.contains(target)) {
                parts[targetIndex]=names.value(target);rules.append(parts.join(','));
            }else if(target=="DIRECT"||target=="REJECT"||(groupNames.contains(target)&&target!="SWIRL"&&target!="GLOBAL"))rules.append(value);
            else {
                m_networkError=QStringLiteral("订阅规则只能引用本文件声明的节点、策略组、DIRECT 或 REJECT；未应用配置。");return false;
            }
        }
        mapped["rules"]=rules.toVariantList();
    }
    QVariantMap canonical;const auto nodes=plan.nodes();
    if(!validateNetworkConfiguration(mapped,&canonical,&nodes))return false;
    if(candidateValidationFailed)*candidateValidationFailed=false;
    const auto previous=networkConfigurationSnapshot();const bool previousNative=m_nativeDocumentRouting,previousSmart=m_options.smartRouting,previousPrivate=m_options.nativePrivateRouting;
    if(!original.isEmpty()){m_nativeDocumentRouting=true;m_options.smartRouting=false;m_options.nativePrivateRouting=false;}
    m_options.dnsConfig=canonical.value("dns").toMap();m_options.customRules=canonical.value("rules").toStringList();m_options.customGroups=canonical.value("groups").toList();
    auto snapshot=serializedNetworkConfiguration();
    if(!snapshot.isEmpty() && !original.isEmpty())snapshot.insert("importedConfiguration",QJsonObject{{"format",sourceFormat},{"sourceId",sourceId},{"configuration",original},{"metadata",importMetadata}});
    if(!snapshot.isEmpty()&&m_imports.automaticImport())snapshot=recordSubscriptionOutcome(snapshot,sourceId,sourceFormat,"full",profileMetadataNotice(importMetadata),importMetadata);
    if(snapshot.isEmpty() || !m_store.commitImport(plan,snapshot)) {
        if(!snapshot.isEmpty())m_networkError=m_store.error();
        m_nativeDocumentRouting=previousNative;m_options.smartRouting=previousSmart;m_options.nativePrivateRouting=previousPrivate;
        m_options.dnsConfig=previous.value("dns").toMap();m_options.customRules=previous.value("rules").toStringList();m_options.customGroups=previous.value("groups").toList();emit optionsChanged();return false;
    }
    m_networkError.clear();emit optionsChanged();emit statusChanged();return true;
}
bool EngineController::configureDns(const QVariantMap &input) {
    if(!networkEditAllowed())return false;
    // The existing settings page sends its visible fields only. Preserve an
    // imported query policy unless the caller explicitly supplies a replacement.
    auto requested=input;
    if(!requested.contains("queryFamily") && m_options.dnsConfig.contains("queryFamily"))
        requested.insert("queryFamily",m_options.dnsConfig.value("queryFamily"));
    QJsonObject validatedDns;const auto error=SwirlRustDns::configuration(requested,&validatedDns);
    if(!error.isEmpty()){m_networkError=error;emit optionsChanged();return false;}
    const auto mode=input.value("mode",0).toInt();
    if(mode<0||mode>2){m_networkError=QStringLiteral("无效 DNS 模式。");emit optionsChanged();return false;}
    QStringList servers;
    const auto raw=input.value("servers").toString();
    for(const auto &part:raw.split(',',Qt::SkipEmptyParts)) {
        const auto server=part.trimmed();
        if(QHostAddress(server).isNull()){m_networkError=QStringLiteral("DNS 服务器必须是 IPv4 或 IPv6 地址。");emit optionsChanged();return false;}
        servers.append(server);
    }
    if(mode==2&&servers.isEmpty()){m_networkError=QStringLiteral("请填写自定义 DNS 服务器。");emit optionsChanged();return false;}
    const auto encrypted=input.value("encrypted").toString().trimmed();
    if(!encrypted.isEmpty()) {
        const QUrl url(encrypted);
        if(!url.isValid()||url.host().isEmpty()||!url.userInfo().isEmpty()||url.hasFragment()||
           !QStringList{"https","tls","tcp"}.contains(url.scheme())||encrypted.size()>2048) {
            m_networkError=QStringLiteral("加密 DNS 地址必须使用 https://、tls:// 或 tcp://。");emit optionsChanged();return false;
        }
    }
    QVariantList hosts;
    for(const auto &entry:input.value("hosts").toList()) {
        const auto row=entry.toMap();const auto name=row.value("name").toString().trimmed();
        const auto value=row.value("value").toString().trimmed();
        if(name.isEmpty()||name.size()>253||!QRegularExpression("^[A-Za-z0-9_.\\*-]+$").match(name).hasMatch()||QHostAddress(value).isNull()) {
            m_networkError=QStringLiteral("本地 DNS 映射必须包含有效域名和 IP 地址。");emit optionsChanged();return false;
        }
        hosts.append(QVariantMap{{"id",name},{"name",name},{"value",value},{"server",row.value("server")},{"comment",row.value("comment")}});
    }
    const auto before=m_options.dnsConfig;
    m_options.dnsConfig={{"mode",mode},{"servers",servers.join(',')},{"encrypted",encrypted},{"hosts",hosts},
        {"useHosts",input.value("useHosts",true).toBool()},{"respectRules",input.value("respectRules",false).toBool()}};
    if(requested.contains("queryFamily"))m_options.dnsConfig.insert("queryFamily",requested.value("queryFamily"));
    if(saveNetworkConfiguration())return true;m_options.dnsConfig=before;emit optionsChanged();return false;
}
bool EngineController::saveRoutingRule(const QString &type,const QString &pattern,const QString &policy,int index) {
    if(!networkEditAllowed())return false;
    const QStringList types={"DOMAIN","DOMAIN-SUFFIX","DOMAIN-KEYWORD","IP-CIDR","IP-CIDR6","PROCESS-NAME","DST-PORT","SRC-IP-CIDR","MATCH"};
    bool valid=types.contains(type)&&pattern.size()<=2048&&!pattern.contains(QRegularExpression("[,\\r\\n]"));
    QStringList policies={"DIRECT","REJECT","SWIRL"};for(const auto &g:m_options.customGroups)policies.append(g.toMap().value("name").toString());
    for(const auto &node:m_store.nodes())policies.append(node.id);
    valid=valid&&policies.contains(policy)&&(type=="MATCH"||!pattern.trimmed().isEmpty());
    if(type=="IP-CIDR"||type=="IP-CIDR6"||type=="SRC-IP-CIDR") {
        const auto cidr=QHostAddress::parseSubnet(pattern);valid=valid&&!cidr.first.isNull()&&cidr.second>=0;
    }
    if(type=="DST-PORT"){bool ok=false;const auto port=pattern.toInt(&ok);valid=valid&&ok&&port>0&&port<=65535;}
    if(!valid||index<-1||index>=m_options.customRules.size()||(index<0&&m_options.customRules.size()>=1000)){m_networkError=QStringLiteral("规则类型、匹配值或目标策略无效。");emit optionsChanged();return false;}
    auto rules=m_options.customRules;
    auto rule=type=="MATCH"?"MATCH,"+policy:type+","+pattern.trimmed()+","+policy;
    if(index>=0) {
        const auto previous=routingRuleFields(rules[index]);
        const auto options=previous.mid(routingRuleTargetIndex(previous)+1);
        // The current editor has no modifier controls. Preserve hidden options
        // on the same rule kind (or the equivalent IPv4/IPv6 CIDR kind), and
        // reject a type change that would otherwise discard their semantics.
        if(!options.isEmpty()) {
            if(previous.value(0)!=type&&!(destinationCidrRule(previous.value(0))&&destinationCidrRule(type))) {
                m_networkError=QStringLiteral("原规则含当前编辑器未显示的附加参数，不能通过更改类型丢弃；原规则保持不变。");emit optionsChanged();return false;
            }
            rule+=','+options.join(',');
        }
        if(routingRuleFields(rule)!=previous)rules[index]=rule;
    } else rules.append(rule);
    return commitRoutingConfiguration(rules,m_options.customGroups);
}
bool EngineController::removeRoutingRule(int index) {
    if(!networkEditAllowed()||index<0||index>=m_options.customRules.size())return false;
    auto rules=m_options.customRules;rules.removeAt(index);
    return commitRoutingConfiguration(rules,m_options.customGroups);
}
bool EngineController::savePolicyGroup(const QString &name,const QString &type,const QStringList &members) {
    if(!networkEditAllowed())return false;
    if(name.trimmed().isEmpty()||name!=name.trimmed()||name.contains(QRegularExpression("[,\\x00-\\x1f\\x7f]"))||name.size()>100||QStringList{"DIRECT","REJECT","SWIRL","GLOBAL"}.contains(name)||
       !QStringList{"select","url-test","fallback","load-balance"}.contains(type)||members.isEmpty()) {
        m_networkError=QStringLiteral("策略组名称、类型或子策略无效。");emit optionsChanged();return false;
    }
    auto groups=m_options.customGroups;
    int position=-1;for(int i=0;i<groups.size();++i)if(groups[i].toMap().value("name")==name.trimmed())position=i;
    QVariantMap group{{"name",name.trimmed()},{"type",type},{"proxies",members},{"url","https://www.gstatic.com/generate_204"},{"interval",300}};
    // The existing editor edits name/type/members only; keep stored options it
    // cannot display, and reject incompatible combinations instead of erasing.
    if(position>=0){group=groups[position].toMap();group["type"]=type;group["proxies"]=members;}
    if(position>=0)groups[position]=group;else groups.append(group);
    return commitRoutingConfiguration(m_options.customRules,groups);
}
bool EngineController::removePolicyGroup(const QString &name) {
    if(!networkEditAllowed())return false;
    for(const auto &rule:m_options.customRules) {
        const auto fields=routingRuleFields(rule);
        if(fields.value(routingRuleTargetIndex(fields))==name){m_networkError=QStringLiteral("请先删除引用此策略组的规则。");emit optionsChanged();return false;}
    }
    for(const auto &value:m_options.customGroups){const auto group=value.toMap();if(group.value("name")!=name&&group.value("proxies").toStringList().contains(name)){m_networkError=QStringLiteral("请先移除其他策略组对此组的引用。");emit optionsChanged();return false;}}
    auto groups=m_options.customGroups;
    for(int i=groups.size()-1;i>=0;--i)if(groups[i].toMap().value("name")==name)groups.removeAt(i);
    return commitRoutingConfiguration(m_options.customRules,groups);
}
QVariantList EngineController::routingRules() const {
    if(processAlive())return m_engine->routingRules();
    auto preview=m_options;preview.routingMode="rule";preview.directSession=false;
    return RustCoreEngine::routingRulesForOptions(preview);

}

bool EngineController::elevated() const {
#ifdef Q_OS_WIN
    HANDLE token=nullptr;TOKEN_ELEVATION elevation{};DWORD size=0;
    if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token))return false;
    const bool result=GetTokenInformation(token,TokenElevation,&elevation,sizeof(elevation),&size)&&elevation.TokenIsElevated;
    CloseHandle(token);return result;
#else
    return false;
#endif
}
bool EngineController::setTunEnabled(bool enabled) {
    m_routingError.clear();
    if(enabled){m_routingError=QStringLiteral("Rust Core 暂不支持 TUN 增强模式；已保存配置保持不变。");emit statusChanged();return false;}
    if(!enabled&&m_options.meteredNetwork){m_routingError=QStringLiteral("计费网络模式正在使用增强模式，请先关闭计费网络模式。");emit statusChanged();return false;}
    if(enabled&&!elevated()){m_routingError=QStringLiteral("请退出 Swirl，并以管理员身份运行后开启增强模式。");emit statusChanged();return false;}
    if(busy()||nodeBusy()||routingBusy()){m_routingError=QStringLiteral("请先选择一个可用代理节点，并等待当前操作结束。");emit statusChanged();return false;}
    const bool previous=m_options.tunEnabled;m_options.tunEnabled=enabled;
    if(!saveNetworkConfiguration()){m_options.tunEnabled=previous;return false;}
    if(enabled||processAlive())startConfiguredSession();
    emit statusChanged();return true;
}

void EngineController::setCaptureProxyPort(int port) {
    if(port<0||port>65535||port==m_captureProxyPort)return;
    m_captureProxyPort=port;
    if(m_systemProxy.owned()){m_systemProxy.disable();if(m_proxyRequested)setSystemProxy(true);}
}

QStringList EngineController::lanAddresses() const {
    return m_lanAddresses;
}
void EngineController::refreshLanAddresses(){
    // GetAdaptersAddresses was running inside a QML text binding on every
    // status tick, including while its LAN dialog was closed (profiled ~9ms).
    if(m_lanScanPending||m_shuttingDown)return;m_lanScanPending=true;
    auto promise=std::make_shared<QPromise<QList<QNetworkInterface>>>();
    auto *watcher=new QFutureWatcher<QList<QNetworkInterface>>(this);
    connect(watcher,&QFutureWatcher<QList<QNetworkInterface>>::finished,this,[this,watcher]{
        m_interfaces=watcher->result();watcher->deleteLater();m_lanScanPending=false;
        QStringList addresses;for(const auto &iface:m_interfaces)for(const auto &entry:iface.addressEntries()){const auto address=entry.ip();if(address.protocol()==QAbstractSocket::IPv4Protocol&&!address.isLoopback()&&!address.isNull())addresses.append(address.toString());}
        if(addresses!=m_lanAddresses){m_lanAddresses=addresses;emit lanAddressesChanged();}
        emit interfacesChanged();
    });
    watcher->setFuture(promise->future());
    QThreadPool::globalInstance()->start([promise]{
        promise->start();promise->addResult(QNetworkInterface::allInterfaces());promise->finish();
    });
}
bool EngineController::configureLan(const QString &username,const QString &password) {
    if(!networkEditAllowed())return false;
    if(!QRegularExpression("^[A-Za-z0-9_.-]{1,64}$").match(username).hasMatch()||password.size()<8||password.size()>128||password.contains(QRegularExpression("[:\\r\\n]"))){
        m_networkError=QStringLiteral("用户名仅支持字母、数字、点和横线；密码需为 8 至 128 字符且不能包含冒号或换行。");emit optionsChanged();return false;
    }
    const auto oldUser=m_options.lanUsername,oldPassword=m_options.lanPassword;m_options.lanUsername=username;m_options.lanPassword=password;
    if(saveNetworkConfiguration())return true;m_options.lanUsername=oldUser;m_options.lanPassword=oldPassword;emit optionsChanged();return false;
}
bool EngineController::setLanEnabled(bool enabled) {
    m_networkError.clear();
    if(enabled){m_networkError=QStringLiteral("Rust Core 暂不支持局域网代理；地址和认证配置保持不变。");emit optionsChanged();return false;}
    if(enabled&&!lanConfigured()){m_networkError=QStringLiteral("请先设置局域网代理用户名和密码。");emit optionsChanged();return false;}
    if(busy()||nodeBusy()||routingBusy()){m_networkError=QStringLiteral("请先选择代理节点，并等待当前操作结束。");emit optionsChanged();return false;}
    const bool previous=m_options.allowLan;m_options.allowLan=enabled;if(!saveNetworkConfiguration()){m_options.allowLan=previous;return false;}
    if(enabled||processAlive())startConfiguredSession();
    emit statusChanged();return true;
}

bool EngineController::setGatewayForwarding(bool enabled) {
    if(enabled){m_routingError=QStringLiteral("Rust Core 暂不支持 TUN 网关转发；网关配置保持不变。");emit statusChanged();return false;}
    if(enabled&&m_options.meteredNetwork){m_routingError=QStringLiteral("请先关闭计费网络模式，再开启局域网网关。");emit statusChanged();return false;}
    if(enabled){if(m_options.gatewayForwarding)return true;m_tunBeforeGateway=m_options.tunEnabled;m_options.gatewayForwarding=true;
        if(setTunEnabled(true))return true;m_options.gatewayForwarding=false;return false;}
    if(!m_options.gatewayForwarding)return true;m_options.gatewayForwarding=false;m_options.tunEnabled=m_tunBeforeGateway;saveNetworkConfiguration();
    if(m_connectionRequested&&!m_store.selectedId().isEmpty()&&(processAlive()||busy())){m_systemProxy.disable();m_restartPending=true;m_engine->stop();}
    emit statusChanged();return true;
}

bool EngineController::configureMeteredAllowlist(const QStringList &processes) {
    if(busy()||nodeBusy()||routingBusy()){m_networkError=QStringLiteral("请等待网络操作结束。");emit optionsChanged();return false;}
    QStringList valid;
    for(const auto &value:processes){const auto name=value.trimmed();if(!QRegularExpression("^[A-Za-z0-9_. -]{1,128}\\.exe$").match(name).hasMatch()||valid.size()>=64){m_networkError=QStringLiteral("允许名单最多 64 项，每项填写 Windows 程序名，例如 chrome.exe。");emit optionsChanged();return false;}if(!valid.contains(name,Qt::CaseInsensitive))valid.append(name);}
    const auto previous=m_options.meteredAllowlist;m_options.meteredAllowlist=valid;
    if(!saveNetworkConfiguration()){m_options.meteredAllowlist=previous;return false;}
    if(m_options.meteredNetwork&&processAlive())startConfiguredSession();return true;
}
bool EngineController::setMeteredEnabled(bool enabled) {
    m_routingError.clear();
    if(enabled){m_routingError=QStringLiteral("Rust Core 暂不支持计费网络接管；允许名单和已有配置保持不变。");emit statusChanged();return false;}
    if(enabled==m_options.meteredNetwork)return true;
    if(busy()||nodeBusy()||routingBusy()||m_options.gatewayForwarding){m_routingError=QStringLiteral("请先停止网关并等待当前网络操作结束。");emit statusChanged();return false;}
    if(enabled&&!elevated()){m_routingError=QStringLiteral("计费网络模式需要管理员权限，以通过 TUN 接管程序网络。");emit statusChanged();return false;}
    const auto oldTun=m_options.tunEnabled;const auto oldMode=m_options.routingMode;
    if(enabled){m_tunBeforeMetered=oldTun;m_modeBeforeMetered=oldMode;m_options.tunEnabled=true;m_options.routingMode="rule";}
    else {m_options.tunEnabled=m_tunBeforeMetered;m_options.routingMode=m_modeBeforeMetered;}
    m_options.meteredNetwork=enabled;
    if(!saveNetworkConfiguration()){m_options.meteredNetwork=!enabled;m_options.tunEnabled=oldTun;m_options.routingMode=oldMode;return false;}
    m_meteredPending=enabled;m_meteredOldTun=oldTun;m_meteredOldMode=oldMode;
    if(enabled||processAlive())startConfiguredSession();emit statusChanged();return true;
}
