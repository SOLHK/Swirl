#include "engine/NodeImporter.h"
#include "engine/NodeImportService.h"
#include "engine/MihomoAdapter.h"
#include "engine/EngineController.h"
#include "ControlledNetwork.h"
#include <QTest>
#include <QTemporaryDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSignalSpy>
#include <QNetworkProxy>
#include <QNetworkReply>

class SubscriptionServer:public QTcpServer {
public:
    QByteArray content;int count=0,code=200;bool hanging=false;
    SubscriptionServer(){connect(this,&QTcpServer::newConnection,this,[this]{while(hasPendingConnections()){
        auto *socket=nextPendingConnection();auto data=std::make_shared<QByteArray>();
        connect(socket,&QTcpSocket::readyRead,socket,[this,socket,data]{data->append(socket->readAll());if(!data->contains("\r\n\r\n"))return;
            if(socket->property("done").toBool())return;socket->setProperty("done",true);++count;
            if(hanging)return;
            socket->write("HTTP/1.1 "+QByteArray::number(code)+" Result\r\nContent-Length: "+QByteArray::number(content.size())+"\r\nConnection: close\r\n\r\n"+content);socket->disconnectFromHost();});
        connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
    }});}
    QUrl url() const{return QUrl(QString("http://127.0.0.1:%1/sub?token=PRIVATE-TOKEN").arg(serverPort()));}
};
static QByteArray socks(quint16 port){return "proxies:\n  - {name: Controlled, type: socks5, server: 127.0.0.1, port: "+QByteArray::number(port)+"}\n";}
static quint16 freePort(){QTcpServer s;s.listen(QHostAddress::LocalHost,0);return s.serverPort();}
class ImportTests:public QObject {
    Q_OBJECT
private slots:
    void fullProtocolRegistryCanBeImported() {
        const QStringList expected{"socks5","ss","trojan","http","ssr","vmess","vless","snell","hysteria","hysteria2","wireguard","tuic","shadowquic","gost-relay","ssh","mieru","anytls","sudoku","masque","trusttunnel","openvpn","tailscale","zerotier","easytier"};
        QCOMPARE(ProxyNode::protocols(),expected);
        QTemporaryDir temp;NodeStore store(temp.filePath("nodes"));
        for(const auto &protocol:expected) {
            QJsonObject proxy{{"name",protocol},{"type",protocol},{"server","127.0.0.1"},{"port",443},{"username","fixture"},{"password","fixture-secret"},{"cipher","aes-128-gcm"},
                {"uuid","11111111-1111-4111-8111-111111111111"},{"psk","fixture-psk"},{"key","fixture-key"},{"udp",true}};
            const auto parsed=NodeImporter::parse(QJsonDocument(proxy).toJson(QJsonDocument::Compact));
            QVERIFY2(bool(parsed),qPrintable(protocol+": "+parsed.error));QVERIFY(store.importNodes(parsed.nodes));
        }
        NodeStore loaded(store.filePath());QCOMPARE(loaded.nodes().size(),24);
        for(const auto &node:loaded.nodes()){
            QVERIFY(node.parameters.value("udp").toBool());
            if(node.protocol=="ssr"){
                auto input=node.publicInfo();input.insert("cipher",QString());input.insert("name","Edited SSR");
                QVERIFY(loaded.saveNode(input));
                NodeStore edited(store.filePath());
                for(const auto &saved:edited.nodes())if(saved.id==node.id)QCOMPARE(saved.cipher,QString("aes-128-gcm"));
            }
        }
    }
    void manualOptionsCannotBypassImportSafety() {
        QTemporaryDir temp;NodeStore store(temp.filePath("nodes"));
        QVERIFY(!store.saveNode({{"name","Unsafe"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",1080},
            {"options",QVariantMap{{"interface-name","Ethernet"}}}}));
    }
    void yamlPreservesTlsAndTransport() {
        const auto parsed=NodeImporter::parse(R"(base: &base {type: vless, server: edge.example.org, port: '443', uuid: 11111111-1111-4111-8111-111111111111}
proxies:
  - <<: *base
    name: imported
    tls: true
    servername: edge.example.org
    network: ws
    ws-opts: {path: /private, headers: {Host: edge.example.org}}
    reality-opts: {public-key: private-key-value, short-id: abcd}
tun: {enable: true, auto-route: true}
external-controller: 0.0.0.0:9090
)");
        QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
        QCOMPARE(parsed.nodes.first().port,quint16(443));
        QCOMPARE(parsed.nodes.first().parameters.value("ws-opts").toObject().value("path").toString(),QString("/private"));
        QVERIFY(!parsed.nodes.first().parameters.contains("tun"));QVERIFY(!parsed.nodes.first().publicInfo().contains("options"));
        QTemporaryDir temp;NodeStore store(temp.filePath("nodes"));QVERIFY(store.importNodes(parsed.nodes));
        NodeStore loaded(store.filePath());QCOMPARE(loaded.nodes().first().parameters,parsed.nodes.first().parameters);
    }
    void rejectsMalformedAndHostChanges() {
        for(const auto &bad:{QByteArray("proxies: ["),QByteArray("proxies: [{name: n, type: socks5, server: localhost, port: 70000}]"),
            QByteArray("proxies: [{name: n, type: unknown, server: localhost, port: 123}]"),
            QByteArray("proxies: [{name: n, type: socks5, server: localhost, port: 123, private-key-path: C:/secret}]"),
            QByteArray("a: &a {x: *a}\nproxies: [*a]"),QByteArray("proxies: [{name: n, type: socks5, server: localhost, port: 123, dialer-proxy: absent}]"),
            QByteArray("proxies: [{name: n, type: socks5, server: localhost, port: 123}, {name: n, type: socks5, server: localhost, port: 124}]")})
            QVERIFY(!NodeImporter::parse(bad));
        QVERIFY(!NodeImporter::parse(QByteArray(NodeImporter::MaximumBytes+1,'x')));
        QVERIFY(!NodeStore::allowedSubscriptionUrl(QUrl("http://remote.example.org/private")));
        QVERIFY(!NodeStore::allowedSubscriptionUrl(QUrl("https://user:pass@remote.example.org/private")));
    }
    void subscriptionAtomicRefreshAndEncryptedUrl() {
        SubscriptionServer server;QVERIFY(server.listen(QHostAddress::LocalHost,0));server.content=socks(1080);
        QTemporaryDir temp;NodeStore store(temp.filePath("nodes"));qint64 now=QDateTime::currentSecsSinceEpoch();
        NodeImportService service(&store,nullptr,[&]{return now;},100);
        QVERIFY(service.saveSubscription({},"Controlled subscription",server.url(),15,true));
        const auto source=store.subscriptions().first().id;service.refreshSubscription(source);
        QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),4000);QCOMPARE(store.nodes().size(),1);
        const auto id=store.nodes().first().id;QVERIFY(store.select(id));
        QVERIFY(!QJsonDocument::fromVariant(service.providers()).toJson().contains("PRIVATE-TOKEN"));
        QFile encrypted(store.filePath());QVERIFY(encrypted.open(QIODevice::ReadOnly));QVERIFY(!encrypted.readAll().contains("PRIVATE-TOKEN"));encrypted.close();
        server.content=socks(1081);now+=901;
        QTRY_COMPARE_WITH_TIMEOUT(store.nodes().first().port,quint16(1081),4000);QCOMPARE(store.selectedId(),id);QCOMPARE(store.nodes().first().id,id);
        server.content="proxies: [";service.refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),4000);
        QCOMPARE(store.nodes().first().port,quint16(1081));QVERIFY(service.providers().first().toMap().value("status").toString().contains("失败"));
        server.code=403;service.refreshSubscription(source);QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),4000);
        QCOMPARE(store.selectedId(),id);QVERIFY(!service.message().contains("PRIVATE-TOKEN"));
        QVERIFY(service.saveSubscription(source,"Paused",{},15,false));const int count=server.count;now+=10000;QTest::qWait(250);QCOMPARE(server.count,count);
        NodeStore reloaded(store.filePath());QCOMPARE(reloaded.subscriptions().first().url,server.url());QCOMPARE(reloaded.nodes().first().port,quint16(1081));
        QVERIFY(service.removeSubscription(source));QVERIFY(store.subscriptions().isEmpty());QVERIFY(store.nodes().first().sourceId.isEmpty());
    }
    void importedChainAndRunningRefresh() {
        ControlledNetwork network;QVERIFY(network.start());SubscriptionServer source;QVERIFY(source.listen(QHostAddress::LocalHost,0));
        QTemporaryDir temp;EngineController controller(std::make_unique<MihomoAdapter>(),nullptr,temp.filePath("nodes"));
        controller.setControlPort(freePort());controller.setProxyPort(freePort());
        auto *imports=controller.imports();source.content=socks(network.a.serverPort());
        QVERIFY(imports->saveSubscription({},"Chain",source.url(),360,false));const auto sid=imports->providers().first().toMap().value("id").toString();
        imports->refreshSubscription(sid);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);QCOMPARE(controller.nodes().size(),1);
        const auto id=controller.nodes().first().toMap().value("id").toString();controller.connectNode(id);
        QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),18000);
        controller.testNode(network.url());QTRY_VERIFY_WITH_TIMEOUT(!controller.nodeBusy(),8000);
        QVERIFY(controller.requestSucceeded());QVERIFY(network.a.forwarded>=2);QCOMPARE(network.b.forwarded,0);
        const auto pid=controller.processId();network.b.username.clear();network.b.password.clear();
        source.content=socks(network.b.serverPort());imports->refreshSubscription(sid);
        QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy()&&controller.processId()!=pid,18000);
        QCOMPARE(controller.selectedNodeId(),id);QVERIFY(!controller.requestSucceeded());
        controller.testNode(network.url());QTRY_VERIFY_WITH_TIMEOUT(!controller.nodeBusy(),8000);QVERIFY(controller.requestSucceeded());QVERIFY(network.b.forwarded>=2);
        controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);QTcpServer reuse;QVERIFY(reuse.listen(QHostAddress::LocalHost,controller.proxyPort()));
        reuse.close();imports->refreshSubscription(sid);controller.stop();
        QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);QTest::qWait(300);QVERIFY(!controller.processAlive());
        qInfo()<<"IMPORTED_REAL_CHAIN: selected A -> subscription refresh -> selected B; real owned engine restarted; no remote environment claimed";
    }
};
QTEST_GUILESS_MAIN(ImportTests)
#include "ImportTests.moc"
