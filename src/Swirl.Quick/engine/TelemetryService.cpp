#include "TelemetryService.h"
#include <QStandardPaths>
#include <QDir>
#include <QFile>
#include <QSaveFile>
#include <QDateTime>
#include <QJsonDocument>
#include <QJsonArray>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QDnsLookup>
#include <QElapsedTimer>
#include <QHostAddress>
#include <QThreadPool>
#include <QPointer>
#include <QSet>
#include <QTcpSocket>
#include <cmath>
#include <algorithm>
#ifdef Q_OS_WIN
#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#include <icmpapi.h>
#endif
namespace {
qint64 nowMs(){return QDateTime::currentMSecsSinceEpoch();}
void add(QJsonObject &o,const QString &key,double value){o[key]=o.value(key).toDouble()+value;}
void aggregate(QJsonObject &day,const QString &kind,QString key,double up,double down,bool count){
 key=key.left(256);auto group=day.value(kind).toObject();if(!group.contains(key)&&group.size()>=128)key=QStringLiteral("其他（分类上限）");
 auto row=group.value(key).toObject();add(row,"up",up);add(row,"down",down);if(count)add(row,"count",1);
 group[key]=row;day[kind]=group;
}
}
TelemetryService::TelemetryService(QString path,bool networkMeasurements,QObject *parent):QObject(parent),m_path(path),m_networkEnabled(networkMeasurements){
 if(m_path.isEmpty())m_path=QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/telemetry.json";
 load();m_save.setInterval(5000);connect(&m_save,&QTimer::timeout,this,&TelemetryService::flush);m_save.start();
 m_measure.setInterval(60000);connect(&m_measure,&QTimer::timeout,this,[this]{if(m_networkEnabled&&m_status.apiHealthy)measureNetwork();});m_measure.start();
 m_stale.setInterval(1000);connect(&m_stale,&QTimer::timeout,this,[this]{if(!sampled()||!connectionsSampled())publish();});m_stale.start();
}
TelemetryService::~TelemetryService(){flush();}
bool TelemetryService::sampled() const{return m_status.apiHealthy&&m_status.trafficAt>0&&nowMs()-m_status.trafficAt<6000;}
bool TelemetryService::connectionsSampled() const{return m_status.apiHealthy&&m_status.connectionsAt>0&&nowMs()-m_status.connectionsAt<6000;}
void TelemetryService::publish(){++m_revision;emit changed();}
QString TelemetryService::formatBytes(double bytes) const {
 const QStringList units={"B","KB","MB","GB","TB"};int i=0;while(bytes>=1024&&i<4){bytes/=1024;++i;}
 return QString::number(bytes,'f',i?1:0)+" "+units[i];
}
int TelemetryService::activeProcesses() const {QSet<QString> names;for(const auto &r:m_status.connections){const auto name=r.toMap().value("process").toString();if(!name.isEmpty()&&name!="未知进程")names.insert(name);}return names.size();}
void TelemetryService::ingest(const ProxyEngine::Status &status){
 const auto epoch=QString::number(status.processId);
 if(status.processAlive&&m_epoch!=epoch){m_epoch=epoch;m_seen.clear();m_lastConnections=0;m_lastTraffic=0;m_lastUp=0;m_lastDown=0;m_externalIp.clear();m_latencies.clear();}
 const auto route=epoch+"/"+status.selectedNodeId+"/"+status.mode;
 if(route!=m_routeEpoch){m_routeEpoch=route;m_externalIp.clear();m_latencies.clear();}
 m_status=status;
 if(!status.apiHealthy){for(auto it=m_seen.begin();it!=m_seen.end();++it)(*it)["status"]="已结束";publish();return;}
 if(status.connectionsAt>m_lastConnections){
  m_lastConnections=status.connectionsAt;const auto date=QDateTime::fromMSecsSinceEpoch(status.connectionsAt).date().toString(Qt::ISODate);
  auto day=m_days.value(date).toObject();day["sampled"]=true;
  // Session counters are owned by this process. A reset starts a new baseline.
  const auto up=qMax<qint64>(0,status.uploadTotal),down=qMax<qint64>(0,status.downloadTotal);
  add(day,"up",up>=m_lastUp?up-m_lastUp:up);add(day,"down",down>=m_lastDown?down-m_lastDown:down);m_lastUp=up;m_lastDown=down;
  QSet<QString> active;
  for(const auto &value:status.connections){
   auto row=value.toMap();const auto id=row.value("id").toString();if(id.isEmpty()||active.contains(id))continue;active.insert(id);
   const auto old=m_seen.value(id);const auto u=row.value("uploadBytes").toLongLong(),d=row.value("downloadBytes").toLongLong();
   const auto ou=old.value("uploadBytes").toLongLong(),od=old.value("downloadBytes").toLongLong();
   const auto du=qMax<qint64>(0,u>=ou?u-ou:u),dd=qMax<qint64>(0,d>=od?d-od:d);
   const bool count=old.value("accountedDay").toString()!=date;
   aggregate(day,"apps",row.value("process","未知进程").toString(),du,dd,count);
   aggregate(day,"domains",row.value("host",row.value("ip")).toString(),du,dd,count);
   aggregate(day,"nodes",row.value("policy").toString(),du,dd,count);
   aggregate(day,"categories",row.value("category","other").toString(),du,dd,count);
   row["accountedDay"]=date;row["lastSeen"]=status.connectionsAt;row["status"]="活动";
   row["up"]=formatBytes(u);row["down"]=formatBytes(d);row["time"]=QDateTime::fromString(row.value("time").toString(),Qt::ISODateWithMs).toLocalTime().toString("MM-dd HH:mm:ss");
   m_seen[id]=row;
  }
  for(auto it=m_seen.begin();it!=m_seen.end();++it)if(!active.contains(it.key()))(*it)["status"]="已结束";
  while(m_seen.size()>2000){auto oldest=m_seen.end();for(auto it=m_seen.begin();it!=m_seen.end();++it)if(!active.contains(it.key())&&(oldest==m_seen.end()||it->value("lastSeen").toLongLong()<oldest->value("lastSeen").toLongLong()))oldest=it;if(oldest==m_seen.end())break;m_seen.erase(oldest);}
  m_days[date]=day;const auto oldest=QDate::currentDate().addDays(-31).toString(Qt::ISODate);for(const auto &key:m_days.keys())if(key<oldest)m_days.remove(key);while(m_days.size()>32)m_days.remove(m_days.keys().first());m_dirty=true;
 }
 if(status.trafficAt>m_lastTraffic){m_lastTraffic=status.trafficAt;m_history.append(QVariantMap{{"time",status.trafficAt},{"down",status.downloadRate},{"up",status.uploadRate}});while(m_history.size()>3600)m_history.removeFirst();m_dirty=true;}
 publish();
}
QVariantList TelemetryService::connections() const {QVariantList rows;for(const auto &r:m_seen)rows.append(r);std::sort(rows.begin(),rows.end(),[](const QVariant &a,const QVariant &b){return a.toMap().value("lastSeen").toLongLong()>b.toMap().value("lastSeen").toLongLong();});return rows;}
QJsonObject TelemetryService::periodData(int period) const {
 QJsonObject out;const auto today=QDate::currentDate();const auto start=period==1?today.addDays(-1):period==2?today.addDays(1-today.dayOfWeek()):today;
 const auto end=period==1?today.addDays(-1):today;
 for(const auto &key:m_days.keys()){const auto date=QDate::fromString(key,Qt::ISODate);if(date<start||date>end)continue;const auto d=m_days.value(key).toObject();if(d.value("sampled").toBool())out["sampled"]=true;add(out,"up",d.value("up").toDouble());add(out,"down",d.value("down").toDouble());
  for(const auto &kind:{"apps","domains","nodes","categories"}){auto group=out.value(kind).toObject();const auto entries=d.value(kind).toObject();for(const auto &name:entries.keys()){auto sum=group.value(name).toObject();const auto row=entries.value(name).toObject();for(const auto &field:{"up","down","count"})add(sum,field,row.value(field).toDouble());group[name]=sum;}out[kind]=group;}
 }return out;
}
QVariantMap TelemetryService::summary(int period) const {auto d=periodData(period);return {{"sampled",d.value("sampled").toBool()},{"up",d.value("up").toDouble()},{"down",d.value("down").toDouble()},{"total",d.value("up").toDouble()+d.value("down").toDouble()},{"domains",d.value("domains").toObject().size()},{"apps",d.value("apps").toObject().size()}};}
QVariantList TelemetryService::ranking(const QString &kind,int period,int limit) const {
 if(kind!="apps"&&kind!="domains"&&kind!="nodes")return {};const auto data=periodData(period),entries=data.value(kind).toObject();QVariantList result;const auto total=data.value("up").toDouble()+data.value("down").toDouble();
 for(const auto &name:entries.keys()){const auto r=entries.value(name).toObject();const auto up=r.value("up").toDouble(),down=r.value("down").toDouble();result.append(QVariantMap{{"id",name},{"name",name},{"upload",formatBytes(up)},{"download",formatBytes(down)},{"value",formatBytes(up+down)},{"total",up+down},{"connections",r.value("count").toDouble()},{"percent",total>0?QString::number(100*(up+down)/total,'f',1)+"%":"0%"},{"mark",name.left(1)},{"color","#596273"}});}
 std::sort(result.begin(),result.end(),[](const QVariant &a,const QVariant &b){return a.toMap().value("total").toDouble()>b.toMap().value("total").toDouble();});while(result.size()>qBound(1,limit,512))result.removeLast();return result;
}
QVariantList TelemetryService::distribution(int period) const {
 const auto d=periodData(period),cats=d.value("categories").toObject();double measured=0;for(const auto &v:cats){const auto r=v.toObject();measured+=r.value("up").toDouble()+r.value("down").toDouble();}
 const auto total=qMax(measured,d.value("up").toDouble()+d.value("down").toDouble());QVariantList rows;
 const QStringList keys={"proxy","direct","reject","other"},names={"代理流量","直连流量","阻止请求","其他流量"},colors={"#0069D9","#00852A","#976217","#596273"};
 for(int i=0;i<4;++i){const auto r=cats.value(keys[i]).toObject();double bytes=r.value("up").toDouble()+r.value("down").toDouble();if(i==3)bytes+=qMax(0.0,total-measured);const bool known=d.value("sampled").toBool();rows.append(QVariantMap{{"name",names[i]},{"tint",colors[i]},{"bytes",bytes},{"value",!known?QStringLiteral("未采集"):i==2?QString::number(r.value("count").toInt())+" 次":formatBytes(bytes)},{"percent",known?QString::number(total>0?100*bytes/total:0,'f',1)+"%":"—"}});}return rows;
}
QVariantList TelemetryService::history(const QString &series,int seconds,bool normalized) const {QVariantList out;double maximum=1;const auto cutoff=nowMs()-qBound(60,seconds,86400)*1000LL;for(const auto &v:m_history){const auto r=v.toMap();if(r.value("time").toLongLong()<cutoff)continue;const auto value=series=="total"?r.value("up").toDouble()+r.value("down").toDouble():r.value(series).toDouble();out.append(value);maximum=qMax(maximum,value);}if(normalized)for(auto &v:out)v=v.toDouble()/maximum;return out;}
QVariantList TelemetryService::historyPoints(const QString &series,int seconds) const {QVariantList out;const auto cutoff=nowMs()-qBound(60,seconds,86400)*1000LL;for(const auto &v:m_history){const auto row=v.toMap();if(row.value("time").toLongLong()<cutoff)continue;const auto value=series=="total"?row.value("up").toDouble()+row.value("down").toDouble():row.value(series).toDouble();out.append(QVariantMap{{"time",row.value("time")},{"value",value}});}return out;}
void TelemetryService::load(){QFile file(m_path);if(!file.exists())return;if(!file.open(QIODevice::ReadOnly)||file.size()>16*1024*1024){m_storageError="监控历史无法读取或超过大小限制";return;}QJsonParseError e;const auto doc=QJsonDocument::fromJson(file.readAll(),&e);if(e.error!=QJsonParseError::NoError||doc.object().value("schema").toInt()!=1){m_storageError="监控历史格式无效";return;}m_days=doc.object().value("days").toObject();m_history=doc.object().value("history").toArray().toVariantList();while(m_history.size()>3600)m_history.removeFirst();}
void TelemetryService::flush(){if(!m_dirty)return;QDir().mkpath(QFileInfo(m_path).absolutePath());QSaveFile file(m_path);const auto bytes=QJsonDocument(QJsonObject{{"schema",1},{"days",m_days},{"history",QJsonArray::fromVariantList(m_history)}}).toJson(QJsonDocument::Compact);if(!file.open(QIODevice::WriteOnly)||file.write(bytes)!=bytes.size()||!file.commit()){m_storageError="监控历史保存失败";emit diagnostic("Telemetry","StorageWrite",m_storageError);publish();return;}m_dirty=false;}
void TelemetryService::measureHttp(const QString &key,const QUrl &url,bool throughProxy,bool ip){
 auto network=new QNetworkAccessManager(this);network->setProxy(throughProxy?QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",m_status.proxyPort):QNetworkProxy(QNetworkProxy::NoProxy));QNetworkRequest req(url);req.setTransferTimeout(8000);req.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);req.setAttribute(QNetworkRequest::CacheLoadControlAttribute,QNetworkRequest::AlwaysNetwork);req.setRawHeader("Connection","close");auto timer=std::make_shared<QElapsedTimer>();timer->start();auto reply=network->get(req);auto deadline=new QTimer(reply);deadline->setSingleShot(true);connect(deadline,&QTimer::timeout,reply,&QNetworkReply::abort);deadline->start(9000);const auto epoch=m_routeEpoch;
 connect(reply,&QNetworkReply::readyRead,this,[reply]{if(reply->bytesAvailable()>4096)reply->abort();});
 connect(reply,&QNetworkReply::finished,this,[this,network,reply,timer,key,ip,epoch]{const auto code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();const bool ok=reply->error()==QNetworkReply::NoError&&code>=200&&code<300;if(epoch==m_routeEpoch){if(ip){const QString candidate=QString::fromUtf8(reply->readAll()).trimmed();m_externalIp=ok&&!QHostAddress(candidate).isNull()?candidate:QString();}else m_latencies[key]=ok?QString::number(timer->elapsed())+" ms":"检测失败";if(!ok)emit diagnostic("NetworkMeasurement",key,QString("测量失败，HTTP %1，网络错误 %2").arg(code).arg(int(reply->error())));}reply->deleteLater();network->deleteLater();--m_measurements;m_measurementState=m_measurements?"正在测量":"测量完成";publish();});
}
void TelemetryService::measureNetwork(){
 if(!m_networkEnabled||m_measurements)return;m_measurementState="正在测量";m_measurements=2;
 // TCP handshake to a public Internet endpoint; independent of proxy routing,
 // HTTP redirects and the DNS lookup measured below.
 auto socket=new QTcpSocket(this);socket->setProxy(QNetworkProxy::NoProxy);auto tcpClock=std::make_shared<QElapsedTimer>();tcpClock->start();auto tcpDeadline=new QTimer(socket);tcpDeadline->setSingleShot(true);tcpDeadline->start(6000);
 const auto tcpEpoch=m_routeEpoch;
 auto tcpDone=[this,socket,tcpClock,tcpEpoch](bool ok){if(socket->property("measured").toBool())return;socket->setProperty("measured",true);if(tcpEpoch==m_routeEpoch){m_latencies["internet"]=ok?QString::number(tcpClock->elapsed())+" ms":"连接失败";if(!ok)emit diagnostic("NetworkMeasurement","InternetTCP","外部 TCP 握手失败或超时");}socket->deleteLater();--m_measurements;m_measurementState=m_measurements?"正在测量":"测量完成";publish();};
 connect(socket,&QTcpSocket::connected,this,[tcpDone]{tcpDone(true);});connect(socket,&QTcpSocket::errorOccurred,this,[tcpDone](QAbstractSocket::SocketError){tcpDone(false);});connect(tcpDeadline,&QTimer::timeout,this,[tcpDone]{tcpDone(false);});socket->connectToHost(QHostAddress("1.1.1.1"),443);
 if(m_status.apiHealthy&&m_status.proxyPort>0){++m_measurements;measureHttp("exit",QUrl("https://api.ipify.org"),true,true);}
 auto dns=new QDnsLookup(QDnsLookup::A,"www.microsoft.com",this);auto elapsed=std::make_shared<QElapsedTimer>();elapsed->start();const auto epoch=m_routeEpoch;
 auto dnsDeadline=new QTimer(dns);dnsDeadline->setSingleShot(true);connect(dnsDeadline,&QTimer::timeout,dns,&QDnsLookup::abort);dnsDeadline->start(8000);
 connect(dns,&QDnsLookup::finished,this,[this,dns,elapsed,epoch]{if(epoch==m_routeEpoch){const bool ok=dns->error()==QDnsLookup::NoError&&!dns->hostAddressRecords().isEmpty();m_latencies["dns"]=ok?QString::number(elapsed->elapsed())+" ms":"解析失败";if(!ok)emit diagnostic("NetworkMeasurement","DNS",QString("DNS 测量失败，错误 %1").arg(int(dns->error())));}dns->deleteLater();--m_measurements;m_measurementState=m_measurements?"正在测量":"测量完成";publish();});dns->lookup();
#ifdef Q_OS_WIN
 ++m_measurements;QPointer<TelemetryService> guard(this);QThreadPool::globalInstance()->start([guard,epoch]{int delay=-1;ULONG size=16384;QByteArray buffer(size,0);ULONG result=GetAdaptersAddresses(AF_INET,GAA_FLAG_INCLUDE_GATEWAYS,nullptr,reinterpret_cast<IP_ADAPTER_ADDRESSES *>(buffer.data()),&size);if(result==ERROR_BUFFER_OVERFLOW){buffer.resize(size);result=GetAdaptersAddresses(AF_INET,GAA_FLAG_INCLUDE_GATEWAYS,nullptr,reinterpret_cast<IP_ADAPTER_ADDRESSES *>(buffer.data()),&size);}if(result==NO_ERROR)for(auto a=reinterpret_cast<IP_ADAPTER_ADDRESSES *>(buffer.data());a;a=a->Next){if(a->OperStatus!=IfOperStatusUp||a->IfType==IF_TYPE_SOFTWARE_LOOPBACK||!a->FirstGatewayAddress)continue;const auto address=reinterpret_cast<sockaddr_in *>(a->FirstGatewayAddress->Address.lpSockaddr);HANDLE handle=IcmpCreateFile();if(handle!=INVALID_HANDLE_VALUE){char payload[]="Swirl gateway latency";QByteArray response(sizeof(ICMP_ECHO_REPLY)+sizeof(payload)+32,0);if(IcmpSendEcho(handle,address->sin_addr.S_un.S_addr,payload,sizeof(payload),nullptr,response.data(),response.size(),1500)){const auto echo=reinterpret_cast<ICMP_ECHO_REPLY *>(response.data());if(echo->Status==IP_SUCCESS)delay=echo->RoundTripTime;}IcmpCloseHandle(handle);}break;}if(guard)QMetaObject::invokeMethod(guard,[guard,delay,epoch]{if(!guard)return;if(epoch==guard->m_routeEpoch){guard->m_latencies["router"]=delay>=0?QString::number(delay)+" ms":"未响应 ICMP";if(delay<0)emit guard->diagnostic("NetworkMeasurement","Gateway","默认网关未响应 ICMP 或没有可用网关");}--guard->m_measurements;guard->m_measurementState=guard->m_measurements?"正在测量":"测量完成";guard->publish();},Qt::QueuedConnection);});
#else
 m_latencies["router"]="未支持";
#endif
 publish();
}
