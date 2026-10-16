#include "ControlledProtocolPeers.h"
#include "engine/NodeImporter.h"
#include "engine/NodeImportService.h"
#include "engine/MihomoAdapter.h"
#include <QNetworkReply>
#include <QSignalSpy>
#include <QJsonArray>
#include <QUrlQuery>

class FormatSource:public QSslServer {
public:
    QByteArray document;int requests=0;
    FormatSource(const QSslConfiguration &ssl){setSslConfiguration(ssl);connect(this,&QTcpServer::pendingConnectionAvailable,this,[this]{while(hasPendingConnections()){
        auto socket=nextPendingConnection();connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
        connect(socket,&QTcpSocket::readyRead,socket,[this,socket]{auto bytes=socket->property("request").toByteArray()+socket->readAll();socket->setProperty("request",bytes);if(!bytes.contains("\r\n\r\n")||socket->property("done").toBool())return;socket->setProperty("done",true);++requests;socket->write("HTTP/1.1 200 OK\r\nContent-Length: "+QByteArray::number(document.size())+"\r\nConnection: close\r\n\r\n"+document);socket->disconnectFromHost();});
    }});}
    QUrl url()const{return QUrl(QString("https://localhost:%1/isolated-subscription").arg(serverPort()));}
};
class SubscriptionFormatTests:public QObject {
    Q_OBJECT
    static QByteArray fixture(int format,quint16 port,const QString &password){
        const bool trojan=QList<int>{1,3,5,7,9,11,13,15}.contains(format);
        const QString p=trojan?"trojan":"ss",name="Format fixture";
        if(format<=3)return QJsonDocument(QJsonObject{{"proxies",QJsonArray{QJsonObject{{"name",name},{"type",p},{"server","127.0.0.1"},{"port",port},{"password",password},{"cipher","aes-128-gcm"},{"sni","localhost"}}}}}).toJson();
        if(format==4||format==5||format==12||format==13)return QString("[Proxy]\n%1 = %2, 127.0.0.1, %3, %4password=%5%6\n[Rule]\nFINAL,DIRECT\n").arg(name,p).arg(port).arg(trojan?"":"encrypt-method=aes-128-gcm, ",password,trojan?", sni=localhost":"").toUtf8();
        if(format==6||format==7)return QString("[server_local]\n%1=127.0.0.1:%2, %3password=%4, tag=%5%6\n[filter_local]\nfinal,direct\n").arg(trojan?"trojan":"shadowsocks").arg(port).arg(trojan?"":"method=aes-128-gcm, ",password,name,trojan?", over-tls=true, tls-host=localhost":"").toUtf8();
        if(format==14||format==15)return QString("[Proxy]\n%1 = %2, 127.0.0.1, %3, %4\n").arg(name,trojan?"Trojan":"Shadowsocks").arg(port).arg(trojan?"\""+password+"\", tls-name=localhost":"aes-128-gcm, \""+password+"\"").toUtf8();
        if(format==16)return QJsonDocument(QJsonObject{{"outbounds",QJsonArray{QJsonObject{{"tag",name},{"type","shadowsocks"},{"server","127.0.0.1"},{"server_port",port},{"method","aes-128-gcm"},{"password",password}}}}}).toJson();
        const auto uri=trojan?QString("trojan://%1@127.0.0.1:%2?sni=localhost#Format%20fixture").arg(password).arg(port).toUtf8():"ss://"+QString("aes-128-gcm:%1").arg(password).toUtf8().toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals)+"@127.0.0.1:"+QByteArray::number(port)+"#Format%20fixture";
        return format==8||format==9?uri.toBase64():uri;
    }
private slots:
    void normalizationPreservesSensitiveExtensions(){
        const auto result=NodeImporter::parse(R"({"outbounds":[{"tag":"extra","type":"vless","server":"edge.example.org","server_port":443,"uuid":"11111111-1111-4111-8111-111111111111","tls":{"enabled":true,"server_name":"edge.example.org"},"transport":{"type":"ws","path":"/socket","headers":{"Host":"edge.example.org"}},"multiplex":{"enabled":true},"unknown_secret":"private-test-only"}]})");
        QVERIFY2(bool(result),qPrintable(result.error));QCOMPARE(result.incompleteNodes,1);const auto n=result.nodes.first();
        QCOMPARE(n.parameters.value("ws-opts").toObject().value("path").toString(),QString("/socket"));
        QVERIFY(n.originalConfiguration.contains("multiplex"));QVERIFY(!n.conversionIssues.isEmpty());
        QVERIFY(!QJsonDocument::fromVariant(n.publicInfo()).toJson().contains("private-test-only"));
        QTemporaryDir temp;NodeStore store(temp.filePath("nodes"));QVERIFY(store.importNodes(result.nodes));NodeStore loaded(store.filePath());QCOMPARE(loaded.nodes().first().originalConfiguration,n.originalConfiguration);
        QFile file(store.filePath());QVERIFY(file.open(QIODevice::ReadOnly));QVERIFY(!file.readAll().contains("private-test-only"));
        EngineStartOptions opts;opts.nodes=loaded.nodes();opts.selectedNodeId=n.id;MihomoAdapter adapter;adapter.start(opts);QCOMPARE(adapter.status().error,ProxyEngine::Error::InvalidNode);
    }
    void uriTransportAndInvalidEncoding(){
        QVERIFY(!NodeImporter::parse("vmess://"+QByteArray(R"({"add":"first.example.org","add":"second.example.org","port":443,"id":"11111111-1111-4111-8111-111111111111"})").toBase64()));
        const auto result=NodeImporter::parse("vless://11111111-1111-4111-8111-111111111111@edge.example.org:443?security=reality&type=ws&path=%2Fsocket&host=edge.example.org&sni=edge.example.org&pbk=fixture-public-key&sid=abcd#Fixture");
        QVERIFY2(bool(result),qPrintable(result.error));QCOMPARE(result.nodes.first().parameters.value("network").toString(),QString("ws"));QCOMPARE(result.nodes.first().parameters.value("reality-opts").toObject().value("short-id").toString(),QString("abcd"));
        QCOMPARE(result.nodes.first().parameters.value("client-fingerprint").toString(),QString("chrome"));QVERIFY(!result.nodes.first().publicInfo().value("normalizationNotes").toString().isEmpty());
        for(const auto &bad:{QByteArray("vmess://not_base64!"),QByteArray("ss://bad@localhost:443"),QByteArray("[Proxy]\nn=ss,localhost,443,aes-128-gcm,\"unterminated"),QByteArray("trojan://p@localhost:70000")})QVERIFY(!NodeImporter::parse(bad));
    }
    void everyRequestedFormatDownloadsPersistsAndForwards(){
        ControlledNetwork network;QVERIFY(network.start());ControlledProtocolPeers peers;QVERIFY2(peers.start(network),qPrintable(peers.failure));
        const auto previous=QSslConfiguration::defaultConfiguration();struct Restore{QSslConfiguration ssl;~Restore(){QSslConfiguration::setDefaultConfiguration(ssl);}}restore{previous};
        auto ssl=previous;ssl.addCaCertificate(network.certificate);QSslConfiguration::setDefaultConfiguration(ssl);
        FormatSource source(network.https.sslConfiguration());QVERIFY(source.listen(QHostAddress::LocalHost,0));
        const QStringList formats{"Clash","Trojan Clash","Clash compatible","Trojan Clash compatible","Surge","Trojan Surge","Quantumult X","Trojan Quantumult X","Shadowrocket","Trojan Shadowrocket","Shadowsocks SIP002","Trojan URI","Surfboard","Trojan Surfboard","Loon","Trojan Loon","sing-box"};
        for(int i=0;i<formats.size();++i){
            const bool trojan=QList<int>{1,3,5,7,9,11,13,15}.contains(i);source.document=fixture(i,trojan?peers.trojanPort:peers.ssPort,peers.password);
            QTemporaryDir temp;NodeStore store(temp.filePath("nodes"));NodeImportService importer(&store);QVERIFY(importer.saveSubscription({},"Isolated format source",source.url(),360,false));const auto sourceId=store.subscriptions().first().id;
            const auto count=source.requests;importer.refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!importer.busy(),8000);QVERIFY2(store.nodes().size()==1,qPrintable(formats[i]+": "+importer.message()));QCOMPARE(source.requests,count+1);
            auto n=store.nodes().first();QVERIFY(n.conversionIssues.isEmpty());QVERIFY(store.select(n.id));
            // Test-only certificate pin for the isolated self-signed peer; no
            // system trust or skip-cert-verify changes, and no public material.
            if(trojan)QVERIFY(store.saveNode({{"id",n.id},{"name",n.name},{"protocol",n.protocol},{"host",n.host},{"port",n.port},{"options",QVariantMap{{"fingerprint",QString::fromLatin1(peers.fingerprint)}}}}));
            NodeStore reloaded(store.filePath());QCOMPARE(reloaded.nodes().size(),1);QCOMPARE(reloaded.nodes().first().sourceId,sourceId);
            EngineStartOptions opts;opts.executablePath=QCoreApplication::applicationDirPath()+"/core/mihomo.exe";QFile binary(opts.executablePath);QVERIFY(binary.open(QIODevice::ReadOnly));QCryptographicHash hash(QCryptographicHash::Sha256);QVERIFY(hash.addData(&binary));opts.expectedSha256=hash.result().toHex();opts.expectedVersion="v1.19.32";opts.controlPort=ControlledProtocolPeers::port();opts.proxyPort=ControlledProtocolPeers::port();while(opts.proxyPort==opts.controlPort)opts.proxyPort=ControlledProtocolPeers::port();opts.nodes=reloaded.nodes();opts.selectedNodeId=n.id;opts.routingMode="global";
            opts.startupTimeoutMs=15000;
            MihomoAdapter engine;engine.start(opts);QTRY_VERIFY2_WITH_TIMEOUT(engine.status().apiHealthy,qPrintable(formats[i]+": "+engine.status().message),15000);
            QNetworkAccessManager client;client.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,"127.0.0.1",opts.proxyPort));
            const int forwarded=network.a.forwarded;
            for(bool tls:{false,true}){QNetworkRequest request(network.url(tls));request.setTransferTimeout(5000);auto reply=client.get(request);QSignalSpy finished(reply,&QNetworkReply::finished);QTRY_VERIFY_WITH_TIMEOUT(!finished.isEmpty(),7000);QCOMPARE(reply->error(),QNetworkReply::NoError);QCOMPARE(reply->readAll(),QByteArray("exit-A"));reply->deleteLater();}
            QVERIFY(network.a.forwarded>=forwarded+2);engine.stop();QTRY_VERIFY_WITH_TIMEOUT(!engine.status().processAlive,4000);
            importer.refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!importer.busy(),8000);QCOMPARE(store.selectedId(),n.id);QCOMPARE(store.nodes().first().id,n.id);
            qInfo()<<"FORMAT_REAL_HTTP_HTTPS"<<formats[i]<<"downloaded, parsed, DPAPI persisted, reloaded, Mihomo selected exit-A, disconnected, refreshed; local fixtures only";
        }
    }
};
QTEST_GUILESS_MAIN(SubscriptionFormatTests)
#include "SubscriptionFormatTests.moc"
