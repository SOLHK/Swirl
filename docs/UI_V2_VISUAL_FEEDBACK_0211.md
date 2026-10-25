# Swirl 0.2.11 visual feedback — 2026-10-25

Continue in `D:/Codex/work/Swirl-ui-v2-20261024` on `work/swirl-ui-v2-20261024`. The installed 0.2.10 source is `e201d82104605601c8aa7842aa43108e3108e867`; this iteration addresses the user's three screenshots. Main/test and installed binaries are not updated by development or isolated tests.

## Changes

- Keep the existing 14 logical DIP shell/sidebar contours. Same-level card tokens and the two actual Activity cards now use 14dp rather than the Activity-specific 9dp override.
- Light canvas is neutral near-white `#FAFAFA`, with white independent cards. The light sidebar shares the continuous window material with no second fill or transmission darkening. Its contour, rim, exterior shadow, selection animation and navigation remain. Dark palette stays unchanged.
- Remove the inert chevron between the default-flow label and the exit picker. Give the actual picker a persistent flat surface/border, explicit “更换出口” action and larger downward chevron; preserve real target choice, keyboard input and cancellation.
- Update obsolete appearance assertions for the authorized shared background and 0.2.10 Activity master-switch semantics. Never click real host network settings during appearance checks.

Primary design reference: [Qt Quick Controls Basic ComboBox](https://github.com/qt/qtdeclarative/blob/dev/src/quickcontrols/basic/ComboBox.qml), inspected for native control/background/indicator separation; changes independently use existing Swirl controls. Existing Qt QML, UI UX Pro Max and Motion guidance applies. No framework or external runtime is added.

## Validation and limits

Local Release/MinGW builds and qmllint complete; qmllint retains existing unqualified-access warnings. Portable-core boundary tests pass (7). Native policy checks pass 364/364, appearance checks 190/190 (plus its separate process restoration check), motion checks 205/205; actual Activity and policy captures were viewed. The V2 source boundary guard still exits 1 for the existing 0.2.10 OverviewPage redirect, outside this delta; all shell geometry invariants pass. Do not relabel this legacy guard as passed or change its frozen baseline.

Native checks use fresh `SWIRL_TEST_ROOT` directories, explicit argument arrays and immutable EXE/DLL snapshots on never-activated desktops. System proxy actions in policy tests use the per-instance in-memory backend. Sampling-only VBlank/VSync overrides are inherited by those test processes; production defaults are unchanged. Real Qt captures are inspected separately from physical desktop composition.

Initial policy preflight correctly refused a missing test-storage directory before starting the UI; the runner now explicitly creates it. A first keyboard cancellation test sent Escape before the popup settled and to the root scene, producing subsequent modal-blocked failures. Preserve that attempt as failed. The replacement waits for the opened popup, hero completion and actual input focus, then sends the key to the owning window. No production cancellation behavior was changed to satisfy this fixture.

Appearance checks verify actual equal light sidebar/workspace RGB and alpha, including contrast and opaque fallback, while retaining dark and content-isolation checks. Policy checks exercise real pointer/keyboard selection, minimum-size affordance geometry and actual Activity card radii. Motion retains the existing suite. Exact final source, test counts and CI installer identity belong in the delivery evidence.

This is a visual feedback update. Visible desktop material/contour acceptance, DPI/multi-monitor appearance, private-provider/Codex networking, TUN and earlier terminal-page timing gaps remain unverified by this change.
