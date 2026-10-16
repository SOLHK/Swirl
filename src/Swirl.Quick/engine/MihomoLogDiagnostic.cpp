#include "MihomoLogDiagnostic.h"
#include <QRegularExpression>

MihomoLogDiagnostic classifyMihomoLog(const QString &payload) {
    // Mihomo's routing preamble contains arbitrary user node/rule names. Only
    // inspect the error suffix, so a node called 'DNS TLS' is not a DNS failure.
    static const QRegularExpression errorMarker(QStringLiteral(R"(\berror\s*[:=]\s*)"),QRegularExpression::CaseInsensitiveOption);
    const auto bounded=payload.left(16384);
    const auto marker=errorMarker.match(bounded);
    auto reason=marker.hasMatch()?bounded.mid(marker.capturedEnd()).toLower():QString();
    static const QRegularExpression url(QStringLiteral(R"([a-z][a-z0-9+.-]*://[^\s]+)"));
    reason.remove(url); // Do not classify a credential or server URL as a fault.
    QString code=QStringLiteral("RouteHandshakeFailure"), detail=QStringLiteral("未匹配到已知错误原因");
    const auto contains=[&](const char *value){return reason.contains(QLatin1String(value));};
    if(contains("407 proxy authentication") || contains("proxy authentication required")){code="ProxyAuthenticationFailure";detail="HTTP 代理要求认证（407）";}
    else if(contains("authentication failed") || contains("authentication failure") || contains("no acceptable authentication")){code="ProxyAuthenticationFailure";detail="上游代理认证被拒绝";}
    else if(contains("no such host") || contains("nxdomain")){code="DNSFailure";detail="域名不存在或没有可用解析记录";}
    else if(contains("dns resolve failed") || contains("dns resolution failed") || contains("all dns requests failed") || contains("couldn't find ip") || contains("server misbehaving")){code="DNSFailure";detail="上游 DNS 解析失败";}
    else if(contains("certificate") || contains("x509:")){code="TLSFailure";detail="上游 TLS 证书校验失败";}
    else if(contains("tls handshake") && (contains("eof") || contains("closed"))){code="TLSFailure";detail="上游 TLS 握手期间连接提前关闭（EOF）";}
    else if(contains("tls:") || contains("tls handshake")){code="TLSFailure";detail="上游 TLS 协商失败";}
    else if(contains("connection refused") || contains("actively refused")){code="UpstreamConnectionRefused";detail="上游 TCP 连接被拒绝";}
    else if(contains("connection reset") || contains("forcibly closed")){code="UpstreamConnectionReset";detail="上游 TCP 连接被重置";}
    else if(contains("timeout") || contains("timed out") || contains("deadline exceeded")){code="UpstreamTimeout";detail="上游连接或握手超时";}
    else if(contains("eof")){code="UpstreamEOF";detail="上游连接提前结束（EOF）；阶段未确定";}
    // The sole destination detail allowed in a report is a known public
    // OpenAI hostname from the explicit target field, never the upstream node.
    static const QRegularExpression target(QStringLiteral(R"(--\s*>\s*(auth\.openai\.com|ws\.chatgpt\.com|chatgpt\.com|api\.openai\.com):443\b)"),QRegularExpression::CaseInsensitiveOption);
    const auto destination=target.match(bounded);
    const auto suffix=destination.hasMatch()?QStringLiteral("；目标 %1:443").arg(destination.captured(1).toLower()):QString();
    return {code,QStringLiteral("Mihomo 观察到：%1%2。未记录节点、原始端点或凭据；不能仅凭此事件判定应用请求根因。").arg(detail,suffix)};
}
