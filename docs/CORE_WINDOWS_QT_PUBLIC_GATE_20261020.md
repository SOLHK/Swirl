# Windows Qt public product gate (2026-10-20)

## Recovered source, stricter evidence retention

The recovered public gate is now a required step of the existing Windows Rust
workflow, before the complete Swirl.exe build. It uses the real Qt test binary:

`NodeImportService -> NodeImporter -> NodeStore/DPAPI -> EngineController ->
ThreadedEngine/RustCoreEngine -> in-process Rust Runtime -> REALITY -> VLESS ->
Vision -> independent pinned Xray -> public HTTP/HTTPS target`.

The user-facing engine receives synthetic subscriptions through its normal
import operation. The test destroys and recreates the controller, checks actual
encrypted storage, complete parameters and persisted selection, and then runs
**A/B x HTTP CONNECT/SOCKS5 x public HTTP/HTTPS**, eight requests. It asserts the
current process identity and in-process endpoint, listener cleanup and restored
B selection. Public targets remain the existing fixed allowlist:

- Microsoft connection-test GET: exact HTTP 200 body and Content-Length.
- www.rust-lang.org HEAD: HTTP 2xx/3xx, no redirect following, system-trusted
  certificate/hostname verification and TLS 1.3 with HTTP/1.1 ALPN.

No private provider, user subscription, external client core, credential refresh,
certificate bypass, dropped fingerprint or automatic DIRECT fallback is used.

## Independent assertions

Each Xray peer must independently record four accepted VLESS sessions, at least
four authenticated REALITY/verified ClientFinished sessions, two upload and two
download Vision Direct commands, and exactly two real TCP connections to each
pinned public destination. Camouflage application bytes must remain zero.
Missing peer evidence cannot be replaced by a successful Qt JSON report.

The public matrix uses global A/B selection. An imported rule-mode MATCH REJECT
check separately proves an actual loopback target is reachable, sends both raw
frontend protocols to Rust, requires exact policy error responses and verifies
zero target accepts. DNS failure cannot satisfy this new REJECT assertion.
The existing controlled product suites retain their DIRECT/REJECT/MATCH, A/B,
domain/suffix/keyword/port, TLS hostname rejection and half-close/echo-tail tests.

The resumed review found the original wrapper discarded partial Qt reports
when the executable failed. The gate now preserves a strict allowlist even on
nonzero exit or timeout: synthetic node A/B, frontend and bound proxy port,
fixed public target, request stage, HTTP status, numeric socket/TLS errors and
elapsed time. Arbitrary child fields and diagnostic strings are discarded.
Partial evidence remains a failure; successful validation still requires the
complete matrix, every product state and both independent Xray reports.

The artifact includes source identity and executable hashes. Raw synthetic
credential fixtures and peer logs remain temporary; only authored summaries
and redacted logs are uploaded. The verifier rejects a dirty/untracked source,
missing or skipped Qt execution, failed cleanup and weakened workflow blocks.

## Actual local checks and pending native work

- Nine public evidence tests passed, including missing/duplicate evidence,
  partial failure retention and timeout behavior.
- All 55 workflow guard tests passed; generator check is idempotent.
- The exact new C++ slot passed moc and C++23 syntax against real engine
  declarations and local Qt 6.4.2. An unused StoragePaths include requires a
  newer Qt for complete application compilation; this was not changed.
- Rust source is identical to the preceding validated subscription stage:
  324 regular tests plus one doctest, fmt/check/clippy passed locally.

Local source hashes and command details are in
[the gate evidence](evidence/CORE_WINDOWS_QT_PUBLIC_GATE_LOCAL_20261020.json).
**This checkpoint has not yet executed the new gate on Windows.** The exact
new-SHA Rust/App workflow results and public artifact must be inspected before
claiming Windows Qt Internet success. The existing private inspector build
target is also built/deployed in preparation for separate offline-cache checks.

Three additional full-Qt cases remain to be completed: inner TLS 1.2 with no
Vision Direct, incorrect REALITY/VLESS credentials, and cancellation after an
authenticated data transfer. Existing Rust Runtime cases cover these but are
not substituted for Qt product evidence. QSslSocket disconnection in the public
test is not independent proof of public close_notify receipt; the controlled
TLS origin separately verifies the close exchange and raw EOF.

Primary references: [Qt network proxies](https://doc.qt.io/qt-6/qnetworkproxy.html),
[QSslSocket verification](https://doc.qt.io/qt-6/qsslsocket.html), and the locked
[Xray source](https://github.com/XTLS/Xray-core/tree/92ccc939aaf4f8965f369cf0b142e005aeaa11d5).
Qt is the existing LGPL/GPL dependency and Xray is an MPL-2.0 independent test
peer. No upstream implementation is copied or new runtime dependency added.

Private provider authentication, the 59-node current candidate count and physical
Windows 11 remain unverified. Historical DNS/DoH/health-probe failures remain
unresolved. Frozen full-project acceptance stays **79 / 6 / 10.83%**.
