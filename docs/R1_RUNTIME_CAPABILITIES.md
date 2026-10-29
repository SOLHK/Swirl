# R1 Rust runtime ownership and capability record

Date: 2026-10-22. R1 starts from
`b8aa4f6f40a091697e89ae4c8291789661edca60` on its own branch.
This document records source ownership and test requirements. A feature being
implemented here does not certify the user's 419 private subscription nodes,
physical Windows installation, or a new build that has not executed the gates.

## Ownership migration

| Former production responsibility | Rust owner / current Qt boundary | Remaining boundary |
| --- | --- | --- |
| `MihomoAdapter`, process control API and generated execution YAML | `RustCoreEngine` → `swirl-api::Controller` → `swirl-core::Core` | Qt holds UI/config data and bounded JSON FFI; no executable dispatch |
| `SwirlEngineManager` selection/fallback | `ThreadedEngine` constructs only `RustCoreEngine` | An unsupported node fails with its original data preserved |
| `SwirlProxyEngine` HTTP/SOCKS listener and TCP relay | `swirl-core` listener/session tasks; `swirl-protocol::accept/connect` | Qt has no proxy protocol listener |
| `NativeDuplexRelay` | Tokio forwarding and `swirl-transport` | Cancellation and counters belong to the Rust session |
| `SwirlUdpExchange` | `swirl-core::udp_associate` and `socks5_udp` | Supported UDP exits are explicit; other combinations fail |
| Legacy per-node probe runtime | `NodeTestService` dispatches to at most three `ThreadedEngine` workers | A batch reuses Rust sessions via configure; UI never runs FFI lifecycle calls |
| `ProxyLatencyProbe` selected-node HEAD/TLS timing | `TelemetryService::nativeProbeRequested` → live Rust `probe_start` | UI observes native snapshots, invalidates stale generations and bounds waiting |
| Windows system proxy | `SystemProxySession` and existing ownership guard | Retained OS integration, not a forwarding runtime |
| Node/subscribe/editor/storage | `NodeStore`, `NodeImporter`, `SubscriptionNormalizer`, `NodeImportService` | Keep encrypted source data and Clash-format parsing |
| Connections and traffic display | `TelemetryService::ingest` | Reads Rust counters, stores UI history; no derived success from mere listening |
| HTTP availability/IP display, DNS/router diagnostics | Qt data-service clients and OS diagnostics | Requests may use the Rust listener; these are separately named UI/OS observations, not node-latency substitutes |
| Capture, process and network pages | Existing Qt UI/platform services | Review separately before deletion; they are not wholesale legacy-proxy deletion candidates |

The retired engine-selection preference is no longer a QML property and is not
read by production. Its historical QSettings value is left untouched, so an old
`true` does not block Rust startup or reset unrelated user settings. The ordinary
Start action now uses the current stored node and routing mode instead of clearing
the selected ID before invoking Rust.

## Capability of the R1 baseline

| Capability | Source status and limits |
| --- | --- |
| HTTP proxy, HTTP CONNECT, SOCKS5 inbound | Native mixed listener; authenticated inbound configuration supported |
| TCP, IPv4/IPv6 | Native; DNS/connection address selection is bounded and failures are surfaced |
| SOCKS5 UDP inbound | Native bounded association; Direct, Shadowsocks AEAD and SOCKS5 exits; not every protocol supports UDP |
| HTTP/HTTPS CONNECT outbound | Native, optional authentication and verified TLS |
| SOCKS4 / SOCKS4a | Native; local/remote domain resolution semantics kept distinct |
| SOCKS5 outbound | Native TCP and opt-in UDP; TLS+UDP combination is rejected by the Qt converter |
| Shadowsocks | Native `aes-128-gcm`, `aes-256-gcm`, `chacha20-ietf-poly1305`; explicit UDP; limited HTTP simple-obfs |
| Shadowsocks 2022 / SSR / arbitrary plugins | Not executable in this baseline; imported data does not authorize fallback |
| Trojan | Native verified TLS, optional supported WebSocket; no Trojan UDP claim |
| VLESS | Native TCP/TLS/WebSocket and supported REALITY/Vision combinations; validated UUID/flow/auth fields |
| REALITY + Vision | Existing native authenticated transport; valid combinations and pinned-peer evidence must be rerun for the delivered SHA |
| VMess | No native `Outbound::Vmess` in the inspected R1 or parallel transport branch; importing VMess is not execution |
| WebSocket | Existing native VLESS/Trojan path; restricted headers/path/ALPN are rejected if unsupported |
| HTTP/2, gRPC, HTTPUpgrade, XHTTP | Independent transport branch implements these; not part of this baseline until explicitly integrated and tested |
| Hysteria2, TUIC | Import support exists on subscription work; no native outbound in inspected branches |
| Global / Direct / rules | Rust-owned; direct is an explicit user route, never fallback from missing selection |
| China domains/IP/MRS | Existing Rust loader accepts explicit verified directory or bundled rules; decisions use real matched domain/IP |
| Custom rules/groups | Supported exact/suffix/keyword domains, CIDR, source CIDR, destination port, MATCH; manual groups and bounded automatic groups; unsupported semantics reject |
| DNS | System/custom UDP/TCP and verified DoT/HTTP1 DoH; hosts maps, bounded caches and query-family policy. No Fake-IP/DoQ/DoH3 claim |
| Node switch | Native reconfiguration; old connections retain their immutable plan, new connections use selected config |
| Counters / connection lifecycle | Rust owns measurement and cancellation; Qt observes immutable snapshots |
| TUN / gateway forwarding / LAN listener / metered process takeover | Not implemented in this baseline. Enabling fails before saved data changes; configuration remains available to disable or edit |
| Subscription updates | Existing Qt importer/persistence remains; active immutable runtime is not silently replaced by a background refresh |

## Parallel branches inspected without merging

- `work/xray-v2ray-transport-20261022` at
  `fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870`: native transport modules,
  separate runtime transport configuration, test-peer and CI evidence. Its Qt
  converter still accepts only the earlier core protocol whitelist; do not infer
  end-user UI integration from standalone transport implementation.
- `work/xray-v2ray-qt-import-20261022` at
  `148757627e8ac8d310e75e1af850b9598a18e072`: lossless JSON import and
  `XrayJsonBridge::executableOutbound`; requires independent staged integration.
- `work/xray-v2ray-json-b-20261022` at
  `4e9f6ea0411c03bba418bb46884748ba7e0ba03b`: conversion work does not add
  a native VMess/Hysteria2/TUIC outbound to the inspected enum.

These are read-only snapshots, not assertions that the branches will stay at
those commits or that all their functionality is merged into R1.

## Node latency definition and regression coverage

The displayed node metric is a fresh Rust HEAD request through the chosen
outbound, ending at validated final response headers. It excludes UI polling,
process startup, response body and EOF waiting. It includes the node's resolver,
connection and protocol setup and, for HTTPS URLs, origin TLS. Existing fields:

- `outboundConnectMs`: cumulative node DNS + TCP + outbound handshake.
- `originTlsMs`: origin TLS duration, absent for HTTP.
- `latency` / `response_headers_ms`: cumulative time to final HEAD headers.

DNS, TCP and protocol handshake are still combined in `outboundConnectMs`;
individual phase durations must not be invented from this number. A
300–600 ms vs 50–60 ms observation cannot be attributed to the server without
same-node, same-URL, same-transport cold/warm measurements on the user's network.

R1 node batches keep at most three Rust sessions, select a new node on each
reused worker and release every listener at batch end/cancellation. A stale
snapshot for node A cannot complete node B's test. Telemetry attaches a unique
Qt request tag, accepts only its corresponding native result and invalidates it
on A→B→A route changes. A simultaneous manual URL request is explicitly rejected
as busy instead of being counted as the periodic URL's success.

New/updated Qt regression cases cover real HTTP forwarding across eight nodes
through two controlled exits, exactly three reused Rust sessions, unsupported
node rejection, UI heartbeat activity, released listeners, native telemetry
results, manual/periodic request collisions, untrusted target TLS rejection,
stale snapshots and bounded completion.
Execution results belong in the exact R1 validation report; merely adding these
cases is not a passing test result.

## Executed Linux integration evidence

On 2026-10-22, using commit `9a68ed685fac50891378823aa713569a380773bc`
plus this migration's working changes, CMake Release targets
`SwirlRustCoreTests` and `SwirlTelemetryTests` compiled against Qt 6.10.3 and the
paired, freshly built Rust library. The build directory was `build/r1-runtime`.
These are Linux results, not Windows product acceptance.

| Run | Actual result | Evidence / boundary |
| --- | --- | --- |
| Full `SwirlTelemetryTests` | 17 passed, 0 failed, 0 skipped; 1.347 s | `r1-telemetry.xml`; controlled Rust HTTP request, target TLS rejection, request collision, history/accounting |
| Focused Rust migration cases | 10 passed, 0 failed, 0 skipped including init/cleanup; 4.302 s | `r1-migration.xml`; retired preference, unsupported configuration, Qt facade, bounded worker reuse/cancel/listener release, response-header timing and selection reset |
| Full `SwirlRustCoreTests` | 42 passed, 28 failed, 9 skipped; 8.905 s | `r1-rust-qt.xml`; 28 Windows DPAPI persistence cases cannot save on Linux, which intentionally has no plaintext fallback; 9 independent-peer cases require their separate fixture environments |

The sandbox run could not bind local TCP listeners; the controlled loopback runs
above executed outside that network restriction. No private subscription node
credentials or user encrypted archive were used. Windows DPAPI and independently
launched external-peer tests still require their own matching CI evidence.

## Primary design references and license review

No upstream proxy implementation was copied or linked into production.

- [Qt worker objects and queued communication](https://doc.qt.io/qt-6/qthread.html),
  [QObject affinity and ownership](https://doc.qt.io/qt-6/qobject.html): each
  `RustCoreEngine` and its timer are created on its control worker thread; snapshots
  return via queued calls. Existing Qt licensing obligations remain unchanged.
- [Mihomo URLTest at 3f27ef39](https://github.com/MetaCubeX/mihomo/blob/3f27ef39f8c96bbfbc8b0b9bb10f5c9ef60149d8/adapter/adapter.go):
  reference-only inspection shows HEAD measurement and an optional second
  request under `UnifiedDelay`. The second request can reuse a connection and
  reset the measured start, so it is a different metric from a cold first request.
  [GPL-3.0 license](https://github.com/MetaCubeX/mihomo/blob/3f27ef39f8c96bbfbc8b0b9bb10f5c9ef60149d8/LICENSE)
  was checked; none of that code is copied into Swirl.
- [Loon official test configuration](https://loon0x00.github.io/docs/General/#测试)
  and [official example f5b97c72](https://github.com/Loon0x00/LoonExampleConfig/blob/f5b97c72dfe35283678c6da68b21c959ff30126d/example.conf):
  proxy and internet test URLs are distinct, and URL-test uses an HTTP-header
  request. These public configuration descriptions do not establish every
  internal timing boundary of the user's installed Loon build.

## Deletion candidates after replacement gates

`MihomoAdapter.{h,cpp}`, `MihomoLogDiagnostic.{h,cpp}`, the Mihomo manifest,
staging/download scripts and packaging resources; `SwirlEngineManager.{h,cpp}`,
`SwirlProxyEngine.{h,cpp}`, `NativeDuplexRelay.{h,cpp}`,
`SwirlUdpExchange.{h,cpp}`, and `ProxyLatencyProbe.{h,cpp}`.

`OwnedProcess` remains referenced by controlled test peers; move it to a
non-production test-support location or replace those fixtures before deleting
it. Remove old acceptance binaries/fixtures from product build inputs; do not
remove the new independent protocol peers used to prove Rust interoperability.

## R1-C/D physical removal checkpoint

The retired process adapters, C++ TCP/UDP forwarding, compatibility selection,
external control endpoint and downloader are physically removed in this stage.
Qt import/persistence, system proxy ownership/recovery, telemetry presentation
and capture/debugging services are retained. Source guards are not executable
acceptance: Windows compile, Qt tests, clean-package loader and public response
evidence must be obtained for the resulting commit before marking R1 complete.

The old process-termination UI test is not meaningful for an in-process core;
it would terminate Swirl itself. It is replaced by listener conflict, actual
in-process identity, UI start/stop/restart and released-port checks. Missing DLL,
wrong ABI/build/exports are tested using real shared-library fixtures.

The 17-format Qt subscription test still downloads over authenticated loopback
HTTPS, preserves secrets through DPAPI save/reload, refreshes stable IDs and
checks exact native configuration. Its old external-server execution is removed;
independent Python SS/Trojan/VLESS peer tests must separately run with the Qt
product integration executable. Mapping alone is never counted as networking.

R1-B public evidence received a certificate-verified HTTP 204 but failed during
TLS shutdown. The new public check requests HTTPS keep-alive then initiates
strict TLS shutdown itself. No close-notify, certificate or counter validation
is removed, and the earlier failure remains a failure. Private supplier nodes
and same-node Loon/Clash latency comparisons remain unverified.
