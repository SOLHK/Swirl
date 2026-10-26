# Swirl 3.0 page migration

This is an implementation ledger, not route acceptance. The native smoke fixture
enumerates 61 routes; file counts do not substitute for that result. All runtime
state remains owned by the existing controllers. No private provider is used.

## Layout and interaction choices

The shared palette and font manager come from the APEC design foundation.
Page titles use navy with a stable 26px hierarchy; body text remains 14px and
supporting text 12px. Content aligns to the shared page inset. Empty states name
the missing input and the next available action. Ordinary data workspaces use
open toolbars, a single table surface and an anchored inspector, rather than a
grid of identical cards. The one memorable state treatment is the small curved
flow, bound to a real operation.

Activity becomes a connection status band, a broad transfer workspace and a
compact diagnostic rail. Nodes use a source-scoped resource table. Policy is a
route workspace showing the permanent default policy and service precedence.
Subscriptions form a source ledger with inline, reversible detail expansion.
Settings use a keyboard-owned section index and a reading-order form. Tools
and draft modules clearly distinguish saved input from actual execution.

## Coverage ledger

| Route / family | Interaction first | Visual migration | Verification |
| --- | --- | --- | --- |
| activity | INTERNET pending/result flow; semantic metric origins | implemented | latest load/input; full metric geometry regression pending |
| proxies | test flow; row/menu interruption; browse/runtime separation | implemented | latest load/input; full node fixture retest pending |
| policies | receipt flow; reversible curved tabs; picker origins | implemented | latest load/input; full policy fixture retest pending |
| subscriptions | source update flow; reversible curved row expansion | implemented | latest native dirty/modal/return input passed |
| settings / fonts, 13 sections | arc directory; live async pane cache; local history | implemented | native 13-section/draft/key checks and latest input passed; font pressure pending |
| featurehub | stationary shared origin; interaction contact/light | implemented | native navigation/input passed |
| FeatureCatalog dynamic routes | reversible local sections; real local draft edits and priority | implemented | 32 dynamic routes loaded; real form/tab/reorder/restore checks passed before final visual |
| overview | shared action feedback; unavailable adapters remain unavailable | implemented | latest native load/input passed |
| processes / gateway | retained linked detail origin/return; actual selection and menus | implemented | latest route loading passed; visual capture pending |
| rules / dns | receipt pending/error; shared radio/focus and guarded editor lifecycle | implemented | latest native add/delete and DNS Apply/Cancel passed |
| capture / requestlogs / inspector | actual listener flow; request detail/read-only sections | implemented | latest native loopback listener/flow passed; visual capture pending |
| tls / rewrite | actual enabled-state flow; shared guarded rule/certificate dialogs | implemented | latest native CA generation/interception/flow passed; visual capture pending |
| external / dashboard | real source selection and read-only summary feedback | implemented | latest independent-window open/close passed; visual capture pending |
| profiles / modules / scripts | stable-key row mutation; actual script execution state | implemented | latest native local script save/evaluate passed; visual capture pending |
| connections / logs / traffic | linked inspectors; retained route metadata and metric targets | implemented | latest route loading passed; visual capture pending |
| toolbox / api / workbench | real measurement flow; local reference selection | implemented | native API reference selection retained inactive service; final visual pending |
| automation / breakpoint / map / replay | local tabs/buffers retarget; execution stays unavailable | implemented | native local draft isolation/no-execution checks passed before final visual |

All corresponding dialogs, menus, loading/error/empty states and secondary
panes remain in scope. Physical 60/120Hz, high refresh, real GPU performance,
100/125/150/175/200% visual acceptance and private networks remain unverified
until separately measured. Application Logo sources remain SVG.

## Interaction foundation checkpoint

Before the visual page migration, the independent Qt 6.12.0/GCC 15.1 build
passed, using its own CMake and Cargo target directories. The three GNU runtime
DLL hashes were verified against that compiler's bin directory. The portable
core dependency guard passed 7 tests; no Rust or host networking changed.

Actual isolated checks: 61-route offscreen/software smoke passed; native node
UI passed 635 checks; native policy UI passed; navigation passed with all 13
settings sections, cached diagnostic/font drafts and real Down/Alt-Left/Window
Escape input; native interaction passed 66 checks; APEC motion passed 36 checks;
the earlier native motion suite also passed. The final clean navigation/input
evidence is in `work/build-pages/evidence-20261027-035404`, APEC in
`evidence-20261027-035507`, and final 61-route smoke in
`evidence-20261027-035254`. These are controlled UI fixtures.

Earlier failing runs remain in the local evidence directory. They caught an
OutboundMode menu still using the old Qt Menu lifecycle, a settings visibility
feedback loop, and an About test using a fixed 80ms wait before asynchronous
content was ready. The menu now consumes the shared popup motion, offscreen
settling observes the page's visibility without feeding its own moving binding,
and the test waits for actual readiness and finds the 104dp SVG inside the page.
Assertions were retained. That checkpoint preceded the visual page migration.

## Main visual source checkpoint

All 31 original page implementations have been migrated, including the shared
FeatureModule implementation for 32 dynamic catalogue routes, the independent
request window and the request-inspector overlay. Settings has 13 retained
sections and five supporting panes; these supporting files are not extra main
routes. Every family is listed above with its actual verification scope.

The independent Qt 6.12 build of the complete visual source passed. The latest
61-catalogue-route smoke passed with exit 0 in 13.27 seconds, and actual native
mouse/keyboard interaction passed 68 checks with exit 0 in 28.88 seconds. The
two additional checks verify that Capture/TLS flows follow the real controlled
listener/interception state. Evidence: `work/build-pages/evidence-20261027-042622`
and `evidence-20261027-042636`. The 308-check navigation/tool run immediately
before the last visual batch also passed: it exercises real local module forms,
retargeted tabs, priority/restore, independent mapping/replay buffers and the
continued absence of execution for unimplemented services.

This is an incremental source checkpoint. Final node/policy/motion reruns,
all-page/settings/dialog captures and the original cold font pressure fixture
are still pending. The known two remaining raw policy controls are tracked for
the next small interaction increment. Physical refresh/DPI acceptance and the
pending final review are not claimed. The capture helper uses real isolated
state, includes all runtime route IDs and secondary settings, and no longer
seeds fictional recent events or successful network activity.
