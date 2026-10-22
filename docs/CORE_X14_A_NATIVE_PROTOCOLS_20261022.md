# X1.4-A native protocol implementation and evidence

This is a Linux cloud checkout. No files are written to the user's Windows D drive.
The work branch is `work/rust-native-protocols-x14a-20261022`. Neither `main`
nor another development branch is modified. Test proxy executables are independent
servers only; Swirl's client and forwarding path are implemented in Rust.

## A1: verified starting point

Remote branches were read on 2026-10-22 before implementation. The requested
branch did not exist. These are the observed commits, not assumptions from chat:

| Branch | Observed commit |
| --- | --- |
| work/core-completion-20261017 | f87b6f98eb7018c4a5e86f281fe707764565ce58 |
| work/xray-v2ray-json-import-20261021 | 44dda9d4fe27a6667aa977d879d8dfc2ca82688d |
| work/xray-v2ray-native-20261021 | b88bb978d31fad1865e1b648cecd4f230bc3487c |
| work/subscription-import-20261021 | bf40f6dd639b0a9583a0dbea8e50851ac0c9ed29 |
| work/rust-core-network-fixes-20261021 | b8aa4f6f40a091697e89ae4c8291789661edca60 |
| work/x13-a-protocol-runtime-20261022 | fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870 |
| work/xray-v2ray-transport-20261022 | fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870 |
| work/rust-core-full-replacement-20261022 | 5d96214ac80d63985cdccf4942c3c1d79035e793 |

The transport commit is the starting parent. The complete latest X1.2-B JSON
conversion lineage is merged without conflicts as the second parent. This reuses
both tested lines instead of reimplementing either. The R1 Qt deletion branch
is a separate workstream; its latest Rust sole runtime workflow was observed
failed (run 39735436164). That failure is not hidden or treated as this branch's
test result.

### Baseline source capability matrix

"Existing evidence" below refers to versioned historical reports, not a rerun on
the current commit. Import/configuration, handshake, payload interoperability,
and Windows Qt acceptance remain separate states.

| Protocol | Parsed | Native config | Connector in starting tree | UDP in Core | Existing independent evidence |
| --- | --- | --- | --- | --- | --- |
| HTTP CONNECT | yes | yes | TCP, optional TLS, noauth/Basic | not applicable | independent HTTP peers |
| SOCKS4/4a | yes | yes | CONNECT, user ID, local/remote DNS | not applicable | independent SOCKS4 peers |
| SOCKS5 | yes | yes | CONNECT, user/password, UDP association | yes, no TLS UDP | independent SOCKS5 peers |
| Shadowsocks AEAD | yes | yes | AES128/256-GCM, ChaCha20-Poly1305 | yes | independent encrypted peers |
| Shadowsocks 2022 | fields retained | rejected | absent | absent | none |
| Trojan | yes | supported subset | TLS, WSS, explicit gRPC/HTTP transports | absent | pinned Xray transport reports |
| VLESS | yes | supported subset | TCP/TLS/WS, REALITY/Vision, explicit HTTP transports | absent | pinned Xray transport and earlier product reports |
| VMess | yes | rejected | absent | absent | none |
| Hysteria2 | yes | rejected | absent; no QUIC dependency | absent | none |
| TUIC | yes | rejected | absent; no QUIC dependency | absent | none |

Sources: `swirl-subscription/src/lib.rs` Outbound and Config validator,
`swirl-subscription/src/inspect.rs`, `xray/convert/native.rs`,
`swirl-protocol/src/lib.rs` connect/handshake dispatch,
`swirl-core/src/lib.rs` prepare_udp/udp_associate, and Cargo.lock.

### Existing transport scope to preserve

TCP/TLS/WS, gRPC Tun/TunMulti, legacy HTTP/2, HTTPUpgrade and explicit XHTTP
stream-one over H2/H2C already exist. Historical official peer results and
limitations are in [the transport handoff](XRAY_TRANSPORT_C_20261022.md).
Legacy HTTP/2 uses Xray 1.8.24 because current Xray removed it. Other transport
tests pin Xray 26.10.21. XHTTP auto/packet-up/stream-up/HTTP3/XMUX and WebSocket
early data are not implemented in this starting tree. Xray WSS normal-close
limitations are retained; complete payload reception is not a clean-close proof.

Resolver/address fallback and a shared handshake deadline already exist. TLS
uses verified certificates, SNI and explicit ALPN; REALITY owns its authenticated
TLS record stream and opt-in fingerprint profiles. TCP relay has fixed buffers
and independent half-close. Production cross-outbound HTTP/2 pooling, mobile
platform builds, weak-network longevity and physical Windows acceptance remain
unverified. No private subscription is fetched by this task.

### Primary specifications

- [Xray VMess source, pinned peer version](https://github.com/XTLS/Xray-core/tree/v26.10.21/proxy/vmess)
- [Hysteria2 protocol](https://v2.hysteria.network/docs/developers/Protocol/)
- [Hysteria2 URI](https://v2.hysteria.network/docs/developers/URI-Scheme/)
- [TUIC v5 protocol](https://github.com/tuic-protocol/tuic/blob/master/SPEC.md)
- [Quinn generic QUIC library](https://github.com/quinn-rs/quinn)

The current TUIC repository maintains the specification, not a current server.
Any historical official reference server and its exact version must be identified
separately from maintained third-party implementations.

### Local validation record

The first default-debug workspace build failed because temporary disk space was
exhausted. Only this task's generated build cache was removed. Subsequent local
builds disable debug symbols and incremental compilation, and use two build jobs.
This changes build resource use, not protocol behavior or test assertions.
Actual final gate results are recorded in the stage evidence; no failed or
unexecuted run is counted as a pass.


## A2: native VMess and common QUIC foundation

Native VMess AEAD now owns AuthID, request/response authentication, KDF,
AES-128-GCM and ChaCha20-Poly1305 frames, bounded lengths and nonce exhaustion.
The connector handles TCP, TLS, WS and WSS with UUID and alterId=0. Nonzero
alterId and legacy/none/zero/CFB security are rejected rather than rewritten.
Clash, VMess URI, Xray/V2Ray JSON and restored archives project to the same
`Outbound::Vmess`; the C ABI and inspector preserve that type. Import and
lifecycle acceptance continue to report `network_verified=false`.

Independent Xray 26.10.21 (commit 1b1647cd9ddf0abc34b981d4611fc03bcac1ca74)
was the server only. Swirl's Rust executable was the client. The completed-response
suite ran 12 test methods, zero failures/errors/skips: four transports with two
AEAD ciphers, 4 MiB verified bidirectional payload, eight concurrent connections,
HTTPS target, invalid UUID/cipher/alterId/certificate/SNI rejection, IPv6 target,
Clash/URI/Xray import and Core node selection. Normal application completion
returned authenticated clean closure. Detailed receipts and command logs are
in `docs/evidence/x14-a2-vmess/`.

**Strict target half-close is not accepted.** The separately executed
`--strict-half-close` suite ran two methods and reported five subtest failures.
All four transports returned the expected 4 MiB hash, but the official peer did
not deliver authenticated VMess terminal closure when the target waited for
client EOF; concurrent WSS also failed this requirement. The initial failed
attempt and the strict rerun remain versioned. Finite application-response
completion is reported separately and is not substituted for half-close.

This checkpoint also registers the common Quinn/rustls TLS1.3 transport and
native Hysteria2/TUIC modules in the unified Core. Their ongoing acceptance is
reported in A3/A4, not inferred from compilation. SOCKS5 UDP associations use
bounded protocol workers, including the new QUIC outbounds. TUIC URI passwords
are now preserved. No third-party client executable is invoked.

Before the two new positive ABI/CLI tests, the integrated workspace ran 596
unit/integration/doc tests with zero failures or ignored tests. The two boundary
tests separately verify modern VMess export/start/stop without dialing an
upstream. A1 clean remote CI run 39779971139 passed fmt/check/clippy/test on
Ubuntu, Windows and macOS. That run applies to A1, not to this newer code.
There has been no Windows Qt product test or public subscription test here.

## A3/A4: authenticated native QUIC protocols

Hysteria2 and TUIC v5 now use the common native Quinn/rustls transport and Core
TCP/UDP routing. Their exact official peer versions, source specifications,
authentication, verified payloads, negative cases and retained limitations are
recorded in [Hysteria2 evidence](HYSTERIA2_NATIVE_INTEROP_20261022.md) and
[TUIC evidence](TUIC_NATIVE_INTEROP_20261022.md). Hysteria salamander and negotiated
bandwidth limits are exercised with the official server. TUIC uses the v5 TLS
exporter token, supports native/quic UDP relay modes, and keeps bounded sessions,
reassembly, heartbeat and DNS-generation-aware connection reuse.

A4 run `39783473847` passed native Rust gates on all three OSes. Official
interoperability passed on Windows and Ubuntu. macOS failed two maximum-payload
TUIC UDP cases plus their aggregate assertion: the independent destination never
received either 65,507-byte packet. The original failure is retained in
`docs/evidence/x14-a4-tuic/macos-ci-39783473847-*`. The new disposable-runner
preparation records bare UDP behavior, OS buffer defaults and any explicit
adjustment before retrying the unchanged payloads. It is not a product runtime
dependency, and its addition does not by itself establish a macOS pass.

## A5: persisted native transports and shared protocol integration

The ordinary native configuration now persists typed gRPC, legacy HTTP/2,
HTTPUpgrade and XHTTP stream-one options. Xray/V2Ray source JSON maps those
options into the same Outbound used by normal Core start, configure, selection,
probes and C ABI v1; no external transport override is needed. Source host/path,
serviceName, supported headers, SNI, ALPN and inline verification CA survive
archive restore. Unknown semantics, early data, unsupported fingerprint and
XHTTP modes still block export. See the exact [imported transport results](
IMPORTED_TRANSPORT_NATIVE_INTEROP_20261022.md): five official test methods,
HTTP/HTTPS, 4 MiB in each direction, negative credentials/parameters and normal
application completion. Legacy H2 is explicitly tied to Xray 1.8.24.

This shared integration checkpoint also registers native Shadowsocks 2022 AES
and classic VLESS/Trojan UDP carriers. The common Core UDP dispatcher remains
bounded; VLESS carriers are keyed by destination, while Trojan uses per-packet
addresses. New protocol frames have length/deadline limits and cancelled writes
cannot silently reuse a partly written UDP carrier. The detailed consolidation
evidence is retained separately under `x14-a6-ss2022` and `x14-a6-stream-udp`.

TLS validates SNI, ALPN and custom CA material before DNS/socket allocation. A
bounded 32-entry context cache avoids rebuilding root stores on repeated ordinary
TLS connections; session resumption and early data remain disabled. Invalid
reconfiguration preserves the running Core generation, verified through the
actual C ABI. This proves an ABI/configuration boundary, not Qt UI integration.

Local A5 gates on Linux completed with `cargo fmt --all -- --check`, `cargo check
--workspace --locked`, `cargo clippy --workspace --all-targets --locked -- -D
warnings`, and `cargo test --workspace --locked`: 631 tests passed, zero failed,
zero ignored. Logs and scope are in `docs/evidence/x14-a5-local`. Two obsolete
negative cases were updated to still-unsupported XHTTP auto and SS2022 ChaCha
after gRPC and SS2022 AES became executable; rejection and sibling-isolation
assertions remain. Official interop is an additional CI matrix with pinned peer
downloads; local gates are never substituted for its actual result.
