# U1 source-resolution and Core audit

## Audit scope and identity

Git ancestry and source comparisons below are anchored to `208e50dbd5f0b05b607afab0386fd4bb0dae8b79`. The initial API inventory contains 45 branches; the second API inventory contains 47 (the new integration branch and Activity V7). All 45 original heads were unchanged. Full snapshots remain in `U1-source-snapshot.json` and `U1-source-recheck.json`. There are 136 distinct source-only commit IDs in the initial inventory, before removing merge commits and overlapping branch ranges. This audit examined changed paths and executable implementations; titles and old test reports were not used as acceptance evidence.

History inclusion does not authorize restoring an obsolete runtime. For example, older Qt/Mihomo branches are ancestors of the chosen baseline, while R1 subsequently removes their runtime paths. Selective adaptations have different patch IDs from their mixed source commits; they are identified explicitly rather than called byte-identical merges.

A final pre-publication API check still found 47 branches; all original 45
source heads remain unchanged. The independently active Activity V7 branch
advanced to `9d6b572828c1cd4f14251b6cd74dfd5c777491df`. GitHub compare shows
only two new visual commits (`4e39d8d4b4c9aa029197cf4ea32a5a42cf2997d9` and
that head), affecting Theme, glass/sidebar materials and WindowChecks. All
patches were inspected and excluded under the same visual-work boundary;
neither source branch nor worktree was modified. See
[U1-source-freeze-recheck.json](U1-source-freeze-recheck.json).

## Every discovered branch

| Remote branch | Observed full head SHA | Resolution |
| --- | --- | --- |
| `backup/pre-qt-only-20261012` | `eed41b06d9e49d25fd0d7062fe5018a8fb669222` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `codex/surge-activity` | `49559fa5fa6ad999086afc2444ac17ed35945657` | Superseded: old ActivityTelemetry/Mihomo and SystemProxy implementation; retain unified TelemetryService/SystemProxySession. |
| `feat/mihomo-import-motion` | `b7f058f2f584602e6764fd28a808c3eb1c5ab088` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `feat/phase2-real-node` | `0d8bd85e8af668eee80be609c6c89813a354cb9d` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `feat/phase3-final-integration` | `564e213ce604d7b79bb2414cd3aefba5744d46eb` | Selectively retained: read-only proxy/privacy b3a6f624; QML cache isolation and success-log fix in this change; visual changes excluded. |
| `feat/phase3-system-proxy-ui` | `0ae36d6f2ac3ef55921f7927e06b6cc9401b99e3` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `feat/qt-quick-ui-demo` | `dcdfc072389d154fd53c542f33089e881e27c99b` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `feature/core-engine` | `170188de532a2f3f802abe89bde07c32908ea85d` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `feature/phase1-proxy-engine` | `7101cd25e19bbf292427714e58f5c48be9b6fb28` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `feature/ui-animation` | `170188de532a2f3f802abe89bde07c32908ea85d` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `fix/node-selection-layout` | `5c6e36adda7d327199ab399c16f54f71390679d5` | Excluded: former C#/WPF AdShield implementation, incompatible with the retained Qt/Rust product. |
| `fix/windows-motion-network` | `c113903e18067fbfc55308bc28bad56e90ae1aca` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `integration/all-open-prs-20261022` | `fa97b084769b39d8bddd5a6ffa40007345c5bc0f` | Do not merge wholesale: contains excluded VF/UI and legacy code; inspect independent network patches individually below. |
| `main` | `87409c0bf9c957ef113f84c176c5a1529c27b9df` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `test` | `e19dc9f663ac326b6654953db212b97177a56966` | Do not merge wholesale: same mixed integration lineage; relevant independent patches are resolved individually below. |
| `work/activity-page-v7-20261023` | `857f6b4e129ae138d3df674c1e6073d6b929b499` | Excluded visual redesign: V7-only ranking buckets and floating sidebar have no existing network-chain consumer. |
| `work/core-buildkit-20261017` | `6f007c73fdf449bda8322a5cf3a83214144c7999` | Excluded: old standalone development-cache artifact workflow, no runtime or product build change; current locked builds retained. |
| `work/core-completion-20261017` | `f87b6f98eb7018c4a5e86f281fe707764565ce58` | Selectively retained in 208: manual observation/offline identity tools; standalone monitor installer/autostart excluded. |
| `work/core-rule-routing-20261021` | `b6dce3a415619c2c3b107fe7b761f63727da11b2` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/product-ui-fixes-20261021` | `bbb4ea33d3a3ae596027b840af630260ba6bdbcc` | Selectively retained in 748: nodes-only import, preserved policy, selection and accurate latency; unrelated preview/version/UI changes excluded. |
| `work/qt-http2-security-20261023` | `9dd8a675eed6374ac1c35265074f594a39262479` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/rust-core-full-replacement-20261022` | `5d96214ac80d63985cdccf4942c3c1d79035e793` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/rust-core-network-fixes-20261021` | `b8aa4f6f40a091697e89ae4c8291789661edca60` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/rust-dot-20261017` | `4dca7268bfd63db6b942f169811fa6d09e3388e0` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/rust-native-protocols-x14a-20261022` | `2a41b360d0fed90bf2818d5e4c8e93b4f41f021b` | All executable changes inherited through 21c562a7; head is only handoff documentation, retained separately. |
| `work/subscription-import-20261021` | `bf40f6dd639b0a9583a0dbea8e50851ac0c9ed29` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/subscription-native-bridge-20261023` | `442138a3d40fc13a9a761b43f3a2ce829a2b47ec` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/subscription-unified-integration-20261023` | `748040cb84f4a71d79a99cc50ab3807f828b6351` | Integration destination; this is the head recorded by the second API snapshot, not a final acceptance SHA. |
| `work/swirl-performance-20261021` | `294cdd29fceb966e9c11437ed57188e4917004ea` | Selectively retained in 748: notification coalescing, timing semantics, nodes-only tests; visual/layout/version changes excluded. |
| `work/swirl-ui-012-20261022` | `505216bc5007c9a8181c2d18490a50baa2b812c5` | Shared nodes-only fixes retained; 505216bc periodTraffic only serves excluded new visual pages. |
| `work/vf-axis-a3` | `66594e9d32a33c1d216319e2dccd2f35c7e47a4a` | Excluded by explicit task boundary: variable-font experiment and its evidence; no subscription/network implementation selected. |
| `work/vf-b1-public-containment-20261020` | `ba8039a1028808140453adcbe150438e2bb20385` | Excluded by explicit task boundary: variable-font experiment and its evidence; no subscription/network implementation selected. |
| `work/vf-macos-native` | `e6b44f83cd92e4b8082d54a84d4a98bef1cd5b28` | Excluded by explicit task boundary: variable-font experiment and its evidence; no subscription/network implementation selected. |
| `work/vf-macos-windows-d1-20261021` | `54e579f1b46ee75187069d40b9ec626b3cc980d5` | Excluded by explicit task boundary: variable-font experiment and its evidence; no subscription/network implementation selected. |
| `work/vf-metrics-b1` | `7902cdb7b449a56939346263df54a692c22d8337` | Excluded by explicit task boundary: variable-font experiment and its evidence; no subscription/network implementation selected. |
| `work/vf-p8-gvar-pro` | `7ff8d17cb18c624b50895cda00216a2f3a86f844` | Excluded by explicit task boundary: variable-font experiment and its evidence; no subscription/network implementation selected. |
| `work/vf-rebuild-c1` | `c0fe6c47f1a4a0854fcbbde7c9f08b791b44123e` | Excluded by explicit task boundary: variable-font experiment and its evidence; no subscription/network implementation selected. |
| `work/vf-smart-width-w1` | `2be6c78cae93544af57e90cb4904a399959d6b7c` | Excluded by explicit task boundary: variable-font experiment and its evidence; no subscription/network implementation selected. |
| `work/vf-takeover-abc-20261021` | `0d47f057b91912e3be4048cbd7a5548e505763da` | Excluded by explicit task boundary: variable-font experiment and its evidence; no subscription/network implementation selected. |
| `work/vf-windows-d1` | `844544f92c8f2c0cc96dfb7af02e4fa8e6604b4f` | Excluded by explicit task boundary: variable-font experiment and its evidence; no subscription/network implementation selected. |
| `work/x12b-resume-20261022` | `44dda9d4fe27a6667aa977d879d8dfc2ca82688d` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/x13-a-protocol-runtime-20261022` | `fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/xray-v2ray-json-b-20261022` | `4e9f6ea0411c03bba418bb46884748ba7e0ba03b` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/xray-v2ray-json-import-20261021` | `44dda9d4fe27a6667aa977d879d8dfc2ca82688d` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/xray-v2ray-native-20261021` | `b88bb978d31fad1865e1b648cecd4f230bc3487c` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/xray-v2ray-qt-import-20261022` | `506014d6386610411f48c939ab62cb93a3509431` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |
| `work/xray-v2ray-transport-20261022` | `fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870` | Included in integration ancestry; later Rust-only runtime and unified model remain authoritative. |

## Independent network and product patches

| Source commit (full SHA) | Actual implementation and final disposition |
| --- | --- |
| `70a18d58f2aafa41072fb422bfd0e4d6d342fb2f` | Read-only TCP/path observer retained and adapted to Rust package identity; the historical script name is not an engine startup path. |
| `75bc81d5ae6fb4b7955b06ebd410f7267c628ac8` | Manual Core observation and safe wrapper retained. Background startup, registry autorun and independent NSIS monitor installer excluded. |
| `00b9f50973fc14dc4c912c694c344d064e790a20` | Existing-session sampling retained; a live monitor is not started by U1 or CI. |
| `83e36ee40399c4f14f7b6257d744709c47e1ee1c` | Hash/offline diagnostic checks retained and extended to paired `package-manifest.json` / `swirl-rust-build.json`; incompatible mixed manifests fail. |
| `f87b6f98eb7018c4a5e86f281fe707764565ce58` | 64-bit inspection requirement retained; installer launch changes excluded with the standalone installer. These five sources were adapted in `75708ecdb41116214530464167eae46391fb1028` and integrated in `208e50dbd5f0b05b607afab0386fd4bb0dae8b79`. |
| `bbb4ea33d3a3ae596027b840af630260ba6bdbcc` | Nodes-only service/store/selection semantics retained via `dbfdc0bd355383234aecb1a537accaa5b9e592ca`; accurate timing retained with the performance adaptation in 748. Old preview version/installer and visual changes are not copied over R1 packaging. |
| `871cc6e93a083c8624aadae8d9f4c1fe8db6e7e8` | Nodes-only policy-preservation assertions ported to Rust Qt tests without reintroducing Mihomo; inherited D5 asynchronous storage and D6 identity guards remain. |
| `2b186783a704af3f4c1a91cd835997485282e2ec` | Engine/telemetry redundant-notification coalescing retained in 748; no fabricated or cached latency substituted for a handshake. |
| `9e892b3746012ef8b1d983467b45cf6f336ddbe7` | Full HTTPS timing labels retained in 748; probe metrics distinguish whole HTTPS request latency from bare RTT. |
| `564e213ce604d7b79bb2414cd3aefba5744d46eb` | Read-only Windows proxy-store observations and generic-URI/credential/Unicode-host privacy checks adapted in `b3a6f624372ecb4f67debc18bcf250a723f05c1f`, prepared for the next root candidate; current ownership/recovery logic is retained. Visual window changes excluded. |
| `ac4b051f2ac048bb56144245e558d5244f3f4d54` | Selectively ported here: `CodexNetwork/PublicEndpointReachable` reports INFO; failures remain ERROR. Current `SystemDataProvider` previously classified every telemetry diagnostic as ERROR. |
| `3410ffb2ab872d4dd264e8431fd083193e0a8741` | Selectively ported here: content/Qt/build-flavor QML disk-cache isolation. Adapted to the newer explicit `SWIRL_TEST_ROOT`: QA stays inside that root, production honors an explicit cache override, old cache files are preserved. No UI layout/version changes. |
| `49559fa5fa6ad999086afc2444ac17ed35945657`, `361053d5bed9238d8e15772bdf0b52800df64495`, `de28acb405a4863b27c065bf9232d062efc36171` | Superseded former SystemProxy/ActivityTelemetry/Mihomo product model. The retained `SystemProxySession`, `TelemetryService`, Rust-only lifecycle and strict import/store implementation are the single product path. The useful later read-only fixes are selected above, not silently discarded. |
| `e2254f4e321b6112dd3135989907a2664fba4928` | Alternative DoH implementation intentionally replaced by the integrated chain below after comparing executable validation, resolver wiring, negative cache and IPv4 query-family behavior. No second resolver/model is introduced. |
| `6f007c73fdf449bda8322a5cf3a83214144c7999` | Standalone offline development cache export only; it fetches extra dependencies for a proposed HTTP/2 DoH experiment. Excluded because the actual product uses locked native authenticated HTTP/1.1 DoH and current build workflows. |
| `505216bc5007c9a8181c2d18490a50baa2b812c5` | Monthly `periodTraffic` display API only consumed by the excluded visual redesign; no current network or node consumer requires it. |
| `1a29ba119fcc7d858af3ce677f91c6cab4807c85`, `857f6b4e129ae138d3df674c1e6073d6b929b499` | Parent independently inspected GitHub commit files: V7-only proxy-ranking buckets and floating sidebar. Excluded by the visual-redesign boundary. These remote objects were not present in the audit worker's cached object database. |
| `5c6e36adda7d327199ab399c16f54f71390679d5`, `9d73cbc25f33bc599187ab4b55b99cd9f6f56343` | Former C#/WPF AdShield configuration/store/node UI, not a second model to merge into Qt/Rust. Excluded as obsolete implementation. |

The other performance-branch changes modify Activity layouts, visual styling,
window blur state, lazy page presentation or preview release labels. They are
excluded from this subscription/Core integration. VF commits touch font tooling,
font manager/width experiments, their workflows and evidence; none is selected
to repair this network path. The mixed `test`/`integration/all-open-prs` branches
must not be merged to recover these individually resolved patches.

## DoH quality comparison and duplicate control

Reproducible comparison:

```sh
git range-diff 'e2254f4e321b6112dd3135989907a2664fba4928^!' 'c6f4b4d0e2e9c3449ee0d21b8b2b6a043753374e^!'
git show --pretty=format: <sha> | git patch-id --stable
git merge-base --is-ancestor <sha> 208e50dbd5f0b05b607afab0386fd4bb0dae8b79
```

The range-diff reports one source-only patch and one target-only patch. This is
an independent implementation, not an equal patch which happened to be renamed.

| Commit | Stable patch ID | Disposition |
| --- | --- | --- |
| `e2254f4e321b6112dd3135989907a2664fba4928` | `895936f2d8b50bafe6063274eb1e097187fba4aa` | Replaced alternative; not an ancestor |
| `c6f4b4d0e2e9c3449ee0d21b8b2b6a043753374e` | `a42ec585e142bd7950498624962dab1f1c082273` | Native bounded DoH framing, ancestor |
| `e12b1a21f182111b16598d0f82784498bd58c080` | `c4be0b3f949beed04b4b4adeef8f6e58239369a1` | Resolver/configuration/product wiring, ancestor |
| `95b4fbc8f58b166a93fcc10b648bef39d396c4d6` | `11746afc2123b3f4e0b970d0e5b984abed0d63e4` | Negative-cache behavior, ancestor |
| `f81eab6e2eaf5a2d9f1f538a4ce04cde268797c0` | `e54d125e22451aa9800eb70d688480d1dc7b09af` | Explicit DNS query family, ancestor |
| `564e213ce604d7b79bb2414cd3aefba5744d46eb` | `fcebe2424b8292e65af65627b5fa32481d6a7283` | Selective read-only/privacy adaptation; whole patch includes excluded visuals |
| `ac4b051f2ac048bb56144245e558d5244f3f4d54` | `06fc80806591fe857e8f35a780e384de554f3487` | Selective log-level adaptation |
| `871cc6e93a083c8624aadae8d9f4c1fe8db6e7e8` | `32b624cb9c37085cf0fd07b5c9653ce26d667735` | Tests adapted to the newer Rust runtime and D5/D6 store |

Both DoH variants authenticate TLS with an explicit bootstrap address and bound
HTTP parsing. The retained implementation validates one existing IR-v1
`DnsTlsServer` model with optional `https_path`, forbids mixing encrypted and
plaintext fallback resolvers, and includes subsequent negative-cache and
query-family fixes. `dot::resolve` dispatches to DoH when `https_path` exists.
The resolver's explicit-upstream checks therefore correctly include DoH through
`tls_servers`; absence of an additional `https_servers` field is not a bug.
Its parser bounds headers, bodies and trailers, rejects ambiguous framing and
unsupported compression, and treats conflicting cache hints conservatively.
Reintroducing e225's separate `dns_https.rs` and `DnsHttpsServer` would split the
schema again and lose the integrated follow-up behavior.

## Rust protocol lineage, routing and installed rules

- X1/X1.2/X1.3 code is already on the chosen baseline, through the native,
  JSON import, Qt import and transport branch SHAs in the inventory. X14's
  latest executable ancestor is `21c562a7c7adc2654416636e4de2f038ffc220cd`.
  The Windows-sensitive QUIC dispatch heap-allocation fix is
  `b6fba1827b0136c50123dab41fa4cb1c79a9ebce`; poll-frame isolation and strict
  Hysteria2 stack regressions are
  `5d6b9e370ae29add8ed11d8c8ebf9e54c2ea2611`; normal authentication-request
  stop handling is `21c562a7c7adc2654416636e4de2f038ffc220cd`. All are ancestors
  of 208. Their presence is not Windows runtime acceptance.
- `china_rules_directory` is optional and validated. Release resolution uses
  the real executable directory's `rules` subdirectory. The repository fallback
  in `core/crates/swirl-routing/src/mrs.rs` is debug-only. No developer absolute
  path is required by the installed Release product.
- `SwirlRustCore.cmake` stages bundled rules beside the executable/DLL.
  `Stage-WindowsRustProduct.ps1` uses the verified rule-copy helper, and the
  active `Swirl.nsi` packages that staged tree under the user's local Programs
  directory. The obsolete preview installer is not the active build script.
- The two fixed rule digests, `MRS\x01` format/version, 16 MiB compressed bound,
  64 MiB expanded bound and two-million item bound remain enforced. Invalid
  bodies, malformed tries, trailing bytes and absent rules fail explicitly.
- Rule evaluation retains explicit priority, then Chinese domain/IP direct
  decisions and foreign proxy decisions. Explicit upstream DNS resolution used
  for China-IP decisions is carried into the final dial target; the code does
  not classify one address and silently resolve another at connection time.
  This is system-proxy/listener routing; TUN is not implemented.

## Runtime ownership and honest remaining categories

The product constructs one `ThreadedEngine`/Rust Core lifecycle. The shared
`RustCoreLibrary` loader pins the paired native library and checks ABI/build
identity. The C ABI controller can also own up to three isolated node-probe
handles: these are deliberate Rust test/probe instances, not hidden Mihomo
processes or a second product data path. Epoch/cancellation guards suppress
stale node/telemetry results. Native protocol admission now uses the strict
Rust inspector via `NativeNodeBridge`; the earlier UI capability whitelist no
longer separately blocks VMess/Hysteria2/TUIC configurations.

`MihomoAdapter`, the old engine manager/runtime selector, legacy native relay,
old probe data channel and Mihomo download/staging path are removed by R1.
Remaining Mihomo mentions are format compatibility, historical docs/licenses,
negative source guards or the manual read-only observation script. That script
does not download/start/stop an engine or mutate system proxy settings.

| Category | Actual remaining boundary |
| --- | --- |
| A — code development required | TUN/gateway/allow-LAN product modes are explicitly rejected; macOS/Linux node-store encryption is not implemented and fails closed; arbitrary third-party full-profile DNS/policy translation is deliberately restricted. These are not merely missing real-device tests. |
| B — source inclusion | The root commit containing this document also includes b3a6f624 proxy/privacy, the cache/log adaptation and c58602b2's complete Qt fixture menu. They were absent at the 208 audit anchor; their final execution state belongs to C until exact-tip regression. No additional completed subscription/Core source is currently identified as awaiting integration. |
| C — integrated regression still required | All complete build/test gates, nine conditional Qt slots, five lifecycle modes, native QUIC/UDP and packaged rules must pass on the final root SHA. Earlier branch or 748/208 successes do not transfer automatically. |
| D — real environment only | Physical Windows 11 installation, provider subscription credentials, actual desktop system-proxy behavior, long-running reconnect/switch/exit and same-node performance comparison remain real-environment acceptance. GitHub Windows Server 2022 is not a physical Windows 11 result. |

Local validation for the new cache adaptation: the actual Qt 6.10.3 Core-only
`StoragePathsTests.cpp` executable compiled on Linux and passed 26 checks,
including a fresh child process, changed revision, QA/production separation,
explicit production override and preservation of earlier cache directories.
That component result is separate from Qt 6.11.3 Windows product acceptance.
The actual Windows test is added to the new fixture workflow; the root product
workflow executes fresh-directory and repeat-same-directory production launches.
Those launches verify restart behavior and do not by themselves prove cache hits.
