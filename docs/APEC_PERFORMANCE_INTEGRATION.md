# Integrated APEC motion and performance evidence

This record supplements `APEC_MOTION_FOUNDATION.md` and
`APEC_GLASS_DESIGN_SYSTEM.md`. Native results must identify the complete page
source and the matching executable; successful foundation tests alone do not
accept the migrated pages.

## Historical sample audit

The retained `work/build-motion/evidence-20261027-033950/motion.json` reports
560 intervals, p95 6.7435 ms, p99 62.9959 ms and eight gaps above 50 ms. Seven
of those eight are in the warm phase. Seven end at the same route's
`moving=true` to `false` boundary; the remaining proxies gap has `moving=true`
at both snapshots. `SwirlPageHost.moving` includes its static 32 ms terminal
commit hold, so these observations do not establish continuous animation
through each gap. They also do not establish the absence of a real stall.

Six additional 26–35 ms gaps follow the mixed fixture's resize sequence.
The prior fixture had already visited several routes before starting its
stress probe and explicitly disabled transparency. It is neither a first-visit
benchmark nor a glass-shader performance acceptance.

Measured probe callbacks total 1.2741 ms on the rendering thread and 5.7422 ms
for GUI snapshots. These measured bodies alone do not explain the regular
63 ms gaps, but dispatch, final unlock and other observation costs were not
included. The reported 761,856-byte revisit delta is process working set,
not private bytes or GPU memory. The old data and its original aggregate
statistics remain unchanged.

## Continuous native measurement

The existing UI-test-only `RouteBench` retains all its raw frame, event and
GUI-snapshot records. Schema 3 adds direct rendering-thread timestamps for
frame begin, scene synchronization begin/end, command recording begin/end,
presentation queue and frame end. Render callbacks copy native state only;
GUI objects are read on the GUI thread. The stopping mutex remains the writer
barrier before disconnect and serialization. Dropped samples and measured
probe body costs are explicit.

The `first-visits` scenario starts from the normal initial Activity page. It
verifies each requested route was absent from the live cache and waits using
the native event loop, with no frame pump or prior warming. It then revisits
the same routes, checking retained loader/page identity. The historical
`routes`, `resize` and `mixed` scenarios retain their documented setup-only
warming protocol so old evidence is not silently redefined.

`SWIRL_ROUTE_BENCH_MATERIAL=glass` explicitly enables transparency and checks
the first sidebar shader is Compiled, its source is sampled and live, and the
renderer is native. `opaque` remains a separate control. No environment flags
disable VSync or change the product frame cadence in the principal comparison.
Any diagnostic override must be recorded and compared only with matching runs.

`tools/Analyze-ApecPerformance.py` records the source report's SHA-256 and
preserves whole-run statistics. Additional interval groups use direct
`pageTravel.running` / `pageCommit.running` / pending-state notification
events, including overlap durations and the events inside each long interval.
It never removes a gap because the endpoints look inactive. The explicit
boundary group retains intervals crossing animation, commit or setup phases.

These timestamps are elapsed CPU-stage brackets. They include scheduling and
observer effects and do not measure GPU execution, display presentation or
input-to-photon latency. A reported 240 Hz screen is not a physical refresh
acceptance. The original unfiltered result remains alongside every subdivision.

API semantics were checked against Qt's primary documentation:
[QQuickWindow render signals](https://doc.qt.io/qt-6/qquickwindow.html) and
[QQmlIncubationController](https://doc.qt.io/qt-6/qqmlincubationcontroller.html).
In particular, `afterRendering` occurs after command recording and before
queue submission; `frameSwapped` records presentation queue cadence.

## Shared interaction completion

Reference checkboxes and native window-caption buttons now use independently
owned presentation animations, which stop at the correct final state when
reduced motion or visibility changes during a running transition. Checkmark
reveal, contact feedback and colour interpolation remain. Arc and interaction
controllers also settle when their own window is hidden or minimized.

The unsaved-change confirmation uses the same curved popup presentation and
Qt transition finalizer as other dialogs. The complete popup surface moves
together. Parent dialog closure leaves focus restoration to the existing
generation-fenced dismissal controller instead of separately forcing an old
focus target over a newer popup. The public `returnFocus` snapshot remains.

Native checks cover checkbox/caption interruption, hidden controls, window
minimization, confirmation enter/exit interruption, cancellation back to the
editor, discarding both modal layers and a new popup retaining focus while an
older dialog finishes closing. Results are pending integration execution;
building these assertions is not a pass.

The default Activity-to-Settings font stress failure is tracked separately.
A direct Settings-start pass must not be substituted for that cold route.
Font axes, asynchronous loading and initialization fences remain intact.

## Integration checkpoint, 2026-10-27

The expanded 58-check motion suite now passes locally, including same-turn
reversal, preparation interrupted by a cold route, nested discard confirmation,
and focus retained by a newer popup while an older popup finishes closing.
The fixes retain the existing caches, asynchronous incubation and animations.
Native navigation and the updated floating-surface appearance checks pass.

The recorded Hero run passed all 102 behavioral assertions and its nested
navigation assertions, but exited unsuccessfully because a font binding emitted
QML lifecycle warnings. The subsequent binding change retains its completion
fence, binds its lexical component context and guards detached Window access;
Hero needs rerunning against that change.

The original synthetic-font cold Activity-to-Settings stress was rerun after
the new settings and binding changes: zero FreeType creation warnings, and the
unchanged memory-plateau and finite-coordinate memory checks passed. The overall
font run still failed two license-popup lookup/inheritance checks; these remain
under investigation. No private user font was used. This checkpoint is not final
font, performance, CI or installer acceptance.

CI `40396167707` built the full MSVC source and passed 30 of 32 CTests. The old
appearance assertions required V2 identical canvas/sidebar pixels; the new
checks verify Swirl 3's separate tokens and stopped fallback capture. The three
Hero screenshot differences were exactly 877 pixels in the close-button tooltip
area, outside page content. The pointer now parks in the blank outer gutter;
the original pixel threshold remains unchanged. Resource checks await actual
retirement rather than assuming a fixed 150 ms delay is sufficient.

## Final integration evidence, 2026-10-28

This section supersedes the pending results in the historical checkpoint above.
The cold Activity-to-Settings run with the original synthetic automation font
passed all 37 assertions with zero FreeType engine creation warnings. The two
license assertions now locate the dialog through its cached font-pane owner,
matching the actual QObject ownership. The native Hero run passed all 102
assertions and its nested navigation checks, with no QML lifecycle warnings.
The expanded 58 motion checks and native appearance/navigation checks pass.
GitHub run `40510223760` passed the complete CI pipeline for integration commit
`4a6987d008a69ffed4f45f8beb3a733c5ee94e59`; final 3.0.0 package validation belongs
to the subsequent versioned commit and must be checked independently.

Native D3D11 measurements used Qt 6.12.0, DPR 1.5, the reported 240 Hz display,
live sampled glass and normal VSync settings. All three isolated scenarios
exited successfully, retained cached page identities and reported no warnings.

| Measurement | p95 (ms) | p99 (ms) | Maximum (ms) |
| --- | ---: | ---: | ---: |
| First-visits run, all intervals including setup and commit | 4.62 | 27.18 | 47.05 |
| Route run, all intervals including instrumented prewarming | 21.98 | 32.04 | 39.86 |
| Resize run, all intervals including setup | 22.71 | 32.15 | 145.77 |
| First visits, intervals wholly within travel events | 4.41 | 4.66 | 8.03 |
| Warm visits, intervals wholly within travel events | 4.47 | 4.78 | 5.58 |
| Rapid retargeting, intervals wholly within travel events | 5.09 | 5.58 | 5.96 |
| Settled route changes, intervals wholly within travel events | 4.39 | 4.76 | 5.58 |
| Resize measurement phase, all intervals | 21.64 | 25.12 | 25.12 |

The setup-only 145.77 ms gap and all original intervals remain in the evidence;
the separated rows are not substitutes for whole-run results. These are Qt
frame delivery observations, not physical presentation FPS or proof of universal
60/120/240 Hz smoothness. Resize cadence remains a stated limitation. No effect,
animation, asynchronous loader, font axis, or cache was removed for these results.

The full screenshot pass saved 340 real app-window captures across light/dark,
normal/compact windows, all page implementations, settings sections and editors.
Its initial eight harness errors were navigation aliases `dashboard` and
`requestlogs`, whose actual independent window and overlay were already captured.
The harness now models those surfaces explicitly and respects the 672-DIP minimum
height. Visual inspection also led to a narrow empty-state placement correction
in the two request inspectors. The versioned 3.0.0 screenshot verification then
completed with 340 saved captures, 61 main-route targets, both themes, 800/1100-DIP
widths, and zero capture errors or QML warnings. The two corrected compact
inspectors were visually checked again. Manual DPI and physical-display
acceptance remain with the user.
