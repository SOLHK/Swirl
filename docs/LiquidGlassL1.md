# Swirl Liquid Glass L1 implementation and manual acceptance

Baseline: remote `work/activity-page-v7-20261023`, `a47209420fe237b2970c2edb4194df318fc6d856`.
Development branch: `work/ui-liquid-glass-unification-20261023`.

## Material ownership

- `Theme.qml`: shared light/dark content colors, glass tint, separator and accessibility tokens. Existing `SwirlMotion.qml` remains the motion-token singleton.
- `SwirlGlassPanel`: ordinary opaque content material; one background-only analytic shadow. Activity retains two 276 DIP cards and three unboxed lower sections.
- `SwirlClearGlassSurface`: retained public component name; regular, legible navigation/control material, with optional elevation. It does not implement Apple's native optical refraction or a per-control backdrop blur.
- `SwirlSidebar`: unfilled pane over the continuous application canvas. Only an exterior rounded shadow establishes elevation. It has no source capture, content mirror, blur pipeline or independently colored fill. Selection is an ordinary overlay.
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

Hover 150 ms, press 80 ms, release 140 ms, selection 220 ms, page 190 ms, dialog 220 ms. Buttons and switches use bounded cubic easing rather than springs for press feedback. Existing retargetable page/sidebar animation ownership remains in place. Reduced motion suppresses decorative motion; activation changes do not cancel popup interaction. Increased contrast and reduced transparency have explicit shared-material behavior.

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

## 0.1.8 history (sidebar material rejected by user)

User-confirmed material source: Swirl's internal background and content, not desktop windows. No independent white/grey tint may be added to the sidebar. The former 0.1.7 sidebar was not accepted.

- The pane fill is transparent. A bounded crop of the adjacent app content is mirrored below it, blurred with Qt MultiEffect, and sampled with a small rounded-edge lens shader. No tint, brightness or saturation adjustment is applied. Native content text remains outside this effect path.
- An exterior-only analytic shadow replaces the full-area shadow behind this transparent pane, so the shadow cannot darken its interior. The original app canvas remains the underlying background.
- Neutral grey/white control surfaces improve affordance, with a distinct selected segment.
- The system-proxy capsule now navigates to `proxies`; the separate status popup and its full-window input-catching MouseArea are removed. It does not toggle network state.
- Non-Activity pages start below a 48 DIP caption exclusion area. Activity card geometry is preserved.
- Capture and Rewrite use complete grid rows; TLS right panel fills the height of the left column. The extra Fonts tile is removed from More; font settings remain under General. The final More tile spans the incomplete row.
- Combo boxes use an in-window popup. Opening a separate native popup no longer interacts with main-window activation. Window activation no longer changes the reduced-motion preference/transition policy. Static combo delegates no longer have insert/remove animations that can interfere with popup timing.

Functional verification is distinct from user visual acceptance. The targeted appearance test now exercises real pointer selection through Light/Dark/System repeatedly, keyboard selection, the next switch click, persistence, and direct proxy-to-node navigation while preserving proxy state. At reported DPR 1.5/D3D11, two different homogeneous in-app color fixtures were transmitted with identical RGB values and no pane tint. These are synthetic rendering checks, not a claim that the final look matches Apple Music. Final appearance remains pending user review.

No Rust source or dependency changed. Qt shaders are bundled through qsb; non-Windows builds remain NOT TESTED. Windows-only backdrop integration remains outside Rust Core.

## 0.1.9 sidebar correction

The user rejected the 0.1.8 mirrored content, which fabricated text/chart ghosts under a sidebar that originally had no such underlying content. Apple's optional background-extension technique was applied to the wrong input (the entire adjacent page, including labels and controls). Color-preservation checks verified the shader's arithmetic but did not verify the intended appearance.

Remove the sidebar's ShaderEffectSource captures, MultiEffect blur, source connection to mainArea, and sidebar-glass shader. The pane now has no fill; a continuous Theme.canvas covers the main application background on both sides. Keep an exterior-only rounded shadow, 8 DIP inset and 16 DIP radius. No right-page graphics or desktop pixels are sampled. Normal navigation content stays sharp.

The new regression check places a strongly colored/text-filled fixture over the right page and verifies that the sidebar interior is unchanged. It also checks that an empty sidebar sample matches the actual app canvas and that the pane fill is transparent. Tests are executed at reported DPR 1.5. Functional corrections from 0.1.8 remain intact. Final visual match to the user's Apple Music reference remains pending user acceptance.