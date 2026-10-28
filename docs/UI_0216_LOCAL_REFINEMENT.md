# 0.2.16 — Activity and glass refinement

Continues `work/swirl-apec-flat-v2-20261028` from
`ef397457d187160709ae139fb49cc15c66569ca4`. The patch version distinguishes the
new installer from the user's 0.2.15 screenshots. No main-branch or runtime
protocol changes are included.

## UI contract

- Three existing top entry points retain their positions. Subtle neutral
  capsule gradients and one physical pixel rims distinguish resting, hover,
  press and keyboard focus. Green is reserved for the reported enabled state.
  The system-proxy label distinguishes Swirl ownership, an external proxy,
  a running core without ownership, pending transitions and off. TUN reports
  the actual `tunEnabled` flag; its tooltip states current Rust support limits.
- `assets/icons/swirl-wing.svg` is the single small-wing master, used through
  `SwirlFlow` by the proxy capsule, status and diagnostics, and other existing
  flow consumers. Four closed feather contours replace the two procedural
  curves. Existing pending, one-shot success and reduced-motion timing remains.
- The status and left-column cards share the neutral `Theme.surface`, 14 DIP
  corners and existing analytic shadow. Flow sources occupy the primary upper
  card; transfer retains rates, totals, period/category filters and a compact
  daily trend below. The right diagnostic and connection rails keep their order.
- Sources retain eight ranked entries in a bounded scrolling viewport. Labels
  elide; hover/keyboard focus exposes the complete name and traffic in a bounded
  tooltip. Known policy/node IDs resolve to display names without changing the
  raw ID used by detail navigation.
- The floating sidebar retains its existing inset, dimensions, interaction,
  sampled source, blur, edge refraction, local light and shadow. The current
  request explicitly sets its contour to 14 DIP, superseding the previous 20.
  The wing crosses its lower region visibly: the initial overly faint/downward
  treatment was rejected by the user and is not the final material. Light-mode
  wing opacity is 0.52; the footprint ends 8 DIP below the window. The glass
  retains 66% chroma and lightly lifts transmitted color while preserving alpha.
  It adds no opaque cover. Native pixel tests require visible colored feather
  coverage through the lower sidebar at three window sizes, in addition to live
  sampling, blur, refraction, alpha and local-light checks.

## Native icon investigation and limit

The existing raster path already removes SVG artboard padding and fits the
original knot proportionally to the entire square icon width. On this 150%
desktop, `WM_GETICON` returned 24×24 small and 48×48 large frames for both Swirl
and ChatGPT. Swirl's nontransparent large-frame bounds were (0,5)–(48,43): full
width, 38-pixel height. The wide original silhouette, rather than a missing
large HICON or an extra horizontal inset, accounts for its shorter appearance.

Increasing it further within Windows' square slot would crop the side curls;
making it equally tall would require changing its proportions. Neither is done.
This update adds exact 28/42/56-pixel frames for 175% title/taskbar rendering and
regenerates the tracked ICO. Runtime and resource icon paths share all 18 frames.
It does **not** claim an additional 150% size increase or equal perceived area
with ChatGPT. Physical multi-monitor DPI switching remains separate acceptance.

## Validation scope

Required local gates: incremental Qt 6.12/GCC 15 build; appearance, all-page
startup, Activity input/motion, APEC motion/glass, node input and navigation;
portable-core dependency guard; SVG consistency; native 100–200% controlled
scaling and ICO frame inspection. System-setting mutation is confined to the
existing disposable CI tests. Local proxy-button tests inject an isolated
controller and verify the host proxy snapshot is unchanged.

The first APEC motion run failed `caption-hover-animates` and
`menu-interrupt-reopen`; an isolated rerun of the unchanged test passed. Keep
that failure in delivery evidence; timing assertions were not removed or relaxed.
Final CI, installer SHA and package/runtime identity belong to the delivery
report, not to inferred success from this design record.

Primary implementation references reviewed:
[Qt Quick Effect Maker](https://github.com/qt/qtquickeffectmaker),
[QIcon](https://doc.qt.io/qt-6/qicon.html), and
[Qt Windows icon loading](https://github.com/qt/qtbase/blob/6.12/src/plugins/platforms/windows/qwindowswindow.cpp).
Existing Qt rendering infrastructure is reused; no third-party visual code is copied.
