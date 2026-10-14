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
