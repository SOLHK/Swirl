# PR #12 interaction upgrade — staged validation

2026-10-14, Windows x64, Qt 6.10.3, MinGW 13.1, Release. All work remains on `feat/phase3-system-proxy-ui`; PR #12 stays draft. No main merge or release.

## Phase 1

- More retains the existing seven entries in their original positions and adds Subscription Management in the same grid. It opens the existing subscription page in the secondary window. Main navigation and Ctrl+K are preserved.
- A window-scoped dismissal stack handles one Escape per layer, including Escape during entry animation. It restores keyboard focus, guards edited forms, and cancels discard confirmations without discarding edits. Qt retains native file/menu popup handling. DNS Apply/Cancel retain explicit save/discard semantics.
- Subscription deletion requires confirmation. Existing HTTPS imports, DPAPI storage, refresh timers, and network code are unchanged.
- Adjacent sidebar/workspace tints avoid stacking opacity. Light sidebar/workspace alpha is 0.88/0.94; dark is 0.92/0.96. Independent cards use separate surfaces. Windows 11 Desktop Acrylic supplies real DWM blur with native corners/shadows. Unsupported systems retain the existing alpha fallback; this fallback does not claim true blur.
- Original reference images inspected from the user-provided `D:/AdShield/111`: settings grid, process page, and independent panel. The light material is neutral, the work area remains clear, and existing navigation geometry/icons are retained.

Validation before Phase 2: `swirl-import-subscription`, `swirl-overview-input`, `swirl-all-pages` all passed (3/3). Native Windows input passed (69 checks); native compositor/geometry passed (56/56), at 150% Windows DPI. The split-color background produced 30 intermediate pixels, verifying actual blur rather than alpha alone. Native shadow darkening is accounted for when checking the four corner background pixels.

Evidence is delivered outside the source repository in `outputs/phase1`: secondary page PNGs, compositor light/dark/disabled/maximized PNGs, and test logs. Real user subscription URLs, tokens, passwords and stores were not used. Tests run with isolated temporary stores. Physical HDR and other monitors/resolutions still require separate acceptance; 150% DPI is the tested desktop.

Changed areas: CMake/main context setup, DismissalController, WindowsBackdrop, Main/Theme, shared dialog/title bar, FeatureHub, Subscriptions, DNS/Scripts save semantics, native input/window checks.

## Phase 2

Shared motion tokens now distinguish press (110 ms), hover (150), switch (180), page/dialog (220), exit (160), and expansion (240). Buttons retain fixed hit areas, get subtle interrupted press/rebound and a bounded click light, and stop feedback when disabled/hidden/reduced. Navigation hover, directional page history, segmented selection travel, checkbox/radio state, switch thumb and field focus transitions follow the same policy. Secondary settings windows fade/scale; quick reopening cancels exit. Dialogs release modal mouse interception when exit starts so fading cannot swallow the next table click. Noninteractive cards have no hover loop; interactive cards opt in. Software rendering retains a rounded opaque fallback.

Validation: the full 14-test run initially found one input regression and the missing packaged rule fixtures. Both were fixed. The other 13 tests passed, including actual Mihomo HTTP/HTTPS switching, subscriptions, gateway, capture, telemetry and local scripts. The repaired input check (61/61) and motion check passed on repeat; all-page startup passed. Native input also passed. Native GPU motion checks had zero failures, 704 measured frames, 240 Hz refresh, warm median 4.1501 ms and warm P95 4.6092 ms. Revisit working-set growth was 2,027,520 bytes; one idle frame, zero live texture grabs. These describe this machine, not every GPU/resolution.

`outputs/phase2/motion-comparison.gif` uses the same 80-frame native input sequence before and after Phase 2: hover/press the More subscription entry, open Add Subscription, Escape the form and settings, and switch navigation. It is a UI recording of empty isolated stores. Capture is deliberately sampled for review; it is not the FPS measurement. `gpu-motion.json` contains the separate GPU measurements.

Changed areas: SwirlMotion, shared buttons/dialogs/combo/toggle/segmented/field controls, checkbox/radio/card/navigation surfaces, AppState/PageHost history direction, Main settings animation, CMake test fixture staging, input/motion recording tests. No animation runtime dependency added.

## Phase 3

Subscription cards use incremental updates by stable ID. Updates preserve the delegate, expansion and scroll position; deletion and insertion have bounded list transitions. Details expand/collapse over 240 ms. Busy badges rotate only while a real operation is active and the window is visible; reduced motion uses a static mark. Success/error colors follow actual subscription and node results. Node rows also use stable identity; repeated measured latency values interpolate locally, while missing/failed measurements retain their explicit text. Chart repaint/transition work is skipped while hidden. Modal drafts disable navigation shortcuts to avoid bypassing data protection.

Validation: relevant CTest 6/6 passed. Extended node/subscription UI checks 89/89 passed, including HTTPS form save, hidden URL on edit, preservation of the encrypted URL, actual refresh, stable card identity and expansion, real failed download retaining nodes, Escape cancelling deletion, confirmed deletion retaining nodes as manual nodes, and real Mihomo node request/switch/disconnect. The final 3 checks after state-color/recording changes also passed. Synthetic TLS fixtures and temporary stores only; no real subscriber credentials. `outputs/phase3/subscription-update.gif` records an actual delayed HTTPS update, with success/failure PNGs and logs alongside it. This recording contains only fixture names.

Changed areas: SubscriptionsPage, ProxiesPage, SwirlAnimatedModel/DataTable, activity indicator and expander, status badge/capsule, TrafficChart visibility, Main shortcuts, CMake resource registration and NodeUiChecks.

## Phase 4

Qt Quick Effect Maker v6.10.3 was actually built with the same Qt/MinGW kit and exported Swirl's original click-light project. The tiny shader is loaded only during a bounded click pulse and unloaded at idle; software, reduced-motion and adaptive performance fallbacks remain native QML. Rive's dependencies/licenses were inspected and its actual configuration was attempted; the missing `fxc.exe` prerequisite prevents declaring a stable MinGW integration, so no Rive runtime/assets are shipped. FluentUI Qt6 button/toggle/input/combo implementations informed the interaction choices without replacing Swirl's controls or copying its runtime. See ANIMATION_DEPENDENCY_RESEARCH.md for pinned revisions and file-level license inventory.

Main, settings and panel windows now each own their DWM compositor instance. Separate settings and popup tint tokens prevent inheriting the main work area's opacity. Native restore exposed an Escape shortcut activation regression; independent window dismissal now uses the same event controller as popups, and the real restore/Escape check passes.

Validation before packaging: full CTest 14/14 passed; final UI/all-page/motion regression 3/3 passed; native input 69/69 passed; native window compositor 56/56 passed. Physical-viewport rendering passed 18/18 at native DPR 1.5 and 18/18 at per-process DPR 1.25 for 1920x1080, 2560x1440 and 3840x2160, Light/Dark, More/Overview/Subscriptions. Native compositor/restore tests passed 56/56 at per-process DPR 2.0. The render-only driver permits a 4K swapchain larger than the current desktop; it is excluded from production and does not change OS display settings. A high-DPI capture fixture was fixed to restore window geometry after manual zoom, avoiding offscreen black pixels being misreported as bad corners.

FP16/HDR production shader checks passed 7/7, including above-SDR-white GPU readback and SDR fallback. Current physical display: NVIDIA RTX 5060 Laptop GPU, 2560x1600, 240 Hz, Windows native DPR 1.5, SDR. Actual HDR panel appearance and a physical 4K desktop are therefore still user acceptance items, not claimed as tested hardware.

Final GPU motion run: zero failures, 711 measured frames, warm median 4.1578 ms, warm P95 4.5883 ms, two idle frames, zero retained grabs, revisit working-set growth 1,286,144 bytes. Separate coarse per-process counters sampled 13 times: median CPU 33.44% of one core (24 logical processors), peak per-process 3D-engine sample 3%, peak working set about 238.8 MiB and peak private allocation about 504.0 MiB. The private allocation includes graphics/Qt resources and differs from resident memory; GPU samples are coarse, not total-device utilization or a sustained-load guarantee. See process-profile.json and gpu-motion.json.

Release packaging turns SWIRL_BUILD_UI_TESTS off, deploys the existing Qt/Mihomo/runtime files, and validates light/dark startup without Qt SDK directories in PATH. The delivered archive is a local PR acceptance preview only. No installer changes the existing installation; no main merge or formal release is performed. Backend protocol implementations are unchanged.

Changed areas: SwirlClickLight/QEP/generated shaders, motion button resource wiring, secondary DWM contexts/material tokens, DismissalController/title-bar Esc, viewport/native/HDR validation driver, third-party notices and dependency research documentation.

## Acceptance limits

- Subscription/DPAPI/timer/node paths were tested with isolated synthetic HTTPS sources and actual pinned Mihomo/TCP forwarding. No real user subscription credentials were supplied or copied into evidence.
- Physical HDR/4K/multi-monitor handoff and long-duration usage on other GPUs remain acceptance checks. Current hardware, viewport/DPI simulations and FP16 readbacks are listed separately above.
- On platforms where Desktop Acrylic is unavailable, the existing native-alpha/opaque fallback remains. It is not described as verified true blur.
- Rive is deliberately absent from the production build because its prerequisite/build compatibility was not established. The requested native QML fallback is used.
- Existing unimplemented advanced networking modules documented in design-qa.md are preserved as existing limitations; this interaction upgrade does not claim to implement them.
