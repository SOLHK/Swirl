# U1 unified subscription and native Core integration

## U1-A: verified baseline and source inventory

Integration branch: `work/subscription-unified-integration-20261023`.
The user authorizes this independent branch; older single-branch handoffs do not
override this instruction. `main`, `test` and source branches are unchanged.

The GitHub branches API was read before selecting the baseline. All 45 remote
branch SHAs matched the isolated local Git object copies. No other working tree
is edited. The complete pinned snapshot and merge bases are in
[U1-source-snapshot.json](U1-source-snapshot.json).

Baseline: `442138a3d40fc13a9a761b43f3a2ce829a2b47ec`
(`work/subscription-native-bridge-20261023`). Git ancestry establishes that this
contains strict Xray/V2Ray conversion, the Qt import/store product chain, native
X14 protocol code through `21c562a7c7adc2654416636e4de2f038ffc220cd`, MRS routing,
and network fixes. It avoids importing separate VF and visual redesign branches.

The source snapshot is evidence of source inclusion, not test success. No
historical green run is treated as acceptance of U1. Every final regression must
report the exact integrated SHA.

| Source branch | Full source SHA | State at U1-A | Integration action |
|---|---|---|---|
| `work/core-completion-20261017` | `f87b6f98eb7018c4a5e86f281fe707764565ce58` | 5 source-only commits | audit-and-integrate |
| `work/core-rule-routing-20261021` | `b6dce3a415619c2c3b107fe7b761f63727da11b2` | Ancestor | included-in-baseline |
| `work/product-ui-fixes-20261021` | `bbb4ea33d3a3ae596027b840af630260ba6bdbcc` | 1 source-only commits | audit-and-integrate |
| `work/qt-http2-security-20261023` | `9dd8a675eed6374ac1c35265074f594a39262479` | 7 source-only commits | audit-and-integrate |
| `work/rust-core-full-replacement-20261022` | `5d96214ac80d63985cdccf4942c3c1d79035e793` | 5 source-only commits | audit-and-integrate |
| `work/rust-core-network-fixes-20261021` | `b8aa4f6f40a091697e89ae4c8291789661edca60` | Ancestor | included-in-baseline |
| `work/rust-dot-20261017` | `4dca7268bfd63db6b942f169811fa6d09e3388e0` | Ancestor | included-in-baseline |
| `work/rust-native-protocols-x14a-20261022` | `2a41b360d0fed90bf2818d5e4c8e93b4f41f021b` | 1 source-only commits | audit-and-integrate |
| `work/subscription-import-20261021` | `bf40f6dd639b0a9583a0dbea8e50851ac0c9ed29` | Ancestor | included-in-baseline |
| `work/subscription-native-bridge-20261023` | `442138a3d40fc13a9a761b43f3a2ce829a2b47ec` | Ancestor | integration-baseline |
| `work/swirl-performance-20261021` | `294cdd29fceb966e9c11437ed57188e4917004ea` | 15 source-only commits | audit-and-integrate |
| `work/x12b-resume-20261022` | `44dda9d4fe27a6667aa977d879d8dfc2ca82688d` | Ancestor | included-in-baseline |
| `work/x13-a-protocol-runtime-20261022` | `fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870` | Ancestor | included-in-baseline |
| `work/xray-v2ray-json-b-20261022` | `4e9f6ea0411c03bba418bb46884748ba7e0ba03b` | Ancestor | included-in-baseline |
| `work/xray-v2ray-json-import-20261021` | `44dda9d4fe27a6667aa977d879d8dfc2ca82688d` | Ancestor | included-in-baseline |
| `work/xray-v2ray-native-20261021` | `b88bb978d31fad1865e1b648cecd4f230bc3487c` | Ancestor | included-in-baseline |
| `work/xray-v2ray-qt-import-20261022` | `506014d6386610411f48c939ab62cb93a3509431` | Ancestor | included-in-baseline |
| `work/xray-v2ray-transport-20261022` | `fca13d3c06f9a6a45cab0b8e28c3587fbbe2f870` | Ancestor | included-in-baseline |

## Verified remaining integration conflicts

- R1 (`5d96214ac80d63985cdccf4942c3c1d79035e793`) has five source-only commits:
  paired Rust build/loader identity, native lifecycle/probes, license packaging
  and removal of Mihomo/legacy C++ forwarding. Preserve the Qt product services.
- The R1 and native branches independently add `swirl_api.h`. Keep BOTH the
  build identity ABI and the bounded import ABI.
- JSON import currently loads a separate `QLibrary`; route it through the R1
  checked library loader to avoid split ABI behavior.
- Non-JSON Qt nodes still use an older protocol allowlist and converter. Native
  VMess/Hysteria2/TUIC and additional transports must become callable from the
  ordinary product path; parsing alone is not completion.
- Qt security (`9dd8a675eed6374ac1c35265074f594a39262479`) adds two commits on R1.
  Keep its real TLS positive controls and cancellation fixture. It mitigates
  request-level HTTP/2 while Qt 6.10.3 itself is still an affected library.
- Product/performance source branches mix network fixes with visual changes.
  Extract nodes-only import/policy preservation and truthful timing semantics;
  do not merge unrelated layout, font, blur or release-number changes.
- Core completion has five monitor/installer commits beyond the common base.
  Audit the diagnostic tools individually; do not restore Mihomo execution.

## Existing capabilities and material limits

MRS missing-directory handling is already implemented in the baseline: normal
release operation loads verified assets next to the executable; an explicit
invalid directory fails with a diagnostic. Package staging and actual route
behavior still require fresh U1 tests.

The Windows Hysteria2 stack fixes are ancestors of the baseline. Windows official
peer, cancellation/reconnect, Core and exported-library tests must be rerun on U1.

TUN/gateway forwarding is explicitly rejected in current product code. This is
an unimplemented code capability, not a physical-device-only validation item.

## Stages and acceptance

| Stage | Scope | Current result |
|---|---|---|
| U1-A | Remote inventory, isolated baseline, ancestry/duplicate identification | Source audit complete; no product acceptance claimed |
| U1-B | Unified subscription and persistence chain | In progress |
| U1-C | R1 and native protocols, one DLL/ABI lifecycle | In progress |
| U1-D | Bundled MRS/DNS and actual routing | Source present; integrated regression pending |
| U1-E | Qt request safety | Merge and integrated regression pending |
| U1-F | Same-SHA multi-platform regression | Pending |
| U1-G | Final result and exact-SHA evidence | Pending |

Windows physical-device use, private subscription/provider connectivity and
like-for-like Loon/Clash performance remain separate from CI and controlled
reference-server tests. No credentials or private raw sources belong here.

## U1-C1: R1 merge and checked ABI unification

The R1 source `5d96214ac80d63985cdccf4942c3c1d79035e793` is retained as
the second parent of this integration merge. Eight explicit conflicts were
resolved by preserving JSON import/async storage and the R1 runtime removal.
The combined header exports both bounded import and build-identity functions.
The product and the importer now share one mutex-protected, identity-checked
library loader. Probe workers deliberately own isolated Rust sessions; they do
not create an alternative proxy engine or replace the product's live session.

The independent Qt product test project now builds its Rust library from the
same checkout, checks the EXE/library build identity, and stages packaged rules.
No cached/prebuilt library is accepted as evidence for this target. A concurrent
loader test checks eight callers see the same checked command/import exports.

An integration regression exposed a lifecycle mismatch: old catalogue tests
assumed synchronous startup while R1 starts on a network thread. Cancellation
now invalidates queued worker operations through an atomic generation and a
guarded next-turn probe callback. Tests cover cancellation before startup,
after the actual in-process runtime becomes healthy, and during a live request;
the original process-identity and no-late-traffic assertions are retained.

Candidate validation before this checkpoint uses Linux x86_64, Qt 6.10.3,
GCC 13.3, Rust 1.99.1 and the isolated checkout. Commands: `cargo fmt --all
--check`, `cargo check --workspace --locked --offline`,
`python tools/test_rust_only_runtime.py`, `python tools/test_rust_build_chain.py`,
and CMake/CTest in `src/Swirl.Quick/tests/xray`. These are checkpoint checks,
not final U1 acceptance. The final SHA will be rebuilt and tested after the
subscription bridge, security and CI changes are integrated.
