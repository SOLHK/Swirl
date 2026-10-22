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

## Upstream pins and independent implementation

* [Xray v26.10.21 / 1b1647c](https://github.com/XTLS/Xray-core/tree/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74): MPL-2.0. Read `transport/internet/{websocket,grpc,httpupgrade,splithttp,tls,reality}` and `infra/conf/transport_internet.go`.
* [Legacy Xray v1.8.24 / 6baad79](https://github.com/XTLS/Xray-core/tree/6baad79f9881ee2cf75bdc825b3e2e92b289477a): MPL-2.0; retained legacy HTTP/2 fixture. Current Xray rejects that removed transport, so current-version H2 transport support is not claimed.
* V2Ray v5.39.0: MIT; gRPC and HTTP streaming wire/configuration comparison.
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

## B integration boundary

`Transport` is deliberately outside `swirl-subscription`, avoiding changes to
B's JSON parser, six-protocol mapping and existing internal outbound shape.
B can pass a validated `Outbound` and separate native `Transport` into
`connect_with_transport`. Unsupported options must remain explicit errors;
import success alone must not change execution capability reporting.
VMess does not exist in this pinned native protocol baseline; an enum in an
importer cannot make it executable. New transports will be tested with the
implemented VLESS and Trojan connectors and report VMess separately.

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
