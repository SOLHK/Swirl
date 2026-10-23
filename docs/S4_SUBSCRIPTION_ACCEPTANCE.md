# S4 subscription completion evidence

The S4 change closes the sing-box TUIC v5 / Hysteria2 import gap through the existing Qt importer, encrypted Windows store, native import ABI and Rust runtime. It does not make every subscription dialect or every sing-box extension executable. No provider subscription, system proxy, TUN, route or system DNS was changed.

## Architecture and source contracts

`swirl-subscription/src/singbox_quic.rs` owns protocol semantics, typed fields, duration units, TLS requirements and execution rejection. It uses existing portable Rust dependencies only. Qt retains the complete original object and forwards every option; it adapts endpoint/display aliases and an explicit source-dialect marker. The existing one-node ABI still requires a single `proxies` object and still rejects disabled certificate verification. No new ABI or Windows dependency was added to Rust. Windows DPAPI remains in `NodeStore`, outside the Rust parser.

Primary references reviewed before implementation:

- [sing-box 1.12 TUIC options](https://github.com/SagerNet/sing-box/blob/v1.12.0/option/tuic.go) and [outbound constructor](https://github.com/SagerNet/sing-box/blob/v1.12.0/protocol/tuic/outbound.go).
- [sing-box 1.12 Hysteria2 outbound](https://github.com/SagerNet/sing-box/blob/v1.12.0/protocol/hysteria2/outbound.go).
- [sing-quic TUIC client](https://github.com/SagerNet/sing-quic/blob/v0.4.4/tuic/client.go) for heartbeat/default congestion and the absence of a positive authentication acknowledgment.
- Current [TUIC](https://sing-box.sagernet.org/configuration/outbound/tuic/) and [Hysteria2](https://sing-box.sagernet.org/configuration/outbound/hysteria2/) option documentation. Newer fields remain explicitly outside this closed subset.

## Implemented subset

| Field family | Preserved executable behavior | Explicit rejection |
| --- | --- | --- |
| Endpoint and credentials | Typed host/port; password including `:`; TUIC UUID | Wrong scalar types, conflicting internal aliases, malformed endpoint |
| TLS | Required enabled TLS; SNI; ALPN; verification; one inline PEM trust anchor, string or line array | Disabled TLS, product `insecure`, local certificate paths, uTLS/REALITY/ECH/unmapped TLS options; multiple PEM blocks |
| TUIC | Native/quic UDP relay; cubic/bbr/new_reno congestion; checked Go-style heartbeat duration in exact milliseconds | UDP-over-stream, zero-RTT, v4 token, unsupported heartbeat range, omitted TUIC ALPN (no invented h3 default) |
| Hysteria2 | Nested Salamander type/password; integer Mbps, checked protocol byte conversion | Gecko, hopping/server_ports/hop_interval, bandwidth overflow/fractions, unknown obfs fields |
| Enabled networks | Default TCP+UDP; explicit TCP disables UDP; TCP+UDP array | UDP-only, because the current IR always permits TCP; unknown networks |
| Unknown fields | Complete source retained; Rust refuses activation | No option stripping or insecure downgrade |

Native inspection now reports successful QUIC candidates as QUIC, reports their actual enabled UDP state, and does not label mapped protocol fields as unrecognized. `real_network_verified` remains false: offline conversion never grants network verification.

## Tests and evidence

The six new Rust tests cover full native projections, Qt/dialect parity, field preservation after rejection, overflow, duration syntax, missing/disabled TLS, wrong types, unsupported requirements and source provenance. `cargo test -p swirl-subscription --locked --offline` passed **253 tests**, with no failures/skips. `cargo clippy -p swirl-subscription --all-targets --locked --offline -- -D warnings` passed. The GNU linker emits the existing `.drectve` warning during tests; this is not presented as a warning-free build.

The extended `SubscriptionFormatTests` passed **7 Qt slots**, no failures/skips, including real DPAPI save/reload and native conversion of both QUIC formats, plus existing 17 format downloads and persistence mappings. This test alone is L2/L3 evidence.

`tools/tests/test_singbox_quic_product.py` drives the actual `singBoxQuicProductChainAgainstIndependentPeer` Qt slot against pinned Hysteria **2.13.0** and historical official TUIC server **1.0.0**. It verifies source retention, actual encrypted store reload, in-process Rust identity, 65,553 exact TCP bytes via explicit HTTP CONNECT, a SOCKS5 UDP association with exact datagram receipt, and listener release. Separate origins record bytes/datagrams; local listener success alone is insufficient. Bad-authentication cases require zero target connections and zero target bytes. TUIC has no positive authentication response, so an optimistic local CONNECT reply must be followed by stream closure without target data; the separate origin counter remains decisive.

The existing CI fixture inventory is expanded from 9 to 10 conditional Qt slots. Its new QUIC stage requires all six cases and actual Qt XML pass evidence; missing servers, missing slots and skips fail the gate.

The six local peer cases passed **6/6**, with no skips, using Windows 11, Qt 6.10.3 / MinGW and Rust GNU. All four positive cases transferred the exact TCP payload and UDP datagram; both bad-auth cases recorded zero independent origin connections. This proves this bounded L4 matrix, not all provider extensions.

The local worktree build records source base `a4534010e1509972a8df49f7f706ae315f1ffee2` plus uncommitted S4 implementation, Rust build ID `3b0b109509c47e6e2dd2e4d84bad94a21f85f4b5ea82acb554cbc3056ace850e`, and DLL SHA-256 `a06bf0a2a6f75edb4938dd59a6cbee01a7d0e14f8b233725dfe3ba5d14bc5a64`. The final staged commit must be rebuilt for its own source identity. Evidence XML and redacted receipts are under `D:/Codex/outputs/s4/singbox-quic`, with the suite log at `D:/Codex/outputs/s4/singbox-quic-product.log`.

Development checks initially exposed a duration `+` parser bug, which was fixed before the 253-test pass. A test invoked during EXE/DLL replacement correctly rejected the mismatched pair; the completed paired build subsequently passed all seven format slots. The TUIC negative fixture initially assumed synchronous HTTP 502 and then assumed a still-open socket; its corrected contract explicitly checks peer rejection with zero returned data and the independent origin counter. No runtime assertions or original protocol regression tests were weakened.

## Remaining scope

- `v2rayn://` private ProfileItemDto backups remain unimplemented; ordinary v2rayN sharing URIs already use the established path.
- ETag/304 and structured refresh change summaries remain unimplemented. Existing write-lease/revision/generation/cancel transactions are preserved; this patch does not replace that storage system.
- Unsupported full configuration rules/DNS/scripts and protocol combinations keep their existing rejection boundaries.
- Windows loopback import/persistence/interoperation is distinct from installer acceptance, private subscriptions, WAN/weak-network/long-run validation and other platforms' system adapters. Those are not established by this change.
- macOS, Android, iOS and HarmonyOS NEXT can reuse this platform-independent Rust parsing code; their native network permissions, UI and storage adapters are separate work. HarmonyOS compilation and VPN/permission support must be validated independently.
