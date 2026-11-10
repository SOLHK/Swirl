#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#endif
#include "DhcpServer.h"
#include <QNetworkDatagram>
#include <QNetworkInterface>
#include <QNetworkProxy>
#include <QDateTime>
#include <QRegularExpression>
#include <QtEndian>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QSaveFile>
#include <QSet>
#include <algorithm>
#include <cmath>
namespace {
quint32 number(const QByteArray &bytes,int offset=0){return offset+4<=bytes.size()?qFromBigEndian<quint32>(reinterpret_cast<const uchar *>(bytes.constData()+offset)):0;}
QByteArray address(quint32 value){QByteArray bytes(4,Qt::Uninitialized);qToBigEndian(value,reinterpret_cast<uchar *>(bytes.data()));return bytes;}
QByteArray option(int key,const QByteArray &value){return QByteArray(1,char(key))+QByteArray(1,char(value.size()))+value;}
qint64 now(){return QDateTime::currentSecsSinceEpoch();}
bool optionsFrom(const QByteArray &packet,QHash<int,QByteArray> &options){
    if(packet.size()<240||packet.size()>1500||packet.mid(236,4)!=QByteArray::fromHex("63825363"))return false;
    for(int offset=240;offset<packet.size();){
        const int key=uchar(packet[offset++]);
        if(key==255)return true;
        if(key==0)continue;
        if(offset>=packet.size())return false;
        const int size=uchar(packet[offset++]);
        if(offset+size>packet.size()||options.contains(key))return false;
        options.insert(key,packet.mid(offset,size));offset+=size;
    }
    return false;
}
bool cleanName(const QString &name){return name.size()<=63&&std::none_of(name.cbegin(),name.cend(),[](QChar c){return c.unicode()<32||c.unicode()==127;});}
bool jsonTime(const QJsonValue &value,qint64 &result){
    if(!value.isDouble())return false;
    const auto number=value.toDouble();
    if(!std::isfinite(number)||number<0||number>9007199254740991.0||std::trunc(number)!=number)return false;
    result=qint64(number);return true;
}
}
DhcpServer::DhcpServer(bool isolated,QObject *parent):QObject(parent),m_isolated(isolated) {
    m_socket.setProxy(QNetworkProxy::NoProxy);connect(&m_socket,&QUdpSocket::readyRead,this,&DhcpServer::receive);
    m_expiry.setInterval(10000);connect(&m_expiry,&QTimer::timeout,this,&DhcpServer::expire);
    m_rateClock.start();
}
DhcpServer::~DhcpServer(){
    m_expiry.stop();m_socket.close();
#ifdef Q_OS_WIN
    if(m_nativeWinsock)WSACleanup();
#endif
}
bool DhcpServer::bindProductionSocket(){
#ifdef Q_OS_WIN
    WSADATA data{};
    if(WSAStartup(MAKEWORD(2,2),&data)!=0){m_error=QStringLiteral("DHCP Winsock 初始化失败。");return false;}
    m_nativeWinsock=true;
    const auto socket=WSASocketW(AF_INET,SOCK_DGRAM,IPPROTO_UDP,nullptr,0,WSA_FLAG_OVERLAPPED);
    const auto failed=[&](const QString &message){
        const int code=WSAGetLastError();if(socket!=INVALID_SOCKET)closesocket(socket);
        WSACleanup();m_nativeWinsock=false;m_error=message+QString::number(code);return false;
    };
    if(socket==INVALID_SOCKET)return failed(QStringLiteral("DHCP UDP socket 创建失败："));
    const DWORD enabled=1,index=DWORD(m_config.interfaceIndex),outgoing=htonl(index);
    // The wildcard address is necessary for an unconfigured client's DHCP
    // broadcast. Restrict kernel reception BEFORE bind, then verify the exact
    // list; application-level packet-info checks below remain an extra guard.
    if(setsockopt(socket,SOL_SOCKET,SO_EXCLUSIVEADDRUSE,reinterpret_cast<const char *>(&enabled),sizeof(enabled))!=0
       ||setsockopt(socket,SOL_SOCKET,SO_BROADCAST,reinterpret_cast<const char *>(&enabled),sizeof(enabled))!=0
       ||setsockopt(socket,IPPROTO_IP,IP_PKTINFO,reinterpret_cast<const char *>(&enabled),sizeof(enabled))!=0
       ||setsockopt(socket,IPPROTO_IP,IP_IFLIST,reinterpret_cast<const char *>(&enabled),sizeof(enabled))!=0
       ||setsockopt(socket,IPPROTO_IP,IP_ADD_IFLIST,reinterpret_cast<const char *>(&index),sizeof(index))!=0
       ||setsockopt(socket,IPPROTO_IP,IP_UNICAST_IF,reinterpret_cast<const char *>(&outgoing),sizeof(outgoing))!=0)
        return failed(QStringLiteral("DHCP 无法限制到专用 LAN 接口："));
    DWORD actualEnabled=0,actualInterface=0,actualOutgoing=0;
    int length=sizeof(actualEnabled);
    if(getsockopt(socket,IPPROTO_IP,IP_IFLIST,reinterpret_cast<char *>(&actualEnabled),&length)!=0||length!=sizeof(actualEnabled)||actualEnabled!=1)
        return failed(QStringLiteral("DHCP 接口限制验证失败："));
    length=sizeof(actualInterface);
    if(getsockopt(socket,IPPROTO_IP,IP_GET_IFLIST,reinterpret_cast<char *>(&actualInterface),&length)!=0||length!=sizeof(actualInterface)||actualInterface!=index)
        return failed(QStringLiteral("DHCP 接收接口验证失败："));
    length=sizeof(actualOutgoing);
    // Winsock takes IP_UNICAST_IF in network order but returns host order.
    if(getsockopt(socket,IPPROTO_IP,IP_UNICAST_IF,reinterpret_cast<char *>(&actualOutgoing),&length)!=0||length!=sizeof(actualOutgoing)||actualOutgoing!=index)
        return failed(QStringLiteral("DHCP 发送接口验证失败："));
    sockaddr_in endpoint{};endpoint.sin_family=AF_INET;endpoint.sin_port=htons(67);endpoint.sin_addr.s_addr=INADDR_ANY;
    if(::bind(socket,reinterpret_cast<const sockaddr *>(&endpoint),sizeof(endpoint))!=0)
        return failed(QStringLiteral("DHCP 端口监听失败："));
    if(!m_socket.setSocketDescriptor(qintptr(socket),QAbstractSocket::BoundState,QIODevice::ReadWrite))
        return failed(QStringLiteral("DHCP socket 接管失败："));
    return true;
#else
    m_error=QStringLiteral("专用 LAN DHCP 运行时需要 Windows。");return false;
#endif
}
QJsonObject DhcpServer::ownerReceipt(quint32 helperWorkerPid,QString *error) const{
    const auto fail=[&](const QString &message){if(error)*error=message;return QJsonObject();};
    if(m_isolated||!running()||port()!=67||!helperWorkerPid)return fail(QStringLiteral("DHCP 尚未在已确认的专用 LAN 上监听。"));
#ifdef Q_OS_WIN
    FILETIME creation{},exit{},kernel{},user{};
    if(!GetProcessTimes(GetCurrentProcess(),&creation,&exit,&kernel,&user))return fail(QStringLiteral("无法验证 DHCP 进程身份。"));
    WSAPROTOCOL_INFOW info{};
    if(WSADuplicateSocketW(SOCKET(m_socket.socketDescriptor()),helperWorkerPid,&info)!=0)return fail(QStringLiteral("无法生成专用 LAN socket 验证凭据。"));
    const auto created=(quint64(creation.dwHighDateTime)<<32)|creation.dwLowDateTime;
    return {{"owner_pid",double(GetCurrentProcessId())},{"owner_creation",QString::number(created)},
            {"target_helper_pid",double(helperWorkerPid)},
            {"protocol_info_base64",QString::fromLatin1(QByteArray(reinterpret_cast<const char *>(&info),sizeof(info)).toBase64())}};
#else
    return fail(QStringLiteral("DHCP socket 验证需要 Windows。"));
#endif
}
bool DhcpServer::validate(const Config &c,QString *error) {
    const auto fail=[&](const char *message){if(error)*error=QString::fromUtf8(message);return false;};
    for(const auto &ip:{c.gateway,c.first,c.last,c.dns})if(ip.protocol()!=QAbstractSocket::IPv4Protocol||ip.isNull()||ip.isMulticast())return fail("DHCP 需要有效的 IPv4 地址。");
    if(c.prefix<8||c.prefix>30||c.leaseSeconds<60||c.leaseSeconds>86400)return fail("子网前缀需要 /8 至 /30，租期需要 60 至 86400 秒。");
    const auto mask=0xffffffffu<<(32-c.prefix),gateway=c.gateway.toIPv4Address(),first=c.first.toIPv4Address(),last=c.last.toIPv4Address(),network=gateway&mask,broadcast=network|~mask;
    if(gateway<=network||gateway>=broadcast||(first&mask)!=network||(last&mask)!=network||first<=network||last>=broadcast||first>last||last-first>=512||(gateway>=first&&gateway<=last))return fail("地址池需要在网关子网内，最多 512 个地址，并排除网关、网络地址和广播地址。");
    return true;
}
bool DhcpServer::start(const Config &config) {
    if(running()){if(config==m_config)return true;m_error=QStringLiteral("请先停止 DHCP，再更改接口或地址池。");return false;}if(!validate(config,&m_error))return false;
    if(!m_isolated){const auto iface=QNetworkInterface::interfaceFromIndex(config.interfaceIndex);bool found=false;for(const auto &entry:iface.addressEntries())if(entry.ip()==config.gateway&&entry.prefixLength()==config.prefix)found=true;
        if(!found||!iface.flags().testFlag(QNetworkInterface::IsUp)||iface.flags().testFlag(QNetworkInterface::IsLoopBack)){m_error=QStringLiteral("所选接口必须已配置网关 IPv4 地址和对应子网。");return false;}}
    if(!configure(config))return false;m_error.clear();
    if(m_isolated){if(!m_socket.bind(QHostAddress::LocalHost,0,QAbstractSocket::DontShareAddress)){m_error=QStringLiteral("DHCP 测试端口监听失败：")+m_socket.errorString();return false;}}
    else if(!bindProductionSocket())return false;
    m_expiry.start();emit changed();return true;
}
void DhcpServer::stop(){m_expiry.stop();m_socket.close();
#ifdef Q_OS_WIN
    if(m_nativeWinsock){WSACleanup();m_nativeWinsock=false;}
#endif
    emit changed();}
void DhcpServer::expire(){bool changedState=false;for(auto i=m_leases.begin();i!=m_leases.end();)if(i->expires<now()){i=m_leases.erase(i);changedState=true;}else ++i;for(auto i=m_quarantine.begin();i!=m_quarantine.end();)if(i.value()<now())i=m_quarantine.erase(i);else ++i;if(changedState)emit changed();}
bool DhcpServer::available(quint32 ip,const QByteArray &client) const {
    if(ip<m_config.first.toIPv4Address()||ip>m_config.last.toIPv4Address()||m_quarantine.value(ip)>now())return false;
    const auto mac=QString::fromLatin1(client.left(6).toHex(':'));
    for(const auto &row:m_reservations)if(QHostAddress(row.value("ip").toString()).toIPv4Address()==ip&&row.value("mac").toString()!=mac)return false;
    for(auto i=m_leases.cbegin();i!=m_leases.cend();++i)if(i.key()!=client&&i->expires>=now()&&i->ip==ip)return false;return true;
}
quint32 DhcpServer::allocate(const QByteArray &client,quint32 preferred) {
    const auto mac=QString::fromLatin1(client.left(6).toHex(':'));const auto reserved=m_reservations.value(mac);
    if(!reserved.isEmpty()){const auto ip=QHostAddress(reserved.value("ip").toString()).toIPv4Address();return available(ip,client)?ip:0;}
    if(m_leases.contains(client)&&available(m_leases.value(client).ip,client))return m_leases.value(client).ip;
    if(preferred&&available(preferred,client))return preferred;
    for(quint32 ip=m_config.first.toIPv4Address();ip<=m_config.last.toIPv4Address();++ip)if(available(ip,client))return ip;return 0;
}
QByteArray DhcpServer::reply(const QByteArray &packet) {
    if(packet.size()<240||packet.size()>1500||packet[0]!=1||packet[1]!=1||packet[2]!=6||packet[3]!=0||number(packet,24)!=0||packet.mid(236,4)!=QByteArray::fromHex("63825363"))return {};
    QHash<int,QByteArray> options;
    if(!optionsFrom(packet,options)||options.value(53).size()!=1||(options.contains(50)&&options.value(50).size()!=4)||(options.contains(61)&&(options.value(61).size()<2||options.value(61).size()>64)))return {};const int type=uchar(options.value(53)[0]);if(!QList<int>{1,3,4,7,8}.contains(type))return {};
    if(options.contains(54)&&(options.value(54).size()!=4||number(options.value(54))!=m_config.gateway.toIPv4Address()))return {};
    const auto mac=packet.mid(28,6);if(mac==QByteArray(6,char(0))||(uchar(mac[0])&1))return {};const auto client=mac+options.value(61);
    const auto second=m_rateClock.elapsed()/1000;
    if(second!=m_rateSecond){m_rateSecond=second;m_requestsThisSecond=0;m_clientRequests.clear();}
    if(++m_requestsThisSecond>256||++m_clientRequests[mac]>16)return {};
    const auto requested=number(options.value(50)),current=number(packet,12);
    const auto mask=0xffffffffu<<(32-m_config.prefix),network=m_config.gateway.toIPv4Address()&mask,broadcast=network|~mask;
    const auto validClientAddress=[&](quint32 ip){return ip>network&&ip<broadcast&&ip!=m_config.gateway.toIPv4Address()&&(ip&mask)==network;};
    // RFC 2131 distinguishes SELECTING/INIT-REBOOT from RENEWING. In
    // particular, a REQUEST with no address must never allocate a random one.
    if((type==1&&(current||options.contains(54)))
       ||(type==3&&((!requested&&!current)||(requested&&current)||(options.contains(54)&&!requested)))
       ||(type==4&&(!requested||current))
       ||(type==7&&(!current||requested))
       ||(type==8&&(!validClientAddress(current)||requested||options.contains(54))))return {};
    expire();
    if(type==7){if(m_leases.contains(client)&&m_leases.value(client).ip==current){const auto previous=m_leases.take(client);if(!saveLeases())m_leases.insert(client,previous);else emit changed();}return {};}
    if(type==4){if(m_leases.contains(client)&&m_leases.value(client).ip==requested){const auto previous=m_leases.take(client);const auto oldQuarantine=m_quarantine;m_quarantine[requested]=now()+600;if(!saveLeases()){m_leases.insert(client,previous);m_quarantine=oldQuarantine;}else emit changed();}return {};}
    // A changing client identifier on one MAC must not consume the entire pool
    // or transfer an active reservation to another unacknowledged identity.
    const auto macText=QString::fromLatin1(mac.toHex(':'));
    for(auto i=m_leases.cbegin();i!=m_leases.cend();++i)if(i.key()!=client&&i->mac==macText&&i->expires>=now())return {};
    if(type==3&&!options.contains(54)&&!m_leases.contains(client)){
        // INIT-REBOOT/renewal with no known binding is ignored on the correct
        // subnet (RFC 2131 4.3.2), allowing the client to discover a server.
        if(validClientAddress(requested?requested:current))return {};
    }
    quint32 ip=type==8?0:allocate(client,requested?requested:current);int answer=type==1?2:5;
    if(type==3&&(!ip||(requested&&ip!=requested)||(current&&ip!=current)))answer=6;
    if(type==1&&!ip)return {};
    quint32 leaseDuration=quint32(m_config.leaseSeconds);
    if(type!=8&&answer!=6){QString name=QString::fromUtf8(options.value(12)).left(63);QString cleanName;for(const auto character:name)if(character.unicode()>=32&&character.unicode()!=127)cleanName+=character;name=cleanName;
        const auto previous=m_leases;
        if(type==1&&m_leases.contains(client)&&m_leases.value(client).committed){
            // An OFFER does not shorten or revoke an already committed lease.
            // Only DHCPREQUEST commits a new expiry.
            leaseDuration=quint32(std::max<qint64>(1,m_leases.value(client).expires-now()));
        }else m_leases[client]={ip,macText,name,now()+(type==1?60:m_config.leaseSeconds),now(),type==3};
        if(!saveLeases()){m_leases=previous;return {};}emit changed();}
    QByteArray out(236,char(0));out[0]=2;out[1]=1;out[2]=6;out.replace(4,4,packet.mid(4,4));out.replace(10,2,packet.mid(10,2));out.replace(28,16,packet.mid(28,16));
    if(answer!=6){out.replace(12,4,packet.mid(12,4));out.replace(16,4,address(ip));out.replace(20,4,address(m_config.gateway.toIPv4Address()));}
    out+=QByteArray::fromHex("63825363");out+=option(53,QByteArray(1,char(answer)));out+=option(54,address(m_config.gateway.toIPv4Address()));
    if(answer!=6){out+=option(1,address(0xffffffffu<<(32-m_config.prefix)));out+=option(3,address(m_config.gateway.toIPv4Address()));out+=option(6,address(m_config.dns.toIPv4Address()));if(type!=8){out+=option(51,address(leaseDuration));out+=option(58,address(leaseDuration/2));out+=option(59,address(leaseDuration*7/8));}}
    if(options.contains(61))out+=option(61,options.value(61));
    out+=char(255);if(out.size()<300)out.append(QByteArray(300-out.size(),char(0)));return out;
}

bool DhcpServer::configure(const Config &config) {
    if(running()||!validate(config,&m_error))return false;
    DhcpServer staged(true);staged.m_config=config;staged.m_leasePath=m_leasePath;
    if(!staged.loadLeases()){m_error=staged.m_error;return false;}
    if(!staged.replaceReservations(reservations())){m_error=staged.m_error;return false;}
    m_config=config;m_leases=std::move(staged.m_leases);m_quarantine=std::move(staged.m_quarantine);m_error.clear();return true;
}
QHostAddress DhcpServer::replyAddress(const QByteArray &request,const QByteArray &response){
    QHash<int,QByteArray> options;
    if(!optionsFrom(response,options)||options.value(53).size()!=1)return QHostAddress(QHostAddress::Broadcast);
    const auto current=number(request,12);
    if(uchar(options.value(53)[0])==6||!current)return QHostAddress(QHostAddress::Broadcast);
    return QHostAddress(current);
}
void DhcpServer::receive() {
    int count=0;while(m_socket.hasPendingDatagrams()&&count++<32){const auto incoming=m_socket.receiveDatagram(1501);
        if(!m_isolated&&(incoming.interfaceIndex()!=uint(m_config.interfaceIndex)||incoming.senderPort()!=68))continue;
        if(m_isolated&&!incoming.senderAddress().isLoopback())continue;
        const auto response=reply(incoming.data());if(response.isEmpty())continue;
        QNetworkDatagram outgoing(response,m_isolated?incoming.senderAddress():replyAddress(incoming.data(),response),m_isolated?incoming.senderPort():68);
        if(!m_isolated){outgoing.setInterfaceIndex(m_config.interfaceIndex);outgoing.setSender(m_config.gateway,67);}
        if(m_socket.writeDatagram(outgoing)<0){m_error=QStringLiteral("DHCP 响应发送失败：")+m_socket.errorString();emit changed();}
    }
    if(m_socket.hasPendingDatagrams())QTimer::singleShot(0,this,&DhcpServer::receive);
}
QVariantList DhcpServer::leases() const {
    QVariantList rows;for(auto i=m_leases.cbegin();i!=m_leases.cend();++i){if(i->expires<now())continue;const auto reservation=m_reservations.value(i->mac);
        rows.append(QVariantMap{{"id",QString::fromLatin1(i.key().toHex())},{"mac",i->mac},{"ip",QHostAddress(i->ip).toString()},{"name",reservation.value("name",i->name)},{"lastSeen",i->lastSeen},{"expires",i->expires},{"status",i->committed?QStringLiteral("租用中"):QStringLiteral("已提供")}});}
    return rows;
}
bool DhcpServer::reserve(const QString &mac,const QString &ip,const QString &name) {
    const auto normalized=mac.trimmed().toLower();const QHostAddress address(ip);
    if(!QRegularExpression("^[0-9a-f]{2}(:[0-9a-f]{2}){5}$").match(normalized).hasMatch()||address.protocol()!=QAbstractSocket::IPv4Protocol||name.toUtf8().size()>128||std::any_of(name.cbegin(),name.cend(),[](QChar c){return c.unicode()<32||c.unicode()==127;})){m_error=QStringLiteral("MAC、IPv4 地址或设备名格式无效。");return false;}
    const auto raw=QByteArray::fromHex(normalized.toLatin1());bool inUse=false;const auto number=address.toIPv4Address();
    for(const auto &row:m_reservations)if(QHostAddress(row.value("ip").toString()).toIPv4Address()==number&&row.value("mac").toString()!=normalized)inUse=true;
    for(const auto &lease:m_leases)if(lease.ip==number&&lease.mac!=normalized&&lease.expires>now())inUse=true;
    if(raw==QByteArray(6,char(0))||(uchar(raw[0])&1)||number<m_config.first.toIPv4Address()||number>m_config.last.toIPv4Address()||m_quarantine.value(number)>now()||inUse){m_error=QStringLiteral("保留地址超出地址池，或已被其他设备使用。");return false;}
    m_reservations[normalized]={{"mac",normalized},{"ip",address.toString()},{"name",name}};emit changed();return true;
}
void DhcpServer::clearReservations(){m_reservations.clear();emit changed();}
QVariantList DhcpServer::reservations() const {QVariantList result;for(const auto &row:m_reservations)result.append(row);return result;}

bool DhcpServer::loadLeases() {
    m_leases.clear();m_quarantine.clear();if(m_leasePath.isEmpty())return true;
    QFile file(m_leasePath);if(!file.exists())return true;
    if(!file.open(QIODevice::ReadOnly)||file.size()>1024*1024){m_error=QStringLiteral("DHCP 租约记录无法读取。");return false;}
    QJsonParseError error;const auto object=QJsonDocument::fromJson(file.readAll(),&error).object();
    if(error.error!=QJsonParseError::NoError||object.value("schema").toInt()!=1||!object.value("leases").isArray()||object.value("leases").toArray().size()>512
       ||!object.value("quarantine").isArray()||object.value("quarantine").toArray().size()>512){m_error=QStringLiteral("DHCP 租约记录损坏，已保留原文件并停止分配。");return false;}
    QSet<quint32> allocated;
    QSet<QByteArray> clients;
    for(const auto &entry:object.value("leases").toArray()){const auto row=entry.toObject();qint64 expiry=0,lastSeen=0;
        if(!jsonTime(row.value("expires"),expiry)||!jsonTime(row.value("lastSeen"),lastSeen)||lastSeen>expiry||expiry-lastSeen>86400
           ||lastSeen>now()+300||expiry>now()+86400+300
           ||!row.value("committed").isBool()||!row.value("name").isString()||!cleanName(row.value("name").toString())){m_error=QStringLiteral("DHCP 租约时间或名称格式无效。");return false;}
        if(expiry<=now())continue;
        const QHostAddress ip(row.value("ip").toString());const auto hex=row.value("client").toString();
        if(ip.protocol()!=QAbstractSocket::IPv4Protocol||!QRegularExpression("^[0-9a-f]{12,140}$").match(hex).hasMatch()||hex.size()%2||hex.size()==14){m_error=QStringLiteral("DHCP 租约格式无效。");return false;}
        if(ip.toIPv4Address()<m_config.first.toIPv4Address()||ip.toIPv4Address()>m_config.last.toIPv4Address())continue;
        const auto client=QByteArray::fromHex(hex.toLatin1()),mac=client.left(6);
        if(mac==QByteArray(6,char(0))||(uchar(mac[0])&1)||allocated.contains(ip.toIPv4Address())||m_leases.contains(client)||clients.contains(mac)){m_error=QStringLiteral("DHCP 租约包含无效身份或重复地址。");return false;}allocated.insert(ip.toIPv4Address());clients.insert(mac);
        m_leases[client]={ip.toIPv4Address(),QString::fromLatin1(mac.toHex(':')),row.value("name").toString(),expiry,lastSeen,row.value("committed").toBool()};
    }
    for(const auto &entry:object.value("quarantine").toArray()){const auto row=entry.toObject();const QHostAddress ip(row.value("ip").toString());qint64 expiry=0;
        if(!jsonTime(row.value("expires"),expiry)||expiry>now()+600+300||ip.protocol()!=QAbstractSocket::IPv4Protocol){m_error=QStringLiteral("DHCP 冲突隔离记录格式无效。");return false;}
        if(expiry<=now()||ip.toIPv4Address()<m_config.first.toIPv4Address()||ip.toIPv4Address()>m_config.last.toIPv4Address())continue;
        if(m_quarantine.contains(ip.toIPv4Address())||allocated.contains(ip.toIPv4Address())){m_error=QStringLiteral("DHCP 冲突隔离记录与租约重叠。");return false;}
        m_quarantine[ip.toIPv4Address()]=expiry;}
    return true;
}
bool DhcpServer::saveLeases() {
    if(m_leasePath.isEmpty())return true;QJsonArray leases,quarantine;
    for(auto i=m_leases.cbegin();i!=m_leases.cend();++i)leases.append(QJsonObject{{"client",QString::fromLatin1(i.key().toHex())},{"ip",QHostAddress(i->ip).toString()},{"name",i->name},{"expires",double(i->expires)},{"lastSeen",double(i->lastSeen)},{"committed",i->committed}});
    for(auto i=m_quarantine.cbegin();i!=m_quarantine.cend();++i)quarantine.append(QJsonObject{{"ip",QHostAddress(i.key()).toString()},{"expires",double(i.value())}});
    QDir().mkpath(QFileInfo(m_leasePath).absolutePath());QSaveFile file(m_leasePath);const auto bytes=QJsonDocument(QJsonObject{{"schema",1},{"leases",leases},{"quarantine",quarantine}}).toJson(QJsonDocument::Compact);
    if(!file.open(QIODevice::WriteOnly)||file.write(bytes)!=bytes.size()||!file.commit()){m_error=QStringLiteral("DHCP 租约保存失败，已停止分配以避免重复地址。");stop();return false;}return true;
}

bool DhcpServer::replaceReservations(const QVariantList &rows){if(rows.size()>512){m_error=QStringLiteral("最多保存 512 个客户端保留地址。");return false;}DhcpServer staged(true);staged.m_config=m_config;staged.m_leases=m_leases;staged.m_quarantine=m_quarantine;
    for(const auto &entry:rows){const auto row=entry.toMap();const auto mac=row.value("mac").toString().trimmed().toLower();if(staged.m_reservations.contains(mac)||!staged.reserve(mac,row.value("ip").toString(),row.value("name").toString())){m_error=staged.m_error.isEmpty()?QStringLiteral("CSV 包含重复 MAC。"):staged.m_error;return false;}}
    m_reservations=staged.m_reservations;emit changed();return true;}
