#include "NodeStore.h"
#include "NodeImporter.h"
#include "XrayJsonBridge.h"
#include "../app/StoragePaths.h"
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QStandardPaths>
#include <QUuid>
#include <QSet>
#include <QMap>
#include <QFileInfo>
#include <QDateTime>
#include <QCryptographicHash>
#include <QRegularExpression>
#include <QCoreApplication>
#include <QPointer>
#include <QThread>
#include <QThreadPool>
#include <QLockFile>
#include <limits>
#include <algorithm>
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif

static QByteArray protect(const QByteArray &input, bool decrypt) {
#ifdef Q_OS_WIN
    DATA_BLOB source{DWORD(input.size()), reinterpret_cast<BYTE *>(const_cast<char *>(input.constData()))}, result{};
    const QByteArray context("Swirl.NodeStore.v1");
    DATA_BLOB entropy{DWORD(context.size()), reinterpret_cast<BYTE *>(const_cast<char *>(context.constData()))};
    const bool ok = decrypt ? CryptUnprotectData(&source, nullptr, &entropy, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &result)
        : CryptProtectData(&source, L"Swirl nodes", &entropy, nullptr, nullptr, CRYPTPROTECT_UI_FORBIDDEN, &result);
    if (!ok) return {};
    const QByteArray bytes(reinterpret_cast<char *>(result.pbData), result.cbData);
    SecureZeroMemory(result.pbData, result.cbData); LocalFree(result.pbData);
    return bytes;
#else
    Q_UNUSED(input); Q_UNUSED(decrypt); return {}; // No plaintext fallback.
#endif
}
static QJsonObject serialize(const ProxyNode &n) {
    if(n.isXray()) {
        // The exact source is persisted once in the document table. Derived
        // per-account options and raw outbounds must not duplicate a large
        // multi-user outbound for every expanded node (quadratic disk use).
        return {{"id",n.id},{"name",n.name},{"protocol",n.protocol},{"host",n.host},{"port",n.port},
            {"sourceId",n.sourceId},{"sourceFormat",n.sourceFormat},{"importSource",n.importSource},{"providerAlias",n.providerAlias},
            {"transportType",n.transportType},{"securityType",n.securityType},
            {"conversionIssues",QJsonArray::fromStringList(n.conversionIssues)}};
    }
    // Explicit private persistence schema: adding a UI role must never cause
    // executable capability caches or other derived flags to become authority.
    return {{"id",n.id},{"name",n.name},{"protocol",n.protocol},{"host",n.host},{"port",n.port},
        {"username",n.username},{"password",n.password},{"cipher",n.cipher},{"serverName",n.serverName},
        {"sourceId",n.sourceId},{"sourceFormat",n.sourceFormat},{"importSource",n.importSource},{"providerAlias",n.providerAlias},
        {"options",n.parameters},{"originalConfiguration",n.originalConfiguration},
        {"conversionIssues",QJsonArray::fromStringList(n.conversionIssues)},
        {"certificateVerificationEnforced",n.certificateVerificationEnforced}};
}
static ProxyNode deserialize(const QVariantMap &m) {
    ProxyNode n; n.id=m.value("id").toString(); n.name=m.value("name").toString().trimmed();
    n.protocol=m.value("protocol").toString(); n.host=m.value("host").toString().trimmed();
    const auto port=m.value("port").toInt(); n.port=port>0 && port<=65535 ? quint16(port) : 0;
    n.username=m.value("username").toString(); n.password=m.value("password").toString();
    n.cipher=m.value("cipher").toString(); n.serverName=m.value("serverName").toString().trimmed();
    n.parameters=QJsonObject::fromVariantMap(m.value("options").toMap());n.sourceId=m.value("sourceId").toString();
    n.originalConfiguration=QJsonObject::fromVariantMap(m.value("originalConfiguration").toMap());
    n.sourceFormat=m.value("sourceFormat").toString();n.conversionIssues=m.value("conversionIssues").toStringList();
    n.certificateVerificationEnforced=m.value("certificateVerificationEnforced").toBool();
    n.importSource=m.value("importSource").toString();
    n.providerAlias=m.value("providerAlias").toString();
    n.transportType=m.value("transportType").toString();n.securityType=m.value("securityType").toString();
    // A previous importer may have accepted a URI while losing an unsupported
    // source field from its normalized options. Recheck the preserved source
    // with today's parser; capability changes must not authorize that loss.
    // This only adds bounded diagnostics in memory. Keep the stored parameters,
    // identity, selection and original document, and never rewrite on load.
    if(n.originalConfiguration.contains("uri")){
        const auto source=n.originalConfiguration.value("uri");
        const auto parsed=source.isString()?NodeImporter::parse(source.toString().toUtf8()):NodeImporter::Result{};
        const auto issues=parsed&&parsed.nodes.size()==1?parsed.nodes.first().conversionIssues:
            QStringList{QStringLiteral("保存的原始 URI 无法通过当前导入校验；原始字段已保留，拒绝执行。")};
        for(const auto &issue:issues)if(!n.conversionIssues.contains(issue)&&n.conversionIssues.size()<32)n.conversionIssues.append(issue);
    }
    if(n.cipher.isEmpty())n.cipher=n.parameters.value("cipher").toString();
    return n;
}
NodeStore::NodeStore(QString path, QObject *parent) : QObject(parent), m_path(std::move(path)) {
    if (m_path.isEmpty()) m_path=SwirlPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/nodes.dpapi";
    m_configurationStoreId=QUuid::createUuid().toString(QUuid::WithoutBraces);
    load();
    if(configurationV2()) {
        if(!acquireConfigurationLock()){m_healthy=false;return;}
        const auto pending=m_configurationEnvelope.value("pending").toObject();
        if(!pending.isEmpty()) {
            if(!QStringList{"configuration","catalogue"}.contains(pending.value("operation").toString())) {
                m_configurationRecoveryRequired=true;m_healthy=false;
                m_error=QStringLiteral("配置包含待恢复的凭据撤销操作；保持断开，未恢复旧凭据。");return;
            }
            // The DLL shares this process. No runtime plan survived a crash;
            // only committed data may be restored. Keep the revision high-water.
            m_configurationEnvelope.remove("pending");
            if(!write(m_nodes,m_selected,m_subscriptions,m_networkConfiguration,true)) {
                m_configurationRecoveryRequired=true;m_healthy=false;return;
            }
        }
        return; // A V2 store never replays the legacy selection sidecar.
    }
    // Bind the non-secret selection sidecar to this exact encrypted snapshot.
    // A later import must not be undone by an older, still-valid selected ID.
    // Existing v1 snapshots retain their old sidecar on their first read only.
    QFile selection(m_path+".selected");
    if(m_healthy && selection.open(QIODevice::ReadOnly) && selection.size()<=512) {
        const auto object=QJsonDocument::fromJson(selection.read(513)).object();
        const auto id=object.value("selected").toString();
        const bool sameSnapshot=object.value("schema").toInt()==2 &&
            object.value("snapshot").toString().toLatin1()==m_snapshotDigest;
        const bool legacy=m_legacySelection && !object.contains("schema") && !object.contains("snapshot");
        if((sameSnapshot || legacy) && object.value("selected").isString() &&
            (id.isEmpty() || std::any_of(m_nodes.cbegin(),m_nodes.cend(),[&](const auto &n){return n.id==id;})))m_selected=id;
    }
}
NodeStore::~NodeStore() {
    if(m_saveCancelled)m_saveCancelled->store(true,std::memory_order_release);
}
bool NodeStore::allowMutation() {
    if(!m_saving)return true;
    m_error=QStringLiteral("节点库正在安全保存，请等待完成后重试。");return false;
}
QVariantList NodeStore::publicRows() const {
    if(m_publicRows.isEmpty()) {
        QHash<QString,QString> sources;
        for(const auto &source:m_subscriptions)sources.insert(source.id,source.name);
        for(const auto &n:m_nodes) {
            auto row=n.publicInfo();
            const bool legacy=legacyNode(n),subscription=!legacy&&!n.sourceId.isEmpty();
            row.insert("sourceKind",legacy?QStringLiteral("legacy"):subscription?QStringLiteral("subscription"):QStringLiteral("manual"));
            row.insert("sourceName",legacy?QStringLiteral("历史节点 · 归属待确认"):subscription?sources.value(n.sourceId):QStringLiteral("手动添加"));
            m_publicRows.append(row);
        }
    }
    return m_publicRows;
}
bool NodeStore::legacyNode(const ProxyNode &node) const {
    if(!node.sourceId.isEmpty())
        return std::none_of(m_subscriptions.cbegin(),m_subscriptions.cend(),[&](const auto &source){return source.id==node.sourceId;});
    // Old catalogs can have lost *all* provenance when detaching a subscription.
    // Absence of sourceFormat is not evidence of a manually created node. Only
    // explicit user-entry origins establish that; all other unowned records
    // remain visible for review and are removed only by confirmed cleanup.
    static const QStringList userOrigins{"manual","manual-import","text","clipboard","file","url"};
    return !userOrigins.contains(node.importSource);
}
int NodeStore::legacyNodeCount() const {
    return int(std::count_if(m_nodes.cbegin(),m_nodes.cend(),[this](const auto &node){return legacyNode(node);}));
}
void NodeStore::load() {
    QFile file(m_path);
    if (!file.exists()) return;
    m_healthy=false;
    if (!file.open(QIODevice::ReadOnly) || file.size()>MaximumBytes) { m_error=QStringLiteral("节点文件无法读取或超过 32 MiB；未覆盖原文件。"); return; }
    auto ciphertext=file.read(MaximumBytes+1);
    if(ciphertext.size()>MaximumBytes || file.error()!=QFile::NoError) {m_error=QStringLiteral("节点文件读取失败或超过上限；未覆盖原文件。");return;}
    const bool v2=ciphertext.startsWith("SWIRLNODE2\n");
    if (!v2&&!ciphertext.startsWith("SWIRLNODE1\n")) { m_error=QStringLiteral("节点文件格式无效；未覆盖原文件。"); return; }
    auto plaintext=protect(ciphertext.mid(11), true);
    if(plaintext.isEmpty() || plaintext.size()>MaximumBytes) {plaintext.fill('\0');m_error=QStringLiteral("节点解密失败或超过上限；原文件保持不变。");return;}
    QJsonParseError parse;
    auto document=QJsonDocument::fromJson(plaintext, &parse); plaintext.fill('\0');
    if(v2 && parse.error==QJsonParseError::NoError && document.isObject()) {
        const auto envelope=document.object();const auto committed=envelope.value("committed").toObject();
        const auto decimal=[](const QJsonValue &value,quint64 *number){
            if(!value.isString()||!QRegularExpression("^(0|[1-9][0-9]{0,19})$").match(value.toString()).hasMatch())return false;
            bool ok=false;*number=value.toString().toULongLong(&ok);return ok;
        };
        quint64 issued=0,saved=0;
        if(envelope.value("schema").toInt()!=2 || QUuid(envelope.value("store_id").toString()).isNull() ||
           !decimal(envelope.value("last_issued_revision"),&issued)||!decimal(committed.value("saved_revision"),&saved)||!saved||saved>issued||
           QUuid(committed.value("request_id").toString()).isNull()||
           !QRegularExpression("^[0-9a-f]{64}$").match(committed.value("plan_digest").toString()).hasMatch()||
           !committed.value("snapshot").isObject() ||
           (envelope.contains("pending")&&!envelope.value("pending").isObject())) {
            m_error=QStringLiteral("V2 配置身份或版本无效；原文件保持不变。");return;
        }
        if(envelope.contains("pending")){
            const auto pending=envelope.value("pending").toObject();quint64 base=0,candidate=0;
            const auto operation=pending.value("operation").toString();
            if(!QStringList{"configuration","catalogue","revoke"}.contains(operation)||
               QUuid(pending.value("request_id").toString()).isNull()||pending.value("request_id")==committed.value("request_id")||
               !decimal(pending.value("base_revision"),&base)||base!=saved||
               !decimal(pending.value("candidate_revision"),&candidate)||candidate<=base||candidate>issued||
               !QRegularExpression("^[0-9a-f]{64}$").match(pending.value("plan_digest").toString()).hasMatch()||
               !pending.value("network_configuration").isObject()||
               (operation!="configuration"&&(!pending.value("catalog_snapshot").isObject()||!pending.value("revoked_node_ids").isArray()))||
               (operation=="configuration"&&(pending.contains("catalog_snapshot")||pending.contains("revoked_node_ids")))){
                m_error=QStringLiteral("V2 待处理事务身份无效；未清理或回放候选。");return;
            }
        }
        m_configurationEnvelope=envelope;m_configurationStoreId=envelope.value("store_id").toString();m_lastIssuedRevision=issued;
        auto current=committed.value("snapshot").toObject();
        if(envelope.contains("documents")){
            if(!envelope.value("documents").isObject()||current.contains("documents")){
                m_error=QStringLiteral("V2 源文档表无效；原文件保持不变。");return;
            }
            current.insert("documents",envelope.value("documents"));
        }
        document=QJsonDocument(current);
    }
    if (parse.error!=QJsonParseError::NoError || !document.isObject() || document.object().value("schema").toInt()!=1) {
        m_error=QStringLiteral("DPAPI 节点解密失败或文件损坏；请使用保存它的 Windows 用户。原文件未覆盖。"); return;
    }
    ImportPlan decoded;
    if(!decodeCatalogSnapshot(document.object(),&decoded))return;
    const auto pending=m_configurationEnvelope.value("pending").toObject();
    if(!pending.isEmpty()&&pending.value("operation").toString()!="configuration") {
        auto candidate=pending.value("catalog_snapshot").toObject();
        if(candidate.contains("documents")){m_error=QStringLiteral("待处理目录的源文档表存在歧义；未恢复旧凭据。");return;}
        if(m_configurationEnvelope.contains("documents"))candidate.insert("documents",m_configurationEnvelope.value("documents"));
        ImportPlan checked;
        if(!decodeCatalogSnapshot(candidate,&checked)||checked.m_network!=pending.value("network_configuration").toObject()){
            m_error=QStringLiteral("待处理目录或网络配置不一致；未清理候选。");return;
        }
        QSet<QString> nextIds;for(const auto &node:checked.m_nodes)nextIds.insert(node.id);
        QSet<QString> removed;for(const auto &node:decoded.m_nodes)if(!nextIds.contains(node.id))removed.insert(node.id);
        QSet<QString> declared;
        for(const auto &value:pending.value("revoked_node_ids").toArray()){
            const auto id=value.toString();
            if(!value.isString()||QUuid(id).isNull()||declared.contains(id)){m_error=QStringLiteral("待撤销节点标识无效；未清理候选。");return;}
            declared.insert(id);
        }
        if(removed!=declared||(pending.value("operation").toString()=="catalogue"?!removed.isEmpty():removed.isEmpty())){
            m_error=QStringLiteral("待处理目录操作与撤销集合不一致；未恢复旧凭据。");return;
        }
    }
    m_nodes=decoded.m_nodes;m_selected=decoded.m_selected;m_subscriptions=decoded.m_sources;m_networkConfiguration=decoded.m_network;
    m_healthy=true;m_snapshotDigest=QCryptographicHash::hash(ciphertext,QCryptographicHash::Sha256).toHex();
    m_legacySelection=!v2&&document.object().value("catalogVersion").toInt(1)==1;
}
bool NodeStore::decodeCatalogSnapshot(const QJsonObject &snapshot,ImportPlan *output) {
    if(!output||snapshot.value("schema").toInt()!=1){m_error=QStringLiteral("目录快照版本无效。");return false;}
    const int catalogVersion=snapshot.value("catalogVersion").toInt(1);
    if((catalogVersion!=1 && catalogVersion!=2) || !snapshot.value("nodes").isArray() ||
       !snapshot.value("selected").isString() ||
       (snapshot.contains("subscriptions") && !snapshot.value("subscriptions").isArray())) {
        m_error=QStringLiteral("节点库版本或结构无效；原文件保持不变。");return false;
    }
    // Store one exact byte sequence per document, even when it yielded 2000
    // nodes. QByteArray copies below remain implicitly shared in memory.
    QHash<QString,QByteArray> originals;
    const auto storedDocuments=snapshot.value("documents");
    if(!storedDocuments.isUndefined() && !storedDocuments.isObject()) {m_error=QStringLiteral("保存的源文档表无效。");return false;}
    const auto documents=storedDocuments.toObject();
    const auto pendingCatalog=m_configurationEnvelope.value("pending").toObject().value("catalog_snapshot").isObject();
    if(documents.size()>(pendingCatalog?4000:2000)) {m_error=QStringLiteral("保存的源文档数量超过上限。");return false;}
    static const QRegularExpression digestPattern(QStringLiteral("^[0-9a-f]{64}$"));
    qsizetype originalBytes=0;
    for(auto it=documents.begin();it!=documents.end();++it) {
        if(!digestPattern.match(it.key()).hasMatch() || !it.value().isString() ||
           it.value().toString().size()>((NodeImporter::MaximumBytes+2)/3)*4) {
            m_error=QStringLiteral("保存的源文档标识或大小无效。");return false;
        }
        auto decoded=QByteArray::fromBase64Encoding(it.value().toString().toLatin1(),QByteArray::AbortOnBase64DecodingErrors);
        if(!decoded || decoded.decoded.isEmpty() || decoded.decoded.size()>NodeImporter::MaximumBytes ||
           QCryptographicHash::hash(decoded.decoded,QCryptographicHash::Sha256).toHex()!=it.key().toLatin1()) {
            m_error=QStringLiteral("保存的源文档校验失败；原文件保持不变。");return false;
        }
        originalBytes+=decoded.decoded.size();
        if(originalBytes>MaximumBytes) {m_error=QStringLiteral("保存的源文档超过总大小上限。");return false;}
        originals.insert(it.key(),std::move(decoded.decoded));
    }
    const auto array=snapshot.value("nodes").toArray();
    if (array.size()>2000) { m_error=QStringLiteral("节点数量超过上限。"); return false; }
    QHash<QString,QHash<int,ProxyNode>> replayedDocuments;
    QList<ProxyNode> nodes; QSet<QString> ids;
    for (const auto &entry : array) {
        if(!entry.isObject()) {m_error=QStringLiteral("保存的节点结构无效。");return false;}
        const auto object=entry.toObject();
        if(object.contains("providerAlias")&&!object.value("providerAlias").isString()){m_error=QStringLiteral("保存的订阅节点别名类型无效；原文件保持不变。");return false;}
        auto n=deserialize(object.toVariantMap());
        if(object.contains("sourceDocumentRef")) {
            const auto reference=object.value("sourceDocumentRef");
            const auto index=object.value("sourceNodeIndex");
            if(!reference.isString() || !originals.contains(reference.toString()) ||
               !index.isDouble() || index.toDouble()!=index.toInt(-1) || index.toInt(-1)<0 || index.toInt()>=2000) {
                m_error=QStringLiteral("保存的节点源文档引用无效；原文件保持不变。");return false;
            }
            n.sourceDocument=originals.value(reference.toString());n.sourceNodeIndex=index.toInt();n.sourceFingerprint=reference.toString();
            if(!replayedDocuments.contains(reference.toString())) {
                // All runtime decisions are rebuilt by today's A/B parser,
                // once per distinct source rather than once per node.
                const auto parsed=XrayJsonBridge::parse(n.sourceDocument);
                QHash<int,ProxyNode> replay;
                if(parsed)for(const auto &candidate:parsed.nodes)replay.insert(candidate.sourceNodeIndex,candidate);
                replayedDocuments.insert(reference.toString(),std::move(replay));
            }
            const auto &replay=replayedDocuments[reference.toString()];
            const auto found=replay.constFind(n.sourceNodeIndex);
            if(found!=replay.cend()) {
                // Raw source is authoritative for secrets/options. Preserve
                // user identity, the editable display name and provenance.
                const auto saved=n;n=found.value();
                n.id=saved.id;n.name=saved.name;n.sourceId=saved.sourceId;n.importSource=saved.importSource;n.providerAlias=saved.providerAlias;
                n.sourceDocument=saved.sourceDocument;n.sourceNodeIndex=saved.sourceNodeIndex;
            } else {
                // A missing/new DLL or failed revalidation must disable the
                // affected node, never erase an otherwise intact catalog.
                n.nativeOutbound={};n.nativeExecutable=false;n.parameterState="unverified";
                n.runtimeIssues={QStringLiteral("SavedXraySourceRevalidationFailed")};
            }
        } else if(object.contains("sourceNodeIndex")) {
            m_error=QStringLiteral("保存的节点缺少源文档引用。");return false;
        }
        if (!ProxyNode::validate(n).isEmpty() || ids.contains(n.id)) { m_error=QStringLiteral("保存的节点参数无效；未覆盖原文件。"); return false; }
        ids.insert(n.id); nodes.append(n);
    }
    const auto selected=snapshot.value("selected").toString();
    if (!selected.isEmpty() && !ids.contains(selected)) { m_error=QStringLiteral("保存的选择无效。"); return false; }
    QList<NodeSubscription> subscriptions; QSet<QString> sourceIds;
    for(const auto &entry:snapshot.value("subscriptions").toArray()) {
        const auto o=entry.toObject();NodeSubscription s;
        s.id=o.value("id").toString();s.name=o.value("name").toString();s.url=QUrl(o.value("url").toString());
        s.formatHint=o.value("formatHint").toString("auto");
        if(o.contains("importScope") && !o.value("importScope").isString()){m_error=QStringLiteral("保存的订阅导入范围无效；未覆盖原文件。");return false;}
        s.importScope=o.value("importScope").toString("full-profile");
        s.intervalMinutes=o.value("interval").toInt();s.enabled=o.value("enabled").toBool();s.lastSuccess=o.value("lastSuccess").toInteger();
        if(QUuid(s.id).isNull() || sourceIds.contains(s.id) || !allowedSubscriptionUrl(s.url) || !subscriptionFormats().contains(s.formatHint) || !subscriptionScopes().contains(s.importScope) || s.name.isEmpty() || s.name.size()>128 || s.intervalMinutes<15 || s.intervalMinutes>10080 || subscriptions.size()>=32){m_error=QStringLiteral("保存的订阅参数无效；未覆盖原文件。");return false;}
        sourceIds.insert(s.id);subscriptions.append(s);
    }
    // An older version may have removed the subscription record while leaving
    // its nodes behind. Preserve orphaned data and present it for explicit
    // cleanup; an uncertain owner must not make the entire catalog unreadable.
    for(const auto &n:nodes)if(!n.sourceId.isEmpty() && QUuid(n.sourceId).isNull()){m_error=QStringLiteral("节点订阅标识无效；未覆盖原文件。");return false;}
    const auto network=snapshot.value("networkConfiguration");
    if(!network.isUndefined() && (!network.isObject() || network.toObject().value("schema").toInt()!=1)) {
        m_error=QStringLiteral("保存的网络配置无效；原文件保持不变。");return false;
    }
    ImportPlan plan;plan.m_owner=this;plan.m_revision=m_revision;
    plan.m_nodes=nodes;plan.m_selected=selected;plan.m_sources=subscriptions;plan.m_network=network.toObject();
    *output=std::move(plan);return true;
}
namespace {
struct StoreSnapshot {
    QList<ProxyNode> nodes;
    QString selected;
    QList<NodeSubscription> subscriptions;
    QJsonObject networkConfiguration;
    QJsonObject configurationEnvelope;
    std::shared_ptr<const StoreSnapshot> pendingCatalog{};
};
// This function owns every serializer, DPAPI buffer and QSaveFile it uses. It
// receives only value snapshots, so an asynchronous save never accesses a
// NodeStore or another QObject belonging to the UI thread.
QString encodeCatalog(const StoreSnapshot &data,const std::shared_ptr<std::atomic_bool> &cancel,
                      QJsonObject &documents,QHash<quintptr,QString> &documentIds,qsizetype &privateBytes,QJsonObject *encoded) {
    const auto cancelled=[&] {return cancel && cancel->load(std::memory_order_acquire);};
    if(cancelled())return QStringLiteral("节点保存已取消；原配置保持不变。");
    const auto &nodes=data.nodes;
    const auto &selected=data.selected;
    const auto &subscriptions=data.subscriptions;
    const auto &networkConfiguration=data.networkConfiguration;
    if(nodes.size()>2000 || subscriptions.size()>32) {return QStringLiteral("节点或订阅数量超过保存上限。");}
    QJsonArray array;
    for(const auto &n:nodes) {
        if(cancelled())return QStringLiteral("节点保存已取消；原配置保持不变。");
        auto stored=serialize(n);
        if(!n.sourceDocument.isEmpty()) {
            if(n.sourceDocument.size()>NodeImporter::MaximumBytes || n.sourceNodeIndex<0 || n.sourceNodeIndex>=2000) {
                return QStringLiteral("源文档大小或节点位置无效；旧配置保持不变。");
            }
            // A batch shares the source QByteArray. Hash that shared buffer
            // once, while different allocations still deduplicate by content.
            const auto buffer=quintptr(n.sourceDocument.constData());
            auto digest=documentIds.value(buffer);
            if(digest.isEmpty()) {
                digest=QString::fromLatin1(QCryptographicHash::hash(n.sourceDocument,QCryptographicHash::Sha256).toHex());
                documentIds.insert(buffer,digest);
            }
            stored.insert("sourceDocumentRef",digest);stored.insert("sourceNodeIndex",n.sourceNodeIndex);
            if(!documents.contains(digest)) {
                const auto encoded=n.sourceDocument.toBase64();privateBytes+=encoded.size()+digest.size()+6;
                if(privateBytes>NodeStore::MaximumBytes) {return QStringLiteral("源文档超过 32 MiB 保存上限；旧配置保持不变。");}
                documents.insert(digest,QString::fromLatin1(encoded));
            }
        }
        privateBytes+=QJsonDocument(stored).toJson(QJsonDocument::Compact).size()+1;
        if(privateBytes>NodeStore::MaximumBytes) {return QStringLiteral("节点库超过 32 MiB 保存上限；旧配置保持不变。");}
        array.append(stored);
    }
    QJsonArray sources;
    for(const auto &s:subscriptions)sources.append(QJsonObject{{"id",s.id},{"name",s.name},{"formatHint",s.formatHint},{"importScope",s.importScope},{"url",s.url.toString(QUrl::FullyEncoded)},{"interval",s.intervalMinutes},{"enabled",s.enabled},{"lastSuccess",s.lastSuccess}});
    QJsonObject snapshot{{"schema",1},{"catalogVersion",2},{"selected",selected},{"nodes",array},{"subscriptions",sources}};
    if(!networkConfiguration.isEmpty()) {
        if(networkConfiguration.value("schema").toInt()!=1){return QStringLiteral("网络配置版本无效。");}
        snapshot.insert("networkConfiguration",networkConfiguration);
    }
    *encoded=std::move(snapshot);return {};
}
QString persistSnapshot(const QString &path,const StoreSnapshot &data,
                        const std::shared_ptr<std::atomic_bool> &cancel = {},QByteArray *snapshotDigest = nullptr,QJsonObject *savedEnvelope=nullptr) {
    const auto cancelled=[&] {return cancel && cancel->load(std::memory_order_acquire);};
    QJsonObject documents,snapshot;QHash<quintptr,QString> documentIds;qsizetype privateBytes=0;
    auto error=encodeCatalog(data,cancel,documents,documentIds,privateBytes,&snapshot);if(!error.isEmpty())return error;
    auto persisted=snapshot;
    if(!data.configurationEnvelope.isEmpty()) {
        persisted=data.configurationEnvelope;
        auto committed=persisted.value("committed").toObject();
        committed.insert("snapshot",snapshot);persisted.insert("committed",committed);
        if(data.pendingCatalog){
            QJsonObject candidate;
            error=encodeCatalog(*data.pendingCatalog,cancel,documents,documentIds,privateBytes,&candidate);if(!error.isEmpty())return error;
            auto pending=persisted.value("pending").toObject();pending.insert("catalog_snapshot",candidate);persisted.insert("pending",pending);
        }
        if(documents.isEmpty())persisted.remove("documents");else persisted.insert("documents",documents);
    } else if(!documents.isEmpty()) {
        persisted.insert("documents",documents);
    }
    auto plaintext=QJsonDocument(persisted).toJson(QJsonDocument::Compact);
    if(plaintext.size()>NodeStore::MaximumBytes) {plaintext.fill('\0');return QStringLiteral("节点库超过 32 MiB 保存上限；旧配置保持不变。");}
    if(cancelled()) {plaintext.fill('\0');return QStringLiteral("节点保存已取消；原配置保持不变。");}
    const auto encrypted=protect(plaintext, false); plaintext.fill('\0');
    if(cancelled())return QStringLiteral("节点保存已取消；原配置保持不变。");
    if (encrypted.isEmpty()) { return QStringLiteral("Windows DPAPI 加密失败，未保存任何明文凭据。"); }
    if (!QDir().mkpath(QFileInfo(path).absolutePath())) { return QStringLiteral("节点目录无法创建。"); }
    QSaveFile file(path); const auto bytes=QByteArray(data.configurationEnvelope.isEmpty()?"SWIRLNODE1\n":"SWIRLNODE2\n")+encrypted;
    file.setDirectWriteFallback(false);
    if(bytes.size()>NodeStore::MaximumBytes) {
        return QStringLiteral("节点库超过 32 MiB 保存上限；旧配置保持不变。");
    }
    if (!file.open(QIODevice::WriteOnly) || !file.setPermissions(QFile::ReadOwner|QFile::WriteOwner) || file.write(bytes)!=bytes.size() || cancelled() || !file.commit()) {
        return QStringLiteral("节点配置无法安全保存，旧配置保持不变。");
    }
    if(snapshotDigest)*snapshotDigest=QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex();
    if(savedEnvelope)*savedEnvelope=data.configurationEnvelope.isEmpty()?QJsonObject{}:persisted;
    return {};
}
}
void NodeStore::adoptSnapshot(const QList<ProxyNode> &nodes,const QString &selected,
                              const QList<NodeSubscription> &subscriptions,const QJsonObject &networkConfiguration,const QByteArray &snapshotDigest) {
    m_snapshotDigest=snapshotDigest;m_legacySelection=false;
    m_nodes=nodes;m_publicRows.clear();m_selected=selected;m_subscriptions=subscriptions;
    m_networkConfiguration=networkConfiguration;m_error.clear();++m_revision;emit changed();
}
bool NodeStore::write(const QList<ProxyNode> &nodes,const QString &selected,
                      const QList<NodeSubscription> &subscriptions,const QJsonObject &networkConfiguration,bool configurationMaintenance) {
    if(!allowMutation())return false;
    if(configurationV2()&&!configurationMaintenance){m_error=QStringLiteral("V2 配置变更必须通过统一配置事务；未绕过运行回执保存。");return false;}
    if(!m_healthy) {m_error=QStringLiteral("节点库损坏或无法解密；未覆盖原文件。");return false;}
    if(!acquireConfigurationLock())return false;
    const auto pathLock=m_configurationLock;
    if(!configurationV2())m_configurationLock.reset(); // Legacy readers may take turns; each write still verifies its baseline.
    QByteArray snapshotDigest;QJsonObject savedEnvelope;
    m_error=persistSnapshot(m_path,{nodes,selected,subscriptions,networkConfiguration,m_configurationEnvelope},{},&snapshotDigest,&savedEnvelope);
    if(!m_error.isEmpty())return false;
    if(!savedEnvelope.isEmpty())m_configurationEnvelope=savedEnvelope;
    adoptSnapshot(nodes,selected,subscriptions,networkConfiguration,snapshotDigest);return true;
}
bool NodeStore::saveNode(const QVariantMap &input) {
    ImportPlan plan;return prepareSaveNode(input,&plan)&&commitImport(plan);
}
bool NodeStore::prepareSaveNode(const QVariantMap &input,ImportPlan *output) {
    if(!allowMutation())return false;
    // The editor/API boundary must obey the same scalar types as import. A
    // QVariant conversion must not synthesize credentials or an SNI default.
    for(const auto &key:QStringList{"username","password","cipher","serverName"})if(input.contains(key)&&input.value(key).metaType().id()!=QMetaType::QString){
        m_error=QStringLiteral("凭据、加密方式和 TLS 名称必须为字符串；原节点保持不变。");return false;
    }
    if(input.contains("replaceCredentials")&&input.value("replaceCredentials").metaType().id()!=QMetaType::Bool){
        m_error=QStringLiteral("替换凭据开关必须为布尔值；原节点保持不变。");return false;
    }
    auto n=deserialize(input); auto nodes=m_nodes; int index=-1;
    if(input.contains("options") && input.value("options").metaType().id()!=QMetaType::QVariantMap){m_error=QStringLiteral("扩展选项须为 JSON 对象。");return false;}
    if (n.id.isEmpty()) n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);
    else { for (int i=0;i<nodes.size();++i) if (nodes[i].id==n.id) index=i;
        if (index<0) { m_error=QStringLiteral("编辑的节点不存在。"); return false; } }
    if(index>=0 && !nodes[index].sourceDocument.isEmpty()) {
        // The raw JSON remains the authority for the imported node. Allow a
        // local display-name edit, but never keep a stale raw source beside
        // independently edited authentication or transport fields.
        const auto &old=nodes[index];
        const QHash<QString,QVariant> fixed{{"protocol",old.protocol},{"host",old.host},{"port",old.port},
            {"cipher",old.cipher},{"serverName",old.serverName}};
        bool changed=input.value("replaceCredentials").toBool();
        for(auto it=fixed.cbegin();it!=fixed.cend();++it)if(input.contains(it.key())) {
            if(it.key()=="port")changed=changed || input.value(it.key()).toInt()!=old.port;
            else changed=changed || input.value(it.key()).toString()!=it.value().toString();
        }
        if(input.contains("options"))changed=changed || QJsonObject::fromVariantMap(input.value("options").toMap())!=old.parameters;
        for(const auto &key:QStringList{"username","password"})if(input.contains(key) && !input.value(key).toString().isEmpty())
            changed=changed || input.value(key).toString()!=(key=="username"?old.username:old.password);
        if(changed) {m_error=QStringLiteral("JSON 导入节点仅支持修改显示名称；请修改原配置后重新导入以更新连接参数。");return false;}
        auto renamed=old;if(input.contains("name"))renamed.name=input.value("name").toString().trimmed();
        m_error=ProxyNode::validate(renamed);if(!m_error.isEmpty())return false;
        nodes[index]=std::move(renamed);return prepareCatalog(nodes,m_selected,m_subscriptions,m_networkConfiguration,output);
    }
    if (index>=0 && n.protocol==nodes[index].protocol && !input.value("replaceCredentials").toBool()) {
        if (n.password.isEmpty()) n.password=nodes[index].password;
        if (n.username.isEmpty()) n.username=nodes[index].username;
        if(!input.contains("options"))n.parameters=nodes[index].parameters;
        else {auto merged=nodes[index].parameters;for(auto it=n.parameters.begin();it!=n.parameters.end();++it)merged.insert(it.key(),it.value());n.parameters=merged;}
    }
    if(index>=0){n.sourceId=nodes[index].sourceId;n.sourceFormat=nodes[index].sourceFormat;n.originalConfiguration=nodes[index].originalConfiguration;n.conversionIssues=nodes[index].conversionIssues;n.importSource=nodes[index].importSource;n.providerAlias=nodes[index].providerAlias;n.certificateVerificationEnforced=nodes[index].certificateVerificationEnforced;}
    else {n.sourceId.clear();n.sourceFormat.clear();n.importSource="manual";n.providerAlias.clear();n.originalConfiguration={};n.conversionIssues.clear();n.certificateVerificationEnforced=false;}
    if(index>=0 && n.protocol==nodes[index].protocol && n.protocol!="ss" && n.cipher.isEmpty())n.cipher=nodes[index].cipher;
    m_error=ProxyNode::validate(n); if (!m_error.isEmpty()) return false;
    if (index<0) { if (nodes.size()>=2000) { m_error=QStringLiteral("最多保存 2000 个节点。"); return false; } nodes.append(n); }
    else nodes[index]=n;
    return prepareCatalog(nodes,m_selected,m_subscriptions,m_networkConfiguration,output);
}
bool NodeStore::removeNode(const QString &id) {
    ImportPlan plan;return prepareRemoveNode(id,&plan)&&commitImport(plan);
}
bool NodeStore::prepareRemoveNode(const QString &id,ImportPlan *output) {
    if(!allowMutation())return false;
    auto nodes=m_nodes; const auto old=nodes.size(); nodes.removeIf([&](const ProxyNode &n){return n.id==id;});
    if (nodes.size()==old) { m_error=QStringLiteral("节点不存在。"); return false; }
    return prepareCatalog(nodes,m_selected==id ? QString() : m_selected,m_subscriptions,m_networkConfiguration,output);
}
bool NodeStore::select(const QString &id) {
    if(!allowMutation())return false;
    if(configurationV2()){m_error=QStringLiteral("V2 默认出口必须通过策略配置事务修改。");return false;}
    if (!id.isEmpty() && std::none_of(m_nodes.begin(),m_nodes.end(),[&](const ProxyNode &n){return n.id==id;})) {
        m_error=QStringLiteral("选择的节点不存在。"); return false;
    }
    if(!m_healthy){m_error=QStringLiteral("节点库无法解密；选择未保存。");return false;}
    if(m_selected==id){m_error.clear();return true;}
    if(!acquireConfigurationLock())return false;
    const auto pathLock=m_configurationLock;
    m_configurationLock.reset(); // This method rejects V2 above.
    QSaveFile file(m_path+".selected");
    file.setDirectWriteFallback(false);
    const auto bytes=QJsonDocument(QJsonObject{{"schema",2},{"snapshot",QString::fromLatin1(m_snapshotDigest)},{"selected",id}}).toJson(QJsonDocument::Compact);
    if(!QDir().mkpath(QFileInfo(m_path).absolutePath()) || !file.open(QIODevice::WriteOnly) ||
       !file.setPermissions(QFile::ReadOwner|QFile::WriteOwner) || file.write(bytes)!=bytes.size() || !file.commit()){
        m_error=QStringLiteral("无法保存节点选择，原选择保持不变。");return false;
    }
    m_selected=id;m_error.clear();++m_revision;emit selectionChanged();return true;
}
bool NodeStore::allowedSubscriptionUrl(const QUrl &url) {
    const bool secure=url.scheme()=="https";
    const bool local=url.scheme()=="http" && (url.host()=="127.0.0.1" || url.host()=="::1");
    return url.isValid() && !url.host().isEmpty() && url.userInfo().isEmpty() && url.fragment().isEmpty() && (secure||local) && url.toEncoded().size()<=8192;
}
QVariantList NodeStore::publicSubscriptions() const {
    QVariantList rows;
    for(const auto &s:m_subscriptions){
        int count=0;for(const auto &n:m_nodes)if(n.sourceId==s.id)++count;
        rows.append(QVariantMap{{"id",s.id},{"name",s.name},{"formatHint",s.formatHint},{"importScope",s.importScope},{"source",QStringLiteral("订阅地址已加密隐藏")},{"nodes",count},{"intervalMinutes",s.intervalMinutes},{"enabled",s.enabled},
            {"lastSuccess",s.lastSuccess},{"update",s.lastSuccess?QDateTime::fromSecsSinceEpoch(s.lastSuccess).toLocalTime().toString("yyyy-MM-dd HH:mm"):QStringLiteral("尚未成功更新")}});
    }
    return rows;
}
bool NodeStore::saveSubscription(const QString &id,const QString &name,const QUrl &url,int interval,bool enabled,const QString &formatHint,const QString &importScope) {
    ImportPlan plan;return prepareSaveSubscription(id,name,url,interval,enabled,formatHint,importScope,&plan)&&commitImport(plan);
}
bool NodeStore::prepareSaveSubscription(const QString &id,const QString &name,const QUrl &url,int interval,bool enabled,const QString &formatHint,const QString &importScope,ImportPlan *output) {
    if(!allowMutation())return false;
    auto sources=m_subscriptions;int index=-1;
    for(int i=0;i<sources.size();++i)if(sources[i].id==id)index=i;
    if(!id.isEmpty() && index<0){m_error=QStringLiteral("订阅不存在。");return false;}
    NodeSubscription s=index<0?NodeSubscription{}:sources[index];
    if(s.id.isEmpty())s.id=QUuid::createUuid().toString(QUuid::WithoutBraces);
    s.name=name.trimmed();if(!url.isEmpty())s.url=url;s.intervalMinutes=interval;s.enabled=enabled;
    if(!formatHint.isEmpty())s.formatHint=formatHint;
    if(!importScope.isEmpty())s.importScope=importScope;
    if(!subscriptionFormats().contains(s.formatHint)){m_error=QStringLiteral("订阅格式无效。");return false;}
    if(!subscriptionScopes().contains(s.importScope)){m_error=QStringLiteral("订阅导入范围无效。");return false;}
    if(s.name.isEmpty() || s.name.size()>128 || s.name.contains(QRegularExpression("[\\x00-\\x1f]")) || !allowedSubscriptionUrl(s.url) || interval<15 || interval>10080){m_error=QStringLiteral("需要有效名称、HTTPS 订阅地址及 15–10080 分钟更新间隔（仅本机测试允许 HTTP）。");return false;}
    for(const auto &existing:sources)if(existing.id!=s.id&&existing.url==s.url){m_error=QStringLiteral("此订阅地址已存在；请更新已有订阅，避免重复节点来源。");return false;}
    if(index<0){if(sources.size()>=32){m_error=QStringLiteral("最多保存 32 个订阅。");return false;}sources.append(s);}else sources[index]=s;
    return prepareCatalog(m_nodes,m_selected,sources,m_networkConfiguration,output);
}
namespace {
QJsonObject withoutRemovedNodes(QJsonObject configuration,const QSet<QString> &removed,const QString &sourceId={}) {
    // Preserve the policy graph and fail closed at exactly the removed node.
    // Deleting a rule or an empty group could silently change its traffic to
    // the fallback/DIRECT route. REJECT remains a valid explicit destination.
    auto groups=configuration.value("groups").toArray();
    for(int i=0;i<groups.size();++i) {
        auto group=groups[i].toObject();auto members=group.value("proxies").toArray();
        bool changed=false;
        for(int j=0;j<members.size();++j)if(removed.contains(members[j].toString())){members[j]="REJECT";changed=true;}
        if(changed) {
            QJsonArray unique;for(const auto &member:members)if(!unique.contains(member))unique.append(member);
            group.insert("proxies",unique);
            if(removed.contains(group.value("default-selected").toString()))group.insert("default-selected","REJECT");
            groups[i]=group;
        }
    }
    if(configuration.contains("groups"))configuration.insert("groups",groups);
    auto rules=configuration.value("rules").toArray();
    for(int i=0;i<rules.size();++i) {
        auto fields=rules[i].toString().split(',');for(auto &field:fields)field=field.trimmed();
        const auto target=fields.value(0)=="MATCH"?1:2;
        if(fields.size()>target&&removed.contains(fields[target])){fields[target]="REJECT";rules[i]=fields.join(',');}
    }
    if(configuration.contains("rules"))configuration.insert("rules",rules);
    if(!sourceId.isEmpty()&&configuration.value("importedConfiguration").toObject().value("sourceId").toString()==sourceId)
        configuration.remove("importedConfiguration");
    if(!sourceId.isEmpty()&&configuration.value("subscriptionImportResults").isObject()) {
        auto results=configuration.value("subscriptionImportResults").toObject();results.remove(sourceId);
        if(results.isEmpty())configuration.remove("subscriptionImportResults");
        else configuration.insert("subscriptionImportResults",results);
    }
    return configuration;
}
}
bool NodeStore::removeSubscription(const QString &id) {
    ImportPlan plan;return prepareRemoveSubscription(id,&plan)&&commitImport(plan);
}
bool NodeStore::prepareRemoveSubscription(const QString &id,ImportPlan *output) {
    if(!allowMutation())return false;
    auto sources=m_subscriptions;const auto old=sources.size();sources.removeIf([&](const auto &s){return s.id==id;});
    if(old==sources.size()){m_error=QStringLiteral("订阅不存在。");return false;}
    QSet<QString> removed;auto nodes=m_nodes;
    nodes.removeIf([&](const auto &node){if(node.sourceId!=id)return false;removed.insert(node.id);return true;});
    return prepareCatalog(nodes,removed.contains(m_selected)?QString():m_selected,sources,withoutRemovedNodes(m_networkConfiguration,removed,id),output);
}
bool NodeStore::cleanLegacyNodes() {
    ImportPlan plan;return prepareCleanLegacyNodes(&plan)&&commitImport(plan);
}
bool NodeStore::prepareCleanLegacyNodes(ImportPlan *output) {
    if(!allowMutation())return false;
    QSet<QString> removed;auto nodes=m_nodes;
    nodes.removeIf([&](const auto &node){if(!legacyNode(node))return false;removed.insert(node.id);return true;});
    if(removed.isEmpty()){m_error=QStringLiteral("没有需要清理的历史归属节点。");return false;}
    return prepareCatalog(nodes,removed.contains(m_selected)?QString():m_selected,m_subscriptions,withoutRemovedNodes(m_networkConfiguration,removed),output);
}
namespace {
struct IdentityCache {
    QHash<quintptr,QByteArray> documents;
    QHash<QByteArray,QByteArray> publicParts;
};
QJsonObject identitySource(const ProxyNode &node,const QByteArray &origin,IdentityCache &cache) {
    auto original=node.originalConfiguration;
    if(node.isXray()) {
        auto outbound=original.value("outbound").toObject();outbound.remove("tag");
        const auto source=original.value("source").toObject();
        auto settings=outbound.value("settings").toObject();
        const auto serverIndex=source.value("server_index").toInt(-1);
        const auto userIndex=source.value("user_index").toInt(-1);
        const auto serverPath=source.value("server_path").toString();
        const auto key=serverPath.contains(".vnext[")?QStringLiteral("vnext"):
            serverPath.contains(".servers[")?QStringLiteral("servers"):QString();
        auto server=settings;
        const auto servers=settings.value(key).toArray();
        if(!key.isEmpty() && serverIndex>=0 && serverIndex<servers.size()) {
            server=servers.at(serverIndex).toObject();settings.remove(key);
        } else settings={};
        if(outbound.contains("settings"))outbound.insert("settings",settings);
        // Hash shared raw fields once. A 4 MiB transport object expanded to
        // 2000 accounts must not be serialized 2000 times on the UI thread.
        const auto partKey=origin.left(32)+":outbound:"+QByteArray::number(source.value("outbound_index").toInt(-1));
        auto common=cache.publicParts.value(partKey);
        if(common.isEmpty()) {
            common=QCryptographicHash::hash(QJsonDocument(outbound).toJson(QJsonDocument::Compact),QCryptographicHash::Sha256).toHex();
            cache.publicParts.insert(partKey,common);
        }
        QJsonValue user;
        const auto users=server.value("users").toArray();
        if(userIndex>=0 && userIndex<users.size()) {user=users.at(userIndex);server.remove("users");}
        const auto serverKey=partKey+":server:"+key.toUtf8()+':'+QByteArray::number(serverIndex);
        auto endpoint=cache.publicParts.value(serverKey);
        if(endpoint.isEmpty()) {
            endpoint=QCryptographicHash::hash(QJsonDocument(server).toJson(QJsonDocument::Compact),QCryptographicHash::Sha256).toHex();
            cache.publicParts.insert(serverKey,endpoint);
        }
        // Selecting raw source elements is only an identity operation. The
        // original document and Rust's execution mapping remain unchanged.
        return {{"outbound",QString::fromLatin1(common)},{"server",QString::fromLatin1(endpoint)},{"user",user}};
    }
    if(node.conversionIssues.isEmpty())return {};
    original.remove("name");original.remove("tag");original.remove("ps");
    if(original.contains("vmess")) {
        auto vmess=original.value("vmess").toObject();vmess.remove("ps");original.insert("vmess",vmess);original.remove("uri");
    } else if(original.value("uri").isString()) {
        auto uri=original.value("uri").toString();const auto fragment=uri.indexOf('#');
        if(fragment>=0)uri.truncate(fragment);original.insert("uri",uri);
    }
    return original;
}
QByteArray sourceLocator(const ProxyNode &node,IdentityCache &cache) {
    if(!node.isXray() || node.sourceDocument.isEmpty())return {};
    const auto buffer=quintptr(node.sourceDocument.constData());
    auto digest=cache.documents.value(buffer);
    if(digest.isEmpty()) {digest=QCryptographicHash::hash(node.sourceDocument,QCryptographicHash::Sha256);cache.documents.insert(buffer,digest);}
    return digest+':'+QByteArray::number(node.sourceNodeIndex);
}
QByteArray semanticIdentity(const ProxyNode &node,const QByteArray &source,IdentityCache &cache) {
    // A missing/new DLL leaves only safe display data. Never merge those
    // records using host/port while their authentication is still unverified.
    if(node.isXray() && !node.originalConfiguration.value("outbound").isObject())
        return QCryptographicHash::hash(QByteArray("unverified:")+source,QCryptographicHash::Sha256);
    auto options=node.parameters;
    if(node.isXray())for(const auto &key:{"streamSettings","mux","proxySettings"})options.remove(key);
    const QJsonObject identity{{"protocol",node.protocol},{"host",node.host.toCaseFolded()},{"port",node.port},
        {"username",node.username},{"password",node.password},{"cipher",node.cipher},{"serverName",node.serverName},
        {"options",options},{"unmappedSource",identitySource(node,source,cache)}};
    return QCryptographicHash::hash(QJsonDocument(identity).toJson(QJsonDocument::Compact),QCryptographicHash::Sha256);
}
QByteArray sourceAnchor(const ProxyNode &node) {
    // Only an explicit original-source alias is a provider update key. A Qt
    // display name alone never authorizes replacing another remote endpoint.
    const auto original=node.originalConfiguration;
    QJsonValue tag=node.isXray()?original.value("outbound").toObject().value("tag"):QJsonValue(node.providerAlias);
    if(!node.isXray()&&tag.toString().isEmpty()) {
        tag=original.value("name");
        if(tag.toString().isEmpty())tag=original.value("tag");
        if(tag.toString().isEmpty())tag=original.value("vmess").toObject().value("ps");
        if(tag.toString().isEmpty()&&original.value("uri").isString())tag=QUrl(original.value("uri").toString()).fragment(QUrl::FullyDecoded);
    }
    if(!tag.isString() || tag.toString().isEmpty())return {};
    const auto source=original.value("source").toObject();
    const QJsonArray anchor{node.protocol,tag,source.value("server_index"),source.value("user_index")};
    return QCryptographicHash::hash(QJsonDocument(anchor).toJson(QJsonDocument::Compact),QCryptographicHash::Sha256);
}
}
bool NodeStore::scrubRevokedSources(ImportPlan *plan) {
    if(!configurationV2()||plan->m_removedIds.isEmpty())return true;
    const QSet<QString> removed(plan->m_removedIds.cbegin(),plan->m_removedIds.cend());
    QHash<quintptr,QByteArray> digests;
    const auto digest=[&](const ProxyNode &node){
        const auto buffer=quintptr(node.sourceDocument.constData());
        if(!digests.contains(buffer))digests.insert(buffer,QCryptographicHash::hash(node.sourceDocument,QCryptographicHash::Sha256));
        // Identical bytes from another independently authorized source must not
        // make deleting this source revoke or rewrite that source's nodes.
        return digests.value(buffer)+':'+node.sourceId.toUtf8();
    };
    QHash<QByteArray,QSet<int>> revokedOutbounds;QSet<QString> affectedSources;
    for(const auto &node:m_nodes)if(removed.contains(node.id)){
        affectedSources.insert(node.sourceId);
        if(!node.sourceDocument.isEmpty())revokedOutbounds[digest(node)].insert(node.originalConfiguration.value("source").toObject().value("outbound_index").toInt(-1));
    }
    // Retained inert full profiles may contain deleted credentials. The active
    // policy document remains intact; only these replay-disabled archives go.
    const auto imported=plan->m_network.value("importedConfiguration").toObject();
    if(affectedSources.contains(imported.value("sourceId").toString()))plan->m_network.remove("importedConfiguration");
    auto outcomes=plan->m_network.value("subscriptionImportResults").toObject();
    for(const auto &source:affectedSources)outcomes.remove(source);
    if(outcomes.isEmpty())plan->m_network.remove("subscriptionImportResults");else plan->m_network.insert("subscriptionImportResults",outcomes);
    QHash<QByteArray,QList<qsizetype>> shared;
    for(qsizetype i=0;i<plan->m_nodes.size();++i)if(!plan->m_nodes[i].sourceDocument.isEmpty()){
        const auto key=digest(plan->m_nodes[i]);if(revokedOutbounds.contains(key))shared[key].append(i);
    }
    const auto locator=[](const QJsonObject &source){return QString("%1/%2/%3").arg(source.value("outbound_index").toInt(-1)).arg(source.value("server_index").toInt(-1)).arg(source.value("user_index").toInt(-1));};
    for(auto group=shared.cbegin();group!=shared.cend();++group){
        QMap<int,QJsonObject> retained;
        for(const auto index:group.value()){
            const auto &node=plan->m_nodes[index];const auto source=node.originalConfiguration.value("source").toObject();
            const auto outbound=source.value("outbound_index").toInt(-1);const auto raw=node.originalConfiguration.value("outbound");
            if(outbound<0||!raw.isObject()||revokedOutbounds.value(group.key()).contains(outbound)){
                m_error=QStringLiteral("此共享 JSON 出站包含多个账户，无法安全单独撤销；请删除整个来源，或先按独立出站重新导入。");return false;
            }
            if(retained.contains(outbound)&&retained.value(outbound)!=raw.toObject()){
                m_error=QStringLiteral("共享 JSON 来源位置存在歧义；未删除任何凭据。");return false;
            }
            retained.insert(outbound,raw.toObject());
        }
        QJsonArray outbounds;QHash<int,int> remap;
        for(auto raw=retained.cbegin();raw!=retained.cend();++raw){remap.insert(raw.key(),outbounds.size());outbounds.append(raw.value());}
        const auto isolated=QJsonDocument(QJsonObject{{"outbounds",outbounds}}).toJson(QJsonDocument::Compact);
        const auto checked=XrayJsonBridge::parse(isolated);
        if(!checked||checked.nodes.size()!=group.value().size()){
            m_error=QStringLiteral("无法严格复核保留节点的独立源文档；未提交部分撤销。");return false;
        }
        QHash<QString,ProxyNode> bySource;
        for(const auto &node:checked.nodes){const auto key=locator(node.originalConfiguration.value("source").toObject());
            if(bySource.contains(key)){m_error=QStringLiteral("保留节点来源不唯一；未提交撤销。");return false;}bySource.insert(key,node);
        }
        for(const auto index:group.value()){
            const auto previous=plan->m_nodes[index];auto source=previous.originalConfiguration.value("source").toObject();
            source.insert("outbound_index",remap.value(source.value("outbound_index").toInt(-1),-1));
            const auto key=locator(source);
            if(!bySource.contains(key)||bySource.value(key).nativeOutbound!=previous.nativeOutbound||
               bySource.value(key).originalConfiguration.value("outbound")!=previous.originalConfiguration.value("outbound")){
                m_error=QStringLiteral("保留节点的连接参数不等价；未提交撤销。");return false;
            }
            auto node=bySource.value(key);node.id=previous.id;node.name=previous.name;node.sourceId=previous.sourceId;
            node.importSource=previous.importSource;node.providerAlias=previous.providerAlias;node.sourceFormat=previous.sourceFormat;
            node.certificateVerificationEnforced=previous.certificateVerificationEnforced;plan->m_nodes[index]=std::move(node);
        }
    }
    return true;
}
bool NodeStore::prepareCatalog(const QList<ProxyNode> &nodes,const QString &selected,const QList<NodeSubscription> &sources,const QJsonObject &network,ImportPlan *output) {
    if(!output||!m_healthy||nodes.size()>2000||sources.size()>32){m_error=QStringLiteral("无法准备目录变更；原配置保持不变。");return false;}
    ImportPlan plan;plan.m_owner=this;plan.m_revision=m_revision;plan.m_nodes=nodes;plan.m_selected=selected;
    plan.m_sources=sources;plan.m_network=network;QSet<QString> retained;
    for(const auto &node:nodes)retained.insert(node.id);
    for(const auto &node:m_nodes)if(!retained.contains(node.id))plan.m_removedIds.append(node.id);
    if(!scrubRevokedSources(&plan))return false;
    *output=std::move(plan);m_error.clear();return true;
}
bool NodeStore::prepareImport(const QList<ProxyNode> &incoming,const QString &sourceId,ImportPlan *output) {
    if(!allowMutation())return false;
    if(!output || !m_healthy || incoming.isEmpty() || incoming.size()>2000) {
        m_error=QStringLiteral("无法准备空列表、超过上限的列表或不可读节点库；原配置保持不变。");return false;
    }
    ImportPlan plan;plan.m_owner=this;plan.m_revision=m_revision;plan.m_sources=m_subscriptions;plan.m_network=m_networkConfiguration;
    if(!sourceId.isEmpty()) {
        bool found=false;for(auto &source:plan.m_sources)if(source.id==sourceId){found=true;source.lastSuccess=QDateTime::currentSecsSinceEpoch();}
        if(!found){m_error=QStringLiteral("订阅已移除，已丢弃过期下载响应。");return false;}
    }
    QHash<QByteArray,QList<QString>> existing,anchors,origins;
    IdentityCache identityCache;
    QHash<QString,QByteArray> oldIdentities;
    QSet<QString> allIds,parsedIds;
    for(const auto &old:m_nodes) {
        allIds.insert(old.id);
        if(old.sourceId!=sourceId)continue;
        const auto origin=sourceLocator(old,identityCache);
        const auto identity=semanticIdentity(old,origin,identityCache);existing[identity].append(old.id);oldIdentities.insert(old.id,identity);
        if(!origin.isEmpty())origins[origin].append(old.id);
        const auto anchor=sourceAnchor(old);if(!anchor.isEmpty())anchors[anchor].append(old.id);
    }
    QList<QByteArray> identities,incomingAnchors,incomingOrigins;
    QSet<QByteArray> requested;
    QHash<QByteArray,QSet<QByteArray>> anchorIdentities;
    for(auto node:incoming) {
        m_error=ProxyNode::validate(node);if(!m_error.isEmpty())return false;
        if(parsedIds.contains(node.id)) {m_error=QStringLiteral("导入节点标识重复；原配置保持不变。");return false;}
        parsedIds.insert(node.id);
        if(!sourceId.isEmpty()&&node.providerAlias.isEmpty())node.providerAlias=node.name;
        const auto origin=sourceLocator(node,identityCache);
        const auto identity=semanticIdentity(node,origin,identityCache),anchor=sourceAnchor(node);
        incomingOrigins.append(origin);
        identities.append(identity);incomingAnchors.append(anchor);requested.insert(identity);
        if(!anchor.isEmpty())anchorIdentities[anchor].insert(identity);
    }
    plan.m_nodes=m_nodes;
    if(!sourceId.isEmpty())plan.m_nodes.removeIf([&](const auto &node){return node.sourceId==sourceId;});
    QHash<QByteArray,QString> imported;
    QSet<QString> assigned;
    const auto mapName=[&](const QString &name,const QString &id) {
        if(!plan.m_names.contains(name))plan.m_names.insert(name,id);
        else if(plan.m_names.value(name)!=id)plan.m_names.insert(name,QString()); // Explicit policy ambiguity.
    };
    for(int i=0;i<incoming.size();++i) {
        auto node=incoming[i];const auto parsedId=node.id;const auto identity=identities[i];
        if(!sourceId.isEmpty()&&node.providerAlias.isEmpty())node.providerAlias=node.name;
        if(imported.contains(identity)) {
            const auto id=imported.value(identity);
            if(allIds.contains(parsedId) && parsedId!=id) {m_error=QStringLiteral("导入节点标识与其他节点或订阅冲突；原配置保持不变。");return false;}
            plan.m_ids.insert(parsedId,id);mapName(node.name,id);continue;
        }
        QString matched;
        const auto exact=existing.value(identity);
        if(exact.size()>1) {m_error=QStringLiteral("已有节点存在重复身份，无法安全确定更新目标；原配置保持不变。");return false;}
        if(exact.size()==1)matched=exact.first();
        if(matched.isEmpty() && !incomingOrigins[i].isEmpty()) {
            const auto sameSource=origins.value(incomingOrigins[i]);
            if(sameSource.size()>1) {m_error=QStringLiteral("已有节点源文档位置重复；原配置保持不变。");return false;}
            if(sameSource.size()==1)matched=sameSource.first();
        }
        if(matched.isEmpty() && !sourceId.isEmpty() && !incomingAnchors[i].isEmpty()) {
            const auto candidates=anchors.value(incomingAnchors[i]);
            if(candidates.size()>1 || (!candidates.isEmpty()&&anchorIdentities.value(incomingAnchors[i]).size()>1)) {
                m_error=QStringLiteral("订阅节点别名存在多个更新目标，无法安全同步；原配置保持不变。");return false;
            }
            if(candidates.size()==1 && anchorIdentities.value(incomingAnchors[i]).size()==1 &&
               !requested.contains(oldIdentities.value(candidates.first())))matched=candidates.first();
        }
        if(allIds.contains(parsedId) && parsedId!=matched) {m_error=QStringLiteral("导入节点标识与其他节点或订阅冲突；原配置保持不变。");return false;}
        if(!matched.isEmpty())node.id=matched;
        if(assigned.contains(node.id)) {m_error=QStringLiteral("订阅来源身份不唯一；原配置保持不变。");return false;}
        node.sourceId=sourceId;
        if(!sourceId.isEmpty())node.importSource="subscription";
        else if(node.importSource.isEmpty())node.importSource="manual-import";
        assigned.insert(node.id);imported.insert(identity,node.id);
        plan.m_ids.insert(parsedId,node.id);mapName(node.name,node.id);
        plan.m_nodes.removeIf([&](const auto &old){return old.id==node.id;});plan.m_nodes.append(std::move(node));
    }
    if(plan.m_nodes.size()>2000){m_error=QStringLiteral("导入后超过 2000 个节点；原配置保持不变。");return false;}
    plan.m_selected=m_selected;
    if(std::none_of(plan.m_nodes.cbegin(),plan.m_nodes.cend(),[&](const auto &node){return node.id==plan.m_selected;}))plan.m_selected.clear();
    QSet<QString> retained;for(const auto &node:plan.m_nodes)retained.insert(node.id);
    for(const auto &node:m_nodes)if(!retained.contains(node.id))plan.m_removedIds.append(node.id);
    if(!scrubRevokedSources(&plan))return false;
    *output=std::move(plan);m_error.clear();return true;
}
bool NodeStore::commitImport(const ImportPlan &plan,const QJsonObject &networkConfiguration) {
    if(!allowMutation())return false;
    if(plan.m_owner!=this || plan.m_revision!=m_revision) {
        m_error=QStringLiteral("准备导入后节点库已变更，请重新准备；原配置保持不变。");return false;
    }
    return write(plan.m_nodes,plan.m_selected,plan.m_sources,networkConfiguration.isEmpty()?plan.m_network:networkConfiguration);
}
bool NodeStore::commitImportAsync(const ImportPlan &plan,const QJsonObject &networkConfiguration,
                                  std::function<void(bool,const QString &)> completion) {
    if(!allowMutation())return false;
    if(configurationV2()){m_error=QStringLiteral("V2 节点导入必须通过统一配置事务。");return false;}
    if(!completion || !QCoreApplication::instance() || QThread::currentThread()!=thread() ||
       !m_healthy || plan.m_owner!=this || plan.m_revision!=m_revision) {
        m_error=QStringLiteral("无法异步提交过期计划或不可读节点库；请重新准备导入。");return false;
    }
    if(!acquireConfigurationLock())return false;
    const auto data=std::make_shared<const StoreSnapshot>(StoreSnapshot{plan.m_nodes,plan.m_selected,plan.m_sources,
        networkConfiguration.isEmpty()?plan.m_network:networkConfiguration,m_configurationEnvelope});
    const auto cancelled=std::make_shared<std::atomic_bool>(false);
    m_saveCancelled=cancelled;m_saving=true;m_error.clear();
    const auto revision=m_revision;
    const auto path=m_path;
    const QPointer<NodeStore> owner(this);
    // Keep a tiny dispatch context alive through queued delivery. The worker
    // never dereferences the QPointer; it is read only on the owner's thread.
    // This also avoids an invokeMethod/delete race if the store is destroyed.
    auto dispatch=std::shared_ptr<QObject>(new QObject,[](QObject *object){object->deleteLater();});
    const auto pathLock=m_configurationLock;
    m_configurationLock.reset(); // Legacy async write; worker keeps ownership until atomic commit returns.
    QThreadPool::globalInstance()->start([data,cancelled,revision,path,owner,dispatch,pathLock,completion=std::move(completion)]() mutable {
        QByteArray snapshotDigest;const auto error=persistSnapshot(path,*data,cancelled,&snapshotDigest);
        QMetaObject::invokeMethod(dispatch.get(),[data,cancelled,revision,owner,dispatch,error,snapshotDigest,completion=std::move(completion)] {
            if(!owner)return;
            // The write lease rejects every mutation while the worker runs.
            // These checks protect future changes from publishing stale state.
            if(owner->m_saveCancelled!=cancelled || !owner->m_saving || owner->m_revision!=revision) {
                if(owner->m_saveCancelled==cancelled) {
                    owner->m_saveCancelled.reset();owner->m_saving=false;owner->m_healthy=false;
                    owner->m_error=QStringLiteral("保存计划状态已失效；请重新加载节点库。");
                }
                completion(false,QStringLiteral("保存计划状态已失效；请重新加载节点库。"));return;
            }
            owner->m_saveCancelled.reset();owner->m_saving=false;
            if(error.isEmpty())owner->adoptSnapshot(data->nodes,data->selected,data->subscriptions,data->networkConfiguration,snapshotDigest);
            else owner->m_error=error;
            if(owner)completion(error.isEmpty(),error);
        },Qt::QueuedConnection);
    });
    return true;
}
bool NodeStore::importNodes(QList<ProxyNode> incoming,const QString &sourceId) {
    if(!allowMutation())return false;
    ImportPlan plan;
    return prepareImport(incoming,sourceId,&plan) && commitImport(plan);
}
bool NodeStore::saveNetworkConfiguration(const QJsonObject &configuration) {
    if(!allowMutation())return false;
    if(configuration.isEmpty()){m_error=QStringLiteral("网络配置不能为空。");return false;}
    return write(m_nodes,m_selected,m_subscriptions,configuration);
}

QString NodeStore::configurationRevision() const {
    return m_configurationEnvelope.value("committed").toObject().value("saved_revision").toString("0");
}
QJsonObject NodeStore::configurationReceipt() const {
    auto receipt=m_configurationEnvelope.value("committed").toObject();receipt.remove("snapshot");
    receipt.insert("store_id",m_configurationStoreId);return receipt;
}
QString NodeStore::issueConfigurationRevision() {
    if(m_lastIssuedRevision==std::numeric_limits<quint64>::max()) {
        m_error=QStringLiteral("配置版本已达到上限，未受理修改。");return {};
    }
    return QString::number(++m_lastIssuedRevision);
}
bool NodeStore::acquireConfigurationLock() {
    if(m_configurationLock&&m_configurationLock->isLocked())return true;
    if(!QDir().mkpath(QFileInfo(m_path).absolutePath())){m_error=QStringLiteral("无法创建配置目录。");return false;}
    auto lock=std::make_shared<QLockFile>(m_path+".lock");lock->setStaleLockTime(0);
    if(!lock->tryLock(0)){m_error=QStringLiteral("此配置库正在被另一个 Swirl 窗口使用；未修改文件。");return false;}
    // Loading before lock acquisition is read-only. Recheck that exact encrypted
    // snapshot under the lock before granting any writer or migration authority.
    QFile current(m_path);QByteArray currentDigest;
    if(current.exists()) {
        if(!current.open(QIODevice::ReadOnly)||current.size()>MaximumBytes){m_error=QStringLiteral("无法复核配置库的写入基线；未修改文件。");return false;}
        const auto bytes=current.read(MaximumBytes+1);
        if(bytes.size()>MaximumBytes||current.error()!=QFile::NoError){m_error=QStringLiteral("配置基线读取失败；未修改文件。");return false;}
        currentDigest=QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex();
    }
    if(currentDigest!=m_snapshotDigest){
        m_healthy=false;m_configurationRecoveryRequired=configurationV2();
        m_error=QStringLiteral("配置库已被其他写入者更新；请重新打开后再修改。未覆盖新配置。");return false;
    }
    m_configurationLock=std::move(lock);return true;
}
QJsonObject NodeStore::configurationEnvelope(const QString &requestId,const QString &revision,const QString &digest) const {
    auto envelope=m_configurationEnvelope;
    envelope.insert("schema",2);envelope.insert("store_id",m_configurationStoreId);
    envelope.insert("last_issued_revision",QString::number(m_lastIssuedRevision));
    envelope.insert("committed",QJsonObject{{"saved_revision",revision},{"request_id",requestId},{"plan_digest",digest}});
    envelope.remove("pending");return envelope;
}
bool NodeStore::persistConfigurationState(const QJsonObject &network,const QJsonObject &envelope,
                                          bool adopt,bool retainLease,SaveCompletion completion,const ImportPlan *catalog,bool pendingCatalog) {
    if(!completion||!QCoreApplication::instance()||QThread::currentThread()!=thread()||!m_healthy||m_saveCancelled) {
        m_error=QStringLiteral("配置保存不可用或已有写操作；原配置保持不变。");return false;
    }
    if(catalog&&(catalog->m_owner!=this||catalog->m_revision!=m_revision)){
        m_error=QStringLiteral("目录基线已变化，请重新准备事务。");return false;
    }
    const auto &nodes=adopt&&catalog?catalog->m_nodes:m_nodes;
    const auto &sources=adopt&&catalog?catalog->m_sources:m_subscriptions;
    auto selected=adopt&&catalog?catalog->m_selected:m_selected;
    if(adopt&&network.value("policyDocumentV2").isObject()){
        const auto target=network.value("policyDocumentV2").toObject().value("default_policy").toObject().value("target").toObject();
        selected=target.value("kind")==QJsonValue("node")?target.value("id").toString():QString();
        if(!selected.isEmpty()&&std::none_of(nodes.cbegin(),nodes.cend(),[&](const auto &node){return node.id==selected;}))selected.clear();
    }
    StoreSnapshot state{nodes,selected,sources,network,envelope};
    if(pendingCatalog&&catalog)state.pendingCatalog=std::make_shared<const StoreSnapshot>(StoreSnapshot{
        catalog->m_nodes,catalog->m_selected,catalog->m_sources,envelope.value("pending").toObject().value("network_configuration").toObject(),{}});
    const auto data=std::make_shared<const StoreSnapshot>(std::move(state));
    const auto cancelled=std::make_shared<std::atomic_bool>(false);
    m_saveCancelled=cancelled;m_saving=true;m_configurationLease=true;
    const auto revision=m_revision;const auto path=m_path;const QPointer<NodeStore> owner(this);
    auto dispatch=std::shared_ptr<QObject>(new QObject,[](QObject *object){object->deleteLater();});
    const auto pathLock=m_configurationLock;
    QThreadPool::globalInstance()->start([data,cancelled,revision,path,owner,dispatch,pathLock,adopt,retainLease,completion=std::move(completion)]() mutable {
        QByteArray digest;QJsonObject savedEnvelope;const auto error=persistSnapshot(path,*data,cancelled,&digest,&savedEnvelope);
        QMetaObject::invokeMethod(dispatch.get(),[data,cancelled,revision,owner,dispatch,adopt,retainLease,error,digest,savedEnvelope,completion=std::move(completion)] {
            if(!owner)return;
            if(owner->m_saveCancelled!=cancelled||owner->m_revision!=revision||!owner->m_configurationLease) {
                owner->m_configurationRecoveryRequired=true;owner->m_healthy=false;
                completion(false,QStringLiteral("配置写入结果需恢复；保持断开，未猜测回滚。"));return;
            }
            owner->m_saveCancelled.reset();
            if(error.isEmpty()) {
                owner->m_configurationEnvelope=savedEnvelope;owner->m_snapshotDigest=digest;
                if(adopt) {
                    owner->adoptSnapshot(data->nodes,data->selected,data->subscriptions,data->networkConfiguration,digest);
                    if(!owner)return; // changed() may synchronously destroy the owner.
                }
                else owner->m_error.clear();
            } else owner->m_error=error;
            if(!retainLease){owner->m_saving=false;owner->m_configurationLease=false;}
            completion(error.isEmpty(),error);
        },Qt::QueuedConnection);
    });
    return true;
}
namespace {
bool validConfigurationIdentity(const QString &requestId,const QString &revision,const QString &digest,quint64 issued) {
    bool ok=false;const auto value=revision.toULongLong(&ok);
    return !QUuid(requestId).isNull()&&ok&&value>0&&value<=issued&&QString::number(value)==revision&&
        QRegularExpression("^[0-9a-f]{64}$").match(digest).hasMatch();
}
}
bool NodeStore::saveConfigurationOffline(const QJsonObject &network,const QString &requestId,
                                         const QString &revision,const QString &digest,SaveCompletion completion) {
    if((!m_configurationLease&&!allowMutation())||!validConfigurationIdentity(requestId,revision,digest,m_lastIssuedRevision)||
       revision.toULongLong()<=configurationRevision().toULongLong()||!m_configurationEnvelope.value("pending").toObject().isEmpty()||
       requestId==configurationReceipt().value("request_id").toString()||!acquireConfigurationLock())return false;
    return persistConfigurationState(network,configurationEnvelope(requestId,revision,digest),true,false,std::move(completion));
}
bool NodeStore::beginConfigurationIntent(const QJsonObject &network,const QString &requestId,
                                         const QString &revision,const QString &digest,SaveCompletion completion) {
    if((!m_configurationLease&&!allowMutation())||!configurationV2()||!validConfigurationIdentity(requestId,revision,digest,m_lastIssuedRevision)||
       revision.toULongLong()<=configurationRevision().toULongLong()||requestId==configurationReceipt().value("request_id").toString()||
       !m_configurationEnvelope.value("pending").toObject().isEmpty()||!acquireConfigurationLock())return false;
    auto envelope=m_configurationEnvelope;envelope.insert("last_issued_revision",QString::number(m_lastIssuedRevision));
    envelope.insert("pending",QJsonObject{{"operation","configuration"},{"request_id",requestId},{"base_revision",configurationRevision()},
        {"candidate_revision",revision},{"plan_digest",digest},{"network_configuration",network}});
    return persistConfigurationState(m_networkConfiguration,envelope,false,true,std::move(completion));
}
bool NodeStore::saveCatalogOffline(const ImportPlan &catalog,const QJsonObject &network,const QString &requestId,
                                  const QString &revision,const QString &digest,SaveCompletion completion) {
    if((!m_configurationLease&&!allowMutation())||!configurationV2()||catalog.m_owner!=this||catalog.m_revision!=m_revision||
       !validConfigurationIdentity(requestId,revision,digest,m_lastIssuedRevision)||revision.toULongLong()<=configurationRevision().toULongLong()||
       requestId==configurationReceipt().value("request_id").toString()||!m_configurationEnvelope.value("pending").toObject().isEmpty()||!acquireConfigurationLock())return false;
    return persistConfigurationState(network,configurationEnvelope(requestId,revision,digest),true,false,std::move(completion),&catalog);
}
bool NodeStore::beginCatalogIntent(const ImportPlan &catalog,const QJsonObject &network,const QString &requestId,
                                 const QString &revision,const QString &digest,SaveCompletion completion) {
    if((!m_configurationLease&&!allowMutation())||!configurationV2()||catalog.m_owner!=this||catalog.m_revision!=m_revision||
       !validConfigurationIdentity(requestId,revision,digest,m_lastIssuedRevision)||revision.toULongLong()<=configurationRevision().toULongLong()||
       requestId==configurationReceipt().value("request_id").toString()||!m_configurationEnvelope.value("pending").toObject().isEmpty()||!acquireConfigurationLock())return false;
    auto envelope=m_configurationEnvelope;envelope.insert("last_issued_revision",QString::number(m_lastIssuedRevision));
    envelope.insert("pending",QJsonObject{{"operation",catalog.m_removedIds.isEmpty()?"catalogue":"revoke"},{"request_id",requestId},
        {"base_revision",configurationRevision()},{"candidate_revision",revision},{"plan_digest",digest},
        {"network_configuration",network},{"revoked_node_ids",QJsonArray::fromStringList(catalog.m_removedIds)}});
    m_catalogIntent=catalog;
    const bool queued=persistConfigurationState(m_networkConfiguration,envelope,false,true,
        [this,completion=std::move(completion)](bool ok,const QString &error){if(!ok)m_catalogIntent.reset();completion(ok,error);},&catalog,true);
    if(!queued)m_catalogIntent.reset();return queued;
}
QJsonObject NodeStore::pendingConfigurationReceipt() const {
    auto pending=m_configurationEnvelope.value("pending").toObject();
    pending.remove("network_configuration");pending.remove("catalog_snapshot");
    if(!pending.isEmpty())pending.insert("store_id",m_configurationStoreId);
    return pending;
}
bool NodeStore::configurationRecoveryPlan(ImportPlan *output,QJsonObject *network) {
    const auto pending=m_configurationEnvelope.value("pending").toObject();
    if(!output||!network||m_saveCancelled||pending.value("operation").toString()!="revoke"||
       !pending.value("catalog_snapshot").isObject()||!pending.value("network_configuration").isObject()||
       !pending.value("revoked_node_ids").isArray()||!acquireConfigurationLock()||
       !validConfigurationIdentity(pending.value("request_id").toString(),pending.value("candidate_revision").toString(),pending.value("plan_digest").toString(),m_lastIssuedRevision)||
       pending.value("base_revision").toString()!=configurationRevision()||
       pending.value("candidate_revision").toString().toULongLong()<=configurationRevision().toULongLong()) {
        m_error=QStringLiteral("撤销候选不可验证；保持断开，未恢复旧凭据。");return false;
    }
    auto snapshot=pending.value("catalog_snapshot").toObject();
    if(snapshot.contains("documents")){m_error=QStringLiteral("撤销源文档表存在歧义。");return false;}
    if(m_configurationEnvelope.contains("documents"))snapshot.insert("documents",m_configurationEnvelope.value("documents"));
    ImportPlan plan;
    if(!decodeCatalogSnapshot(snapshot,&plan)||plan.m_network!=pending.value("network_configuration").toObject()){
        m_error=QStringLiteral("撤销候选目录或策略不一致；保持断开。");return false;
    }
    QSet<QString> nextIds;for(const auto &node:plan.m_nodes)nextIds.insert(node.id);
    for(const auto &node:m_nodes)if(!nextIds.contains(node.id))plan.m_removedIds.append(node.id);
    QStringList declared;
    for(const auto &value:pending.value("revoked_node_ids").toArray()){
        if(!value.isString()||QUuid(value.toString()).isNull()||declared.contains(value.toString())){
            m_error=QStringLiteral("撤销节点标识无效；保持断开。");return false;
        }
        declared.append(value.toString());
    }
    auto actual=plan.m_removedIds;std::sort(actual.begin(),actual.end());std::sort(declared.begin(),declared.end());
    if(actual!=declared||actual.isEmpty()){m_error=QStringLiteral("撤销集合与候选目录不一致；保持断开。");return false;}
    *network=plan.m_network;*output=std::move(plan);return true;
}
bool NodeStore::recoverCatalogIntentOffline(const QString &validatedDigest,SaveCompletion completion) {
    ImportPlan plan;QJsonObject network;
    if(!completion||!configurationRecoveryPlan(&plan,&network))return false;
    const auto pending=m_configurationEnvelope.value("pending").toObject();
    if(validatedDigest!=pending.value("plan_digest").toString()){
        m_error=QStringLiteral("撤销候选与内核验证摘要不一致；保持断开。");return false;
    }
    m_healthy=true;m_configurationLease=true;m_saving=true;
    const bool queued=persistConfigurationState(network,
        configurationEnvelope(pending.value("request_id").toString(),pending.value("candidate_revision").toString(),validatedDigest),true,false,
        [this,completion=std::move(completion)](bool ok,const QString &error){
            m_configurationRecoveryRequired=!ok;m_healthy=ok;if(ok)m_catalogIntent.reset();completion(ok,error);
        },&plan);
    if(!queued){m_healthy=false;m_configurationRecoveryRequired=true;m_configurationLease=false;m_saving=false;}
    return queued;
}
bool NodeStore::commitConfigurationIntent(SaveCompletion completion) {
    const auto pending=m_configurationEnvelope.value("pending").toObject();
    if(!m_configurationLease||pending.isEmpty()||m_saveCancelled)return false;
    const auto *catalog=m_catalogIntent?&*m_catalogIntent:nullptr;
    if(pending.value("catalog_snapshot").isObject()&&!catalog){m_error=QStringLiteral("目录撤销需要离线恢复验证；保持断开。");return false;}
    return persistConfigurationState(pending.value("network_configuration").toObject(),
        configurationEnvelope(pending.value("request_id").toString(),pending.value("candidate_revision").toString(),pending.value("plan_digest").toString()),
        true,true,[this,completion=std::move(completion)](bool ok,const QString &error){if(ok)m_catalogIntent.reset();completion(ok,error);},catalog);
}
bool NodeStore::abortConfigurationIntent(SaveCompletion completion) {
    if(!m_configurationLease||m_saveCancelled)return false;
    auto envelope=m_configurationEnvelope;envelope.remove("pending");
    return persistConfigurationState(m_networkConfiguration,envelope,false,true,[this,completion=std::move(completion)](bool ok,const QString &error){if(ok)m_catalogIntent.reset();completion(ok,error);});
}
void NodeStore::releaseConfigurationLease() {
    if(m_saveCancelled)return; // An in-progress atomic write must reach a known result.
    m_configurationLease=false;m_saving=false;
}
bool NodeStore::reserveConfigurationLease() {
    if(!allowMutation()||!m_healthy)return false;
    m_configurationLease=true;m_saving=true;return true;
}
