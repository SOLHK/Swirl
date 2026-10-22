# X1.2-C native transport development

Branch: `work/xray-v2ray-transport-20261022`. Baseline:
`ff2e2ad76022a2742b1eb256fdb8058873ca1a3e` (X1.2-A).
The four requested remote heads were read before work:

| Branch | Observed HEAD |
| --- | --- |
| work/xray-v2ray-json-import-20261021 | ff2e2ad76022a2742b1eb256fdb8058873ca1a3e |
| work/xray-v2ray-native-20261021 | b88bb978d31fad1865e1b648cecd4f230bc3487c |
| work/subscription-import-20261021 | bf40f6dd639b0a9583a0dbea8e50851ac0c9ed29 |
| work/rust-core-network-fixes-20261021 | b8aa4f6f40a091697e89ae4c8291789661edca60 |

The A branch contains the other three baselines. A separate git worktree and
branch were created; no B conversion files, main, fonts, UI or rule data were
changed. This is a Linux cloud checkout, not a write to the user's D drive.

## Evidence vocabulary

Parsing, native connector implementation, independent server interoperability,
and authorized public connectivity are separate claims. Tests here use synthetic
loopback credentials and independent official server executables. A TCP/TLS
handshake alone is never counted as a proxy request. No private provider node
or subscription was used. Reference proxy cores run only as test servers.

## Baseline audit

| Transport | Baseline implementation | Baseline protocol dispatch |
| --- | --- | --- |
| TCP/raw | bounded resolver and address racing, TCP half-close | VLESS, Trojan/TLS and existing other protocols |
| TLS | rustls, explicit extra CA, SNI and requested ALPN, certificate verification | existing `secure` path |
| REALITY | native authenticated record stream, existing Vision owner | VLESS/raw only |
| WS/WSS | bounded RFC6455 binary driver, masking, fragmentation, Ping/Pong, close timeout, Drop cancellation | VLESS and Trojan; Host/Path, no arbitrary headers |
| gRPC | absent | absent |
| legacy HTTP/2 | absent | absent |
| HTTPUpgrade | absent | absent |
| XHTTP | absent | absent |

TCP resolves once, bounds attempts to 16 addresses and two in flight, drops
losers before authentication, and shares one DNS/connect/handshake deadline.
Relay uses fixed 16 KiB buffers and independent directional shutdown. These
verified components were retained. WS close is a full-duplex protocol close;
it cannot promise TCP's independent half-close semantics.

## C1 checkpoint

Added bounded custom WebSocket headers without changing the existing WebSocket
IR: maximum 32 headers and 8 KiB, token names, validated values, no duplicated
names or override of Host/Upgrade/Connection/framing/Sec-WebSocket fields.
Host still comes from the explicit settings field. `?ed=` (including an encoded
key) is explicitly rejected; no incompatible early-data implementation is used.

The additive `swirl_protocol::connect_with_transport` accepts a typed
`Transport`. Existing `connect` and all existing subscription structures remain
available. `tcp` and `raw` select the same unframed connection. TCP HTTP-header
camouflage and unrepresented fields are rejected rather than ignored. Unknown
fields on the empty TCP variant are tested (the variant must be a struct, not a
Serde unit variant). Explicit and legacy WebSocket settings cannot conflict.
The transport selection belongs after TCP and applicable security, before the
existing proxy authentication bytes.

Independent official Xray v26.10.21 tests require actual accepted requests in
its access log and exact responses from a separate destination server:

| Combination | HTTP + verified target HTTPS | Other evidence |
| --- | --- | --- |
| VLESS/raw | passed | new raw-alias API passed |
| VLESS/TLS/raw | passed | verification errors rejected |
| VLESS/WS | passed | non-root Path, Host, custom headers, >2 MiB binary and eight concurrent requests |
| VLESS/WSS | passed | same, IPv6 socket/authority, active server interruption |
| Trojan/TLS/raw | passed | existing authentication and target TLS reused |
| Trojan/WSS | passed | inner target TLS close_notify observed |

Wrong Host, Path, UUID, CA and SNI are rejected. The target is not contacted for
those failed requests. Six independent test methods have zero failures and
zero skips. Existing independent Python WS peers run 11 methods with one
explicit Qt-only skip. Rust workspace: 409 passed, zero failed/ignored,
including 16 WebSocket-focused tests. fmt/check/clippy all pass with `--locked`
where applicable. Actual logs and summary are under `evidence/transports/c1/`.

### Retained close limitation

The new example records close status separately from verified payload success.
Its WSS case observed `transport_error` after receiving the complete valid
response. The pinned Xray WebSocket server sends Close(1000), then immediately
closes its connection instead of waiting for the client's close reply. A race
with the reply/TLS shutdown is a source-supported explanation, not yet an
independently instrumented root cause. Swirl does not convert
this error into a successful closing handshake. The strict controlled RFC6455
close tests pass, as do the independent target TLS close_notify tests. **Do not
describe all official Xray WSS closes as clean.** This is an explicit C1 gap,
not a reason to disable certificate checking or weaken EOF validation.

Current upstream also defaults to rejecting private destinations. The test
server explicitly authorizes only its own loopback origins in freedom
`finalRules`; the product routing code is unchanged.

## C2 implementation and limits

The native gRPC connector sends a bidirectional streaming `POST` to the exact
Xray/V2Ray `serviceName` method path. It supports both `Tun` (`Hunk`) and
`TunMulti` (`MultiHunk`): uncompressed five-byte gRPC envelopes, protobuf bytes
field number one, and terminal `grpc-status`. Custom service/method paths and
upstream percent escaping are covered. No unary RPC or HTTP CONNECT is used.
The adapter removes RPC message boundaries and returns the original proxy
byte stream to the existing VLESS/Trojan authentication code.

TLS uses the existing certificate/SNI verifier. HTTP/2 adds `h2` only when the
ALPN offer is empty; an explicitly incompatible offer or an incompatible
negotiated protocol is an error. Plain gRPC uses prior-knowledge HTTP/2 only
with a server that actually permits it. User metadata cannot replace framing,
gRPC status or hop-by-hop headers. Unsupported keepalive/window configuration
fields are rejected by the typed config; configurable active PING keepalive
is not implemented. The `h2` library handles peer PING, SETTINGS, flow control,
GOAWAY and stream resets. No failed request is replayed.

The HTTP/2 adapter uses 16 KiB write chunks, 64 KiB receive windows and an
explicit 64 KiB send-buffer limit per stream. A connection owns one driver
task. Up to 64 active or retiring streams are permitted per internal session;
the retirement queue shares that bound. Dropping an unfinished upload cancels
it. After an explicit write shutdown, dropping the application stream retains
its response in the same driver for at most one second, allowing queued final
DATA/END_STREAM to reach the peer. This avoids losing a nested TLS
`close_notify` to an immediate CANCEL. It does not turn write shutdown into a
wait for the response: independent half-close remains available.

A gRPC message is limited to 4 MiB; decoding can temporarily retain both the
encoded and decoded message, approximately 8 MiB at that maximum, in addition
to HTTP/2/socket buffers. Ordinary 16 KiB chunks use much less. Direct gRPC
read-to-EOF validates terminal status; after a caller drops a stream (including
after nested TLS has independently reached its authenticated EOF), background
draining is resource cleanup and cannot report a late status to that caller.
The test client reports application close, exact payload integrity and remaining
runtime tasks separately and waits for actual driver completion before exiting.

C2 verification: all four required Rust gates passed; 430 workspace tests
including doctests passed with zero failed/ignored. The independent current
Xray suite passed all 11 test methods, zero failures/skips, in 5.243 seconds.
It covers Tun/TunMulti, plain and verified TLS gRPC, custom service paths,
VLESS/Trojan authentication, real HTTP and verified inner HTTPS responses,
8 MiB bidirectional transfers, eight concurrent cancellations, bad credentials,
bad service/SNI/CA/ALPN, server interruption, bounded timeouts and clean close.
Actual commands, output and per-attempt evidence are under
`evidence/transports/c2/`. A transient local doctest dependency-artifact mismatch
was resolved before the final successful serial run; no test was removed or
changed to hide that failure. A similar local incremental-artifact collision
reappeared during C3 without concurrent edits, so concurrency alone is not a
proven root cause. C3 clears only generated local crate artifacts and repeats
the complete gates. Fresh C2 CI checkouts passed the unit/doctest gate on all
three platforms; macOS has also completed the full C2 interoperability job.

## C3 legacy HTTP/2

This connector implements the legacy streaming `PUT` request/response bodies
from Xray 1.8.24, not CONNECT. It requires verified TLS and negotiated `h2`,
preserves authority, decoded configured Path and allowed headers, and passes
the body byte stream directly to VLESS/Trojan. Unsupported plaintext and method
overrides are explicit errors. HTTP errors, GOAWAY, RST_STREAM, flow control,
half-close and cancellation share the tested HTTP/2 engine from C2.

Current Xray 26.10.21 explicitly removed the old transport; this checkpoint's
independent peer is exactly Xray 1.8.24 / `6baad79`. Eight independent test
methods passed in 3.978 seconds, exit zero: 28 native invocations with 14
positive results and 14 expected rejections. Positive cases include VLESS and
Trojan, custom Host/Path/headers, HTTP and verified target HTTPS, an 8 MiB duplex
flow and eight concurrent cancellations. Target TLS close_notify and process
task completion are observed separately. Wrong Host/Path, authentication,
CA/SNI/ALPN, invalid method/header, timeout, interruption and fresh-connection
recovery are covered. There is no automatic replay of an interrupted stream.

The shared internal session supports multiple simultaneous independent streams
on one connection and has direct regression tests for reuse and GOAWAY.
Production outbound connections currently create their own sessions: a
cross-outbound connection pool and Host-list selection are not implemented.
The config accepts one resolved Host; B must not silently discard a Host list.
C3's final serial fmt/check/clippy/test gates all passed after the generated
artifact cleanup: 432 tests including doctests, zero failed/ignored. Evidence
and the actual independent-server command output are in
`evidence/transports/c3/`.

## C4 HTTPUpgrade

The native connector sends HTTP/1.1 `GET`, `Connection: Upgrade` and
`Upgrade: websocket`, validates the status and both response tokens, and then
exposes the unframed byte stream. It is separate from the RFC6455 WebSocket
engine: there is no masking, binary message envelope or WebSocket Close frame.
An upgrade response and first proxy bytes arriving together retain the tail
in a buffered reader. Request headers are bounded to the pinned server's
12 KiB limit, response headers to 16 KiB. Wrong status/tokens, forbidden header
overrides and early data are errors. HTTP/1.1-compatible TLS ALPN is validated;
the existing certificate/SNI verification remains mandatory.

The current official dialer also emits optional Sec-WebSocket-Key/Version
headers. The pinned official listener explicitly accepts the no-key handshake
implemented here. This is direct-server compatibility, not evidence that a
middlebox requiring a complete RFC6455 opening handshake will accept it.
REALITY is not supported by this upstream HTTPUpgrade listener.

C4's independent current-Xray suite passed nine methods in 3.705 seconds,
exit zero: 22 native invocations, 13 successful transfers (seven clean closes,
six explicit cancellations) and nine expected rejections. Both plain and TLS
4 MiB duplex flows, custom literal Unicode/percent/query-like Path, Host,
VLESS/Trojan with verified target HTTPS, six concurrent connections, invalid
authentication/CA/SNI/ALPN/Host/Path, truncation, server termination and fresh
connection recovery passed. Target reciprocal TLS close_notify was observed
twice; every native result had zero remaining runtime tasks. Five focused
HTTPUpgrade Rust tests include wrong status/tokens and same-packet upgrade tail.
All four Rust gates and a complete native workspace build passed; 437 tests
including doctests, zero failed/ignored. Evidence: `evidence/transports/c4/`.

HTTP parsing reuses already-locked `httparse` 1.10.1 and `url` 2.5.8, both
MIT/Apache-2.0; URL declares Rust 1.63. The only C4 lockfile change connects
these existing dependencies to the transport crate; no package version changed.

## C5 XHTTP supported subset

This stage implements **explicit `stream-one` over HTTP/2**, both verified
TLS/H2 and prior-knowledge H2C when the server enables it. A single full-duplex
POST carries raw proxy bytes in its request and response bodies. The upstream
`application/grpc` camouflage header does not imply a gRPC/protobuf envelope.
There is no session ID, sequence counter, split download channel or packet
upload in this mode. Path normalization and query preservation follow pinned
upstream semantics; the default Referer contains cryptographically randomized
100–1000-byte `x_padding`. Header limits reserve the maximum padding size before
dialing, avoiding random configuration acceptance near the limit.

`auto`, `packet-up`, `stream-up`, HTTP/3/QUIC, XMUX tuning, downloadSettings,
custom padding placements/ranges and other unrepresented `extra` options are
explicitly unsupported. No mode falls back to TCP, WebSocket, gRPC or another
XHTTP mode. In particular, upstream `auto` with ordinary TLS usually chooses
packet-up, so it cannot be mapped to stream-one. The upstream plain client
defaults to HTTP/1.1 whereas this implementation's plain subset is explicit
H2C; the pinned official server permits that H2C subset. A future B conversion
must first apply upstream `extra` precedence (top-level host/path/mode remain,
other settings come from extra), then reject settings this connector cannot
represent. There is no attempt to resume/replay a partially sent proxy request.

Repeated module registration in this container exposed stale local Rust
incremental metadata (`StableCrateId` / missing rlib) despite unchanged tests.
For C5 and subsequent local gates, only generated workspace artifacts were
cleared and `CARGO_INCREMENTAL=0` disables caching. Source semantics and test
coverage are unchanged. Independent fresh-checkout CI is a separate check.

C5 verification: ten independent current-Xray methods passed in 2.674 seconds,
exit zero. Of 31 native invocations, 14 succeeded (six clean and eight explicit
cancellations), 17 were correctly rejected. TLS/H2 and H2C, VLESS/Trojan,
verified target HTTPS, Unicode Path and query, Host, 8 MiB duplex data, eight
concurrent connections, bad credentials/CA/SNI/Host/Path, server interruption
and a fresh connection passed. Unimplemented modes/options were rejected.
Target TLS close_notify completed twice and every native result had zero
remaining tasks; fixture cleanup had no errors. All four required Rust gates
passed with 441 tests including doctests, zero failed/ignored. Exact local
evidence is under `evidence/transports/c5/`.

### Platform issue found while C5 ran

C2's [three-platform run 39720068070](https://github.com/SOLHK/Swirl/actions/runs/39720068070)
passed completely. C3's [run 39720581183](https://github.com/SOLHK/Swirl/actions/runs/39720581183)
passed Ubuntu/macOS, but Windows failed the unchanged two-second assertion
that all eight cancelled legacy-H2 target sockets close. All eight native
clients had correct hashes and zero driver tasks; the legacy official server
logged all eight CANCEL frames. This is retained as a failure, not converted
to success. Old Xray's Windows `readv` implementation is the current suspect;
C6 will validate a fixture-only upstream-option workaround with the same
official binary and unchanged transport/closure assertions.

## C6 native runtime and security integration

`Core::start_with_transports(Config, BTreeMap<String, Transport>)` and
`Core::configure_with_transports(Config, map)` add an explicit, immutable map
keyed by concrete node ID. The map is validated before starting listeners or
policy workers. Selection, manual groups, automatic groups, ordinary sessions,
manual HEAD probes and automatic GET health checks all use the same map.
Existing `start` keeps its legacy behavior. Existing `configure` preserves and
revalidates the map; removing/renaming a mapped node cannot silently revert to
raw TCP. Replacing configuration and map is atomic, and accepted sessions keep
their previous immutable map. Four Rust transaction tests cover rejected
activation, preserved probes/generation, old-session ownership and replacement.
The shared WebSocket preflight also rejects literal or percent-encoded `ed`
queries before activating an explicit Core map or starting DNS/socket work;
previously the same rejection occurred only after the outer connection opened.

The independent Core suite additionally exercises two real gRPC/XHTTP TLS
nodes, concrete/group selection, both probe types, rejected XHTTP `auto`, and
wrong service/path failures without reaching a target. Its four methods passed
locally, with 19 actual authenticated Xray requests after deduplicating the
per-peer cumulative log counts. The existing WS/WSS cases also verify an active
session survives reconfiguration, cancellation closes its target socket, and
the listener is unavailable after Core stop. This is actual Core operation,
not only direct calls to the new transport client example.

### REALITY and ALPN semantics

The existing REALITY record engine and Vision owner were retained. The protocol
boundary now wraps an authenticated REALITY stream in gRPC or XHTTP before
writing VLESS bytes. A conflicting TLS or legacy WebSocket setting is rejected.
REALITY with WebSocket, HTTPUpgrade or legacy HTTP/2 is rejected; non-raw Vision
is rejected. There is no ordinary TLS fallback, insecure verification, or
replacement of the fixed Chrome 133 ClientHello profile.

ALPN has a deliberate upstream distinction. Ordinary TLS gRPC/HTTP2/XHTTP must
negotiate `h2`; missing ALPN or an HTTP/1-only server is rejected before proxy
bytes. An empty caller offer is extended with `h2`, while an explicitly
incompatible offer is rejected. Three controlled TLS-only tests verify that
behavior; they are not proxy interoperability evidence.

In Xray v26.10.21,
[`reality/config.go`](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/transport/internet/reality/config.go)
deliberately sets `NextProtos` to nil. Its pinned REALITY dependency
[`83f621788ca88b83179810b12baa7ae518aacb83`](https://github.com/XTLS/REALITY/tree/83f621788ca88b83179810b12baa7ae518aacb83)
therefore sends no selected ALPN in EncryptedExtensions. The official gRPC
dialer and XHTTP dialer/listener start HTTP/2 with prior knowledge after REALITY
authentication. Applying the ordinary TLS requirement here initially rejected
all new positive combinations, and that failed test run is retained.

The corrected rule preserves the advertised `h2` offer (or the fixed Chrome
offer), permits absent selected ALPN only on the already authenticated REALITY
path, and rejects a present incompatible selection. A focused regression covers
these cases. Four independent wire observations (gRPC/XHTTP × rustls/Chrome133)
reported authenticated handshakes with `alpn=null`; these observations sent no
proxy payload and are not counted as full interoperability. The subsequent
full suite passed ten methods: 41 native attempts, 21 successful transfers
(13 clean closes, eight deliberate cancellations), and 20 expected rejections.
It includes gRPC Tun/TunMulti, XHTTP stream-one, both fingerprints, HTTP,
verified target HTTPS, 4 MiB duplex data, concurrent cancellation, bad key,
short ID, SNI, UUID and target certificate. Every native driver drained to zero.
The official peer reported 25 authenticated REALITY sessions, 25 verified
client Finished messages and 23 accepted VLESS requests; the latter include
two intentionally rejected target certificates. Camouflage application bytes
and record-size failures were zero. Raw REALITY and raw REALITY+Vision also
passed; the Vision peer observed actual Direct commands in both directions.

### Windows legacy-server lifecycle condition

The C3/C4/C5 Windows failures are preserved in `evidence/transports/c6/`.
The official v1.8.24 Windows reader calls blocking `WSARecv` from its readv
path; current Xray adds a readiness handoff before that call. C6 starts only
the **legacy Windows test server** with its supported
`xray.buf.readv=disable` setting. The pinned executable, protocol settings,
eight concurrent cancellations and two-second closure assertion are unchanged.
Every fixture report records this environment override. Linux/macOS and the
current-version server do not receive it. This is a test-server compatibility
condition, not a claim that v1.8.24's default Windows readv behavior was fixed
inside Swirl. Its result still requires the C6 Windows job.

### Capability matrix at the C6 source boundary

| Native selection | VLESS | Trojan | REALITY | Vision | Independent server scope |
| --- | --- | --- | --- | --- | --- |
| TCP / raw | plain or TLS | TLS | VLESS only | VLESS/raw/REALITY | current Xray |
| WS | plain | not represented without TLS in existing Trojan IR | rejected | rejected | current Xray, VLESS |
| WSS | verified TLS | verified TLS | rejected | rejected | current Xray; close limitation above remains |
| gRPC Tun / TunMulti | H2C or TLS | TLS; independent Trojan case uses Tun | VLESS, authenticated H2 prior knowledge | rejected | current Xray |
| legacy HTTP/2 PUT | TLS | TLS | rejected | rejected | Xray v1.8.24; removed in current Xray |
| HTTPUpgrade | plain or TLS | TLS | rejected | rejected | current Xray |
| XHTTP stream-one | H2C or TLS | TLS | VLESS, authenticated H2 prior knowledge | rejected | current Xray |
| XHTTP auto / stream-up / packet-up | rejected | rejected | rejected | rejected | not implemented |
| XHTTP HTTP/1.1 / HTTP/3 / XMUX / separate download settings | rejected or unrepresented typed fields | same | same | same | not implemented |

The Trojan/XHTTP independent case uses an HTTP destination; verified HTTPS over
XHTTP is separately established with VLESS. Trojan/TunMulti is not an independently
tested combination here. Core-level map/probe tests cover WS/WSS, gRPC and XHTTP;
legacy HTTP2 and HTTPUpgrade have direct native connector/protocol interoperability
evidence, without a separate Core map/probe-specific server case.

VMess has no native connector in this baseline, for any of these transports.
`spiderX` is not represented by the existing REALITY IR and is rejected as an
unknown field, not silently discarded. The existing ordinary TLS IR does not
offer arbitrary uTLS fingerprints or insecure certificate settings. Explicit
unsupported options must remain errors in B's adapter. Cross-outbound HTTP/2
pooling, configurable active gRPC keepalive and non-default XHTTP padding are
not implemented. The shared internal HTTP/2 session supports bounded stream
reuse in tests; the production connector currently creates one session per
outbound connection. No stream or proxy request is automatically replayed
after a network interruption; tests verify a fresh explicit connection works.

### Public-target attempt

A separate manual test attempted `http://example.com/` and
`https://example.com/` through the local independent Xray server. Xray accepted
both VLESS target requests, but its outbound DNS lookups failed with connection
refused/timeouts. The direct preflight also failed system name resolution.
The test exited 1 with two native `OperationTimeout` results and zero remaining
tasks. No public response or verified public HTTPS result was obtained. No DNS
or trust settings were changed. An authorized remote public proxy node was
not supplied or tested. This failure is retained and does not qualify as
public connectivity success.

### Final local source and release regression

All four required Rust commands passed on the final C6 source in a fresh Cargo
target directory: **446 tests passed**, zero failed/ignored, including doctests.
An earlier reused local directory produced an E0460 stale `swirl_api`/`swirl_core`
artifact error before tests executed; that failure is archived separately. No
test was removed or weakened. The final release build includes the workspace
dynamic library, binaries and every example. The release transport client has
SHA256 `f4fa8cfb328d8f9f38ce96d8dba588c1ff4df406276c4cd12d4fc09f06ed50b6`.

| Final release suite | Methods | Actual exit code | Evidence scope |
| --- | ---: | ---: | --- |
| C1 TCP / WS / WSS | 6 | 0 | 35 accepted official-server proxy requests; WSS outer-close gap retained |
| C2 gRPC | 11 | 0 | 37 native attempts: 24 positive, 13 expected negative |
| C3 legacy HTTP/2 | 8 | 0 | 28 native attempts: 14 positive, 14 expected negative |
| C4 HTTPUpgrade | 9 | 0 | 22 native attempts: 13 positive, nine expected negative |
| C5 XHTTP stream-one | 10 | 0 | 31 native attempts: 14 positive, 17 expected negative |
| C6 Core selection/probes | 4 | 0 | 19 accepted official-server proxy requests |
| C6 ordinary TLS ALPN | 3 | 0 | controlled trusted TLS-only peers; not proxy interoperability |
| C6 REALITY / raw Vision regression | 10 | 0 | 41 native attempts: 21 positive, 20 expected negative |

That is 61 Python test methods, of which 58 belong to suites using independent
official Xray servers. A passed method can deliberately assert rejection of
an invalid request; the attempt counts above separate those cases. All observed
native runtime driver counts drained to zero. Input-syntax rejections that occur
before constructing a runtime have no task-count field and are not represented
as measured runtime results. Exact commands, output, binary hashes and summaries
are committed under `evidence/transports/c6/`. These local Linux results do not
stand in for a later Windows/macOS CI execution.

### Finite release resource measurements

The Linux release benchmark exited 0 without retries. It uses VLESS and
verified outer TLS for every transport, the same loopback origin and byte
pattern, three 16 MiB uploads plus simultaneous 16 MiB downloads per transport,
one 64 KiB warmup and 20 subsequent 64 KiB lifecycle connections. All 144
connections met exact hash/byte-count and clean-close assertions. No Cargo or
other transport suite ran during these measurements. Legacy H2 necessarily
uses Xray v1.8.24; all other rows use v26.10.21, so these figures must not be
presented as a controlled comparison of transport efficiency alone.

| TLS transport | Median payload MiB/s per direction | Connector return ms | Native peak RSS KiB | Native CPU user / system s |
| --- | ---: | ---: | ---: | ---: |
| raw | 214.36 | 1.220 | 4,600 | 0.05 / 0.01 |
| WSS | 195.19 | 1.349 | 5,132 | 0.09 / 0.03 |
| gRPC | 162.86 | 1.281 | 5,520 | 0.09 / 0.03 |
| legacy HTTP/2 | 140.12 | 1.375 | 5,488 | 0.09 / 0.05 |
| HTTPUpgrade | 182.44 | 1.620 | 4,932 | 0.06 / 0.02 |
| XHTTP stream-one | 145.47 | 1.579 | 5,516 | 0.09 / 0.03 |

Each-direction throughput is 16 MiB divided by the complete duplex-transfer
interval; the sum of directions is twice that value. Connector return time
excludes process startup and can precede deferred response/authentication
checks, which are included in transfer time. GNU time CPU/RSS covers the native
client process including startup/shutdown, excluding Xray and Python. The
machine is a Linux x86_64 container on an AMD EPYC 9V74 host; raw measurements,
exact commands, environment and hashes are in `benchmark-release.json` and
`environment.json` under the C6 evidence directory.

Persistent server descriptor counts remained 9 for current Xray and 8 for
legacy H2 after warmup, every transfer and each sequential connection; target
active sockets ended at zero. Clients are fresh processes per connection, so
this is finite resource-release evidence, not proof that a long-lived native
runtime has no leaks. WSS clean closes in this particular echo benchmark do
not erase its separately observed non-clean close for the C1 HTTP response.
There is no WAN, Clash, Loon or third-party-client performance comparison.

## Upstream pins and independent implementation

* [Xray v26.10.21 / 1b1647c](https://github.com/XTLS/Xray-core/tree/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74): MPL-2.0. Read `transport/internet/{websocket,grpc,httpupgrade,splithttp,tls,reality}` and `infra/conf/transport_internet.go`.
* [Legacy Xray v1.8.24 / 6baad79](https://github.com/XTLS/Xray-core/tree/6baad79f9881ee2cf75bdc825b3e2e92b289477a): MPL-2.0; retained legacy HTTP/2 fixture. Current Xray rejects that removed transport, so current-version H2 transport support is not claimed.
* [V2Ray v5.39.0 / 8eef1bb](https://github.com/v2fly/v2ray-core/tree/8eef1bbfb1b4bdb3919b4e27a89abb0fa3252d6f): MIT; gRPC and HTTP streaming wire/configuration comparison.
* [sing-box v1.13.3 / d3768cc](https://github.com/SagerNet/sing-box/tree/d3768cca3602c2949417fe767c1acd88d7f67698): GPL-3.0-or-later with upstream additional condition; architecture reference only. No source or runtime core imported.
* [RFC6455](https://www.rfc-editor.org/rfc/rfc6455): WebSocket opening handshake, binary fragmentation and closing behavior.

Official executable archive SHA256 values are fixed for Windows x64, Linux
x64, macOS x64 and arm64 in `tools/tests/transport-peer-lock.json`.
`tools/Fetch-TransportPeers.py` checks the complete archive digest, extracts only
the selected executable, then checks its version and commit identity. The
reference server is never included in Swirl's runtime dependency tree.

Installed skill discovery found no applicable Rust/network engineering skill.
The repository's only bundled skill is UI/UX-specific and was not applied to
this transport-only task. `AGENTS.md`, the continuation handoff and Core
development contract were read; this user's dedicated C branch instruction
supersedes their older branch destination.

### Rust component selection

The workspace already uses Tokio 1.53.3, patched rustls 0.23.46,
tokio-rustls 0.26.6 and bytes 1.12.1. New HTTP/2 framing uses exactly
`h2 = 0.4.20`, `http = 1.5.0` and `bytes = 1.12.1`, checked against their
published manifests, source and licenses. Their declared minimum Rust versions
(1.63, 1.57 and 1.57 respectively) fit this workspace's Rust 1.89 minimum.
`h2` is MIT, `http` is MIT/Apache-2.0, and `bytes` is MIT. The lockfile change
adds the required HTTP/2 graph without upgrading the existing Tokio/TLS graph.

Hyper 1.12.0 (MIT), tonic 0.14.6 (MIT), futures-util 0.3.34 (MIT/Apache-2.0),
and tokio-tungstenite 0.30.0 (MIT) were reviewed. A direct `h2` adapter avoids
adding a generated RPC client/runtime for this small fixed wire schema and
also supplies the raw streaming bodies needed by legacy HTTP/2 and XHTTP.
The existing verified WebSocket engine remains in place. Quinn 0.11.12,
h3 0.0.8 and h3-quinn 0.0.10 (MIT/Apache-2.0 or MIT as declared upstream)
were inspected for possible HTTP/3 follow-up; no QUIC stack is added or claimed.

### C1 platform evidence

Commit [`4ad768303f4dbea289d87714974e752f544c2542`](https://github.com/SOLHK/Swirl/commit/4ad768303f4dbea289d87714974e752f544c2542)
passed all three jobs in [run 39717767373](https://github.com/SOLHK/Swirl/actions/runs/39717767373):
Ubuntu, Windows and macOS. Each job ran the Rust gates, release dynamic-library
and example build, and independent C1 server suite. These are exact-C1 results,
not evidence for a later unexecuted revision.

## B integration boundary

`Transport` is deliberately outside `swirl-subscription`, avoiding changes to
B's JSON parser, six-protocol mapping and existing internal outbound shape.
B can pass a validated `Outbound` and separate native `Transport` into
`connect_with_transport`. Unsupported options must remain explicit errors;
import success alone must not change execution capability reporting.
VMess does not exist in this pinned native protocol baseline; an enum in an
importer cannot make it executable. New transports will be tested with the
implemented VLESS and Trojan connectors and report VMess separately.

During C2, the B branch advanced to
[`4606b6df484cd0504014b9bdac6cb237a813c9b3`](https://github.com/SOLHK/Swirl/commit/4606b6df484cd0504014b9bdac6cb237a813c9b3).
It was fetched and reviewed without merging. Its four changed files are the
conversion workflow, `xray.rs`, `xray/convert.rs` and conversion tests. There is
no edit to existing Outbound/Config structures or Core/protocol/transport files.
That checkpoint is offline projection and archival: transport/security details
remain accessible as source JSON, `network_verified()` is false, and it has no
native Core adapter. Its `ValidationStatus::Valid` must not be used as an
execution-capability signal; inspect capability diagnostics separately.

The downstream adapter must explicitly map B's classification enum to this
settings-bearing transport enum (their serialized names are not identical).
Security stays in `Outbound.tls/reality/flow`. Explicit WebSocket selection
requires `Outbound.websocket = None` to avoid conflicting configurations;
Host goes to `settings.host`, custom headers remain a separate list. An
unsupported option must return an error, never omit the selection and thereby
invoke legacy raw TCP. The adapter belongs at protocol/Core/API level, avoiding
a `subscription -> protocol -> subscription` dependency cycle. This branch
does not take over B's parameter conversion.

For full Core integration, B's downstream adapter should pass the map to
`start_with_transports` / `configure_with_transports` in the same transaction
as `Config`. Map keys are the final concrete `Config.nodes[*].id`, including
each node produced by server/user expansion, never a group ID. Supplying an
empty map is an explicit return to legacy settings; omitting an unsupported
transport entry is not a valid conversion. This C branch exposes and tests the
native boundary but does not add the B JSON-to-Core adapter or modify B's files.
Some new transport errors retain the legacy generic diagnostic stage while
preserving their exact fixed error code; a separate diagnostic-vocabulary
change should distinguish configuration, handshake and stream failures rather
than classify every `Grpc*` / `Http2*` error as a handshake failure.

## Reproduction

From `core/`:

```sh
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --release --workspace --lib --bins --examples --locked
```

From the repository root, with `SWIRL_XRAY_BINARY`, `SWIRL_RUST_HARNESS`,
`SWIRL_TRANSPORT_CLIENT` pointing to the pinned server and native binaries:

```sh
python tools/tests/test_transport_c1_xray.py -v
python tools/tests/test_transport_grpc_xray.py -v
python tools/tests/test_transport_http2_xray.py -v
python tools/tests/test_transport_http_xray.py -v
python tools/tests/test_transport_xhttp_xray.py -v
python tools/tests/test_transport_runtime_xray.py -v
python tools/tests/test_transport_tls_policy.py
python tools/tests/test_transport_reality_xray.py -v
```

The legacy H2 suite additionally requires `SWIRL_XRAY_LEGACY_BINARY`; the Core
suite requires `SWIRL_TRANSPORT_RUNTIME` pointing to the built
`examples/transport-runtime` executable. `tools/Fetch-TransportPeers.py` obtains
both exact official server archives and verifies their digests. The workflow
provides the exact executable paths and separate evidence directories for all
suites. `benchmark_transport.py` is an optional Linux-only GNU time diagnostic;
`test_transport_public.py` is an explicit manual public-target attempt, not a
CI prerequisite.

The dedicated `Swirl Native Transports` workflow runs all four Rust gates,
dynamic-library/binary builds and independent server tests on Windows, Linux
and macOS. A workflow definition is not a CI result: report exact-SHA outcomes
after execution. Public/provider connectivity remains unverified; the failed
public-target attempt and finite loopback resource measurements have separate
evidence and do not change that status.
