# Swirl 3.0 implementation and evidence ledger

Work branch: `work/swirl-3-20261026`. Baseline: `cba9e3b` (product `8e3fc98`, 0.2.12).
Stage A candidate version: 0.2.13. This document records scope and evidence; a planned check is not a pass.

## Preserved contracts

- Rust Core remains the only proxy core. OS APIs stay in platform adapters.
- The 14 DIP window/sidebar contours, sidebar dimensions/navigation, and Activity's two upper cards plus three independent lower regions stay fixed.
- Activity has the sole master connection switch. Nodes remain a resource library; Strategy selects exits.
- Source refresh, one-use configuration review, encrypted provenance and durable configuration receipts remain in effect.
- No test may change the user's current Clash proxy, TUN, routes, DNS or account data. Real application acceptance and controlled fixtures are recorded separately.

## Stages

| Stage | Scope | State |
| --- | --- | --- |
| A | Desktop network diagnostics, reproduced compatibility fixes, responsive proxy ownership, independent Windows candidate | In progress |
| B | Shared design tokens and complete native control states | Planned |
| C | Every page, settings section and popup; preserve business wiring | Planned |
| D | Purposeful interruptible motion, profiling and resource lifecycle | Planned |
| E | Same-commit regression, Windows installer, manual acceptance instructions | Planned |

## Skills actually read

| Source | Version / license | Application |
| --- | --- | --- |
| [Hallmark](https://github.com/Nutlope/hallmark/tree/7ec868225c6caa040558c321ee0fefa0e73f83a8) | 2.0.0 / MIT | App-screen redesign: existing wiring, token ownership, hierarchy, focus and real states. Web marketing composition and CSS lint are inapplicable to native QML. |
| [UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/d14efff8ed1faa4187f004f79926f428c8074ec7) | Existing expanded repository skill / MIT | Cancellable state transitions, modal focus, consistent controls and information density. Executed UX searches; rejected generated marketing palettes because they conflict with the requested near-white desktop system. |
| [LottieFiles Motion Design](https://github.com/LottieFiles/motion-design-skill/tree/f9a8a041b85185ee4881b3471d3415e939aac772) | 1.0.0 / MIT | Separate response, entry, exit and selection timing; directional continuity; subtle damping; interruption must not delay state commitment. Implemented with Qt, not a web animation runtime. |
| [Qt official agent skills](https://github.com/TheQtCompanyRnD/agent-skills/tree/6845f02d41171a6df8b6e6fe225b7f5d1a6f4adf) | qt-qml 1.2, qt-ui-design 1.1, qt-qml-profiler 1.1 / BSD-3-Clause or Qt commercial | Native controls, asynchronous incubation, layout/animation ownership, reduced motion, bounded traces and truthful profiling. |

Existing installations were reused for implementation. User instructions override web-only short-motion restrictions and font/geometry defaults that would break the locked desktop layout. No invented screenshots, metrics, nodes or success states are product data.

## Primary architecture references

- [sing-box Windows network environment](https://github.com/SagerNet/sing-box/blob/testing/route/network_environment_windows.go): isolate interface/gateway enumeration in OS-specific modules and distinguish IPv4/IPv6 interface identities.
- [mihomo dialer](https://github.com/MetaCubeX/mihomo/blob/Meta/component/dialer/dialer.go): bounded dual-stack dialing, cancellation and closing losing connections; socket policy is separate from route selection.
- [Clash Verge proxy ownership](https://github.com/clash-verge-rev/clash-verge-rev/blob/dev/src-tauri/src/core/sysopt.rs): serialize guard operations, distinguish partial writes from unchanged state, preserve readback evidence and keep blocking OS work away from the event loop.
- These three repositories publish GPLv3-family licenses. They are architecture references only: their source/runtime is not copied into Swirl.
- [Qt performance guidance](https://doc.qt.io/qt-6/qtquick-performance.html) and [QML profiling](https://doc.qt.io/qt-6/qtquick-profiling.html): measure binding/script work and frame timing before claiming optimization.
- [Apple motion](https://developer.apple.com/design/human-interface-guidelines/motion) and [Liquid Glass](https://developer.apple.com/documentation/technologyoverviews/adopting-liquid-glass): reference direction; the Windows implementation does not claim native Apple material APIs.

## Performance acceptance

Use the same workload, renderer, viewport and instrumentation before/after. Record cold and warm navigation, rapid reversals, large-list scrolling, resize, popup/control response and background network work. Retain all slow frames, not only the median. Report p50/p95/p99/max intervals, GUI heartbeat stalls, peak memory and repeated-navigation growth. Profiling overhead is part of the limitations.

The refresh reference is 16.67 ms at 60 Hz and 8.33 ms at 120 Hz. Counting intervals against both budgets does not prove operation on both displays. Hidden/offscreen/unsynchronized runs are diagnostic data, not physical refresh-rate acceptance. Do not set fixed animation FPS or disable effects/caches to manufacture a pass. Windows 100/125/150/175/200% final visual acceptance belongs to the user.
