#include "ControlledNetwork.h"
#include <QTest>
#include <QTemporaryDir>
#include <QJsonDocument>
#include "engine/NodeStore.h"
#include "engine/NodeImporter.h"
#include "engine/NodeImportService.h"
#include "engine/RustCoreEngine.h"
#include "engine/EngineController.h"
#include "app/StoragePaths.h"
#include <QSettings>
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
        if(format<=3){QJsonObject value{{"name",name},{"type",p},{"server","127.0.0.1"},{"port",port},{"password",password}};
            if(trojan)value["sni"]="localhost";else value["cipher"]="aes-128-gcm";
            return QJsonDocument(QJsonObject{{"proxies",QJsonArray{value}}}).toJson();}
        if(format==4||format==5||format==12||format==13)return QString("[Proxy]\n%1 = %2, 127.0.0.1, %3, %4password=%5%6\n[Rule]\nFINAL,DIRECT\n").arg(name,p).arg(port).arg(trojan?"":"encrypt-method=aes-128-gcm, ",password,trojan?", sni=localhost":"").toUtf8();
        if(format==6||format==7)return QString("[server_local]\n%1=127.0.0.1:%2, %3password=%4, tag=%5%6\n[filter_local]\nfinal,direct\n").arg(trojan?"trojan":"shadowsocks").arg(port).arg(trojan?"":"method=aes-128-gcm, ",password,name,trojan?", over-tls=true, tls-host=localhost":"").toUtf8();
        if(format==14||format==15)return QString("[Proxy]\n%1 = %2, 127.0.0.1, %3, %4\n").arg(name,trojan?"Trojan":"Shadowsocks").arg(port).arg(trojan?"\""+password+"\", tls-name=localhost":"aes-128-gcm, \""+password+"\"").toUtf8();
        if(format==16)return QJsonDocument(QJsonObject{{"outbounds",QJsonArray{QJsonObject{{"tag",name},{"type","shadowsocks"},{"server","127.0.0.1"},{"server_port",port},{"method","aes-128-gcm"},{"password",password}}}}}).toJson();
        const auto uri=trojan?QString("trojan://%1@127.0.0.1:%2?sni=localhost#Format%20fixture").arg(password).arg(port).toUtf8():"ss://"+QString("aes-128-gcm:%1").arg(password).toUtf8().toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals)+"@127.0.0.1:"+QByteArray::number(port)+"#Format%20fixture";
        return format==8||format==9?uri.toBase64():uri;
    }
private slots:
    void initTestCase(){QStandardPaths::setTestModeEnabled(true);SwirlPaths::initializeTestStorage();QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation));}
    void singBoxQuicParametersSurviveStorageAndRustConversion(){
        for(const auto &type:QStringList{"tuic","hysteria2"}){
            QJsonObject raw{{"type",type},{"tag","synthetic"},{"server","localhost"},{"server_port",443},{"password","synthetic:password"},{"network","tcp"},
                {"tls",QJsonObject{{"enabled",true},{"server_name","origin.test"},{"alpn",QJsonArray{"h3"}}}}};
            if(type=="tuic"){raw["uuid"]="00112233-4455-6677-8899-aabbccddeeff";raw["heartbeat"]="1s250ms";raw["congestion_control"]="new_reno";raw["udp_relay_mode"]="quic";raw["zero_rtt_handshake"]=false;}
            else{raw["up_mbps"]=3;raw["down_mbps"]=5;raw["obfs"]=QJsonObject{{"type","salamander"},{"password","synthetic-obfs"}};}
            const auto parsed=NodeImporter::parse(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{raw}}}).toJson());
            QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);QCOMPARE(parsed.nodes.first().originalConfiguration,raw);
            QCOMPARE(parsed.nodes.first().serverName,QString("origin.test"));
            QTemporaryDir directory;NodeStore store(directory.filePath("nodes"));QVERIFY(store.importNodes(parsed.nodes));NodeStore restored(store.filePath());
            QCOMPARE(restored.nodes().first().originalConfiguration,raw);QCOMPARE(restored.nodes().first().parameters,parsed.nodes.first().parameters);
            QFile encrypted(store.filePath());QVERIFY(encrypted.open(QIODevice::ReadOnly));const auto bytes=encrypted.readAll();QVERIFY(!bytes.contains("synthetic:password"));QVERIFY(!bytes.contains("synthetic-obfs"));
            EngineStartOptions options;options.nodes=restored.nodes();options.selectedNodeId=options.nodes.first().id;options.routingMode="global";
            QJsonObject config;const auto error=RustCoreEngine::configuration(options,&config);QVERIFY2(error.isEmpty(),qPrintable(error));
            const auto outbound=config["nodes"].toArray().first().toObject()["outbound"].toObject();QCOMPARE(outbound["type"].toString(),type);QCOMPARE(outbound["password"].toString(),QString("synthetic:password"));QCOMPARE(outbound["udp"].toBool(),false);
            QCOMPARE(outbound["tls"].toObject()["server_name"].toString(),QString("origin.test"));
            if(type=="tuic"){QCOMPARE(outbound["heartbeat_interval_ms"].toInt(),1250);QCOMPARE(outbound["congestion_control"].toString(),QString("new_reno"));QCOMPARE(outbound["udp_relay_mode"].toString(),QString("quic"));}
            else {QCOMPARE(outbound["obfs"].toString(),QString("salamander"));QCOMPARE(outbound["obfs_password"].toString(),QString("synthetic-obfs"));QCOMPARE(outbound["up_mbps"].toInt(),3);QCOMPARE(outbound["down_mbps"].toInt(),5);}
            for(const auto &extra:QJsonArray{QJsonObject{{"unknown",true}},QJsonObject{{"network","udp"}},QJsonObject{{"tls",QJsonObject{{"enabled",false}}}},QJsonObject{{"tls",QJsonObject{{"enabled",true},{"insecure",true},{"alpn",QJsonArray{"h3"}}}}}}){
                auto rejected=raw;const auto object=extra.toObject();for(auto it=object.begin();it!=object.end();++it)rejected[it.key()]=it.value();
                const auto imported=NodeImporter::parse(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{rejected}}}).toJson());QVERIFY2(imported,qPrintable(imported.error));QCOMPARE(imported.nodes.first().originalConfiguration,rejected);
                options.nodes=imported.nodes;options.selectedNodeId=options.nodes.first().id;const QJsonObject sentinel{{"unchanged",true}};config=sentinel;QVERIFY(!RustCoreEngine::configuration(options,&config).isEmpty());QCOMPARE(config,sentinel);
            }
            for(const auto &extra:QJsonArray{QJsonObject{{"server_port","443"}},QJsonObject{{"server_port",443.5}},QJsonObject{{"tag",123}},QJsonObject{{"server"," localhost "}},QJsonObject{{"port",443}},QJsonObject{{"sni","origin.test"}},QJsonObject{{"_swirl-source-format","other"}}}){
                auto rejected=raw;const auto object=extra.toObject();for(auto it=object.begin();it!=object.end();++it)rejected[it.key()]=it.value();
                QVERIFY(!NodeImporter::parse(QJsonDocument(QJsonObject{{"outbounds",QJsonArray{rejected}}}).toJson()));
            }
        }
    }
    void formatFixturesKeepProtocolOptionsDistinctAndRejectCrossProtocolFields(){
        for(int format=0;format<17;++format){
            const auto parsed=NodeImporter::parse(fixture(format,443,"synthetic-format-password"));
            QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
            const auto &node=parsed.nodes.first();const bool trojan=node.protocol=="trojan";
            if(trojan){QVERIFY(node.cipher.isEmpty());QCOMPARE(node.serverName,QString("localhost"));}
            else {QCOMPARE(node.cipher,QString("aes-128-gcm"));QVERIFY(node.serverName.isEmpty());}
            EngineStartOptions options;options.nodes=parsed.nodes;options.selectedNodeId=node.id;options.routingMode="global";
            QJsonObject valid;const auto error=RustCoreEngine::configuration(options,&valid);QVERIFY2(error.isEmpty(),qPrintable(error));
            // Keep inapplicable fields as explicit negative coverage. Correct
            // fixtures must not rely on a converter silently deleting them.
            if(trojan)options.nodes.first().cipher="aes-128-gcm";
            else options.nodes.first().serverName="localhost";
            const QJsonObject sentinel{{"unchanged",true}};QJsonObject rejected=sentinel;
            QVERIFY(!RustCoreEngine::configuration(options,&rejected).isEmpty());QCOMPARE(rejected,sentinel);
        }
    }
    void normalizationPreservesSensitiveExtensions(){
        const auto result=NodeImporter::parse(R"({"outbounds":[{"tag":"extra","type":"vless","server":"edge.example.org","server_port":443,"uuid":"11111111-1111-4111-8111-111111111111","tls":{"enabled":true,"server_name":"edge.example.org"},"transport":{"type":"ws","path":"/socket","headers":{"Host":"edge.example.org"}},"multiplex":{"enabled":true},"unknown_secret":"private-test-only"}]})");
        QVERIFY2(bool(result),qPrintable(result.error));QCOMPARE(result.incompleteNodes,1);const auto n=result.nodes.first();
        QCOMPARE(n.parameters.value("ws-opts").toObject().value("path").toString(),QString("/socket"));
        QVERIFY(n.originalConfiguration.contains("multiplex"));QVERIFY(!n.conversionIssues.isEmpty());
        QVERIFY(!QJsonDocument::fromVariant(n.publicInfo()).toJson().contains("private-test-only"));
        QTemporaryDir temp;NodeStore store(temp.filePath("nodes"));QVERIFY(store.importNodes(result.nodes));NodeStore loaded(store.filePath());QCOMPARE(loaded.nodes().first().originalConfiguration,n.originalConfiguration);
        QFile file(store.filePath());QVERIFY(file.open(QIODevice::ReadOnly));QVERIFY(!file.readAll().contains("private-test-only"));
        EngineStartOptions opts;opts.nodes=loaded.nodes();opts.selectedNodeId=n.id;RustCoreEngine adapter;adapter.start(opts);QCOMPARE(adapter.status().error,ProxyEngine::Error::InvalidOptions);
    }
    void uriTransportAndInvalidEncoding(){
        QVERIFY(!NodeImporter::parse("vmess://"+QByteArray(R"({"add":"first.example.org","add":"second.example.org","port":443,"id":"11111111-1111-4111-8111-111111111111"})").toBase64()));
        const auto result=NodeImporter::parse("vless://11111111-1111-4111-8111-111111111111@edge.example.org:443?security=reality&type=ws&path=%2Fsocket&host=edge.example.org&sni=edge.example.org&pbk=fixture-public-key&sid=abcd#Fixture");
        QVERIFY2(bool(result),qPrintable(result.error));QCOMPARE(result.nodes.first().parameters.value("network").toString(),QString("ws"));QCOMPARE(result.nodes.first().parameters.value("reality-opts").toObject().value("short-id").toString(),QString("abcd"));
        QCOMPARE(result.nodes.first().parameters.value("client-fingerprint").toString(),QString("chrome"));QVERIFY(!result.nodes.first().publicInfo().value("normalizationNotes").toString().isEmpty());
        for(const auto &bad:{QByteArray("vmess://not_base64!"),QByteArray("ss://bad@localhost:443"),QByteArray("[Proxy]\nn=ss,localhost,443,aes-128-gcm,\"unterminated"),QByteArray("trojan://p@localhost:70000")})QVERIFY(!NodeImporter::parse(bad));
    }
    void everyRequestedFormatDownloadsPersistsAndMapsToRust(){
        ControlledNetwork network;QVERIFY(network.start());
        const auto previous=QSslConfiguration::defaultConfiguration();struct Restore{QSslConfiguration ssl;~Restore(){QSslConfiguration::setDefaultConfiguration(ssl);}}restore{previous};
        auto ssl=previous;ssl.addCaCertificate(network.certificate);QSslConfiguration::setDefaultConfiguration(ssl);
        FormatSource source(network.https.sslConfiguration());QVERIFY(source.listen(QHostAddress::LocalHost,0));
        const QStringList formats{"Clash","Trojan Clash","Clash compatible","Trojan Clash compatible","Surge","Trojan Surge","Quantumult X","Trojan Quantumult X","Shadowrocket","Trojan Shadowrocket","Shadowsocks SIP002","Trojan URI","Surfboard","Trojan Surfboard","Loon","Trojan Loon","sing-box"};
        for(int i=0;i<formats.size();++i){
            const bool trojan=QList<int>{1,3,5,7,9,11,13,15}.contains(i);source.document=fixture(i,443,"r1-format-fixture-password");
            QTemporaryDir temp;const auto path=temp.filePath("nodes");EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);
            const QVariantMap policy{{"groups",QVariantList{QVariantMap{{"name","retained-format-policy"},{"type","select"},{"proxies",QStringList{"DIRECT"}}}}},{"rules",QStringList{"MATCH,retained-format-policy"}}};
            QVERIFY2(controller.replaceNetworkConfiguration(policy),qPrintable(controller.networkConfigurationError()));const auto retained=controller.networkConfigurationSnapshot();
            auto *importer=controller.imports();QVERIFY(importer->saveSubscription({},"Isolated format source",source.url(),360,false,"auto","nodes-only"));const auto sourceId=importer->providers().first().toMap()["id"].toString();
            const auto count=source.requests;importer->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!importer->busy(),8000);QVERIFY2(controller.nodeCatalog().size()==1,qPrintable(formats[i]+": "+importer->message()));QCOMPARE(source.requests,count+1);
            // Provider labels and the historical saved scope cannot override
            // the downloaded document. Complete INI/QX fixtures carry an
            // explicit terminal rule; node-only documents retain local policy.
            const bool complete=QList<int>{4,5,6,7,12,13}.contains(i);
            const auto applied=controller.networkConfigurationSnapshot();
            const auto outcome=importer->providers().first().toMap();
            QVERIFY2(!outcome.value("status").toString().contains(QStringLiteral("失败")),qPrintable(formats[i]+": "+importer->message()));
            if(complete){
                QCOMPARE(applied.value("rules").toStringList(),QStringList{"MATCH,DIRECT"});
                QVERIFY(applied.value("groups").toList().isEmpty());QCOMPARE(applied.value("dns"),retained.value("dns"));
                QCOMPARE(outcome.value("importMode").toString(),QString("full"));
            }else{
                QCOMPARE(applied,retained);QCOMPARE(outcome.value("importMode").toString(),QString("nodes"));
            }
            NodeStore store(path);const auto n=store.nodes().first();QVERIFY(n.conversionIssues.isEmpty());QVERIFY(controller.chooseNode(n.id));
            NodeStore reloaded(path);QCOMPARE(reloaded.nodes().size(),1);QCOMPARE(reloaded.nodes().first().sourceId,sourceId);QCOMPARE(reloaded.selectedId(),n.id);QCOMPARE(reloaded.subscriptions().first().importScope,QString("nodes-only"));
            QCOMPARE(reloaded.nodes().first().password,QString("r1-format-fixture-password"));
            QFile encrypted(store.filePath());QVERIFY(encrypted.open(QIODevice::ReadOnly));QVERIFY(!encrypted.readAll().contains("r1-format-fixture-password"));
            EngineStartOptions opts;opts.nodes=reloaded.nodes();opts.selectedNodeId=n.id;opts.routingMode="global";
            QJsonObject config;const auto error=RustCoreEngine::configuration(opts,&config);QVERIFY2(error.isEmpty(),qPrintable(formats[i]+": "+error));
            const auto outbound=config.value("nodes").toArray().first().toObject().value("outbound").toObject();
            QCOMPARE(outbound.value("type").toString(),trojan?QString("trojan"):QString("shadowsocks"));
            QCOMPARE(outbound.value("password").toString(),QString("r1-format-fixture-password"));
            if(trojan)QCOMPARE(outbound.value("tls").toObject().value("server_name").toString(),QString("localhost"));
            else QCOMPARE(outbound.value("cipher").toString(),QString("aes-128-gcm"));
            importer->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!importer->busy(),8000);QCOMPARE(controller.selectedNodeId(),n.id);QCOMPARE(controller.networkConfigurationSnapshot(),applied);
            NodeStore refreshed(path);QCOMPARE(refreshed.selectedId(),n.id);QCOMPARE(refreshed.nodes().first().id,n.id);QCOMPARE(refreshed.networkConfiguration(),reloaded.networkConfiguration());
            qInfo()<<"FORMAT_DOWNLOAD_STORE_RUST_MAPPING"<<formats[i]<<"downloaded, parsed, DPAPI persisted, reloaded and mapped; protocol execution is a separate independent-peer test";
            controller.shutdown();
        }
    }
};
QTEST_GUILESS_MAIN(SubscriptionFormatTests)
#include "SubscriptionFormatTests.moc"
