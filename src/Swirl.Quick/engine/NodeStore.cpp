#include "NodeStore.h"
#include "NodeImporter.h"
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
#include <QRegularExpression>
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
    auto result = QJsonObject::fromVariantMap(n.publicInfo());
    result.remove("capability");result.remove("configurationState");result.remove("normalizationNotes");
    result.remove("regionCode");result.remove("regionName");
    result.remove("hasCredentials"); result.insert("username", n.username); result.insert("password", n.password);
    result.insert("options",n.parameters);
    result.insert("originalConfiguration",n.originalConfiguration);
    return result;
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
QVariantList NodeStore::publicRows() const {
    if(m_publicRows.isEmpty())for(const auto &n:m_nodes)m_publicRows.append(n.publicInfo());
    return m_publicRows;
}
void NodeStore::load() {
    QFile file(m_path);
    if (!file.exists()) return;
    m_healthy=false;
    if (!file.open(QIODevice::ReadOnly) || file.size()>1024*1024) { m_error=QStringLiteral("节点文件无法读取；未覆盖原文件。"); return; }
    auto ciphertext=file.readAll();
    if (!ciphertext.startsWith("SWIRLNODE1\n")) { m_error=QStringLiteral("节点文件格式无效；未覆盖原文件。"); return; }
    auto plaintext=protect(ciphertext.mid(11), true);
    QJsonParseError parse;
    const auto document=QJsonDocument::fromJson(plaintext, &parse); plaintext.fill('\0');
    if (parse.error!=QJsonParseError::NoError || !document.isObject() || document.object().value("schema").toInt()!=1) {
        m_error=QStringLiteral("DPAPI 节点解密失败或文件损坏；请使用保存它的 Windows 用户。原文件未覆盖。"); return;
    }
    const auto array=document.object().value("nodes").toArray();
    if (array.size()>2000) { m_error=QStringLiteral("节点数量超过上限。"); return; }
    QList<ProxyNode> nodes; QSet<QString> ids;
    for (const auto &entry : array) {
        const auto n=deserialize(entry.toObject().toVariantMap());
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
        if(o.contains("importScope") && !o.value("importScope").isString()){m_error=QStringLiteral("保存的订阅导入范围无效；未覆盖原文件。");return;}
        s.importScope=o.value("importScope").toString("full-profile");
        s.intervalMinutes=o.value("interval").toInt();s.enabled=o.value("enabled").toBool();s.lastSuccess=o.value("lastSuccess").toInteger();
        if(QUuid(s.id).isNull() || sourceIds.contains(s.id) || !allowedSubscriptionUrl(s.url) || !subscriptionFormats().contains(s.formatHint) || !subscriptionScopes().contains(s.importScope) || s.name.isEmpty() || s.name.size()>128 || s.intervalMinutes<15 || s.intervalMinutes>10080 || subscriptions.size()>=32){m_error=QStringLiteral("保存的订阅参数无效；未覆盖原文件。");return;}
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
bool NodeStore::write(const QList<ProxyNode> &nodes, const QString &selected, const QList<NodeSubscription> &subscriptions,const QJsonObject &networkConfiguration) {
    if (!m_healthy) { m_error=QStringLiteral("节点库损坏或无法解密；未覆盖原文件。"); return false; }
    QJsonArray array; for (const auto &n : nodes) array.append(serialize(n));
    QJsonArray sources;
    for(const auto &s:subscriptions)sources.append(QJsonObject{{"id",s.id},{"name",s.name},{"formatHint",s.formatHint},{"importScope",s.importScope},{"url",s.url.toString(QUrl::FullyEncoded)},{"interval",s.intervalMinutes},{"enabled",s.enabled},{"lastSuccess",s.lastSuccess}});
    QJsonObject snapshot{{"schema",1},{"selected",selected},{"nodes",array},{"subscriptions",sources}};
    if(!networkConfiguration.isEmpty()) {
        if(networkConfiguration.value("schema").toInt()!=1){m_error=QStringLiteral("网络配置版本无效。");return false;}
        snapshot.insert("networkConfiguration",networkConfiguration);
    }
    auto plaintext=QJsonDocument(snapshot).toJson(QJsonDocument::Compact);
    const auto encrypted=protect(plaintext, false); plaintext.fill('\0');
    if (encrypted.isEmpty()) { m_error=QStringLiteral("Windows DPAPI 加密失败，未保存任何明文凭据。"); return false; }
    if (!QDir().mkpath(QFileInfo(m_path).absolutePath())) { m_error=QStringLiteral("节点目录无法创建。"); return false; }
    QSaveFile file(m_path); const auto bytes=QByteArray("SWIRLNODE1\n")+encrypted;
    if(bytes.size()>1024*1024) {
        m_error=QStringLiteral("节点库超过 1 MiB 保存上限；旧配置保持不变。"); return false;
    }
    if (!file.open(QIODevice::WriteOnly) || !file.setPermissions(QFile::ReadOwner|QFile::WriteOwner) || file.write(bytes)!=bytes.size() || !file.commit()) {
        m_error=QStringLiteral("节点配置无法安全保存，旧配置保持不变。"); return false;
    }
    m_nodes=nodes; m_publicRows.clear(); m_selected=selected;m_subscriptions=subscriptions;m_networkConfiguration=networkConfiguration; m_error.clear(); ++m_revision; emit changed(); return true;
}
bool NodeStore::saveNode(const QVariantMap &input) {
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
    auto nodes=m_nodes; const auto old=nodes.size(); nodes.removeIf([&](const ProxyNode &n){return n.id==id;});
    if (nodes.size()==old) { m_error=QStringLiteral("节点不存在。"); return false; }
    return write(nodes,m_selected==id ? QString() : m_selected,m_subscriptions,m_networkConfiguration);
}
bool NodeStore::select(const QString &id) {
    if (!id.isEmpty() && std::none_of(m_nodes.begin(),m_nodes.end(),[&](const ProxyNode &n){return n.id==id;})) {
        m_error=QStringLiteral("选择的节点不存在。"); return false;
    }
    if(!m_healthy){m_error=QStringLiteral("节点库无法解密；选择未保存。");return false;}
    if(m_selected==id){m_error.clear();return true;}
    QSaveFile file(m_path+".selected");
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
        rows.append(QVariantMap{{"id",s.id},{"name",s.name},{"formatHint",s.formatHint},{"importScope",s.importScope},{"source",QStringLiteral("订阅地址已加密隐藏")},{"nodes",count},{"intervalMinutes",s.intervalMinutes},{"enabled",s.enabled},
            {"lastSuccess",s.lastSuccess},{"update",s.lastSuccess?QDateTime::fromSecsSinceEpoch(s.lastSuccess).toLocalTime().toString("yyyy-MM-dd HH:mm"):QStringLiteral("尚未成功更新")}});
    }
    return rows;
}
bool NodeStore::saveSubscription(const QString &id,const QString &name,const QUrl &url,int interval,bool enabled,const QString &formatHint,const QString &importScope) {
    auto sources=m_subscriptions;int index=-1;
    for(int i=0;i<sources.size();++i)if(sources[i].id==id)index=i;
    if(!id.isEmpty() && index<0){m_error=QStringLiteral("订阅不存在。");return false;}
    NodeSubscription s=index<0?NodeSubscription{}:sources[index];
    if(s.id.isEmpty())s.id=QUuid::createUuid().toString(QUuid::WithoutBraces);
    s.name=name.trimmed();if(!url.isEmpty())s.url=url;s.intervalMinutes=interval;s.enabled=enabled;
    if(!formatHint.isEmpty())s.formatHint=formatHint;
    if(!importScope.isEmpty())s.importScope=importScope;
    if(!subscriptionFormats().contains(s.formatHint)){m_error=QStringLiteral("订阅格式偏好无效。");return false;}
    if(!subscriptionScopes().contains(s.importScope)){m_error=QStringLiteral("订阅导入范围无效。");return false;}
    if(s.name.isEmpty() || s.name.size()>128 || s.name.contains(QRegularExpression("[\\x00-\\x1f]")) || !allowedSubscriptionUrl(s.url) || interval<15 || interval>10080){m_error=QStringLiteral("需要有效名称、HTTPS 订阅地址及 15–10080 分钟更新间隔（仅本机测试允许 HTTP）。");return false;}
    if(index<0){if(sources.size()>=32){m_error=QStringLiteral("最多保存 32 个订阅。");return false;}sources.append(s);}else sources[index]=s;
    return write(m_nodes,m_selected,sources,m_networkConfiguration);
}
bool NodeStore::removeSubscription(const QString &id) {
    auto sources=m_subscriptions;const auto old=sources.size();sources.removeIf([&](const auto &s){return s.id==id;});
    if(old==sources.size()){m_error=QStringLiteral("订阅不存在。");return false;}
    // Removing a source keeps its already imported nodes as manual nodes.
    auto nodes=m_nodes;for(auto &n:nodes)if(n.sourceId==id)n.sourceId.clear();
    return write(nodes,m_selected,sources,m_networkConfiguration);
}
bool NodeStore::prepareImport(const QList<ProxyNode> &incoming,const QString &sourceId,ImportPlan *output) {
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
    if(plan.m_owner!=this || plan.m_revision!=m_revision) {
        m_error=QStringLiteral("准备导入后节点库已变更，请重新准备；原配置保持不变。");return false;
    }
    return write(plan.m_nodes,plan.m_selected,plan.m_sources,networkConfiguration.isEmpty()?m_networkConfiguration:networkConfiguration);
}
bool NodeStore::importNodes(QList<ProxyNode> incoming,const QString &sourceId) {
    ImportPlan plan;
    return prepareImport(incoming,sourceId,&plan) && commitImport(plan);
}
bool NodeStore::saveNetworkConfiguration(const QJsonObject &configuration) {
    if(configuration.isEmpty()){m_error=QStringLiteral("网络配置不能为空。");return false;}
    return write(m_nodes,m_selected,m_subscriptions,configuration);
}
