#pragma once

#include <QNetworkRequest>
#include <QVariant>

namespace SwirlNetwork {

// Qt 6.10.3 is affected by CVE-2026-96432 in its HTTP/2 client.
// Apply the official mitigation to every Qt HTTP request, including requests
// rebuilt for redirects. Direct HTTP/2 takes precedence over Allowed; explicitly
// disable h2c too so QT_NETWORK_H2C_ALLOWED cannot change this policy.
// Keep this until the shipped Qt library has the upstream fix and HTTP/2 has
// been revalidated. HTTPS certificate verification is unchanged.
// https://www.qt.io/blog/security-advisory-cve-2026-96432
inline void applyHttp1OnlyPolicy(QNetworkRequest &request)
{
    request.setAttribute(QNetworkRequest::Http2AllowedAttribute, false);
    request.setAttribute(QNetworkRequest::Http2DirectAttribute, false);
    request.setAttribute(QNetworkRequest::Http2CleartextAllowedAttribute, false);
}

} // namespace SwirlNetwork
