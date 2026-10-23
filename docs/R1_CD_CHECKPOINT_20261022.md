# R1-C/D: physical runtime removal checkpoint

Scope: `work/rust-core-full-replacement-20261022` only. No other branch or main is changed.

The 54 source changes promoted here are byte-for-byte identical to the SHA-256
and Git blob manifest from candidate run
https://github.com/SOLHK/Swirl/actions/runs/39733735385
at candidate commit `2d48b29d7289adb5218d8f2783f8cc89dcd6ae15`.
The temporary patch/export workflow has been removed; it never changed refs.

## Evidence observed before promotion

- Static sole-runtime guard: 8 tests passed.
- CMake build/deployment dependency graph: 3 tests passed.
- Native Rust formatting, Clippy, workspace tests and Release build passed.
- Windows MSVC compiled the actual Swirl UI and all migrated regression targets.
- Real Windows DLL loader fixtures: 26 passed, zero failed/skipped.
- Qt/Rust integration: 70 passed, zero failed, 9 explicitly fixture-dependent skips.
- Node suite: 22 passed, one private-provider skip, zero failures.
- Import suite: 27 passed, zero failed/skipped.
- Stream regression: 7 passed, zero failed/skipped.
- Extensions: 8 passed; telemetry: 17 passed; diagnostics: 8 passed.
- A separate Windows Python-driven Qt/DPAPI product test executed HTTP, SOCKS5,
  Shadowsocks and VLESS peers: download/import/encrypted persistence/reload,
  authenticated HTTP/verified HTTPS, node switching, ordered rules and stream
  preservation. Its result.json reports success and no skips.

## Failures retained, not counted as success

- SubscriptionFormatTests: 4 passed and 1 failed. The Surge fixture contains a
  complete INI profile with FINAL,DIRECT but still uses a node-only importer.
  The importer correctly refuses to drop global semantics; migrate this test
  to the existing transactional EngineController configuration owner.
- Public HTTPS received a certificate-verified TLS 1.3 HTTP 204 through an
  authenticated independent Shadowsocks node, but strict shutdown returned
  SSLEOFError. Both Connection:close and keep-alive experiments failed. This
  run is NOT a full public-network pass; no private provider nodes were used.
- This candidate workflow did not stage a production package or execute its
  clean-directory EXE/UI gates. Exact promoted-commit product acceptance must
  run separately. No installer is certified by this checkpoint.

## Physical deletions

MihomoAdapter, MihomoLogDiagnostic, SwirlEngineManager, SwirlProxyEngine,
NativeDuplexRelay, SwirlUdpExchange, OwnedProcess and ProxyLatencyProbe .cpp/.h;
scripts/stage-mihomo.ps1; packaging/mihomo-manifest.json; retired EngineTests,
EngineFixture, NativeEngineTests and ControlledProtocolPeers test sources.

Qt NodeImporter/SubscriptionNormalizer/NodeImportService/NodeStore, system proxy
ownership/recovery, telemetry presentation, OS integration and capture/debugging
remain. Clash YAML compatibility is retained as data parsing. Historical license
notices remain and cannot whitelist executable files in the package.

TUN, LAN proxy, gateway forwarding and unintegrated protocols remain explicitly
unsupported, with stored settings retained. Physical removal and compile/test
coverage are not a claim of complete R1 feature parity or user-machine repair.
