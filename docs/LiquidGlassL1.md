# Swirl Liquid Glass L1 implementation and manual acceptance

Baseline: remote `work/activity-page-v7-20261023`, `a47209420fe237b2970c2edb4194df318fc6d856`.
Development branch: `work/ui-liquid-glass-unification-20261023`.

## Material ownership

- `Theme.qml`: shared light/dark content colors, glass tint, separator and accessibility tokens. Existing `SwirlMotion.qml` remains the motion-token singleton.
- `SwirlGlassPanel`: ordinary opaque content material; one background-only analytic shadow. Activity retains two 276 DIP cards and three unboxed lower sections.
- `SwirlClearGlassSurface`: retained public component name; regular, legible navigation/control material, with optional elevation. It does not implement Apple's native optical refraction or a per-control backdrop blur.
- `SwirlSidebar`: one glass surface with its own broad, offset shadow and tint, so the large navigation plane remains visibly elevated on a light canvas. Selection is an ordinary overlay, not another glass panel.
- Buttons, icon buttons, status capsules, segmented controls, combo boxes and dialogs share the material. Content tables and charts stay ordinary surfaces.
- `SwirlWindowControls`: right-aligned Windows-style minimize, maximize/restore and close controls using QWindow operations. This is a Qt-drawn caption, not an OS-drawn caption; Windows Snap Layout hover is not implemented. Native move/resize and the system menu remain in the existing Windows adapter.

## Edge audit: evidence versus hypotheses

1. The previous shared clear surface painted a permanent one-DIP border on every sidebar, capsule and card. At DPR 1.5 this can cover more than one physical pixel. Remove the decorative rim; retain a physical-pixel focus/high-contrast edge.
2. Activity nested that surface inside each `SwirlGlassPanel`. Remove the nested material and give the panel ownership of its ordinary opaque fill/shadow.
3. The previous Canvas shadow erased its center using an expanded `destination-out` rounded path. The independent inset/antialiasing contours could leave a visible halo/gap. Replace the entire Canvas construction with Qt `RectangularShadow`, sharing the surface radius. This removes the suspected sampling mechanism; it does not prove every historical screenshot line had that cause.
4. The clear segmented control put an outlined selection directly on the outer contour. Inset the selector by two DIP and remove its decorative border; round segment endpoints to device pixels.
5. Activity separators used blue-grey one-DIP fills. Use a neutral separator token and one physical pixel. Chart guide lines remain functional chart content.
6. Retain the single outer window contour and antialiasing. No global clip/AA disabling or white cover blocks were introduced.

## Motion

Hover 150 ms, press 80 ms, release 140 ms, selection 220 ms, page 190 ms, dialog 220 ms. Buttons and switches use bounded cubic easing rather than springs for press feedback. Existing retargetable page/sidebar animation ownership remains in place. Reduced motion and inactive-window policy suppress decorative motion. Increased contrast and reduced transparency have explicit shared-material behavior.

## Verification status

- An intermediate test build compiled Qt/QML and the unchanged Rust DLL.
- Before the user took over acceptance, an intermediate D3D11 run at actual reported DPR 1.5 captured 62 routes in both themes and checked window operations/geometry. These captures predate the final sidebar elevation change and are NOT final visual acceptance.
- The first capture harness waited too briefly for asynchronous page loading. It was corrected to wait for the active loader route, pending preparation and motion to settle. Only the corrected harness is retained.
- Final visual, DPI, animation and performance acceptance belongs to the user. Do not mark it passed based on build success or intermediate captures.
- `tools/Test-LiquidGlass.ps1` is an optional reproducible engineering check for a build with `SWIRL_BUILD_UI_TESTS=ON`; it uses per-process DPR overrides, not changes to Windows display settings.
- The user preview package is a production build with UI test drivers OFF. `--ui-preview` uses isolated temporary node/extension stores and isolated appearance settings, bypasses activation of the installed instance, and stays open for manual use. Its data is intentionally empty and does not establish real-network acceptance.

## Platform boundary

No files under `core/`, Rust dependencies, network calculations, proxy/TUN actions or subscription behavior are changed. New production code uses Qt/QML and the existing platform adapter. No Win32, WinTUN or Qt dependency is added to the reusable Rust core.

Required future boundary: protocols, subscriptions, DNS policy, routing and measurements belong in portable Rust; OS routing, VPN/TUN, credentials, system proxy and platform paths belong in independent adapters with explicit interfaces. macOS/iOS/Android and HarmonyOS NEXT UI/adapters are separate work. HarmonyOS NEXT target compilation and OS network permission/API support must be verified separately; Android VpnService is not an assumed substitute.

Existing limitations found in this baseline: the Qt/Rust product packaging CMake path is Windows-only, and `swirl-dns::system_hosts` chooses platform filesystem paths internally. Those are not cross-platform acceptance. No non-Windows toolchain is installed in the selected Rust toolchain, so non-Windows compilation is NOT TESTED in this UI change. A future core portability task must inject OS hosts discovery rather than assume `/etc/hosts` on every non-Windows target.

## Primary references reviewed

- https://developer.apple.com/documentation/technologyoverviews/liquid-glass
- https://developer.apple.com/design/human-interface-guidelines/materials
- https://developer.apple.com/design/human-interface-guidelines/motion
- https://developer.apple.com/videos/play/wwdc2025/219/
- https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass
- https://doc.qt.io/qt-6/qml-qtquick-effects-rectangularshadow.html
- https://doc.qt.io/qt-6/highdpi.html
- https://github.com/stdware/qwindowkit (Apache-2.0; considered as a reference, not copied or added. Its private-Qt dependency and framework scope are unnecessary for this bounded change.)

The Apple Music screenshot supplied by the user guides the sidebar's inset contour, broad soft shadow and material separation. It does not authorize adding glass to content cards or restoring traffic-light buttons.
