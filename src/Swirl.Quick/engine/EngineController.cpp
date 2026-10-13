#include "EngineController.h"
#include <QCoreApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaEnum>
#include <QTimer>

EngineController::EngineController(std::unique_ptr<ProxyEngine> engine, QObject *parent, QString storePath)
    : QObject(parent), m_engine(std::move(engine)), m_store(std::move(storePath)),m_imports(&m_store,this) {
    QFile manifest(QStringLiteral(":/engine/mihomo-manifest.json"));
    if (manifest.open(QIODevice::ReadOnly)) {
        const auto object = QJsonDocument::fromJson(manifest.readAll()).object();
        m_options.expectedSha256 = object.value(QStringLiteral("executableSha256")).toString().toLatin1();
        m_options.expectedVersion = object.value(QStringLiteral("version")).toString();
    }
    m_options.executablePath = QCoreApplication::applicationDirPath() + QStringLiteral("/core/mihomo.exe");
    connect(m_engine.get(), &ProxyEngine::statusChanged, this, &EngineController::statusChanged);
    connect(m_engine.get(), &ProxyEngine::telemetryChanged, this, &EngineController::telemetryChanged);
    connect(m_engine.get(), &ProxyEngine::statusChanged, this, &EngineController::telemetryChanged);
    connect(&m_store,&NodeStore::changed,this,&EngineController::nodesChanged);
    connect(&m_imports,&NodeImportService::changed,this,&EngineController::statusChanged);
    connect(&m_imports,&NodeImportService::nodesApplied,this,[this]{
        m_nodeError.clear();
        // A source refresh changes credentials/options too. Restart the owned
        // process with the new snapshot; never leave the UI ahead of the engine.
        if(m_connectionRequested && (processAlive() || busy())) {
            m_options.nodes=m_store.nodes();m_options.selectedNodeId=m_store.selectedId();
            m_restartPending=!m_options.selectedNodeId.isEmpty();
            if(!m_restartPending){m_connectionRequested=false;m_nodeError=QStringLiteral("更新移除了当前节点；已停止连接，请重新选择。");}
            m_engine->stop();
        }
        emit nodesChanged();
    });
    connect(m_engine.get(),&ProxyEngine::statusChanged,this,[this] {
        emit nodesChanged();
        if (m_restartPending && m_engine->status().state==ProxyEngine::State::Stopped) {
            m_restartPending=false;
            QTimer::singleShot(0,this,[this]{if(m_connectionRequested && !m_options.selectedNodeId.isEmpty())m_engine->start(m_options);});
        }
    });
    connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, m_engine.get(), &ProxyEngine::stop);
}
void EngineController::setExecutablePath(const QString &path) {
    if (!canStart() || m_options.executablePath == path) return;
    m_options.executablePath = path; emit optionsChanged();
}
void EngineController::setControlPort(int port) {
    if (!canStart() || port < 1 || port > 65535 || m_options.controlPort == port) return;
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
void EngineController::start() { if (canStart()) { m_connectionRequested=false;m_options.nodes=m_store.nodes(); m_options.selectedNodeId.clear(); m_engine->start(m_options); } }
void EngineController::stop() { m_connectionRequested=false;m_restartPending=false; m_options.selectedNodeId.clear(); m_engine->stop(); }
void EngineController::refresh() { m_engine->refresh(); }

QVariantList EngineController::nodes() const {
    auto rows=m_store.publicRows(); const auto status=m_engine->status();
    for (auto &value : rows) {
        auto row=value.toMap(); const bool active=processAlive() && row.value("id").toString()==status.selectedNodeId;
        row.insert("address",row.value("host").toString().isEmpty()?QStringLiteral("协议扩展配置"):row.value("host").toString()+":"+row.value("port").toString());
        row.insert("status",active?nodeStateText():QStringLiteral("未连接"));
        row.insert("latency",active && status.latencyMs>=0?QString::number(status.latencyMs):QStringLiteral("—"));
        value=row;
    }
    return rows;
}
QString EngineController::selectedNodeName() const {
    for (const auto &n:m_store.nodes()) if(n.id==m_store.selectedId())return n.name;
    return QStringLiteral("未选择节点");
}
QString EngineController::nodeStateText() const {
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
    if(nodeBusy())return false;
    if(processAlive()&&!activeNodeId().isEmpty()&&!apiHealthy()){m_nodeError=QStringLiteral("控制接口未就绪，不能切换节点。");emit nodesChanged();return false;}
    m_nodeError.clear();const bool ok=m_store.select(id);
    if(ok&&processAlive()&&!activeNodeId().isEmpty())m_engine->selectNode(id);
    emit nodesChanged();return ok;
}
void EngineController::connectNode(const QString &id) {
    if(id.isEmpty()){m_nodeError=QStringLiteral("请先添加并选择节点。");emit nodesChanged();return;}
    if(nodeBusy() || !chooseNode(id))return;
    if(processAlive() && !activeNodeId().isEmpty())return;
    m_connectionRequested=true;
    m_options.nodes=m_store.nodes();m_options.selectedNodeId=id;
    if(processAlive()){m_restartPending=true;m_engine->stop();}
    else m_engine->start(m_options);
}
void EngineController::testNode(const QUrl &url) { if(!nodeBusy())m_engine->probeNode(url); }
void EngineController::disconnectNode() { stop(); }
