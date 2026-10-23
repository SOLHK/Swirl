# Swirl 0.1.7 S4 candidate integration

This branch is a **test candidate**, not a declaration that all strict protocol or private-provider acceptance has passed. Product identity is Swirl; the Rust engine remains an internal component. Frozen S3 `9f8af5754d2a932f7b967eea0e64cbc75717e6be` is the base. Main, test and other development branches are unchanged.

## Changes delivered

- Rust-owned, lossless sing-box Hysteria2/TUIC conversion, including nested TLS, Salamander, checked bandwidth/duration units, UDP modes and explicit rejection of unsupported requirements. Qt forwards source semantics through the existing ABI. Six independent-server Qt/DPAPI/TCP/UDP cases passed during implementation; private subscriptions were not used.
- Node model batches contiguous changes and ignores unrelated telemetry refreshes. The 2,000-node measured update fell from 24.47 ms to 8.46 ms, with 2,000 notifications reduced to one and no full model reset. Node delegates reset transient latency state when reused while retaining interpolation for the same node.
- Existing motion/caches/effects are retained. Shared easing and activity tokens, render-thread spinner, status contrast, subscription states and product naming are refined. Window/sidebar geometry and contour source hashes remain fixed; five native DPI scales were checked.
- Packaging validates inventory and every payload digest after smoke, saves diagnostics outside the archive, verifies installed bytes, removes only proven obsolete program files on upgrade and preserves unlisted or modified files during cleanup. No recursive application-directory uninstall is used. Installer test payloads are synthetic and distinct from actual final product installation.
- Platform dependency guards resolve aliases and target-specific dependencies. Full desktop Rust/native suites, Android/iOS library compilation and explicitly limited OpenHarmony module compilation are wired to S4. Compilation does not grant system network/VPN permission.

## Acceptance and retained failures

The implementation-stage evidence is detailed in:

- [Subscription acceptance](S4_SUBSCRIPTION_ACCEPTANCE.md)
- [Protocol support matrix](S4_PROTOCOL_SUPPORT_MATRIX.md)
- [Strict closure investigation](S4_PROTOCOL_CLOSURE_20261024.md)
- [UI and animation report](S4_UI_ANIMATION_REPORT.md)
- [Performance comparison and metric definitions](S4_PERFORMANCE_BENCHMARK.md)
- [Package acceptance and data-preservation tests](S4_PACKAGE_ACCEPTANCE.md)
- [Platform boundaries and SDK scope](S4_CROSS_PLATFORM.md)
- [CI review](S4_CI_REVIEW.md)

The original strict VMess half-close tests remain failures. Both Swirl and the same-version official Xray client receive the complete echoed payload but fail the stronger post-EOF receipt on all four tested transports. The independent direct control passes; the pinned server cancels the connection after upload completion. The test contract is retained rather than changing EOF into success.

The original public Shadowsocks HTTPS test also remains a failure: verified TLS and HTTP 204 are followed by a missing orderly TLS close. A same-IP, same-certificate direct control shows the same failure. Controlled orderly-close, truncated-close and bad-certificate tests remain separate. Neither external comparison proves that every other Swirl network path is defect-free.

The 20% memory-reduction target is **not achieved**. The comparable motion-run working set changed from 397.90 MB to 396.94 MB (about 0.24%); the long-frame count remained eight. Fresh-process message-loop readiness is not true cold-start or first-frame latency, and its noisy P95 difference is not attributed solely to this change. Do not substitute these metrics for input-to-photon or long-duration leak acceptance.

## Exact-source final regression and package identity

Each implementation stage is committed separately. Final regression must use the integrated branch tip and all jobs/artifacts must report that same full source SHA. The containing commit cannot embed its own future hash; obtain it with `git rev-parse HEAD` and compare it with `swirl-rust-build.json`, `package-manifest.json`, the runtime identity and the Actions run's `head_sha`.

Final run records and downloadable artifacts are available through [the S4 branch Actions history](https://github.com/SOLHK/Swirl/actions?query=branch%3Awork%2Fswirl-s4-final-completion-20261023). The delivery response and accompanying acceptance JSON identify the exact final SHA, run URLs, passed/failed/cancelled/skipped counts, installer SHA256 and local artifact location. Earlier stage runs are provenance only and must not be combined into a green final result. A candidate artifact may be retained after production gates even when the mandatory public network test fails; that failure remains visible.

Required local/final checks: portable boundary, Rust fmt/clippy/workspace tests; controlled native protocol menu; original strict VMess and official-client receipt control; Qt import/store/loader/selection/update/cancel/HTTP security/DNS tests; real native UI and headless stress with both exit status and assertion count checked; package manifest and isolated installer lifecycle. Final mobile checks use their CI SDKs. Disabled or unavailable device tests remain unverified.

## Remaining boundaries

- User private-provider import, refresh, node switching, actual Windows WAN/weak-network/long-run use and production installation into the user's existing environment require final user acceptance.
- TUN, gateway takeover, unsupported protocol/transport combinations, full foreign-client configuration semantics and other-platform UI/system adapters are not completed by this stage. Unsupported requests remain rejected; no third-party proxy core is shipped as fallback.
- OpenHarmony subscription/platform compilation does not establish full Rust Core linking with its native SDK or HarmonyOS NEXT VPN permissions/device networking. Android VpnService is never assumed to work there.
- v2rayN private ProfileItemDto backups and conditional ETag/304 refresh remain gaps; standard sharing URIs and existing periodic refresh are separate supported paths.
- Unknown legacy installed files are preserved when ownership cannot be proven. File-copy interruption does not yet have full executable rollback; no such recovery is claimed.

## User acceptance

Use only the final SHA's candidate package. Exit the existing Swirl before normal installation. Confirm the displayed 0.1.7 version, import private subscriptions locally, check supported protocol/transport options and retained unsupported-field diagnostics, exercise update/cancel/failure preservation, then test node selection, TCP/UDP, DNS/rules and repeated start/stop. Keep credentials out of public issues, logs and CI. System proxy and TUN acceptance are separate; no test in this work authorized changing the user's existing Clash/network setup.
