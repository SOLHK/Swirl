# Swirl Core: native Rust runtime and staged product migration

This workspace lives inside the existing Swirl product repository. The Qt/QML
interface is unchanged. It replaces actual forwarding with Rust when configured
using `SWIRL_USE_RUST_CORE=ON`; it does not wrap the C++ forwarder or Mihomo.
The default build preserves historical capabilities until their Rust replacements
are implemented and tested. This is **not the completed all-protocol product**.

## Current development scope (2026-10-19)

The [REALITY R3 gate](../docs/REALITY_XRAY_INTEROP_20261019.md) exercises the
native R2 TLS engine against pinned, unmodified official Xray/REALITY source.
It verifies source/module identity, repeats both executable builds and runs
12 tests / 13 synthetic loopback sessions: native X25519/hybrid authentication,
both Finished messages, bidirectional data, large/short I/O, authenticated
closure, credential rejection and timeout/cancellation/cleanup. Bare TCP EOF
remains an error without close_notify. The controlled local camouflage target
does not cover arbitrary public sites, browser fingerprints, real providers or
the full VLESS configuration path.

R3 source [`5ad68bcb22a23573d462cbfd972c7120093f504a`](https://github.com/SOLHK/Swirl/commit/5ad68bcb22a23573d462cbfd972c7120093f504a)
passed [Rust 39239280852](https://github.com/SOLHK/Swirl/actions/runs/39239280852)
on Linux/macOS/Windows, including Windows Qt and native application compilation,
and [App 39239280949](https://github.com/SOLHK/Swirl/actions/runs/39239280949).
The App archive's exact source was verified. Generic Windows Qt retained six
peer-hook skips, followed by five dedicated wrappers exercising those six slots;
neither the generic skips nor physical GUI coverage are relabeled as passes.

The [Vision R2 substage](../docs/VISION_ASYNC_INSPECTION_20261019.md) extends R1
with bounded incremental inner-TLS inspection and async framing/padding,
partial writes, backpressure, terminal-frame tails, cancellation and upload
half-close while retaining downlink reads. Its four full-Xray cases are three
inner-TLS-1.2 positive cases and one inner-TLS-1.3 Direct-request refusal.
The initial source [`f3ce257f14e59e82977d89ac4be436d08926c6b8`](https://github.com/SOLHK/Swirl/commit/f3ce257f14e59e82977d89ac4be436d08926c6b8)
passed Linux in [Rust 39243009089](https://github.com/SOLHK/Swirl/actions/runs/39243009089)
and [App 39243009132](https://github.com/SOLHK/Swirl/actions/runs/39243009132),
but its macOS/Windows Direct-refusal case failed; subsequent Windows Qt/native
application gates did not run. Those original failures remain archived.

Correction [`0be68231b15c1e4f69b138cda7bae0a3930d956b`](https://github.com/SOLHK/Swirl/commit/0be68231b15c1e4f69b138cda7bae0a3930d956b)
(tree `72cf2ebcb652baeefeb415be66ebe59184725697`) explicitly bounds both
ciphertext records and authenticated plaintext delivery. This lets Vision reject
command 2 before outer TLS consumes subsequent raw inner ciphertext. Five new
real-TLS regressions retain authentication, strict EOF, partial-read and
half-close guarantees; no DirectReady or raw-socket extraction was added.
Final [local evidence](../docs/evidence/vision-r2/record-boundary-local.json)
records 272 Rust tests plus one doctest and four mature-Xray cases passing
without relaxed assertions; the workflow guard suite has 41 cases.
[Rust 39246770262](https://github.com/SOLHK/Swirl/actions/runs/39246770262) passed
on Linux/macOS, and [App 39246770049](https://github.com/SOLHK/Swirl/actions/runs/39246770049)
passed with all 262 archived source files verified. Windows failed at an older
DNS fixture's UDP bind because the chosen TCP port was in that host's UDP
excluded range; its R3/Vision/Qt stages did not execute. The original
[Windows failure](../docs/evidence/vision-r2/record-ci-windows-failure.json) and
[Linux](../docs/evidence/vision-r2/record-ci-linux.json),
[macOS](../docs/evidence/vision-r2/record-ci-macos.json),
[App](../docs/evidence/vision-r2/record-ci-app.json) successes remain distinct.

The next test-fixture correction, `included with this commit`, queries Windows
TCP/UDP exclusions read-only, chooses a port outside their union and keeps both
sockets allocated. Query/parse failures and unknown 10013 errors remain fatal;
the existing eight collision attempts and non-Windows OS allocation remain.
Six selector regressions were added; final [local tests](../docs/evidence/vision-r2/port-pair-local.json)
passed DNS 37, Shadowsocks fixture 16 and guards 41 (94 total, no failures/skips).
New-source CI is **not yet executed**. Development preserves font commits
aab06bf/501099da/7dfbdda/b3ac464 and
6cba41ff43b989a240191a3731d9d8a5e29908b1.

DirectReady, raw-socket/residual-buffer handoff, eligible HRR processing,
production async REALITY and combined VLESS/REALITY/Vision remain unfinished.
The subscription-to-IR-to-route-to-runtime-to-Qt path is not enabled for these
requirements. Native import/startup preserve and explicitly reject unsupported
requirements; no failure falls back to DIRECT or ordinary TLS. Private
subscription updates remain disabled. See the [current handoff](../docs/CORE_REALITY_VISION_HANDOFF_20261019.md)
for original failure evidence and pending gates. The fixed acceptance baseline
remains **79 items, six accepted, weighted 10.83%**; B13/B14 remain partial.

After the automatic-font implementation passed its Windows application/font
gates, native Core development resumed on `work/core-completion-20261017`.
Rule editing now preserves trailing modifiers, validates the complete candidate
configuration and commits persistent state before publishing it; see the
[rule transaction evidence](../docs/RULE_EDIT_TRANSACTION_20261019.md).

The new standard SOCKS5 UDP outbound supports configured no-authentication or
username/password authentication, actual advertised relay addresses, bounded
associations and queues, control-stream shutdown and existing Qt import paths.
`udp` defaults to false; TLS plus UDP is explicitly rejected. A fixed socket
buffer minimum preserves the full datagram boundary across platforms without
reducing larger OS defaults. It does not change system network settings.
See the [implementation and exact CI results](../docs/RUST_SOCKS5_UDP_20261019.md)
for `8d045ab` and its `dc3ed5e` portability/test fix, including the first failures
and explicit skips. The Qt adapter and complete native application have their
own Windows gates; portable tests cannot substitute for those results.

The [fixed acceptance baseline](../docs/SELF_DEVELOPMENT_PROGRESS.md) remains
79 items and 10.83% accepted weight. SOCKS5 outbound UDP is now a partial
implementation; protocol profiles remain 0/21 fully accepted. No new private
provider, full subscription chain, REALITY/Vision or TUN acceptance is claimed.
The older dated sections below retain their original source and scope.

## Build and verification

Use stable Rust and a native C toolchain (ring builds C/assembly cryptography).
Previous Windows local validation: rustc 1.99.1, GNU x64, Qt 6.10.3, MinGW 13.1.0.
Cargo.lock pins dependencies; CI additionally checks Windows MSVC.

```text
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --release --locked --workspace --lib --bins
cargo build --release --locked -p swirl-transport --example reality-client
```

Configure the real desktop with CMake options `SWIRL_USE_RUST_CORE=ON` and
`SWIRL_BUILD_UI_TESTS=ON`. Cargo must be on the build environment PATH. Build
`Swirl` and `SwirlRustCoreTests`, then run CTest `swirl-rust-qt-integration`.
No Mihomo executable is staged into this build. The retained MihomoAdapter has a
compile-time start rejection in this mode, including legacy diagnostic callers.
Production sessions use RustCoreEngine through the existing ThreadedEngine
worker; isolated node tests instantiate RustCoreEngine directly. Forwarding and
protocol tasks execute in Rust. The old build and tests remain separately usable.

Python `tools/tests/test_rust_core.py` uses an independent socket/TLS peer and
ephemeral CA/leaf certificates (cryptography 50.0.2). Set SWIRL_RUST_HARNESS to
the built swirl-api executable. No global certificate trust changes occur.
`tools/Benchmark-RustCore.py` records loopback latency/throughput/CPU/memory and
optional public HTTPS checks; it does not claim private-node performance.

## Second capture and bounded connectivity diagnostics (2026-10-18)

The current stage continues from `13ea97af5c94198ecba4ed79b16cfc7b1b676f27` on
`work/core-completion-20261017`. All 16 subscription bodies were independently
encrypted and persisted before the second fixed cutoff; 14 are newly recovered
entries and two are refreshes. The first offline merge exposed an equal URI-alias
compatibility bug; after the parser fix, all 16 bodies passed the native parser
and canonical merging, decryption and body-hash verification succeeded. The old
window, three new windows and previous canonical version remain preserved. See the
[current stage record](../docs/RUST_CAPTURE_DIAGNOSTICS_VALIDATION_20261018.md)
for actual merge and later network outcomes; the older two-body evidence below
is historical.

`swirl-diagnose` accepts an endpoint only through stdin JSON and observes the
same TCP scheduler used by product connections. It emits address-family counts,
per-attempt timings and fixed outcomes without endpoint strings or raw OS errors.
`tools/Diagnose-NativeConnectivity.py` runs an independent system-DNS/socket
backend and this native binary serially within one ten-second sample budget;
their DNS budgets are 1500ms each. A successful probe sends no application data
and establishes only TCP reachability. Product timeouts remain unchanged.
The three immutable old SS samples were compared on hosted Linux: both engines
resolved four IPv4 addresses per sample and exhausted them with TCP timeouts;
each paired sample finished within 9.55 seconds. No IPv6 addresses were returned
and no sample reached SS obfuscation, authentication or HTTPS. These outcomes
are recorded as actual failures and do not identify the provider or network root
cause. All 16 imported full configurations remain explicitly non-executable as
complete configurations; their individual supported TCP candidates are separate.

The importer now preserves raw IPv6 hosts, refuses conflicting positional and
named INI parameters, keeps reserved characters in legacy SS passwords, and
strictly separates SIP002 percent decoding from legacy credentials. Equivalent
`peer/sni` aliases from the actual cached Trojan URI list now coalesce only when
decoded typed values agree; conflicting values and duplicate raw keys still fail.
URI UDP booleans remain declarations and do not imply native UDP support. Unknown
fields remain present and unsupported semantics cannot turn into DIRECT.
New independent Python SS and strict-TLS Trojan peers cover actual credentials,
forwarding and close, including expected certificate failures.
No Qt, QML or product settings are changed by this stage.

Final tested source `056fd56387e15d65259eff5f612b3ad7a1ce7009` passed
[Rust Core #35](https://github.com/SOLHK/Swirl/actions/runs/39093009560) on all
three platforms and [App #32](https://github.com/SOLHK/Swirl/actions/runs/39093009558).
Each platform passed 125 Rust tests, fmt/check/strict Clippy and Release builds.
Linux/macOS each passed 162 Python cases with four Qt-only skips; Windows passed
198 distinct Python cases after Qt supplements, with two optional skips. Qt6.10.3
build and CTest1/1 passed, as did four independent Qt protocol peers. Three strict
public DIRECT/DoH HTTPS checks passed. Earlier Windows/macOS fixture failures are
preserved with their source identities; Windows OS refusal actually took about
two seconds, while native scheduling and product deadlines were not changed.
Subsequent handoff updates affect only documentation and JSON evidence; the
compiled source, tests and workflows remain identical to this tested commit.

## Previous connection/policy stage evidence

Continue `work/core-completion-20261017`, not the older main or test head. The
previous connection/policy stage continued from `d27fcc74ed549f2219f97da1f5c56a83bace3ac1`.
It adds bounded TCP fallback across an already resolved address set, one deadline
for outbound DNS/TCP/TLS/protocol establishment, and static failure-stage fields.
It also connects the existing Qt custom-group settings to nested manual selectors
and the supported native automatic policies. The UI and stored source settings
are preserved; unsupported semantics still fail before activation.

Implementation commit `11eafea` and cross-platform fixture correction
`99ad9b3e71b7aeb9b5ff1f8c418550561f59fd63` are pushed. The latter passed
[Rust Core #32](https://github.com/SOLHK/Swirl/actions/runs/39061540612) on all
three platforms and [App #29](https://github.com/SOLHK/Swirl/actions/runs/39061540617).
Each platform passed fmt, check, strict clippy, 101 workspace tests and release
builds. Linux/macOS each passed 131 of 135 Python cases, with four explicit Qt
skips. Windows passed 167 of 169 distinct Python cases after four Qt supplements;
only optional C++ importer and real CLI cases remain skipped. Windows Qt/MSVC
build and CTest passed 1/1 in 6.92 seconds. Exact results, skips and source identities belong in the
[historical connection/policy validation](../docs/RUST_CONNECTION_POLICY_VALIDATION_20261017.md).
The subsequent evidence update changes only documentation; preserve it when
continuing from the actual branch HEAD. No private-provider connection passed.
The 2026-10-17 report for three cached SS samples recorded `UpstreamTcpTimeout`
at `tcp_connect`, before HTTP obfuscation or SS authentication. That historical
report lacks DNS or per-address timing; the 2026-10-18 paired diagnostics above
now include those measurements, while the underlying cause remains unresolved.
All 90 cached Trojan entries remain rejected because their configuration disables
certificate verification. Three strict public native DIRECT/DoH checks passed;
their success is separate from private-provider validation.

The preceding [DNS/subscription stage](../docs/RUST_DNS_SUBSCRIPTION_VALIDATION_20261017.md)
already completed hostname-shared positive caching and validated SOA negative
caching. Its three-platform #30 evidence is bound to `f13c695`, not to the new
connection or Qt group changes. Earlier evidence is retained below with its
original scope.

### Historical policy, SOCKS4 and WebSocket-close evidence: 58969bc and 5dbe762

The earlier policy stage continued from `0bf2666` and made the automatic-policy
candidates executable: nested manual groups, native HTTP/HTTPS health probes,
`url_test`, `fallback`, per-session `load_balance`, immutable session choices,
bounded scheduling and cancellation are connected to the IR, router and API.
See [policy semantics](../docs/RUST_NATIVE_POLICIES.md) and the
[historical policy validation](../docs/RUST_POLICY_VALIDATION_20261017.md) for tested
source identities, results, skips and remaining work.

That stage also connected SOCKS4/4a subscription-inspector conversion and the
existing Qt import/adapter chain, preserving USERID and local/remote DNS
semantics. New Qt SOCKS4 and VLESS WS forwarding slots use independent Python
peers and passed Windows CI on `5dbe762`: six imported SOCKS4/4a HTTP sessions and
a 131073-byte VLESS WS origin response. Qt CTest passed 1/1 in 3.12 seconds;
the existing independent SS/VLESS Qt paths also passed. At that stage,
automatic/nested policy groups were an IR/API capability without Qt group-editor
mapping; the current mapping is described separately below.

WebSocket shutdown now has one two-second budget starting at the first close
request, covering queued output, writes, flush, peer close and transport shutdown.
Local Rust fmt, check, clippy, workspace tests and release compilation have passed
for that integration. [Swirl Rust Core #25](https://github.com/SOLHK/Swirl/actions/runs/39033762503)
passed on Linux/macOS/Windows with 83 Rust tests each, all 13 independent policy
tests on each platform, and three strict Linux public HTTPS/DIRECT/DoH checks.
The implementation commit is `58969bc`; the existing App added only nine reviewed
workflow lines in `5dbe762`. Complete Python counts, explicit skips, Qt results
and downloaded public evidence belong in the historical policy validation record.
QML and product UI are preserved. The
[architecture audit](../docs/RUST_CORE_AUDIT_20261017.md) is explicitly a historical
`8bd89f2` audit, with a header pointing to these subsequent changes.

### Historical WebSocket and public-network evidence: 510c62a through c0eb221

The following commits, counts, binary hashes and Actions runs belong to the
previous WebSocket/public-network stage. They do not validate the later policy,
SOCKS4 conversion, Qt peer slots, shutdown or subsequent connection-stage changes.

That stage's WebSocket implementation was published as
[`510c62a`](https://github.com/SOLHK/Swirl/commit/510c62ade64418c76241bbe76ae118c5040dad92).
The existing GitHub App job then successfully pushed
[`a60c446`](https://github.com/SOLHK/Swirl/commit/a60c446fdb54c10753c2d367752c4e0275a89922),
changing only `.github/workflows/rust-core.yml` (+23/-1). The resulting workflow
SHA-256 is `c40f0a47abafd50a7ebe6782c25572578544920263439d3ac249125a22c6e9e8`.
[Core implementation validation #17](https://github.com/SOLHK/Swirl/actions/runs/39029146435)
records the successful App-token generation, checkout and workflow commit/push;
this establishes actual Workflows write access without changing the App or Secrets.
[Swirl Rust Core #21](https://github.com/SOLHK/Swirl/actions/runs/39029167841)
completed successfully on `a60c446` at 2026-10-17 11:42:56 UTC. Linux, macOS and
Windows each passed 57 Rust tests and 64 independent Python protocol tests.
The two Qt-dependent Python cases were skipped in those initial protocol runs;
Windows subsequently executed both the SS and VLESS Qt paths against independent
peers successfully. Windows Qt CTest also passed 1/1 in 3.09 seconds, including
the new WS configuration acceptance/rejection regressions. Actual forwarding
through the Qt WS mapping remains a separate, unverified case.

The follow-up verification fix is published as
[`c0eb221`](https://github.com/SOLHK/Swirl/commit/c0eb2211ea646da023119e9458139d538a311000).
The first public run's `failed=1` / `StreamIo` came from the verification client
closing its TLS socket without completing TLS and TCP shutdown. The client now
completes TLS shutdown, half-closes TCP and drains EOF; the verifier requires
zero session errors and completed connection records. The Rust relay was unchanged.
[Core implementation validation #19](https://github.com/SOLHK/Swirl/actions/runs/39030037978)
passed. In [Swirl Rust Core #22](https://github.com/SOLHK/Swirl/actions/runs/39030038029),
Linux, macOS and Windows each passed 57 Rust tests, 69 of 71 Python
protocol/verifier cases (two Qt-dependent skips), and all 11 workflow regression
tests. Windows then passed the Qt CTest target (1/1, 3.17 seconds) and separately
ran both Qt forwarding cases successfully. The complete run finished successfully
at 2026-10-17 11:56:56 UTC.

The #22 Linux job passed all three strict public HTTPS/DIRECT and native DoH
checks with authenticated TLS 1.3, HTTP 200/301/200 and positive traffic counters.
Each session had `orderly_close=true`, `accepted=1`, `active=0`, `failed=0`,
an empty `last_error` and exactly one recorded connection. The
[verified report](../docs/evidence/RUST_PUBLIC_NETWORK_20261017_VERIFIED.json)
identifies `c0eb221` and the same Rust binary SHA-256 as the initial run;
see the stage validation above for both reports and the controlled comparison.

At that historical baseline, the three policy/probe files were unintegrated
candidates. The later policy stage declared them in their crate roots, connected
the runtime call paths and executed their tests; that evidence is recorded
separately in the historical policy validation document.

## Explicit DNS query family

Native `dns.query_family` accepts strict strings `dual` (the unchanged default)
and `ipv4_only`. The latter sends A queries only to explicit UDP/TCP/DoT/DoH
upstreams; pure OS lookup rejects it. It does not disable IPv6 literal targets,
static hosts, IPv6 upstream endpoints, or remote DNS performed by a proxy server.
Qt maps `queryFamily` and preserves it across legacy settings edits; compatibility
builds reject the native policy instead of dropping it. No UI control or complete
Clash DNS import is enabled. See [scope and verification](../docs/RUST_DNS_QUERY_FAMILY_20261018.md).

## Encrypted DNS: DoT and HTTP/1.1 DoH

DNS-over-TLS is now implemented in Rust using explicit IP bootstrap endpoints
and separately verified authentication names. The existing DNS wire parser and
rustls transport are reused. A/AAAA/CNAME queries reuse one authenticated stream
per lookup, with bounded deadlines, generation-isolated TTL caches and no
plaintext/system-DNS fallback. `tools/tests/test_dns_tls.py` supplies independent
synthetic TLS peers; it is run by Rust CI alongside the original protocol tests.

The same resolver now also executes authenticated RFC 8484 HTTP/1.1 POST with
bounded HTTP headers, exact/chunked bodies and cache-age handling. Existing Qt
encrypted-DNS fields map strict `tls://` or `https://` URLs; domain URLs need an
exact local IP mapping. No GUI is changed. Encrypted DNS connects directly to the
explicit resolver, not through proxy policy. Positive entries are shared by
hostname across destination ports. Validated NXDOMAIN and combined A/AAAA NODATA
use SOA negative caching, including CNAME and DoH cache-age restrictions; see
[local DNS cache semantics](../docs/RUST_LOCAL_DNS.md).
Bounded one-second resolution-failure caching is implemented; see
[failure-cache evidence](../docs/RUST_DNS_FAILURE_CACHE_20261018.md).
System bootstrap, mixed resolver mode, DNS split and HTTP/2 remain later work. DoH has its own
independent peer suite, `tools/tests/test_dns_https.py`. See the historical
[DoT semantics](../docs/RUST_DOT.md), the earlier
[DoH/public-network evidence](../docs/RUST_WS_VALIDATION_20261017.md) and the
[completed DNS-stage validation](../docs/RUST_DNS_SUBSCRIPTION_VALIDATION_20261017.md)
and the [historical connection/policy validation](../docs/RUST_CONNECTION_POLICY_VALIDATION_20261017.md).
The old DoT-only document's exclusions do not override the implemented DoH
behavior described here.

## TCP address fallback and connection diagnostics

`swirl-protocol::connect` creates one absolute outbound-establishment deadline.
Locally resolving the target or proxy endpoint, every TCP address attempt, TLS,
WebSocket Upgrade and protocol negotiation consume that same budget. The existing
inbound handshake and route-required DNS lookup retain their separate limits.
No timeout is increased to make a failed node appear usable.

The dialer uses only the resolver's returned socket addresses, at most 16. It
removes duplicates, preserves the resolver's first-family preference and ordering
within each family, and interleaves the families. While attempts are still pending,
new launches are staggered by 250 ms, with at most two pending sockets. A failed
or retired attempt frees its slot immediately for the next address, avoiding an
artificial delay that would exhaust a valid 100 ms handshake budget. If untried
addresses remain when an attempt is launched, that attempt is capped at two
seconds so later addresses can obtain a slot; the last address, or a single-address
result, keeps the remaining overall
budget. This cap is a local resource/availability tradeoff, not an RFC requirement.

The current resolver returns its address set after lookup completion. This change
does not implement full RFC 8305 DNS answer streaming, address history, network
interface selection or NAT64 synthesis. It follows the address-interleaving and
stagger/cancel principles in [RFC 8305 sections 4–5](https://www.rfc-editor.org/rfc/rfc8305),
with independently written scheduling over Tokio socket futures. The
[sing-box resolved-address dialer interface](https://github.com/SagerNet/sing-box/blob/testing/protocol/direct/outbound.go)
and [Tokio TCP API](https://docs.rs/tokio/latest/tokio/net/struct.TcpStream.html)
were reviewed as primary design references; no proxy-core implementation is copied.
The immediate completed-failure behavior follows the observable behavior covered
by [Go's standard-library dial tests](https://github.com/golang/go/blob/master/src/net/dial_test.go).
RFC 8305 also specifies a minimum attempt delay; this bounded fast-failure policy
is not presented as complete conformance to every RFC timing requirement.

Route-pinned IP literals remain single-address destinations. The dialer never
re-resolves their original hostname or borrows another address's policy. For a
normal proxy domain target, only the configured proxy endpoint is resolved
locally; the target domain remains in the native proxy request. A winning TCP
connection drops all losing futures before TLS or proxy/application bytes.
TLS, certificate, authentication or protocol failure never restarts address
selection or falls back to a different proxy or DIRECT.

Snapshot `last_error_stage` describes the latest recorded failure. Each connection
record has its own static `error` and `failure_stage`; successful records use empty
strings. These values contain no server-supplied text or credentials.

| Failure stage | Representative static error codes |
|---|---|
| `dns` | `UpstreamDnsTimeout`, existing `Dns*` and `RouteDns*` errors |
| `tcp_connect` | `UpstreamTcpTimeout`, `UpstreamConnectFailed`, `UpstreamAddressLimit` |
| `tls_handshake` | `UpstreamTlsTimeout`, `TlsVerificationOrHandshake` |
| `websocket_upgrade` | `WebSocketUpgradeTimeout`, existing Upgrade validation/read/write errors |
| `protocol_handshake` | `UpstreamProtocolTimeout`, existing authentication/rejection and protocol-write errors |
| `http_obfs` | `ShadowsocksObfsWrite`, `ShadowsocksObfsWriteTimeout` |

The HTTP-obfs category covers the initial framed write. Its later lazy response
and SS decryption errors still surface as `StreamIo`; no fixed first-response
idle timeout is added. Other known boundaries include `initial_write`, `inbound`
and `routing`; ambiguous legacy errors remain `unknown`. A stage narrows where
the failure occurred without claiming that a password, server certificate or
provider is the root cause. Current tests and private-node limitations are tracked
in [connection/policy validation](../docs/RUST_CONNECTION_POLICY_VALIDATION_20261017.md).

## Implemented boundary

| Crate | Actual implementation | Not yet implemented |
|---|---|---|
| swirl-subscription | Versioned typed Swirl IR; bounded content detection for Clash YAML/JSON, sing-box JSON, URI/Base64 and INI; raw/unknown field preservation; redacted capability matrix; mapped TCP/WS and SOCKS4/4a candidates; validated DoT/DoH settings, explicit probes and bounded policy membership graphs | Complete client-specific config execution and integrated subscription updating; existing C++ adapters and Python capture retained; arbitrary imported full configurations and unsupported group semantics are not automatically executable |
| swirl-protocol | Mixed HTTP/CONNECT/SOCKS4/4a/5 input, input auth, HTTP CONNECT/SOCKS4/4a/5 upstream, explicit standard SOCKS5 UDP with control lifetime and strict authentication, Trojan TLS, SS AEAD TCP/UDP, simple-obfs HTTP TCP, VLESS v0 TCP/TLS; native VLESS WS/WSS and Trojan WSS framing; native HTTP/HTTPS health requests; bounded multi-address TCP, one establishment deadline and static failure stages | SS2022/SSR/VMess/REALITY/QUIC families, VLESS Vision/mux/encryption extensions, other protocol UDP, SOCKS5 TLS+UDP and obfs TLS; full RFC 8305 asynchronous DNS behavior |
| swirl-transport | rustls TLS with verification/SNI/ALPN, including origin TLS over an existing native proxy stream; bounded duplex copying, independent TCP half-close and live byte counters; the bounded WS driver currently resides in swirl-protocol | gRPC/XHTTP, mux and QUIC; WS close is full duplex and does not promise TCP half-close semantics |
| swirl-routing | Ordered domain/suffix/keyword, source/destination CIDR, destination port and final rules; lazy configured DNS and pinned IP decisions; bounded nested manual groups and session-bound automatic choices; Qt mappings for nested manual and supported automatic groups | Process rules, GEOIP/GEOSITE/MRS, reevaluation/retry of alternative destination IPs after CIDR-based selection; automatic-group members that are themselves groups |
| swirl-dns | Rust custom UDP/TCP DNS, strict DoT and HTTP/1.1 DoH with explicit IP bootstrap; validated A/AAAA/CNAME, hostname-shared positive TTL cache and strict SOA negative cache; system resolver, exact hosts through Qt, immutable caches, shared 8-query budget, max 16 addresses | Combined system/custom mode, proxy-routed encrypted DNS, domain bootstrap, EDNS/DNSSEC, RFC 9520 failure cache, DNS split/Fake-IP |
| swirl-core | Two Tokio workers, max 256 sessions, immutable per-session configuration and policy view; bounded health scheduling, `url_test`/`fallback`/round-robin groups, atomic updates, stop/cancel and stats; SOCKS5 UDP ASSOCIATE with explicit DIRECT, SS AEAD or standard SOCKS5 routes | Other protocol UDP, TUN, platform network takeover and long-duration performance validation |
| swirl-api | ABI v1 caller-buffer JSON, lifecycle handles, start/configure/select/select_group/snapshot/stop; explicit policy input and redacted health reports; per-connection static errors/stages and snapshot last-error stage; local stdin harness | Complete product configuration migration and persisted IR migration |

The Qt adapter contains mappings for supported HTTP/SOCKS4/4a/5/Trojan/SS AEAD/VLESS
nodes, including the limited VLESS/Trojan WS combinations, through existing
controls. SOCKS4/4a now has subscription-inspector conversion plus Qt import,
normalization and Rust-IR mapping. Those SOCKS4/WS forwarding slots passed the
historical Windows #25 CTest and Python peers; this is not
a complete desktop package or personal-machine visual check. SOCKS4 USERID is not password authentication;
unsupported passwords, TLS, UDP and other extensions are rejected explicitly.
Unsupported options fail explicitly before startup or selection. In
particular, old default smart-routing/TUN/unsupported DNS sessions are not silently
downgraded to global/direct. Existing stored nodes and unselected unsupported
imports are preserved. Complete product migration still requires those features.
Custom rule mode is now connected to the existing rule editor and runtime rule
list. See [native routing semantics and evidence](../docs/RUST_NATIVE_ROUTING.md),
including no-resolve, mode switches, DNS address pinning and unsupported options.
The existing system/custom DNS modes and local mappings execute in Rust; see
[local DNS semantics and limits](../docs/RUST_LOCAL_DNS.md) and the newer
[strict DoT stage](../docs/RUST_DOT.md).

The current Qt adapter additionally maps existing `select` groups with bounded,
acyclic nested references, and `url-test`, `fallback` and `load-balance` groups
with explicit HTTP/HTTPS health URLs. Automatic groups require concrete members;
they cannot probe another group. Load balancing requires an explicit
`strategy: round-robin`, because the native per-session behavior does not implement
Mihomo's default hashing semantics. Unknown fields, unsafe probe settings,
missing members and cycles fail before startup or saving. Source mappings and
Qt regressions were built and executed in Windows #32 at `99ad9b3`: CTest 1/1
passed, together with all four independent Qt protocol supplements. This includes
the new nested automatic-policy data paths, round robin and atomic settings tests;
the successful CTest log does not publish an internal QtTest case total.

The Rust-only build is an opt-in development artifact, not a replacement that
silently removes capabilities from the user's normal installation.

`swirl-inspect` reads a document on stdin and reports only anonymous capabilities.
The explicit `--private-json` pipeline returns original parsed fields and isolated
TCP candidates. It may feed authorized local encrypted persistence or in-memory
evaluation in the approved private archive workflow, never public logs or artifacts.
It never derives
protocol support from subscription/client/node display names. Missing versions
remain `not-declared`. Unknown fields remain in the original/parsed document and
block executable conversion when their semantics are not known. YAML has explicit
node/depth/event/alias budgets, duplicate-key rejection and no include resolver.

`tools/Analyze-CapturedSubscriptions.py` sends decrypted bytes to this Rust parser
over stdin, re-encrypts private results with DPAPI and emits a redacted report.
It can generate bounded Rust-only HTTPS HEAD tests for supported TCP candidates;
UDP and full-config semantics remain separately unverified. It reads cache after
the website window closes and never needs a subscription refresh for offline work.
Local exports use `SubscriptionCapture.py import-file <file> <cache>` with no
network access. Plaintext downloads and local exports stay out of Git; the approved
private repository retains encrypted archives and whitelisted reports only.
INI detection accepts leading comments and standalone DIRECT/REJECT policy
entries. String credentials retain their type, and conflicting canonical/alias
parameters fail explicitly instead of overwriting one another. Anonymous test
cases distinguish parsed, blocked, not-tested, passed and failed evidence;
unsupported certificate policies and TCP Fast Open have explicit diagnostics.

## Shadowsocks AEAD implementation

Swirl owns SIP004/SIP007 framing, address encoding, nonce sequencing, stream
state and UDP association handling. Supported ciphers are aes-128-gcm,
aes-256-gcm and chacha20-ietf-poly1305. ring provides AEAD, HKDF-SHA1 and OS random
bytes; RustCrypto md-5 implements the protocol's legacy password derivation.
No complete proxy core or simple-obfs executable/library is linked or launched.
HTTP obfs is its wire framing implemented in Rust, not TLS or WebSocket security.

TCP chunks are at most 16383 bytes; malformed lengths, truncated records, bad
tags, reflected salts and counter exhaustion fail closed. Authenticated empty
chunks yield cooperatively. Partial reads/writes retain state, buffers are bounded,
and half-close drains encrypted output before shutting down its socket direction.
The process-local TCP replay window is 600 seconds and UDP is 30 seconds, with
separate 65536-entry caps. Exhaustion fails closed; unexpired entries are not
evicted. This is bounded process-lifetime replay protection, not persistent
protection across application restarts or arbitrarily old replays.

SS UDP has independent random salt and zero nonce for each authenticated packet.
SS IR must explicitly set `udp: true`; missing/false keeps UDP disabled. Import
and Qt mappings preserve this choice instead of enabling UDP implicitly.
The SOCKS association owns both UDP sockets, pins the local client, tracks at most
64 remote endpoints for 30 seconds, and refuses ambiguous key/route reuse for the
same endpoint. Payload statistics exclude AEAD and SOCKS framing. HTTP obfs applies
only to TCP. SS proxy UDP has independent Python-peer evidence; private-provider
UDP has not been tested. Oversized packets and SOCKS fragments are dropped.
Per-datagram route/DNS/send failures and recoverable ICMP socket errors are
counted as `udp_dropped` without closing the association. Up to four bounded
preparation tasks keep DNS waits from blocking incoming replies. Existing
associations retain their immutable configuration snapshot across updates.

The offline mapper supports plain SS AEAD and explicit HTTP obfs options from
Clash, supported INI forms and SIP002 plugin strings with escaped delimiters.
Unknown options, unsupported plugins, TFO=true,
SS2022 and insecure Trojan certificate policies remain explicit execution blockers.
No source parameters are altered to make a test pass. Private node material stays
within the authorized local or private encrypted-archive workflows.

Protocol references: https://shadowsocks.org/doc/aead.html and the official
simple-obfs HTTP wire implementation at
https://github.com/shadowsocks/simple-obfs/blob/master/src/obfs_http.c .
The latter is a protocol reference only; no GPL source is copied into the product.
Independent Python cryptography peers exercise all three ciphers, TCP/UDP,
HTTP obfs, IPv4/IPv6/domain targets, partial records, half-close, tampering,
replay and the Qt facade. Run `tools/tests/test_shadowsocks.py` with
SWIRL_RUST_HARNESS and optionally SWIRL_RUST_QT_TESTS pointing to built executables.

## Bounds and ownership

VLESS supports the version-0 TCP request layout used by the reference Xray
implementation, canonical UUID authentication, IPv4/IPv6/domain target encoding,
and optional generic TLS. It does not import or execute Xray. The response prefix
is decoded lazily because the peer may wait for application data; partial header
bytes survive cancellation and a partial-header deadline uses the configured
handshake limit. Waiting for the first application response has no fixed idle
cutoff. Unknown versions, nonempty addons, flow/Vision, REALITY, multiplexing,
gRPC/XHTTP/QUIC transports, UDP and encryption extensions are rejected rather than stripped.
Python independent peers verify plain/TLS forwarding, invalid UUID, certificate
name rejection and malformed response prefixes; a Qt peer test verifies the
existing product adapter. Private-provider VLESS is unverified. Reference:
https://github.com/XTLS/Xray-core/blob/main/proxy/vless/encoding/encoding.go .

- IR/control input <=1 MiB, <=512 nodes, <=4096 rules, <=256 active sessions.
- <=128 policy groups, <=16 group depth; <=32 automatic groups, <=64 members per
  automatic group and <=512 automatic member jobs. Four active probes per core
  share one concurrency budget across configuration generations. Health views
  freeze at TCP accept; an established UDP association keeps the same view.
- HTTP headers <=16 KiB/64 fields; handshake <=30 seconds. No blanket idle timer
  on established TCP streams. Duplex uses two 16 KiB buffers with backpressure.
- Outbound DNS, bounded TCP address attempts, TLS and proxy handshake share one
  deadline. At most two TCP candidates wait concurrently; no post-TCP-success
  address retry, authentication downgrade or application replay is permitted.
- UDP control connection owns one association; exact client IP/port pinning,
  fragments dropped, <=65507-byte datagrams. Explicit DIRECT, SS AEAD and
  standard SOCKS5 (`udp: true`, without TLS) routes execute UDP. DIRECT/SS keep
  <=64 recent destinations with a 30-second response allowance. SOCKS5 keeps
  <=16 upstream associations including closed-node tombstones, with no implicit
  reconnect in the same inbound association. All UDP preparation/queued sends
  share four in-flight permits; SOCKS5 replies share a four-entry queue. Its
  connected UDP socket checks the relay source, with a 30-second recent-send
  window per relay, not a per-destination verification claim. Control EOF
  cancels pending sends and invalidates queued replies. See the exact scope and
  independent evidence in [SOCKS5 UDP validation](../docs/RUST_SOCKS5_UDP_20261019.md).
- Resolver permits remain owned by pending OS lookup tasks after caller timeout,
  limiting detached work. Runtime shutdown waits at most 500ms for OS resolver
  work; Qt uses PreventUnloadHint so late OS completion cannot call unloaded code.
- Snapshot history retains 128 completed sessions plus active sessions. Targets
  are private control-plane data; credentials and config documents are not logged.
- Updates validate before swapping the immutable plan. Old streams keep their
  selected outbound; a failed update retains the last valid plan. An application
  connection failure never triggers request replay or a retry through another
  proxy/direct route. Automatic health-based decisions apply to new session views.
- ABI callers must supply valid nonoverlapping buffers; unsafe is limited to
  copying them at the FFI edge. All protocol/runtime crates forbid unsafe code.
  TLS/crypto dependencies have their own audited low-level implementations.

TLS trusts Mozilla WebPKI roots by default. An explicitly provided DER/base64 CA
can add a local trust anchor without disabling hostname/signature validation or
reading a filesystem path. The Qt mapper currently accepts public-root TLS only;
it does not silently ignore unsupported pins or certificate options.

## Evidence interpretation

Rust tests use actual loopback sockets and independent Python protocol peers.
Public HEAD tests through Rust DIRECT only establish that path, not remote
SOCKS/Trojan provider operation. TLS/Trojan/DoT loopback tests establish the tested
framing and certificate behavior, not all public servers or private extensions.
Local private subscription capture and offline parsing have been exercised;
this does not establish working provider connections. TUN, real provider traffic,
Codex remote control, mobile actions, long soak tests,
visual acceptance and non-Windows products are still unverified.
The App workflow includes separate public-origin HTTPS and native DoH checks
with fixed endpoints and actual byte counters. As historical evidence, the #22 Linux run passed
the stricter HTTP/TLS, connection-count, traffic and orderly-shutdown gates.
The initial run's `failed=1` / `StreamIo` was resolved by fixing verification-client
shutdown. Both runs used Rust binary SHA-256
`7e83e9b89232f4712335ca9e4d8e6f3dacbb52b5f2daefbe357055792ce132d9`.
The earlier local public-network attempt failed and remains recorded separately.
These are earlier-stage binary hashes and results, not current-source evidence.
Exact historical run identities, the initial and verified reports and scope are recorded in
[`RUST_WS_VALIDATION_20261017.md`](../docs/RUST_WS_VALIDATION_20261017.md).
Use [`RUST_CAPTURE_DIAGNOSTICS_VALIDATION_20261018.md`](../docs/RUST_CAPTURE_DIAGNOSTICS_VALIDATION_20261018.md)
for the current stage's test counts, exact commit and actual CI status.
Public DIRECT success does not prove a provider's WS endpoint,
private subscription or all product settings. The user's personal Windows
visual/private-node testing remains deferred.

The original C++ native engine, encrypted NodeStore, importers, proxy recovery,
subscription capture utility and regression tests remain available. No Go/C#
network core or Rust workspace was present in the audited `main` baseline
`87409c0bf9c957ef113f84c176c5a1529c27b9df`. The development branch already
contained the Rust workspace when the earlier WS stage began at `8bd89f2`.
The policy stage continued from `0bf2666`, the completed DNS stage followed it,
and the previous connection/Qt-policy stage continued from `d27fcc7`. The current
capture/diagnostic stage continued from `13ea97a`.

## Primary specifications

- SOCKS5: https://www.rfc-editor.org/rfc/rfc1928
- SOCKS username/password: https://www.rfc-editor.org/rfc/rfc1929
- HTTP message syntax: https://www.rfc-editor.org/rfc/rfc9112
- DNS over TLS: https://www.rfc-editor.org/rfc/rfc7858
- DNS over HTTPS: https://www.rfc-editor.org/rfc/rfc8484
- WebSocket framing and control: https://www.rfc-editor.org/rfc/rfc6455
- DNS privacy profiles: https://www.rfc-editor.org/rfc/rfc8310
- TCP address-interleaving and stagger/cancel principles: https://www.rfc-editor.org/rfc/rfc8305
- Trojan: https://trojan-gfw.github.io/trojan/protocol.html
- Tokio half-close semantics: https://docs.rs/tokio/latest/tokio/io/fn.copy_bidirectional.html
- rustls: https://rustls.dev/docs/rustls/index.html

See the merged requirements in `docs/SWIRL_CORE_DEVELOPMENT_CONTRACT.md`, and the
separate compatibility/evidence reports. Third-party versions, source URLs and
licenses are listed in DEPENDENCIES.json; release bundles include their notices.
