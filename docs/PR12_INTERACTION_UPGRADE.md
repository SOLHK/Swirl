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
