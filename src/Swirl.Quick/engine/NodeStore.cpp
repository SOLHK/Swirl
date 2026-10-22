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
#include <QFileInfo>
#include <QDateTime>
#include <QCryptographicHash>
#include <QRegularExpression>
#include <QCoreApplication>
#include <QPointer>
#include <QThread>
#include <QThreadPool>
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
            {"sourceId",n.sourceId},{"sourceFormat",n.sourceFormat},{"importSource",n.importSource},
            {"transportType",n.transportType},{"securityType",n.securityType},
            {"conversionIssues",QJsonArray::fromStringList(n.conversionIssues)}};
    }
    // Explicit private persistence schema: adding a UI role must never cause
    // executable capability caches or other derived flags to become authority.
    return {{"id",n.id},{"name",n.name},{"protocol",n.protocol},{"host",n.host},{"port",n.port},
        {"username",n.username},{"password",n.password},{"cipher",n.cipher},{"serverName",n.serverName},
        {"sourceId",n.sourceId},{"sourceFormat",n.sourceFormat},{"importSource",n.importSource},
        {"options",n.parameters},{"originalConfiguration",n.originalConfiguration},
        {"conversionIssues",QJsonArray::fromStringList(n.conversionIssues)}};
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
    n.importSource=m.value("importSource").toString();
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
    load();
    // Non-secret selection sidecar. Invalid/stale IDs never override the store.
    QFile selection(m_path+".selected");
    if(m_healthy && selection.open(QIODevice::ReadOnly) && selection.size()<=256) {
        const auto object=QJsonDocument::fromJson(selection.readAll()).object();
        const auto id=object.value("selected").toString();
        if(object.contains("selected") && (id.isEmpty() || std::any_of(m_nodes.cbegin(),m_nodes.cend(),[&](const auto &n){return n.id==id;})))m_selected=id;
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
    if(m_publicRows.isEmpty())for(const auto &n:m_nodes)m_publicRows.append(n.publicInfo());
    return m_publicRows;
}
void NodeStore::load() {
    QFile file(m_path);
    if (!file.exists()) return;
    m_healthy=false;
    if (!file.open(QIODevice::ReadOnly) || file.size()>MaximumBytes) { m_error=QStringLiteral("节点文件无法读取或超过 32 MiB；未覆盖原文件。"); return; }
    auto ciphertext=file.read(MaximumBytes+1);
    if(ciphertext.size()>MaximumBytes || file.error()!=QFile::NoError) {m_error=QStringLiteral("节点文件读取失败或超过上限；未覆盖原文件。");return;}
    if (!ciphertext.startsWith("SWIRLNODE1\n")) { m_error=QStringLiteral("节点文件格式无效；未覆盖原文件。"); return; }
    auto plaintext=protect(ciphertext.mid(11), true);
    if(plaintext.isEmpty() || plaintext.size()>MaximumBytes) {plaintext.fill('\0');m_error=QStringLiteral("节点解密失败或超过上限；原文件保持不变。");return;}
    QJsonParseError parse;
    const auto document=QJsonDocument::fromJson(plaintext, &parse); plaintext.fill('\0');
    if (parse.error!=QJsonParseError::NoError || !document.isObject() || document.object().value("schema").toInt()!=1) {
        m_error=QStringLiteral("DPAPI 节点解密失败或文件损坏；请使用保存它的 Windows 用户。原文件未覆盖。"); return;
    }
    const auto snapshot=document.object();
    const int catalogVersion=snapshot.value("catalogVersion").toInt(1);
    if((catalogVersion!=1 && catalogVersion!=2) || !snapshot.value("nodes").isArray() ||
       !snapshot.value("selected").isString() ||
       (snapshot.contains("subscriptions") && !snapshot.value("subscriptions").isArray())) {
        m_error=QStringLiteral("节点库版本或结构无效；原文件保持不变。");return;
    }
    // Store one exact byte sequence per document, even when it yielded 2000
    // nodes. QByteArray copies below remain implicitly shared in memory.
    QHash<QString,QByteArray> originals;
    const auto storedDocuments=snapshot.value("documents");
    if(!storedDocuments.isUndefined() && !storedDocuments.isObject()) {m_error=QStringLiteral("保存的源文档表无效。");return;}
    const auto documents=storedDocuments.toObject();
    if(documents.size()>2000) {m_error=QStringLiteral("保存的源文档数量超过上限。");return;}
    static const QRegularExpression digestPattern(QStringLiteral("^[0-9a-f]{64}$"));
    qsizetype originalBytes=0;
    for(auto it=documents.begin();it!=documents.end();++it) {
        if(!digestPattern.match(it.key()).hasMatch() || !it.value().isString() ||
           it.value().toString().size()>((NodeImporter::MaximumBytes+2)/3)*4) {
            m_error=QStringLiteral("保存的源文档标识或大小无效。");return;
        }
        auto decoded=QByteArray::fromBase64Encoding(it.value().toString().toLatin1(),QByteArray::AbortOnBase64DecodingErrors);
        if(!decoded || decoded.decoded.isEmpty() || decoded.decoded.size()>NodeImporter::MaximumBytes ||
           QCryptographicHash::hash(decoded.decoded,QCryptographicHash::Sha256).toHex()!=it.key().toLatin1()) {
            m_error=QStringLiteral("保存的源文档校验失败；原文件保持不变。");return;
        }
        originalBytes+=decoded.decoded.size();
        if(originalBytes>MaximumBytes) {m_error=QStringLiteral("保存的源文档超过总大小上限。");return;}
        originals.insert(it.key(),std::move(decoded.decoded));
    }
    const auto array=snapshot.value("nodes").toArray();
    if (array.size()>2000) { m_error=QStringLiteral("节点数量超过上限。"); return; }
    QHash<QString,QHash<int,ProxyNode>> replayedDocuments;
    QList<ProxyNode> nodes; QSet<QString> ids;
    for (const auto &entry : array) {
        if(!entry.isObject()) {m_error=QStringLiteral("保存的节点结构无效。");return;}
        const auto object=entry.toObject();
        auto n=deserialize(object.toVariantMap());
        if(object.contains("sourceDocumentRef")) {
            const auto reference=object.value("sourceDocumentRef");
            const auto index=object.value("sourceNodeIndex");
            if(!reference.isString() || !originals.contains(reference.toString()) ||
               !index.isDouble() || index.toDouble()!=index.toInt(-1) || index.toInt(-1)<0 || index.toInt()>=2000) {
                m_error=QStringLiteral("保存的节点源文档引用无效；原文件保持不变。");return;
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
                n.id=saved.id;n.name=saved.name;n.sourceId=saved.sourceId;n.importSource=saved.importSource;
                n.sourceDocument=saved.sourceDocument;n.sourceNodeIndex=saved.sourceNodeIndex;
            } else {
                // A missing/new DLL or failed revalidation must disable the
                // affected node, never erase an otherwise intact catalog.
                n.nativeOutbound={};n.nativeExecutable=false;n.parameterState="unverified";
                n.runtimeIssues={QStringLiteral("SavedXraySourceRevalidationFailed")};
            }
        } else if(object.contains("sourceNodeIndex")) {
            m_error=QStringLiteral("保存的节点缺少源文档引用。");return;
        }
        if (!ProxyNode::validate(n).isEmpty() || ids.contains(n.id)) { m_error=QStringLiteral("保存的节点参数无效；未覆盖原文件。"); return; }
        ids.insert(n.id); nodes.append(n);
    }
    const auto selected=document.object().value("selected").toString();
    if (!selected.isEmpty() && !ids.contains(selected)) { m_error=QStringLiteral("保存的选择无效。"); return; }
    QList<NodeSubscription> subscriptions; QSet<QString> sourceIds;
    for(const auto &entry:document.object().value("subscriptions").toArray()) {
        const auto o=entry.toObject();NodeSubscription s;
        s.id=o.value("id").toString();s.name=o.value("name").toString();s.url=QUrl(o.value("url").toString());
        s.formatHint=o.value("formatHint").toString("auto");
        s.intervalMinutes=o.value("interval").toInt();s.enabled=o.value("enabled").toBool();s.lastSuccess=o.value("lastSuccess").toInteger();
        if(QUuid(s.id).isNull() || sourceIds.contains(s.id) || !allowedSubscriptionUrl(s.url) || !subscriptionFormats().contains(s.formatHint) || s.name.isEmpty() || s.name.size()>128 || s.intervalMinutes<15 || s.intervalMinutes>10080 || subscriptions.size()>=32){m_error=QStringLiteral("保存的订阅参数无效；未覆盖原文件。");return;}
        sourceIds.insert(s.id);subscriptions.append(s);
    }
    for(const auto &n:nodes)if(!n.sourceId.isEmpty() && !sourceIds.contains(n.sourceId)){m_error=QStringLiteral("节点订阅归属无效；未覆盖原文件。");return;}
    const auto network=document.object().value("networkConfiguration");
    if(!network.isUndefined() && (!network.isObject() || network.toObject().value("schema").toInt()!=1)) {
        m_error=QStringLiteral("保存的网络配置无效；原文件保持不变。");return;
    }
    m_networkConfiguration=network.toObject();
    m_nodes=nodes; m_selected=selected; m_subscriptions=subscriptions;m_healthy=true;
}
namespace {
struct StoreSnapshot {
    QList<ProxyNode> nodes;
    QString selected;
    QList<NodeSubscription> subscriptions;
    QJsonObject networkConfiguration;
};
// This function owns every serializer, DPAPI buffer and QSaveFile it uses. It
// receives only value snapshots, so an asynchronous save never accesses a
// NodeStore or another QObject belonging to the UI thread.
QString persistSnapshot(const QString &path,const StoreSnapshot &data,
                        const std::shared_ptr<std::atomic_bool> &cancel = {}) {
    const auto cancelled=[&] {return cancel && cancel->load(std::memory_order_acquire);};
    if(cancelled())return QStringLiteral("节点保存已取消；原配置保持不变。");
    const auto &nodes=data.nodes;
    const auto &selected=data.selected;
    const auto &subscriptions=data.subscriptions;
    const auto &networkConfiguration=data.networkConfiguration;
    if(nodes.size()>2000 || subscriptions.size()>32) {return QStringLiteral("节点或订阅数量超过保存上限。");}
    QJsonArray array;QJsonObject documents;QHash<quintptr,QString> documentIds;qsizetype privateBytes=0;
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
    for(const auto &s:subscriptions)sources.append(QJsonObject{{"id",s.id},{"name",s.name},{"formatHint",s.formatHint},{"url",s.url.toString(QUrl::FullyEncoded)},{"interval",s.intervalMinutes},{"enabled",s.enabled},{"lastSuccess",s.lastSuccess}});
    QJsonObject snapshot{{"schema",1},{"catalogVersion",2},{"selected",selected},{"nodes",array},{"subscriptions",sources}};
    if(!documents.isEmpty())snapshot.insert("documents",documents);
    if(!networkConfiguration.isEmpty()) {
        if(networkConfiguration.value("schema").toInt()!=1){return QStringLiteral("网络配置版本无效。");}
        snapshot.insert("networkConfiguration",networkConfiguration);
    }
    auto plaintext=QJsonDocument(snapshot).toJson(QJsonDocument::Compact);
    if(plaintext.size()>NodeStore::MaximumBytes) {plaintext.fill('\0');return QStringLiteral("节点库超过 32 MiB 保存上限；旧配置保持不变。");}
    if(cancelled()) {plaintext.fill('\0');return QStringLiteral("节点保存已取消；原配置保持不变。");}
    const auto encrypted=protect(plaintext, false); plaintext.fill('\0');
    if(cancelled())return QStringLiteral("节点保存已取消；原配置保持不变。");
    if (encrypted.isEmpty()) { return QStringLiteral("Windows DPAPI 加密失败，未保存任何明文凭据。"); }
    if (!QDir().mkpath(QFileInfo(path).absolutePath())) { return QStringLiteral("节点目录无法创建。"); }
    QSaveFile file(path); const auto bytes=QByteArray("SWIRLNODE1\n")+encrypted;
    file.setDirectWriteFallback(false);
    if(bytes.size()>NodeStore::MaximumBytes) {
        return QStringLiteral("节点库超过 32 MiB 保存上限；旧配置保持不变。");
    }
    if (!file.open(QIODevice::WriteOnly) || !file.setPermissions(QFile::ReadOwner|QFile::WriteOwner) || file.write(bytes)!=bytes.size() || cancelled() || !file.commit()) {
        return QStringLiteral("节点配置无法安全保存，旧配置保持不变。");
    }
    return {};
}
}
void NodeStore::adoptSnapshot(const QList<ProxyNode> &nodes,const QString &selected,
                              const QList<NodeSubscription> &subscriptions,const QJsonObject &networkConfiguration) {
    m_nodes=nodes;m_publicRows.clear();m_selected=selected;m_subscriptions=subscriptions;
    m_networkConfiguration=networkConfiguration;m_error.clear();++m_revision;emit changed();
}
bool NodeStore::write(const QList<ProxyNode> &nodes,const QString &selected,
                      const QList<NodeSubscription> &subscriptions,const QJsonObject &networkConfiguration) {
    if(!allowMutation())return false;
    if(!m_healthy) {m_error=QStringLiteral("节点库损坏或无法解密；未覆盖原文件。");return false;}
    m_error=persistSnapshot(m_path,{nodes,selected,subscriptions,networkConfiguration});
    if(!m_error.isEmpty())return false;
    adoptSnapshot(nodes,selected,subscriptions,networkConfiguration);return true;
}
bool NodeStore::saveNode(const QVariantMap &input) {
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
        nodes[index]=std::move(renamed);return write(nodes,m_selected,m_subscriptions,m_networkConfiguration);
    }
    if (index>=0 && n.protocol==nodes[index].protocol && !input.value("replaceCredentials").toBool()) {
        if (n.password.isEmpty()) n.password=nodes[index].password;
        if (n.username.isEmpty()) n.username=nodes[index].username;
        if(!input.contains("options"))n.parameters=nodes[index].parameters;
        else {auto merged=nodes[index].parameters;for(auto it=n.parameters.begin();it!=n.parameters.end();++it)merged.insert(it.key(),it.value());n.parameters=merged;}
    }
    if(index>=0){n.sourceId=nodes[index].sourceId;n.sourceFormat=nodes[index].sourceFormat;n.originalConfiguration=nodes[index].originalConfiguration;n.conversionIssues=nodes[index].conversionIssues;}
    if(index>=0 && n.protocol==nodes[index].protocol && n.protocol!="ss" && n.cipher.isEmpty())n.cipher=nodes[index].cipher;
    m_error=ProxyNode::validate(n); if (!m_error.isEmpty()) return false;
    if (index<0) { if (nodes.size()>=2000) { m_error=QStringLiteral("最多保存 2000 个节点。"); return false; } nodes.append(n); }
    else nodes[index]=n;
    return write(nodes,m_selected,m_subscriptions,m_networkConfiguration);
}
bool NodeStore::removeNode(const QString &id) {
    if(!allowMutation())return false;
    auto nodes=m_nodes; const auto old=nodes.size(); nodes.removeIf([&](const ProxyNode &n){return n.id==id;});
    if (nodes.size()==old) { m_error=QStringLiteral("节点不存在。"); return false; }
    return write(nodes,m_selected==id ? QString() : m_selected,m_subscriptions,m_networkConfiguration);
}
bool NodeStore::select(const QString &id) {
    if(!allowMutation())return false;
    if (!id.isEmpty() && std::none_of(m_nodes.begin(),m_nodes.end(),[&](const ProxyNode &n){return n.id==id;})) {
        m_error=QStringLiteral("选择的节点不存在。"); return false;
    }
    if(!m_healthy){m_error=QStringLiteral("节点库无法解密；选择未保存。");return false;}
    if(m_selected==id){m_error.clear();return true;}
    QSaveFile file(m_path+".selected");
    file.setDirectWriteFallback(false);
    const auto bytes=QJsonDocument(QJsonObject{{"selected",id}}).toJson(QJsonDocument::Compact);
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
        rows.append(QVariantMap{{"id",s.id},{"name",s.name},{"formatHint",s.formatHint},{"source",QStringLiteral("订阅地址已加密隐藏")},{"nodes",count},{"intervalMinutes",s.intervalMinutes},{"enabled",s.enabled},
            {"lastSuccess",s.lastSuccess},{"update",s.lastSuccess?QDateTime::fromSecsSinceEpoch(s.lastSuccess).toLocalTime().toString("yyyy-MM-dd HH:mm"):QStringLiteral("尚未成功更新")}});
    }
    return rows;
}
bool NodeStore::saveSubscription(const QString &id,const QString &name,const QUrl &url,int interval,bool enabled,const QString &formatHint) {
    if(!allowMutation())return false;
    auto sources=m_subscriptions;int index=-1;
    for(int i=0;i<sources.size();++i)if(sources[i].id==id)index=i;
    if(!id.isEmpty() && index<0){m_error=QStringLiteral("订阅不存在。");return false;}
    NodeSubscription s=index<0?NodeSubscription{}:sources[index];
    if(s.id.isEmpty())s.id=QUuid::createUuid().toString(QUuid::WithoutBraces);
    s.name=name.trimmed();if(!url.isEmpty())s.url=url;s.intervalMinutes=interval;s.enabled=enabled;
    if(!formatHint.isEmpty())s.formatHint=formatHint;
    if(!subscriptionFormats().contains(s.formatHint)){m_error=QStringLiteral("订阅格式偏好无效。");return false;}
    if(s.name.isEmpty() || s.name.size()>128 || s.name.contains(QRegularExpression("[\\x00-\\x1f]")) || !allowedSubscriptionUrl(s.url) || interval<15 || interval>10080){m_error=QStringLiteral("需要有效名称、HTTPS 订阅地址及 15–10080 分钟更新间隔（仅本机测试允许 HTTP）。");return false;}
    if(index<0){if(sources.size()>=32){m_error=QStringLiteral("最多保存 32 个订阅。");return false;}sources.append(s);}else sources[index]=s;
    return write(m_nodes,m_selected,sources,m_networkConfiguration);
}
bool NodeStore::removeSubscription(const QString &id) {
    if(!allowMutation())return false;
    auto sources=m_subscriptions;const auto old=sources.size();sources.removeIf([&](const auto &s){return s.id==id;});
    if(old==sources.size()){m_error=QStringLiteral("订阅不存在。");return false;}
    // Removing a source keeps its already imported nodes as manual nodes.
    auto nodes=m_nodes;for(auto &n:nodes)if(n.sourceId==id)n.sourceId.clear();
    return write(nodes,m_selected,sources,m_networkConfiguration);
}
bool NodeStore::prepareImport(const QList<ProxyNode> &incoming,const QString &sourceId,ImportPlan *output) {
    if(!allowMutation())return false;
    if(!output || !m_healthy || incoming.isEmpty()) {
        m_error=QStringLiteral("无法准备空列表或不可读节点库；原配置保持不变。");return false;
    }
    ImportPlan plan;plan.m_owner=this;plan.m_revision=m_revision;plan.m_sources=m_subscriptions;
    if(!sourceId.isEmpty()) {
        bool found=false;for(auto &source:plan.m_sources)if(source.id==sourceId){found=true;source.lastSuccess=QDateTime::currentSecsSinceEpoch();}
        if(!found){m_error=QStringLiteral("订阅已移除，已丢弃过期下载响应。");return false;}
    }
    plan.m_nodes=m_nodes;
    if(!sourceId.isEmpty())plan.m_nodes.removeIf([&](const auto &node){return node.sourceId==sourceId;});
    QSet<QString> assigned;
    for(auto node:incoming) {
        m_error=ProxyNode::validate(node);if(!m_error.isEmpty())return false;
        const auto parsedId=node.id;
        if(plan.m_names.contains(node.name) || plan.m_ids.contains(parsedId)) {
            m_error=QStringLiteral("导入含重复节点名称或标识，无法唯一映射策略；原配置保持不变。");return false;
        }
        node.sourceId=sourceId;
        int matches=0;
        for(const auto &old:m_nodes)if(old.sourceId==sourceId && old.name==node.name && old.protocol==node.protocol){node.id=old.id;++matches;}
        if(matches>1 || assigned.contains(node.id)) {
            m_error=QStringLiteral("已有节点身份不唯一；原配置保持不变。");return false;
        }
        // Never let a supplied UUID replace an unrelated node/source.
        for(const auto &old:m_nodes)if(old.id==node.id &&
            (old.sourceId!=sourceId || old.name!=node.name || old.protocol!=node.protocol)) {
            m_error=QStringLiteral("导入节点标识与其他节点冲突；原配置保持不变。");return false;
        }
        assigned.insert(node.id);plan.m_names.insert(node.name,node.id);plan.m_ids.insert(parsedId,node.id);
        plan.m_nodes.removeIf([&](const auto &old){return old.id==node.id;});plan.m_nodes.append(node);
    }
    if(plan.m_nodes.size()>2000){m_error=QStringLiteral("导入后超过 2000 个节点；原配置保持不变。");return false;}
    plan.m_selected=m_selected;
    if(std::none_of(plan.m_nodes.cbegin(),plan.m_nodes.cend(),[&](const auto &node){return node.id==plan.m_selected;}))plan.m_selected.clear();
    *output=std::move(plan);m_error.clear();return true;
}
bool NodeStore::commitImport(const ImportPlan &plan,const QJsonObject &networkConfiguration) {
    if(!allowMutation())return false;
    if(plan.m_owner!=this || plan.m_revision!=m_revision) {
        m_error=QStringLiteral("准备导入后节点库已变更，请重新准备；原配置保持不变。");return false;
    }
    return write(plan.m_nodes,plan.m_selected,plan.m_sources,networkConfiguration.isEmpty()?m_networkConfiguration:networkConfiguration);
}
bool NodeStore::commitImportAsync(const ImportPlan &plan,const QJsonObject &networkConfiguration,
                                  std::function<void(bool,const QString &)> completion) {
    if(!allowMutation())return false;
    if(!completion || !QCoreApplication::instance() || QThread::currentThread()!=thread() ||
       !m_healthy || plan.m_owner!=this || plan.m_revision!=m_revision) {
        m_error=QStringLiteral("无法异步提交过期计划或不可读节点库；请重新准备导入。");return false;
    }
    const auto data=std::make_shared<const StoreSnapshot>(StoreSnapshot{plan.m_nodes,plan.m_selected,plan.m_sources,
        networkConfiguration.isEmpty()?m_networkConfiguration:networkConfiguration});
    const auto cancelled=std::make_shared<std::atomic_bool>(false);
    m_saveCancelled=cancelled;m_saving=true;m_error.clear();
    const auto revision=m_revision;
    const auto path=m_path;
    const QPointer<NodeStore> owner(this);
    // Keep a tiny dispatch context alive through queued delivery. The worker
    // never dereferences the QPointer; it is read only on the owner's thread.
    // This also avoids an invokeMethod/delete race if the store is destroyed.
    auto dispatch=std::shared_ptr<QObject>(new QObject,[](QObject *object){object->deleteLater();});
    QThreadPool::globalInstance()->start([data,cancelled,revision,path,owner,dispatch,completion=std::move(completion)]() mutable {
        const auto error=persistSnapshot(path,*data,cancelled);
        QMetaObject::invokeMethod(dispatch.get(),[data,cancelled,revision,owner,dispatch,error,completion=std::move(completion)] {
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
            if(error.isEmpty())owner->adoptSnapshot(data->nodes,data->selected,data->subscriptions,data->networkConfiguration);
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
