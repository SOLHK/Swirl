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
#include <QHostAddress>
#include <QRegularExpression>
#include <QNetworkInterface>
#ifndef SWIRL_USE_RUST_CORE
#include <QTemporaryDir>
#include "MihomoAdapter.h"
#endif
#include <QFutureWatcher>
#include <QPromise>
#include <QThreadPool>
#ifdef SWIRL_USE_RUST_CORE
#include "RustCoreEngine.h"
#include "RustDnsConfiguration.h"
#endif
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif

namespace {
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
    m_options.autoControlPort=true;
    m_imports.setConfigurationApplier([this](const NodeImporter::Result &result,const QString &sourceId,bool nodesOnly,QString *error) {
        const auto &configuration=result.configurationFormat=="ini"?result.executionConfiguration:result.configuration;
        if(nodesOnly || result.configuration.isEmpty()) {
            NodeStore::ImportPlan plan;
            if(!m_store.prepareImport(result.nodes,sourceId,&plan)){*error=m_store.error();return false;}
#ifdef SWIRL_USE_RUST_CORE
            const auto nodes=plan.nodes();QVariantMap canonical;
            if(!validateNetworkConfiguration(networkConfigurationSnapshot(),&canonical,&nodes)){*error=m_networkError;return false;}
#endif
            auto retained=m_store.networkConfiguration();
            if(nodesOnly && retained.contains("importedConfiguration") &&
                retained.value("importedConfiguration").toObject().value("sourceId").toString()==sourceId) {
                auto provenance=retained.value("importedConfiguration").toObject();
                provenance.insert("policyRetainedAfterNodesOnlyRefresh",true);
                retained.insert("importedConfiguration",provenance);
            }
            if(!m_store.commitImport(plan,retained)){*error=m_store.error();return false;}
            return true;
        }
#ifndef SWIRL_USE_RUST_CORE
        *error=QStringLiteral("完整订阅事务当前仅在 Rust 模式提供；旧配置保持不变。");return false;
#else
        if(result.configurationFormat!="clash"&&(result.configurationFormat!="ini"||configuration.isEmpty())) {
            *error=QStringLiteral("此格式的完整配置尚未映射；未应用节点或全局配置，原有设置保持不变。");return false;
        }
        // First executable document profile: self-contained Clash groups/rules.
        // External DNS dialects and every other root semantic remain explicit
        // rejection rather than silently becoming Qt defaults or DIRECT.
        for(auto it=configuration.begin();it!=configuration.end();++it) {
            if(it.key()!="proxy-groups" && it.key()!="rules" && it.key()!="dns") {
                *error=QStringLiteral("完整订阅含尚未映射的全局配置；未应用节点或网络配置。");return false;
            }
        }
        if(configuration.contains("dns")) {
            *error=QStringLiteral("此订阅的 DNS 语义尚未映射到 Rust；未应用节点或网络配置。");return false;
        }
        if(configuration.contains("rules")) {
            if(!configuration["rules"].isArray()){*error=QStringLiteral("规则必须为字符串数组。");return false;}
            for(const auto &rule:configuration["rules"].toArray())if(!rule.isString()){*error=QStringLiteral("规则必须为字符串。");return false;}
        }
        const auto rules=configuration.value("rules").toArray();
        if(rules.isEmpty() || !rules.last().toString().trimmed().startsWith("MATCH,")) {
            *error=QStringLiteral("当前完整订阅档案要求显式末尾 MATCH 规则；未猜测默认出站策略。");return false;
        }
        const QVariantMap mapped{{"groups",configuration.value("proxy-groups").toVariant()},{"rules",configuration.value("rules").toVariant()}};
        auto input=mapped;if(!configuration.contains("proxy-groups"))input.remove("groups");if(!configuration.contains("rules"))input.remove("rules");
        if(!importNodesAndConfiguration(result.nodes,sourceId,input,result.configuration,result.configurationFormat)){*error=m_networkError;return false;}
        return true;
#endif
    });
    connect(m_engine.get(),&ProxyEngine::statusChanged,this,[this]{m_telemetry.ingest(m_engine->status());});
    connect(&m_telemetry,&TelemetryService::changed,this,&EngineController::statusChanged);
    connect(&m_tests,&NodeTestService::changed,this,&EngineController::nodesChanged);
    connect(m_engine.get(),&ProxyEngine::diagnostic,this,&EngineController::diagnostic);
#ifdef SWIRL_USE_RUST_CORE
    connect(m_engine.get(),&ProxyEngine::diagnostic,this,[this](const QString &module,const QString &code,const QString &message){
        if(module=="SwirlRust"&&(code=="SelectionUnsupported"||code=="SelectionFailed"))rollbackPendingSelection(message);
        if(module=="SwirlRust"&&(code=="RoutingUnsupported"||code=="RoutingFailed")){
            m_routingError=message;const auto actual=m_engine->status().mode;
            if(!actual.isEmpty()&&actual!=m_options.routingMode){m_options.routingMode=actual;m_options.directSession=actual=="direct";QSettings().setValue("Proxy/routingMode",actual);}
            emit statusChanged();
        }
    });
#endif
    connect(this,&EngineController::diagnostic,&m_diagnostics,[this](const QString &module,const QString &code,const QString &message){m_diagnostics.noteEvent(module+" / "+code,message);});
#ifndef SWIRL_USE_RUST_CORE
    QFile manifest(QStringLiteral(":/engine/mihomo-manifest.json"));
    if (manifest.open(QIODevice::ReadOnly)) {
        const auto object = QJsonDocument::fromJson(manifest.readAll()).object();
        m_options.expectedSha256 = object.value(QStringLiteral("executableSha256")).toString().toLatin1();
        m_options.expectedVersion = object.value(QStringLiteral("version")).toString();
    }
#endif
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
#ifndef SWIRL_USE_RUST_CORE
    m_options.rulesDirectory=QCoreApplication::applicationDirPath()+"/rules";
#endif
    QSettings settings;
    m_options.preferCompatibility=settings.value("Proxy/preferCompatibility",false).toBool();
    m_options.routingMode=settings.value("Proxy/routingMode","rule").toString();
    if(m_options.routingMode!="rule"&&m_options.routingMode!="global"&&m_options.routingMode!="direct")m_options.routingMode="rule";
    if(m_options.meteredNetwork)m_options.routingMode="rule";
    connect(m_engine.get(),&ProxyEngine::statusChanged,this,[this] {
        const int runtimePort=QUrl(m_engine->status().controlEndpoint).port();
        if(m_options.autoControlPort && runtimePort>0 && runtimePort!=m_options.controlPort){
            m_options.controlPort=quint16(runtimePort);emit optionsChanged();
        }
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
        m_imports.setDownloadProxy(s.processAlive?s.proxyPort:0);
        if(s.state==ProxyEngine::State::Stopping||s.state==ProxyEngine::State::Stopped||s.state==ProxyEngine::State::Failed) {
            m_systemProxy.disable();
            if(s.state==ProxyEngine::State::Failed)m_proxyRequested=false;
        } else if(s.state==ProxyEngine::State::Running&&s.apiHealthy&&m_proxyRequested&&!m_systemProxy.owned()&&!m_proxyChecking)setSystemProxy(true);
    });
    if(m_options.tunEnabled&&!elevated()){m_options.tunEnabled=false;m_options.meteredNetwork=false;m_routingError=QStringLiteral("增强模式需要管理员权限，本次启动保持关闭。");}
#ifndef SWIRL_USE_RUST_CORE
    m_options.executablePath = QCoreApplication::applicationDirPath() + QStringLiteral("/core/mihomo.exe");
#endif
    connect(m_engine.get(), &ProxyEngine::statusChanged, this, &EngineController::statusChanged);
    connect(&m_store,&NodeStore::changed,this,&EngineController::nodesChanged);
    connect(&m_store,&NodeStore::changed,this,&EngineController::nodeCatalogChanged);
    connect(&m_store,&NodeStore::selectionChanged,this,&EngineController::selectionChanged);
    connect(this,&EngineController::nodesChanged,this,&EngineController::selectionChanged);
    connect(&m_imports,&NodeImportService::changed,this,&EngineController::statusChanged);
    connect(&m_imports,&NodeImportService::nodesApplied,this,[this]{
        m_nodeError.clear();
        // A background subscription refresh must not interrupt live Codex/WS
        // streams. The current immutable engine snapshot lives until reconnect.
        if(m_connectionRequested && (processAlive() || busy())) {
            m_nodeError=QStringLiteral("节点库已更新；当前连接继续使用启动时配置。新增节点与凭据更新在手动断开重连后生效。");
            emit diagnostic("EngineController","SubscriptionUpdateDeferred",m_nodeError);
        }
        emit nodesChanged();
    });
    connect(m_engine.get(),&ProxyEngine::statusChanged,this,[this] {
        emit nodesChanged();
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
#ifdef SWIRL_USE_RUST_CORE
    m_options.smartRouting=m_smartRoutingEligible&&!m_nativeDocumentRouting&&m_options.customRules.isEmpty();
    m_options.nativePrivateRouting=m_smartRoutingEligible&&!m_nativeDocumentRouting&&!m_options.customRules.isEmpty();
#else
    m_options.smartRouting=m_smartRoutingEligible&&!m_nativeDocumentRouting;
    m_options.nativePrivateRouting=false;
#endif
}
QString EngineController::engineIdentityLabel() const {
    const auto status=m_engine->status();
    QString identity;
    if(status.processAlive) {
        if(status.engineKind==QStringLiteral("rust"))identity=QStringLiteral("Swirl Core");
        else if(status.engineKind==QStringLiteral("compatibility"))identity=QStringLiteral("Mihomo");
        else if(status.engineKind==QStringLiteral("native"))identity=QStringLiteral("Swirl C++ Native");
        else identity=QStringLiteral("未知内核");
    } else {
#ifdef SWIRL_USE_RUST_CORE
        identity=QStringLiteral("Swirl Core");
#else
        identity=QStringLiteral("Mihomo");
#endif
    }
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
void EngineController::setExecutablePath(const QString &path) {
    if (!canStart() || m_options.executablePath == path) return;
    m_options.executablePath = path; emit optionsChanged();
}
void EngineController::setControlPort(int port) {
    if (!canStart() || port < 1 || port > 65535) return;
    m_options.autoControlPort=false;
    m_options.controlPort = quint16(port); emit optionsChanged();
}
QString EngineController::stateText() const {
    switch (m_engine->status().state) {
    case ProxyEngine::State::Stopped: return QStringLiteral("已停止");
    case ProxyEngine::State::Validating: return QStringLiteral("正在校验");
    case ProxyEngine::State::Starting: return QStringLiteral("正在启动 · 等待认证 API");
    case ProxyEngine::State::Running: return QStringLiteral("进程运行 · 控制接口健康");
    case ProxyEngine::State::Degraded: return QStringLiteral("进程运行 · 控制接口异常");
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
void EngineController::start() { if (canStart()) { m_connectionRequested=false;m_options.nodes=m_store.nodes(); m_options.selectedNodeId.clear();m_options.directSession=false; m_engine->start(m_options); } }
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
        const auto measured=m_tests.result(id);
        QString nodeStatus=QStringLiteral("未测试");
        if(m_tests.testing(id))nodeStatus=QStringLiteral("测试中");
        else if(!measured.isEmpty())nodeStatus=measured.value("success").toBool()?QStringLiteral("可用"):
            measured.value("error").toString().contains("timeout",Qt::CaseInsensitive)||measured.value("error").toString().contains(QStringLiteral("超时"))?QStringLiteral("超时"):QStringLiteral("测试失败");
        if(m_connectionRequested&&m_options.selectedNodeId==id){
            if(status.state==ProxyEngine::State::Failed||status.requestState==ProxyEngine::RequestState::Failed||status.nodeHealth==ProxyEngine::NodeHealth::Unavailable)nodeStatus=QStringLiteral("连接失败");
            else if(active&&status.requestState==ProxyEngine::RequestState::Succeeded)nodeStatus=QStringLiteral("已连接");
            else if(busy()||status.nodeBusy)nodeStatus=QStringLiteral("正在连接");
            else if(active)nodeStatus=QStringLiteral("会话就绪 · 未验证");
        }
        row.insert("status",nodeStatus);
        row.insert("testAvailable",!m_tests.testing(id)&&measured.value("success").toBool());
#ifdef SWIRL_USE_RUST_CORE
        row.insert("latency",QStringLiteral("—"));
#else
        row.insert("latency",active && status.latencyMs>=0?QString::number(status.latencyMs):QStringLiteral("—"));
#endif
        if(!measured.isEmpty()){
            const auto sample=measured.value(measured.value("metricType")==QStringLiteral("http_headers")
                ?"outboundConnectMs":"latency");
            const auto elapsed=sample.isValid()?sample.toInt():-1;
            row.insert("latency",measured.value("success").toBool()&&elapsed>=0?QString::number(elapsed):QStringLiteral("失败"));
            row.insert("testHttp",measured.value("http"));row.insert("testError",measured.value("error"));
        }
        value=row;
    }
    return rows;
}
QString EngineController::selectedNodeName() const {
    for (const auto &n:m_store.nodes()) if(n.id==m_store.selectedId())return n.name;
    return QStringLiteral("未选择节点");
}
QString EngineController::nodeStateText() const {
    if (connected()&&m_engine->status().directSession)return QStringLiteral("直接连接");
    if (!processAlive() || activeNodeId().isEmpty())return QStringLiteral("未连接");
    switch(m_engine->status().nodeHealth) {
    case ProxyEngine::NodeHealth::Unknown:return QStringLiteral("已选择 · 未检测");
    case ProxyEngine::NodeHealth::Checking:return QStringLiteral("正在真实检测");
    case ProxyEngine::NodeHealth::Available:return QStringLiteral("节点可用");
    case ProxyEngine::NodeHealth::Unavailable:return QStringLiteral("节点检测失败");
    }
    return {};
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
void EngineController::setProxyPort(int port) { if(canStart() && port>0 && port<=65535 && port!=controlPort()){m_options.proxyPort=quint16(port);emit optionsChanged();} }
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
#ifdef SWIRL_USE_RUST_CORE
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
#endif
#ifdef SWIRL_USE_RUST_CORE
    if(active&&activeNodeId()!=id){
        m_previousSelection=activeNodeId();m_pendingSelection=id;
    }
#endif
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
#ifdef SWIRL_USE_RUST_CORE
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
#endif
    m_connectionRequested=true;
    m_options.nodes=m_store.nodes();m_options.selectedNodeId=id;m_options.directSession=false;
    if(processAlive()){m_restartPending=true;m_engine->stop();}
    else m_engine->start(m_options);
}
void EngineController::startConfiguredSession() {
    if(m_shuttingDown)return;
#ifdef SWIRL_USE_RUST_CORE
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
#endif
    m_nodeError.clear();
    m_connectionRequested=true;
    m_options.nodes=m_store.nodes();m_options.selectedNodeId=m_store.selectedId();
#ifdef SWIRL_USE_RUST_CORE
    m_options.directSession=m_options.routingMode=="direct";
#else
    m_options.directSession=m_options.selectedNodeId.isEmpty()&&!m_nativeDocumentRouting;
#endif
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
#ifdef SWIRL_USE_RUST_CORE
    if(processAlive()){
        auto candidate=m_options;candidate.routingMode=mode;candidate.directSession=mode=="direct";
        candidate.nodes=m_store.nodes();candidate.selectedNodeId=m_store.selectedId();
        QJsonObject configuration;const auto reason=RustCoreEngine::configuration(candidate,&configuration);
        if(!reason.isEmpty()){m_routingError=reason;emit statusChanged();return;}
    }
#endif
    m_routingError.clear();m_options.routingMode=mode;
#ifdef SWIRL_USE_RUST_CORE
    m_options.directSession=mode=="direct";
#endif
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
    if(!connected()&&m_store.selectedId().isEmpty()&&!busy()&&!m_imports.busy()){startConfiguredSession();return;}
    if(!s.processAlive||!s.apiHealthy||s.proxyPort<1||(!s.directSession&&s.selectedNodeId.isEmpty())||s.nodeHealth==ProxyEngine::NodeHealth::Unavailable){
        m_proxyRequested=false;m_routingError=QStringLiteral("请先连接可用节点，并等待引擎与控制接口健康。");emit statusChanged();return;}
    m_proxyChecking=true;
    auto socket=new QTcpSocket(this);socket->setProxy(QNetworkProxy::NoProxy);
    auto timer=new QTimer(socket);timer->setSingleShot(true);timer->start(1500);
    connect(socket,&QTcpSocket::connected,this,[this,socket,timer,s] {
        timer->stop();m_proxyChecking=false;socket->deleteLater();
        const auto now=m_engine->status();
        if(m_proxyRequested&&now.processAlive&&now.apiHealthy&&now.processId==s.processId&&now.proxyPort==s.proxyPort)
            if(!m_systemProxy.enable(m_captureProxyPort>0?m_captureProxyPort:s.proxyPort,s.processId))m_proxyRequested=false;
        emit statusChanged();
    });
    const auto failed=[this,socket,timer] {if(!m_proxyChecking)return;timer->stop();m_proxyChecking=false;m_proxyRequested=false;
        m_routingError=QStringLiteral("本机代理端口未监听，未修改 Windows 系统代理。");socket->deleteLater();emit statusChanged();};
    connect(timer,&QTimer::timeout,this,failed);
    connect(socket,&QTcpSocket::errorOccurred,this,[failed](QAbstractSocket::SocketError){failed();});
    socket->connectToHost(QHostAddress::LocalHost,quint16(m_captureProxyPort>0?m_captureProxyPort:s.proxyPort));
}
QString EngineController::proxyEnvironmentAdvice() const {
#ifdef SWIRL_USE_RUST_CORE
    return QStringLiteral("从新的 PowerShell 会话启动支持代理变量的应用：\n"
        "$env:HTTP_PROXY='http://127.0.0.1:%1'\n$env:HTTPS_PROXY='http://127.0.0.1:%1'\n"
        "$env:ALL_PROXY='http://127.0.0.1:%1'\n$env:NO_PROXY='localhost,127.0.0.1,::1'\n"
        "Codex 是否读取系统代理或这些变量取决于具体版本。完全退出后从该会话重新启动，已有进程不会自动继承。"
        "当前 Rust Core 构建不提供 TUN；忽略代理设置的应用无法通过本页接入。"
        "本页只提供建议，不写入环境变量、.codex 配置文件或密钥。").arg(m_options.proxyPort);
#else
    return QStringLiteral("从新的 PowerShell 会话启动支持代理变量的应用：\n"
        "$env:HTTP_PROXY='http://127.0.0.1:%1'\n$env:HTTPS_PROXY='http://127.0.0.1:%1'\n"
        "$env:ALL_PROXY='http://127.0.0.1:%1'\n$env:NO_PROXY='localhost,127.0.0.1,::1'\n"
        "Codex 是否读取系统代理或这些变量取决于具体版本。完全退出后从该会话重新启动，已有进程不会自动继承。"
        "忽略两者的应用请使用自身代理设置，或由用户主动开启现有 TUN 增强模式。"
        "本页只提供建议，不写入环境变量、.codex 配置文件或密钥。").arg(m_options.proxyPort);
#endif
}
void EngineController::setPreferCompatibility(bool enabled) {
#ifdef SWIRL_USE_RUST_CORE
    const auto unsupported=QStringLiteral("当前 Rust Core 构建不提供兼容引擎；请关闭已保存的旧偏好后重试。");
    if(enabled){m_routingError=unsupported;emit statusChanged();return;}
#endif
    if(!canStart()){m_routingError=QStringLiteral("请先断开当前连接，再修改引擎兼容设置。");emit statusChanged();return;}
    if(m_options.preferCompatibility==enabled)return;m_options.preferCompatibility=enabled;
    QSettings().setValue("Proxy/preferCompatibility",enabled);
#ifdef SWIRL_USE_RUST_CORE
    if(m_routingError==unsupported){m_routingError.clear();emit statusChanged();}
#endif
    emit optionsChanged();
}

bool EngineController::networkEditAllowed() {
    if(m_moduleOverlayActive){m_networkError=QStringLiteral("请先停用已启用的配置模块，再编辑基础网络配置。");emit optionsChanged();return false;}
    if(!canStart()){m_networkError=QStringLiteral("请先断开引擎，再修改 DNS、规则或策略组。");emit optionsChanged();return false;}
    m_networkError.clear();return true;
}

QVariantMap EngineController::networkConfigurationSnapshot() const {return {{"dns",m_options.dnsConfig},{"rules",m_options.customRules},{"groups",m_options.customGroups}};}
bool EngineController::validateNetworkConfiguration(const QVariantMap &input,QVariantMap *canonical,const QList<ProxyNode> *candidateNodes) {
    for(const auto &key:input.keys())if(!QStringList{"dns","rules","groups"}.contains(key)){m_networkError=QStringLiteral("不支持的配置覆盖字段：")+key;emit optionsChanged();return false;}
#ifdef SWIRL_USE_RUST_CORE
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
#else
    QTemporaryDir temporary;if(!temporary.isValid()){m_networkError=QStringLiteral("无法创建配置校验目录。");emit optionsChanged();return false;}
    const auto store=temporary.filePath("nodes.dpapi");
    if(candidateNodes){m_networkError=QStringLiteral("完整配置事务当前仅支持 Rust 模式。");return false;}
    if(QFile::exists(m_store.filePath())&&!QFile::copy(m_store.filePath(),store)){m_networkError=QStringLiteral("无法校验当前节点配置。");return false;}
    EngineController staged(std::make_unique<MihomoAdapter>(),nullptr,store);
    staged.m_options.dnsConfig.clear();staged.m_options.customRules.clear();staged.m_options.customGroups.clear();
    const auto reject=[&]{m_networkError=staged.networkConfigurationError();emit optionsChanged();return false;};
    const auto dns=input.value("dns").toMap();if(!dns.isEmpty()&&!staged.configureDns(dns))return reject();
    const auto groups=input.value("groups").toList();if(groups.size()>128){m_networkError=QStringLiteral("最多支持 128 个策略组。");emit optionsChanged();return false;}
    for(const auto &entry:groups){const auto group=entry.toMap();if(!staged.savePolicyGroup(group.value("name").toString(),group.value("type").toString(),group.value("proxies").toStringList()))return reject();}
    for(const auto &value:input.value("rules").toStringList()){const auto parts=value.split(',');
        if(parts.size()==2&&parts[0]=="MATCH"){if(!staged.saveRoutingRule("MATCH","",parts[1]))return reject();}
        else if(parts.size()==3){if(!staged.saveRoutingRule(parts[0],parts[1],parts[2]))return reject();}
        else {m_networkError=QStringLiteral("规则需要 类型,匹配值,策略 或 MATCH,策略。");emit optionsChanged();return false;}}
    if(canonical)*canonical=staged.networkConfigurationSnapshot();m_networkError.clear();return true;
#endif
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
#ifdef SWIRL_USE_RUST_CORE
    const auto error=RustCoreEngine::validateNetworkConfiguration(m_store.nodes(),m_options.dnsConfig,rules,groups,m_smartRoutingEligible&&!m_nativeDocumentRouting&&!rules.isEmpty());
    if(!error.isEmpty()){m_networkError=error;emit optionsChanged();return false;}
#endif
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
bool EngineController::importNodesAndConfiguration(const QList<ProxyNode> &incoming,const QString &sourceId,const QVariantMap &input,const QJsonObject &original,const QString &sourceFormat) {
#ifndef SWIRL_USE_RUST_CORE
    Q_UNUSED(incoming);Q_UNUSED(sourceId);Q_UNUSED(input);Q_UNUSED(original);Q_UNUSED(sourceFormat);
    m_networkError=QStringLiteral("完整订阅事务当前仅在 Rust 模式提供。");return false;
#else
    // Only this owner may apply while its importer is busy. Existing active
    // sessions and module overlays must never be reconfigured underneath them.
    if(m_shuttingDown || busy() || processAlive() || m_moduleOverlayActive) {
        m_networkError=QStringLiteral("请先断开引擎并停用模块，再导入完整网络配置。");return false;
    }
    NodeStore::ImportPlan plan;
    if(!m_store.prepareImport(incoming,sourceId,&plan)){m_networkError=m_store.error();return false;}
    auto mapped=input;
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
    const auto previous=networkConfigurationSnapshot();const bool previousNative=m_nativeDocumentRouting,previousSmart=m_options.smartRouting,previousPrivate=m_options.nativePrivateRouting;
    if(!original.isEmpty()){m_nativeDocumentRouting=true;m_options.smartRouting=false;m_options.nativePrivateRouting=false;}
    m_options.dnsConfig=canonical.value("dns").toMap();m_options.customRules=canonical.value("rules").toStringList();m_options.customGroups=canonical.value("groups").toList();
    auto snapshot=serializedNetworkConfiguration();
    if(!snapshot.isEmpty() && !original.isEmpty())snapshot.insert("importedConfiguration",QJsonObject{{"format",sourceFormat},{"sourceId",sourceId},{"configuration",original}});
    if(snapshot.isEmpty() || !m_store.commitImport(plan,snapshot)) {
        if(!snapshot.isEmpty())m_networkError=m_store.error();
        m_nativeDocumentRouting=previousNative;m_options.smartRouting=previousSmart;m_options.nativePrivateRouting=previousPrivate;
        m_options.dnsConfig=previous.value("dns").toMap();m_options.customRules=previous.value("rules").toStringList();m_options.customGroups=previous.value("groups").toList();emit optionsChanged();return false;
    }
    m_networkError.clear();emit optionsChanged();emit statusChanged();return true;
#endif
}
bool EngineController::configureDns(const QVariantMap &input) {
    if(!networkEditAllowed())return false;
#ifdef SWIRL_USE_RUST_CORE
    // The existing settings page sends its visible fields only. Preserve an
    // imported query policy unless the caller explicitly supplies a replacement.
    auto requested=input;
    if(!requested.contains("queryFamily") && m_options.dnsConfig.contains("queryFamily"))
        requested.insert("queryFamily",m_options.dnsConfig.value("queryFamily"));
    QJsonObject validatedDns;const auto error=SwirlRustDns::configuration(requested,&validatedDns);
    if(!error.isEmpty()){m_networkError=error;emit optionsChanged();return false;}
#else
    if(input.contains("queryFamily") || m_options.dnsConfig.contains("queryFamily")){m_networkError=QStringLiteral("当前兼容内核不能执行已保存的 DNS 查询策略，请使用 Rust 内核。");emit optionsChanged();return false;}
#endif
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
#ifdef SWIRL_USE_RUST_CORE
    if(requested.contains("queryFamily"))m_options.dnsConfig.insert("queryFamily",requested.value("queryFamily"));
#endif
    if(saveNetworkConfiguration())return true;m_options.dnsConfig=before;emit optionsChanged();return false;
}
bool EngineController::saveRoutingRule(const QString &type,const QString &pattern,const QString &policy,int index) {
    if(!networkEditAllowed())return false;
    const QStringList types={"DOMAIN","DOMAIN-SUFFIX","DOMAIN-KEYWORD","IP-CIDR","IP-CIDR6","PROCESS-NAME","DST-PORT","SRC-IP-CIDR","MATCH"};
    bool valid=types.contains(type)&&pattern.size()<=2048&&!pattern.contains(QRegularExpression("[,\\r\\n]"));
    QStringList policies={"DIRECT","REJECT","SWIRL"};for(const auto &g:m_options.customGroups)policies.append(g.toMap().value("name").toString());
#ifdef SWIRL_USE_RUST_CORE
    for(const auto &node:m_store.nodes())policies.append(node.id);
#endif
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
#ifdef SWIRL_USE_RUST_CORE
    // The existing editor edits name/type/members only; keep stored options it
    // cannot display, and reject incompatible combinations instead of erasing.
    if(position>=0){group=groups[position].toMap();group["type"]=type;group["proxies"]=members;}
#else
    QStringList available={"DIRECT","REJECT"};for(const auto &node:m_store.nodes())available.append(node.id);
    for(const auto &member:members)if(!available.contains(member)){m_networkError=QStringLiteral("策略组包含不存在的节点。");emit optionsChanged();return false;}
#endif
    if(position>=0)groups[position]=group;else groups.append(group);
    return commitRoutingConfiguration(m_options.customRules,groups);
}
bool EngineController::removePolicyGroup(const QString &name) {
    if(!networkEditAllowed())return false;
    for(const auto &rule:m_options.customRules) {
        const auto fields=routingRuleFields(rule);
        if(fields.value(routingRuleTargetIndex(fields))==name){m_networkError=QStringLiteral("请先删除引用此策略组的规则。");emit optionsChanged();return false;}
    }
#ifdef SWIRL_USE_RUST_CORE
    for(const auto &value:m_options.customGroups){const auto group=value.toMap();if(group.value("name")!=name&&group.value("proxies").toStringList().contains(name)){m_networkError=QStringLiteral("请先移除其他策略组对此组的引用。");emit optionsChanged();return false;}}
#endif
    auto groups=m_options.customGroups;
    for(int i=groups.size()-1;i>=0;--i)if(groups[i].toMap().value("name")==name)groups.removeAt(i);
    return commitRoutingConfiguration(m_options.customRules,groups);
}
QVariantList EngineController::routingRules() const {
    if(processAlive())return m_engine->routingRules();
#ifdef SWIRL_USE_RUST_CORE
    auto preview=m_options;preview.routingMode="rule";preview.directSession=false;
    return RustCoreEngine::routingRulesForOptions(preview);
#endif
    QVariantList rows;int order=0;
    for(const auto &line:m_options.customRules){const auto parts=routingRuleFields(line);const bool match=parts.value(0)=="MATCH";
        rows.append(QVariantMap{{"id",QString::number(order)},{"order",order},{"customIndex",order},{"type",match?"FINAL":parts.value(0)},{"pattern",match?"":parts.value(1)},{"policy",parts.value(routingRuleTargetIndex(parts))},{"hits","—"}});++order;}
    rows.append(QVariantMap{{"id","final"},{"order",order},{"type","FINAL"},{"pattern",""},{"policy","DIRECT"},{"hits","—"}});
    return rows;
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
    if(enabled&&!lanConfigured()){m_networkError=QStringLiteral("请先设置局域网代理用户名和密码。");emit optionsChanged();return false;}
    if(busy()||nodeBusy()||routingBusy()){m_networkError=QStringLiteral("请先选择代理节点，并等待当前操作结束。");emit optionsChanged();return false;}
    const bool previous=m_options.allowLan;m_options.allowLan=enabled;if(!saveNetworkConfiguration()){m_options.allowLan=previous;return false;}
    if(enabled||processAlive())startConfiguredSession();
    emit statusChanged();return true;
}

bool EngineController::setGatewayForwarding(bool enabled) {
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
    m_routingError.clear();if(enabled==m_options.meteredNetwork)return true;
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
