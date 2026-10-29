#include "engine/NodeImporter.h"
#include "engine/NodeStore.h"
#include "engine/SwirlProtocolRegistry.h"
#include <QCoreApplication>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QTextStream>
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif

namespace {
// Only fixed classifications are public. Source-derived text is never echoed.
QString reasonCode(const QString &reason) {
    static const QHash<QString,QString> known{
        {QStringLiteral("节点 URI 含重复参数，无法安全确定配置。"), "DuplicateUriParameter"},
        {QStringLiteral("节点 URI 别名参数冲突；未应用配置。"), "ConflictingUriParameter"},
        {QStringLiteral("节点 URI 布尔参数无效；未应用配置。"), "InvalidUriBoolean"},
        {QStringLiteral("节点 URI REALITY 缺少公钥；未降级为普通 TLS。"), "RealityPublicKeyRequired"},
        {QStringLiteral("节点 URI REALITY 参数与安全层冲突；未应用配置。"), "RealitySecurityConflict"},
        {QStringLiteral("节点 URI TLS 参数冲突；未应用配置。"), "TlsParameterConflict"},
        {QStringLiteral("此 URI 安全层尚未映射。"), "SecurityLayerUnsupported"},
        {QStringLiteral("VLESS URI 含未映射的额外密码；原始参数已保留，不能忽略后连接。"), "VlessUriPasswordUnsupported"},
        {QStringLiteral("VLESS URI 含未映射的地址路径；原始参数已保留，不能忽略后连接。"), "VlessUriPathUnsupported"},
        {QStringLiteral("TCP URI 的 path、host 或 serviceName 尚未映射；原始参数已保留，不能忽略后连接。"), "TcpUriTransportOptionsUnsupported"},
        {QStringLiteral("TCP 传输含未映射的 Host 或路径；原始参数已保留。"), "TcpTransportOptionsUnsupported"},
        {QStringLiteral("URI 显式传输类型为空；原始参数已保留，不能当作省略后连接。"), "ExplicitEmptyTransport"},
        {QStringLiteral("URI 的 headerType 仅支持 TCP 的 none；原始参数已保留，不能忽略后连接。"), "HeaderTypeUnsupported"},
        {QStringLiteral("此传输不支持 URI 的 headerType；原始参数已保留，不能忽略后连接。"), "HeaderTypeTransportConflict"},
        {QStringLiteral("VLESS URI 的加密扩展尚未映射。"), "VlessEncryptionUnsupported"},
        {QStringLiteral("URI 的附加伪装或 QUIC 加密选项尚未映射。"), "QuicSecurityUnsupported"},
        {QStringLiteral("节点 URI 包含未映射选项，原始参数已保留。"), "UnmappedUriOptions"},
        {QStringLiteral("保存的原始 URI 无法通过当前导入校验；原始字段已保留，拒绝执行。"), "StoredOriginalUriRejected"},
        {QStringLiteral("节点含无效或未映射参数，Rust 拒绝执行。"), "UnmappedOrInvalidParameters"},
        {QStringLiteral("此节点协议尚未迁移到 Rust；未使用外部内核。"), "ProtocolNotImplemented"},
        {QStringLiteral("Rust 尚未实现此传输或扩展参数。"), "TransportOrExtensionUnsupported"},
        {QStringLiteral("Rust 尚未实现此传输。"), "TransportNotImplemented"},
        {QStringLiteral("Rust 不允许关闭证书验证。"), "CertificateVerificationDisabledUnsupported"},
        {QStringLiteral("Rust 尚未实现 TCP Fast Open；必须明确为 false。"), "TcpFastOpenNotImplemented"},
        {QStringLiteral("Rust 尚不支持该出口的代理 UDP。"), "ProxyUdpUnsupported"},
        {QStringLiteral("Rust 布尔参数类型无效。"), "InvalidBooleanParameter"},
        {QStringLiteral("TLS 名称字段不一致。"), "TlsServerNameConflict"},
        {QStringLiteral("未启用 TLS 却含 TLS 参数。"), "TlsSecurityRequired"},
        {QStringLiteral("REALITY 必须明确启用安全连接；未降级为 TCP。"), "RealitySecurityRequired"},
        {QStringLiteral("VLESS 只支持 UUID 认证。"), "VlessAuthenticationUnsupported"},
        {QStringLiteral("Rust 仅支持 REALITY 的 xtls-rprx-vision flow；未删除或更换原值。"), "VlessFlowUnsupported"},
        {QStringLiteral("Rust 尚未实现该 VLESS encryption 扩展。"), "VlessEncryptionUnsupported"},
        {QStringLiteral("REALITY 指纹尚未支持；当前支持显式 rustls、chrome 或 chrome_133，未替换源配置。"), "RealityFingerprintUnsupported"},
        // NativeNodeBridge wraps the Rust inspector's fixed code. Match the
        // complete known message; never expose an arbitrary source code/text.
        {QStringLiteral("Rust 无法执行此节点：RealityFingerprintUnsupported；原始参数已保留。"), "RealityFingerprintUnsupported"},
        {QStringLiteral("REALITY 需要源配置明确声明受支持的指纹；未执行导入时推断的默认值。"), "RealityFingerprintRequired"},
        {QStringLiteral("REALITY 当前仅支持 TCP 传输。"), "RealityTransportUnsupported"},
        {QStringLiteral("REALITY 参数必须是对象。"), "RealityParameterType"},
        {QStringLiteral("REALITY 不能附带 WebSocket 参数。"), "RealityTransportConflict"},
        {QStringLiteral("REALITY 含尚未映射的参数；未丢弃原值。"), "RealityUnmappedFields"},
        {QStringLiteral("REALITY 公钥或 shortId 类型无效。"), "RealityParameterType"},
        {QStringLiteral("REALITY 需要明确的有效 SNI 域名。"), "RealityServerNameInvalid"},
        {QStringLiteral("REALITY 公钥编码无效。"), "RealityPublicKeyInvalid"},
        {QStringLiteral("REALITY 公钥无效。"), "RealityPublicKeyInvalid"},
        {QStringLiteral("REALITY 公钥必须使用规范的 Base64URL 编码。"), "RealityPublicKeyInvalid"},
        {QStringLiteral("REALITY shortId 必须是最长 8 字节的十六进制。"), "RealityShortIdInvalid"},
        {QStringLiteral("REALITY ALPN 格式无效。"), "RealityAlpnInvalid"},
        {QStringLiteral("REALITY ALPN 数量超过限制。"), "RealityAlpnLimit"},
        {QStringLiteral("REALITY ALPN 重复或总长度超过限制。"), "RealityAlpnInvalid"},
        {QStringLiteral("REALITY ALPN 值无效。"), "RealityAlpnInvalid"},
        {QStringLiteral("REALITY Chrome 指纹仅支持默认 ALPN 或按顺序声明 h2、http/1.1；未替换源配置。"), "RealityFingerprintAlpnUnsupported"},
        {QStringLiteral("源配置 uTLS 参数类型无效。"), "UtlsParameterType"},
        {QStringLiteral("源配置 uTLS 含未映射参数；未丢弃原值。"), "UtlsUnmappedFields"},
        {QStringLiteral("源配置 uTLS 仅支持 REALITY 的显式 chrome 或 chrome_133 指纹；未替换原值。"), "UtlsFingerprintUnsupported"},
        {QStringLiteral("源配置 uTLS 指纹与节点指纹冲突；未覆盖原值。"), "UtlsFingerprintConflict"},
        {QStringLiteral("源配置 uTLS 未明确启用却含指纹要求；未丢弃原值。"), "UtlsSecurityRequired"},
    };
    return reason.isEmpty()?QStringLiteral("TcpCandidateNotYetVerified"):
        known.value(reason,QStringLiteral("UnclassifiedNativeOrImportDiagnostic"));
}

QString choice(const QJsonValue &value,const QStringList &allowed,const QString &missing="not-declared") {
    if(value.isUndefined())return missing;
    return value.isString()&&allowed.contains(value.toString())?value.toString():QStringLiteral("unsupported-or-invalid");
}

bool sameParameters(const ProxyNode &a,const ProxyNode &b) {
    // Reload may add current diagnostics; that is not parameter loss.
    return a.host==b.host&&a.port==b.port&&a.protocol==b.protocol&&a.username==b.username&&a.password==b.password
        &&a.cipher==b.cipher&&a.serverName==b.serverName&&a.parameters==b.parameters
        &&a.originalConfiguration==b.originalConfiguration;
}

QJsonObject nodeReport(const ProxyNode &node,int ordinal,bool imported) {
    const auto nativeReason=SwirlProtocolRegistry::nativeNodeReason(node);
    const bool candidate=nativeReason.isEmpty();
    QJsonArray issues;for(const auto &issue:node.conversionIssues){const auto code=reasonCode(issue);if(!issues.contains(code))issues.append(code);}
    const auto source=node.originalConfiguration.value("uri");
    QString parsed=imported?"passed":"not-tested",remapped="not-tested";
    if(source.isString()){
        const auto current=NodeImporter::parse(source.toString().toUtf8());
        parsed=current&&current.nodes.size()==1?"passed":"failed";
        if(parsed=="passed")remapped=sameParameters(node,current.nodes.first())?"passed":"different";
    }
    const bool reality=node.protocol=="vless"&&node.parameters.contains("reality-opts");
    QJsonObject stages{{"parse",parsed},{"completeParameterMapping",candidate?"passed":"blocked"},
        {"qtNodeStoreReload","passed"},{"nativeEligibility",candidate?"passed":"blocked"},
        {"sourceRemapping",remapped},{"runtimeStart","not-tested"},{"proxyConnect","not-tested"},
        {"realityConnection","not-tested"},{"realityAuthentication","not-tested"},
        {"vision","not-tested"},{"visionDirect","not-tested"},{"http","not-tested"},{"https","not-tested"},
        {"fullConfiguration","not-tested"}};
    return {{"node",ordinal},{"protocol",choice(node.protocol,ProxyNode::protocols())},
        {"transport",choice(node.parameters.value("network"),{"tcp","ws","grpc","h2","httpupgrade","xhttp","quic"},"tcp")},
        {"security",reality?"reality":node.parameters.value("tls").toBool()||node.protocol=="trojan"?"tls":"none"},
        {"fingerprint",choice(node.parameters.value("client-fingerprint"),{"chrome","chrome_133","rustls","firefox","safari","ios","edge","android","random","randomized"})},
        {"flow",choice(node.parameters.value("flow"),{"","xtls-rprx-vision","xtls-rprx-vision-udp443"})},
        {"nativeTcpCandidate",candidate},{"reasonCode",reasonCode(nativeReason)},
        {"conversionIssueCodes",issues},{"originalUriPresent",source.isString()},
        {"stages",stages}};
}

int error(QTextStream &out,const char *code,int status,const QString &diagnostic={}) {
    QJsonObject report{{"schema",2},{"errorCode",code},{"offlineOnly",true},{"networkRequests",0}};
    if(!diagnostic.isEmpty())report["reasonCode"]=reasonCode(diagnostic);
    out<<QJsonDocument(report).toJson(QJsonDocument::Compact)<<Qt::endl;
    return status;
}

QByteArray readFile(const QString &path,qint64 limit) {
    QFile file(path);if(!file.open(QIODevice::ReadOnly)||file.size()>limit)return {};
    return file.readAll();
}
}

// Offline only: no engine start, downloads, existing-store writes or selection.
// Legacy input.dpapi/new-store mode verifies a new encrypted round trip.
// --node-store existing-store re-evaluates the current mapper without writes.
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);QTextStream output(stdout);
    if(app.arguments().size()!=3)return error(output,"UsageInvalid",2);
#if !defined(Q_OS_WIN)
    return error(output,"WindowsDpapiRequired",4);
#else
    const bool existing=app.arguments()[1]=="--node-store";
    const auto path=app.arguments()[2];
    QByteArray before;QList<ProxyNode> saved;QString selected;
    if(existing){
        before=readFile(path,1024*1024);
        if(!before.startsWith("SWIRLNODE1\n"))return error(output,"NodeStoreInputInvalid",3);
    }else{
        if(QFileInfo::exists(path)||QFileInfo::exists(path+".selected"))return error(output,"OutputAlreadyExists",6);
        auto encrypted=readFile(app.arguments()[1],8*1024*1024);
        if(encrypted.isEmpty())return error(output,"EncryptedInputInvalid",3);
        DATA_BLOB source{DWORD(encrypted.size()),reinterpret_cast<BYTE *>(encrypted.data())},out{};
        if(!CryptUnprotectData(&source,nullptr,nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&out))return error(output,"DpapiDecryptFailed",4);
        QByteArray plain(reinterpret_cast<char *>(out.pbData),out.cbData);SecureZeroMemory(out.pbData,out.cbData);LocalFree(out.pbData);
        auto result=NodeImporter::parse(plain);plain.fill('\0');
        if(!result)return error(output,"SubscriptionParseFailed",5,result.error);
        NodeStore store(path);
        if(!store.importNodes(result.nodes))return error(output,"NodeStoreImportFailed",6);
        saved=store.nodes();selected=store.selectedId();before=readFile(path,1024*1024);
        if(!before.startsWith("SWIRLNODE1\n"))return error(output,"EncryptedSaveFailed",6);
    }
    const auto selectionBefore=readFile(path+".selected",256);
    NodeStore loaded(path);
    if(!loaded.error().isEmpty())return error(output,"NodeStoreReloadFailed",8);
    const auto nodes=loaded.nodes();
    if(!existing){
        if(nodes.size()!=saved.size()||loaded.selectedId()!=selected)return error(output,"EncryptedReloadMismatch",8);
        for(qsizetype i=0;i<nodes.size();++i)
            if(nodes[i].id!=saved[i].id||!sameParameters(nodes[i],saved[i]))return error(output,"EncryptedReloadMismatch",8);
    }
    QJsonArray rows;QJsonObject protocols;int candidates=0,incomplete=0,ordinal=0;
    for(const auto &node:nodes){
        const auto row=nodeReport(node,++ordinal,!existing);rows.append(row);
        candidates+=row.value("nativeTcpCandidate").toBool()?1:0;
        incomplete+=node.conversionIssues.isEmpty()?0:1;
        const auto protocol=row.value("protocol").toString();protocols[protocol]=protocols.value(protocol).toInt()+1;
    }
    if(readFile(path,1024*1024)!=before||readFile(path+".selected",256)!=selectionBefore)return error(output,"InputChangedDuringInspection",9);
    output<<QJsonDocument(QJsonObject{{"schema",2},{"engine","swirl-rust"},
        {"scope","offline current Qt Rust mapper; no Runtime or provider connection"},
        {"inputMode",existing?"existing-node-store":"encrypted-response-to-new-store"},
        {"offlineOnly",true},{"networkRequests",0},{"inputUnchanged",true},
        {"encryptedSaveReload",existing?"reload-only":"passed"},{"nodes",nodes.size()},
        {"nativeTcpCandidates",candidates},{"incompleteNodes",incomplete},{"protocols",protocols},{"cases",rows}}).toJson(QJsonDocument::Compact)<<Qt::endl;
    return 0;
#endif
}
