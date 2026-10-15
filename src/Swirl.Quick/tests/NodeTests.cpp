#include "engine/MihomoAdapter.h"
#include "engine/NodeTestService.h"
#include "engine/TelemetryService.h"
#include "engine/NodeStore.h"
#include "engine/NodeImporter.h"
#include "engine/NodeImportService.h"
#include "engine/EngineController.h"
#include "engine/SwirlEngineManager.h"
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

static quint16 freePort(){QTcpServer server;server.listen(QHostAddress::LocalHost,0);return server.serverPort();}
static ProxyNode node(QString name,quint16 port){ProxyNode n;n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);n.name=name;n.protocol="socks5";n.host="127.0.0.1";n.port=port;return n;}
class NodeTests:public QObject {
    Q_OBJECT
    EngineStartOptions options() {
        QFile file(QString::fromUtf8(SWIRL_TEST_MANIFEST));if(!file.open(QIODevice::ReadOnly))return {};const auto m=QJsonDocument::fromJson(file.readAll()).object();
        EngineStartOptions options;options.executablePath=QCoreApplication::applicationDirPath()+"/core/mihomo.exe";
        options.expectedSha256=m.value("executableSha256").toString().toLatin1();options.expectedVersion=m.value("version").toString();
        options.controlPort=freePort();options.proxyPort=freePort();options.startupTimeoutMs=15000;options.healthIntervalMs=500;return options;
    }
    QByteArray fetch(ControlledNetwork &net,quint16 proxyPort,bool tls=false) {
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",proxyPort));
        QNetworkRequest request(net.url(tls));request.setAttribute(QNetworkRequest::Http2AllowedAttribute,false);request.setRawHeader("Connection","close");
        if(tls){auto ssl=QSslConfiguration::defaultConfiguration();ssl.addCaCertificate(net.certificate);request.setSslConfiguration(ssl);}
        auto *reply=client.get(request);QSignalSpy done(reply,&QNetworkReply::finished);
        if(!done.wait(8000)){qInfo()<<"FIXTURE_TIMEOUT relays"<<net.a.forwarded<<net.b.forwarded<<"origins"<<net.httpRequests<<net.httpsRequests<<"sslBackend"<<QSslSocket::activeBackend();reply->abort();return "REQUEST_TIMEOUT";}
        const auto body=reply->readAll();const int code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if(reply->error()!=QNetworkReply::NoError || code!=200){qInfo()<<"FIXTURE_REQUEST_FAILURE HTTP"<<code<<"relays"<<net.a.forwarded<<net.b.forwarded<<"origins"<<net.httpRequests<<net.httpsRequests;return QByteArray("REQUEST_ERROR_")+QByteArray::number(reply->error());}
        return body;
    }
private slots:
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
            config.selectedNodeId=id;config.controlPort=freePort();config.proxyPort=freePort();MihomoAdapter engine;engine.start(config);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,20000);
            QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",config.proxyPort));
            for(const auto &url:{QUrl("http://www.msftconnecttest.com/connecttest.txt"),QUrl("https://www.gstatic.com/generate_204")}){
                QNetworkRequest request(url);request.setTransferTimeout(15000);request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);auto *reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),18000);
                const int status=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();const bool ok=reply->error()==QNetworkReply::NoError&&status>=200&&status<300;if(ok)++passed;
                transfers.append(QJsonObject{{"node",QString("node-%1").arg(ids.indexOf(id)+1,3,10,QChar('0'))},{"scheme",url.scheme()},{"success",ok},{"httpStatus",status},{"networkError",int(reply->error())},{"bodyBytes",reply->readAll().size()}});reply->deleteLater();
            }engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
        }
        QJsonObject reconnect{{"attempted",false}};
        if(!available.isEmpty()){
            EngineController controller(std::make_unique<SwirlEngineManager>(),nullptr,store.filePath());controller.setControlPort(freePort());controller.setProxyPort(freePort());
            const auto id=available.first();controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),25000);const auto oldPid=controller.processId();
            controller.imports()->refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),35000);
            QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy()&&controller.processId()!=oldPid,25000);QCOMPARE(controller.activeNodeId(),id);
            QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",controller.activeProxyPort()));QJsonArray requests;
            for(const auto &url:{QUrl("http://www.msftconnecttest.com/connecttest.txt"),QUrl("https://www.gstatic.com/generate_204")}){
                QNetworkRequest request(url);request.setTransferTimeout(15000);auto reply=client.get(request);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),18000);const int code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();const bool ok=reply->error()==QNetworkReply::NoError&&code>=200&&code<300;
                requests.append(QJsonObject{{"scheme",url.scheme()},{"httpStatus",code},{"success",ok}});QVERIFY(ok);
            }
            reconnect={{"attempted",true},{"automaticEngineRestart",true},{"selectedNodePreserved",true},{"engine",controller.engineName()},{"requests",requests}};controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
        }
        QJsonObject protocols;for(auto i=protocolCounts.cbegin();i!=protocolCounts.cend();++i)protocols[i.key()]=i.value();
        const QJsonObject report{{"importedNodes",config.nodes.size()},{"protocolCounts",protocols},{"downloadUsedExistingLocalProxy",usedProxy},{"sampledNodes",ids.size()},{"successfulProbes",available.size()},{"probes",rows},{"transfers",transfers},{"refreshReconnect",reconnect}};
        const auto output=qEnvironmentVariable("SWIRL_LIVE_REPORT");if(!output.isEmpty()){QSaveFile file(output);QVERIFY(file.open(QIODevice::WriteOnly));file.write(QJsonDocument(report).toJson());QVERIFY(file.commit());}
        qInfo()<<"LIVE_SUBSCRIPTION imported="<<config.nodes.size()<<"sampled="<<ids.size()<<"available="<<available.size()<<"successfulRequests="<<passed;
        QVERIFY(!available.isEmpty());QCOMPARE(passed,qMin(3,available.size())*2);
    }
    void meteredRulesReallyRejectAndAllowProcesses() {
        ControlledNetwork net;QVERIFY(net.start());auto config=options();config.directSession=true;config.meteredNetwork=true;
        MihomoAdapter engine;engine.start(config);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);
        QVERIFY(fetch(net,config.proxyPort).startsWith("REQUEST_ERROR"));QCOMPARE(net.httpRequests,0);
        engine.setRoutingMode("direct");QTest::qWait(150);QCOMPARE(engine.status().mode,QString("rule"));
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
        config.meteredAllowlist={QFileInfo(QCoreApplication::applicationFilePath()).fileName()};
        engine.start(config);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);
        QCOMPARE(fetch(net,config.proxyPort),QByteArray("DIRECT-BYPASS"));QVERIFY(net.httpRequests>0);
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
        config.meteredAllowlist={"unknown-app.exe","another-app.exe"};
        engine.start(config);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);
        const auto before=net.httpRequests;QVERIFY(fetch(net,config.proxyPort).startsWith("REQUEST_ERROR"));QCOMPARE(net.httpRequests,before);
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
    }
    void noNodeDirectSessionAndAuthenticatedListener() {
        ControlledNetwork net;QVERIFY(net.start());auto config=options();config.directSession=true;
        MihomoAdapter engine;engine.start(config);
        QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);
        QVERIFY(engine.status().directSession);QVERIFY(engine.status().selectedNodeId.isEmpty());
        QCOMPARE(fetch(net,config.proxyPort),QByteArray("DIRECT-BYPASS"));
        QCOMPARE(fetch(net,config.proxyPort,true),QByteArray("DIRECT-BYPASS"));
        QCOMPARE(net.a.forwarded+net.b.forwarded,0);
        engine.setRoutingMode("global");QTRY_COMPARE_WITH_TIMEOUT(engine.status().mode,QString("global"),5000);
        QCOMPARE(fetch(net,config.proxyPort),QByteArray("DIRECT-BYPASS"));
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
        config.allowLan=true;config.lanUsername="fixture";config.lanPassword="test-password-only";
        config.lanBindAddress="127.0.0.1";config.lanSkipLocalAuthentication=false;
        engine.start(config);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);
        QVERIFY(!engine.configurationSummary().contains(config.lanPassword));
        const auto authenticatedFetch=[&](QString password){
            QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",config.proxyPort,config.lanUsername,password));
            auto reply=client.get(QNetworkRequest(net.url()));QSignalSpy done(reply,&QNetworkReply::finished);
            if(!done.wait(8000)){reply->abort();return QByteArray("TIMEOUT");}
            return reply->error()==QNetworkReply::NoError?reply->readAll():QByteArray("REJECTED");
        };
        const auto before=net.httpRequests;QCOMPARE(authenticatedFetch("wrong-password"),QByteArray("REJECTED"));
        QCOMPARE(net.httpRequests,before);QCOMPARE(authenticatedFetch(config.lanPassword),QByteArray("DIRECT-BYPASS"));
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
    }
    void customDnsRulesAndGroupsReachRealMihomo() {
        ControlledNetwork network;QVERIFY(network.start());
        auto opts=options();opts.nodes={node("A",network.a.serverPort())};opts.selectedNodeId=opts.nodes.first().id;
        opts.dnsConfig={{"mode",0},{"hosts",QVariantList{QVariantMap{{"name","fixture.test"},{"value","127.0.0.1"}}}}};
        opts.customGroups={QVariantMap{{"name","Custom"},{"type","select"},{"proxies",QStringList{"DIRECT"}}}};
        opts.customRules={"DOMAIN,fixture.test,Custom"};
        MihomoAdapter engine;engine.start(opts);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);
        QFile configuration(engine.status().configPath);QVERIFY(configuration.open(QIODevice::ReadOnly));const auto config=configuration.readAll();configuration.close();QVERIFY(config.contains("fixture.test"));QVERIFY(config.contains("Custom"));
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",opts.proxyPort));
        auto destination=network.url();destination.setHost("fixture.test");QNetworkRequest request(destination);request.setRawHeader("Connection","close");
        auto *reply=client.get(request);QSignalSpy done(reply,&QNetworkReply::finished);QVERIFY(done.wait(8000));QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("DIRECT-BYPASS"));
        QCOMPARE(network.a.forwarded,0);QVERIFY(network.httpRequests>0);
        engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
    }
    void isolatedBatchNeverChangesMainSelection() {
        ControlledNetwork network;QVERIFY(network.start());network.b.reject=true;
        auto opts=options();opts.nodes={node("A",network.a.serverPort()),node("B",network.b.serverPort())};opts.selectedNodeId=opts.nodes.first().id;
        MihomoAdapter main;main.start(opts);QTRY_VERIFY_WITH_TIMEOUT(main.status().apiHealthy,18000);const auto pid=main.status().processId;
        NodeTestService tests;tests.start(opts,{opts.nodes[0].id,opts.nodes[1].id},network.url());QTRY_VERIFY_WITH_TIMEOUT(!tests.busy(),45000);
        if(tests.succeeded()!=1)qInfo()<<"BATCH_RESULT"<<tests.results();
        QCOMPARE(tests.completed(),2);QCOMPARE(tests.succeeded(),1);QCOMPARE(tests.failed(),1);QVERIFY(tests.result(opts.nodes[0].id).value("success").toBool());QVERIFY(!tests.result(opts.nodes[1].id).value("success").toBool());
        QCOMPARE(main.status().selectedNodeId,opts.nodes.first().id);QCOMPARE(main.status().processId,pid);QVERIFY(network.a.forwarded>=2);
        tests.start(opts,{opts.nodes[0].id,opts.nodes[1].id},network.url());tests.cancel();QVERIFY(!tests.busy());main.stop();QTRY_VERIFY_WITH_TIMEOUT(!main.status().processAlive,4000);
    }
    void authenticTrafficStreamAndConnectionHistory() {
        ControlledNetwork network;QVERIFY(network.start());QTcpServer origin;QVERIFY(origin.listen(QHostAddress::LocalHost,0));network.a.targetPorts.append(origin.serverPort());
        connect(&origin,&QTcpServer::newConnection,&origin,[&]{auto socket=origin.nextPendingConnection();connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);connect(socket,&QTcpSocket::readyRead,socket,[socket]{socket->readAll();if(socket->property("sent").toBool())return;socket->setProperty("sent",true);socket->write("HTTP/1.1 200 OK\r\nContent-Length: 65536\r\nConnection: close\r\n\r\n");auto timer=new QTimer(socket);timer->setInterval(100);connect(timer,&QTimer::timeout,socket,[socket,timer]{socket->write(QByteArray(2048,'x'));const auto n=socket->property("chunks").toInt()+1;socket->setProperty("chunks",n);if(n==32){timer->stop();socket->disconnectFromHost();}});timer->start();});});
        auto opts=options();opts.nodes={node("A",network.a.serverPort())};opts.selectedNodeId=opts.nodes.first().id;MihomoAdapter engine;QTemporaryDir temp;TelemetryService model(temp.filePath("history"),false);connect(&engine,&ProxyEngine::statusChanged,&model,[&]{model.ingest(engine.status());});engine.start(opts);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",opts.proxyPort));auto reply=client.get(QNetworkRequest(QUrl(QString("http://127.0.0.1:%1/real-stream").arg(origin.serverPort()))));QTRY_VERIFY_WITH_TIMEOUT(model.sampled()&&model.downloadRate()>0,6000);QTRY_VERIFY_WITH_TIMEOUT(!model.connections().isEmpty(),6000);QTRY_VERIFY_WITH_TIMEOUT(reply->isFinished(),7000);QCOMPARE(reply->readAll().size(),65536);QTRY_VERIFY_WITH_TIMEOUT(model.summary().value("total").toDouble()>=65536,4000);QVERIFY(!model.ranking("domains").isEmpty());QTRY_VERIFY_WITH_TIMEOUT(model.activeConnections()==0,4000);QVERIFY(!model.connections().isEmpty());engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
    }
    void additionalProtocolsUseActualMihomoConfiguration() {
        const QList<QJsonObject> samples{
            {{"type","http"}},
            {{"type","vmess"},{"uuid","11111111-1111-4111-8111-111111111111"},{"alterId",0},{"cipher","auto"},{"network","ws"},{"ws-opts",QJsonObject{{"path","/fixture"}}}},
            {{"type","vless"},{"uuid","11111111-1111-4111-8111-111111111111"},{"tls",true},{"network","grpc"},{"grpc-opts",QJsonObject{{"grpc-service-name","fixture"}}}},
            {{"type","ssr"},{"password","fixture-password"},{"cipher","aes-128-cfb"},{"protocol","origin"},{"obfs","plain"}},
            {{"type","snell"},{"psk","fixture-password"},{"version",3}},
            {{"type","hysteria"},{"auth-str","fixture-password"},{"up","10 Mbps"},{"down","10 Mbps"}},
            {{"type","hysteria2"},{"password","fixture-password"}},
            {{"type","tuic"},{"uuid","11111111-1111-4111-8111-111111111111"},{"password","fixture-password"},{"congestion-controller","bbr"}},
            {{"type","anytls"},{"password","fixture-password"}},
            {{"type","ssh"},{"username","fixture"},{"password","fixture-password"}},
            {{"type","gost-relay"},{"username","fixture"},{"password","fixture-password"}},
            {{"type","mieru"},{"username","fixture"},{"password","fixture-password"},{"transport","TCP"}},
            {{"type","shadowquic"},{"username","fixture"},{"password","fixture-password"}},
            {{"type","trusttunnel"},{"username","fixture"},{"password","fixture-password"}}
        };
        for(auto sample:samples) {
            const auto protocol=sample.value("type").toString();sample.insert("name","fixture");sample.insert("server","127.0.0.1");sample.insert("port",443);
            const auto parsed=NodeImporter::parse(QJsonDocument(sample).toJson());QVERIFY2(bool(parsed),qPrintable(protocol+": "+parsed.error));
            auto config=options();config.nodes=parsed.nodes;config.selectedNodeId=parsed.nodes.first().id;
            MihomoAdapter engine;engine.start(config);
            QTRY_VERIFY_WITH_TIMEOUT(engine.status().state==ProxyEngine::State::Running || engine.status().state==ProxyEngine::State::Failed,16000);
            QVERIFY2(engine.status().state==ProxyEngine::State::Running,qPrintable(protocol+": "+engine.status().message));
            QVERIFY(!engine.configurationSummary().contains("fixture-password"));
            qInfo()<<"REAL_MIHOMO_CONFIG"<<protocol<<"accepted by pinned engine; remote handshake not tested";
            engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);
        }
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
        auto n=node("large",1080);n.protocol="ss";n.cipher="aes-128-gcm";n.password=QString(4096,QChar(1));
        auto input=n.publicInfo();input.remove("id");input.insert("password",n.password);
        QByteArray previous;int accepted=0;
        for(int i=0;i<100;++i) {
            if(!store.saveNode(input))break;
            ++accepted;QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));previous=file.readAll();
        }
        QVERIFY(accepted>0 && accepted<100);QVERIFY(previous.size()<=1024*1024);
        QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),previous);
        NodeStore reloaded(path);QCOMPARE(reloaded.nodes().size(),accepted);QVERIFY(reloaded.error().isEmpty());
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
        MihomoAdapter engine;engine.start(config);
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
        QCOMPARE(engine.status().nodeHealth,ProxyEngine::NodeHealth::Unavailable);QCOMPARE(engine.status().requestState,ProxyEngine::RequestState::NotTested);
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
    void protocolConfigurationAndPortConflict() {
        auto config=options();QTcpServer occupied;QVERIFY(occupied.listen(QHostAddress::LocalHost,0));
        auto n=node("S",1080);config.nodes={n};config.selectedNodeId=n.id;config.proxyPort=occupied.serverPort();
        MihomoAdapter engine;engine.start(config);QCOMPARE(engine.status().error,ProxyEngine::Error::PortConflict);QVERIFY(!engine.status().processAlive);
        for(const auto &protocol: {QString("ss"),QString("trojan")}){
            config.proxyPort=freePort();n.protocol=protocol;n.password="fixture-secret-'\\\n";n.cipher="aes-128-gcm";n.serverName="localhost";config.nodes={n};
            engine.start(config);QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Running,16000);
            QVERIFY(!engine.configurationSummary().contains("fixture-secret"));
            engine.stop();QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Stopped,4000);
        }
    }
    void verifiedRoutingProviders() {
        ControlledNetwork net;QVERIFY(net.start());auto config=options();
        auto n=node("routing-fixture",net.a.serverPort());config.nodes={n};config.selectedNodeId=n.id;
        QTemporaryDir rules;QVERIFY(rules.isValid());
        for(const auto &name:{"manifest.json","cn-domain.mrs","cn-ip.mrs"})
            QVERIFY(QFile::copy(QCoreApplication::applicationDirPath()+"/rules/"+name,rules.filePath(name)));
        config.smartRouting=true;config.rulesDirectory=rules.path();
        MihomoAdapter engine;engine.start(config);
        QTRY_COMPARE_WITH_TIMEOUT(engine.status().state,ProxyEngine::State::Running,16000);
        QVERIFY(engine.routingRules().size()>=20);
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
