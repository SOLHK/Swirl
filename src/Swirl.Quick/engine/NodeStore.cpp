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
    return result;
}
static ProxyNode deserialize(const QVariantMap &m) {
    ProxyNode n; n.id=m.value("id").toString(); n.name=m.value("name").toString().trimmed();
    n.protocol=m.value("protocol").toString(); n.host=m.value("host").toString().trimmed();
    const auto port=m.value("port").toInt(); n.port=port>0 && port<=65535 ? quint16(port) : 0;
    n.username=m.value("username").toString(); n.password=m.value("password").toString();
    n.cipher=m.value("cipher").toString(); n.serverName=m.value("serverName").toString().trimmed();
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
    if (array.size()>100) { m_error=QStringLiteral("节点数量超过上限。"); return; }
    QList<ProxyNode> nodes; QSet<QString> ids;
    for (const auto &entry : array) {
        const auto n=deserialize(entry.toObject().toVariantMap());
        if (!ProxyNode::validate(n).isEmpty() || ids.contains(n.id)) { m_error=QStringLiteral("保存的节点参数无效；未覆盖原文件。"); return; }
        ids.insert(n.id); nodes.append(n);
    }
    const auto selected=document.object().value("selected").toString();
    if (!selected.isEmpty() && !ids.contains(selected)) { m_error=QStringLiteral("保存的选择无效。"); return; }
    m_nodes=nodes; m_selected=selected; m_healthy=true;
}
bool NodeStore::write(const QList<ProxyNode> &nodes, const QString &selected) {
    if (!m_healthy) { m_error=QStringLiteral("节点库损坏或无法解密；未覆盖原文件。"); return false; }
    QJsonArray array; for (const auto &n : nodes) array.append(serialize(n));
    auto plaintext=QJsonDocument(QJsonObject{{"schema",1},{"selected",selected},{"nodes",array}}).toJson(QJsonDocument::Compact);
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
    m_nodes=nodes; m_selected=selected; m_error.clear(); emit changed(); return true;
}
bool NodeStore::saveNode(const QVariantMap &input) {
    auto n=deserialize(input); auto nodes=m_nodes; int index=-1;
    if (n.id.isEmpty()) n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);
    else { for (int i=0;i<nodes.size();++i) if (nodes[i].id==n.id) index=i;
        if (index<0) { m_error=QStringLiteral("编辑的节点不存在。"); return false; } }
    if (index>=0 && n.protocol==nodes[index].protocol && !input.value("replaceCredentials").toBool()) {
        if (n.password.isEmpty()) n.password=nodes[index].password;
        if (n.username.isEmpty()) n.username=nodes[index].username;
    }
    m_error=ProxyNode::validate(n); if (!m_error.isEmpty()) return false;
    if (index<0) { if (nodes.size()>=100) { m_error=QStringLiteral("最多保存 100 个节点。"); return false; } nodes.append(n); }
    else nodes[index]=n;
    return write(nodes,m_selected);
}
bool NodeStore::removeNode(const QString &id) {
    auto nodes=m_nodes; const auto old=nodes.size(); nodes.removeIf([&](const ProxyNode &n){return n.id==id;});
    if (nodes.size()==old) { m_error=QStringLiteral("节点不存在。"); return false; }
    return write(nodes,m_selected==id ? QString() : m_selected);
}
bool NodeStore::select(const QString &id) {
    if (!id.isEmpty() && std::none_of(m_nodes.begin(),m_nodes.end(),[&](const ProxyNode &n){return n.id==id;})) {
        m_error=QStringLiteral("选择的节点不存在。"); return false;
    }
    return write(m_nodes,id);
}
