#include "engine/RustCoreEngine.h"
#include "engine/ThreadedEngine.h"
#include "engine/NodeTestService.h"
#include "engine/NodeImporter.h"
#include "engine/SwirlProtocolRegistry.h"
#include "ControlledNetwork.h"
#include <QTest>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkProxy>
#include <QUuid>
#include <QJsonArray>
#include <QJsonDocument>

class RustCoreTests:public QObject {
 Q_OBJECT
 EngineStartOptions options(ControlledNetwork &net){
  EngineStartOptions o;QTcpServer port;port.listen(QHostAddress::LocalHost);o.proxyPort=port.serverPort();o.routingMode="global";
  ProxyNode n;n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);n.name="synthetic";n.protocol="socks5";n.host="127.0.0.1";n.port=net.a.serverPort();
  o.nodes={n};o.selectedNodeId=n.id;return o;
 }
private slots:
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
