#include "NodeStore.h"
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
    result.remove("hasCredentials"); result.insert("username", n.username); result.insert("password", n.password);
    result.insert("options",n.parameters);
    return result;
}
static ProxyNode deserialize(const QVariantMap &m) {
    ProxyNode n; n.id=m.value("id").toString(); n.name=m.value("name").toString().trimmed();
    n.protocol=m.value("protocol").toString(); n.host=m.value("host").toString().trimmed();
    const auto port=m.value("port").toInt(); n.port=port>0 && port<=65535 ? quint16(port) : 0;
    n.username=m.value("username").toString(); n.password=m.value("password").toString();
    n.cipher=m.value("cipher").toString(); n.serverName=m.value("serverName").toString().trimmed();
    n.parameters=QJsonObject::fromVariantMap(m.value("options").toMap());n.sourceId=m.value("sourceId").toString();
    if(n.cipher.isEmpty())n.cipher=n.parameters.value("cipher").toString();
    return n;
}
NodeStore::NodeStore(QString path, QObject *parent) : QObject(parent), m_path(std::move(path)) {
    if (m_path.isEmpty()) m_path=QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation)+"/nodes.dpapi";
    load();
}
QVariantList NodeStore::publicRows() const {
    QVariantList result; for (const auto &n : m_nodes) result.append(n.publicInfo()); return result;
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
        s.intervalMinutes=o.value("interval").toInt();s.enabled=o.value("enabled").toBool();s.lastSuccess=o.value("lastSuccess").toInteger();
        if(QUuid(s.id).isNull() || sourceIds.contains(s.id) || !allowedSubscriptionUrl(s.url) || s.name.isEmpty() || s.name.size()>128 || s.intervalMinutes<15 || s.intervalMinutes>10080 || subscriptions.size()>=32){m_error=QStringLiteral("保存的订阅参数无效；未覆盖原文件。");return;}
        sourceIds.insert(s.id);subscriptions.append(s);
    }
    for(const auto &n:nodes)if(!n.sourceId.isEmpty() && !sourceIds.contains(n.sourceId)){m_error=QStringLiteral("节点订阅归属无效；未覆盖原文件。");return;}
    m_nodes=nodes; m_selected=selected; m_subscriptions=subscriptions;m_healthy=true;
}
bool NodeStore::write(const QList<ProxyNode> &nodes, const QString &selected, const QList<NodeSubscription> &subscriptions) {
    if (!m_healthy) { m_error=QStringLiteral("节点库损坏或无法解密；未覆盖原文件。"); return false; }
    QJsonArray array; for (const auto &n : nodes) array.append(serialize(n));
    QJsonArray sources;
    for(const auto &s:subscriptions)sources.append(QJsonObject{{"id",s.id},{"name",s.name},{"url",s.url.toString(QUrl::FullyEncoded)},{"interval",s.intervalMinutes},{"enabled",s.enabled},{"lastSuccess",s.lastSuccess}});
    auto plaintext=QJsonDocument(QJsonObject{{"schema",1},{"selected",selected},{"nodes",array},{"subscriptions",sources}}).toJson(QJsonDocument::Compact);
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
    m_nodes=nodes; m_selected=selected;m_subscriptions=subscriptions; m_error.clear(); emit changed(); return true;
}
bool NodeStore::saveNode(const QVariantMap &input) {
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
    if(index>=0)n.sourceId=nodes[index].sourceId;
    if(index>=0 && n.protocol==nodes[index].protocol && n.protocol!="ss" && n.cipher.isEmpty())n.cipher=nodes[index].cipher;
    m_error=ProxyNode::validate(n); if (!m_error.isEmpty()) return false;
    if (index<0) { if (nodes.size()>=2000) { m_error=QStringLiteral("最多保存 2000 个节点。"); return false; } nodes.append(n); }
    else nodes[index]=n;
    return write(nodes,m_selected,m_subscriptions);
}
bool NodeStore::removeNode(const QString &id) {
    auto nodes=m_nodes; const auto old=nodes.size(); nodes.removeIf([&](const ProxyNode &n){return n.id==id;});
    if (nodes.size()==old) { m_error=QStringLiteral("节点不存在。"); return false; }
    return write(nodes,m_selected==id ? QString() : m_selected,m_subscriptions);
}
bool NodeStore::select(const QString &id) {
    if (!id.isEmpty() && std::none_of(m_nodes.begin(),m_nodes.end(),[&](const ProxyNode &n){return n.id==id;})) {
        m_error=QStringLiteral("选择的节点不存在。"); return false;
    }
    return write(m_nodes,id,m_subscriptions);
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
        rows.append(QVariantMap{{"id",s.id},{"name",s.name},{"source",QStringLiteral("订阅地址已加密隐藏")},{"nodes",count},{"intervalMinutes",s.intervalMinutes},{"enabled",s.enabled},
            {"lastSuccess",s.lastSuccess},{"update",s.lastSuccess?QDateTime::fromSecsSinceEpoch(s.lastSuccess).toLocalTime().toString("yyyy-MM-dd HH:mm"):QStringLiteral("尚未成功更新")}});
    }
    return rows;
}
bool NodeStore::saveSubscription(const QString &id,const QString &name,const QUrl &url,int interval,bool enabled) {
    auto sources=m_subscriptions;int index=-1;
    for(int i=0;i<sources.size();++i)if(sources[i].id==id)index=i;
    if(!id.isEmpty() && index<0){m_error=QStringLiteral("订阅不存在。");return false;}
    NodeSubscription s=index<0?NodeSubscription{}:sources[index];
    if(s.id.isEmpty())s.id=QUuid::createUuid().toString(QUuid::WithoutBraces);
    s.name=name.trimmed();if(!url.isEmpty())s.url=url;s.intervalMinutes=interval;s.enabled=enabled;
    if(s.name.isEmpty() || s.name.size()>128 || s.name.contains(QRegularExpression("[\\x00-\\x1f]")) || !allowedSubscriptionUrl(s.url) || interval<15 || interval>10080){m_error=QStringLiteral("需要有效名称、HTTPS 订阅地址及 15–10080 分钟更新间隔（仅本机测试允许 HTTP）。");return false;}
    if(index<0){if(sources.size()>=32){m_error=QStringLiteral("最多保存 32 个订阅。");return false;}sources.append(s);}else sources[index]=s;
    return write(m_nodes,m_selected,sources);
}
bool NodeStore::removeSubscription(const QString &id) {
    auto sources=m_subscriptions;const auto old=sources.size();sources.removeIf([&](const auto &s){return s.id==id;});
    if(old==sources.size()){m_error=QStringLiteral("订阅不存在。");return false;}
    // Removing a source keeps its already imported nodes as manual nodes.
    auto nodes=m_nodes;for(auto &n:nodes)if(n.sourceId==id)n.sourceId.clear();
    return write(nodes,m_selected,sources);
}
bool NodeStore::importNodes(QList<ProxyNode> incoming,const QString &sourceId) {
    if(incoming.isEmpty()){m_error=QStringLiteral("导入列表为空，原节点保持不变。");return false;}
    auto sources=m_subscriptions;
    if(!sourceId.isEmpty()) {
        bool found=false;for(auto &s:sources)if(s.id==sourceId){found=true;s.lastSuccess=QDateTime::currentSecsSinceEpoch();}
        if(!found){m_error=QStringLiteral("订阅已移除，已丢弃过期响应。");return false;}
    }
    auto nodes=m_nodes;
    if(!sourceId.isEmpty())nodes.removeIf([&](const auto &n){return n.sourceId==sourceId;});
    for(auto n:incoming) {
        m_error=ProxyNode::validate(n);if(!m_error.isEmpty())return false;
        n.sourceId=sourceId;
        for(const auto &old:m_nodes)if(old.sourceId==sourceId && old.name==n.name && old.protocol==n.protocol){n.id=old.id;break;}
        nodes.removeIf([&](const auto &old){return old.id==n.id;});nodes.append(n);
    }
    if(nodes.size()>2000){m_error=QStringLiteral("导入后超过 2000 个节点；原节点保持不变。");return false;}
    QString selected=m_selected;
    if(std::none_of(nodes.cbegin(),nodes.cend(),[&](const auto &n){return n.id==selected;}))selected.clear();
    return write(nodes,selected,sources);
}
