# Swirl 0.2.11 visual feedback — 2026-10-25

Continue in `D:/Codex/work/Swirl-ui-v2-20261024` on `work/swirl-ui-v2-20261024`. The installed 0.2.10 source is `e201d82104605601c8aa7842aa43108e3108e867`; this iteration addresses the user's three screenshots. Main/test and installed binaries are not updated by development or isolated tests.

## Changes

- Keep the existing 14 logical DIP shell/sidebar contours. Same-level card tokens and the two actual Activity cards now use 14dp rather than the Activity-specific 9dp override.
- Light canvas is neutral near-white `#FAFAFA`, with white independent cards. The light sidebar shares the continuous window material with no second fill or transmission darkening. Its contour, rim, exterior shadow, selection animation and navigation remain. Dark palette stays unchanged.
- Remove the inert chevron between the default-flow label and the exit picker. Give the actual picker a persistent flat surface/border, explicit “更换出口” action and larger downward chevron; preserve real target choice, keyboard input and cancellation. Keep the left explanation at its 148dp design width so the clickable target receives remaining width, including narrow windows.
- Update obsolete appearance assertions for the authorized shared background and 0.2.10 Activity master-switch semantics. Never click real host network settings during appearance checks.

Primary design reference: [Qt Quick Controls Basic ComboBox](https://github.com/qt/qtdeclarative/blob/dev/src/quickcontrols/basic/ComboBox.qml), inspected for native control/background/indicator separation; changes independently use existing Swirl controls. Existing Qt QML, UI UX Pro Max and Motion guidance applies. No framework or external runtime is added.

## Validation and limits

Local Release/MinGW builds and qmllint complete; qmllint retains existing unqualified-access warnings. Portable-core boundary tests pass (7). Native policy checks pass 364/364, appearance checks 190/190 (plus its separate process restoration check), motion checks 205/205; actual Activity and policy captures were viewed. The V2 source boundary guard still exits 1 for the existing 0.2.10 OverviewPage redirect, outside this delta; all shell geometry invariants pass. Do not relabel this legacy guard as passed or change its frozen baseline.

Native checks use fresh `SWIRL_TEST_ROOT` directories, explicit argument arrays and immutable EXE/DLL snapshots on never-activated desktops. System proxy actions in policy tests use the per-instance in-memory backend. Sampling-only VBlank/VSync overrides are inherited by those test processes; production defaults are unchanged. Real Qt captures are inspected separately from physical desktop composition.

Initial policy preflight correctly refused a missing test-storage directory before starting the UI; the runner now explicitly creates it. A first keyboard cancellation test sent Escape before the popup settled and to the root scene, producing subsequent modal-blocked failures. Preserve that attempt as failed. The replacement waits for the opened popup, hero completion and actual input focus, then sends the key to the owning window. No production cancellation behavior was changed to satisfy this fixture.

Appearance checks verify actual equal light sidebar/workspace RGB and alpha, including contrast and opaque fallback, while retaining dark and content-isolation checks. Policy checks exercise real pointer/keyboard selection, minimum-size affordance geometry and actual Activity card radii. Motion retains the existing suite. Exact final source, test counts and CI installer identity belong in the delivery evidence.

This is a visual feedback update. Visible desktop material/contour acceptance, DPI/multi-monitor appearance, private-provider/Codex networking, TUN and earlier terminal-page timing gaps remain unverified by this change.

## Production startup gate follow-up

Final-width source `3fc69e0` passed all 17 CI CTest suites but failed the separate real production startup gate in CI run `40203735526`. Local D3D11 `--smoke-test` reproduced an access violation after about 11 seconds with font-binding method-table warnings. The preserved matching Windows minidump locates the fault in `QQmlConnections::connectSignalsToMethods`, called by `QQmlObjectCreator::finalize` and asynchronous incubation. This is creation/finalization, not a demonstrated FontManager observer teardown fault.

`SwirlFontBinding` now waits for `Component.onCompleted` before publishing axes, scheduling refreshes or assigning Connections targets. The destruction hook disables this activity. Existing live font/fit-width/preview behavior and Qt.callLater coalescing remain; no page animation, effect, cache or asynchronous Loader is disabled. Three fresh identical rapid-navigation runs each completed all 61 pages without warnings or crashes after the target guards. Exact final source/package validation still requires the subsequent successful CI run; do not deliver the failed `3fc69e0` package attempt. A separate superseded `cff01e6` run `40203212477` failed an unchanged loopback-port fixture and produced no installer.

The existing `FontTests::qmlLiveAutomaticFonts` source-QML integration check passes (3 QtTest cases including setup/cleanup, no failures/skips) using the original synthetic `automation.ttf` fixture. It verifies live automatic font axes still update with the lifecycle guard. Qt's existing offscreen font-directory warning is retained; no private font was used or new Python dependency installed.

## Verified final delivery

- Product source: `fd5fd506d14281956e23845d0ee4b6ef80d0b0e8`, version 0.2.11. [CI 40204975412](https://github.com/SOLHK/Swirl/actions/runs/40204975412) completed both jobs successfully, including real production startup. This final record supersedes the pending-validation wording above.
- Final same-source native checks: policy 364/364, appearance 190/190 plus independent theme-restoration process, motion 205/205; rapid D3D11 smoke completed 61 pages with exit 0. Actual Activity/policy/narrow-window Qt captures were viewed. Font/live test above also passed; existing font-directory and qmllint warnings are retained.
- CI: all 17 CTest suites passed. Actual XML Qt totals are 651 passed, 0 failed, 11 skipped. Skips are independent-fixture/private-source requirements, not passes. Exact production graph, 18 reused engine objects, packaged loopback roundtrips, real startup, no-change rebuild and NSIS lifecycle steps passed.
- CI staged payload: 1509 files, exact inventory and all hashes verified. Installer PE FileVersion/ProductVersion are 0.2.11.0. Installer bytes 74658127; SHA256 `63dd7676a02156473f5a1f46f12ec10244d227d00ac83e855653a898bdca2950`. Candidate archive digest independently matches GitHub metadata.
- Deliverable: `C:/Users/sysfr/Documents/Codex/2026-10-25/ton/outputs/Swirl-0.2.11-UI-Refinement-Setup.exe`, with screenshot previews, hash, Chinese notes and `Swirl-0.2.11-交付证据.json` in the same directory. The installer was not executed on the user's machine. CI validated the staged payload; the installer payload was not independently extracted locally.
- Main remains `87409c0bf9c957ef113f84c176c5a1529c27b9df`; all development stayed on `work/swirl-ui-v2-20261024`. This delivery-only documentation commit does not rebuild or alter the accepted product source. All failed attempts and remaining desktop/DPI/private-network limitations above remain part of the record.
