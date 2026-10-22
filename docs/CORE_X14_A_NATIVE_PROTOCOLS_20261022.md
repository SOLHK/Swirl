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
