#include "engine/NodeImporter.h"
#include "engine/NodeImportService.h"
#include "engine/MihomoAdapter.h"
#include "engine/EngineController.h"
#include "engine/SwirlProtocolRegistry.h"
#include "ControlledNetwork.h"
#include <QTest>
#include <QSettings>
#include "app/StoragePaths.h"
#include <QTemporaryDir>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QSignalSpy>
#include <QNetworkProxy>
#include <QNetworkReply>

class SubscriptionServer:public QTcpServer {
public:
    QByteArray content,location;int count=0,code=200;bool hanging=false;
    SubscriptionServer(){connect(this,&QTcpServer::newConnection,this,[this]{while(hasPendingConnections()){
        auto *socket=nextPendingConnection();auto data=std::make_shared<QByteArray>();
        connect(socket,&QTcpSocket::readyRead,socket,[this,socket,data]{data->append(socket->readAll());if(!data->contains("\r\n\r\n"))return;
            if(socket->property("done").toBool())return;socket->setProperty("done",true);++count;
            if(hanging)return;
            socket->write("HTTP/1.1 "+QByteArray::number(code)+" Result\r\n"+(location.isEmpty()?QByteArray():"Location: "+location+"\r\n")+"Content-Length: "+QByteArray::number(content.size())+"\r\nConnection: close\r\n\r\n"+content);socket->disconnectFromHost();});
        connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
    }});}
    QUrl url() const{return QUrl(QString("http://127.0.0.1:%1/sub?token=PRIVATE-TOKEN").arg(serverPort()));}
};
static QByteArray socks(quint16 port){return "proxies:\n  - {name: Controlled, type: socks5, server: 127.0.0.1, port: "+QByteArray::number(port)+"}\n";}
static quint16 freePort(){QTcpServer s;s.listen(QHostAddress::LocalHost,0);return s.serverPort();}
static QJsonObject xrayRealitySource(){
    const auto key=QString::fromLatin1(QByteArray(32,'\x09').toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals));
    const QJsonObject user{{"id","00112233-4455-6677-8899-aabbccddeeff"},{"encryption","none"},{"flow","xtls-rprx-vision"}};
    const QJsonObject endpoint{{"address","proxy.invalid"},{"port",443},{"users",QJsonArray{user}}};
    const QJsonObject reality{{"serverName","camouflage.invalid"},{"fingerprint","chrome"},{"publicKey",key},{"shortId","a1B2"}};
    return {{"protocol","vless"},{"tag","fixture"},{"settings",QJsonObject{{"vnext",QJsonArray{endpoint}}}},
        {"streamSettings",QJsonObject{{"network","raw"},{"security","reality"},{"realitySettings",reality}}}};
}
class HttpsSubscriptionServer:public QSslServer {
public:
    QByteArray content,location;int count=0,code=200;
    HttpsSubscriptionServer(const QSslConfiguration &configuration){setSslConfiguration(configuration);connect(this,&QTcpServer::pendingConnectionAvailable,this,[this]{while(hasPendingConnections()){
        auto *socket=nextPendingConnection();auto data=std::make_shared<QByteArray>();
        connect(socket,&QTcpSocket::readyRead,socket,[this,socket,data]{data->append(socket->readAll());if(!data->contains("\r\n\r\n")||socket->property("done").toBool())return;socket->setProperty("done",true);++count;
            socket->write("HTTP/1.1 "+QByteArray::number(code)+" Result\r\n"+(location.isEmpty()?QByteArray():"Location: "+location+"\r\n")+"Content-Length: "+QByteArray::number(content.size())+"\r\nConnection: close\r\n\r\n"+content);socket->disconnectFromHost();});
        connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
    }});}
    QUrl url() const{return QUrl(QString("https://localhost:%1/sub").arg(serverPort()));}
};
class ImportTests:public QObject {
    Q_OBJECT
private slots:
    void initTestCase() { QStandardPaths::setTestModeEnabled(true);SwirlPaths::initializeTestStorage();QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,SwirlPaths::writableLocation(QStandardPaths::AppConfigLocation)); }
    void tcpUriTransportRequirementsRemainBlockedAfterPersistence() {
        const auto key=QByteArray(32,'\x09').toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals);
        const QByteArray prefix="vless://00112233-4455-6677-8899-aabbccddeeff@proxy.invalid:443?security=reality&sni=camouflage.invalid&fp=chrome&pbk="+key+"&sid=abcd&flow=xtls-rprx-vision";
        for(const auto &network:QList<QByteArray>{"","&type=tcp","&network=tcp"}){
            const auto baseline=NodeImporter::parse(prefix+network);QVERIFY2(baseline,qPrintable(baseline.error));QVERIFY(baseline.nodes.first().conversionIssues.isEmpty());
#ifdef SWIRL_USE_RUST_CORE
            QVERIFY(SwirlProtocolRegistry::nativeNodeReason(baseline.nodes.first()).isEmpty());
#endif
        }
        QList<QByteArray> uris{prefix+"&type=",prefix+"&network="};
        for(const auto &network:QList<QByteArray>{"","&type=tcp","&network=tcp"})
        for(const auto &parameter:QList<QByteArray>{"&path=%2Ffixture-secret","&host=fixture-secret.invalid","&serviceName=fixture-secret","&path=","&host=","&serviceName="})uris.append(prefix+network+parameter);
        for(const auto &uri:uris){
            for(const auto &body:{uri,uri.toBase64()}){
                const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);QCOMPARE(parsed.incompleteNodes,1);
                const auto node=parsed.nodes.first();QVERIFY(!node.conversionIssues.isEmpty());QCOMPARE(node.originalConfiguration.value("uri"),QJsonValue(QString::fromUtf8(uri)));
                QVERIFY(!node.conversionIssues.join(' ').contains("fixture-secret"));QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
                QTemporaryDir directory;QVERIFY(directory.isValid());const auto path=directory.filePath("transport.dpapi");
                {NodeStore store(path);QVERIFY(store.importNodes(parsed.nodes));}
                NodeStore restored(path);QCOMPARE(restored.nodes().size(),1);const auto saved=restored.nodes().first();
                QCOMPARE(saved.originalConfiguration,node.originalConfiguration);QCOMPARE(saved.conversionIssues,node.conversionIssues);
                QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(saved).isEmpty());
                QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));QVERIFY(!file.readAll().contains("fixture-secret"));
            }
        }
        // Valid WebSocket path/Host mapping remains intact; this change does
        // not treat every transport-specific URI field as an unsupported one.
        const QByteArray websocket="vless://00112233-4455-6677-8899-aabbccddeeff@proxy.invalid:443?type=ws&path=%2Fsocket&host=websocket.invalid";
        const auto parsed=NodeImporter::parse(websocket);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.incompleteNodes,0);
        const auto options=parsed.nodes.first().parameters.value("ws-opts").toObject();QCOMPARE(options.value("path"),QJsonValue("/socket"));QCOMPARE(options.value("headers").toObject().value("Host"),QJsonValue("websocket.invalid"));
    }
    void vlessUriAuthorityAndPathRequirementsRemainBlocked() {
        const auto key=QByteArray(32,'\x09').toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals);
        const QByteArray user="vless://00112233-4455-6677-8899-aabbccddeeff";
        const QByteArray endpoint="@proxy.invalid:443";
        const QByteArray query="?security=reality&type=tcp&sni=camouflage.invalid&fp=chrome&pbk="+key+"&sid=abcd&flow=xtls-rprx-vision";
        for(const auto &uri:QList<QByteArray>{user+":fixture-secret"+endpoint+query,user+endpoint+"/fixture-secret"+query,user+endpoint+"/fixture-secret/.."+query,user+endpoint+"/fixture-secret/%2e%2e"+query,user+endpoint+"/."+query,user+endpoint+"/%2e"+query,user+":fixture-secret"+endpoint+"/fixture-secret"+query})
        for(const auto &body:{uri,uri.toBase64()}){
            const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);QCOMPARE(parsed.incompleteNodes,1);
            const auto node=parsed.nodes.first();QCOMPARE(node.originalConfiguration.value("uri"),QJsonValue(QString::fromUtf8(uri)));
            QVERIFY(!node.conversionIssues.isEmpty());QVERIFY(!node.conversionIssues.join(' ').contains("fixture-secret"));QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
        }
        // An empty userinfo password or a single neutral slash does not carry
        // an additional requirement. Keep both equivalent spellings usable.
        for(const auto &password:QList<QByteArray>{"",":"})for(const auto &path:QList<QByteArray>{"","/"}){
            const auto uri=user+password+endpoint+path+query;
            for(const auto &body:{uri,uri.toBase64()}){
                const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);QCOMPARE(parsed.incompleteNodes,0);
                QCOMPARE(parsed.nodes.first().originalConfiguration.value("uri"),QJsonValue(QString::fromUtf8(uri)));QVERIFY(parsed.nodes.first().conversionIssues.isEmpty());
#ifdef SWIRL_USE_RUST_CORE
                QVERIFY(SwirlProtocolRegistry::nativeNodeReason(parsed.nodes.first()).isEmpty());
#endif
            }
        }
        for(const auto &extra:QList<QByteArray>{"&type=tcp","&network=ws"}){
            const auto uri=user+":fixture-secret"+endpoint+"/fixture-secret"+query+extra;
            for(const auto &body:{uri,uri.toBase64()}){
                const auto parsed=NodeImporter::parse(body);QVERIFY(!parsed);QVERIFY(parsed.nodes.isEmpty());QVERIFY(!parsed.error.contains("fixture-secret"));
            }
        }
    }
    void uriHeaderTypeHasClosedTransportSemantics() {
        const auto key=QByteArray(32,'\x09').toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals);
        const QByteArray prefix="vless://00112233-4455-6677-8899-aabbccddeeff@proxy.invalid:443?security=reality&sni=camouflage.invalid&fp=chrome&pbk="+key+"&sid=abcd&flow=xtls-rprx-vision";
        for(const auto &network:QList<QByteArray>{"","&type=tcp","&network=tcp"}){
            const auto baseline=NodeImporter::parse(prefix+network);QVERIFY(baseline);
            const auto uri=prefix+network+"&headerType=none";
            for(const auto &body:{uri,uri.toBase64()}){
                const auto parsed=NodeImporter::parse(body);QVERIFY(parsed);QCOMPARE(parsed.incompleteNodes,0);QCOMPARE(parsed.nodes.size(),1);
                QCOMPARE(parsed.nodes.first().parameters,baseline.nodes.first().parameters);
                QCOMPARE(parsed.nodes.first().originalConfiguration.value("uri"),QJsonValue(QString::fromUtf8(uri)));
#ifdef SWIRL_USE_RUST_CORE
                QVERIFY(SwirlProtocolRegistry::nativeNodeReason(parsed.nodes.first()).isEmpty());
#endif
            }
        }
        for(const auto &uri:QList<QByteArray>{prefix+"&type=tcp&headerType=",prefix+"&type=tcp&headerType=None",prefix+"&type=tcp&headerType=http",QByteArray("vless://00112233-4455-6677-8899-aabbccddeeff@proxy.invalid:443?type=ws&headerType=none")})
        for(const auto &body:{uri,uri.toBase64()}){
            const auto parsed=NodeImporter::parse(body);QVERIFY(parsed);QCOMPARE(parsed.incompleteNodes,1);QCOMPARE(parsed.nodes.size(),1);
            QCOMPARE(parsed.nodes.first().originalConfiguration.value("uri"),QJsonValue(QString::fromUtf8(uri)));
            QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(parsed.nodes.first()).isEmpty());
        }
        for(const auto &extra:QList<QByteArray>{"&headerType=none&headerType=none","&headerType=none&headerType=http"})
        for(const auto &body:{prefix+extra,(prefix+extra).toBase64()}){
            const auto parsed=NodeImporter::parse(body);QVERIFY(!parsed);QVERIFY(parsed.nodes.isEmpty());
        }
    }
    void preUpgradeUriStoreRechecksSourceWithoutRewriting() {
        const auto key=QByteArray(32,'\x09').toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals);
        const QByteArray user="vless://00112233-4455-6677-8899-aabbccddeeff";
        const QByteArray endpoint="@proxy.invalid:443";
        const QByteArray query="?security=reality&type=tcp&sni=camouflage.invalid&fp=chrome&pbk="+key+"&sid=abcd&flow=xtls-rprx-vision";
        const auto prefix=user+endpoint+query;
        auto emptyType=prefix,emptyNetwork=prefix;emptyType.replace("&type=tcp","&type=");emptyNetwork.replace("&type=tcp","&network=");
        const QList<QByteArray> sources{prefix,prefix+"&headerType=none",prefix+"&headerType=",prefix+"&path=%2Ffixture-secret",prefix+"&host=fixture-secret.invalid",prefix+"&serviceName=fixture-secret",user+":fixture-secret"+endpoint+query,user+endpoint+"/fixture-secret"+query,emptyType,emptyNetwork};
        for(const auto &uri:sources)for(const auto &existing:QStringList{"","已有的未映射配置诊断。"}){
            const bool supported=uri==prefix||uri==prefix+"&headerType=none";
            const auto imported=NodeImporter::parse(uri);QVERIFY(imported);QCOMPARE(imported.nodes.size(),1);
            auto old=imported.nodes.first();old.conversionIssues.clear(); // Actual pre-fix persisted shape.
            if(!existing.isEmpty())old.conversionIssues.append(existing);
            QTemporaryDir directory;QVERIFY(directory.isValid());const auto path=directory.filePath("old.dpapi");
            {NodeStore saved(path);QVERIFY(saved.importNodes({old}));QVERIFY(saved.select(old.id));}
            QFile file(path);QVERIFY(file.open(QIODevice::ReadOnly));const auto encrypted=file.readAll();file.close();
            NodeStore restored(path);QCOMPARE(restored.nodes().size(),1);QCOMPARE(restored.selectedId(),old.id);const auto node=restored.nodes().first();
            QCOMPARE(node.id,old.id);QCOMPARE(node.parameters,old.parameters);QCOMPARE(node.originalConfiguration,old.originalConfiguration);
            QCOMPARE(node.conversionIssues.isEmpty(),supported&&existing.isEmpty());
            if(!existing.isEmpty())QVERIFY(node.conversionIssues.contains(existing));
            if(!supported){QVERIFY(node.conversionIssues.size()>old.conversionIssues.size());QVERIFY(!node.conversionIssues.join(' ').contains("fixture-secret"));}
            if(!supported||!existing.isEmpty())QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
#ifdef SWIRL_USE_RUST_CORE
            else {QVERIFY(SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());QCOMPARE(SwirlProtocolRegistry::describe(node).value("tested"),QVariant(false));}
#endif
            QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),encrypted);
        }
    }
    void sourceGlobalsArePreservedAndCannotBecomeNodeOnlyImports() {
        const QByteArray ini="; fixture\n[ Proxy ] # nodes\nA = socks5, 127.0.0.1, 1080\n[Rule]\nFINAL,A\n[Future]\nopaque fixture-secret\n";
        const QByteArray json=R"({"outbounds":[{"type":"socks","tag":"A","server":"127.0.0.1","server_port":1080},{"type":"selector","tag":"choice","outbounds":["A"]}],"route":{"final":"choice"},"future":{"fixture-secret":true}})";
        const auto xray=QJsonDocument(QJsonObject{{"outbounds",QJsonArray{xrayRealitySource(),QJsonObject{{"protocol","freedom"},{"tag","direct"}}}},{"routing",QJsonObject{{"domainStrategy","IPIfNonMatch"}}},{"future",QJsonObject{{"fixture-secret",true}}}}).toJson();
        for(const auto &original:{ini,json,xray})for(const auto &body:{original,original.toBase64()}){
            const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);QVERIFY(!parsed.configuration.isEmpty());
            if(original==ini){QCOMPARE(parsed.configurationFormat,QString("ini"));QVERIFY(parsed.configuration["document"].toString().contains("opaque fixture-secret"));}
            else {QCOMPARE(parsed.configurationFormat,original==json?QString("sing-box"):QString("xray-v2ray-json"));QCOMPARE(parsed.configuration,QJsonDocument::fromJson(original).object());QVERIFY(parsed.executionConfiguration.isEmpty());}
            QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);
            const auto seed=NodeImporter::parse("proxies: [{name: retained, type: socks5, server: 127.0.0.1, port: 1081}]");QVERIFY(seed);QVERIFY(store.importNodes(seed.nodes));
            QFile file(store.filePath());QVERIFY(file.open(QIODevice::ReadOnly));const auto before=file.readAll();file.close();
            service.importText(QString::fromUtf8(body));QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),4000);QCOMPARE(store.nodes().size(),1);QCOMPARE(store.nodes().first().name,QString("retained"));
            QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),before);QVERIFY(!service.message().contains("fixture-secret"));
        }
        for(const auto &body:{QByteArray("[Proxy]\nA = socks5, 127.0.0.1, 1080\nBypass = direct\n"),QByteArray(R"({"outbounds":[{"type":"socks","tag":"A","server":"127.0.0.1","server_port":1080},{"type":"direct","tag":"bypass"}]})")}){
            const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));QVERIFY(!parsed.configuration.isEmpty());
        }
    }
    void xrayRealityRejectsUnknownConflictingOrMultipleSourceParameters() {
        const auto source=xrayRealitySource();const auto settings=source.value("settings").toObject();
        const auto endpoint=settings.value("vnext").toArray().first().toObject();const auto user=endpoint.value("users").toArray().first().toObject();
        const auto stream=source.value("streamSettings").toObject();const auto reality=stream.value("realitySettings").toObject();
        QList<QJsonObject> rejected;
        auto withStream=[&](const QJsonObject &value){auto node=source;node["streamSettings"]=value;return node;};
        auto withReality=[&](const QJsonObject &value){auto changed=stream;changed["realitySettings"]=value;return withStream(changed);};
        auto withEndpoint=[&](const QJsonObject &value){auto node=source;node["settings"]=QJsonObject{{"vnext",QJsonArray{value}}};return node;};
        auto withUser=[&](const QJsonObject &value){auto changed=endpoint;changed["users"]=QJsonArray{value};return withEndpoint(changed);};
        for(const auto &key:QStringList{"sendThrough","proxySettings","future"}){auto node=source;node[key]="fixture-secret";rejected.append(node);}
        for(const auto &mux:QJsonArray{QJsonValue(),true,QJsonObject{},QJsonObject{{"enabled",true}},QJsonObject{{"enabled",false},{"concurrency",1}}}){auto node=source;node["mux"]=mux;rejected.append(node);}
        for(const auto &key:QStringList{"address","future"}){auto node=source;auto changed=settings;changed[key]="fixture-secret";node["settings"]=changed;rejected.append(node);}
        for(const auto &endpoints:QJsonArray{QJsonValue(),QJsonObject{},QJsonArray{},QJsonArray{endpoint,endpoint}}){auto node=source;node["settings"]=QJsonObject{{"vnext",endpoints}};rejected.append(node);}
        for(const auto &users:QJsonArray{QJsonValue(),QJsonObject{},QJsonArray{},QJsonArray{user,user}}){auto changed=endpoint;changed["users"]=users;rejected.append(withEndpoint(changed));}
        for(const auto &port:QJsonArray{QJsonValue(),"443",false,0,65536,443.5}){auto changed=endpoint;changed["port"]=port;rejected.append(withEndpoint(changed));}
        auto changedEndpoint=endpoint;changedEndpoint["future"]="fixture-secret";rejected.append(withEndpoint(changedEndpoint));
        for(const auto &key:QStringList{"level","future"}){auto changed=user;changed[key]="fixture-secret";rejected.append(withUser(changed));}
        for(const auto &encryption:QJsonArray{QJsonValue(),"",true,"fixture-secret"}){auto changed=user;changed["encryption"]=encryption;rejected.append(withUser(changed));}
        auto missing=user;missing.remove("encryption");rejected.append(withUser(missing));missing=user;missing.remove("id");rejected.append(withUser(missing));
        for(const auto &key:QStringList{"network","security","realitySettings"}){auto changed=stream;changed.remove(key);rejected.append(withStream(changed));}
        for(const auto &network:QJsonArray{QJsonValue(),"ws","",false}){auto changed=stream;changed["network"]=network;rejected.append(withStream(changed));}
        auto changedStream=stream;changedStream["security"]="tls";rejected.append(withStream(changedStream));
        changedStream=stream;changedStream["sockopt"]=QJsonObject{{"mark",1}};rejected.append(withStream(changedStream));
        for(const auto &tcp:QJsonArray{QJsonValue(),QJsonObject{{"header",QJsonObject{{"type","http"}}}},QJsonObject{{"future","fixture-secret"}},QJsonObject{{"header",QJsonObject{{"type","none"},{"future","fixture-secret"}}}}}){
            auto changed=stream;changed["tcpSettings"]=tcp;rejected.append(withStream(changed));
        }
        changedStream=stream;changedStream["tcpSettings"]=QJsonObject{};changedStream["rawSettings"]=QJsonObject{{"header",QJsonObject{{"type","none"}}}};rejected.append(withStream(changedStream));
        for(const auto &key:QStringList{"publicKey","serverName","fingerprint","shortId"}){auto changed=reality;changed.remove(key);rejected.append(withReality(changed));changed=reality;changed[key]=false;rejected.append(withReality(changed));}
        for(const auto &key:QStringList{"alpn","mldsa65Verify","future","spiderX"}){auto changed=reality;changed[key]="fixture-secret";rejected.append(withReality(changed));}
        auto changedReality=reality;changedReality["password"]="fixture-secret";rejected.append(withReality(changedReality));
        changedReality=reality;changedReality["show"]=true;rejected.append(withReality(changedReality));
        for(const auto &node:rejected){
            // A valid preceding node cannot authorize a partial import after a
            // later malformed node, nor can wrapping it in Base64 hide fields.
            for(const auto &nodes:QList<QJsonArray>{QJsonArray{node},QJsonArray{source,node}}){
                const auto original=QJsonDocument(QJsonObject{{"outbounds",nodes}}).toJson();
                for(const auto &body:{original,original.toBase64()}){const auto parsed=NodeImporter::parse(body);QVERIFY2(!parsed,"Xray source fields were dropped or a list was flattened");QVERIFY(parsed.nodes.isEmpty());QVERIFY(!parsed.error.contains("fixture-secret"));QVERIFY(!parsed.error.contains(reality.value("publicKey").toString()));}
            }
        }
        auto noFlow=user;noFlow.remove("flow");auto node=withUser(noFlow);auto emptyShortId=reality;emptyShortId["shortId"]="";auto changed=stream;changed["realitySettings"]=emptyShortId;node["streamSettings"]=changed;
        const auto original=QJsonDocument(QJsonObject{{"outbounds",QJsonArray{node}}}).toJson();const auto parsed=NodeImporter::parse(original);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.first().originalConfiguration,node);QVERIFY(!parsed.nodes.first().parameters.contains("flow"));QCOMPARE(parsed.nodes.first().parameters.value("reality-opts").toObject().value("short-id"),QJsonValue(""));
    }
    void socks5TlsUriAliasesPreserveSecurity() {
        const QByteArray prefix="socks5-tls://synthetic-socks5-user:synthetic-socks5-password@127.0.0.1:1080";
        const auto secure=prefix+"#secure";
        const QByteArray plain="socks5://127.0.0.1:1081#plain";
        // A TLS alias is equally binding when it is the first URI, a later
        // item, or inside a Base64 subscription envelope.
        for(const auto &original:QList<QByteArray>{secure,plain+"\n"+secure})for(const auto &body:{original,original.toBase64()}){
            const auto parsed=NodeImporter::parse(body);QVERIFY2(bool(parsed),qPrintable(parsed.error));
            QCOMPARE(parsed.nodes.size(),original==secure?1:2);QVERIFY(parsed.configuration.isEmpty());
            const auto &node=parsed.nodes.last();QCOMPARE(node.protocol,QString("socks5"));
            QCOMPARE(node.parameters.value("tls"),QJsonValue(true));QVERIFY(node.conversionIssues.isEmpty());
            QCOMPARE(node.username,QString("synthetic-socks5-user"));QCOMPARE(node.password,QString("synthetic-socks5-password"));
            QCOMPARE(node.originalConfiguration.value("uri"),QJsonValue(QString::fromUtf8(secure)));
            if(parsed.nodes.size()==2){QVERIFY(!parsed.nodes.first().parameters.contains("tls"));QCOMPARE(parsed.nodes.first().originalConfiguration.value("uri"),QJsonValue(QString::fromUtf8(plain)));}
        }
        const auto conflict=prefix+"?security=none#conflict";
        for(const auto &original:QList<QByteArray>{conflict,plain+"\n"+conflict})for(const auto &body:{original,original.toBase64()})
            QVERIFY2(!NodeImporter::parse(body),"An explicit security=none cannot downgrade the implicit TLS URI scheme.");
        const auto unknown=prefix+"?tls=false#unknown";
        for(const auto &original:QList<QByteArray>{unknown,plain+"\n"+unknown})for(const auto &body:{original,original.toBase64()}){
            const auto parsed=NodeImporter::parse(body);QVERIFY2(bool(parsed),qPrintable(parsed.error));const auto &node=parsed.nodes.last();
            QCOMPARE(node.parameters.value("tls"),QJsonValue(true));QVERIFY(!node.conversionIssues.isEmpty());
            QCOMPARE(node.originalConfiguration.value("uri"),QJsonValue(QString::fromUtf8(unknown)));
            QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
        }
        for(const auto &source:QList<QByteArray>{
                "[Proxy]\nfixture = socks5-tls,127.0.0.1,1080,over-tls=false\n",
                "[server_local]\nsocks5-tls=127.0.0.1:1080,tag=fixture,tls=false\n"})
            for(const auto &body:{source,source.toBase64()})QVERIFY(!NodeImporter::parse(body));
        // This URI fix does not extend the raw Clash protocol vocabulary.
        QVERIFY(!NodeImporter::parse("proxies: [{name: fixture, type: socks5-tls, server: 127.0.0.1, port: 1080}]"));
    }
    void iniTransportAliasesCannotDowngradeSecurity() {
        for(const auto &protocol:{"vless","trojan"}) {
            const QByteArray prefix=QByteArray("[Proxy]\nfixture = ")+protocol+",example.org,443,"+(QByteArray(protocol)=="vless"?"11111111-1111-4111-8111-111111111111":"synthetic")+",";
            for(const auto &options:{"transport=reality", "transport=reality,tls=true", "tls=true,transport=reality", "transport=ws,ws=false", "ws=false,transport=ws", "obfs=ws,ws=false", "ws=false,obfs=ws", "transport=tcp,obfs=ws", "obfs=ws,transport=tcp", "transport=grpc,ws=true", "ws=true,transport=grpc", "transport=tls,public-key=synthetic", "public-key=synthetic,transport=tls", "transport="})
                for(const auto &body:{prefix+options,(prefix+options).toBase64()})QVERIFY2(!NodeImporter::parse(body),options);
            const QByteArray key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
            const auto reality=NodeImporter::parse(prefix+"transport=reality,public-key="+key);QVERIFY(reality);QVERIFY(reality.nodes.first().parameters.contains("reality-opts"));
            for(const auto &options:{"transport=ws,ws=true", "ws=true,transport=ws", "obfs=wss,transport=ws", "transport=ws,obfs=wss"}){const auto parsed=NodeImporter::parse(prefix+options);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.first().parameters.value("network"),QJsonValue("ws"));}
        }
    }
    void uriRealityRequiresAnExplicitSecurityLayerAndCredential() {
        const QByteArray plain="socks5://127.0.0.1:1081#retained";
        for(const auto &protocol:{"vless","trojan"}){
            const QByteArray prefix=QByteArray(protocol)+"://"+(QByteArray(protocol)=="vless"?"11111111-1111-4111-8111-111111111111":"synthetic-secret")+"@edge.example.org:443?";
            for(const auto &query:{"security=reality", "security=reality&sid=abcd", "security=reality&pbk=", "pbk=&security=reality", "security=reality&pbk=%20", "security=tls&pbk=synthetic-key", "pbk=synthetic-key&security=tls", "security=none&pbk=synthetic-key", "pbk=synthetic-key&security=none", "pbk=synthetic-key", "sid=abcd", "security=tls&sid="}){
                const auto invalid=prefix+query;
                for(const auto &original:{invalid,plain+"\n"+invalid})for(const auto &body:{original,original.toBase64()}){
                    const auto parsed=NodeImporter::parse(body);QVERIFY2(!parsed,query);QVERIFY(parsed.nodes.isEmpty());
                    QVERIFY(!parsed.error.contains("synthetic-secret"));QVERIFY(!parsed.error.contains("synthetic-key"));
                }
            }
            for(const auto &query:{"security=reality&pbk=synthetic-key&sid=abcd", "sid=abcd&pbk=synthetic-key&security=reality", "security=reality&pbk=synthetic-key&sid="}){
                const auto original=prefix+query;
                for(const auto &body:{original,original.toBase64()}){
                    const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));const auto &node=parsed.nodes.first();
                    QCOMPARE(node.parameters.value("tls"),QJsonValue(true));QCOMPARE(node.parameters.value("reality-opts").toObject().value("public-key"),QJsonValue("synthetic-key"));
                    QCOMPARE(node.originalConfiguration.value("uri"),QJsonValue(QString::fromUtf8(original)));
                    QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
                }
            }
            const auto ordinary=NodeImporter::parse(prefix+"security=tls");QVERIFY(ordinary);QVERIFY(ordinary.nodes.first().conversionIssues.isEmpty());
            QCOMPARE(ordinary.nodes.first().parameters.value("tls"),QJsonValue(true));QVERIFY(!ordinary.nodes.first().parameters.contains("reality-opts"));
        }
    }
    void singBoxTlsTypesAndFingerprintIntentArePreserved() {
        const QByteArray prefix=R"({"outbounds":[{"tag":"fixture","type":"vless","server":"edge.example.org","server_port":443,"uuid":"11111111-1111-4111-8111-111111111111","tls":)";
        const QList<QByteArray> invalidTls{
            "null", "false", "true", "1", "\"synthetic-secret\"", "[]",
            R"({"enabled":"true"})", R"({"enabled":1})", R"({"enabled":true,"insecure":"false"})",
            R"({"enabled":true,"reality":"synthetic-secret"})", R"({"enabled":true,"reality":[]})", R"({"enabled":true,"reality":null})",
            R"({"enabled":true,"reality":{"enabled":"true","public_key":"synthetic-secret"}})",
            R"({"enabled":true,"reality":{"enabled":1,"public_key":"synthetic-secret"}})",
            R"({"enabled":true,"utls":"chrome"})", R"({"enabled":true,"utls":[]})", R"({"enabled":true,"utls":null})",
            R"({"enabled":true,"utls":{"enabled":"true"}})", R"({"enabled":true,"utls":{"enabled":1}})",
            R"({"enabled":true,"utls":{"enabled":true,"fingerprint":null}})", R"({"enabled":true,"utls":{"enabled":true,"fingerprint":[]}})",
            R"({"enabled":true,"utls":{"enabled":true},"reality":{"enabled":true}})",
            R"({"enabled":true,"utls":{"enabled":true},"reality":{"enabled":true,"public_key":""}})",
            R"({"enabled":true,"utls":{"enabled":true},"reality":{"enabled":true,"public_key":42}})",
            R"({"enabled":true,"utls":{"enabled":true},"reality":{"enabled":true,"public_key":"synthetic-key","short_id":7}})",
            R"({"enabled":true,"reality":{"enabled":true,"public_key":"synthetic-key"}})",
            R"({"enabled":true,"utls":{"enabled":false},"reality":{"enabled":true,"public_key":"synthetic-key"}})",
            R"({"enabled":false,"utls":{"enabled":true}})", R"({"utls":{"enabled":true}})",
            R"({"enabled":false,"reality":{"enabled":true,"public_key":"synthetic-key"}})"
        };
        for(const auto &tls:invalidTls){
            const auto original=prefix+tls+"}]}";
            for(const auto &body:{original,original.toBase64()}){
                const auto parsed=NodeImporter::parse(body);QVERIFY2(!parsed,"Malformed TLS options became an ordinary connection");QVERIFY(parsed.nodes.isEmpty());
                QVERIFY(!parsed.error.contains("synthetic-secret"));QVERIFY(!parsed.error.contains("synthetic-key"));
            }
        }
        for(const auto &tls:QList<QByteArray>{"{}",R"({"enabled":false})",R"({"enabled":true})",R"({"enabled":true,"utls":{"enabled":false},"reality":{"enabled":false}})"}){
            const auto parsed=NodeImporter::parse(prefix+tls+"}]}");QVERIFY2(parsed,qPrintable(parsed.error));const auto &node=parsed.nodes.first();
            QVERIFY(node.conversionIssues.isEmpty());QVERIFY(!node.parameters.contains("client-fingerprint"));QVERIFY(!node.parameters.contains("reality-opts"));
        }
        for(const auto &fields:QList<QByteArray>{R"("enabled":true)",R"("enabled":true,"fingerprint":"")",R"("enabled":true,"fingerprint":"firefox")"}){
            const auto original=prefix+R"({"enabled":true,"utls":{)"+fields+"}}}]}";
            for(const auto &body:{original,original.toBase64()}){
                const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));const auto &node=parsed.nodes.first();
                QCOMPARE(node.parameters.value("client-fingerprint"),QJsonValue(fields.contains("firefox")?"firefox":"chrome"));
                QCOMPARE(node.originalConfiguration,QJsonDocument::fromJson(original).object().value("outbounds").toArray().first().toObject());
                QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
            }
        }
        for(const auto &fields:QList<QByteArray>{R"("enabled":false,"fingerprint":"chrome")",R"("fingerprint":"chrome_133")"}){
            const auto original=prefix+R"({"enabled":true,"utls":{)"+fields+"}}}]}";
            for(const auto &body:{original,original.toBase64()}){
                const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));const auto &node=parsed.nodes.first();
                QCOMPARE(node.originalConfiguration,QJsonDocument::fromJson(original).object().value("outbounds").toArray().first().toObject());
                QVERIFY(!node.conversionIssues.isEmpty());QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
            }
        }
        const auto original=prefix+R"({"enabled":true,"utls":{"enabled":true},"reality":{"enabled":true,"public_key":"synthetic-key","short_id":"abcd"}},"flow":"xtls-rprx-vision"}]})";
        const auto parsed=NodeImporter::parse(original);QVERIFY2(parsed,qPrintable(parsed.error));const auto &node=parsed.nodes.first();
        QCOMPARE(node.parameters.value("reality-opts").toObject().value("public-key"),QJsonValue("synthetic-key"));
        QCOMPARE(node.parameters.value("reality-opts").toObject().value("short-id"),QJsonValue("abcd"));
        QCOMPARE(node.parameters.value("client-fingerprint"),QJsonValue("chrome"));QCOMPARE(node.parameters.value("flow"),QJsonValue("xtls-rprx-vision"));
        QCOMPARE(node.originalConfiguration,QJsonDocument::fromJson(original).object().value("outbounds").toArray().first().toObject());
        QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
        const auto unknown=NodeImporter::parse(prefix+R"({"enabled":true,"utls":{"enabled":true,"future":"synthetic-secret"}}}]})");
        QVERIFY(unknown);QVERIFY(!unknown.nodes.first().conversionIssues.isEmpty());QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(unknown.nodes.first()).isEmpty());
        QVERIFY(!QJsonDocument::fromVariant(unknown.nodes.first().publicInfo()).toJson().contains("synthetic-secret"));
    }
    void singBoxTransportShapesAndFieldsCannotDowngrade() {
        const QByteArray prefix=R"({"outbounds":[{"tag":"fixture","type":"vless","server":"edge.example.org","server_port":443,"uuid":"11111111-1111-4111-8111-111111111111","transport":)";
        const QList<QByteArray> invalidTransport{
            "false", "true", "1", "\"ws\"", "[]", "{}",
            R"({"type":null})",R"({"type":1})",R"({"type":[]})",R"({"type":""})",R"({"type":"tcp"})",R"({"type":"h2"})",R"({"type":"synthetic-secret"})",
            R"({"type":"ws","path":42})",R"({"type":"ws","path":[]})",
            R"({"type":"grpc","service_name":42})",R"({"type":"ws","early_data_header_name":false})",
            R"({"type":"ws","headers":[]})",R"({"type":"ws","headers":"synthetic-secret"})",
            R"({"type":"ws","headers":{"Host":42}})",R"({"type":"ws","headers":{"Host":["ws.example.org",42]}})",
            R"({"type":"ws","max_early_data":true})",R"({"type":"ws","max_early_data":"0"})",
            R"({"type":"ws","max_early_data":-1})",R"({"type":"ws","max_early_data":1.5})",R"({"type":"ws","max_early_data":4294967296})"
        };
        for(const auto &transport:invalidTransport){
            const auto original=prefix+transport+"}]}";
            for(const auto &body:{original,original.toBase64()}){
                const auto parsed=NodeImporter::parse(body);QVERIFY2(!parsed,"Invalid transport silently became TCP or a default WS path");QVERIFY(parsed.nodes.isEmpty());
                QVERIFY(!parsed.error.contains("synthetic-secret"));
            }
        }
        const auto absent=prefix+"null}]}";
        for(const auto &body:{absent,absent.toBase64()}){
            const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));const auto &node=parsed.nodes.first();
            QVERIFY(node.conversionIssues.isEmpty());QVERIFY(!node.parameters.contains("network"));QVERIFY(!node.parameters.contains("ws-opts"));
            QCOMPARE(node.originalConfiguration,QJsonDocument::fromJson(absent).object().value("outbounds").toArray().first().toObject());
        }
        const QList<QJsonObject> websocketOptions{
            QJsonObject{{"type","ws"}},QJsonObject{{"type","ws"},{"path",""}},
            QJsonObject{{"type","ws"},{"path","/socket%20path?fixture=1"},{"headers",QJsonObject{{"hOsT","ws.fixture.invalid:8443"}}}},
            QJsonObject{{"type","ws"},{"path","/ws"},{"headers",QJsonObject{{"X-Fixture",QJsonArray{"first","second"}}}},{"max_early_data",qint64(0)},{"early_data_header_name",""}},
            QJsonObject{{"type","ws"},{"max_early_data",qint64(4294967295)},{"early_data_header_name","Sec-WebSocket-Protocol"}}
        };
        for(const auto &transport:websocketOptions){
            const auto original=prefix+QJsonDocument(transport).toJson(QJsonDocument::Compact)+"}]}";
            for(const auto &body:{original,original.toBase64()}){
                const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));const auto &node=parsed.nodes.first();QVERIFY(node.conversionIssues.isEmpty());
                QCOMPARE(node.parameters.value("network"),QJsonValue("ws"));const auto ws=node.parameters.value("ws-opts").toObject();
                QCOMPARE(ws.value("path"),QJsonValue(transport.value("path").toString().isEmpty()?"/":transport.value("path").toString()));
                QCOMPARE(ws.value("headers"),transport.contains("headers")?transport.value("headers"):QJsonValue(QJsonObject{}));
                QCOMPARE(ws.value("max-early-data"),transport.value("max_early_data"));QCOMPARE(ws.value("early-data-header-name"),transport.value("early_data_header_name"));
                QCOMPARE(node.originalConfiguration,QJsonDocument::fromJson(original).object().value("outbounds").toArray().first().toObject());
            }
        }
        const QJsonObject defaultWs{{"path","/"},{"headers",QJsonObject{}}};
        const QList<QPair<QByteArray,QJsonObject>> nullableWs{
            {R"({"type":"ws","path":null})",defaultWs},
            {R"({"type":"ws","headers":null})",defaultWs},
            {R"({"type":"ws","headers":{"Host":null,"X-Fixture":null}})",defaultWs},
            {R"({"type":"ws","max_early_data":null,"early_data_header_name":null})",defaultWs},
            {R"({"type":"ws","path":null,"headers":null,"max_early_data":null,"early_data_header_name":null})",defaultWs},
            {R"({"type":"ws","headers":{"Host":null,"X-Fixture":["first",null,"second"]}})",
             QJsonObject{{"path","/"},{"headers",QJsonObject{{"X-Fixture",QJsonArray{"first","","second"}}}}}}
        };
        for(const auto &[transport,expected]:nullableWs){
            const auto original=prefix+transport+"}]}";
            for(const auto &body:{original,original.toBase64()}){
                const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));const auto &node=parsed.nodes.first();
                QVERIFY(node.conversionIssues.isEmpty());QCOMPARE(node.parameters.value("ws-opts"),QJsonValue(expected));
                QCOMPARE(node.originalConfiguration,QJsonDocument::fromJson(original).object().value("outbounds").toArray().first().toObject());
            }
        }
        for(const auto &transport:QList<QByteArray>{R"({"type":"ws","service_name":"synthetic-secret"})",R"({"type":"ws","future":"synthetic-secret"})",R"({"type":"grpc","path":"/synthetic-secret"})",R"({"type":"grpc","headers":{"Host":"synthetic-secret"}})"}){
            const auto original=prefix+transport+"}]}";const auto parsed=NodeImporter::parse(original);QVERIFY2(parsed,qPrintable(parsed.error));const auto &node=parsed.nodes.first();
            QVERIFY(!node.conversionIssues.isEmpty());QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(node).isEmpty());
            QCOMPARE(node.originalConfiguration.value("transport"),QJsonValue(QJsonDocument::fromJson(transport).object()));
            QVERIFY(!QJsonDocument::fromVariant(node.publicInfo()).toJson().contains("synthetic-secret"));
        }
        const auto grpc=NodeImporter::parse(prefix+R"({"type":"grpc","service_name":"fixture-service"}}]})");QVERIFY(grpc);
        QCOMPARE(grpc.nodes.first().parameters.value("network"),QJsonValue("grpc"));QCOMPARE(grpc.nodes.first().parameters.value("grpc-opts").toObject().value("grpc-service-name"),QJsonValue("fixture-service"));
        QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(grpc.nodes.first()).isEmpty());
        const auto nullGrpc=NodeImporter::parse(prefix+R"({"type":"grpc","service_name":null}}]})");QVERIFY(nullGrpc);
        QCOMPARE(nullGrpc.nodes.first().parameters.value("grpc-opts").toObject().value("grpc-service-name"),QJsonValue(""));
        QVERIFY(nullGrpc.nodes.first().originalConfiguration.value("transport").toObject().value("service_name").isNull());
        QVERIFY(!SwirlProtocolRegistry::nativeNodeReason(nullGrpc.nodes.first()).isEmpty());
    }
    void iniCompleteProfileHasClosedExecutionSemantics() {
        const QByteArray original="[Proxy]\nA = socks5,127.0.0.1,1080\nDIRECT = direct\nREJECT = reject\n[Proxy Group]\nroute = select,A,DIRECT\nnested = select,route,REJECT\n[Rule]\nDOMAIN,exact.invalid,REJECT\nDOMAIN-SUFFIX,suffix.invalid,route\nDOMAIN-KEYWORD,keyword,nested\nFINAL,route\n";
        for(const auto &body:{original,original.toBase64()}) {
            const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);QCOMPARE(parsed.configurationFormat,QString("ini"));QCOMPARE(parsed.configuration["document"],QJsonValue(QString::fromUtf8(original).trimmed()));
            QCOMPARE(parsed.executionConfiguration["proxy-groups"].toArray().size(),2);const auto rules=parsed.executionConfiguration["rules"].toArray();QCOMPARE(rules.size(),4);QCOMPARE(rules.last(),QJsonValue("MATCH,route"));
            QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService importer(&store);importer.importText(QString::fromUtf8(body));QTRY_VERIFY_WITH_TIMEOUT(!importer.busy(),4000);QVERIFY(store.nodes().isEmpty());
        }
        QList<QByteArray> rejected;
        for(const auto &tail:{"[General]\ndns-server=192.0.2.53\n", "[Remote Rule]\nhttps://fixture.invalid/rules,policy=route\n", "[Future]\nopaque=value\n", "DOMAIN,late.invalid,route\n"})rejected.append(original+tail);
        for(const auto &replacement:{"route = url-test,A,DIRECT", "route = select,A,A", "route = select,A,policy-path=remote", "route = select", "route = select,A\nroute = select,DIRECT"}) {auto body=original;body.replace("route = select,A,DIRECT",replacement);rejected.append(body);}
        for(const auto &replacement:{"IP-CIDR,192.0.2.0/24,route", "PROCESS-NAME,fixture.exe,route", "DOMAIN,exact.invalid,route,no-resolve"}) {auto body=original;body.replace("DOMAIN,exact.invalid,REJECT",replacement);rejected.append(body);}
        {auto body=original;body.replace("DIRECT = direct\n","DIRECT = direct\nDIRECT = direct\n");rejected.append(body);body=original;body.replace("DIRECT = direct","Bypass = direct");rejected.append(body);body=original;body.replace("FINAL,route\n","");rejected.append(body);}
        for(const auto &body:rejected)for(const auto &wrapped:{body,body.toBase64()}){const auto parsed=NodeImporter::parse(wrapped);QVERIFY2(parsed,qPrintable(parsed.error));QVERIFY(!parsed.configuration.isEmpty());QVERIFY2(parsed.executionConfiguration.isEmpty(),"Unknown profile semantics became executable");}
    }
    void iniEnvelopeAndWrappedJsonFailClosed() {
        const QByteArray node="A = socks5, 127.0.0.1, 1080\n";
        const QList<QByteArray> malformed{
            "[Proxy]\n"+node+"[Rule\nFINAL,A", "[Proxy]\n"+node+"[Rule] trailing\nFINAL,A",
            "[Proxy]\n"+node+"[ proxy ]\nB = socks5, 127.0.0.1, 1081", "[Proxy]\n"+node+"[]\n",
            "[Proxy]\n"+node+"["+QByteArray(129,'a')+"]\n", "preface = ignored\n[Proxy]\n"+node,
            QByteArray(1,char(0x0b))+"[Proxy]\n"+node, "[Proxy]\n"+node+QByteArray(1,char(0x7f)),
            "[Proxy]\n"+node+QByteArray(1,char(0xff)), "[Proxy]\n"+node+QByteArray(1,char(0xe4)), "[Proxy]\n"+node+"[Future\tSection]\n",
            QByteArray(R"({"outbounds":[{"type":"socks","tag":"A","server":"127.0.0.1","server_port":1080,"server_port":1081}]})")
        };
        for(const auto &body:malformed)for(const auto &wrapped:{body,body.toBase64(),body.toBase64().toBase64()})QVERIFY(!NodeImporter::parse(wrapped));
        const QByteArray yaml="proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]\n";
        for(const auto &suffix:{QByteArray("---\ndns: {nameserver: [192.0.2.53]}\n"),QByteArray("...\n---\nfuture: true\n"),QByteArray("---\n[invalid"),QByteArray("---\n")}){
            const auto body=yaml+suffix;for(const auto &wrapped:{body,body.toBase64(),QByteArray("STATUS=fixture\n")+body})QVERIFY(!NodeImporter::parse(wrapped));
        }
        const auto json=malformed.last();QVERIFY(!NodeImporter::parse("STATUS=fixture\n"+json));QVERIFY(!NodeImporter::parse(QByteArray("\xef\xbb\xbf")+json));QVERIFY(!NodeImporter::parse(QByteArray("\xef\xbb\xbf\xef\xbb\xbf")+json));
        QVERIFY(NodeImporter::parse("[{name: flow, type: socks5, server: 127.0.0.1, port: 1080}]"));
        QVERIFY(NodeImporter::parse("[\n{name: flow, type: socks5, server: 127.0.0.1, port: 1080}\n]"));
        for(const auto &body:{QByteArray("; comments\n[ Proxy ] # nodes\n")+node,QByteArray("[server_local] ; nodes\nsocks5=127.0.0.1:1080, tag=A\n"),node}){
            const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));QVERIFY(parsed.configuration.isEmpty());
        }
    }
    void typedOptionsAndAliasesCannotOverwriteImportedState() {
        const QByteArray ini="[Proxy]\nfixture = trojan, example.org, 443, fixture-secret, ";
        const QByteArray uri="trojan://fixture-secret@example.org:443?";
        QList<QByteArray> rejected;
        for(const auto &option:{"udp=maybe","tls=garbage","skip-cert-verify=off","tls-verification=on","fast-open=2","ws=invalid","aead=invalid","tls=1","password=second","sni=a.example,tls-name=b.example","fast-open=false,tfo=false","skip-cert-verify=false,tls-verification=false"})rejected.append(ini+option);
        for(const auto &option:{"udp=maybe","insecure=off","allowInsecure=FALSE","peer=a.example&sni=b.example","allowInsecure=0&insecure=1","skip-cert-verify=false&insecure=true","sni=a.example&sni=a.example"})rejected.append(uri+option);
        for(const auto &plugin:{"obfs-local%3Bobfs%3Dhttp%3Bobfs%3Dtls", "obfs-local%3Bobfs%3Dhttp%3Bmode%3Dhttp", "simple-obfs%3Bobfs-host%3Da.example%3Bhost%3Db.example"})rejected.append(QByteArray("ss://YWVzLTEyOC1nY206c3ludGhldGlj@example.org:443?plugin=")+plugin);
        rejected.append("[Proxy]\nfixture = trojan,example.org,443,password=first,second");
        rejected.append("[Proxy]\nfixture = vless,example.org,443,11111111-1111-4111-8111-111111111111,uuid=22222222-2222-4222-8222-222222222222");
        rejected.append("[Proxy]\nfixture = socks5,example.org,1080,fixture,fixture-secret,password=second");
        for(const auto &declaration:{"https,example.org,443,tls=false", "socks5-tls,example.org,443,over-tls=false", "http,example.org,443,tls=false,transport=tls", "http,example.org,443,transport=tls,tls=false"})rejected.append(QByteArray("[Proxy]\nfixture = ")+declaration);
        rejected.append(uri+"security=none");
        rejected.append("vless://11111111-1111-4111-8111-111111111111@example.org:443?security=reality");
        rejected.append("vless://11111111-1111-4111-8111-111111111111@example.org:443?security=tls&pbk=fixture-secret");
        rejected.append(R"({"outbounds":[{"type":"vless","tag":"invalid","server":"example.org","server_port":443,"uuid":"11111111-1111-4111-8111-111111111111","tls":{"enabled":true,"reality":"fixture-secret"}}]})");
        rejected.append(R"({"outbounds":[{"type":"vless","tag":"invalid","server":"example.org","server_port":443,"uuid":"11111111-1111-4111-8111-111111111111","tls":{"enabled":true,"utls":{"enabled":"true","fingerprint":"fixture-secret"}}}]})");
        for(const auto &transport:QList<QByteArray>{R"("fixture-secret")",R"({"type":42})",R"({"type":"ws","path":42})",R"({"type":"ws","headers":["fixture-secret"]})"})
            rejected.append(QByteArray(R"({"outbounds":[{"type":"vless","tag":"invalid","server":"example.org","server_port":443,"uuid":"11111111-1111-4111-8111-111111111111","transport":)")+transport+"}]}");
        for(const auto &protocol:{"https","socks5-tls"})rejected.append(QByteArray("[server_local]\n")+protocol+"=example.org:443,tag=fixture,over-tls=false");
        for(const auto &body:rejected)for(const auto &wrapped:{body,body.toBase64()}){
            const auto parsed=NodeImporter::parse(wrapped);QVERIFY2(!parsed,"Malformed or conflicting typed option was accepted");
            QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);
            const auto seed=NodeImporter::parse("proxies: [{name: retained, type: socks5, server: 127.0.0.1, port: 1081}]");QVERIFY(seed);QVERIFY(store.importNodes(seed.nodes));
            QFile file(store.filePath());QVERIFY(file.open(QIODevice::ReadOnly));const auto before=file.readAll();file.close();
            service.importText(QString::fromUtf8(wrapped));QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),4000);QCOMPARE(store.nodes().size(),1);QCOMPARE(store.nodes().first().name,QString("retained"));
            QVERIFY(file.open(QIODevice::ReadOnly));QCOMPARE(file.readAll(),before);QVERIFY(!service.message().contains("fixture-secret"));
        }
    }
    void legacyLoonAndEquivalentUriAliasesRetainTypedValues() {
        for(const auto &protocol:{"https","socks5-tls"})for(const auto &suffix:{"",",tls=true"}){
            const auto parsed=NodeImporter::parse(QByteArray("[server_local]\n")+protocol+"=example.org:443,tag=fixture"+suffix);QVERIFY(parsed);QCOMPARE(parsed.nodes.first().parameters.value("tls"),QJsonValue(true));
        }
        const QByteArray ini="[Proxy]\nfixture = trojan, example.org, 443, \"secret:with,comma=plus+percent%25\", tls-name:tls.example.org, skip-cert-verify:FALSE, fast-open:false";
        for(const auto &body:{ini,ini.toBase64()}){
            const auto parsed=NodeImporter::parse(body);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);const auto &n=parsed.nodes.first();
            QCOMPARE(n.password,QString("secret:with,comma=plus+percent%25"));QCOMPARE(n.serverName,QString("tls.example.org"));QVERIFY(n.conversionIssues.isEmpty());
            QCOMPARE(n.parameters.value("tls"),QJsonValue(true));QCOMPARE(n.parameters.value("skip-cert-verify"),QJsonValue(false));QCOMPARE(n.parameters.value("tfo"),QJsonValue(false));QVERIFY(!n.originalConfiguration.isEmpty());
        }
        for(const auto &declaration:{QByteArray("\"Shadowsocks\",example.org,443,aes-128-gcm,\"  secret=a,b:c  \",http,obfs.example"),QByteArray("trojan,example.org,443,\"  secret=a,b:c  \"")}){
            const auto parsed=NodeImporter::parse("[Proxy]\nfixture = "+declaration);QVERIFY(parsed);QVERIFY(parsed.nodes.first().conversionIssues.isEmpty());QCOMPARE(parsed.nodes.first().password,QString("  secret=a,b:c  "));
        }
        for(const auto &field:{QByteArray("\"  fixture=with,comma:and\\\"quote\\\\slash  \""),QByteArray("password=\"  fixture=with,comma:and\\\"quote\\\\slash  \"")}){
            const auto parsed=NodeImporter::parse("[Proxy]\nfixture = trojan,example.org,443,"+field);QVERIFY(parsed);QCOMPARE(parsed.nodes.first().password,QString("  fixture=with,comma:and\"quote\\slash  "));
        }
        for(const auto &options:{"peer=tls.example.org&sni=tls.example.org&allowInsecure=0&insecure=false&skip-cert-verify=false", "sni=tls.example.org&peer=tls.example.org&skip-cert-verify=0&insecure=0&allowInsecure=false"}){
            const auto body=QByteArray("trojan://secret%3Awith%2Ccomma%3Dplus%2Bpercent%2525@example.org:443?")+options;
            for(const auto &wrapped:{body,body.toBase64()}){
                const auto parsed=NodeImporter::parse(wrapped);QVERIFY2(parsed,qPrintable(parsed.error));const auto &n=parsed.nodes.first();QCOMPARE(n.password,QString("secret:with,comma=plus+percent%25"));QCOMPARE(n.serverName,QString("tls.example.org"));QCOMPARE(n.parameters.value("skip-cert-verify"),QJsonValue(false));QVERIFY(n.conversionIssues.isEmpty());
            }
        }
    }
    void completeConfigurationWithoutOwnerDoesNotDiscardGlobals() {
        QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService imports(&store);
        imports.importText("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]\nrules: [MATCH,DIRECT]\n");
        QTRY_VERIFY_WITH_TIMEOUT(!imports.busy(),4000);QVERIFY(store.nodes().isEmpty());QVERIFY(!QFile::exists(store.filePath()));
    }
#ifndef SWIRL_USE_RUST_CORE
    void compatibilityModeRejectsCompleteDocumentWithoutLosingFields() {
        QTemporaryDir directory;EngineController controller(std::make_unique<MihomoAdapter>(),nullptr,directory.filePath("nodes.dpapi"));
        controller.imports()->importText("proxies: [{name: A, type: socks5, server: 127.0.0.1, port: 1080}]\nproxy-groups: [{name: route, type: select, proxies: [A], default-selected: A, future-option: true}]\nrules: ['MATCH,route']\n");
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),4000);QVERIFY(controller.nodeCatalog().isEmpty());QVERIFY(controller.policyGroups().isEmpty());
        QVERIFY(!QFile::exists(directory.filePath("nodes.dpapi")));QVERIFY(controller.imports()->message().contains("Rust"));
    }
#endif
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
    void httpsRedirectAndDowngradeProtection() {
        const auto original=QSslConfiguration::defaultConfiguration();
        struct Restore {QSslConfiguration value;~Restore(){QSslConfiguration::setDefaultConfiguration(value);}} restore{original};
        QFile certificate(QStringLiteral(SWIRL_FIXTURE_DIR "/localhost-cert.pem")),key(QStringLiteral(SWIRL_FIXTURE_DIR "/localhost-key.pem"));
        QVERIFY(certificate.open(QIODevice::ReadOnly));QVERIFY(key.open(QIODevice::ReadOnly));
        const QSslCertificate cert(certificate.readAll());const QSslKey privateKey(key.readAll(),QSsl::Rsa);
        QVERIFY(!cert.isNull());QVERIFY(!privateKey.isNull());
        auto trusted=original;trusted.addCaCertificate(cert);QSslConfiguration::setDefaultConfiguration(trusted);
        auto serverConfiguration=trusted;serverConfiguration.setLocalCertificate(cert);serverConfiguration.setPrivateKey(privateKey);serverConfiguration.setPeerVerifyMode(QSslSocket::VerifyNone);
        HttpsSubscriptionServer first(serverConfiguration),second(serverConfiguration);QVERIFY(first.listen(QHostAddress::LocalHost,0));QVERIFY(second.listen(QHostAddress::LocalHost,0));
        first.code=302;first.location=second.url().toEncoded();second.content=socks(1080);
        QTemporaryDir temp;NodeStore store(temp.filePath("nodes"));NodeImportService service(&store);
        service.importUrl(second.url());QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),8000);QCOMPARE(store.nodes().size(),1);QCOMPARE(second.count,1);
        const auto id=store.nodes().first().id;QVERIFY(store.select(id));
        service.importUrl(first.url());QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),8000);QCOMPARE(first.count,1);QCOMPARE(second.count,1);QCOMPARE(store.nodes().size(),1);QCOMPARE(store.selectedId(),id);
        SubscriptionServer plain;QVERIFY(plain.listen(QHostAddress::LocalHost,0));first.location=plain.url().toEncoded();
        service.importUrl(first.url());QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),8000);QVERIFY(service.message().contains(QStringLiteral("降级")));QCOMPARE(plain.count,0);QCOMPARE(store.nodes().size(),1);QCOMPARE(store.selectedId(),id);
    }
    void redirectsPreserveNodesAndBoundLoops() {
        SubscriptionServer first,second;QVERIFY(first.listen(QHostAddress::LocalHost,0));QVERIFY(second.listen(QHostAddress::LocalHost,0));
        first.code=302;first.location=second.url().toEncoded();second.content=socks(1080);
        QTemporaryDir temp;NodeStore store(temp.filePath("nodes"));NodeImportService service(&store);
        service.importUrl(second.url());QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),5000);QCOMPARE(store.nodes().size(),1);QCOMPARE(store.nodes().first().port,quint16(1080));
        const auto id=store.nodes().first().id;QVERIFY(store.select(id));
        service.importUrl(first.url());QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),5000);QCOMPARE(first.count,1);QCOMPARE(second.count,1);QCOMPARE(store.nodes().size(),1);QCOMPARE(store.selectedId(),id);
        first.location=first.url().toEncoded();service.importUrl(first.url());QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),5000);QCOMPARE(store.nodes().size(),1);QVERIFY(service.message().contains(QStringLiteral("重定向")));QVERIFY(first.count<=7);
        first.location="file:///C:/private";service.importUrl(first.url());QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),5000);QCOMPARE(store.nodes().size(),1);QVERIFY(service.message().contains(QStringLiteral("不安全")));
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
        QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);
        QVERIFY(controller.apiHealthy());QCOMPARE(controller.processId(),pid);
        QCOMPARE(controller.selectedNodeId(),id);
        const auto forwardedBefore=network.a.forwarded;
        controller.testNode(network.url());QTRY_VERIFY_WITH_TIMEOUT(!controller.nodeBusy(),8000);
        QVERIFY(controller.requestSucceeded());QVERIFY(network.a.forwarded>forwardedBefore);QCOMPARE(network.b.forwarded,0);
        // A refresh must preserve existing streams. The updated node snapshot
        // is applied only after the user explicitly disconnects and reconnects.
        controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);
        controller.connectNode(id);QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),18000);
        controller.testNode(network.url());QTRY_VERIFY_WITH_TIMEOUT(!controller.nodeBusy(),8000);
        QVERIFY(controller.requestSucceeded());QVERIFY(network.b.forwarded>=2);
        controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),4000);QTcpServer reuse;QVERIFY(reuse.listen(QHostAddress::LocalHost,controller.proxyPort()));
        reuse.close();imports->refreshSubscription(sid);controller.stop();
        QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),5000);QTest::qWait(300);QVERIFY(!controller.processAlive());
        qInfo()<<"IMPORTED_REAL_CHAIN: selected A remains live through refresh; manual reconnect selects B; no remote environment claimed";
    }
    void hysteria2UriParsesAuthPortSniObfsAndFingerprint() {
        for(const auto &scheme:QList<QByteArray>{"hysteria2","hy2"}){
            const QByteArray uri=scheme+"://secret-auth@example.org:443?sni=camouflage.invalid&obfs=salamander&obfs-password=fixture-obfs&pinSHA256="+QByteArray(32,'\xab').toHex(':').toUpper()+"&alpn=h3&up=100&down=50#Fixture%20Node";
            const auto parsed=NodeImporter::parse(uri);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
            const auto node=parsed.nodes.first();QCOMPARE(node.protocol,QString("hysteria2"));QCOMPARE(node.host,QString("example.org"));QCOMPARE(node.port,quint16(443));
            QCOMPARE(node.password,QString("secret-auth"));QCOMPARE(node.serverName,QString("camouflage.invalid"));QCOMPARE(node.name,QString("Fixture Node"));
            QCOMPARE(node.parameters.value("obfs"),QJsonValue("salamander"));QCOMPARE(node.parameters.value("obfs-password"),QJsonValue("fixture-obfs"));
            QCOMPARE(node.parameters.value("fingerprint"),QJsonValue(QString::fromLatin1(QByteArray(32,'\xab').toHex())));QCOMPARE(node.parameters.value("up"),QJsonValue("100"));QCOMPARE(node.parameters.value("down"),QJsonValue("50"));
            QVERIFY(node.conversionIssues.isEmpty());
        }
    }
    void hysteria2UriHandlesDefaultPortIPv6AndMultiPort() {
        {
            const QByteArray uri="hysteria2://example.org";
            const auto parsed=NodeImporter::parse(uri);QVERIFY2(parsed,qPrintable(parsed.error));
            QCOMPARE(parsed.nodes.first().port,quint16(443));QVERIFY(parsed.nodes.first().password.isEmpty());
        }
        {
            const QByteArray uri="hy2://auth@[2001:db8::1]:8443";
            const auto parsed=NodeImporter::parse(uri);QVERIFY2(parsed,qPrintable(parsed.error));
            QCOMPARE(parsed.nodes.first().host,QString("2001:db8::1"));QCOMPARE(parsed.nodes.first().port,quint16(8443));
        }
        {
            const QByteArray uri="hysteria2://auth@example.org:443,5000-6000";
            const auto parsed=NodeImporter::parse(uri);QVERIFY2(parsed,qPrintable(parsed.error));
            const auto node=parsed.nodes.first();QCOMPARE(node.port,quint16(0));QCOMPARE(node.parameters.value("ports"),QJsonValue("443,5000-6000"));
        }
    }
    void hysteria2UriAcceptsRootPathBeforeQuery() {
        for(const auto &uri:QList<QByteArray>{"hysteria2://fixture-pass@example.com:443/?sni=example.com","hy2://fixture-pass@example.com/?sni=example.com",
            "hysteria2://fixture-pass@[2001:db8::1]:8443/?sni=example.com","hysteria2://fixture-pass@example.com:443,5000-6000/?sni=example.com","hysteria2://fixture-pass@example.com:443/"}){
            const auto parsed=NodeImporter::parse(uri);QVERIFY2(parsed,qPrintable(QString::fromUtf8(uri)+": "+parsed.error));
            const auto node=parsed.nodes.first();QCOMPARE(node.password,QString("fixture-pass"));QVERIFY(node.conversionIssues.isEmpty());
            QCOMPARE(node.originalConfiguration.value("uri"),QJsonValue(QString::fromUtf8(uri)));
        }
        QCOMPARE(NodeImporter::parse("hysteria2://fixture-pass@example.com:443/?sni=example.com").nodes.first().port,quint16(443));
        QCOMPARE(NodeImporter::parse("hy2://fixture-pass@example.com/?sni=example.com").nodes.first().port,quint16(443));
        QCOMPARE(NodeImporter::parse("hysteria2://fixture-pass@example.com:443/?sni=example.com").nodes.first().serverName,QString("example.com"));
        QCOMPARE(NodeImporter::parse("hysteria2://fixture-pass@[2001:db8::1]:8443/?sni=example.com").nodes.first().host,QString("2001:db8::1"));
        QCOMPARE(NodeImporter::parse("hysteria2://fixture-pass@example.com:443,5000-6000/?sni=example.com").nodes.first().parameters.value("ports"),QJsonValue("443,5000-6000"));
        // Percent-encoded credentials and names decode exactly once.
        const auto encoded=NodeImporter::parse("hysteria2://p%40ss%3Aword%2F@example.com:443/?sni=example.com#Node%20%E4%B8%80");
        QVERIFY2(encoded,qPrintable(encoded.error));QCOMPARE(encoded.nodes.first().password,QString("p@ss:word/"));QCOMPARE(encoded.nodes.first().name,QString::fromUtf8("Node \xe4\xb8\x80"));
        // A non-root path has no defined meaning and must not be dropped.
        QVERIFY(!NodeImporter::parse("hysteria2://fixture-pass@example.com:443/extra?sni=example.com"));
        QVERIFY(!NodeImporter::parse("hysteria2://fixture-pass@example.com:443//?sni=example.com"));
        // pinSHA256 must be a full SHA-256 digest.
        QVERIFY(!NodeImporter::parse("hysteria2://fixture-pass@example.com:443?pinSHA256=AA:BB:CC:DD"));
        QVERIFY(!NodeImporter::parse("hysteria2://fixture-pass@example.com:443?pinSHA256="+QByteArray(64,'z')));
        const auto plain=NodeImporter::parse("hysteria2://fixture-pass@example.com:443?pinSHA256="+QByteArray(32,'\x01').toHex());
        QVERIFY2(plain,qPrintable(plain.error));QCOMPARE(plain.nodes.first().parameters.value("fingerprint"),QJsonValue(QString::fromLatin1(QByteArray(32,'\x01').toHex())));
    }
    void hysteria2UriRejectsInvalidOrUnsafeInput() {
        QVERIFY(!NodeImporter::parse("hysteria2://auth@example.org:"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@example.org:44a"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@example.org:443,"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@[2001:db8::1"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@[2001:db8::1]x"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@example.org:443?insecure=yes"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@example.org:0"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@example.org:70000"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@example.org:443,99999"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@example.org:443?insecure=true"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@example.org:443?obfs=salamander"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@example.org:443?sni=a&sni=b"));
        QVERIFY(!NodeImporter::parse("hysteria2://auth@"));
        const auto echo=NodeImporter::parse("hysteria2://auth@example.org:443?ech=1");
        QVERIFY2(echo,qPrintable(echo.error));QVERIFY(!echo.nodes.first().conversionIssues.isEmpty());
    }
    void tuicUriParsesUuidPasswordAndCongestionOptions() {
        const QByteArray uri="tuic://00112233-4455-6677-8899-aabbccddeeff:fixture-pass@example.org:443?sni=camouflage.invalid&congestion_control=bbr&udp_relay_mode=native&alpn=h3&allow_insecure=0#TUIC%20Fixture";
        const auto parsed=NodeImporter::parse(uri);QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1);
        const auto node=parsed.nodes.first();QCOMPARE(node.protocol,QString("tuic"));QCOMPARE(node.host,QString("example.org"));QCOMPARE(node.port,quint16(443));
        QCOMPARE(node.parameters.value("uuid"),QJsonValue("00112233-4455-6677-8899-aabbccddeeff"));QCOMPARE(node.password,QString("fixture-pass"));
        QCOMPARE(node.serverName,QString("camouflage.invalid"));QCOMPARE(node.name,QString("TUIC Fixture"));
        QCOMPARE(node.parameters.value("congestion-controller"),QJsonValue("bbr"));QCOMPARE(node.parameters.value("udp-relay-mode"),QJsonValue("native"));
        QCOMPARE(node.parameters.value("skip-cert-verify"),QJsonValue(false));QVERIFY(node.conversionIssues.isEmpty());
    }
    void tuicUriRejectsInvalidUuidOrDuplicateParameters() {
        QVERIFY(!NodeImporter::parse("tuic://not-a-uuid:pass@example.org:443"));
        QVERIFY(!NodeImporter::parse("tuic://00112233-4455-6677-8899-aabbccddeeff:pass@example.org:443?sni=a&sni=b"));
        QVERIFY(!NodeImporter::parse("tuic://00112233-4455-6677-8899-aabbccddeeff:pass@example.org:0"));
        const auto unknown=NodeImporter::parse("tuic://00112233-4455-6677-8899-aabbccddeeff:pass@example.org:443?unknown-flag=1");
        QVERIFY2(unknown,qPrintable(unknown.error));QVERIFY(!unknown.nodes.first().conversionIssues.isEmpty());
    }
    void hysteriaV1UriIsExplicitlyRejectedNotConvertedToV2() {
        const auto parsed=NodeImporter::parse(QByteArray("hysteria://example.org:443?peer=camouflage.invalid&auth=fixture&upmbps=100&downmbps=50"));
        // The intent is that no node is produced and nothing is silently
        // rewritten into a Hysteria2 outbound; the diagnostic may name v2 in
        // order to state that it was NOT applied.
        QVERIFY(!parsed);QVERIFY(parsed.nodes.isEmpty());QVERIFY(parsed.error.contains("v1",Qt::CaseInsensitive));
    }
    void multiNodeSubscriptionIsolatesOneInvalidHysteria2Node() {
        const QByteArray good="hysteria2://auth@good.example.org:443?sni=good.invalid";
        const QByteArray bad="hysteria2://auth@bad.example.org:443?sni=a&sni=b";
        const auto parsed=NodeImporter::parse(good+"\n"+bad);
        QVERIFY(!parsed);QVERIFY(!parsed.error.isEmpty());
    }
};
QTEST_GUILESS_MAIN(ImportTests)
#include "ImportTests.moc"
