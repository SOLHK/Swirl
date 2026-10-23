#include "engine/RustCoreEngine.h"
#include "engine/NodeTestService.h"
#include "engine/TelemetryService.h"
#include "engine/NodeStore.h"
#include "engine/NodeRegion.h"
#include "engine/NodeImporter.h"
#include "engine/NodeImportService.h"
#include "engine/EngineController.h"
#include "engine/ThreadedEngine.h"
#include "app/StoragePaths.h"
#include <QSettings>
#include <QStandardPaths>
#include "ControlledNetwork.h"
#include <QCoreApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTest>
#include <QUuid>
#include <QJsonArray>
#include <QSaveFile>
#include <QFileInfo>
#include <QUdpSocket>

static quint16 freePort(){
    QTcpServer tcp;QUdpSocket udp;
    for(int attempt=0;attempt<16;++attempt){
        if(!tcp.listen(QHostAddress::LocalHost,0))return 0;
        if(udp.bind(QHostAddress::LocalHost,tcp.serverPort(),QUdpSocket::DontShareAddress))return tcp.serverPort();
        tcp.close();
    }
    return 0;
}
static ProxyNode node(QString name,quint16 port){ProxyNode n;n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);n.name=name;n.protocol="socks5";n.host="127.0.0.1";n.port=port;return n;}
class NodeTests:public QObject {
    Q_OBJECT
    EngineStartOptions options() {
        EngineStartOptions options;options.proxyPort=freePort();options.routingMode="global";
        options.startupTimeoutMs=10000;options.healthIntervalMs=500;return options;
    }
    QByteArray fetch(ControlledNetwork &net,quint16 proxyPort,bool tls=false) {
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",proxyPort));
        QNetworkRequest request(net.url(tls));request.setAttribute(QNetworkRequest::Http2AllowedAttribute,false);request.setRawHeader("Connection","close");
        if(tls){auto ssl=QSslConfiguration::defaultConfiguration();ssl.addCaCertificate(net.certificate);request.setSslConfiguration(ssl);}
        auto *reply=client.get(request);QSignalSpy done(reply,&QNetworkReply::finished);
        if(!done.wait(8000)){qInfo()<<"FIXTURE_TIMEOUT relays"<<net.a.forwarded<<net.b.forwarded<<"origins"<<net.httpRequests<<net.httpsRequests<<"sslBackend"<<QSslSocket::activeBackend();reply->abort();return "REQUEST_TIMEOUT";}
        const auto body=reply->readAll();const int code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if(reply->error()!=QNetworkReply::NoError || code!=200){qInfo()<<"FIXTURE_REQUEST_FAILURE HTTP"<<code<<"networkError"<<int(reply->error())<<reply->errorString()<<"relays"<<net.a.forwarded<<net.b.forwarded<<"origins"<<net.httpRequests<<net.httpsRequests;return QByteArray("REQUEST_ERROR_")+QByteArray::number(reply->error());}
        return body;
    }
private slots:
    void initTestCase(){QStandardPaths::setTestModeEnabled(true);SwirlPaths::initializeTestStorage();QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation));}
    void init(){QSettings().clear();}
    void probesNeverInheritNetworkOwnership(){
        auto source=options();source.tunEnabled=true;source.gatewayForwarding=true;source.allowLan=true;source.meteredNetwork=true;
        source.meteredAllowlist={"Codex.exe"};source.lanUsername="private";source.lanPassword="private";
        source.inboundUsername="private";source.inboundPassword="private";source.directSession=true;
        source.dnsConfig={{"mode",2},{"servers","198.18.0.1"}};source.customRules={"MATCH,REJECT"};
        source.customGroups={QVariantMap{{"name","stale"},{"type","select"},{"proxies",QStringList{"DIRECT"}}}};
        const auto isolated=NodeTestService::isolatedOptions(source);
        QVERIFY(!isolated.tunEnabled);QVERIFY(!isolated.gatewayForwarding);QVERIFY(!isolated.allowLan);QVERIFY(!isolated.meteredNetwork);
        QVERIFY(!isolated.directSession);QVERIFY(isolated.dnsConfig.isEmpty());QVERIFY(isolated.customRules.isEmpty());QVERIFY(isolated.customGroups.isEmpty());
        QVERIFY(isolated.lanPassword.isEmpty());QVERIFY(isolated.inboundPassword.isEmpty());QCOMPARE(isolated.routingMode,QString("global"));
        QCOMPARE(isolated.nodes.size(),source.nodes.size());QVERIFY(!isolated.smartRouting);
    }

    void regionLabelsDoNotInventLocations() {
        QCOMPARE(NodeRegion::fromName(QStringLiteral("🇭🇰 HK 01")).code,QString("HK"));
        QCOMPARE(NodeRegion::fromName(QStringLiteral("日本 东京 02")).code,QString("JP"));
        QCOMPARE(NodeRegion::fromName(QStringLiteral("SG-03")).code,QString("SG"));
        QCOMPARE(NodeRegion::fromName(QStringLiteral("印度尼西亚 01")).code,QString("ID"));
        QCOMPARE(NodeRegion::fromName(QStringLiteral("🇳🇿 Auckland")).code,QString("NZ"));
        QCOMPARE(NodeRegion::fromName(QStringLiteral("business proxy")).code,QString("unknown"));
        QCOMPARE(NodeRegion::fromName(QStringLiteral("JPX private")).code,QString("unknown"));
        QCOMPARE(NodeRegion::fromName(QStringLiteral("节点 001")).code,QString("unknown"));
    }
    void selectingDoesNotRewriteCredentialsOrInvalidateRows() {
        QTemporaryDir temp;const auto path=temp.filePath("nodes.dpapi");NodeStore store(path);
        QList<ProxyNode> nodes;for(int i=0;i<180;++i)nodes.append(node(QString("HK node %1").arg(i),quint16(1080+i)));
        QVERIFY(store.importNodes(nodes));
        QFile encrypted(path);QVERIFY(encrypted.open(QIODevice::ReadOnly));const auto original=encrypted.readAll();encrypted.close();
        QSignalSpy changed(&store,&NodeStore::changed),selection(&store,&NodeStore::selectionChanged);
        const auto first=nodes.first().id,last=nodes.last().id;
        QVERIFY(store.select(first));QVERIFY(store.select(last));QVERIFY(store.select(last));
        QCOMPARE(changed.size(),0);QCOMPARE(selection.size(),2);
        QVERIFY(encrypted.open(QIODevice::ReadOnly));QCOMPARE(encrypted.readAll(),original);encrypted.close();
        NodeStore loaded(path);QCOMPARE(loaded.selectedId(),last);QCOMPARE(loaded.nodes().size(),180);
        QVERIFY(loaded.removeNode(last));NodeStore removed(path);QVERIFY(removed.selectedId().isEmpty());
        QVERIFY(removed.select(first));QVERIFY(removed.select({}));NodeStore cleared(path);QVERIFY(cleared.selectedId().isEmpty());
        QFile sidecar(path+".selected");QVERIFY(sidecar.open(QIODevice::WriteOnly));sidecar.write("{\"selected\":\"nonexistent\"}");sidecar.close();
        NodeStore stale(path);QVERIFY(stale.selectedId().isEmpty());
        QVERIFY(QFile::remove(path+".selected"));QVERIFY(QDir().mkdir(path+".selected"));
        QVERIFY(!stale.select(first));QVERIFY(stale.selectedId().isEmpty());QVERIFY(!stale.error().isEmpty());
    }
    void selectionLeavesCatalogAndNodeRowsStable() {
        QTemporaryDir temp;EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,temp.filePath("catalog.dpapi"));
        QVERIFY(controller.saveNode({{"name","HK fixture"},{"protocol","http"},{"host","127.0.0.1"},{"port",9}}));
        const auto id=controller.nodes().first().toMap().value("id").toString();
        QSignalSpy catalog(&controller,&EngineController::nodeCatalogChanged),rows(&controller,&EngineController::nodesChanged);
        QVERIFY(controller.chooseNode(id));QCOMPARE(catalog.size(),0);QCOMPARE(rows.size(),0);
        QCOMPARE(controller.nodeCatalog().first().toMap().value("regionCode").toString(),QString("HK"));
        QVERIFY(controller.saveNode({{"id",id},{"name","JP fixture"},{"protocol","http"},{"host","127.0.0.1"},{"port",9}}));
        QCOMPARE(catalog.size(),1);QCOMPARE(controller.nodeCatalog().first().toMap().value("regionCode").toString(),QString("JP"));
    }
    void userAuthorizedLiveSubscription() {
        const auto subscription=qEnvironmentVariable("SWIRL_LIVE_SUBSCRIPTION_URL");
        if(subscription.isEmpty())QSKIP("Requires an explicitly user-authorized subscription supplied in the environment");
        QTemporaryDir privateData;QVERIFY(privateData.isValid());NodeStore store(privateData.filePath("nodes.dpapi"));NodeImportService importer(&store);
        QVERIFY(importer.saveSubscription({},"User authorized test",QUrl(subscription),360,false,qEnvironmentVariable("SWIRL_LIVE_FORMAT_HINT","auto")));
        const auto source=store.subscriptions().first().id;importer.refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!importer.busy(),35000);
        bool usedProxy=false;
        if(store.nodes().isEmpty()&&qEnvironmentVariableIntValue("SWIRL_LIVE_DOWNLOAD_PROXY_PORT")>0){usedProxy=true;importer.setDownloadProxy(qEnvironmentVariableIntValue("SWIRL_LIVE_DOWNLOAD_PROXY_PORT"));importer.refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!importer.busy(),35000);}
        QVERIFY2(!store.nodes().isEmpty(),qPrintable(importer.message()));
        NodeStore reloaded(privateData.filePath("nodes.dpapi"));QCOMPARE(reloaded.nodes().size(),store.nodes().size());
        QFile encrypted(store.filePath());QVERIFY(encrypted.open(QIODevice::ReadOnly));QVERIFY(!encrypted.readAll().contains(subscription.toUtf8()));encrypted.close();
        auto config=options();config.nodes=store.nodes();QStringList ids;QHash<QString,int> protocolCounts;
        // Bound account traffic while sampling multiple protocols/regions.
        const int requested=qEnvironmentVariableIntValue("SWIRL_LIVE_TEST_LIMIT");const int limit=requested>0?qBound(1,requested,60):12;
        for(const auto &node:config.nodes){++protocolCounts[node.protocol];if(ids.size()<limit)ids.append(node.id);}
        NodeTestService probes;probes.start(config,ids,QUrl("https://www.gstatic.com/generate_204"));QTRY_VERIFY_WITH_TIMEOUT(!probes.busy(),((ids.size()+2)/3)*45000+5000);
        QJsonArray rows;QStringList available;
        for(int i=0;i<ids.size();++i){const auto result=probes.result(ids[i]);QString protocol;for(const auto &node:config.nodes)if(node.id==ids[i])protocol=node.protocol;
            rows.append(QJsonObject{{"node",QString("node-%1").arg(i+1,3,10,QChar('0'))},{"protocol",protocol},{"success",result.value("success").toBool()},{"latencyMs",result.value("latency").toInt()},{"httpStatus",result.value("http").toInt()},{"diagnostic",result.value("error").toString()}});
            if(result.value("success").toBool())available.append(ids[i]);}
        std::sort(available.begin(),available.end(),[&](const auto &a,const auto &b){return probes.result(a).value("latency").toInt()<probes.result(b).value("latency").toInt();});
        QJsonArray transfers;int passed=0;
        for(const auto &id:available.mid(0,3)){
            config.selectedNodeId=id;config.proxyPort=freePort();RustCoreEngine engine;engine.start(config);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,20000);
            QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",config.proxyPort));
            for(const auto &url:{QUrl("http://www.msftconnecttest.com/connecttest.txt"),QUrl("https://www.gstatic.com/generate_204")}){
                QNetworkRequest request(url);request.setTransferTimeout(15000);request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);auto *reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),18000);
                const int status=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();const bool ok=reply->error()==QNetworkReply::NoError&&status>=200&&status<300;if(ok)++passed;
                transfers.append(QJsonObject{{"node",QString("node-%1").arg(ids.indexOf(id)+1,3,10,QChar('0'))},{"scheme",url.scheme()},{"success",ok},{"httpStatus",status},{"networkError",int(reply->error())},{"bodyBytes",reply->readAll().size()}});reply->deleteLater();
            }engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
        }
        QJsonObject reconnect{{"attempted",false}};
        if(!available.isEmpty()){
            EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,store.filePath());controller.setProxyPort(freePort());
            const auto id=available.first();controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),25000);const auto oldPid=controller.processId();
            controller.imports()->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),35000);
            QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),25000);QCOMPARE(controller.processId(),oldPid);
            controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
            controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),25000);QCOMPARE(controller.activeNodeId(),id);
            QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",controller.activeProxyPort()));QJsonArray requests;
            for(const auto &url:{QUrl("http://www.msftconnecttest.com/connecttest.txt"),QUrl("https://www.gstatic.com/generate_204")}){
                QNetworkRequest request(url);request.setTransferTimeout(15000);auto reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),18000);const int code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();const bool ok=reply->error()==QNetworkReply::NoError&&code>=200&&code<300;
                requests.append(QJsonObject{{"scheme",url.scheme()},{"httpStatus",code},{"success",ok}});QVERIFY(ok);
            }
            reconnect={{"attempted",true},{"explicitReconnect",true},{"selectedNodePreserved",true},{"engine",controller.engineName()},{"requests",requests}};controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
        }
        QJsonObject protocols;for(auto i=protocolCounts.cbegin();i!=protocolCounts.cend();++i)protocols[i.key()]=i.value();
        const QJsonObject report{{"importedNodes",config.nodes.size()},{"protocolCounts",protocols},{"downloadUsedExistingLocalProxy",usedProxy},{"sampledNodes",ids.size()},{"successfulProbes",available.size()},{"probes",rows},{"transfers",transfers},{"refreshReconnect",reconnect}};
        const auto output=qEnvironmentVariable("SWIRL_LIVE_REPORT");if(!output.isEmpty()){QSaveFile file(output);QVERIFY(file.open(QIODevice::WriteOnly));file.write(QJsonDocument(report).toJson());QVERIFY(file.commit());}
        qInfo()<<"LIVE_SUBSCRIPTION imported="<<config.nodes.size()<<"sampled="<<ids.size()<<"available="<<available.size()<<"successfulRequests="<<passed;
        QVERIFY(!available.isEmpty());QCOMPARE(passed,qMin(3,available.size())*2);
    }
    void unsupportedNetworkOwnershipFailsBeforeListening() {
        for(int mode=0;mode<4;++mode){auto config=options();config.directSession=true;
            config.meteredNetwork=mode==0;config.tunEnabled=mode==1;config.allowLan=mode==2;config.gatewayForwarding=mode==3;
            RustCoreEngine engine;engine.start(config);QCOMPARE(engine.status().state,ProxyEngine::State::Failed);
            QCOMPARE(engine.status().error,ProxyEngine::Error::InvalidOptions);QVERIFY(!engine.status().apiHealthy);
            QTcpServer unused;QVERIFY(unused.listen(QHostAddress::LocalHost,config.proxyPort));
        }
    }
    void explicitDirectAndAuthenticatedLoopbackListener() {
        ControlledNetwork net;QVERIFY(net.start());auto config=options();config.directSession=true;config.routingMode="direct";
        RustCoreEngine engine;engine.start(config);QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
        QVERIFY(engine.status().directSession);QCOMPARE(fetch(net,config.proxyPort),QByteArray("DIRECT-BYPASS"));
        QCOMPARE(fetch(net,config.proxyPort,true),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded+net.b.forwarded,0);
        // A missing selected node cannot silently become DIRECT after changing mode.
        engine.setRoutingMode("global");QCOMPARE(engine.status().mode,QString("direct"));engine.stop();
        config.inboundUsername="fixture";config.inboundPassword="test-password-only";engine.start(config);
        QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
        const auto request=[&](const QString &password){QNetworkAccessManager client;
            client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",config.proxyPort,config.inboundUsername,password));
            QNetworkRequest input(net.url());input.setTransferTimeout(3000);auto *reply=client.get(input);
            if(!QTest::qWaitFor([&]{return reply->isFinished();},4000)){reply->abort();return QByteArray("TIMEOUT");}
            return reply->error()==QNetworkReply::NoError?reply->readAll():QByteArray("REJECTED");};
        const auto before=net.httpRequests;QCOMPARE(request("wrong-password"),QByteArray("REJECTED"));QCOMPARE(net.httpRequests,before);
        QCOMPARE(request(config.inboundPassword),QByteArray("DIRECT-BYPASS"));engine.stop();QVERIFY(!engine.status().processAlive);
    }
    void customDnsRulesAndGroupsReachRust() {
        ControlledNetwork network;QVERIFY(network.start());
        auto opts=options();opts.nodes={node("A",network.a.serverPort())};opts.selectedNodeId=opts.nodes.first().id;
        opts.dnsConfig={{"mode",0},{"hosts",QVariantList{QVariantMap{{"name","fixture.test"},{"value","127.0.0.1"}}}}};
        opts.customGroups={QVariantMap{{"name","Custom"},{"type","select"},{"proxies",QStringList{"DIRECT"}}}};
        opts.customRules={"DOMAIN,fixture.test,Custom"};opts.routingMode="rule";
        RustCoreEngine engine;engine.start(opts);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);
        QJsonObject mapped;QVERIFY(RustCoreEngine::configuration(opts,&mapped).isEmpty());
        QVERIFY(QJsonDocument(mapped).toJson().contains("fixture.test"));QCOMPARE(mapped.value("selectors").toArray().size(),1);
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",opts.proxyPort));
        auto destination=network.url();destination.setHost("fixture.test");QNetworkRequest request(destination);request.setRawHeader("Connection","close");
        auto *reply=client.get(request);QSignalSpy done(reply,&QNetworkReply::finished);QVERIFY(done.wait(8000));QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("DIRECT-BYPASS"));
        QCOMPARE(network.a.forwarded,0);QVERIFY(network.httpRequests>0);
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
    }
    void explicitDomainRulesRemainOrderedAheadOfChinaFallback() {
        auto opts=options();opts.nodes={node("Selected",9)};opts.selectedNodeId=opts.nodes.first().id;
        opts.smartRouting=true;opts.routingMode="rule";
        for(const auto &domain:{"chatgpt.com","openai.com","oaistatic.com","oaiusercontent.com","auth0.com","statsigapi.net"})
            opts.customRules.append(QString("DOMAIN-SUFFIX,%1,SWIRL").arg(domain));
        QJsonObject config;QVERIFY(RustCoreEngine::configuration(opts,&config).isEmpty());
        QVERIFY(config.value("smart_routing").toBool());const auto rules=config.value("rules").toArray();QCOMPARE(rules.size(),6);
        for(int i=0;i<rules.size();++i){const auto row=rules[i].toObject();QCOMPARE(row.value("outbound").toString(),opts.selectedNodeId);
            QCOMPARE(row.value("matcher").toObject().value("value").toString(),opts.customRules[i].split(',')[1]);}
    }
    void inProcessControlNeedsNoRestListener() {
        QTcpServer occupied;QVERIFY(occupied.listen(QHostAddress::LocalHost,0));auto opts=options();
        opts.directSession=true;
        RustCoreEngine engine;engine.start(opts);QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
        QCOMPARE(engine.status().controlEndpoint,QString("in-process://SwirlRust/v1"));QVERIFY(occupied.isListening());
        QCOMPARE(engine.status().processId,QCoreApplication::applicationPid());engine.stop();QVERIFY(!engine.status().processAlive);
    }
    void isolatedBatchNeverChangesMainSelection() {
        ControlledNetwork network;QVERIFY(network.start());network.b.reject=true;
        auto opts=options();opts.nodes={node("A",network.a.serverPort()),node("B",network.b.serverPort())};opts.selectedNodeId=opts.nodes.first().id;
        RustCoreEngine main;main.start(opts);QTRY_VERIFY_WITH_TIMEOUT(main.status().apiHealthy,18000);const auto pid=main.status().processId;
        auto probeOptions=opts;probeOptions.tunEnabled=true;probeOptions.gatewayForwarding=true;probeOptions.allowLan=true;probeOptions.meteredNetwork=true;
        probeOptions.customRules={"MATCH,REJECT"};probeOptions.dnsConfig={{"mode",2},{"servers","198.18.0.1"}};
        NodeTestService tests;tests.start(probeOptions,{opts.nodes[0].id,opts.nodes[1].id},network.url());
        QTRY_VERIFY_WITH_TIMEOUT(!tests.busy(),45000);
        if(tests.succeeded()!=1 || tests.result(opts.nodes[1].id).value("phase").toString()!="outbound_handshake")qInfo()<<"BATCH_RESULT"<<tests.results();
        QCOMPARE(tests.completed(),2);QCOMPARE(tests.succeeded(),1);QCOMPARE(tests.failed(),1);QVERIFY(tests.result(opts.nodes[0].id).value("success").toBool());QVERIFY(!tests.result(opts.nodes[1].id).value("success").toBool());
        QCOMPARE(tests.result(opts.nodes[1].id).value("phase").toString(),QString("outbound_handshake"));
        QCOMPARE(main.status().selectedNodeId,opts.nodes.first().id);QCOMPARE(main.status().processId,pid);
        // Native probes perform one real request, without the legacy adapter's
        // extra availability request. Prove the main route independently.
        QCOMPARE(tests.result(opts.nodes[0].id).value("engineKind").toString(),QString("rust"));
        const auto beforeMainRequest=network.a.forwarded;
        main.probeNode(network.url());QTRY_COMPARE_WITH_TIMEOUT(main.status().requestState,ProxyEngine::RequestState::Succeeded,10000);
        QVERIFY(network.a.forwarded>beforeMainRequest);QVERIFY(network.a.forwarded>=2);
        tests.start(opts,{opts.nodes[0].id,opts.nodes[1].id},network.url());tests.cancel();QTRY_VERIFY_WITH_TIMEOUT(!tests.busy(),5000);main.stop();QTRY_VERIFY_WITH_TIMEOUT(!main.status().processAlive,4000);
    }
    void authenticTrafficStreamAndConnectionHistory() {
        ControlledNetwork network;QVERIFY(network.start());QTcpServer origin;QVERIFY(origin.listen(QHostAddress::LocalHost,0));network.a.targetPorts.append(origin.serverPort());
        connect(&origin,&QTcpServer::newConnection,&origin,[&]{auto socket=origin.nextPendingConnection();connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);connect(socket,&QTcpSocket::readyRead,socket,[socket]{socket->readAll();if(socket->property("sent").toBool())return;socket->setProperty("sent",true);socket->write("HTTP/1.1 200 OK\r\nContent-Length: 65536\r\nConnection: close\r\n\r\n");auto timer=new QTimer(socket);timer->setInterval(100);connect(timer,&QTimer::timeout,socket,[socket,timer]{socket->write(QByteArray(2048,'x'));const auto n=socket->property("chunks").toInt()+1;socket->setProperty("chunks",n);if(n==32){timer->stop();socket->disconnectFromHost();}});timer->start();});});
        auto opts=options();opts.nodes={node("A",network.a.serverPort())};opts.selectedNodeId=opts.nodes.first().id;RustCoreEngine engine;QTemporaryDir temp;TelemetryService model(temp.filePath("history"),false);connect(&engine,&ProxyEngine::statusChanged,&model,[&]{model.ingest(engine.status());});engine.start(opts);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",opts.proxyPort));auto reply=client.get(QNetworkRequest(QUrl(QString("http://127.0.0.1:%1/real-stream").arg(origin.serverPort()))));QTRY_VERIFY_WITH_TIMEOUT(model.sampled()&&model.downloadRate()>0,6000);QTRY_VERIFY_WITH_TIMEOUT(!model.connections().isEmpty(),6000);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),7000);QCOMPARE(reply->readAll().size(),65536);QTRY_VERIFY_WITH_TIMEOUT(model.summary().value("total").toDouble()>=65536,4000);QVERIFY(!model.ranking("domains").isEmpty());QTRY_VERIFY_WITH_TIMEOUT(model.activeConnections()==0,4000);QVERIFY(!model.connections().isEmpty());engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
    }
    void unsupportedImportedProtocolIsPreservedButCannotStart() {
        // Hysteria2 itself is implemented. Port hopping is still unsupported
        // and must survive persistence without silently becoming single-port.
        const auto parsed=NodeImporter::parse(R"({"name":"pending","type":"hysteria2","server":"127.0.0.1","port":443,"ports":"443-445","password":"private-test-only"})");
        QVERIFY2(bool(parsed),qPrintable(parsed.error));QTemporaryDir directory;NodeStore store(directory.filePath("nodes"));
        QVERIFY(store.importNodes(parsed.nodes));NodeStore loaded(store.filePath());QCOMPARE(loaded.nodes().size(),1);
        QCOMPARE(loaded.nodes().first().password,QString("private-test-only"));auto opts=options();
        opts.nodes=loaded.nodes();opts.selectedNodeId=opts.nodes.first().id;RustCoreEngine engine;engine.start(opts);
        QCOMPARE(engine.status().state,ProxyEngine::State::Failed);QCOMPARE(engine.status().error,ProxyEngine::Error::InvalidOptions);
        QVERIFY(!engine.status().message.contains("private-test-only"));QVERIFY(!engine.status().processAlive);
        QCOMPARE(loaded.nodes().first().protocol,QString("hysteria2"));
        QCOMPARE(loaded.nodes().first().parameters.value("ports").toString(),QString("443-445"));
    }
    void importedHysteria2StartsNativeListenerWithoutClaimingPeerHandshake() {
        const auto parsed=NodeImporter::parse(R"({"name":"native-hy2","type":"hysteria2","server":"127.0.0.1","port":443,"password":"private-test-only"})");
        QVERIFY2(parsed,qPrintable(parsed.error));auto opts=options();opts.nodes=parsed.nodes;opts.selectedNodeId=parsed.nodes.first().id;
        QJsonObject config;QVERIFY2(RustCoreEngine::configuration(opts,&config).isEmpty(),"Supported Hysteria2 must reach native configuration");
        QCOMPARE(config.value("nodes").toArray().first().toObject().value("outbound").toObject().value("type").toString(),QString("hysteria2"));
        RustCoreEngine engine;engine.start(opts);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,10000);
        QVERIFY(engine.status().processAlive);QVERIFY(!engine.status().message.contains("private-test-only"));
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,5000);
        qInfo()<<"HY2_NATIVE_LISTENER startup/stop verified; no remote QUIC handshake claimed";
    }
    void importedVlessKeepsTransportPrivate() {
        QTemporaryDir temp; const auto path=temp.filePath("import.dpapi"); NodeStore store(path);
        QVariantMap options{{"uuid","11111111-1111-4111-8111-111111111111"},{"network","ws"},
            {"ws-opts",QVariantMap{{"path","/private-path"},{"headers",QVariantMap{{"Host","edge.example.org"}}}}}};
        QVERIFY(store.saveNode({{"name","VLESS imported"},{"protocol","vless"},{"host","edge.example.org"},{"port",443},{"options",options}}));
        NodeStore loaded(path); QCOMPARE(loaded.nodes().size(),1);
        QVERIFY(!loaded.publicRows().first().toMap().contains("options"));
        QFile encrypted(path); QVERIFY(encrypted.open(QIODevice::ReadOnly));
        QVERIFY(!encrypted.readAll().contains("private-path"));
    }
    void oversizedStorePreservesPreviousFile() {
        QTemporaryDir temp;const auto path=temp.filePath("nodes.dat");NodeStore store(path);
        auto existing=node("existing",1080);auto input=existing.publicInfo();input.remove("id");
        QVERIFY(store.saveNode(input));QVERIFY(store.select(store.nodes().first().id));
        const auto selected=store.selectedId();QFile before(path);QVERIFY(before.open(QIODevice::ReadOnly));
        const auto previous=before.readAll();before.close();
        QList<ProxyNode> incoming;const QString payload(40*1024,u'x');
        for(int i=0;i<1000;++i) {
            // Distinct endpoints prevent semantic deduplication from reducing
            // the intended >32 MiB snapshot to one node.
            auto large=node(QStringLiteral("large-%1").arg(i),quint16(10000+i));
            large.parameters.insert("preserved-extension",payload);incoming.append(large);
        }
        NodeStore::ImportPlan plan;QVERIFY(store.prepareImport(incoming,{},&plan));QCOMPARE(plan.nodes().size(),1001);
        QVERIFY(!store.importNodes(incoming));QVERIFY(store.error().contains("32 MiB"));
        QFile after(path);QVERIFY(after.open(QIODevice::ReadOnly));QCOMPARE(after.readAll(),previous);
        QVERIFY(previous.size()<=NodeStore::MaximumBytes);
        NodeStore reloaded(path);QCOMPARE(reloaded.nodes().size(),1);QCOMPARE(reloaded.selectedId(),selected);
        QVERIFY(reloaded.error().isEmpty());
    }
    void encryptedPersistence() {
        QTemporaryDir temp;QVERIFY(temp.isValid());const auto path=temp.filePath("nodes.dat");
        NodeStore store(path);
        auto n=node("保存的节点",1080);n.username="test-user";n.password="fixture-private-secret";
        auto input=n.publicInfo();input.remove("id");input.insert("username",n.username);input.insert("password",n.password);
        QVERIFY(store.saveNode(input));QCOMPARE(store.nodes().size(),1);const auto id=store.nodes().first().id;
        QFile encrypted(path);QVERIFY(encrypted.open(QIODevice::ReadOnly));const auto bytes=encrypted.readAll();encrypted.close();
        QVERIFY(!bytes.contains(n.password.toUtf8()));QVERIFY(!bytes.contains(n.username.toUtf8()));QVERIFY(!bytes.contains(n.name.toUtf8()));
        QVERIFY(!store.publicRows().first().toMap().contains("password"));QVERIFY(!store.publicRows().first().toMap().contains("username"));
        QVERIFY(store.select(id));NodeStore loaded(path);QCOMPARE(loaded.selectedId(),id);QCOMPARE(loaded.nodes().first().password,n.password);
        auto edit=loaded.publicRows().first().toMap();edit.insert("name","修改后的节点");QVERIFY(loaded.saveNode(edit));QCOMPARE(loaded.nodes().first().password,n.password);
        NodeStore reloaded(path);QCOMPARE(reloaded.nodes().first().name,QString("修改后的节点"));QVERIFY(reloaded.removeNode(id));QVERIFY(reloaded.nodes().isEmpty());
        QVERIFY(encrypted.open(QIODevice::WriteOnly));encrypted.write("SWIRLNODE1\ncorrupted");encrypted.close();
        NodeStore corrupted(path);QVERIFY(!corrupted.error().isEmpty());QVERIFY(!corrupted.saveNode(input));
        QVERIFY(encrypted.open(QIODevice::ReadOnly));QCOMPARE(encrypted.readAll(),QByteArray("SWIRLNODE1\ncorrupted"));
    }
    void invalidParameters() {
        auto n=node("valid",1080);QVERIFY(ProxyNode::validate(n).isEmpty());
        n.host="http://user:secret@host";QVERIFY(!ProxyNode::validate(n).isEmpty());n.host="127.0.0.1";
        n.port=0;QVERIFY(!ProxyNode::validate(n).isEmpty());n.port=1080;
        n.protocol="vless";QVERIFY(!ProxyNode::validate(n).isEmpty());n.protocol="socks5";
        n.username="user";QVERIFY(!ProxyNode::validate(n).isEmpty());n.password="secret";QVERIFY(ProxyNode::validate(n).isEmpty());
        n.protocol="ss";n.cipher="";QVERIFY(!ProxyNode::validate(n).isEmpty());n.cipher="aes-128-gcm";QVERIFY(ProxyNode::validate(n).isEmpty());
        n.protocol="trojan";n.serverName="bad server";QVERIFY(!ProxyNode::validate(n).isEmpty());
    }
    void realHttpHttpsAndSwitch() {
        ControlledNetwork net;QVERIFY(net.start());auto config=options();
        auto a=node("A",net.a.serverPort()),b=node("B",net.b.serverPort());b.username=QString::fromUtf8(net.b.username);b.password=QString::fromUtf8(net.b.password);
        config.nodes={a,b};config.selectedNodeId=a.id;
        RustCoreEngine engine;engine.start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Running,16000);
        QCOMPARE(engine.status().nodeHealth,ProxyEngine::NodeHealth::Unknown);QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
        QVERIFY(!engine.configurationSummary().contains(b.password));QCOMPARE(fetch(net,config.proxyPort),QByteArray("exit-A"));
        QCOMPARE(fetch(net,config.proxyPort,true),QByteArray("exit-A"));QVERIFY(net.a.forwarded>=2);QCOMPARE(net.b.forwarded,0);QVERIFY(net.httpsRequests>0);
        engine.probeNode(net.url());QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,8000);
        QCOMPARE(engine.status().nodeHealth,ProxyEngine::NodeHealth::Available);QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::Succeeded);
        const auto pid=engine.status().processId;
        for(int i=0;i<6;++i){const bool toB=i%2==0;const auto id=toB?b.id:a.id;engine.selectNode(id);
            QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,5000);QCOMPARE(engine.status().selectedNodeId,id);QCOMPARE(engine.status().processId,pid);
            QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
            QCOMPARE(fetch(net,config.proxyPort,i%2==0),toB?QByteArray("exit-B"):QByteArray("exit-A"));}
        QVERIFY(net.b.forwarded>=3);QVERIFY(net.httpRequests>0);
        net.a.reject=true;engine.probeNode(net.url());QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,8000);
        QCOMPARE(engine.status().nodeHealth,ProxyEngine::NodeHealth::Unavailable);QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::Failed);
        QVERIFY(engine.status().processAlive);QVERIFY(engine.status().apiHealthy);
        net.a.reject=false;engine.probeNode(net.url());QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,8000);
        QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::Succeeded);
        engine.setRoutingMode("global");
        QTRY_VERIFY_WITH_TIMEOUT(engine.status().mode=="global"&&engine.status().apiHealthy,5000);
        QCOMPARE(fetch(net,config.proxyPort),QByteArray("exit-A"));
        engine.selectNode(b.id);QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,5000);
        QCOMPARE(fetch(net,config.proxyPort),QByteArray("exit-B"));
        const int forwards=net.a.forwarded+net.b.forwarded;
        engine.setRoutingMode("direct");
        QTRY_VERIFY_WITH_TIMEOUT(engine.status().mode=="direct"&&engine.status().apiHealthy,5000);
        QCOMPARE(fetch(net,config.proxyPort),QByteArray("DIRECT-BYPASS"));
        QCOMPARE(net.a.forwarded+net.b.forwarded,forwards);
        engine.setRoutingMode("rule");
        QTRY_VERIFY_WITH_TIMEOUT(engine.status().mode=="rule"&&engine.status().apiHealthy,5000);
        engine.selectNode(a.id);QTRY_VERIFY_WITH_TIMEOUT(!engine.status().nodeBusy,5000);
        QCOMPARE(fetch(net,config.proxyPort),QByteArray("exit-A"));
        engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);
        QVERIFY(engine.status().nodeMessage.isEmpty());QCOMPARE(engine.status().latencyMs,-1);QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
        QTcpServer reuse;QVERIFY(reuse.listen(QHostAddress::LocalHost,config.proxyPort));reuse.close();
        for(int i=0;i<3;++i){engine.start(config);QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Running,16000);
            QCOMPARE(fetch(net,config.proxyPort),QByteArray("exit-A"));engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);}
        qInfo()<<"CONTROLLED_CHAIN HTTP HTTPS exit-A/exit-B verified;"<<net.a.forwarded<<"A relays,"<<net.b.forwarded<<"B relays; no remote environment claimed";
    }
    void occupiedTcpPortCannotReportReady() {
        auto config=options();QTcpServer occupied;QVERIFY(occupied.listen(QHostAddress::LocalHost,0));
        config.directSession=true;config.proxyPort=occupied.serverPort();RustCoreEngine engine;engine.start(config);
        QCOMPARE(engine.status().state,ProxyEngine::State::Failed);QVERIFY(engine.status().message.contains("ListenerBind"));
        QVERIFY(!engine.status().apiHealthy);QVERIFY(!engine.status().processAlive);QVERIFY(occupied.isListening());
    }
    void unrelatedUdpPortDoesNotMasqueradeAsRustTcpListener() {
        // Rust SOCKS5 negotiates a dedicated UDP association port, rather than
        // binding a second UDP service to the HTTP/TCP mixed listener port.
        QUdpSocket occupied;QVERIFY(occupied.bind(QHostAddress::LocalHost,0,QUdpSocket::DontShareAddress));
        auto config=options();config.directSession=true;config.proxyPort=occupied.localPort();
        RustCoreEngine engine;engine.start(config);QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
        QCOMPARE(occupied.state(),QAbstractSocket::BoundState);engine.stop();QVERIFY(!engine.status().processAlive);
    }
    void verifiedRoutingProviders() {
        ControlledNetwork net;QVERIFY(net.start());auto config=options();
        auto n=node("routing-fixture",net.a.serverPort());config.nodes={n};config.selectedNodeId=n.id;
        QTemporaryDir rules;QVERIFY(rules.isValid());
        for(const auto &name:{"manifest.json","cn-domain.mrs","cn-ip.mrs"})
            QVERIFY(QFile::copy(QCoreApplication::applicationDirPath()+"/rules/"+name,rules.filePath(name)));
        config.smartRouting=true;config.rulesDirectory=rules.path();config.routingMode="rule";config.nativePrivateRouting=true;
        RustCoreEngine engine;engine.start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Running,16000);
        QVERIFY(engine.routingRules().size()>=10);
        QCOMPARE(fetch(net,config.proxyPort),QByteArray("DIRECT-BYPASS"));
        engine.setRoutingMode("global");QTRY_VERIFY_WITH_TIMEOUT(engine.status().mode=="global"&&engine.status().apiHealthy,5000);
        QCOMPARE(fetch(net,config.proxyPort),QByteArray("exit-A"));
        engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);
        QFile modified(rules.filePath("cn-domain.mrs"));QVERIFY(modified.open(QIODevice::Append));modified.write("changed");modified.close();
        engine.start(config);QCOMPARE(engine.status().error,ProxyEngine::Error::ConfigurationFailed);
        QVERIFY(!engine.status().processAlive);
    }
};
QTEST_GUILESS_MAIN(NodeTests)
#include "NodeTests.moc"
