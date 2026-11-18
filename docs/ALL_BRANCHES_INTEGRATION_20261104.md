# Swirl all-branch integration — 2026-11-04

## Scope and fixed source identity

The owner requested a subscription-download investigation, inspection of existing
GitHub fixes, integration of every remote branch, and delivery to `test`.
This request supersedes the older draft-PR restrictions against merging those
branches to `test`. It does not authorize promotion to `main`, force pushes,
branch deletion, a Release, or claims that previously failed product gates pass.

- Starting `test`: `63dde8812f85839aa6024cbba6c498c96cae022d`.
- Windows compatibility candidate inspected and fast-forwarded first:
  `0deb136403fa6cfe1f0562dd77034f2f1ab12ef4` (0.2.33).
- Integration branch: `work/subscription-all-test-20261104`.
- All-head ancestry verification commit:
  `34740282937fdf25178db1e02b311fdd8b755af2`.
- Fixed fetched inventory: **82 remote branch heads**; **82/82** were verified
  with `git merge-base --is-ancestor <fixed-sha> HEAD`, with no missing heads.
  See `ALL_BRANCHES_INTEGRATION_20261104.json` for every ref and exact SHA.

The ancestry result records preservation of branch history. It does not imply
that every historical implementation is simultaneously active in the product.
Later fixes and verified replacements take precedence over obsolete versions.
No unrelated existing checkout was reset or cleaned.

## GitHub investigation

The existing subscription-recovery commits, including `8e3fc984` and the older
subscription branches, were already ancestors of the starting `test`. The
Windows compatibility branch does not change the subscription fetcher or parser;
its completed automation cannot establish that it repairs the screenshot errors.

The mature client reference was reviewed for behavior and failure modes rather
than copied: [Clash Verge Rev issue 7752](https://github.com/clash-verge-rev/clash-verge-rev/issues/7752)
records client-dependent subscription HTTP 403 responses and independent curl
controls. This is a diagnostic reference, not proof that all HTTP 403 failures
are client defects or that a User-Agent change is always appropriate.

Current subscription findings and bounded local checks are recorded separately
in `SUBSCRIPTION_DOWNLOAD_20261104.md`. Private URLs, credentials, provider
payloads and decrypted cache data are excluded from these records.

## Integration decisions

At the starting `test`, 55 remote heads were already ancestors and 27 were not.
Those 27 reduce to 26 independent heads because the final Mac handoff includes
the Windows-native font branch. The table records the distinct work requiring
integration; the JSON inventory also covers every already-contained branch.

| Branch or group | Result and conflict decision |
|---|---|
| `main` | Ordinary merge preserving its ancestry; no tree change was needed. This does not change remote `main`. |
| `work/windows-proxy-compat-20261102` | Fast-forwarded the current checked Windows candidate, preserving its proxy stop/exit, app-local CRT, installer, streaming and protocol/security gates. |
| `work/about-attribution-license-20261103` | Ordinary merge of the About attribution and prospective policy documentation. |
| `work/core-buildkit-20261017` | Preserved its separate offline build workflow. |
| `work/core-completion-20261017` | Preserved optional monitoring tools and installer. Conflicting offline/private-DIRECT checks retain current source/DLL/rule identity checks, exact proxy exclusion and honest route-evidence limits instead of the old weaker manifest checks. No monitor was started by integration. |
| `work/u1-public-close-diagnostic-20261023` | Preserved the standalone diagnostic workflow. |
| `work/swirl-apec-motion-20261027` | Its two non-merge commits are patch-equivalent to existing `test` history. An explicit history-only ordinary merge preserves the branch without reverting later UI work. |
| `work/swirl-apec-pages-20261027` | The pages were already integrated as `e46f1204`, with receipt/settings work in `2d7b7c97` and glass tokens in `c59b0786`. Comparing the old page head to `e46f1204` found only unrelated `main.cpp`/capture-test differences under `src`; current refined pages, geometry, animation and About attribution were retained. |
| `work/swirl-performance-20261021` | Retained current equivalents and their existing tests: single publication per engine pulse, node-row invalidation, stale-sampling transitions, truthful HTTPS timing and nodes-only subscription scope. Its old 0.1.2 layout, packaging and blur helper are superseded by current Activity/native-helper implementations. |
| `work/native-tun-windows-20261030` | Preserved simulated TUN research history first, then reconciled the active product with the later isolated native implementation. The simulated command ABI is not activated alongside the native backend. |
| `work/native-tun-windows-20261030-isolated` | Preserved the native TUN implementation, restricted worker, delegated journal, driver/WFP diagnostics and enforcement gates. Shared TCP routing retains the Windows candidate's full-address loop detection, equivalent DIRECT address retries and partial-reply protection. |
| `work/native-lan-proxy-20261031` | Integrated authenticated LAN listeners and Qt controls. Loopback, LAN and native ingress share one registered-session budget and shutdown barrier. LAN endpoint/DNS boundaries remain enforced; unvalidated alternate-address retries are not enabled across that boundary. |
| `work/native-lan-gateway-20261031` | Integrated packet admission, client budgets, IPv4/IPv6 restrictions, transactional recovery and dedicated-LAN activation. Its PacketBridge changes were ported into the newer Core-owned bridge, retaining abort-on-drop, true failed-UDP idle handling and current DNS-guard audits. Separate TUN-scoped and gateway-scoped Windows WFP modules preserve both implementations without name collisions. |
| `work/vf-b1-public-containment-20261020`, `work/vf-metrics-b1` | Preserved metric containment/startup research, authored controls and original failure/evidence records. |
| `work/vf-axis-a3`, `work/vf-windows-d1`, `work/vf-macos-native`, `work/vf-p8-gvar-pro` | Preserved their independent axis/native/point-identity diagnostics and tests. |
| `work/vf-rebuild-c1` | Preserved standalone staging validation and retained both independent binary-contract and production-table-contract regressions when tests overlapped. |
| `work/vf-smart-width-w1` | Ported bounded width fitting and its native/solver tests. Current title geometry, input typography, multiline dialog-title behavior, palette, tabular figures, initialized lifecycle guards and owned QML bindings are retained. Fixed-width labels opt in explicitly and exclude text padding from the available fitting width. |
| `work/swirlvf-delivery-20261102` | Preserved vertical-layout research and Qt 6.12 evidence. Font CI keeps both W1 controls and exact-SHA delivery/PR coverage with public-runner and same-repository restrictions. |
| `work/swirlvf-recovery-20261102` | Preserved exact serialized-coefficient recovery and nested-blend admission checks. Independent experimental layout and nested controls are both retained. |
| `work/swirlvf-continuation-20261102` | Preserved local-box/hierarchical experiments, their selection guards, independent layout guards and serialized-coefficient reports. |
| `work/swirlvf-joint-acceptance-20261103` | Preserved joint-corpus work and exact expression-sharing options without removing the other diagnostic/admission options or their tests. |
| `work/swirlvf-windows-native-20261103`, `work/swirlvf-mac-final-handoff-20261103` | Preserved the native glyf/gvar alternative and sealed offline Mac reference reader/replay. Both heads are covered by the final Mac handoff ancestry. |

Old `backup/*`, pre-Qt feature branches and earlier subscription/Xray work were
already contained in `test`; their superseded runtimes were not reactivated.
The unused old `swirl-wintun` crate is removed from the final working tree rather
than weakening the portable-core platform boundary. Its complete source remains
in the ordinary merge ancestry. The obsolete simulated TUN entry points are
superseded by the native backend, not evidence of a functioning native data plane.

## Validation and limits

The combined tree exposed real integration defects before delivery: a missing
shared session semaphore, a Windows Gateway example borrowing an Arc rather
than its device, a fragmented-IPv4 UDP client-admission gap, and a loopback
route-rejection error-contract regression. These were corrected without
weakening the original assertions. The fragmented-client and budget regressions
were first observed failing and then passed with all 37 TUN package tests.
The workspace subsequently executed 1,141 passing Rust tests; three explicitly
privileged Windows fixtures were left for disposable CI. Native LAN push
coverage now includes `test` and `main`, so those existing WFP/DHCP ownership
fixtures run after direct integration pushes as well as development PRs.

The MinGW COM linker issue was repaired using SDK type UUIDs, following the
interface-identification approach in the [Microsoft Windows Firewall sample](https://github.com/microsoft/Windows-classic-samples/blob/main/Samples/Win7Samples/security/windowsfirewall/getfirewallsettings/GetFirewallSettings.cpp).
The UUID values and COM behavior are unchanged. A Windows GNU Clippy false
positive on an already-constant thread-local initializer is handled only on
that declaration/platform with a self-expiring `expect`; see the independently
reproduced [upstream defect](https://github.com/rust-lang/rust-clippy/issues/17566).
The complete workspace Clippy check passed with zero warnings/errors.

Separate real Loon-format mapping fixes and 305 affected-crate passing tests
are recorded in `LOON_IMPORT_COMPATIBILITY_20261104.md`. They do not establish
that the owner's real Shadowsocks URL now downloads. Its continuing Windows
403 and the owner's fresh successful Loon refresh are both recorded in
`SUBSCRIPTION_DOWNLOAD_20261104.md`; the difference remains unresolved.

The all-head ancestry verification ran and passed at the SHA above. Compilation,
the subscription/network tests, integrated Rust tests, boundary/source checks,
font research regressions and post-integration fixes must be reported against
the final delivery SHA by the delivery owner. Earlier branch CI results are
historical evidence; they are not results of this combined tree.

Integrated font authoring checks ran locally with an isolated Python 3.12.14,
`fonttools==4.61.1`, `numpy==2.2.6` and `uharfbuzz==0.56.3`, without private
fonts or native Apple probes:

- Complete discovery: **1,568 tests in 119.488 seconds; 17 failures, 17 errors,
  25 skips; overall FAIL**. Twenty-nine failing subcases involve the Unix-style
  executable Python protocol doubles, which Windows rejects with WinError 193;
  four require unavailable Windows symlink privileges (WinError 1314); one was
  the unconditional Unix `resource` import described below. These are recorded
  as failed/not exercised on this Windows host, not promoted to passes.
- The subset probe now uses the existing portable `peak_rss()` measurement
  function. The authored subset preservation test then actually passes **1/1**;
  unavailable Windows peak RSS is reported as null. No memory value is invented.
- The older C1 tests were reconciled with current checkpoint publication and
  GDEF admission. Actual serialized file hashes are bound to each report;
  independent stale writer instances must preserve both committed entries.
  The original variable GDEF fixture retains its 25-unit source delta, and
  reconstruction must reject the unremapped layout before creating a candidate.
  This file passes **19/19**. The GDEF path remains blocked rather than certified.
- Independent parser audit: **6/6 passed**.

The full failed discovery was retained locally. It was not rerun merely to
replace its result with a selected passing subset. Unix protocol-double and
symlink coverage requires a capable CI runner; existing security assertions and
production oracle invocation were not relaxed to accommodate this host.

Required integration compilation corrections include restoring the single
`Shared.connection_slots` field/initialization used by every ingress, adapting
the gateway smoke example to the current `Arc<WintunDevice>` interface, and
using the SDK's typed `__uuidof` values for LAN firewall COM activation so MinGW
does not depend on absent external CLSID/IID symbols. The TUN IPv4/Gateway merge
also requires actual second-client fragmented request/reply and client-budget
controls at the final UDP publication boundary; their final results belong in
the delivery's Rust report.

Windows 11 authenticated Codex Desktop, a real private-provider/selected-node
A/B, physical DPI/high-refresh and real LAN/TUN topology acceptance are not
established by this merge. No host proxy, TUN, routes, firewall or DNS settings
were changed by the merge operations. Font experiments retain their failed
precision/native-layout gates and do not certify or install a final font. No
private font, private reference payload or source outline is included.

Historical evidence and license files are preserved byte-for-byte even where
upstream files contain trailing whitespace. Their hashes must not be silently
invalidated to make a whitespace check appear clean. Newly authored source and
documentation still require the ordinary whitespace/static checks.
