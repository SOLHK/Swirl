#include <QtTest>
#include <QClipboard>
#include <QFile>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QNetworkProxy>
#include <QSettings>
#include <QSignalSpy>
#include <QStandardPaths>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTemporaryDir>
#include "app/StoragePaths.h"
#include "engine/EngineController.h"
#include "engine/RustCoreEngine.h"

#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif

namespace {
// These are public synthetic format fixtures. They never identify a provider.
QByteArray document(int format) {
    if(format==18)return document(4).toBase64();
    const bool trojan=QList<int>{1,3,5,7,9,11,13,15}.contains(format);
    const QString protocol=trojan?"trojan":"ss",name="scope fixture",password="SYNTHETIC-SCOPE-SECRET";
    constexpr int port=1080;
    if(format<=3){
        QJsonObject node{{"name",name},{"type",protocol},{"server","127.0.0.1"},{"port",port},{"password",password}};
        node[trojan?"sni":"cipher"]=trojan?"localhost":"aes-128-gcm";
        return QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}},
            {"dns",QJsonObject{{"nameserver",QJsonArray{"192.0.2.53"}}}},
            {"rules",QJsonArray{"MATCH,DIRECT"}}}).toJson();
    }
    if(format==4||format==5||format==12||format==13)
        return QString("[Proxy]\n%1 = %2, 127.0.0.1, %3, %4password=%5%6\n[Rule]\nFINAL,DIRECT\n")
            .arg(name,protocol).arg(port).arg(trojan?"":"encrypt-method=aes-128-gcm, ",password,trojan?", sni=localhost":"").toUtf8();
    if(format==6||format==7)
        return QString("[server_local]\n%1=127.0.0.1:%2, %3password=%4, tag=%5%6\n[filter_local]\nfinal,direct\n")
            .arg(trojan?"trojan":"shadowsocks").arg(port).arg(trojan?"":"method=aes-128-gcm, ",password,name,trojan?", over-tls=true, tls-host=localhost":"").toUtf8();
    if(format==14||format==15)
        return QString("[Proxy]\n%1 = %2, 127.0.0.1, %3, %4\n").arg(name,trojan?"Trojan":"Shadowsocks").arg(port)
            .arg(trojan?"\""+password+"\", tls-name=localhost":"aes-128-gcm, \""+password+"\"").toUtf8();
    if(format==16)return QJsonDocument(QJsonObject{{"outbounds",QJsonArray{QJsonObject{
        {"tag",name},{"type","shadowsocks"},{"server","127.0.0.1"},{"server_port",port},
        {"method","aes-128-gcm"},{"password",password}}}}}).toJson();
    if(format==17)return QJsonDocument(QJsonObject{{"outbounds",QJsonArray{QJsonObject{
        {"tag",name},{"protocol","http"},{"settings",QJsonObject{{"servers",QJsonArray{
            QJsonObject{{"address","127.0.0.1"},{"port",port},{"users",QJsonArray{
                QJsonObject{{"user","synthetic-user"},{"pass",password}}}}}}}}}}}}}).toJson();
    const auto uri=trojan?QString("trojan://%1@127.0.0.1:%2?sni=localhost#scope").arg(password).arg(port).toUtf8():
        "ss://"+QString("aes-128-gcm:%1").arg(password).toUtf8().toBase64(QByteArray::Base64UrlEncoding|QByteArray::OmitTrailingEquals)+"@127.0.0.1:1080#scope";
    return format==8||format==9?uri.toBase64():uri;
}

class SubscriptionSource final : public QTcpServer {
public:
    QByteArray body;
    int requests=0;
    SubscriptionSource() {
        connect(this,&QTcpServer::newConnection,this,[this]{while(hasPendingConnections()){
            auto *socket=nextPendingConnection();
            connect(socket,&QTcpSocket::disconnected,socket,&QObject::deleteLater);
            connect(socket,&QTcpSocket::readyRead,this,[this,socket]{
                const auto bytes=socket->property("request").toByteArray()+socket->readAll();
                socket->setProperty("request",bytes);
                if(!bytes.contains("\r\n\r\n")||socket->property("done").toBool())return;
                socket->setProperty("done",true);++requests;
                socket->write("HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: "+QByteArray::number(body.size())+"\r\n\r\n"+body);
                socket->disconnectFromHost();
            });
        }});
    }
    QUrl url() const {return QUrl(QString("http://127.0.0.1:%1/scope").arg(serverPort()));}
};

QByteArray read(const QString &path) {QFile file(path);return file.open(QIODevice::ReadOnly)?file.readAll():QByteArray{};}

#ifdef Q_OS_WIN
QByteArray crypt(const QByteArray &input,bool decrypt) {
    DATA_BLOB in{DWORD(input.size()),reinterpret_cast<BYTE *>(const_cast<char *>(input.constData()))},out{};
    const QByteArray context("Swirl.NodeStore.v1");
    DATA_BLOB entropy{DWORD(context.size()),reinterpret_cast<BYTE *>(const_cast<char *>(context.constData()))};
    const bool ok=decrypt?CryptUnprotectData(&in,nullptr,&entropy,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&out):
        CryptProtectData(&in,L"Swirl nodes",&entropy,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&out);
    if(!ok)return {};
    QByteArray result(reinterpret_cast<char *>(out.pbData),out.cbData);
    SecureZeroMemory(out.pbData,out.cbData);LocalFree(out.pbData);return result;
}
#endif
}

class NodeImportScopeTests final : public QObject {
    Q_OBJECT
    QTemporaryDir settings;
private slots:
    void initTestCase() {
        QStandardPaths::setTestModeEnabled(true);SwirlPaths::initializeTestStorage();
        QCoreApplication::setOrganizationName("SwirlScopeTests");QCoreApplication::setApplicationName("NodeImportScope");
        QSettings::setDefaultFormat(QSettings::IniFormat);
        QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,settings.path());
        QNetworkProxy::setApplicationProxy(QNetworkProxy::NoProxy);
    }
    void init() {QSettings state;state.clear();state.setValue("Proxy/routingMode","global");state.sync();}

    void formatScopeReachesValidationWithoutDiscardingOptions_data() {
        QTest::addColumn<int>("format");
        const QStringList names{"Clash","Trojan Clash","Clash compatible","Trojan Clash compatible","Surge","Trojan Surge",
            "Quantumult X","Trojan Quantumult X","Shadowrocket","Trojan Shadowrocket","SIP002","Trojan URI",
            "Surfboard","Trojan Surfboard","Loon","Trojan Loon","sing-box","Xray V2Ray JSON","Base64 INI"};
        for(int i=0;i<names.size();++i)QTest::newRow(qPrintable(names[i]))<<i;
    }
    void formatScopeReachesValidationWithoutDiscardingOptions() {
        QFETCH(int,format);QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);
        const auto source=document(format);const auto expected=NodeImporter::parse(source);QVERIFY2(expected,qPrintable(expected.error));
        bool observed=false,scope=false;NodeImporter::Result actual;
        // A rejecting observer proves the service boundary, not persistence or traffic.
        service.setConfigurationApplier([&](const auto &result,const QString &id,bool nodesOnly,QString *error){
            observed=id.isEmpty();scope=nodesOnly;actual=result;*error="ScopeBoundaryObserved";return false;
        });
        QSignalSpy applied(&service,&NodeImportService::nodesApplied);
        service.importNodesOnlyText(QString::fromUtf8(source));QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),10000);
        if(service.hasPreview())service.confirmImport();
        QVERIFY(observed);QVERIFY(scope);QCOMPARE(applied.count(),0);QVERIFY(store.nodes().isEmpty());
        QCOMPARE(actual.configuration,expected.configuration);QCOMPARE(actual.executionConfiguration,expected.executionConfiguration);
        QCOMPARE(actual.nodes.size(),expected.nodes.size());
        for(int i=0;i<actual.nodes.size();++i){
            QCOMPARE(actual.nodes[i].parameters,expected.nodes[i].parameters);
            QCOMPARE(actual.nodes[i].originalConfiguration,expected.nodes[i].originalConfiguration);
            QCOMPARE(actual.nodes[i].conversionIssues,expected.nodes[i].conversionIssues);
            QCOMPARE(actual.nodes[i].sourceDocument,expected.nodes[i].sourceDocument);
        }
        service.shutdown();
    }

    void fileClipboardAndUrlUseNodesOnlyAndDoNotLeakScope() {
        QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);
        const auto bytes=document(0);const auto path=directory.filePath("scope.json");QFile file(path);
        QVERIFY(file.open(QIODevice::WriteOnly));QCOMPARE(file.write(bytes),bytes.size());file.close();
        QList<bool> scopes;
        service.setConfigurationApplier([&](const auto &,const auto &,bool nodesOnly,QString *error){
            scopes.append(nodesOnly);*error="ScopeBoundaryObserved";return false;
        });
        service.importNodesOnlyFile(QUrl::fromLocalFile(path));QTRY_COMPARE_WITH_TIMEOUT(scopes.size(),1,10000);
        QGuiApplication::clipboard()->setText(QString::fromUtf8(bytes));service.importNodesOnlyClipboard();
        QTRY_COMPARE_WITH_TIMEOUT(scopes.size(),2,10000);
        SubscriptionSource source;source.body=bytes;QVERIFY(source.listen(QHostAddress::LocalHost));
        service.importNodesOnlyUrl(source.url());QTRY_COMPARE_WITH_TIMEOUT(scopes.size(),3,10000);QCOMPARE(source.requests,1);
        service.importText(QString::fromUtf8(bytes));QTRY_COMPARE_WITH_TIMEOUT(scopes.size(),4,10000);
        QCOMPARE(scopes,QList<bool>({true,true,true,false}));service.shutdown();
    }

    void nodesOnlyRequiresPolicyValidator() {
        QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);
        service.importNodesOnlyText(QString::fromUtf8(document(0)));QTRY_VERIFY_WITH_TIMEOUT(!service.busy(),10000);
        QVERIFY(service.message().contains(QStringLiteral("无法校验当前网络配置")));
        QVERIFY(store.nodes().isEmpty());QVERIFY(!QFile::exists(store.filePath()));service.shutdown();
    }

    void iniHeadingsStillValidateAndJsonKeepsStrictBoundary() {
        for(const auto &invalid:{QByteArray("[Proxy\nn = http, 127.0.0.1, 1080"),
            QByteArray("[Proxy] trailing\nn = http, 127.0.0.1, 1080"),
            QByteArray("[Proxy]\nn = http, 127.0.0.1, 1080\n[Proxy]\nn = http, 127.0.0.1, 1081"),
            QByteArray("[{\"protocol\":\"http\",\"settings\":{}"),
            QByteArray("[{\"protocol\":\"http\",\"protocol\":\"socks\",\"settings\":{}}]")})
            QVERIFY(!NodeImporter::parse(invalid));
    }

    void jsonScopeSurvivesPreviewAndAsyncCommit() {
        QTemporaryDir directory;NodeStore store(directory.filePath("nodes.dpapi"));NodeImportService service(&store);
        int requests=0;bool scope=false;NodeImportService::ApplyCompletion complete;
        service.setAsyncConfigurationApplier([&](const auto &,const auto &,bool nodesOnly,auto completion,QString *){
            ++requests;scope=nodesOnly;complete=std::move(completion);return true;
        });
        service.importNodesOnlyText(QString::fromUtf8(document(17)));QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(),10000);
        QCOMPARE(requests,0);service.confirmImport();QVERIFY(scope);QCOMPARE(requests,1);QVERIFY(service.busy());
        service.cancelImport();QVERIFY(service.busy());complete(false,"ScopeWriteRejected");QVERIFY(!service.busy());
        service.importText(QString::fromUtf8(document(17)));QTRY_VERIFY_WITH_TIMEOUT(service.hasPreview(),10000);
        service.confirmImport();QVERIFY(!scope);QCOMPARE(requests,2);complete(false,"ScopeWriteRejected");service.shutdown();
    }

#ifdef Q_OS_WIN
    void formatSubscriptionPersistsWithoutPolicyMutation_data() {
        formatScopeReachesValidationWithoutDiscardingOptions_data();
    }
    void formatSubscriptionPersistsWithoutPolicyMutation() {
        QFETCH(int,format);QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");
        SubscriptionSource source;source.body=document(format);QVERIFY(source.listen(QHostAddress::LocalHost));
        EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);
        const QVariantMap policy{{"groups",QVariantList{QVariantMap{{"name","retained-policy"},{"type","select"},{"proxies",QStringList{"DIRECT"}}}}},
            {"rules",QStringList{"MATCH,retained-policy"}}};
        QVERIFY2(controller.replaceNetworkConfiguration(policy),qPrintable(controller.networkConfigurationError()));
        const auto retained=controller.networkConfigurationSnapshot();
        auto *imports=controller.imports();QVERIFY(imports->saveSubscription({},"format source",source.url(),360,false,"auto","nodes-only"));
        const auto sourceId=imports->providers().first().toMap().value("id").toString();
        imports->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),10000);
        QVERIFY2(controller.nodeCatalog().size()==1,qPrintable(imports->message()));QCOMPARE(source.requests,1);
        QCOMPARE(controller.networkConfigurationSnapshot(),retained);
        const auto id=controller.nodeCatalog().first().toMap().value("id").toString();QVERIFY(controller.chooseNode(id));
        NodeStore loaded(path);QCOMPARE(loaded.selectedId(),id);QCOMPARE(loaded.nodes().size(),1);
        QCOMPARE(loaded.nodes().first().sourceId,sourceId);QCOMPARE(loaded.subscriptions().first().importScope,QString("nodes-only"));
        const auto savedPolicy=loaded.networkConfiguration();
        imports->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),10000);
        QCOMPARE(source.requests,2);QCOMPARE(controller.selectedNodeId(),id);QCOMPARE(controller.networkConfigurationSnapshot(),retained);
        NodeStore refreshed(path);QCOMPARE(refreshed.networkConfiguration(),savedPolicy);QCOMPARE(refreshed.selectedId(),id);
        controller.shutdown();
    }

    void subscriptionScopePersistsAndLegacySnapshotDoesNotChangeBehavior() {
        QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");NodeStore store(path);
        QVERIFY(store.saveSubscription({},"scope",QUrl("https://example.invalid/SYNTHETIC-SCOPE-TOKEN"),360,false,"auto","nodes-only"));
        const auto id=store.subscriptions().first().id;NodeStore loaded(path);
        QCOMPARE(loaded.subscriptions().first().importScope,QString("nodes-only"));
        QCOMPARE(loaded.publicSubscriptions().first().toMap().value("importScope").toString(),QString("nodes-only"));
        QVERIFY(loaded.saveSubscription(id,"renamed",{},720,false));QCOMPARE(loaded.subscriptions().first().importScope,QString("nodes-only"));
        const auto retained=read(path);QVERIFY(!loaded.saveSubscription(id,"bad",{},720,false,"auto","unknown"));QCOMPARE(read(path),retained);
        QVERIFY(!retained.contains("SYNTHETIC-SCOPE-TOKEN"));
        auto snapshot=QJsonDocument::fromJson(crypt(retained.mid(11),true)).object();
        auto subscriptions=snapshot["subscriptions"].toArray();auto old=subscriptions.first().toObject();old.remove("importScope");subscriptions[0]=old;snapshot["subscriptions"]=subscriptions;
        const auto legacy=QByteArray("SWIRLNODE1\n")+crypt(QJsonDocument(snapshot).toJson(QJsonDocument::Compact),false);
        QFile file(path);QVERIFY(file.open(QIODevice::WriteOnly));QCOMPARE(file.write(legacy),legacy.size());file.close();
        NodeStore migrated(path);QVERIFY2(migrated.error().isEmpty(),qPrintable(migrated.error()));
        QCOMPARE(migrated.subscriptions().first().id,id);QCOMPARE(migrated.subscriptions().first().importScope,QString("full-profile"));
        QCOMPARE(read(path),legacy);
    }

    void nodesOnlySubscriptionPreservesPolicySelectionAndRejectsDanglingRefresh() {
        QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");SubscriptionSource source;QVERIFY(source.listen(QHostAddress::LocalHost));
        QJsonObject node{{"name","retained"},{"type","http"},{"server","127.0.0.1"},{"port",1080}};
        auto payload=[&]{return QJsonDocument(QJsonObject{{"proxies",QJsonArray{node}},
            {"dns",QJsonObject{{"nameserver",QJsonArray{"192.0.2.53"}}}},{"rules",QJsonArray{"MATCH,DIRECT"}},
            {"mode","direct"}}).toJson();};source.body=payload();
        EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);auto *imports=controller.imports();
        QVERIFY(imports->saveSubscription({},"nodes-only",source.url(),360,false,"auto","nodes-only"));
        const auto sourceId=imports->providers().first().toMap().value("id").toString();
        const auto initial=controller.networkConfigurationSnapshot();imports->refreshSubscription(sourceId);
        QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),10000);QCOMPARE(source.requests,1);QCOMPARE(controller.nodeCatalog().size(),1);
        QCOMPARE(controller.networkConfigurationSnapshot(),initial);QVERIFY(imports->message().contains(QStringLiteral("本次仅更新节点")));
        const auto id=controller.nodeCatalog().first().toMap().value("id").toString();QVERIFY(controller.chooseNode(id));
        const QVariantMap policy{{"groups",QVariantList{QVariantMap{{"name","local-policy"},{"type","select"},{"proxies",QStringList{id}}}}},
            {"rules",QStringList{"MATCH,local-policy"}}};
        QVERIFY2(controller.replaceNetworkConfiguration(policy),qPrintable(controller.networkConfigurationError()));
        const auto retained=controller.networkConfigurationSnapshot();
        imports->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),10000);
        QCOMPARE(controller.networkConfigurationSnapshot(),retained);QCOMPARE(controller.selectedNodeId(),id);
        const auto bytes=read(path);NodeStore reloaded(path);QCOMPARE(reloaded.selectedId(),id);QCOMPARE(reloaded.subscriptions().first().importScope,QString("nodes-only"));
        // A replacement with both a new identity and new source alias removes
        // the referenced node. Reject the entire refresh instead of clearing policy.
        node["name"]="replacement";node["port"]=1081;source.body=payload();
        imports->refreshSubscription(sourceId);QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),10000);
        QCOMPARE(source.requests,3);QCOMPARE(read(path),bytes);QCOMPARE(controller.selectedNodeId(),id);
        QCOMPARE(controller.networkConfigurationSnapshot(),retained);QCOMPARE(controller.nodeCatalog().first().toMap().value("id").toString(),id);
        QVERIFY(imports->providers().first().toMap().value("status").toString().contains(QStringLiteral("失败")));
        controller.shutdown();
    }

    void changingProfileToNodesOnlyRetainsPolicyAndProvenance() {
        QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");SubscriptionSource source;QVERIFY(source.listen(QHostAddress::LocalHost));
        QJsonObject payload{{"proxies",QJsonArray{QJsonObject{{"name","owned node"},{"type","http"},{"server","127.0.0.1"},{"port",1080}}}},
            {"proxy-groups",QJsonArray{QJsonObject{{"name","owned policy"},{"type","select"},{"proxies",QJsonArray{"owned node"}}}}},
            {"rules",QJsonArray{"MATCH,owned policy"}}};
        source.body=QJsonDocument(payload).toJson();EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);
        auto *imports=controller.imports();QVERIFY(imports->saveSubscription({},"profile",source.url(),360,false));
        const auto sourceId=imports->providers().first().toMap().value("id").toString();imports->refreshSubscription(sourceId);
        QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),10000);QVERIFY2(controller.nodeCatalog().size()==1,qPrintable(imports->message()));
        const auto retained=controller.networkConfigurationSnapshot();NodeStore original(path);
        const auto provenance=original.networkConfiguration().value("importedConfiguration").toObject();
        QCOMPARE(provenance.value("sourceId").toString(),sourceId);
        QVERIFY(imports->saveSubscription(sourceId,"profile",{},360,false,{},"nodes-only"));
        payload["dns"]=QJsonObject{{"nameserver",QJsonArray{"192.0.2.53"}}};payload["rules"]=QJsonArray{"MATCH,DIRECT"};
        source.body=QJsonDocument(payload).toJson();imports->refreshSubscription(sourceId);
        QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),10000);QCOMPARE(source.requests,2);QCOMPARE(controller.networkConfigurationSnapshot(),retained);
        NodeStore reloaded(path);auto updated=reloaded.networkConfiguration().value("importedConfiguration").toObject();
        QVERIFY(updated.take("policyRetainedAfterNodesOnlyRefresh").toBool());QCOMPARE(updated,provenance);
        EngineController reopened(std::make_unique<RustCoreEngine>(),nullptr,path,true);QCOMPARE(reopened.networkConfigurationSnapshot(),retained);
        reopened.shutdown();controller.shutdown();
    }

    void asyncJsonNodesOnlyRetainsPolicyAfterReload() {
        QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");
        EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);
        QVERIFY(controller.replaceNetworkConfiguration({{"rules",QStringList{"MATCH,DIRECT"}}}));
        const auto retained=controller.networkConfigurationSnapshot();
        auto *imports=controller.imports();imports->importNodesOnlyText(QString::fromUtf8(document(17)));
        QTRY_VERIFY_WITH_TIMEOUT(imports->hasPreview(),10000);imports->confirmImport();QTRY_VERIFY_WITH_TIMEOUT(!imports->busy(),10000);
        QCOMPARE(controller.nodeCatalog().size(),1);QCOMPARE(controller.networkConfigurationSnapshot(),retained);
        const auto id=controller.nodeCatalog().first().toMap().value("id").toString();QVERIFY(controller.chooseNode(id));
        NodeStore reloaded(path);QCOMPARE(reloaded.selectedId(),id);QCOMPARE(reloaded.nodes().size(),1);
        QCOMPARE(reloaded.nodes().first().sourceDocument,document(17));
        QCOMPARE(reloaded.networkConfiguration().value("rules"),QJsonValue::fromVariant(retained.value("rules")));
        controller.shutdown();
    }
#else
    void unsupportedEncryptedStorageStillFailsClosed() {
        QTemporaryDir directory;const auto path=directory.filePath("nodes.dpapi");
        EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path,true);
        const auto retained=controller.networkConfigurationSnapshot();
        controller.imports()->importNodesOnlyText(QString::fromUtf8(document(0)));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.imports()->busy(),10000);
        QVERIFY(controller.nodeCatalog().isEmpty());QCOMPARE(controller.networkConfigurationSnapshot(),retained);
        QVERIFY(!QFile::exists(path));QVERIFY(controller.imports()->message().contains("DPAPI"));controller.shutdown();
    }
#endif
};

QTEST_MAIN(NodeImportScopeTests)
#include "NodeImportScopeTests.moc"
