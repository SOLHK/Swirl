#include "engine/TelemetryService.h"
#include <QTest>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QDateTime>
#include <QNetworkReply>
#include <QTcpServer>
#include <QTcpSocket>
#include "ControlledNetwork.h"
#include "engine/ThreadedEngine.h"
#include <QUuid>
#include <QJsonDocument>
class TelemetryTests:public QObject {
 Q_OBJECT
 ProxyEngine::Status sample(qint64 time,int up,int down){ProxyEngine::Status s;s.processAlive=true;s.processId=1;s.apiHealthy=true;s.connectionsAt=time;s.trafficAt=time;s.uploadTotal=up;s.downloadTotal=down;s.uploadRate=up;s.downloadRate=down;s.connections={QVariantMap{{"id","connection-a"},{"host","fixture.test"},{"process","fixture.exe"},{"policy","DIRECT"},{"category","direct"},{"uploadBytes",up},{"downloadBytes",down},{"time",QDateTime::fromMSecsSinceEpoch(time).toString(Qt::ISODateWithMs)}}};return s;}
private slots:
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
