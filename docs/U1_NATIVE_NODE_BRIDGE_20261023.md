# U1: subscription nodes use the authoritative Rust converter

## Audited source and integration gap

This change was developed on `work/subscription-native-bridge-20261023` at
`442138a3d40fc13a9a761b43f3a2ce829a2b47ec`. The audit used the commit graph and
implementation, not previous acceptance claims.

| Source | SHA | Source inspection and required action |
| --- | --- | --- |
| Subscription native bridge | `442138a3d40fc13a9a761b43f3a2ce829a2b47ec` | Xray sources already rerun through Rust on activation, but other formats still reached the older C++ protocol whitelist in `RustCoreEngine::configuration`. Replace only that converter with the existing Rust inspector. |
| Qt JSON product import | `506014d6386610411f48c939ab62cb93a3509431` | Inherited through merge `7b35bb1474fa5827c3e184231e07d059609532a7`. `NodeStore`, `NodeImportService`, `EngineController` already share one catalog, source table, selection and revision lease. Preserve these services and encrypted schema. |
| Strict Xray/V2Ray import | `44dda9d4fe27a6667aa977d879d8dfc2ca82688d` | Inherited parser checks and original-document retention must remain. This change shares its bounded FFI buffer helper and leaves all existing Xray tests in place. |
| Native stream transports | `fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870` | Inherited typed gRPC, HTTP/2, HTTPUpgrade and XHTTP mapping/runtime. Reuse `xray::stream_transport::build`; do not introduce another transport implementation. |
| Native protocols and Windows HY2 fixes | `21c562a7c7adc2654416636e4de2f038ffc220cd` | Inherited VMess, Hysteria2, TUIC and Shadowsocks 2022 implementations, plus `5d6b9e370ae29add8ed11d8c8ebf9e54c2ea2611` / `b6fba1827b0136c50123dab41fa4cb1c79a9ebce` stack fixes. Product non-JSON conversion had rejected these protocols. The later branch tip `2a41b360d0fed90bf2818d5e4c8e93b4f41f021b` adds handoff documentation only. |
| Rust-only product/loader | `5d96214ac80d63985cdccf4942c3c1d79035e793` | Separate from the bridge at merge-base `b8aa4f6f40a091697e89ae4c8291789661edca60`. Integration must retain its ABI/build pairing, Rust-only lifecycle and threaded probes. `NativeNodeBridge` requires the unified `RustCoreLibrary::instance().importNode()` provided by U1 integration. |
| Qt download security | `9dd8a675eed6374ac1c35265074f594a39262479` | Separate source to be integrated by U1. This change does not replace `NodeImportService` or create another downloader, so the security patch applies to the shared product download path. |

Baseline storage is one versioned `nodes.dpapi` catalog, with `QSaveFile`, Windows
DPAPI, asynchronous bounded persistence, stable source identities and revision
checks. Linux/macOS persistence fails closed rather than writing plaintext. This
change neither claims that encrypted persistence exists on those platforms nor
creates an alternative database. Baseline downloads use an explicit direct
connection or Swirl's active local proxy; they do not inherit arbitrary system
proxy settings. Download cancellation, deadlines, same-origin redirects and
selection-preserving updates belong to the existing product services.

## Unified conversion contract

`NativeNodeBridge` reconstructs one complete Clash-shaped node from the existing
`ProxyNode` scalar fields and all retained extension parameters. Reserved field
conflicts fail rather than overriding credentials or TLS names. UUID spelling is
canonicalized without changing its value. Original configuration bytes/objects,
node identity, storage and QML interfaces remain under the existing services.

The versioned `swirl_import_node_v1` ABI accepts exactly one normalized node. It
calls `swirl_subscription::inspect`, then the actual typed `Config::validate`.
Full policy documents, multiple nodes, duplicate fields, unknown options and
unrepresented controls fail closed. There is no network operation in this ABI.
The returned private candidate is never exposed to QML or logs, and
`network_verified` is always false. The shared import FFI helper preserves the
Xray ABI's size query, untouched insufficient buffer, no overlap, input/output
budgets, panic containment and concurrent-call isolation.

The product now uses completed Rust mappings for HTTP, SOCKS4/4a/5, Shadowsocks
AEAD/2022, VLESS, VLESS REALITY/Vision, Trojan, VMess, Hysteria2 and TUIC, with the
protocol-specific restrictions already enforced in Rust. Declared UDP capability
and all supported TLS, ALPN, WebSocket, QUIC, authentication, pin, obfuscation and
bandwidth parameters pass through that same native schema. This is capability
integration; it is not proof of every protocol's external interoperability.

For VLESS/Trojan stream transports the new Clash projection reuses the inherited
Xray typed builder. Explicit `grpc-opts`, one-host `h2-opts`, HTTPUpgrade selected
by `ws-opts.v2ray-http-upgrade`, and VLESS `xhttp-opts.mode=stream-one` are mapped.
Unresolved defaults (a transport name without its option block), randomized
multiple HTTP/2 hosts, gRPC pooling/keepalive settings, HTTPUpgrade fast open and
other XHTTP modes remain blocked. URI gRPC Host requirements remain visible as
blocking conversion issues rather than being silently discarded. These limits
preserve the existing negative tests and prevent guessing client semantics.

The existing URI normalizer now rejects scalar coercion and alias conflicts
before they can become runnable defaults: VMess `aid`, version, TLS/string types;
Hysteria2 SNI aliases; TUIC paths and option aliases; malformed percent encoding;
invalid UTF-8; and empty ALPN list elements. Insecure QUIC aliases cannot bypass
the product's certificate-verification requirement.

Primary format references checked for this projection:

- https://wiki.metacubex.one/config/proxies/transport/
- https://xtls.github.io/en/config/transports/grpc.html

## Regression requirements and evidence boundaries

The new Rust tests exercise the exported buffer ABI, strict source boundaries,
credentials/UDP/transport preservation, malformed controls, concurrency and actual
`Core::start`/stop validation for VMess, QUIC and stream candidates. Existing
subscription and Xray tests are retained, including the unsupported bare gRPC
source assertions. No test is skipped or changed to accept weakened behavior.

`NativeNodeBridgeTests.cpp` exercises the actual Qt importer, native bridge and
Rust product adapter. It includes 13 URI/Clash candidate startup cases, malformed
source and alias rejection, and real local SOCKS5 relay requests that prove node
switching, correct exit, wrong-password rejection and listener cleanup. Synthetic
fixtures contain no real subscription or production credential.

Required integrated-commit commands include:

```sh
cargo fmt --all --check
cargo clippy --locked -p swirl-api -p swirl-subscription --all-targets -- -D warnings
cargo test --locked -p swirl-api -p swirl-subscription
ctest --test-dir <paired-Qt-build> -R swirl-native-node-bridge --output-on-failure
```

The U1 final report must attach these results to the integrated SHA, with the
complete workspace/platform suites. Development runs on this branch are not a
substitute for that evidence. Loopback listener startup is level 2 evidence;
controlled relay business traffic is explicitly identified as local. Windows
Hysteria2 real-device operation, real subscription credentials and external
service traffic still require the corresponding real environment.
