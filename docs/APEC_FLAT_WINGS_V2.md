# APEC flat wings V2 — 0.2.15

Based on `80509bd9f73980acf23ce2959c138e5b23ceff7d`, on the independent
`work/swirl-apec-flat-v2-20261028` branch. The user supplied the APEC CHINA 2026
reference image and selected the bottom horizontal composition.

## Scope and baseline discrepancy

The actual 80509bd homepage contains the status area, transfer card, diagnostics,
traffic sources and active connections. Those QML layouts and all their actions
retain their geometry and behavior; only text colors over the artwork change. The brief describes an older INTERNET/traffic
layout; restoring it would be a separate structural change. The baseline sidebar
radius is 20 DIP and is preserved, as explicitly confirmed by the user after the
baseline check. Its 12 DIP inset,
208/76 DIP expanded/collapsed widths, navigation and glass shader are unchanged.
The window's 22 DIP contour remains unchanged.

No Rust, network, subscription, node or policy implementation is modified.
The existing transparency-off/high-contrast behavior suppresses decoration.

## Palette

All runtime colors are in the existing `Theme.qml` singleton.

| Role | Light token |
| --- | --- |
| Canvas | #F3F3F5 |
| Secondary/fields | #F0F0F2 |
| Cards | #F8F8FA |
| Border | #E3E3E7 |
| Primary text | #202027 |
| Secondary text | #71717A |
| Text over artwork | #393941 |
| APEC action blue | #171D87 |
| Warm wing | #FFB264 → #FF954B → #FF554D → #F40050 |
| Cool wing | #00BDE1 → #36CBB0 → #A3E65D |

The translucent window still owns the background once. Sidebar sampling,
refraction, blur, local rim response and shadow remain intact. No opaque overlay
is placed over the glass. Dark mode retains its existing base palette.

## Vector and motion

`SwirlWorkspaceBackdrop.qml` is the vector source: one CurveRenderer Shape, two
ShapePaths containing closed cubic SVG paths and continuous shared gradients.
The long, branching sweeps and intersecting central streams are an original Swirl
composition; the supplied logo informs color and lightness rather than its silhouette.
The visible tips extend above the window midpoint. It has no texture artwork, lighting, folds, highlights, shadows or particles.
Light wing opacity is 72%, dark 56%, with a gradual reduction toward the tips. Text over artwork uses the darker contrast token.
An SVG export is supplied with the delivery for reuse; the QML remains canonical.

The footprint width is 85% of the current main content width, with height 76%
of wing width (1200:912 artboard), centered in that area and 12 DIP above the
window bottom. At 914×672 with the expanded 208-DIP sidebar this is 600.1×456.076
DIP, or 67.87% of window height. Only uniform scaling is used. Cards are above
the decoration, and it adds no input handler or focus target.

Entry fades for 620 ms and unfolds through uniform 0.955→1 scale plus 8→0 DIP
translation for 760 ms, all OutCubic and render-thread Animator properties.
Paths are fixed during animation. Idle is completely static. Leaving Activity,
minimizing, disabling transparency or enabling high contrast stops the animation;
reduced motion settles immediately. Existing global motion speed is respected.

Implementation references: [Qt Shape](https://doc.qt.io/qt-6/qml-qtquick-shapes-shape.html),
[Qt Shapes example](https://code.qt.io/cgit/qt/qtdeclarative.git/tree/examples/quick/shapes).
Only API/design principles are reused; the wing curves were authored for this brief.

## Validation boundary

The delivery report records actual build, tests, native D3D11 captures and
100/125/150/175/200% controlled DPR renders. Controlled scaling does not establish
physical multi-monitor migration or 60/120 Hz display performance. Full regression
and the independent production MSVC installer are tied to the final Git SHA.
Historical extreme variable-font stress warnings remain outside this visual fix.

Local Qt 6.12.0 / MinGW GCC 15.1 validation: appearance and native navigation
passed; after the final enlarged artwork, 61-page smoke (13.30 s), APEC motion
(15.68 s) and native D3D11 glass/geometry (2.90 s) passed. Original offscreen smoke
attempts timed out before application diagnostics because windeployqt's default
native-only deployment lacked qoffscreen.dll. The test runtime was repaired with
the matching SDK plugin; the timeout limit and assertions were not changed.
The exact neutral canvas replaced an obsolete >245-white assertion with equality
to Theme.canvas, retaining the full-opacity check. Five DPR captures have verified
914/1143/1371/1600/1828-pixel widths for the same 914-DIP window.

The final CI and package receipt are delivered separately; a local test result
is not a claim of CI success or private-provider/TUN acceptance.
