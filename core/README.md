# Swirl Core: native Rust runtime and staged product migration

This workspace lives inside the existing Swirl product repository. The Qt/QML
interface is unchanged. It replaces actual forwarding with Rust when configured
using `SWIRL_USE_RUST_CORE=ON`; it does not wrap the C++ forwarder or Mihomo.
The default build preserves historical capabilities until their Rust replacements
are implemented and tested. This is **not the completed all-protocol product**.

## Build and verification

Use stable Rust and a native C toolchain (ring builds C/assembly cryptography).
Windows local validation: rustc 1.99.1, GNU x64, Qt 6.10.3, MinGW 13.1.0.
Cargo.lock pins dependencies; CI additionally checks Windows MSVC.

```text
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --release --locked -p swirl-api
```

Configure the real desktop with CMake options `SWIRL_USE_RUST_CORE=ON` and
`SWIRL_BUILD_UI_TESTS=ON`. Cargo must be on the build environment PATH. Build
`Swirl` and `SwirlRustCoreTests`, then run CTest `swirl-rust-qt-integration`.
No Mihomo executable is staged into this build. The retained MihomoAdapter has a
compile-time start rejection in this mode, including legacy diagnostic callers.
Production data forwarding and node probes use RustCoreEngine through the
existing ThreadedEngine worker. The old build and tests remain separately usable.

Python `tools/tests/test_rust_core.py` uses an independent socket/TLS peer and
ephemeral CA/leaf certificates (cryptography 50.0.2). Set SWIRL_RUST_HARNESS to
the built swirl-api executable. No global certificate trust changes occur.
`tools/Benchmark-RustCore.py` records loopback latency/throughput/CPU/memory and
optional public HTTPS checks; it does not claim private-node performance.

## Implemented boundary

| Crate | Actual implementation | Not yet implemented |
|---|---|---|
| swirl-subscription | Versioned typed Swirl IR; bounded content detection for Clash YAML/JSON, sing-box JSON, URI/Base64 and INI; raw/unknown field preservation; redacted protocol/transport/TLS/cipher matrix; fully mapped TCP test candidates | Complete client-specific config execution and integrated subscription updating; existing C++ adapters and Python capture retained |
| swirl-protocol | Mixed HTTP/CONNECT/SOCKS5 input, input auth, HTTP CONNECT/SOCKS5 upstream auth, Trojan TLS framing, SS AEAD TCP/UDP, simple-obfs HTTP TCP, VLESS v0 TCP with optional verified TLS | SOCKS4, SS2022/SSR/VMess/REALITY/QUIC families, VLESS Vision/mux/encryption extensions, other protocol UDP and obfs TLS |
| swirl-transport | rustls TLS with verification/SNI/ALPN, bounded duplex copying, independent half-close, live byte counters | WS/gRPC/XHTTP protocol transports, mux, QUIC; application WS/SSE opaque tunneling is a different layer |
| swirl-routing | Ordered domain/suffix/keyword, source/destination CIDR, destination port and final rules; lazy system DNS and pinned IP decisions; Qt rules map DIRECT/REJECT/selected node/manual groups; atomic selector updates | Process rules, GEOIP/GEOSITE/MRS, nested/automatic groups/failover, policy-aware multi-address retries |
| swirl-dns | System resolver and exact local host maps through Qt settings, optional mapped proxy targets, immutable plan-owned caches, shared 8-query concurrency limit, 256-entry cache with 30-second policy lifetime, max 16 addresses | Custom DNS servers, authoritative TTL handling, DoH/DoT/DNS split/Fake-IP |
| swirl-core | Two Tokio workers, max 256 sessions, immutable per-session plan, atomic updates, stop/cancel, stats; SOCKS5 UDP ASSOCIATE with explicit DIRECT or SS AEAD routes | Other protocol UDP, TUN, platform network takeover |
| swirl-api | ABI v1 caller-buffer JSON, lifecycle handles, start/configure/select/snapshot/stop; local stdin harness | More advanced policy/config schemas and persisted IR migration |

The Qt adapter exposes supported HTTP/SOCKS5/Trojan/SS AEAD/VLESS TCP nodes using the existing
controls. Unsupported options fail explicitly before startup or selection. In
particular, old default smart-routing/TUN/custom DNS server sessions are not silently
downgraded to global/direct. Existing stored nodes and unselected unsupported
imports are preserved. Complete product migration still requires those features.
Custom rule mode is now connected to the existing rule editor and runtime rule
list. See [native routing semantics and evidence](../docs/RUST_NATIVE_ROUTING.md),
including no-resolve, mode switches, DNS address pinning and unsupported options.
The existing system DNS mode and local mappings now execute in Rust; see
[local DNS semantics and limits](../docs/RUST_LOCAL_DNS.md).

The Rust-only build is an opt-in development artifact, not a replacement that
silently removes capabilities from the user's normal installation.

`swirl-inspect` reads a document on stdin and reports only anonymous capabilities.
The explicit `--private-json` pipeline returns original parsed fields and isolated
TCP candidates and must only feed local encrypted persistence. It never derives
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
network access. Original downloads and local exports stay encrypted outside Git.
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
No source parameters are altered to make a test pass. Private nodes stay local.

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
other transports, UDP and encryption extensions are rejected rather than stripped.
Python independent peers verify plain/TLS forwarding, invalid UUID, certificate
name rejection and malformed response prefixes; a Qt peer test verifies the
existing product adapter. Private-provider VLESS is unverified. Reference:
https://github.com/XTLS/Xray-core/blob/main/proxy/vless/encoding/encoding.go .

- IR/control input <=1 MiB, <=512 nodes, <=4096 rules, <=256 active sessions.
- HTTP headers <=16 KiB/64 fields; handshake <=30 seconds. No blanket idle timer
  on established TCP streams. Duplex uses two 16 KiB buffers with backpressure.
- UDP control connection owns one association; exact client IP/port pinning,
  fragments dropped, <=64 recent destinations with 30-second response allowance,
  <=65507-byte datagrams. Only explicit DIRECT or SS AEAD (`udp: true`) routes execute UDP in this phase.
- Resolver permits remain owned by pending OS lookup tasks after caller timeout,
  limiting detached work. Runtime shutdown waits at most 500ms for OS resolver
  work; Qt uses PreventUnloadHint so late OS completion cannot call unloaded code.
- Snapshot history retains 128 completed sessions plus active sessions. Targets
  are private control-plane data; credentials and config documents are not logged.
- Updates validate before swapping the immutable plan. Old streams keep their
  selected outbound; a failed update retains the last valid plan. No automatic
  request replay or fallback to another proxy/direct route.
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
SOCKS/Trojan provider operation. TLS/Trojan loopback tests establish the tested
framing and certificate behavior, not all public servers or private extensions.
Local private subscription capture and offline parsing have been exercised;
this does not establish working provider connections. TUN, real provider traffic,
Codex remote control, mobile actions, long soak tests,
visual acceptance and non-Windows products are still unverified.

The original C++ native engine, encrypted NodeStore, importers, proxy recovery,
subscription capture utility and regression tests remain available. No Go/C#
network core or pre-existing Rust workspace was present in the audited baseline.

## Primary specifications

- SOCKS5: https://www.rfc-editor.org/rfc/rfc1928
- SOCKS username/password: https://www.rfc-editor.org/rfc/rfc1929
- HTTP message syntax: https://www.rfc-editor.org/rfc/rfc9112
- Trojan: https://trojan-gfw.github.io/trojan/protocol.html
- Tokio half-close semantics: https://docs.rs/tokio/latest/tokio/io/fn.copy_bidirectional.html
- rustls: https://rustls.dev/docs/rustls/index.html

See the merged requirements in `docs/SWIRL_CORE_DEVELOPMENT_CONTRACT.md`, and the
separate compatibility/evidence reports. Third-party versions, source URLs and
licenses are listed in DEPENDENCIES.json; release bundles include their notices.
