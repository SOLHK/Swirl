# APEC flat wing V2 — 0.2.15

Independent branch `work/swirl-apec-flat-v2-20261028`, based on
`80509bd9f73980acf23ce2959c138e5b23ceff7d`.

## Final visual contract

The user's annotated screenshot specifies **one visible right-facing half-wing**:
a large diagonal fan entering from beyond the lower-left edge and opening toward
the upper right. There is no mirrored left wing or centered pair. APEC informs
color and abstract flow; these curves are independently drawn for Swirl.
This latest composition supersedes the earlier centered 85%-width paired-wing
proposal. The upper feathers reach above the window midpoint and continue behind
the existing cards; the cards completely occlude them.

The user explicitly confirmed retaining the actual 80509bd homepage and **20 DIP
sidebar radius**. The sidebar's 12 DIP inset, 208/76 DIP widths, collapse/navigation
logic, blur, refraction, local rim response and shadow are unchanged. Window
contour remains 22 DIP. Actual Activity geometry and business expressions are
unchanged; text over the artwork uses a darker neutral role for contrast.
No Rust, network, node, subscription or policy implementation is modified.

## Palette

The existing Theme.qml singleton owns all runtime colors.

| Role | Light token |
| --- | --- |
| Canvas | #F3F3F5 |
| Secondary / fields | #F0F0F2 |
| Cards | #F8F8FA |
| Border | #E3E3E7 |
| Primary text | #202027 |
| Secondary text | #71717A |
| Text over artwork | #393941 |
| APEC action blue | #171D87 |
| Wing | #FFB264 → #FF554D → #F40050 → #00BDE1 → #36CBB0 → #A3E65D |

One continuous translucent window base is retained. Sidebar sampling sees only
the independent wing source, never page text. The existing workspace-wing shader
masks the direct copy inside the glass contour to avoid double compositing. Its
source texture now uses the actual device-pixel ratio, preserving sharp edges.
Dark mode retains its existing base palette. High contrast or transparency-off
retains the previous decoration suppression behavior.

## Vector and placement

The canonical resource is SwirlWorkspaceBackdrop.qml: one CurveRenderer Shape,
one winding-filled ShapePath, five closed cubic SVG feather paths and a continuous
gradient. There is no volumetric lighting, folding/highlight layer, wing shadow,
particle system or raster artwork. A matching SVG export accompanies delivery.

Artboard: 1600×1000. For a window W×H, uniform footprint width is
max(1.08 W, 1.52 H), height is 0.625 of width. Its right edge is 20 DIP inside the
window; its bottom extends 40 DIP below the window. The native window crops the
root rather than squeezing the wing. At 914×672 DIP this gives a 1021.44×638.4 DIP
footprint, x=-127.44, y=73.6. The outer tip is approximately (874.8, 86.4) DIP.
Only the uncovered background is visible; opaque content cards stay in front.

## Opening animation

Each application window consumes its opening once when Activity is first shown.
The wing fades in over 620 ms and unfolds through uniform 0.92→1 scale,
4→0 degree rotation and 14→0 DIP vertical travel over 900 ms, all OutCubic.
These are render-thread Animator properties; paths do not rebuild each frame.
No repeated idle motion, navigation replay, theme-change replay or restore replay.
Hiding the page/minimizing stops motion; reduced motion settles immediately.
The consumed state belongs to this application window, not persistent settings,
so the next application launch has a fresh opening.

Implementation reference: [Qt Shape](https://doc.qt.io/qt-6/qml-qtquick-shapes-shape.html).

## Validation

Qt 6.12.0 / GCC 15.1.0 local build passed. Native appearance and 61-page smoke
passed. The revised motion and D3D11 glass checks validate single-wing geometry,
actual status/transfer card pixel equality with the wing on/off, advancing native
opening frames, static resting pixels, and no replay after returning.

A first motion-fixture run had zero assertion failures but correctly failed on
QML warnings: the standalone fixture lacked its targetWindow during construction.
It now supplies the real window through createWithInitialProperties, matching the
production call site. Assertions and warning enforcement remain enabled.
Earlier offscreen smoke timeouts were missing qoffscreen.dll in the local test
runtime; the matching SDK plugin fixed deployment without changing the 60s limit.

The delivery report supplies source-bound CI, installer, five controlled DPR
renders and performance evidence. Controlled scaling is not physical multi-monitor
DPI acceptance; frame fixtures do not establish sustained 60/120 Hz. Historical
extreme variable-font FreeType warnings remain outside this visual change.
