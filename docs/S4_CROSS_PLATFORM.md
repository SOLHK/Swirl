# One Rust Core, separate platform adapters

## Required boundary

Portable crates own protocol parsing/handshakes, subscription semantics, DNS, routing, connection timing, cancellation and resource bounds. They must not directly import Windows/Win32/WinTUN, Qt, JNI/Android SDK, Apple frameworks or HarmonyOS SDK APIs. Established portable libraries (Tokio, Rustls, Quinn, serde, ring) may implement their own OS backends; this is distinct from coupling Swirl business logic to a platform.

`swirl-platform` is the existing host adapter. Its `system_hosts_path() -> Option<PathBuf>` keeps Windows host-path discovery outside DNS. On unsupported mobile hosts it returns no desktop integration; it does not claim network permission or silently implement a tunnel. Future socket protection, tunnel I/O, route/DNS ownership, secure storage and lifecycle hooks must enter through explicit platform-neutral contracts implemented by the host adapter. Add contracts when a real consumer exists, not placeholder implementations that pretend to provide VPN capability.

`swirl-api` is a C ABI around the portable engine. Qt owns the current Windows product shell and may use Windows APIs in that platform layer. The common Rust crate dependency graph does not depend on Qt. Windows DPAPI persistence remains outside common Rust; current non-Windows product storage is not completed or claimed.

## Compile checks and acceptance levels

Run `python tools/tests/test_portable_core_boundary.py` before committing. It guards direct platform dependencies and SDK calls; compiler checks are additionally required because source scanning alone cannot prove portability.

| Target | Applicable check | Separate system acceptance |
|---|---|---|
| Windows x64 GNU/MSVC | Full workspace check, tests and actual paired Qt/DLL build | Install/upgrade/recovery and user-provider acceptance |
| macOS ARM64 | Full workspace native CI and library check | Future host networking, secure storage, UI and permissions |
| Android ARM64 | Full library check with Android NDK | VpnService permission, socket protection, lifecycle and device traffic |
| iOS ARM64 | Full library check on macOS with Xcode SDK | Network Extension entitlement, host lifecycle and device traffic |
| OpenHarmony ARM64 | Portable modules check without C SDK; full core requires OpenHarmony native SDK for C dependencies | HarmonyOS NEXT application permissions, VPN Extension, signing/provisioning and actual device traffic |

All rows are obligations/check definitions, not declarations that S4 has passed them. Current results belong in the final validation report with exact source SHA and scope. A subset check must be labeled with its crates; it cannot stand for a full-core build. No other-platform UI or system adapter is required during this Windows stage.

## HarmonyOS NEXT is a separate verification track

Rust documents `aarch64-unknown-linux-ohos` for OpenHarmony and provides Rust target artifacts, with native SDK/toolchain requirements for C and linking. That does not validate a commercial HarmonyOS NEXT application's permissions, available API levels, VPN authorization, signing, background execution or socket routing. Do not call Android VPN APIs for this target. Keep compilation and device/system-network validation in separate report fields; lack of a HarmonyOS device is **unverified**, not a pass.

Primary references checked during S4:

- [Rust OpenHarmony target and SDK requirements](https://doc.rust-lang.org/stable/rustc/platform-support/openharmony.html)
- [Rust Android target](https://doc.rust-lang.org/rustc/platform-support/android.html)
- [Rust iOS target and Xcode SDK requirements](https://doc.rust-lang.org/stable/rustc/platform-support/apple-ios.html)
- [Huawei VPN Extension guide](https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/net-vpnextension) (browser endpoint found; complete guide text was unavailable to the research tool, so no unverified permission details are asserted here).

Prefer maintained multi-platform dependencies, retain pinned source/license provenance and negative tests, and avoid adding OS dependencies for Windows convenience. Keep unsupported semantics explicit rather than translating them to DIRECT or weakened security.
