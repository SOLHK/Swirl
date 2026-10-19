#include "engine/RustCoreEngine.h"
#include "engine/ThreadedEngine.h"
#include "engine/NodeTestService.h"
#include "engine/NodeImporter.h"
#include "engine/SwirlProtocolRegistry.h"
#include "engine/EngineController.h"
#include "ControlledNetwork.h"
#include <QTest>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QNetworkDatagram>
#include <QUdpSocket>
#include <QUuid>
#include <QJsonArray>
#include <QJsonDocument>
#include <QTemporaryDir>
#include <QSettings>
#include <QThreadPool>
#include "app/StoragePaths.h"

class RustCoreTests:public QObject {
 Q_OBJECT
 EngineStartOptions options(ControlledNetwork &net){
  EngineStartOptions o;QTcpServer port;port.listen(QHostAddress::LocalHost);o.proxyPort=port.serverPort();o.routingMode="global";
  ProxyNode n;n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);n.name="synthetic";n.protocol="socks5";n.host="127.0.0.1";n.port=net.a.serverPort();
  o.nodes={n};o.selectedNodeId=n.id;return o;
 }
 QList<QByteArray> socks5Sources(quint16 port,bool authenticated,int udp=-1,bool tls=false){
  QJsonObject proxy{{"name","fixture"},{"type","socks5"},{"server","127.0.0.1"},{"port",port}};
  QByteArray ini="[Proxy]\nfixture = socks5,127.0.0.1,"+QByteArray::number(port);
  if(authenticated){
   proxy["username"]="synthetic-socks5-user";proxy["password"]="synthetic-socks5-password";
   ini+=",username=synthetic-socks5-user,password=synthetic-socks5-password";
  }
  if(udp>=0){proxy["udp"]=udp==1;ini+=udp==1?",udp-relay=true":",udp-relay=false";}
  if(tls){proxy["tls"]=true;ini+=",over-tls=true";}
  return {QJsonDocument(QJsonObject{{"proxies",QJsonArray{proxy}}}).toJson(),ini+"\n"};
 }
private slots:
 void initTestCase(){QStandardPaths::setTestModeEnabled(true);SwirlPaths::initializeTestStorage();QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation));}
 void fullDocumentCannotUseExternalSelectedNodeAlias(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");NodeStore seed(path);
  QVERIFY(seed.saveSubscription({},"retained source",QUrl("https://fixture.invalid/retained"),360,false));const auto oldSource=seed.subscriptions().first().id;
  QVERIFY(seed.saveSubscription({},"incoming source",QUrl("https://fixture.invalid/incoming"),360,false));const auto newSource=seed.subscriptions().last().id;QVERIFY(oldSource!=newSource);
  const auto old=NodeImporter::parse("proxies: [{name: outside, type: socks5, server: 127.0.0.1, port: 1080}]");QVERIFY(old);QVERIFY(seed.importNodes(old.nodes,oldSource));const auto oldId=seed.nodes().first().id;QVERIFY(seed.select(oldId));
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  QVERIFY(controller.saveRoutingRule("MATCH",{},"SWIRL")); // Existing native editor meaning remains supported.
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto before=file.readAll();file.close();const auto network=controller.networkConfigurationSnapshot();
  const auto incoming=NodeImporter::parse("proxies: [{name: inside, type: socks5, server: 127.0.0.1, port: 1081}]");QVERIFY(incoming);
  for(const auto &target:QStringList{"SWIRL","GLOBAL","outside",oldId}){
   const QVariantMap settings{{"rules",QStringList{"MATCH,"+target}}};const QJsonObject original{{"rules",QJsonArray{"MATCH,"+target}}};
   QVERIFY(!controller.importNodesAndConfiguration(incoming.nodes,newSource,settings,original));
   QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.networkConfigurationSnapshot(),network);
   QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),before);file.close();NodeStore reopened(path);QCOMPARE(reopened.selectedId(),oldId);QCOMPARE(reopened.nodes().first().sourceId,oldSource);
  }
  controller.imports()->importText("proxies: [{name: inside, type: socks5, server: 127.0.0.1, port: 1081}]\nrules: ['MATCH,SWIRL']\n");QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),4000);QCOMPARE(controller.nodeCatalog().size(),1);
 }
 void nonClashGlobalConfigurationDoesNotAlterNativeState(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  controller.imports()->importText("proxies: [{name: retained, type: socks5, server: 127.0.0.1, port: 1080}]");QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),4000);QCOMPARE(controller.nodeCatalog().size(),1);
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto before=file.readAll();file.close();const auto nodes=controller.nodeCatalog();const auto network=controller.networkConfigurationSnapshot();
  for(const auto &body:{QByteArray("[Proxy]\nA = socks5, 127.0.0.1, 1081\n[Rule]\nFINAL,A\n[Future]\nfixture-secret\n"),QByteArray(R"({"outbounds":[{"type":"socks","tag":"A","server":"127.0.0.1","server_port":1081},{"type":"selector","tag":"choice","outbounds":["A"]}],"route":{"final":"choice"}})")}){
   controller.imports()->importText(QString::fromUtf8(body));QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),4000);QCOMPARE(controller.nodeCatalog(),nodes);QCOMPARE(controller.networkConfigurationSnapshot(),network);
   QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),before);file.close();QVERIFY(!controller.imports()->message().contains("fixture-secret"));QVERIFY(!controller.processAlive());
  }
 }
 void fullClashSubscriptionReachesNativePolicyAndRejectsPartialUpdates(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);QTcpServer port;QVERIFY(port.listen(QHostAddress::LocalHost));const auto proxyPort=port.serverPort();port.close();controller.setProxyPort(proxyPort);controller.setRoutingMode("rule");
  QJsonArray proxies{QJsonObject{{"name","A"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.a.serverPort()}},QJsonObject{{"name","B"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.b.serverPort()},{"username",QString::fromUtf8(net.b.username)},{"password",QString::fromUtf8(net.b.password)}}};
  const QJsonObject route{{"name","route"},{"type","select"},{"proxies",QJsonArray{"B","A"}}};
  QJsonObject document{{"proxies",proxies},{"proxy-groups",QJsonArray{route}},{"rules",QJsonArray{"MATCH,route"}}};
  QByteArray body=QJsonDocument(document).toJson();QTcpServer subscription;QVERIFY(subscription.listen(QHostAddress::LocalHost));int downloads=0;
  connect(&subscription,&QTcpServer::newConnection,this,[&]{while(subscription.hasPendingConnections()){
   auto *socket=subscription.nextPendingConnection();connect(socket,&QTcpSocket::readyRead,socket,[&,socket]{socket->readAll();if(socket->property("done").toBool())return;socket->setProperty("done",true);++downloads;socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(body.size())+"\r\nConnection: close\r\n\r\n"+body);socket->disconnectFromHost();});connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
  }});
  auto *imports=controller.imports();QVERIFY(imports->saveSubscription({},"fixture",QUrl(QString("http://127.0.0.1:%1/sub").arg(subscription.serverPort())),360,false));const auto source=imports->providers().first().toMap().value("id").toString();
  imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(downloads,1);QCOMPARE(controller.nodeCatalog().size(),2);
  const auto id=controller.nodeCatalog().first().toMap().value("id").toString();const auto group=controller.policyGroups();
  NodeStore disk(path);QCOMPARE(disk.networkConfiguration()["importedConfiguration"].toObject()["configuration"].toObject()["rules"],document["rules"]);
  controller.start();QVERIFY(!controller.processAlive());QVERIFY(!controller.apiHealthy());
  controller.connectNode(QString{});QVERIFY(!controller.processAlive());QVERIFY(!controller.apiHealthy());
  controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),4000);
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",proxyPort));QNetworkRequest request(net.url());request.setTransferTimeout(4000);auto *reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->readAll(),QByteArray("exit-B"));QCOMPARE(net.a.forwarded,0);QCOMPARE(net.b.forwarded,1);reply->deleteLater();
  // A complete document refresh cannot alter a running immutable session.
  imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QVERIFY(controller.apiHealthy());QCOMPARE(controller.policyGroups(),group);QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
  body=QJsonDocument(QJsonObject{{"proxies",QJsonArray{proxies.first()}}}).toJson();imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QVERIFY(controller.apiHealthy());QCOMPARE(controller.nodeCatalog().size(),2);QCOMPARE(controller.policyGroups(),group);
  {NodeStore unchanged(path);QCOMPARE(unchanged.nodes().size(),2);}
  controller.disconnectNode();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
  for(const auto &mutation:QList<QJsonObject>{QJsonObject{{"future-global",true}},QJsonObject{{"dns",QJsonObject{{"respect-rules",true}}}},QJsonObject{{"rules",QJsonArray{false}}},QJsonObject{{"proxy-groups","not-an-array"}},QJsonObject{{"rules",QJsonArray{"PROCESS-NAME,fixture.exe,route","MATCH,route"}}},QJsonObject{{"rules",QJsonArray{"DOMAIN,example.invalid,route"}}}}) {
   auto invalid=document;for(auto it=mutation.begin();it!=mutation.end();++it)invalid[it.key()]=it.value();body=QJsonDocument(invalid).toJson();imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.policyGroups(),group);QCOMPARE(controller.nodeCatalog().size(),2);QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
  }
  body=QJsonDocument(document).toJson();imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);QCOMPARE(controller.policyGroups(),group);
  EngineController reopened(std::make_unique<RustCoreEngine>(),nullptr,path,true);reopened.setProxyPort(proxyPort);reopened.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(reopened.apiHealthy(),4000);
  reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->readAll(),QByteArray("exit-B"));reply->deleteLater();reopened.stop();QTRY_VERIFY_WITH_TIMEOUT(!reopened.processAlive(),4000);
  NodeStore persisted(path);QCOMPARE(persisted.networkConfiguration()["nativeDocumentRouting"],QJsonValue(true));
 }
 void iniProfileImportConnectsAndUpdatesAtomically(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);QTcpServer port;QVERIFY(port.listen(QHostAddress::LocalHost));const auto proxyPort=port.serverPort();port.close();controller.setProxyPort(proxyPort);controller.setRoutingMode("rule");
  const auto a=QString("A = socks5,127.0.0.1,%1\n").arg(net.a.serverPort()).toUtf8();
  const auto b=QString("B = socks5,127.0.0.1,%1,username=%2,password=%3\n").arg(net.b.serverPort()).arg(QString::fromUtf8(net.b.username),QString::fromUtf8(net.b.password)).toUtf8();
  const QByteArray original="[Proxy]\n"+a+b+"[Proxy Group]\nroute = select,B,A\n[Rule]\nDOMAIN,localhost,REJECT\nFINAL,route\n";
  QByteArray body=original;int status=200,downloads=0;QTcpServer subscription;QVERIFY(subscription.listen(QHostAddress::LocalHost));net.a.targetPorts.append(subscription.serverPort());net.b.targetPorts.append(subscription.serverPort());
  connect(&subscription,&QTcpServer::newConnection,this,[&]{while(subscription.hasPendingConnections()){
   auto *socket=subscription.nextPendingConnection();connect(socket,&QTcpSocket::readyRead,socket,[&,socket]{socket->readAll();if(socket->property("done").toBool())return;socket->setProperty("done",true);++downloads;socket->write("HTTP/1.1 "+QByteArray::number(status)+" Fixture\r\nContent-Length: "+QByteArray::number(body.size())+"\r\nConnection: close\r\n\r\n"+body);socket->disconnectFromHost();});connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
  }});
  auto *imports=controller.imports();QVERIFY(imports->saveSubscription({},"INI fixture",QUrl(QString("http://127.0.0.1:%1/sub").arg(subscription.serverPort())),360,false));const auto source=imports->providers().first().toMap().value("id").toString();
  imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(downloads,1);QCOMPARE(controller.nodeCatalog().size(),2);
  const auto id=controller.nodeCatalog().first().toMap().value("id").toString();auto beforeNetwork=controller.networkConfigurationSnapshot();const auto beforeNodes=controller.nodeCatalog();
  {NodeStore disk(path);const auto imported=disk.networkConfiguration()["importedConfiguration"].toObject();QCOMPARE(imported["format"],QJsonValue("ini"));QCOMPARE(imported["configuration"].toObject()["document"],QJsonValue(QString::fromUtf8(original).trimmed()));}
  controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),4000);
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",proxyPort));QNetworkRequest request(net.url());request.setTransferTimeout(4000);
  auto *reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-B"));reply->deleteLater();
  const auto forwarded=net.a.forwarded+net.b.forwarded;auto deniedUrl=net.url();deniedUrl.setHost("localhost");QNetworkRequest denied(deniedUrl);denied.setTransferTimeout(4000);reply=client.get(denied);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QVERIFY(reply->error()!=QNetworkReply::NoError);QCOMPARE(net.a.forwarded+net.b.forwarded,forwarded);reply->deleteLater();
  body="[Proxy]\n"+a+"[Proxy Group]\nroute = select,A\n[Rule]\nFINAL,route\n";
  imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(downloads,2);QVERIFY(controller.apiHealthy());QCOMPARE(controller.nodeCatalog(),beforeNodes);QCOMPARE(controller.networkConfigurationSnapshot(),beforeNetwork);
  controller.disconnectNode();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
  body=original;body.replace("select,B,A","select,A,B");imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);
  QCOMPARE(controller.nodeCatalog(),beforeNodes);const auto retained=controller.networkConfigurationSnapshot().value("groups").toList().first().toMap();QCOMPARE(retained.value("default-selected").toString(),controller.nodeCatalog().last().toMap().value("id").toString());
  controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),4000);reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->readAll(),QByteArray("exit-B"));reply->deleteLater();controller.disconnectNode();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
  beforeNetwork=controller.networkConfigurationSnapshot();
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto ciphertext=file.readAll();file.close();
  QList<QByteArray> invalid{original+"[General]\ndns-server=192.0.2.53\n",original+"[Remote Rule]\nhttps://fixture.invalid/rules,policy=route\n",original+"DOMAIN,late.invalid,route\n"};
  for(const auto &replacement:{"IP-CIDR,192.0.2.0/24,route","PROCESS-NAME,fixture.exe,route","DOMAIN,example.invalid,route,no-resolve","DOMAIN,example.invalid,SWIRL"}){auto bad=original;bad.replace("DOMAIN,localhost,REJECT",replacement);invalid.append(bad);}
  {auto bad=original;bad.replace("select,B,A","url-test,B,A");invalid.append(bad);bad=original;bad.replace("select,B,A","select,missing");invalid.append(bad);bad=original;bad.replace("FINAL,route\n","");invalid.append(bad);}
  invalid.append("[Proxy]\n"+a+"[Proxy Group]\nroute = select,A\n[Rule]\n"+QByteArray("DOMAIN,example.invalid,REJECT\n").repeated(1000)+"FINAL,route\n");
  for(const auto &bad:invalid){body=bad;imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog(),beforeNodes);QCOMPARE(controller.networkConfigurationSnapshot(),beforeNetwork);QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),ciphertext);file.close();}
  status=503;body=original;imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog(),beforeNodes);status=200;
  body="[Proxy]\n"+a+"[Proxy Group]\nroute = select,A\n[Rule]\nFINAL,route\n";imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);
  controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),4000);reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-A"));reply->deleteLater();controller.disconnectNode();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
  body.replace("A =","Renamed =");body.replace("select,A","select,Renamed");imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog().size(),1);const auto renamed=controller.nodeCatalog().first().toMap().value("id").toString();QVERIFY(renamed!=id);
  EngineController reopened(std::make_unique<RustCoreEngine>(),nullptr,path,true);reopened.setProxyPort(proxyPort);reopened.connectNode(renamed);QTRY_VERIFY_WITH_TIMEOUT(reopened.apiHealthy(),4000);reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->readAll(),QByteArray("exit-A"));reply->deleteLater();reopened.stop();QTRY_VERIFY_WITH_TIMEOUT(!reopened.processAlive(),4000);
 }
 void iniRealityCannotStartAsOrdinaryTls(){
  QTcpServer endpoint;QVERIFY(endpoint.listen(QHostAddress::LocalHost));int requests=0;connect(&endpoint,&QTcpServer::newConnection,this,[&]{++requests;});
  for(const auto &protocol:{"vless","trojan"}) {
   const auto credential=QByteArray(protocol)=="vless"?"11111111-1111-4111-8111-111111111111":"synthetic";
   const auto document=QByteArray("[Proxy]\nfixture = ")+protocol+",127.0.0.1,"+QByteArray::number(endpoint.serverPort())+","+credential+",transport=reality,public-key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
   const auto parsed=NodeImporter::parse(document);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);QVERIFY(parsed.nodes.first().parameters.contains("reality-opts"));
   const auto id=QUuid::createUuid().toString(QUuid::WithoutBraces);EngineStartOptions options;options.nodes=parsed.nodes;options.nodes.first().id=id;options.selectedNodeId=id;options.routingMode="global";options.proxyPort=endpoint.serverPort();QJsonObject configuration;
   auto plain=options;auto simple=document;simple.replace(",transport=reality,public-key=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",",tls=true");const auto plainParsed=NodeImporter::parse(simple);QVERIFY(plainParsed);plain.nodes=plainParsed.nodes;plain.nodes.first().id=id;const auto plainError=RustCoreEngine::configuration(plain,&configuration);QVERIFY2(plainError.isEmpty(),qPrintable(plainError));
   QVERIFY(!RustCoreEngine::configuration(options,&configuration).isEmpty());RustCoreEngine engine;engine.start(options);QCOMPARE(engine.status().state,ProxyEngine::State::Failed);QVERIFY(!engine.status().processAlive);
  }
  QCoreApplication::processEvents();QCOMPARE(requests,0);
 }
 void profileRefreshKeepsOnlyItsOwnValidSelection(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");NodeStore seed(path);
  QVERIFY(seed.saveSubscription({},"first",QUrl("https://fixture.invalid/first"),360,false));const auto first=seed.subscriptions().last().id;
  QVERIFY(seed.saveSubscription({},"second",QUrl("https://fixture.invalid/second"),360,false));const auto second=seed.subscriptions().last().id;
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  const auto nodes=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}, {name: B, type: socks5, server: 127.0.0.1, port: 1081}]");QVERIFY(nodes);
  const QJsonObject original{{"fixture",true}};
  auto apply=[&](const QString &source,const QStringList &members,const QString &explicitChoice=QString()){
   QVariantMap group{{"name","route"},{"type","select"},{"proxies",members}};if(!explicitChoice.isEmpty())group["default-selected"]=explicitChoice;
   auto incoming=nodes.nodes;for(auto &node:incoming)node.id=QUuid::createUuid().toString(QUuid::WithoutBraces);
   return controller.importNodesAndConfiguration(incoming,source,{{"groups",QVariantList{group}},{"rules",QStringList{"MATCH,route"}}},original);
  };
  auto current=[&]{return controller.networkConfigurationSnapshot().value("groups").toList().first().toMap();};
  QVERIFY(apply(first,{"B","A"}));const auto firstMembers=current().value("proxies").toStringList();QCOMPARE(firstMembers.size(),2);
  QVERIFY(apply(first,{"A","B"}));QCOMPARE(current().value("default-selected").toString(),firstMembers.first());
  QVERIFY(apply(first,{"B","A"},"A"));QCOMPARE(current().value("default-selected").toString(),firstMembers.last());
  QVERIFY(apply(second,{"B","A"}));QVERIFY(!current().contains("default-selected"));const auto secondMembers=current().value("proxies").toStringList();QVERIFY(secondMembers.first()!=firstMembers.first());
  QVERIFY(apply(second,{"A","B"}));QCOMPARE(current().value("default-selected").toString(),secondMembers.first());
 }
 void atomicNodeNetworkImportUsesPreparedIdsAndSurvivesReload(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  const QVariantMap dns{{"mode",0},{"servers",""},{"encrypted","https://1.1.1.1/dns-query"}};
  QVERIFY(controller.configureDns(dns));const auto preservedDns=controller.dnsConfiguration();
  const auto parsed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]");QVERIFY(parsed);
  const QVariantMap configuration{{"groups",QVariantList{QVariantMap{{"name","choice"},{"type","select"},{"proxies",QStringList{"A","DIRECT"}},{"default-selected","A"}}}},{"rules",QStringList{"MATCH,choice"}}};
  QVERIFY2(controller.importNodesAndConfiguration(parsed.nodes,{},configuration),qPrintable(controller.networkConfigurationError()));
  const auto id=controller.nodeCatalog().first().toMap().value("id").toString();QCOMPARE(controller.dnsConfiguration(),preservedDns);
  QCOMPARE(controller.policyGroups().first().toMap().value("proxies").toStringList(),QStringList({id,"DIRECT"}));
  auto refreshed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1081}]");QVERIFY(refreshed);
  QVERIFY(controller.importNodesAndConfiguration(refreshed.nodes,{},configuration));QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);
  EngineController reopened(std::make_unique<RustCoreEngine>(),nullptr,path);QCOMPARE(QJsonObject::fromVariantMap(reopened.dnsConfiguration()),QJsonObject::fromVariantMap(preservedDns));QCOMPARE(QJsonArray::fromVariantList(reopened.policyGroups()),QJsonArray::fromVariantList(controller.policyGroups()));QCOMPARE(QJsonObject::fromVariantMap(reopened.networkConfigurationSnapshot()),QJsonObject::fromVariantMap(controller.networkConfigurationSnapshot()));
  NodeStore disk(path);QCOMPARE(disk.nodes().first().port,quint16(1081));QCOMPARE(disk.networkConfiguration()["groups"].toArray(),QJsonArray::fromVariantList(controller.policyGroups()));
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));QVERIFY(!file.readAll().contains("choice"));QVERIFY(!QFile::exists(path+".network.json"));
 }
 void atomicNodeNetworkImportRejectsInvalidGraphAndWriteFailure(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  auto parsed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]");QVERIFY(parsed);
  const QVariantMap configuration{{"groups",QVariantList{QVariantMap{{"name","choice"},{"type","select"},{"proxies",QStringList{"A"}}}}},{"rules",QStringList{"MATCH,choice"}}};
  QVERIFY(controller.importNodesAndConfiguration(parsed.nodes,{},configuration));const auto before=controller.networkConfigurationSnapshot();
  parsed.nodes.first().port=1081;auto invalid=configuration;invalid["groups"]=QVariantList{QVariantMap{{"name","choice"},{"type","select"},{"proxies",QStringList{"missing"}}}};
  QVERIFY(!controller.importNodesAndConfiguration(parsed.nodes,{},invalid));QCOMPARE(controller.networkConfigurationSnapshot(),before);
  const auto backup=directory.filePath("old.dpapi");QVERIFY(QFile::rename(path,backup));QVERIFY(QDir().mkdir(path));
  QVERIFY(!controller.importNodesAndConfiguration(parsed.nodes,{},configuration,QJsonObject{{"rules",QJsonArray{"MATCH,choice"}}}));QCOMPARE(controller.networkConfigurationSnapshot(),before);
  QCOMPARE(controller.nodeCatalog().first().toMap().value("port").toInt(),1080);
  QVERIFY(QDir().rmdir(path));QVERIFY(QFile::rename(backup,path));NodeStore disk(path);QCOMPARE(disk.nodes().first().port,quint16(1080));QCOMPARE(disk.networkConfiguration()["groups"].toArray(),QJsonArray::fromVariantList(before.value("groups").toList()));
  QVERIFY(!disk.networkConfiguration().contains("nativeDocumentRouting"));
  QTcpServer port;QVERIFY(port.listen(QHostAddress::LocalHost));const auto listenPort=port.serverPort();port.close();controller.setProxyPort(listenPort);
  controller.connectNode(QString{});QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),4000);controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
 }
 void legacyNetworkSettingsMigrateWithoutStaleSidecarOverride(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");QFile legacy(path+".network.json");
  const QJsonObject original{{"schema",1},{"dns",QJsonObject{}},{"rules",QJsonArray{"MATCH,REJECT"}},{"groups",QJsonArray{}}};
  QVERIFY(legacy.open(QIODevice::WriteOnly));legacy.write(QJsonDocument(original).toJson());legacy.close();
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);QCOMPARE(controller.networkConfigurationSnapshot().value("rules").toStringList(),QStringList{"MATCH,REJECT"});
  QVERIFY(controller.replaceNetworkConfiguration({{"rules",QStringList{"MATCH,DIRECT"}}}));
  EngineController reopened(std::make_unique<RustCoreEngine>(),nullptr,path);QCOMPARE(reopened.networkConfigurationSnapshot().value("rules").toStringList(),QStringList{"MATCH,DIRECT"});
  QVERIFY(legacy.open(QIODevice::ReadOnly));QCOMPARE(QJsonDocument::fromJson(legacy.readAll()).object(),original);
 }
 void candidateValidationPreservesIndependentSourceNamespaces(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");NodeStore store(path);
  auto parsed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]");QVERIFY(parsed);
  for(int i=0;i<2;++i){QVERIFY(store.saveSubscription({},QString("source-%1").arg(i),QUrl(QString("https://example.invalid/%1").arg(i)),360,false));auto nodes=parsed.nodes;nodes.first().id=QUuid::createUuid().toString(QUuid::WithoutBraces);QVERIFY(store.importNodes(nodes,store.subscriptions().last().id));}
  QCOMPARE(store.nodes().size(),2);EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  const QVariantMap configuration{{"groups",QVariantList{QVariantMap{{"name","route"},{"type","select"},{"proxies",QStringList{store.nodes()[0].id,store.nodes()[1].id}}}}},{"rules",QStringList{"MATCH,route"}}};
  QVERIFY2(controller.replaceNetworkConfiguration(configuration),qPrintable(controller.networkConfigurationError()));
  QFile snapshot(path);QVERIFY(snapshot.open(QIODevice::ReadOnly));const auto before=snapshot.readAll();snapshot.close();
  for(const auto &group:QVariantList{
      QVariantMap{{"name","bad"},{"type","select"},{"proxies",QStringList{store.nodes()[1].id}}},
      QVariantMap{{"name","bad"},{"type","select"},{"proxies",QStringList{"A"}},{"default-selected",store.nodes()[0].id}}}) {
   QVERIFY(!controller.importNodesAndConfiguration(parsed.nodes,store.subscriptions()[0].id,{{"groups",QVariantList{group}},{"rules",QStringList{"MATCH,bad"}}}));
   QVERIFY(snapshot.open(QIODevice::ReadOnly));QCOMPARE(snapshot.readAll(),before);snapshot.close();
  }
  QVERIFY(controller.importNodesAndConfiguration(parsed.nodes,store.subscriptions()[0].id,{{"groups",QVariantList{QVariantMap{{"name","new-route"},{"type","select"},{"proxies",QStringList{"A"}}}}},{"rules",QStringList{"MATCH,new-route"}}}));
  NodeStore reopened(path);QCOMPARE(reopened.nodes().size(),2);QCOMPARE(reopened.nodes()[0].sourceId,store.subscriptions()[1].id);
 }
 void shutdownDiscardsPendingParsedConfiguration(){
  QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService imports(&store);
  imports.importText("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]");imports.shutdown();
  QVERIFY(QThreadPool::globalInstance()->waitForDone(5000));QCoreApplication::sendPostedEvents();QCoreApplication::processEvents();
  QVERIFY(store.nodes().isEmpty());QVERIFY(!QFile::exists(store.filePath()));
 }
 void preparedImportMapsStableIdsWithoutPublishingBeforeCommit(){
  QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));
  QVERIFY(store.saveSubscription({},"fixture",QUrl("https://example.invalid/sub"),360,false));
  const auto source=store.subscriptions().first().id;
  auto parsed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]");QVERIFY(parsed);
  QVERIFY(store.importNodes(parsed.nodes,source));const auto id=store.nodes().first().id;QVERIFY(store.select(id));
  QFile original(store.filePath());QVERIFY(original.open(QIODevice::ReadOnly));const auto before=original.readAll();original.close();
  parsed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1081}, {name: B, type: socks5, server: 127.0.0.1, port: 1082}]");QVERIFY(parsed);
  NodeStore::ImportPlan plan;QVERIFY(store.prepareImport(parsed.nodes,source,&plan));
  QCOMPARE(plan.nameToId().value("A"),id);QCOMPARE(plan.importedToStoredIds().value(parsed.nodes.first().id),id);
  QCOMPARE(plan.nodes().size(),2);QCOMPARE(store.nodes().size(),1);QCOMPARE(store.nodes().first().port,quint16(1080));
  QVERIFY(original.open(QIODevice::ReadOnly));QCOMPARE(original.readAll(),before);original.close();
  QVERIFY(store.commitImport(plan));QCOMPARE(store.selectedId(),id);QCOMPARE(store.nodes().first().port,quint16(1081));
  QVERIFY(!store.commitImport(plan));NodeStore reopened(store.filePath());QCOMPARE(reopened.nodes().size(),2);QCOMPARE(reopened.selectedId(),id);
 }
 void preparedImportRejectsAmbiguousIdsCrossSourceAndStalePlans(){
  QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));
  auto parsed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]");QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes));
  NodeStore::ImportPlan plan;auto duplicate=parsed.nodes;auto other=duplicate.first();other.id=QUuid::createUuid().toString(QUuid::WithoutBraces);duplicate.append(other);
  QVERIFY(!store.prepareImport(duplicate,{},&plan));QCOMPARE(store.nodes().size(),1);
  other.name="B";other.id=parsed.nodes.first().id;QVERIFY(!store.prepareImport({other},{},&plan));
  QVERIFY(store.saveSubscription({},"fixture",QUrl("https://example.invalid/sub"),360,false));
  QVERIFY(!store.prepareImport(parsed.nodes,store.subscriptions().first().id,&plan));QVERIFY(store.nodes().first().sourceId.isEmpty());
  QVERIFY(store.prepareImport(parsed.nodes,{},&plan));QVERIFY(store.select(parsed.nodes.first().id));QVERIFY(!store.commitImport(plan));
  NodeStore otherStore(directory.filePath("other.dpapi"));QVERIFY(!otherStore.commitImport(plan));
  NodeStore::ImportPlan empty;QVERIFY(!store.commitImport(empty));QCOMPARE(store.nodes().size(),1);
 }
 void preparedImportWriteFailurePreservesMemoryAndDurableSnapshot(){
  QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));
  auto parsed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]");QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes));
  const auto id=store.nodes().first().id;parsed.nodes.first().port=1081;
  NodeStore::ImportPlan plan;QVERIFY(store.prepareImport(parsed.nodes,{},&plan));
  // A directory at the destination forces a real QSaveFile failure without
  // permission assumptions or a production fault-injection switch.
  const auto backup=directory.filePath("old.dpapi");QVERIFY(QFile::rename(store.filePath(),backup));QVERIFY(QDir().mkdir(store.filePath()));
  QVERIFY(!store.commitImport(plan));QCOMPARE(store.nodes().first().port,quint16(1080));QCOMPARE(store.nodes().first().id,id);
  QVERIFY(QDir().rmdir(store.filePath()));QVERIFY(QFile::rename(backup,store.filePath()));
  NodeStore reopened(store.filePath());QCOMPARE(reopened.nodes().first().port,quint16(1080));QCOMPARE(reopened.nodes().first().id,id);
 }
 void socks5UdpMappingPreservesTypedOptionsAndTls(){
  EngineStartOptions o;o.routingMode="global";
  const QJsonObject sentinel{{"unchanged",true}};
  for(const bool authenticated:{false,true})for(const int udp:{-1,0,1}){
   for(const auto &source:socks5Sources(1080,authenticated,udp)){
    const auto parsed=NodeImporter::parse(source);QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
    const auto &node=parsed.nodes.first();QCOMPARE(node.protocol,QString("socks5"));
    QVERIFY(node.conversionIssues.isEmpty());QVERIFY(!node.originalConfiguration.isEmpty());
    QCOMPARE(node.parameters.contains("udp"),udp>=0);
    if(udp>=0)QCOMPARE(node.parameters.value("udp"),QJsonValue(udp==1));
    QCOMPARE(node.username,authenticated?QString("synthetic-socks5-user"):QString());
    QCOMPARE(node.password,authenticated?QString("synthetic-socks5-password"):QString());
    o.nodes=parsed.nodes;o.selectedNodeId=node.id;QJsonObject config;
    const auto error=RustCoreEngine::configuration(o,&config);QVERIFY2(error.isEmpty(),qPrintable(error));
    QJsonObject expected{{"type","socks5"},{"host","127.0.0.1"},{"port",1080},{"udp",udp==1}};
    if(authenticated)expected["auth"]=QJsonObject{{"username","synthetic-socks5-user"},{"password","synthetic-socks5-password"}};
    QCOMPARE(config["nodes"].toArray().first().toObject()["outbound"].toObject(),expected);
    QVERIFY(SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
   }
  }
  // TLS remains explicit. Enabling UDP may not silently erase it, while the
  // existing TCP-only TLS configuration still crosses the real native ABI.
  for(const auto &source:socks5Sources(1080,true,1,true)){
   const auto parsed=NodeImporter::parse(source);QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
   const auto &node=parsed.nodes.first();QCOMPARE(node.parameters.value("tls"),QJsonValue(true));QCOMPARE(node.parameters.value("udp"),QJsonValue(true));
   o.nodes=parsed.nodes;o.selectedNodeId=node.id;QJsonObject config=sentinel;
   QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());QCOMPARE(config,sentinel);
   RustCoreEngine engine;engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Failed);
   QCOMPARE(engine.status().error,ProxyEngine::Error::InvalidOptions);QVERIFY(!engine.status().processAlive);QVERIFY(!engine.status().apiHealthy);
  }
  auto tcpTlsSources=socks5Sources(1080,true,0,true);
  tcpTlsSources.append("socks5-tls://synthetic-socks5-user:synthetic-socks5-password@127.0.0.1:1080#fixture");
  for(const auto &source:tcpTlsSources){
   const auto parsed=NodeImporter::parse(source);QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
   const auto &node=parsed.nodes.first();QCOMPARE(node.parameters.value("tls"),QJsonValue(true));QVERIFY(node.conversionIssues.isEmpty());
   o.nodes=parsed.nodes;o.selectedNodeId=node.id;QJsonObject config;
   const auto error=RustCoreEngine::configuration(o,&config);QVERIFY2(error.isEmpty(),qPrintable(error));
   const auto outbound=config["nodes"].toArray().first().toObject()["outbound"].toObject();
   QCOMPARE(outbound["udp"],QJsonValue(false));
   const QJsonObject tls{{"server_name","127.0.0.1"},{"alpn",QJsonArray{}}};QCOMPARE(outbound["tls"].toObject(),tls);
   QTcpServer port;QVERIFY(port.listen(QHostAddress::LocalHost));o.proxyPort=port.serverPort();port.close();
   RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
   QCOMPARE(engine.status().engineKind,QString("rust"));engine.stop();QCOMPARE(engine.status().state,ProxyEngine::State::Stopped);
  }
  for(const auto &source:QList<QByteArray>{
      "socks5-tls://127.0.0.1:1080?udp=true#fixture",
      "socks5-tls://127.0.0.1:1080?tls=false#fixture"}){
   const auto parsed=NodeImporter::parse(source);QVERIFY2(bool(parsed),qPrintable(parsed.error));
   QCOMPARE(parsed.nodes.first().parameters.value("tls"),QJsonValue(true));
   o.nodes=parsed.nodes;o.selectedNodeId=parsed.nodes.first().id;QJsonObject config=sentinel;
   QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());QCOMPARE(config,sentinel);
  }
  const QJsonObject base{{"name","fixture"},{"type","socks5"},{"server","127.0.0.1"},{"port",1080}};
  for(const auto &value:QList<QJsonValue>{"true","false",0,1,QJsonValue(QJsonValue::Null),QJsonObject{},QJsonArray{}}){
   auto proxy=base;proxy["udp"]=value;
   const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{proxy}}}).toJson());
   QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.first().originalConfiguration,proxy);
   QCOMPARE(parsed.nodes.first().parameters.value("udp"),value);
   o.nodes=parsed.nodes;o.selectedNodeId=parsed.nodes.first().id;QJsonObject config=sentinel;
   QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());QCOMPARE(config,sentinel);
  }
  auto unknown=base;unknown["udp"]=true;unknown["future-udp-mode"]="preserved";
  const QList<QByteArray> unknownSources{QJsonDocument(QJsonObject{{"proxies",QJsonArray{unknown}}}).toJson(),
    "[Proxy]\nfixture = socks5,127.0.0.1,1080,udp-relay=true,future-udp-mode=preserved\n"};
  for(const auto &source:unknownSources){
   const auto parsed=NodeImporter::parse(source);QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
   const auto &node=parsed.nodes.first();QVERIFY(!node.originalConfiguration.isEmpty());
   QVERIFY(node.parameters.contains("future-udp-mode")||!node.conversionIssues.isEmpty());
   o.nodes=parsed.nodes;o.selectedNodeId=node.id;QJsonObject config=sentinel;
   QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());QCOMPARE(config,sentinel);
  }
  auto insecure=base;insecure["tls"]=true;insecure["skip-cert-verify"]=true;
  QVERIFY(!NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{insecure}}}).toJson()));
  QVERIFY(!NodeImporter::parse("[Proxy]\nfixture = socks5,127.0.0.1,1080,over-tls=true,tls-verification=false\n"));
  QVERIFY(!NodeImporter::parse("[Proxy]\nfixture = socks5,127.0.0.1,1080,udp-relay=maybe\n"));
  QVERIFY(!NodeImporter::parse("[Proxy]\nfixture = socks5,127.0.0.1,1080,udp-relay=true,udp=false\n"));
  const auto valid=NodeImporter::parse(socks5Sources(1080,false,0,true).first());QVERIFY(bool(valid));
  o.nodes=valid.nodes;o.selectedNodeId=o.nodes.first().id;o.nodes.first().parameters["skip-cert-verify"]=true;
  QJsonObject config=sentinel;QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());QCOMPARE(config,sentinel);
 }
 void socks5UdpThroughIndependentPeer(){
  const bool hasPeer=qEnvironmentVariableIsSet("SWIRL_SOCKS5_UDP_REFERENCE_PORT");
  const bool hasOrigin=qEnvironmentVariableIsSet("SWIRL_SOCKS5_UDP_ORIGIN_PORT");
  const bool hasAuth=qEnvironmentVariableIsSet("SWIRL_SOCKS5_UDP_EXPECT_AUTH");
  if(!hasPeer&&!hasOrigin&&!hasAuth)QSKIP("Independent Python SOCKS5 UDP peer supplies isolated ports and authentication mode in its integration run.");
  QVERIFY2(hasPeer&&hasOrigin&&hasAuth,"All SOCKS5 UDP reference environment variables must be supplied together.");
  bool validPeer=false,validOrigin=false;
  const int peer=qEnvironmentVariableIntValue("SWIRL_SOCKS5_UDP_REFERENCE_PORT",&validPeer);
  const int origin=qEnvironmentVariableIntValue("SWIRL_SOCKS5_UDP_ORIGIN_PORT",&validOrigin);
  const auto auth=qgetenv("SWIRL_SOCKS5_UDP_EXPECT_AUTH");
  QVERIFY(validPeer&&validOrigin&&peer>0&&peer<=65535&&origin>0&&origin<=65535);
  QVERIFY2(auth=="0"||auth=="1","SOCKS5 UDP authentication mode must be exactly 0 or 1.");
  const auto sources=socks5Sources(quint16(peer),auth=="1",1);
  for(qsizetype index=0;index<sources.size();++index){
   const auto parsed=NodeImporter::parse(sources[index]);QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
   const auto &node=parsed.nodes.first();QVERIFY(node.conversionIssues.isEmpty());QCOMPARE(node.parameters.value("udp"),QJsonValue(true));
   EngineStartOptions o;o.routingMode="global";o.nodes=parsed.nodes;o.selectedNodeId=node.id;o.executablePath="must-not-start-mihomo.exe";
   QTcpServer port;QVERIFY(port.listen(QHostAddress::LocalHost));o.proxyPort=port.serverPort();port.close();
   ThreadedEngine engine;engine.start(o);
   QVERIFY2(QTest::qWaitFor([&]{return engine.status().apiHealthy;},5000),qPrintable(engine.status().message));
   QCOMPARE(engine.status().engineKind,QString("rust"));QCOMPARE(engine.status().processId,QCoreApplication::applicationPid());
   QUdpSocket client;client.setProxy(QNetworkProxy::NoProxy);QVERIFY(client.bind(QHostAddress::LocalHost,0,QUdpSocket::DontShareAddress));
   QTcpSocket control;control.setProxy(QNetworkProxy::NoProxy);control.connectToHost(QHostAddress::LocalHost,o.proxyPort);
   QVERIFY(QTest::qWaitFor([&]{return control.state()==QAbstractSocket::ConnectedState;},4000));
   QCOMPARE(control.write(QByteArray::fromHex("050100")),qint64(3));
   QVERIFY(QTest::qWaitFor([&]{return control.bytesAvailable()>=2;},4000));QCOMPARE(control.read(2),QByteArray::fromHex("0500"));
   auto associate=QByteArray::fromHex("050300017f000001");associate.append(char(client.localPort()>>8));associate.append(char(client.localPort()&0xff));
   QCOMPARE(control.write(associate),qint64(associate.size()));
   QVERIFY(QTest::qWaitFor([&]{return control.bytesAvailable()>=10;},4000));const auto bound=control.read(10);
   QCOMPARE(bound.left(8),QByteArray::fromHex("050000017f000001"));
   const quint16 relayPort=(quint16(quint8(bound[8]))<<8)|quint8(bound[9]);QVERIFY(relayPort>0);
   // Hand-encoded RFC 1928 bytes, independent of the production Rust codec.
   // Send to the returned UDP bind port; it is not the mixed TCP listener.
   auto header=QByteArray::fromHex("000000017f000001");header.append(char(origin>>8));header.append(char(origin&0xff));
   const QByteArray payload="qt-socks5-udp",responsePayload="socks5-udp-native:qt-socks5-udp";
   const auto packet=header+payload;
   QCOMPARE(client.writeDatagram(packet,QHostAddress::LocalHost,relayPort),qint64(packet.size()));
   QVERIFY(QTest::qWaitFor([&]{return client.hasPendingDatagrams();},6000));const auto reply=client.receiveDatagram();
   QCOMPARE(reply.senderAddress(),QHostAddress(QHostAddress::LocalHost));QCOMPARE(reply.senderPort(),int(relayPort));
   QCOMPARE(reply.data(),header+responsePayload);
   QVERIFY(QTest::qWaitFor([&]{return engine.status().uploadTotal>=payload.size()&&engine.status().downloadTotal>=responsePayload.size();},2000));
   const auto udpReleased=[&]{QUdpSocket reclaimed;reclaimed.setProxy(QNetworkProxy::NoProxy);return reclaimed.bind(QHostAddress::LocalHost,relayPort,QUdpSocket::DontShareAddress);};
   if(index==0){
    control.disconnectFromHost();QVERIFY(QTest::qWaitFor([&]{return control.state()==QAbstractSocket::UnconnectedState;},3000));
    QVERIFY2(QTest::qWaitFor(udpReleased,3000),"Closing the SOCKS TCP control connection must release its UDP association.");
   }
   // The INI pass instead keeps control connected until engine shutdown.
   engine.stop();QVERIFY(QTest::qWaitFor([&]{return engine.status().state==ProxyEngine::State::Stopped;},5000));
   QVERIFY(!engine.status().processAlive);QVERIFY(!engine.status().apiHealthy);
   QVERIFY(QTest::qWaitFor([&]{return control.state()==QAbstractSocket::UnconnectedState;},3000));
   QVERIFY2(QTest::qWaitFor(udpReleased,3000),"Engine shutdown must release its UDP relay port.");
   QTcpServer reclaimed;QVERIFY(reclaimed.listen(QHostAddress::LocalHost,o.proxyPort));
  }
 }
 void socks4ImportsMapAndAcceptAcrossNativeAbi(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  for(const auto &version:QStringList{"4","4a"}){
   const auto protocol="socks"+version;
   const auto uri=QString("%1://user%3Afixture@127.0.0.1:1080#fixture").arg(protocol).toUtf8();
   const auto sing=QJsonDocument(QJsonObject{{"outbounds",QJsonArray{QJsonObject{{"type","socks"},{"tag","fixture"},{"version",version},{"server","127.0.0.1"},{"server_port",1080},{"username","user:fixture"},{"network","tcp"}}}}}).toJson();
   const auto yaml=QString("proxies: [{name: fixture, type: %1, server: 127.0.0.1, port: 1080, username: 'user:fixture'}]").arg(protocol).toUtf8();
   const auto json=QJsonDocument(QJsonObject{{"proxies",QJsonArray{QJsonObject{{"name","fixture"},{"type",protocol},{"server","127.0.0.1"},{"port",1080},{"username","user:fixture"},{"password",""},{"udp",false},{"tls",false}}}}}).toJson();
   for(const auto &source:QList<QByteArray>{uri,uri.toBase64(),yaml,json,sing,sing.toBase64()}){
    const auto parsed=NodeImporter::parse(source);QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
    const auto &node=parsed.nodes.first();QCOMPARE(node.protocol,protocol);QCOMPARE(node.username,QString("user:fixture"));QVERIFY(node.password.isEmpty());
    QVERIFY(node.conversionIssues.isEmpty());QVERIFY(!node.originalConfiguration.isEmpty());
    o.nodes=parsed.nodes;o.selectedNodeId=node.id;QJsonObject config;
    const auto error=RustCoreEngine::configuration(o,&config);QVERIFY2(error.isEmpty(),qPrintable(error));
    const QJsonObject expected{{"type","socks4"},{"host","127.0.0.1"},{"port",1080},{"user_id","user:fixture"},{"remote_dns",version=="4a"}};
    QCOMPARE(config["nodes"].toArray().first().toObject()["outbound"].toObject(),expected);
    RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
    QCOMPARE(engine.status().engineKind,QString("rust"));engine.stop();
    QVERIFY(SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
   }
  }
  const auto userid=NodeImporter::parse("socks4://dXNlcjpwYXNz@127.0.0.1:1080#fixture");
  QVERIFY(bool(userid));QCOMPARE(userid.nodes.first().username,QString("dXNlcjpwYXNz"));QVERIFY(userid.nodes.first().password.isEmpty());
 }
 void socks4ImportsRejectAuthenticationAndUnmappedExtensions(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  const QJsonObject base{{"name","fixture"},{"type","socks4a"},{"server","127.0.0.1"},{"port",1080}};
  const QList<QJsonObject> mutations{
   {{"password","must-not-be-discarded"}},{{"password",1}},{{"username",1}},
   {{"username",QString("x")+QChar(0)+"y"}},{{"username",QString(128,QChar(0x00e9))}},
   {{"port","1080"}},{{"port",1080.5}},{{"port",0}},{{"port",65536}},
   {{"tls",true}},{{"tls","false"}},{{"udp",true}},{{"udp","false"}},
   {{"sni","tls.fixture.invalid"}},{{"sni",1}},{{"cipher","none"}},{{"cipher",1}},
   {{"tfo",true}},{{"network","ws"}},{{"network","udp"}},{{"remote_dns",false}},
   {{"future-option","preserved"}},{{"server_port",1080}}
  };
  const QJsonObject sentinel{{"unchanged",true}};
  for(const auto &mutation:mutations){
   auto node=base;for(auto it=mutation.begin();it!=mutation.end();++it)node[it.key()]=it.value();
   const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}}}).toJson());
   if(!parsed)continue;
   QCOMPARE(parsed.nodes.first().originalConfiguration,node);
   o.nodes=parsed.nodes;o.selectedNodeId=parsed.nodes.first().id;QJsonObject config=sentinel;
   QVERIFY2(!RustCoreEngine::configuration(o,&config).isEmpty(),qPrintable(QString::fromUtf8(QJsonDocument(mutation).toJson())));QCOMPARE(config,sentinel);
  }
  for(const auto &uri:QList<QByteArray>{"socks4://user:password@127.0.0.1:1080#fixture", "socks4a://127.0.0.1:1080/path#fixture", "socks4://127.0.0.1:1080?remote_dns=true#fixture"}){
   const auto parsed=NodeImporter::parse(uri);if(!parsed)continue;
   o.nodes=parsed.nodes;o.selectedNodeId=parsed.nodes.first().id;QJsonObject config=sentinel;
   QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());QCOMPARE(config,sentinel);
  }
  for(const auto &version:QList<QJsonValue>{4,QJsonValue(),"4A","6",false}){
   const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{QJsonObject{{"type","socks"},{"tag","fixture"},{"version",version},{"server","127.0.0.1"},{"server_port",1080}}}}}).toJson());
   if(!parsed)continue;
   QVERIFY(!parsed.nodes.first().conversionIssues.isEmpty());o.nodes=parsed.nodes;o.selectedNodeId=parsed.nodes.first().id;QJsonObject config=sentinel;
   QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());QCOMPARE(config,sentinel);
  }
 }
 void socks4ThroughIndependentPeer(){
  bool validPeer=false,validOrigin=false;
  const int peer=qEnvironmentVariableIntValue("SWIRL_SOCKS4_REFERENCE_PORT",&validPeer),origin=qEnvironmentVariableIntValue("SWIRL_SOCKS4_ORIGIN_PORT",&validOrigin);
  if(!validPeer||!validOrigin)QSKIP("Independent Python SOCKS4/4a peer supplies isolated ports in its integration run.");
  QVERIFY(peer>0&&peer<=65535&&origin>0&&origin<=65535);
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  o.dnsConfig={{"mode",0},{"useHosts",true},{"hosts",QVariantList{QVariantMap{{"name","origin.fixture.invalid"},{"value","127.0.0.1"}}}}};
  for(const auto &version:QStringList{"4","4a"}){
   const auto protocol="socks"+version;
   const auto uri=QString("%1://qt-user%3Afixture@127.0.0.1:%2#fixture").arg(protocol).arg(peer).toUtf8();
   const auto sing=QJsonDocument(QJsonObject{{"outbounds",QJsonArray{QJsonObject{{"type","socks"},{"tag","fixture"},{"version",version},{"server","127.0.0.1"},{"server_port",peer},{"username","qt-user:fixture"},{"network","tcp"}}}}}).toJson();
   const auto yaml=QString("proxies: [{name: fixture, type: %1, server: 127.0.0.1, port: %2, username: 'qt-user:fixture'}]").arg(protocol).arg(peer).toUtf8();
   for(const auto &source:QList<QByteArray>{uri,sing,yaml}){
    const auto parsed=NodeImporter::parse(source);QVERIFY2(bool(parsed),qPrintable(parsed.error));
    o.nodes=parsed.nodes;o.selectedNodeId=parsed.nodes.first().id;
    RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
    QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
    QNetworkRequest request(QUrl(QString("http://origin.fixture.invalid:%1/socks4/%2").arg(origin).arg(version)));
    request.setTransferTimeout(5000);request.setRawHeader("Connection","close");
    auto reply=client.get(request);QVERIFY(QTest::qWaitFor([&]{return reply->isFinished();},6000));
    QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("socks4-native-http"));
    QVERIFY(QTest::qWaitFor([&]{return engine.status().uploadTotal>0&&engine.status().downloadTotal>0;},2000));
    QCOMPARE(engine.status().engineKind,QString("rust"));QCOMPARE(engine.status().processId,QCoreApplication::applicationPid());engine.stop();
   }
  }
 }
 void webSocketThroughIndependentPeer(){
  bool validPeer=false,validOrigin=false;
  const int peer=qEnvironmentVariableIntValue("SWIRL_WS_REFERENCE_PORT",&validPeer),origin=qEnvironmentVariableIntValue("SWIRL_WS_ORIGIN_PORT",&validOrigin);
  if(!validPeer||!validOrigin)QSKIP("Independent Python VLESS WS peer supplies isolated ports in its integration run.");
  QVERIFY(peer>0&&peer<=65535&&origin>0&&origin<=65535);
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  const auto source=QString("vless://00112233-4455-6677-8899-aabbccddeeff@127.0.0.1:%1?type=ws&path=%2Fws%3Ffixture%3D1&host=ws.fixture.invalid#fixture").arg(peer).toUtf8();
  const auto parsed=NodeImporter::parse(source);QVERIFY2(bool(parsed),qPrintable(parsed.error));QVERIFY(parsed.nodes.first().conversionIssues.isEmpty());
  o.nodes=parsed.nodes;o.selectedNodeId=parsed.nodes.first().id;
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
  QNetworkRequest request(QUrl(QString("http://origin.fixture.invalid:%1/websocket").arg(origin)));
  request.setTransferTimeout(5000);request.setRawHeader("Connection","close");
  auto reply=client.get(request);QVERIFY(QTest::qWaitFor([&]{return reply->isFinished();},6000));
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray(131073,'w'));
  QVERIFY(QTest::qWaitFor([&]{return engine.status().uploadTotal>0&&engine.status().downloadTotal>=131073;},2000));
  QCOMPARE(engine.status().engineKind,QString("rust"));QCOMPARE(engine.status().processId,QCoreApplication::applicationPid());engine.stop();
 }
 void webSocketMapsExistingFieldsAndRustAcceptsConfiguration(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  auto &node=o.nodes.first();node.protocol="vless";
  node.parameters={{"uuid","00112233-4455-6677-8899-aabbccddeeff"},{"network","ws"}};
  QJsonObject config;auto error=RustCoreEngine::configuration(o,&config);
  QVERIFY2(error.isEmpty(),qPrintable(error));
  auto outbound=config["nodes"].toArray().first().toObject()["outbound"].toObject();
  const QJsonObject defaults{{"host","127.0.0.1"},{"path","/"}};
  QCOMPARE(outbound["websocket"].toObject(),defaults);QVERIFY(!outbound.contains("tls"));
  // Configuration acceptance crosses the actual Rust ABI. Independent framed
  // peers exercise forwarding; this test does not claim Qt WS interoperability.
  RustCoreEngine engine;engine.start(o);
  QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
  QCOMPARE(engine.status().engineKind,QString("rust"));engine.stop();

  node.serverName="tls.fixture.invalid";
  node.parameters["tls"]=true;node.parameters["sni"]=node.serverName;
  node.parameters["alpn"]=QJsonArray{"http/1.1"};
  node.parameters["ws-opts"]=QJsonObject{{"path","/proxy%20path?client=fixture"},
    {"headers",QJsonObject{{"hOsT","ws.fixture.invalid:8443"}}}};
  error=RustCoreEngine::configuration(o,&config);QVERIFY2(error.isEmpty(),qPrintable(error));
  outbound=config["nodes"].toArray().first().toObject()["outbound"].toObject();
  const QJsonObject explicitWs{{"host","ws.fixture.invalid:8443"},{"path","/proxy%20path?client=fixture"}};
  QCOMPARE(outbound["websocket"].toObject(),explicitWs);
  QCOMPARE(outbound["tls"].toObject()["server_name"].toString(),node.serverName);
  QCOMPARE(outbound["tls"].toObject()["alpn"].toArray(),QJsonArray{"http/1.1"});
  engine.start(o);
  QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));engine.stop();

  node.protocol="trojan";node.password="synthetic-ws-password";
  node.parameters.remove("uuid");node.parameters.remove("tls");
  error=RustCoreEngine::configuration(o,&config);QVERIFY2(error.isEmpty(),qPrintable(error));
  outbound=config["nodes"].toArray().first().toObject()["outbound"].toObject();
  QCOMPARE(outbound["type"].toString(),QString("trojan"));
  QCOMPARE(outbound["websocket"].toObject(),explicitWs);
  QCOMPARE(outbound["tls"].toObject()["server_name"].toString(),node.serverName);
  engine.start(o);
  QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));engine.stop();
 }
 void webSocketRejectsUnsupportedParametersWithoutPartialConfiguration(){
  ControlledNetwork net;QVERIFY(net.start());auto valid=options(net);
  auto &node=valid.nodes.first();node.protocol="vless";node.serverName="tls.fixture.invalid";
  node.parameters={{"uuid","00112233-4455-6677-8899-aabbccddeeff"},{"network","ws"},{"tls",true},
    {"sni",node.serverName},{"alpn",QJsonArray{"http/1.1"}},
    {"ws-opts",QJsonObject{{"path","/proxy"},{"headers",QJsonObject{{"Host","ws.fixture.invalid"}}}}}};
  struct RejectedCase {const char *name;QJsonObject parameters;};
  const RejectedCase cases[]{
   {"unsupported transport",{{"network","grpc"}}},
   {"WS options on TCP",{{"network","tcp"}}},
   {"invalid options type",{{"ws-opts","invalid"}}},
   {"early data unsupported",{{"ws-opts",QJsonObject{{"max-early-data",2048}}}}},
   {"extra request header",{{"ws-opts",QJsonObject{{"headers",QJsonObject{{"Cookie","fixture=1"}}}}}}},
   {"duplicate Host aliases",{{"ws-opts",QJsonObject{{"headers",QJsonObject{{"Host","ws.fixture.invalid"},{"host","other.fixture.invalid"}}}}}}},
   {"header injection",{{"ws-opts",QJsonObject{{"headers",QJsonObject{{"Host","ws.fixture.invalid\r\nX-Fixture: 1"}}}}}}},
   {"ambiguous request target",{{"ws-opts",QJsonObject{{"path","//other.fixture.invalid/proxy"}}}}},
   {"unsupported ALPN",{{"alpn",QJsonArray{"h2"}}}},
   {"unsupported proxy UDP",{{"udp",true}}},
   {"disabled certificate verification",{{"skip-cert-verify",true}}},
   {"unsupported VLESS flow",{{"flow","xtls-rprx-vision"}}}
  };
  const QJsonObject sentinel{{"unchanged",true}};
  for(const auto &test:cases){
   auto bad=valid;auto &parameters=bad.nodes.first().parameters;
   for(auto it=test.parameters.begin();it!=test.parameters.end();++it)parameters[it.key()]=it.value();
   QJsonObject config=sentinel;
   QVERIFY2(!RustCoreEngine::configuration(bad,&config).isEmpty(),test.name);QCOMPARE(config,sentinel);
   RustCoreEngine engine;engine.start(bad);
   QCOMPARE(engine.status().state,ProxyEngine::State::Failed);
   QCOMPARE(engine.status().error,ProxyEngine::Error::InvalidOptions);QVERIFY(!engine.status().processAlive);
  }
 }
 void dnsQueryFamilyMapsStrictlyAndPersistsAcrossLegacyEdits(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="direct";
  const QJsonObject sentinel{{"unchanged",true}};
  for(const auto &encrypted:QStringList{"","tls://127.0.0.1","https://127.0.0.1/dns-query"}) {
   o.dnsConfig={{"mode",encrypted.isEmpty()?2:0},{"servers",encrypted.isEmpty()?"::1":""},{"encrypted",encrypted},{"useHosts",false},{"queryFamily","ipv4_only"}};
   QJsonObject output;QVERIFY(RustCoreEngine::configuration(o,&output).isEmpty());QCOMPARE(output["dns"].toObject()["query_family"].toString(),QString("ipv4_only"));
   for(const auto &bad:QVariantList{false,0,QVariant{},QString("ipv6_only"),QString("IPV4_ONLY")}){
    const auto original=o.dnsConfig;o.dnsConfig["queryFamily"]=bad;output=sentinel;QVERIFY(!RustCoreEngine::configuration(o,&output).isEmpty());QCOMPARE(output,sentinel);o.dnsConfig=original;
   }
  }
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  const QVariantMap initial{{"mode",2},{"servers","127.0.0.1"},{"useHosts",false},{"queryFamily","ipv4_only"}};
  QVERIFY(controller.configureDns(initial));
  auto edit=initial;edit.remove("queryFamily");edit["servers"]="::1";QVERIFY(controller.configureDns(edit));QCOMPARE(controller.dnsConfiguration().value("queryFamily").toString(),QString("ipv4_only"));
  EngineController restored(std::make_unique<RustCoreEngine>(),nullptr,path);QCOMPARE(restored.dnsConfiguration(),controller.dnsConfiguration());
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto before=file.readAll();file.close();const auto saved=controller.dnsConfiguration();
  for(const auto &bad:QVariantList{false,QVariant{},QString("future")}){edit["queryFamily"]=bad;QVERIFY(!controller.configureDns(edit));QCOMPARE(controller.dnsConfiguration(),saved);}
  QVERIFY(!controller.configureDns({{"mode",0},{"useHosts",true}}));QCOMPARE(controller.dnsConfiguration(),saved);
  QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),before);file.close();
  QVERIFY(controller.configureDns({{"mode",0},{"useHosts",true},{"queryFamily","dual"}}));QCOMPARE(controller.dnsConfiguration().value("queryFamily").toString(),QString("dual"));
 }
 void nativeDohMapsExistingHttpsField(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="direct";
  o.dnsConfig={{"mode",0},{"servers",""},{"encrypted","https://DNS.fixture.invalid:8443/dns-query"},{"useHosts",false},
    {"hosts",QVariantList{QVariantMap{{"name","dns.fixture.invalid"},{"value","127.0.0.1"}}}}};
  QJsonObject config;QVERIFY2(RustCoreEngine::configuration(o,&config).isEmpty(),"DoH configuration maps");
  const auto endpoint=config["dns"].toObject()["tls_servers"].toArray().first().toObject();
  QCOMPARE(endpoint["address"].toString(),QString("127.0.0.1:8443"));
  QCOMPARE(endpoint["https_path"].toString(),QString("/dns-query"));
  QCOMPARE(endpoint["tls"].toObject()["server_name"].toString(),QString("dns.fixture.invalid"));
  QCOMPARE(endpoint["tls"].toObject()["alpn"].toArray(),QJsonArray{"http/1.1"});
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));engine.stop();
  const QJsonObject sentinel{{"unchanged",true}};
  for(const auto &url:QStringList{"http://127.0.0.1/dns-query","https://missing.invalid/dns-query","https://user@127.0.0.1/dns-query","https://127.0.0.1/dns-query?x=1","https://127.0.0.1/dns-query#x","https://127.0.0.1:0/dns-query","https://127.0.0.1//bad"}){
   o.dnsConfig["encrypted"]=url;config=sentinel;QVERIFY2(!RustCoreEngine::configuration(o,&config).isEmpty(),qPrintable(url));QCOMPARE(config,sentinel);
  }
 }
 void strictDotMapsExistingFieldWithoutResolvingOrChangingUi(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="direct";
  o.dnsConfig={{"mode",0},{"servers",""},{"encrypted","tls://DNS.fixture.invalid:8853"},{"useHosts",false},
   {"hosts",QVariantList{QVariantMap{{"name","dns.fixture.invalid"},{"value","127.0.0.1"}}}}};
  QJsonObject config;QVERIFY(RustCoreEngine::configuration(o,&config).isEmpty());
  const auto dns=config["dns"].toObject();const auto endpoints=dns["tls_servers"].toArray();QCOMPARE(endpoints.size(),1);
  const auto endpoint=endpoints.first().toObject();QCOMPARE(endpoint["address"].toString(),QString("127.0.0.1:8853"));
  QCOMPARE(endpoint["tls"].toObject()["server_name"].toString(),QString("dns.fixture.invalid"));
  QCOMPARE(endpoint["tls"].toObject()["alpn"].toArray(),QJsonArray{"dot"});
  QVERIFY(dns["servers"].toArray().isEmpty());QVERIFY(!dns["use_system_hosts"].toBool());
  // Configuration acceptance only; independent TLS peers verify authentication.
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));engine.stop();
  o.dnsConfig["hosts"]=QVariantList{};o.dnsConfig["encrypted"]="tls://127.0.0.1";
  QVERIFY(RustCoreEngine::configuration(o,&config).isEmpty());
  QCOMPARE(config["dns"].toObject()["tls_servers"].toArray().first().toObject()["address"].toString(),QString("127.0.0.1:853"));
  o.dnsConfig["encrypted"]="tls://[::1]:8853/";
  QVERIFY(RustCoreEngine::configuration(o,&config).isEmpty());
  const auto v6=config["dns"].toObject()["tls_servers"].toArray().first().toObject();
  QCOMPARE(v6["address"].toString(),QString("[::1]:8853"));QCOMPARE(v6["tls"].toObject()["server_name"].toString(),QString("::1"));
 }
 void strictDotRejectsAmbiguousOrUnimplementedBootstrap(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="direct";
  o.dnsConfig={{"mode",0},{"servers",""},{"useHosts",false},{"hosts",QVariantList{}}};
  const QJsonObject sentinel{{"unchanged",true}};
  for(const auto &url:QStringList{"https://dns.fixture.invalid/dns-query","tcp://127.0.0.1","tls://dns.fixture.invalid",
    "tls://127.0.0.1:0","tls://0.0.0.0","tls://[::]","tls://224.0.0.1","tls://127.0.0.1:99999",
    "tls://user@127.0.0.1","tls://127.0.0.1?insecure=true","tls://127.0.0.1#name","tls://127.0.0.1/path",
    "tls://%31%32%37.0.0.1","tls://127.0.0.1,other","tls://[fe80::1%251]"}){
   o.dnsConfig["encrypted"]=url;QJsonObject config=sentinel;
   QVERIFY2(!RustCoreEngine::configuration(o,&config).isEmpty(),qPrintable(url));QCOMPARE(config,sentinel);
  }
  o.dnsConfig["encrypted"]="tls://127.0.0.1";o.dnsConfig["servers"]="127.0.0.1";
  QJsonObject config;QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
  o.dnsConfig["servers"]="";o.dnsConfig["mode"]=1;QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
  o.dnsConfig["mode"]=2;QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
 }
 void customDnsMapsServersWithoutChangingSystemSettings(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="direct";
  o.dnsConfig={{"mode",2},{"servers","127.0.0.1, ::1"},{"useHosts",false},{"hosts",QVariantList{QVariantMap{{"name","local.fixture.invalid"},{"value","127.0.0.1"}}}}};
  QJsonObject config;QVERIFY(RustCoreEngine::configuration(o,&config).isEmpty());
  QCOMPARE(config["dns"].toObject()["servers"].toArray(),QJsonArray({"127.0.0.1:53","[::1]:53"}));QVERIFY(!config["dns"].toObject()["use_system_hosts"].toBool());
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));auto url=net.url();url.setHost("local.fixture.invalid");QNetworkRequest request(url);request.setTransferTimeout(4000);auto reply=client.get(request);
  QVERIFY(QTest::qWaitFor([&]{return reply->isFinished();},5000));QCOMPARE(reply->readAll(),QByteArray("DIRECT-BYPASS"));engine.stop();
  for(const auto &servers:QStringList{"","127.0.0.1,127.0.0.1","0.0.0.0","::","224.0.0.1","https://dns.invalid/query","127.0.0.1:5353"}){o.dnsConfig["servers"]=servers;QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());}
  o.dnsConfig["servers"]="127.0.0.1";o.dnsConfig["mode"]=1;QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
 }
 void dnsSettingsUseLocalMappingsAndProxyToggle(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  const QVariantMap mapping{{"id","fixture"},{"name","origin.fixture.invalid"},{"value","127.0.0.1"},{"server",""},{"comment","local fixture"}};
  o.dnsConfig={{"mode",0},{"servers",""},{"encrypted",""},{"useHosts",true},{"respectRules",true},{"hosts",QVariantList{mapping}}};
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
  const auto request=[&]{QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));auto url=net.url();url.setHost("origin.fixture.invalid");QNetworkRequest req(url);req.setTransferTimeout(4000);auto reply=client.get(req);if(!QTest::qWaitFor([&]{return reply->isFinished();},5000))return QByteArray("timed-out");return reply->readAll();};
  QCOMPARE(request(),QByteArray("exit-A"));QCOMPARE(net.a.forwarded,1);engine.stop();
  o.dnsConfig["respectRules"]=false;engine.start(o);QVERIFY(request()!=QByteArray("exit-A"));QCOMPARE(net.a.forwarded,1);engine.stop();
  o.routingMode="direct";engine.start(o);QCOMPARE(request(),QByteArray("DIRECT-BYPASS"));engine.stop();
  const auto valid=o.dnsConfig;QJsonObject config;
  for(const auto &bad:QVariantList{QVariantMap{{"mode",2}},QVariantMap{{"useHosts",false}},QVariantMap{{"respectRules","true"}},QVariantMap{{"encrypted","https://dns.invalid/query"}},QVariantMap{{"extra",true}}}){
   o.dnsConfig=valid;const auto map=bad.toMap();for(auto it=map.begin();it!=map.end();++it)o.dnsConfig[it.key()]=it.value();QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
  }
  o.dnsConfig=valid;auto duplicate=mapping;duplicate["name"]="ORIGIN.FIXTURE.INVALID";o.dnsConfig["hosts"]=QVariantList{mapping,duplicate};QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
  duplicate["name"]="*.fixture.invalid";o.dnsConfig["hosts"]=QVariantList{duplicate};QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
 }
 void manualGroupUsesItsMemberRatherThanGlobalSelection(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="rule";
  auto b=o.nodes.first();b.id=QUuid::createUuid().toString(QUuid::WithoutBraces);b.port=net.b.serverPort();b.username=QString::fromUtf8(net.b.username);b.password=QString::fromUtf8(net.b.password);o.nodes.append(b);
  o.customGroups={QVariantMap{{"name","手动组"},{"type","select"},{"proxies",QStringList{b.id,o.selectedNodeId}},{"url","https://www.gstatic.com/generate_204"},{"interval",300}}};
  o.customRules={"MATCH,手动组"};RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
  const auto request=[&]{QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));QNetworkRequest req(net.url());req.setTransferTimeout(4000);auto reply=client.get(req);if(!QTest::qWaitFor([&]{return reply->isFinished();},5000))return QByteArray("timed-out");return reply->readAll();};
  QCOMPARE(request(),QByteArray("exit-B"));QCOMPARE(net.a.forwarded,0);QCOMPARE(net.b.forwarded,1);
  engine.selectNode(o.selectedNodeId);QCOMPARE(request(),QByteArray("exit-B"));
  engine.setRoutingMode("global");QCOMPARE(request(),QByteArray("exit-A"));
  engine.setRoutingMode("rule");net.b.reject=true;QVERIFY(request()!=QByteArray("exit-A"));QCOMPARE(net.a.forwarded,1);engine.stop();
  auto group=o.customGroups.first().toMap();group["default-selected"]=o.selectedNodeId;o.customGroups={group};engine.start(o);QCOMPARE(request(),QByteArray("exit-A"));engine.stop();
  QJsonObject config;
  for(const auto &type:QStringList{"fallback","url-test","load-balance"}){group["type"]=type;o.customGroups={group};QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());}
  group["type"]="select";group["proxies"]=QStringList{b.id,"missing"};o.customGroups={group};QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
  group["proxies"]=QStringList{b.id,b.id};o.customGroups={group};QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
  group["proxies"]=QStringList{b.id};group["default-selected"]=b.id;group["url"]="https://unmapped.invalid/check";o.customGroups={group};QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
 }
 void nestedAutomaticGroupsUseNativeDataPath_data(){
  QTest::addColumn<QString>("type");
  QTest::newRow("url-test")<<QString("url-test");
  QTest::newRow("fallback")<<QString("fallback");
  QTest::newRow("round-robin")<<QString("load-balance");
 }
 void nestedAutomaticGroupsUseNativeDataPath(){
  QFETCH(QString,type);
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="rule";
  auto b=o.nodes.first();b.id=QUuid::createUuid().toString(QUuid::WithoutBraces);b.port=net.b.serverPort();b.username=QString::fromUtf8(net.b.username);b.password=QString::fromUtf8(net.b.password);o.nodes.append(b);
  QVariantMap automatic{{"name","自动组"},{"type",type},{"proxies",QStringList{b.id}},{"url",net.url().toString()},{"interval",1},{"timeout",500},{"expected-status",200}};
  if(type=="load-balance")automatic["strategy"]="round-robin";
  // Both forward references cross the Qt conversion and actual Rust ABI.
  o.customGroups={QVariantMap{{"name","外层"},{"type","select"},{"proxies",QStringList{"中层"}}},
   QVariantMap{{"name","中层"},{"type","select"},{"proxies",QStringList{o.selectedNodeId,"自动组"}},{"default-selected","自动组"}},automatic};
  o.customRules={"MATCH,外层"};const auto original=o.customGroups;QJsonObject config;
  const auto error=RustCoreEngine::configuration(o,&config);QVERIFY2(error.isEmpty(),qPrintable(error));QCOMPARE(o.customGroups,original);
  const auto groups=config["selectors"].toArray();QCOMPARE(groups.size(),3);
  QCOMPARE(groups[0].toObject()["selected"],groups[1].toObject()["id"]);QCOMPARE(groups[1].toObject()["selected"],groups[2].toObject()["id"]);
  const auto probe=groups[2].toObject()["probe"].toObject();QCOMPARE(probe["interval_ms"].toInt(),1000);QCOMPARE(probe["timeout_ms"].toInt(),500);QCOMPARE(probe["expected_status"].toInt(),200);
  QVERIFY(!groups[2].toObject().contains("selected"));
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
  QNetworkReply::NetworkError requestError=QNetworkReply::NoError;
  const auto request=[&]{requestError=QNetworkReply::NoError;QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));QNetworkRequest req(net.url());req.setTransferTimeout(2000);auto reply=client.get(req);if(!QTest::qWaitFor([&]{return reply->isFinished();},3000))return QByteArray("timed-out");requestError=reply->error();return reply->readAll();};
  // Readiness is established by an actual routed response, not merely by the
  // listener being up. Initial requests may fail before the first probe.
  QVERIFY(QTest::qWaitFor([&]{return request()==QByteArray("exit-B");},5000));
  QCOMPARE(net.a.forwarded,0);QCOMPARE(net.httpRequestsByExit.value("DIRECT-BYPASS"),0);
  net.b.reject=true;const auto failed=request();QVERIFY(requestError!=QNetworkReply::NoError);QVERIFY(failed!=QByteArray("exit-A")&&failed!=QByteArray("exit-B")&&failed!=QByteArray("DIRECT-BYPASS")&&failed!=QByteArray("timed-out"));
  QCOMPARE(net.a.forwarded,0);QCOMPARE(net.httpRequestsByExit.value("DIRECT-BYPASS"),0);
  engine.setRoutingMode("global");QCOMPARE(request(),QByteArray("exit-A"));QCOMPARE(engine.status().engineKind,QString("rust"));engine.stop();
  // Invalid inactive settings cannot replace the running global plan when a
  // later mode switch would activate the entire membership graph.
  auto cycle=o.customGroups[1].toMap();cycle["proxies"]=QStringList{o.selectedNodeId,"外层"};cycle["default-selected"]=o.selectedNodeId;o.customGroups[1]=cycle;o.routingMode="global";
  engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Running);engine.setRoutingMode("rule");
  QCOMPARE(engine.status().mode,QString("global"));QCOMPARE(request(),QByteArray("exit-A"));engine.stop();
 }
 void roundRobinPolicyBalancesNewNativeSessions(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="rule";
  auto b=o.nodes.first();b.id=QUuid::createUuid().toString(QUuid::WithoutBraces);b.port=net.b.serverPort();b.username=QString::fromUtf8(net.b.username);b.password=QString::fromUtf8(net.b.password);o.nodes.append(b);
  o.customGroups={QVariantMap{{"name","轮询"},{"type","load-balance"},{"strategy","round-robin"},{"proxies",QStringList{o.selectedNodeId,b.id}},{"url",net.url().toString()},{"interval",1},{"timeout",500},{"expected-status",200}}};o.customRules={"MATCH,轮询"};
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
  const auto request=[&]{QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));QNetworkRequest req(net.url());req.setTransferTimeout(2000);auto reply=client.get(req);if(!QTest::qWaitFor([&]{return reply->isFinished();},3000))return QByteArray("timed-out");return reply->readAll();};
  QVERIFY(QTest::qWaitFor([&]{return net.httpRequestsByExit.value("exit-A")>0&&net.httpRequestsByExit.value("exit-B")>0;},4000));
  // A response can arrive just before its health record is committed. Wait
  // for both paths to be selected, then require the following exact alternation.
  QByteArray previous;QVERIFY(QTest::qWaitFor([&]{const auto first=request(),second=request();if((first=="exit-A"&&second=="exit-B")||(first=="exit-B"&&second=="exit-A")){previous=second;return true;}return false;},4000));
  for(int i=0;i<4;++i){const auto next=request();QCOMPARE(next,previous=="exit-A"?QByteArray("exit-B"):QByteArray("exit-A"));previous=next;}
  QCOMPARE(net.httpRequestsByExit.value("DIRECT-BYPASS"),0);engine.stop();
 }
 void policyConversionRejectsUnknownSemanticsAndBounds(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="rule";
  const QVariantMap automatic{{"name","auto"},{"type","url-test"},{"proxies",QStringList{o.selectedNodeId}},{"url",net.url().toString()},{"interval",1},{"timeout",500},{"expected-status",200}};
  const QJsonObject sentinel{{"unchanged",true}};
  const QVariantList mutations{
   QVariantMap{{"url",QVariant()}},QVariantMap{{"url","https://user:secret@host/"}},QVariantMap{{"url","https://@host/"}},QVariantMap{{"url","http://host/#fragment"}},QVariantMap{{"url","http://host/\\path"}},QVariantMap{{"url","file:///local"}},QVariantMap{{"url","http://host:0/"}},QVariantMap{{"url","http://host:65536/"}},
   QVariantMap{{"interval",0}},QVariantMap{{"interval",1.5}},QVariantMap{{"interval","1"}},QVariantMap{{"interval",3601}},QVariantMap{{"timeout",99}},QVariantMap{{"timeout",1001}},QVariantMap{{"timeout",true}},QVariantMap{{"expected-status",302}},QVariantMap{{"expected-status","200-299"}},QVariantMap{{"tolerance",10001}},
   QVariantMap{{"type","fallback"},{"tolerance",1}},QVariantMap{{"type","load-balance"}},QVariantMap{{"type","load-balance"},{"strategy","consistent-hashing"}},QVariantMap{{"type","load-balance"},{"strategy","sticky-sessions"}},QVariantMap{{"strategy","round-robin"}},QVariantMap{{"default-selected",o.selectedNodeId}},
   QVariantMap{{"lazy",true}},QVariantMap{{"skip-cert-verify",true}},QVariantMap{{"use",QStringList{"provider"}}},QVariantMap{{"future-field",1}},QVariantMap{{"proxies",QStringList{"REJECT"}}},QVariantMap{{"proxies",QStringList{"missing"}}},QVariantMap{{"proxies",QStringList{o.selectedNodeId,o.selectedNodeId}}},QVariantMap{{"proxies",QVariantList{1}}},QVariantMap{{"name",o.selectedNodeId}}
  };
  for(const auto &value:mutations){auto group=automatic;const auto mutation=value.toMap();for(auto it=mutation.begin();it!=mutation.end();++it)group[it.key()]=it.value();o.customGroups={group};QJsonObject config=sentinel;QVERIFY2(!RustCoreEngine::configuration(o,&config).isEmpty(),qPrintable(QString::fromUtf8(QJsonDocument::fromVariant(mutation).toJson())));QCOMPARE(config,sentinel);}
  auto missing=automatic;missing.remove("url");o.customGroups={missing};QJsonObject config=sentinel;QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());QCOMPARE(config,sentinel);
  auto nested=automatic;nested["proxies"]=QStringList{"manual"};o.customGroups={nested,QVariantMap{{"name","manual"},{"type","select"},{"proxies",QStringList{o.selectedNodeId}}}};QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
  for(const int count:{16,17}){o.customGroups.clear();for(int i=0;i<count;++i)o.customGroups.append(QVariantMap{{"name",QString("g%1").arg(i)},{"type","select"},{"proxies",QStringList{i+1<count?QString("g%1").arg(i+1):o.selectedNodeId}}});QCOMPARE(RustCoreEngine::configuration(o,&config).isEmpty(),count==16);if(count==16){RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));engine.stop();}}
  o.customGroups.clear();for(int i=0;i<33;++i){auto group=automatic;group["name"]=QString("auto%1").arg(i);o.customGroups.append(group);}QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
 }
 void policySettingsPreserveFullMapsAndRejectInvalidReplacements(){
  QTemporaryDir directory;QVERIFY(directory.isValid());EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,directory.filePath("nodes.dpapi"));
  const QVariantMap outer{{"name","outer"},{"type","select"},{"proxies",QStringList{"DIRECT","automatic"}},{"default-selected","automatic"}};
  const QVariantMap automatic{{"name","automatic"},{"type","load-balance"},{"strategy","round-robin"},{"proxies",QStringList{"DIRECT"}},{"url","https://www.gstatic.com/generate_204"},{"interval",10},{"timeout",250},{"expected-status",204}};
  const QVariantList groups{outer,automatic};const QVariantMap input{{"groups",groups},{"rules",QStringList{"MATCH,outer"}}};
  QVERIFY2(controller.replaceNetworkConfiguration(input),qPrintable(controller.networkConfigurationError()));QCOMPARE(controller.policyGroups(),groups);
  QVERIFY(controller.savePolicyGroup("automatic","load-balance",{"DIRECT"}));QCOMPARE(controller.policyGroups(),groups);
  auto changed=automatic;changed["future-option"]=true;auto invalid=input;invalid["groups"]=QVariantList{outer,changed};
  QVERIFY(!controller.replaceNetworkConfiguration(invalid));QCOMPARE(controller.policyGroups(),groups);
  invalid["groups"]=QString("not-an-array");QVERIFY(!controller.replaceNetworkConfiguration(invalid));QCOMPARE(controller.policyGroups(),groups);
  QVERIFY(!controller.savePolicyGroup("outer","select",{"DIRECT"}));QCOMPARE(controller.policyGroups(),groups);
  QVERIFY(!controller.removePolicyGroup("automatic"));QCOMPARE(controller.policyGroups(),groups);
  NodeStore persisted(directory.filePath("nodes.dpapi"));QCOMPARE(persisted.networkConfiguration()["groups"].toArray(),QJsonArray::fromVariantList(groups));
  QVERIFY(!QFile::exists(directory.filePath("nodes.dpapi.network.json")));
 }
 void rulesUseActualRustDataPathAndModeSwitches(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="rule";
  o.customRules={"DOMAIN,blocked.invalid,REJECT",QString("DST-PORT,%1,DIRECT").arg(net.http.serverPort()),"MATCH,SWIRL"};
  RustCoreEngine engine;engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Running);
  QCOMPARE(engine.routingRules().size(),4);QCOMPARE(engine.routingRules()[1].toMap()["policy"].toString(),QString("DIRECT"));
  const auto request=[&](const QUrl &url){
   QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
   QNetworkRequest req(url);req.setTransferTimeout(4000);auto reply=client.get(req);
   if(!QTest::qWaitFor([&]{return reply->isFinished();},5000))return QByteArray("timed-out");
   return reply->readAll();
  };
  QCOMPARE(request(net.url()),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,0);
  const auto before=net.httpRequests;request(QUrl(QString("http://blocked.invalid:%1/").arg(net.http.serverPort())));
  QCOMPARE(net.httpRequests,before);QCOMPARE(net.a.forwarded,0);
  engine.refresh();bool rejected=false;for(const auto &record:engine.status().connections){const auto row=record.toMap();if(row["host"]=="blocked.invalid"&&row["category"]=="reject")rejected=true;}QVERIFY(rejected);
  engine.setRoutingMode("global");QCOMPARE(request(net.url()),QByteArray("exit-A"));QCOMPARE(net.a.forwarded,1);
  engine.setRoutingMode("rule");QCOMPARE(request(net.url()),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,1);
  engine.setRoutingMode("direct");QCOMPARE(request(net.url()),QByteArray("DIRECT-BYPASS"));QCOMPARE(engine.routingRules().size(),1);
  engine.selectNode(o.selectedNodeId);QVERIFY(engine.status().directSession);QCOMPARE(request(net.url()),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,1);
  engine.stop();
 }
 void controllerRuleEditsPreserveNoResolve(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  QVERIFY(controller.saveNode({{"name","fixture"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",net.a.serverPort()}}));
  const auto node=controller.nodeCatalog().first().toMap().value("id").toString();
  const QVariantList groups{QVariantMap{{"name","route"},{"type","select"},{"proxies",QStringList{"DIRECT"}}}};
  const QStringList original{" IP-CIDR , 127.0.0.1/32 , route , no-resolve ","IP-CIDR6,::1/128,route,no-resolve"," MATCH , SWIRL "};
  QVERIFY(controller.replaceNetworkConfiguration({{"groups",groups},{"rules",original}}));
  QCOMPARE(controller.routingRules()[0].toMap().value("policy").toString(),QString("route"));
  QCOMPARE(controller.routingRules()[1].toMap().value("policy").toString(),QString("route"));
  QCOMPARE(controller.routingRules()[2].toMap().value("type").toString(),QString("FINAL"));
  QCOMPARE(controller.routingRules()[2].toMap().value("policy").toString(),QString("SWIRL"));
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto unchanged=file.readAll();file.close();
  QVERIFY(controller.saveRoutingRule("IP-CIDR","127.0.0.1/32","route",0));
  QCOMPARE(controller.networkConfigurationSnapshot().value("rules").toStringList(),original);
  QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),unchanged);file.close();
  QVERIFY(controller.saveRoutingRule("IP-CIDR","127.0.0.0/8","route",0));
  QVERIFY(controller.saveRoutingRule("IP-CIDR6","::1/128","route",1));
  const auto saved=controller.networkConfigurationSnapshot();
  QCOMPARE(saved.value("rules").toStringList()[0],QString("IP-CIDR,127.0.0.0/8,route,no-resolve"));
  QCOMPARE(saved.value("rules").toStringList()[1],QString("IP-CIDR6,::1/128,route,no-resolve"));
  QVERIFY(!controller.saveRoutingRule("DOMAIN","localhost","route",0));
  QCOMPARE(controller.networkConfigurationSnapshot(),saved);
  EngineController restored(std::make_unique<RustCoreEngine>(),nullptr,path);
  QCOMPARE(QJsonObject::fromVariantMap(restored.networkConfigurationSnapshot()),QJsonObject::fromVariantMap(saved));
  auto configuration=options(net);configuration.nodes=NodeStore(path).nodes();configuration.selectedNodeId=node;
  configuration.routingMode="rule";configuration.customGroups=groups;configuration.customRules=saved.value("rules").toStringList();
  QJsonObject mapped;QVERIFY(RustCoreEngine::configuration(configuration,&mapped).isEmpty());
  for(int i=0;i<2;++i)QCOMPARE(mapped["rules"].toArray()[i].toObject()["matcher"].toObject()["resolve"],QJsonValue(false));
  restored.setProxyPort(configuration.proxyPort);restored.setRoutingMode("rule");restored.connectNode(node);
  QTRY_VERIFY_WITH_TIMEOUT(restored.apiHealthy(),4000);
  QCOMPARE(restored.routingRules()[0].toMap().value("policy").toString(),QString("route"));
  const auto request=[&](const QUrl &url){
   QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",configuration.proxyPort));
   QNetworkRequest input(url);input.setTransferTimeout(4000);auto *reply=client.get(input);
   if(!QTest::qWaitFor([&]{return reply->isFinished();},5000))return QByteArray("timed-out");
   return reply->error()==QNetworkReply::NoError?reply->readAll():QByteArray("request-failed");
  };
  QCOMPARE(request(net.url()),QByteArray("DIRECT-BYPASS"));
  auto domain=net.url();domain.setHost("localhost");
  // The unresolved hostname skips both CIDRs and reaches the explicit fallback.
  // The independent SOCKS peer permits only localhost and this fixture's ports.
  QCOMPARE(request(domain),QByteArray("exit-A"));QCOMPARE(net.a.forwarded,1);
  restored.stop();
 }
 void controllerRuleReferencesPreventGroupDeletion(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  const QVariantList groups{QVariantMap{{"name","route"},{"type","select"},{"proxies",QStringList{"DIRECT"}}}};
  for(const auto &rule:QStringList{"IP-CIDR,198.51.100.0/24,route,no-resolve"," IP-CIDR6 , 2001:db8::/32 , route , no-resolve ","DOMAIN,fixture.invalid, route "," MATCH , route "}) {
   const QVariantMap input{{"dns",QVariantMap{}},{"groups",groups},{"rules",QStringList{rule,"MATCH,REJECT"}}};
   QVERIFY(controller.replaceNetworkConfiguration(input));
   QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto before=file.readAll();file.close();
   QVERIFY(!controller.removePolicyGroup("route"));QCOMPARE(controller.networkConfigurationSnapshot(),input);
   QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),before);file.close();
   NodeStore disk(path);QCOMPARE(disk.networkConfiguration()["groups"].toArray(),QJsonArray::fromVariantList(groups));
   QVERIFY(controller.removeRoutingRule(0));QVERIFY(controller.removePolicyGroup("route"));QVERIFY(controller.policyGroups().isEmpty());
  }
 }
 void controllerRuleValidationAndPersistenceAreAtomic(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  const QVariantList groups{QVariantMap{{"name","unused"},{"type","select"},{"proxies",QStringList{"DIRECT"}}}};
  QVERIFY(controller.replaceNetworkConfiguration({{"groups",groups},{"rules",QStringList{"DOMAIN,kept.invalid,DIRECT","MATCH,REJECT"}}}));
  const auto before=controller.networkConfigurationSnapshot();
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto ciphertext=file.readAll();file.close();
  QList<QVariantMap> observed;QObject observer;
  connect(&controller,&EngineController::optionsChanged,&observer,[&]{observed.append(controller.networkConfigurationSnapshot());});
  // These fields pass the editor's old checks; native validation must reject
  // them before writing, including an unsupported rule below terminal MATCH.
  QVERIFY(!controller.saveRoutingRule("PROCESS-NAME","fixture.exe","DIRECT"));
  QVERIFY(!controller.saveRoutingRule("DOMAIN","bad..invalid","DIRECT"));
  QVERIFY(!controller.saveRoutingRule("IP-CIDR","::1/128","DIRECT"));
  QVERIFY(!controller.saveRoutingRule("IP-CIDR6","127.0.0.1/32","DIRECT"));
  QCOMPARE(controller.networkConfigurationSnapshot(),before);
  QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),ciphertext);file.close();
  const auto backup=directory.filePath("retained.dpapi");QVERIFY(QFile::rename(path,backup));QVERIFY(QDir().mkdir(path));
  QVERIFY(!controller.saveRoutingRule("DOMAIN","changed.invalid","DIRECT",0));
  QVERIFY(!controller.removeRoutingRule(0));
  QVERIFY(!controller.savePolicyGroup("new","select",{"DIRECT"}));
  QVERIFY(!controller.removePolicyGroup("unused"));
  QCOMPARE(controller.networkConfigurationSnapshot(),before);
  QVERIFY(!observed.isEmpty());for(const auto &snapshot:observed)QCOMPARE(snapshot,before);
  QVERIFY(QDir().rmdir(path));QVERIFY(QFile::rename(backup,path));
  QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),ciphertext);file.close();
  EngineController restored(std::make_unique<RustCoreEngine>(),nullptr,path);QCOMPARE(QJsonObject::fromVariantMap(restored.networkConfigurationSnapshot()),QJsonObject::fromVariantMap(before));
  QVERIFY(controller.saveRoutingRule("DOMAIN","changed.invalid","DIRECT",0));
  NodeStore persisted(path);QCOMPARE(persisted.networkConfiguration()["rules"].toArray()[0].toString(),QString("DOMAIN,changed.invalid,DIRECT"));
 }
 void rulesValidateAllFieldsAndPreserveUnsupportedImports(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="rule";
  auto unsupported=o.nodes.first();unsupported.id="unused";unsupported.protocol="vmess";o.nodes.append(unsupported);
  o.customRules={"DOMAIN,localhost,SWIRL","DOMAIN-SUFFIX,example.org,DIRECT","DOMAIN-KEYWORD,ads,REJECT","IP-CIDR,127.0.0.0/8,DIRECT,no-resolve","IP-CIDR6,::1/128,DIRECT","SRC-IP-CIDR,127.0.0.0/8,DIRECT","DST-PORT,443,SWIRL","MATCH,REJECT"};
  QJsonObject config;QVERIFY(RustCoreEngine::configuration(o,&config).isEmpty());
  QCOMPARE(config["nodes"].toArray().size(),3);QCOMPARE(config["rules"].toArray().size(),8);
  RustCoreEngine engine;engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Running);engine.stop();
  for(const auto &bad:QStringList{"MATCH,REJECT,extra","DOMAIN,x,REJECT,no-resolve","DOMAIN,x..y,DIRECT","DOMAIN-KEYWORD,*,DIRECT","DST-PORT,0,DIRECT","IP-CIDR,::1/128,DIRECT","IP-CIDR6,127.0.0.0/8,DIRECT","SRC-IP-CIDR,127.0.0.1/33,DIRECT","PROCESS-NAME,app.exe,DIRECT","MATCH,unknown-group","MATCH,SWIRL\n"}){
   o.customRules={"MATCH,SWIRL",bad};QVERIFY2(!RustCoreEngine::configuration(o,&config).isEmpty(),qPrintable(bad));
  }
  // Inactive stored rules stay intact; activating them fails atomically.
  o.routingMode="global";engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Running);
  engine.setRoutingMode("rule");QCOMPARE(engine.status().mode,QString("global"));QCOMPARE(engine.routingRules().size(),1);engine.stop();
 }
 void vlessThroughIndependentPeer(){
  bool valid=false;const int port=qEnvironmentVariableIntValue("SWIRL_VLESS_REFERENCE_PORT",&valid);
  if(!valid)QSKIP("Independent VLESS peer supplies the port in its integration run.");
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);auto &n=o.nodes.first();
  n.protocol="vless";n.host="127.0.0.1";n.port=quint16(port);n.parameters={{"uuid","00112233-4455-6677-8899-aabbccddeeff"}};
  RustCoreEngine engine;engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Running);
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
  QNetworkRequest request(QUrl("http://origin.example/vless"));request.setTransferTimeout(5000);
  auto reply=client.get(request);QVERIFY(QTest::qWaitFor([&]{return reply->isFinished();},6000));
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("vless-ok"));engine.stop();
 }
 void capabilityUsesTheSelectedRustRuntime(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);auto n=o.nodes.first();
  n.protocol="ss";n.password="fixture";n.cipher="aes-128-gcm";n.parameters={{"udp",true}};
  auto capability=SwirlProtocolRegistry::describe(n);QVERIFY(capability["native"].toBool());QVERIFY(!capability["compatible"].toBool());QVERIFY(!capability["engine"].toString().contains("Mihomo"));
  n.protocol="vless";n.password.clear();n.cipher.clear();n.parameters={{"uuid","00112233-4455-6677-8899-aabbccddeeff"}};
  QVERIFY(SwirlProtocolRegistry::nativeNodeReason(n).isEmpty());
  n.parameters["flow"]="xtls-rprx-vision";QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(n).isEmpty());
 }
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
 void disabledFastOpenIsAnExactNoOpAcrossNativeProtocols(){
  ControlledNetwork net;QVERIFY(net.start());
  for(const auto &protocol:QStringList{"http","socks4","socks4a","socks5","ss","trojan","vless"}){
   auto o=options(net);auto &n=o.nodes.first();n.protocol=protocol;
   if(protocol=="ss"){n.password="synthetic";n.cipher="aes-128-gcm";}
   if(protocol=="trojan")n.password="synthetic";
   if(protocol=="vless")n.parameters["uuid"]="11111111-1111-4111-8111-111111111111";
   QJsonObject baseline;QVERIFY2(RustCoreEngine::configuration(o,&baseline).isEmpty(),qPrintable(protocol));
   n.parameters["tfo"]=false;QJsonObject disabled;QVERIFY2(RustCoreEngine::configuration(o,&disabled).isEmpty(),qPrintable(protocol));QCOMPARE(disabled,baseline);
   for(const auto &invalid:QJsonArray{true,0,1,"false",QJsonValue(QJsonValue::Null),QJsonObject{},QJsonArray{}}){
    n.parameters["tfo"]=invalid;QJsonObject unchanged{{"sentinel",true}};QVERIFY(!RustCoreEngine::configuration(o,&unchanged).isEmpty());QCOMPARE(unchanged,QJsonObject({{"sentinel",true}}));
   }
  }
 }
 void disabledFastOpenForwardsThroughNativeSocks5(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.nodes.first().parameters["tfo"]=false;
  RustCoreEngine engine;engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Running);
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
  auto reply=client.get(QNetworkRequest(net.url()));QVERIFY(QTest::qWaitFor([&]{return reply->isFinished();},5000));
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-A"));QVERIFY(net.a.forwarded>0);
  QCOMPARE(engine.status().engineKind,QString("rust"));engine.stop();QTcpServer reuse;QVERIFY(reuse.listen(QHostAddress::LocalHost,o.proxyPort));
 }
 void loonShadowsocksImportsKeepCredentialsAndRejectUnsafeOptions(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  for(const auto &tail:QStringList{"http,obfs.example","obfs-name=http,obfs-host=obfs.example"}){
   const auto source=QString("[Proxy]\nfixture = Shadowsocks,127.0.0.1,443,aes-128-gcm,\"secret,with:punctuation\",%1").arg(tail).toUtf8();
   const auto parsed=NodeImporter::parse(source);QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
   const auto &node=parsed.nodes.first();QCOMPARE(node.password,QString("secret,with:punctuation"));QVERIFY(node.conversionIssues.isEmpty());QVERIFY(!node.originalConfiguration.isEmpty());
   o.nodes=parsed.nodes;o.selectedNodeId=node.id;QJsonObject config;QVERIFY(RustCoreEngine::configuration(o,&config).isEmpty());
   const auto outbound=config["nodes"].toArray().first().toObject()["outbound"].toObject();
   QCOMPARE(outbound["obfs_http"].toObject()["host"].toString(),QString("obfs.example"));QCOMPARE(outbound["password"].toString(),node.password);
  }
  for(const auto &tail:QStringList{"tls,obfs.example","http","http,","http,obfs.example,extra","http,obfs.example,future=retained","obfs-name=http,obfs-host=obfs.example,obfs-uri=/custom"}){
   const auto parsed=NodeImporter::parse(QString("[Proxy]\nfixture = Shadowsocks,127.0.0.1,443,aes-128-gcm,secret,%1").arg(tail).toUtf8());
   if(!parsed)continue;
   QCOMPARE(parsed.nodes.first().password,QString("secret"));QVERIFY(!parsed.nodes.first().originalConfiguration.isEmpty());
   o.nodes=parsed.nodes;o.selectedNodeId=parsed.nodes.first().id;QJsonObject config;QVERIFY(!RustCoreEngine::configuration(o,&config).isEmpty());
  }
  for(const auto &parameters:QStringList{"aes-128-gcm,secret,http,obfs.example,obfs=tls","aes-128-gcm,secret,http,obfs.example,obfs-name=http","aes-128-gcm,secret,http,obfs.example,obfs-host=other.example","aes-128-gcm,password=first,second,http,obfs.example","method=aes-256-gcm,aes-128-gcm,secret","aes-128-gcm,secret,encrypt-method=aes-256-gcm"}){
   const auto parsed=NodeImporter::parse(QString("[Proxy]\nfixture = Shadowsocks,127.0.0.1,443,%1").arg(parameters).toUtf8());QVERIFY(!parsed);
  }
 }
 void loonShadowsocksThroughIndependentPeer(){
  bool valid=false;const int port=qEnvironmentVariableIntValue("SWIRL_SS_REFERENCE_PORT",&valid);
  if(!valid)QSKIP("Independent Python SS peer supplies the isolated port.");
  ControlledNetwork net;QVERIFY(net.start());
  for(const auto &tail:QStringList{"http,obfs.example","obfs-name=http,obfs-host=obfs.example","obfs-name=http,obfs-host=obfs.example,fast-open=false"}){
   auto o=options(net);const auto source=QString("[Proxy]\nfixture = Shadowsocks,127.0.0.1,%1,aes-128-gcm,synthetic-ss-password,%2").arg(port).arg(tail).toUtf8();
   const auto parsed=NodeImporter::parse(source);QVERIFY2(bool(parsed),qPrintable(parsed.error));o.nodes=parsed.nodes;o.selectedNodeId=parsed.nodes.first().id;
   RustCoreEngine engine;engine.start(o);QCOMPARE(engine.status().state,ProxyEngine::State::Running);
   QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
   QNetworkRequest request(QUrl("http://origin.example/ss"));request.setTransferTimeout(5000);
   auto reply=client.get(request);QVERIFY(QTest::qWaitFor([&]{return reply->isFinished();},6000));
   QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("ss-native-ok"));
   QCOMPARE(engine.status().engineKind,QString("rust"));QCOMPARE(engine.status().processId,QCoreApplication::applicationPid());engine.stop();
  }
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
