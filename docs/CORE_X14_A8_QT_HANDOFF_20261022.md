# X1.4-A8 Qt product handoff to X1.4-B

Date: 2026-10-22. Branch: `work/rust-native-protocols-x14a-20261022`.
Remote HEAD was checked immediately before creating this document and remained
`b6fba1827b0136c50123dab41fa4cb1c79a9ebce`. That commit changes only the Rust
protocol connector; the Qt paths below are unchanged from its parent
`de115093691ff00371b6e8313e4f1bb832c1fa3a`.

This is a source audit. **No Qt source/UI was changed, no Windows Qt executable
was run, and no new Qt product acceptance is claimed in A8.** The final A8
report owns the actual Core CI results; this document does not predict them.

## Decision and acceptance boundary

**Start X1.4-B formally after the A8 Core gates are all green**, including the
original Windows Hysteria2 suite, official interoperability and exported C ABI
on Windows/macOS/Linux. Those six jobs establish the declared Core scope only.
They do not establish Qt import, DPAPI reload, QLibrary loading, QML controls,
system proxy or TUN acceptance. See the
[native workflow](../.github/workflows/rust-native-protocols.yml).

The new protocols can run from native Rust `Config`, but the Qt product still
uses a separate, older C++ importer and outbound projection. Removing a protocol
whitelist alone would leave authentication, TLS, transport and UDP fields
unmapped. Unsupported options must continue to fail without silent downgrade.

## Ten product checks

| Check | Verified source behavior | X1.4-B acceptance still needed |
| --- | --- | --- |
| Subscription to native node management | `NodeImportService::parse` calls C++ `NodeImporter::parse`, which calls `SubscriptionNormalizer::normalize`; there is no Rust native-conversion bridge. | Import through one validated Rust conversion path, then preserve the native result privately. |
| Node list protocol display | `ProxyNode::protocols/publicInfo` and QML can display VMess/Hysteria2/TUIC; `SwirlProtocolRegistry::describe` still uses the older Qt execution projection. Display does not prove executability. | Show actual native capability and unsupported-option reasons for every supported node. |
| Qt configuration to Rust | `RustCoreEngine::configuration` builds JSON manually and rejects the newly added protocol/transport combinations. | Preserve complete native credentials, TLS, QUIC, transport and UDP settings end to end. |
| Configuration updates and switching | C ABI already implements `start/configure/select/select_group/stop`; Qt `selectNode` uses `configure`, with saved-selection rollback on failure. | Exercise real new-protocol A/B switching, invalid updates and retained active state through Qt. |
| Windows DLL loading | `RustCoreEngine::start` loads `swirl_api` from the application directory and checks ABI version 1 and required symbols. CMake builds/copies the locked Rust DLL. | Run the actual packaged Swirl.exe/QLibrary path and verify its DLL identity, missing/incompatible DLL errors and cleanup. |
| Start/stop controls | Main connection controls reach `ThreadedEngine → RustCoreEngine → C ABI`. The separate Settings start action clears selection; see below. | Unify startup behavior; test persisted selection, repeated start/stop and resource release. |
| Authentication errors | `failProbe/updateProbe` retain failure stage/code; `NodeTestService` exposes phase/error. New protocols are rejected before reaching this path. | Verify actual TLS/authentication/timeout/cancellation failures in Qt; consume applicable new timing fields without inventing success. |
| Native traffic | Rust-build runtime sockets/protocol state belong to Rust; Qt receives counters and connection snapshots. | Prove new protocols through import/store/select/start and independent target traffic in the actual product. |
| Old engine paths | Rust builds have no automatic Mihomo fallback. Legacy sources remain, CMake defaults to compatibility mode, and ordinary Qt preview does not select Rust mode. | Reconcile the separate replacement work, then verify production flags, package contents, process identity and actual forwarding path. |
| TUN/system proxy/DNS/routing | System proxy and DNS/routing subsets are integrated; Rust configuration explicitly rejects TUN/gateway/LAN/metered sessions. | Test supported controls with new protocols; track unsupported TUN and other network modes separately. |

## Concrete conversion and persistence blockers

Sources: [NodeImportService](../src/Swirl.Quick/engine/NodeImportService.cpp),
[NodeImporter](../src/Swirl.Quick/engine/NodeImporter.cpp),
[SubscriptionNormalizer](../src/Swirl.Quick/engine/SubscriptionNormalizer.cpp),
[ProxyNode](../src/Swirl.Quick/engine/ProxyNode.h),
[NodeStore](../src/Swirl.Quick/engine/NodeStore.cpp), and
[RustCoreEngine](../src/Swirl.Quick/engine/RustCoreEngine.cpp).

- `ProxyNode` contains scalar credentials, `parameters`, `originalConfiguration`,
  `sourceFormat` and `conversionIssues`, but no typed native outbound/native config.
  `NodeStore::serialize/deserialize` cannot retain a field absent from that model.
- `NodeStore` uses Windows DPAPI and has no non-Windows plaintext fallback.
  Native private data must remain excluded from `ProxyNode::publicInfo` and QML.
- The Qt protocol whitelist accepts HTTP, SOCKS4/4a/5, Trojan, classic SS and
  VLESS; it rejects VMess, Hysteria2 and TUIC before starting Rust.
- SS accepts only `aes-128-gcm`, `aes-256-gcm` and
  `chacha20-ietf-poly1305`; the implemented AES-2022 modes are rejected here.
- Qt permits outbound UDP only for SS/SOCKS5, blocking VLESS/Trojan UDP.
- VLESS/Trojan projection supports the existing TCP/WS subset, without the
  typed gRPC/HTTP2/HTTPUpgrade/XHTTP transport fields. Qt REALITY is TCP-only;
  its Vision mapping requires the supported REALITY profile.
- Hysteria2 QUIC/pin/Salamander/bandwidth and TUIC v5 credentials/relay/QUIC
  settings have no executable Qt mapping. General Rust Xray conversion is not
  automatically inherited by the separate C++ normalizer.
- [C ABI `Command`](../core/crates/swirl-api/src/lib.rs) accepts native JSON for
  start/configure, but has no subscription inspect/import/convert operation.

## Additional startup inconsistency found in source

[SettingsPage](../src/Swirl.Quick/qml/pages/SettingsPage.qml)'s
`engineStartButton` calls `EngineController::start`. In
[EngineController](../src/Swirl.Quick/engine/EngineController.cpp), that function
clears `selectedNodeId` and sets `directSession=false` before starting the engine.
For a non-direct route, `RustCoreEngine::configuration` consequently finds no
selected node and returns the missing-node error. This is a **source finding,
not a Qt runtime reproduction** in A8.

The main connection control uses `connectNode/startConfiguredSession`, which
loads the saved selection and validates actual routing/network options. X1.4-B
should align the Settings action with this behavior and test both entry points.
Do not bypass the missing-node error with an implicit DIRECT session.

## Existing boundaries to reuse

[ThreadedEngine](../src/Swirl.Quick/engine/ThreadedEngine.h) constructs
`RustCoreEngine` under `SWIRL_USE_RUST_CORE` and passes work to its network thread.
`RustCoreEngine::start` checks DLL symbols/version and fails visibly; it does not
launch a compatibility process. `QLibrary::PreventUnloadHint` retains code for
in-flight work. The existing JSON ABI is bounded and remains version 1.

[CMake](../src/Swirl.Quick/CMakeLists.txt) defaults `SWIRL_USE_RUST_CORE` to OFF.
Legacy MihomoAdapter/SwirlEngineManager/SwirlProxyEngine/UDP sources and the
Mihomo manifest remain compiled when Rust mode is off or UI tests are on.
[Ordinary Qt preview](../.github/workflows/build-qt-quick-ui.yml) does not pass
`SWIRL_USE_RUST_CORE=ON`; its artifact is not automatically a native Rust product.
Rust Qt packaging is currently restricted to Windows by CMake.

[SystemProxySession](../src/Swirl.Quick/engine/SystemProxySession.cpp) has
snapshot/ownership/recovery handling; `EngineController::setSystemProxy` checks
the healthy engine and local listening port before taking ownership.
[RustDnsConfiguration](../src/Swirl.Quick/engine/RustDnsConfiguration.h) maps OS
DNS, explicit IP DNS, hosts, strict DoT/DoH POST and limited query-family policy.
Encrypted server names require explicit local IP mapping; unsupported bootstrap
or mixed configurations fail. `routingConfiguration` maps domain/suffix/keyword,
IP/source CIDR, destination port, MATCH, DIRECT/REJECT and supported policy groups.
Smart routing supplies `china_rules_directory` from the packaged rules directory.
These implemented subsets still require current-product integration tests.

## X1.4-B work and exit gate

1. Bridge Qt imports/edits to Rust validation/conversion; retain complete private
   native outbounds, diagnostics, provenance and stable IDs across DPAPI reload.
2. Consume those outbounds through the existing ABI; update capability display
   and cover VMess/Hysteria2/TUIC, SS2022, stream UDP and typed transports.
3. Fix the Settings startup discrepancy and test all connection/stop/switch
   entry points, rollback, cancellation and accurate authentication errors.
4. Build/package explicit Rust mode and prove DLL identity plus actual traffic
   in Swirl.exe; integrate reviewed replacement-branch work without overwriting it.
5. Run Windows Qt import → encrypted reload → selection → native startup →
   independent peer/target → switch → shutdown acceptance with failure cases.
6. Test system proxy restoration, supported DNS/routing and normal product
   lifecycle. Keep unsupported TUN/LAN/gateway/metered capabilities explicitly
   separate until implemented and accepted. Preserve the existing UI.

Historical Qt evidence for older protocol subsets is not current A8 acceptance.
Core six-job success alone cannot close any of the product gates above.
