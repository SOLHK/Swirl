# Swirl Core: first executable Rust migration

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
| swirl-protocol | Mixed HTTP/CONNECT/SOCKS5 input, input auth, HTTP CONNECT/SOCKS5 upstream auth, Trojan TLS framing | SOCKS4, SS/SSR/VMess/VLESS/REALITY/QUIC families and protocol UDP |
| swirl-transport | rustls TLS with verification/SNI/ALPN, bounded duplex copying, independent half-close, live byte counters | WS/gRPC/XHTTP protocol transports, mux, QUIC; application WS/SSE opaque tunneling is a different layer |
| swirl-routing | Ordered domain/exact/suffix/IP-CIDR, explicit DIRECT/REJECT/node selection | GEOIP/GEOSITE, groups/failover; custom routing is currently exposed through IR API, not the legacy Qt configuration mapper |
| swirl-dns | System resolver, 8-query concurrency limit, 256-entry cache with 30-second policy lifetime, max 16 addresses | Authoritative DNS TTL handling, DoH/DoT/DNS split/Fake-IP |
| swirl-core | Two Tokio workers, max 256 sessions, immutable per-session plan, atomic updates, stop/cancel, stats; SOCKS5 UDP ASSOCIATE with explicit DIRECT routes | UDP via proxy protocols, TUN, platform network takeover |
| swirl-api | ABI v1 caller-buffer JSON, lifecycle handles, start/configure/select/snapshot/stop; local stdin harness | More advanced policy/config schemas and persisted IR migration |

The Qt adapter exposes supported HTTP/SOCKS5/Trojan nodes using the existing
controls. Unsupported options fail explicitly before startup or selection. In
particular, old default smart-routing/TUN/custom DNS sessions are not silently
downgraded to global/direct. Existing stored nodes and unselected unsupported
imports are preserved. Complete product migration still requires those features.

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

## Bounds and ownership

- IR/control input <=1 MiB, <=512 nodes, <=4096 rules, <=256 active sessions.
- HTTP headers <=16 KiB/64 fields; handshake <=30 seconds. No blanket idle timer
  on established TCP streams. Duplex uses two 16 KiB buffers with backpressure.
- UDP control connection owns one association; exact client IP/port pinning,
  fragments dropped, <=64 recent destinations with 30-second response allowance,
  <=65507-byte datagrams. Only explicit DIRECT routes execute UDP in this phase.
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
TUN, real subscriptions, Codex remote control, mobile actions, long soak tests,
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
