#include "engine/NodeStore.h"
#include "engine/NodeImportService.h"
#include "engine/XrayJsonBridge.h"
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QPointer>
#include <QSaveFile>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QTcpServer>
#include <QTcpSocket>
#include <QTest>
#include <QThread>
#include <QUuid>
#include <functional>
#include <memory>
#include <utility>
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif

namespace {
const QString requestOne=QStringLiteral("11111111-1111-4111-8111-000000000001");
const QString requestTwo=QStringLiteral("11111111-1111-4111-8111-000000000002");
const QString requestThree=QStringLiteral("11111111-1111-4111-8111-000000000003");
const QString digestOne(64,QLatin1Char('a')),digestTwo(64,QLatin1Char('b')),digestThree(64,QLatin1Char('c'));
QVariantMap editorInput(const QString &name) {return {{"name",name},{"protocol","socks5"},{"host","127.0.0.1"},{"port",9},{"username","synthetic-catalog-user"},{"password","SYNTHETIC-CATALOG-TRANSACTION-SECRET"}};}
QByteArray readFile(const QString &path) {QFile file(path);return file.open(QIODevice::ReadOnly)?file.readAll():QByteArray{};}
QJsonObject network(const QString &selected={},const QString &mode=QStringLiteral("rule")) {
    const QJsonObject target=selected.isEmpty()?QJsonObject{{"kind","unconfigured"}}:QJsonObject{{"kind","node"},{"id",selected}};
    const QJsonObject policy{{"schema",2},{"mode",mode},{"default_policy",QJsonObject{{"id","policy:default"},{"target",target}}},
        {"service_policies",QJsonArray{}},{"groups",QJsonArray{}},{"explicit_direct_rules",QJsonArray{}},{"custom_rules",QJsonArray{}},{"missing_targets",QJsonArray{}},{"classification_dns","disabled"}};
    return {{"schema",1},{"policyDocumentV2",policy}};
}
QJsonObject markRemoved(QJsonObject next,const QStringList &ids) {
    auto policy=next.value("policyDocumentV2").toObject();auto missing=policy.value("missing_targets").toArray();
    for(const auto &id:ids)missing.append(QJsonObject{{"kind","node"},{"id",id},{"safe_label","Removed synthetic fixture"},{"reason","deleted_target"}});
    policy.insert("missing_targets",missing);next.insert("policyDocumentV2",policy);return next;
}
struct WriteOutcome {bool accepted=false,completed=false,success=false,ownerThread=false,savingAtCompletion=false;QString error;explicit operator bool() const {return accepted&&completed&&success&&ownerThread;}};
WriteOutcome perform(NodeStore &store,const std::function<bool(NodeStore::SaveCompletion)> &start) {
    auto result=std::make_shared<WriteOutcome>();const auto expected=store.thread();const QPointer<NodeStore> owner(&store);
    result->accepted=start([result,owner,expected](bool ok,const QString &error){result->completed=true;result->success=ok;result->error=error;result->ownerThread=QThread::currentThread()==expected;result->savingAtCompletion=owner&&owner->saving();});
    if(result->accepted&&!QTest::qWaitFor([result]{return result->completed;},10000))result->error=QStringLiteral("Atomic write completion timed out");
    return *result;
}
bool migrate(NodeStore &store,const QJsonObject &configuration) {
    const auto revision=store.issueConfigurationRevision();
    return bool(perform(store,[&](auto callback){return store.saveConfigurationOffline(configuration,requestOne,revision,digestOne,std::move(callback));}));
}
QJsonObject decryptSnapshot(const QString &path) {
#ifdef Q_OS_WIN
    const auto bytes=readFile(path);if(!bytes.startsWith("SWIRLNODE2\n"))return {};
    const auto encrypted=bytes.mid(11);const QByteArray context("Swirl.NodeStore.v1");
    DATA_BLOB input{DWORD(encrypted.size()),reinterpret_cast<BYTE *>(const_cast<char *>(encrypted.constData()))},output{};
    DATA_BLOB entropy{DWORD(context.size()),reinterpret_cast<BYTE *>(const_cast<char *>(context.constData()))};
    if(!CryptUnprotectData(&input,nullptr,&entropy,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&output))return {};
    QByteArray plaintext(reinterpret_cast<char *>(output.pbData),output.cbData);SecureZeroMemory(output.pbData,output.cbData);LocalFree(output.pbData);
    const auto snapshot=QJsonDocument::fromJson(plaintext).object();plaintext.fill('\0');return snapshot;
#else
    Q_UNUSED(path);return {};
#endif
}
bool encryptFixture(const QString &path,const QJsonObject &snapshot) {
#ifdef Q_OS_WIN
    auto plaintext=QJsonDocument(snapshot).toJson(QJsonDocument::Compact);const QByteArray context("Swirl.NodeStore.v1");
    DATA_BLOB input{DWORD(plaintext.size()),reinterpret_cast<BYTE *>(plaintext.data())},output{};
    DATA_BLOB entropy{DWORD(context.size()),reinterpret_cast<BYTE *>(const_cast<char *>(context.constData()))};
    const bool protectedOk=CryptProtectData(&input,L"Swirl catalog malformed fixture",&entropy,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&output);plaintext.fill('\0');if(!protectedOk)return false;
    QByteArray encrypted(reinterpret_cast<char *>(output.pbData),output.cbData);SecureZeroMemory(output.pbData,output.cbData);LocalFree(output.pbData);const auto bytes=QByteArrayLiteral("SWIRLNODE2\n")+encrypted;encrypted.fill('\0');
    QSaveFile file(path);file.setDirectWriteFallback(false);return file.open(QIODevice::WriteOnly)&&file.write(bytes)==bytes.size()&&file.commit();
#else
    Q_UNUSED(path);Q_UNUSED(snapshot);return false;
#endif
}
QByteArray sharedXrayDocument() {
    QJsonArray outbounds;
    for(int i=0;i<2;++i)outbounds.append(QJsonObject{{"tag",QString("shared-fixture-%1").arg(i)},{"protocol","http"},
        {"settings",QJsonObject{{"servers",QJsonArray{QJsonObject{{"address","fixture.example.invalid"},{"port",8080+i},
            {"users",QJsonArray{QJsonObject{{"user","synthetic-shared-user"},{"pass",QString("SYNTHETIC-SHARED-SECRET-%1").arg(i)}}}}}}}}}});
    return QJsonDocument(QJsonObject{{"outbounds",outbounds}}).toJson(QJsonDocument::Compact);
}
QByteArray sharedAccountDocument() {
    return QByteArrayLiteral(R"({"outbounds":[{"tag":"shared-accounts","protocol":"http","settings":{"servers":[{"address":"fixture.example.invalid","port":8080,"users":[{"user":"synthetic-first-user","pass":"SYNTHETIC-FIRST-ACCOUNT-SECRET"},{"user":"synthetic-second-user","pass":"SYNTHETIC-SECOND-ACCOUNT-SECRET"}]}]}}]})");
}
}

class CatalogTransactionTests final:public QObject {
    Q_OBJECT
private slots:
    void initTestCase() {
#ifndef Q_OS_WIN
        QSKIP("Real current-user DPAPI and Windows file-lock coverage requires Windows");
#endif
    }
    void v1MigrationProducesOneEncryptedCommittedAuthority() {
        QTemporaryDir temporary;QVERIFY(temporary.isValid());const auto path=temporary.filePath("catalog.dpapi");QString id,storeId;
        {
            NodeStore store(path);QVERIFY(store.saveNode(editorInput("migration fixture")));id=store.nodes().first().id;QVERIFY(store.select(id));
            const auto old=readFile(path);QVERIFY(old.startsWith("SWIRLNODE1\n"));const auto next=network(id);const auto issued=store.issueConfigurationRevision();
            const auto written=perform(store,[&](auto callback){return store.saveConfigurationOffline(next,requestOne,issued,digestOne,std::move(callback));});
            QVERIFY2(bool(written),qPrintable(written.error));QVERIFY(!written.savingAtCompletion);QVERIFY(!store.saving());QVERIFY(store.configurationV2());
            QCOMPARE(store.configurationRevision(),QString("1"));QCOMPARE(store.selectedId(),id);QVERIFY(store.networkConfiguration()==next);storeId=store.configurationStoreId();QVERIFY(!QUuid(storeId).isNull());
            const auto bytes=readFile(path);QVERIFY(bytes.startsWith("SWIRLNODE2\n"));QVERIFY(!bytes.contains("SYNTHETIC-CATALOG-TRANSACTION-SECRET"));
            const auto envelope=decryptSnapshot(path);QCOMPARE(envelope.value("schema").toInt(),2);QVERIFY(envelope.value("pending").isUndefined());
            const auto committed=envelope.value("committed").toObject();QCOMPARE(committed.value("saved_revision").toString(),issued);QCOMPARE(committed.value("request_id").toString(),requestOne);QCOMPARE(committed.value("plan_digest").toString(),digestOne);
        }
        NodeStore loaded(path);QVERIFY2(loaded.error().isEmpty(),qPrintable(loaded.error()));QCOMPARE(loaded.configurationStoreId(),storeId);QCOMPARE(loaded.configurationRevision(),QString("1"));QCOMPARE(loaded.selectedId(),id);QCOMPARE(loaded.nodes().size(),1);
    }
    void legacyCatalogWritersCannotBypassV2Receipts() {
        QTemporaryDir temporary;NodeStore store(temporary.filePath("catalog.dpapi"));QVERIFY(store.saveNode(editorInput("retained fixture")));
        QVERIFY(store.saveSubscription({},"source fixture",QUrl("https://source.fixture.invalid/list"),60,true,"auto","nodes-only"));const auto source=store.subscriptions().first().id,id=store.nodes().first().id;
        QVERIFY(migrate(store,network(id)));const auto before=readFile(store.filePath());
        QVERIFY(!store.saveNode(editorInput("forbidden direct write")));QVERIFY(!store.removeNode(id));QVERIFY(!store.select({}));
        QVERIFY(!store.saveSubscription({},"second source",QUrl("https://other.fixture.invalid/list"),60,true));QVERIFY(!store.removeSubscription(source));QVERIFY(!store.saveNetworkConfiguration(network()));
        NodeStore::ImportPlan plan;QVERIFY(store.prepareSaveNode(editorInput("candidate"),&plan));QVERIFY(!store.commitImport(plan));
        bool called=false;QVERIFY(!store.commitImportAsync(plan,network(id),[&](bool,const QString &){called=true;}));QCoreApplication::processEvents();QVERIFY(!called);
        QVERIFY(readFile(store.filePath())==before);QCOMPARE(store.nodes().size(),1);QCOMPARE(store.subscriptions().size(),1);QCOMPARE(store.configurationRevision(),QString("1"));
    }
    void changedReceiverMayDestroyTheStoreWithoutALateCompletion() {
        QTemporaryDir temporary;QVERIFY(temporary.isValid());const auto path=temporary.filePath("catalog.dpapi");auto store=std::make_unique<NodeStore>(path);QVERIFY(store->saveNode(editorInput("destroy-on-adopt fixture")));const auto revision=store->issueConfigurationRevision();const QPointer<NodeStore> guard(store.get());bool completed=false;
        connect(store.get(),&NodeStore::changed,this,[&store]{store.reset();},Qt::DirectConnection);
        QVERIFY(store->saveConfigurationOffline(network(),requestOne,revision,digestOne,[&](bool,const QString &){completed=true;}));
        QVERIFY(QTest::qWaitFor([&]{return guard.isNull();},10000));QTest::qWait(50);QVERIFY(!store);QVERIFY(!completed);
        NodeStore reloaded(path);QVERIFY2(reloaded.error().isEmpty(),qPrintable(reloaded.error()));QVERIFY(reloaded.configurationV2());QCOMPARE(reloaded.configurationRevision(),revision);QCOMPARE(reloaded.nodes().size(),1);
    }
    void catalogIntentKeepsOldCommitUntilFinalAtomicWrite() {
        QTemporaryDir temporary;NodeStore store(temporary.filePath("catalog.dpapi"));QVERIFY(store.saveNode(editorInput("old manual fixture")));
        QVERIFY(store.saveSubscription({},"source fixture",QUrl("https://source.fixture.invalid/list"),60,true,"auto","nodes-only"));const auto source=store.subscriptions().first().id,id=store.nodes().first().id;const auto oldNetwork=network(id);QVERIFY(migrate(store,oldNetwork));
        ProxyNode incoming;incoming.id=QStringLiteral("22222222-2222-4222-8222-222222222222");incoming.name="imported fixture";incoming.protocol="socks5";incoming.host="127.0.0.1";incoming.port=10;incoming.importSource="subscription";
        NodeStore::ImportPlan plan;QVERIFY(store.prepareImport({incoming},source,&plan));const auto next=network(id,"global");const auto revision=store.issueConfigurationRevision();
        const auto begun=perform(store,[&](auto callback){return store.beginCatalogIntent(plan,next,requestTwo,revision,digestTwo,std::move(callback));});
        QVERIFY2(bool(begun),qPrintable(begun.error));QVERIFY(begun.savingAtCompletion);QVERIFY(store.saving());QCOMPARE(store.nodes().size(),1);QCOMPARE(store.subscriptions().first().lastSuccess,qint64(0));QVERIFY(store.networkConfiguration()==oldNetwork);QCOMPARE(store.configurationRevision(),QString("1"));
        const auto pending=store.pendingConfigurationReceipt();QCOMPARE(pending.value("operation").toString(),QString("catalogue"));QCOMPARE(pending.value("candidate_revision").toString(),revision);QVERIFY(!pending.contains("catalog_snapshot"));QVERIFY(!pending.contains("network_configuration"));
        const auto committed=perform(store,[&](auto callback){return store.commitConfigurationIntent(std::move(callback));});QVERIFY2(bool(committed),qPrintable(committed.error));QVERIFY(committed.savingAtCompletion);QVERIFY(store.saving());
        QCOMPARE(store.nodes().size(),2);QVERIFY(store.subscriptions().first().lastSuccess>0);QVERIFY(store.networkConfiguration()==next);QCOMPARE(store.configurationRevision(),revision);QVERIFY(store.pendingConfigurationReceipt().isEmpty());
        store.releaseConfigurationLease();QVERIFY(!store.saving());
    }
    void stalePreparedCatalogCannotReplaceNewerCommit() {
        QTemporaryDir temporary;NodeStore store(temporary.filePath("catalog.dpapi"));QVERIFY(store.saveNode(editorInput("base fixture")));QVERIFY(migrate(store,network()));
        NodeStore::ImportPlan stale,current;QVERIFY(store.prepareSaveNode(editorInput("stale fixture"),&stale));QVERIFY(store.prepareSaveNode(editorInput("new fixture"),&current));
        const auto revision=store.issueConfigurationRevision();QVERIFY(bool(perform(store,[&](auto callback){return store.saveCatalogOffline(current,network(),requestTwo,revision,digestTwo,std::move(callback));})));const auto bytes=readFile(store.filePath());
        const auto next=store.issueConfigurationRevision();const auto refused=perform(store,[&](auto callback){return store.saveCatalogOffline(stale,network(),requestThree,next,digestThree,std::move(callback));});QVERIFY(!refused.accepted);QVERIFY(!refused.completed);
        QVERIFY(readFile(store.filePath())==bytes);QCOMPARE(store.configurationRevision(),revision);QCOMPARE(store.nodes().last().name,QString("new fixture"));
    }
    void finalWriteFailureRetainsIntentAndCommittedCatalogUntilExplicitAbort() {
        QTemporaryDir temporary;QVERIFY(temporary.isValid());const auto path=temporary.filePath("catalog.dpapi"),held=temporary.filePath("held-intent.dpapi");NodeStore store(path);QVERIFY(store.saveNode(editorInput("retained fixture")));QVERIFY(migrate(store,network()));
        NodeStore::ImportPlan plan;QVERIFY(store.prepareSaveNode(editorInput("candidate fixture"),&plan));const auto revision=store.issueConfigurationRevision();QVERIFY(bool(perform(store,[&](auto callback){return store.beginCatalogIntent(plan,network(),requestTwo,revision,digestTwo,std::move(callback));})));
        const auto durableIntent=readFile(path);QVERIFY(QFile::rename(path,held));QVERIFY(QDir().mkdir(path));
        const auto failed=perform(store,[&](auto callback){return store.commitConfigurationIntent(std::move(callback));});QVERIFY(failed.accepted);QVERIFY(failed.completed);QVERIFY(!failed.success);QVERIFY(failed.ownerThread);QVERIFY(failed.savingAtCompletion);QVERIFY(!failed.error.isEmpty());
        QCOMPARE(store.configurationRevision(),QString("1"));QCOMPARE(store.nodes().size(),1);QCOMPARE(store.nodes().first().name,QString("retained fixture"));QCOMPARE(store.pendingConfigurationReceipt().value("candidate_revision").toString(),revision);QVERIFY(readFile(held)==durableIntent);
        QVERIFY(QDir().rmdir(path));QVERIFY(QFile::rename(held,path));QVERIFY(bool(perform(store,[&](auto callback){return store.abortConfigurationIntent(std::move(callback));})));store.releaseConfigurationLease();QVERIFY(!store.saving());QVERIFY(store.pendingConfigurationReceipt().isEmpty());QCOMPARE(store.nodes().size(),1);QCOMPARE(store.configurationRevision(),QString("1"));
    }
    void subscriptionAndLegacyPlansCommitThroughTheSameCatalogLease() {
        QTemporaryDir temporary;NodeStore store(temporary.filePath("catalog.dpapi"));ProxyNode legacy;legacy.id=QStringLiteral("33333333-3333-4333-8333-333333333333");legacy.name="legacy fixture";legacy.protocol="http";legacy.host="127.0.0.1";legacy.port=9;legacy.importSource="legacy";QVERIFY(store.importNodes({legacy}));QVERIFY(migrate(store,network()));
        NodeStore::ImportPlan source;QVERIFY(store.prepareSaveSubscription({},"prepared source",QUrl("https://source.fixture.invalid/list"),60,true,"auto","nodes-only",&source));const auto revision=store.issueConfigurationRevision();
        QVERIFY(bool(perform(store,[&](auto callback){return store.saveCatalogOffline(source,source.retainedNetworkConfiguration(),requestTwo,revision,digestTwo,std::move(callback));})));QCOMPARE(store.subscriptions().size(),1);QCOMPARE(store.subscriptions().first().name,QString("prepared source"));QCOMPARE(store.legacyNodeCount(),1);
        NodeStore::ImportPlan clean;QVERIFY(store.prepareCleanLegacyNodes(&clean));QCOMPARE(clean.removedNodeIds(),QStringList{legacy.id});const auto next=store.issueConfigurationRevision();
        QVERIFY(bool(perform(store,[&](auto callback){return store.saveCatalogOffline(clean,markRemoved(clean.retainedNetworkConfiguration(),clean.removedNodeIds()),requestThree,next,digestThree,std::move(callback));})));QVERIFY(store.nodes().isEmpty());QCOMPARE(store.subscriptions().size(),1);
    }
    void revocationCrashRequiresMatchingOfflineRecoveryAndPreservesHighWater() {
        QTemporaryDir temporary;const auto path=temporary.filePath("catalog.dpapi");QString removed,revision;
        {
            NodeStore store(path);QVERIFY(store.saveNode(editorInput("revoked fixture")));removed=store.nodes().first().id;QVERIFY(migrate(store,network(removed)));
            NodeStore::ImportPlan plan;QVERIFY(store.prepareRemoveNode(removed,&plan));QCOMPARE(plan.removedNodeIds(),QStringList{removed});revision=store.issueConfigurationRevision();const auto candidate=markRemoved(plan.retainedNetworkConfiguration(),plan.removedNodeIds());
            QVERIFY(bool(perform(store,[&](auto callback){return store.beginCatalogIntent(plan,candidate,requestTwo,revision,digestTwo,std::move(callback));})));QCOMPARE(store.nodes().size(),1);QCOMPARE(store.configurationRevision(),QString("1"));
            // Destroy only after the actual atomic intent write callback. No
            // runtime is started, so this simulates process loss at a known boundary.
        }
        NodeStore recovered(path);QVERIFY(recovered.configurationRecoveryRequired());QCOMPARE(recovered.pendingConfigurationReceipt().value("operation").toString(),QString("revoke"));QCOMPARE(recovered.configurationRevision(),QString("1"));
        const auto bytes=readFile(path);const auto refused=perform(recovered,[&](auto callback){return recovered.recoverCatalogIntentOffline(digestThree,std::move(callback));});QVERIFY(!refused.accepted);QVERIFY(!refused.completed);QVERIFY(readFile(path)==bytes);QVERIFY(recovered.configurationRecoveryRequired());
        NodeStore::ImportPlan candidate;QJsonObject configuration;QVERIFY(recovered.configurationRecoveryPlan(&candidate,&configuration));QVERIFY(candidate.nodes().isEmpty());QCOMPARE(candidate.removedNodeIds(),QStringList{removed});
        const auto written=perform(recovered,[&](auto callback){return recovered.recoverCatalogIntentOffline(digestTwo,std::move(callback));});QVERIFY2(bool(written),qPrintable(written.error));QVERIFY(!recovered.configurationRecoveryRequired());QVERIFY(!recovered.saving());QVERIFY(recovered.nodes().isEmpty());QVERIFY(recovered.selectedId().isEmpty());QVERIFY(recovered.pendingConfigurationReceipt().isEmpty());QCOMPARE(recovered.configurationRevision(),revision);QCOMPARE(recovered.configurationReceipt().value("request_id").toString(),requestTwo);QVERIFY(recovered.issueConfigurationRevision().toULongLong()>revision.toULongLong());
    }
    void pathLockRefusesASecondV2WriterWithoutChangingCiphertext() {
        QTemporaryDir temporary;const auto path=temporary.filePath("catalog.dpapi");NodeStore owner(path);QVERIFY(owner.saveNode(editorInput("owner fixture")));QVERIFY(migrate(owner,network()));const auto before=readFile(path);
        NodeStore second(path);QVERIFY(!second.error().isEmpty());const auto revision=second.issueConfigurationRevision();const auto refused=perform(second,[&](auto callback){return second.saveConfigurationOffline(network(),requestTwo,revision,digestTwo,std::move(callback));});QVERIFY(!refused.accepted);QVERIFY(!refused.completed);QVERIFY(readFile(path)==before);QVERIFY(!owner.saving());
    }
    void staleLegacyReaderCannotMigrateOverANewerWriter() {
        QTemporaryDir temporary;QVERIFY(temporary.isValid());const auto path=temporary.filePath("catalog.dpapi");
        {NodeStore initial(path);QVERIFY(initial.saveNode(editorInput("initial fixture")));}
        NodeStore stale(path);QCOMPARE(stale.nodes().size(),1);
        {NodeStore writer(path);QVERIFY(writer.saveNode(editorInput("newer fixture")));QCOMPARE(writer.nodes().size(),2);}
        const auto before=readFile(path);const auto revision=stale.issueConfigurationRevision();const auto refused=perform(stale,[&](auto callback){return stale.saveConfigurationOffline(network(),requestOne,revision,digestOne,std::move(callback));});QVERIFY(!refused.accepted);QVERIFY(!refused.completed);QVERIFY(!stale.error().isEmpty());QVERIFY(readFile(path)==before);
        NodeStore reloaded(path);QVERIFY2(reloaded.error().isEmpty(),qPrintable(reloaded.error()));QCOMPARE(reloaded.nodes().size(),2);QVERIFY(!reloaded.configurationV2());
    }
    void malformedPendingCatalogNeverReplaysOrCleansItself_data() {
        QTest::addColumn<QString>("fault");
        for(const auto &fault:QStringList{"catalogue_with_removal","revoke_empty","revoke_duplicate","revoke_nonstring","revoke_wrong_uuid","bad_snapshot_schema","network_mismatch","nested_documents","bad_base_revision","bad_candidate_revision","bad_digest","unknown_operation"})QTest::newRow(qPrintable(fault))<<fault;
    }
    void malformedPendingCatalogNeverReplaysOrCleansItself() {
        QFETCH(QString,fault);QTemporaryDir temporary;QVERIFY(temporary.isValid());const auto path=temporary.filePath("catalog.dpapi");
        {
            NodeStore store(path);QVERIFY(store.saveNode(editorInput("pending validation fixture")));const auto id=store.nodes().first().id;QVERIFY(migrate(store,network(id)));NodeStore::ImportPlan removal;QVERIFY(store.prepareRemoveNode(id,&removal));const auto revision=store.issueConfigurationRevision();
            QVERIFY(bool(perform(store,[&](auto callback){return store.beginCatalogIntent(removal,markRemoved(removal.retainedNetworkConfiguration(),removal.removedNodeIds()),requestTwo,revision,digestTwo,std::move(callback));})));
        }
        auto envelope=decryptSnapshot(path),pending=envelope.value("pending").toObject(),snapshot=pending.value("catalog_snapshot").toObject();QVERIFY(!pending.isEmpty());
        if(fault=="catalogue_with_removal")pending.insert("operation","catalogue");
        else if(fault=="revoke_empty")pending.insert("revoked_node_ids",QJsonArray{});
        else if(fault=="revoke_duplicate"){auto ids=pending.value("revoked_node_ids").toArray();ids.append(ids.first());pending.insert("revoked_node_ids",ids);}
        else if(fault=="revoke_nonstring")pending.insert("revoked_node_ids",QJsonArray{7});
        else if(fault=="revoke_wrong_uuid")pending.insert("revoked_node_ids",QJsonArray{requestThree});
        else if(fault=="bad_snapshot_schema"){snapshot.insert("schema",2);pending.insert("catalog_snapshot",snapshot);}
        else if(fault=="network_mismatch")pending.insert("network_configuration",network({},"global"));
        else if(fault=="nested_documents"){snapshot.insert("documents",QJsonObject{});pending.insert("catalog_snapshot",snapshot);}
        else if(fault=="bad_base_revision")pending.insert("base_revision","01");
        else if(fault=="bad_candidate_revision")pending.insert("candidate_revision","1");
        else if(fault=="bad_digest")pending.insert("plan_digest",QString(64,QLatin1Char('A')));
        else if(fault=="unknown_operation")pending.insert("operation","unknown");
        envelope.insert("pending",pending);QVERIFY(encryptFixture(path,envelope));const auto before=readFile(path);
        NodeStore malformed(path);QVERIFY(!malformed.error().isEmpty());QVERIFY(!malformed.configurationAvailable());QVERIFY(malformed.nodes().isEmpty());QVERIFY(readFile(path)==before);QVERIFY(!malformed.saveNode(editorInput("must not replace malformed fixture")));QVERIFY(readFile(path)==before);
    }
    void pendingRevocationBlocksAutomaticAndManualSourceDownloads() {
        QTemporaryDir temporary;QVERIFY(temporary.isValid());const auto path=temporary.filePath("catalog.dpapi");QTcpServer origin;QVERIFY(origin.listen(QHostAddress::LocalHost));int connections=0;
        connect(&origin,&QTcpServer::newConnection,this,[&]{while(auto *socket=origin.nextPendingConnection()){++connections;socket->abort();socket->deleteLater();}});QUrl url(QString("http://127.0.0.1:%1/source").arg(origin.serverPort()));QString source;
        {
            NodeStore store(path);QVERIFY(store.saveSubscription({},"revoked source fixture",url,60,true,"xray-v2ray-json","nodes-only"));source=store.subscriptions().first().id;const auto parsed=XrayJsonBridge::parse(sharedXrayDocument());QVERIFY(bool(parsed));QVERIFY(store.importNodes(parsed.nodes,source));QVERIFY(migrate(store,network()));NodeStore::ImportPlan removal;QVERIFY(store.prepareRemoveSubscription(source,&removal));const auto revision=store.issueConfigurationRevision();
            QVERIFY(bool(perform(store,[&](auto callback){return store.beginCatalogIntent(removal,markRemoved(removal.retainedNetworkConfiguration(),removal.removedNodeIds()),requestTwo,revision,digestTwo,std::move(callback));})));
            QVERIFY(!store.configurationAvailable());const auto durable=readFile(path);
            NodeImportService live(&store,nullptr,[]{return qint64(4000000000LL);},100,[](const QNetworkProxyQuery &){return QList<QNetworkProxy>{QNetworkProxy(QNetworkProxy::NoProxy)};});QSignalSpy liveDiagnostics(&live,&NodeImportService::downloadDiagnostic);QVERIFY(liveDiagnostics.isValid());
            live.refreshSubscription(source);live.refreshAll();live.importUrl(url);live.importNodesOnlyUrl(url);QTest::qWait(250);
            QCOMPARE(connections,0);QCOMPARE(liveDiagnostics.count(),0);QVERIFY(!live.busy());QVERIFY(!live.hasPreview());QVERIFY(readFile(path)==durable);live.shutdown();
        }
        NodeStore blocked(path);QVERIFY(blocked.configurationRecoveryRequired());QVERIFY(!blocked.configurationAvailable());const auto before=readFile(path);
        NodeImportService imports(&blocked,nullptr,[]{return qint64(4000000000LL);},100,[](const QNetworkProxyQuery &){return QList<QNetworkProxy>{QNetworkProxy(QNetworkProxy::NoProxy)};});QSignalSpy diagnostics(&imports,&NodeImportService::downloadDiagnostic);QVERIFY(diagnostics.isValid());
        imports.refreshSubscription(source);imports.refreshAll();imports.importUrl(url);imports.importNodesOnlyUrl(url);QTest::qWait(250);
        QCOMPARE(connections,0);QCOMPARE(diagnostics.count(),0);QVERIFY(!imports.busy());QVERIFY(!imports.hasPreview());QVERIFY(readFile(path)==before);imports.shutdown();
    }
    void sharedXrayDocumentHasOneOuterCopyAcrossCommittedAndPendingSnapshots() {
        QTemporaryDir temporary;NodeStore store(temporary.filePath("catalog.dpapi"));const auto bytes=sharedXrayDocument();const auto parsed=XrayJsonBridge::parse(bytes);QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),2);QVERIFY(store.importNodes(parsed.nodes));QVERIFY(migrate(store,network(store.nodes().first().id)));
        NodeStore::ImportPlan rename;QVERIFY(store.prepareSaveNode({{"id",store.nodes().first().id},{"name","renamed shared fixture"}},&rename));const auto revision=store.issueConfigurationRevision();
        QVERIFY(bool(perform(store,[&](auto callback){return store.beginCatalogIntent(rename,rename.retainedNetworkConfiguration(),requestTwo,revision,digestTwo,std::move(callback));})));
        const auto envelope=decryptSnapshot(store.filePath()),committed=envelope.value("committed").toObject().value("snapshot").toObject(),pending=envelope.value("pending").toObject().value("catalog_snapshot").toObject();const auto documents=envelope.value("documents").toObject();
        QCOMPARE(documents.size(),1);QVERIFY(!committed.contains("documents"));QVERIFY(!pending.contains("documents"));QCOMPARE(committed.value("nodes").toArray().size(),2);QCOMPARE(pending.value("nodes").toArray().size(),2);
        const auto digest=QString::fromLatin1(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex());QVERIFY(documents.contains(digest));QVERIFY(QCryptographicHash::hash(QByteArray::fromBase64(documents.value(digest).toString().toLatin1()),QCryptographicHash::Sha256)==QCryptographicHash::hash(bytes,QCryptographicHash::Sha256));
        for(const auto &snapshot:{committed,pending})for(const auto &entry:snapshot.value("nodes").toArray()){const auto record=entry.toObject();QCOMPARE(record.value("sourceDocumentRef").toString(),digest);QVERIFY(!record.contains("sourceDocument"));QVERIFY(!record.contains("nativeOutbound"));}
        QVERIFY(bool(perform(store,[&](auto callback){return store.abortConfigurationIntent(std::move(callback));})));store.releaseConfigurationLease();QCOMPARE(store.nodes().first().name,parsed.nodes.first().name);
    }
    void deletingWholeSourcePurgesRetainedArchivesAndDocumentTable() {
        QTemporaryDir temporary;NodeStore store(temporary.filePath("catalog.dpapi"));QVERIFY(store.saveSubscription({},"shared source",QUrl("https://source.fixture.invalid/list"),60,true,"xray-v2ray-json","nodes-only"));const auto source=store.subscriptions().first().id;
        const auto parsed=XrayJsonBridge::parse(sharedXrayDocument());QVERIFY(bool(parsed));QVERIFY(store.importNodes(parsed.nodes,source));auto configuration=network();configuration.insert("importedConfiguration",QJsonObject{{"sourceId",source},{"raw","SYNTHETIC-RETAINED-ARCHIVE"}});configuration.insert("subscriptionImportResults",QJsonObject{{source,QJsonObject{{"raw","SYNTHETIC-RETAINED-ARCHIVE"}}}});QVERIFY(migrate(store,configuration));
        NodeStore::ImportPlan removal;QVERIFY(store.prepareRemoveSubscription(source,&removal));QCOMPARE(removal.removedNodeIds().size(),2);QVERIFY(removal.nodes().isEmpty());const auto retained=removal.retainedNetworkConfiguration();QVERIFY(!retained.contains("importedConfiguration"));QVERIFY(!retained.value("subscriptionImportResults").toObject().contains(source));
        const auto revision=store.issueConfigurationRevision();QVERIFY(bool(perform(store,[&](auto callback){return store.saveCatalogOffline(removal,retained,requestTwo,revision,digestTwo,std::move(callback));})));QVERIFY(store.nodes().isEmpty());QVERIFY(store.subscriptions().isEmpty());
        const auto envelope=decryptSnapshot(store.filePath());QVERIFY(envelope.value("documents").toObject().isEmpty());const auto saved=envelope.value("committed").toObject().value("snapshot").toObject().value("networkConfiguration").toObject();QVERIFY(!saved.contains("importedConfiguration"));QVERIFY(!saved.contains("subscriptionImportResults"));
    }
    void deletingOneSharedOutboundPurgesOnlyRevokedCredentials() {
        QTemporaryDir temporary;const auto path=temporary.filePath("catalog.dpapi");QString retainedId;
        {
            NodeStore store(path);const auto parsed=XrayJsonBridge::parse(sharedXrayDocument());QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),2);QVERIFY(store.importNodes(parsed.nodes));QVERIFY(migrate(store,network()));
            const auto removed=store.nodes().first(),retained=store.nodes().last();retainedId=retained.id;NodeStore::ImportPlan removal;QVERIFY2(store.prepareRemoveNode(removed.id,&removal),qPrintable(store.error()));QCOMPARE(removal.removedNodeIds(),QStringList{removed.id});QCOMPARE(removal.nodes().size(),1);
            const auto candidate=removal.nodes().first();QCOMPARE(candidate.id,retained.id);QVERIFY(candidate.nativeOutbound==retained.nativeOutbound);QVERIFY(candidate.originalConfiguration.value("outbound")==retained.originalConfiguration.value("outbound"));QVERIFY(!candidate.sourceDocument.contains("SYNTHETIC-SHARED-SECRET-0"));QVERIFY(candidate.sourceDocument.contains("SYNTHETIC-SHARED-SECRET-1"));
            const auto revision=store.issueConfigurationRevision();QVERIFY(bool(perform(store,[&](auto callback){return store.saveCatalogOffline(removal,markRemoved(removal.retainedNetworkConfiguration(),removal.removedNodeIds()),requestTwo,revision,digestTwo,std::move(callback));})));
            const auto envelope=decryptSnapshot(path),documents=envelope.value("documents").toObject();QCOMPARE(documents.size(),1);const auto onlyDocument=QByteArray::fromBase64(documents.begin().value().toString().toLatin1());QVERIFY(!onlyDocument.contains("SYNTHETIC-SHARED-SECRET-0"));QVERIFY(onlyDocument.contains("SYNTHETIC-SHARED-SECRET-1"));QCOMPARE(envelope.value("committed").toObject().value("snapshot").toObject().value("nodes").toArray().size(),1);
        }
        NodeStore reloaded(path);QVERIFY2(reloaded.error().isEmpty(),qPrintable(reloaded.error()));QCOMPARE(reloaded.nodes().size(),1);QCOMPARE(reloaded.nodes().first().id,retainedId);QVERIFY(!reloaded.nodes().first().sourceDocument.contains("SYNTHETIC-SHARED-SECRET-0"));
    }
    void sharedOutboundAccountsRejectPartialDeletionButAllowWholeSourcePurge() {
        QTemporaryDir temporary;NodeStore store(temporary.filePath("catalog.dpapi"));QVERIFY(store.saveSubscription({},"shared account source",QUrl("https://source.fixture.invalid/accounts"),60,true,"xray-v2ray-json","nodes-only"));const auto source=store.subscriptions().first().id;
        const auto parsed=XrayJsonBridge::parse(sharedAccountDocument());QVERIFY2(bool(parsed),qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),2);QVERIFY(store.importNodes(parsed.nodes,source));QVERIFY(migrate(store,network()));const auto before=readFile(store.filePath());
        NodeStore::ImportPlan partial;QVERIFY(!store.prepareRemoveNode(store.nodes().first().id,&partial));QVERIFY(!store.error().isEmpty());QCOMPARE(store.nodes().size(),2);QVERIFY(readFile(store.filePath())==before);QVERIFY(store.pendingConfigurationReceipt().isEmpty());QVERIFY(!store.saving());
        NodeStore::ImportPlan whole;QVERIFY2(store.prepareRemoveSubscription(source,&whole),qPrintable(store.error()));QCOMPARE(whole.removedNodeIds().size(),2);QVERIFY(whole.nodes().isEmpty());const auto revision=store.issueConfigurationRevision();QVERIFY(bool(perform(store,[&](auto callback){return store.saveCatalogOffline(whole,markRemoved(whole.retainedNetworkConfiguration(),whole.removedNodeIds()),requestTwo,revision,digestTwo,std::move(callback));})));
        QVERIFY(store.nodes().isEmpty());QVERIFY(store.subscriptions().isEmpty());QVERIFY(decryptSnapshot(store.filePath()).value("documents").toObject().isEmpty());
    }
    void deletingOneSourceKeepsIndependentlyAuthorizedIdenticalSource() {
        QTemporaryDir temporary;NodeStore store(temporary.filePath("catalog.dpapi"));QVERIFY(store.saveSubscription({},"source one",QUrl("https://one.fixture.invalid/list"),60,true,"xray-v2ray-json","nodes-only"));QVERIFY(store.saveSubscription({},"source two",QUrl("https://two.fixture.invalid/list"),60,true,"xray-v2ray-json","nodes-only"));const auto sourceOne=store.subscriptions().first().id,sourceTwo=store.subscriptions().last().id;
        const auto first=XrayJsonBridge::parse(sharedXrayDocument()),second=XrayJsonBridge::parse(sharedXrayDocument());QVERIFY(bool(first));QVERIFY(bool(second));QVERIFY(store.importNodes(first.nodes,sourceOne));QVERIFY(store.importNodes(second.nodes,sourceTwo));QCOMPARE(store.nodes().size(),4);QStringList retained;for(const auto &node:store.nodes())if(node.sourceId==sourceTwo)retained.append(node.id);QCOMPARE(retained.size(),2);QVERIFY(migrate(store,network(retained.first())));
        NodeStore::ImportPlan removal;QVERIFY2(store.prepareRemoveSubscription(sourceOne,&removal),qPrintable(store.error()));QCOMPARE(removal.nodes().size(),2);QCOMPARE(removal.removedNodeIds().size(),2);for(const auto &node:removal.nodes()){QVERIFY(retained.contains(node.id));QCOMPARE(node.sourceId,sourceTwo);QVERIFY(node.sourceDocument==sharedXrayDocument());}
        const auto revision=store.issueConfigurationRevision();QVERIFY(bool(perform(store,[&](auto callback){return store.saveCatalogOffline(removal,markRemoved(removal.retainedNetworkConfiguration(),removal.removedNodeIds()),requestTwo,revision,digestTwo,std::move(callback));})));QCOMPARE(store.subscriptions().size(),1);QCOMPARE(store.subscriptions().first().id,sourceTwo);QCOMPARE(decryptSnapshot(store.filePath()).value("documents").toObject().size(),1);
        NodeStore::ImportPlan last;QVERIFY(store.prepareRemoveSubscription(sourceTwo,&last));const auto next=store.issueConfigurationRevision();QVERIFY(bool(perform(store,[&](auto callback){return store.saveCatalogOffline(last,markRemoved(last.retainedNetworkConfiguration(),last.removedNodeIds()),requestThree,next,digestThree,std::move(callback));})));QVERIFY(store.nodes().isEmpty());QVERIFY(decryptSnapshot(store.filePath()).value("documents").toObject().isEmpty());
    }
};
QTEST_GUILESS_MAIN(CatalogTransactionTests)
#include "CatalogTransactionTests.moc"
