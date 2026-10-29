# APEC-inspired motion foundation

This is Swirl's independently implemented motion language. It is not an APEC
motion specification. The component work precedes the visual sidebar/material
redesign and the later migration of every page.

## Shared presentation contracts

- `SwirlArcMotion` owns only presentation coordinates. Navigation hit targets
  stay in their final layout. Its cubic Hermite trajectory snapshots numeric
  position and velocity before retargeting; a perpendicular lobe has zero
  endpoint derivative. Carry velocity is bounded for near-coincident targets.
- `SwirlPageHost` retains live cached loaders, asynchronous incubation, source
  and target surfaces, and generation fences. Ordinary routes use small curved
  offsets; shared settings transitions keep their existing geometry ownership.
  Interruption snapshots the currently rendered offsets before starting again.
- `SwirlInteractionMotion` separates hovered/pressed/focused inputs from light
  and contact presentation. Its animations are independent root animations,
  which can actually be stopped when hidden or when Reduce Motion changes.
- `SwirlPopupMotion` is a nonvisual QObject. Making it an Item would insert an
  extra entry into a Menu's visual content model. It carries the invoking
  direction through a short curved path. Dialog presentation transforms the
  entire popup item, including header, content, background and footer.
- `SwirlFlow.phase` consumes `idle`, `pending`, `succeeded`, or `failed` from
  real operation state. Pending animates only while visible; success is a
  single bounded sweep; idle/failure settle. It does not invent progress or
  report successful connection from a click. The proxy capsule requires owned
  and enabled system proxy plus a live core for its success state.
- The small flow shader measures polyline arc length along two cubic paths.
  Unequal colour stops and a phase-shifted second ribbon follow that distance,
  rather than translating a rectangular gradient. Do not enlarge this shader
  to a full-window background without separately profiling the fragment cost.

## Qt 6.12 interruption adapter

Actual Qt 6.12 tests showed that setting `Transition.enabled` or
`Behavior.enabled` false does not stop an existing job. Calling `complete()`
on an animation owned by a Transition/Behavior also did not retire that job.

`app/PopupMotionBridge.cpp` is a narrow UI-layer adapter around Qt Quick
Templates' transition manager. It cancels the owned job and invokes Qt's
normal enter/exit finalizer, retaining overlay removal, focus and closed/opened
signals. A QPointer and transition-state recheck protect cancellation callbacks.
The rest of the application must not include those private headers. This bridge
depends on the tested Qt **6.12.0** SDK, and must be rebuilt/retested for each Qt
upgrade; it is not a stable public ABI or a Windows/Rust dependency.

Qt 6.12's Menu override has an additional `visible == requested` guard that
rejects a reopen during its still-visible exit. `SwirlContextMenu.showAt()`
uses the base Popup reversal only for an item popup already exiting, then
preserves the current reveal. Use this entry point for real context actions.
Normal open still uses Qt's menu positioning. A deferred focus restoration
generation fence prevents an old dismissal from stealing a newer popup's focus.

Sources inspected: [Qt Popup implementation](https://github.com/qt/qtdeclarative/blob/6.12/src/quicktemplates/qquickpopup.cpp),
[Qt Menu implementation](https://github.com/qt/qtdeclarative/blob/6.12/src/quicktemplates/qquickmenu.cpp),
[ShaderEffect](https://doc.qt.io/qt-6/qml-qtquick-shadereffect.html), and
[ShaderEffectSource](https://doc.qt.io/qt-6/qml-qtquick-shadereffectsource.html).
Implementation is original; Qt remains the existing distribution dependency.

## Page migration entry points

Keep the page host and business controller as the owners of route and operation
state. Use `SwirlMotion.noteTrigger(control)` for invoking origins (shared
buttons already do so), `SwirlDialog` for guarded forms, `SwirlContextMenu.showAt`
for context menus, and `SwirlComboBox` for native keyboard-owned choice. Bind
`SwirlFlow.phase` to verified operation state; never drive it from local timers.
Use `SwirlArcMotion` for another single-owner selection indicator and
`SwirlTransitionCoordinator` for reversible bounded expansions. Build and verify
each page's interaction before applying its new layout and visual tokens.

The `SWIRL_APEC_MOTION_CHECKS=1` application fixture, also registered as CTest
`swirl-apec-motion`, exercises the real application components, repeated
retargets, native keyboard/mouse input, midflight reduced motion, popup
lifecycle, sidebar width reversal and registry retirement. It is a controlled
UI test, not physical 60/120 Hz, all-DPI, private-network or end-user acceptance.

## Foundation verification, before visual migration

The independent Qt 6.12.0/GCC 15.1 application build passed on 2026-10-27.
The dedicated native D3D11 fixture passed **36 checks**, followed by the existing
mouse/keyboard interaction suite, navigation suite, motion suite and **61-route**
startup smoke, all with exit code 0. The portable Rust dependency boundary
guard passed 7 tests; no Rust implementation or host network setting changed.

Local evidence is under `work/build-motion/foundation-native9.json` and
`work/build-motion/evidence-20261027-031659/`. Earlier failing fixture runs are
retained there: they exposed a Qt final-property name collision, numeric value
snapshot semantics, in-flight reduced-motion handling, menu QObject ownership,
ComboBox focus ownership and the Qt Menu reopen guard. Assertions were retained
and the final run exercises actual opened/closed state, not merely opacity.

The existing motion probe observed a 240 Hz-reported screen at DPR 1.5. Its
whole-run p99 was 63.17 ms with 8 frames over 50 ms; this is not a high-refresh
performance pass. It is retained as diagnostic data for the later integrated
performance stage. These results do not accept the subsequent glass shader or
the not-yet-migrated pages.
