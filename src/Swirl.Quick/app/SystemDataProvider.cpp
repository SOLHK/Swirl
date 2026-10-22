#include "SystemDataProvider.h"
#include "DiagnosticService.h"
#include "network/CaptureService.h"
#include "engine/EngineController.h"
#include <QGuiApplication>
#include <QClipboard>
#include <QNetworkInterface>
#include <QDateTime>
#include <QUrl>
#include <QCoreApplication>
#include <QFile>
#include <QCryptographicHash>

SystemDataProvider::SystemDataProvider(CaptureService *capture,EngineController *engine,DiagnosticService *diagnostics):m_capture(capture),m_engine(engine),m_diagnostics(diagnostics) {
    connect(engine,&EngineController::interfacesChanged,this,[this]{++m_revision;emit dataChanged();});
    connect(capture,&CaptureService::sessionsChanged,this,[this]{++m_revision;emit dataChanged();});
    connect(diagnostics,&DiagnosticService::changed,this,[this]{++m_revision;emit dataChanged();});
    connect(engine,&EngineController::statusChanged,this,[this]{
        const auto state=m_engine->stateText()+" | "+m_engine->error()+" | "+m_engine->requestStateText()+" | "+m_engine->routingError();
        if(property("lastEngineState").toString()!=state){setProperty("lastEngineState",state);m_diagnostics->record(m_engine->error().isEmpty()&&m_engine->routingError().isEmpty()?"INFO":"ERROR","Engine",m_engine->errorCode(),state);}
        ++m_revision;emit dataChanged();
    });
    connect(engine,&EngineController::diagnostic,this,[this](const QString &module,const QString &code,const QString &message){m_diagnostics->record("ERROR",module,code,message);});
    connect(engine->telemetry(),&TelemetryService::diagnostic,this,[this](const QString &module,const QString &code,const QString &message){m_diagnostics->record("ERROR",module,code,message);});
    connect(engine->tests(),&NodeTestService::diagnostic,this,[this](const QString &code,const QString &message){m_diagnostics->record("ERROR","NodeTest",code,message);});
    connect(engine->imports(),&NodeImportService::changed,this,[this]{const auto message=m_engine->imports()->message();if(!message.isEmpty()&&property("lastSubscription").toString()!=message){setProperty("lastSubscription",message);const bool failed=message.contains(QStringLiteral("失败"))||message.contains(QStringLiteral("拒绝"))||message.contains(QStringLiteral("错误"));m_diagnostics->record(failed?"ERROR":"INFO","Subscription","Update",message);}});
    connect(engine->systemProxy(),&SystemProxySession::changed,this,[this]{const auto proxy=m_engine->systemProxy();const auto state=QString::number(proxy->enabled())+" | "+proxy->error();if(property("lastProxy").toString()!=state){setProperty("lastProxy",state);m_diagnostics->record(proxy->error().isEmpty()?"INFO":"ERROR","SystemProxy","WindowsState",state);}});
    connect(capture,&CaptureService::stateChanged,this,[this]{m_diagnostics->record(m_capture->error().isEmpty()?"INFO":"ERROR","Capture","Listener",m_capture->error().isEmpty()?(m_capture->running()?QStringLiteral("HTTP 抓包监听启动"):QStringLiteral("HTTP 抓包监听停止")):m_capture->error());});
}
int SystemDataProvider::eventCount() const { return m_diagnostics->eventCount(); }
QVariantList SystemDataProvider::logs() const { return m_diagnostics->records(); }
void SystemDataProvider::clearLogs() { m_diagnostics->clearView(); }
QVariantMap SystemDataProvider::diagnosticSnapshot() const {
    const auto t=m_engine->telemetry();
    const static auto executable=QCoreApplication::applicationFilePath();
    const static auto executableHash=[] {
        QFile binary(QCoreApplication::applicationFilePath());
        if(!binary.open(QIODevice::ReadOnly))return QString();
        QCryptographicHash hash(QCryptographicHash::Sha256);
        return hash.addData(&binary)?QString::fromLatin1(hash.result().toHex()):QString();
    }();
    return {{"engineState",m_engine->stateText()},{"engineError",m_engine->errorCode()},{"engineVersion",m_engine->version()},
        {"sourceSha",QStringLiteral(SWIRL_SOURCE_SHA)},{"executablePath",executable},{"executableSha256",executableHash},
        {"actualEngineType",m_engine->processAlive()?m_engine->engineKind():QStringLiteral("not-running")},{"engineProcessId",m_engine->processAlive()?m_engine->processId():QString()},
        {"apiHealthy",m_engine->apiHealthy()},{"processAlive",m_engine->processAlive()},{"routingMode",m_engine->routingMode()},
        {"systemProxyEnabled",m_engine->systemProxy()->enabled()},{"systemProxyOwned",m_engine->systemProxy()->owned()},
        {"systemProxyError",m_engine->systemProxy()->error()},{"networkType",currentNetwork().value("type")},
        {"trafficSampled",t->sampled()},{"connectionsSampled",t->connectionsSampled()},{"activeConnections",t->activeConnections()},
        {"activeProcesses",t->activeProcesses()},{"uploadRate",t->uploadRate()},{"downloadRate",t->downloadRate()},{"today",t->summary()},
        {"latencies",t->latencies()},{"storageError",t->storageError()},{"pendingEvents",m_diagnostics->eventCount()},
        {"loginAuthenticationVerified",false}};
}
QVariantMap SystemDataProvider::currentNetwork() const {
    for(const auto &iface:m_engine->networkInterfaces()) {
        const auto flags=iface.flags();
        if(!(flags&QNetworkInterface::IsUp) || !(flags&QNetworkInterface::IsRunning) || (flags&QNetworkInterface::IsLoopBack))continue;
        if(iface.type()!=QNetworkInterface::Wifi && iface.type()!=QNetworkInterface::Ethernet)continue;
        if(!iface.addressEntries().isEmpty())return {{"type",iface.type()==QNetworkInterface::Wifi?"Wi-Fi":"以太网"},{"name",iface.humanReadableName()}};
    }
    return {{"type","未连接"},{"name","无活动网络接口"}};
}
QVariantList SystemDataProvider::requests() const {
    auto result=m_capture->sessions();
    for(auto &value:result){auto row=value.toMap();row.insert("path",QUrl(row.value("url").toString()).path());row.insert("version","—");value=row;}
    return result;
}
QVariantList SystemDataProvider::nodes() const { return m_engine->nodes(); }
QVariantList SystemDataProvider::connections() const { return m_engine->connections(); }
bool SystemDataProvider::copyText(const QString &text) const { if(auto *clipboard=QGuiApplication::clipboard()){clipboard->setText(text);return true;}return false; }
