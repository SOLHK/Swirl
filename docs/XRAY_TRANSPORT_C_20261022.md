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

## Reproduction

From `core/`:

```sh
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --locked -p swirl-api --bin swirl-api -p swirl-protocol --example transport-client
```

From the repository root, with `SWIRL_XRAY_BINARY`, `SWIRL_RUST_HARNESS`,
`SWIRL_TRANSPORT_CLIENT` pointing to the pinned server and native binaries:

```sh
python tools/tests/test_transport_c1_xray.py -v
```

The dedicated `Swirl Native Transports` workflow runs all four Rust gates,
dynamic-library/binary builds and independent server tests on Windows, Linux
and macOS. A workflow definition is not a CI result: report exact-SHA outcomes
after execution. Public/provider connectivity and comparative performance are
not established by this C1 checkpoint.
