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
