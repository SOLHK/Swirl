# Qt HTTP client mitigation for CVE-2026-96432

## Scope and status

The Qt advisory published on 2026-10-21 covers Qt 6.8.0–6.8.9 and
6.9.0–6.11.2, including the Qt 6.10.3 SDK pinned by Swirl's build workflows.
A malicious or compromised HTTP/2 server can cause a null-pointer dereference
in Qt Network's `QNetworkAccessManager` client and crash the application.
There is no evidence here that Swirl has experienced this CVE, and this change
does not attribute earlier import-cancel UI failures to it.

This is the official **application-request mitigation**, not a patch to the
Qt 6.10.3 shared libraries. Keep Qt HTTP/2 disabled until the shipped Qt
libraries contain the upstream fix and the affected paths have been revalidated.
The advisory names Qt 6.8.10 and 6.11.3 or later as fixed releases; alternatively
apply the matching official Qt patch and rebuild/distribute the Qt libraries.
Simply replacing Swirl's proxy core with Rust does not repair Qt's downloader.

The repair starts at the exact reported source
`5d96214ac80d63985cdccf4942c3c1d79035e793`, the head of
`work/rust-core-full-replacement-20261022` when inspected. Delivery is isolated
on `work/qt-http2-security-20261023`; `main`, `test` and parallel development
branches are not modified.

## Production changes

`network/HttpRequestPolicy.h` explicitly sets these request attributes to false:

- `Http2AllowedAttribute`, the official advisory mitigation;
- `Http2DirectAttribute`, which otherwise overrides the first attribute;
- `Http2CleartextAllowedAttribute`, so environment-driven h2c cannot reopen it.

All four application-owned Qt HTTP request construction sites apply this policy:

| Request path | Coverage |
| --- | --- |
| `NodeImportService::download()` | URL import, subscription refresh, automatic refresh and each manually rebuilt redirect request |
| `TelemetryService::measureHttp()` | Internet connectivity and external-IP measurement, direct or through Swirl's local proxy |
| `CaptureService` upstream request | Qt requests to the destination server, including decrypted capture/rewrite traffic |
| `runRustCoreSelfTest()` | The product's controlled loopback HTTP self-test |

HTTPS certificate checks, proxy selection, download limits, timeouts and
redirect restrictions remain in force. Capture's independent nghttp2 input
session still accepts HTTP/2 clients; opaque CONNECT tunnels and Rust protocol
transports do not use the vulnerable Qt HTTP/2 client. No global SSL defaults
or system proxy settings are changed by the repair.

The temporary compatibility cost is that these Qt clients require an origin
that accepts HTTP/1.1. HTTP/2-only origins can fail until the Qt dependency is
fixed and HTTP/2 is deliberately restored. HTTPS is not downgraded to HTTP.

## Verification

The new standalone `tests/qt-network` project compiles the real downloader and
parser. Real loopback TLS servers offer both `h2` and `http/1.1`. An unprotected
Qt client is a positive control that actually negotiates `h2`; the server then
closes safely without sending exploit frames. Protected requests must send an
actual HTTP/1.1 request line and complete the expected response/parse flow.
An empty negotiated ALPN is valid for HTTP/1.1 and is not mistaken for HTTP/2.

Initial local verification used Qt 6.10.3, OpenSSL 3.0.13, GCC 13.3 and
Ubuntu 24.04. All 8 behavior cases passed (10 Qt Test results including
initialization/cleanup, zero skipped): explicit HTTP/2/direct override,
HTTPS download/parse, HTTPS redirects, h2c environment override, untrusted
certificate rejection, HTTPS downgrade rejection, shutdown cancellation and
the unprotected positive control.

A detached baseline checkout retained the original downloader blob
`20320ae5b753ba85cfe1f4e66823d4cf9952cc41`. Against identical tests, the baseline
failed direct HTTPS, redirected HTTPS and h2c cases, while the h2 positive
control passed. This proves the tests detect the exposed protocol path; it
is not a reproduction of the advisory's crash.

The portable tests observe parsed synthetic nodes using the existing
configuration-applier callback. They do not substitute that callback for
Windows DPAPI persistence or for Rust proxy interoperability. The focused
Windows product CI separately runs the existing encrypted subscription-refresh,
HTTPS redirect/downgrade and redirect-loop tests, as well as telemetry and capture
regressions. The capture tests retain concurrent inbound HTTP/2 streams and a
3 MiB response while requiring HTTP/1.1 at the Qt upstream destination.

Run the portable test with:

```sh
cmake -S src/Swirl.Quick/tests/qt-network -B build/qt-network -DCMAKE_BUILD_TYPE=Release
cmake --build build/qt-network --config Release --parallel 2
ctest --test-dir build/qt-network -C Release --output-on-failure
```

The `Qt HTTP client security` workflow runs the portable test on Linux, macOS
and Windows and the product regressions on Windows. Its status and artifacts
must be checked for the actual pushed commit; workflow presence is not a pass.
All network fixtures are synthetic loopback services. No private subscriptions
are refreshed, exposed or committed.

## Primary references and dependency follow-up

- [Qt advisory and official patch links](https://www.qt.io/blog/security-advisory-cve-2026-96432)
- [Qt request attribute semantics](https://doc.qt.io/qt-6/qnetworkrequest.html#Attribute-enum)
- [Qt 6.10.3 request and redirect implementation](https://github.com/qt/qtbase/blob/v6.10.3/src/network/access/qnetworkreplyhttpimpl.cpp)
- [Qt 6.10.3 connection type and ALPN selection](https://github.com/qt/qtbase/blob/v6.10.3/src/network/access/qhttpthreaddelegate.cpp)

These primary upstream references were reviewed before implementation. No
upstream implementation code or exploit was copied. Dependency follow-up remains
open: move the distributed Qt libraries to a fixed release or rebuild with the
official patch, verify Qt private GUI/font integrations and packaging, then
explicitly decide whether to restore HTTP/2. Changing a version string alone or
running this mitigation test does not verify a Qt library repair.
