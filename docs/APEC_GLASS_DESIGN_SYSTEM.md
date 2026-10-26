# Floating navigation material and shared design tokens

This stage follows the verified interaction foundation in
`APEC_MOTION_FOUNDATION.md`. It applies the independent Swirl visual language
to the shell, navigation and shared semantic colours. Individual page layouts
remain the separate full-page migration stage.

## Material and scene ownership

`Main.qml` owns a `SwirlWorkspaceBackdrop` sibling behind the sidebar. The
sidebar's `SwirlLiquidGlass` samples only this application scene. It never
contains its own capture, and never captures foreground navigation labels.
The quiet curves in this backdrop are stationary; network activity remains
state-driven in the separate `SwirlFlow` components.

The capture is padded by 16 logical pixels and constrained to the navigation
envelope. A horizontal 9-tap Gaussian prepares one small texture; the final
vertical 9-tap pass combines blur, a maximum few-pixel edge refraction, tint
and directional rim response. Safe texture coordinates are clamped to texel
centres. Closely spaced weighted taps replaced the first prototype's visibly
stepped blur at a hard source-colour boundary.

The surface follows the existing 2.5-power contour. Its brighter upper/left
reflection and restrained opposite reflection are directional, not a uniform
white outline. Hover, contact, keyboard focus and the navigation trajectory
drive the material response; there is no idle glint timer.

The capture width remains the maximum expanded navigation envelope during
collapse/expand, avoiding a new width allocation on every animation frame.
Resolution is bounded by the panel and `min(1, DPR × 0.6)`. Source captures stop
updating while hidden or minimized. Disabling transparency or requesting
increased contrast unbinds the sample and draws the explicit opaque fallback.
The software scenegraph uses that same fallback and cannot accept the shader.

This is **application-background glass**, not desktop sampling. The existing
Windows backdrop/shadow adapter independently owns DWM material and native HWND
composition. The QML material does not claim to read or blur windows behind
Swirl. Native shadow caching, input transparency and ownership remain intact.

## Shared visual contract

The floating navigation material is 184 logical pixels wide inside a 208-pixel
shell allocation (12-pixel inset on both sides); collapsed allocation is 76.
Rows remain 40 high, with a 12-pixel row radius. Window and navigation contour
extents are independently 22 and 20. Their native tests now assert those new
explicit values while retaining geometry, fractional alpha, outside-corner
pixels, resizing, maximization and cached-shadow checks. The user explicitly
removed the former fixed 14-pixel restriction.

Light canvas is `#FBFCFD`, surface white, main text `#14283F`, supporting text
`#53667A`, and interaction accent `#007EAA`. Dark uses `#101D2D`, `#182A40`,
`#EDF5FC`, `#B4C7D9`, and `#55C8E6`. Controls, fields, selections, tables and
capsules share these semantic families instead of mixing the old neutral-grey
and blue palette. Brand orange/red/blue/cyan/green remain separate named tokens.
Error/success labels retain their independent semantic colours.

Nominal foreground contrast ratios (solid token surfaces, not a claim about
every material/background): light main text/canvas 14.55:1; light supporting
text/white 5.92:1; white/primary cyan 4.60:1; dark main text/surface 13.20:1;
dark supporting text/surface 8.39:1; navy/dark-mode primary cyan 8.73:1.

The existing font manager, variable axes and async startup fencing are retained.
Shared type roles are 12 supporting, 14 body, 18 section and 26 page title;
page-level migration must adopt the roles while preserving meaningful density.
The navigation mark is the SVG brand asset; no PNG has replaced it.

## Verification method and Qt status caveat

`SWIRL_APEC_GLASS_CHECKS=1` uses the real D3D11 application and `grabToImage`
readback. It changes a controlled scene's source colour, checks blurred edge
mixtures, compares refraction and interaction-rim pixels, inspects rounded alpha,
tests opaque fallback pixels, and verifies bounded/hidden captures. This is
separate from a software scenegraph smoke pass and from the desktop DWM tests.

Qt 6.12's shader-status handling needs a precise test: the first application
instance goes through `prepareShaderCode` and reports Compiled. A later instance
of the same QSB can hit the global `shaderInfoCache` in
`QQuickShaderEffectPrivate::updateShader`. That path copies the valid reflected
shader without calling `prepareShaderCode`, leaving its new manager status at
the default Uncompiled even though native pixel output is correct. The test
therefore strictly checks the actual first sidebar shader's Compiled status,
then requires the fixture to have no Error and pass every pixel assertion.
It does not label an unrendered shader as accepted.

Sources actually inspected:
[Qt ShaderEffect](https://doc.qt.io/qt-6/qml-qtquick-shadereffect.html),
[Qt ShaderEffectSource](https://doc.qt.io/qt-6/qml-qtquick-shadereffectsource.html),
[Qt 6.12 shader cache implementation](https://github.com/qt/qtdeclarative/blob/6.12/src/quick/items/qquickshadereffect.cpp), and
[Qt RHI shader manager](https://github.com/qt/qtdeclarative/blob/6.12/src/quick/scenegraph/qsgrhishadereffectnode.cpp).
The material implementation is original; the existing Swirl Gaussian shader helper is
reused inside this bounded pipeline. No downloaded shader, web CSS or third-party
visual asset has been copied into the product.

Physical 60/120 Hz, all Windows DPI values, full-page visual acceptance and
private-provider networking remain separate acceptance work. The foundation's
observed long frames are retained for the later integrated performance stage.

## Local verification, 2026-10-27

The independent Qt 6.12.0 / GCC 15.1.0 build completed. Native validation used
D3D11 at the host's reported DPR 1.5:

| Check | Actual result |
| --- | --- |
| Glass shader and pixel fixture | 17/17 passed, including first-instance Compiled, source response, Gaussian edge mixing, refraction, rim, alpha and opaque pixels |
| APEC motion and keyboard fixture | 38/38 passed, including Ctrl+K/Escape retaining the underlying route |
| Standard input regression | 66/66 passed |
| Navigation regression | Passed |
| Existing motion regression | Passed, including idle-loop and released-grab assertions |
| All-route startup | Three consecutive 61-route runs passed with no QML warnings |
| Native window radius/shadow | Passed: 22/20 contract, actual outside-corner pixels, fractional alpha, cached movement, maximize/restore and input transparency |
| Portable Rust dependency boundary | 7/7 passed; no Rust source changed |

The native window test also exercised the existing desktop-material adapter on
its controlled background: the desktop colour change produced delta 18 and did
not steal foreground activation. This is separate evidence from application
scene sampling; it does not mean the sidebar shader reads desktop pixels.

Earlier failed runs remain in `work/build-motion/evidence-20261027-033950/`:
the About test's global `brandVector` lookup hit the new small sidebar SVG; its
lookup now starts at the actual settings page and retains the >=104 size check.
The first rapid startup run loaded 61 routes but emitted QObject member-data
and font-callback warnings. Font implementation and async loading were retained.
New popup controllers/transform bindings now gate activation on component
completion, and all QML AOT outputs were regenerated without deleting the Rust,
Ninja or SDK caches. The subsequent three native runs were clean. This combined
verification does not isolate which earlier generated-state/timing condition
caused each original warning.

Successful local evidence: `work/build-motion/glass-native/`,
`work/build-motion/evidence-20261027-035202/`, and the registered native CTest
`swirl-apec-glass` (passed). Navigation, motion and native contour reports are
also retained in the earlier directory above because those suites passed there.
The measured motion run reported whole-run p95 6.74 ms, p99 63.00 ms and eight
frames above 50 ms, with warm p95 5.72 ms and 761,856 bytes of revisit growth.
These diagnostics are not a physical-refresh performance acceptance.
