# 0.2.17 — global interaction and Windows icon follow-up

The final follow-up advances the original 0.2.16 request to 0.2.17. Activity's
policy arrow aligns with the whole two-line selector rather than its caption;
the text column keeps bounded elision and the existing motion continues.
The centered arrow retains fractional coordinates at mixed DPI. Segmented
hover paint also stops reading its owner after page teardown. The Windows CI
test runtime explicitly includes its offscreen plugin, and independent TLS
fixtures serve their complete generated chain with one explicit test CA;
production certificate verification and every rejection gate remain intact.

Continues `f895801` on `work/swirl-0216-interaction-icon-20261028`. The current
request preserves the neutral theme, APEC background, floating
sidebar, page structure and Rust runtime behavior.

## Current repair

Shared buttons reserve 16 DIP horizontal padding and enough intrinsic height
for the label. Activity gives the policy selector a larger width allocation,
bounded plain-text elision and a complete-name tooltip. Section actions keep
their caption alignment while gaining a larger padded hit target. DNS title
verification checks the actual settled title opacity and semantic foreground,
including the existing shared-title handoff repair.

The existing interaction system supplies a 70 ms press ingress, spring release,
110 ms hover, 150 ms focus and a one-DIP lift with soft surface tint.
Labels and icons follow the surface scale. Navigation, combo/menu items,
segmented choices, switches, radio/checkbox controls, subscription dialogs and
table rows use these shared states. Disabled navigation cannot retain hover
color, and pooled rows finish old interaction state before reuse.
The root content clip confines antialiased and animated dirty regions to the
native window. The software-backend failure previously passed a negative/outside
dirty rectangle to `UpdateLayeredWindowIndirect`; the outer native shadow keeps
its separate window and every feather/glass effect remains enabled.
Nonvisual popup-motion helpers use explicit typed ownership properties, matching
the dialog contract. This avoids a production compiled-QML default-`data`
warning; the staged 61-page smoke must remain free of Qt/QML warnings.

Windows uses `assets/icons/swirl_windows.svg`, preserving every original path
and the original horizontally open cloud-knot proportions. The final requested
line weight uses the canonical filled ribbon contours with no added stroke.
Native rasterization removes transparent artboard margins without stretching
or reshaping any curl. The
application-scene logo remains canonical SVG. Buttons use filled hover/focus
feedback, with no added normal-state interaction or focus outlines.
All 18 native sizes are rendered by the same rasterizer for runtime QIcon and
EXE ICO resources. The RC object explicitly depends on its generated ICO;
previous target ordering alone allowed an old resource object to survive a
regenerated icon. `tools/Verify-WindowsIconResources.py` rejects any frame or
EXE resource mismatch before package staging writes its manifest.
The versioned ICO follows the target EXE directory, including MSVC's Release
subdirectory, and the CI preview runtime carries the same verified file.
Taskbar properties are published only for the native Windows platform, which
has a real HWND; offscreen renderers retain their strict warning checks.

The window publishes its explicit AppID and relaunch resources before first
show. `Swirl-brand-0217-canonical.ico` gives the shell a distinct resource path.
The installer repairs only existing Swirl shortcuts targeting that installation
and notifies the shell. During investigation, correct native HICONs coexisted
with the old taskbar group image. Item-only notifications retained that bitmap;
after a verified owned shortcut save, `SHCNE_ASSOCCHANGED` invalidates the shell
icon cache. Its completed notification followed by application relaunch was
verified against actual taskbar pixels. No taskbar
height, network setting, global icon-cache deletion or Explorer restart is part
of this repair.

## Verification contract

`swirl-appearance-ui` exercises rendered shared controls, short presses, release
motion, keyboard focus and disabled states. `swirl-navigation-ui` additionally
drives 17 actual page controls with canceled releases and saves per-state crops;
it asserts no command was invoked, then checks rapid hover reversal and page
switching. A geometry-only process row enables its real detail action without
claiming captured traffic. Empty-source update-all is tested as disabled.

Focused startup, node, engine, overview, motion and native GPU-glass checks are
retained alongside configuration, catalog, import and network-security gates.
Physical taskbar captures at each Windows scale must be recorded separately
from controlled Qt DPR renders. Failed attempts, fixture dependency failures
and independent-peer skips remain in the delivery evidence. Final source SHA,
installer hash and actual acceptance results belong to the accompanying
verification report, not to this implementation description.

Primary platform references:
[Qt application icons](https://doc.qt.io/qt-6.12/appicon.html),
[Microsoft AppUserModelID](https://learn.microsoft.com/en-us/windows/win32/properties/props-system-appusermodel-id),
and [taskbar relaunch icons](https://learn.microsoft.com/en-us/windows/win32/properties/props-system-appusermodel-relaunchiconresource),
plus [shell icon-cache notifications](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shchangenotify).

# Previous Activity and glass refinement

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

## Earlier native icon investigation and limit

This earlier record predates the optical ribbon-weight and shell-cache repairs
described above. Its no-increase statement is historical, not the current
acceptance result. The final installer and physical-DPI evidence are recorded
separately.

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
