#include "GatewayService.h"
#include "GatewayRouting.h"
#include "engine/EngineController.h"
#include <QNetworkInterface>
#include <QStandardPaths>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QSaveFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QCoreApplication>
#include <QUuid>
#include <QRegularExpression>
#ifdef Q_OS_WIN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <iphlpapi.h>
#include <netioapi.h>
#endif
namespace {
bool isWan(int index){
#ifdef Q_OS_WIN
    PMIB_IPFORWARD_TABLE2 table=nullptr;if(GetIpForwardTable2(AF_INET,&table)!=NO_ERROR)return true;bool wan=false;
    for(ULONG i=0;i<table->NumEntries;++i)if(table->Table[i].InterfaceIndex==ULONG(index)&&table->Table[i].DestinationPrefix.PrefixLength==0)wan=true;FreeMibTable(table);return wan;
#else
    Q_UNUSED(index);return true;
#endif
}
QString csv(QString value){return '"'+value.replace('"',"\"\"")+'"';}
}
GatewayService::GatewayService(EngineController *engine,QString path,QObject *parent):QObject(parent),m_engine(engine),m_path(std::move(path)),m_dhcp(false,this) {
    connect(engine,&EngineController::interfacesChanged,this,&GatewayService::interfacesChanged);
    if(m_path.isEmpty())m_path=QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/gateway.json";
    m_journal=m_path+".forwarding";m_dhcp.setLeaseStorePath(m_path+".leases");loadConfiguration();
    connect(&m_dhcp,&DhcpServer::changed,this,[this]{if(m_forwarding&&!m_dhcp.running()&&!busy()){m_error=m_dhcp.error();stop();}emit changed();});
    connect(&m_process,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this](int code,QProcess::ExitStatus){processFinished(code);});
    connect(&m_process,&QProcess::errorOccurred,this,[this](QProcess::ProcessError error){if(error==QProcess::FailedToStart){m_error=QStringLiteral("Windows 转发辅助进程无法启动。");processFinished(-1);}});
    connect(m_engine->telemetry(),&TelemetryService::changed,this,&GatewayService::changed);
    m_deadline.setSingleShot(true);connect(&m_deadline,&QTimer::timeout,this,[this]{m_error=QStringLiteral("Windows 转发操作超时；恢复记录已保留。");if(m_process.state()!=QProcess::NotRunning)m_process.kill();else {m_phase=Phase::Idle;m_engine->setGatewayForwarding(false);emit changed();}});
    connect(m_engine,&EngineController::statusChanged,this,[this]{if(m_phase==Phase::WaitingTun){if(m_engine->gatewayForwardingReady())startForwarding();else if(!m_engine->busy()&&!m_engine->processAlive()){m_deadline.stop();m_phase=Phase::Idle;m_error=m_engine->error();m_engine->setGatewayForwarding(false);emit changed();}}
        else if(m_forwarding&&!m_engine->tunEnabled()&&!busy())stop();});
}
GatewayService::~GatewayService(){m_deadline.stop();QObject::disconnect(&m_dhcp,nullptr,this,nullptr);QObject::disconnect(&m_process,nullptr,this,nullptr);QObject::disconnect(m_engine,nullptr,this,nullptr);m_dhcp.stop();if(m_process.state()!=QProcess::NotRunning){if(!m_process.waitForFinished(m_shutdown?1000:35000)){m_process.kill();m_process.waitForFinished(2000);}}
    if(recoveryNeeded())GatewayRouting::cleanup(m_journal);m_engine->setGatewayForwarding(false);}
bool GatewayService::recoveryNeeded() const {return QFileInfo::exists(m_journal);}
QVariantList GatewayService::devices() const {auto rows=m_dhcp.leases();const auto traffic=m_engine->telemetry()->ranking("devices",0,512);
    for(auto &value:rows){auto row=value.toMap();row["total"]=0;row["speed"]=0;row["upload"]="0 B";row["download"]="0 B";row["speedText"]="0 B/s";
        for(const auto &entry:traffic){const auto measured=entry.toMap();if(measured.value("name")==row.value("ip"))for(const auto &key:{"total","speed","upload","download","speedText"})row[key]=measured.value(key);}value=row;}return rows;}
QVariantMap GatewayService::configuration() const {return {{"interfaceIndex",m_config.interfaceIndex},{"gateway",m_config.gateway.toString()},{"prefix",m_config.prefix},{"first",m_config.first.toString()},{"last",m_config.last.toString()},{"dns",m_config.dns.toString()},{"leaseSeconds",m_config.leaseSeconds}};}
QVariantList GatewayService::interfaces() const {QVariantList rows;for(const auto &iface:m_engine->networkInterfaces())if(iface.flags().testFlag(QNetworkInterface::IsUp)&&!iface.flags().testFlag(QNetworkInterface::IsLoopBack)&&iface.humanReadableName().compare("Swirl",Qt::CaseInsensitive)&&!isWan(iface.index()))for(const auto &entry:iface.addressEntries())if(entry.ip().protocol()==QAbstractSocket::IPv4Protocol&&!entry.ip().isLinkLocal())rows.append(QVariantMap{{"id",iface.index()},{"index",iface.index()},{"name",iface.humanReadableName()},{"ip",entry.ip().toString()},{"prefix",entry.prefixLength()},{"label",iface.humanReadableName()+" · "+entry.ip().toString()}});return rows;}
bool GatewayService::configure(const QVariantMap &input) {
    if(running()||busy()||recoveryNeeded()){m_error=QStringLiteral("请先停止或恢复现有网关，再修改配置。");emit changed();return false;}
    DhcpServer::Config next{QHostAddress(input.value("gateway").toString()),QHostAddress(input.value("first").toString()),QHostAddress(input.value("last").toString()),QHostAddress(input.value("dns").toString()),input.value("prefix",24).toInt(),input.value("interfaceIndex").toInt(),input.value("leaseSeconds",3600).toInt()};
    if(!input.value("dedicatedLan").toBool()||!DhcpServer::validate(next,&m_error)){if(m_error.isEmpty())m_error=QStringLiteral("请选择已有静态 IPv4 地址的专用 LAN 接口，并确认已关闭该网络的其他 DHCP 服务。");emit changed();return false;}
    if(next.interfaceIndex<=0||isWan(next.interfaceIndex)){m_error=QStringLiteral("网关需要独立的 LAN 接口，不能使用当前系统默认上网接口。");emit changed();return false;}
    const auto old=m_config;const auto wasConfigured=m_configured;m_config=next;
    if(!m_dhcp.configure(next)){m_config=old;m_error=m_dhcp.error();emit changed();return false;}
    m_configured=true;if(!saveConfiguration()){m_config=old;m_configured=wasConfigured;m_dhcp.configure(old);return false;}m_error.clear();emit changed();return true;
}
bool GatewayService::saveConfiguration(){QDir().mkpath(QFileInfo(m_path).absolutePath());QSaveFile file(m_path);const auto bytes=QJsonDocument(QJsonObject{{"schema",1},{"config",QJsonObject::fromVariantMap(configuration())},{"reservations",QJsonArray::fromVariantList(m_dhcp.reservations())}}).toJson();
    if(!file.open(QIODevice::WriteOnly)||file.write(bytes)!=bytes.size()||!file.commit()){m_error=QStringLiteral("网关配置保存失败。");emit changed();return false;}return true;}
void GatewayService::loadConfiguration(){QFile file(m_path);if(!file.open(QIODevice::ReadOnly)||file.size()>1024*1024)return;const auto document=QJsonDocument::fromJson(file.readAll()).object();if(document.value("schema").toInt()!=1)return;const auto input=document.value("config").toObject();
    m_config={QHostAddress(input.value("gateway").toString()),QHostAddress(input.value("first").toString()),QHostAddress(input.value("last").toString()),QHostAddress(input.value("dns").toString()),input.value("prefix").toInt(),input.value("interfaceIndex").toInt(),input.value("leaseSeconds").toInt()};
    m_configured=m_dhcp.configure(m_config);for(const auto &entry:document.value("reservations").toArray()){const auto row=entry.toObject();if(!m_dhcp.reserve(row.value("mac").toString(),row.value("ip").toString(),row.value("name").toString())){m_error=m_dhcp.error();m_configured=false;break;}}}

bool GatewayService::start() {
    if(running())return true;if(busy())return false;
    if(!m_configured||recoveryNeeded()||!m_engine->elevated()){m_error=!m_configured?QStringLiteral("请先配置专用 LAN、地址池和 DNS。"):recoveryNeeded()?QStringLiteral("请先恢复上次保留的接口转发状态。"):QStringLiteral("网关需要以管理员身份运行 Swirl。");emit changed();return false;}
    if(isWan(m_config.interfaceIndex)){m_error=QStringLiteral("所选 LAN 已成为系统默认上网接口，无法开启网关。");emit changed();return false;}
    m_error.clear();m_stopping=false;m_phase=Phase::WaitingTun;m_deadline.start(30000);emit changed();
    if(!m_engine->setGatewayForwarding(true)){m_deadline.stop();m_phase=Phase::Idle;m_error=m_engine->routingError();emit changed();return false;}
    if(m_engine->gatewayForwardingReady())startForwarding();return true;
}
void GatewayService::startForwarding() {
    if(m_phase!=Phase::WaitingTun)return;int tunIndex=0;for(const auto &iface:QNetworkInterface::allInterfaces())if(!iface.humanReadableName().compare("Swirl",Qt::CaseInsensitive)&&iface.flags().testFlag(QNetworkInterface::IsUp))tunIndex=iface.index();
    const auto guardPath=QCoreApplication::applicationDirPath()+"/SwirlGatewayGuard.exe";
    if(tunIndex<=0||!QFileInfo::exists(guardPath)){m_error=QStringLiteral("Swirl TUN 接口或网关恢复守护程序不可用。");m_phase=Phase::Idle;m_deadline.stop();m_engine->setGatewayForwarding(false);emit changed();return;}
#ifdef Q_OS_WIN
    FILETIME created{},exited{},kernel{},user{};if(!GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user)){m_error=QStringLiteral("无法建立网关进程身份。");m_phase=Phase::Idle;m_engine->setGatewayForwarding(false);emit changed();return;}
    const quint64 creation=(quint64(created.dwHighDateTime)<<32)|created.dwLowDateTime;
    const auto subnet=QHostAddress::parseSubnet(m_config.gateway.toString()+"/"+QString::number(m_config.prefix));
    QJsonObject journal{{"schema",1},{"name","SwirlGateway-"+QUuid::createUuid().toString(QUuid::Id128)},{"prefix",subnet.first.toString()+"/"+QString::number(subnet.second)},{"gateway",m_config.gateway.toString()},{"lanIndex",m_config.interfaceIndex},{"tunIndex",tunIndex},{"ownerPid",double(QCoreApplication::applicationPid())},{"ownerCreation",QString::number(creation)},{"phase","pending"}};
    QDir().mkpath(QFileInfo(m_journal).absolutePath());QSaveFile file(m_journal);const auto bytes=QJsonDocument(journal).toJson(QJsonDocument::Compact);
    if(!file.open(QIODevice::WriteOnly)||file.write(bytes)!=bytes.size()||!file.commit()){m_error=QStringLiteral("转发恢复记录无法保存，未修改接口。");m_phase=Phase::Idle;m_engine->setGatewayForwarding(false);emit changed();return;}
    if(!QProcess::startDetached(guardPath,{m_journal})){m_error=QStringLiteral("恢复守护程序无法启动，未修改接口。");QFile::remove(m_journal);m_phase=Phase::Idle;m_engine->setGatewayForwarding(false);emit changed();return;}
    m_phase=Phase::Starting;m_deadline.start(35000);GatewayRouting::prepareProcess(m_process,GatewayRouting::startScript(m_journal));m_process.start();emit changed();
#endif
}
void GatewayService::processFinished(int code) {
    m_deadline.stop();if(m_phase==Phase::Starting){
        if(code==0&&!m_stopping){m_forwarding=true;if(m_dhcp.start(m_config)){m_phase=Phase::Idle;emit changed();return;}m_error=m_dhcp.error();}
        else if(m_error.isEmpty())m_error=QStringLiteral("Windows 转发启动失败：")+QString::fromUtf8(m_process.readAllStandardError().left(2048));
        runCleanup();return;
    }
    if(m_phase==Phase::Stopping){m_forwarding=false;m_phase=Phase::Idle;if(code!=0)m_error=QStringLiteral("接口转发恢复失败，恢复记录已保留：")+QString::fromUtf8(m_process.readAllStandardError().left(2048));m_engine->setGatewayForwarding(false);emit changed();}
}
void GatewayService::runCleanup(){if(m_shutdownExpired){m_phase=Phase::Idle;m_forwarding=false;return;}m_phase=Phase::Stopping;m_dhcp.stop();if(!recoveryNeeded()){m_forwarding=false;m_phase=Phase::Idle;m_engine->setGatewayForwarding(false);emit changed();return;}
    QFile journal(m_journal);if(!journal.open(QIODevice::ReadOnly)||journal.size()>16384||!GatewayRouting::validJournal(QJsonDocument::fromJson(journal.readAll()).object())){m_phase=Phase::Idle;m_forwarding=false;m_error=QStringLiteral("转发恢复记录无效，已停止 DHCP 并保留记录，未自动修改接口。");m_engine->setGatewayForwarding(false);emit changed();return;}journal.close();
    m_deadline.start(50000);GatewayRouting::prepareProcess(m_process,GatewayRouting::cleanupScript(m_journal));m_process.start();emit changed();}
void GatewayService::shutdown(){
    m_shutdown=true;stop();
    QTimer::singleShot(6500,this,[this]{
        m_shutdownExpired=true;
        if(m_process.state()!=QProcess::NotRunning){
            m_error=QStringLiteral("退出时网关清理超时；恢复记录已保留。");
            m_process.kill();
        }
    });
}
void GatewayService::stop(){if(m_phase==Phase::Starting){m_stopping=true;emit changed();return;}if(m_phase==Phase::Stopping)return;if(m_phase==Phase::WaitingTun){m_deadline.stop();m_phase=Phase::Idle;m_engine->setGatewayForwarding(false);emit changed();return;}runCleanup();}
bool GatewayService::recover(){if(busy()||running())return false;if(!m_engine->elevated()){m_error=QStringLiteral("恢复接口状态需要管理员权限。");emit changed();return false;}m_error.clear();runCleanup();return true;}
bool GatewayService::exportClients(const QUrl &destination){if(!destination.isLocalFile())return false;QByteArray bytes="MAC,IP,Name\r\n";auto rows=m_dhcp.reservations();for(const auto &lease:m_dhcp.leases()){const auto row=lease.toMap();bool exists=false;for(const auto &entry:rows)if(entry.toMap().value("mac")==row.value("mac"))exists=true;if(!exists)rows.append(row);}
    for(const auto &entry:rows){const auto row=entry.toMap();bytes+=(csv(row.value("mac").toString())+","+csv(row.value("ip").toString())+","+csv(row.value("name").toString())+"\r\n").toUtf8();}
    QSaveFile file(destination.toLocalFile());if(!file.open(QIODevice::WriteOnly)||file.write(bytes)!=bytes.size()||!file.commit()){m_error=QStringLiteral("客户端 CSV 导出失败。");emit changed();return false;}return true;}
bool GatewayService::importClients(const QUrl &source){if(busy()||running()||!m_configured||!source.isLocalFile()){m_error=QStringLiteral("请先配置并停止网关，再导入客户端 CSV。");emit changed();return false;}QFile file(source.toLocalFile());if(!file.open(QIODevice::ReadOnly)||file.size()>512*1024){m_error=QStringLiteral("CSV 无法读取或超过 512 KB。");emit changed();return false;}
    auto text=QString::fromUtf8(file.readAll());if(text.startsWith(QChar(0xfeff)))text.remove(0,1);QList<QStringList> lines;QStringList row;QString field;bool quoted=false;
    for(int i=0;i<text.size();++i){const auto c=text[i];if(c=='"'){if(quoted&&i+1<text.size()&&text[i+1]=='"'){field+='"';++i;}else quoted=!quoted;}else if(c==','&&!quoted){row.append(field);field.clear();}else if(c=='\n'&&!quoted){row.append(field.trimmed());if(!row.join("").isEmpty())lines.append(row);row.clear();field.clear();}else if(c!='\r')field+=c;}
    if(!field.isEmpty()||!row.isEmpty()){row.append(field.trimmed());lines.append(row);}if(quoted||lines.isEmpty()||lines.takeFirst()!=QStringList{"MAC","IP","Name"}||lines.size()>512){m_error=QStringLiteral("CSV 需要 MAC,IP,Name 表头和有效引号。");emit changed();return false;}
    QVariantList reservations;for(const auto &line:lines){if(line.size()!=3){m_error=QStringLiteral("CSV 每行需要三列。");emit changed();return false;}reservations.append(QVariantMap{{"mac",line[0]},{"ip",line[1]},{"name",line[2]}});}
    const auto before=m_dhcp.reservations();if(!m_dhcp.replaceReservations(reservations)){m_error=m_dhcp.error();emit changed();return false;}if(!saveConfiguration()){m_dhcp.replaceReservations(before);return false;}m_error.clear();emit changed();return true;
}
