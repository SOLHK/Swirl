#include "engine/RustCoreEngine.h"
#include "engine/ThreadedEngine.h"
#include "engine/NodeTestService.h"
#include "ControlledNetwork.h"
#include <QTest>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QUuid>

class RustCoreTests:public QObject {
 Q_OBJECT
 EngineStartOptions options(ControlledNetwork &net){
  EngineStartOptions o;QTcpServer port;port.listen(QHostAddress::LocalHost);o.proxyPort=port.serverPort();o.routingMode="global";
  ProxyNode n;n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);n.name="synthetic";n.protocol="socks5";n.host="127.0.0.1";n.port=net.a.serverPort();
  o.nodes={n};o.selectedNodeId=n.id;return o;
 }
private slots:
 void shadowsocksThroughIndependentPeer(){
  bool valid=false;const int port=qEnvironmentVariableIntValue("SWIRL_SS_REFERENCE_PORT",&valid);
  if(!valid)QSKIP("Independent Python SS peer supplies the isolated port in its integration run.");
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);auto &n=o.nodes.first();
  n.protocol="ss";n.host="127.0.0.1";n.port=quint16(port);n.password="synthetic-ss-password";n.cipher="aes-128-gcm";
  n.parameters={{"udp",true},{"plugin","obfs"},{"plugin-opts",QJsonObject{{"mode","http"},{"host","obfs.example"}}}};
  RustCoreEngine engine;engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Running);
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
  QNetworkRequest request(QUrl("http://origin.example/ss"));request.setTransferTimeout(5000);
  auto reply=client.get(request);QVERIFY(QTest::qWaitFor([&]{return reply->isFinished();},6000));
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("ss-native-ok"));
  QCOMPARE(engine.status().engineKind,QString("rust"));QCOMPARE(engine.status().processId,QCoreApplication::applicationPid());
  engine.stop();
 }
 void referenceAdapterBlockedAtCompileTime(){
  MihomoAdapter reference;EngineStartOptions o;o.executablePath="must-never-start.exe";reference.start(o);
  QCOMPARE(reference.status().state,ProxyEngine::State::Failed);QCOMPARE(reference.status().error,ProxyEngine::Error::InvalidOptions);QVERIFY(!reference.status().processAlive);
 }
 void realForwardingThroughQtFacade(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);ThreadedEngine engine;engine.start(o);
  QVERIFY(QTest::qWaitFor([&]{return engine.status().apiHealthy;},5000));QCOMPARE(engine.status().engineKind,QString("rust"));QCOMPARE(engine.status().processId,QCoreApplication::applicationPid());
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
  auto reply=client.get(QNetworkRequest(net.url()));QVERIFY(QTest::qWaitFor([&]{return reply->isFinished();},5000));
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-A"));QVERIFY(net.a.forwarded>0);
  QVERIFY(QTest::qWaitFor([&]{return engine.status().downloadTotal>0;},2000));
  engine.stop();QVERIFY(QTest::qWaitFor([&]{return !engine.status().processAlive;},5000));
  QTcpServer reuse;QVERIFY(reuse.listen(QHostAddress::LocalHost,o.proxyPort));
 }
 void nativeProbeAndUnsupportedDoNotStartCompatibility(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.executablePath="must-not-start-mihomo.exe";
  NodeTestService probes;probes.start(o,{o.selectedNodeId},net.url());QVERIFY(QTest::qWaitFor([&]{return !probes.busy();},6000));
  QCOMPARE(probes.succeeded(),1);QCOMPARE(probes.result(o.selectedNodeId).value("engineKind").toString(),QString("rust"));
  o.nodes.first().protocol="ss";o.nodes.first().password="synthetic";o.nodes.first().cipher="2022-blake3-aes-128-gcm";
  probes.start(o,{o.selectedNodeId},net.url());QVERIFY(QTest::qWaitFor([&]{return !probes.busy();},3000));QCOMPARE(probes.failed(),1);
  QCOMPARE(probes.result(o.selectedNodeId).value("engineKind").toString(),QString("rust"));
 }
 void unsupportedSessionRejectedAndOldStreamSurvivesBadSelection(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);RustCoreEngine engine;
  o.tunEnabled=true;engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Failed);QVERIFY(!engine.status().processAlive);
  o.tunEnabled=false;engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Running);
  const auto session=engine.status().sessionId;engine.selectNode("missing");QCOMPARE(engine.status().sessionId,session);QCOMPARE(engine.status().selectedNodeId,o.selectedNodeId);
  engine.stop();
 }
};
QTEST_GUILESS_MAIN(RustCoreTests)
#include "RustCoreTests.moc"
