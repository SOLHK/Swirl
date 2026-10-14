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
namespace {
quint32 number(const QByteArray &bytes,int offset=0){return offset+4<=bytes.size()?qFromBigEndian<quint32>(reinterpret_cast<const uchar *>(bytes.constData()+offset)):0;}
QByteArray address(quint32 value){QByteArray bytes(4,Qt::Uninitialized);qToBigEndian(value,reinterpret_cast<uchar *>(bytes.data()));return bytes;}
QByteArray option(int key,const QByteArray &value){return QByteArray(1,char(key))+QByteArray(1,char(value.size()))+value;}
qint64 now(){return QDateTime::currentSecsSinceEpoch();}
}
DhcpServer::DhcpServer(bool isolated,QObject *parent):QObject(parent),m_isolated(isolated) {
    m_socket.setProxy(QNetworkProxy::NoProxy);connect(&m_socket,&QUdpSocket::readyRead,this,&DhcpServer::receive);
    m_expiry.setInterval(10000);connect(&m_expiry,&QTimer::timeout,this,&DhcpServer::expire);
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
    if(running())return true;if(!validate(config,&m_error))return false;
    if(!m_isolated){const auto iface=QNetworkInterface::interfaceFromIndex(config.interfaceIndex);bool found=false;for(const auto &entry:iface.addressEntries())if(entry.ip()==config.gateway&&entry.prefixLength()==config.prefix)found=true;
        if(!found||!iface.flags().testFlag(QNetworkInterface::IsUp)||iface.flags().testFlag(QNetworkInterface::IsLoopBack)){m_error=QStringLiteral("所选接口必须已配置网关 IPv4 地址和对应子网。");return false;}}
    if(!configure(config))return false;m_error.clear();
    if(!m_socket.bind(m_isolated?QHostAddress::LocalHost:QHostAddress::AnyIPv4,m_isolated?0:67,QAbstractSocket::DontShareAddress)){m_error=QStringLiteral("DHCP 端口监听失败：")+m_socket.errorString();return false;}
    m_expiry.start();emit changed();return true;
}
void DhcpServer::stop(){m_expiry.stop();m_socket.close();emit changed();}
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
    if(preferred&&available(preferred,client))return preferred;
    if(m_leases.contains(client)&&available(m_leases.value(client).ip,client))return m_leases.value(client).ip;
    for(quint32 ip=m_config.first.toIPv4Address();ip<=m_config.last.toIPv4Address();++ip)if(available(ip,client))return ip;return 0;
}
QByteArray DhcpServer::reply(const QByteArray &packet) {
    if(packet.size()<240||packet.size()>1500||packet[0]!=1||packet[1]!=1||packet[2]!=6||packet[3]!=0||number(packet,24)!=0||packet.mid(236,4)!=QByteArray::fromHex("63825363"))return {};
    bool ended=false;QHash<int,QByteArray> options;for(int offset=240;offset<packet.size();){const int key=uchar(packet[offset++]);if(key==255){ended=true;break;}if(key==0)continue;if(offset>=packet.size())return {};const int size=uchar(packet[offset++]);if(offset+size>packet.size()||options.contains(key))return {};options.insert(key,packet.mid(offset,size));offset+=size;}
    if(!ended||options.value(53).size()!=1||(options.contains(50)&&options.value(50).size()!=4)||(options.contains(61)&&(options.value(61).size()<2||options.value(61).size()>64)))return {};const int type=uchar(options.value(53)[0]);if(!QList<int>{1,3,4,7,8}.contains(type))return {};
    if(options.contains(54)&&(options.value(54).size()!=4||number(options.value(54))!=m_config.gateway.toIPv4Address()))return {};
    const auto mac=packet.mid(28,6);if(mac==QByteArray(6,char(0))||(uchar(mac[0])&1))return {};const auto client=mac+options.value(61);
    const auto requested=number(options.value(50)),current=number(packet,12);expire();
    if(type==7){if(m_leases.contains(client)&&m_leases.value(client).ip==current){m_leases.remove(client);saveLeases();emit changed();}return {};}
    if(type==4){if(m_leases.contains(client)&&m_leases.value(client).ip==requested){m_quarantine[requested]=now()+600;m_leases.remove(client);saveLeases();emit changed();}return {};}
    quint32 ip=type==8?0:allocate(client,requested?requested:current);int answer=type==1?2:5;
    if(type==3&&(!ip||(requested&&ip!=requested)||(current&&ip!=current)))answer=6;
    if(type==1&&!ip)return {};
    if(type!=8&&answer!=6){QString name=QString::fromUtf8(options.value(12)).left(63);QString cleanName;for(const auto character:name)if(character.unicode()>=32&&character.unicode()!=127)cleanName+=character;name=cleanName;
        m_leases[client]={ip,QString::fromLatin1(mac.toHex(':')),name,now()+(type==1?60:m_config.leaseSeconds),now(),type==3};if(!saveLeases())return {};emit changed();}
    QByteArray out(236,char(0));out[0]=2;out[1]=1;out[2]=6;out.replace(4,4,packet.mid(4,4));out.replace(10,2,packet.mid(10,2));out.replace(28,16,packet.mid(28,16));
    if(answer!=6){out.replace(12,4,packet.mid(12,4));out.replace(16,4,address(ip));out.replace(20,4,address(m_config.gateway.toIPv4Address()));}
    out+=QByteArray::fromHex("63825363");out+=option(53,QByteArray(1,char(answer)));out+=option(54,address(m_config.gateway.toIPv4Address()));
    if(answer!=6){out+=option(1,address(0xffffffffu<<(32-m_config.prefix)));out+=option(3,address(m_config.gateway.toIPv4Address()));out+=option(6,address(m_config.dns.toIPv4Address()));if(type!=8){out+=option(51,address(m_config.leaseSeconds));out+=option(58,address(m_config.leaseSeconds/2));out+=option(59,address(m_config.leaseSeconds*7/8));}}
    if(options.contains(61))out+=option(61,options.value(61));
    out+=char(255);if(out.size()<300)out.append(QByteArray(300-out.size(),char(0)));return out;
}

bool DhcpServer::configure(const Config &config) {if(running()||!validate(config,&m_error))return false;m_config=config;return loadLeases();}
void DhcpServer::receive() {
    int count=0;while(m_socket.hasPendingDatagrams()&&count++<32){const auto incoming=m_socket.receiveDatagram(1501);
        if(!m_isolated&&(incoming.interfaceIndex()!=uint(m_config.interfaceIndex)||incoming.senderPort()!=68))continue;
        if(m_isolated&&!incoming.senderAddress().isLoopback())continue;
        const auto response=reply(incoming.data());if(response.isEmpty())continue;
        const auto current=number(incoming.data(),12);const bool nak=response.contains(QByteArray::fromHex("350106"));
        QNetworkDatagram outgoing(response,m_isolated?incoming.senderAddress():current&&!nak?QHostAddress(current):QHostAddress(QHostAddress::Broadcast),m_isolated?incoming.senderPort():68);
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
    if(error.error!=QJsonParseError::NoError||object.value("schema").toInt()!=1||!object.value("leases").isArray()||object.value("leases").toArray().size()>512){m_error=QStringLiteral("DHCP 租约记录损坏，已保留原文件并停止分配。");return false;}
    QSet<quint32> allocated;
    for(const auto &entry:object.value("leases").toArray()){const auto row=entry.toObject();const auto expiry=qint64(row.value("expires").toDouble());if(expiry<=now())continue;
        const QHostAddress ip(row.value("ip").toString());const auto hex=row.value("client").toString();
        if(ip.protocol()!=QAbstractSocket::IPv4Protocol||!QRegularExpression("^[0-9a-f]{12,140}$").match(hex).hasMatch()||hex.size()%2){m_error=QStringLiteral("DHCP 租约格式无效。");return false;}
        if(ip.toIPv4Address()<m_config.first.toIPv4Address()||ip.toIPv4Address()>m_config.last.toIPv4Address())continue;
        const auto client=QByteArray::fromHex(hex.toLatin1());if(allocated.contains(ip.toIPv4Address())||m_leases.contains(client)){m_error=QStringLiteral("DHCP 租约包含重复地址。");return false;}allocated.insert(ip.toIPv4Address());
        m_leases[client]={ip.toIPv4Address(),QString::fromLatin1(client.left(6).toHex(':')),row.value("name").toString().left(63),expiry,qint64(row.value("lastSeen").toDouble()),row.value("committed").toBool()};
    }
    for(const auto &entry:object.value("quarantine").toArray()){const auto row=entry.toObject();const QHostAddress ip(row.value("ip").toString());const auto expiry=qint64(row.value("expires").toDouble());if(expiry>now()&&ip.protocol()==QAbstractSocket::IPv4Protocol)m_quarantine[ip.toIPv4Address()]=expiry;}
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
