#include "engine/EngineController.h"
#include "engine/RustCoreEngine.h"
#include "PolicySystemProxyBackend.h"
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QSettings>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTcpServer>
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
        QTemporaryDir dir;QTcpServer reserved;QVERIFY(reserved.listen(QHostAddress::LocalHost));const auto port=reserved.serverPort();
        auto backend=std::make_unique<PolicySystemProxyBackend>();auto *proxy=backend.get();
        EngineController controller(std::make_unique<RustCoreEngine>(),nullptr,dir.filePath("master.dpapi"),false,std::move(backend));
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
        EngineController controller(std::make_unique<ConfigurationPeer>(),nullptr,dir.filePath("restore.dpapi"),false,std::move(backend));
        controller.setProxyPort(listener.serverPort());QVERIFY(controller.applyPolicyDocument(document().toVariantMap()));QTRY_VERIFY_WITH_TIMEOUT(!controller.policyBusy(),5000);
        controller.toggleSystemProxy();QTRY_VERIFY_WITH_TIMEOUT(!controller.proxyRequested()&&!controller.processAlive(),3000);
        QCOMPARE(proxy->enableAttempts,1);QVERIFY(proxy->current().systemEnabled);QVERIFY(controller.routingError().contains(QStringLiteral("acquisition failure")));
        proxy->rejectEnable=false;controller.toggleSystemProxy();QTRY_VERIFY_WITH_TIMEOUT(controller.systemProxy()->owned(),3000);
        proxy->rejectRestore=true;controller.toggleSystemProxy();QVERIFY(!controller.proxyRequested());QVERIFY(!controller.processAlive());
        QVERIFY(controller.systemProxy()->owned());QVERIFY(controller.systemProxy()->error().contains(QStringLiteral("restoration failure")));
        proxy->rejectRestore=false;controller.toggleSystemProxy();QVERIFY(!controller.systemProxy()->owned());QVERIFY(controller.systemProxy()->systemEnabled());QVERIFY(controller.systemProxy()->error().isEmpty());QCOMPARE(proxy->memory.restoreCalls,1);
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
};
QTEST_GUILESS_MAIN(PolicyConfigurationTests)
#include "PolicyConfigurationTests.moc"
