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
and the cumulative time to validated final HEAD response headers. The source
performance branch's older complete-GET wording is not the unified Rust probe's
measurement contract. A displayed outbound duration requires a successful real
request and includes node resolution and protocol setup; it is not bare RTT.
No latency is fabricated, cached as a new result or
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

## U1-F4: platform regression corrections and preserved failure evidence

The last pre-publication branch check, at `2026-10-23 05:12:30 UTC`, still
contains 47 branches. Every source branch matches the previous freeze snapshot;
only this integration branch advanced. No source worktree, source branch or
`main` was changed. The following are **historical results for exactly
`cf9de0fcd1bf0e70e58d2d8fa7b76b7a797bb702`**, not acceptance of this next commit.

| Exact stage evidence | Actual result and scope |
| --- | --- |
| [Native protocols 39903102964](https://github.com/SOLHK/Swirl/actions/runs/39903102964) | All six jobs passed. Rust workspace totals were 674 on Linux/macOS and 675 on Windows, with no failed/ignored tests. The extra Windows case executes relocated-executable MRS lookup from a different working directory. The official/reference-peer menus passed on all three platforms, including the strict Windows Hysteria2 and SS2022 startup regressions. |
| [Native transports 39903102974](https://github.com/SOLHK/Swirl/actions/runs/39903102974) | All three platform jobs passed. Each DNS/routing menu executed 132 tests without failures, errors or skips; the later transport menus retain their separate actual results. This is controlled routing/peer evidence, not a physical-device or provider-network result. |
| [Qt security 39903103044](https://github.com/SOLHK/Swirl/actions/runs/39903103044) | All six OS/SDK download jobs and the Windows fixed-Qt product-security job passed. Each downloader matrix job has 11 passing Qt incidents, no failures/skips, and source-matched Rust metadata. |
| [Product 39903102958](https://github.com/SOLHK/Swirl/actions/runs/39903102958) | Linux/macOS complete Qt 6.11.3 application builds, 25-incident native loader tests and actual application loopback self-tests passed. Windows executed 14 CTest suites: 13 passed; one REALITY source-provenance assertion failed. The subsequent independent Qt subscription fixture, production package, repeated UI starts and installer were not reached and are not marked passed. |
| [Nine Qt fixtures 39903102999](https://github.com/SOLHK/Swirl/actions/runs/39903102999) | Failed because installing Qt changed the active Python after `cryptography` had been installed. Actual XML covers only one of nine slots (SOCKS5 UDP); eight are missing and no REALITY lifecycle mode ran. The collector correctly returned failure rather than counting the missing slots as successes. |
| [Observation 39903102991](https://github.com/SOLHK/Swirl/actions/runs/39903102991) | PowerShell 7 passed on Windows/Linux. Windows PowerShell 5.1 failed the JSON-array rejection contract. Its concrete type-wrapper difference requires the correction below and a new Windows 5.1 run. |
| [Importer 39903102938](https://github.com/SOLHK/Swirl/actions/runs/39903102938) | Linux/macOS completed all nine Qt suites with no failing/skipped incidents, plus seven actual HTTP/HTTPS node cases. Those portable reports explicitly say `persisted=false` and `reloaded=false`. Windows built the complete application and passed seven of nine Qt suites (211 passing, 11 failing, zero skipped incidents). One policy reload comparison confused QStringList with QVariantList; ten negative-loader fixtures were built into a different configuration directory. The real production DLL checks passed. Windows download cancellation/retry, encrypted snapshot/restore and active-session protection passed; subsequent Windows protocol/UI steps were not reached. |
| Local full product at this same stage SHA | Qt 6.10.3/GCC 13/C++23 complete application build and actual HTTP/SOCKS5/CONNECT/cleanup self-test passed. Twelve product CTest suites were executed: six passed and six failed at the missing non-Windows encrypted-storage precondition. The failures remain failures, including 28 RustCoreTests cases; no DPAPI replacement, plaintext fallback or new skip was introduced. |

The product workflow also retained a genuine public-network failure: authenticated
Rust Shadowsocks delivered HTTP 200 and verified TLS/HTTPS 204, but strict TLS
shutdown failed with `SSLEOFError` at `origin-close`. Core/listener/peer cleanup
completed. This result is not converted into a pass because the response arrived.
The next test records the failed Core snapshot and performs at most one bounded
diagnostic connection to the same chosen public IP/SNI/ALPN/HTTP target. Its
result has `proxy_result=false`, cannot replace the original failure, and still
requires certificate verification and strict TLS shutdown. Three real local TLS
controls require orderly close, reject truncation after 204 and reject an
untrusted certificate. The local public direct-control attempt was blocked by
DNS resolution, so it supplies no conclusion about the remote origin.

Corrections included at this checkpoint:

- Require an actual `System.Management.Automation.PSCustomObject` for manifest
  roots, nested Rust metadata and file entries on both PowerShell generations.
  Preserve the original 36 cases and add six array-wrapper rejection cases.
- Install the locked Python TLS dependency after the Qt action changes PATH,
  using the same Python 3.12 interpreter that executes all nine real fixtures.
  No fixture, lifecycle mode, public-network or zero-skip gate is removed.
- Preserve direct JSON source bytes exactly; for a Base64 wrapper, compare the
  exact effective bytes produced by the existing outer-whitespace normalizer.
  A new parser test checks byte equality, SHA-256, source index and preserved
  outbound values for raw and wrapped input. The Windows encrypted reload test
  additionally compares source document, fingerprint and node index unchanged.
  Protocol/profile/ALPN assertions and unsupported-option negatives remain.
- Compare reloaded policy snapshots in the actual persisted JSON model, while
  retaining the strict in-memory comparison and every DNS/group/rule value.
  Require the same explicitly selected node ID after refresh, NodeStore reload
  and EngineController recreation; container-type differences cannot conceal
  changed values or array order.
- Explicitly place all ten malformed-library fixtures in the test executable's
  `loader-fixtures` directory for every CMake configuration. Parent-project
  `RUNTIME_OUTPUT_DIRECTORY_RELEASE` previously overrode the generic directory
  on Windows. The original actual-DLL/ABI/identity checks remain, and future
  Windows failures also emit stderr diagnostics.
- Retain the original public-network failure and strict-close assertions while
  adding the bounded direct-origin diagnostic and independent TLS controls.

Local candidate checks for this correction passed 42 PowerShell 7 identity
cases, three real TLS controls and nine fixture-evidence guard tests. The actual
Qt parser also passed exact byte/hash/index checks for direct JSON, Base64 and
Base64 with outer whitespace; both changed Qt test executables compiled. These
are pre-commit component checks. An actual Ninja Multi-Config Release build with
both parent output-directory overrides produced all ten shared fixtures in the
expected directory and passed the original 25 loader incidents without skips;
Windows DLL verification still requires the new commit's runner. All final
builds and regressions must run again on
the newly published clean SHA; the earlier stage's green jobs cannot be carried
forward. The known non-Windows storage, unsupported product-mode and real-device
limits remain classified in the source/feature audits.

## U1-F5: restore complete menus and repair Windows delivery gates

This section records historical results of the published F4 commit
`1cd5a84315360c007fcca16c14752d0bc82c9f32` and the corrections made afterwards.
**These results are not acceptance of this new commit.** All final tests and
packages must identify the newly published full SHA and execute again.

| F4 workflow | Actual outcome and boundary |
| --- | --- |
| [Native protocols 39905833205](https://github.com/SOLHK/Swirl/actions/runs/39905833205) | Six jobs passed. Rust: Windows 675, Linux/macOS 674 each, zero failed/ignored. Official/reference-peer menus: 127 method executions on Windows/macOS, 145 on Linux including the additional constrained-stack Hysteria2 run. Windows cancellation, same-runtime reconnect and zero remaining tasks were observed. |
| [Transports 39905833198](https://github.com/SOLHK/Swirl/actions/runs/39905833198) | Three platform jobs passed. Each executed 132 DNS/routing methods and 61 transport-method executions with zero reported skips and actual cleanup. Three TLS ALPN methods are policy checks, explicitly not protocol interoperability. |
| [Qt security 39905833201](https://github.com/SOLHK/Swirl/actions/runs/39905833201) | All seven jobs passed. Six OS/Qt combinations each have 11 passing downloader incidents, zero failed/skipped. The Windows Qt 6.11.3 product job also passed its real DPAPI/import subset, telemetry, HTTP policy and actual application capture. |
| [Observation 39905833235](https://github.com/SOLHK/Swirl/actions/runs/39905833235) | Windows PowerShell 5.1, Windows PowerShell 7 and Linux PowerShell 7 each passed all 42 identity assertions. |
| [Source/package guards 39905833277](https://github.com/SOLHK/Swirl/actions/runs/39905833277) | Both jobs passed: runtime guards 8/8, dependency guards 3/3, Windows PS5/7 package-path assertions 28 each. Actual MRS copying from another working directory and missing/corrupt-resource rejection passed. The 2,094-file source artifact was hash-checked. |
| [Qt importer 39905833229](https://github.com/SOLHK/Swirl/actions/runs/39905833229) | All platforms passed nine Qt suites: Windows 222, Linux 182, macOS 181 passing incidents, zero failures/skips, and seven actual HTTP/verified-HTTPS protocol cases each. Linux/macOS jobs passed. Windows failed the later product-versus-tested-DLL hash gate; deployment and mounted QML checks did not execute. Portable evidence retains `persisted=false`/`reloaded=false`. |
| [Nine Qt fixtures 39905833261](https://github.com/SOLHK/Swirl/actions/runs/39905833261) | All nine slots executed: 22 XML documents, 67 passing incidents, zero failed/skipped; all five lifecycle modes executed. Public REALITY/Vision made eight HTTP/HTTPS requests after Qt import, DPAPI save/reload and A/B selection. This menu does not assert Python's strict TLS close contract. Its later private-inspector diagnostic classification failed, so the workflow remained failed. |
| [Unified product 39905833227](https://github.com/SOLHK/Swirl/actions/runs/39905833227) | Linux/macOS complete Qt 6.11.3 builds, 25-incident loader suites and actual executable self-tests passed. Linux Rust fmt/check/Clippy/674 tests passed, but the strict public Shadowsocks closure gate failed. Windows passed all 14 CTest suites, actual Qt/DPAPI product integration, test and production builds, and paired DLL hashes. Staging then misread CRLF CMake configuration; its remaining production and packaging steps did not execute. |
| Local F4 | fmt/check/Clippy and 674 Rust tests passed; complete Qt 6.10.3 product and importer builds passed. Actual Swirl HTTP/SOCKS5/CONNECT/listener cleanup passed. Nine standalone Qt suites passed, 182 incidents, zero failed/skipped. Full product CTest remained six passed/six failed because non-Windows encrypted persistence is unimplemented. These failures were retained. |

QTest incident counts include initialization, cleanup and data rows; they are
not unique method counts. Windows product CTest includes 11 QTest runs totaling
258 passing incidents and ten original conditional skips (nine fixture cases
plus one private-provider case), including repeated import-boundary execution.
The other three entries execute actual Node UI, Engine UI and capture. The
separate nine-slot workflow actually exercises the nine conditional fixtures
with zero skips. None of these results is physical Windows 11 acceptance.

### Failures retained without weakening assertions

The F4 public Shadowsocks gate completed HTTP 200, then verified TLS 1.3 and
HTTP 204 before `SSLEOFError` at strict `origin-close`. Its failure-time Core
snapshot has accepted=2, active=0, failed=0 and peer-consistent byte totals;
Core/process/listener cleanup succeeded. A bounded direct connection to the
same IP/SNI/ALPN also verified the certificate and 204, then failed identically.
The isolated [diagnostic run 39907081127](https://github.com/SOLHK/Swirl/actions/runs/39907081127),
workflow commit `5ae6b88270193fc40c3a08d871031b050fc500f2`, checked out F4 and
tested keep-alive, Connection-close and omitted-Connection variants on Linux
and Windows. All six completed certificate verification and HTTP 204, and all
six failed strict TLS closure. Diagnostic collection success is explicitly
`product_acceptance_evaluated=false`. No endpoint substitution, ignored EOF or
weaker shutdown assertion was introduced.

The original two `test_vmess_xray.py --strict-half-close` methods also actually
ran on clean F4 with a fresh release example and pinned official Xray. Exit 1
contained five failed assertions, zero errors/skips. Four variants received
`4 MiB + 17` bytes with matching hashes but reported `UnexpectedEof` or
`WebSocketTransportClosed`; the concurrent case stopped with six actual records,
not eight completed sessions. Tasks reached zero and cleanup errors were empty.
The example has no embedded source-SHA API: its identity was based on clean
checkout, build command, source and executable hashes. Strict closure remains
unaccepted independently of the ordinary 13-method VMess menu.

### Changes at this checkpoint

- Private inspection recognizes two complete fixed normalizer/native diagnostic
  strings; unknown strings still become `UnclassifiedNativeOrImportDiagnostic`.
  Native eligibility remains independently calculated. DPAPI, redaction,
  zero-network, immutable ciphertext/sidecar, overwrite and tamper assertions
  remain; exact diagnostics and eligibility must survive reload.
  Isolated source: `89cc64e31ae12a4fe143cf43aad175c5b4e9deaa`.
- The Windows fixture workflow runs the entire original 31-method subscription
  capture module using the same actual Qt inspector for both entry points.
  Actual discovered/executed IDs, source/ABI/binary identity and counts are
  recorded; absent required methods, skips and expected failures fail. It runs
  independently after prior fixture failures without converting them to success.
  Sources: `b46fc1f18eacdbe95e1eadafdb0deae802fd09a3` and
  `c3b196a57aa89227a1d6049615fd8da0d92e6062`.
- The new supplemental workflow restores 76 omitted existing methods: REALITY
  peer 16, TLS 19, source Xray 14, fingerprint oracle 4, standalone Vision 4,
  native SOCKS4 9 and native WebSocket 10. Both vector checks and original strict
  VMess methods run on three platforms. The original four REALITY public menus
  and DIRECT/native-DoH menu retain their Linux requirement. Independent menus
  continue after failures, with no `continue-on-error`; failures and incomplete
  source identity still fail the final summary. Existing protocol assertions
  are unchanged. Sources: runner `a04936c692979cc7a16b1087358c280555126bee`,
  workflow `839b2f277f163584c3b83d4abcbc97470c4fb38f`.
- Windows Release staging accepts the CRLF line ending in Visual Studio's
  CMake cache by adding only `\r?` before the existing multiline end anchor.
  Fourteen LF/CRLF cases invoke the actual staging entry point and preserve all
  28 package-policy checks. Missing Release, wrong source, UI-test builds and
  incorrect native identity remain rejected. Source:
  `cd344b530440e8bc7d2203bdefd58c389a98e8be`.
- The Windows importer now tests the actual product DLL. The two MSBuild/Cargo
  invocations had rebuilt native dependencies and produced different bytes.
  F4 importer metadata was observed; product metadata was not read before the
  old hash gate failed, so equality was not an observed result. The new step
  checks both identities against compile-time metadata before any tests, records
  both original hashes, and stages the product DLL into the test directory.
  All suites then use that DLL; the final strict hash gate and malformed-library
  fixtures remain unchanged. Source: `dfbc2d41e8edb93b86d29a40375c8f6056b17fb1`.
- Candidate NSIS/ZIP compilation follows all production identity, actual EXE,
  missing-DLL and repeated-UI gates, and precedes the mandatory public test.
  Original packaging commands and public assertions are unchanged. A later
  public failure still fails the job; a built package is retained explicitly as
  a candidate, not a release. Packaging-only failure does not suppress the
  independent public test after the UI gate. Initial ordering source:
  `db47935298c8de44e61967e1152490cb580adbf5`.

Candidate checks passed nine scheduler guards, seven subscription evidence
guards, 16 original REALITY peer methods, both vector checks, and the 28+14
PowerShell package-policy cases. After an execution-environment replacement,
all ten code/workflow files were recovered byte-for-byte against their previously
reviewed Git blob hashes; the nine and seven Python guards passed again. These
component checks do not replace final-commit CI. The earlier F4 Windows importer
and fixture artifact ZIP digests were reverified after recovery.

The 48-branch snapshot is [U1-final-source-recheck.json](U1-final-source-recheck.json).
The resumed 49-branch check is [U1-resumed-source-recheck.json](U1-resumed-source-recheck.json):
the integration head and all subscription/Core source heads remained unchanged;
only explicit visual/preview work advanced. Those independent UI branches are
excluded. Non-Windows secure storage, unsupported product/protocol modes,
strict-close failures and real-device/provider acceptance remain separate A/C/D
issues. No earlier stage's green jobs transfer to the newly published SHA.

## U1-F6: exact public candidate checks and explicit MRS resource boundaries

This checkpoint follows published F5
`2340f835a7f35321567554cbaf4613b425b54638`. All results in the following table
belong to **F5 only**. They do not establish acceptance of the new checkpoint.

| F5 workflow | Actual observed result and scope |
| --- | --- |
| [Native protocols 39940862341](https://github.com/SOLHK/Swirl/actions/runs/39940862341) | All six jobs passed. Rust: Windows 675 and Linux/macOS 674 each, zero failures/ignored. Official/reference-peer method executions: Windows/macOS 127, Linux 145 including its constrained-stack Hysteria2 run. The Windows QUIC lifecycle, reconnect, cancellation and actual FFI checks executed. |
| [Transports 39940862513](https://github.com/SOLHK/Swirl/actions/runs/39940862513) | All three jobs passed. Each executed 132 DNS/routing methods and 61 transport method executions, zero skips, no reported cleanup errors. China IP matching uses actual bundled IPv4/IPv6 MRS data; controlled socket routing is not a visit to a Chinese public site. |
| [Retained network regressions 39940862543](https://github.com/SOLHK/Swirl/actions/runs/39940862543) | All three jobs failed, with their failures retained. Each completed all 76 original deterministic methods and both vectors, no skips/xfail. Both original strict VMess methods executed on every OS. Linux's four original public REALITY menus stopped at an exact import assertion; its separate public DIRECT/system-DNS/native-DoH menu passed three checks. |
| [Qt security 39940862370](https://github.com/SOLHK/Swirl/actions/runs/39940862370) | All seven jobs passed. Six OS/Qt combinations each passed 11 downloader incidents with zero failures/skips. Windows Qt 6.11.3 full-product security XML has five passing incidents; actual telemetry, request-policy and capture CTest entries exited successfully. No unavailable per-case capture count is inferred from the exit code. |
| [Observation 39940862415](https://github.com/SOLHK/Swirl/actions/runs/39940862415) | Windows PowerShell 5.1, Windows PowerShell 7 and Linux PowerShell 7 each passed all 42 identity assertions. |
| [Source/package guards 39940862301](https://github.com/SOLHK/Swirl/actions/runs/39940862301) | Both jobs passed. Runtime guards 8/8, build guards 3/3, PowerShell package checks 28 original plus 14 Release-cache cases on each Windows shell. Actual MRS copying and missing/corrupt-resource rejection passed. All 2,099 source-package files were checked against their Git blobs. |
| [Qt importer 39940862364](https://github.com/SOLHK/Swirl/actions/runs/39940862364) | All three jobs passed. Nine Qt suites: Windows 222, Linux 182 and macOS 181 passing incidents, zero failures/skips. Each platform executed seven real controlled HTTP/verified-HTTPS protocol cases. Windows also verified actual DPAPI persistence/reload, the product DLL as the tested input, final byte-for-byte product/test/network DLL equality, 61 mounted pages and import UI at both 1.0/1.5 scales. Portable persistence/reload remains explicitly false. |
| [Nine Qt fixtures 39940862353](https://github.com/SOLHK/Swirl/actions/runs/39940862353) | Job passed. All nine slots, 23 invocations, all five lifecycle modes, 22 XML files and 67 passing incidents executed with zero failed/skipped. The entire capture module ran 31 discovered/31 executed methods, zero failures/errors/skips/xfail/xpass, including all four mandatory private-inspector cases. Eight public REALITY/Vision HTTP/HTTPS requests passed with actual DPAPI reload, preserved parameters, selection restoration, rejection and stop cleanup. This menu does not assert the separate Python strict TLS-close contract or physical-device/provider acceptance. |
| [Unified product 39940862307](https://github.com/SOLHK/Swirl/actions/runs/39940862307) | Linux/macOS complete Qt 6.11.3 products, 25-incident loader menus and actual executable loopback self-tests passed. Linux Rust fmt/check/Clippy/674 tests passed; its mandatory public Shadowsocks test failed at strict TLS shutdown. Windows passed all 14 relevant product CTest entries, actual Qt DPAPI/import/select/route checks, production build, strict product/test DLL identity, clean-directory actual EXE roundtrips, missing-DLL refusal, two UI starts and candidate NSIS/ZIP compilation. Its final public module ran four methods with one pass and three failures: two Windows diagnostic-fixture contract failures and the retained strict public TLS-close failure. |
| Local F5 | Clean-source Rust fmt, all-target check/Clippy and 674 workspace tests passed with permitted loopback sockets; the earlier sandbox-denied listener attempt remains a separate failure. Full Qt 6.11.3 product and importer builds, actual executable HTTP/SOCKS5/CONNECT cleanup, and nine importer suites (182 incidents, zero failures/skips) passed. Of the 15 relevant product suites, six passed and nine remained failed after two locally mis-permissioned ELF executables were retested with unchanged binary hashes. Independent font/visual/gateway suites were outside this network integration menu. |

All 32 F5 jobs completed: 27 succeeded and five failed (the three retained
network jobs and the Linux/Windows mandatory public-product jobs). Windows
candidate artifact `12498610290` has verified archive SHA-256
`8ace8291afae5f7f1905e9d3ddad99965bb0daa02629767e66bc45254aa865ff`.
Its 1,510 staging-manifest entries match the packaged bytes; actual AMD64 EXE,
native identity and both bundled MRS files match F5. The portable ZIP also
contains the subsequently generated diagnostic log. NSIS compilation is not an
observed installation/uninstall or signed-release acceptance. Windows public
HTTP 200 and verified TLS 1.3/HTTPS 204 precede `SSLEOFError` at origin closure;
a diagnostic direct connection to the same `142.251.153.120` address also fails
that strict closure contract. Neither direct result overrides the proxy failure.

QTest incidents include initialization, cleanup and data rows; they are not
distinct test methods. The nine-slot Windows job closes only its explicit
conditional fixture menu. A missing private-provider environment and the
Linux product's existing conditional skips cannot be reported as executed.

### Exact REALITY candidate mismatch

The restored original Linux public verifier rejected all four combinations of
rustls/Chrome and plain REALITY/Vision **before traffic**, with
`NativeCandidateParametersChanged`. The actual U1 inspector now includes
`udp: false` in its TCP VLESS candidate. The old expected whole-object literal
predated that field. This checkpoint explicitly requires the disabled UDP field;
it retains complete list/dictionary equality, all credentials, REALITY values,
TLS/WebSocket/flow values and the terminal REJECT route. It does not strip fields
or compare a permissive subset. Isolated source:
`a30cc4c09ffc275e750692a545b408285e1e59f2`.

Candidate validation replayed the actual F5 inspector for all four combinations:
the old verifier rejected all four, the corrected verifier preserved every
candidate, and all 64 deliberate field/missing-UDP/unknown-option mutations
remained rejected. This is input-conversion evidence only. Public networking
and strict shutdown must execute again on the new published source.

### MRS resource-boundary regressions

Three additional parser regressions cover a concrete gap in the original menu.
They exercise a matching-checksum compressed container over the explicit 16 MiB
contract, real streamed Zstandard expansion at exactly 64 MiB and one byte over,
and domain/IP rule counts and extra-header lengths at and beyond their limits.
The exact-bound controls reach the intentionally invalid later payload version;
over-limit cases must fail at the specific size/header gate. Test inputs retain
valid checksums so checksum rejection cannot conceal an untested resource limit.
The production parser, checksum/version requirements, 2,000,000-item ceiling and
all previous tests remain unchanged. Fourteen existing-plus-new MRS tests passed
in the candidate Linux run; final three-platform workspace execution is required.

The Windows security and R1 product uploads now retain the already-generated
capture diagnostics; R1 also retains the actual Node UI diagnostic file.
Only three exact upload paths change, so test commands, assertions, conditions
and verdicts remain intact. Isolated source:
`fdc105ab34a6ff535a45ca8ff5ff4f4239a15750`. F5 capture success remains the
observed CTest exit status, without inventing unavailable per-case counts.

### Deterministic Windows TLS diagnostic controls

F5's Windows public module exposed two additional controlled-fixture failures.
The intentional missing-close-notify peer used an immediate socket close,
which produced `ConnectionAbortedError` on Windows instead of the precisely
asserted `SSLEOFError`. The repaired fixture explicitly detaches TLS, sends a
TCP write-side FIN without TLS close_notify, and drains the client's alert before
closing the raw socket. All operations share a cumulative three-second deadline.
The exact `SSLEOFError`, failed result, verified certificate and HTTP 204 checks
remain, with an additional prohibition on an orderly-close success field.

For the untrusted-CA case, the F5 log records a server-side Windows
`ConnectionResetError` with errno and winerror both 10054 during `wrap_socket`'s
handshake. Only that precise platform/error/stage combination is handled for the
untrusted fixture. The client must still report `SSLCertVerificationError`
before HTTP, with no requests, response status or orderly-close claim. Trusted
connections, other errors and later phases still fail. Non-daemon bounded
handlers are joined before checking the unchanged empty server-error list.
The formal public proxy class and direct-origin diagnostic helper are unchanged.
Isolated source: `e972e3a67d9106dffa2809d3295a53976fcde0f4`.

The repaired three original control methods passed on candidate Linux with zero
failures/skips. The three-OS retained-network workflow now executes this exact
three-method menu independently, records actual discovered/executed IDs and
source identity, and fails on missing, skipped or failed methods. This does not
replace the complete mandatory public module in the Linux/Windows product jobs,
change public endpoints, relax TLS closure, or turn the public failure into a
diagnostic pass. Final Windows/macOS/Linux results require the new published SHA.

### Failures and platform gaps remain explicit

F5 strict VMess produced five failed assertions on Linux, three on macOS and five
on Windows. Every platform transferred all four 4 MiB + 17 payloads with matching
hashes; orderly authenticated closure did not pass for every transport.
The concurrent method stopped on failure after eight, six and seven recorded
sessions respectively. Recorded payloads were complete and cleanup errors were
empty, but these facts do not convert strict-close failures to passes. The
fixed client/reference-peer combination remains unaccepted for that contract;
the evidence does not by itself assign every root cause to Xray.

Linux's mandatory public Shadowsocks test received HTTP 200, then verified TLS
1.3 and HTTPS 204 before `SSLEOFError` at `origin-close`. The bounded direct
control to the same selected `142.251.219.35` address also failed strict closure.
The failure-time Core snapshot has active=0/failed=0, exact peer byte totals and
successful Core/process/listener cleanup. No weaker EOF handling, endpoint swap
or direct-control pass substitution is introduced.

Non-Windows node encryption remains unimplemented; NodeStore fails closed and
does not save plaintext. Linux's node/import regressions consequently fail,
and the node UI test reaches a later empty-list access after failed save checks.
Capture has a separate implementation gap: non-Windows `TlsCertificateService`
cannot generate/import a CA or issue a leaf identity. Its real service returns
empty certificate/key values, and the existing capture/Engine UI tests fail.
An independent Qt 6.11.3 trusted TLS/ALPN h2 positive control passed, so these
capture failures are not evidence that the Qt upgrade disables native HTTP/2.
Neither platform gap is classified as merely awaiting a physical device.

Portable CI builds bare Linux/macOS executables and tested native libraries.
It does not produce a deployed Linux package, macOS .app/DMG, code signature or
notarization result. CMake copies rules beside the actual executable, and Release
lookup is executable-relative; the portable loopback self-test does not exercise
an installed smart-routing package. Windows package evidence cannot replace
those missing portable deployment checks.

### Runtime and diagnostic-service boundaries

The production constructor has one primary `ThreadedEngine` whose implementation
is `RustCoreEngine`. Node selection and reconfiguration use its existing handle;
stopping clears it. Runtime, native import and Xray import share the checked
`RustCoreLibrary` loader and its ABI/source/build identity gates. No selectable
Mihomo or old C++ `ProxyEngine` fallback was found. Isolated node-speed workers
create up to three additional Rust handles from that same library; this is not
a claim that the entire process can only ever contain one Core instance.

Qt product services remain. With Core running, CaptureService sends HTTP and
CONNECT upstream through the Rust listener. Explicit independent capture uses
Qt direct connections when Core is absent; an already enabled capture listener
does not stop merely because the primary Core stops. The full application exit
does stop it. Explicit rewrite TCP port-forward rules also use direct Qt sockets,
including while Core is running. These are retained diagnostic/product services,
not a hidden alternate ProxyEngine, but all C++ forwarding paths have **not**
been eliminated. A broader requirement that every diagnostic forwarding socket
must pass through Rust is still unmet. `SwirlProxyGuard` only monitors ownership
and restores the system-proxy journal; it does not listen or forward traffic.

### Speed measurements and unproven comparisons

The node list displays `outbound_connect_ms` after a successful Rust HEAD probe;
details retain cumulative `response_headers_ms` and `origin_tls_ms`. The first
includes applicable node resolution, dialing, transport and protocol request
setup. Some protocols only write their authentication request before returning
the connector, so it is neither a bare node RTT nor universally a completed
authentication exchange. The cumulative HEAD value stops at validated final
headers, excluding response-body download, EOF and Core/UI startup. Rust exposes
additional microsecond resolution, TCP, proxy TLS/REALITY, QUIC/TLS, transport and
authentication observations; Qt currently projects only the three millisecond
fields. Unperformed phases are null, phases can overlap, and summing them is not
a valid reconstruction of total latency.

The three native timing methods produce eight observations per OS using HTTP
origins, so their origin TLS values are null. A separate existing HTTPS HEAD test
verifies the origin TLS phase. The repository's October 21 corrected GET samples
use the same target IP but different node names/exits and lack a source/binary
identity; they are historical measurements, not a controlled final-U1 comparison.
There is no accepted same-node/target/protocol/network Loon or Clash performance
comparison for this integration SHA. No ranking or speedup is claimed.

The latest source-only inventory is
[U1-f6-source-recheck.json](U1-f6-source-recheck.json). The final acceptance report
must identify the new full SHA, freshly executed commands, actual Actions runs,
and any remaining A/B/C/D issues. Historical F5 greens are not carried forward.
