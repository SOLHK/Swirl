#include <QtTest>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QTemporaryDir>
#include <QUuid>
#include <QThread>
#include <QThreadPool>
#include <QSemaphore>
#include <QCryptographicHash>
#include "engine/NodeImporter.h"
#include "engine/NodeStore.h"
#include "engine/XrayJsonBridge.h"

#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif

namespace {
ProxyNode node(const QString &name="fixture",quint16 port=8443) {
    ProxyNode n;n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);
    n.name=name;n.protocol="http";n.host="proxy.example.invalid";n.port=port;
    n.username="synthetic-user";n.password="SYNTHETIC-PRIVATE-PASSWORD";return n;
}
QJsonObject vlessRecord(const QString &tag,int port,const QString &uuid) {
    const QJsonObject user{{"id",uuid},{"encryption","none"}};
    const QJsonObject server{{"address","proxy.example.invalid"},{"port",port},{"users",QJsonArray{user}}};
    return {{"protocol","vless"},{"tag",tag},{"settings",QJsonObject{{"vnext",QJsonArray{server}}}}};
}
NodeImporter::Result parseOutbounds(const QJsonArray &outbounds) {
    return XrayJsonBridge::parse(QJsonDocument(QJsonObject{{"outbounds",outbounds}}).toJson(QJsonDocument::Compact));
}
QByteArray read(const QString &path) {
    QFile file(path);if(!file.open(QIODevice::ReadOnly))return {};return file.readAll();
}
bool write(const QString &path,const QByteArray &bytes) {
    QFile file(path);return file.open(QIODevice::WriteOnly) && file.write(bytes)==bytes.size();
}
QByteArray expandedDocumentFixture() {
    QJsonArray users;
    for(int i=0;i<1000;++i)users.append(QJsonObject{{"id",QString("11111111-1111-4111-8111-%1").arg(i,12,16,QChar('0'))},{"encryption","none"}});
    const QJsonObject server{{"address","example.invalid"},{"port",443},{"users",users}};
    const QJsonObject settings{{"vnext",QJsonArray{server}}};
    const QJsonObject outbound{{"protocol","vless"},{"tag","expanded"},{"settings",settings}};
    return QJsonDocument(outbound).toJson(QJsonDocument::Compact);
}
#ifdef Q_OS_WIN
QByteArray crypt(const QByteArray &input,bool decrypt) {
    DATA_BLOB in{DWORD(input.size()),reinterpret_cast<BYTE *>(const_cast<char *>(input.constData()))},out{};
    const QByteArray context("Swirl.NodeStore.v1");
    DATA_BLOB entropy{DWORD(context.size()),reinterpret_cast<BYTE *>(const_cast<char *>(context.constData()))};
    const bool ok=decrypt?CryptUnprotectData(&in,nullptr,&entropy,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&out)
        :CryptProtectData(&in,L"Swirl nodes",&entropy,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&out);
    if(!ok)return {};
    QByteArray result(reinterpret_cast<char *>(out.pbData),out.cbData);
    SecureZeroMemory(out.pbData,out.cbData);LocalFree(out.pbData);return result;
}
QByteArray documentFixture() {
    // Every value is synthetic. The exact bytes (including BOM/whitespace)
    // and all advanced settings must survive the shared encrypted document.
    QByteArray bytes=QByteArray::fromHex("efbbbf")+R"JSON( {
      "inbounds":[{"protocol":"socks","listen":"127.0.0.1","port":54321}],
      "outbounds":[
        {"protocol":"freedom","tag":"local-action","settings":{}},
        {"protocol":"vless","tag":"WS 文本","settings":{"vnext":[{"address":"example.invalid","port":443,"users":[{"id":"11111111-1111-4111-8111-111111111111","encryption":"none"}]}]},"streamSettings":{"network":"ws","security":"tls","tlsSettings":{"serverName":"example.invalid","alpn":["http/1.1"],"fingerprint":"chrome"},"wsSettings":{"path":"/private-ws-path","headers":{"Host":"edge.example.invalid"}}}},
        {"protocol":"vless","tag":"REALITY Vision","settings":{"vnext":[{"address":"example.invalid","port":443,"users":[{"id":"22222222-2222-4222-8222-222222222222","encryption":"none","flow":"xtls-rprx-vision"}]}]},"streamSettings":{"network":"tcp","security":"reality","realitySettings":{"serverName":"example.invalid","publicKey":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA","shortId":"aabbccdd","spiderX":"/private-spider","fingerprint":"chrome"}}},
        {"protocol":"vmess","tag":"VMess gRPC","settings":{"vnext":[{"address":"example.invalid","port":443,"users":[{"id":"33333333-3333-4333-8333-333333333333","alterId":0,"security":"auto"}]}]},"streamSettings":{"network":"grpc","security":"tls","grpcSettings":{"serviceName":"private-grpc","multiMode":true}}},
        {"protocol":"trojan","tag":"Trojan H2","settings":{"servers":[{"address":"example.invalid","port":443,"password":"SYNTHETIC-TROJAN-PASSWORD"}]},"streamSettings":{"network":"http","security":"tls","httpSettings":{"host":["edge.example.invalid"],"path":"/private-h2"}}},
        {"protocol":"shadowsocks","tag":"SS","settings":{"servers":[{"address":"example.invalid","port":8388,"method":"aes-128-gcm","password":"SYNTHETIC-SS-PASSWORD"}]}},
        {"protocol":"socks","tag":"SOCKS Upgrade","settings":{"servers":[{"address":"example.invalid","port":1080,"users":[{"user":"synthetic-user","pass":"SYNTHETIC-SOCKS-PASSWORD"}]}]},"streamSettings":{"network":"httpupgrade","httpupgradeSettings":{"host":"edge.example.invalid","path":"/private-upgrade"}}},
        {"protocol":"http","tag":"HTTP XHTTP","settings":{"servers":[{"address":"example.invalid","port":8080,"users":[{"user":"synthetic-user","pass":"SYNTHETIC-HTTP-PASSWORD"}]}]},"streamSettings":{"network":"xhttp","xhttpSettings":{"host":"edge.example.invalid","path":"/private-xhttp","mode":"auto","extra":{"opaque":"preserved"}}}}
      ]
    } )JSON";
    return bytes;
}
#endif
}

class XrayStoreTests final:public QObject {
    Q_OBJECT
private slots:
    void expandedDocumentParsingPreservesAccounts() {
        const auto bytes=expandedDocumentFixture();const auto parsed=XrayJsonBridge::parse(bytes);
        QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1000);
        for(int i=0;i<parsed.nodes.size();++i) {
            QCOMPARE(parsed.nodes[i].sourceNodeIndex,i);QCOMPARE(parsed.nodes[i].sourceDocument,bytes);
            QCOMPARE(parsed.nodes[i].parameters.value("authentication").toObject().value("id").toString(),
                QString("11111111-1111-4111-8111-%1").arg(i,12,16,QChar('0')));
        }
    }

    void damagedStoreIsNotOverwritten() {
        QTemporaryDir temp;QVERIFY(temp.isValid());const auto path=temp.filePath("broken.dpapi");
        const QByteArray damaged("SWIRLNODE1\nnot-a-dpapi-blob");QVERIFY(write(path,damaged));
        NodeStore store(path);QVERIFY(!store.error().isEmpty());
        QVERIFY(!store.importNodes({node()}));QVERIFY(store.nodes().isEmpty());QCOMPARE(read(path),damaged);
    }

    void boundedDocumentBudget() {
        QTemporaryDir temp;NodeStore store(temp.filePath("bounded.dpapi"));
#ifdef Q_OS_WIN
        const auto existing=node("existing",9443);QVERIFY(store.importNodes({existing}));
        const auto previous=read(store.filePath());
#endif
        QList<ProxyNode> incoming;
        for(int i=0;i<8;++i) {
            auto n=node(QString("bounded-%1").arg(i),quint16(8443+i));
            n.sourceFormat="xray-v2ray-json";n.sourceNodeIndex=0;n.importSource="file";
            n.sourceDocument=QByteArray("{\"protocol\":\"http\",\"tag\":\"")+QByteArray::number(i)+
                "\",\"settings\":{\"servers\":[{\"address\":\"proxy.example.invalid\",\"port\":"+QByteArray::number(n.port)+"}]},\"opaque\":\"";
            n.sourceDocument+=QByteArray(NodeImporter::MaximumBytes-n.sourceDocument.size()-2,'x');
            n.sourceDocument+="\"}";QCOMPARE(n.sourceDocument.size(),NodeImporter::MaximumBytes);
            incoming.append(std::move(n));
        }
        QVERIFY(!store.importNodes(incoming));QVERIFY(store.error().contains("32 MiB"));
#ifdef Q_OS_WIN
        QCOMPARE(store.nodes().size(),1);QCOMPARE(store.nodes().first().id,existing.id);QCOMPARE(read(store.filePath()),previous);
#else
        QVERIFY(store.nodes().isEmpty());QVERIFY(!QFile::exists(store.filePath()));
#endif
    }

    void asyncImportProtectsWriteLease() {
        QTemporaryDir temp;NodeStore store(temp.filePath(QStringLiteral("异步节点.dpapi")));
        const QByteArray source=R"({"protocol":"http","tag":"async","settings":{"servers":[{"address":"proxy.example.invalid","port":8443,"users":[{"user":"synthetic-user","pass":"ASYNC-SYNTHETIC-PASSWORD"}]}]}})";
        const auto parsed=XrayJsonBridge::parse(source);QVERIFY2(parsed,qPrintable(parsed.error));
        NodeStore::ImportPlan plan;QVERIFY(store.prepareImport(parsed.nodes,{},&plan));
        const QJsonObject config{{"schema",1}};QSignalSpy changed(&store,&NodeStore::changed);
        bool done=false,success=false,onOwnerThread=false,callbackHasLease=true;QString error;
        QVERIFY(store.commitImportAsync(plan,config,[&](bool ok,const QString &message) {
            done=true;success=ok;error=message;onOwnerThread=QThread::currentThread()==store.thread();callbackHasLease=store.saving();
        }));
        QVERIFY(store.saving());QVERIFY(store.nodes().isEmpty());QVERIFY(store.publicRows().isEmpty());
        QVERIFY(!store.saveNode(node().publicInfo()));QVERIFY(!store.removeNode(parsed.nodes.first().id));
        QVERIFY(!store.select({}));QVERIFY(!store.saveSubscription({},"async",QUrl("https://example.invalid/config"),360,true));
        QVERIFY(!store.removeSubscription({}));QVERIFY(!store.saveNetworkConfiguration(config));
        NodeStore::ImportPlan refused;QVERIFY(!store.prepareImport(parsed.nodes,{},&refused));
        QVERIFY(!store.commitImport(plan));QVERIFY(!store.importNodes(parsed.nodes));
        bool secondCalled=false;
        QVERIFY(!store.commitImportAsync(plan,config,[&](bool,const QString &){secondCalled=true;}));
        QVERIFY(!done);QVERIFY(!secondCalled);
        QTRY_VERIFY_WITH_TIMEOUT(done,15000);
        QVERIFY(onOwnerThread);QVERIFY(!callbackHasLease);QVERIFY(!store.saving());QVERIFY(!secondCalled);
#ifdef Q_OS_WIN
        QVERIFY2(success,qPrintable(error));QVERIFY(error.isEmpty());QCOMPARE(changed.count(),1);
        QCOMPARE(store.nodes().size(),1);QCOMPARE(store.nodes().first().sourceDocument,source);
        QCOMPARE(store.networkConfiguration(),config);
        NodeStore restored(store.filePath());QVERIFY2(restored.error().isEmpty(),qPrintable(restored.error()));
        QCOMPARE(restored.nodes().first().sourceDocument,source);QCOMPARE(restored.nodes().first().parameters,parsed.nodes.first().parameters);
        QCOMPARE(restored.networkConfiguration(),config);
#else
        QVERIFY(!success);QVERIFY(error.contains("加密失败"));QCOMPARE(changed.count(),0);
        QVERIFY(store.nodes().isEmpty());QVERIFY(store.networkConfiguration().isEmpty());
        QVERIFY(!QFile::exists(store.filePath()));QVERIFY(store.select({}));
#endif
    }

    void asyncWrongStorePlanIsRejected() {
        QTemporaryDir temp;NodeStore first(temp.filePath("first.dpapi")),second(temp.filePath("second.dpapi"));
        NodeStore::ImportPlan plan;QVERIFY(first.prepareImport({node()}, {},&plan));bool called=false;
        QVERIFY(!second.commitImportAsync(plan,{},[&](bool,const QString &){called=true;}));
        QVERIFY(!called);QVERIFY(!second.saving());QVERIFY(!QFile::exists(second.filePath()));
    }

    void destroyedStoreCancelsQueuedWrite() {
        QTemporaryDir temp;const auto path=temp.filePath("cancelled.dpapi");
        auto *pool=QThreadPool::globalInstance();QVERIFY(pool->waitForDone(15000));
        QSemaphore blocked,release;const int oldCount=pool->maxThreadCount();pool->setMaxThreadCount(1);
        struct ResetPool {
            QThreadPool *pool;QSemaphore &release;int count;
            ~ResetPool(){release.release();pool->waitForDone(15000);pool->setMaxThreadCount(count);}
        } reset{pool,release,oldCount};
        pool->start([&]{blocked.release();release.acquire();});QVERIFY(blocked.tryAcquire(1,5000));
        bool called=false;
        {
            NodeStore store(path);NodeStore::ImportPlan plan;QVERIFY(store.prepareImport({node()},{},&plan));
            QVERIFY(store.commitImportAsync(plan,{},[&](bool,const QString &){called=true;}));QVERIFY(store.saving());
        }
        release.release();QVERIFY(pool->waitForDone(15000));QCoreApplication::processEvents();
        QVERIFY(!called);QVERIFY(!QFile::exists(path));
    }

    void duplicateBatchIdentity() {
        QTemporaryDir temp;NodeStore store(temp.filePath("identity.dpapi"));
        const auto a=node("same",8443),b=node("same",8444),renamed=node("renamed",8443);
        NodeStore::ImportPlan plan;
        QVERIFY2(store.prepareImport({a,b,renamed},{},&plan),qPrintable(store.error()));
        QCOMPARE(plan.nodes().size(),2);QVERIFY(store.nodes().isEmpty());
        QVERIFY(plan.nameToId().contains("same"));QVERIFY(plan.nameToId().value("same").isEmpty());
        QCOMPARE(plan.nameToId().value("renamed"),a.id);
        QCOMPARE(plan.importedToStoredIds().value(renamed.id),a.id);
        QVERIFY(!store.prepareImport({a,a},{},&plan));QVERIFY(!QFile::exists(store.filePath()));
        NodeStore other(temp.filePath("other.dpapi"));QVERIFY(!other.commitImport(plan));
        NodeStore::ImportPlan empty;QVERIFY(!store.commitImport(empty));
    }

    void unverifiedSourcesDoNotMerge() {
        auto first=node("unverified"),second=node("unverified"),duplicate=node("same bytes renamed");
        for(auto *n:{&first,&second,&duplicate}) {n->sourceFormat="xray-v2ray-json";n->sourceNodeIndex=0;}
        first.sourceDocument="{\"protocol\":\"http\",\"opaque\":1}";
        second.sourceDocument="{\"protocol\":\"http\",\"opaque\":2}";duplicate.sourceDocument=first.sourceDocument;
        QTemporaryDir temp;NodeStore store(temp.filePath("unverified.dpapi"));NodeStore::ImportPlan plan;
        QVERIFY(store.prepareImport({first,second,duplicate},{},&plan));QCOMPARE(plan.nodes().size(),2);
        QCOMPARE(plan.importedToStoredIds().value(duplicate.id),first.id);
    }

    void sharedTransportIdentityIsBounded() {
        auto outbound=QJsonDocument::fromJson(expandedDocumentFixture()).object();
        const QJsonObject xhttp{{"path","/synthetic"},{"extra",QJsonObject{{"opaque",QString(1024*1024,QChar('x'))}}}};
        outbound.insert("streamSettings",QJsonObject{{"network","xhttp"},{"xhttpSettings",xhttp}});
        const auto parsed=XrayJsonBridge::parse(QJsonDocument(outbound).toJson(QJsonDocument::Compact));
        QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1000);
        QTemporaryDir temp;NodeStore store(temp.filePath("shared-identity.dpapi"));NodeStore::ImportPlan plan;
        QVERIFY2(store.prepareImport(parsed.nodes,{},&plan),qPrintable(store.error()));QCOMPARE(plan.nodes().size(),1000);
    }

    void sameTagsKeepDifferentAccounts() {
        const auto parsed=parseOutbounds({vlessRecord("same",443,"11111111-1111-4111-8111-111111111111"),
            vlessRecord("same",443,"22222222-2222-4222-8222-222222222222")});
        QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),2);
        QTemporaryDir temp;NodeStore store(temp.filePath("accounts.dpapi"));NodeStore::ImportPlan plan;
        QVERIFY2(store.prepareImport(parsed.nodes,{},&plan),qPrintable(store.error()));
        QCOMPARE(plan.nodes().size(),2);QVERIFY(plan.nodes()[0].id!=plan.nodes()[1].id);
        QVERIFY(plan.nameToId().value("same").isEmpty());
    }

#ifndef Q_OS_WIN
    void encryptionUnavailableFailsClosed() {
        QTemporaryDir temp;NodeStore store(temp.filePath("no-backend.dpapi"));
        QVERIFY(!store.importNodes({node()}));QVERIFY(store.nodes().isEmpty());
        QVERIFY(store.error().contains("加密失败"));QVERIFY(!QFile::exists(store.filePath()));
        QVERIFY(!QFile::exists(store.filePath()+".selected"));
    }
#else
    void encryptedDocumentRoundtrip() {
        QTemporaryDir temp;QVERIFY(temp.isValid());const auto path=temp.filePath(QStringLiteral("节点保存.dpapi"));
        const auto source=documentFixture();const auto imported=XrayJsonBridge::parse(source);
        QVERIFY2(imported,qPrintable(imported.error));QCOMPARE(imported.nodes.size(),7);QVERIFY(imported.nodes.first().sourceNodeIndex>0);
        QList<ProxyNode> before;
        {
            NodeStore store(path);auto nodes=imported.nodes;
            for(auto &n:nodes)n.importSource="file";
            QVERIFY2(store.importNodes(nodes),qPrintable(store.error()));before=store.nodes();
            QVERIFY(store.select(before[1].id));
        }
        const auto encrypted=read(path);QVERIFY(!encrypted.isEmpty());
        QVERIFY(!encrypted.contains("SYNTHETIC"));QVERIFY(!encrypted.contains("11111111-1111"));
        QVERIFY(!encrypted.contains("private-ws-path"));QVERIFY(!encrypted.contains("private-spider"));
        const auto plaintext=crypt(encrypted.mid(11),true);const auto saved=QJsonDocument::fromJson(plaintext).object();
        QCOMPARE(saved.value("documents").toObject().size(),1);QCOMPARE(saved.value("catalogVersion").toInt(),2);
        for(const auto &entry:saved.value("nodes").toArray()) {
            const auto n=entry.toObject();QVERIFY(n.contains("sourceDocumentRef"));
            QVERIFY(!n.contains("nativeExecutable"));QVERIFY(!n.contains("nativeOutbound"));
            QVERIFY(!n.contains("capability"));
        }
        NodeStore reloaded(path);QVERIFY2(reloaded.error().isEmpty(),qPrintable(reloaded.error()));
        QCOMPARE(reloaded.nodes().size(),before.size());QCOMPARE(reloaded.selectedId(),before[1].id);
        for(int i=0;i<before.size();++i) {
            const auto &a=before[i];const auto b=reloaded.nodes()[i];
            QCOMPARE(b.id,a.id);QCOMPARE(b.name,a.name);QCOMPARE(b.protocol,a.protocol);QCOMPARE(b.host,a.host);QCOMPARE(b.port,a.port);
            QCOMPARE(b.username,a.username);QCOMPARE(b.password,a.password);QCOMPARE(b.cipher,a.cipher);QCOMPARE(b.serverName,a.serverName);
            QCOMPARE(b.parameters,a.parameters);QCOMPARE(b.originalConfiguration,a.originalConfiguration);
            QCOMPARE(b.sourceDocument,source);QCOMPARE(b.sourceNodeIndex,a.sourceNodeIndex);QCOMPARE(b.importSource,QString("file"));
            const auto publicText=QJsonDocument(QJsonObject::fromVariantMap(b.publicInfo())).toJson();
            QVERIFY(!publicText.contains("SYNTHETIC"));QVERIFY(!publicText.contains("11111111-1111"));
            QVERIFY(!publicText.contains("private-ws-path"));QVERIFY(!publicText.contains("private-grpc"));
        }
        auto edit=reloaded.nodes().first().publicInfo();edit.insert("name",QStringLiteral("仅修改显示名称"));
        QVERIFY(reloaded.saveNode(edit));const auto renamed=reloaded.nodes().first();
        QCOMPARE(renamed.sourceDocument,source);QCOMPARE(renamed.parameters,before.first().parameters);
        edit=renamed.publicInfo();edit.insert("host","changed.example.invalid");
        QVERIFY(!reloaded.saveNode(edit));QCOMPARE(reloaded.nodes().first().host,renamed.host);
    }

    void expandedDocumentStoredOnce() {
        const auto bytes=expandedDocumentFixture();auto parsed=XrayJsonBridge::parse(bytes);
        QVERIFY2(parsed,qPrintable(parsed.error));QCOMPARE(parsed.nodes.size(),1000);
        for(int i=0;i<parsed.nodes.size();++i)parsed.nodes[i].name=QString("expanded-%1").arg(i);
        QTemporaryDir temp;const auto path=temp.filePath("expanded.dpapi");
        {NodeStore store(path);QVERIFY2(store.importNodes(parsed.nodes),qPrintable(store.error()));}
        const auto encrypted=read(path);QVERIFY(encrypted.size()<bytes.size()*8+512*1024);
        const auto snapshot=QJsonDocument::fromJson(crypt(encrypted.mid(11),true)).object();
        QCOMPARE(snapshot.value("documents").toObject().size(),1);
        for(const auto &entry:snapshot.value("nodes").toArray()) {
            const auto stored=entry.toObject();QVERIFY(!stored.contains("options"));QVERIFY(!stored.contains("originalConfiguration"));
            QVERIFY(!stored.contains("password"));QVERIFY(!stored.contains("username"));
        }
        NodeStore restored(path);QVERIFY2(restored.error().isEmpty(),qPrintable(restored.error()));QCOMPARE(restored.nodes().size(),1000);
        const auto nodes=restored.nodes();
        for(int i=0;i<nodes.size();++i) {
            QCOMPARE(nodes[i].sourceNodeIndex,parsed.nodes[i].sourceNodeIndex);
            QCOMPARE(nodes[i].parameters,parsed.nodes[i].parameters);QCOMPARE(nodes[i].sourceDocument,bytes);
        }
    }

    void legacyStoreMigration() {
        QTemporaryDir temp;const auto path=temp.filePath("legacy.dpapi");const auto a=node("legacy-a"),b=node("legacy-b",8444);
        QJsonArray nodes;
        for(const auto &n:{a,b})nodes.append(QJsonObject{{"id",n.id},{"name",n.name},{"protocol",n.protocol},{"host",n.host},{"port",n.port},
            {"username",n.username},{"password",n.password},{"options",n.parameters}});
        const auto snapshot=QJsonDocument(QJsonObject{{"schema",1},{"nodes",nodes},{"selected",a.id}}).toJson(QJsonDocument::Compact);
        const auto encrypted=crypt(snapshot,false);QVERIFY(!encrypted.isEmpty());QVERIFY(write(path,QByteArray("SWIRLNODE1\n")+encrypted));
        QVERIFY(write(path+".selected",QJsonDocument(QJsonObject{{"selected",b.id}}).toJson(QJsonDocument::Compact)));
        NodeStore loaded(path);QVERIFY2(loaded.error().isEmpty(),qPrintable(loaded.error()));QCOMPARE(loaded.selectedId(),b.id);
        QCOMPARE(loaded.nodes().first().password,a.password);
        auto edit=loaded.nodes().first().publicInfo();edit.insert("name","renamed legacy");QVERIFY(loaded.saveNode(edit));
        NodeStore migrated(path);QVERIFY(migrated.error().isEmpty());QCOMPARE(migrated.selectedId(),b.id);QCOMPARE(migrated.nodes().size(),2);
        QCOMPARE(migrated.nodes().first().password,a.password);QCOMPARE(migrated.nodes().first().name,QString("renamed legacy"));
        const auto current=QJsonDocument::fromJson(crypt(read(path).mid(11),true)).object();QCOMPARE(current.value("catalogVersion").toInt(),2);
    }

    void damagedDocumentTableIsNotOverwritten() {
        QTemporaryDir temp;const auto path=temp.filePath("document-digest.dpapi");
        const auto imported=XrayJsonBridge::parse(documentFixture());QVERIFY(imported);
        {NodeStore store(path);QVERIFY(store.importNodes(imported.nodes));}
        auto snapshot=QJsonDocument::fromJson(crypt(read(path).mid(11),true)).object();
        auto documents=snapshot.value("documents").toObject();QCOMPARE(documents.size(),1);
        const auto key=documents.keys().first();
        const auto changed=QByteArray::fromBase64(documents.value(key).toString().toLatin1())+' ';
        documents.insert(key,QString::fromLatin1(changed.toBase64()));snapshot.insert("documents",documents);
        const auto encrypted=crypt(QJsonDocument(snapshot).toJson(QJsonDocument::Compact),false);QVERIFY(!encrypted.isEmpty());
        const auto damaged=QByteArray("SWIRLNODE1\n")+encrypted;QVERIFY(write(path,damaged));
        NodeStore rejected(path);QVERIFY(!rejected.error().isEmpty());QVERIFY(rejected.nodes().isEmpty());
        QVERIFY(!rejected.importNodes(imported.nodes));QCOMPARE(read(path),damaged);
    }

    void failedReplayKeepsOriginalDocumentDisabled() {
        QTemporaryDir temp;const auto path=temp.filePath("replay-failure.dpapi");auto saved=node("retained");
        saved.sourceFormat="xray-v2ray-json";saved.sourceNodeIndex=0;saved.sourceDocument=R"({"protocol":"http","protocol":"socks"})";
        saved.transportType="tcp";saved.securityType="none";saved.nativeExecutable=true;
        {NodeStore store(path);QVERIFY(store.importNodes({saved}));}
        NodeStore restored(path);QVERIFY2(restored.error().isEmpty(),qPrintable(restored.error()));QCOMPARE(restored.nodes().size(),1);
        const auto node=restored.nodes().first();QCOMPARE(node.id,saved.id);QCOMPARE(node.sourceDocument,saved.sourceDocument);
        QCOMPARE(node.sourceFingerprint,QString::fromLatin1(QCryptographicHash::hash(saved.sourceDocument,QCryptographicHash::Sha256).toHex()));
        QVERIFY(!node.nativeExecutable);QVERIFY(node.nativeOutbound.isEmpty());QCOMPARE(node.parameterState,QString("unverified"));
        QVERIFY(!node.runtimeIssues.isEmpty());
    }

    void storedCapabilityFlagsAreNotAuthority() {
        QTemporaryDir temp;const auto path=temp.filePath("capability-cache.dpapi");
        const auto imported=XrayJsonBridge::parse(documentFixture());QVERIFY(imported);
        {NodeStore store(path);QVERIFY(store.importNodes(imported.nodes));}
        auto snapshot=QJsonDocument::fromJson(crypt(read(path).mid(11),true)).object();auto nodes=snapshot.value("nodes").toArray();
        for(qsizetype i=0;i<nodes.size();++i) {
            auto entry=nodes[i].toObject();entry.insert("nativeExecutable",true);entry.insert("parameterState","valid");
            entry.insert("nativeOutbound",QJsonObject{{"type","direct"}});nodes[i]=entry;
        }
        snapshot.insert("nodes",nodes);const auto encrypted=crypt(QJsonDocument(snapshot).toJson(QJsonDocument::Compact),false);
        QVERIFY(!encrypted.isEmpty());QVERIFY(write(path,QByteArray("SWIRLNODE1\n")+encrypted));
        NodeStore restored(path);QVERIFY2(restored.error().isEmpty(),qPrintable(restored.error()));QCOMPARE(restored.nodes().size(),imported.nodes.size());
        bool disabled=false;
        for(qsizetype i=0;i<imported.nodes.size();++i) {
            const auto node=restored.nodes()[i];QCOMPARE(node.nativeExecutable,imported.nodes[i].nativeExecutable);
            QCOMPARE(node.nativeOutbound,imported.nodes[i].nativeOutbound);disabled=disabled || !node.nativeExecutable;
        }
        QVERIFY(disabled);
    }

    void manualImportRenameAndCredentialSeparation() {
        QTemporaryDir temp;NodeStore store(temp.filePath("manual.dpapi"));
        const auto a=node("A");QVERIFY(store.importNodes({a}));QVERIFY(store.select(a.id));
        auto renamed=node("renamed");QVERIFY(store.importNodes({renamed}));QCOMPARE(store.nodes().size(),1);
        QCOMPARE(store.nodes().first().id,a.id);QCOMPARE(store.selectedId(),a.id);QCOMPARE(store.nodes().first().name,QString("renamed"));
        auto different=node("renamed",9443);QVERIFY(store.importNodes({different}));QCOMPARE(store.nodes().size(),2);
        QCOMPARE(store.selectedId(),a.id);
        auto rotated=node("renamed");rotated.password="ANOTHER-SYNTHETIC-PASSWORD";
        QVERIFY(store.importNodes({rotated}));QCOMPARE(store.nodes().size(),3);QCOMPARE(store.selectedId(),a.id);
        NodeStore::ImportPlan stale;QVERIFY(store.prepareImport({node("renamed")},{},&stale));
        QVERIFY(store.select(different.id));QVERIFY(!store.commitImport(stale));
        const auto otherSource=QUuid::createUuid().toString(QUuid::WithoutBraces);
        QVERIFY(!store.prepareImport({a},otherSource,&stale));QCOMPARE(store.nodes().size(),3);
    }

    void refreshAndSelectionIdentity() {
        QTemporaryDir temp;const auto path=temp.filePath("refresh.dpapi");NodeStore store(path);
        QVERIFY(store.saveSubscription({},"synthetic source",QUrl("https://example.invalid/config"),360,false,"xray-v2ray-json"));
        const auto source=store.subscriptions().first().id;
        const QString firstId="11111111-1111-4111-8111-111111111111",secondId="22222222-2222-4222-8222-222222222222";
        QJsonArray raw{vlessRecord("A",443,firstId),vlessRecord("B",444,secondId)};
        auto parsed=parseOutbounds(raw);QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes,source));
        const auto selected=store.nodes().first().id,other=store.nodes().last().id;
        const auto activeSnapshot=store.nodes().first();QVERIFY(store.select(selected));
        raw=QJsonArray{raw[1],raw[0]};parsed=parseOutbounds(raw);QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes,source));
        QCOMPARE(store.selectedId(),selected);QCOMPARE(store.nodes()[0].id,other);QCOMPARE(store.nodes()[1].id,selected);
        raw[1]=vlessRecord("Renamed",443,firstId);parsed=parseOutbounds(raw);QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes,source));
        QCOMPARE(store.selectedId(),selected);QCOMPARE(store.nodes()[1].id,selected);QCOMPARE(store.nodes()[1].name,QString("Renamed"));
        raw[1]=vlessRecord("Renamed",8443,"33333333-3333-4333-8333-333333333333");
        parsed=parseOutbounds(raw);QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes,source));
        QCOMPARE(store.selectedId(),selected);QCOMPARE(store.nodes()[1].id,selected);QCOMPARE(store.nodes()[1].port,quint16(8443));
        QCOMPARE(store.nodes()[1].parameters.value("authentication").toObject().value("id").toString(),QString("33333333-3333-4333-8333-333333333333"));
        raw=QJsonArray{raw[0]};parsed=parseOutbounds(raw);QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes,source));
        QCOMPARE(store.nodes().size(),1);QCOMPARE(store.nodes().first().id,other);QVERIFY(store.selectedId().isEmpty());
        // The running engine owns a value snapshot, not an address into the
        // mutable catalog. NodeStore never mutates that old account in place.
        QCOMPARE(activeSnapshot.port,quint16(443));QCOMPARE(activeSnapshot.parameters.value("authentication").toObject().value("id").toString(),firstId);
        NodeStore restored(path);QVERIFY(restored.selectedId().isEmpty());QCOMPARE(restored.nodes().first().id,other);
    }

    void reorderedAccountsKeepSelectedIdentity() {
        QTemporaryDir temp;NodeStore store(temp.filePath("reordered-accounts.dpapi"));
        QVERIFY(store.saveSubscription({},"synthetic",QUrl("https://example.invalid/config"),360,false,"xray-v2ray-json"));
        const auto source=store.subscriptions().first().id;
        auto first=vlessRecord("shared",443,"11111111-1111-4111-8111-111111111111");
        auto settings=first.value("settings").toObject();auto server=settings.value("vnext").toArray().first().toObject();
        auto users=server.value("users").toArray();users.append(QJsonObject{{"id","22222222-2222-4222-8222-222222222222"},{"encryption","none"}});
        server.insert("users",users);settings.insert("vnext",QJsonArray{server});first.insert("settings",settings);
        auto parsed=parseOutbounds({first});QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes,source));
        const auto a=store.nodes().first().id,b=store.nodes().last().id;QVERIFY(store.select(a));
        server.insert("users",QJsonArray{users[1],users[0]});settings.insert("vnext",QJsonArray{server});first.insert("settings",settings);
        parsed=parseOutbounds({first});QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes,source));
        QCOMPARE(store.nodes()[0].id,b);QCOMPARE(store.nodes()[1].id,a);QCOMPARE(store.selectedId(),a);
    }

    void incomingExactMatchWinsOverSourceAlias() {
        QTemporaryDir temp;NodeStore store(temp.filePath("exact-before-alias.dpapi"));
        QVERIFY(store.saveSubscription({},"synthetic",QUrl("https://example.invalid/config"),360,false,"xray-v2ray-json"));
        const auto source=store.subscriptions().first().id;
        const auto a=vlessRecord("provider-name",443,"11111111-1111-4111-8111-111111111111");
        auto parsed=parseOutbounds({a});QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes,source));
        const auto selected=store.nodes().first().id;QVERIFY(store.select(selected));
        auto renamed=a;renamed.insert("tag","new-provider-name");
        parsed=parseOutbounds({vlessRecord("provider-name",8443,"22222222-2222-4222-8222-222222222222"),renamed});
        QVERIFY(parsed);QVERIFY(store.importNodes(parsed.nodes,source));QCOMPARE(store.nodes().size(),2);
        QVERIFY(store.nodes()[0].id!=selected);QCOMPARE(store.nodes()[1].id,selected);QCOMPARE(store.selectedId(),selected);
    }

    void ambiguousSourceAliasesDoNotOverwrite() {
        QTemporaryDir temp;NodeStore store(temp.filePath("ambiguous.dpapi"));
        QVERIFY(store.saveSubscription({},"synthetic source",QUrl("https://example.invalid/config"),360,false,"xray-v2ray-json"));
        const auto source=store.subscriptions().first().id;
        auto parsed=parseOutbounds({vlessRecord("same",443,"11111111-1111-4111-8111-111111111111"),
            vlessRecord("same",444,"22222222-2222-4222-8222-222222222222")});QVERIFY(parsed);
        QVERIFY(store.importNodes(parsed.nodes,source));const auto old=store.nodes().first().id;QVERIFY(store.select(old));
        parsed=parseOutbounds({vlessRecord("same",8443,"33333333-3333-4333-8333-333333333333"),
            vlessRecord("same",8444,"44444444-4444-4444-8444-444444444444")});QVERIFY(parsed);
        QVERIFY(store.importNodes(parsed.nodes,source));QCOMPARE(store.nodes().size(),2);QVERIFY(store.selectedId().isEmpty());
        for(const auto &n:store.nodes())QVERIFY(n.id!=old);
    }

    void selectionSidecarSnapshotBinding() {
        QTemporaryDir temp;const auto path=temp.filePath("selection.dpapi");NodeStore store(path);
        const auto a=node("A"),b=node("B",8444);QVERIFY(store.importNodes({a,b}));QVERIFY(store.select(a.id));
        const auto stale=read(path+".selected");QVERIFY(store.select(b.id));
        auto edit=b.publicInfo();edit.insert("name","updated B");QVERIFY(store.saveNode(edit));
        QVERIFY(write(path+".selected",stale));NodeStore loaded(path);QCOMPARE(loaded.selectedId(),b.id);
        QVERIFY(loaded.select(a.id));NodeStore selected(path);QCOMPARE(selected.selectedId(),a.id);
    }

    void atomicFailureKeepsOldStore() {
        QTemporaryDir temp;const auto path=temp.filePath(QStringLiteral("原子保存.dpapi"));NodeStore store(path);
        const auto a=node("old");QVERIFY(store.importNodes({a}));QVERIFY(store.select(a.id));const auto previous=read(path);
        struct LockedFile {HANDLE handle;~LockedFile(){if(handle!=INVALID_HANDLE_VALUE)CloseHandle(handle);}} locked{
            CreateFileW(reinterpret_cast<LPCWSTR>(path.utf16()),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr)};
        QVERIFY(locked.handle!=INVALID_HANDLE_VALUE);
        QVERIFY(!store.importNodes({node("new")}));QCOMPARE(store.nodes().size(),1);QCOMPARE(store.selectedId(),a.id);QCOMPARE(read(path),previous);
        NodeStore::ImportPlan plan;QVERIFY(store.prepareImport({node("async-new")},{},&plan));
        bool done=false,success=true;QString error;
        QVERIFY(store.commitImportAsync(plan,{},[&](bool ok,const QString &message){done=true;success=ok;error=message;}));
        QTRY_VERIFY_WITH_TIMEOUT(done,15000);QVERIFY(!success);QVERIFY(!error.isEmpty());QVERIFY(!store.saving());
        QCOMPARE(store.nodes().size(),1);QCOMPARE(store.selectedId(),a.id);QCOMPARE(read(path),previous);
    }


#endif
};
QTEST_GUILESS_MAIN(XrayStoreTests)
#include "XrayStoreTests.moc"
