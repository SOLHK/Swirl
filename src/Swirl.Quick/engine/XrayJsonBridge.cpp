#include "XrayJsonBridge.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLibrary>
#include <QRegularExpression>
#include <QSet>
#include <QUuid>
#include <algorithm>

namespace {
using Import = qintptr (*)(const unsigned char *, size_t, unsigned char *, size_t);
constexpr qsizetype MaximumResponse = 64 * 1024 * 1024;
struct Api {
    QLibrary library{QCoreApplication::applicationDirPath() + QStringLiteral("/swirl_api")};
    Import import = nullptr;
    Api() {
        library.setLoadHints(QLibrary::ResolveAllSymbolsHint | QLibrary::PreventUnloadHint);
        if (library.load()) import = reinterpret_cast<Import>(library.resolve("swirl_import_xray_v1"));
    }
};
QString diagnostic(const QJsonObject &item) {
    // Only Rust's fixed code and sanitized structural path cross into the UI.
    const auto code = item.value("code").toString();
    const auto path = item.value("path").toString();
    return path.isEmpty() ? code : code + QStringLiteral(" · ") + path;
}
QStringList diagnostics(const QJsonArray &items) {
    QStringList result;
    for (const auto &item : items) {
        const auto text = diagnostic(item.toObject());
        if (!text.isEmpty() && result.size() < 64) result.append(text);
    }
    return result;
}
struct SecretNames { QSet<QString> values; bool hideAll=false; };
QString displayName(QString value) {
    static const QRegularExpression controls(QStringLiteral("[\\x00-\\x1f\\x7f-\\x9f]"));
    value.replace(controls, QStringLiteral(" "));
    return value.trimmed();
}
void findSecrets(const QJsonValue &value, SecretNames *secrets) {
    if (secrets->hideAll) return;
    if (value.isArray()) for (const auto &item : value.toArray()) findSecrets(item, secrets);
    if (!value.isObject()) return;
    const auto object = value.toObject();
    for (auto it = object.begin(); it != object.end(); ++it) {
        const auto key = it.key().toLower();
        if (it.value().isString() && (key == "id" || key == "uuid" || key == "pass" ||
            key.contains("password") || key.contains("token") || key.contains("authorization") || key.contains("privatekey"))) {
            const auto secret = it.value().toString();
            if (!secret.isEmpty() && secret.size() <= 128) secrets->values.insert(secret);
            // A tag may repeat a password containing NUL/control characters
            // or surrounding whitespace. Its display normalization must not
            // turn the same credential into a different, unredacted string.
            const auto visible = displayName(secret);
            if (!visible.isEmpty() && visible.size() <= 128) secrets->values.insert(visible);
            // Keep name redaction work bounded even for adversarial unknowns.
            if (secrets->values.size() > 4096) { secrets->hideAll = true; return; }
        }
        findSecrets(it.value(), secrets);
    }
}
QString safeName(QString name, const SecretNames &secrets, int index) {
    const auto fallback = QStringLiteral("JSON 节点 %1").arg(index + 1);
    if (secrets.hideAll || name.size() > 128 || name.contains("://") ||
        name.contains(QRegularExpression(QStringLiteral("(?:token|password|authorization)\\s*[=:]|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), QRegularExpression::CaseInsensitiveOption))) return fallback;
    for (const auto &secret : secrets.values)
        if (name == secret || (secret.size() >= 4 && name.contains(secret))) return fallback;
    name = displayName(name);
    for (const auto &secret : secrets.values)
        if (name == secret || (secret.size() >= 4 && name.contains(secret))) return fallback;
    return name.isEmpty() ? fallback : name;
}
}

NodeImporter::Result XrayJsonBridge::parse(const QByteArray &bytes) {
    NodeImporter::Result result;
    result.format = result.configurationFormat = QStringLiteral("xray-v2ray-json");
    if (bytes.isEmpty() || bytes.size() > NodeImporter::MaximumBytes) {
        result.error = QStringLiteral("JSON 内容为空或超过 4 MiB；原节点保持不变。");
        return result;
    }
    static Api api;
    if (!api.import) {
        result.error = QStringLiteral("Rust 严格 JSON 导入接口不可用，请安装包含 swirl_api 的完整版本。");
        return result;
    }
    const auto *input = reinterpret_cast<const unsigned char *>(bytes.constData());
    const auto required = api.import(input, size_t(bytes.size()), nullptr, 0);
    if (required <= 0 || required > MaximumResponse) {
        result.error = QStringLiteral("Rust JSON 导入失败或响应超出安全上限；原节点保持不变。");
        return result;
    }
    QByteArray output(required, Qt::Uninitialized);
    const auto count = api.import(input, size_t(bytes.size()), reinterpret_cast<unsigned char *>(output.data()), size_t(output.size()));
    if (count != required) {
        output.fill('\0');
        result.error = QStringLiteral("Rust JSON 导入接口返回无效响应；原节点保持不变。");
        return result;
    }
    QJsonParseError error;
    const auto response = QJsonDocument::fromJson(output, &error);
    output.fill('\0');
    if (error.error != QJsonParseError::NoError || !response.isObject() || response.object().value("schema").toInt() != 1) {
        result.error = QStringLiteral("Rust JSON 导入接口版本或响应无效。");
        return result;
    }
    const auto object = response.object();
    result.diagnostics = diagnostics(object.value("diagnostics").toArray());
    if (!object.value("ok").toBool()) {
        if (result.diagnostics.isEmpty() && object.value("error").isObject())
            result.diagnostics.append(diagnostic(object.value("error").toObject()));
        result.error = QStringLiteral("JSON 校验失败：%1。原节点保持不变。").arg(result.diagnostics.join(QStringLiteral("；")));
        return result;
    }
    const auto outbounds = object.value("outbounds").toArray();
    const auto sourceFingerprint=QString::fromLatin1(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex());
    // Input has already passed Rust's strict checks. This read only finds
    // credential strings for redaction (including inbound/global secrets);
    // it never decides syntax validity, converts protocols or enables options.
    const auto redactionSource=QJsonDocument::fromJson(bytes);
    SecretNames secrets;
    findSecrets(redactionSource.isArray()?QJsonValue(redactionSource.array()):QJsonValue(redactionSource.object()), &secrets);
    const auto nodes = object.value("nodes").toArray();
    if (nodes.isEmpty() || nodes.size() > 2000) {
        result.error = QStringLiteral("JSON 必须包含 1–2000 个出站节点。");
        return result;
    }
    for (const auto &value : nodes) {
        const auto item = value.toObject();
        if (!item.value("is_remote_node").toBool(true)) continue;
        const auto source = item.value("source").toObject();
        const auto outboundIndex = source.value("outbound_index").toInt(-1);
        const auto index = item.value("index").toInt(-1);
        if (index < 0 || outboundIndex < 0 || outboundIndex >= outbounds.size()) {
            result.nodes.clear(); result.error = QStringLiteral("Rust 返回的节点来源索引无效。"); return result;
        }
        const auto raw = outbounds.at(outboundIndex).toObject();
        const auto authentication = item.value("authentication").toObject();
        ProxyNode node;
        node.id = QUuid::createUuid().toString(QUuid::WithoutBraces);
        node.name = safeName(item.value("name").toString(), secrets, index);
        node.protocol = item.value("protocol").toString();
        if (node.protocol == "shadowsocks") node.protocol = "ss";
        if (node.protocol == "socks") node.protocol = "socks5";
        node.host = item.value("host").toString();
        node.port = quint16(item.value("port").toInt());
        node.sourceFormat = result.format;
        node.sourceDocument = bytes;
        node.sourceFingerprint = sourceFingerprint;
        node.sourceNodeIndex = index;
        node.parameterState = item.value("validation").toString("unverified");
        node.transportType = item.value("transport").toString("unknown");
        node.securityType = item.value("security").toString("unknown");
        node.nativeExecutable = item.value("executable").toBool();
        node.nativeOutbound = item.value("native_outbound").toObject();
        for (const auto &reason : item.value("execution_issues").toArray())
            node.runtimeIssues.append(reason.isString() ? reason.toString() : diagnostic(reason.toObject()));
        node.conversionIssues = diagnostics(item.value("diagnostics").toArray());
        node.originalConfiguration = QJsonObject{{"outbound", raw}, {"source", source}};
        // A transparent private container, not a second protocol converter.
        node.parameters = QJsonObject{{"authentication", authentication}};
        for (const auto &key : {"streamSettings", "mux", "proxySettings"})
            if (raw.contains(key)) node.parameters.insert(key, raw.value(key));
        node.password = authentication.value("password").toString(authentication.value("pass").toString());
        node.username = authentication.value("user").toString();
        node.cipher = authentication.value("method").toString(authentication.value("security").toString());
        if (!node.nativeExecutable) ++result.incompleteNodes;
        result.nodes.append(std::move(node));
    }
    if (result.nodes.isEmpty()) result.error = QStringLiteral("配置只包含本地出站动作，没有可导入的远端代理节点。");
    // Global JSON, inbound listeners, files and scripts remain in the private
    // source. They never populate Result::configuration or local settings.
    return result;
}

bool XrayJsonBridge::refreshNode(ProxyNode *node, QString *error) {
    if (!node || !node->isXray()) return false;
    const auto parsed = parse(node->sourceDocument);
    if (parsed) for (const auto &candidate : parsed.nodes) if (candidate.sourceNodeIndex == node->sourceNodeIndex) {
        auto restored = candidate;
        restored.id = node->id; restored.name = node->name;
        restored.sourceId = node->sourceId; restored.importSource = node->importSource;
        *node = std::move(restored);
        return true;
    }
    node->nativeExecutable = false; node->nativeOutbound = {};
    node->runtimeIssues = {QStringLiteral("SourceRevalidationFailed")};
    if (error) *error = parsed.error.isEmpty() ? QStringLiteral("JSON 节点来源失效；请重新导入。") : parsed.error;
    return false;
}

QString XrayJsonBridge::executableOutbound(const ProxyNode &node, QJsonObject *output) {
    auto current = node;
    QString error;
    if (!refreshNode(&current, &error)) return error;
    if (!current.nativeExecutable || current.nativeOutbound.isEmpty())
        return QStringLiteral("Rust 无法执行此 JSON 节点：%1；原始参数已保留。").arg(current.runtimeIssues.join(QStringLiteral("；")));
    *output = current.nativeOutbound;
    return {};
}
