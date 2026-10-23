# S4 protocol support and closure evidence

Recorded 2026-10-24 Asia/Shanghai. The S4 branch starts at
`9f8af5754d2a932f7b967eea0e64cbc75717e6be`. This matrix separates inherited S3
evidence from the S4 closure investigation; it is not final product acceptance.
L1 means recognized input, L2 faithful conversion of the stated subset, L3 native
startup, L4 independent-peer transfer, and L5 installed-product user acceptance.
L5 is **NOT TESTED** throughout.

| Protocol / transport | Native scope already established in S3 | S4 closure verification | Remaining boundary |
|---|---|---|---|
| VMess AEAD | alterId 0, AES-128-GCM / ChaCha20-Poly1305; TCP, TLS, WS, WSS | Normal response menu **13/13 passed**; includes 64 MiB, concurrency, reconnect, TLS and import cases. Original strict half-close **2 methods / 5 failures** | A target response depending on upload EOF does not pass through the pinned Xray. Same-version official-client control also fails the post-EOF response contract on all four transports. This remains a failed L4 case. |
| VLESS / REALITY / Vision | Explicit Xray peer, fingerprint and flow combinations from S3 | Not rerun by this closure investigation | No implicit TLS downgrade; no claim of every transport/flow combination. |
| Trojan TLS | Certificate/name/authentication and explicitly exercised TCP/UDP wrappers | Not rerun by this closure investigation | Unsupported encapsulation remains rejected; credentials and certificates stay mandatory. |
| Shadowsocks AEAD / 2022 | Official ssserver, TCP/UDP, three AEAD methods, 2022 AES128/AES256, replay/tamper and controlled HTTPS | Strict TLS diagnostic controls **3/3 passed**; original public SS test **FAILED** after verified TLS / HTTP 204. Same address and certificate direct control fails at the same close phase. | Public source/path truncation is not repaired by accepting HTTP success as TLS closure. Controlled success does not prove every provider or WAN path. |
| Hysteria2 | Pinned official server, 17 protocol methods and lifecycle/Core/FFI coverage in S3 | Not rerun by this closure investigation | Loopback evidence is not Windows WAN loss/MTU/sleep/roaming acceptance. |
| TUIC v5 | Independent Rust server, TCP/UDP, fragmentation, heartbeat, multiplexing and cancellation in S3 | Not rerun by this closure investigation | v4, 0-RTT and unsupported TLS modes remain rejected; format conversion is separately validated. |
| WS / H2 / gRPC / HTTPUpgrade / XHTTP / QUIC | Only concrete combinations in the pinned transport/UDP fixtures | VMess WS/WSS normal completion reverified above | No Cartesian-product claim; H2 uses its separately pinned legacy server. |
| AnyTLS / Snell / Hysteria1 / SSR / WireGuard / SSH and other unimplemented families | Recognition or preserved raw input may exist | No native acceptance added | Recognition is not native execution or networking support. |

All protocol, authentication and stream-state code remains portable Rust. This
investigation adds Python test diagnostics and public certificate fingerprints;
it adds no Rust dependency, OS API, platform adapter or product fallback. Windows
GNU was executed locally. macOS, Android, iOS and HarmonyOS NEXT execution or
permissions are not inferred from this result; their compile and system checks
remain separate under [the platform contract](S4_CROSS_PLATFORM.md).

The exact commands, artifacts, failure interpretation and rerun requirements are
in [S4 protocol closure evidence](S4_PROTOCOL_CLOSURE_20261024.md). Historical
scope is documented in [the S3 handoff](S3_MAX_HANDOFF_20261023.md).
