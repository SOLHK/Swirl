# Current final acceptance and branch delivery (2026-10-29)

- The latest user request advances the next delivery to 0.2.17 before the next GitHub push. Keep application, PE and installer versions synchronized, and vertically center Activity's policy-selector arrow across the full two-line control.
- The latest user explicitly permits slight Windows-only structural optical correction: tuck the side clouds inward and enlarge the central knot within the fixed taskbar canvas. Preserve a horizontally wide silhouette and fine contours without added strokes; the in-app canonical artwork stays unchanged. Ordinary buttons remain borderless in hover, press and focus. Keep all existing animation and visual effects while fixing measured rendering problems.
- Complete actual taskbar comparisons, native Windows 100/125/150/175/200% DPI and button-motion checks, plus exact-source installer verification before updating `test`. Temporary scale changes are for acceptance only; restore the original 150% setting and never use system scale/taskbar height to conceal icon defects.
- The latest user CANCELLED main promotion/recreation. Push only to `test` after acceptance; do not delete, recreate or push main or change its protection/default-branch settings. Preserve unrelated work on `test` through integration.
- Keep Clash/Mihomo configuration and subscription import compatibility; remove obsolete external core, invocation and packaging paths. Preserve required dependencies/licenses and do not touch other installed proxy applications, private data or the host proxy/TUN/routes/DNS.

# Swirl active engineering contract — APEC V3 / Rust-only (2026-10-27)

## Source of truth
- Product UI: `src/Swirl.Quick/main.cpp` + `qml/`, Qt 6.12 Quick/QML, C++23. Work from the current APEC V3 branch/commit and [design baseline](docs/SWIRL_V3_APEC_BASELINE.md); older UI V2 notes are historical evidence, not constraints.
- Product network runtime: `core/` native Rust only. `RustCoreLibrary` + `RustCoreEngine` are its Qt bridge; `ProxyEngine` and `ThreadedEngine` are Qt control/thread abstractions, **not** a second proxy core. Never ship or restore Mihomo, C++ forwarding fallbacks, downloaded external proxy executables, or their process managers.
- Third-party config parsing is required: Clash YAML, sing-box and Xray/V2Ray JSON and supported URIs are *data formats*. Do not delete format parsers, imported subscriptions, node provenance or migration adapters just because their names mention third-party clients.
- See [current architecture](docs/ARCHITECTURE.md), [core](core/README.md), [Windows build](src/Swirl.Quick/BUILDING.md), [APEC motion](docs/APEC_MOTION_FOUNDATION.md) and [performance](docs/APEC_PERFORMANCE_INTEGRATION.md).

## UI and behavior
- Replace old appearance with APEC V3 across pages, dialogs, shared controls, motion and branding; preserve behavior and user data. Old frozen 14dp / UI V2 layout directions are superseded.
- Keep node library (inspect/probe, no row-based connection), policy-controlled exit selection, source-owned subscriptions, automatic import, and the current transactional receipt/admission checks. Preserve window/page continuity and input, text/contrast, cold-start fonts and animation cancellation semantics.
- A screenshot or software-renderer smoke check is not native GPU / 60+ FPS / DPI proof. Record the exact source SHA, test scope, skips and packaging identity; do not claim unrun checks have passed.

## Security and acceptance
- Validate protocol support in native Rust. Unsupported options fail closed with a clear error; do not silently substitute DIRECT, other exits, or an external core.
- Keep DPAPI/encrypted data, subscription ownership, existing settings, System Proxy/TUN restore, rules/DNS and offline migration. Do not delete user data as part of source cleanup.
- Isolated CI/loopback acceptance must not change the developer machine's Clash, Windows proxy, TUN, DNS or routes. Private credentials, URLs, subscriptions and logs must not enter public commits.
- Windows product packaging must pair source-identical Rust DLL/EXE; keep `scripts/RustProductPackagePolicy.ps1` and runtime source guards. Do not package test executables or unrelated peer binaries. Commit/PR only after necessary static checks and appropriate CI tests; never force-push protected `main`.
- The historical `docs/` and older branch handoffs preserve their original evidence and may describe retired architecture. Do not treat them as active implementation instructions.
