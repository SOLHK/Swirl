#include "TelemetryService.h"
#include "../network/HttpRequestPolicy.h"
#include "../app/StoragePaths.h"
#include "RouteObservation.h"
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
#include <QHash>
#include <QTcpSocket>
#include <cmath>
#include <algorithm>
#include <array>
#ifdef SWIRL_ACTIVITY_PERF_TRACE
#include <QThread>
#endif
#ifdef Q_OS_WIN
#include <winsock2.h>
#include <windows.h>
#include <iphlpapi.h>
#include <icmpapi.h>
#endif
namespace {
#ifdef SWIRL_ACTIVITY_PERF_TRACE
// Test-only, opt-in timings. Keep synchronous signal fan-out separate from
// accounting without changing the service layout or any publication path.
struct TelemetryIngestProfile;
thread_local TelemetryIngestProfile *activeTelemetryIngestProfile=nullptr;
struct TelemetryIngestProfile {
 QPointer<QObject> owner;
 TelemetryIngestProfile *previous;
 QElapsedTimer clock;
 qint64 publishNs=0;
 int publishDepth=0;
 bool enabled;
 explicit TelemetryIngestProfile(QObject *service)
  :owner(service),previous(activeTelemetryIngestProfile),enabled(service->property("_swirlProfileIngest").toBool()){
  if(enabled){activeTelemetryIngestProfile=this;clock.start();}
 }
 ~TelemetryIngestProfile(){
  if(!enabled)return;
  const auto totalNs=clock.nsecsElapsed();
  activeTelemetryIngestProfile=previous;
  // Dynamic-property writes happen after the measured interval, never per row.
  if(owner)owner->setProperty("_swirlLastIngestAccountingMs",double(totalNs-publishNs)/1000000.0);
  if(owner)owner->setProperty("_swirlLastIngestPublishMs",double(publishNs)/1000000.0);
 }
};
struct TelemetryPublishProfile {
 TelemetryIngestProfile *ingest;
 qint64 startedNs=0;
 bool outermost=false;
 explicit TelemetryPublishProfile(QObject *service)
  :ingest(activeTelemetryIngestProfile&&activeTelemetryIngestProfile->owner==service?activeTelemetryIngestProfile:nullptr){
  if(ingest){outermost=ingest->publishDepth++==0;if(outermost)startedNs=ingest->clock.nsecsElapsed();}
 }
 ~TelemetryPublishProfile(){
  if(!ingest)return;
  if(outermost)ingest->publishNs+=ingest->clock.nsecsElapsed()-startedNs;
  --ingest->publishDepth;
 }
};
struct TelemetryConnectionsProfile {
 QPointer<QObject> observer;
 explicit TelemetryConnectionsProfile(const QObject *service)
  :observer(service->property("_swirlPerformanceObserver").value<QObject *>()){
  if(!observer)return;
  const auto thread=QThread::currentThread();
  if(service->thread()!=thread||observer->thread()!=thread){observer.clear();return;}
  if(!QMetaObject::invokeMethod(observer.data(),"mark",Qt::DirectConnection,Q_ARG(int,12),Q_ARG(bool,true)))observer.clear();
 }
 ~TelemetryConnectionsProfile(){
  if(observer)QMetaObject::invokeMethod(observer.data(),"mark",Qt::DirectConnection,Q_ARG(int,12),Q_ARG(bool,false));
 }
};
#endif
qint64 nowMs(){return QDateTime::currentMSecsSinceEpoch();}
void add(QJsonObject &o,const QString &key,double value){o[key]=o.value(key).toDouble()+value;}
struct TelemetryGroupAccumulator {
 struct Totals {
  QJsonObject original;
  double up=0,down=0,count=0;
  bool countTouched=false;
 };
 QJsonObject original;
 QHash<QString,Totals> entries;
 qsizetype addedKeys=0;
 void accumulate(QString key,double up,double down,bool count){
  key=key.left(256);
  auto entry=entries.find(key);
  if(entry==entries.end()&&!original.contains(key)&&original.size()+addedKeys>=128){
   key=QStringLiteral("其他（分类上限）");entry=entries.find(key);
  }
  if(entry==entries.end()){
   const bool existing=original.contains(key);const auto row=original.value(key).toObject();
   entry=entries.insert(key,Totals{row,row.value("up").toDouble(),row.value("down").toDouble(),row.value("count").toDouble(),false});
   if(!existing)++addedKeys;
  }
  // Preserve the exact per-key addition order, including floating-point
  // rounding. Do not sum a separate delta and add it to the old total later.
  entry->up+=up;entry->down+=down;
  if(count){entry->count+=1;entry->countTouched=true;}
 }
 QJsonObject finish() const {
  auto group=original;
  for(auto entry=entries.cbegin();entry!=entries.cend();++entry){
   auto row=entry->original;row["up"]=entry->up;row["down"]=entry->down;
   if(entry->countTouched)row["count"]=entry->count;
   group[entry.key()]=row;
  }
  return group;
 }
};
}
TelemetryService::TelemetryService(QString path,bool networkMeasurements,QObject *parent):QObject(parent),m_path(path),m_networkEnabled(networkMeasurements){
 if(m_path.isEmpty())m_path=SwirlPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/telemetry.json";
 load();m_save.setInterval(5000);connect(&m_save,&QTimer::timeout,this,&TelemetryService::flush);m_save.start();
 m_measure.setInterval(60000);connect(&m_measure,&QTimer::timeout,this,[this]{if(m_networkEnabled&&m_status.apiHealthy)measureNetwork();});m_measure.start();
 m_stale.setInterval(1000);connect(&m_stale,&QTimer::timeout,this,[this]{if(sampled()!=m_publishedSampled||connectionsSampled()!=m_publishedConnectionsSampled)publish();});m_stale.start();
 m_nativeProbeDeadline.setSingleShot(true);m_nativeProbeDeadline.setInterval(10000);
 connect(&m_nativeProbeDeadline,&QTimer::timeout,this,[this]{finishNativeProbe({{"code","timeout"},{"state",QStringLiteral("Rust 节点检测超时")},{"success",false},{"metricType","http_headers"}});});
}
TelemetryService::~TelemetryService(){flush();}
bool TelemetryService::sampled() const{return m_status.apiHealthy&&m_status.trafficAt>0&&nowMs()-m_status.trafficAt<6000;}
bool TelemetryService::connectionsSampled() const{return m_status.apiHealthy&&m_status.connectionsAt>0&&nowMs()-m_status.connectionsAt<6000;}
void TelemetryService::publish(){
#ifdef SWIRL_ACTIVITY_PERF_TRACE
 TelemetryPublishProfile profile(this);
#endif
 m_publishedSampled=sampled();m_publishedConnectionsSampled=connectionsSampled();++m_revision;emit changed();
}
QString TelemetryService::formatBytes(double bytes) const {
 static const QStringList units={QStringLiteral("B"),QStringLiteral("KB"),QStringLiteral("MB"),QStringLiteral("GB"),QStringLiteral("TB")};int i=0;while(bytes>=1024&&i<4){bytes/=1024;++i;}
 return QString::number(bytes,'f',i?1:0)+" "+units[i];
}
int TelemetryService::activeConnections() const {int count=0;for(const auto &r:m_status.connections)if(!r.toMap().value("closed").toBool())++count;return count;}
int TelemetryService::activeProcesses() const {QSet<QString> names;for(const auto &r:m_status.connections){const auto row=r.toMap();if(row.value("closed").toBool())continue;const auto name=row.value("process").toString();if(!name.isEmpty()&&name!="未知进程")names.insert(name);}return names.size();}
int TelemetryService::activeDevices() const {
 QSet<QString> addresses;
 for(const auto &row:m_seen){
  if(row.value("status").toString()!=QStringLiteral("活动"))continue;
  const auto address=row.value("sourceIp").toString();
  if(!address.isEmpty()&&address!=QStringLiteral("127.0.0.1")&&address!=QStringLiteral("::1"))addresses.insert(address);
 }
 return addresses.size();
}
void TelemetryService::ingest(const ProxyEngine::Status &status){
#ifdef SWIRL_ACTIVITY_PERF_TRACE
 TelemetryIngestProfile profile(this);
#endif
 const auto epoch=QString::number(status.processId)+"/"+status.sessionId;
 if(status.processAlive&&m_epoch!=epoch){m_epoch=epoch;m_seen.clear();++m_connectionRevision;m_lastConnections=0;m_lastTraffic=0;m_lastUp=0;m_lastDown=0;m_externalIp.clear();m_latencies.clear();}
 const auto route=epoch+"/"+status.selectedNodeId+"/"+status.mode+"/"+QString::number(status.proxyPort)+"/"+QString::number(status.processAlive)+"/"+QString::number(status.apiHealthy)+"/"+QString::number(status.directSession)+"/"+status.configurationReceipt.value("applied_revision").toString()+"/"+status.configurationReceipt.value("generation").toString();
 if(route!=m_routeEpoch){m_routeEpoch=route;++m_routeGeneration;
  // Switching away and back still invalidates the old native measurement.
  if(m_nativeProbePending){m_nativeProbePending=false;m_nativeProbeObservedRunning=false;m_nativeProbeDeadline.stop();--m_measurements;}
  m_externalIp.clear();m_latencies.clear();m_failedMeasurements.clear();m_internetDiagnostic.clear();m_proxyDiagnostic.clear();m_latencies["proxy"]=status.processAlive&&!status.directSession?QStringLiteral("尚未测量"):QStringLiteral("未连接");m_measurementState=QStringLiteral("尚未测量");}
 m_status=status;
 if(m_nativeProbePending&&m_nativeProbeGeneration==m_routeGeneration&&status.probeRequestTag==m_nativeProbeTag){
  if(status.nodeBusy&&status.requestState==ProxyEngine::RequestState::InProgress)m_nativeProbeObservedRunning=true;
  if(!status.nodeBusy&&(status.requestState==ProxyEngine::RequestState::Succeeded||status.requestState==ProxyEngine::RequestState::Failed)){
   const bool ok=status.requestState==ProxyEngine::RequestState::Succeeded;
   finishNativeProbe({{"code",ok?QString("success"):status.probeFailureStage.isEmpty()?QString("native-probe"):status.probeFailureStage},
    {"state",ok?QString::number(status.latencyMs)+" ms":status.nodeMessage},{"success",ok},{"http",status.responseCode},{"elapsedMs",status.latencyMs},
    {"outboundConnectMs",status.probeOutboundConnectMs},{"originTlsMs",status.probeOriginTlsMs},{"metricType","http_headers"},
    {"routeVerified",ok},{"route",status.configurationReceipt.isEmpty()?QStringLiteral("当前所选 Rust 出站"):QStringLiteral("当前 Rust 策略")},{"detail",status.configurationReceipt.isEmpty()?QStringLiteral("Rust Core 测量所选出站至最终响应首部；不含界面刷新等待时间。"):QStringLiteral("Rust Core 根据当前策略测量至响应首部；本次实际出口见连接详情。")}});
  }
 }
 if(!status.apiHealthy){
  const auto state=status.processAlive?QStringLiteral("采样中断"):QStringLiteral("已结束");bool changed=false;
  for(auto it=m_seen.begin();it!=m_seen.end();++it)if(it->value("status")!="已结束"&&it->value("status")!=state){(*it)["status"]=state;changed=true;}
  if(changed)++m_connectionRevision;
  publish();return;
 }
 if(status.connectionsAt>m_lastConnections){
  ++m_connectionRevision;
  m_lastConnections=status.connectionsAt;const auto date=QDateTime::fromMSecsSinceEpoch(status.connectionsAt).date().toString(Qt::ISODate);
  auto day=m_days.value(date).toObject();
  // Earlier persisted days cannot be split by source after the fact.
  if(!day.value("sampled").toBool()&&!day.contains("proxyRankingComplete"))day["proxyRankingComplete"]=true;
  day["sampled"]=true;
  // Session counters are owned by this process. A reset starts a new baseline.
  const auto up=qMax<qint64>(0,status.uploadTotal),down=qMax<qint64>(0,status.downloadTotal);
  const auto totalDelta=(up>=m_lastUp?up-m_lastUp:up)+(down>=m_lastDown?down-m_lastDown:down);
  add(day,"up",up>=m_lastUp?up-m_lastUp:up);add(day,"down",down>=m_lastDown?down-m_lastDown:down);m_lastUp=up;m_lastDown=down;
  const auto time=QDateTime::fromMSecsSinceEpoch(status.connectionsAt).time();const auto bucketKey=QString::number(time.hour()*2+time.minute()/30);
  auto buckets=day.value("buckets").toObject(),bucket=buckets.value(bucketKey).toObject();bucket["sampled"]=true;add(bucket,"total",totalDelta);
  const QStringList groupKeys={"apps","domains","devices","nodes","categories","proxyApps","proxyDomains","proxyDevices","proxyNodes"};
  std::array<TelemetryGroupAccumulator,9> groups;
  for(int index=0;index<int(groups.size());++index)groups[index].original=day.value(groupKeys[index]).toObject();
  // Update native scalars in the original record order, then construct each
  // touched JSON row once. Hot categories no longer detach a row per connection.
  const auto aggregateGroup=[&](int index,const QString &key,double up,double down,bool count){groups[index].accumulate(key,up,down,count);};
  QSet<QString> active;
  QString previousRawTime,previousDisplayTime;bool havePreviousTime=false;
  for(const auto &value:status.connections){
   auto row=value.toMap();const auto id=row.value(QStringLiteral("id")).toString();if(id.isEmpty()||active.contains(id))continue;active.insert(id);
   if(row.contains(QStringLiteral("route")))row.insert(QStringLiteral("route"),SwirlRouteObservation::sanitized(QJsonObject::fromVariantMap(row.value(QStringLiteral("route")).toMap())));
   const auto old=m_seen.value(id);const auto u=row.value(QStringLiteral("uploadBytes")).toLongLong(),d=row.value(QStringLiteral("downloadBytes")).toLongLong();
   const auto ou=old.value(QStringLiteral("uploadBytes")).toLongLong(),od=old.value(QStringLiteral("downloadBytes")).toLongLong();
   const auto du=qMax<qint64>(0,u>=ou?u-ou:u),dd=qMax<qint64>(0,d>=od?d-od:d);
   const bool count=old.value(QStringLiteral("accountedDay")).toString()!=date;
   const auto process=row.value(QStringLiteral("process"),QStringLiteral("未知进程")).toString();
   const auto domain=row.value(QStringLiteral("host"),row.value(QStringLiteral("ip"))).toString();
   const auto sourceIp=row.value(QStringLiteral("sourceIp")).toString();
   const auto policy=row.value(QStringLiteral("policy")).toString();
   const auto category=row.value(QStringLiteral("category"),QStringLiteral("other")).toString();
   const bool proxy=category==QStringLiteral("proxy");
   const bool proxyCount=old.value(QStringLiteral("proxyAccountedDay")).toString()!=date;
   aggregateGroup(0,process,du,dd,count);
   aggregateGroup(1,domain,du,dd,count);
   if(!sourceIp.isEmpty())aggregateGroup(2,sourceIp,du,dd,count);
   aggregateGroup(3,policy,du,dd,count);
   aggregateGroup(4,category,du,dd,count);
   if(proxy){
    aggregateGroup(5,process,du,dd,proxyCount);
    aggregateGroup(6,domain,du,dd,proxyCount);
    if(!sourceIp.isEmpty())aggregateGroup(7,sourceIp,du,dd,proxyCount);
    aggregateGroup(8,policy,du,dd,proxyCount);
    add(bucket,"proxy",du+dd);
    row[QStringLiteral("proxyAccountedDay")]=date;
   }else if(old.contains(QStringLiteral("proxyAccountedDay")))row[QStringLiteral("proxyAccountedDay")]=old.value(QStringLiteral("proxyAccountedDay"));
   const auto interval=status.connectionsAt-old.value(QStringLiteral("lastSeen")).toLongLong();
   row[QStringLiteral("uploadRate")]=!old.isEmpty()&&interval>0?double(du)*1000/interval:0;row[QStringLiteral("downloadRate")]=!old.isEmpty()&&interval>0?double(dd)*1000/interval:0;
   row[QStringLiteral("accountedDay")]=date;row[QStringLiteral("lastSeen")]=status.connectionsAt;row[QStringLiteral("status")]=row.value(QStringLiteral("closed")).toBool()?QStringLiteral("已结束"):QStringLiteral("活动");
   row[QStringLiteral("up")]=formatBytes(u);row[QStringLiteral("down")]=formatBytes(d);
   const auto rawTime=row.value(QStringLiteral("time")).toString();
   if(!havePreviousTime||rawTime!=previousRawTime){
    previousRawTime=rawTime;previousDisplayTime=QDateTime::fromString(rawTime,Qt::ISODateWithMs).toLocalTime().toString(QStringLiteral("MM-dd HH:mm:ss"));havePreviousTime=true;
   }
   row[QStringLiteral("time")]=previousDisplayTime;
   m_seen[id]=row;
  }
  // Untouched groups retain their original missing/empty representation.
  for(int index=0;index<int(groups.size());++index)if(!groups[index].entries.isEmpty())day[groupKeys[index]]=groups[index].finish();
  for(auto it=m_seen.begin();it!=m_seen.end();++it)if(!active.contains(it.key()))(*it)["status"]="已结束";
  while(m_seen.size()>2000){auto oldest=m_seen.end();for(auto it=m_seen.begin();it!=m_seen.end();++it)if(!active.contains(it.key())&&(oldest==m_seen.end()||it->value("lastSeen").toLongLong()<oldest->value("lastSeen").toLongLong()))oldest=it;if(oldest==m_seen.end())break;m_seen.erase(oldest);}
  buckets[bucketKey]=bucket;day["buckets"]=buckets;
  m_days[date]=day;m_periodCache.clear();const auto oldest=QDate::currentDate().addDays(-31).toString(Qt::ISODate);for(const auto &key:m_days.keys())if(key<oldest)m_days.remove(key);while(m_days.size()>32)m_days.remove(m_days.keys().first());m_dirty=true;
 }
 if(status.trafficAt>m_lastTraffic){m_lastTraffic=status.trafficAt;m_history.append(QVariantMap{{"time",status.trafficAt},{"down",status.downloadRate},{"up",status.uploadRate}});while(m_history.size()>3600)m_history.removeFirst();m_dirty=true;}
 publish();
}
QVariantList TelemetryService::connections() const {
#ifdef SWIRL_ACTIVITY_PERF_TRACE
 // This ends after native return-value construction; QVariant-to-JS conversion
 // happens in the caller and is included only in the page's fetch/normalize span.
 TelemetryConnectionsProfile profile(this);
#endif
 QVariantList rows;for(const auto &r:m_seen)rows.append(r);std::sort(rows.begin(),rows.end(),[](const QVariant &a,const QVariant &b){return a.toMap().value("lastSeen").toLongLong()>b.toMap().value("lastSeen").toLongLong();});return rows;
}
QJsonObject TelemetryService::periodData(int period) const {
 if(period<0||period>3)period=0;
 const auto today=QDate::currentDate();
 if(m_periodCacheDate!=today){m_periodCache.clear();m_periodCacheDate=today;}
 if(m_periodCache.contains(period))return m_periodCache.value(period);
 QJsonObject out{{"proxyRankingComplete",true}};const auto start=period==1?today.addDays(-1):period==2?today.addDays(1-today.dayOfWeek()):period==3?QDate(today.year(),today.month(),1):today;
 const auto end=period==1?today.addDays(-1):today;
 for(const auto &key:m_days.keys()){const auto date=QDate::fromString(key,Qt::ISODate);if(date<start||date>end)continue;const auto d=m_days.value(key).toObject();if(d.value("sampled").toBool()){out["sampled"]=true;if(!d.value("proxyRankingComplete").toBool())out["proxyRankingComplete"]=false;}add(out,"up",d.value("up").toDouble());add(out,"down",d.value("down").toDouble());
  for(const auto &kind:{"apps","domains","nodes","devices","categories","proxyApps","proxyDomains","proxyNodes","proxyDevices"}){auto group=out.value(kind).toObject();const auto entries=d.value(kind).toObject();for(const auto &name:entries.keys()){auto sum=group.value(name).toObject();const auto row=entries.value(name).toObject();for(const auto &field:{"up","down","count"})add(sum,field,row.value(field).toDouble());group[name]=sum;}out[kind]=group;}
 }m_periodCache.insert(period,out);return out;
}
QVariantMap TelemetryService::summary(int period) const {auto d=periodData(period);return {{"sampled",d.value("sampled").toBool()},{"up",d.value("up").toDouble()},{"down",d.value("down").toDouble()},{"total",d.value("up").toDouble()+d.value("down").toDouble()},{"domains",d.value("domains").toObject().size()},{"apps",d.value("apps").toObject().size()}};}
bool TelemetryService::proxyRankingAvailable(int period) const {return periodData(period).value("proxyRankingComplete").toBool();}
QVariantList TelemetryService::ranking(const QString &kind,int period,int limit,bool proxyOnly) const {
 if(kind!="apps"&&kind!="domains"&&kind!="nodes"&&kind!="devices")return {};
 const auto data=periodData(period);
 if(proxyOnly&&!data.value("proxyRankingComplete").toBool())return {};
 const auto group=proxyOnly?QStringLiteral("proxy")+kind.left(1).toUpper()+kind.mid(1):kind;
 const auto entries=data.value(group).toObject();QVariantList result;
 const auto total=proxyOnly?data.value("categories").toObject().value("proxy").toObject().value("up").toDouble()+data.value("categories").toObject().value("proxy").toObject().value("down").toDouble():data.value("up").toDouble()+data.value("down").toDouble();
 for(const auto &name:entries.keys()){const auto r=entries.value(name).toObject();const auto up=r.value("up").toDouble(),down=r.value("down").toDouble();result.append(QVariantMap{{"id",name},{"name",name},{"upload",formatBytes(up)},{"download",formatBytes(down)},{"uploadBytes",up},{"downloadBytes",down},{"value",formatBytes(up+down)},{"total",up+down},{"connections",r.value("count").toDouble()},{"percent",total>0?QString::number(100*(up+down)/total,'f',1)+"%":"0%"},{"mark",name.left(1)},{"color","#596273"}});}
 QHash<QString,double> speeds;
 if(connectionsSampled())for(const auto &value:m_seen){
  if(value.value("status")!="活动"||(proxyOnly&&value.value("category")!="proxy"))continue;
  const auto key=kind=="apps"?value.value("process"):kind=="domains"?value.value("host",value.value("ip")):kind=="devices"?value.value("sourceIp"):value.value("policy");
  speeds[key.toString()]+=value.value("uploadRate").toDouble()+value.value("downloadRate").toDouble();
 }
 for(auto &entry:result){auto row=entry.toMap();const auto speed=speeds.value(row.value("name").toString());row["speed"]=speed;row["speedText"]=formatBytes(speed)+"/s";row["kind"]=kind;entry=row;}
 std::sort(result.begin(),result.end(),[](const QVariant &a,const QVariant &b){return a.toMap().value("total").toDouble()>b.toMap().value("total").toDouble();});if(limit!=0)while(result.size()>qBound(1,limit,512))result.removeLast();return result;
}
QVariantList TelemetryService::distribution(int period) const {
 const auto d=periodData(period),cats=d.value("categories").toObject();double measured=0;for(const auto &v:cats){const auto r=v.toObject();measured+=r.value("up").toDouble()+r.value("down").toDouble();}
 const auto total=qMax(measured,d.value("up").toDouble()+d.value("down").toDouble());QVariantList rows;
 const QStringList keys={"proxy","direct","reject","other"},names={"代理流量","直连流量","阻止请求","其他流量"},colors={"#0069D9","#00852A","#976217","#596273"};
 for(int i=0;i<4;++i){const auto r=cats.value(keys[i]).toObject();double bytes=r.value("up").toDouble()+r.value("down").toDouble();if(i==3)bytes+=qMax(0.0,total-measured);const bool known=d.value("sampled").toBool();rows.append(QVariantMap{{"name",names[i]},{"tint",colors[i]},{"bytes",bytes},{"value",!known?QStringLiteral("未采集"):i==2?QString::number(r.value("count").toInt())+" 次":formatBytes(bytes)},{"percent",known?QString::number(total>0?100*bytes/total:0,'f',1)+"%":"—"}});}return rows;
}
QVariantList TelemetryService::history(const QString &series,int seconds,bool normalized) const {QVariantList out;double maximum=1;const auto cutoff=nowMs()-qBound(60,seconds,86400)*1000LL;for(const auto &v:m_history){const auto r=v.toMap();if(r.value("time").toLongLong()<cutoff)continue;const auto value=series=="total"?r.value("up").toDouble()+r.value("down").toDouble():r.value(series).toDouble();out.append(value);maximum=qMax(maximum,value);}if(normalized)for(auto &v:out)v=v.toDouble()/maximum;return out;}
QVariantList TelemetryService::historyPoints(const QString &series,int seconds) const {QVariantList out;const auto cutoff=nowMs()-qBound(60,seconds,86400)*1000LL;for(const auto &v:m_history){const auto row=v.toMap();if(row.value("time").toLongLong()<cutoff)continue;const auto value=series=="total"?row.value("up").toDouble()+row.value("down").toDouble():row.value(series).toDouble();out.append(QVariantMap{{"time",row.value("time")},{"value",value}});}return out;}
QVariantList TelemetryService::dailyTraffic(bool proxyOnly) const {
 const auto date=QDate::currentDate();const auto buckets=m_days.value(date.toString(Qt::ISODate)).toObject().value("buckets").toObject();QVariantList rows;
 for(int i=0;i<48;++i){const auto bucket=buckets.value(QString::number(i)).toObject();rows.append(QVariantMap{{"time",QDateTime(date,QTime(i/2,(i%2)*30)).toMSecsSinceEpoch()},{"sampled",bucket.value("sampled").toBool()},{"value",bucket.value(proxyOnly?"proxy":"total").toDouble()}});}return rows;
}
QVariantList TelemetryService::periodTraffic(int period,bool proxyOnly) const {
 if(period==0)return dailyTraffic(proxyOnly);
 if(period!=3)return {};
 const auto today=QDate::currentDate(),first=QDate(today.year(),today.month(),1);
 QVariantList rows;
 for(auto date=first;date<=today;date=date.addDays(1)){
  const auto day=m_days.value(date.toString(Qt::ISODate)).toObject();
  double value=day.value("up").toDouble()+day.value("down").toDouble();
  if(proxyOnly){
   value=0;
   const auto buckets=day.value("buckets").toObject();
   for(const auto &bucket:buckets)value+=bucket.toObject().value("proxy").toDouble();
  }
  rows.append(QVariantMap{{"time",QDateTime(date,QTime(0,0)).toMSecsSinceEpoch()},
                          {"sampled",day.value("sampled").toBool()},{"value",value}});
 }
 return rows;
}
void TelemetryService::load(){QFile file(m_path);if(!file.exists())return;if(!file.open(QIODevice::ReadOnly)||file.size()>16*1024*1024){m_storageError="监控历史无法读取或超过大小限制";return;}QJsonParseError e;const auto doc=QJsonDocument::fromJson(file.readAll(),&e);if(e.error!=QJsonParseError::NoError||doc.object().value("schema").toInt()!=1){m_storageError="监控历史格式无效";return;}m_days=doc.object().value("days").toObject();m_history=doc.object().value("history").toArray().toVariantList();while(m_history.size()>3600)m_history.removeFirst();}
void TelemetryService::flush(){if(!m_dirty)return;QDir().mkpath(QFileInfo(m_path).absolutePath());QSaveFile file(m_path);const auto bytes=QJsonDocument(QJsonObject{{"schema",1},{"days",m_days},{"history",QJsonArray::fromVariantList(m_history)}}).toJson(QJsonDocument::Compact);if(!file.open(QIODevice::WriteOnly)||file.write(bytes)!=bytes.size()||!file.commit()){m_storageError="监控历史保存失败";emit diagnostic("Telemetry","StorageWrite",m_storageError);publish();return;}m_dirty=false;}
void TelemetryService::reportMeasurement(const QString &key,bool ok,const QString &message){
 // Periodic probes describe a continuing condition, not a new incident each minute.
 if(ok){m_failedMeasurements.remove(key);return;}
 if(m_failedMeasurements.contains(key))return;
 m_failedMeasurements.insert(key);emit diagnostic("NetworkMeasurement",key,message);
}
void TelemetryService::recordInternetResult(int error,int http,bool proxy,qint64 elapsed) {
 QString code,state,advice;
 const bool success=error==int(QNetworkReply::NoError)&&http>=200&&http<300;
 if(success){code="ok";state=QStringLiteral("请求成功");advice=proxy?QStringLiteral("HTTPS 请求经 Swirl 当前策略完成；耗时包含连接、TLS 与目标响应，仅代表本次检测。"):QStringLiteral("直连 HTTPS 请求成功；耗时包含连接、TLS 与目标响应，未验证代理节点。");}
 else if(m_status.error==ProxyEngine::Error::SelectionFailed){code="policy";state=QStringLiteral("策略选择失败");advice=QStringLiteral("检查所选节点和代理策略。");}
 else if(proxy && m_status.nodeHealth==ProxyEngine::NodeHealth::Unavailable){code="node";state=QStringLiteral("节点不可用");advice=QStringLiteral("尝试测速或切换节点，再检测实际请求。");}
 else if(error==int(QNetworkReply::SslHandshakeFailedError)){code="tls";state=QStringLiteral("TLS 握手失败");advice=QStringLiteral("检查证书信任与系统时间；不要关闭证书校验。");}
 else if(error==int(QNetworkReply::HostNotFoundError)||error==int(QNetworkReply::ProxyNotFoundError)){code="dns";state=QStringLiteral("DNS 解析失败");advice=QStringLiteral("检查系统 DNS 与 Swirl DNS 配置。");}
 else if(error==int(QNetworkReply::TimeoutError)||error==int(QNetworkReply::OperationCanceledError)){code="timeout";state=QStringLiteral("检测超时");advice=QStringLiteral("检查网络、节点可达性或稍后重试。");}
 else if(proxy && (error==int(QNetworkReply::ProxyConnectionRefusedError)||error==int(QNetworkReply::ConnectionRefusedError))){code="proxy-port";state=QStringLiteral("本地代理端口不可用");advice=QStringLiteral("确认 Rust Core 正在运行，且本地代理端口正常监听。");}
 else if(!proxy && error==int(QNetworkReply::NetworkSessionFailedError)){code="offline";state=QStringLiteral("本机网络不可用");advice=QStringLiteral("检查 Wi-Fi、网线或系统网络连接。");}
 else if(!proxy && m_status.processAlive && !m_status.apiHealthy){code="proxy-unconnected";state=QStringLiteral("代理尚未就绪");advice=QStringLiteral("确认 Rust Core 状态健康，等待连接完成或检查内核错误。");}
 else if(http>=300){code="service";state=QStringLiteral("检测服务响应异常");advice=QStringLiteral("检测服务未返回成功响应，可使用节点详情中的自选 URL 测试。");}
 else {code="outbound";state=QStringLiteral("出站请求失败");advice=QStringLiteral("检查网络和节点；路由、DNS 有延迟不代表 HTTPS 出站成功。");}
 m_internetDiagnostic["code"]=code;m_internetDiagnostic["state"]=state;m_internetDiagnostic["advice"]=advice;
 m_internetDiagnostic["route"]=proxy?QStringLiteral("Swirl 本地代理策略"):QStringLiteral("直连");
 m_internetDiagnostic["http"]=http;m_internetDiagnostic["networkError"]=error;m_internetDiagnostic["elapsedMs"]=elapsed;
 m_internetDiagnostic["success"]=success;
 m_latencies["internet"]=success?QString::number(elapsed)+" ms":state;
}
void TelemetryService::finishMeasurement(quint64 generation){
 --m_measurements;
 if(generation==m_routeGeneration)m_measurementState=m_measurements?QStringLiteral("正在测量"):QStringLiteral("测量完成");
 publish();
}
void TelemetryService::measureHttp(const QString &key,const QUrl &url,bool throughProxy,bool ip){
 auto network=new QNetworkAccessManager(this);network->setProxy(throughProxy?QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",m_status.proxyPort):QNetworkProxy(QNetworkProxy::NoProxy));QNetworkRequest req(url);
 SwirlNetwork::applyHttp1OnlyPolicy(req);
 req.setTransferTimeout(8000);req.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);req.setAttribute(QNetworkRequest::CacheLoadControlAttribute,QNetworkRequest::AlwaysNetwork);req.setRawHeader("Connection","close");auto timer=std::make_shared<QElapsedTimer>();timer->start();auto reply=network->get(req);auto deadline=new QTimer(reply);deadline->setSingleShot(true);connect(deadline,&QTimer::timeout,reply,&QNetworkReply::abort);deadline->start(9000);const auto epoch=m_routeGeneration;
 connect(reply,&QNetworkReply::readyRead,this,[reply]{if(reply->bytesAvailable()>4096)reply->abort();});
 connect(reply,&QNetworkReply::finished,this,[this,network,reply,timer,key,ip,epoch,throughProxy]{const auto code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();const bool ok=reply->error()==QNetworkReply::NoError&&code>=200&&code<300;if(epoch==m_routeGeneration){if(key=="internet")recordInternetResult(int(reply->error()),code,throughProxy,timer->elapsed());if(ip){const QString candidate=QString::fromUtf8(reply->readAll()).trimmed();m_externalIp=ok&&!QHostAddress(candidate).isNull()?candidate:QString();}else if(key!="internet")m_latencies[key]=ok?QString::number(timer->elapsed())+" ms":"检测失败";reportMeasurement(key,ok,QString("测量失败，HTTP %1，网络错误 %2").arg(code).arg(int(reply->error())));}reply->deleteLater();network->deleteLater();finishMeasurement(epoch);});
}
void TelemetryService::measureProxy(){
 if(m_nativeProbePending)return;
 if(!m_status.apiHealthy||!m_status.processAlive||m_status.directSession||(m_status.selectedNodeId.isEmpty()&&m_status.configurationReceipt.isEmpty())){m_latencies["proxy"]=QStringLiteral("未连接");return;}
 if(m_status.nodeBusy){m_latencies["proxy"]=QStringLiteral("节点检测进行中");return;}
 ++m_measurements;m_nativeProbePending=true;m_nativeProbeObservedRunning=false;m_nativeProbeGeneration=m_routeGeneration;
 m_latencies["proxy"]=QStringLiteral("测量中");m_proxyDiagnostic={{"code","measuring"},{"metricType","http_headers"},{"route",m_status.configurationReceipt.isEmpty()?QStringLiteral("当前所选 Rust 出站"):QStringLiteral("当前 Rust 策略")}};
 if(++m_nativeProbeTag==0)++m_nativeProbeTag;
 m_nativeProbeDeadline.start();emit nativeProbeRequested(m_internetProbe,m_nativeProbeTag);
}
void TelemetryService::rejectNativeProbe(quint64 tag,const QString &code){
 if(m_nativeProbePending&&tag==m_nativeProbeTag)finishNativeProbe({{"code",code},{"state",code=="probe-busy"?QStringLiteral("另一个节点检测正在进行"):QStringLiteral("Rust 节点检测不可用")},{"success",false},{"metricType","http_headers"}});
}
void TelemetryService::finishNativeProbe(const QVariantMap &result){
 if(!m_nativeProbePending)return;
 m_nativeProbePending=false;m_nativeProbeObservedRunning=false;m_nativeProbeDeadline.stop();
 const auto generation=m_nativeProbeGeneration;
 if(generation==m_routeGeneration){m_proxyDiagnostic=result;m_latencies["proxy"]=result.value("state");reportMeasurement("proxy",result.value("success").toBool(),result.value("code").toString());}
 finishMeasurement(generation);
}
void TelemetryService::measureNetwork(){
 if(!m_networkEnabled||m_measurements)return;m_measurementState="正在测量";m_measurements=2;
 // A fixed direct TCP handshake bypassed the selected proxy and falsely
 // reported failure on networks blocking that endpoint. Test real HTTPS
 // through the active local proxy policy, or explicitly report a direct route.
 const bool throughProxy=m_status.apiHealthy && m_status.proxyPort>0;
 m_internetDiagnostic={{"code","measuring"},{"state",QStringLiteral("正在检测")},{"route",throughProxy?QStringLiteral("Swirl 本地代理策略"):QStringLiteral("直连")},{"engineRunning",m_status.processAlive},{"apiHealthy",m_status.apiHealthy},{"proxyPort",m_status.proxyPort},{"selectedNode",!m_status.selectedNodeId.isEmpty()},{"directSession",m_status.directSession}};
 measureHttp("internet",m_internetProbe,throughProxy);
 if(throughProxy&&!m_status.directSession)measureProxy();
 else m_latencies["proxy"]=QStringLiteral("未连接");
 if(m_status.apiHealthy&&m_status.proxyPort>0){++m_measurements;measureHttp("exit",QUrl("https://api.ipify.org"),true,true);}
 auto dns=new QDnsLookup(QDnsLookup::A,"www.microsoft.com",this);auto elapsed=std::make_shared<QElapsedTimer>();elapsed->start();const auto epoch=m_routeGeneration;
 auto dnsDeadline=new QTimer(dns);dnsDeadline->setSingleShot(true);connect(dnsDeadline,&QTimer::timeout,dns,&QDnsLookup::abort);dnsDeadline->start(8000);
 connect(dns,&QDnsLookup::finished,this,[this,dns,elapsed,epoch]{if(epoch==m_routeGeneration){const bool ok=dns->error()==QDnsLookup::NoError&&!dns->hostAddressRecords().isEmpty();m_latencies["dns"]=ok?QString::number(elapsed->elapsed())+" ms":"解析失败";reportMeasurement("DNS",ok,QString("DNS 测量失败，错误 %1").arg(int(dns->error())));}dns->deleteLater();finishMeasurement(epoch);});dns->lookup();
#ifdef Q_OS_WIN
 ++m_measurements;QPointer<TelemetryService> guard(this);QThreadPool::globalInstance()->start([guard,epoch]{int delay=-1;ULONG size=16384;QByteArray buffer(size,0);ULONG result=GetAdaptersAddresses(AF_INET,GAA_FLAG_INCLUDE_GATEWAYS,nullptr,reinterpret_cast<IP_ADAPTER_ADDRESSES *>(buffer.data()),&size);if(result==ERROR_BUFFER_OVERFLOW){buffer.resize(size);result=GetAdaptersAddresses(AF_INET,GAA_FLAG_INCLUDE_GATEWAYS,nullptr,reinterpret_cast<IP_ADAPTER_ADDRESSES *>(buffer.data()),&size);}if(result==NO_ERROR)for(auto a=reinterpret_cast<IP_ADAPTER_ADDRESSES *>(buffer.data());a;a=a->Next){if(a->OperStatus!=IfOperStatusUp||a->IfType==IF_TYPE_SOFTWARE_LOOPBACK||!a->FirstGatewayAddress)continue;const auto address=reinterpret_cast<sockaddr_in *>(a->FirstGatewayAddress->Address.lpSockaddr);HANDLE handle=IcmpCreateFile();if(handle!=INVALID_HANDLE_VALUE){char payload[]="Swirl gateway latency";QByteArray response(sizeof(ICMP_ECHO_REPLY)+sizeof(payload)+32,0);if(IcmpSendEcho(handle,address->sin_addr.S_un.S_addr,payload,sizeof(payload),nullptr,response.data(),response.size(),1500)){const auto echo=reinterpret_cast<ICMP_ECHO_REPLY *>(response.data());if(echo->Status==IP_SUCCESS)delay=echo->RoundTripTime;}IcmpCloseHandle(handle);}break;}if(guard)QMetaObject::invokeMethod(guard,[guard,delay,epoch]{if(!guard)return;if(epoch==guard->m_routeGeneration){guard->m_latencies["router"]=delay>=0?QString::number(delay)+" ms":"未响应 ICMP";guard->reportMeasurement("Gateway",delay>=0,"默认网关未响应 ICMP 或没有可用网关");}guard->finishMeasurement(epoch);},Qt::QueuedConnection);});
#else
 m_latencies["router"]="未支持";
#endif
 publish();
}
