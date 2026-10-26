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
| activity | INTERNET pending/result flow; shared detail origins | pending | pending |
| proxies | test flow; row/menu interruption; browse/runtime separation | pending | pending |
| policies | receipt flow; reversible curved tabs; picker origins | pending | pending |
| subscriptions | source update flow; reversible curved row expansion | pending | pending |
| settings / fonts, 13 sections | arc directory; live async pane cache; local history | pending | native 13-section, draft and real key checks passed |
| featurehub | stationary shared origin; interaction contact/light | pending | native navigation and input passed |
| FeatureCatalog dynamic routes | pending | pending | pending |
| overview | pending | pending | pending |
| processes / gateway | pending | pending | pending |
| rules / dns | pending | pending | pending |
| capture / requestlogs / inspector | pending | pending | pending |
| tls / rewrite | pending | pending | pending |
| external / dashboard | pending | pending | pending |
| profiles / modules / scripts | pending | pending | pending |
| connections / logs / traffic | pending | pending | pending |
| toolbox / api / workbench | pending | pending | pending |
| automation / breakpoint / map / replay | pending | pending | pending |

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
Assertions were retained. This checkpoint does not claim the pending visual
migration or physical high-refresh performance is accepted.
