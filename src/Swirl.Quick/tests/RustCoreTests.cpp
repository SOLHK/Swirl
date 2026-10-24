#ifdef _WIN32
#include <winsock2.h>
#else
#include <sys/socket.h>
#endif
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
#include <QSignalSpy>
#include <QElapsedTimer>
#include <QTimer>
#include <QPointer>
#include <QFileInfo>
#include <QSaveFile>
#include <QScopeGuard>
#include <QRegularExpression>
#include <algorithm>
#include "app/StoragePaths.h"

// Keep real Rust listeners and real A/B traffic while making one asynchronous
// control failure deterministic. Invalid configurations are now rejected before
// the worker, so they cannot stand in for a later selection failure.
class RejectOneSelectionEngine final : public ProxyEngine {
public:
 RejectOneSelectionEngine(){
  connect(&m_engine,&ProxyEngine::statusChanged,this,&ProxyEngine::statusChanged);
  connect(&m_engine,&ProxyEngine::diagnostic,this,&ProxyEngine::diagnostic);
  connect(&m_engine,&ProxyEngine::probeRequestRejected,this,&ProxyEngine::probeRequestRejected);
 }
 QString rejectNextSelection;
 int selectionCalls=0,injectedRejections=0;
 void start(const EngineStartOptions &options) override{m_engine.start(options);}
 void stop() override{m_engine.stop();}
 void refresh() override{m_engine.refresh();}
 void selectNode(const QString &id) override{
  ++selectionCalls;
  if(!rejectNextSelection.isEmpty()&&id==rejectNextSelection){
   rejectNextSelection.clear();
   QMetaObject::invokeMethod(this,[this]{
    ++injectedRejections;
    emit diagnostic(QStringLiteral("SwirlRust"),QStringLiteral("SelectionFailed"),QStringLiteral("Synthetic queued control failure; current Rust session retained."));
   },Qt::QueuedConnection);
   return;
  }
  m_engine.selectNode(id);
 }
 void probeNode(const QUrl &url) override{m_engine.probeNode(url);}
 void probeNodeTagged(const QUrl &url,quint64 tag) override{m_engine.probeNodeTagged(url,tag);}
 void setRoutingMode(const QString &mode) override{m_engine.setRoutingMode(mode);}
 Status status() const override{return m_engine.status();}
 QString configurationSummary() const override{return m_engine.configurationSummary();}
 QVariantList routingRules() const override{return m_engine.routingRules();}
private:
 ThreadedEngine m_engine;
};

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
 void startRejectsInvalidReplacementWithoutStoppingLiveRuntime_data(){
  QTest::addColumn<bool>("threaded");QTest::addColumn<int>("invalidKind");
  for(const bool threaded:{false,true})for(int kind=0;kind<3;++kind)
   QTest::newRow(qPrintable(QString("%1-%2").arg(threaded?"worker":"direct").arg(kind)))<<threaded<<kind;
 }
 void startRejectsInvalidReplacementWithoutStoppingLiveRuntime(){
  QFETCH(bool,threaded);QFETCH(int,invalidKind);
  ControlledNetwork net;QVERIFY(net.start());auto original=options(net);
  std::unique_ptr<ProxyEngine> engine;
  if(threaded)engine=std::make_unique<ThreadedEngine>();else engine=std::make_unique<RustCoreEngine>();
  engine->start(original);QTRY_VERIFY_WITH_TIMEOUT(engine->status().apiHealthy,5000);
  const auto previous=engine->status();auto invalid=original;
  QTcpServer occupied;QVERIFY(occupied.listen(QHostAddress::LocalHost,0));
  if(invalidKind==0)invalid.tunEnabled=true;
  else if(invalidKind==1)invalid.selectedNodeId="missing-node";
  else invalid.proxyPort=occupied.serverPort();
  QSignalSpy diagnostics(engine.get(),&ProxyEngine::diagnostic);engine->start(invalid);
  QTRY_VERIFY_WITH_TIMEOUT(!diagnostics.isEmpty(),5000);
  // The worker queues the rejection diagnostic before its restored snapshot.
  // Observe that snapshot before checking the retained session and real traffic.
  QTRY_COMPARE_WITH_TIMEOUT(engine->status().state,ProxyEngine::State::Running,5000);
  QVERIFY(engine->status().apiHealthy);QCOMPARE(engine->status().sessionId,previous.sessionId);
  QCOMPARE(engine->status().proxyPort,previous.proxyPort);QCOMPARE(engine->status().selectedNodeId,previous.selectedNodeId);
  QCOMPARE(diagnostics.last()[1].toString(),QString("CoreStartRejected"));
  QNetworkAccessManager manager;manager.setProxy(QNetworkProxy(QNetworkProxy::Socks5Proxy,"127.0.0.1",previous.proxyPort));
  auto *reply=manager.get(QNetworkRequest(net.url()));QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-A"));
  reply->deleteLater();engine->stop();QTRY_VERIFY_WITH_TIMEOUT(!engine->status().processAlive,5000);
  QTcpServer released;QVERIFY(released.listen(QHostAddress::LocalHost,previous.proxyPort));
 }
 void repeatedStartReconfiguresOneRuntimeAndPreservesEstablishedTunnel(){
  ControlledNetwork net;QVERIFY(net.start());auto config=options(net);
  auto second=config.nodes.first();second.id=QUuid::createUuid().toString(QUuid::WithoutBraces);second.name="second";
  second.port=net.b.serverPort();second.username=QString::fromUtf8(net.b.username);second.password=QString::fromUtf8(net.b.password);
  config.nodes.append(second);ThreadedEngine engine;engine.start(config);
  QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,5000);const auto previous=engine.status();
  QTcpSocket held;held.setProxy(QNetworkProxy::NoProxy);held.connectToHost(QHostAddress::LocalHost,previous.proxyPort);
  QTRY_COMPARE_WITH_TIMEOUT(held.state(),QAbstractSocket::ConnectedState,5000);
  const auto authority=QByteArray("127.0.0.1:")+QByteArray::number(net.url().port());
  held.write("CONNECT "+authority+" HTTP/1.1\r\nHost: "+authority+"\r\n\r\n");
  QByteArray response;QVERIFY(QTest::qWaitFor([&]{response+=held.readAll();return response.contains("\r\n\r\n");},5000));
  QVERIFY(response.startsWith("HTTP/1.1 200"));QCOMPARE(net.a.forwarded,1);
  config.selectedNodeId=second.id;engine.start(config);
  QTRY_COMPARE_WITH_TIMEOUT(engine.status().selectedNodeId,second.id,5000);
  QCOMPARE(engine.status().sessionId,previous.sessionId);QCOMPARE(engine.status().proxyPort,previous.proxyPort);
  response.clear();held.write("GET / HTTP/1.1\r\nHost: "+authority+"\r\nConnection: close\r\n\r\n");
  QVERIFY(QTest::qWaitFor([&]{response+=held.readAll();return response.endsWith("exit-A");},5000));
  QNetworkAccessManager manager;manager.setProxy(QNetworkProxy(QNetworkProxy::Socks5Proxy,"127.0.0.1",previous.proxyPort));
  auto *reply=manager.get(QNetworkRequest(net.url()));QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-B"));
  QCOMPARE(net.a.forwarded,1);QCOMPARE(net.b.forwarded,1);reply->deleteLater();
  engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,5000);
 }
 void invalidColdStartDoesNotOpenListenerAndCanRecover(){
  ControlledNetwork net;QVERIFY(net.start());auto config=options(net);auto invalid=config;invalid.tunEnabled=true;
  RustCoreEngine engine;engine.start(invalid);QCOMPARE(engine.status().state,ProxyEngine::State::Failed);
  QVERIFY(!engine.status().processAlive);QTcpServer available;QVERIFY(available.listen(QHostAddress::LocalHost,config.proxyPort));available.close();
  engine.start(config);QVERIFY(engine.status().apiHealthy);engine.stop();QVERIFY(!engine.status().processAlive);
 }
 void queuedExplicitStopThenStartReleasesPreviousListener(){
  ControlledNetwork net;QVERIFY(net.start());auto first=options(net);ThreadedEngine engine;
  engine.start(first);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,5000);const auto previous=engine.status();
  auto next=first;QTcpServer port;QVERIFY(port.listen(QHostAddress::LocalHost,0));next.proxyPort=port.serverPort();port.close();
  engine.stop();engine.start(next);
  QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy&&engine.status().proxyPort==next.proxyPort,5000);
  QVERIFY(engine.status().sessionId!=previous.sessionId);
  QTcpServer released;QVERIFY(released.listen(QHostAddress::LocalHost,previous.proxyPort));
  QNetworkAccessManager manager;manager.setProxy(QNetworkProxy(QNetworkProxy::Socks5Proxy,"127.0.0.1",next.proxyPort));
  auto *reply=manager.get(QNetworkRequest(net.url()));QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-A"));reply->deleteLater();
  engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,5000);
 }
 void retiredPreferenceCannotSelectAnEngineOrBlockRustStartup(){
  QTemporaryDir directory;QVERIFY(directory.isValid());
  QSettings settings;const auto previous=settings.value("Proxy/preferCompatibility"),previousMode=settings.value("Proxy/routingMode");
  const auto restore=qScopeGuard([&]{
   if(previous.isValid())settings.setValue("Proxy/preferCompatibility",previous);else settings.remove("Proxy/preferCompatibility");
   if(previousMode.isValid())settings.setValue("Proxy/routingMode",previousMode);else settings.remove("Proxy/routingMode");settings.sync();
  });
  settings.setValue("Proxy/preferCompatibility",true);settings.setValue("Proxy/routingMode","direct");settings.sync();
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,directory.filePath("saved.dpapi"));
  QVERIFY(controller.rustCoreBuild());QVERIFY(controller.property("rustCoreBuild").toBool());
  QCOMPARE(controller.metaObject()->indexOfProperty("preferCompatibility"),-1);
  QTcpServer port;QVERIFY(port.listen(QHostAddress::LocalHost,0));const auto available=port.serverPort();port.close();
  controller.setProxyPort(available);controller.start();
  QVERIFY2(controller.apiHealthy(),qPrintable(controller.error()));QCOMPARE(controller.engineKind(),QString("rust"));
  QCOMPARE(QSettings().value("Proxy/preferCompatibility").toBool(),true);
  controller.stop();QVERIFY(!controller.processAlive());
 }
 void unsupportedCapabilitiesCannotBeEnabledOrRewriteConfiguration(){
  QTemporaryDir directory;QVERIFY(directory.isValid());
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,directory.filePath("unsupported.dpapi"));
  const auto before=controller.networkConfigurationSnapshot();
  QVERIFY(!controller.setTunEnabled(true));QVERIFY(controller.routingError().contains("TUN"));
  QVERIFY(!controller.setLanEnabled(true));QVERIFY(controller.networkConfigurationError().contains(QString::fromUtf8("局域网")));
  QVERIFY(!controller.setGatewayForwarding(true));QVERIFY(controller.routingError().contains(QString::fromUtf8("网关")));
  QVERIFY(!controller.setMeteredEnabled(true));QVERIFY(controller.routingError().contains(QString::fromUtf8("计费")));
  QCOMPARE(controller.networkConfigurationSnapshot(),before);QVERIFY(!QFile::exists(directory.filePath("unsupported.dpapi")));
 }
 void smartRoutingUsesBundledRulesUnlessDirectoryIsExplicit(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="rule";o.smartRouting=true;
  QJsonObject config;QVERIFY(RustCoreEngine::configuration(o,&config).isEmpty());
  QCOMPARE(config.value("smart_routing"),QJsonValue(true));
  QVERIFY(!config.contains("china_rules_directory"));
  o.rulesDirectory=QStringLiteral("D:/Codex/custom-rules");
  QVERIFY(RustCoreEngine::configuration(o,&config).isEmpty());
  QCOMPARE(config.value("china_rules_directory"),QJsonValue(o.rulesDirectory));
 }
 void realAcceptanceStartsGlobalWithoutChangingSavedRouting(){
  const auto previousVersion=QCoreApplication::applicationVersion();
  QCoreApplication::setApplicationVersion("9.8.7");
  const auto restoreVersion=qScopeGuard([&]{QCoreApplication::setApplicationVersion(previousVersion);});
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;QVERIFY(directory.isValid());
  QSettings settings;settings.setValue("Proxy/routingMode","rule");settings.sync();
  const auto path=directory.filePath("acceptance.dpapi");const auto o=options(net);
  EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);controller.setProxyPort(o.proxyPort);
  QCOMPARE(controller.routingMode(),QString("rule"));QVERIFY(controller.prepareRealAcceptance());
  QCOMPARE(controller.routingMode(),QString("global"));
  QCOMPARE(controller.engineIdentityLabel(),QString::fromUtf8("Swirl · v9.8.7"));
  QCOMPARE(QSettings().value("Proxy/routingMode").toString(),QString("rule"));
  const QJsonObject node{{"name","synthetic"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.a.serverPort()}};
  controller.imports()->importText(QString::fromUtf8(QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}}}).toJson()));
  QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);
  QCOMPARE(controller.nodeCatalog().size(),1);
  const auto id=controller.nodeCatalog().first().toMap().value("id").toString();
  QVERIFY(controller.chooseNode(id));controller.connectNode(id);
  QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);
  QCOMPARE(controller.routingMode(),QString("global"));QCOMPARE(controller.engineKind(),QString("rust"));
  QCOMPARE(controller.engineIdentityLabel(),QString::fromUtf8("Swirl · v9.8.7"));
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
  QNetworkRequest request(net.url());request.setTransferTimeout(4000);
  auto *reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-A"));
  QCOMPARE(net.a.forwarded,1);
  QCOMPARE(QSettings().value("Proxy/routingMode").toString(),QString("rule"));
  controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),5000);
  QCOMPARE(controller.engineIdentityLabel(),QString::fromUtf8("Swirl · v9.8.7"));
 }
 void savedRuleModeStartsWithBundledRulesWithoutChangingSavedRouting(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;QVERIFY(directory.isValid());
  QSettings settings;const auto previous=settings.value("Proxy/routingMode");
  const auto restore=qScopeGuard([&]{if(previous.isValid())settings.setValue("Proxy/routingMode",previous);else settings.remove("Proxy/routingMode");settings.sync();});
  settings.setValue("Proxy/routingMode","rule");settings.sync();
  const auto o=options(net);
  EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,directory.filePath("product-rule.dpapi"),true);
  controller.setProxyPort(o.proxyPort);
  QCOMPARE(controller.routingMode(),QString("rule"));
  const QJsonObject node{{"name","synthetic"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.a.serverPort()}};
  controller.imports()->importText(QString::fromUtf8(QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}}}).toJson()));
  QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);
  QCOMPARE(controller.nodeCatalog().size(),1);
  const auto id=controller.nodeCatalog().first().toMap().value("id").toString();
  QVERIFY(controller.chooseNode(id));
  controller.connectNode(id);
  QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);
  QCOMPARE(controller.routingMode(),QString("rule"));
  QCOMPARE(controller.engineKind(),QString("rust"));
  QCOMPARE(QSettings().value("Proxy/routingMode").toString(),QString("rule"));
  controller.setRoutingMode("global");
  QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);
  QCOMPARE(controller.engineKind(),QString("rust"));
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
  QNetworkRequest request(net.url());request.setTransferTimeout(4000);
  auto *reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-A"));
  QCOMPARE(net.a.forwarded,1);
  controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),5000);
 }
 void unsupportedSessionMessagesIdentifyActualBlocker(){
  ControlledNetwork net;QVERIFY(net.start());const auto o=options(net);QJsonObject configuration;
  auto blocked=o;blocked.smartRouting=true;blocked.routingMode="rule";
  QVERIFY(RustCoreEngine::configuration(blocked,&configuration).isEmpty());
  QCOMPARE(configuration.value("smart_routing"),QJsonValue(true));
  QVERIFY(!configuration.contains("china_rules_directory"));
  blocked=o;blocked.tunEnabled=true;
  QVERIFY(RustCoreEngine::configuration(blocked,&configuration).contains(QString::fromUtf8("增强模式")));
  blocked=o;blocked.allowLan=true;
  QVERIFY(RustCoreEngine::configuration(blocked,&configuration).contains(QString::fromUtf8("局域网代理")));
  blocked=o;blocked.meteredNetwork=true;
  QVERIFY(RustCoreEngine::configuration(blocked,&configuration).contains(QString::fromUtf8("计费网络")));
 }
 void nativeRealityParametersSurviveEncryptedStoreAndConfiguration(){
  const QByteArray key=QByteArray(32,'\x09').toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals);
  const QByteArray source="vless://00112233-4455-6677-8899-aabbccddeeff@proxy.invalid:443?security=reality&type=tcp&sni=camouflage.invalid&pbk="+key+"&sid=a1B2&fp=rustls&encryption=none&alpn=h2,http%2F1.1";
  const auto imported=NodeImporter::parse(source);QVERIFY2(imported,qPrintable(imported.error));QCOMPARE(imported.nodes.size(),1);
  QTemporaryDir directory;QVERIFY(directory.isValid());const auto path=directory.filePath("reality.dat");QString id;
  {NodeStore saved(path);QVERIFY(saved.importNodes(imported.nodes));QCOMPARE(saved.nodes().size(),1);id=saved.nodes().first().id;QVERIFY(saved.select(id));}
  NodeStore restored(path);QCOMPARE(restored.nodes().size(),1);QCOMPARE(restored.selectedId(),id);
  const auto original=imported.nodes.first();const auto node=restored.nodes().first();QCOMPARE(node.parameters,original.parameters);QCOMPARE(node.originalConfiguration,original.originalConfiguration);
  EngineStartOptions options;options.nodes=restored.nodes();options.selectedNodeId=id;options.routingMode="global";options.proxyPort=12345;
  QJsonObject configuration;const auto error=RustCoreEngine::configuration(options,&configuration);QVERIFY2(error.isEmpty(),qPrintable(error));
  const auto outbound=configuration.value("nodes").toArray().first().toObject().value("outbound").toObject();
  QVERIFY(!outbound.contains("tls"));QVERIFY(!outbound.contains("websocket"));QCOMPARE(outbound.value("type"),QJsonValue("vless"));
  const auto reality=outbound.value("reality").toObject();QCOMPARE(reality.value("public_key"),QJsonValue(QString::fromLatin1(key)));QCOMPARE(reality.value("short_id"),QJsonValue("a1B2"));QCOMPARE(reality.value("fingerprint"),QJsonValue("rustls"));QCOMPARE(reality.value("server_name"),QJsonValue("camouflage.invalid"));QCOMPARE(reality.value("alpn"),QJsonValue(QJsonArray{"h2","http/1.1"}));
  for(const auto &profile:QStringList{"safari","firefox","","random","Chrome","chrome_120"}){auto invalid=options;invalid.nodes.first().parameters["client-fingerprint"]=profile;QVERIFY(!RustCoreEngine::configuration(invalid,&configuration).isEmpty());}
  for(const auto &shortId:QStringList{"a","zz","001122334455667788"}){auto invalid=options;auto settings=invalid.nodes.first().parameters.value("reality-opts").toObject();settings["short-id"]=shortId;invalid.nodes.first().parameters["reality-opts"]=settings;QVERIFY(!RustCoreEngine::configuration(invalid,&configuration).isEmpty());}
  auto invalid=options;auto settings=invalid.nodes.first().parameters.value("reality-opts").toObject();settings["spider-x"]="/private";invalid.nodes.first().parameters["reality-opts"]=settings;QVERIFY(!RustCoreEngine::configuration(invalid,&configuration).isEmpty());
  auto invalidAlpn=source;invalidAlpn.replace("alpn=h2,http%2F1.1","alpn=h2,,http%2F1.1");const auto retained=NodeImporter::parse(invalidAlpn);QVERIFY(retained);QCOMPARE(retained.nodes.first().parameters.value("alpn"),QJsonValue(QJsonArray{"h2","","http/1.1"}));invalid=options;invalid.nodes=retained.nodes;invalid.selectedNodeId=retained.nodes.first().id;QVERIFY(!RustCoreEngine::configuration(invalid,&configuration).isEmpty());
  const auto visionSource=source+"&flow=xtls-rprx-vision";const auto visionImported=NodeImporter::parse(visionSource);QVERIFY(visionImported);const auto visionPath=directory.filePath("vision.dat");
  {NodeStore saved(visionPath);QVERIFY(saved.importNodes(visionImported.nodes));QVERIFY(saved.select(saved.nodes().first().id));}
  NodeStore visionRestored(visionPath);QCOMPARE(visionRestored.nodes().size(),1);QCOMPARE(visionRestored.nodes().first().originalConfiguration,visionImported.nodes.first().originalConfiguration);
  auto visionOptions=options;visionOptions.nodes=visionRestored.nodes();visionOptions.selectedNodeId=visionRestored.selectedId();QVERIFY(RustCoreEngine::configuration(visionOptions,&configuration).isEmpty());QCOMPARE(configuration.value("nodes").toArray().first().toObject().value("outbound").toObject().value("flow"),QJsonValue("xtls-rprx-vision"));
  for(const auto &flow:QStringList{"xtls-rprx-direct","xtls-rprx-vision-udp443","XTLS-RPRX-VISION"}){auto unsupported=visionOptions;unsupported.nodes.first().parameters["flow"]=flow;QVERIFY(!RustCoreEngine::configuration(unsupported,&configuration).isEmpty());}
 }
 void browserRealityParametersSurviveImportStoreAndConfiguration(){
  const auto key=QByteArray(32,'\x09').toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals);
  QTemporaryDir directory;QVERIFY(directory.isValid());int index=0;
  for(const auto &profile:QStringList{"chrome","chrome_133"})for(const bool explicitAlpn:{false,true}){
   const QByteArray uri="vless://00112233-4455-6677-8899-aabbccddeeff@proxy.invalid:443?security=reality&type=tcp&sni=camouflage.invalid&pbk="+key+"&sid=a1B2&fp="+profile.toUtf8()+"&flow=xtls-rprx-vision"+(explicitAlpn?"&alpn=h2,http%2F1.1":"");
   const QByteArray yaml="proxies:\n  - name: fixture\n    type: vless\n    server: proxy.invalid\n    port: 443\n    uuid: 00112233-4455-6677-8899-aabbccddeeff\n    tls: true\n    servername: camouflage.invalid\n    client-fingerprint: "+profile.toUtf8()+"\n    reality-opts: {public-key: "+key+", short-id: a1B2}\n    flow: xtls-rprx-vision\n"+(explicitAlpn?"    alpn: [h2, http/1.1]\n":"");
   QJsonObject tls{{"enabled",true},{"server_name","camouflage.invalid"},{"insecure",false},{"utls",QJsonObject{{"enabled",true},{"fingerprint",profile}}},{"reality",QJsonObject{{"enabled",true},{"public_key",QString::fromLatin1(key)},{"short_id","a1B2"}}}};
   if(explicitAlpn)tls["alpn"]=QJsonArray{"h2","http/1.1"};
   const QJsonObject source{{"tag","fixture"},{"type","vless"},{"server","proxy.invalid"},{"server_port",443},{"uuid","00112233-4455-6677-8899-aabbccddeeff"},{"flow","xtls-rprx-vision"},{"tls",tls}};
   const auto json=QJsonDocument(QJsonObject{{"outbounds",QJsonArray{source}}}).toJson();
   QList<QByteArray> bodies{uri,uri.toBase64(),yaml,json,json.toBase64()};
   if(!explicitAlpn){
    const QJsonObject user{{"id","00112233-4455-6677-8899-aabbccddeeff"},{"encryption","none"},{"flow","xtls-rprx-vision"}};
    const QJsonObject endpoint{{"address","proxy.invalid"},{"port",443},{"users",QJsonArray{user}}};
    // Xray source names are distinct from Swirl's native IR aliases.
    const auto sourceProfile=profile=="chrome_133"?QStringLiteral("HelloChrome_133"):profile;
    const QJsonObject reality{{"serverName","camouflage.invalid"},{"fingerprint",sourceProfile},{"publicKey",QString::fromLatin1(key)},{"shortId","a1B2"}};
    const QJsonObject stream{{"network","raw"},{"security","reality"},{"realitySettings",reality}};
    const QJsonObject legacy{{"protocol","vless"},{"tag","fixture"},{"settings",QJsonObject{{"vnext",QJsonArray{endpoint}}}},{"streamSettings",stream}};
    auto tcp=legacy;auto tcpStream=stream;tcpStream["network"]="tcp";tcpStream["tcpSettings"]=QJsonObject{{"header",QJsonObject{{"type","none"}}}};tcp["streamSettings"]=tcpStream;
    auto simplified=legacy;auto settings=user;settings["address"]="proxy.invalid";settings["port"]=443;simplified["settings"]=settings;
    auto renamed=reality;renamed["password"]=renamed.take("publicKey");auto renamedStream=stream;renamedStream["realitySettings"]=renamed;simplified["streamSettings"]=renamedStream;
    auto aliases=simplified;renamed["publicKey"]=renamed.value("password");renamed["show"]=false;renamedStream["realitySettings"]=renamed;renamedStream["tcpSettings"]=tcpStream.value("tcpSettings");renamedStream["rawSettings"]=tcpStream.value("tcpSettings");aliases["streamSettings"]=renamedStream;aliases["mux"]=QJsonObject{{"enabled",false}};
    for(const auto &xray:QList<QJsonObject>{legacy,tcp,simplified,aliases}){const auto body=QJsonDocument(QJsonObject{{"outbounds",QJsonArray{xray}}}).toJson();bodies.append(body);bodies.append(body.toBase64());}
   }
   QJsonObject expected;
   for(const auto &body:bodies){
    const auto imported=NodeImporter::parse(body);QVERIFY2(imported,qPrintable(imported.error));QCOMPARE(imported.nodes.size(),1);
    const auto original=imported.nodes.first();
    if(original.isXray()){
     // The authoritative Rust import retains an informational semantic notice:
     // native authentication fails closed instead of invoking Xray's crawler.
     QCOMPARE(original.conversionIssues,QStringList{QStringLiteral("RealityNativeAuthenticationOnly · outbounds[0].streamSettings.realitySettings")});
     QVERIFY(original.nativeExecutable);QVERIFY(original.runtimeIssues.isEmpty());
     QCOMPARE(original.nativeOutbound.value("reality").toObject().value("fingerprint"),QJsonValue(profile));
     const auto decoded=body.startsWith('{')?body:QByteArray::fromBase64(body);
     // Direct JSON reaches Rust byte-for-byte. Base64 wrappers first pass
     // through SubscriptionNormalizer, which removes only outer whitespace.
     // Preserve the exact effective source on each path, including all JSON
     // interior whitespace and values; neither path reparses/reprints it.
     const auto effectiveSource=body.startsWith('{')?decoded:decoded.trimmed();
     QCOMPARE(original.sourceDocument,effectiveSource);QCOMPARE(original.sourceNodeIndex,0);
     QCOMPARE(original.originalConfiguration.value("outbound"),QJsonDocument::fromJson(decoded).object().value("outbounds").toArray().first());
     QCOMPARE(imported.configurationFormat,QString("xray-v2ray-json"));QVERIFY(imported.configuration.isEmpty());QVERIFY(imported.executionConfiguration.isEmpty());
    }else{QVERIFY(original.conversionIssues.isEmpty());QCOMPARE(original.parameters.value("client-fingerprint"),QJsonValue(profile));}
    if(body==json||body==json.toBase64())QCOMPARE(original.originalConfiguration,source);
    const auto path=directory.filePath(QString("browser-reality-%1.dat").arg(index++));QString id;
    {NodeStore saved(path);QVERIFY(saved.importNodes(imported.nodes));id=saved.nodes().first().id;QVERIFY(saved.select(id));}
    NodeStore restored(path);QCOMPARE(restored.nodes().size(),1);QCOMPARE(restored.selectedId(),id);
    const auto node=restored.nodes().first();QCOMPARE(node.parameters,original.parameters);QCOMPARE(node.originalConfiguration,original.originalConfiguration);
    QCOMPARE(node.sourceDocument,original.sourceDocument);QCOMPARE(node.sourceFingerprint,original.sourceFingerprint);QCOMPARE(node.sourceNodeIndex,original.sourceNodeIndex);
    QVERIFY(SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());QCOMPARE(SwirlProtocolRegistry::describe(node).value("tested"),QVariant(false));
    EngineStartOptions options;options.nodes=restored.nodes();options.selectedNodeId=id;options.routingMode="global";options.proxyPort=12345;
    QJsonObject configuration;const auto reason=RustCoreEngine::configuration(options,&configuration);QVERIFY2(reason.isEmpty(),qPrintable(reason));
    auto outbound=configuration.value("nodes").toArray().first().toObject().value("outbound").toObject();
    // Serde emits absent Option values as null; generic-node conversion omits
    // the same absent values. Neither representation may carry ordinary TLS/WS.
    for(const auto &optional:{"tls","websocket"}){QVERIFY(outbound.value(optional).isNull()||outbound.value(optional).isUndefined());outbound.remove(optional);}
    if(expected.isEmpty())expected=outbound;else QCOMPARE(outbound,expected);
    QVERIFY(!outbound.contains("tls"));QVERIFY(!outbound.contains("websocket"));QCOMPARE(outbound.value("flow"),QJsonValue("xtls-rprx-vision"));
    const auto reality=outbound.value("reality").toObject();QCOMPARE(reality.value("fingerprint"),QJsonValue(profile));QCOMPARE(reality.value("public_key"),QJsonValue(QString::fromLatin1(key)));QCOMPARE(reality.value("short_id"),QJsonValue("a1B2"));QCOMPARE(reality.value("server_name"),QJsonValue("camouflage.invalid"));
    const QJsonArray expectedAlpn=explicitAlpn?QJsonArray{"h2","http/1.1"}:QJsonArray{};QCOMPARE(reality.value("alpn"),QJsonValue(expectedAlpn));
   }
  }
 }
 void browserRealityXraySourceNamesAndUnsupportedProfilesRemainExplicit(){
  const auto key=QString::fromLatin1(QByteArray(32,'\x09').toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals));
  for(const auto &sourceProfile:QStringList{"chrome","HelloChrome_133","chrome_133","rustls","firefox"}){
   const bool supported=sourceProfile=="chrome"||sourceProfile=="HelloChrome_133";
   const QJsonObject reality{{"serverName","camouflage.invalid"},{"fingerprint",sourceProfile},{"publicKey",key},{"shortId","a1B2"}};
   const QJsonObject user{{"id","00112233-4455-6677-8899-aabbccddeeff"},{"encryption","none"},{"flow","xtls-rprx-vision"}};
   const QJsonObject endpoint{{"address","proxy.invalid"},{"port",443},{"users",QJsonArray{user}}};
   const QJsonObject source{{"protocol","vless"},{"tag","fixture"},{"settings",QJsonObject{{"vnext",QJsonArray{endpoint}}}},{"streamSettings",QJsonObject{{"network","raw"},{"security","reality"},{"realitySettings",reality}}}};
   const auto document=QJsonDocument(QJsonObject{{"outbounds",QJsonArray{source}}}).toJson();
   const auto parsed=NodeImporter::parse(document);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
   const auto node=parsed.nodes.first();QVERIFY(node.isXray());QCOMPARE(node.sourceDocument,document);
   QCOMPARE(node.originalConfiguration.value("outbound"),QJsonValue(source));QCOMPARE(node.nativeExecutable,supported);
   QCOMPARE(SwirlProtocolRegistry::describe(node).value("tested"),QVariant(false));
   EngineStartOptions options;options.nodes=parsed.nodes;options.selectedNodeId=node.id;options.routingMode="global";
   QJsonObject config{{"sentinel",true}};const auto reason=RustCoreEngine::configuration(options,&config);
   if(supported){
    QVERIFY2(reason.isEmpty(),qPrintable(reason));QVERIFY(node.runtimeIssues.isEmpty());
    const auto outbound=config.value("nodes").toArray().first().toObject().value("outbound").toObject();
    QCOMPARE(outbound.value("reality").toObject().value("fingerprint"),QJsonValue(sourceProfile=="chrome"?"chrome":"chrome_133"));
    QCOMPARE(outbound.value("flow"),QJsonValue("xtls-rprx-vision"));QVERIFY(outbound.value("tls").isNull());
   }else{
    QVERIFY(!reason.isEmpty());QCOMPARE(config,QJsonObject({{"sentinel",true}}));
    QVERIFY(node.nativeOutbound.isEmpty());QVERIFY(node.runtimeIssues.contains(QStringLiteral("RealitySourceFingerprintUnsupported")));
   }
  }
 }
 void browserRealityAlpnAndSourceFingerprintCannotBeOverwritten(){
  const auto key=QString::fromLatin1(QByteArray(32,'\x09').toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals));
  const QJsonObject tls{{"enabled",true},{"server_name","camouflage.invalid"},{"utls",QJsonObject{{"enabled",true},{"fingerprint","chrome"}}},{"reality",QJsonObject{{"enabled",true},{"public_key",key},{"short_id","abcd"}}}};
  const QJsonObject source{{"tag","fixture"},{"type","vless"},{"server","proxy.invalid"},{"server_port",443},{"uuid","00112233-4455-6677-8899-aabbccddeeff"},{"flow","xtls-rprx-vision"},{"tls",tls}};
  const auto document=QJsonDocument(QJsonObject{{"outbounds",QJsonArray{source}}}).toJson();const auto imported=NodeImporter::parse(document);QVERIFY(imported);
  EngineStartOptions options;options.nodes=imported.nodes;options.selectedNodeId=imported.nodes.first().id;options.routingMode="global";options.proxyPort=12345;
  QJsonObject configuration;QVERIFY(RustCoreEngine::configuration(options,&configuration).isEmpty());
  // Neither a later edit nor an old normalized cache may silently rename an
  // explicit source profile. The native IR preserves chrome versus chrome_133.
  auto changed=options;changed.nodes.first().parameters["client-fingerprint"]="chrome_133";QVERIFY(!RustCoreEngine::configuration(changed,&configuration).isEmpty());
  for(const auto &alpn:QList<QJsonArray>{QJsonArray{"h2"},QJsonArray{"http/1.1"},QJsonArray{"http/1.1","h2"},QJsonArray{"h2","h2"},QJsonArray{""},QJsonArray{"custom"}}){
   auto changedSource=source;auto changedTls=tls;changedTls["alpn"]=alpn;changedSource["tls"]=changedTls;
   const auto body=QJsonDocument(QJsonObject{{"outbounds",QJsonArray{changedSource}}}).toJson();
   const auto parsed=NodeImporter::parse(body);QVERIFY(parsed);QCOMPARE(parsed.nodes.first().originalConfiguration,changedSource);QCOMPARE(parsed.nodes.first().parameters.value("alpn"),QJsonValue(alpn));
   changed=options;changed.nodes=parsed.nodes;changed.selectedNodeId=parsed.nodes.first().id;const auto reason=RustCoreEngine::configuration(changed,&configuration);QVERIFY(reason.contains("ALPN"));
  }
  for(const auto &profile:QStringList{"firefox","rustls","","random","Chrome"}){
   auto changedSource=source;auto changedTls=tls;changedTls["utls"]=QJsonObject{{"enabled",true},{"fingerprint",profile}};changedSource["tls"]=changedTls;
   const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{changedSource}}}).toJson());QVERIFY(parsed);QCOMPARE(parsed.nodes.first().originalConfiguration,changedSource);
   changed=options;changed.nodes=parsed.nodes;changed.selectedNodeId=parsed.nodes.first().id;QVERIFY(!RustCoreEngine::configuration(changed,&configuration).isEmpty());
  }
  for(const auto &alias:QStringList{"fp","client-fingerprint"}){
   auto collision=source;collision[alias]="chrome_133";const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{collision}}}).toJson());QVERIFY(parsed);QCOMPARE(parsed.nodes.first().originalConfiguration,collision);QVERIFY(parsed.nodes.first().conversionIssues.join(' ').contains("冲突"));
   changed=options;changed.nodes=parsed.nodes;changed.selectedNodeId=parsed.nodes.first().id;QVERIFY(!RustCoreEngine::configuration(changed,&configuration).isEmpty());
  }
 }
 void importedScalarTypesCannotBecomeCredentialsOrTlsDefaults(){
  const QJsonObject base{{"name","typed-fixture"},{"type","http"},{"server","127.0.0.1"},{"port",443},{"tls",true}};
  for(const auto &key:QStringList{"username","password","cipher","sni","servername"})for(const auto &value:QJsonArray{QJsonValue(),false,123,QJsonArray{},QJsonObject{{"secret","synthetic-private"}}}){
   auto node=base;node[key]=value;
   const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}}}).toJson());
   QVERIFY2(!parsed,qPrintable(key));QVERIFY(parsed.nodes.isEmpty());QVERIFY(!parsed.error.contains("synthetic-private"));
  }
  auto node=base;node["username"]="123";node["password"]="false";node["sni"]="tls.fixture.invalid";
  const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}}}).toJson());QVERIFY2(parsed,qPrintable(parsed.error));
  QCOMPARE(parsed.nodes.first().username,QString("123"));QCOMPARE(parsed.nodes.first().password,QString("false"));QCOMPARE(parsed.nodes.first().serverName,QString("tls.fixture.invalid"));
  for(const auto &names:QList<QStringList>{{"","other.fixture.invalid"},{"other.fixture.invalid",""},{"a.fixture.invalid","b.fixture.invalid"}}){
   auto aliasNode=base;aliasNode["sni"]=names[0];aliasNode["servername"]=names[1];const auto aliasResult=NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{aliasNode}}}).toJson());QVERIFY(!aliasResult);QVERIFY(aliasResult.nodes.isEmpty());
  }
  for(const auto &name:QStringList{"","same.fixture.invalid"}){
   auto aliasNode=base;aliasNode["sni"]=name;aliasNode["servername"]=name;const auto aliasResult=NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{aliasNode}}}).toJson());QVERIFY2(aliasResult,qPrintable(aliasResult.error));
   QCOMPARE(aliasResult.nodes.first().serverName,name);QCOMPARE(aliasResult.nodes.first().originalConfiguration,aliasNode);
   EngineStartOptions options;options.nodes=aliasResult.nodes;options.selectedNodeId=aliasResult.nodes.first().id;options.routingMode="global";QJsonObject config;QVERIFY(RustCoreEngine::configuration(options,&config).isEmpty());
  }
  const QJsonObject singbox{{"type","http"},{"tag","typed-fixture"},{"server","127.0.0.1"},{"server_port",443},{"tls",QJsonObject{{"enabled",true},{"server_name",QJsonValue()}}}};
  QVERIFY(!NodeImporter::parse(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{singbox}}}).toJson()));
 }
 void extractedUnsupportedFieldsNeverDisappearBeforeNativeValidation(){
  ControlledNetwork net;QVERIFY(net.start());auto baseline=options(net);const QJsonObject sentinel{{"sentinel",true}};
  for(const auto &protocol:QStringList{"http","socks5","trojan","vless"}){
   QJsonObject node{{"name","unsupported-field"},{"type",protocol},{"server","127.0.0.1"},{"port",net.a.serverPort()},{"cipher","synthetic-cipher"}};
   if(protocol=="trojan")node["password"]="synthetic-password";
   if(protocol=="vless")node["uuid"]="00112233-4455-6677-8899-aabbccddeeff";
   auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}}}).toJson());QVERIFY2(parsed,qPrintable(parsed.error));
   baseline.nodes=parsed.nodes;baseline.selectedNodeId=parsed.nodes.first().id;QJsonObject output=sentinel;
   QVERIFY(!RustCoreEngine::configuration(baseline,&output).isEmpty());QCOMPARE(output,sentinel);
   QCOMPARE(parsed.nodes.first().originalConfiguration.value("cipher"),node.value("cipher"));
  }
  auto node=QJsonObject{{"name","trojan-user"},{"type","trojan"},{"server","127.0.0.1"},{"port",net.a.serverPort()},{"password","synthetic-password"},{"username","synthetic-user"}};
  const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}}}).toJson());QVERIFY(parsed);
  baseline.nodes=parsed.nodes;baseline.selectedNodeId=parsed.nodes.first().id;QJsonObject output=sentinel;
  QVERIFY(!RustCoreEngine::configuration(baseline,&output).isEmpty());QCOMPARE(output,sentinel);
 }
 void importedParametersSurviveStoreDestructionAndNativeRoundTrip(){
  QTemporaryDir directory;const auto path=directory.filePath("parameters.dpapi");
  const QJsonObject node{{"name","round-trip"},{"type","vless"},{"server","2001:db8::1"},{"port",8443},{"uuid","00112233-4455-6677-8899-aabbccddeeff"},
   {"tls",true},{"sni","tls.fixture.invalid"},{"alpn",QJsonArray{"http/1.1"}},{"skip-cert-verify",false},{"udp",false},{"tfo",false},{"encryption","none"},{"flow",""},
   {"network","ws"},{"ws-opts",QJsonObject{{"path","/proxy%20path?roundtrip=1"},{"headers",QJsonObject{{"hOsT","ws.fixture.invalid:8443"}}}}}};
  const auto body=QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}}}).toJson();const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));
  EngineStartOptions options;options.nodes=parsed.nodes;options.selectedNodeId=parsed.nodes.first().id;options.routingMode="global";options.proxyPort=12345;
  QJsonObject before;const auto error=RustCoreEngine::configuration(options,&before);QVERIFY2(error.isEmpty(),qPrintable(error));QString source,id;
  {
   NodeStore store(path);QVERIFY(store.saveSubscription({},"round-trip source",QUrl("https://fixture.invalid/subscription"),360,false));source=store.subscriptions().first().id;
   QVERIFY(store.importNodes(parsed.nodes,source));id=store.nodes().first().id;QVERIFY(store.select(id));
   QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto ciphertext=file.readAll();QVERIFY(!ciphertext.contains("00112233-4455"));QVERIFY(!ciphertext.contains("ws.fixture.invalid"));
  }
  {
   NodeStore restored(path);QVERIFY2(restored.error().isEmpty(),qPrintable(restored.error()));QCOMPARE(restored.selectedId(),id);QCOMPARE(restored.nodes().size(),1);
   const auto saved=restored.nodes().first();QCOMPARE(saved.sourceId,source);QCOMPARE(saved.parameters,parsed.nodes.first().parameters);QCOMPARE(saved.originalConfiguration,node);
   options.nodes=restored.nodes();options.selectedNodeId=restored.selectedId();QJsonObject after;QVERIFY(RustCoreEngine::configuration(options,&after).isEmpty());QCOMPARE(after,before);
   // Unknown extensions keep their original JSON null/false values, survive
   // encryption and remain ineligible for native execution after recreation.
   auto extension=node;extension["future-security"]=QJsonObject{{"enabled",false},{"key",QJsonValue()}};
   const auto unsupported=NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{extension}}}).toJson());QVERIFY(unsupported);QVERIFY(restored.importNodes(unsupported.nodes,source));
  }
  NodeStore unsupported(path);QCOMPARE(unsupported.nodes().first().originalConfiguration["future-security"],QJsonValue(QJsonObject{{"enabled",false},{"key",QJsonValue()}}));
  options.nodes=unsupported.nodes();options.selectedNodeId=unsupported.selectedId();QJsonObject output{{"sentinel",true}};
  QVERIFY(!RustCoreEngine::configuration(options,&output).isEmpty());QCOMPARE(output,QJsonObject({{"sentinel",true}}));
 }
 void controllerSelectionFailureRestoresPersistenceAndActualExit(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;const auto path=directory.filePath("selection.dpapi");
  const auto a=QJsonObject{{"name","A"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.a.serverPort()}};
  auto b=a;b["name"]="B";b["port"]=net.b.serverPort();b["username"]=QString::fromUtf8(net.b.username);b["password"]=QString::fromUtf8(net.b.password);
  auto unsupported=a;unsupported["name"]="unsupported";unsupported["future-security"]=QJsonObject{{"enabled",false},{"key",QJsonValue()}};
  // HTTP imports can preserve passwords up to the product's storage bound;
  // this value exceeds the native runtime's narrower credential capability.
  auto nativeLimit=a;nativeLimit["name"]="native-limit";nativeLimit["type"]="http";nativeLimit["username"]="synthetic";nativeLimit["password"]=QString(256,'x');
  auto engine=std::make_unique<RejectOneSelectionEngine>();auto *runtime=engine.get();EngineController controller(std::move(engine),nullptr,path);auto o=options(net);controller.setProxyPort(o.proxyPort);controller.setRoutingMode("global");
  controller.imports()->importText(QString::fromUtf8(QJsonDocument(QJsonObject{{"proxies",QJsonArray{a,b,unsupported,nativeLimit}}}).toJson()));
  QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);QCOMPARE(controller.nodeCatalog().size(),4);
  const auto catalog=controller.nodeCatalog();const auto idA=catalog[0].toMap()["id"].toString(),idB=catalog[1].toMap()["id"].toString();
  const auto request=[&]{QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));QNetworkRequest input(net.url());input.setTransferTimeout(4000);input.setRawHeader("Connection","close");auto *reply=client.get(input);if(!QTest::qWaitFor([&]{return reply->isFinished();},5000)||reply->error()!=QNetworkReply::NoError)return QByteArray("request-failed");return reply->readAll();};
  controller.connectNode(idA);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);QCOMPARE(request(),QByteArray("exit-A"));const auto sessionA=runtime->status().sessionId;QVERIFY(!sessionA.isEmpty());
  QVERIFY(!controller.chooseNode(catalog[2].toMap()["id"].toString()));QCOMPARE(controller.selectedNodeId(),idA);QCOMPARE(controller.activeNodeId(),idA);QCOMPARE(NodeStore(path).selectedId(),idA);
  QVERIFY(!controller.chooseNode("missing"));QVERIFY(!controller.chooseNode({}));QCOMPARE(NodeStore(path).selectedId(),idA);
  QSignalSpy diagnostics(&controller,&EngineController::diagnostic);
  QVERIFY(!controller.chooseNode(catalog[3].toMap()["id"].toString()));
  QVERIFY(!controller.nodeBusy());QCOMPARE(runtime->selectionCalls,0);QCOMPARE(diagnostics.count(),0);
  QCOMPARE(controller.selectedNodeId(),idA);QCOMPARE(controller.activeNodeId(),idA);QCOMPARE(NodeStore(path).selectedId(),idA);
  QCOMPARE(runtime->status().sessionId,sessionA);QCOMPARE(request(),QByteArray("exit-A"));
  // Preserve the asynchronous rollback contract independently of the earlier
  // native capability check. B is valid, but one queued control result fails.
  runtime->rejectNextSelection=idB;QVERIFY(controller.chooseNode(idB));QCOMPARE(runtime->selectionCalls,1);
  QCOMPARE(NodeStore(path).selectedId(),idB);QCOMPARE(controller.activeNodeId(),idA);
  // The worker result is queued. An immediate reconnect request must obey the
  // same pending-selection gate and must not restart A with the unaccepted ID.
  QVERIFY(controller.nodeBusy());controller.connectNode({});QVERIFY(!controller.busy());QVERIFY(controller.apiHealthy());QCOMPARE(runtime->status().sessionId,sessionA);
  QTRY_VERIFY_WITH_TIMEOUT(!controller.nodeBusy(),5000);QCOMPARE(controller.selectedNodeId(),idA);QCOMPARE(controller.activeNodeId(),idA);QCOMPARE(NodeStore(path).selectedId(),idA);
  QCOMPARE(runtime->status().sessionId,sessionA);
  bool receivedQueuedFailure=false;for(const auto &event:diagnostics)if(event[0].toString()=="SwirlRust"&&event[1].toString()=="SelectionFailed")receivedQueuedFailure=true;QVERIFY(receivedQueuedFailure);QCOMPARE(runtime->injectedRejections,1);
  QCOMPARE(request(),QByteArray("exit-A"));QCOMPARE(net.b.forwarded,0);
  QVERIFY(controller.chooseNode(idB));QTRY_COMPARE_WITH_TIMEOUT(controller.activeNodeId(),idB,5000);QCOMPARE(NodeStore(path).selectedId(),idB);QCOMPARE(request(),QByteArray("exit-B"));
  controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),5000);
 }
 void storeCredentialEditsRejectCoercionWithoutRewritingTheSnapshot(){
  QTemporaryDir directory;const auto path=directory.filePath("editable.dpapi");NodeStore store(path);
  QVariantMap edit{{"name","editable"},{"protocol","http"},{"host","127.0.0.1"},{"port",1080},{"username","keep-user"},{"password","keep-password"}};
  QVERIFY(store.saveNode(edit));edit["id"]=store.nodes().first().id;
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto original=file.readAll();file.close();
  for(const auto &key:QStringList{"username","password","cipher","serverName"})for(const auto &value:QVariantList{QVariant(),false,123,QVariantList{},QVariantMap{}}){auto bad=edit;bad[key]=value;QVERIFY(!store.saveNode(bad));}
  auto bad=edit;bad["replaceCredentials"]="true";QVERIFY(!store.saveNode(bad));
  QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),original);file.close();NodeStore restored(path);QCOMPARE(restored.nodes().first().username,QString("keep-user"));QCOMPARE(restored.nodes().first().password,QString("keep-password"));
 }
 void lostSubscriptionSelectionCannotActivateImplicitDirect(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;const auto path=directory.filePath("removed-selection.dpapi");
  {
   NodeStore store(path);QVERIFY(store.saveSubscription({},"synthetic source",QUrl("https://fixture.invalid/subscription"),360,false));const auto source=store.subscriptions().first().id;
   const auto first=NodeImporter::parse(QString("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: %1}]").arg(net.a.serverPort()).toUtf8());QVERIFY(first);QVERIFY(store.importNodes(first.nodes,source));QVERIFY(store.select(store.nodes().first().id));
   const auto replacement=NodeImporter::parse(QString("proxies: [{name: replacement, type: socks5, server: 127.0.0.1, port: %1}]").arg(net.b.serverPort()).toUtf8());QVERIFY(replacement);QVERIFY(store.importNodes(replacement.nodes,source));QVERIFY(store.selectedId().isEmpty());
  }
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);auto o=options(net);controller.setProxyPort(o.proxyPort);controller.setRoutingMode("global");
  controller.connectNode({});QVERIFY(!controller.processAlive());QVERIFY(!controller.apiHealthy());QVERIFY(!controller.nodeError().isEmpty());QCOMPARE(net.a.forwarded,0);QCOMPARE(net.b.forwarded,0);QCOMPARE(net.httpRequests,0);
  // An explicit user routing decision may still choose DIRECT normally.
  controller.setRoutingMode("direct");controller.connectNode({});QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),4000);
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));QNetworkRequest request(net.url());request.setTransferTimeout(4000);auto *reply=client.get(request);
  QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,0);QCOMPARE(net.b.forwarded,0);reply->deleteLater();controller.stop();
 }
 void leavingExplicitDirectUsesTheSavedNodeForGlobalAndRuleModes(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;const auto path=directory.filePath("direct-mode.dpapi");
  auto engine=std::make_unique<ThreadedEngine>();auto *runtime=engine.get();EngineController controller(std::move(engine),nullptr,path);const auto o=options(net);controller.setProxyPort(o.proxyPort);controller.setRoutingMode("global");
  QJsonObject a{{"name","A"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.a.serverPort()}},b=a;b["name"]="B";b["port"]=net.b.serverPort();b["username"]=QString::fromUtf8(net.b.username);b["password"]=QString::fromUtf8(net.b.password);
  auto unknown=a;unknown["name"]="unknown";unknown["future-security"]=QJsonObject{{"enabled",false},{"key",QJsonValue()}};
  auto vision=a;vision["name"]="vision";vision["type"]="vless";vision["uuid"]="00112233-4455-6677-8899-aabbccddeeff";vision["tls"]=true;vision["flow"]="xtls-rprx-vision";
  controller.imports()->importText(QString::fromUtf8(QJsonDocument(QJsonObject{{"proxies",QJsonArray{a,b,unknown,vision}}}).toJson()));QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);QCOMPARE(controller.nodeCatalog().size(),4);
  const auto idA=controller.nodeCatalog()[0].toMap()["id"].toString(),idB=controller.nodeCatalog()[1].toMap()["id"].toString();QVERIFY(controller.chooseNode(idA));QVERIFY(controller.saveRoutingRule("MATCH",{},"SWIRL"));
  controller.setRoutingMode("direct");controller.connectNode({});QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);QVERIFY(runtime->status().directSession);const auto session=runtime->status().sessionId;
  const auto request=[&]{QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));QNetworkRequest input(net.url());input.setTransferTimeout(4000);input.setRawHeader("Connection","close");auto *reply=client.get(input);if(!QTest::qWaitFor([&]{return reply->isFinished();},5000)||reply->error()!=QNetworkReply::NoError)return QByteArray("request-failed");return reply->readAll();};
  QCOMPARE(request(),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,0);
  for(qsizetype index=2;index<4;++index){
   const auto unsupported=controller.nodeCatalog()[index].toMap()["id"].toString();QVERIFY(!controller.chooseNode(unsupported));QVERIFY(!controller.nodeError().isEmpty());QCOMPARE(NodeStore(path).selectedId(),idA);
   // The worker adapter enforces the same boundary independently of the
   // controller, while an explicit DIRECT route remains operational.
   QSignalSpy diagnostics(runtime,&ProxyEngine::diagnostic);runtime->selectNode(unsupported);QTRY_COMPARE_WITH_TIMEOUT(diagnostics.size(),qsizetype(1),5000);QCOMPARE(diagnostics.first()[1].toString(),QString("SelectionUnsupported"));
   QCOMPARE(controller.selectedNodeId(),idA);QCOMPARE(controller.activeNodeId(),idA);QVERIFY(controller.apiHealthy());QVERIFY(runtime->status().directSession);QCOMPARE(runtime->status().sessionId,session);
  }
  QVERIFY(controller.chooseNode(idB));QTRY_COMPARE_WITH_TIMEOUT(controller.activeNodeId(),idB,5000);QCOMPARE(NodeStore(path).selectedId(),idB);QVERIFY(runtime->status().directSession);QCOMPARE(controller.routingMode(),QString("direct"));
  QCOMPARE(request(),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,0);QCOMPARE(net.b.forwarded,0);
  for(const auto &mode:QStringList{"global","rule"}){
   controller.setRoutingMode(mode);QTRY_COMPARE_WITH_TIMEOUT(controller.routingMode(),mode,5000);QVERIFY(!runtime->status().directSession);
   QCOMPARE(controller.selectedNodeId(),idB);QCOMPARE(controller.activeNodeId(),idB);QCOMPARE(NodeStore(path).selectedId(),idB);QCOMPARE(runtime->status().sessionId,session);
   QCOMPARE(request(),QByteArray("exit-B"));
   if(mode=="global"){
    controller.setRoutingMode("direct");QTRY_COMPARE_WITH_TIMEOUT(controller.routingMode(),QString("direct"),5000);QVERIFY(runtime->status().directSession);QCOMPARE(request(),QByteArray("DIRECT-BYPASS"));
   }
  }
  QCOMPARE(net.a.forwarded,0);QCOMPARE(net.b.forwarded,2);QCOMPARE(net.httpRequestsByExit.value("DIRECT-BYPASS"),3);controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.busy(),5000);
 }
 void importedRulesResolveNodeNamesToStableSourceOwnedIds(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;const auto path=directory.filePath("rule-leaves.dpapi");
  QJsonObject a{{"name","A"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.a.serverPort()}},b=a;b["name"]="B";b["port"]=net.b.serverPort();b["username"]=QString::fromUtf8(net.b.username);b["password"]=QString::fromUtf8(net.b.password);
  const QJsonObject document{{"proxies",QJsonArray{a,b}},{"rules",QJsonArray{"DOMAIN,localhost,B","MATCH,A"}}};
  const auto o=options(net);EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);controller.setProxyPort(o.proxyPort);controller.setRoutingMode("rule");
  controller.imports()->importText(QString::fromUtf8(QJsonDocument(document).toJson()));QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);
  QCOMPARE(controller.nodeCatalog().size(),2);const auto idA=controller.nodeCatalog()[0].toMap()["id"].toString(),idB=controller.nodeCatalog()[1].toMap()["id"].toString();
  QCOMPARE(controller.networkConfigurationSnapshot()["rules"].toStringList(),QStringList({"DOMAIN,localhost,"+idB,"MATCH,"+idA}));
  QCOMPARE(NodeStore(path).networkConfiguration()["importedConfiguration"].toObject()["configuration"].toObject()["rules"],document["rules"]);
  controller.connectNode(idA);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),4000);
  const auto request=[&](const QString &host){QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));auto url=net.url();url.setHost(host);QNetworkRequest input(url);input.setTransferTimeout(4000);input.setRawHeader("Connection","close");auto *reply=client.get(input);if(!QTest::qWaitFor([&]{return reply->isFinished();},5000)||reply->error()!=QNetworkReply::NoError)return QByteArray("request-failed");return reply->readAll();};
  QCOMPARE(request("127.0.0.1"),QByteArray("exit-A"));QCOMPARE(request("localhost"),QByteArray("exit-B"));QCOMPARE(net.a.forwarded,1);QCOMPARE(net.b.forwarded,1);
  controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
  // Editing a persisted direct node target retains the same stable reference.
  QVERIFY(controller.saveRoutingRule("DOMAIN","localhost",idB,0));QCOMPARE(controller.networkConfigurationSnapshot()["rules"].toStringList().first(),"DOMAIN,localhost,"+idB);
  const auto previous=controller.networkConfigurationSnapshot();auto bad=document;bad["rules"]=QJsonArray{"MATCH,"+idA};controller.imports()->importText(QString::fromUtf8(QJsonDocument(bad).toJson()));QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);QCOMPARE(controller.networkConfigurationSnapshot(),previous);
 }
 void subscriptionProductChainAgainstIndependentPeer(){
  if(!qEnvironmentVariableIsSet("SWIRL_PRODUCT_FIXTURE"))QSKIP("Independent Python product-chain fixture supplies synthetic subscription, proxy peers and origins.");
  QFile input(qEnvironmentVariable("SWIRL_PRODUCT_FIXTURE"));QVERIFY(input.open(QIODevice::ReadOnly));QVERIFY(input.size()<=NodeImporter::MaximumBytes);
  const auto fixture=NodeImporter::strictJsonObject(input.readAll());QVERIFY(!fixture.isEmpty());
  for(const auto &key:QStringList{"http_port","https_port","stream_port"}){
   const auto value=fixture.value(key);QVERIFY(value.isDouble());QVERIFY(value.toDouble()==value.toInt());QVERIFY(value.toInt()>0&&value.toInt()<=65535);
  }
  for(const auto &key:QStringList{"subscription","ca_pem","expected_body"})QVERIFY(fixture.value(key).isString()&&!fixture.value(key).toString().isEmpty());
  const auto lengthHeader=fixture.value("stream_length_header");QVERIFY(lengthHeader.isUndefined()||lengthHeader.isBool());
  const bool framedStream=lengthHeader.toBool();QString halfcloseSignal;
  if(fixture.contains("stream_halfclose_signal")){
   const auto signal=fixture.value("stream_halfclose_signal");QVERIFY(framedStream&&signal.isString()&&!signal.toString().isEmpty());halfcloseSignal=signal.toString();
  }
  const int httpPort=fixture["http_port"].toInt(),httpsPort=fixture["https_port"].toInt(),streamPort=fixture["stream_port"].toInt();
  const auto certificates=QSslCertificate::fromData(fixture["ca_pem"].toString().toUtf8());QVERIFY(!certificates.isEmpty());QVERIFY(QSslSocket::supportsSsl());
  const auto expected=fixture["expected_body"].toString().toUtf8();QTemporaryDir directory;QVERIFY(directory.isValid());const auto path=directory.filePath("product.dpapi");
  QTcpServer reservation;QVERIFY(reservation.listen(QHostAddress::LocalHost));const auto proxyPort=reservation.serverPort();reservation.close();
  QString idA,idB;QVariantMap network;QJsonObject original;QList<ProxyNode> savedNodes;
  {
   // This is the application's importer, encrypted store and settings owner.
   // No Rust IR or already-normalized node is injected into the product path.
   EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);controller.setProxyPort(proxyPort);controller.setRoutingMode("global");
   controller.imports()->importText(fixture["subscription"].toString());QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);
   QCOMPARE(controller.nodeCatalog().size(),2);QVERIFY2(controller.networkConfigurationError().isEmpty(),qPrintable(controller.networkConfigurationError()));
   for(const auto &entry:controller.nodeCatalog()){const auto row=entry.toMap();if(row["name"]=="A")idA=row["id"].toString();if(row["name"]=="B")idB=row["id"].toString();}
   QVERIFY(!idA.isEmpty()&&!idB.isEmpty()&&idA!=idB);QVERIFY(controller.chooseNode(idA));
   network=controller.networkConfigurationSnapshot();QCOMPARE(network["groups"].toList().size(),1);QCOMPARE(network["rules"].toStringList().size(),9);
   NodeStore persisted(path);QCOMPARE(persisted.selectedId(),idA);savedNodes=persisted.nodes();original=persisted.networkConfiguration()["importedConfiguration"].toObject();
   QVERIFY(!original.isEmpty());QCOMPARE(original["configuration"].toObject()["rules"].toArray()[0].toString(),QString("DOMAIN,a.product.invalid,A"));
  }
  struct Response {QNetworkReply::NetworkError error;int status;QByteArray body;};
  const auto request=[&](const QString &host,int port,const QString &target,bool encrypted=false){
   QUrl url;url.setScheme(encrypted?"https":"http");url.setHost(host);url.setPort(port);url.setPath(target);
   if(encrypted){
    // QNAM can finish HTTP and close its transport before a TLS close_notify
    // exchange. Own this test client's TLS shutdown so the independent origin
    // can require both authenticated close alerts, without relaxing its checks.
    QSslSocket socket;socket.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",proxyPort));
    auto tls=QSslConfiguration::defaultConfiguration();tls.setCaCertificates(certificates);tls.setPeerVerifyMode(QSslSocket::VerifyPeer);socket.setSslConfiguration(tls);
    socket.connectToHostEncrypted(host,quint16(port));
    if(!QTest::qWaitFor([&]{return socket.isEncrypted()||socket.state()==QAbstractSocket::UnconnectedState;},5000))return Response{QNetworkReply::TimeoutError,0,{}};
    if(!socket.isEncrypted())return Response{socket.error()==QAbstractSocket::SslHandshakeFailedError?QNetworkReply::SslHandshakeFailedError:QNetworkReply::UnknownNetworkError,0,{}};
    const auto message="GET "+url.path(QUrl::FullyEncoded).toUtf8()+" HTTP/1.1\r\nHost: "+host.toUtf8()+':'+QByteArray::number(port)+"\r\nConnection: close\r\n\r\n";
    if(socket.write(message)!=message.size())return Response{QNetworkReply::UnknownNetworkError,0,{}};
    QByteArray response;qsizetype separator=-1;const auto bodyLength=expected.size()+1+target.toUtf8().size();
    if(!QTest::qWaitFor([&]{response+=socket.readAll();separator=response.indexOf("\r\n\r\n");return response.size()>65536||(separator>=0&&response.size()>=separator+4+bodyLength)||socket.state()==QAbstractSocket::UnconnectedState;},5000))return Response{QNetworkReply::TimeoutError,0,{}};
    if(separator<0||response.size()>65536||!response.startsWith("HTTP/1.1 200 ")||!response.left(separator+2).contains("\r\nContent-Length: "+QByteArray::number(bodyLength)+"\r\n"))return Response{QNetworkReply::UnknownNetworkError,0,{}};
    socket.disconnectFromHost();if(!QTest::qWaitFor([&]{return socket.state()==QAbstractSocket::UnconnectedState;},5000))return Response{QNetworkReply::TimeoutError,0,{}};
    response+=socket.readAll();return Response{QNetworkReply::NoError,200,response.mid(separator+4)};
   }
   QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",proxyPort));
   QNetworkRequest message(url);message.setRawHeader("Connection","close");message.setAttribute(QNetworkRequest::Http2AllowedAttribute,false);message.setTransferTimeout(5000);
   auto *reply=client.get(message);if(!QTest::qWaitFor([&]{return reply->isFinished();},6000)){reply->abort();return Response{QNetworkReply::TimeoutError,0,{}};}
   return Response{reply->error(),reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt(),reply->readAll()};
  };
  const auto reachesOrigin=[&](const QString &host,int port,const QString &target,bool encrypted=false){
   const auto response=request(host,port,target,encrypted);return response.error==QNetworkReply::NoError&&response.status==200&&response.body==expected+':'+target.toUtf8();
  };
  {
   EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);controller.setProxyPort(proxyPort);QCOMPARE(controller.metaObject()->indexOfProperty("executablePath"),-1);
   QCOMPARE(controller.selectedNodeId(),idA);QCOMPARE(QJsonObject::fromVariantMap(controller.networkConfigurationSnapshot()),QJsonObject::fromVariantMap(network));
   NodeStore restored(path);QCOMPARE(restored.nodes().size(),savedNodes.size());QCOMPARE(restored.networkConfiguration()["importedConfiguration"].toObject(),original);
   for(qsizetype i=0;i<savedNodes.size();++i){QCOMPARE(restored.nodes()[i].parameters,savedNodes[i].parameters);QCOMPARE(restored.nodes()[i].password,savedNodes[i].password);QCOMPARE(restored.nodes()[i].originalConfiguration,savedNodes[i].originalConfiguration);}
   controller.connectNode({});QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);QCOMPARE(controller.activeNodeId(),idA);QCOMPARE(controller.engineKind(),QString("rust"));QCOMPARE(controller.processId(),QString::number(QCoreApplication::applicationPid()));
   QVERIFY(controller.controlEndpoint().startsWith("in-process://SwirlRust/"));
   QVERIFY(reachesOrigin("a.product.invalid",httpPort,"/selected-a"));QVERIFY(reachesOrigin("localhost",httpsPort,"/selected-a-tls",true));
   QTcpSocket stream;stream.setProxy(QNetworkProxy::NoProxy);stream.connectToHost(QHostAddress::LocalHost,proxyPort);QTRY_COMPARE_WITH_TIMEOUT(stream.state(),QAbstractSocket::ConnectedState,4000);
   const auto authority=QByteArray("stream.product.invalid:")+QByteArray::number(streamPort);const auto connectRequest="CONNECT "+authority+" HTTP/1.1\r\nHost: "+authority+"\r\n\r\n";
   QCOMPARE(stream.write(connectRequest),qint64(connectRequest.size()));QByteArray response;
   QVERIFY(QTest::qWaitFor([&]{response+=stream.readAll();return response.contains("\r\n\r\n");},5000));QVERIFY(response.startsWith("HTTP/1.1 200 "));QVERIFY(response.endsWith("\r\n\r\n"));
   const QByteArray first="before-node-switch\n";constexpr qsizetype payloadSize=256*1024+17;
   if(framedStream){
    // The independent origin can frame a complete upload without requiring
    // an intermediate proxy to propagate TCP CloseWrite to its target socket.
    const auto length=quint32(first.size()+payloadSize);QByteArray prefix(4,'\0');
    for(int index=0;index<4;++index)prefix[index]=char((length>>(8*(3-index)))&0xffu);
    QCOMPARE(stream.write(prefix),qint64(prefix.size()));
   }
   QCOMPARE(stream.write(first),qint64(first.size()));QTRY_VERIFY_WITH_TIMEOUT(stream.bytesAvailable()>=first.size(),5000);QCOMPARE(stream.read(first.size()),first);
   QVERIFY(controller.chooseNode(idB));QTRY_COMPARE_WITH_TIMEOUT(controller.activeNodeId(),idB,5000);QCOMPARE(controller.selectedNodeId(),idB);QCOMPARE(NodeStore(path).selectedId(),idB);
   QVERIFY(reachesOrigin("b.product.invalid",httpPort,"/selected-b"));
   const auto deniedTls=request("wrong.fixture.invalid",httpsPort,"/wrong-certificate",true);QCOMPARE(deniedTls.error,QNetworkReply::SslHandshakeFailedError);QVERIFY(deniedTls.body.isEmpty());
   // The already-established A tunnel survives the B selection. Both sides
   // carry exact bytes in irregular chunks, including reads after upload EOF.
   QByteArray payload(payloadSize,Qt::Uninitialized);for(qsizetype i=0;i<payload.size();++i)payload[i]=char((i*31+17)%256);
   for(qsizetype position=0;position<payload.size();){const auto count=qMin(qsizetype(1+(position*73)%8191),payload.size()-position);QCOMPARE(stream.write(payload.constData()+position,count),qint64(count));position+=count;}
   QByteArray echoed;QVERIFY(QTest::qWaitFor([&]{echoed+=stream.readAll();return echoed.size()>=payload.size();},8000));QCOMPARE(echoed,payload);QTRY_COMPARE_WITH_TIMEOUT(stream.bytesToWrite(),qint64(0),3000);
#ifdef Q_OS_WIN
   QCOMPARE(::shutdown(SOCKET(stream.socketDescriptor()),SD_SEND),0);
#else
   QCOMPARE(::shutdown(int(stream.socketDescriptor()),SHUT_WR),0);
#endif
   if(!halfcloseSignal.isEmpty()){
    // Release the delayed origin response only after the real local upload
    // half-close succeeded. This does not claim the origin observed that FIN.
    QFile signal(halfcloseSignal);QVERIFY(signal.open(QIODevice::WriteOnly|QIODevice::NewOnly));
    const QByteArray marker="half-closed";QCOMPARE(signal.write(marker),qint64(marker.size()));QVERIFY(signal.flush());signal.close();
   }
   const QByteArray tail="origin-after-halfclose";QByteArray receivedTail;QVERIFY(QTest::qWaitFor([&]{receivedTail+=stream.readAll();return receivedTail.size()>=tail.size();},5000));QCOMPARE(receivedTail,tail);
   QTRY_COMPARE_WITH_TIMEOUT(stream.state(),QAbstractSocket::UnconnectedState,5000);controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.busy(),5000);
  }
  {
   // Both the previous engine and configuration manager have been destroyed.
   EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);controller.setProxyPort(proxyPort);QCOMPARE(controller.selectedNodeId(),idB);QCOMPARE(QJsonObject::fromVariantMap(controller.networkConfigurationSnapshot()),QJsonObject::fromVariantMap(network));
   controller.connectNode({});QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);QCOMPARE(controller.activeNodeId(),idB);QVERIFY(reachesOrigin("b.product.invalid",httpPort,"/restored-b"));
   controller.setRoutingMode("rule");QTRY_COMPARE_WITH_TIMEOUT(controller.routingMode(),QString("rule"),5000);
   QVERIFY(reachesOrigin("a.product.invalid",httpPort,"/rule-a"));QVERIFY(reachesOrigin("b.product.invalid",httpPort,"/rule-b"));
   QVERIFY(reachesOrigin("choice.product.invalid",httpPort,"/rule-choice"));QVERIFY(reachesOrigin("127.0.0.1",httpPort,"/rule-direct"));
   QVERIFY(reachesOrigin("nested.suffix.product.invalid",httpPort,"/rule-suffix"));
   QVERIFY(reachesOrigin("keyword.product.invalid",httpPort,"/rule-keyword"));
   QVERIFY(reachesOrigin("port.product.invalid",httpPort,"/rule-port"));
   const auto rejected=request("denied.product.invalid",httpPort,"/rule-reject");QVERIFY(rejected.error!=QNetworkReply::NoError);QVERIFY(rejected.status!=200);
   // Use another destination port so the terminal MATCH rule, rather than the
   // preceding DST-PORT rule, is responsible for refusing this request.
   const auto unmatched=request("unmatched.product.invalid",httpsPort,"/rule-unmatched");QVERIFY(unmatched.error!=QNetworkReply::NoError);QVERIFY(unmatched.status!=200);
   QCOMPARE(controller.engineKind(),QString("rust"));QCOMPARE(controller.activeNodeId(),idB);controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.busy(),5000);
  }
  QTcpServer released;QVERIFY(released.listen(QHostAddress::LocalHost,proxyPort));
 }
 void publicRealityProductChainAgainstIndependentPeer(){
  if(!qEnvironmentVariableIsSet("SWIRL_PUBLIC_QT_FIXTURE"))QSKIP("The explicit public Windows Qt fixture supplies synthetic peers and fixed public targets.");
#ifndef Q_OS_WIN
  QSKIP("The public product gate requires real Windows NodeStore/DPAPI.");
#endif
  const auto fixturePath=qEnvironmentVariable("SWIRL_PUBLIC_QT_FIXTURE"),reportPath=qEnvironmentVariable("SWIRL_PUBLIC_QT_REPORT");
  QVERIFY(!reportPath.isEmpty()&&QFileInfo(reportPath).isAbsolute());
  QVERIFY(QFileInfo(fixturePath).absoluteFilePath()!=QFileInfo(reportPath).absoluteFilePath());
  QJsonObject report{{"schema",1},{"scope","Windows Qt/DPAPI public targets: global node selection plus imported MATCH rejection"},
   {"provider_connection",false},{"imported",false},{"encrypted_store_reloaded",false},{"parameters_preserved",false},
   {"in_process_rust",false},{"node_switch_verified",false},{"selected_node_restored",false},{"match_reject_verified",false},
   {"stopped",false},{"listener_released",false},{"checks",QJsonArray{}}};
  const auto saveReport=[&]{QSaveFile file(reportPath);const auto bytes=QJsonDocument(report).toJson();return file.open(QIODevice::WriteOnly)&&file.write(bytes)==bytes.size()&&file.commit();};
  const auto reportGuard=qScopeGuard([&]{saveReport();});QVERIFY(saveReport());
  QFile input(fixturePath);QVERIFY(input.open(QIODevice::ReadOnly));QVERIFY(input.size()>0&&input.size()<=NodeImporter::MaximumBytes);
  const auto fixture=NodeImporter::strictJsonObject(input.readAll());QVERIFY(!fixture.isEmpty());input.close();
  for(const auto &key:fixture.keys())QVERIFY((QStringList{"subscription","targets","vision"}.contains(key)));
  QVERIFY(fixture["subscription"].isString()&&!fixture["subscription"].toString().isEmpty());QCOMPARE(fixture["vision"],QJsonValue(true));
  const auto document=NodeImporter::strictJsonObject(fixture["subscription"].toString().toUtf8());QVERIFY(!document.isEmpty());
  for(const auto &key:document.keys())QVERIFY((QStringList{"proxies","rules"}.contains(key)));
  const QJsonArray expectedRules{"DOMAIN,www.msftconnecttest.com,A","DOMAIN,www.rust-lang.org,A","MATCH,REJECT"};
  QVERIFY(document["rules"]==QJsonValue(expectedRules));QVERIFY(document["proxies"].isArray()&&document["proxies"].toArray().size()==2);
  QStringList fixtureNames;
  for(const auto &entry:document["proxies"].toArray()){
   QVERIFY(entry.isObject());const auto node=entry.toObject();const auto name=node["name"].toString();
   QVERIFY((name=="A"||name=="B")&&!fixtureNames.contains(name));fixtureNames.append(name);
   QVERIFY(node["server"]==QJsonValue("127.0.0.1")&&node["type"]==QJsonValue("vless"));
   QVERIFY(node["tls"]==QJsonValue(true)&&node["flow"]==QJsonValue("xtls-rprx-vision"));
   QVERIFY(node["client-fingerprint"]==QJsonValue("chrome")&&node["reality-opts"].isObject());
  }
  const QJsonArray targets{
   QJsonObject{{"host","www.msftconnecttest.com"},{"port",80},{"method","GET"},{"path","/connecttest.txt"},{"expected_body","Microsoft Connect Test"}},
   QJsonObject{{"host","www.rust-lang.org"},{"port",443},{"method","HEAD"},{"path","/"}}};
  QVERIFY(fixture["targets"].isArray()&&fixture["targets"].toArray().size()==targets.size());
  const auto suppliedTargets=fixture["targets"].toArray();
  for(qsizetype i=0;i<targets.size();++i){
   QVERIFY(suppliedTargets[i].isObject());const auto supplied=suppliedTargets[i].toObject(),expected=targets[i].toObject();
   for(const auto &key:supplied.keys())QVERIFY((QStringList{"host","port","method","path","expected_body"}.contains(key)));
   for(const auto &key:QStringList{"host","port","method","path"})QVERIFY(supplied[key]==expected[key]);
   if(supplied.contains("expected_body"))QVERIFY(expected.contains("expected_body")&&supplied["expected_body"]==expected["expected_body"]);
  }
  QVERIFY(QSslSocket::supportsSsl());QTemporaryDir directory;QVERIFY(directory.isValid());const auto path=directory.filePath("public-product.dpapi");
  QTcpServer reservation;reservation.setProxy(QNetworkProxy::NoProxy);QVERIFY(reservation.listen(QHostAddress::LocalHost));const auto proxyPort=reservation.serverPort();reservation.close();
  QString idA,idB;QList<ProxyNode> savedNodes;QVariantMap savedNetwork;
  {
   EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);controller.setProxyPort(proxyPort);controller.setRoutingMode("global");
   controller.imports()->importText(fixture["subscription"].toString());QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);
   QVERIFY(controller.networkConfigurationError().isEmpty());QCOMPARE(controller.nodeCatalog().size(),2);
   for(const auto &entry:controller.nodeCatalog()){const auto row=entry.toMap();if(row["name"]=="A")idA=row["id"].toString();if(row["name"]=="B")idB=row["id"].toString();}
   QVERIFY(!idA.isEmpty()&&!idB.isEmpty()&&idA!=idB);QVERIFY(controller.chooseNode(idA));
   savedNetwork=controller.networkConfigurationSnapshot();QCOMPARE(savedNetwork["rules"].toStringList().size(),3);
   NodeStore persisted(path);QVERIFY(persisted.error().isEmpty()&&persisted.selectedId()==idA);savedNodes=persisted.nodes();QCOMPARE(savedNodes.size(),2);
   QFile encrypted(path);QVERIFY(encrypted.open(QIODevice::ReadOnly));auto stored=encrypted.readAll();
   QVERIFY(stored.startsWith("SWIRLNODE1\n")&&stored.size()>11);QVERIFY(!stored.contains(fixture["subscription"].toString().toUtf8()));
   for(const auto &node:savedNodes){
    const auto reality=node.parameters.value("reality-opts").toObject();
    // VLESS stores its credential in uuid, not ProxyNode::password. Check the
    // actual security fields so an empty unrelated member cannot fake a pass.
    for(const auto &credential:QStringList{node.parameters.value("uuid").toString(),reality.value("public-key").toString(),reality.value("short-id").toString()}){
     QVERIFY(!credential.isEmpty());QVERIFY(!stored.contains(credential.toUtf8()));
    }
   }
   stored.fill('\0');report["imported"]=true;
  }
  // Qt's socket-level HttpProxy is CONNECT and Socks5Proxy resolves host names
  // at the proxy. QSslSocket VerifyPeer retains system roots and host checks.
  // Primary references: doc.qt.io/qt-6.10/qnetworkproxy.html and qsslsocket.html;
  // Qt Network is the existing LGPL/GPL dependency. No upstream code is copied.
  const auto request=[&](const QString &nodeName,QNetworkProxy::ProxyType proxyType,const QJsonObject &target){
   const auto host=target["host"].toString(),method=target["method"].toString();const int port=target["port"].toInt();const bool tls=port==443;
   QJsonObject check{{"node",nodeName},{"frontend",proxyType==QNetworkProxy::HttpProxy?"http-connect":"socks5"},
    {"host",host},{"port",port},{"method",method},{"proxy_host","127.0.0.1"},{"proxy_port",int(proxyPort)},{"stage","connect"},{"http_status",0},{"certificate_verified",false},{"tls_version",""},{"expected_body_verified",false},{"success",false}};
   QSslSocket socket;socket.setReadBufferSize(65537);socket.setProxy(QNetworkProxy(proxyType,"127.0.0.1",proxyPort));
   bool verificationError=false,transportError=false;int socketError=-1,tlsErrors=0;
   QObject::connect(&socket,&QSslSocket::sslErrors,&socket,[&](const QList<QSslError>& errors){verificationError=true;tlsErrors=int(errors.size());});
   QObject::connect(&socket,&QAbstractSocket::errorOccurred,&socket,[&](QAbstractSocket::SocketError error){socketError=int(error);if(error!=QAbstractSocket::RemoteHostClosedError)transportError=true;});
   QElapsedTimer timer;timer.start();constexpr int totalBudgetMs=15000;
   const auto finish=[&]{check["socket_error"]=socketError;check["tls_error_count"]=tlsErrors;check["elapsed_ms"]=int(timer.elapsed());check["closed"]=socket.state()==QAbstractSocket::UnconnectedState;return check;};
   const auto wait=[&](const auto &predicate){const auto remaining=totalBudgetMs-int(timer.elapsed());return remaining>0&&QTest::qWaitFor(predicate,remaining);};
   if(tls){
    check["stage"]="tls-handshake";auto configuration=QSslConfiguration::defaultConfiguration();configuration.setPeerVerifyMode(QSslSocket::VerifyPeer);configuration.setProtocol(QSsl::TlsV1_3);
    configuration.setAllowedNextProtocols({QByteArray("http/1.1")});socket.setSslConfiguration(configuration);socket.connectToHostEncrypted(host,quint16(port));
   }else socket.connectToHost(host,quint16(port));
   if(!wait([&]{return (tls?socket.isEncrypted():socket.state()==QAbstractSocket::ConnectedState)||socket.state()==QAbstractSocket::UnconnectedState;}))return finish();
   if(socket.state()!=QAbstractSocket::ConnectedState||verificationError||transportError)return finish();
   if(tls){
    const bool verified=socket.isEncrypted()&&!socket.peerCertificate().isNull()&&socket.sslHandshakeErrors().isEmpty()&&socket.sessionProtocol()==QSsl::TlsV1_3&&socket.sslConfiguration().nextNegotiatedProtocol()==QByteArray("http/1.1");
    check["certificate_verified"]=verified;check["tls_version"]=socket.sessionProtocol()==QSsl::TlsV1_3?"TLSv1.3":"unsupported";if(!verified)return finish();
   }
   check["stage"]="http-write";const auto message=method.toUtf8()+" "+target["path"].toString().toUtf8()+" HTTP/1.1\r\nHost: "+host.toUtf8()+"\r\nConnection: close\r\nAccept-Encoding: identity\r\n\r\n";
   if(socket.write(message)!=message.size())return finish();
   check["stage"]="http-headers";QByteArray response;qsizetype separator=-1;bool oversized=false;
   if(!wait([&]{response+=socket.readAll();oversized=response.size()>65536;separator=response.indexOf("\r\n\r\n");return oversized||separator>=0||socket.state()==QAbstractSocket::UnconnectedState;}))return finish();
   if(oversized||separator<0||verificationError||transportError)return finish();
   const auto lines=response.left(separator).split('\n');if(lines.isEmpty())return finish();
   const auto statusLine=lines.first().trimmed().split(' ');bool validStatus=false;
   const int status=statusLine.size()>=2?statusLine[1].toInt(&validStatus):0;check["http_status"]=status;
   if(!validStatus||statusLine[1].size()!=3||(statusLine[0]!="HTTP/1.1"&&statusLine[0]!="HTTP/1.0")||status<200||status>=400)return finish();
   check["stage"]="http-body";if(method=="GET"){
    if(status!=200)return finish();const auto expected=target["expected_body"].toString().toUtf8();bool contentLengthSeen=false;
    for(qsizetype i=1;i<lines.size();++i){
     const auto line=lines[i].trimmed();const auto colon=line.indexOf(':');if(colon<=0)return finish();const auto header=line.left(colon).toLower(),value=line.mid(colon+1).trimmed();
     if(header=="transfer-encoding")return finish();
     if(header=="content-encoding"&&value.toLower()!="identity")return finish();
     if(header=="content-length"){bool ok=false;const auto length=value.toLongLong(&ok);if(contentLengthSeen||!ok||length!=expected.size())return finish();contentLengthSeen=true;}
    }
    if(!contentLengthSeen)return finish();
    if(!wait([&]{response+=socket.readAll();return response.size()>65536||response.size()>=separator+4+expected.size()||socket.state()==QAbstractSocket::UnconnectedState;}))return finish();
    if(response.mid(separator+4)!=expected||response.size()>65536)return finish();check["expected_body_verified"]=true;
   }else if(method!="HEAD"||!response.mid(separator+4).isEmpty())return finish();
   check["stage"]="close";if(socket.state()!=QAbstractSocket::UnconnectedState){socket.disconnectFromHost();if(!wait([&]{return socket.state()==QAbstractSocket::UnconnectedState;}))return finish();}
   response+=socket.readAll();if(response.size()>65536||verificationError||transportError)return finish();
   if(method=="GET"&&response.mid(separator+4)!=target["expected_body"].toString().toUtf8())return finish();
   if(method=="HEAD"&&!response.mid(separator+4).isEmpty())return finish();
   check["stage"]="complete";check["success"]=true;return finish();
  };
  {
   EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);controller.setProxyPort(proxyPort);controller.setRoutingMode("global");QCOMPARE(controller.metaObject()->indexOfProperty("executablePath"),-1);
   QVERIFY(controller.selectedNodeId()==idA);QVERIFY(controller.networkConfigurationSnapshot()==savedNetwork);
   NodeStore restored(path);const auto restoredNodes=restored.nodes();QVERIFY(restored.error().isEmpty()&&restoredNodes.size()==savedNodes.size());report["encrypted_store_reloaded"]=true;
   for(qsizetype i=0;i<savedNodes.size();++i){const auto &node=restoredNodes[i],&before=savedNodes[i];QVERIFY(node.parameters==before.parameters&&node.password==before.password&&node.originalConfiguration==before.originalConfiguration);}
   report["parameters_preserved"]=true;controller.connectNode({});QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);
   const auto nativeIdentity=[&]{return controller.engineKind()=="rust"&&controller.processId()==QString::number(QCoreApplication::applicationPid())&&controller.controlEndpoint().startsWith("in-process://SwirlRust/")&&controller.activeProxyPort()==proxyPort;};
   QVERIFY(nativeIdentity());report["in_process_rust"]=true;
   for(const auto &name:QStringList{"A","B"}){
    const auto id=name=="A"?idA:idB;
    if(name=="B"){QVERIFY(controller.chooseNode(id));QTRY_VERIFY_WITH_TIMEOUT(controller.activeNodeId()==id&&!controller.nodeBusy(),5000);QVERIFY(NodeStore(path).selectedId()==id);report["node_switch_verified"]=true;}
    QVERIFY(controller.selectedNodeId()==id&&controller.activeNodeId()==id&&nativeIdentity());
    for(const auto frontend:{QNetworkProxy::HttpProxy,QNetworkProxy::Socks5Proxy})for(const auto &target:targets){
     const auto check=request(name,frontend,target.toObject());auto checks=report["checks"].toArray();checks.append(check);report["checks"]=checks;QVERIFY(saveReport());QVERIFY(check["success"].toBool());
     QVERIFY(controller.selectedNodeId()==id&&controller.activeNodeId()==id&&nativeIdentity());
    }
   }
   controller.setRoutingMode("rule");QTRY_COMPARE_WITH_TIMEOUT(controller.routingMode(),QString("rule"),5000);
   // A real reachable listener makes a mistaken DIRECT route observable. A
   // deliberately unresolvable domain could fail DNS and falsely prove REJECT.
   QTcpServer rejectOrigin;rejectOrigin.setProxy(QNetworkProxy::NoProxy);QVERIFY(rejectOrigin.listen(QHostAddress::LocalHost));
   QTcpSocket control;control.setProxy(QNetworkProxy::NoProxy);control.connectToHost(QHostAddress::LocalHost,rejectOrigin.serverPort());
   QVERIFY(QTest::qWaitFor([&]{return control.state()==QAbstractSocket::ConnectedState&&rejectOrigin.hasPendingConnections();},5000));
   const auto accepted=rejectOrigin.nextPendingConnection();QVERIFY(accepted);accepted->abort();delete accepted;control.abort();
   int leakedConnections=0;QObject::connect(&rejectOrigin,&QTcpServer::newConnection,&rejectOrigin,[&]{++leakedConnections;});
   for(const auto frontend:{QNetworkProxy::HttpProxy,QNetworkProxy::Socks5Proxy}){
    // Qt intentionally bypasses its proxy for localhost destinations. Speak
    // each frontend to Rust explicitly so the local target tests its routing.
    QTcpSocket denied;denied.setProxy(QNetworkProxy::NoProxy);denied.connectToHost(QHostAddress::LocalHost,proxyPort);
    QVERIFY(QTest::qWaitFor([&]{return denied.state()==QAbstractSocket::ConnectedState;},5000));QByteArray response;
    if(frontend==QNetworkProxy::HttpProxy){
     const auto authority=QByteArray("127.0.0.1:")+QByteArray::number(rejectOrigin.serverPort());
     const auto message="CONNECT "+authority+" HTTP/1.1\r\nHost: "+authority+"\r\n\r\n";QCOMPARE(denied.write(message),message.size());
     QVERIFY(QTest::qWaitFor([&]{response+=denied.readAll();return response.contains("\r\n\r\n")||denied.state()==QAbstractSocket::UnconnectedState;},5000));
     QCOMPARE(response,QByteArray("HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"));
    }else{
     const auto greeting=QByteArray::fromHex("050100");QCOMPARE(denied.write(greeting),greeting.size());
     QVERIFY(QTest::qWaitFor([&]{response+=denied.readAll();return response.size()>=2||denied.state()==QAbstractSocket::UnconnectedState;},5000));QCOMPARE(response,QByteArray::fromHex("0500"));response.clear();
     auto message=QByteArray::fromHex("050100017f000001");message.append(char(rejectOrigin.serverPort()>>8));message.append(char(rejectOrigin.serverPort()&255));QCOMPARE(denied.write(message),message.size());
     QVERIFY(QTest::qWaitFor([&]{response+=denied.readAll();return response.size()>=10||denied.state()==QAbstractSocket::UnconnectedState;},5000));QCOMPARE(response,QByteArray::fromHex("05050001000000000000"));
    }
    denied.abort();QCOMPARE(leakedConnections,0);QVERIFY(!rejectOrigin.hasPendingConnections());
   }
   controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.busy(),5000);report["stopped"]=true;
   QCOMPARE(leakedConnections,0);QVERIFY(!rejectOrigin.hasPendingConnections());report["match_reject_verified"]=true;
  }
  {
   EngineController restored(std::make_unique<ThreadedEngine>(),nullptr,path,true);QVERIFY(restored.selectedNodeId()==idB);QVERIFY(restored.networkConfigurationSnapshot()==savedNetwork);report["selected_node_restored"]=true;
  }
  QTcpServer released;released.setProxy(QNetworkProxy::NoProxy);QVERIFY(released.listen(QHostAddress::LocalHost,proxyPort));report["listener_released"]=true;
  QCOMPARE(report["checks"].toArray().size(),8);QVERIFY(saveReport());
 }
 void realityLifecycleProductChainAgainstIndependentPeer(){
  if(!qEnvironmentVariableIsSet("SWIRL_QT_LIFECYCLE_FIXTURE"))QSKIP("The explicit independent Qt lifecycle fixture supplies synthetic peers and origins.");
#ifndef Q_OS_WIN
  QSKIP("The lifecycle product gate requires actual Windows NodeStore/DPAPI.");
#endif
  const auto fixturePath=qEnvironmentVariable("SWIRL_QT_LIFECYCLE_FIXTURE"),reportPath=qEnvironmentVariable("SWIRL_QT_LIFECYCLE_REPORT");
  QVERIFY(!reportPath.isEmpty()&&QFileInfo(reportPath).isAbsolute());QVERIFY(QFileInfo(fixturePath).absoluteFilePath()!=QFileInfo(reportPath).absoluteFilePath());
  QJsonObject report{{"schema",1},{"provider_connection",false},{"imported",false},{"encrypted_store_reloaded",false},{"parameters_preserved",false},
   {"in_process_rust",false},{"stopped",false},{"listener_released",false},{"checks",QJsonArray{}}};
  const auto saveReport=[&]{QSaveFile file(reportPath);const auto bytes=QJsonDocument(report).toJson();return file.open(QIODevice::WriteOnly)&&file.write(bytes)==bytes.size()&&file.commit();};
  const auto reportGuard=qScopeGuard([&]{saveReport();});QVERIFY(saveReport());
  QFile input(fixturePath);QVERIFY(input.open(QIODevice::ReadOnly));QVERIFY(input.size()>0&&input.size()<=NodeImporter::MaximumBytes);
  const auto fixture=NodeImporter::strictJsonObject(input.readAll());QVERIFY(!fixture.isEmpty());input.close();
  const auto mode=fixture["mode"].toString();QVERIFY((QStringList{"tls12","http-control","authentication-failure","cancel","reject"}.contains(mode)));report["mode"]=mode;
  const auto targetPortValue=fixture["target_port"];QVERIFY(targetPortValue.isDouble()&&targetPortValue.toDouble()==targetPortValue.toInt()&&targetPortValue.toInt()>0&&targetPortValue.toInt()<=65535);
  const auto targetPort=quint16(targetPortValue.toInt());QVERIFY(fixture["subscription"].isString()&&!fixture["subscription"].toString().isEmpty());
  const auto expected=fixture["expected_body"].toString().toUtf8();QVERIFY(!expected.isEmpty());
  const auto certificates=QSslCertificate::fromData(fixture["ca_pem"].toString().toUtf8());QVERIFY(!certificates.isEmpty());QVERIFY(QSslSocket::supportsSsl());
  QTemporaryDir directory;QVERIFY(directory.isValid());const auto path=directory.filePath("lifecycle.dpapi");
  QTcpServer reservation;reservation.setProxy(QNetworkProxy::NoProxy);QVERIFY(reservation.listen(QHostAddress::LocalHost));const auto proxyPort=reservation.serverPort();reservation.close();
  QString idA,idB;QList<ProxyNode> savedNodes;QJsonObject savedNetwork;
  {
   EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);controller.setProxyPort(proxyPort);controller.setRoutingMode("global");
   controller.imports()->importText(fixture["subscription"].toString());QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);
   QVERIFY(controller.networkConfigurationError().isEmpty());QCOMPARE(controller.nodeCatalog().size(),2);
   for(const auto &entry:controller.nodeCatalog()){const auto row=entry.toMap();if(row["name"]=="A")idA=row["id"].toString();if(row["name"]=="B")idB=row["id"].toString();}
   QVERIFY(!idA.isEmpty()&&!idB.isEmpty()&&idA!=idB);QVERIFY(controller.chooseNode(idA));
   if(mode=="reject"){
    // These application-owned exact hosts are persisted in the isolated store.
    // Both names reach the very same listening origin in the DIRECT control.
    const QVariantList hosts{QVariantMap{{"name","denied.product.invalid"},{"value","127.0.0.1"}},QVariantMap{{"name","unmatched.product.invalid"},{"value","127.0.0.1"}}};
    QVERIFY(controller.configureDns(QVariantMap{{"mode",0},{"hosts",hosts},{"useHosts",true}}));
   }
   // NodeStore persists JSON. Optional host metadata changes from an invalid
   // QVariant to JSON null on reload; compare every persisted field in that
   // same representation, as the existing controlled product slot does.
   savedNetwork=QJsonObject::fromVariantMap(controller.networkConfigurationSnapshot());NodeStore persisted(path);QVERIFY(persisted.error().isEmpty()&&persisted.selectedId()==idA);savedNodes=persisted.nodes();QCOMPARE(savedNodes.size(),2);
   QFile encrypted(path);QVERIFY(encrypted.open(QIODevice::ReadOnly));auto bytes=encrypted.readAll();QVERIFY(bytes.startsWith("SWIRLNODE1\n")&&bytes.size()>11);
   QVERIFY(!bytes.contains(fixture["subscription"].toString().toUtf8()));
   for(const auto &node:savedNodes){const auto reality=node.parameters["reality-opts"].toObject();for(const auto &credential:QStringList{node.parameters["uuid"].toString(),reality["public-key"].toString(),reality["short-id"].toString()}){QVERIFY(!credential.isEmpty()&&!bytes.contains(credential.toUtf8()));}}
   bytes.fill('\0');report["imported"]=true;
  }
  // Speak to the real Rust listener explicitly: Qt's implicit loopback proxy
  // bypass cannot turn a DIRECT or REJECT control into an unrelated local test.
  const auto tunnel=[&](QSslSocket &socket,QNetworkProxy::ProxyType frontend,const QString &host,QJsonObject &check){
   check["stage"]="proxy-connect";socket.setProxy(QNetworkProxy::NoProxy);socket.connectToHost(QHostAddress::LocalHost,proxyPort);
   if(!QTest::qWaitFor([&]{return socket.state()==QAbstractSocket::ConnectedState||socket.state()==QAbstractSocket::UnconnectedState;},5000)||socket.state()!=QAbstractSocket::ConnectedState)return false;
   check["stage"]="proxy-reply";QByteArray response,success,failure;
   if(frontend==QNetworkProxy::HttpProxy){
    const auto authority=host.toUtf8()+':'+QByteArray::number(targetPort);const auto request="CONNECT "+authority+" HTTP/1.1\r\nHost: "+authority+"\r\n\r\n";
    if(socket.write(request)!=request.size())return false;
    if(!QTest::qWaitFor([&]{response+=socket.readAll();return response.contains("\r\n\r\n")||response.size()>65536||socket.state()==QAbstractSocket::UnconnectedState;},5000))return false;
    success="HTTP/1.1 200 Connection Established\r\n\r\n";failure="HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    check["proxy_status"]=response==success?200:response==failure?502:0;
   }else{
    const auto greeting=QByteArray::fromHex("050100");if(socket.write(greeting)!=greeting.size())return false;
    if(!QTest::qWaitFor([&]{response+=socket.readAll();return response.size()>=2||socket.state()==QAbstractSocket::UnconnectedState;},5000)||response!=QByteArray::fromHex("0500"))return false;
    auto request=QByteArray::fromHex("05010003");request.append(char(host.toUtf8().size()));request+=host.toUtf8();request.append(char(targetPort>>8));request.append(char(targetPort&255));response.clear();
    if(socket.write(request)!=request.size())return false;
    if(!QTest::qWaitFor([&]{response+=socket.readAll();return response.size()>=10||socket.state()==QAbstractSocket::UnconnectedState;},5000))return false;
    success=QByteArray::fromHex("05000001000000000000");failure=QByteArray::fromHex("05050001000000000000");check["proxy_status"]=response==success?0:response==failure?5:-1;
   }
   check["frontend_response_valid"]=response==success||response==failure;check["tunnel_accepted"]=response==success;return response==success;
  };
  const auto http=[&](QSslSocket &socket,const QString &host,const QString &target,QJsonObject &check){
   check["stage"]="http-write";const auto message="GET "+target.toUtf8()+" HTTP/1.1\r\nHost: "+host.toUtf8()+':'+QByteArray::number(targetPort)+"\r\nConnection: close\r\n\r\n";
   if(socket.write(message)!=message.size())return false;
   const auto body=expected+':'+target.toUtf8();QByteArray response;qsizetype separator=-1;check["stage"]="http-response";
   if(!QTest::qWaitFor([&]{response+=socket.readAll();separator=response.indexOf("\r\n\r\n");return response.size()>65536||(separator>=0&&response.size()>=separator+4+body.size())||socket.state()==QAbstractSocket::UnconnectedState;},5000))return false;
   check["http_status"]=response.startsWith("HTTP/1.1 200 ")?200:0;
   const bool valid=separator>=0&&response.size()<=65536&&check["http_status"].toInt()==200&&response.left(separator+2).contains("\r\nContent-Length: "+QByteArray::number(body.size())+"\r\n")&&response.mid(separator+4)==body;
   check["expected_body_verified"]=valid;if(!valid)return false;
   check["stage"]="close";socket.disconnectFromHost();if(!QTest::qWaitFor([&]{return socket.state()==QAbstractSocket::UnconnectedState;},5000))return false;
   response+=socket.readAll();return response.mid(separator+4)==body;
  };
  for(const auto frontend:{QNetworkProxy::HttpProxy,QNetworkProxy::Socks5Proxy}){
   const auto frontendName=frontend==QNetworkProxy::HttpProxy?QString("http-connect"):QString("socks5");
   EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);controller.setProxyPort(proxyPort);controller.setRoutingMode(mode=="reject"?"direct":"global");QCOMPARE(controller.metaObject()->indexOfProperty("executablePath"),-1);
   QVERIFY(controller.selectedNodeId()==idA);
   QVERIFY(QJsonObject::fromVariantMap(controller.networkConfigurationSnapshot())==savedNetwork);
   NodeStore restored(path);QVERIFY(restored.error().isEmpty()&&restored.nodes().size()==savedNodes.size());report["encrypted_store_reloaded"]=true;
   for(qsizetype i=0;i<savedNodes.size();++i){const auto node=restored.nodes()[i];QVERIFY(node.parameters==savedNodes[i].parameters&&node.originalConfiguration==savedNodes[i].originalConfiguration);}
   report["parameters_preserved"]=true;controller.connectNode({});QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);
   const auto nativeIdentity=[&]{return controller.engineKind()=="rust"&&controller.processId()==QString::number(QCoreApplication::applicationPid())&&controller.controlEndpoint().startsWith("in-process://SwirlRust/")&&controller.activeProxyPort()==proxyPort;};
   QVERIFY(nativeIdentity());report["in_process_rust"]=true;
   const QStringList phases=mode=="reject"?QStringList{"direct-control","reject"}:QStringList{mode};
   for(const auto &phase:phases){
    if(phase=="reject"){controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.busy(),5000);controller.setRoutingMode("rule");controller.connectNode({});QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);QVERIFY(nativeIdentity());}
    const QStringList hosts=mode=="reject"?QStringList{"denied.product.invalid","unmatched.product.invalid"}:QStringList{mode=="tls12"?"tls.product.invalid":mode=="cancel"?"stream.product.invalid":"a.product.invalid"};
    for(const auto &host:hosts){
     QSslSocket socket;QElapsedTimer elapsed;elapsed.start();
     QJsonObject check{{"frontend",frontendName},{"node","A"},{"phase",phase},{"target",host},{"target_port",targetPort},{"proxy_host","127.0.0.1"},{"proxy_port",proxyPort},
      {"stage","start"},{"frontend_response_valid",false},{"tunnel_accepted",false},{"expected_result_observed",false},{"closed",false},{"socket_error",-1},{"tls_error_count",0}};
     QObject::connect(&socket,&QSslSocket::errorOccurred,&socket,[&](QAbstractSocket::SocketError error){check["socket_error"]=int(error);});
     QObject::connect(&socket,&QSslSocket::sslErrors,&socket,[&](const QList<QSslError> &errors){check["tls_error_count"]=errors.size();});
     const auto checkGuard=qScopeGuard([&]{check["elapsed_ms"]=elapsed.elapsed();check["closed"]=socket.state()==QAbstractSocket::UnconnectedState;auto checks=report["checks"].toArray();checks.append(check);report["checks"]=checks;saveReport();QObject::disconnect(&socket,nullptr,&socket,nullptr);socket.abort();});
     const bool accepted=tunnel(socket,frontend,host,check);
     if(phase=="reject"){
      QVERIFY(!accepted&&check["frontend_response_valid"].toBool());QVERIFY(QTest::qWaitFor([&]{return socket.state()==QAbstractSocket::UnconnectedState;},5000));
     }else if(mode=="authentication-failure"){
      QVERIFY(check["frontend_response_valid"].toBool());check["stage"]="authentication-failure";
      // VLESS checks its response on first application read, so a bad UUID may
      // follow a successful local CONNECT. A proxy ACK is not HTTP success.
      QByteArray received;if(accepted&&socket.state()==QAbstractSocket::ConnectedState){const QByteArray request="GET /authentication-must-not-arrive HTTP/1.1\r\nHost: a.product.invalid\r\nConnection: close\r\n\r\n";QCOMPARE(socket.write(request),request.size());}
      QVERIFY(QTest::qWaitFor([&]{received+=socket.readAll();return socket.state()==QAbstractSocket::UnconnectedState||received.size()>65536;},5000));QVERIFY(received.isEmpty());
     }else{
      QVERIFY(accepted);
      if(mode=="cancel"){
       check["stage"]="authenticated-echo";const QByteArray payload="qt-authenticated-stream-before-cancellation";const auto length=quint32(payload.size()+1);QByteArray prefix(4,'\0');for(int i=0;i<4;++i)prefix[i]=char((length>>(8*(3-i)))&255u);
       QCOMPARE(socket.write(prefix+payload),prefix.size()+payload.size());QByteArray echoed;QVERIFY(QTest::qWaitFor([&]{echoed+=socket.readAll();return echoed.size()>=payload.size()||socket.state()==QAbstractSocket::UnconnectedState;},5000));QCOMPARE(echoed,payload);
       check["echo_verified"]=true;check["echo_bytes"]=payload.size();check["stage"]="runtime-cancel";controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.busy(),5000);
       QVERIFY(QTest::qWaitFor([&]{return socket.state()==QAbstractSocket::UnconnectedState;},5000));check["cancelled_after_echo"]=true;
      }else{
       if(mode=="tls12"){
        check["stage"]="tls-handshake";auto tls=QSslConfiguration::defaultConfiguration();tls.setCaCertificates(certificates);tls.setPeerVerifyMode(QSslSocket::VerifyPeer);tls.setProtocol(QSsl::TlsV1_2);socket.setSslConfiguration(tls);socket.setPeerVerifyName("localhost");socket.startClientEncryption();
        QVERIFY(QTest::qWaitFor([&]{return socket.isEncrypted()||socket.state()==QAbstractSocket::UnconnectedState;},5000));
        const bool verified=socket.isEncrypted()&&!socket.peerCertificate().isNull()&&socket.sslHandshakeErrors().isEmpty()&&socket.sessionProtocol()==QSsl::TlsV1_2;
        check["certificate_verified"]=verified;check["tls_version"]=socket.sessionProtocol()==QSsl::TlsV1_2?"TLSv1.2":"unsupported";QVERIFY(verified);
       }
       const auto target="/qt-"+phase+'-'+frontendName+(mode=="reject"?(host.startsWith("denied")?"-domain":"-match"):"");QVERIFY(http(socket,host,target,check));
      }
     }
     check["stage"]="complete";check["expected_result_observed"]=true;
    }
   }
   controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.busy(),5000);QVERIFY(controller.selectedNodeId()==idA);report["stopped"]=true;
   QTcpServer released;released.setProxy(QNetworkProxy::NoProxy);QVERIFY(released.listen(QHostAddress::LocalHost,proxyPort));report["listener_released"]=true;
  }
  QCOMPARE(report["checks"].toArray().size(),mode=="reject"?8:2);QVERIFY(saveReport());
 }
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
 void unsupportedClientGlobalConfigurationDoesNotAlterNativeState(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  controller.imports()->importText("proxies: [{name: retained, type: socks5, server: 127.0.0.1, port: 1080}]");QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),4000);QCOMPARE(controller.nodeCatalog().size(),1);
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto before=file.readAll();file.close();const auto nodes=controller.nodeCatalog();const auto network=controller.networkConfigurationSnapshot();
  for(const auto &body:{QByteArray("[Proxy]\nA = socks5, 127.0.0.1, 1081\n[Rule]\nFINAL,A\n[Future]\nfixture-secret\n"),QByteArray(R"({"outbounds":[{"type":"socks","tag":"A","server":"127.0.0.1","server_port":1081},{"type":"selector","tag":"choice","outbounds":["A"]}],"route":{"final":"choice"},"inbounds":[{"type":"mixed","listen":"0.0.0.0","listen_port":7890}]})")}){
   controller.imports()->importText(QString::fromUtf8(body));QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),4000);QCOMPARE(controller.nodeCatalog(),nodes);QCOMPARE(controller.networkConfigurationSnapshot(),network);
   QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),before);file.close();QVERIFY(!controller.imports()->message().contains("fixture-secret"));QVERIFY(!controller.processAlive());
  }
 }
 void automaticSubscriptionKeepsValidNodesAndRejectsLateSafetyErrors(){
  QTemporaryDir directory;const auto path=directory.filePath("automatic.dpapi");
  ControlledNetwork net;QVERIFY(net.start());QTcpServer source;QVERIFY(source.listen(QHostAddress::LocalHost));
  const auto node=QJsonObject{{"name","A"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.a.serverPort()}};
  QByteArray body=QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}}}).toJson();
  connect(&source,&QTcpServer::newConnection,this,[&]{while(source.hasPendingConnections()){
   auto *socket=source.nextPendingConnection();connect(socket,&QTcpSocket::readyRead,socket,[&,socket]{
    socket->readAll();if(socket->property("done").toBool())return;socket->setProperty("done",true);
    socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(body.size())+"\r\nConnection: close\r\n\r\n"+body);socket->disconnectFromHost();
   });connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
  }});
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);
  QVERIFY(controller.replaceNetworkConfiguration({{"rules",QStringList{"MATCH,REJECT"}},{"groups",QVariantList{}}}));
  const auto original=controller.networkConfigurationSnapshot();auto *imports=controller.imports();
  // Neither the provider's name, URL nor old persisted mode may override content.
  QVERIFY(imports->saveSubscription({},"Surge named provider",QUrl(QString("http://127.0.0.1:%1/loon.conf").arg(source.serverPort())),360,false,"loon","full-profile"));
  const auto sourceId=imports->providers().first().toMap().value("id").toString();
  imports->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);
  QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.networkConfigurationSnapshot(),original);
  QCOMPARE(imports->providers().first().toMap().value("importMode").toString(),QString("nodes"));
  const auto id=controller.nodeCatalog().first().toMap().value("id").toString();
  body=QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}},
   {"proxy-groups",QJsonArray{QJsonObject{{"name","route"},{"type","relay"},{"proxies",QJsonArray{"A"}}}}},
   {"rules",QJsonArray{"MATCH,route"}}}).toJson();
  imports->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);
  QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);
  QCOMPARE(controller.networkConfigurationSnapshot(),original);
  const auto outcome=imports->providers().first().toMap();
  QVERIFY2(!outcome.value("status").toString().contains(QStringLiteral("失败")),qPrintable(imports->message()));
  QCOMPARE(outcome.value("importMode").toString(),QString("nodes-with-warning"));
  QVERIFY2(outcome.value("warning").toString().contains("ProfileGroupUnsupported"),qPrintable(imports->message()));
  EngineController reloaded(std::make_unique<RustCoreEngine>(),nullptr,path,true);
  QCOMPARE(reloaded.imports()->providers().first().toMap().value("warning"),outcome.value("warning"));
  // Portable structural projection can pass while native execution rejects a
  // non-equivalent default strategy. This remains a recoverable pre-commit
  // configuration problem only after the independent whole-document audit.
  body=QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}},
   {"proxy-groups",QJsonArray{QJsonObject{{"name","route"},{"type","load-balance"},{"proxies",QJsonArray{"A"}}}}},
   {"rules",QJsonArray{"MATCH,route"}}}).toJson();
  imports->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);
  const auto nativeOutcome=imports->providers().first().toMap();
  QVERIFY2(!nativeOutcome.value("status").toString().contains(QStringLiteral("失败")),qPrintable(imports->message()));
  QCOMPARE(nativeOutcome.value("importMode").toString(),QString("nodes-with-warning"));
  QVERIFY(nativeOutcome.value("warning").toString().contains("ProfileNativeValidationUnsupported"));
  QCOMPARE(controller.networkConfigurationSnapshot(),original);
  QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);
  QFile saved(path);QVERIFY(saved.open(QIODevice::ReadOnly));const auto retained=saved.readAll();saved.close();
  QVERIFY(!retained.contains("ProfileGroupUnsupported"));
  // A recoverable first problem must never hide a dangerous later section.
  body=QString("[General]\nloglevel=notify\n[Proxy]\nA=socks5,127.0.0.1,%1\n[Proxy Group]\nroute=url-test,A,url=https://example.invalid/check\n[Rule]\nFINAL,route\n[Script]\nrequest=https://private.invalid/SYNTHETIC-SCRIPT-SECRET\n").arg(net.a.serverPort()).toUtf8();
  imports->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);
  QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
  QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);QCOMPARE(controller.networkConfigurationSnapshot(),original);
  QVERIFY(saved.open(QIODevice::ReadOnly));QCOMPARE(saved.readAll(),retained);
  QVERIFY(!imports->message().contains("SYNTHETIC-SCRIPT-SECRET"));
 }
 void automaticManagedIniAppliesActualRoutingAndKeepsSwirlUpdateSource_data(){
  QTest::addColumn<bool>("quantumult");QTest::newRow("managed-ini")<<false;QTest::newRow("quantumult-x")<<true;
 }
 void automaticManagedIniAppliesActualRoutingAndKeepsSwirlUpdateSource(){
  QFETCH(bool,quantumult);
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;const auto path=directory.filePath("managed.dpapi");
  const QByteArray document=(quantumult?
   QString("[general]\nserver_check_url=https://example.invalid/check\n[dns]\nno-ipv6\nno-system\nserver=192.0.2.53\n[policy]\nstatic=route,A\n[server_local]\nsocks5=127.0.0.1:%1,tag=A\n[filter_local]\nfinal,route\n"):
   QString("#!MANAGED-CONFIG https://example.invalid/SYNTHETIC-MANAGED-TOKEN interval=86400 strict=false\n[General]\nloglevel=notify\ndns-server=192.0.2.53\nipv6=false\n[Proxy]\nA=socks5,127.0.0.1,%1\n[Proxy Group]\nroute=select,A\n[Rule]\nFINAL,route\n")).arg(net.a.serverPort()).toUtf8();
  QTcpServer source;QVERIFY(source.listen(QHostAddress::LocalHost));
  connect(&source,&QTcpServer::newConnection,this,[&]{while(source.hasPendingConnections()){
   auto *socket=source.nextPendingConnection();connect(socket,&QTcpSocket::readyRead,socket,[&,socket]{
    socket->readAll();if(socket->property("done").toBool())return;socket->setProperty("done",true);
    socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(document.size())+"\r\nConnection: close\r\n\r\n"+document);socket->disconnectFromHost();
   });connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
  }});
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);
  QTcpServer lease;QVERIFY(lease.listen(QHostAddress::LocalHost));const auto port=lease.serverPort();lease.close();controller.setProxyPort(port);controller.setRoutingMode("rule");
  const auto url=QUrl(QString("http://127.0.0.1:%1/clash.yaml").arg(source.serverPort()));auto *imports=controller.imports();
  QVERIFY(imports->saveSubscription({},"Clash named provider",url,360,false,"auto","nodes-only"));
  const auto sourceId=imports->providers().first().toMap().value("id").toString();
  imports->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);
  QVERIFY2(imports->providers().first().toMap().value("importMode").toString()=="full",qPrintable(imports->message()));
  QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.policyGroups().size(),1);
  QCOMPARE(controller.dnsConfiguration().value("servers").toString(),QString("192.0.2.53"));
  NodeStore stored(path);QCOMPARE(stored.subscriptions().first().url,url);QCOMPARE(stored.subscriptions().first().intervalMinutes,360);
  const auto metadata=stored.networkConfiguration()["importedConfiguration"].toObject()["metadata"].toObject()["managedConfig"].toObject();
  if(!quantumult){QCOMPARE(metadata["embeddedUrlPreserved"],QJsonValue(true));QCOMPARE(metadata["embeddedUrlApplied"],QJsonValue(false));}
  QVERIFY(imports->providers().first().toMap().value("warning").toString().contains(QStringLiteral("Swirl")));
  controller.connectNode(controller.nodeCatalog().first().toMap().value("id").toString());QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",port));
  QNetworkRequest request(net.url());request.setTransferTimeout(4000);auto *reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-A"));QCOMPARE(net.a.forwarded,1);reply->deleteLater();controller.stop();
  QVERIFY(!imports->message().contains("SYNTHETIC-MANAGED-TOKEN"));
 }
 void manualNodesOnlyImportDoesNotInventPolicyMetadata(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  controller.imports()->importNodesOnlyText("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]\nmode: direct\n");
  QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),4000);
  QCOMPARE(controller.nodeCatalog().size(),1);
  NodeStore stored(path);QCOMPARE(stored.nodes().size(),1);
  QVERIFY(stored.networkConfiguration().isEmpty());
 }
  void nodesOnlySubscriptionPreservesLocalPolicyAndRejectsDanglingRefresh(){
   QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");QTcpServer subscription;QVERIFY(subscription.listen(QHostAddress::LocalHost));
   QJsonObject proxy{{"name","A"},{"type","socks5"},{"server","127.0.0.1"},{"port",1080}};
   auto document=[&]{return QJsonDocument(QJsonObject{{"proxies",QJsonArray{proxy}},{"mode","direct"},{"rules",QJsonArray{"MATCH,DIRECT"}}}).toJson();};
   QByteArray body=document();int downloads=0;
   connect(&subscription,&QTcpServer::newConnection,this,[&]{while(subscription.hasPendingConnections()){
    auto *socket=subscription.nextPendingConnection();connect(socket,&QTcpSocket::readyRead,socket,[&,socket]{socket->readAll();if(socket->property("done").toBool())return;socket->setProperty("done",true);++downloads;
     socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(body.size())+"\r\nConnection: close\r\n\r\n"+body);socket->disconnectFromHost();});connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
   }});
   const auto url=QUrl(QString("http://127.0.0.1:%1/sub").arg(subscription.serverPort()));
   {NodeStore seed(path);QVERIFY(seed.saveSubscription({},"nodes only",url,360,false,"auto","nodes-only"));}
   NodeStore reloaded(path);QCOMPARE(reloaded.subscriptions().first().importScope,QString("nodes-only"));
   EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);const auto network=controller.networkConfigurationSnapshot();auto *imports=controller.imports();
   const auto source=imports->providers().first().toMap().value("id").toString();imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);
   QCOMPARE(downloads,1);QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.networkConfigurationSnapshot(),network);
   QVERIFY(imports->message().contains(QStringLiteral("已自动提取节点")));
   QCOMPARE(imports->providers().first().toMap().value("importMode").toString(),QString("nodes-with-warning"));
   QVERIFY(imports->providers().first().toMap().value("warning").toString().contains("ProfileGlobalFieldUnsupported"));
   const auto id=controller.nodeCatalog().first().toMap().value("id").toString();
   const QVariantMap policy{{"groups",QVariantList{QVariantMap{{"name","route"},{"type","select"},{"proxies",QStringList{id}}}}},{"rules",QStringList{"MATCH,route"}}};
   QVERIFY2(controller.replaceNetworkConfiguration(policy),qPrintable(controller.networkConfigurationError()));const auto retained=controller.networkConfigurationSnapshot();
   // U1 preserves identity across a display-name-only refresh. Verify that
   // stronger contract before constructing a genuinely dangling policy.
   proxy["name"]="B";body=document();
   imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(downloads,2);
   QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);
   QCOMPARE(controller.nodeCatalog().first().toMap().value("name").toString(),QString("B"));
   QCOMPARE(controller.networkConfigurationSnapshot(),retained);QVERIFY(!imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
   NodeStore before(path);const auto success=before.subscriptions().first().lastSuccess;
   QFile saved(path);QVERIFY(saved.open(QIODevice::ReadOnly));const auto ciphertext=saved.readAll();saved.close();
   proxy["name"]="C";proxy["port"]=1082;body=document();
   imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(downloads,3);
   QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);
   QCOMPARE(controller.networkConfigurationSnapshot(),retained);QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
   NodeStore after(path);QCOMPARE(after.subscriptions().first().lastSuccess,success);QCOMPARE(after.nodes().first().id,id);
   QCOMPARE(after.nodes().first().name,QString("B"));QCOMPARE(after.nodes().first().port,quint16(1080));
   QVERIFY(saved.open(QIODevice::ReadOnly));QCOMPARE(saved.readAll(),ciphertext);
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
  // A busy full-profile apply is not a compatibility failure. It cannot fall
  // through to a second nodes-only save or alter the running immutable session.
  QFile saved(path);QVERIFY(saved.open(QIODevice::ReadOnly));const auto runningCiphertext=saved.readAll();saved.close();
  imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QVERIFY(controller.apiHealthy());QCOMPARE(controller.policyGroups(),group);QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
  QVERIFY(saved.open(QIODevice::ReadOnly));QCOMPARE(saved.readAll(),runningCiphertext);saved.close();
  body=QJsonDocument(QJsonObject{{"proxies",QJsonArray{proxies.first()}}}).toJson();imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QVERIFY(controller.apiHealthy());QCOMPARE(controller.nodeCatalog().size(),2);QCOMPARE(controller.policyGroups(),group);
  {NodeStore unchanged(path);QCOMPARE(unchanged.nodes().size(),2);for(const auto &node:unchanged.nodes())QCOMPARE(node.sourceId,source);}
  QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
  QVERIFY(saved.open(QIODevice::ReadOnly));QCOMPARE(saved.readAll(),runningCiphertext);saved.close();
  controller.disconnectNode();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
  const auto network=controller.networkConfigurationSnapshot();const auto nodes=controller.nodeCatalog();
  for(const auto &mutation:QList<QJsonObject>{QJsonObject{{"future-global",true}},QJsonObject{{"script",QJsonObject{{"code","SYNTHETIC-PRIVATE"}}}},QJsonObject{{"mixed-port",7890}},QJsonObject{{"dns",QJsonObject{{"enable",true},{"nameserver",QJsonArray{"file:///SYNTHETIC-PRIVATE"}}}}}}) {
   QVERIFY(saved.open(QIODevice::ReadOnly));const auto ciphertext=saved.readAll();saved.close();NodeStore before(path);const auto lastSuccess=before.subscriptions().first().lastSuccess;
   auto invalid=document;for(auto it=mutation.begin();it!=mutation.end();++it)invalid[it.key()]=it.value();body=QJsonDocument(invalid).toJson();imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);
   QCOMPARE(controller.networkConfigurationSnapshot(),network);QCOMPARE(controller.nodeCatalog(),nodes);QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
   QVERIFY(!imports->message().contains("SYNTHETIC-PRIVATE"));QVERIFY(saved.open(QIODevice::ReadOnly));QCOMPARE(saved.readAll(),ciphertext);saved.close();
   NodeStore after(path);QCOMPARE(after.subscriptions().first().lastSuccess,lastSuccess);
  }
  for(const auto &mutation:QList<QJsonObject>{QJsonObject{{"dns",QJsonObject{{"respect-rules",true}}}},QJsonObject{{"rules",QJsonArray{false}}},QJsonObject{{"proxy-groups","not-an-array"}},QJsonObject{{"rules",QJsonArray{"PROCESS-NAME,fixture.exe,route","MATCH,route"}}},QJsonObject{{"rules",QJsonArray{"DOMAIN,example.invalid,route"}}}}) {
   auto unsupported=document;for(auto it=mutation.begin();it!=mutation.end();++it)unsupported[it.key()]=it.value();body=QJsonDocument(unsupported).toJson();imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);
   QCOMPARE(controller.networkConfigurationSnapshot(),network);QCOMPARE(controller.nodeCatalog(),nodes);const auto outcome=imports->providers().first().toMap();
   QVERIFY2(!outcome.value("status").toString().contains(QStringLiteral("失败")),qPrintable(imports->message()));QCOMPARE(outcome.value("importMode").toString(),QString("nodes-with-warning"));QVERIFY(!outcome.value("warning").toString().isEmpty());
   NodeStore retained(path);for(const auto &node:retained.nodes())QCOMPARE(node.sourceId,source);
   QCOMPARE(retained.networkConfiguration()["subscriptionImportResults"].toObject()[source].toObject()["notice"].toString(),outcome.value("warning").toString());
  }
  body=QJsonDocument(document).toJson();imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);QCOMPARE(controller.policyGroups(),group);
  EngineController reopened(std::make_unique<RustCoreEngine>(),nullptr,path,true);reopened.setProxyPort(proxyPort);reopened.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(reopened.apiHealthy(),4000);
  reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->readAll(),QByteArray("exit-B"));reply->deleteLater();reopened.stop();QTRY_VERIFY_WITH_TIMEOUT(!reopened.processAlive(),4000);
  NodeStore persisted(path);QCOMPARE(persisted.networkConfiguration()["nativeDocumentRouting"],QJsonValue(true));
  QVERIFY(imports->saveSubscription(source,"fixture",{},360,false,"auto","nodes-only"));
  auto nodesOnly=document;nodesOnly["dns"]=QJsonObject{{"respect-rules",true}};body=QJsonDocument(nodesOnly).toJson();
  const auto retainedRules=controller.networkConfigurationSnapshot().value("rules");
  imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);
  QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);
  QCOMPARE(controller.policyGroups(),group);QCOMPARE(controller.networkConfigurationSnapshot().value("rules"),retainedRules);
  QVERIFY(!imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
  QCOMPARE(imports->providers().first().toMap().value("importMode").toString(),QString("nodes-with-warning"));
  NodeStore retained(path);QVERIFY(retained.networkConfiguration()["importedConfiguration"].toObject()["policyRetainedAfterNodesOnlyRefresh"].toBool());
 }
 void fullProfilesKeepDnsPolicyAndOriginsAtomic_data(){
  QTest::addColumn<bool>("singbox");QTest::newRow("clash-dns-hosts")<<false;QTest::newRow("singbox-selector-route-dns")<<true;
 }
 void fullProfilesKeepDnsPolicyAndOriginsAtomic(){
  QFETCH(bool,singbox);ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;QVERIFY(directory.isValid());const auto path=directory.filePath("profile.dpapi");
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);QTcpServer port;QVERIFY(port.listen(QHostAddress::LocalHost));const auto proxyPort=port.serverPort();port.close();controller.setProxyPort(proxyPort);controller.setRoutingMode("rule");
  QJsonObject profile;
  if(singbox){
   const QJsonArray outbounds{QJsonObject{{"tag","A"},{"type","socks"},{"server","127.0.0.1"},{"server_port",net.a.serverPort()}},QJsonObject{{"tag","B"},{"type","socks"},{"server","127.0.0.1"},{"server_port",net.b.serverPort()},{"username",QString::fromUtf8(net.b.username)},{"password",QString::fromUtf8(net.b.password)}},QJsonObject{{"tag","deny"},{"type","block"}},QJsonObject{{"tag","route"},{"type","selector"},{"outbounds",QJsonArray{"B","A"}},{"default","B"}}};
   profile={{"outbounds",outbounds},{"route",QJsonObject{{"rules",QJsonArray{QJsonObject{{"domain",QJsonArray{"profile-target.invalid"}},{"outbound","deny"}}}},{"final","route"}}},{"dns",QJsonObject{{"servers",QJsonArray{QJsonObject{{"type","udp"},{"tag","resolver"},{"server","192.0.2.53"}}}},{"final","resolver"},{"strategy","ipv4_only"}}}};
  }else{
   const QJsonArray proxies{QJsonObject{{"name","A"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.a.serverPort()}},QJsonObject{{"name","B"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.b.serverPort()},{"username",QString::fromUtf8(net.b.username)},{"password",QString::fromUtf8(net.b.password)}}};
   profile={{"proxies",proxies},{"proxy-groups",QJsonArray{QJsonObject{{"name","route"},{"type","select"},{"proxies",QJsonArray{"B","A"}}}}},{"rules",QJsonArray{"DOMAIN,profile-target.invalid,DIRECT","MATCH,route"}},{"hosts",QJsonObject{{"profile-target.invalid","127.0.0.1"}}},{"dns",QJsonObject{{"enable",true},{"nameserver",QJsonArray{"192.0.2.53"}},{"ipv6",false},{"use-hosts",true}}}};
  }
  QByteArray body=QJsonDocument(profile).toJson();QTcpServer subscription;QVERIFY(subscription.listen(QHostAddress::LocalHost));
  connect(&subscription,&QTcpServer::newConnection,this,[&]{while(subscription.hasPendingConnections()){
   auto *socket=subscription.nextPendingConnection();connect(socket,&QTcpSocket::readyRead,socket,[&,socket]{socket->readAll();if(socket->property("done").toBool())return;socket->setProperty("done",true);socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(body.size())+"\r\nConnection: close\r\n\r\n"+body);socket->disconnectFromHost();});connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
  }});
  auto *imports=controller.imports();QVERIFY(imports->saveSubscription({},"Profile fixture",QUrl(QString("http://127.0.0.1:%1/sub").arg(subscription.serverPort())),360,false,"auto","full-profile"));const auto source=imports->providers().first().toMap().value("id").toString();
  imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);QCOMPARE(controller.nodeCatalog().size(),2);QVERIFY2(!imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")),qPrintable(imports->message()));
  const auto snapshot=controller.networkConfigurationSnapshot();const auto dns=snapshot.value("dns").toMap();QCOMPARE(dns.value("servers").toString(),QString("192.0.2.53"));QCOMPARE(dns.value("queryFamily").toString(),QString("ipv4_only"));
  QCOMPARE(controller.policyGroups().size(),1);NodeStore disk(path);QCOMPARE(disk.nodes().size(),2);for(const auto &node:disk.nodes())QCOMPARE(node.sourceId,source);
  QCOMPARE(disk.networkConfiguration().value("dns").toObject().value("queryFamily").toString(),QString("ipv4_only"));QCOMPARE(disk.networkConfiguration().value("importedConfiguration").toObject().value("configuration").toObject(),NodeImporter::parse(QJsonDocument(profile).toJson()).configuration);
  const auto id=controller.nodeCatalog().first().toMap().value("id").toString();controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",proxyPort));QNetworkRequest request(net.url());request.setTransferTimeout(4000);auto *reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-B"));reply->deleteLater();QCOMPARE(net.a.forwarded,0);QCOMPARE(net.b.forwarded,1);
  auto named=net.url();named.setHost("profile-target.invalid");QNetworkRequest namedRequest(named);namedRequest.setTransferTimeout(4000);reply=client.get(namedRequest);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);
  if(singbox){QVERIFY(reply->error()!=QNetworkReply::NoError);QCOMPARE(net.httpRequests,1);}else{QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.httpRequests,2);}reply->deleteLater();
  controller.disconnectNode();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),5000);const auto nodes=controller.nodeCatalog();QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto ciphertext=file.readAll();file.close();
  auto bad=profile;if(singbox){auto route=bad.value("route").toObject();route["rule_set"]=QJsonArray{};bad["route"]=route;}else{auto settings=bad.value("dns").toObject();settings["PRIVATE_TOKEN"]=QStringLiteral("PRIVATE_VALUE");bad["dns"]=settings;}
  body=QJsonDocument(bad).toJson();imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);QCOMPARE(controller.nodeCatalog(),nodes);QCOMPARE(controller.networkConfigurationSnapshot(),snapshot);QVERIFY(!imports->message().contains("PRIVATE"));
  if(singbox) {
   const auto outcome=imports->providers().first().toMap();QVERIFY2(!outcome.value("status").toString().contains(QStringLiteral("失败")),qPrintable(imports->message()));
   QCOMPARE(outcome.value("importMode").toString(),QString("nodes-with-warning"));QVERIFY(outcome.value("warning").toString().contains("ProfileRouteFieldUnsupported"));
   NodeStore retained(path);for(const auto &node:retained.nodes())QCOMPARE(node.sourceId,source);
   QCOMPARE(retained.networkConfiguration()["subscriptionImportResults"].toObject()[source].toObject()["notice"].toString(),outcome.value("warning").toString());
   QCOMPARE(retained.networkConfiguration()["importedConfiguration"].toObject()["configuration"].toObject(),disk.networkConfiguration()["importedConfiguration"].toObject()["configuration"].toObject());
  } else {
   QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
   QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),ciphertext);file.close();
  }
  // A dangerous request still rejects the whole update after a recoverable
  // configuration, without changing the ciphertext or last successful update.
  QVERIFY(file.open(QIODevice::ReadOnly));const auto beforeDanger=file.readAll();file.close();NodeStore beforeDangerStore(path);const auto lastSuccess=beforeDangerStore.subscriptions().first().lastSuccess;
  auto dangerous=bad;dangerous["script"]=QJsonObject{{"code","SYNTHETIC-PRIVATE"}};body=QJsonDocument(dangerous).toJson();imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);
  QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));QVERIFY(!imports->message().contains("SYNTHETIC-PRIVATE"));QCOMPARE(controller.nodeCatalog(),nodes);QCOMPARE(controller.networkConfigurationSnapshot(),snapshot);
  QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),beforeDanger);file.close();QCOMPARE(NodeStore(path).subscriptions().first().lastSuccess,lastSuccess);
  EngineController reopened(std::make_unique<RustCoreEngine>(),nullptr,path,true);QCOMPARE(QJsonObject::fromVariantMap(reopened.networkConfigurationSnapshot()),QJsonObject::fromVariantMap(snapshot));
  NodeStore restored(path);const auto archivedNodes=disk.nodes();QCOMPARE(restored.selectedId(),id);QCOMPARE(restored.nodes().size(),archivedNodes.size());for(const auto &node:restored.nodes()){QCOMPARE(node.sourceId,source);QVERIFY(std::any_of(archivedNodes.cbegin(),archivedNodes.cend(),[&](const ProxyNode &before){return before.id==node.id&&before.name==node.name&&before.host==node.host&&before.port==node.port;}));}
  reopened.setProxyPort(proxyPort);reopened.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(reopened.apiHealthy(),5000);reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-B"));QCOMPARE(net.a.forwarded,0);QCOMPARE(net.b.forwarded,2);reply->deleteLater();reopened.stop();QTRY_VERIFY_WITH_TIMEOUT(!reopened.processAlive(),5000);
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
  // Managed update headers and client-only log settings now have a safe,
  // explicitly disclosed projection. They do not redirect the Swirl source.
  for(const auto &compatible:QList<QByteArray>{original+"[General]\nloglevel=notify\n","#!MANAGED-CONFIG https://fixture.invalid/SYNTHETIC-MANAGED-TOKEN interval=86400 strict=false\n"+original}) {
   const auto dns=controller.dnsConfiguration();body=compatible;imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);
   QCOMPARE(controller.nodeCatalog(),beforeNodes);QCOMPARE(controller.dnsConfiguration(),dns);QCOMPARE(imports->providers().first().toMap().value("importMode").toString(),QString("full"));
   QVERIFY(!imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));QVERIFY(!imports->message().contains("SYNTHETIC-MANAGED-TOKEN"));
   NodeStore retained(path);QCOMPARE(retained.subscriptions().first().url,QUrl(QString("http://127.0.0.1:%1/sub").arg(subscription.serverPort())));QCOMPARE(retained.subscriptions().first().intervalMinutes,360);
   QCOMPARE(retained.networkConfiguration()["importedConfiguration"].toObject()["configuration"].toObject()["document"],QJsonValue(QString::fromUtf8(compatible).trimmed()));
  }
  beforeNetwork=controller.networkConfigurationSnapshot();
  QFile file(path);
  QList<QByteArray> unsupported{original+"[General]\ndns-server=192.0.2.53\n",original+"DOMAIN,late.invalid,route\n"};
  for(const auto &replacement:{"IP-CIDR,192.0.2.0/99,route","PROCESS-NAME,fixture.exe,route","DOMAIN,example.invalid,route,no-resolve","DOMAIN,example.invalid,SWIRL"}){auto bad=original;bad.replace("DOMAIN,localhost,REJECT",replacement);unsupported.append(bad);}
  {auto bad=original;bad.replace("select,B,A","url-test,B,A");unsupported.append(bad);bad=original;bad.replace("select,B,A","select,missing");unsupported.append(bad);bad=original;bad.replace("FINAL,route\n","");unsupported.append(bad);}
  for(const auto &bad:unsupported){body=bad;imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog(),beforeNodes);QCOMPARE(controller.networkConfigurationSnapshot(),beforeNetwork);
   const auto outcome=imports->providers().first().toMap();QVERIFY2(!outcome.value("status").toString().contains(QStringLiteral("失败")),qPrintable(imports->message()));QCOMPARE(outcome.value("importMode").toString(),QString("nodes-with-warning"));QVERIFY(!outcome.value("warning").toString().isEmpty());
   NodeStore retained(path);for(const auto &node:retained.nodes())QCOMPARE(node.sourceId,source);QCOMPARE(retained.networkConfiguration()["subscriptionImportResults"].toObject()[source].toObject()["notice"].toString(),outcome.value("warning").toString());
  }
  QList<QByteArray> dangerous{original+"[Remote Rule]\nhttps://fixture.invalid/rules,policy=route\n",original+"[Script]\nrequest=script-path=file:///SYNTHETIC-PRIVATE\n",original+"[MITM]\np12=SYNTHETIC-PRIVATE\n",original+"[General]\nhttp-listen=0.0.0.0:7890\n"};
  {auto bad=original;bad.replace("select,B,A","select,B,A,policy-path=C:\\SYNTHETIC-PRIVATE");dangerous.append(bad);}
  // This safe but incomplete update removes a node still referenced by the
  // retained policy. Nodes-only fallback must reject that dangling refresh.
  dangerous.append("[Proxy]\n"+a+"[Proxy Group]\nroute = select,A\n[Rule]\n"+QByteArray("DOMAIN,example.invalid,REJECT\n").repeated(1000)+"FINAL,route\n");
  for(const auto &bad:dangerous){
   QVERIFY(file.open(QIODevice::ReadOnly));const auto ciphertext=file.readAll();file.close();NodeStore storedBefore(path);const auto lastSuccess=storedBefore.subscriptions().first().lastSuccess;
   body=bad;imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog(),beforeNodes);QCOMPARE(controller.networkConfigurationSnapshot(),beforeNetwork);
   QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));QVERIFY(!imports->message().contains("SYNTHETIC-PRIVATE"));QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),ciphertext);file.close();QCOMPARE(NodeStore(path).subscriptions().first().lastSuccess,lastSuccess);
  }
  QVERIFY(file.open(QIODevice::ReadOnly));const auto beforeDownloadFailure=file.readAll();file.close();
  status=503;body=original;imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog(),beforeNodes);QCOMPARE(controller.networkConfigurationSnapshot(),beforeNetwork);QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),beforeDownloadFailure);file.close();status=200;
  body="[Proxy]\n"+a+"[Proxy Group]\nroute = select,A\n[Rule]\nFINAL,route\n";imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);
  controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),4000);reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-A"));reply->deleteLater();controller.disconnectNode();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
  body.replace("A =","Renamed =");body.replace("select,A","select,Renamed");imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);QCOMPARE(controller.nodeCatalog().size(),1);
  const auto renamed=controller.nodeCatalog().first().toMap().value("id").toString();
  // Display names are not semantic identities. The same source-owned endpoint
  // retains its ID and selection while the policy resolves the new source name.
  QCOMPARE(renamed,id);QCOMPARE(controller.nodeCatalog().first().toMap().value("name").toString(),QString("Renamed"));QCOMPARE(controller.selectedNodeId(),id);
  QCOMPARE(controller.policyGroups().first().toMap().value("proxies").toStringList(),QStringList{id});
  {NodeStore disk(path);QCOMPARE(disk.selectedId(),id);QCOMPARE(disk.nodes().first().sourceId,source);QCOMPARE(disk.nodes().first().name,QString("Renamed"));}
  const auto renamedCatalog=controller.nodeCatalog();const auto renamedNetwork=controller.networkConfigurationSnapshot();
  body.replace("select,Renamed","select,A");imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);
  QCOMPARE(controller.nodeCatalog(),renamedCatalog);QCOMPARE(controller.networkConfigurationSnapshot(),renamedNetwork);
  QVERIFY(!imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));QCOMPARE(imports->providers().first().toMap().value("importMode").toString(),QString("nodes-with-warning"));QVERIFY(imports->providers().first().toMap().value("warning").toString().contains("ProfileIniUnknownPolicy"));
  QVERIFY(file.open(QIODevice::ReadOnly));const auto renamedCiphertext=file.readAll();file.close();
  body+="[Script]\nrequest=script-path=file:///SYNTHETIC-PRIVATE\n";imports->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),4000);
  QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));QCOMPARE(controller.nodeCatalog(),renamedCatalog);QCOMPARE(controller.networkConfigurationSnapshot(),renamedNetwork);QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),renamedCiphertext);file.close();
  EngineController reopened(std::make_unique<RustCoreEngine>(),nullptr,path,true);QCOMPARE(reopened.selectedNodeId(),id);reopened.setProxyPort(proxyPort);reopened.connectNode(renamed);QTRY_VERIFY_WITH_TIMEOUT(reopened.apiHealthy(),4000);reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),5000);QCOMPARE(reply->readAll(),QByteArray("exit-A"));reply->deleteLater();reopened.stop();QTRY_VERIFY_WITH_TIMEOUT(!reopened.processAlive(),4000);
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
 void importedRealityVisionAndDefaultUtlsCannotStartAsOrdinaryTls(){
  QTcpServer endpoint;QVERIFY(endpoint.listen(QHostAddress::LocalHost));int connections=0;
  connect(&endpoint,&QTcpServer::newConnection,this,[&]{++connections;});
  QTcpServer localPort;QVERIFY(localPort.listen(QHostAddress::LocalHost));const auto proxyPort=localPort.serverPort();localPort.close();
  const QByteArray prefix="vless://11111111-1111-4111-8111-111111111111@127.0.0.1:"+QByteArray::number(endpoint.serverPort())+"?";
  const auto ordinary=NodeImporter::parse(prefix+"security=tls");QVERIFY(ordinary);
  EngineStartOptions options;options.nodes=ordinary.nodes;options.selectedNodeId=ordinary.nodes.first().id;options.proxyPort=proxyPort;options.routingMode="global";
  QJsonObject configuration;QVERIFY(RustCoreEngine::configuration(options,&configuration).isEmpty());
  const auto outbound=configuration.value("nodes").toArray().first().toObject().value("outbound").toObject();
  QCOMPARE(outbound.value("type"),QJsonValue("vless"));QVERIFY(outbound.value("tls").isObject());
  QList<QByteArray> sources{
   prefix+"security=reality&pbk=synthetic-key",
   prefix+"security=reality&pbk=synthetic-key&flow=xtls-rprx-vision",
   prefix+"security=tls&flow=xtls-rprx-vision",
   prefix+"security=tls&flow=xtls-rprx-vision-udp443"
  };
  const auto nativeKey=QString::fromLatin1(QByteArray(32,'\x09').toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals));
  sources.append(prefix+"security=reality&pbk="+nativeKey.toUtf8()+"&sid=abcd&sni=camouflage.invalid&flow=xtls-rprx-vision");
  const QJsonObject utlsNamedRustls{{"tag","declared-utls"},{"type","vless"},{"server","127.0.0.1"},{"server_port",endpoint.serverPort()},{"uuid","11111111-1111-4111-8111-111111111111"},{"tls",QJsonObject{{"enabled",true},{"server_name","camouflage.invalid"},{"insecure",false},{"utls",QJsonObject{{"enabled",true},{"fingerprint","rustls"}}},{"reality",QJsonObject{{"enabled",true},{"public_key",nativeKey},{"short_id","abcd"}}}}}};
  sources.append(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{utlsNamedRustls}}}).toJson());
  for(const auto &extension:QList<QJsonObject>{QJsonObject{{"enabled",true}},QJsonObject{{"enabled",true},{"fingerprint",""}}}){
   QJsonObject node{{"tag","fixture"},{"type","vless"},{"server","127.0.0.1"},{"server_port",endpoint.serverPort()},{"uuid","11111111-1111-4111-8111-111111111111"},
    {"tls",QJsonObject{{"enabled",true},{"utls",extension}}}};
   sources.append(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{node}}}).toJson());
   auto tls=node.value("tls").toObject();tls["server_name"]="camouflage.invalid";tls["reality"]=QJsonObject{{"enabled",true},{"public_key",nativeKey},{"short_id","abcd"}};node["tls"]=tls;node["flow"]="xtls-rprx-vision";
   sources.append(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{node}}}).toJson());
  }
  for(const auto &source:sources)for(const auto &body:{source,source.toBase64()}){
   const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));options.nodes=parsed.nodes;options.selectedNodeId=parsed.nodes.first().id;
   const auto reason=RustCoreEngine::configuration(options,&configuration);QVERIFY2(!reason.isEmpty(),"Declared security profile became ordinary TLS");
   QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(parsed.nodes.first()).isEmpty());
   RustCoreEngine engine;engine.start(options);QCOMPARE(engine.status().state,ProxyEngine::State::Failed);QCOMPARE(engine.status().error,ProxyEngine::Error::InvalidOptions);
   QVERIFY(!engine.status().processAlive);QVERIFY(!engine.status().apiHealthy);
  }
  QCoreApplication::processEvents();QCOMPARE(connections,0);
 }
 void singBoxTransportMapsExactlyAndRejectsUnmappedFieldsBeforeStart(){
  QTcpServer endpoint;QVERIFY(endpoint.listen(QHostAddress::LocalHost));int connections=0;
  connect(&endpoint,&QTcpServer::newConnection,this,[&]{++connections;});
  QTcpServer localPort;QVERIFY(localPort.listen(QHostAddress::LocalHost));const auto proxyPort=localPort.serverPort();localPort.close();
  const QJsonObject source{{"tag","fixture"},{"type","vless"},{"server","127.0.0.1"},{"server_port",endpoint.serverPort()},{"uuid","11111111-1111-4111-8111-111111111111"}};
  EngineStartOptions options;options.proxyPort=proxyPort;options.routingMode="global";
  for(const auto &field:QStringList{"service_name","future_required_field"}){
   auto node=source;node["transport"]=QJsonObject{{"type","ws"},{"path","/ws"},{field,"synthetic-secret"}};
   const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{node}}}).toJson());QVERIFY2(parsed,qPrintable(parsed.error));
   options.nodes=parsed.nodes;options.selectedNodeId=parsed.nodes.first().id;QJsonObject unchanged{{"sentinel",true}};
   QVERIFY(!RustCoreEngine::configuration(options,&unchanged).isEmpty());QCOMPARE(unchanged,QJsonObject({{"sentinel",true}}));
   RustCoreEngine engine;engine.start(options);QCOMPARE(engine.status().state,ProxyEngine::State::Failed);QCOMPARE(engine.status().error,ProxyEngine::Error::InvalidOptions);
   QVERIFY(!engine.status().processAlive);QVERIFY(!engine.status().apiHealthy);QVERIFY(!engine.status().message.contains("synthetic-secret"));
  }
  for(bool tls:{false,true})for(bool websocket:{false,true})for(bool explicitNulls:{false,true}){
   auto node=source;
   if(tls)node["tls"]=QJsonObject{{"enabled",true},{"server_name","tls.fixture.invalid"},{"alpn",QJsonArray{"http/1.1"}}};
   if(websocket)node["transport"]=QJsonObject{{"type","ws"},{"path","/ws%20path?fixture=1"},{"headers",QJsonObject{{"hOsT","ws.fixture.invalid:8443"}}}};
   if(explicitNulls)node["transport"]=websocket?QJsonValue(QJsonObject{{"type","ws"},{"path",QJsonValue()},{"headers",QJsonObject{{"Host",QJsonValue()}}},{"max_early_data",QJsonValue()},{"early_data_header_name",QJsonValue()}}):QJsonValue();
   const auto original=QJsonDocument(QJsonObject{{"outbounds",QJsonArray{node}}}).toJson();
   for(const auto &body:{original,original.toBase64()}){
    const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));QVERIFY(parsed.nodes.first().conversionIssues.isEmpty());
    QCOMPARE(parsed.nodes.first().originalConfiguration,node);
    options.nodes=parsed.nodes;options.selectedNodeId=parsed.nodes.first().id;QJsonObject configuration;const auto error=RustCoreEngine::configuration(options,&configuration);QVERIFY2(error.isEmpty(),qPrintable(error));
    const auto outbound=configuration.value("nodes").toArray().first().toObject().value("outbound").toObject();
    QCOMPARE(outbound.value("type"),QJsonValue("vless"));QCOMPARE(outbound.value("host"),source.value("server"));QCOMPARE(outbound.value("port"),source.value("server_port"));QCOMPARE(outbound.value("uuid"),source.value("uuid"));
    QCOMPARE(outbound.contains("tls"),tls);QCOMPARE(outbound.contains("websocket"),websocket);
    if(tls){QCOMPARE(outbound.value("tls").toObject().value("server_name"),QJsonValue("tls.fixture.invalid"));QCOMPARE(outbound.value("tls").toObject().value("alpn"),QJsonValue(QJsonArray{"http/1.1"}));}
    if(websocket){QCOMPARE(outbound.value("websocket").toObject().value("host"),explicitNulls?source.value("server"):QJsonValue("ws.fixture.invalid:8443"));QCOMPARE(outbound.value("websocket").toObject().value("path"),QJsonValue(explicitNulls?"/":"/ws%20path?fixture=1"));}
    else {QVERIFY(!parsed.nodes.first().parameters.contains("network"));QVERIFY(!parsed.nodes.first().parameters.contains("ws-opts"));}
   }
  }
  QCoreApplication::processEvents();QCOMPARE(connections,0);
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
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");QString source;
  {NodeStore seed(path);QVERIFY(seed.saveSubscription({},"stable provider",QUrl("https://fixture.invalid/stable"),360,false));source=seed.subscriptions().first().id;}
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  const QVariantMap dns{{"mode",0},{"servers",""},{"encrypted","https://1.1.1.1/dns-query"}};
  QVERIFY(controller.configureDns(dns));const auto preservedDns=controller.dnsConfiguration();
  const auto parsed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]");QVERIFY(parsed);
  const QVariantMap configuration{{"groups",QVariantList{QVariantMap{{"name","choice"},{"type","select"},{"proxies",QStringList{"A","DIRECT"}},{"default-selected","A"}}}},{"rules",QStringList{"MATCH,choice"}}};
  QVERIFY2(controller.importNodesAndConfiguration(parsed.nodes,source,configuration),qPrintable(controller.networkConfigurationError()));
  const auto id=controller.nodeCatalog().first().toMap().value("id").toString();QCOMPARE(controller.dnsConfiguration(),preservedDns);
  QCOMPARE(controller.policyGroups().first().toMap().value("proxies").toStringList(),QStringList({id,"DIRECT"}));
  auto refreshed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1081}]");QVERIFY(refreshed);
  QVERIFY(controller.importNodesAndConfiguration(refreshed.nodes,source,configuration));QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);
  EngineController reopened(std::make_unique<RustCoreEngine>(),nullptr,path);QCOMPARE(QJsonObject::fromVariantMap(reopened.dnsConfiguration()),QJsonObject::fromVariantMap(preservedDns));QCOMPARE(QJsonArray::fromVariantList(reopened.policyGroups()),QJsonArray::fromVariantList(controller.policyGroups()));QCOMPARE(QJsonObject::fromVariantMap(reopened.networkConfigurationSnapshot()),QJsonObject::fromVariantMap(controller.networkConfigurationSnapshot()));
  NodeStore disk(path);QCOMPARE(disk.nodes().size(),1);QCOMPARE(disk.nodes().first().id,id);QCOMPARE(disk.nodes().first().port,quint16(1081));QCOMPARE(disk.networkConfiguration()["groups"].toArray(),QJsonArray::fromVariantList(controller.policyGroups()));
  QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));QVERIFY(!file.readAll().contains("choice"));QVERIFY(!QFile::exists(path+".network.json"));
 }
 void atomicNodeNetworkImportRejectsInvalidGraphAndWriteFailure(){
  QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
  auto parsed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]");QVERIFY(parsed);
  const QVariantMap configuration{{"groups",QVariantList{QVariantMap{{"name","choice"},{"type","select"},{"proxies",QStringList{"A"}}}}},{"rules",QStringList{"MATCH,choice"}}};
  QVERIFY(controller.importNodesAndConfiguration(parsed.nodes,{},configuration));const auto before=controller.networkConfigurationSnapshot();
  parsed.nodes.first().port=1081;parsed.nodes.first().id=QUuid::createUuid().toString(QUuid::WithoutBraces);auto invalid=configuration;invalid["groups"]=QVariantList{QVariantMap{{"name","choice"},{"type","select"},{"proxies",QStringList{"missing"}}}};
  QVERIFY(!controller.importNodesAndConfiguration(parsed.nodes,{},invalid));QCOMPARE(controller.networkConfigurationSnapshot(),before);
  const auto backup=directory.filePath("old.dpapi");QVERIFY(QFile::rename(path,backup));QVERIFY(QDir().mkdir(path));
  QVERIFY(!controller.importNodesAndConfiguration(parsed.nodes,{},configuration,QJsonObject{{"rules",QJsonArray{"MATCH,choice"}}}));QCOMPARE(controller.networkConfigurationSnapshot(),before);
  QCOMPARE(controller.nodeCatalog().first().toMap().value("port").toInt(),1080);
  QVERIFY(QDir().rmdir(path));QVERIFY(QFile::rename(backup,path));NodeStore disk(path);QCOMPARE(disk.nodes().first().port,quint16(1080));QCOMPARE(disk.networkConfiguration()["groups"].toArray(),QJsonArray::fromVariantList(before.value("groups").toList()));
  QVERIFY(!disk.networkConfiguration().contains("nativeDocumentRouting"));
  QTcpServer port;QVERIFY(port.listen(QHostAddress::LocalHost));const auto listenPort=port.serverPort();port.close();controller.setProxyPort(listenPort);
  controller.setRoutingMode("global");controller.connectNode(QString{});QVERIFY(!controller.processAlive());QVERIFY(!controller.apiHealthy());
  controller.setRoutingMode("direct");controller.connectNode(QString{});QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),4000);controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
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
  QVERIFY(store.prepareImport(duplicate,{},&plan));QCOMPARE(plan.nodes().size(),1);QCOMPARE(store.nodes().size(),1);
  QCOMPARE(plan.importedToStoredIds().value(other.id),parsed.nodes.first().id);
  QVERIFY(!store.prepareImport({parsed.nodes.first(),parsed.nodes.first()},{},&plan));
  other.name="B";other.id=parsed.nodes.first().id;QVERIFY(store.prepareImport({other},{},&plan));QCOMPARE(plan.nodes().first().id,other.id);
  other.port=1081;QVERIFY(!store.prepareImport({other},{},&plan));
  QVERIFY(store.saveSubscription({},"fixture",QUrl("https://example.invalid/sub"),360,false));
  QVERIFY(!store.prepareImport(parsed.nodes,store.subscriptions().first().id,&plan));QVERIFY(store.nodes().first().sourceId.isEmpty());
  QVERIFY(store.prepareImport(parsed.nodes,{},&plan));QVERIFY(store.select(parsed.nodes.first().id));QVERIFY(!store.commitImport(plan));
  NodeStore otherStore(directory.filePath("other.dpapi"));QVERIFY(!otherStore.commitImport(plan));
  NodeStore::ImportPlan empty;QVERIFY(!store.commitImport(empty));QCOMPARE(store.nodes().size(),1);
 }
 void preparedImportWriteFailurePreservesMemoryAndDurableSnapshot(){
  QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));
  auto parsed=NodeImporter::parse("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]");QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes));
  const auto id=store.nodes().first().id;parsed.nodes.first().port=1081;parsed.nodes.first().id=QUuid::createUuid().toString(QUuid::WithoutBraces);
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
 void singBoxQuicProductChainAgainstIndependentPeer(){
  if(!qEnvironmentVariableIsSet("SWIRL_QT_QUIC_FIXTURE"))QSKIP("The independent QUIC harness supplies synthetic servers and targets.");
#ifndef Q_OS_WIN
  QSKIP("The product persistence gate requires Windows DPAPI.");
#endif
  const auto fixturePath=qEnvironmentVariable("SWIRL_QT_QUIC_FIXTURE"),reportPath=qEnvironmentVariable("SWIRL_QT_QUIC_REPORT");
  QVERIFY(QFileInfo(reportPath).isAbsolute()&&fixturePath!=reportPath);QFile fixtureFile(fixturePath);QVERIFY(fixtureFile.open(QIODevice::ReadOnly));QVERIFY(fixtureFile.size()<=NodeImporter::MaximumBytes);
  const auto fixture=NodeImporter::strictJsonObject(fixtureFile.readAll());QVERIFY(!fixture.isEmpty());
  const auto subscription=fixture["subscription"].toString();QVERIFY(!subscription.isEmpty());
  const auto tcpPort=fixture["tcp_port"].toInt(),udpPort=fixture["udp_port"].toInt();QVERIFY(tcpPort>0&&tcpPort<=65535&&udpPort>0&&udpPort<=65535);
  const bool reject=fixture["reject"].toBool();
  QJsonObject report{{"schema",1},{"imported",false},{"encrypted_store_reloaded",false},{"in_process_rust",false},{"tcp_verified",false},{"udp_verified",false},{"rejected",false},{"listener_released",false}};
  const auto save=[&]{QSaveFile file(reportPath);const auto bytes=QJsonDocument(report).toJson();return file.open(QIODevice::WriteOnly)&&file.write(bytes)==bytes.size()&&file.commit();};
  const auto reportGuard=qScopeGuard([&]{save();});QVERIFY(save());
  QTemporaryDir directory;const auto path=directory.filePath("quic.dpapi");QString selected;QJsonObject original,parameters;
  {
   EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);
   controller.imports()->importText(subscription);QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);
   NodeStore stored(path);QVERIFY2(stored.nodes().size()==1,qPrintable(controller.imports()->message()));selected=stored.nodes().first().id;
   original=stored.nodes().first().originalConfiguration;parameters=stored.nodes().first().parameters;
   QVERIFY(!original.isEmpty()&&original["tls"].isObject());QVERIFY(controller.chooseNode(selected));
   QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto encrypted=file.readAll();QVERIFY(encrypted.startsWith("SWIRLNODE1\n"));QVERIFY(!encrypted.contains(stored.nodes().first().password.toUtf8()));
   report["imported"]=true;
  }
  QTcpServer reservation;QVERIFY(reservation.listen(QHostAddress::LocalHost));const auto proxyPort=reservation.serverPort();reservation.close();
  EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);controller.setProxyPort(proxyPort);controller.setRoutingMode("global");
  NodeStore restored(path);QCOMPARE(restored.nodes().size(),1);QCOMPARE(restored.nodes().first().originalConfiguration,original);QCOMPARE(restored.nodes().first().parameters,parameters);QCOMPARE(restored.selectedId(),selected);report["encrypted_store_reloaded"]=true;
  controller.connectNode({});QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);
  QCOMPARE(controller.engineKind(),QString("rust"));QCOMPARE(controller.processId(),QString::number(QCoreApplication::applicationPid()));report["in_process_rust"]=true;
  QTcpSocket tcp;tcp.setProxy(QNetworkProxy::NoProxy);tcp.connectToHost(QHostAddress::LocalHost,proxyPort);QTRY_COMPARE_WITH_TIMEOUT(tcp.state(),QAbstractSocket::ConnectedState,5000);
  const auto authority="127.0.0.1:"+QByteArray::number(tcpPort);const auto connect="CONNECT "+authority+" HTTP/1.1\r\nHost: "+authority+"\r\n\r\n";QCOMPARE(tcp.write(connect),connect.size());
  QByteArray response;QVERIFY(QTest::qWaitFor([&]{response+=tcp.readAll();return response.contains("\r\n\r\n")||tcp.state()==QAbstractSocket::UnconnectedState;},7000));
  if(reject){
   const auto failed=QByteArray("HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
   if(original["type"]=="tuic"&&response!=failed){
    // TUIC v5 has no positive authentication response. A CONNECT reply only
    // acknowledges the local tunnel; the peer must then reject before any
    // target data arrives. The harness independently requires zero target
    // connections, so an optimistic local reply cannot hide authentication loss.
    QCOMPARE(response,QByteArray("HTTP/1.1 200 Connection Established\r\n\r\n"));const QByteArray payload="must-not-reach-origin";
    if(tcp.state()==QAbstractSocket::ConnectedState){const auto written=tcp.write(payload);QVERIFY(written==-1||written==payload.size());}
    response.clear();QVERIFY(QTest::qWaitFor([&]{response+=tcp.readAll();return tcp.state()==QAbstractSocket::UnconnectedState;},7000));response+=tcp.readAll();QVERIFY(response.isEmpty());
   }else QCOMPARE(response,failed);
   report["rejected"]=true;
  }else{
   QCOMPARE(response,QByteArray("HTTP/1.1 200 Connection Established\r\n\r\n"));const QByteArray payload(65553,'q');QCOMPARE(tcp.write(payload),payload.size());response.clear();
   QVERIFY(QTest::qWaitFor([&]{response+=tcp.readAll();return response.size()>=payload.size()||tcp.state()==QAbstractSocket::UnconnectedState;},7000));QCOMPARE(response,payload);report["tcp_verified"]=true;
   tcp.disconnectFromHost();QTRY_COMPARE_WITH_TIMEOUT(tcp.state(),QAbstractSocket::UnconnectedState,5000);
   QUdpSocket udp;udp.setProxy(QNetworkProxy::NoProxy);QVERIFY(udp.bind(QHostAddress::LocalHost,0,QUdpSocket::DontShareAddress));
   QTcpSocket control;control.setProxy(QNetworkProxy::NoProxy);control.connectToHost(QHostAddress::LocalHost,proxyPort);QTRY_COMPARE_WITH_TIMEOUT(control.state(),QAbstractSocket::ConnectedState,5000);
   QCOMPARE(control.write(QByteArray::fromHex("050100")),qint64(3));QTRY_VERIFY_WITH_TIMEOUT(control.bytesAvailable()>=2,5000);QCOMPARE(control.read(2),QByteArray::fromHex("0500"));
   auto associate=QByteArray::fromHex("050300017f000001");associate.append(char(udp.localPort()>>8));associate.append(char(udp.localPort()&255));QCOMPARE(control.write(associate),associate.size());QTRY_VERIFY_WITH_TIMEOUT(control.bytesAvailable()>=10,5000);
   const auto bound=control.read(10);QCOMPARE(bound.left(8),QByteArray::fromHex("050000017f000001"));const auto relayPort=quint16((quint16(quint8(bound[8]))<<8)|quint8(bound[9]));QVERIFY(relayPort>0);
   auto header=QByteArray::fromHex("000000017f000001");header.append(char(udpPort>>8));header.append(char(udpPort&255));const auto packet=header+QByteArray("s4-quic-udp-payload");
   QCOMPARE(udp.writeDatagram(packet,QHostAddress::LocalHost,relayPort),packet.size());QTRY_VERIFY_WITH_TIMEOUT(udp.hasPendingDatagrams(),7000);const auto datagram=udp.receiveDatagram();QCOMPARE(datagram.senderPort(),int(relayPort));QCOMPARE(datagram.data(),packet);report["udp_verified"]=true;
   control.disconnectFromHost();QTRY_COMPARE_WITH_TIMEOUT(control.state(),QAbstractSocket::UnconnectedState,5000);
  }
  tcp.abort();controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.busy(),5000);QTcpServer reclaimed;QVERIFY(reclaimed.listen(QHostAddress::LocalHost,proxyPort));report["listener_released"]=true;QVERIFY(save());
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
   EngineStartOptions o;o.routingMode="global";o.nodes=parsed.nodes;o.selectedNodeId=node.id;
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
   {{"tfo","true"}},{{"network","ws"}},{{"network","udp"}},{{"remote_dns",false}},
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
 void webSocketUdpDeclarationSurvivesNativeMappingAndRuntimeStartup(){
  ControlledNetwork net;QVERIFY(net.start());
  for(const bool udp:{false,true}){
   const QJsonObject raw{{"name","ws-udp-fixture"},{"type","vless"},{"server","127.0.0.1"},{"port",net.a.serverPort()},
    {"uuid","00112233-4455-6677-8899-aabbccddeeff"},{"network","ws"},{"tls",true},{"sni","tls.fixture.invalid"},
    {"alpn",QJsonArray{"http/1.1"}},{"udp",udp},
    {"ws-opts",QJsonObject{{"path","/proxy"},{"headers",QJsonObject{{"Host","ws.fixture.invalid"}}}}}};
   const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"proxies",QJsonArray{raw}}}).toJson());
   QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.first().parameters.value("udp"),QJsonValue(udp));
   QCOMPARE(parsed.nodes.first().originalConfiguration,raw);
   auto start=options(net);start.nodes=parsed.nodes;start.selectedNodeId=parsed.nodes.first().id;
   QJsonObject config;const auto error=RustCoreEngine::configuration(start,&config);QVERIFY2(error.isEmpty(),qPrintable(error));
   const auto outbound=config.value("nodes").toArray().first().toObject().value("outbound").toObject();
   QCOMPARE(outbound.value("udp"),QJsonValue(udp));
   QCOMPARE(outbound.value("websocket").toObject(),QJsonObject({{"host","ws.fixture.invalid"},{"path","/proxy"}}));
   QCOMPARE(outbound.value("tls").toObject().value("server_name"),QJsonValue("tls.fixture.invalid"));
   RustCoreEngine engine;engine.start(start);
   QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(engine.status().message));
   QVERIFY(engine.status().apiHealthy);QCOMPARE(engine.status().engineKind,QString("rust"));
   // This exercises actual native configuration/lifecycle (level 2). The
   // inherited Rust UDP-over-stream peer suites verify protocol datagrams;
   // listener startup is not labeled as external UDP interoperability.
   engine.stop();QCOMPARE(engine.status().state,ProxyEngine::State::Stopped);
   QTcpServer reclaimed;QVERIFY(reclaimed.listen(QHostAddress::LocalHost,start.proxyPort));
  }
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
   {"string UDP flag",{{"udp","true"}}},
   {"numeric UDP flag",{{"udp",1}}},
   {"null UDP flag",{{"udp",QJsonValue(QJsonValue::Null)}}},
   {"object UDP flag",{{"udp",QJsonObject{}}}},
   {"array UDP flag",{{"udp",QJsonArray{}}}},
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
  engine.refresh();bool rejected=false,direct=false;for(const auto &record:engine.status().connections){const auto row=record.toMap();
   if(row["host"]=="blocked.invalid"&&row["category"]=="reject"){
    rejected=row["rule"].toString().contains("DOMAIN,blocked.invalid")&&row["outbound"]=="REJECT"&&row["transportState"]=="failed";
   }
   if(row["host"]=="127.0.0.1"&&row["category"]=="direct"){
    direct=row["rule"].toString().contains("DST-PORT")&&row["outbound"]=="DIRECT"&&row["downloadBytes"].toLongLong()>0;
   }
  }QVERIFY(rejected);QVERIFY(direct);
  engine.setRoutingMode("global");QCOMPARE(request(net.url()),QByteArray("exit-A"));QCOMPARE(net.a.forwarded,1);
  engine.refresh();bool proxied=false;for(const auto &record:engine.status().connections){const auto row=record.toMap();
   if(row["category"]=="proxy"&&row["host"]=="127.0.0.1")proxied=row["rule"]=="DEFAULT"&&row["outbound"]=="PROXY"&&row["proxyNode"]=="synthetic"&&row["downloadBytes"].toLongLong()>0;
  }QVERIFY(proxied);
  engine.setRoutingMode("rule");QCOMPARE(request(net.url()),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,1);
  engine.setRoutingMode("direct");QCOMPARE(request(net.url()),QByteArray("DIRECT-BYPASS"));QCOMPARE(engine.routingRules().size(),1);
  engine.selectNode(o.selectedNodeId);QVERIFY(engine.status().directSession);QCOMPARE(request(net.url()),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,1);
  engine.stop();
 }
 void manualWindowsRulesUseTwoIndependentTargetsAndPersist(){
  ControlledNetwork net;QVERIFY(net.start());net.a.aliases={"fallback.proxy.invalid","overseas.proxy.invalid"};
  QTcpServer directTarget;QVERIFY(directTarget.listen(QHostAddress::LocalHost,0));int directRequests=0;
  connect(&directTarget,&QTcpServer::newConnection,&directTarget,[&]{
   while(directTarget.hasPendingConnections()){
    auto *socket=directTarget.nextPendingConnection();
    connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
    connect(socket,&QTcpSocket::readyRead,socket,[socket,&directRequests]{
     const auto bytes=socket->property("request").toByteArray()+socket->readAll();socket->setProperty("request",bytes);
     if(!bytes.contains("\r\n\r\n"))return;
     ++directRequests;socket->write("HTTP/1.1 200 OK\r\nContent-Length: 14\r\nConnection: close\r\n\r\nprivate-direct");socket->disconnectFromHost();
    });
   }
  });
  QTemporaryDir directory;QVERIFY(directory.isValid());const auto path=directory.filePath("manual-rules.dpapi");const auto o=options(net);
  QSettings settings;const auto previous=settings.value("Proxy/routingMode");
  const auto restore=qScopeGuard([&]{if(previous.isValid())settings.setValue("Proxy/routingMode",previous);else settings.remove("Proxy/routingMode");settings.sync();});
  const QJsonObject imported{{"name","synthetic"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.a.serverPort()}};
  const auto directUrl=QUrl(QString("http://127.0.0.1:%1/direct").arg(directTarget.serverPort()));
  const auto proxyUrl=QUrl(QString("http://fallback.proxy.invalid:%1/proxy").arg(net.http.serverPort()));
  const auto overseasUrl=QUrl(QString("http://overseas.proxy.invalid:%1/overseas").arg(net.http.serverPort()));
  const auto rejectUrl=QUrl(QString("http://ad.ads.invalid:%1/blocked").arg(net.http.serverPort()));
  const auto request=[&](quint16 port,const QUrl &url){
   QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",port));
   QNetworkRequest req(url);req.setTransferTimeout(4000);auto *reply=client.get(req);
   if(!QTest::qWaitFor([&]{return reply->isFinished();},5000))return QByteArray("timeout");
   return reply->error()==QNetworkReply::NoError?reply->readAll():QByteArray("rejected");
  };
  QString id;
  {
   EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,path,true);controller.setProxyPort(o.proxyPort);
   controller.imports()->importText(QString::fromUtf8(QJsonDocument(QJsonObject{{"proxies",QJsonArray{imported}}}).toJson()));
   QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),5000);QCOMPARE(controller.nodeCatalog().size(),1);
   id=controller.nodeCatalog().first().toMap().value("id").toString();QVERIFY(controller.chooseNode(id));
   controller.setRoutingMode("rule");controller.connectNode(id);
   QTRY_VERIFY_WITH_TIMEOUT(controller.connected()&&!controller.nodeBusy()&&!controller.routingBusy(),5000);
   QCOMPARE(controller.routingMode(),QString("rule"));
   controller.setRoutingMode("global");QVERIFY2(controller.routingError().isEmpty(),qPrintable(controller.routingError()));
   QTRY_COMPARE_WITH_TIMEOUT(controller.routingMode(),QString("global"),5000);
   QTRY_VERIFY_WITH_TIMEOUT(controller.connected()&&!controller.nodeBusy()&&!controller.routingBusy(),5000);
   controller.setRoutingMode("rule");QVERIFY2(controller.routingError().isEmpty(),qPrintable(controller.routingError()));
   QTRY_COMPARE_WITH_TIMEOUT(controller.routingMode(),QString("rule"),5000);
   QTRY_VERIFY_WITH_TIMEOUT(controller.connected()&&!controller.nodeBusy()&&!controller.routingBusy(),5000);
   QCOMPARE(QSettings().value("Proxy/routingMode").toString(),QString("rule"));
   controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),5000);controller.setRoutingMode("rule");
   QVERIFY(controller.saveRoutingRule("DOMAIN-SUFFIX","ads.invalid","REJECT"));
   QVERIFY(!controller.saveRoutingRule("DOMAIN-SUFFIX","ads.invalid","DIRECT"));
   QVERIFY(controller.networkConfigurationError().contains(QString::fromUtf8("遮蔽")));
   QVERIFY(controller.saveRoutingRule("DOMAIN","overseas.proxy.invalid","SWIRL"));
   QVERIFY(controller.saveRoutingRule("DST-PORT",QString::number(directTarget.serverPort()),"DIRECT"));
   const auto saved=controller.networkConfigurationSnapshot();
   QVERIFY(!controller.saveRoutingRule("MATCH","","SWIRL",0));
   QVERIFY(controller.networkConfigurationError().contains(QString::fromUtf8("最后一条")));
   QCOMPARE(controller.networkConfigurationSnapshot(),saved);
   controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);
   QCOMPARE(request(o.proxyPort,directUrl),QByteArray("private-direct"));QCOMPARE(directRequests,1);QCOMPARE(net.a.forwarded,0);
   QCOMPARE(request(o.proxyPort,overseasUrl),QByteArray("exit-A"));QCOMPARE(net.a.forwarded,1);
   QCOMPARE(request(o.proxyPort,proxyUrl),QByteArray("exit-A"));QCOMPARE(net.a.forwarded,2);
   QCOMPARE(request(o.proxyPort,net.url()),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,2);
   const auto before=net.httpRequests,beforeDirect=directRequests,beforeProxy=net.a.forwarded;
   QCOMPARE(request(o.proxyPort,rejectUrl),QByteArray("rejected"));QCOMPARE(net.httpRequests,before);
   QCOMPARE(directRequests,beforeDirect);QCOMPARE(net.a.forwarded,beforeProxy);
   QTRY_VERIFY_WITH_TIMEOUT([&]{for(const auto &entry:controller.telemetry()->connections())if(entry.toMap().value("host")=="ad.ads.invalid")return true;return false;}(),3000);
   bool direct=false,proxy=false,overseas=false,reject=false;
   for(const auto &entry:controller.telemetry()->connections()){
    const auto row=entry.toMap();const auto host=row.value("host").toString();
    if(host=="127.0.0.1"&&row.value("port").toInt()==directTarget.serverPort())direct=row.value("rule").toString().contains("DST-PORT")&&row.value("outbound")=="DIRECT"&&row.value("downloadBytes").toLongLong()>0;
    if(host=="fallback.proxy.invalid")proxy=row.value("rule")=="DEFAULT"&&row.value("outbound")=="PROXY"&&row.value("proxyNode")=="synthetic"&&row.value("downloadBytes").toLongLong()>0;
    if(host=="overseas.proxy.invalid")overseas=row.value("rule").toString().contains("DOMAIN,overseas.proxy.invalid")&&row.value("outbound")=="PROXY"&&row.value("proxyNode")=="synthetic";
    if(host=="ad.ads.invalid")reject=row.value("rule").toString().contains("DOMAIN-SUFFIX,ads.invalid")&&row.value("outbound")=="REJECT";
   }
   QVERIFY(direct);QVERIFY(proxy);QVERIFY(overseas);
   QVERIFY2(reject,qPrintable(QString::fromUtf8(QJsonDocument::fromVariant(controller.telemetry()->connections()).toJson(QJsonDocument::Compact))));
   QVERIFY(!controller.saveRoutingRule("MATCH","","DIRECT"));QVERIFY(controller.connected());
   QCOMPARE(request(o.proxyPort,proxyUrl),QByteArray("exit-A"));
   controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),5000);
  }
  QCOMPARE(NodeStore(path).networkConfiguration()["rules"].toArray().size(),3);
  {
   EngineController restored(std::make_unique<ThreadedEngine>(),nullptr,path,true);restored.setProxyPort(o.proxyPort);
   QCOMPARE(restored.selectedNodeId(),id);QCOMPARE(restored.routingMode(),QString("rule"));
   restored.connectNode({});QTRY_VERIFY_WITH_TIMEOUT(restored.apiHealthy(),5000);
   QCOMPARE(request(o.proxyPort,directUrl),QByteArray("private-direct"));
   QCOMPARE(request(o.proxyPort,proxyUrl),QByteArray("exit-A"));
   restored.stop();QTRY_VERIFY_WITH_TIMEOUT(!restored.processAlive(),5000);
  }
  QCOMPARE(directRequests,2);QCOMPARE(net.a.forwarded,4);
 }
 void nativePrivateRulesPrecedeTerminalMatch(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.routingMode="rule";
  o.nativePrivateRouting=true;o.customRules={"MATCH,REJECT"};
  QJsonObject config;const auto error=RustCoreEngine::configuration(o,&config);QVERIFY2(error.isEmpty(),qPrintable(error));
  const auto rules=config.value("rules").toArray();QVERIFY(rules.size()>2);
  QCOMPARE(rules.first().toObject().value("matcher").toObject().value("value"),QJsonValue("127.0.0.0/8"));
  QCOMPARE(rules.last().toObject().value("matcher").toObject().value("type"),QJsonValue("match"));
  const auto rows=RustCoreEngine::routingRulesForOptions(o);QCOMPARE(rows.last().toMap().value("policy").toString(),QString("REJECT"));
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
  QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
  auto *reply=client.get(QNetworkRequest(net.url()));QVERIFY(QTest::qWaitFor([&]{return reply->isFinished();},5000));
  QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded,0);
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
 void optionalFastOpenUsesOrdinaryTcpAcrossNativeProtocols(){
  ControlledNetwork net;QVERIFY(net.start());
  for(const auto &protocol:QStringList{"http","socks4","socks4a","socks5","ss","trojan","vless"}){
   auto o=options(net);auto &n=o.nodes.first();n.protocol=protocol;
   if(protocol=="ss"){n.password="synthetic";n.cipher="aes-128-gcm";}
   if(protocol=="trojan")n.password="synthetic";
   if(protocol=="vless")n.parameters["uuid"]="11111111-1111-4111-8111-111111111111";
   QJsonObject baseline;QVERIFY2(RustCoreEngine::configuration(o,&baseline).isEmpty(),qPrintable(protocol));
   for(const auto enabled:{false,true}){
    n.parameters["tfo"]=enabled;QJsonObject fallback;QVERIFY2(RustCoreEngine::configuration(o,&fallback).isEmpty(),qPrintable(protocol));QCOMPARE(fallback,baseline);
    QCOMPARE(n.publicInfo().value("normalizationNotes").toString().contains("普通 TCP"),enabled);
   }
   for(const auto &invalid:QJsonArray{0,1,"false",QJsonValue(QJsonValue::Null),QJsonObject{},QJsonArray{}}){
    n.parameters["tfo"]=invalid;QJsonObject unchanged{{"sentinel",true}};QVERIFY(!RustCoreEngine::configuration(o,&unchanged).isEmpty());QCOMPARE(unchanged,QJsonObject({{"sentinel",true}}));
   }
  }
 }
 void optionalFastOpenForwardsThroughNativeSocks5(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.nodes.first().parameters["tfo"]=true;
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
  for(const auto &tail:QStringList{"http,obfs.example","obfs-name=http,obfs-host=obfs.example","obfs-name=http,obfs-host=obfs.example,fast-open=false","obfs-name=http,obfs-host=obfs.example,fast-open=true"}){
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
 void internalNodeTestListenersAreAtomicallyOwnedAndPreserveUserPortValidation(){
  ControlledNetwork net;QVERIFY(net.start());auto user=options(net);user.proxyPort=0;
  QJsonObject configuration;QVERIFY(!RustCoreEngine::configuration(user,&configuration).isEmpty());
  RustCoreEngine invalid;invalid.start(user);QCOMPARE(invalid.status().error,ProxyEngine::Error::InvalidOptions);QVERIFY(!invalid.status().processAlive);
  auto isolated=NodeTestService::isolatedOptions(user);isolated.selectedNodeId=user.selectedNodeId;
  QCOMPARE(isolated.proxyPort,quint16(0));QVERIFY(isolated.internalProbeListener);
  QVERIFY(RustCoreEngine::configuration(isolated,&configuration).isEmpty());QCOMPARE(configuration.value("listen").toString(),QString("127.0.0.1:0"));
  auto other=isolated.nodes.first();other.id=QUuid::createUuid().toString(QUuid::WithoutBraces);isolated.nodes.append(other);
  RustCoreEngine first,second;first.start(isolated);second.start(isolated);
  QVERIFY2(first.status().apiHealthy,qPrintable(first.status().message));QVERIFY2(second.status().apiHealthy,qPrintable(second.status().message));
  const auto firstPort=first.status().proxyPort,secondPort=second.status().proxyPort;
  QVERIFY(firstPort>0);QVERIFY(secondPort>0);QVERIFY(firstPort!=secondPort);
  for(const auto port:{firstPort,secondPort}){
   QTcpServer conflict;conflict.setProxy(QNetworkProxy::NoProxy);QVERIFY(!conflict.listen(QHostAddress::LocalHost,quint16(port)));
  }
  const auto request=[&](int port){
   QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",quint16(port)));
   QNetworkRequest input(net.url());input.setTransferTimeout(4000);auto *reply=client.get(input);
   if(!QTest::qWaitFor([&]{return reply->isFinished();},5000)||reply->error()!=QNetworkReply::NoError)return QByteArray("request-failed");
   return reply->readAll();
  };
  QCOMPARE(request(firstPort),QByteArray("exit-A"));QCOMPARE(request(secondPort),QByteArray("exit-A"));
  const auto session=first.status().sessionId;first.selectNode(other.id);
  QCOMPARE(first.status().selectedNodeId,other.id);QCOMPARE(first.status().sessionId,session);QCOMPARE(first.status().proxyPort,firstPort);
  QCOMPARE(request(firstPort),QByteArray("exit-A"));
  first.probeNode(net.url());second.probeNode(net.url());
  QTRY_COMPARE_WITH_TIMEOUT(first.status().requestState,ProxyEngine::RequestState::Succeeded,5000);
  QTRY_COMPARE_WITH_TIMEOUT(second.status().requestState,ProxyEngine::RequestState::Succeeded,5000);
  QCOMPARE(first.status().responseCode,200);QCOMPARE(second.status().responseCode,200);QCOMPARE(net.a.forwarded,5);QCOMPARE(net.httpRequests,5);
  first.stop();second.stop();QVERIFY(!first.status().processAlive);QVERIFY(!second.status().processAlive);
 }
 void queuedProbesRecoverAfterPeerRejectionAndCancellation(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  const int count=qBound(24,qEnvironmentVariableIntValue("SWIRL_U2_PROBE_COUNT"),5000);
  const auto prototype=o.nodes.first();o.nodes.clear();QStringList ids;
  for(int i=0;i<count;++i){auto node=prototype;node.id=QUuid::createUuid().toString(QUuid::WithoutBraces);node.name=QString("probe-%1").arg(i);o.nodes.append(node);ids.append(node.id);}
  o.selectedNodeId=ids.first();NodeTestService probes;
  int peakActive=0;QElapsedTimer heartbeat;heartbeat.start();qint64 maxGap=0;
  QTimer ticker;ticker.setInterval(10);
  connect(&ticker,&QTimer::timeout,&ticker,[&]{
   maxGap=qMax(maxGap,heartbeat.restart());int active=0;
   for(auto *runner:probes.findChildren<ProxyEngine *>(QString(),Qt::FindDirectChildrenOnly)){
    const auto s=runner->status();if(s.processAlive||s.state==ProxyEngine::State::Starting||s.state==ProxyEngine::State::Stopping)++active;
   }
   peakActive=qMax(peakActive,active);
  });ticker.start();
  net.a.reject=true;const auto before=net.httpRequests;
  probes.start(o,ids.mid(0,6),net.url());
  QVERIFY(QTest::qWaitFor([&]{return !probes.busy();},15000));
  QCOMPARE(probes.failed(),6);QCOMPARE(probes.succeeded(),0);QCOMPARE(net.httpRequests,before);
  net.a.reject=false;QElapsedTimer elapsed;elapsed.start();
  probes.start(o,ids,net.url());
  QVERIFY(QTest::qWaitFor([&]{return !probes.busy();},qMax(30000,count*1000)));
  if(probes.failed())qInfo()<<"Loopback probe failure"<<probes.result(ids.first()).value("phase")<<probes.result(ids.first()).value("error");
  QCOMPARE(probes.succeeded(),count);QCOMPARE(probes.failed(),0);QVERIFY(net.a.forwarded>=count);
  for(const auto &id:ids){QVERIFY(probes.result(id).value("success").toBool());QCOMPARE(probes.result(id).value("engineKind").toString(),QString("rust"));}
  qInfo()<<"U2 real loopback bulk probe count"<<count<<"elapsedMs"<<elapsed.elapsed()<<"maxEventLoopGapMs"<<maxGap<<"peakActive"<<peakActive;
  QVERIFY(peakActive<=3);
  probes.start(o,ids,net.url());probes.cancel();
  QVERIFY(QTest::qWaitFor([&]{return !probes.busy();},10000));QVERIFY(probes.completed()<count);
  probes.start(o,ids.mid(0,3),net.url());
  QVERIFY(QTest::qWaitFor([&]{return !probes.busy();},10000));QCOMPARE(probes.succeeded(),3);
  QVERIFY(QTest::qWaitFor([&]{return probes.findChildren<ProxyEngine *>(QString(),Qt::FindDirectChildrenOnly).isEmpty();},3000));
 }
 void nativeProbeAndUnsupportedUseRustOnly(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  NodeTestService probes;probes.start(o,{o.selectedNodeId},net.url());QVERIFY(QTest::qWaitFor([&]{return !probes.busy();},6000));
  QCOMPARE(probes.succeeded(),1);QCOMPARE(probes.result(o.selectedNodeId).value("engineKind").toString(),QString("rust"));
  QCOMPARE(probes.result(o.selectedNodeId).value("metricType").toString(),QString("http_headers"));
  QCOMPARE(probes.result(o.selectedNodeId).value("resolverPolicy").toString(),QString("isolated_default_dns"));
  o.nodes.first().protocol="ss";o.nodes.first().password="synthetic";o.nodes.first().cipher="2022-blake3-aes-128-gcm";
  probes.start(o,{o.selectedNodeId},net.url());QVERIFY(!probes.result(o.selectedNodeId).value("success").toBool());
  QVERIFY(QTest::qWaitFor([&]{return !probes.busy();},3000));QCOMPARE(probes.failed(),1);
  QCOMPARE(probes.result(o.selectedNodeId).value("engineKind").toString(),QString("rust"));
 }
 void nodeListShowsValidatedOutboundSetupTime(){
  ControlledNetwork net;QVERIFY(net.start());QTemporaryDir directory;
  EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,directory.filePath("nodes.dpapi"),true);
  const auto body=QJsonDocument(QJsonObject{{"proxies",QJsonArray{QJsonObject{{"name","fixture"},{"type","socks5"},{"server","127.0.0.1"},{"port",net.a.serverPort()}}}}}).toJson();
  controller.imports()->importText(QString::fromUtf8(body));
  QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),4000);
  QCOMPARE(controller.nodeCatalog().size(),1);
  const auto id=controller.nodeCatalog().first().toMap().value("id").toString();
  controller.testSelectedNode(id,net.url());
  QTRY_VERIFY_WITH_TIMEOUT(!controller.tests()->busy(),6000);
  const auto result=controller.tests()->result(id);
  QVERIFY(result.value("success").toBool());
  QVERIFY(result.contains("outboundConnectMs"));
  const auto outbound=result.value("outboundConnectMs").toInt();
  QVERIFY(outbound>=0);
  QVERIFY(result.value("latency").toInt()>=outbound);
  QCOMPARE(controller.nodes().first().toMap().value("latency").toString(),QString::number(outbound));
 }
 void nodeBatchReusesBoundedRustWorkersAndReleasesListeners(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);o.nodes.clear();
  QStringList ids;
  for(int index=0;index<8;++index){
   ProxyNode node;node.id=QUuid::createUuid().toString(QUuid::WithoutBraces);node.name=QString("batch-%1").arg(index);node.protocol="socks5";node.host="127.0.0.1";
   node.port=index%2?net.b.serverPort():net.a.serverPort();
   if(index%2){node.username=QString::fromUtf8(net.b.username);node.password=QString::fromUtf8(net.b.password);}
   o.nodes.append(node);ids.append(node.id);
  }
  auto unsupported=o.nodes.first();unsupported.id=QUuid::createUuid().toString(QUuid::WithoutBraces);unsupported.protocol="tuic";unsupported.password="synthetic";o.nodes.append(unsupported);ids.insert(4,unsupported.id);
  NodeTestService probes;QSet<QString> sessions;QSet<quint16> listeners;int maxWorkers=0,uiTicks=0;
  QTimer heartbeat;heartbeat.setInterval(10);connect(&heartbeat,&QTimer::timeout,this,[&]{++uiTicks;});heartbeat.start();
  connect(&probes,&NodeTestService::changed,this,[&]{
   const auto workers=probes.findChildren<ProxyEngine *>(QString(),Qt::FindDirectChildrenOnly);int active=0;
   for(const auto *worker:workers){const auto status=worker->status();if(status.processAlive){++active;sessions.insert(status.sessionId);listeners.insert(quint16(status.proxyPort));}}
   maxWorkers=qMax(maxWorkers,active);
  });
  probes.start(o,ids,net.url());QTRY_VERIFY_WITH_TIMEOUT(!probes.busy(),10000);
  QCOMPARE(probes.total(),9);QCOMPARE(probes.completed(),9);QCOMPARE(probes.succeeded(),8);QCOMPARE(probes.failed(),1);
  QCOMPARE(probes.result(unsupported.id).value("phase").toString(),QString("configuration"));
  QCOMPARE(net.a.forwarded,4);QCOMPARE(net.b.forwarded,4);QCOMPARE(net.httpRequests,8);
  QVERIFY(!sessions.contains(QString()));QCOMPARE(sessions.size(),3);QCOMPARE(maxWorkers,3);QVERIFY(uiTicks>5);
  for(const auto &id:ids)if(id!=unsupported.id){const auto result=probes.result(id);QVERIFY(result.value("success").toBool());QCOMPARE(result.value("http").toInt(),200);QVERIFY(result.value("outboundConnectMs").toLongLong()>=0);}
  for(const auto port:listeners){QTcpServer listener;QVERIFY2(listener.listen(QHostAddress::LocalHost,port),qPrintable(listener.errorString()));}
  // Cancelling while start messages are queued must drain worker-owned handles.
  probes.start(o,ids,net.url());probes.cancel();QTRY_VERIFY_WITH_TIMEOUT(!probes.busy(),5000);QCOMPARE(probes.completed(),0);
  probes.start(o,{ids.first()},net.url());QTRY_VERIFY_WITH_TIMEOUT(!probes.busy(),5000);QCOMPARE(probes.succeeded(),1);
 }
 void nativeHeadProbeFinishesAtHeadersAndReportsHttpFailureStage(){
  ControlledNetwork net;QVERIFY(net.start());QTcpServer origin;QVERIFY(origin.listen(QHostAddress::LocalHost,0));
  net.a.targetPorts.append(origin.serverPort());
  bool sawHead=false,returnFailure=false,holdHeaders=false;int requests=0;
  auto bodySent=std::make_shared<bool>(false);auto headersReleased=std::make_shared<int>(0);
  connect(&origin,&QTcpServer::newConnection,&origin,[&]{
   while(origin.hasPendingConnections()){
    auto *socket=origin.nextPendingConnection();
    connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
    connect(socket,&QTcpSocket::readyRead,socket,[&,socket,bodySent]{
     auto request=socket->property("headers").toByteArray()+socket->readAll();socket->setProperty("headers",request);
     if(!request.contains("\r\n\r\n")||socket->property("responded").toBool())return;
     socket->setProperty("responded",true);sawHead=request.startsWith("HEAD ");++requests;
     if(holdHeaders){
      QPointer<QTcpSocket> guard(socket);
      QTimer::singleShot(500,&origin,[guard,headersReleased]{++*headersReleased;if(guard)guard->write("HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");});
      return;
     }
     if(returnFailure){socket->write("HTTP/1.1 503 Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");socket->disconnectFromHost();return;}
     socket->write("HTTP/1.1 200 OK\r\nContent-Length: 1048576\r\nConnection: keep-alive\r\n\r\n");
     QTimer::singleShot(2500,socket,[socket,bodySent]{*bodySent=true;socket->write("delayed-body");});
    });
   }
  });
  auto o=options(net);auto second=o.nodes.first();second.id=QUuid::createUuid().toString(QUuid::WithoutBraces);o.nodes.append(second);
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
  const QUrl url(QStringLiteral("http://127.0.0.1:%1/headers").arg(origin.serverPort()));
  engine.probeNode(url);QTRY_COMPARE_WITH_TIMEOUT(engine.status().requestState,ProxyEngine::RequestState::Succeeded,3000);
  QVERIFY(sawHead);QVERIFY(!*bodySent);QCOMPARE(engine.status().responseCode,200);QVERIFY(engine.status().latencyMs>=0);
  QVERIFY(engine.probeOutboundConnectMs()>=0);QCOMPARE(engine.probeOriginTlsMs(),qint64(-1));
  returnFailure=true;engine.probeNode(url);
  QTRY_COMPARE_WITH_TIMEOUT(engine.status().requestState,ProxyEngine::RequestState::Failed,3000);
  QCOMPARE(engine.probeFailureStage(),QString("http_status"));QCOMPARE(engine.status().responseCode,503);
  QCOMPARE(engine.status().nodeHealth,ProxyEngine::NodeHealth::Unknown);
  QCOMPARE(engine.status().latencyMs,-1);QVERIFY(engine.status().nodeMessage.contains("http_status"));
  NodeTestService probes;probes.start(o,{o.selectedNodeId},url);
  QTRY_VERIFY_WITH_TIMEOUT(!probes.busy(),5000);
  QCOMPARE(probes.failed(),1);QCOMPARE(probes.result(o.selectedNodeId).value("phase").toString(),QString("http_status"));
  QCOMPARE(probes.result(o.selectedNodeId).value("http").toInt(),503);
  holdHeaders=true;returnFailure=false;auto before=requests;
  engine.probeNode(url);QTRY_VERIFY_WITH_TIMEOUT(requests>before,1500);QVERIFY(engine.status().nodeBusy);
  engine.selectNode(second.id);QCOMPARE(engine.status().selectedNodeId,second.id);
  QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);QCOMPARE(engine.status().latencyMs,-1);
  QTRY_COMPARE_WITH_TIMEOUT(*headersReleased,1,1500);engine.refresh();
  QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
  before=requests;engine.probeNode(url);QTRY_VERIFY_WITH_TIMEOUT(requests>before,1500);
  engine.stop();
  QTRY_COMPARE_WITH_TIMEOUT(*headersReleased,2,1500);
  QCOMPARE(engine.status().state,ProxyEngine::State::Stopped);
  QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
 }
 void switchingNodesClearsOldHttpTiming(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  auto second=o.nodes.first();second.id=QUuid::createUuid().toString(QUuid::WithoutBraces);second.port=net.b.serverPort();o.nodes.append(second);
  RustCoreEngine engine;engine.start(o);QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
  engine.probeNode(net.url());
  QVERIFY(QTest::qWaitFor([&]{return engine.status().requestState==ProxyEngine::RequestState::Succeeded;},5000));
  QVERIFY(engine.status().latencyMs>=0);QCOMPARE(engine.status().responseCode,200);
  engine.probeNode(net.url());QCOMPARE(engine.status().latencyMs,-1);QCOMPARE(engine.status().responseCode,0);
  QVERIFY(QTest::qWaitFor([&]{return engine.status().requestState==ProxyEngine::RequestState::Succeeded;},5000));
  engine.selectNode(second.id);QCOMPARE(engine.status().selectedNodeId,second.id);
  QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
  QCOMPARE(engine.status().nodeHealth,ProxyEngine::NodeHealth::Unknown);
  QCOMPARE(engine.status().latencyMs,-1);QCOMPARE(engine.status().responseCode,0);
  engine.stop();
 }
 void forwardingFailuresAreRetainedOnceWithoutPrivateTargets(){
  ControlledNetwork net;QVERIFY(net.start());auto o=options(net);
  QTcpServer closed;QVERIFY(closed.listen(QHostAddress::LocalHost,0));o.nodes.first().port=closed.serverPort();closed.close();
  o.nodes.first().name="PRIVATE-NODE-NAME";
  RustCoreEngine engine;QSignalSpy diagnostics(&engine,&ProxyEngine::diagnostic);
  const auto failures=[&]{QStringList result;for(const auto &event:diagnostics)if(event[1].toString()=="ForwardingFailed")result.append(event[2].toString());return result;};
  const auto failRequest=[&]{
   QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",o.proxyPort));
   QNetworkRequest request(QUrl("http://PRIVATE-TARGET.invalid:8080/PRIVATE-PATH?token=PRIVATE-TOKEN"));request.setTransferTimeout(3000);
   auto *reply=client.get(request);QVERIFY(QTest::qWaitFor([&]{return reply->isFinished();},4000));QVERIFY(reply->error()!=QNetworkReply::NoError);
  };
  engine.start(o);QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
  failRequest();
  QTRY_COMPARE_WITH_TIMEOUT(failures().size(),1,3000);
  const auto message=failures().first();QVERIFY(message.contains("tcp_connect"));QVERIFY(message.contains("UpstreamConnectionRefused"));
  QVERIFY(!message.contains("PRIVATE",Qt::CaseInsensitive));QVERIFY(!message.contains(o.selectedNodeId));QVERIFY(message.contains(QRegularExpression("节点 #[0-9a-f]{12} ·")));
  engine.refresh();engine.refresh();QCOMPARE(failures().size(),1);engine.stop();QCOMPARE(failures().size(),1);
  // A new Rust runtime reuses connection ordinals; it must not inherit the old
  // dedup state, and the final pre-stop snapshot must remain observable.
  engine.start(o);QVERIFY(engine.status().apiHealthy);failRequest();engine.stop();QCOMPARE(failures().size(),2);
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
