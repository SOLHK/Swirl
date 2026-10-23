# U1 unified subscription and native Core integration

This file is a chronological integration ledger. Tables inside an earlier
checkpoint describe that checkpoint, not final acceptance. The complete source
disposition is in [U1-source-resolution.md](U1-source-resolution.md), the
product feature/gap matrix in
[U1-subscription-feature-audit.md](U1-subscription-feature-audit.md), and the
required conditional Qt menu in [U1-qt-fixture-audit.md](U1-qt-fixture-audit.md).
Only test artifacts whose `source_sha` equals the delivered branch tip can
establish the final result. A workflow's build success does not erase the
non-Windows encrypted-storage code gap or establish physical-device acceptance.

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

## Integration conflicts identified at U1-A

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

| Stage | Scope | U1-A checkpoint result |
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

## U1-E1: Qt request mitigation in the product path

Security source `9dd8a675eed6374ac1c35265074f594a39262479` is retained
as this merge's second parent. Its request policy covers subscription download,
telemetry, capture-origin requests and the product self-test, including rebuilt
redirect requests. All three Qt HTTP/2 request switches are explicitly disabled;
certificate verification and Rust's native HTTP/2/gRPC transports are preserved.

The official Qt advisory identifies 6.8.0–6.8.9 and 6.9.0–6.11.2 as affected,
and names 6.8.10/6.11.3 or its qtbase patch as fixes. U1's local installed SDK is
6.10.3, so local runs test the advisory's temporary request-level mitigation.
The unified CI must validate the fixed 6.11.3 product SDK before claiming an
upgraded shipped library. See the advisory linked in the source policy.

Integration found that the security branch's redirect fixture changed ports,
while the newer subscription bridge deliberately rejects cross-origin URLs to
protect signed source URLs/cookies. The positive TLS redirect case now exercises
two real same-origin requests; an additional negative case verifies a different
origin is rejected before TLS/HTTP reaches it. No production redirect restriction
was relaxed. The standalone suite now links the current JSON converter and
builds/stages the same checked Rust library as the product.

## U1-B/C2/F1: one subscription-to-Core product chain

The ordinary URI/Clash-shaped node path now calls `swirl_import_node_v1` through
the same checked library as JSON import and runtime control. It reuses the Rust
subscription inspector, typed transport builder and final `Config::validate`;
the former C++ runtime protocol converter is removed. VMess, Hysteria2, TUIC,
SS2022, stream UDP and supported VLESS/Trojan transports can reach the existing
native runtime. Unsupported options remain preserved and explicitly rejected.
The import ABI reports `network_verified: false`: parsing or listener startup
is never represented as a successful remote connection.

Nodes-only import/policy retention is selectively integrated from
`bbb4ea33d3a3ae596027b840af630260ba6bdbcc` and its regression work at
`871cc6e93a083c8624aadae8d9f4c1fe8db6e7e8`. Existing subscriptions without a
scope retain full-profile semantics; new node imports preserve DNS/rules/groups.
Refresh validates the replacement catalogue before the encrypted atomic commit,
retains source provenance and rejects dangling policy references. JSON async
transactions, stable identities, selection and original documents are retained.
INI section headers are recognized before JSON-array sniffing, restoring the
existing Surge/Quantumult X/Surfboard/Loon path without loosening JSON checks.

Subscription download now queries the platform proxy for the exact URL on a
worker, while preserving live Swirl proxy priority and local-target bypass.
The total 30-second deadline includes discovery. Cancellation discards late
query results; it does not claim to terminate an uninterruptible OS PAC call.
Actual previously owned Swirl/capture ports are excluded after shutdown, with
an explicit diagnostic if no valid proxy alternative remains. Tests use real
HTTP CONNECT and verified TLS, redirects, rejected certificates and retry.

Performance changes from `2b186783a704af3f4c1a91cd835997485282e2ec` and
`9e892b3746012ef8b1d983467b45cf6f336ddbe7` merge redundant UI notifications
and distinguish outbound establishment, origin TLS, HEAD response-header time
and complete Qt GET response time. A displayed outbound duration requires a
successful real request. No latency is fabricated, cached as a new result or
compared against Loon/Clash measurements with different definitions.

The final X14 source checkpoint `2a41b360d0fed90bf2818d5e4c8e93b4f41f021b`
adds source handoff/evidence only; its protocol implementation was already in
the baseline. Its historical green runs are retained as provenance, not U1
acceptance. This integration commit retains that source as an additional parent.

Six existing workflows now trigger on the U1 branch and check out the triggering
full SHA. They cover three-platform Rust/protocol/transport tests, the Qt product
chain, DLL identity, Windows packaging, and Qt request safety. Product SDK jobs
request Qt 6.11.3 and check the actual version; security jobs additionally retain
6.10.3 on all three systems to verify the temporary mitigation. Linux/macOS
build the complete product and execute its real loopback runtime self-test.

**Material platform limit:** encrypted catalogue storage currently implements
Windows DPAPI only. Linux/macOS reject persistence instead of writing secrets
in plaintext. Building those products and passing native/network tests does not
close their persistent UI import/restart loop. This is remaining code work,
not a physical-device validation item.

## U1-D/F2: route regression, package observation and first CI corrections

The U1 transport workflow now executes 131 additional existing Python cases:
DoT, DoH, negative DNS cases, answer/connection routing policy, subscription
import, diagnostics, streaming/half-close fixtures and the Rust product chain.
It requires every discovered case to run with no skips or failures and records
the full source SHA and built binary hashes. Windows product CI additionally
executes the existing four-protocol Qt subscription/DPAPI/routing fixture.
The bundled MRS package policy is checked in the Windows packaging guard.

Read-only Core observation from the five core-completion source commits is
selectively integrated. Current paired-package manifests, EXE/DLL/metadata/rule
hashes and expected source SHA are checked; historical package formats remain
diagnosable, and mixing formats is rejected. The tools do not start an external
proxy, change system settings, install a background launcher or claim that a
TCP snapshot proves DNS/QUIC routing. Monitoring defaults to one explicit manual
sample. The separate monitor installer is excluded. See the full source and
patch-ID audit in [U1-observation-source-audit.md](U1-observation-source-audit.md).
All 36 package-identity/negative fixtures ran successfully in local PowerShell
7.6.6 before this checkpoint; Windows PowerShell 5.1/7 run on the same pushed SHA.

The first U1 CI at `748040cb84f4a71d79a99cc50ab3807f828b6351` found two
startup defects. The R1 workflow used the unavailable `runner` context in a
job-level environment declaration; its test directory is now created inside a
PowerShell step. Qt 6.11.3 Windows changed repository layout, which aqt 3.3.0
does not recognize. Windows installs now pin the upstream merged fix at
`miurahr/aqtinstall@8c3695d4a4e1ceabf6a74dc6c79681656dc6b74b` through the
action's supported `aqtsource` input. The requested SDK remains 6.11.3. These
fixes require new-SHA remote execution before being called successful.

Local full-product compilation succeeded with Qt 6.10.3. The full Qt regression
exposed 28 RustCoreTests and one stream-test failure at non-Windows encrypted
catalogue writes (DPAPI is not implemented there); these are real product gaps,
not passing tests. Another timing fixture had an invalid non-UUID node ID and
was rejected before networking. The fixture now uses a valid UUID and explicitly
asserts production validation; its real SOCKS/HEAD timing and HTTP error checks
pass. No production validation or timing assertion was weakened.

A second GitHub API snapshot found 47 branches: all 45 original source heads
are unchanged, plus U1 and a new Activity V7 visual branch. The new branch's
three unique commits were inspected and excluded under the user's visual-work
boundary. See [U1-source-recheck.json](U1-source-recheck.json). Source inclusion,
checkpoint tests, CI builds, independent-peer traffic and physical Windows use
remain separate evidence categories. None of these checkpoint results is final
U1 acceptance.

## U1-B/F3: system proxy diagnostics and complete Qt fixture inventory

The independent legacy diagnostic fix at
`564e213ce604d7b79bb2414cd3aefba5744d46eb` is selectively integrated.
WinINET and the native registry manual-proxy state are observed separately;
registry-only activation is no longer shown as disabled. Unknown/malformed
values and read errors stay distinguishable. The current encrypted recovery
journal, ownership rules, external-change detection and independent guard are
preserved. Diagnostic export uses an allowlist and redacts additional protocol
URIs, PSKs, auth-str and Unicode hostnames. No visual redesign is included.

The shared registry reader is bounded and read-only. Windows fixtures use only
a unique temporary volatile HKCU key; live Internet Settings are not mutated.
The standalone importer now links the same new state module as the complete
product. The Windows product and three-platform importer CI both execute its
tests. Local integrated candidate checks pass: 23 proxy-state cases, 12 export
cases, and the importer/scope/loader suites. Final-SHA regression remains required.

The original RustCoreTests menu contains nine conditional independent-peer
slots. U1 now executes all nine through their existing Python harnesses instead
of relying on a green baseline run that omitted fixture-dependent cases. The
new Windows workflow checks the complete slot inventory, all five existing
REALITY lifecycle modes, actual Qt XML, source SHA, paired DLL metadata and
zero fixture skips. Public endpoint failure remains a test failure. Details:
[U1-qt-fixture-audit.md](U1-qt-fixture-audit.md). This is a new execution gate,
not a claim that the fixtures have already passed on the unified final commit.

The observation workflow's dynamic shell was moved to the supported job
`defaults.run.shell` location. The previous stage's fixed Qt 6.11.3 Windows
installation and four-job R1 workflow now start successfully in GitHub Actions;
that establishes installation/startup only, not product acceptance. Obsolete
U1 runs may be cancelled when a newer integrated SHA is pushed. Cancelled and
superseded runs are never counted toward final acceptance.

## U1-B/F3 continuation: cancellation, cache isolation and real regression fixes

Background subscription updates now have an explicit `cancelRefresh(id)` owner.
The existing refresh control exposes queued/active cancellation without allowing
a manual import dialog to cancel an unrelated subscription. Cancellation revokes
the generation, aborts the owned reply, removes only that provider's queue item,
and keeps the encrypted snapshot and selected node. Retry starts a fresh request.
Once encryption/atomic commit begins, cancellation is rejected through the
`nodesApplied` notification; the UI must not report cancellation after a save.
Direct Qt signal reentrancy is checked at text/file/URL/confirmation/refresh entry
points, so a cancellation or shutdown during `changed` cannot launch stale work.
Tests include real stalled TLS, manual-owner isolation, synchronous cancellation,
and Windows actual encrypted snapshot equality, reload, retry and commit guards.
Windows cases are mandatory in the importer XML gate; they are not treated as
executed by a Linux component check.

The source cache/log patches `3410ffb2ab872d4dd264e8431fd083193e0a8741` and
`ac4b051f2ac048bb56144245e558d5244f3f4d54` are selectively integrated. QML cache
paths include content revision, Qt version and QA/production flavor, respect
explicit production overrides and preserve old files for rollback. The existing
production EXE is launched twice against the same isolated directory in CI.
Successful public-endpoint diagnostics are INFO; failure diagnostics remain
ERROR. Neither change imports the source branch's visual redesign.

Actual CI at `208e50dbd5f0b05b607afab0386fd4bb0dae8b79` exposed additional
regressions; those results are retained as failed stage evidence:

| Exact stage run | Observed result and follow-up |
| --- | --- |
| [Rust/product 39900630355](https://github.com/SOLHK/Swirl/actions/runs/39900630355) | Linux/macOS complete product builds, loader and executable self-tests passed. The Rust menu had an obsolete gRPC negative. Windows full product exposed six failing suites and did not reach final packaging acceptance. |
| [Transports 39900630389](https://github.com/SOLHK/Swirl/actions/runs/39900630389) | The added complete routing/subscription menu exposed the same obsolete gRPC negative. Supported gRPC now has positive mapping/startup and ordinary imported-config traffic through the locked official Xray peer; unsupported options remain negative cases. |
| [Protocols 39900630419](https://github.com/SOLHK/Swirl/actions/runs/39900630419) | macOS official SS2022 failed before traffic: its server log reported `Address already in use`. TCP/UDP port ownership and bounded startup-conflict handling require revalidation; protocol/authentication/replay assertions are retained. |
| [Importer 39900630400](https://github.com/SOLHK/Swirl/actions/runs/39900630400) | macOS proxy download positive controls failed. The test CONNECT relay aborted on a normal upstream close and could discard response bytes. It now drains/flushes normal closure; certificate and redirect rejection assertions remain unchanged. Final macOS execution is required. |
| [Qt security 39900630424](https://github.com/SOLHK/Swirl/actions/runs/39900630424) | All six OS/SDK downloader jobs and the Windows fixed-SDK product security menu passed on this stage SHA only. |

The Windows failures also exposed assumptions invalidated by semantic node
identity. Rename tests must keep the same ID and selected policy reference;
adding a distinct authenticated endpoint still exercises live-tunnel preservation.
The >32 MiB rejection fixture now uses 1,000 distinct endpoints and asserts the
prepared count before retaining the original size/error/old-file checks.
Hysteria2 positive native-listener startup is distinguished from the still
unsupported port-hopping negative; neither local startup nor a rejected option
is presented as a successful remote QUIC session.

The four product suites that formerly wrote only text files now also emit XML
and stdout, preserving assertions while making future CI failures directly
diagnosable. Changes in this section need a fresh clean-SHA regression; the
stage runs above are not added together into final acceptance.
