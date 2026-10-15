#include "engine/TelemetryService.h"
#include <QTest>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QDateTime>
#include <QNetworkReply>
#include <QTcpServer>
#include <QTcpSocket>
class TelemetryTests:public QObject {
 Q_OBJECT
 ProxyEngine::Status sample(qint64 time,int up,int down){ProxyEngine::Status s;s.processAlive=true;s.processId=1;s.apiHealthy=true;s.connectionsAt=time;s.trafficAt=time;s.uploadTotal=up;s.downloadTotal=down;s.uploadRate=up;s.downloadRate=down;s.connections={QVariantMap{{"id","connection-a"},{"host","fixture.test"},{"process","fixture.exe"},{"policy","DIRECT"},{"category","direct"},{"uploadBytes",up},{"downloadBytes",down},{"time",QDateTime::fromMSecsSinceEpoch(time).toString(Qt::ISODateWithMs)}}};return s;}
private slots:
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
