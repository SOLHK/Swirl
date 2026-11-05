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
#include "LoopbackPortLease.h"
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
#include <algorithm>

static quint16 freePort(){
    LoopbackPortLease ports;
    if(!ports.reserve()){qInfo()<<"FIXTURE_PORT_ALLOCATION_FAILURE"<<ports.errorString();QTest::qFail("Could not reserve a controlled loopback TCP/UDP port.",__FILE__,__LINE__);return 0;}
    return ports.proxyPort();
}
static ProxyNode node(QString name,quint16 port){ProxyNode n;n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);n.name=name;n.protocol="socks5";n.host="127.0.0.1";n.port=port;return n;}
class NodeTests:public QObject {
    Q_OBJECT
    EngineStartOptions options() {
        EngineStartOptions options;options.proxyPort=freePort();options.routingMode="global";
        options.startupTimeoutMs=10000;options.healthIntervalMs=500;return options;
    }
    QByteArray fetch(ControlledNetwork &net,quint16 proxyPort,bool tls=false,RustCoreEngine *engine=nullptr) {
        const auto evidence=[&]{
            qInfo()<<"FIXTURE_PROXY_PORT"<<proxyPort;
            if(engine){engine->refresh();const auto state=engine->status();qInfo()<<"FIXTURE_CORE_STATE proxyPort"<<state.proxyPort<<"healthy"<<state.apiHealthy<<"accepted"<<state.rustAccepted<<"failed"<<state.rustFailed<<"lastErrorStage"<<state.rustLastErrorStage;}
        };
        if(!proxyPort){qInfo()<<"FIXTURE_INVALID_PROXY_PORT";evidence();return "FIXTURE_INVALID_PROXY_PORT";}
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",proxyPort));
        QNetworkRequest request(net.url(tls));request.setAttribute(QNetworkRequest::Http2AllowedAttribute,false);request.setRawHeader("Connection","close");
        if(tls){auto ssl=QSslConfiguration::defaultConfiguration();ssl.addCaCertificate(net.certificate);request.setSslConfiguration(ssl);}
        auto *reply=client.get(request);QSignalSpy done(reply,&QNetworkReply::finished);
        if(!done.wait(8000)){qInfo()<<"FIXTURE_TIMEOUT relays"<<net.a.forwarded<<net.b.forwarded<<"origins"<<net.httpRequests<<net.httpsRequests<<"sslBackend"<<QSslSocket::activeBackend();evidence();reply->abort();return "REQUEST_TIMEOUT";}
        const auto body=reply->readAll();const int code=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
        if(reply->error()!=QNetworkReply::NoError || code!=200){qInfo()<<"FIXTURE_REQUEST_FAILURE HTTP"<<code<<"networkError"<<int(reply->error())<<reply->errorString()<<"relays"<<net.a.forwarded<<net.b.forwarded<<"origins"<<net.httpRequests<<net.httpsRequests;evidence();return QByteArray("REQUEST_ERROR_")+QByteArray::number(reply->error());}
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
        QVERIFY(!isolated.directSession);QCOMPARE(isolated.dnsConfig,source.dnsConfig);QVERIFY(isolated.customRules.isEmpty());QVERIFY(isolated.customGroups.isEmpty());
        QVERIFY(isolated.lanPassword.isEmpty());QVERIFY(isolated.inboundPassword.isEmpty());QCOMPARE(isolated.routingMode,QString("global"));
        QCOMPARE(isolated.nodes.size(),source.nodes.size());QVERIFY(!isolated.smartRouting);
        // A saved TUN preference is not evidence of live capture ownership.
        QVERIFY(!isolated.internalProbePhysicalEgress);
        source.internalProbePhysicalEgress=true;
        const auto physical=NodeTestService::isolatedOptions(source);
        QVERIFY(physical.internalProbePhysicalEgress);QVERIFY(!physical.tunEnabled);
        QVERIFY(physical.internalProbeListener);QCOMPARE(physical.proxyPort,quint16(0));
    }
    void probeFailureStatusText_data() {
        QTest::addColumn<QString>("phase");QTest::addColumn<QString>("code");QTest::addColumn<QString>("expected");
        QTest::newRow("dns")<<QString("dns")<<QString("DnsLookupFailed")<<QStringLiteral("DNS 失败");
        QTest::newRow("dns-timeout")<<QString("dns")<<QString("UpstreamDnsTimeout")<<QStringLiteral("DNS 超时");
        QTest::newRow("tcp")<<QString("tcp_connect")<<QString("UpstreamConnectionRefused")<<QStringLiteral("连接失败");
        QTest::newRow("tcp-timeout")<<QString("tcp_connect")<<QString("UpstreamTcpTimeout")<<QStringLiteral("连接超时");
        QTest::newRow("proxy-handshake")<<QString("outbound_handshake")<<QString("UpstreamRejected")<<QStringLiteral("握手失败");
        QTest::newRow("proxy-certificate")<<QString("outbound_handshake")<<QString("TlsCertificateUnknownIssuer")<<QStringLiteral("TLS 验证失败");
        QTest::newRow("proxy-tls-timeout")<<QString("outbound_handshake")<<QString("UpstreamTlsTimeout")<<QStringLiteral("握手超时");
        QTest::newRow("quic-dns-timeout")<<QString("dns")<<QString("TuicDnsTimeout")<<QStringLiteral("DNS 超时");
        QTest::newRow("quic-handshake-timeout")<<QString("outbound_handshake")<<QString("QuicHandshakeTimeout")<<QStringLiteral("握手超时");
        QTest::newRow("origin-tls")<<QString("origin_tls")<<QString("TlsCertificateNameMismatch")<<QStringLiteral("目标 TLS 失败");
        QTest::newRow("origin-tls-timeout")<<QString("origin_tls")<<QString("UrlTestTimeout")<<QStringLiteral("目标 TLS 超时");
        QTest::newRow("response-timeout")<<QString("response_headers")<<QString("UrlTestTimeout")<<QStringLiteral("响应超时");
        QTest::newRow("http-status")<<QString("http_status")<<QString("UrlTestStatus")<<QStringLiteral("HTTP 异常");
        QTest::newRow("invalid-configuration")<<QString("configuration")<<QString("NodeConfigurationRejected")<<QStringLiteral("配置无效");
        QTest::newRow("service-deadline")<<QString("timeout")<<QString("ProbeDeadlineExceeded")<<QStringLiteral("测试超时");
        QTest::newRow("physical-conflict")<<QString("outbound_connect")<<QString("ProbeEgressNetworkConflict")<<QStringLiteral("网络路由冲突");
        QTest::newRow("physical-unavailable")<<QString("outbound_connect")<<QString("ProbeEgressUnavailable")<<QStringLiteral("物理出口不可用");
        QTest::newRow("unknown-phase")<<QString("future_stage")<<QString("FutureCode")<<QStringLiteral("测试失败");
    }
    void probeFailureStatusText() {
        QFETCH(QString,phase);QFETCH(QString,code);QFETCH(QString,expected);
        QCOMPARE(NodeTestService::failureStatusText({{"phase",phase},{"failureCode",code}}),expected);
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
            QVERIFY2(config.proxyPort>0,"The unsupported-feature test requires a successfully reserved nonzero proxy port.");
            config.meteredNetwork=mode==0;config.tunEnabled=mode==1;config.allowLan=mode==2;config.gatewayForwarding=mode==3;
            RustCoreEngine engine;engine.start(config);QCOMPARE(engine.status().state,ProxyEngine::State::Failed);
            QCOMPARE(engine.status().error,ProxyEngine::Error::InvalidOptions);QVERIFY(!engine.status().apiHealthy);
            QTcpServer unused;QVERIFY(unused.listen(QHostAddress::LocalHost,config.proxyPort));
        }
    }
    void zeroQtListenerPortIsRejectedBeforeStart() {
        EngineStartOptions config;config.proxyPort=0;config.directSession=true;config.routingMode="direct";
        RustCoreEngine engine;engine.start(config);
        QCOMPARE(engine.status().state,ProxyEngine::State::Failed);
        QCOMPARE(engine.status().error,ProxyEngine::Error::InvalidOptions);
        QVERIFY(!engine.status().processAlive);QVERIFY(!engine.status().apiHealthy);
        QVERIFY(!engine.status().message.isEmpty());QCOMPARE(engine.status().proxyPort,0);
    }
    void zeroQtListenerPortCannotReplaceRunningSession() {
        ControlledNetwork net;QVERIFY(net.start());auto config=options();QVERIFY(config.proxyPort>0);
        config.directSession=true;config.routingMode="direct";RustCoreEngine engine;engine.start(config);
        QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
        const auto original=engine.status();QCOMPARE(fetch(net,config.proxyPort,false,&engine),QByteArray("DIRECT-BYPASS"));
        QSignalSpy diagnostic(&engine,&ProxyEngine::diagnostic);auto invalid=config;invalid.proxyPort=0;
        engine.start(invalid);
        QCOMPARE(diagnostic.size(),1);QCOMPARE(diagnostic.first().at(1).toString(),QString("CoreStartRejected"));
        QVERIFY(engine.status().processAlive);QVERIFY(engine.status().apiHealthy);
        QCOMPARE(engine.status().sessionId,original.sessionId);QCOMPARE(engine.status().proxyPort,original.proxyPort);
        QCOMPARE(engine.status().processId,original.processId);
        QCOMPARE(fetch(net,config.proxyPort,false,&engine),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.httpRequests,2);
        QCOMPARE(net.a.forwarded+net.b.forwarded,0);engine.stop();QVERIFY(!engine.status().processAlive);
    }
    void explicitDirectAndAuthenticatedLoopbackListener() {
        ControlledNetwork net;QVERIFY(net.start());auto config=options();config.directSession=true;config.routingMode="direct";
        QVERIFY2(config.proxyPort>0,"The controlled Qt request requires a successfully reserved nonzero proxy port.");
        RustCoreEngine engine;engine.start(config);QVERIFY2(engine.status().apiHealthy,qPrintable(engine.status().message));
        QCOMPARE(engine.status().proxyPort,int(config.proxyPort));
        QVERIFY(engine.status().directSession);QCOMPARE(fetch(net,config.proxyPort,false,&engine),QByteArray("DIRECT-BYPASS"));
        QCOMPARE(fetch(net,config.proxyPort,true,&engine),QByteArray("DIRECT-BYPASS"));QCOMPARE(net.a.forwarded+net.b.forwarded,0);
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
        QVERIFY2(opts.proxyPort>0,"The controlled custom-DNS request requires a successfully reserved nonzero proxy port.");
        opts.dnsConfig={{"mode",0},{"hosts",QVariantList{QVariantMap{{"name","fixture.test"},{"value","127.0.0.1"}}}}};
        opts.customGroups={QVariantMap{{"name","Custom"},{"type","select"},{"proxies",QStringList{"DIRECT"}}}};
        opts.customRules={"DOMAIN,fixture.test,Custom"};opts.routingMode="rule";
        RustCoreEngine engine;engine.start(opts);QTRY_VERIFY_WITH_TIMEOUT(engine.status().apiHealthy,18000);
        QJsonObject mapped;QVERIFY(RustCoreEngine::configuration(opts,&mapped).isEmpty());
        QVERIFY(QJsonDocument(mapped).toJson().contains("fixture.test"));QCOMPARE(mapped.value("selectors").toArray().size(),1);
        QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",opts.proxyPort));
        auto destination=network.url();destination.setHost("fixture.test");QNetworkRequest request(destination);request.setRawHeader("Connection","close");
        auto *reply=client.get(request);QSignalSpy done(reply,&QNetworkReply::finished);QVERIFY(done.wait(8000));
        if(reply->error()!=QNetworkReply::NoError){engine.refresh();const auto state=engine.status();qInfo()<<"FIXTURE_CUSTOM_DNS_FAILURE requestedProxyPort"<<opts.proxyPort<<"coreProxyPort"<<state.proxyPort<<"networkError"<<int(reply->error())<<reply->errorString()<<"accepted"<<state.rustAccepted<<"failed"<<state.rustFailed<<"lastErrorStage"<<state.rustLastErrorStage<<"origins"<<network.httpRequests;}
        QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("DIRECT-BYPASS"));
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
        QVERIFY(!tests.result(opts.nodes[1].id).value("failureCode").toString().isEmpty());
        QCOMPARE(tests.result(opts.nodes[1].id).value("nodeReference").toString(),NodeTestService::nodeReference(opts.nodes[1].id));
        QVERIFY(tests.result(opts.nodes[0].id).value("failureCode").toString().isEmpty());
        QCOMPARE(main.status().selectedNodeId,opts.nodes.first().id);QCOMPARE(main.status().processId,pid);
        // Native probes perform one real request, without the legacy adapter's
        // extra availability request. Prove the main route independently.
        QCOMPARE(tests.result(opts.nodes[0].id).value("engineKind").toString(),QString("rust"));
        const auto beforeMainRequest=network.a.forwarded;
        main.probeNode(network.url());QTRY_COMPARE_WITH_TIMEOUT(main.status().requestState,ProxyEngine::RequestState::Succeeded,10000);
        QVERIFY(network.a.forwarded>beforeMainRequest);QVERIFY(network.a.forwarded>=2);
        tests.start(opts,{opts.nodes[0].id,opts.nodes[1].id},network.url());tests.cancel();QTRY_VERIFY_WITH_TIMEOUT(!tests.busy(),5000);main.stop();QTRY_VERIFY_WITH_TIMEOUT(!main.status().processAlive,4000);
    }
    void isolatedBatchPreservesConfiguredDnsAcrossWorkerReuse_data() {
        QTest::addColumn<bool>("physical");
        QTest::newRow("ordinary-system-routes")<<false;
#ifdef Q_OS_WIN
        QTest::newRow("isolated-physical-route")<<true;
#endif
    }
    void isolatedBatchPreservesConfiguredDnsAcrossWorkerReuse() {
        QFETCH(bool,physical);
        ControlledNetwork network;QVERIFY(network.start());auto opts=options();QStringList ids;QVariantList hosts;
        opts.internalProbePhysicalEgress=physical;
        // Four nodes require reusing at least one of the three probe workers.
        // These reserved names resolve only through the supplied local map;
        // even a missed map is confined to an explicit loopback DNS endpoint.
        for(int i=0;i<4;++i){
            auto n=node(QString("DNS fixture %1").arg(i),network.a.serverPort());
            n.host=QString("probe-%1.invalid").arg(i);ids.append(n.id);opts.nodes.append(n);
            hosts.append(QVariantMap{{"name",n.host},{"value","127.0.0.1"}});
        }
        opts.dnsConfig={{"mode",2},{"servers","127.0.0.1"},{"useHosts",false},{"queryFamily","ipv4_only"},{"hosts",hosts}};
        NodeTestService tests;tests.start(opts,ids,network.url());QTRY_VERIFY_WITH_TIMEOUT(!tests.busy(),45000);
        QCOMPARE(tests.completed(),4);QCOMPARE(tests.succeeded(),4);QCOMPARE(tests.failed(),0);
        QCOMPARE(network.a.forwarded,4);QCOMPARE(network.httpRequestsByExit.value("exit-A"),4);QCOMPARE(network.httpRequestsByExit.value("DIRECT-BYPASS"),0);
        for(const auto &id:ids){
            QVERIFY(tests.result(id).value("success").toBool());
            QCOMPARE(tests.result(id).value("resolverPolicy").toString(),QString("isolated_configured_dns"));
            QCOMPARE(tests.result(id).value("egressPolicy").toString(),physical?QString("isolated_physical_egress"):QString("system_routes"));
        }
        // A later batch must use its new resolver, not the preceding worker's
        // cached endpoint. Only 127.0.0.1 has the controlled SOCKS listener.
        opts.dnsConfig["hosts"]=QVariantList{QVariantMap{{"name",opts.nodes.first().host},{"value","127.0.0.2"}}};
        tests.start(opts,{ids.first()},network.url());QTRY_VERIFY_WITH_TIMEOUT(!tests.busy(),45000);
        QCOMPARE(tests.completed(),1);QCOMPARE(tests.failed(),1);QVERIFY(!tests.result(ids.first()).value("success").toBool());
        QCOMPARE(tests.result(ids.first()).value("phase").toString(),QString("tcp_connect"));
        QCOMPARE(network.a.forwarded,4);QCOMPARE(network.httpRequests,4);
        opts.dnsConfig["hosts"]=hosts;tests.start(opts,{ids.first()},network.url());QTRY_VERIFY_WITH_TIMEOUT(!tests.busy(),45000);
        QCOMPARE(tests.succeeded(),1);QVERIFY(tests.result(ids.first()).value("success").toBool());QCOMPARE(network.a.forwarded,5);
    }
    void invalidProbeDnsDoesNotFallBackToSystemResolution() {
        ControlledNetwork network;QVERIFY(network.start());auto opts=options();opts.nodes={node("Fixture",network.a.serverPort())};
        // An encrypted DNS hostname without its explicit bootstrap map is
        // invalid. The old probe isolation discarded it and silently succeeded.
        opts.dnsConfig={{"mode",0},{"encrypted","https://resolver.invalid/dns-query"}};
        NodeTestService tests;tests.start(opts,{opts.nodes.first().id},network.url());
        QVERIFY(!tests.busy());QCOMPARE(tests.completed(),1);QCOMPARE(tests.failed(),1);
        const auto result=tests.result(opts.nodes.first().id);
        QCOMPARE(result.value("phase").toString(),QString("configuration"));
        QCOMPARE(result.value("failureCode").toString(),QString("NodeConfigurationRejected"));
        QCOMPARE(result.value("resolverPolicy").toString(),QString("isolated_configured_dns"));
        QCOMPARE(network.a.forwarded,0);QCOMPARE(network.httpRequests,0);
    }
    void largeRealProbeBatchCancelsRestartsAndReusesThreeWorkers_data(){
        QTest::addColumn<int>("count");
        QTest::newRow("104-nodes")<<104;
        QTest::newRow("88-nodes")<<88;
    }
    void largeRealProbeBatchCancelsRestartsAndReusesThreeWorkers(){
        QFETCH(int,count);
        ControlledNetwork network;QVERIFY(network.start());
        QTcpServer stalled;QVERIFY(stalled.listen(QHostAddress::LocalHost,0));
        auto opts=options();QStringList ids;QVariantList hosts;
        for(int i=0;i<count;++i){
            auto n=node(QString("Batch fixture %1").arg(i),stalled.serverPort());
            n.host=QString("batch-%1.invalid").arg(i);opts.nodes.append(n);ids.append(n.id);
            hosts.append(QVariantMap{{"name",n.host},{"value","127.0.0.1"}});
        }
        opts.dnsConfig={{"mode",2},{"servers","127.0.0.1"},{"useHosts",false},{"queryFamily","ipv4_only"},{"hosts",hosts}};
        NodeTestService tests;QList<QPointer<QTcpSocket>> pending;
        connect(&stalled,&QTcpServer::newConnection,&stalled,[&]{
            while(stalled.hasPendingConnections()){
                auto *socket=stalled.nextPendingConnection();socket->setParent(&stalled);pending.append(socket);
            }
        });
        tests.start(opts,ids,network.url());
        QTRY_COMPARE_WITH_TIMEOUT(pending.size(),3,15000);
        QTRY_VERIFY_WITH_TIMEOUT(std::all_of(pending.begin(),pending.end(),[](const auto &socket){return socket&&socket->bytesAvailable()>0;}),5000);
        QCOMPARE(tests.completed(),0);QCOMPARE(tests.total(),count);
        QCOMPARE(tests.findChildren<ProxyEngine *>(QString(),Qt::FindDirectChildrenOnly).size(),3);
        tests.cancel();tests.start(opts,ids,network.url()); // retiring workers still block a rapid restart
        QTRY_VERIFY_WITH_TIMEOUT(!tests.busy(),10000);
        QTRY_VERIFY_WITH_TIMEOUT(std::all_of(pending.begin(),pending.end(),[](const auto &socket){return socket&&socket->state()==QAbstractSocket::UnconnectedState;}),5000);
        QTRY_VERIFY_WITH_TIMEOUT(tests.findChildren<ProxyEngine *>(QString(),Qt::FindDirectChildrenOnly).isEmpty(),5000);
        QCOMPARE(pending.size(),3);QCOMPARE(tests.completed(),0);QCOMPARE(network.httpRequests,0);

        for(auto &n:opts.nodes)n.port=network.a.serverPort();
        QSet<ProxyEngine *> workers;int peak=0;
        // Disconnect before captured stack state or the service is destroyed,
        // including when a failing assertion returns before workers retire.
        QObject workerObserver;
        connect(&tests,&NodeTestService::changed,&workerObserver,[&]{
            const auto live=tests.findChildren<ProxyEngine *>(QString(),Qt::FindDirectChildrenOnly);
            peak=qMax(peak,int(live.size()));for(auto *worker:live)workers.insert(worker);
        });
        tests.start(opts,ids+ids,network.url()); // duplicate selection IDs still yield one request per node
        for(int i=0;i<20;++i)tests.start(opts,ids,network.url());
        QCOMPARE(tests.total(),count);
        QTRY_VERIFY_WITH_TIMEOUT(!tests.busy(),60000);
        QTRY_VERIFY_WITH_TIMEOUT(tests.findChildren<ProxyEngine *>(QString(),Qt::FindDirectChildrenOnly).isEmpty(),5000);
        QCOMPARE(peak,3);QCOMPARE(workers.size(),3);
        QCOMPARE(tests.completed(),count);QCOMPARE(tests.succeeded(),count);QCOMPARE(tests.failed(),0);
        QCOMPARE(tests.results().size(),count);QCOMPARE(network.a.forwarded,count);
        QCOMPARE(network.httpRequests,count);QCOMPARE(network.httpRequestsByExit.value("exit-A"),count);
        QCOMPARE(network.httpRequestsByExit.value("DIRECT-BYPASS"),0);
        for(const auto &id:ids){const auto result=tests.result(id);
            QVERIFY(result.value("success").toBool());QCOMPARE(result.value("http").toInt(),200);
            QVERIFY(result.value("latency").toLongLong()>=0);QVERIFY(!tests.testing(id));
        }
        QTest::qWait(50);QCOMPARE(tests.completed(),count);QCOMPARE(network.httpRequests,count);
    }
    void independentMeasurementDoesNotClaimAConnectedSession() {
        ControlledNetwork network;QVERIFY(network.start());QTemporaryDir temp;
        network.a.username="private-probe-user";network.a.password="private-probe-password";
        EngineController controller(std::make_unique<ThreadedEngine>(),nullptr,temp.filePath("nodes.dpapi"));
        QVERIFY(controller.saveNode({{"name","private-fixture-name"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",network.a.serverPort()},
            {"username",QString::fromLatin1(network.a.username)},{"password",QString::fromLatin1(network.a.password)}}));
        const auto id=controller.nodes().first().toMap().value("id").toString();
        controller.testSelectedNode(id,network.url());QTRY_VERIFY_WITH_TIMEOUT(!controller.tests()->busy(),45000);
        QVERIFY(controller.tests()->result(id).value("success").toBool());QVERIFY(network.a.forwarded>0);
        const auto row=controller.nodes().first().toMap();
        QCOMPARE(row.value("status").toString(),QStringLiteral("可用"));
        QCOMPARE(row.value("connectionState").toString(),QStringLiteral("未连接"));
        QVERIFY(row.value("testAvailable").toBool());QVERIFY(!row.value("networkVerified").toBool());QVERIFY(!controller.processAlive());
        const auto diagnostic=controller.nodeDiagnosticRows().first().toMap();
        QCOMPARE(diagnostic.value("nodeReference").toString(),NodeTestService::nodeReference(id));
        QVERIFY(diagnostic.value("tested").toBool());QVERIFY(diagnostic.value("testSucceeded").toBool());
        QVERIFY(!diagnostic.value("requestVerified").toBool());QVERIFY(diagnostic.value("executable").toBool());
        const auto json=QJsonDocument(QJsonObject::fromVariantMap(diagnostic)).toJson();
        QVERIFY(!json.contains(id.toUtf8()));QVERIFY(!json.contains("private-fixture-name"));QVERIFY(!json.contains("127.0.0.1"));
        // An actual failed request must reach the application's diagnostic log,
        // with the same opaque reference/stage as the row and no node secrets.
        network.a.reject=true;QSignalSpy events(&controller,&EngineController::diagnostic);
        controller.testSelectedNode(id,network.url());QTRY_VERIFY_WITH_TIMEOUT(!controller.tests()->busy(),45000);
        const auto failure=controller.tests()->result(id);QVERIFY(!failure.value("success").toBool());
        QCOMPARE(failure.value("phase").toString(),QString("outbound_handshake"));
        QCOMPARE(events.size(),1);QCOMPARE(events.first().at(0).toString(),QString("NodeTestService"));
        QCOMPARE(events.first().at(1).toString(),QString("NodeTestFailed"));
        const auto message=events.first().at(2).toString();
        QVERIFY(message.contains(NodeTestService::nodeReference(id)));QVERIFY(message.contains("outbound_handshake"));
        QVERIFY(!failure.value("failureCode").toString().isEmpty());QVERIFY(message.contains(failure.value("failureCode").toString()));
        const auto report=controller.diagnostics()->report();QVERIFY(report.contains(message));
        for(const auto &secret:QStringList{id,"private-fixture-name","127.0.0.1","private-probe-user","private-probe-password"})QVERIFY(!report.contains(secret));
        const auto failedRow=controller.nodes().first().toMap();
        QCOMPARE(failedRow.value("status").toString(),QStringLiteral("测试失败"));
        QCOMPARE(failedRow.value("statusDetail").toString(),QStringLiteral("握手失败"));
        QCOMPARE(failedRow.value("connectionState").toString(),QStringLiteral("未连接"));QVERIFY(!controller.processAlive());
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
