#include "engine/TelemetryService.h"
#include "engine/EngineController.h"
#include <QElapsedTimer>
#include <QScopeGuard>
#include <QTest>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QDateTime>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QTcpServer>
#include <QTcpSocket>
#include "ControlledNetwork.h"
#include "engine/ThreadedEngine.h"
#include <QUuid>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QFile>
class PulseEngine final:public ProxyEngine {
public:
 Status current;
 void start(const EngineStartOptions &) override {}
 void stop() override {}
 void refresh() override {emit statusChanged();}
 void selectNode(const QString &) override {}
 void probeNode(const QUrl &) override {}
 Status status() const override {return current;}
 QString configurationSummary() const override {return {};}
};
class TelemetryTests:public QObject {
 Q_OBJECT
 ProxyEngine::Status sample(qint64 time,int up,int down){ProxyEngine::Status s;s.processAlive=true;s.processId=1;s.apiHealthy=true;s.connectionsAt=time;s.trafficAt=time;s.uploadTotal=up;s.downloadTotal=down;s.uploadRate=up;s.downloadRate=down;s.connections={QVariantMap{{"id","connection-a"},{"host","fixture.test"},{"process","fixture.exe"},{"policy","DIRECT"},{"category","direct"},{"uploadBytes",up},{"downloadBytes",down},{"time",QDateTime::fromMSecsSinceEpoch(time).toString(Qt::ISODateWithMs)}}};return s;}
private slots:
 void batchedGroupsMatchLegacyAccountingAtCardinalityAndSessionBoundaries(){
  QTemporaryDir temp;const auto path=temp.filePath("batched-groups.json");TelemetryService model(path,false);
  const QStringList kinds={"apps","domains","devices","nodes","categories","proxyApps","proxyDomains","proxyDevices","proxyNodes"};
  // Keep the former per-record algorithm as an independent reference. It
  // deliberately writes each group back immediately, unlike production's batch.
  const auto legacyAdd=[](QJsonObject &object,const QString &key,double value){object[key]=object.value(key).toDouble()+value;};
  const auto legacyAggregate=[&](QJsonObject &day,const QString &kind,QString key,double up,double down,bool count){
   key=key.left(256);auto group=day.value(kind).toObject();if(!group.contains(key)&&group.size()>=128)key=QStringLiteral("其他（分类上限）");
   auto row=group.value(key).toObject();legacyAdd(row,"up",up);legacyAdd(row,"down",down);if(count)legacyAdd(row,"count",1);group[key]=row;day[kind]=group;
  };
  QSignalSpy changes(&model,&TelemetryService::changed);
  const auto verify=[&](const ProxyEngine::Status &status){
   auto expected=model.m_days;auto history=model.m_history;
   const bool newEpoch=status.processAlive&&model.m_epoch!=QString::number(status.processId)+"/"+status.sessionId;
   const auto previous=newEpoch?QHash<QString,QVariantMap>():model.m_seen;
   const auto lastConnections=newEpoch?0:model.m_lastConnections,lastTraffic=newEpoch?0:model.m_lastTraffic;
   const auto lastUp=newEpoch?0:model.m_lastUp,lastDown=newEpoch?0:model.m_lastDown;
   const auto date=QDateTime::fromMSecsSinceEpoch(status.connectionsAt).date().toString(Qt::ISODate);
   if(status.apiHealthy&&status.connectionsAt>lastConnections){
    auto day=expected.value(date).toObject();if(!day.value("sampled").toBool()&&!day.contains("proxyRankingComplete"))day["proxyRankingComplete"]=true;day["sampled"]=true;
    const auto up=qMax<qint64>(0,status.uploadTotal),down=qMax<qint64>(0,status.downloadTotal);
    const auto du=up>=lastUp?up-lastUp:up,dd=down>=lastDown?down-lastDown:down;
    legacyAdd(day,"up",du);legacyAdd(day,"down",dd);
    const auto time=QDateTime::fromMSecsSinceEpoch(status.connectionsAt).time();const auto bucketKey=QString::number(time.hour()*2+time.minute()/30);
    auto buckets=day.value("buckets").toObject(),bucket=buckets.value(bucketKey).toObject();bucket["sampled"]=true;legacyAdd(bucket,"total",du+dd);
    QSet<QString> seen;
    for(const auto &value:status.connections){
     const auto row=value.toMap();const auto id=row.value("id").toString();if(id.isEmpty()||seen.contains(id))continue;seen.insert(id);
     const auto old=previous.value(id);const auto u=row.value("uploadBytes").toLongLong(),d=row.value("downloadBytes").toLongLong();
     const auto ou=old.value("uploadBytes").toLongLong(),od=old.value("downloadBytes").toLongLong();
     const auto rowUp=qMax<qint64>(0,u>=ou?u-ou:u),rowDown=qMax<qint64>(0,d>=od?d-od:d);
     const bool count=old.value("accountedDay").toString()!=date,proxyCount=old.value("proxyAccountedDay").toString()!=date;
     legacyAggregate(day,"apps",row.value("process","未知进程").toString(),rowUp,rowDown,count);
     legacyAggregate(day,"domains",row.value("host",row.value("ip")).toString(),rowUp,rowDown,count);
     if(!row.value("sourceIp").toString().isEmpty())legacyAggregate(day,"devices",row.value("sourceIp").toString(),rowUp,rowDown,count);
     legacyAggregate(day,"nodes",row.value("policy").toString(),rowUp,rowDown,count);
     legacyAggregate(day,"categories",row.value("category","other").toString(),rowUp,rowDown,count);
     if(row.value("category").toString()=="proxy"){
      legacyAggregate(day,"proxyApps",row.value("process","未知进程").toString(),rowUp,rowDown,proxyCount);
      legacyAggregate(day,"proxyDomains",row.value("host",row.value("ip")).toString(),rowUp,rowDown,proxyCount);
      if(!row.value("sourceIp").toString().isEmpty())legacyAggregate(day,"proxyDevices",row.value("sourceIp").toString(),rowUp,rowDown,proxyCount);
      legacyAggregate(day,"proxyNodes",row.value("policy").toString(),rowUp,rowDown,proxyCount);legacyAdd(bucket,"proxy",rowUp+rowDown);
     }
    }
    buckets[bucketKey]=bucket;day["buckets"]=buckets;expected[date]=day;
   }
   if(status.apiHealthy&&status.trafficAt>lastTraffic)history.append(QVariantMap{{"time",status.trafficAt},{"down",status.downloadRate},{"up",status.uploadRate}});
   const auto notifications=changes.size();const int revision=model.revision();model.ingest(status);
   QCOMPARE(changes.size(),notifications+1);QCOMPARE(model.revision(),revision+1);
   QCOMPARE(model.m_days,expected);QCOMPARE(model.m_history,history);
   // Public rankings must expose the same complete numeric group values,
   // including the overflow bucket; the result order is intentionally irrelevant.
   const int period=QDateTime::fromMSecsSinceEpoch(status.connectionsAt).date()==QDate::currentDate()?0:1;
   for(const auto &kind:{QString("apps"),QString("domains"),QString("devices"),QString("nodes")})for(bool proxyOnly:{false,true}){
    const auto groupKey=proxyOnly?QString("proxy")+kind.left(1).toUpper()+kind.mid(1):kind;
    const auto group=expected.value(date).toObject().value(groupKey).toObject();const auto ranking=model.ranking(kind,period,0,proxyOnly);QCOMPARE(ranking.size(),group.size());
    for(const auto &value:ranking){const auto row=value.toMap();const auto key=row.value("id").toString();QVERIFY(group.contains(key));const auto entry=group.value(key).toObject();
     QCOMPARE(row.value("uploadBytes").toDouble(),entry.value("up").toDouble());QCOMPARE(row.value("downloadBytes").toDouble(),entry.value("down").toDouble());QCOMPARE(row.value("connections").toDouble(),entry.value("count").toDouble());
    }
   }
   model.flush();QFile saved(path);QVERIFY(saved.open(QIODevice::ReadOnly));const auto document=QJsonDocument::fromJson(saved.readAll()).object();
   QCOMPARE(document.value("days").toObject(),expected);QCOMPARE(document.value("history").toArray(),QJsonArray::fromVariantList(history));
  };
  const auto yesterday=QDate::currentDate().addDays(-1);const auto firstTime=QDateTime(yesterday,QTime(12,0)).toMSecsSinceEpoch();
  const auto firstDay=yesterday.toString(Qt::ISODate);model.m_days[firstDay]=QJsonObject{{"devices",QJsonObject{}}};
  auto status=sample(firstTime,0,0);status.sessionId="batch-reference";status.connections.clear();verify(status);
  const auto emptyDay=model.m_days.value(firstDay).toObject();QVERIFY(emptyDay.contains("devices"));QVERIFY(emptyDay.value("devices").toObject().isEmpty());
  for(const auto &kind:kinds)if(kind!="devices")QVERIFY(!emptyDay.contains(kind));
  const auto record=[&](int index){return QVariantMap{{"id",QString("edge-%1").arg(index)},{"process",QString("process-%1").arg(index)},{"host",QString("host-%1.test").arg(index)},
   {"sourceIp",QString("2001:db8::%1").arg(index+1,0,16)},{"ip","198.51.100.8"},{"policy",QString("node-%1").arg(index)},{"category","proxy"},{"uploadBytes",index+1},{"downloadBytes",2*index+3},{"time",QDateTime::fromMSecsSinceEpoch(firstTime).toString(Qt::ISODateWithMs)}};};
  const auto advance=[&](qint64 time){status.connectionsAt=status.trafficAt=time;status.uploadTotal=status.downloadTotal=0;QSet<QString> ids;
   for(const auto &value:status.connections){const auto row=value.toMap();const auto id=row.value("id").toString();if(id.isEmpty()||ids.contains(id))continue;ids.insert(id);status.uploadTotal+=row.value("uploadBytes").toLongLong();status.downloadTotal+=row.value("downloadBytes").toLongLong();}
   verify(status);
  };
  for(int index=0;index<128;++index)status.connections.append(record(index));advance(firstTime+1000);
  for(const auto &kind:kinds)if(kind!="categories")QCOMPARE(model.m_days.value(firstDay).toObject().value(kind).toObject().size(),128);
  status.connections.append(record(128));advance(firstTime+2000);
  const auto overflow=model.m_days.value(firstDay).toObject().value("apps").toObject();QCOMPARE(overflow.size(),129);
  QCOMPARE(overflow.value(QStringLiteral("其他（分类上限）")).toObject().value("count").toInt(),1);
  auto duplicate=record(0);duplicate["process"]="must-not-appear";duplicate["uploadBytes"]=999999;status.connections.append(duplicate);
  auto invalid=record(999);invalid["id"]="";status.connections.append(invalid);
  auto noSource=record(129);noSource.remove("sourceIp");noSource.remove("process");noSource.remove("host");noSource["category"]="direct";status.connections.append(noSource);advance(firstTime+3000);
  const QString longKey(256,QChar(0x4e2d));auto longA=record(2001),longB=record(2002);
  longA["process"]=longKey+"A";longB["process"]=longKey+"B";longA["category"]=longB["category"]="direct";longA.remove("sourceIp");longB.remove("sourceIp");
  status.connections={longA,longB};const auto todayTime=QDateTime(QDate::currentDate(),QTime(12,0)).toMSecsSinceEpoch();advance(todayTime);
  const auto today=QDate::currentDate().toString(Qt::ISODate);const auto todayDay=model.m_days.value(today).toObject();
  QCOMPARE(todayDay.value("apps").toObject().size(),1);QCOMPARE(todayDay.value("apps").toObject().value(longKey).toObject().value("count").toInt(),2);
  QVERIFY(!todayDay.contains("devices"));for(const auto &kind:{"proxyApps","proxyDomains","proxyDevices","proxyNodes"})QVERIFY(!todayDay.contains(kind));
  status.connections.clear();for(int index=0;index<2000;++index){auto row=record(index);if(index%2)row["category"]="direct";if(index%11==0)row.remove("sourceIp");status.connections.append(row);}advance(todayTime+1000);
  verify(status); // Identical heartbeat retains every value but still publishes.
  for(auto &value:status.connections){auto row=value.toMap();row["uploadBytes"]=row.value("uploadBytes").toInt()+7;row["downloadBytes"]=row.value("downloadBytes").toInt()+13;value=row;}advance(todayTime+2000);
  for(auto &value:status.connections){auto row=value.toMap();row["uploadBytes"]=5;row["downloadBytes"]=10;value=row;}advance(todayTime+3000);
  status.processId=2;status.sessionId="batch-reference-restarted";advance(todayTime+4000);
  TelemetryService restored(path,false);QCOMPARE(restored.m_days,model.m_days);QCOMPARE(restored.m_history,model.m_history);
  for(int period=0;period<4;++period){QCOMPARE(restored.summary(period),model.summary(period));QCOMPARE(restored.distribution(period),model.distribution(period));}
 }
 void completeSourceRankingKeepsRecordedRowsAndNumericBytes(){
  QTemporaryDir directory;const auto path=directory.filePath("ranking.json");QJsonObject domains;
  for(int i=0;i<600;++i)domains.insert(QString("source-%1.test").arg(i),QJsonObject{{"up",i},{"down",i*2},{"count",1}});
  QFile fixture(path);QVERIFY(fixture.open(QIODevice::WriteOnly));
  fixture.write(QJsonDocument(QJsonObject{{"schema",1},{"days",QJsonObject{{QDate::currentDate().toString(Qt::ISODate),QJsonObject{{"sampled",true},{"up",179700},{"down",359400},{"proxyRankingComplete",true},{"domains",domains}}}}}}).toJson());fixture.close();
  TelemetryService model(path,false);
  const auto complete=model.ranking("domains",0,0);QCOMPARE(complete.size(),600);
  const auto first=complete.first().toMap();QCOMPARE(first.value("uploadBytes").toDouble(),599.0);QCOMPARE(first.value("downloadBytes").toDouble(),1198.0);QCOMPARE(first.value("total").toDouble(),1797.0);
  QCOMPARE(model.ranking("domains").size(),50);QCOMPARE(model.ranking("domains",0,10000).size(),512);QCOMPARE(model.ranking("domains",0,-1).size(),1);
  QCOMPARE(model.ranking("domains",0,0,true).size(),0);model.flush();
  TelemetryService restored(path,false);QCOMPARE(restored.ranking("domains",0,0).size(),600);
 }
 void actualRouteObservationKeepsStableIdentityAndDropsPrivateFields(){
  QTemporaryDir directory;TelemetryService model(directory.filePath("route.json"),false);auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);
  const QVariantMap expected{{"revision","9007199254740993"},{"generation","4"},{"mode","rule"},{"tier",2},
   {"rule_id","service:rule"},{"service_policy_id","30000000-0000-4000-8000-000000000001"},
   {"group_chain",QStringList{"20000000-0000-4000-8000-000000000001"}},
   {"leaf_node_id","10000000-0000-4000-8000-000000000001"},{"source_id","40000000-0000-4000-8000-000000000001"},
   {"chosen_ip","2001:db8::1"},{"dns_profile","classification"},{"dns_path","direct_encrypted"},{"classification_state","classified"},{"affinity_reason","service"}};
  auto supplied=expected;supplied.insert("plan_digest",QString(64,'a'));supplied.insert("raw_configuration",QVariantMap{{"password","never-export-this"}});
  auto row=status.connections.first().toMap();row.insert("route",supplied);status.connections={row};model.ingest(status);
  QCOMPARE(model.connections().first().toMap().value("route").toMap(),expected);model.flush();
  QFile saved(directory.filePath("route.json"));QVERIFY(saved.open(QIODevice::ReadOnly));const auto output=saved.readAll();QVERIFY(!output.contains("never-export-this"));QVERIFY(!output.contains("plan_digest"));
 }
 void groupConfigurationReceiptInvalidatesOldMeasurementsWithoutInventingALeaf(){
  QTemporaryDir directory;TelemetryService model(directory.filePath("group.json"),false);auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);
  status.selectedNodeId.clear();status.mode="rule";status.proxyPort=7898;status.configurationReceipt={{"applied_revision","12"},{"generation","3"}};model.ingest(status);
  model.m_externalIp="203.0.113.7";const auto previousGeneration=model.m_routeGeneration;QSignalSpy requested(&model,&TelemetryService::nativeProbeRequested);
  model.measureProxy();QCOMPARE(requested.size(),1);QVERIFY(model.m_nativeProbePending);
  status.configurationReceipt={{"applied_revision","13"},{"generation","4"}};++status.connectionsAt;model.ingest(status);
  QVERIFY(model.m_routeGeneration>previousGeneration);QVERIFY(!model.m_nativeProbePending);QCOMPARE(model.m_measurements,0);QVERIFY(model.externalIp().isEmpty());QVERIFY(status.selectedNodeId.isEmpty());
 }
 void malformedRouteMetadataCannotBecomeAValidIdentity(){
  QTemporaryDir directory;TelemetryService model(directory.filePath("malformed-route.json"),false);auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);
  auto row=status.connections.first().toMap();row.insert("route",QVariantMap{{"revision","01"},{"generation","18446744073709551616"},{"mode","unknown"},
   {"tier",9},{"rule_id",QString("bad\nrule")},{"chosen_ip","password@example.invalid"},{"group_chain",QStringList{QString("bad\nmember")}},{"plan_digest","secret"}});
  status.connections={row};model.ingest(status);QVERIFY(model.connections().first().toMap().value("route").toMap().isEmpty());
 }
 void directModePreservesItsActualBypassTierWithoutAcceptingRuleTierZero(){
  QTemporaryDir directory;TelemetryService model(directory.filePath("direct-tier.json"),false);auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);
  auto row=status.connections.first().toMap();row.insert("route",QVariantMap{{"mode","direct"},{"tier",0}});status.connections={row};model.ingest(status);
  QCOMPARE(model.connections().first().toMap().value("route").toMap().value("tier").toInt(),0);
  row.insert("route",QVariantMap{{"mode","rule"},{"tier",0}});status.connections={row};++status.connectionsAt;model.ingest(status);
  QVERIFY(!model.connections().first().toMap().value("route").toMap().contains("tier"));
 }
  void controllerPublishesOneStatusChangePerEnginePulse(){
   QTemporaryDir temp;auto engine=std::make_unique<PulseEngine>();auto *pulse=engine.get();
   EngineController controller(std::move(engine),nullptr,temp.filePath("nodes.dpapi"));
   QSignalSpy controllerChanges(&controller,&EngineController::statusChanged);
   QSignalSpy telemetryChanges(controller.telemetry(),&TelemetryService::changed);
   pulse->refresh();
   QCOMPARE(telemetryChanges.size(),1);QCOMPARE(controllerChanges.size(),1);
   pulse->refresh();
   QCOMPARE(telemetryChanges.size(),2);QCOMPARE(controllerChanges.size(),2);
   controller.telemetry()->ingest({});
   QCOMPARE(telemetryChanges.size(),3);QCOMPARE(controllerChanges.size(),3);
  }
  void nodeRowsNotifyOnlyForRelevantEngineStatus(){
   QTemporaryDir temp;auto engine=std::make_unique<PulseEngine>();auto *pulse=engine.get();
   EngineController controller(std::move(engine),nullptr,temp.filePath("nodes.dpapi"));
   const auto saved=controller.saveNode({{"name","fixture"},{"protocol","http"},{"host","127.0.0.1"},{"port",9}});
#ifdef Q_OS_WIN
   QVERIFY(saved);const auto id=controller.nodes().first().toMap().value("id").toString();QVERIFY(!id.isEmpty());
#else
   // Non-Windows storage intentionally fails closed. Exercise every display
   // invalidation transition without inventing an unencrypted saved catalogue.
   QVERIFY(!saved);QVERIFY(controller.nodes().isEmpty());const QString id="fixture";
#endif
   const auto verifyRow=[&](const QString &status){
#ifdef Q_OS_WIN
    const auto row=controller.nodes().first().toMap();
    QCOMPARE(row.value("status").toString(),status);
    QCOMPARE(row.value("latency").toString(),QStringLiteral("—"));
    QCOMPARE(row.value("connectionState").toString(),status==QStringLiteral("未测试")?QStringLiteral("未连接"):status);
    QCOMPARE(controller.nodeStateText(),row.value("connectionState").toString());
    QCOMPARE(row.value("networkVerified").toBool(),status==QStringLiteral("已连接"));
    QVERIFY(!row.value("testAvailable").toBool());
    const auto diagnostic=controller.nodeDiagnosticRows().first().toMap();
    QCOMPARE(diagnostic.value("connectionState"),row.value("connectionState"));
    QCOMPARE(diagnostic.value("requestVerified"),row.value("networkVerified"));
    QVERIFY(!diagnostic.contains("host"));QVERIFY(!diagnostic.contains("id"));QVERIFY(!diagnostic.contains("name"));
#else
    Q_UNUSED(status);QVERIFY(controller.nodes().isEmpty());
#endif
   };
   QSignalSpy rows(&controller,&EngineController::nodesChanged);
   pulse->refresh();pulse->refresh();QCOMPARE(rows.size(),0);
   pulse->current.uptimeSeconds=10;pulse->current.uploadTotal=100;
   pulse->refresh();QCOMPARE(rows.size(),0);
#ifdef Q_OS_WIN
   QVERIFY(controller.prepareRealAcceptance());controller.connectNode(id);
#endif
   pulse->current.processAlive=true;pulse->current.apiHealthy=true;pulse->current.selectedNodeId=id;
   pulse->current.nodeHealth=ProxyEngine::NodeHealth::Checking;pulse->current.latencyMs=42;
   pulse->refresh();QCOMPARE(rows.size(),1);verifyRow(QStringLiteral("会话就绪 · 未验证"));
   pulse->current.nodeHealth=ProxyEngine::NodeHealth::Available;
   pulse->refresh();QCOMPARE(rows.size(),2);verifyRow(QStringLiteral("会话就绪 · 未验证"));
   pulse->current.latencyMs=50;pulse->refresh();QCOMPARE(rows.size(),2);verifyRow(QStringLiteral("会话就绪 · 未验证"));
   pulse->current.requestState=ProxyEngine::RequestState::Succeeded;pulse->refresh();
   QCOMPARE(rows.size(),3);verifyRow(QStringLiteral("已连接"));
   pulse->current.requestState=ProxyEngine::RequestState::Failed;pulse->refresh();
   QCOMPARE(rows.size(),4);verifyRow(QStringLiteral("连接失败"));
   pulse->current.requestState=ProxyEngine::RequestState::NotTested;
   pulse->current.selectedNodeId.clear();pulse->refresh();QCOMPARE(rows.size(),5);verifyRow(QStringLiteral("未测试"));
  }
  void stalePollingPublishesOnlySamplingTransitions(){
   QTemporaryDir temp;TelemetryService model(temp.filePath("stale.json"),false);model.m_stale.stop();
   QSignalSpy changes(&model,&TelemetryService::changed);
   auto poll=[&]{QVERIFY(QMetaObject::invokeMethod(&model.m_stale,"timeout",Qt::DirectConnection));};
   poll();poll();QCOMPARE(changes.size(),0);
   model.ingest(sample(QDateTime::currentMSecsSinceEpoch(),0,0));
   QCOMPARE(changes.size(),1);QVERIFY(model.sampled());QVERIFY(model.connectionsSampled());
   poll();poll();QCOMPARE(changes.size(),1);
   model.m_status.trafficAt=QDateTime::currentMSecsSinceEpoch()-7000;
   poll();QCOMPARE(changes.size(),2);QVERIFY(!model.sampled());QVERIFY(model.connectionsSampled());
   poll();QCOMPARE(changes.size(),2);
   model.m_status.connectionsAt=QDateTime::currentMSecsSinceEpoch()-7000;
   poll();QCOMPARE(changes.size(),3);QVERIFY(!model.connectionsSampled());
   poll();poll();QCOMPARE(changes.size(),3);
  }
 void httpsMeasurementWaitsForCompleteResponse(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("https-timing.json"),false);
  QFile cert(QString::fromUtf8(SWIRL_FIXTURE_DIR)+"/localhost-cert.pem"),key(QString::fromUtf8(SWIRL_FIXTURE_DIR)+"/localhost-key.pem");
  QVERIFY(cert.open(QIODevice::ReadOnly));QVERIFY(key.open(QIODevice::ReadOnly));
  const QSslCertificate certificate(cert.readAll());auto serverTls=QSslConfiguration::defaultConfiguration();
  serverTls.setLocalCertificate(certificate);serverTls.setPrivateKey(QSslKey(key.readAll(),QSsl::Rsa));
  serverTls.setPeerVerifyMode(QSslSocket::VerifyNone);serverTls.setAllowedNextProtocols({QByteArray("http/1.1")});
  QSslServer origin;origin.setSslConfiguration(serverTls);QVERIFY(origin.listen(QHostAddress::LocalHost,0));
  const auto original=QSslConfiguration::defaultConfiguration();auto trusted=original;trusted.addCaCertificate(certificate);
  const auto restore=qScopeGuard([&]{QSslConfiguration::setDefaultConfiguration(original);});
  QSslConfiguration::setDefaultConfiguration(trusted);
  QPointer<QTcpSocket> pending;QByteArray request;
  connect(&origin,&QTcpServer::pendingConnectionAvailable,&origin,[&]{
   auto *socket=origin.nextPendingConnection();pending=socket;connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
   connect(socket,&QTcpSocket::readyRead,&origin,[&,socket]{request+=socket->readAll();});
   request+=socket->readAll();
  });
  model.m_measurements=1;model.measureHttp("internet",QUrl(QString("https://127.0.0.1:%1/timing").arg(origin.serverPort())),false);
  QTRY_VERIFY_WITH_TIMEOUT(request.contains("\r\n\r\n"),5000);QVERIFY(request.startsWith("GET /timing HTTP/1.1"));
  pending->write("HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\n");
  QElapsedTimer bodyDelay;bodyDelay.start();QTest::qWait(100);
  // The diagnostic measures QNetworkReply completion, not TCP/TLS handshake
  // or HTTP headers. A response whose body is withheld must remain pending.
  QCOMPARE(model.m_measurements,1);QVERIFY(model.internetDiagnostic().isEmpty());
  const auto withheldMs=bodyDelay.elapsed();pending->write("done");pending->disconnectFromHost();
  QTRY_COMPARE_WITH_TIMEOUT(model.m_measurements,0,3000);
  const auto result=model.internetDiagnostic();QVERIFY(result.value("success").toBool());
  QVERIFY(result.value("elapsedMs").toLongLong()>=withheldMs);
  QCOMPARE(model.latencies().value("internet").toString(),QString::number(result.value("elapsedMs").toLongLong())+" ms");
  QVERIFY(result.value("advice").toString().contains(QStringLiteral("连接、TLS 与目标响应")));
 }
 void nativeNodeProbeKeepsOutboundAndHeaderDurationsSeparate(){
  ControlledNetwork net;QVERIFY(net.start());QTcpServer origin;QVERIFY(origin.listen(QHostAddress::LocalHost,0));
  net.a.targetPorts.append(origin.serverPort());QPointer<QTcpSocket> pending;QByteArray request;
  connect(&origin,&QTcpServer::newConnection,&origin,[&]{
   auto *socket=origin.nextPendingConnection();pending=socket;connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
   connect(socket,&QTcpSocket::readyRead,&origin,[&,socket]{request+=socket->readAll();});
   request+=socket->readAll();
  });
  EngineStartOptions options;ProxyNode node;node.id=QUuid::createUuid().toString(QUuid::WithoutBraces);node.name="Timing fixture";node.protocol="socks5";node.host="127.0.0.1";node.port=net.a.serverPort();options.nodes={node};
  const auto validation=ProxyNode::validate(node);QVERIFY2(validation.isEmpty(),qPrintable(validation));
  NodeTestService probes;const QUrl url(QString("http://127.0.0.1:%1/timing").arg(origin.serverPort()));
  probes.start(options,{node.id},url);QTRY_VERIFY_WITH_TIMEOUT(request.contains("\r\n\r\n"),5000);
  QVERIFY(request.startsWith("HEAD /timing HTTP/1.1"));QElapsedTimer headerDelay;headerDelay.start();QTest::qWait(100);
  QVERIFY(probes.busy());QVERIFY(probes.result(node.id).isEmpty());const auto withheldMs=headerDelay.elapsed();
  // A HEAD response completes at headers; the declared body is never sent.
  pending->write("HTTP/1.1 200 OK\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n");
  QTRY_VERIFY_WITH_TIMEOUT(!probes.busy(),5000);const auto result=probes.result(node.id);
  QVERIFY2(result.value("success").toBool(),qPrintable(result.value("error").toString()));
  QCOMPARE(result.value("metricType").toString(),QString("http_headers"));
  const auto outbound=result.value("outboundConnectMs").toLongLong(),headers=result.value("latency").toLongLong();
  QVERIFY(outbound>=0);QVERIFY(headers>outbound);QVERIFY(headers>=withheldMs);
  QCOMPARE(result.value("originTlsMs").toLongLong(),qint64(-1));QCOMPARE(net.a.forwarded,1);
  request.clear();probes.start(options,{node.id},url);QTRY_VERIFY_WITH_TIMEOUT(request.contains("\r\n\r\n"),5000);
  pending->write("HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");pending->disconnectFromHost();
  QTRY_VERIFY_WITH_TIMEOUT(!probes.busy(),5000);const auto failed=probes.result(node.id);
  QVERIFY(!failed.value("success").toBool());QCOMPARE(failed.value("latency").toLongLong(),qint64(-1));
  QCOMPARE(failed.value("outboundConnectMs").toLongLong(),qint64(-1));QCOMPARE(net.a.forwarded,2);
 }

 void httpsMeasurementStaysHttp1WhenOriginOffersHttp2(){
  const auto original=QSslConfiguration::defaultConfiguration();
  struct RestoreSsl {QSslConfiguration value;~RestoreSsl(){QSslConfiguration::setDefaultConfiguration(value);}} restore{original};
  QFile certificate(QStringLiteral(SWIRL_FIXTURE_DIR "/localhost-cert.pem"));
  QFile key(QStringLiteral(SWIRL_FIXTURE_DIR "/localhost-key.pem"));
  QVERIFY(certificate.open(QIODevice::ReadOnly));QVERIFY(key.open(QIODevice::ReadOnly));
  const QSslCertificate cert(certificate.readAll());const QSslKey privateKey(key.readAll(),QSsl::Rsa);
  QVERIFY(!cert.isNull());QVERIFY(!privateKey.isNull());
  auto trusted=original;trusted.addCaCertificate(cert);
  QSslConfiguration::setDefaultConfiguration(trusted);
  auto serverSsl=trusted;serverSsl.setLocalCertificate(cert);serverSsl.setPrivateKey(privateKey);
  serverSsl.setPeerVerifyMode(QSslSocket::VerifyNone); // This fixture does not require client certificates.
  serverSsl.setAllowedNextProtocols({QByteArray("h2"),QByteArray("http/1.1")});
  QList<QByteArray> protocols,requestLines;
  QSslServer origin;origin.setSslConfiguration(serverSsl);
  QVERIFY(origin.listen(QHostAddress::LocalHost,0));
  connect(&origin,&QSslServer::pendingConnectionAvailable,&origin,[&]{
   while(origin.hasPendingConnections()){
    auto *socket=qobject_cast<QSslSocket *>(origin.nextPendingConnection());
    if(!socket)continue;
    const auto protocol=socket->sslConfiguration().nextNegotiatedProtocol();protocols.append(protocol);
    connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
    // Negotiating h2 is the regression: this endpoint deliberately handles
    // only HTTP/1.1 payloads and never sends malformed HTTP/2 frames.
    if(protocol=="h2"){socket->disconnectFromHost();continue;}
    auto data=std::make_shared<QByteArray>();
    const auto respond=[&,socket,data]{
     *data+=socket->readAll();if(!data->contains("\r\n\r\n")||socket->property("responded").toBool())return;
     socket->setProperty("responded",true);requestLines.append(data->left(data->indexOf("\r\n")));
     socket->write("HTTP/1.1 200 OK\r\nContent-Length: 12\r\nConnection: close\r\n\r\n203.0.113.10");
     socket->disconnectFromHost();
    };
    connect(socket,&QTcpSocket::readyRead,socket,respond);if(socket->bytesAvailable())respond();
   }
  });
  // A verified TLS positive control proves this exact origin can select h2.
  QSslSocket control;control.setProxy(QNetworkProxy::NoProxy);
  auto controlSsl=trusted;controlSsl.setAllowedNextProtocols({QByteArray("h2"),QByteArray("http/1.1")});
  control.setSslConfiguration(controlSsl);QSignalSpy encrypted(&control,&QSslSocket::encrypted);
  control.connectToHostEncrypted("localhost",origin.serverPort());
  QTRY_VERIFY_WITH_TIMEOUT(!encrypted.isEmpty(),4000);
  QTRY_COMPARE_WITH_TIMEOUT(protocols.size(),1,4000);QCOMPARE(protocols.first(),QByteArray("h2"));
  control.abort();protocols.clear();

  QTemporaryDir temp;QVERIFY(temp.isValid());TelemetryService model(temp.filePath("https-policy.json"),false);
  const QUrl url(QString("https://localhost:%1/probe").arg(origin.serverPort()));
  model.m_measurements=1;model.measureHttp("internet",url,false);
  QTRY_COMPARE_WITH_TIMEOUT(model.m_measurements,0,5000);
  QVERIFY(model.internetDiagnostic().value("success").toBool());
  QCOMPARE(model.internetDiagnostic().value("http").toInt(),200);
  // The public-IP measurement uses the same real request path.
  model.m_measurements=1;model.measureHttp("exit",url,false,true);
  QTRY_COMPARE_WITH_TIMEOUT(model.m_measurements,0,5000);
  QCOMPARE(model.externalIp(),QString("203.0.113.10"));
  QCOMPARE(protocols.size(),2);QCOMPARE(requestLines.size(),2);
  for(const auto &protocol:protocols)QVERIFY(protocol.isEmpty()||protocol=="http/1.1");
  for(const auto &line:requestLines)QCOMPARE(line,QByteArray("GET /probe HTTP/1.1"));
 }
 void proxyLatencyComesFromRustAndRejectsUntrustedTargetTls(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;QVERIFY(directory.isValid());
  QTcpServer reservation;QVERIFY(reservation.listen(QHostAddress::LocalHost,0));
  EngineStartOptions options;options.routingMode="global";options.proxyPort=reservation.serverPort();reservation.close();
  ProxyNode node;node.id=QUuid::createUuid().toString(QUuid::WithoutBraces);node.name="Probe node";node.protocol="socks5";node.host="127.0.0.1";node.port=net.a.serverPort();options.nodes={node};options.selectedNodeId=node.id;
  ThreadedEngine engine;TelemetryService model(directory.filePath("probe.json"),false);
  connect(&engine,&ProxyEngine::statusChanged,&model,[&]{model.ingest(engine.status());});
  connect(&model,&TelemetryService::nativeProbeRequested,&engine,&ProxyEngine::probeNodeTagged);
  connect(&engine,&ProxyEngine::probeRequestRejected,&model,&TelemetryService::rejectNativeProbe);
  engine.start(options);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,5000);
  model.m_internetProbe=net.url();model.measureProxy();QVERIFY(model.m_nativeProbePending);
  QTRY_VERIFY_WITH_TIMEOUT(!model.m_nativeProbePending,5000);
  const auto result=model.proxyDiagnostic();
  QVERIFY2(result.value("success").toBool(),qPrintable(result.value("state").toString()));
  QCOMPARE(result.value("metricType").toString(),QString("http_headers"));QVERIFY(result.value("routeVerified").toBool());
  QVERIFY(result.value("elapsedMs").toLongLong()>=0);QVERIFY(result.value("outboundConnectMs").toLongLong()>=0);
  QCOMPARE(net.a.forwarded,1);QCOMPARE(net.b.forwarded,0);QCOMPARE(net.httpRequests,1);QCOMPARE(model.m_measurements,0);
  // Queue a user URL before the worker's busy snapshot reaches the UI. The
  // periodic request must not consume that other request's response.
  engine.probeNode(net.url());model.measureProxy();
  QTRY_VERIFY_WITH_TIMEOUT(!model.m_nativeProbePending,5000);
  QCOMPARE(model.proxyDiagnostic().value("code").toString(),QString("probe-busy"));
  QVERIFY(!model.proxyDiagnostic().value("success").toBool());
  QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,5000);QCOMPARE(net.httpRequests,2);
  // The self-signed target certificate is not a Rust trusted CA. Qt's UI TLS
  // state cannot accidentally make this core probe claim HTTPS success.
  model.m_internetProbe=net.url(true);model.measureProxy();
  QTRY_VERIFY_WITH_TIMEOUT(!model.m_nativeProbePending,5000);
  QVERIFY(!model.proxyDiagnostic().value("success").toBool());
  QCOMPARE(model.proxyDiagnostic().value("code").toString(),QString("origin_tls"));
  QCOMPARE(model.m_measurements,0);engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,5000);
 }
 void nativeProbeIgnoresStaleSuccessAndInvalidatesOnRouteChange(){
  QTemporaryDir directory;TelemetryService model(directory.filePath("probe-generation.json"),false);
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);status.proxyPort=7898;status.selectedNodeId="A";model.ingest(status);
  QSignalSpy requested(&model,&TelemetryService::nativeProbeRequested);model.measureProxy();QCOMPARE(requested.size(),1);
  // A queued terminal snapshot from a previous request is not a new success.
  status.requestState=ProxyEngine::RequestState::Succeeded;status.latencyMs=5;status.responseCode=200;model.ingest(status);
  QVERIFY(model.m_nativeProbePending);QVERIFY(!model.proxyDiagnostic().value("success").toBool());
  // A manual probe on the same node has tag zero and must not be attributed to
  // the periodic URL, even if both requests were queued before UI refresh.
  status.requestState=ProxyEngine::RequestState::InProgress;status.nodeBusy=true;model.ingest(status);QVERIFY(!model.m_nativeProbeObservedRunning);
  status.probeRequestTag=requested.first().at(1).toULongLong();model.ingest(status);QVERIFY(model.m_nativeProbeObservedRunning);
  status.selectedNodeId="B";model.ingest(status);QVERIFY(!model.m_nativeProbePending);QCOMPARE(model.m_measurements,0);
  status.selectedNodeId="A";status.nodeBusy=false;status.requestState=ProxyEngine::RequestState::Succeeded;model.ingest(status);
  QVERIFY(model.proxyDiagnostic().isEmpty());QCOMPARE(model.latencies().value("proxy").toString(),QStringLiteral("尚未测量"));
  // A missing completion also has a bounded diagnostic, not an eternal spinner.
  model.m_nativeProbeDeadline.setInterval(1);model.measureProxy();QTRY_VERIFY_WITH_TIMEOUT(!model.m_nativeProbePending,500);
  QCOMPARE(model.proxyDiagnostic().value("code").toString(),QString("timeout"));QCOMPARE(model.m_measurements,0);
 }
 void httpProbeRejectsObsoleteRoundTrip(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("proxy.json"),false);
  QTcpServer proxy;QVERIFY(proxy.listen(QHostAddress::LocalHost,0));
  QPointer<QTcpSocket> pending;QByteArray request;
  connect(&proxy,&QTcpServer::newConnection,this,[&]{pending=proxy.nextPendingConnection();connect(pending,&QTcpSocket::readyRead,this,[&]{request+=pending->readAll();});});
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);status.proxyPort=proxy.serverPort();status.selectedNodeId="A";model.ingest(status);

  model.m_measurements=1;model.measureHttp("internet",QUrl("http://fixture.invalid/proxy"),true);
  QTRY_VERIFY_WITH_TIMEOUT(request.contains("\r\n\r\n"),3000);
  QVERIFY(request.startsWith("GET http://fixture.invalid/proxy HTTP/1.1"));
  pending->write("HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");pending->disconnectFromHost();
  QTRY_COMPARE(model.m_measurements,0);QVERIFY(model.internetDiagnostic().value("success").toBool());

  request.clear();model.m_measurements=1;model.measureHttp("internet",QUrl("http://fixture.invalid/proxy"),true);
  QTRY_VERIFY_WITH_TIMEOUT(request.contains("\r\n\r\n"),3000);
  // A -> B -> A must still invalidate the first A request (string IDs alone cannot).
  status.selectedNodeId="B";model.ingest(status);status.selectedNodeId="A";model.ingest(status);
  pending->write("HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");pending->disconnectFromHost();
  QTRY_COMPARE(model.m_measurements,0);QVERIFY(model.internetDiagnostic().isEmpty());
  QCOMPARE(model.latencies().value("proxy").toString(),QStringLiteral("尚未测量"));
  QCOMPARE(model.measurementState(),QStringLiteral("尚未测量"));
  proxy.close();model.m_measurements=1;model.measureHttp("internet",QUrl("http://fixture.invalid/proxy"),true);
  QTRY_COMPARE(model.m_measurements,0);QCOMPARE(model.internetDiagnostic().value("code").toString(),QString("proxy-port"));
 }
 void periodCacheSurvivesStatusOnlyUpdatesAndExpiresWithHistory(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("cache-lifetime.json"),false);
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),10,20);model.ingest(status);
  for(int period=0;period<4;++period)model.summary(period);
  const auto cached=model.m_periodCache;QCOMPARE(cached.size(),4);
  QSignalSpy changed(&model,&TelemetryService::changed);
  model.ingest(status);QCOMPARE(changed.size(),1);QCOMPARE(model.m_periodCache,cached);
  model.recordInternetResult(QNetworkReply::NoError,204,false,25);model.publish();
  QCOMPARE(changed.size(),2);QCOMPARE(model.m_periodCache,cached);
  QVERIFY(model.internetDiagnostic().value("success").toBool());QCOMPARE(model.summary().value("total").toInt(),30);
  status.trafficAt=QDateTime::currentMSecsSinceEpoch()-7000;model.ingest(status);
  QVERIFY(!model.sampled());QCOMPARE(model.m_periodCache,cached);QCOMPARE(model.summary().value("total").toInt(),30);
  status=sample(status.connectionsAt+1000,20,40);model.ingest(status);
  QVERIFY(model.m_periodCache.isEmpty());QCOMPARE(model.summary().value("total").toInt(),60);
  const auto current=model.m_periodCache;
  status.processAlive=false;status.apiHealthy=false;model.ingest(status);
  QVERIFY(!model.sampled());QCOMPARE(model.m_periodCache,current);QCOMPARE(model.summary().value("total").toInt(),60);
  QCOMPARE(model.ranking("apps").first().toMap().value("speed").toDouble(),0.0);
 }
 void periodCacheRebuildsAtDateBoundary(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("cache-date.json"),false);
  model.ingest(sample(QDateTime::currentMSecsSinceEpoch(),10,20));
  model.summary(0);model.summary(3);QCOMPARE(model.m_periodCache.size(),2);
  model.m_periodCacheDate=QDate::currentDate().addDays(-1);
  model.m_periodCache[0]=QJsonObject{{"sampled",true},{"up",9999}};
  QCOMPARE(model.summary().value("total").toInt(),30);
  QCOMPARE(model.m_periodCacheDate,QDate::currentDate());QCOMPARE(model.m_periodCache.size(),1);
 }
 void cachedPeriodInvalidatesWithoutErasingHistory(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("cache.json"),false);
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),10,20);model.ingest(status);
  QCOMPARE(model.summary().value("total").toInt(),30);model.distribution();model.ranking("apps");
  status=sample(status.connectionsAt+1000,20,40);model.ingest(status);
  QCOMPARE(model.summary().value("total").toInt(),60);
  QCOMPARE(model.ranking("apps").first().toMap().value("total").toInt(),60);
  status.processAlive=false;status.apiHealthy=false;model.ingest(status);
  QVERIFY(!model.sampled());QCOMPARE(model.summary().value("total").toInt(),60);
  QCOMPARE(model.ranking("apps").first().toMap().value("speed").toDouble(),0.0);
 }
 void activeDevicesCountUniqueObservedAddressesWithExactLoopbackExclusions(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("device-addresses.json"),false);
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);const auto base=status.connections.first().toMap();status.connections.clear();
  const auto append=[&](const QString &id,const QString &address,bool closed=false){auto row=base;row["id"]=id;row["sourceIp"]=address;row["closed"]=closed;status.connections.append(row);};
  append("peer-a1","192.0.2.10");append("peer-a2","192.0.2.10");append("peer-b","2001:db8::8");
  append("loopback-v4","127.0.0.1");append("loopback-v6","::1");append("empty",QString());
  auto missing=base;missing["id"]="missing";status.connections.append(missing);
  append("closed","192.0.2.20",true);append("closed-duplicate","192.0.2.10",true);
  append("other-local-address","127.0.0.2");append("mapped-address","::ffff:127.0.0.1");
  model.ingest(status);QCOMPARE(model.activeDevices(),4);QCOMPARE(model.property("activeDevices").toInt(),4);
  for(auto &value:status.connections){auto row=value.toMap();if(row.value("id")=="peer-a1"||row.value("id")=="peer-a2"){row["closed"]=true;value=row;}}
  ++status.connectionsAt;model.ingest(status);QCOMPARE(model.activeDevices(),3);
 }
 void activeDevicesFollowObservedSamplingInterruptionAndSessionChanges(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("device-lifecycle.json"),false);
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);auto first=status.connections.first().toMap();first["sourceIp"]="192.0.2.10";status.connections={first};
  auto second=first;second["id"]="connection-b";second["sourceIp"]="192.0.2.20";status.connections.append(second);
  model.ingest(status);QCOMPARE(model.activeDevices(),2);QVERIFY(model.connectionsSampled());
  const auto liveTimestamp=status.connectionsAt;status.connectionsAt=QDateTime::currentMSecsSinceEpoch()-7000;model.ingest(status);
  QVERIFY(!model.connectionsSampled());QCOMPARE(model.activeDevices(),2);
  status.apiHealthy=false;model.ingest(status);QCOMPARE(model.activeDevices(),0);
  status.apiHealthy=true;status.connectionsAt=liveTimestamp+1;model.ingest(status);QCOMPARE(model.activeDevices(),2);
  status.processAlive=false;status.apiHealthy=false;model.ingest(status);QCOMPARE(model.activeDevices(),0);
  status=sample(liveTimestamp+2,0,0);status.processId=2;first["sourceIp"]="192.0.2.30";status.connections={first};
  model.ingest(status);QCOMPARE(model.activeDevices(),1);
 }
 void closedSnapshotsAreNotActiveAndControlFailureIsNotClosure(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("activity-state.json"),false);
  auto s=sample(QDateTime::currentMSecsSinceEpoch(),10,20);
  auto closed=s.connections.first().toMap();closed["id"]="closed";closed["process"]="retired.exe";closed["closed"]=true;
  s.connections.append(closed);model.ingest(s);
  QCOMPARE(model.activeConnections(),1);QCOMPARE(model.activeProcesses(),1);
  s.apiHealthy=false;model.ingest(s);
  auto rows=model.connections();for(const auto &r:rows)if(r.toMap().value("id")=="connection-a")QCOMPARE(r.toMap().value("status").toString(),QStringLiteral("采样中断"));
  s.processAlive=false;model.ingest(s);
  for(const auto &r:model.connections())QCOMPARE(r.toMap().value("status").toString(),QStringLiteral("已结束"));
 }
 void internetUsesExplicitProxyAndActualHttpResponse(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("diagnostic.json"),false);
  QTcpServer proxy;QVERIFY(proxy.listen(QHostAddress::LocalHost,0));QByteArray request;
  connect(&proxy,&QTcpServer::newConnection,this,[&]{auto socket=proxy.nextPendingConnection();connect(socket,&QTcpSocket::readyRead,this,[&,socket]{request+=socket->readAll();if(request.contains("\r\n\r\n")){socket->write("HTTP/1.1 204 No Content\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");socket->disconnectFromHost();}});});
  auto status=sample(QDateTime::currentMSecsSinceEpoch(),0,0);status.proxyPort=proxy.serverPort();model.ingest(status);
  model.m_measurements=1;model.measureHttp("internet",QUrl("http://fixture.invalid/probe"),true);
  QTRY_VERIFY_WITH_TIMEOUT(model.m_measurements==0,4000);
  QVERIFY(request.startsWith("GET http://fixture.invalid/probe HTTP/1.1"));
  QVERIFY(model.internetDiagnostic().value("success").toBool());QCOMPARE(model.internetDiagnostic().value("http").toInt(),204);
  // A stopped listener must never reuse the previous success.
  proxy.close();model.m_measurements=1;model.measureHttp("internet",QUrl("http://fixture.invalid/probe"),true);
  QTRY_VERIFY_WITH_TIMEOUT(model.m_measurements==0,4000);
  QVERIFY(!model.internetDiagnostic().value("success").toBool());QCOMPARE(model.internetDiagnostic().value("code").toString(),QString("proxy-port"));
 }
 void internetFailureClassificationAndRouteChanges(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("classification.json"),false);
  model.recordInternetResult(QNetworkReply::HostNotFoundError,0,false,2);QCOMPARE(model.internetDiagnostic().value("code").toString(),QString("dns"));
  model.recordInternetResult(QNetworkReply::OperationCanceledError,0,true,9000);QCOMPARE(model.internetDiagnostic().value("code").toString(),QString("timeout"));
  model.recordInternetResult(QNetworkReply::ServiceUnavailableError,503,true,80);QCOMPARE(model.internetDiagnostic().value("code").toString(),QString("service"));
  QVERIFY(!model.internetDiagnostic().value("success").toBool());
  model.recordInternetResult(QNetworkReply::NoError,204,false,20);QVERIFY(model.internetDiagnostic().value("success").toBool());
  QVERIFY(model.internetDiagnostic().value("advice").toString().contains(QStringLiteral("未验证代理节点")));
  model.ingest(sample(QDateTime::currentMSecsSinceEpoch(),0,0));QVERIFY(model.internetDiagnostic().isEmpty());
 }
 void continuingMeasurementFailureIsOneIncident(){
  QTemporaryDir temp;TelemetryService model(temp.filePath("measurements.json"),false);QSignalSpy incidents(&model,&TelemetryService::diagnostic);
  for(int i=0;i<510;++i)model.reportMeasurement("InternetTCP",false,"timeout");
  QCOMPARE(incidents.size(),1);
  model.reportMeasurement("DNS",false,"lookup failed");QCOMPARE(incidents.size(),2);
  model.reportMeasurement("InternetTCP",true,{});model.reportMeasurement("InternetTCP",false,"timeout");QCOMPARE(incidents.size(),3);
  model.ingest(sample(QDateTime::currentMSecsSinceEpoch(),0,0));model.reportMeasurement("InternetTCP",false,"timeout");QCOMPARE(incidents.size(),4);
 }
 void dailyBucketsPreserveGapsAndProxyFilter(){QTemporaryDir temp;const auto path=temp.filePath("day.json");TelemetryService model(path,false);const auto now=QDateTime::currentMSecsSinceEpoch();auto s=sample(now,100,200);auto row=s.connections.first().toMap();row["category"]="proxy";s.connections={row};model.ingest(s);model.ingest(s);s=sample(now+1,150,300);row=s.connections.first().toMap();row["category"]="proxy";s.connections={row};model.ingest(s);
  const auto all=model.dailyTraffic(),proxy=model.dailyTraffic(true);QCOMPARE(all.size(),48);int observed=0;double sum=0,proxySum=0;for(int i=0;i<48;++i){observed+=all[i].toMap().value("sampled").toBool();sum+=all[i].toMap().value("value").toDouble();proxySum+=proxy[i].toMap().value("value").toDouble();}QCOMPARE(observed,1);QCOMPARE(sum,450.0);QCOMPARE(proxySum,450.0);model.flush();TelemetryService restored(path,false);QCOMPARE(restored.dailyTraffic(),all);}
 void processAndDeviceRates(){QTemporaryDir temp;TelemetryService model(temp.filePath("rates.json"),false);auto s=sample(QDateTime::currentMSecsSinceEpoch(),100,200);auto row=s.connections.first().toMap();row["sourceIp"]="192.0.2.100";s.connections={row};model.ingest(s);QCOMPARE(model.ranking("apps").first().toMap().value("speed").toDouble(),0.0);
  s.connectionsAt+=1000;s.trafficAt=s.connectionsAt;s.uploadTotal=400;s.downloadTotal=900;row["uploadBytes"]=400;row["downloadBytes"]=900;s.connections={row};model.ingest(s);
  QCOMPARE(model.ranking("apps").first().toMap().value("speed").toDouble(),1000.0);QCOMPARE(model.ranking("devices").first().toMap().value("total").toDouble(),1300.0);QCOMPARE(model.ranking("devices").first().toMap().value("speed").toDouble(),1000.0);
  s.connectionsAt++;s.connections.clear();model.ingest(s);QCOMPARE(model.ranking("apps").first().toMap().value("speed").toDouble(),0.0);}
 void accounting(){QTemporaryDir temp;TelemetryService model(temp.filePath("history.json"),false);QVERIFY(!model.sampled());auto s=sample(QDateTime::currentMSecsSinceEpoch(),10,20);model.ingest(s);QVERIFY(model.sampled());QCOMPARE(model.summary().value("total").toInt(),30);model.ingest(s);QCOMPARE(model.summary().value("total").toInt(),30);s=sample(s.connectionsAt+1,15,30);model.ingest(s);QCOMPARE(model.summary().value("total").toInt(),45);auto rank=model.ranking("apps");QCOMPARE(rank.first().toMap().value("connections").toInt(),1);QCOMPARE(rank.first().toMap().value("total").toInt(),45);QCOMPARE(model.activeProcesses(),1);s.connectionsAt++;s.connections.clear();model.ingest(s);QCOMPARE(model.activeConnections(),0);QCOMPARE(model.connections().size(),1);QCOMPARE(model.connections().first().toMap().value("status").toString(),QStringLiteral("已结束"));model.flush();TelemetryService restored(temp.filePath("history.json"),false);QCOMPARE(restored.summary().value("total").toInt(),45);QVERIFY(!restored.sampled());QCOMPARE(restored.ranking("apps").first().toMap().value("connections").toInt(),1);}
 void resetsAndNewProcess(){QTemporaryDir temp;TelemetryService model(temp.filePath("history.json"),false);auto s=sample(QDateTime::currentMSecsSinceEpoch(),100,200);model.ingest(s);s=sample(s.connectionsAt+1,5,10);model.ingest(s);QCOMPARE(model.summary().value("total").toInt(),315);s=sample(s.connectionsAt+1,7,14);s.processId=2;model.ingest(s);QCOMPARE(model.summary().value("total").toInt(),336);QCOMPARE(model.ranking("apps").first().toMap().value("connections").toInt(),2);}
 void idleAndUncollected(){QTemporaryDir temp;TelemetryService model(temp.filePath("history.json"),false);auto s=sample(QDateTime::currentMSecsSinceEpoch(),0,0);model.ingest(s);QVERIFY(model.sampled());QCOMPARE(model.downloadRate(),0.0);QVERIFY(model.summary().value("sampled").toBool());s.trafficAt=0;s.connectionsAt=0;s.apiHealthy=false;model.ingest(s);QVERIFY(!model.sampled());QVERIFY(!model.connectionsSampled());}
 void timestampedHistory(){QTemporaryDir temp;TelemetryService model(temp.filePath("history.json"),false);const auto t=QDateTime::currentMSecsSinceEpoch();auto s=sample(t-20000,2,4);model.ingest(s);s=sample(t-1000,3,6);model.ingest(s);const auto points=model.historyPoints("down",60);QCOMPARE(points.size(),2);QCOMPARE(points.first().toMap().value("time").toLongLong(),t-20000);QCOMPARE(points.last().toMap().value("time").toLongLong(),t-1000);QCOMPARE(points.last().toMap().value("value").toDouble(),6.0);}
 void ranges(){QTemporaryDir temp;TelemetryService model(temp.filePath("history.json"),false);const auto yesterday=QDateTime(QDate::currentDate().addDays(-1),QTime(12,0)).toMSecsSinceEpoch();auto s=sample(yesterday,2,4);model.ingest(s);QCOMPARE(model.summary(0).value("total").toInt(),0);QCOMPARE(model.summary(1).value("total").toInt(),6);s=sample(QDateTime::currentMSecsSinceEpoch(),3,6);model.ingest(s);QCOMPARE(model.summary(0).value("total").toInt(),3);QCOMPARE(model.summary(1).value("total").toInt(),6);QCOMPARE(model.ranking("apps",0).first().toMap().value("connections").toInt(),1);}
};
QTEST_GUILESS_MAIN(TelemetryTests)
#include "TelemetryTests.moc"
