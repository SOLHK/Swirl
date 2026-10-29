# Current delivery and promotion (2026-10-29)

- The owner explicitly authorized the current 0.2.25 candidate (continuing the 0.2.23 UI work and 0.2.24 TLS deployment correction): refine the dark transparent floating sidebar, remove obsolete Mihomo runtime paths, refresh README and real software screenshots, then integrate into test and promote test to main through the existing release-approved process.
- After the exact-test-SHA public HTTPS gate failed, the owner explicitly extended this task to isolate and fix that gate's real root cause before continuing to main. Preserve certificate, TLS and protocol verification; do not skip checks or relax assertions. This permits the related diagnostic, network or runtime-deployment correction, not unrelated network refactoring.
- This authorization applies to this change set. It does not authorize a Release, force-push, branch deletion/recreation, default-branch change or branch-protection change. Earlier main-cancellation and one-time reconstruction plans are superseded for this candidate.
- Keep the sidebar body fully transparent and unblurred, with clear APEC background detail. Light appearance is already accepted; dark edges must be subtle. Preserve fonts, geometry, animations, caches and actual data bindings.
- Preserve Clash/Mihomo-format, sing-box and Xray/V2Ray import, subscriptions, provenance and encrypted migration. They are input formats, not external runtime integration. Keep anti-bundling/source guards and licenses for dependencies still in use.
- Use ordinary merge commits. Preserve unrelated test history. Require the four exact test-HEAD push workflows, then an owner-applied release-approved label after their completion, a successful production-gate and all applicable PR checks before merging test to main. Never infer approval for a later unrelated candidate.
- Build and verify the local Windows installer and source identity before delivery. Keep private screenshots, endpoints, credentials and profiles local; README screenshots must come from an isolated real UI with truthful empty states.
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
