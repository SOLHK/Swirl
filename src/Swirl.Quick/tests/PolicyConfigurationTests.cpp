#include "engine/EngineController.h"
#include "engine/RustCoreEngine.h"
#include "PolicySystemProxyBackend.h"
#include "ControlledNetwork.h"
#include <QCryptographicHash>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSettings>
#include <QScopeGuard>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTcpServer>
#include <QTimer>
#include <QTest>
#include <QUuid>
#include <functional>
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif

// This peer tests the Qt transaction coordinator and actual encrypted writes.
// Independent Rust/transport tests prove routing and admission on real sockets.
class ConfigurationPeer final : public ProxyEngine {
public:
    using ProxyEngine::ProxyEngine;
    Status current;
    QStringList operations;
    QJsonObject prepared,base;
    quint64 generation=1;
    bool rejectPrepare=false,rejectFinishOnce=false,rolledBack=false,gate=false;
    bool probeSucceeds=true;
    int activations=0,starts=0,stops=0;
    std::function<void()> beforeActivate,beforeRollback,beforeFinish;
    static QString digest(const QJsonObject &candidate) {
        return QString::fromLatin1(QCryptographicHash::hash(QJsonDocument(candidate).toJson(QJsonDocument::Compact),QCryptographicHash::Sha256).toHex());
    }
    void start(const EngineStartOptions &options) override {
        ++starts;current.processId=QCoreApplication::applicationPid();
        current.state=State::Running;current.processAlive=true;current.apiHealthy=true;current.proxyPort=options.proxyPort;
        current.directSession=options.policyDocument.value("mode")==QJsonValue("direct");current.mode=options.policyDocument.value("mode").toString();
        current.configurationReceipt={{"engine_epoch","1"},{"generation",QString::number(generation)},
            {"applied_revision",options.configurationRevision},{"plan_digest",options.configurationDigest},
            {"applied_mode",current.mode},{"store_id",options.configurationStoreId},{"request_id",options.configurationRequestId}};
        emit statusChanged();
    }
    void stop() override {++stops;current.state=State::Stopped;current.processAlive=false;current.apiHealthy=false;current.configurationReceipt={};gate=false;emit statusChanged();}
    void refresh() override {}
    void selectNode(const QString &) override {QFAIL("V2 coordinator used legacy selection");}
    void probeNode(const QUrl &) override {}
    void probeNodeTagged(const QUrl &,quint64 tag) override {
        // Coordinator fixture only: real TLS/exit behavior is tested by the
        // Rust and socket integration suites, never inferred from this peer.
        current.probeRequestTag=tag;current.nodeBusy=true;current.requestState=RequestState::InProgress;emit statusChanged();
        QTimer::singleShot(0,this,[this,tag]{
            current.probeRequestTag=tag;current.nodeBusy=false;
            current.requestState=probeSucceeds?RequestState::Succeeded:RequestState::Failed;
            current.nodeHealth=probeSucceeds?NodeHealth::Available:NodeHealth::Unknown;
            current.nodeMessage=probeSucceeds?QString():QString("Controlled origin TLS failure");emit statusChanged();
        });
    }
    Status status() const override {return current;}
    QString configurationSummary() const override {return "controlled configuration peer";}
    void configurationCommand(const QJsonObject &request) override {
        const auto op=request.value("op").toString(),id=request.value("request_id").toString();operations.append(op);
        QJsonObject response{{"ok",true},{"request_id",id}};
        if(op=="validate_configuration_v2")response.insert("plan_digest",digest(request.value("candidate").toObject()));
        else if(op=="prepare_configuration_v2"){
            if(rejectPrepare){emit configurationCommandFinished(id,{{"ok",false},{"request_id",id},{"code","InjectedPrepareFailure"},{"phase","prepare"}});return;}
            prepared=request;base=current.configurationReceipt;rolledBack=false;
            response.insert("prepared_token","controlled-token");response.insert("plan_digest",digest(request.value("candidate").toObject()));
            response.insert("candidate_revision",request.value("candidate_revision"));response.insert("expected_generation",QString::number(generation));
            response.insert("generation",QString::number(generation));response.insert("engine_epoch","1");response.insert("applied_revision",base.value("applied_revision"));
        }else if(op=="activate_configuration_v2"){
            if(beforeActivate)beforeActivate();gate=true;++activations;++generation;
            current.configurationReceipt={{"engine_epoch","1"},{"generation",QString::number(generation)},
                {"applied_revision",prepared.value("candidate_revision")},{"plan_digest",digest(prepared.value("candidate").toObject())},
                {"applied_mode",prepared.value("candidate").toObject().value("policy").toObject().value("mode")},
                {"store_id",prepared.value("store_id")},{"request_id",id}};
            current.mode=current.configurationReceipt.value("applied_mode").toString();current.directSession=current.mode=="direct";
            response=current.configurationReceipt;response.insert("ok",true);
        }else if(op=="rollback_configuration_v2"){
            if(beforeRollback)beforeRollback();rolledBack=true;++generation;current.configurationReceipt=base;
            current.configurationReceipt.insert("generation",QString::number(generation));
            current.mode=current.configurationReceipt.value("applied_mode").toString();current.directSession=current.mode=="direct";
            response=current.configurationReceipt;response.insert("request_id",id);response.insert("ok",true);
        }else if(op=="finish_configuration_v2"){
            if(beforeFinish)beforeFinish();
            const auto receipt=request.value("durable_receipt").toObject();
            if(receipt.value("saved_revision").toString()!=current.configurationReceipt.value("applied_revision").toString())QFAIL("Mismatching durable receipt reached finish");
            gate=false;response=current.configurationReceipt;response.insert("request_id",id);response.insert("ok",true);
            if(rejectFinishOnce){rejectFinishOnce=false;emit configurationCommandFinished(id,{{"ok",false},{"request_id",id},{"code","InjectedLostFinishAck"},{"phase","finish"}});return;}
        }else if(op=="configuration_status_v2"){
            response=current.configurationReceipt;response.insert("request_id",id);response.insert("ok",true);
        }else {QFAIL("Unexpected configuration command");}
        // Deliberately publish the reply before the telemetry notification.
        emit configurationCommandFinished(id,response);emit statusChanged();
    }
};

class FailingPolicyProxyBackend final : public SystemProxySession::Backend {
public:
    PolicySystemProxyBackend memory;
    State observed=memory.current();
    bool rejectEnable=false,rejectRestore=false;
    int enableAttempts=0,restoreAttempts=0;
    State current() const {return observed;}
    State refresh() override {return observed;}
    State enable(int port,qint64 pid) override {
        ++enableAttempts;
        if(rejectEnable){observed.error=QStringLiteral("Controlled proxy acquisition failure");return observed;}
        observed=memory.enable(port,pid);return observed;
    }
    State disable() override {
        ++restoreAttempts;
        if(rejectRestore){observed.error=QStringLiteral("Controlled proxy restoration failure");return observed;}
        observed=memory.disable();return observed;
    }
};
class WaitingPolicyProxyBackend final : public SystemProxySession::Backend {
public:
    PolicySystemProxyBackend memory;
    bool ready=false,releaseReady=true,releaseFails=false;
    int preparations=0;
    State refresh() override {return memory.refresh();}
    State enable(int port,qint64 pid) override {return memory.enable(port,pid);}
    State disable() override {return memory.disable();}
    Preparation prepareEnable(int,qint64,QString *) override {++preparations;return ready?Preparation::Ready:Preparation::Pending;}
    Preparation prepareDisable(QString *error) override {
        if(releaseFails){if(error)*error=QStringLiteral("Controlled proxy release preparation failure");return Preparation::Failed;}
        return releaseReady?Preparation::Ready:Preparation::Pending;
    }
};

class PolicyConfigurationTests final : public QObject {
    Q_OBJECT
    QTemporaryDir settings;
    static QJsonObject document() {
        return {{"schema",2},{"mode","direct"},{"default_policy",QJsonObject{{"id","policy:default"},{"target",QJsonObject{{"kind","unconfigured"}}}}},
            {"service_policies",QJsonArray{}},{"groups",QJsonArray{}},{"explicit_direct_rules",QJsonArray{}},{"custom_rules",QJsonArray{}},{"missing_targets",QJsonArray{}}};
    }
    static QJsonObject changedDocument(){auto result=document();result.insert("service_policies",QJsonArray{QJsonObject{
        {"id","30000000-0000-4000-8000-000000000001"},{"name","Controlled service"},{"enabled",true},{"priority",10},
        {"domains",QJsonArray{QJsonObject{{"type","domain_suffix"},{"value","service.example.invalid"}}}},{"target",QJsonObject{{"kind","direct"}}}}});return result;}
    static QByteArray bytes(const QString &path){QFile file(path);if(!file.open(QIODevice::ReadOnly))return {};return file.readAll();}
    struct SourcePools {QString a,b,nodeA,otherA,nodeB,independent;};
    static SourcePools seedSourcePools(const QString &path) {
        NodeStore store(path);SourcePools pool;
        if(!store.saveSubscription({},"Source A",QUrl("https://a.fixture.invalid/sub"),360,false)||
           !store.saveSubscription({},"Source B",QUrl("https://b.fixture.invalid/sub"),360,false))return {};
        pool.a=store.subscriptions().first().id;pool.b=store.subscriptions().last().id;
        const auto node=[](const QString &name,int port){ProxyNode result;result.id=QUuid::createUuid().toString(QUuid::WithoutBraces);
            result.name=name;result.protocol="socks5";result.host="127.0.0.1";result.port=quint16(port);return result;};
        const auto a=node("A first",9),otherA=node("A second",10),b=node("B first",11);auto independent=node("URL import",12);independent.importSource="url";
        if(!store.importNodes({a,otherA},pool.a)||!store.importNodes({b},pool.b)||!store.importNodes({independent})||!store.select(a.id))return {};
        pool.nodeA=a.id;pool.otherA=otherA.id;pool.nodeB=b.id;pool.independent=independent.id;return pool;
    }
    static QJsonObject sourcePolicy(const SourcePools &pool) {
        auto policy=document();policy.insert("mode","global");
        auto fallback=policy.value("default_policy").toObject();fallback.insert("target",QJsonObject{{"kind","node"},{"id",pool.nodeA}});policy.insert("default_policy",fallback);
        const QJsonObject first{{"kind","node"},{"id",pool.nodeA}};
        policy.insert("groups",QJsonArray{QJsonObject{{"id","20000000-0000-4000-8000-000000000007"},{"name","Mixed sources"},{"strategy","manual"},
            {"members",QJsonArray{first,QJsonObject{{"kind","node"},{"id",pool.otherA}},QJsonObject{{"kind","node"},{"id",pool.nodeB}}}},{"selected",first}}});
        return policy;
    }
    static QString seedReviewSource(const QString &path,const QJsonObject &extra={},bool identity=true) {
        NodeStore store(path);
        if(!store.saveSubscription({},"Review source",QUrl("https://source.invalid/private-fixture-token"),360,false))return {};
        const auto id=store.subscriptions().first().id;
        QJsonObject profile{{"proxies",QJsonArray{QJsonObject{{"name","Review node"},{"type","socks5"},{"server","127.0.0.1"},{"port",9}}}},
            {"proxy-groups",QJsonArray{QJsonObject{{"name","Review group"},{"type","select"},{"proxies",QJsonArray{"Review node"}}}}},
            {"rules",QJsonArray{"DOMAIN-SUFFIX,review.invalid,Review group","MATCH,Review group"}}};
        for(auto it=extra.begin();it!=extra.end();++it)profile.insert(it.key(),it.value());
        const auto parsed=NodeImporter::parse(QJsonDocument(profile).toJson(QJsonDocument::Compact));
        if(!parsed||!store.importNodes(parsed.nodes,id))return {};
        const QJsonObject archive{{"mode","nodes-with-warning"},{"format",parsed.format},{"configurationFormat",parsed.configurationFormat},
            {"sourceDigest",identity?parsed.sourceDigest:QString()},{"preservedConfiguration",parsed.configuration}};
        if(!store.saveNetworkConfiguration({{"schema",1},{"groups",QJsonArray{}},{"rules",QJsonArray{}},
            {"subscriptionImportResults",QJsonObject{{id,archive}}}}))return {};
        return id;
    }
    static QJsonObject envelope(const QString &path){
#ifdef Q_OS_WIN
        const auto ciphertext=bytes(path);if(!ciphertext.startsWith("SWIRLNODE2\n"))return {};
        auto encrypted=ciphertext.mid(11);QByteArray entropy("Swirl.NodeStore.v1");
        DATA_BLOB source{DWORD(encrypted.size()),reinterpret_cast<BYTE *>(encrypted.data())},context{DWORD(entropy.size()),reinterpret_cast<BYTE *>(entropy.data())},result{};
        if(!CryptUnprotectData(&source,nullptr,&context,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&result))return {};
        const auto json=QJsonDocument::fromJson(QByteArray(reinterpret_cast<char *>(result.pbData),result.cbData)).object();
        SecureZeroMemory(result.pbData,result.cbData);LocalFree(result.pbData);return json;
#else
        Q_UNUSED(path);return {};
#endif
    }
private slots:
    void initTestCase(){QVERIFY(settings.isValid());QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,settings.path());QCoreApplication::setOrganizationName("SwirlControlledTests");QCoreApplication::setApplicationName("PolicyConfigurationTests");}
    void offlinePolicyUsesEncryptedV2CommitAndDoesNotStartAProxy(){
        QTemporaryDir dir;auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();EngineController controller(std::move(peer),nullptr,dir.filePath("nodes.dpapi"));
        QSignalSpy finished(&controller,&EngineController::policyApplyFinished);
        QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QVERIFY(controller.policyBusy());QCOMPARE(finished.size(),0);
        QTRY_COMPARE_WITH_TIMEOUT(finished.size(),1,5000);QVERIFY(finished.first().at(1).toBool());QVERIFY(!controller.policyBusy());
        QCOMPARE(controller.savedRevision(),QString("1"));QVERIFY(controller.appliedRevision().isEmpty());QVERIFY(!engine->current.processAlive);
        const auto stored=envelope(dir.filePath("nodes.dpapi"));QCOMPARE(stored.value("schema").toInt(),2);QVERIFY(!stored.contains("pending"));
        QCOMPARE(stored.value("committed").toObject().value("snapshot").toObject().value("networkConfiguration").toObject().value("policyDocumentV2").toObject(),document());
        QCOMPARE(engine->operations,QStringList{"validate_configuration_v2"});QVERIFY(!bytes(dir.filePath("nodes.dpapi")).contains("default_policy"));
    }
#ifndef SWIRL_PROXY_STOP_NEGATIVE_CONTROL
    // The pinned controller predates these APIs; its six stop cases stay intact.
    void subscriptionChoiceScopesCandidatesRuntimeAndColdReloadWithoutDeletingIndependentImports(){
        QTemporaryDir dir;const auto path=dir.filePath("sources.dpapi");const auto pool=seedSourcePools(path);QVERIFY(!pool.a.isEmpty());
        {
            EngineController controller(std::make_unique<ConfigurationPeer>(),nullptr,path);
            QVERIFY(!controller.subscriptionScopeEnabled());QCOMPARE(controller.nodes().size(),4);
            QVERIFY(controller.policyMigrationRequired());QVERIFY(controller.confirmPolicyMigration());
            QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));
            QVERIFY(controller.applyPolicyDocument(sourcePolicy(pool).toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
            QVERIFY(controller.selectSubscription(pool.a));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY(controller.policyError().isEmpty());
            QVERIFY(controller.subscriptionScopeEnabled());QCOMPARE(controller.activeSubscriptionId(),pool.a);QCOMPARE(controller.nodes().size(),2);QCOMPARE(controller.nodeCatalog().size(),2);
            for(const auto &row:controller.nodeCatalog())QCOMPARE(row.toMap().value("sourceId").toString(),pool.a);
            for(const auto &row:controller.policyTargetOptions())if(row.toMap().value("kind")==QString("node")){
                const auto id=row.toMap().value("id").toString();QVERIFY(id==pool.nodeA||id==pool.otherA);QCOMPARE(row.toMap().value("sourceName").toString(),QString("Source A"));
            }
            QVERIFY(!controller.chooseNode(pool.nodeB));QVERIFY(controller.selectSubscription(pool.b));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));
            QCOMPARE(controller.nodes().size(),1);QCOMPARE(controller.nodes().first().toMap().value("id").toString(),pool.nodeB);QCOMPARE(controller.m_store.nodes().size(),4);
            QCOMPARE(controller.defaultPolicy().value("target").toMap().value("kind").toString(),QString("unconfigured"));QCOMPARE(controller.routingMode(),QString("global"));
            const auto group=controller.strategyGroups().first().toMap();QCOMPARE(group.value("members").toList().size(),1);QVERIFY(!group.contains("selected"));
            QJsonObject runtime;QVERIFY(RustCoreEngine::configurationV2(controller.m_options,QJsonObject::fromVariantMap(controller.policyDocument()),&runtime).isEmpty());
            for(const auto &entry:runtime.value("nodes").toArray())QCOMPARE(entry.toObject().value("id").toString(),pool.nodeB);
            QVERIFY(controller.chooseNode(pool.nodeB));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);const auto savedB=controller.policyDocument();
            QVERIFY(controller.selectSubscription(pool.a));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY(controller.policyError().isEmpty());
            QCOMPARE(controller.defaultPolicy().value("target").toMap().value("id").toString(),pool.nodeA);QCOMPARE(controller.strategyGroups().first().toMap().value("members").toList().size(),2);
            QVERIFY(controller.selectSubscription(pool.b));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY(controller.policyError().isEmpty());QCOMPARE(controller.policyDocument(),savedB);
        }
        EngineController reopened(std::make_unique<ConfigurationPeer>(),nullptr,path);QVERIFY(reopened.subscriptionScopeEnabled());QCOMPARE(reopened.activeSubscriptionId(),pool.b);
        QCOMPARE(reopened.nodes().size(),1);QCOMPARE(reopened.m_store.nodes().size(),4);QVERIFY(!reopened.processAlive());
        QVERIFY(reopened.imports()->removeSubscription(pool.b));QTRY_VERIFY_WITH_TIMEOUT(!reopened.imports()->busy(),5000);QVERIFY(reopened.policyError().isEmpty());
        QCOMPARE(reopened.activeSubscriptionId(),pool.b);QVERIFY(reopened.nodes().isEmpty());QCOMPARE(reopened.m_store.nodes().size(),3);
        QVERIFY(reopened.selectSubscription({}));QTRY_VERIFY_WITH_TIMEOUT(!reopened.policyBusy(),5000);QVERIFY(reopened.policyError().isEmpty());
        QVERIFY(reopened.subscriptionScopeEnabled());QVERIFY(reopened.activeSubscriptionId().isEmpty());QCOMPARE(reopened.nodes().size(),1);
        QCOMPARE(reopened.nodes().first().toMap().value("id").toString(),pool.independent);QCOMPARE(reopened.nodes().first().toMap().value("sourceName").toString(),QStringLiteral("独立链接导入"));
        QCOMPARE(reopened.defaultPolicy().value("target").toMap().value("kind").toString(),QString("unconfigured"));QCOMPARE(reopened.routingMode(),QString("global"));
    }
    void returningToASubscriptionRestoresItsChosenGroupAndServiceInsteadOfDeletingThem(){
        QTemporaryDir dir;const auto path=dir.filePath("source-policy-snapshots.dpapi");const auto pool=seedSourcePools(path);QVERIFY(!pool.a.isEmpty());
        EngineController controller(std::make_unique<ConfigurationPeer>(),nullptr,path);
        QVERIFY(controller.policyMigrationRequired());QVERIFY(controller.confirmPolicyMigration());
        QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));
        QVERIFY(controller.applyPolicyDocument(sourcePolicy(pool).toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QVERIFY(controller.selectSubscription(pool.a));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        auto policyA=controller.policyDocument();auto fallback=policyA.value("default_policy").toMap();
        fallback.insert("target",QVariantMap{{"kind","group"},{"id","20000000-0000-4000-8000-000000000007"}});policyA.insert("default_policy",fallback);
        policyA.insert("service_policies",changedDocument().value("service_policies").toArray().toVariantList());
        QVERIFY(controller.applyPolicyDocument(policyA));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY(controller.policyError().isEmpty());
        QVERIFY(controller.selectSubscription(pool.b));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY(controller.policyError().isEmpty());
        QVERIFY(controller.chooseNode(pool.nodeB));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);const auto policyB=controller.policyDocument();
        QVERIFY(controller.selectSubscription(pool.a));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));QCOMPARE(controller.policyDocument(),policyA);
        QVERIFY(controller.selectSubscription(pool.b));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY(controller.policyError().isEmpty());QCOMPARE(controller.policyDocument(),policyB);
        QCOMPARE(controller.m_store.nodes().size(),4);QCOMPARE(controller.imports()->providers().size(),2);
    }
    void runningSubscriptionSwitchRevokesOnlyTheOldPoolAndKeepsFailedChoiceAtomic(){
        QTemporaryDir dir;const auto path=dir.filePath("online-sources.dpapi");const auto pool=seedSourcePools(path);QVERIFY(!pool.a.isEmpty());
        auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();EngineController controller(std::move(peer),nullptr,path);
        QVERIFY(controller.policyMigrationRequired());QVERIFY(controller.confirmPolicyMigration());
        QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));
        QVERIFY(controller.applyPolicyDocument(sourcePolicy(pool).toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QVERIFY(controller.selectSubscription(pool.a));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY(controller.policyError().isEmpty());
        controller.connectConfiguredPolicy();QVERIFY(controller.processAlive());const auto oldPolicy=controller.policyDocument();const auto oldBytes=bytes(path);
        engine->rejectPrepare=true;QVERIFY(controller.selectSubscription(pool.b));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QCOMPARE(controller.activeSubscriptionId(),pool.a);QCOMPARE(controller.policyDocument(),oldPolicy);QCOMPARE(bytes(path),oldBytes);QVERIFY(!controller.policyError().isEmpty());
        engine->rejectPrepare=false;engine->rejectFinishOnce=true;QVERIFY(controller.selectSubscription(pool.b));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY(controller.policyError().isEmpty());
        const auto revoked=engine->prepared.value("revoked_node_ids").toArray();QCOMPARE(revoked.size(),2);QVERIFY(revoked.contains(pool.nodeA));QVERIFY(revoked.contains(pool.otherA));
        QVERIFY(!revoked.contains(pool.nodeB));QVERIFY(!revoked.contains(pool.independent));QCOMPARE(controller.activeSubscriptionId(),pool.b);QVERIFY(!engine->gate);
        QVERIFY(engine->operations.contains("configuration_status_v2"));QVERIFY(!controller.policyReceipt().value("applied_revision").toString().isEmpty());
        const auto runtime=engine->prepared.value("candidate").toObject();for(const auto &entry:runtime.value("nodes").toArray())QCOMPARE(entry.toObject().value("id").toString(),pool.nodeB);
        const auto saved=envelope(path).value("committed").toObject().value("snapshot").toObject();
        QCOMPARE(saved.value("networkConfiguration").toObject().value("activeSubscriptionId").toString(),pool.b);QCOMPARE(saved.value("nodes").toArray().size(),4);
    }
    void tunPreparesSecureDefaultsPreservesExplicitDnsAndNeverEnablesGateway(){
        QTemporaryDir dir;const auto path=dir.filePath("tun-configuration.dpapi");const auto pool=seedSourcePools(path);QVERIFY(!pool.a.isEmpty());
        NodeStore store(path);EngineStartOptions options;options.nodes=store.nodes();options.proxyPort=1080;options.tunEnabled=true;
        const auto policy=sourcePolicy(pool);QJsonObject runtime;
#ifdef Q_OS_WIN
        QVERIFY(RustCoreEngine::configurationV2(options,policy,&runtime).isEmpty());
        const auto defaults=runtime.value("dns").toObject().value("tls_servers").toArray();QCOMPARE(defaults.size(),2);
        QCOMPARE(defaults.first().toObject().value("tls").toObject().value("server_name").toString(),QString("dns.alidns.com"));
        QVERIFY(runtime.value("dns").toObject().value("servers").toArray().isEmpty());QVERIFY(options.dnsConfig.isEmpty());
        options.dnsConfig={{"mode",2},{"servers","1.1.1.1"}};
        QVERIFY(!RustCoreEngine::configurationV2(options,policy,&runtime).isEmpty());
        options.dnsConfig={{"mode",0},{"encrypted","https://1.1.1.1/dns-query"}};
        QVERIFY(RustCoreEngine::configurationV2(options,policy,&runtime).isEmpty());
        QVERIFY(runtime.value("dns").toObject().value("servers").toArray().isEmpty());
        QCOMPARE(runtime.value("dns").toObject().value("tls_servers").toArray().size(),1);
        options.gatewayForwarding=true;
        QVERIFY(!RustCoreEngine::configurationV2(options,policy,&runtime).isEmpty());
#else
        QVERIFY(!RustCoreEngine::configurationV2(options,policy,&runtime).isEmpty());
#endif
    }
    void tunPreferenceCannotSwitchControllersWhileTheCurrentCoreIsAlive(){
        QTemporaryDir dir;const auto path=dir.filePath("tun-live-choice.dpapi");const auto pool=seedSourcePools(path);QVERIFY(!pool.a.isEmpty());
        auto peer=std::make_unique<ConfigurationPeer>();EngineController controller(std::move(peer),nullptr,path);
        QVERIFY(controller.policyMigrationRequired());QVERIFY(controller.confirmPolicyMigration());
        QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));
        QVERIFY(controller.applyPolicyDocument(sourcePolicy(pool).toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        controller.connectConfiguredPolicy();QVERIFY(controller.processAlive());
        controller.m_options.tunEnabled=true;const auto before=bytes(path);
        QVERIFY(!controller.setTunEnabled(false));QVERIFY(controller.tunRequested());QVERIFY(controller.processAlive());
        QCOMPARE(bytes(path),before);QVERIFY(!controller.routingError().isEmpty());
    }
    void probeEgressUsesActualCaptureOwnershipInsteadOfTheSavedPreference(){
        QTemporaryDir dir;auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("probe-egress-state.dpapi"));
        controller.m_options.tunEnabled=true;
        QVERIFY(!controller.nodeProbeOptions().internalProbePhysicalEgress);
        engine->current.state=ProxyEngine::State::Running;engine->current.processAlive=true;
        QVERIFY(!controller.nodeProbeOptions().internalProbePhysicalEgress);
        controller.m_options.tunEnabled=false;engine->current.tunCapturePossible=true;
        QVERIFY(controller.nodeProbeOptions().internalProbePhysicalEgress);
        engine->current.state=ProxyEngine::State::Degraded;engine->current.tunEnabled=false;
        QVERIFY(controller.nodeProbeOptions().internalProbePhysicalEgress);
        engine->current.tunRecoveryRequired=true;
        QVERIFY(!controller.nodeProbeOptions().internalProbePhysicalEgress);
        QVERIFY(!controller.canStart());QVERIFY(!controller.nodeProbeReady());
        QVERIFY(controller.nodeError().contains(QStringLiteral("TUN")));
        controller.testAllNodes(QUrl("http://127.0.0.1:9/probe"));QVERIFY(!controller.m_tests.busy());
        engine->current.tunRecoveryRequired=false;
        engine->current.tunCapturePossible=false;engine->current.processAlive=false;engine->current.state=ProxyEngine::State::Stopped;
        QVERIFY(!controller.nodeProbeOptions().internalProbePhysicalEgress);
    }
#ifdef Q_OS_WIN
    void tunStartWaitsForOldProbeSockets_data(){
        QTest::addColumn<int>("action");
        QTest::newRow("continue-original-connection-intent")<<0;
        QTest::newRow("stop-withdraws-intent")<<1;
        QTest::newRow("queued-stop-and-new-start")<<2;
    }
    void tunStartWaitsForOldProbeSockets(){
        QFETCH(int,action);
        QTemporaryDir dir;auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("probe-start-barrier.dpapi"));
        QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));
        auto candidate=controller.m_options;candidate.tunEnabled=true;candidate.dnsConfig={{"mode",0},{"encrypted","https://1.1.1.1/dns-query"}};
        QVERIFY(controller.applyPolicyConfiguration(document(),candidate));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));
        QTcpServer stalled;QVERIFY(stalled.listen(QHostAddress::LocalHost,0));
        ProxyNode node;node.id=QUuid::createUuid().toString(QUuid::WithoutBraces);node.name="Controlled pending probe";
        node.protocol="socks5";node.host="127.0.0.1";node.port=stalled.serverPort();
        EngineStartOptions options;options.nodes={node};
        controller.m_tests.start(options,{node.id},QUrl("http://127.0.0.1:9/probe"));
        QTRY_VERIFY_WITH_TIMEOUT(stalled.hasPendingConnections(),10000);
        auto *socket=stalled.nextPendingConnection();QVERIFY(socket);socket->setParent(&stalled);
        QTRY_VERIFY_WITH_TIMEOUT(socket->bytesAvailable()>0,2000);
        QVERIFY(controller.m_tests.busy());
        bool replacedIntent=false;
        // The observer must disconnect before controller/member destruction
        // can emit changed(), including on an assertion's early return.
        QObject probeObserver;
        connect(&controller.m_tests,&NodeTestService::changed,&probeObserver,[&]{
            if(action!=2||replacedIntent||controller.m_tests.busy()||!controller.m_startAfterProbes)return;
            replacedIntent=true;controller.stop();controller.connectConfiguredPolicy();
        });
        controller.connectConfiguredPolicy();
        QVERIFY(controller.m_startAfterProbes);QCOMPARE(engine->starts,0);
        if(action==1)controller.stop();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.m_tests.busy(),10000);
        QTRY_VERIFY_WITH_TIMEOUT(socket->state()==QAbstractSocket::UnconnectedState,3000);
        if(action==1){QTest::qWait(50);QCOMPARE(engine->starts,0);QVERIFY(!controller.processAlive());}
        else {QTRY_COMPARE_WITH_TIMEOUT(engine->starts,1,5000);QTest::qWait(50);QCOMPARE(engine->starts,1);QVERIFY(controller.processAlive());}
        QCOMPARE(replacedIntent,action==2);
        QVERIFY(!controller.m_startAfterProbes);QVERIFY(!controller.m_tests.busy());
        QVERIFY(controller.m_tests.message().contains(QStringLiteral("已取消")));
    }
#endif
#endif
    void acceptedMutationRejectsAConcurrentWriterWithoutReplacingItsRequest(){
        QTemporaryDir dir;EngineController controller(std::make_unique<ConfigurationPeer>(),nullptr,dir.filePath("nodes.dpapi"));
        QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));const auto request=controller.policyRequestId();
        QVERIFY(!controller.applyPolicyDocument(changedDocument().toVariantMap()));QCOMPARE(controller.policyRequestId(),request);
        QVERIFY(!controller.saveNode({{"name","not-saved"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",9}}));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QCOMPARE(controller.policyDocument().value("mode").toString(),QString("direct"));QVERIFY(controller.nodes().isEmpty());
    }
    void changingTheOfflineListenerCommitsItsDigestAndSurvivesReload(){
        QTemporaryDir dir;const auto path=dir.filePath("ports.dpapi");QTcpServer first,second;
        QVERIFY(first.listen(QHostAddress::LocalHost));QVERIFY(second.listen(QHostAddress::LocalHost));
        const auto original=first.serverPort(),updated=second.serverPort();
        {
            EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);
            controller.setProxyPort(original);QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));
            QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY(controller.policyError().isEmpty());
            const auto revision=controller.savedRevision();controller.setProxyPort(updated);
            QVERIFY(controller.policyBusy());QCOMPARE(controller.proxyPort(),int(original));
            QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));
            QCOMPARE(controller.proxyPort(),int(updated));QVERIFY(controller.savedRevision().toULongLong()>revision.toULongLong());
            QCOMPARE(envelope(path).value("committed").toObject().value("snapshot").toObject().value("networkConfiguration").toObject().value("proxyPort").toInt(),int(updated));
            first.close();second.close();controller.connectConfiguredPolicy();QTRY_VERIFY_WITH_TIMEOUT(controller.apiHealthy(),5000);
            QVERIFY(!controller.policyReceipt().value("engine_epoch").toString().isEmpty());
            QCOMPARE(controller.policyReceipt().value("applied_revision").toString(),controller.savedRevision());
            QVERIFY(!controller.policyReceipt().value("request_id").toString().isEmpty());
            QVERIFY(controller.applyPolicyDocument(changedDocument().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
            QCOMPARE(controller.policyReceipt().value("request_id").toString(),controller.policyRequestId());
            controller.m_engine->refresh();QCOMPARE(controller.policyReceipt().value("request_id").toString(),controller.policyRequestId());
            QCOMPARE(controller.activeProxyPort(),int(updated));controller.stop();QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive(),5000);
            QVERIFY(!controller.policyReceipt().contains("engine_epoch"));
        }
        EngineController reopened(std::make_unique<RustCoreEngine>(),nullptr,path);QCOMPARE(reopened.proxyPort(),int(updated));
        reopened.connectConfiguredPolicy();QTRY_VERIFY_WITH_TIMEOUT(reopened.apiHealthy(),5000);QCOMPARE(reopened.activeProxyPort(),int(updated));
        reopened.stop();QTRY_VERIFY_WITH_TIMEOUT(!reopened.processAlive(),5000);
    }
    void callerCannotForgeARevocationRecordForAnUnknownNode(){
        QTemporaryDir dir;auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();EngineController controller(std::move(peer),nullptr,dir.filePath("nodes.dpapi"));
        auto forged=document();forged.insert("missing_targets",QJsonArray{QJsonObject{{"kind","node"},{"id","10000000-0000-4000-8000-000000000099"},{"safe_label","forged"},{"reason","deleted_target"}}});
        QVERIFY(!controller.applyPolicyDocument(forged.toVariantMap()));QVERIFY(!controller.policyBusy());QVERIFY(engine->operations.isEmpty());QVERIFY(!QFile::exists(dir.filePath("nodes.dpapi")));
    }
    void missingTargetsDoNotConsumeTheRuntimeLeafBudget(){
        auto policy=document();QJsonArray missing,members;
        for(int index=0;index<600;++index){const auto id=QUuid::createUuid().toString(QUuid::WithoutBraces);members.append(QJsonObject{{"kind","node"},{"id",id}});missing.append(QJsonObject{{"kind","node"},{"id",id},{"safe_label","removed fixture"},{"reason","deleted_target"}});}
        policy.insert("missing_targets",missing);policy.insert("groups",QJsonArray{QJsonObject{{"id","20000000-0000-4000-8000-000000000001"},{"name","Missing fixture"},{"strategy","manual"},{"members",members},{"selected",members.first()}}});
        QJsonObject runtime;QVERIFY2(RustCoreEngine::configurationV2({},policy,&runtime).isEmpty(),"Unavailable tombstones must not count as live runtime nodes");QVERIFY(runtime.value("nodes").toArray().isEmpty());
    }
    void v2WorkerRetainsLabelsWithoutKeepingStartupCredentialsOrSourceArchives(){
        RustCoreEngine worker;ProxyNode secret;secret.id="10000000-0000-4000-8000-000000000001";secret.name="retained label";
        secret.password="synthetic password";secret.host="synthetic.example.invalid";secret.sourceDocument="synthetic private archive";secret.nativeOutbound={{"password","synthetic"}};secret.originalConfiguration={{"private","synthetic"}};
        worker.m_options.nodes={secret};worker.m_options.dnsConfig={{"synthetic","private"}};worker.m_options.inboundPassword="synthetic";worker.m_options.lanPassword="synthetic";
        worker.retainPublicNodeIdentities();QCOMPARE(worker.m_options.nodes.size(),1);const auto retained=worker.m_options.nodes.first();
        QCOMPARE(retained.id,secret.id);QCOMPARE(retained.name,secret.name);QVERIFY(retained.password.isEmpty());QVERIFY(retained.host.isEmpty());QVERIFY(retained.sourceDocument.isEmpty());QVERIFY(retained.originalConfiguration.isEmpty());QVERIFY(retained.nativeOutbound.isEmpty());
        QVERIFY(worker.m_options.dnsConfig.isEmpty());QVERIFY(worker.m_options.inboundPassword.isEmpty());QVERIFY(worker.m_options.lanPassword.isEmpty());
    }
    void missingDefaultExitIsReportedAsConfigurationFailure_data(){
        QTest::addColumn<bool>("deleted");
        QTest::newRow("not-selected")<<false;QTest::newRow("deleted-source-node")<<true;
    }
    void missingDefaultExitIsReportedAsConfigurationFailure(){
        QFETCH(bool,deleted);RustCoreEngine worker;
        // A running session can lose its source through a catalog transaction.
        // Feed that core response through the real UI status adapter; starting
        // a new session with a missing default is correctly rejected earlier.
        worker.m_probeRequestId=7;
        worker.updateProbe({{"request_id",7},{"state","failed"},{"failure",QJsonObject{
            {"stage","outbound_connect"},{"code",deleted?"MissingTarget":"DefaultUnconfigured"}}}});
        QCOMPARE(worker.status().requestState,ProxyEngine::RequestState::Failed);
        QCOMPARE(worker.status().probeFailureCode,deleted?QString("MissingTarget"):QString("DefaultUnconfigured"));
        QCOMPARE(worker.status().nodeHealth,ProxyEngine::NodeHealth::Unknown);
        QVERIFY(worker.status().nodeMessage.contains(QStringLiteral("策略")));
        QVERIFY(worker.status().nodeMessage.contains(QStringLiteral("出口")));
    }
    void confirmedTunFaultReportsDisconnectedWithoutHidingTheFailure(){
        RustCoreEngine worker;
        // The first native authentication/recovery chain is exercised by the
        // owned Windows fault acceptance. This seam checks its observable
        // post-stop contract without a broker, registry write, driver or UAC.
        worker.m_tunRecoveryRequired=false;worker.m_tunRecoveryState=NativeTunRecoveryState::Clear;
        worker.m_status.state=ProxyEngine::State::Stopped;
        worker.m_status.processAlive=false;worker.m_status.tunEnabled=false;worker.m_status.proxyPort=0;
        QSignalSpy diagnostics(&worker,&ProxyEngine::diagnostic);
        worker.finishUnexpectedTunStop(QStringLiteral("controlled worker failure"));
        const auto status=worker.status();
        QCOMPARE(status.state,ProxyEngine::State::Failed);
        QCOMPARE(status.error,ProxyEngine::Error::ApiUnavailable);
        QVERIFY(!status.processAlive);QVERIFY(!status.apiHealthy);QVERIFY(!status.tunEnabled);
        QVERIFY(!status.tunCapturePossible);QVERIFY(!status.tunRecoveryRequired);QCOMPARE(status.proxyPort,0);
        QVERIFY(status.message.contains(QStringLiteral("增强模式意外停止")));QVERIFY(status.message.contains(QStringLiteral("系统网络已恢复")));
        QVERIFY(status.message.contains(QStringLiteral("可以重新连接")));QVERIFY(!status.message.contains("controlled worker failure"));
        QCOMPARE(diagnostics.size(),1);QCOMPARE(diagnostics.first().at(1).toString(),QString("TunFaultRecoveryConfirmed"));
        QVERIFY(diagnostics.first().at(2).toString().contains("controlled worker failure"));
        worker.refresh();worker.refresh();
        QCOMPARE(diagnostics.size(),1);QCOMPARE(worker.status().message,status.message);
    }
    void failedTunFaultConfirmationStaysBlockedWithoutRefreshRetries_data(){
        QTest::addColumn<bool>("brokerRetained");
        QTest::newRow("authentication-or-owner-unconfirmed")<<true;
        QTest::newRow("marker-write-unconfirmed")<<false;
    }
    void failedTunFaultConfirmationStaysBlockedWithoutRefreshRetries(){
        QFETCH(bool,brokerRetained);RustCoreEngine worker;
        // Keep teardown independent of the simulated owner. No native broker
        // is created: repeated public refresh must return before any I/O.
        const auto cleanup=qScopeGuard([&]{worker.m_brokerSession=false;worker.m_handle=0;});
        worker.m_brokerSession=brokerRetained;worker.m_handle=brokerRetained?7:0;
        worker.m_tunRecoveryRequired=!brokerRetained;
        worker.m_tunRecoveryState=brokerRetained?NativeTunRecoveryState::Pending:NativeTunRecoveryState::Unknown;
        worker.m_status.state=ProxyEngine::State::Degraded;
        worker.m_status.message=QStringLiteral("controlled recovery unconfirmed");
        worker.m_status.processAlive=brokerRetained;worker.m_status.tunEnabled=brokerRetained;
        QSignalSpy diagnostics(&worker,&ProxyEngine::diagnostic),changes(&worker,&ProxyEngine::statusChanged);
        for(int attempt=0;attempt<8;++attempt)worker.refresh();
        QCOMPARE(worker.status().state,ProxyEngine::State::Degraded);
        QCOMPARE(worker.status().message,QString("controlled recovery unconfirmed"));QCOMPARE(changes.size(),0);
        worker.finishUnexpectedTunStop(QStringLiteral("controlled worker failure"));
        const auto status=worker.status();
        QCOMPARE(status.state,ProxyEngine::State::Failed);QCOMPARE(status.error,ProxyEngine::Error::OwnershipFailed);
        QVERIFY(status.tunRecoveryRequired);QVERIFY(status.tunCapturePossible);QVERIFY(!status.apiHealthy);
        QCOMPARE(status.processAlive,brokerRetained);QCOMPARE(status.tunEnabled,brokerRetained);
        QCOMPARE(worker.m_handle,quint64(brokerRetained?7:0));QCOMPARE(worker.m_brokerSession,brokerRetained);
        QVERIFY(status.message.contains(QStringLiteral("恢复尚未确认")));QVERIFY(status.message.contains(QStringLiteral("连接已暂停")));
        QVERIFY(status.message.contains(QStringLiteral("重试关闭代理")));QVERIFY(!status.message.contains("controlled recovery unconfirmed"));
        QVERIFY(!worker.m_poll.isActive());
        QCOMPARE(diagnostics.size(),1);QCOMPARE(diagnostics.first().at(1).toString(),QString("TunFaultRecoveryUnconfirmed"));
        QVERIFY(diagnostics.first().at(2).toString().contains("controlled worker failure"));
        QVERIFY(diagnostics.first().at(2).toString().contains("controlled recovery unconfirmed"));
        for(int attempt=0;attempt<8;++attempt)worker.refresh();
        QCOMPARE(changes.size(),1);QCOMPARE(diagnostics.size(),1);QCOMPARE(worker.status().message,status.message);
        QCOMPARE(worker.m_handle,quint64(brokerRetained?7:0));QVERIFY(worker.status().tunRecoveryRequired);
    }
    void repeatedRealCoreFinishKeepsTheAdoptedWorkerPolicy(){
        QTcpServer lease;QVERIFY(lease.listen(QHostAddress::LocalHost));const auto port=lease.serverPort();lease.close();
        RustCoreEngine worker;EngineStartOptions options;options.proxyPort=port;options.policyDocument=document();
        options.configurationStoreId="40000000-0000-4000-8000-000000000001";options.configurationRevision="1";
        options.configurationRequestId="50000000-0000-4000-8000-000000000001";
        worker.start(options);QVERIFY2(worker.status().apiHealthy,qPrintable(worker.status().message));
        const auto base=worker.status().configurationReceipt;QJsonObject candidate;
        const auto changed=changedDocument();QVERIFY(RustCoreEngine::configurationV2(options,changed,&candidate).isEmpty());
        const auto requestId=QStringLiteral("50000000-0000-4000-8000-000000000002");
        QSignalSpy replies(&worker,&ProxyEngine::configurationCommandFinished);
        worker.configurationCommand({{"control_schema",2},{"op","prepare_configuration_v2"},{"request_id",requestId},
            {"store_id",options.configurationStoreId},{"base_saved_revision","1"},{"candidate_revision","2"},
            {"expected_generation",base.value("generation")},{"base_applied_revision","1"},{"candidate",candidate}});
        QCOMPARE(replies.size(),1);const auto prepared=replies.last().at(1).toJsonObject();QVERIFY2(prepared.value("ok").toBool(),qPrintable(QString::fromUtf8(QJsonDocument(prepared).toJson())));
        worker.configurationCommand({{"control_schema",2},{"op","activate_configuration_v2"},{"request_id",requestId},
            {"prepared_token",prepared.value("prepared_token")},{"plan_digest",prepared.value("plan_digest")},
            {"candidate_revision","2"},{"expected_generation",prepared.value("expected_generation")}});
        QCOMPARE(replies.size(),2);QVERIFY(replies.last().at(1).toJsonObject().value("ok").toBool());
        const QJsonObject finish{{"control_schema",2},{"op","finish_configuration_v2"},{"request_id",requestId},
            {"prepared_token",prepared.value("prepared_token")},{"durable_receipt",QJsonObject{
                {"store_id",options.configurationStoreId},{"request_id",requestId},{"saved_revision","2"},{"plan_digest",prepared.value("plan_digest")}}}};
        worker.configurationCommand(finish);QCOMPARE(replies.size(),3);QVERIFY(replies.last().at(1).toJsonObject().value("ok").toBool());
        QCOMPARE(worker.m_options.policyDocument,changed);QVERIFY(worker.m_preparedPolicy.isEmpty());
        worker.configurationCommand(finish);QCOMPARE(replies.size(),4);QVERIFY(replies.last().at(1).toJsonObject().value("ok").toBool());
        QCOMPARE(worker.m_options.policyDocument,changed);QCOMPARE(worker.status().configurationReceipt.value("applied_revision").toString(),QString("2"));
        worker.stop();QVERIFY(!worker.status().processAlive);
    }
    void durableRevokeDropsControllerCredentialsBeforeTheFinishAcknowledgement(){
        QTemporaryDir dir;const auto path=dir.filePath("nodes.dpapi");QString removed;
        {NodeStore legacy(path);QVERIFY(legacy.saveNode({{"name","revoked fixture"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",9},{"username","fixture-user"},{"password","synthetic-revoked-secret"}}));removed=legacy.nodes().first().id;}
        auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();EngineController controller(std::move(peer),nullptr,path);
        QVERIFY(controller.confirmPolicyMigration());QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QCOMPARE(controller.m_options.nodes.size(),1);controller.connectConfiguredPolicy();
        bool cachePurgedBeforeAck=false;engine->beforeFinish=[&]{cachePurgedBeforeAck=controller.m_options.nodes.isEmpty()&&controller.m_policyCandidateOptions.nodes.isEmpty()&&envelope(path).value("committed").toObject().value("request_id").toString()==controller.policyRequestId();};
        QVERIFY(controller.deleteNode(removed));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY(cachePurgedBeforeAck);QVERIFY(controller.m_options.nodes.isEmpty());QVERIFY(controller.m_policyCandidateOptions.nodes.isEmpty());QVERIFY(controller.m_policyRuntimeCandidate.isEmpty());QVERIFY(controller.m_policyCandidateNetwork.isEmpty());
    }
    void reconcilingConfigurationCannotAdmitIndependentNodeTests(){
        QTemporaryDir dir;const auto path=dir.filePath("nodes.dpapi");QString id;
        {NodeStore legacy(path);QVERIFY(legacy.saveNode({{"name","blocked probe fixture"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",9}}));id=legacy.nodes().first().id;}
        EngineController controller(std::make_unique<ConfigurationPeer>(),nullptr,path);controller.m_policyState="reconciling";
        controller.testAllNodes(QUrl("https://fixture.example.invalid"));QVERIFY(!controller.m_tests.busy());QVERIFY(!controller.nodeError().isEmpty());
        controller.testNodes({id},QUrl("https://fixture.example.invalid"));QVERIFY(!controller.m_tests.busy());
        controller.testSelectedNode(id,QUrl("https://fixture.example.invalid"));QVERIFY(!controller.m_tests.busy());
    }
    void lanPreferencesUseTheExistingDurableTransactionWithoutRestartingCore(){
        QTemporaryDir dir;const auto path=dir.filePath("lan-preferences.dpapi");const QString secret="synthetic-lan-password-1234";
        QVariantMap expected{{"listen_ip","192.168.50.1"},{"http_port",7899},{"socks_port",7899},{"udp_port_start",7900},{"udp_port_end",7915},
            {"allowed_cidrs",QStringList{"192.168.50.0/24"}},{"max_connections",128},{"max_connections_per_client",16},{"auth_failures_per_minute",10},{"idle_timeout_secs",300}};
        {
            auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
            EngineController controller(std::move(peer),nullptr,path,false,std::make_unique<PolicySystemProxyBackend>());
            QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
            controller.connectConfiguredPolicy();QVERIFY(controller.processAlive());const auto starts=engine->starts,stops=engine->stops;
            auto candidate=controller.m_options;candidate.lanConfiguration=expected;candidate.lanUsername="swirl";candidate.lanPassword=secret;
            QJsonObject beforePlan,afterPlan;QVERIFY(RustCoreEngine::configurationV2(controller.m_options,document(),&beforePlan).isEmpty());
            QVERIFY(RustCoreEngine::configurationV2(candidate,document(),&afterPlan).isEmpty());QCOMPARE(beforePlan,afterPlan);
            QVERIFY(controller.applyPolicyConfiguration(document(),candidate));QVERIFY(controller.m_options.lanPassword.isEmpty());
            QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));
            QCOMPARE(controller.m_options.lanConfiguration,expected);QCOMPARE(controller.m_options.lanPassword,secret);
            QCOMPARE(engine->starts,starts);QCOMPARE(engine->stops,stops);QVERIFY(controller.processAlive());QVERIFY(!controller.lanEnabled());
            const auto stored=envelope(path);QVERIFY(!stored.contains("pending"));
            const auto network=stored.value("committed").toObject().value("snapshot").toObject().value("networkConfiguration").toObject();
            QCOMPARE(network.value("lanConfiguration").toObject(),QJsonObject::fromVariantMap(expected));QCOMPARE(network.value("allowLan"),QJsonValue(false));
            QVERIFY(!network.value("lanPasswordProtected").toString().isEmpty());QVERIFY(!QJsonDocument(stored).toJson().contains(secret.toUtf8()));
            QVERIFY(!bytes(path).contains(secret.toUtf8()));
            const auto original=bytes(path);const auto revision=controller.savedRevision();engine->rejectPrepare=true;
            candidate=controller.m_options;candidate.lanPassword="another-synthetic-lan-password";
            QVERIFY(controller.applyPolicyConfiguration(document(),candidate));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
            QCOMPARE(bytes(path),original);QCOMPARE(controller.savedRevision(),revision);QCOMPARE(controller.m_options.lanPassword,secret);
            QCOMPARE(engine->starts,starts);QCOMPARE(engine->stops,stops);QVERIFY(controller.processAlive());
            controller.stop();
        }
        EngineController reopened(std::make_unique<ConfigurationPeer>(),nullptr,path,false,std::make_unique<PolicySystemProxyBackend>());
        // Exercise the QML property while keeping the stop-regression suite
        // compilable against its exact pre-LAN controller negative control.
        QCOMPARE(QJsonObject::fromVariantMap(reopened.property("lanConfiguration").toMap()),QJsonObject::fromVariantMap(expected));
        QCOMPARE(reopened.m_options.lanPassword,secret);QVERIFY(!reopened.lanEnabled());
    }
    void preparationFailureLeavesDiskAndRunningReceiptUnchanged(){
        QTemporaryDir dir;auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();EngineController controller(std::move(peer),nullptr,dir.filePath("nodes.dpapi"));
        QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);controller.connectConfiguredPolicy();QVERIFY(controller.processAlive());
        const auto prior=bytes(dir.filePath("nodes.dpapi"));const auto revision=controller.savedRevision();engine->rejectPrepare=true;
        QVERIFY(controller.applyPolicyDocument(changedDocument().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QCOMPARE(bytes(dir.filePath("nodes.dpapi")),prior);QCOMPARE(controller.savedRevision(),revision);QCOMPARE(controller.appliedRevision(),revision);QCOMPARE(engine->activations,0);QVERIFY(!engine->gate);
    }
    void onlineCommitHasDurableIntentBeforeActivationAndAcknowledgesActualReceipt(){
        QTemporaryDir dir;const auto path=dir.filePath("nodes.dpapi");auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();EngineController controller(std::move(peer),nullptr,path);
        QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);controller.connectConfiguredPolicy();
        bool intentObserved=false;engine->beforeActivate=[&]{const auto stored=envelope(path);intentObserved=stored.value("pending").toObject().value("request_id").toString()==controller.policyRequestId()&&stored.value("committed").toObject().value("saved_revision")==QJsonValue("1");};
        QVERIFY(controller.applyPolicyDocument(changedDocument().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QVERIFY(intentObserved);QCOMPARE(controller.savedRevision(),QString("2"));QCOMPARE(controller.appliedRevision(),QString("2"));QVERIFY(!engine->gate);
        QCOMPARE(controller.policyReceipt().value("applied_revision").toString(),QString("2"));QVERIFY(!envelope(path).contains("pending"));QCOMPARE(engine->activations,1);
    }
    void finalWriteFailureRestoresOldPlanBeforeReopeningAdmission(){
        QTemporaryDir dir;const auto path=dir.filePath("nodes.dpapi"),backup=dir.filePath("intent.dpapi");auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();EngineController controller(std::move(peer),nullptr,path);
        QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);controller.connectConfiguredPolicy();
        bool injected=false,restored=false;
        engine->beforeActivate=[&]{injected=QFile::rename(path,backup)&&QDir().mkdir(path);};
        engine->beforeRollback=[&]{restored=QDir().rmdir(path)&&QFile::rename(backup,path);};
        QVERIFY(controller.applyPolicyDocument(changedDocument().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QVERIFY(injected);QVERIFY(restored);QVERIFY(engine->rolledBack);QVERIFY(!engine->gate);QCOMPARE(controller.savedRevision(),QString("1"));QCOMPARE(controller.appliedRevision(),QString("1"));
        QCOMPARE(controller.policyDocument().value("mode").toString(),QString("direct"));QVERIFY(!envelope(path).contains("pending"));QVERIFY(!controller.policyError().isEmpty());
    }
    void lostFinishAcknowledgementReconcilesWithoutASecondActivation(){
        QTemporaryDir dir;auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();EngineController controller(std::move(peer),nullptr,dir.filePath("nodes.dpapi"));
        QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);controller.connectConfiguredPolicy();engine->rejectFinishOnce=true;
        QVERIFY(controller.applyPolicyDocument(changedDocument().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QCOMPARE(engine->activations,1);QCOMPARE(engine->operations.count("finish_configuration_v2"),2);QCOMPARE(engine->operations.count("configuration_status_v2"),1);
        QCOMPARE(controller.savedRevision(),QString("2"));QCOMPARE(controller.appliedRevision(),QString("2"));QVERIFY(controller.policyError().isEmpty());
    }
    void legacyCatalogRequiresReviewAndKeepsNodeIdentityInTheV2Commit(){
        QTemporaryDir dir;const auto path=dir.filePath("nodes.dpapi");QString nodeId;
        {NodeStore legacy(path);QVERIFY(legacy.saveNode({{"name","Legacy resource"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",9}}));nodeId=legacy.nodes().first().id;}
        const auto original=bytes(path);auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();EngineController controller(std::move(peer),nullptr,path);
        QVERIFY(controller.policyMigrationRequired());QVERIFY(!controller.applyPolicyDocument(controller.policyDocument()));QCOMPARE(bytes(path),original);QVERIFY(engine->operations.isEmpty());
        // An ordinary rejection must not destroy the immutable migration review.
        QVERIFY(controller.confirmPolicyMigration());QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QVERIFY(!controller.policyMigrationRequired());QVERIFY(controller.policyV2Active());QCOMPARE(controller.nodes().first().toMap().value("id").toString(),nodeId);
        QCOMPARE(envelope(path).value("schema").toInt(),2);QVERIFY(!controller.processAlive());
    }
    void ambiguousLegacyReferencesNeverPartiallyMigrateOrRewriteTheOriginal(){
        QTemporaryDir dir;const auto path=dir.filePath("nodes.dpapi");
        {NodeStore legacy(path);QVERIFY(legacy.saveNode({{"name","Collision"},{"protocol","socks5"},{"host","127.0.0.1"},{"port",9}}));
         QVERIFY(legacy.saveNetworkConfiguration({{"schema",1},{"groups",QJsonArray{QJsonObject{{"name","Collision"},{"type","select"},{"proxies",QJsonArray{legacy.nodes().first().id}}}}}}));}
        const auto original=bytes(path);auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();EngineController controller(std::move(peer),nullptr,path);
        QVERIFY(controller.policyMigrationRequired());QVERIFY(!controller.policyError().isEmpty());QVERIFY(!controller.confirmPolicyMigration());
        QCOMPARE(bytes(path),original);QVERIFY(!controller.policyV2Active());QVERIFY(engine->operations.isEmpty());QVERIFY(!controller.processAlive());
    }
    void cachedConfigurationReviewIsReadOnlyAndOneUseAfterRealRustValidation(){
        QTemporaryDir dir;const auto path=dir.filePath("review.dpapi"),source=seedReviewSource(path);QVERIFY(!source.isEmpty());
        EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);QVERIFY(controller.confirmPolicyMigration());
        QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));
        const auto before=bytes(path);const auto refreshed=controller.m_store.subscriptions().first().lastSuccess;
        QSignalSpy downloads(&controller.m_imports,&NodeImportService::downloadDiagnostic);
        controller.m_imports.reviewConfiguration(source);const auto review=controller.m_imports.configurationReview();
        QVERIFY2(review.value("canApply").toBool(),qPrintable(review.value("error").toString()));QVERIFY(controller.m_imports.hasConfigurationReview());
        QCOMPARE(bytes(path),before);QCOMPARE(downloads.size(),0);QVERIFY(controller.m_subscriptionReview.has_value());
        const auto publicBytes=QJsonDocument::fromVariant(review).toJson();QVERIFY(!publicBytes.contains("private-fixture-token"));QVERIFY(!publicBytes.contains("sourceDigest"));
        QVERIFY(controller.m_imports.applyReviewedConfiguration());QVERIFY(!controller.m_imports.applyReviewedConfiguration());
        QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy()&&!controller.m_imports.busy(),5000);
        QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));QVERIFY(controller.m_imports.configurationReview().value("applied").toBool());
        QCOMPARE(controller.strategyGroups().size(),1);QCOMPARE(controller.servicePolicies().size(),0);
        QCOMPARE(controller.m_store.subscriptions().first().lastSuccess,refreshed);QCOMPARE(downloads.size(),0);
        QVERIFY(!controller.m_subscriptionReview.has_value());QVERIFY(!controller.m_imports.applyReviewedConfiguration());
        QVERIFY(!bytes(path).contains("private-fixture-token"));controller.m_imports.cancelConfigurationReview();QVERIFY(!controller.m_imports.hasConfigurationReview());
    }
    void expiredAndChangedRevisionReviewsCannotBeReplayed(){
        QTemporaryDir dir;const auto path=dir.filePath("expired.dpapi"),source=seedReviewSource(path);QVERIFY(!source.isEmpty());
        EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);QVERIFY(controller.confirmPolicyMigration());QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        controller.m_imports.reviewConfiguration(source);QVERIFY(controller.m_imports.configurationReview().value("canApply").toBool());
        const auto before=bytes(path);controller.m_subscriptionReview->expiry=QDeadlineTimer(0);
        QVERIFY(!controller.m_imports.applyReviewedConfiguration());QCOMPARE(bytes(path),before);QVERIFY(!controller.m_imports.applyReviewedConfiguration());
        controller.m_imports.reviewConfiguration(source);QVERIFY(controller.m_subscriptionReview.has_value());
        // A separate configuration editor can commit while this review exists.
        auto changed=controller.m_policyDocument;changed.insert("mode",changed.value("mode")==QJsonValue("direct")?"rule":"direct");
        QVERIFY(controller.applyPolicyDocument(changed.toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        const auto changedBytes=bytes(path);
        QVERIFY(!controller.m_imports.applyReviewedConfiguration());QCOMPARE(bytes(path),changedBytes);QVERIFY(!controller.m_subscriptionReview.has_value());
    }
    void synchronousReviewDismissalAtReceiptReleasesTheImportGate(){
        QTemporaryDir dir;const auto path=dir.filePath("dismiss.dpapi"),source=seedReviewSource(path);QVERIFY(!source.isEmpty());
        EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);QVERIFY(controller.confirmPolicyMigration());QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        controller.m_imports.reviewConfiguration(source);QVERIFY(controller.m_imports.configurationReview().value("canApply").toBool());
        // Reduced motion can close the popup synchronously from this signal,
        // before the coordinator invokes the importer's catalog completion.
        connect(&controller,&EngineController::policyApplyFinished,&controller.m_imports,[&](const QString &,bool){controller.m_imports.cancelConfigurationReview();});
        QVERIFY(controller.m_imports.applyReviewedConfiguration());QTRY_VERIFY_WITH_TIMEOUT(!controller.m_imports.busy(),5000);
        QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));QVERIFY(!controller.m_imports.hasPreview());QVERIFY(!controller.m_imports.hasConfigurationReview());
        const auto existing=controller.m_store.subscriptions().first();
        QVERIFY(controller.m_imports.saveSubscription(existing.id,"Edited after review",{},360,false));QTRY_VERIFY_WITH_TIMEOUT(!controller.m_imports.busy(),5000);
        QCOMPARE(controller.m_imports.providers().first().toMap().value("name").toString(),QString("Edited after review"));
    }
    void fullConfigurationReviewRejectsUnknownExecutionFieldsAndMissingSourceIdentity(){
        QTemporaryDir dir;const auto path=dir.filePath("unsafe.dpapi"),source=seedReviewSource(path,{{"script",QJsonObject{{"code","never-execute"}}}});QVERIFY(!source.isEmpty());
        EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,path);QVERIFY(controller.confirmPolicyMigration());QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        const auto before=bytes(path);controller.m_imports.reviewConfiguration(source);
        QVERIFY(!controller.m_imports.configurationReview().value("canApply").toBool());QVERIFY(!controller.m_imports.configurationReview().value("error").toString().isEmpty());
        QVERIFY(!controller.m_imports.applyReviewedConfiguration());QCOMPARE(bytes(path),before);QVERIFY(!controller.m_subscriptionReview.has_value());
        controller.m_imports.cancelConfigurationReview();
        const auto legacyPath=dir.filePath("unidentified.dpapi"),legacySource=seedReviewSource(legacyPath,{},false);QVERIFY(!legacySource.isEmpty());
        EngineController legacy(std::make_unique<RustCoreEngine>(),nullptr,legacyPath);QVERIFY(legacy.confirmPolicyMigration());QTRY_VERIFY_WITH_TIMEOUT(!legacy.policyBusy(),5000);
        const auto legacyBytes=bytes(legacyPath);legacy.m_imports.reviewConfiguration(legacySource);QVERIFY(!legacy.m_imports.configurationReview().value("canApply").toBool());
        QVERIFY(legacy.m_imports.configurationReview().value("error").toString().contains(QStringLiteral("原始响应身份")));QCOMPARE(bytes(legacyPath),legacyBytes);
    }
    void importerHashBindsTheExactResponseInsteadOfOnlyItsDecodedMeaning(){
        const QByteArray plain="socks5://127.0.0.1:9#Hash%20fixture";
        const auto first=NodeImporter::parse(plain),second=NodeImporter::parse(plain.toBase64());QVERIFY(first);QVERIFY(second);
        QCOMPARE(first.sourceDigest,QString::fromLatin1(QCryptographicHash::hash(plain,QCryptographicHash::Sha256).toHex()));
        QCOMPARE(second.sourceDigest,QString::fromLatin1(QCryptographicHash::hash(plain.toBase64(),QCryptographicHash::Sha256).toHex()));
        QVERIFY(first.sourceDigest!=second.sourceDigest);
    }
    void activityProxySwitchStartsSavedRustAndRestoresTheExternalProxy(){
        ControlledNetwork network;QVERIFY(network.start());
        QTemporaryDir dir;QTcpServer reserved;QVERIFY(reserved.listen(QHostAddress::LocalHost));const auto port=reserved.serverPort();
        auto backend=std::make_unique<PolicySystemProxyBackend>();auto *proxy=backend.get();
        EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,dir.filePath("master.dpapi"),false,std::move(backend));
        controller.m_proxyProbeUrl=network.url();
        controller.setProxyPort(port);QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        QVERIFY2(controller.policyError().isEmpty(),qPrintable(controller.policyError()));const auto revision=controller.savedRevision();reserved.close();
        QVERIFY(controller.systemProxy()->systemEnabled());QVERIFY(!controller.systemProxy()->owned());
        controller.toggleSystemProxy();QVERIFY(controller.proxyRequested());
        QTRY_VERIFY_WITH_TIMEOUT(controller.systemProxy()->owned()&&controller.systemProxy()->enabled(),7000);
        QVERIFY(controller.processAlive());QCOMPARE(controller.appliedRevision(),revision);QCOMPARE(proxy->takeoverCalls,1);QCOMPARE(proxy->lastPort,int(port));QVERIFY(proxy->lastPid>0);
        controller.toggleSystemProxy();QVERIFY(!controller.proxyRequested());
        QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.busy(),5000);
        QVERIFY(!controller.systemProxy()->owned());QVERIFY(controller.systemProxy()->systemEnabled());QCOMPARE(proxy->restoreCalls,1);QCOMPARE(controller.savedRevision(),revision);
    }
    void aListeningCoreWithAFailedExitDoesNotTakeSystemProxyOwnership(){
        QTemporaryDir dir;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        auto backend=std::make_unique<PolicySystemProxyBackend>();auto *proxy=backend.get();
        auto peer=std::make_unique<ConfigurationPeer>();peer->probeSucceeds=false;
        EngineController controller(std::move(peer),nullptr,dir.filePath("failed-exit.dpapi"),false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY(!controller.policyBusy());
        controller.toggleSystemProxy();QTRY_VERIFY_WITH_TIMEOUT(!controller.proxyRequested()&&!controller.processAlive(),5000);
        QCOMPARE(proxy->enableCalls,0);QVERIFY(!controller.systemProxy()->owned());QVERIFY(proxy->current().systemEnabled);
        QVERIFY(controller.routingError().contains("Controlled origin TLS failure"));
    }
    void closingDuringTheListenerProbeCannotReacquireFromALateCallback(){
        QTemporaryDir dir;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        auto backend=std::make_unique<PolicySystemProxyBackend>();auto *proxy=backend.get();auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("cancel.dpapi"),false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        controller.toggleSystemProxy();QVERIFY(controller.systemProxyBusy());controller.toggleSystemProxy();
        QVERIFY(!controller.proxyRequested());QVERIFY(!controller.processAlive());QCOMPARE(proxy->enableCalls,0);
        controller.toggleSystemProxy();QTRY_VERIFY_WITH_TIMEOUT(controller.systemProxy()->owned(),3000);
        QTest::qWait(1600);QVERIFY(controller.proxyRequested());QVERIFY(controller.processAlive());QCOMPARE(proxy->enableCalls,1);QCOMPARE(engine->starts,2);
        controller.toggleSystemProxy();QVERIFY(!controller.proxyRequested());QVERIFY(!controller.processAlive());QVERIFY(proxy->current().systemEnabled);QCOMPARE(proxy->restoreCalls,1);
    }
    void stoppingAndClosingDuringGuardReadinessNeverTakeOwnership(){
        for(const bool closing:{false,true}) {
            QTemporaryDir dir;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
            auto backend=std::make_unique<WaitingPolicyProxyBackend>();auto *proxy=backend.get();
            EngineController controller(std::make_unique<ConfigurationPeer>(),nullptr,dir.filePath("guard-cancel.dpapi"),false,std::move(backend));
            controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY(!controller.policyBusy());
            controller.toggleSystemProxy();QTRY_VERIFY(proxy->preparations>0);QVERIFY(controller.systemProxyBusy());
            if(closing)controller.shutdown();else controller.toggleSystemProxy();
            proxy->ready=true;QTest::qWait(80);
            QVERIFY(!controller.proxyRequested());QVERIFY(!controller.processAlive());QVERIFY(!controller.systemProxyBusy());
            QCOMPARE(proxy->memory.enableCalls,0);QVERIFY(proxy->memory.current().systemEnabled);
            if(!closing){controller.toggleSystemProxy();QTRY_VERIFY(controller.systemProxy()->owned());QCOMPARE(proxy->memory.enableCalls,1);controller.stop();}
        }
    }
    void changedCoreReceiptDuringGuardReadinessRejectsTheOldTakeover(){
        QTemporaryDir dir;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        auto backend=std::make_unique<WaitingPolicyProxyBackend>();auto *proxy=backend.get();auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("guard-generation.dpapi"),false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY(!controller.policyBusy());
        controller.toggleSystemProxy();QTRY_VERIFY(proxy->preparations>0);
        engine->current.configurationReceipt.insert("applied_revision","unexpected-new-revision");proxy->ready=true;
        QTRY_VERIFY(!controller.proxyRequested()&&!controller.processAlive());
        QCOMPARE(proxy->memory.enableCalls,0);QVERIFY(!controller.routingError().isEmpty());QVERIFY(proxy->memory.current().systemEnabled);
    }
    void releaseCompletionResumesOnlyTheCurrentProxyIntent(){
        for(const bool cancel:{false,true}) {
            QTemporaryDir dir;QTcpServer listener,capture;QVERIFY(listener.listen(QHostAddress::LocalHost));QVERIFY(capture.listen(QHostAddress::LocalHost));
            auto backend=std::make_unique<WaitingPolicyProxyBackend>();auto *proxy=backend.get();proxy->ready=true;
            auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
            EngineController controller(std::move(peer),nullptr,dir.filePath("restore-contention.dpapi"),false,std::move(backend));
            controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY(!controller.policyBusy());
            controller.toggleSystemProxy();QTRY_VERIFY(controller.systemProxy()->owned());QCOMPARE(proxy->memory.enableCalls,1);
            const auto startsBefore=engine->starts,stopsBefore=engine->stops;
            proxy->releaseReady=false;controller.setCaptureProxyPort(capture.serverPort());QVERIFY(controller.systemProxyBusy());
            if(cancel){
                controller.toggleSystemProxy();
                QVERIFY(!controller.proxyRequested());QVERIFY(controller.systemProxy()->owned());QVERIFY(controller.systemProxyBusy());
                QVERIFY(controller.processAlive());QCOMPARE(engine->stops,stopsBefore);QCOMPARE(engine->starts,startsBefore);
                QTest::qWait(80);QVERIFY(controller.processAlive());QCOMPARE(engine->stops,stopsBefore);
                QCOMPARE(engine->starts,startsBefore);QCOMPARE(proxy->memory.restoreCalls,0);
            }
            proxy->releaseReady=true;
            if(cancel) {
                QTRY_VERIFY(!controller.systemProxyBusy());QTest::qWait(60);
                QVERIFY(!controller.proxyRequested());QVERIFY(!controller.systemProxy()->owned());QCOMPARE(proxy->memory.enableCalls,1);
                QVERIFY(!controller.processAlive());QCOMPARE(engine->stops,stopsBefore+1);QCOMPARE(engine->starts,startsBefore);
            }else {
                QTRY_COMPARE(proxy->memory.enableCalls,2);QTRY_VERIFY(!controller.systemProxyBusy());
                QVERIFY(controller.proxyRequested());QVERIFY(controller.systemProxy()->owned());QCOMPARE(proxy->memory.lastPort,int(capture.serverPort()));
                controller.stop();
            }
            QCOMPARE(proxy->memory.restoreCalls,cancel?1:2);QVERIFY(proxy->memory.current().systemEnabled);
        }
    }
    void normalStopKeepsTheCoreAliveUntilOwnedProxyReleaseCompletes(){
        QTemporaryDir dir;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        auto backend=std::make_unique<WaitingPolicyProxyBackend>();auto *proxy=backend.get();proxy->ready=true;
        auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("normal-stop-release.dpapi"),false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY(!controller.policyBusy());
        const auto original=controller.systemProxy()->diagnosticState();
        controller.toggleSystemProxy();QTRY_VERIFY(controller.systemProxy()->owned());QVERIFY(controller.processAlive());QVERIFY(controller.apiHealthy());
        const auto startsBefore=engine->starts,stopsBefore=engine->stops;
        QSignalSpy released(controller.systemProxy(),&SystemProxySession::releaseFinished);
        bool aliveAtRelease=false,healthyAtRelease=false;
        connect(controller.systemProxy(),&SystemProxySession::releaseFinished,&controller,[&](bool){
            aliveAtRelease=controller.processAlive();healthyAtRelease=controller.apiHealthy();
        });
        bool releaseReentryArmed=false,reentrantStopObserved=false,reentryKeptCoreAlive=false;
        connect(&controller,&EngineController::statusChanged,&controller,[&]{
            if(!releaseReentryArmed||controller.systemProxy()->owned())return;
            releaseReentryArmed=false;reentrantStopObserved=true;
            controller.stop();reentryKeptCoreAlive=controller.processAlive()&&engine->stops==stopsBefore;
        });
        proxy->releaseReady=false;controller.stop();controller.stop();
        QVERIFY(!controller.proxyRequested());QVERIFY(controller.systemProxy()->owned());QVERIFY(controller.systemProxyBusy());
        QVERIFY(controller.processAlive());QVERIFY(controller.apiHealthy());QCOMPARE(engine->stops,stopsBefore);QCOMPARE(engine->starts,startsBefore);
        QTest::qWait(80);controller.stop();
        QVERIFY(controller.processAlive());QVERIFY(controller.apiHealthy());QCOMPARE(engine->stops,stopsBefore);QCOMPARE(engine->starts,startsBefore);
        QCOMPARE(released.size(),0);QCOMPARE(proxy->memory.restoreCalls,0);QCOMPARE(proxy->memory.enableCalls,1);
        releaseReentryArmed=true;proxy->releaseReady=true;
        QTRY_COMPARE_WITH_TIMEOUT(released.size(),1,1000);QVERIFY(released.first().first().toBool());QVERIFY(aliveAtRelease);QVERIFY(healthyAtRelease);
        QVERIFY(reentrantStopObserved);QVERIFY(reentryKeptCoreAlive);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.systemProxyBusy(),1000);
        QCOMPARE(engine->stops,stopsBefore+1);QCOMPARE(engine->starts,startsBefore);QCOMPARE(proxy->memory.restoreCalls,1);
        QVERIFY(!controller.systemProxy()->owned());QVERIFY(!controller.proxyRequested());QCOMPARE(controller.systemProxy()->diagnosticState(),original);
        QTest::qWait(80);QCOMPARE(released.size(),1);QCOMPARE(engine->stops,stopsBefore+1);QCOMPARE(engine->starts,startsBefore);
        QCOMPARE(proxy->memory.enableCalls,1);QCOMPARE(proxy->memory.restoreCalls,1);QCOMPARE(proxy->memory.disableCalls,1);
    }
    void normalStopReleaseFailureAndTimeoutKeepTheOwnedListenerRetryable_data(){
        QTest::addColumn<bool>("timeout");
        QTest::newRow("release-preparation-failure")<<false;
        QTest::newRow("real-two-second-release-timeout")<<true;
    }
    void normalStopReleaseFailureAndTimeoutKeepTheOwnedListenerRetryable(){
        QFETCH(bool,timeout);
        QTemporaryDir dir;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        auto backend=std::make_unique<WaitingPolicyProxyBackend>();auto *proxy=backend.get();proxy->ready=true;
        auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("normal-stop-failed-release.dpapi"),false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY(!controller.policyBusy());
        const auto original=controller.systemProxy()->diagnosticState();
        controller.toggleSystemProxy();QTRY_VERIFY(controller.systemProxy()->owned());QVERIFY(controller.processAlive());
        const auto startsBefore=engine->starts,stopsBefore=engine->stops;
        QSignalSpy released(controller.systemProxy(),&SystemProxySession::releaseFinished);
        QList<bool> aliveAtRelease,healthyAtRelease;QStringList errorsAtRelease;
        connect(controller.systemProxy(),&SystemProxySession::releaseFinished,&controller,[&](bool){
            aliveAtRelease.append(controller.processAlive());healthyAtRelease.append(controller.apiHealthy());errorsAtRelease.append(controller.systemProxy()->error());
        });
        proxy->releaseReady=false;QElapsedTimer releaseElapsed;releaseElapsed.start();controller.stop();
        QVERIFY(!controller.proxyRequested());QVERIFY(controller.systemProxy()->owned());QVERIFY(controller.systemProxyBusy());
        QVERIFY(controller.processAlive());QVERIFY(controller.apiHealthy());QCOMPARE(engine->stops,stopsBefore);
        if(!timeout)proxy->releaseFails=true;
        // Exercise the unchanged production deadline; do not advance a private
        // timer or replace ownership restoration with a timeout-only success.
        QTRY_COMPARE_WITH_TIMEOUT(released.size(),1,4500);
        if(timeout)QVERIFY2(releaseElapsed.elapsed()>=2000,"The real two-second release deadline did not elapse.");
        QVERIFY(!released.first().first().toBool());QCOMPARE(aliveAtRelease.size(),1);QVERIFY(aliveAtRelease.first());QVERIFY(healthyAtRelease.first());
        QVERIFY(!errorsAtRelease.first().isEmpty());
        if(timeout)QVERIFY(errorsAtRelease.first().contains(QStringLiteral("可重试释放代理")));
        else QVERIFY(errorsAtRelease.first().contains(QStringLiteral("release preparation failure")));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.systemProxyBusy(),1000);
        QVERIFY(controller.systemProxy()->owned());QVERIFY(controller.processAlive());QVERIFY(controller.apiHealthy());
        QVERIFY(!controller.systemProxy()->error().isEmpty());QVERIFY(!controller.proxyRequested());
        QCOMPARE(engine->stops,stopsBefore);QCOMPARE(engine->starts,startsBefore);QCOMPARE(proxy->memory.restoreCalls,0);
        QTest::qWait(80);QCOMPARE(released.size(),1);QVERIFY(controller.processAlive());QVERIFY(controller.systemProxy()->owned());
        QVERIFY(!controller.systemProxyBusy());QCOMPARE(engine->stops,stopsBefore);QCOMPARE(engine->starts,startsBefore);QCOMPARE(proxy->memory.enableCalls,1);
        proxy->releaseFails=false;proxy->releaseReady=true;controller.stop();
        QTRY_COMPARE_WITH_TIMEOUT(released.size(),2,1000);QVERIFY(released.last().first().toBool());
        QCOMPARE(aliveAtRelease.size(),2);QVERIFY(aliveAtRelease.last());QVERIFY(healthyAtRelease.last());
        QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.systemProxyBusy(),1000);
        QCOMPARE(engine->stops,stopsBefore+1);QCOMPARE(engine->starts,startsBefore);QCOMPARE(proxy->memory.restoreCalls,1);
        QVERIFY(!controller.systemProxy()->owned());QVERIFY(!controller.proxyRequested());QVERIFY(controller.systemProxy()->error().isEmpty());
        QCOMPARE(controller.systemProxy()->diagnosticState(),original);QTest::qWait(80);
        QCOMPARE(released.size(),2);QCOMPARE(engine->stops,stopsBefore+1);QCOMPARE(engine->starts,startsBefore);QCOMPARE(proxy->memory.enableCalls,1);
    }
    void shutdownKeepsTheCoreAliveUntilOwnedProxyReleaseCompletes(){
        QTemporaryDir dir;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        auto backend=std::make_unique<WaitingPolicyProxyBackend>();auto *proxy=backend.get();proxy->ready=true;
        auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("shutdown-release.dpapi"),false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY(!controller.policyBusy());
        controller.toggleSystemProxy();QTRY_VERIFY(controller.systemProxy()->owned());QVERIFY(controller.processAlive());
        const auto stoppedBefore=engine->stops;
        QSignalSpy released(controller.systemProxy(),&SystemProxySession::releaseFinished);
        bool aliveAtRelease=false;
        connect(controller.systemProxy(),&SystemProxySession::releaseFinished,&controller,[&](bool){aliveAtRelease=controller.processAlive();});
        proxy->releaseReady=false;controller.shutdown();controller.shutdown();
        QVERIFY(controller.systemProxy()->owned());QVERIFY(controller.systemProxyBusy());
        QVERIFY(controller.processAlive());QCOMPARE(engine->stops,stoppedBefore);
        QTest::qWait(80);QVERIFY(controller.processAlive());QCOMPARE(released.size(),0);QCOMPARE(proxy->memory.restoreCalls,0);
        proxy->releaseReady=true;
        QTRY_COMPARE_WITH_TIMEOUT(released.size(),1,1000);QVERIFY(released.first().first().toBool());QVERIFY(aliveAtRelease);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.systemProxyBusy(),1000);
        QCOMPARE(engine->stops,stoppedBefore+1);QCOMPARE(proxy->memory.restoreCalls,1);QVERIFY(!controller.systemProxy()->owned());
        QVERIFY(proxy->memory.current().systemEnabled);QVERIFY(!controller.proxyRequested());
        controller.shutdown();QTest::qWait(60);
        QCOMPARE(engine->stops,stoppedBefore+1);QCOMPARE(proxy->memory.enableCalls,1);
    }
    void shutdownReleaseFailureAndTimeoutStopOnceWithoutReacquiring(){
        for(const bool timeout:{false,true}) {
            QTemporaryDir dir;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
            auto backend=std::make_unique<WaitingPolicyProxyBackend>();auto *proxy=backend.get();proxy->ready=true;
            auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
            EngineController controller(std::move(peer),nullptr,dir.filePath("shutdown-failed-release.dpapi"),false,std::move(backend));
            controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY(!controller.policyBusy());
            controller.toggleSystemProxy();QTRY_VERIFY(controller.systemProxy()->owned());
            const auto stoppedBefore=engine->stops;
            QSignalSpy released(controller.systemProxy(),&SystemProxySession::releaseFinished);
            bool aliveAtRelease=false;
            connect(controller.systemProxy(),&SystemProxySession::releaseFinished,&controller,[&](bool){aliveAtRelease=controller.processAlive();});
            proxy->releaseReady=false;controller.shutdown();
            QVERIFY(controller.processAlive());QVERIFY(controller.systemProxyBusy());QCOMPARE(engine->stops,stoppedBefore);
            if(!timeout)proxy->releaseFails=true;
            QTRY_COMPARE_WITH_TIMEOUT(released.size(),1,4500);
            QVERIFY(!released.first().first().toBool());QVERIFY(aliveAtRelease);
            QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.systemProxyBusy(),1000);
            QCOMPARE(engine->stops,stoppedBefore+1);QVERIFY(!controller.systemProxy()->error().isEmpty());
            QVERIFY(controller.systemProxy()->owned());QCOMPARE(proxy->memory.restoreCalls,0);
            QVERIFY(!controller.proxyRequested());QTest::qWait(80);
            QCOMPARE(released.size(),1);QCOMPARE(engine->stops,stoppedBefore+1);QCOMPARE(proxy->memory.enableCalls,1);
        }
    }
    void shutdownWithoutOwnedProxyStopsOnceAndPreservesExternalProxy(){
        QTemporaryDir dir;auto backend=std::make_unique<WaitingPolicyProxyBackend>();auto *proxy=backend.get();
        auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("shutdown-unowned.dpapi"),false,std::move(backend));
        EngineStartOptions options;engine->start(options);QVERIFY(controller.processAlive());
        QSignalSpy released(controller.systemProxy(),&SystemProxySession::releaseFinished);
        controller.shutdown();controller.shutdown();
        QVERIFY(!controller.processAlive());QVERIFY(!controller.systemProxyBusy());QCOMPARE(engine->stops,1);
        QCOMPARE(released.size(),0);QCOMPARE(proxy->memory.disableCalls,0);QCOMPARE(proxy->memory.enableCalls,0);
        QVERIFY(proxy->memory.current().systemEnabled);
    }
    void unavailableListenerRollsBackTheMasterIntentAndStopsTheCore(){
        QTemporaryDir dir;QTcpServer reserved;QVERIFY(reserved.listen(QHostAddress::LocalHost));const auto port=reserved.serverPort();reserved.close();
        auto backend=std::make_unique<PolicySystemProxyBackend>();auto *proxy=backend.get();auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("unavailable.dpapi"),false,std::move(backend));
        controller.setProxyPort(port);QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        controller.toggleSystemProxy();QTRY_VERIFY_WITH_TIMEOUT(!controller.proxyRequested()&&!controller.processAlive(),3000);
        QCOMPARE(engine->starts,1);QVERIFY(engine->stops>0);QCOMPARE(proxy->enableCalls,0);QVERIFY(proxy->current().systemEnabled);QVERIFY(!controller.routingError().isEmpty());
    }
    void acquisitionFailureStopsTheCoreAndRestorationFailureRetainsItsRetry(){
        QTemporaryDir dir;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        auto backend=std::make_unique<FailingPolicyProxyBackend>();auto *proxy=backend.get();proxy->rejectEnable=true;
        auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("restore.dpapi"),false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        const auto original=controller.systemProxy()->diagnosticState();
        controller.toggleSystemProxy();QTRY_VERIFY_WITH_TIMEOUT(!controller.proxyRequested()&&!controller.processAlive(),3000);
        QCOMPARE(proxy->enableAttempts,1);QVERIFY(proxy->current().systemEnabled);QVERIFY(controller.routingError().contains(QStringLiteral("acquisition failure")));
        QCOMPARE(engine->starts,1);QCOMPARE(engine->stops,1);
        proxy->rejectEnable=false;controller.toggleSystemProxy();QTRY_VERIFY_WITH_TIMEOUT(controller.systemProxy()->owned(),3000);
        const auto stopsBefore=engine->stops;QCOMPARE(engine->starts,2);
        // A failed restore still owns the system proxy. Keeping its listener
        // alive is a stronger safety requirement than the former dead-core assertion.
        proxy->rejectRestore=true;controller.toggleSystemProxy();QVERIFY(!controller.proxyRequested());QVERIFY(controller.processAlive());
        QVERIFY(controller.systemProxy()->owned());QVERIFY(controller.systemProxy()->error().contains(QStringLiteral("restoration failure")));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.systemProxyBusy(),1000);QCOMPARE(engine->stops,stopsBefore);QCOMPARE(engine->starts,2);
        proxy->rejectRestore=false;controller.toggleSystemProxy();QVERIFY(!controller.systemProxy()->owned());QVERIFY(controller.systemProxy()->systemEnabled());QVERIFY(controller.systemProxy()->error().isEmpty());QCOMPARE(proxy->memory.restoreCalls,1);
        QTRY_VERIFY_WITH_TIMEOUT(!controller.processAlive()&&!controller.systemProxyBusy(),1000);QCOMPARE(engine->stops,stopsBefore+1);QCOMPARE(engine->starts,2);
        QCOMPARE(controller.systemProxy()->diagnosticState(),original);
    }
    void stoppingDuringADurablePolicyChangeClearsIntentBeforeDeferredShutdown(){
        QTemporaryDir dir;QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        auto backend=std::make_unique<PolicySystemProxyBackend>();auto *proxy=backend.get();auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,dir.filePath("stop-policy.dpapi"),false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        controller.toggleSystemProxy();QTRY_VERIFY_WITH_TIMEOUT(controller.systemProxy()->owned(),3000);
        bool deferred=false;engine->beforeActivate=[&]{controller.stop();deferred=controller.policyBusy()&&controller.processAlive()&&!controller.proxyRequested()&&!controller.systemProxy()->owned();};
        QVERIFY(controller.applyPolicyDocument(changedDocument().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy()&&!controller.processAlive(),5000);
        QVERIFY(deferred);QVERIFY(!controller.proxyRequested());QVERIFY(!controller.systemProxy()->owned());QVERIFY(proxy->current().systemEnabled);QCOMPARE(proxy->takeoverCalls,1);QCOMPARE(proxy->restoreCalls,1);
        QCOMPARE(controller.policyDocument(),changedDocument().toVariantMap());QVERIFY(controller.policyError().isEmpty());
    }
    void durablePolicyStopWaitsForProxyRelease(){
        QTemporaryDir dir;const auto path=dir.filePath("durable-policy-stop.dpapi");QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        auto backend=std::make_unique<WaitingPolicyProxyBackend>();auto *proxy=backend.get();proxy->ready=true;
        auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,path,false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        const auto original=controller.systemProxy()->diagnosticState();
        controller.toggleSystemProxy();QTRY_VERIFY_WITH_TIMEOUT(controller.systemProxy()->owned(),3000);
        const auto startsBefore=engine->starts,stopsBefore=engine->stops;
        QSignalSpy finished(&controller,&EngineController::policyApplyFinished);
        QSignalSpy released(controller.systemProxy(),&SystemProxySession::releaseFinished);
        bool deferred=false,aliveAtRelease=false;
        connect(controller.systemProxy(),&SystemProxySession::releaseFinished,&controller,[&](bool){aliveAtRelease=controller.processAlive();});
        bool completionReentryArmed=true,completionReentryObserved=false,completionKeptStopped=false;
        connect(&controller,&EngineController::policyApplyFinished,&controller,[&](const QString &,bool success){
            if(!success||!completionReentryArmed)return;
            completionReentryArmed=false;completionReentryObserved=true;
            controller.setSystemProxy(true);
            completionKeptStopped=!controller.proxyRequested()&&!controller.processAlive()&&engine->starts==startsBefore;
        });
        engine->beforeActivate=[&]{
            proxy->releaseReady=false;controller.stop();
            deferred=controller.policyBusy()&&controller.processAlive()&&!controller.proxyRequested()&&controller.systemProxy()->owned();
        };
        QVERIFY(controller.applyPolicyDocument(changedDocument().toVariantMap()));const auto request=controller.policyRequestId();
        QTRY_VERIFY_WITH_TIMEOUT(controller.m_policyWaitingForStop,5000);
        QVERIFY(deferred);QVERIFY(controller.policyBusy());QVERIFY(controller.processAlive());QVERIFY(controller.apiHealthy());QVERIFY(engine->gate);
        QVERIFY(controller.systemProxy()->owned());QVERIFY(controller.systemProxy()->busy());QVERIFY(controller.systemProxyBusy());
        QCOMPARE(engine->stops,stopsBefore);QCOMPARE(engine->starts,startsBefore);QCOMPARE(released.size(),0);QCOMPARE(finished.size(),0);
        const auto committedWhileWaiting=envelope(path);QVERIFY(!committedWhileWaiting.contains("pending"));
        QCOMPARE(committedWhileWaiting.value("committed").toObject().value("request_id").toString(),request);
        QCOMPARE(engine->current.configurationReceipt.value("applied_revision").toString(),controller.savedRevision());
        controller.stop();QTest::qWait(80);
        QVERIFY(controller.m_policyWaitingForStop);QVERIFY(controller.processAlive());QVERIFY(engine->gate);QCOMPARE(engine->stops,stopsBefore);
        QCOMPARE(engine->starts,startsBefore);QCOMPARE(proxy->memory.restoreCalls,0);QCOMPARE(finished.size(),0);
        proxy->releaseReady=true;
        QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy()&&!controller.processAlive()&&!controller.systemProxyBusy(),5000);
        QCOMPARE(released.size(),1);QVERIFY(released.first().first().toBool());QVERIFY(aliveAtRelease);
        QCOMPARE(finished.size(),1);QCOMPARE(finished.first().first().toString(),request);QVERIFY(finished.first().at(1).toBool());
        QVERIFY(completionReentryObserved);QVERIFY(completionKeptStopped);
        QVERIFY(!controller.m_policyWaitingForStop);QVERIFY(!controller.systemProxy()->owned());QVERIFY(!controller.proxyRequested());QVERIFY(!engine->gate);
        QCOMPARE(engine->stops,stopsBefore+1);QCOMPARE(engine->starts,startsBefore);QCOMPARE(proxy->memory.enableCalls,1);QCOMPARE(proxy->memory.restoreCalls,1);
        QCOMPARE(controller.systemProxy()->diagnosticState(),original);QCOMPARE(controller.policyDocument(),changedDocument().toVariantMap());
        QCOMPARE(controller.savedRevision(),QString("2"));QVERIFY(controller.policyError().isEmpty());
        const auto stored=envelope(path);QCOMPARE(stored,committedWhileWaiting);
        const auto committed=stored.value("committed").toObject();
        QCOMPARE(committed.value("snapshot").toObject().value("networkConfiguration").toObject().value("policyDocumentV2").toObject(),changedDocument());
        auto expectedReceipt=committed;expectedReceipt.remove("snapshot");expectedReceipt.insert("store_id",stored.value("store_id"));
        QCOMPARE(controller.m_store.configurationReceipt(),expectedReceipt);expectedReceipt.insert("scope","saved-next-connect");
        QCOMPARE(controller.policyReceipt(),expectedReceipt.toVariantMap());
        QTest::qWait(80);QCOMPARE(engine->stops,stopsBefore+1);QCOMPARE(engine->starts,startsBefore);QCOMPARE(finished.size(),1);
    }
    void durablePolicyStopTimeoutKeepsTheOwnedListenerAndTransactionRetryable(){
        QTemporaryDir dir;const auto path=dir.filePath("durable-policy-stop-timeout.dpapi");QTcpServer listener;QVERIFY(listener.listen(QHostAddress::LocalHost));
        auto backend=std::make_unique<WaitingPolicyProxyBackend>();auto *proxy=backend.get();proxy->ready=true;
        auto peer=std::make_unique<ConfigurationPeer>();auto *engine=peer.get();
        EngineController controller(std::move(peer),nullptr,path,false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        const auto original=controller.systemProxy()->diagnosticState();
        controller.toggleSystemProxy();QTRY_VERIFY_WITH_TIMEOUT(controller.systemProxy()->owned(),3000);
        const auto startsBefore=engine->starts,stopsBefore=engine->stops;
        QSignalSpy finished(&controller,&EngineController::policyApplyFinished);
        QSignalSpy released(controller.systemProxy(),&SystemProxySession::releaseFinished);
        QElapsedTimer releaseElapsed;QList<bool> aliveAtRelease;QStringList errorsAtRelease;bool deferred=false;
        connect(controller.systemProxy(),&SystemProxySession::releaseFinished,&controller,[&](bool){
            aliveAtRelease.append(controller.processAlive());errorsAtRelease.append(controller.systemProxy()->error());
        });
        engine->beforeActivate=[&]{
            proxy->releaseReady=false;releaseElapsed.start();controller.stop();
            deferred=controller.policyBusy()&&controller.processAlive()&&!controller.proxyRequested()&&controller.systemProxy()->owned();
        };
        QVERIFY(controller.applyPolicyDocument(changedDocument().toVariantMap()));const auto request=controller.policyRequestId();
        QTRY_VERIFY_WITH_TIMEOUT(controller.m_policyWaitingForStop,5000);
        QVERIFY(deferred);QVERIFY(controller.policyBusy());QVERIFY(controller.processAlive());QVERIFY(engine->gate);
        QVERIFY(controller.systemProxy()->owned());QVERIFY(controller.systemProxy()->busy());QVERIFY(controller.systemProxyBusy());
        QCOMPARE(engine->stops,stopsBefore);QCOMPARE(engine->starts,startsBefore);QCOMPARE(released.size(),0);
        const auto committedWhileWaiting=envelope(path);QVERIFY(!committedWhileWaiting.contains("pending"));
        QCOMPARE(committedWhileWaiting.value("committed").toObject().value("request_id").toString(),request);
        // Keep the actual release pending until its production deadline. The
        // durable transaction must retain its admission gate and live listener.
        QTRY_COMPARE_WITH_TIMEOUT(released.size(),1,4500);
        QVERIFY2(releaseElapsed.elapsed()>=2000,"The durable-policy release did not reach the real two-second deadline.");
        QVERIFY(!released.first().first().toBool());QCOMPARE(aliveAtRelease.size(),1);QVERIFY(aliveAtRelease.first());
        QVERIFY(errorsAtRelease.first().contains(QStringLiteral("可重试释放代理")));
        QTRY_VERIFY_WITH_TIMEOUT(!controller.systemProxyStopping()&&!controller.systemProxyBusy(),1000);
        QVERIFY(controller.policyBusy());QVERIFY(controller.m_policyWaitingForStop);QVERIFY(engine->gate);
        QVERIFY(controller.processAlive());QVERIFY(controller.apiHealthy());QVERIFY(controller.systemProxy()->owned());QVERIFY(!controller.proxyRequested());
        QVERIFY(!controller.routingError().isEmpty());QCOMPARE(finished.size(),0);QCOMPARE(engine->stops,stopsBefore);QCOMPARE(engine->starts,startsBefore);
        QCOMPARE(proxy->memory.restoreCalls,0);QCOMPARE(proxy->memory.enableCalls,1);QCOMPARE(envelope(path),committedWhileWaiting);
        QTest::qWait(80);QVERIFY(controller.processAlive());QVERIFY(controller.m_policyWaitingForStop);QVERIFY(engine->gate);
        QVERIFY(!controller.systemProxyStopping());QVERIFY(!controller.systemProxyBusy());QCOMPARE(released.size(),1);QCOMPARE(engine->stops,stopsBefore);
        proxy->releaseReady=true;controller.toggleSystemProxy();
        QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy()&&!controller.processAlive()&&!controller.systemProxyBusy(),5000);
        QCOMPARE(released.size(),2);QVERIFY(released.last().first().toBool());QCOMPARE(aliveAtRelease.size(),2);QVERIFY(aliveAtRelease.last());
        QCOMPARE(finished.size(),1);QCOMPARE(finished.first().first().toString(),request);QVERIFY(finished.first().at(1).toBool());
        QVERIFY(!controller.m_policyWaitingForStop);QVERIFY(!controller.systemProxyStopping());QVERIFY(!controller.systemProxy()->owned());
        QVERIFY(!controller.proxyRequested());QVERIFY(!engine->gate);QVERIFY(controller.routingError().isEmpty());QVERIFY(controller.policyError().isEmpty());
        QCOMPARE(engine->stops,stopsBefore+1);QCOMPARE(engine->starts,startsBefore);QCOMPARE(proxy->memory.enableCalls,1);QCOMPARE(proxy->memory.restoreCalls,1);
        QCOMPARE(controller.systemProxy()->diagnosticState(),original);QCOMPARE(controller.policyDocument(),changedDocument().toVariantMap());
        QCOMPARE(controller.savedRevision(),QString("2"));const auto stored=envelope(path);QCOMPARE(stored,committedWhileWaiting);
        const auto committed=stored.value("committed").toObject();
        QCOMPARE(committed.value("snapshot").toObject().value("networkConfiguration").toObject().value("policyDocumentV2").toObject(),changedDocument());
        auto expectedReceipt=committed;expectedReceipt.remove("snapshot");expectedReceipt.insert("store_id",stored.value("store_id"));
        QCOMPARE(controller.m_store.configurationReceipt(),expectedReceipt);expectedReceipt.insert("scope","saved-next-connect");
        QCOMPARE(controller.policyReceipt(),expectedReceipt.toVariantMap());
        QTest::qWait(80);QCOMPARE(engine->stops,stopsBefore+1);QCOMPARE(engine->starts,startsBefore);QCOMPARE(finished.size(),1);
    }
};
QTEST_GUILESS_MAIN(PolicyConfigurationTests)
#include "PolicyConfigurationTests.moc"
