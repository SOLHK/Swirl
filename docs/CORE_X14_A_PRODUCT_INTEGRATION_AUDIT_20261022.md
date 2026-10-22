# X1.4-A Qt / C ABI product integration audit

Date: 2026-10-22. Inspected checkout: `work/rust-native-protocols-x14a-20261022`,
starting from `930be89374a64d600730b3056e8a756bba5fcde4` and the current additive
A5/A6 Rust working tree. This is a source-path audit, **not a Windows Qt product
network acceptance result**. None of the new protocol combinations is promoted
to product-accepted by this document.

## Finding

The new Rust protocol connectors are reachable through native `Config`, the
Rust Core connector, the CLI importer, and the existing JSON C ABI. The current
Qt importer and Qt-to-Rust projection still form a separate, older conversion
path. They do not preserve or consume the Rust importer's `native_config`.
Consequently the current Qt product cannot select and start VMess, Hysteria2 or
TUIC through this path, even when the corresponding Rust interoperability suite
passes. Existing Qt configuration checks reject these nodes before `Core::start`.

The same old projection blocks Shadowsocks AEAD-2022, VLESS/Trojan UDP, and the
new typed gRPC, HTTP/2, HTTPUpgrade and XHTTP transport configuration. Keeping this
rejection is safer than relabelling imported nodes or silently replacing their
transport. It is an outstanding product integration task, not missing Rust wire
implementation evidence.

## Actual data path

| Boundary | Current behavior | Evidence in source |
| --- | --- | --- |
| QML text/file/URL import | Calls `NodeImportService`, which parses with the C++ `NodeImporter`; downloaded bytes do not call the Rust subscription importer. | `src/Swirl.Quick/engine/NodeImportService.cpp`, `NodeImporter.cpp` |
| Format conversion | `SubscriptionNormalizer` preserves raw provenance and diagnostic strings, but its Xray JSON adapter is the earlier VLESS REALITY subset. General Xray VMess/Trojan/transport conversion added to Rust is absent here. | `src/Swirl.Quick/engine/SubscriptionNormalizer.cpp`, especially `xrayReality` and `normalize` |
| Private node representation | `ProxyNode` has scalar credentials, `parameters`, `originalConfiguration`, `sourceFormat` and `conversionIssues`; it has no typed/native outbound or `native_config` member. | `src/Swirl.Quick/engine/ProxyNode.h` |
| Persistence | The DPAPI snapshot retains the existing scalar credentials, options, original configuration and conversion issues. It cannot retain a native field that is not in this model. Public QML rows exclude options, credentials and original configuration. | `src/Swirl.Quick/engine/NodeStore.cpp`, `ProxyNode::publicInfo` |
| Selection | `EngineController::chooseNode` checks `RustCoreEngine::configuration` before saving/activating a selection. A failed running reconfiguration rolls back the saved selection. | `src/Swirl.Quick/engine/EngineController.cpp` |
| Start/reconfigure | `RustCoreEngine::configuration` reconstructs an outbound from the older C++ fields. Its protocol list, cipher list, UDP list and transport checks reject the new combinations. | `src/Swirl.Quick/engine/RustCoreEngine.cpp` |
| Rust execution | The JSON `start`/`configure` operations deserialize the current Rust `Config`, validate it and call native Core code. New protocol enum members use the same byte-buffer C ABI. | `core/crates/swirl-api/src/lib.rs`, `core/crates/swirl-core/src/lib.rs` |

### Field-level blockers

| Combination | Qt import/storage situation | Qt execution projection |
| --- | --- | --- |
| HTTP CONNECT / SOCKS5 | Existing normalized scalar fields and options persist. | Existing native mapping remains. SOCKS5 TLS plus UDP is explicitly rejected. |
| SOCKS4 / SOCKS4a | Imported native protocols are allowed only in the Rust build; no claim that the retained compatibility build supports them. | Existing TCP-only mapping remains. |
| Shadowsocks classic AEAD | Cipher/password/options persist. | Three classic ciphers remain accepted. |
| Shadowsocks AEAD-2022 | A Clash node can preserve its cipher and password. | Cipher whitelist rejects both newly implemented AES-2022 methods. |
| Trojan / VLESS TCP, TLS, existing WS, supported REALITY | Existing supported fields persist. | Existing mapping remains; no new Qt test was run in this audit. |
| Trojan / VLESS UDP | `udp` can persist in options. | UDP is accepted only for `ss`/`socks5`; no `udp` is emitted for Trojan/VLESS. |
| VLESS / Trojan gRPC, HTTP/2, HTTPUpgrade, XHTTP | Raw source can be retained, but C++ import support varies and may report issues or reject Xray JSON. | Only `network=tcp/ws` plus the older `ws-opts` subset is mapped; typed `transport` is absent. |
| VMess TCP/TLS/WS/WSS | Existing C++ format parsers can preserve several VMess fields; general Xray JSON is still rejected. | Protocol whitelist rejects `vmess`; there is no Qt mapping for AEAD security or nonzero alterId diagnostics. |
| Hysteria2 | URI/Clash fields are handled independently by the C++ importer. | Protocol whitelist rejects `hysteria2`; QUIC options, certificate pin, salamander and bandwidth are not forwarded. |
| TUIC v5 | URI/Clash fields can be retained independently of Rust validation. | Protocol whitelist rejects `tuic`; UUID/password, relay mode and QUIC security options are not forwarded. |

The private `native_config` emitted by `swirl-inspect --xray-json --private-json
--native-node ...` is a complete Rust configuration. It is not a format currently
accepted as a Qt `ProxyNode`. Adding that object to unrecognized C++ options would
still be rejected at startup. It must not be described as preserved end to end.

## C ABI, Windows DLL and threading

The existing ABI remains version 1. `swirl_core_command` accepts UTF-8 JSON input
and writes a response into caller-owned memory. Its `usize` lengths and `isize`
return match Qt's `size_t` and `qintptr` function pointer on the same architecture.
This work adds JSON variants, not protocol-specific C structs, and therefore
does not require changing pointer layout or Qt-facing Rust types.

Both sides currently bound input/output at 1 MiB. Qt serializes compact JSON,
clears its temporary input bytes after a call, and receives structured error
codes instead of parser messages containing credentials. The Rust boundary
catches unwinds. Qt checks `swirl_core_abi_version() == 1` and the required symbol
before starting; a missing or incompatible DLL fails visibly.

There is currently no C ABI operation for subscription inspection or conversion.
The `start`/`configure` operations can execute new native JSON, but cannot supply
the missing Qt conversion step themselves. A future bridge should call the Rust
converter in process and retain its validated private outbound and diagnostics;
starting a third-party executable to translate/run the node is not necessary.

`ThreadedEngine` sends engine work to its existing network thread and returns
snapshots to the GUI thread. Runtime sockets and protocol state remain owned by
Rust. `QLibrary::PreventUnloadHint` deliberately keeps the DLL mapped for bounded
shutdown and any in-flight OS resolver work.

The CMake Rust build compiles and copies `swirl_api.dll` from the same locked
workspace. Its dedicated copy target avoids a stale DLL when only Rust source
changes. The present Qt packaging path explicitly requires Windows; this is
separate from the Rust Core's Windows/macOS/Linux build matrix. `NodeStore` uses
Windows DPAPI and has no plaintext fallback on other platforms. A future macOS or
Linux Qt product needs a platform credential-store implementation.

## No hidden compatibility fallback in the Rust build

With `SWIRL_USE_RUST_CORE=ON`:

- `main.cpp` always constructs `ThreadedEngine` for normal and isolated runs.
- `ThreadedEngine` constructs `RustCoreEngine`, not `SwirlEngineManager`.
- Missing DLL, invalid options, unsupported node parameters and failed
  reconfiguration return errors; they do not launch Mihomo.
- `SwirlProtocolRegistry::describe` reports `compatible=false` and `tested=false`.
- A saved preference for the compatibility engine is rejected with a diagnostic.
- Empty node selection does not silently become DIRECT; DIRECT is an explicit
  routing mode.

The compatibility source code still exists for legacy builds/tests. The CMake
option defaults to `OFF`, and the separate Qt preview workflow still builds that
legacy mode. Thus a generic existing preview artifact is **not automatically a
Rust-only X1.4-A product**. Artifact provenance and build flags must accompany any
later product acceptance. The X1.4 native Rust/official-peer CI does not prove the
Qt preview package uses the Rust engine.

## Other-branch reuse check

Read-only GitHub checks on 2026-10-22 examined:

- `work/rust-core-full-replacement-20261022`
- `work/x13-a-protocol-runtime-20261022`

Both still have the same `ProxyNode.h` blob
`244ecced29616b6158e5d5d7b50641e65b55eabd` and `NodeImporter.cpp` blob
`4b65c6a09e01151589645fe3683d687735a8fa75` as this path, with no native import bridge.
Both retain the seven-protocol Qt execution whitelist. No ready-made VMess/HY2/
TUIC Qt bridge was found in these files, so a broad cherry-pick is not justified.
The full-replacement branch has an additional `swirl_core_build_info` export;
its build-identity work can be reviewed independently for package provenance but
does not repair the conversion path.

## Resource and security cross-review

Concrete findings were delivered to the corresponding Rust owners:

1. VMess initially had a response-header deadline without a deadline for a
   partially received encrypted body record. A malicious authenticated peer
   could retain that connection with a stalled partial record. The owner's
   current source now has a record deadline that starts at the first byte and
   clears only after the complete record authenticates; idle between records is
   distinguished from a partial frame. The added tests include partial prefixes
   and ciphertext drip feeding.
2. TUIC explicit UDP close initially propagated a dissociation timeout before
   closing its connection. The owner changed it to close the connection on all
   outcomes, then return the error.
3. TUIC's receive loop now yields after a bounded batch of heartbeat/incomplete
   fragment messages to preserve cooperative scheduling fairness.

Review also verified bounded protocol/frame/reassembly buffers, bounded QUIC
send/receive windows, TLS chain/SNI verification by default, additive certificate
pin verification, explicit-only insecure mode, no QUIC 0-RTT, and RAII ownership
of H3/heartbeat work. SS2022 replay state is updated only after authentication
and validation; invalid ciphertext does not poison that window. VMess refuses
AEAD nonce wrap; its 16-bit record counter is a real per-connection limit, not a
claim of unlimited stream duration. These are code-review conclusions and do not
substitute for hostile-peer fuzzing, WAN stress tests or product execution.

## Verification and next product gate

This environment has CMake but no Qt 6 SDK (`pkg-config Qt6Core` fails and no
`Qt6CoreConfig.cmake`/`qmake6` was found in the searched SDK locations). No Qt
source was changed or compiled during this audit. Windows DPAPI persistence,
Windows DLL loading, QML selection and new-protocol product networking remain
**not executed here**. Rust ABI and official-server tests are reported separately
by their actual test receipts.

For X1.4-B, the concrete remaining product work is to route imported and edited
nodes through one Rust validation/conversion path, retain validated native
outbounds privately in node persistence without exposing credentials to QML,
preserve diagnostics and rejected options, and exercise reload/selection/
reconfiguration with the actual Windows Qt application and independent servers.
The existing ABI start/configure boundary can then consume those same native
outbounds. Removing only the protocol whitelist would be insufficient: it would
leave credential, TLS, transport and UDP fields unmapped.
