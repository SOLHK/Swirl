#include "NativeNodeBridge.h"
#include "RustCoreLibrary.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QRegularExpression>
#include <QUuid>

QString NativeNodeBridge::executableOutbound(const ProxyNode &node, QJsonObject *output) {
    if (!output || node.isXray() || !node.conversionIssues.isEmpty() || !ProxyNode::validate(node).isEmpty())
        return QStringLiteral("节点含无效或未映射参数，Rust 拒绝执行；原始配置已保留。");
    auto raw = node.parameters;
    const auto put = [&raw](const QString &key, const QJsonValue &value) {
        if (raw.contains(key) && raw.value(key) != value) return false;
        raw.insert(key, value); return true;
    };
    if (!put("name", node.name) || !put("type", node.protocol) ||
        !put("server", node.host) || !put("port", int(node.port)) ||
        ((!node.username.isEmpty() || raw.contains("username")) && !put("username", node.username)) ||
        ((!node.password.isEmpty() || raw.contains("password")) && !put("password", node.password)) ||
        ((!node.cipher.isEmpty() || raw.contains("cipher")) && !put("cipher", node.cipher)))
        return QStringLiteral("节点字段与保留的扩展参数冲突；未覆盖认证或连接参数。");
    if (node.protocol == "vless" || node.protocol == "vmess" || node.protocol == "tuic") {
        // Qt's existing editor accepts braced UUIDs. Preserve their value while
        // emitting the canonical spelling required by the Rust schema.
        const QUuid uuid(raw.value("uuid").toString());
        if (!uuid.isNull()) raw["uuid"] = uuid.toString(QUuid::WithoutBraces);
    }
    for (const auto &key : {"sni", "servername"})
        if (raw.contains(key) && raw.value(key) != QJsonValue(node.serverName))
            return QStringLiteral("TLS 名称字段不一致；未覆盖源配置。");
    const bool singBoxQuic = raw.value("_swirl-source-format") == QJsonValue("sing-box") &&
        (node.protocol == "tuic" || node.protocol == "hysteria2");
    if (singBoxQuic) {
        // SNI is exposed to the editor, but the source dialect remains nested.
        // Reject stale editor/source disagreement instead of inventing aliases
        // or overwriting the retained security requirements.
        const auto tls = raw.value("tls").toObject();
        if (!node.serverName.isEmpty() && tls.value("server_name") != QJsonValue(node.serverName))
            return QStringLiteral("TLS 名称字段不一致；未覆盖源配置。");
    } else if (!node.serverName.isEmpty()) {
        // VMess's existing Clash parser uses servername; other protocol
        // parsers explicitly validate the sni/servername aliases.
        if (!put(node.protocol == "vmess" ? "servername" : "sni", node.serverName))
            return QStringLiteral("TLS 名称字段不一致；未覆盖源配置。");
    }
    auto bytes = QJsonDocument(QJsonObject{{"proxies", QJsonArray{raw}}}).toJson(QJsonDocument::Compact);
    constexpr qsizetype Maximum = 1024 * 1024;
    if (bytes.size() > Maximum) { bytes.fill('\0'); return QStringLiteral("节点配置超过 Rust 导入接口上限。"); }
    auto &library = RustCoreLibrary::instance();
    if (!library.load() || !library.importNode()) {
        bytes.fill('\0');
        return QStringLiteral("Rust 节点转换接口不可用；请安装 ABI 匹配的完整版本。");
    }
    const auto import = library.importNode();
    const auto *input = reinterpret_cast<const unsigned char *>(bytes.constData());
    const auto required = import(input, size_t(bytes.size()), nullptr, 0);
    if (required <= 0 || required > Maximum) {
        bytes.fill('\0'); return QStringLiteral("Rust 节点转换失败或响应超过上限。");
    }
    QByteArray response(required, Qt::Uninitialized);
    const auto count = import(input, size_t(bytes.size()), reinterpret_cast<unsigned char *>(response.data()), size_t(response.size()));
    bytes.fill('\0');
    if (count != required) { response.fill('\0'); return QStringLiteral("Rust 节点转换返回无效长度。"); }
    QJsonParseError error;
    const auto document = QJsonDocument::fromJson(response, &error); response.fill('\0');
    if (error.error != QJsonParseError::NoError || !document.isObject() || document.object().value("schema").toInt() != 1)
        return QStringLiteral("Rust 节点转换接口版本或响应无效。");
    const auto result = document.object();
    if (!result.value("ok").toBool()) {
        // Only fixed Rust diagnostic identifiers can enter the UI; never raw
        // option values, source excerpts or a serialized native outbound.
        const auto code = result.value("error").toString();
        const auto safe = QRegularExpression("^[A-Za-z][A-Za-z0-9]{0,127}$").match(code).hasMatch();
        const auto field = safe && code.contains("alpn", Qt::CaseInsensitive) ? QStringLiteral("ALPN ") : QString();
        return QStringLiteral("Rust 无法执行此节点：%1%2；原始参数已保留。").arg(field, safe ? code : QStringLiteral("NativeNodeInvalid"));
    }
    if (!result.value("native_outbound").isObject() || result.value("native_outbound").toObject().isEmpty())
        return QStringLiteral("Rust 未返回可执行节点配置。");
    *output = result.value("native_outbound").toObject();
    return {};
}
