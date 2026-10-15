#include "engine/ThreadedEngine.h"
#include "engine/NodeTestService.h"
#include "engine/EngineController.h"
#include <QTemporaryDir>
#include "ControlledNetwork.h"
#include <QTest>
#include <QCryptographicHash>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QNetworkProxy>
#include <QUuid>

// Real TLS, RFC6455 handshake/masked frames and chunked SSE over the actual
// mixed listener. Loopback peers only; never enable TUN or change Windows proxy.
class NetworkRegressionTests : public QObject {
 Q_OBJECT
 EngineStartOptions options(ControlledNetwork &net,bool compatibility,const QString &mode){
  EngineStartOptions o;o.preferCompatibility=compatibility;o.routingMode=mode;
  QTcpServer reserve;reserve.listen(QHostAddress::LocalHost);o.proxyPort=reserve.serverPort();reserve.close();
  reserve.listen(QHostAddress::LocalHost);o.controlPort=reserve.serverPort();reserve.close();
  QFile file(QString::fromUtf8(SWIRL_TEST_MANIFEST));file.open(QIODevice::ReadOnly);const auto m=QJsonDocument::fromJson(file.readAll()).object();
  o.expectedSha256=m["executableSha256"].toString().toLatin1();o.expectedVersion=m["version"].toString();
  o.executablePath=QCoreApplication::applicationDirPath()+"/core/mihomo.exe";
  ProxyNode a;a.id=QUuid::createUuid().toString(QUuid::WithoutBraces);a.name="A";a.protocol="socks5";a.host="127.0.0.1";a.port=net.a.serverPort();
  auto b=a;b.id=QUuid::createUuid().toString(QUuid::WithoutBraces);b.name="B";b.port=net.b.serverPort();b.username=QString::fromUtf8(net.b.username);b.password=QString::fromUtf8(net.b.password);
  o.nodes={a,b};o.selectedNodeId=a.id;return o;
 }
 static QByteArray frame(const QByteArray &payload,int opcode=1){
  QByteArray out;out+=char(0x80|opcode);out+=char(0x80|payload.size());out+="mask";
  for(int i=0;i<payload.size();++i)out+=char(payload[i]^"mask"[i%4]);return out;
 }
 static bool receive(QSslSocket &socket,QByteArray &buffer,const QByteArray &marker,int timeout=5000){
  return QTest::qWaitFor([&]{buffer+=socket.readAll();return buffer.contains(marker);},timeout);
 }
 static void configure(QSslSocket &socket,ControlledNetwork &net,const EngineStartOptions &o,quint16 port){
  auto ssl=QSslConfiguration::defaultConfiguration();ssl.addCaCertificate(net.certificate);ssl.setAllowedNextProtocols({QByteArray("http/1.1")});socket.setSslConfiguration(ssl);
  socket.setPeerVerifyName("localhost");socket.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));socket.connectToHostEncrypted("127.0.0.1",port);
 }
private slots:
 void importedNodeUpdatesPreserveExistingTunnel(){
  ControlledNetwork net;QVERIFY(net.start());QTcpServer origin;QVERIFY(origin.listen(QHostAddress::LocalHost));net.a.targetPorts.append(origin.serverPort());
  connect(&origin,&QTcpServer::newConnection,&origin,[&]{while(auto *socket=origin.nextPendingConnection()){
   connect(socket,&QTcpSocket::readyRead,socket,[socket]{socket->write(socket->readAll());});connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
  }});
  QTemporaryDir temporary;EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,temporary.filePath("nodes.dpapi"));
  const auto o=options(net,false,"global");controller.setProxyPort(o.proxyPort);controller.setRoutingMode("global");
  QVERIFY(controller.saveNode({{"name","original"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",net.a.serverPort()}}));
  const auto id=controller.nodes().first().toMap().value("id").toString();controller.connectNode(id);QVERIFY(QTest::qWaitFor([&]{return controller.connected();},5000));
  const auto pid=controller.processId();QTcpSocket client;client.setProxy(QNetworkProxy::NoProxy);client.connectToHost(QHostAddress::LocalHost,controller.activeProxyPort());
  QVERIFY(QTest::qWaitFor([&]{return client.state()==QAbstractSocket::ConnectedState;},5000));
  client.write("CONNECT 127.0.0.1:"+QByteArray::number(origin.serverPort())+" HTTP/1.1\r\nHost: fixture\r\n\r\n");QByteArray bytes;
  QVERIFY(QTest::qWaitFor([&]{bytes+=client.readAll();return bytes.contains("200 Connection Established");},5000));
  controller.imports()->importText(QString("socks5://127.0.0.1:%1#new-subscription-node").arg(net.a.serverPort()));
  QVERIFY(QTest::qWaitFor([&]{return !controller.imports()->busy();},5000));QVERIFY(controller.nodes().size()>=2);QCOMPARE(controller.processId(),pid);
  client.write("still-connected-after-import");bytes.clear();QVERIFY(QTest::qWaitFor([&]{bytes+=client.readAll();return bytes=="still-connected-after-import";},5000));
  client.abort();controller.shutdown();QVERIFY(QTest::qWaitFor([&]{return !controller.processAlive();},5000));
 }

 void streamedProtocolsSurviveMaintenance_data(){
  QTest::addColumn<bool>("compatibility");QTest::addColumn<QString>("mode");
  for(bool compatibility:{false,true})for(const auto &mode:{QString("rule"),QString("global")})QTest::newRow(qPrintable((compatibility?"mihomo-":"native-")+mode))<<compatibility<<mode;
 }
 void streamedProtocolsSurviveMaintenance(){
  QFETCH(bool,compatibility);QFETCH(QString,mode);
  ControlledNetwork net;QVERIFY(net.start());QSslServer origin;origin.setSslConfiguration(net.https.sslConfiguration());QVERIFY(origin.listen(QHostAddress::LocalHost));
  net.a.targetPorts.append(origin.serverPort());net.b.targetPorts.append(origin.serverPort());
  connect(&origin,&QTcpServer::pendingConnectionAvailable,&origin,[&]{while(auto *socket=origin.nextPendingConnection()){
   connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
   connect(socket,&QTcpSocket::readyRead,socket,[socket]{
    auto input=socket->property("input").toByteArray()+socket->readAll();
    if(!socket->property("headers").toBool()){
     const auto end=input.indexOf("\r\n\r\n");if(end<0){socket->setProperty("input",input);return;}
     socket->setProperty("headers",true);
     if(input.startsWith("GET /cut ")){
      socket->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\nd\r\ndata: first\n\n\r\n");
      QTimer::singleShot(150,socket,[socket]{socket->abort();});return;
     }
     if(input.startsWith("GET /reject ")){socket->write("HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n");socket->disconnectFromHost();return;}
     if(input.startsWith("GET /sse ")){
      socket->write("HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n");
      auto send=[socket](const QByteArray &event){socket->write(QByteArray::number(event.size(),16)+"\r\n"+event+"\r\n");};
      send("data: first\n\n");
      QTimer::singleShot(600,socket,[socket,send]{send("data: after-idle\n\n");send("data: last\n\n");socket->write("0\r\n\r\n");socket->disconnectFromHost();});return;
     }
     if(!input.contains("Upgrade: websocket\r\n")){socket->abort();return;}
     const auto key=input.split('\n');QByteArray challenge;
     for(auto line:key)if(line.startsWith("Sec-WebSocket-Key:"))challenge=line.mid(18).trimmed();
     if(challenge.isEmpty()){socket->abort();return;}
     const auto accept=QCryptographicHash::hash(challenge+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11",QCryptographicHash::Sha1).toBase64();
     socket->write("HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Accept: "+accept+"\r\n\r\n");
     socket->setProperty("websocket",true);input.remove(0,end+4);
    }
    if(socket->property("websocket").toBool())while(input.size()>=6){
     const int size=quint8(input[1])&127;if(!(quint8(input[1])&128)||size>=126){socket->abort();return;}
     if(input.size()<6+size)break;
     const int opcode=quint8(input[0])&15;QByteArray payload=input.mid(6,size);
     for(int i=0;i<size;++i)payload[i]=char(payload[i]^input[2+i%4]);input.remove(0,6+size);
     QByteArray response;response+=char(0x80|(opcode==9?10:opcode));response+=char(size);response+=payload;socket->write(response);
     if(opcode==8){socket->disconnectFromHost();break;}
    }
    socket->setProperty("input",input);
   });
   if(socket->bytesAvailable())QMetaObject::invokeMethod(socket,"readyRead",Qt::QueuedConnection);
  }});
  auto o=options(net,compatibility,mode);ThreadedEngine engine;engine.start(o);
  QVERIFY2(QTest::qWaitFor([&]{return engine.status().apiHealthy;},15000),qPrintable(engine.status().message));const auto pid=engine.status().processId;const auto session=engine.status().sessionId;
  QSslSocket websocket;configure(websocket,net,o,origin.serverPort());QVERIFY(QTest::qWaitFor([&]{return websocket.isEncrypted();},5000));
  websocket.write("GET /ws HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n");
  QByteArray bytes;QVERIFY(receive(websocket,bytes,"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo="));
  auto probeOptions=o;probeOptions.tunEnabled=true;probeOptions.meteredNetwork=true;probeOptions.allowLan=true;
  NodeTestService probes;probes.start(probeOptions,{o.nodes.first().id},net.url());
  QVERIFY(QTest::qWaitFor([&]{return !probes.busy();},30000));QCOMPARE(probes.succeeded(),1);
  QCOMPARE(engine.status().processId,pid);QCOMPARE(engine.status().sessionId,session);
  engine.selectNode(o.nodes.last().id);QVERIFY(QTest::qWaitFor([&]{return engine.status().selectedNodeId==o.nodes.last().id;},5000));
  bytes.clear();websocket.write(frame("alive-after-probe-and-switch"));QVERIFY(receive(websocket,bytes,"alive-after-probe-and-switch"));
  // A failed dial on the newly selected node must finish as a failure while
  // the healthy stream on the previous node remains usable.
  net.b.reject=true;QSslSocket failedDial;configure(failedDial,net,o,origin.serverPort());
  QVERIFY(QTest::qWaitFor([&]{return failedDial.state()==QAbstractSocket::UnconnectedState;},5000));
  QVERIFY(!failedDial.isEncrypted());QVERIFY(failedDial.error()!=QAbstractSocket::UnknownSocketError);
  QCOMPARE(engine.status().processId,pid);QCOMPARE(engine.status().sessionId,session);
  bytes.clear();websocket.write(frame("healthy-after-failed-new-dial"));QVERIFY(receive(websocket,bytes,"healthy-after-failed-new-dial"));
  net.b.reject=false;
  // Backpressure: wait before consuming a burst larger than the relay queue.
  QByteArray burst,expected;for(int i=0;i<6000;++i){const QByteArray payload(100,char('a'+i%20));burst+=frame(payload);expected+=QByteArray::fromHex("8164")+payload;}
  websocket.write(burst);QTest::qWait(250);bytes.clear();QVERIFY(QTest::qWaitFor([&]{bytes+=websocket.readAll();return bytes.size()>=expected.size();},10000));QCOMPARE(bytes,expected);
  QSslSocket sse;configure(sse,net,o,origin.serverPort());QVERIFY(QTest::qWaitFor([&]{return sse.isEncrypted();},5000));
  sse.write("GET /sse HTTP/1.1\r\nHost: localhost\r\nAccept: text/event-stream\r\n\r\n");bytes.clear();QVERIFY(receive(sse,bytes,"data: first"));QVERIFY(!bytes.contains("data: last"));
  engine.setRoutingMode(mode=="rule"?"global":"rule");QVERIFY(receive(sse,bytes,"data: last"));QVERIFY(bytes.contains("data: after-idle"));
  bytes.clear();websocket.write(frame("after-mode-change",9));QVERIFY(receive(websocket,bytes,"after-mode-change"));QVERIFY(bytes.startsWith(QByteArray::fromHex("8a")));
  QSslSocket rejected;configure(rejected,net,o,origin.serverPort());QVERIFY(QTest::qWaitFor([&]{return rejected.isEncrypted();},5000));
  rejected.write("GET /reject HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n\r\n");bytes.clear();QVERIFY(receive(rejected,bytes,"403 Forbidden"));
  QSslSocket cut;configure(cut,net,o,origin.serverPort());QVERIFY(QTest::qWaitFor([&]{return cut.isEncrypted();},5000));
  cut.write("GET /cut HTTP/1.1\r\nHost: localhost\r\n\r\n");bytes.clear();QVERIFY(receive(cut,bytes,"data: first"));
  QVERIFY(QTest::qWaitFor([&]{bytes+=cut.readAll();return cut.state()==QAbstractSocket::UnconnectedState;},5000));
  QVERIFY(!bytes.endsWith("0\r\n\r\n")); // Truncation stays visible; no fabricated completion or replay.
  bytes.clear();websocket.write(frame(QByteArray::fromHex("03e8"),8));QVERIFY(receive(websocket,bytes,QByteArray::fromHex("880203e8")));
  engine.stop();QVERIFY(QTest::qWaitFor([&]{return !engine.status().processAlive&&engine.status().state==ProxyEngine::State::Stopped;},5000));
 }
};
QTEST_GUILESS_MAIN(NetworkRegressionTests)
#include "NetworkRegressionTests.moc"
