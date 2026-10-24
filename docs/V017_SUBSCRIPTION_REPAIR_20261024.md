# Swirl 0.1.7 subscription and node repair

This independent branch starts at S4 `ca7015679aef49702a40302de55d83e367ed9e95`. It does not change main, test, S4 or parallel development branches. Product version remains the requested 0.1.7.

## Changes

Subscription deletion previously detached imported nodes by clearing their source ID. The protected catalog now removes only nodes owned by that subscription in the same atomic file replacement as its source record. Manual nodes remain. Historical detached/orphaned nodes are classified separately and require explicit cleanup confirmation. Removed policy members and rule destinations become REJECT, and active snapshots depending on removed nodes stop. Updates retain stable identities through an encrypted provider alias; ambiguous replacements fail without changing the protected file.

Automatic download negotiation now uses a Swirl User-Agent; Clash is an independent explicit choice. The actual response content still selects the parser. HTTP status, Qt NetworkError, redirect, format recognition, parsing and strict profile validation have separate diagnostics. In particular Qt `ProtocolInvalidOperationError` is enum value 302, not an HTTP redirect status (`ContentOperationNotPermittedError` is 202). Same-origin redirects remain bounded; insecure or cross-origin redirects require an explicitly authorized final address instead of forwarding signed subscription data to another origin. TLS verification remains enabled.

New portable Rust profile projection owns the supported complete Clash/normalized INI and sing-box semantics behind a bounded offline C ABI. Supported rules, groups, exact hosts and supported DNS modes are validated before Qt atomically commits nodes and network configuration. Unknown or unsupported root/nested fields cause explicit whole-profile failure. Compound sing-box predicates, unsupported DNS policy/servers, scripts, local files and unimplemented global options are not silently dropped. A complete profile requires an explicit final destination. Clash DNS enable and IPv6 defaults are checked against the source schema. Node-only import preserves network settings and rejects dangling policy references.

The format picker has Automatic, Clash, Loon, Shadowrocket / Generic, Surge / Surfboard, Quantumult X and sing-box. Format recognition does not imply support for every protocol or complete profile dialect. Base64-wrapped JSON detection preserves its actual dialect. No external conversion service or third-party proxy core is used.

Subscription form scrolling/focus reset, window-bounded dropdowns, footer visibility, ESC draft protection, compact empty state and node source filtering are repaired. Node rows remain virtualized and the last row is reachable. Window/sidebar geometry and shell contours remain protected.

## Validation and limits

Native Windows testing uses Qt 6.10.3 MinGW and Rust GNU; production packaging uses Qt 6.11.3 MSVC on GitHub's disposable Windows runner. The paired DLL identity, final source SHA and package manifest must agree. No MinGW artifact is substituted for the production MSVC package.

The regression set includes Rust workspace tests, formatting/clippy, dependency boundary checks, C++ subscription/DPAPI/lifecycle and actual controlled socket traffic, Qt TLS/HTTP policy, mounted QML dialogs and five explicit effective DPR values (1, 1.25, 1.5, 1.75, 2). Synthetic UI rows verify layout/performance only, never subscription or network acceptance. Local and CI reports must state the source and renderer actually exercised. Initial harness setup failures and any remaining failed checks are retained separately.

Portable subscription/platform libraries can be checked locally against Apple, Android and OpenHarmony Rust targets. The CI additionally builds the full library for Android/iOS and runs native macOS/Linux product checks. OpenHarmony subset compilation is not full-core linking, a HarmonyOS NEXT adapter, network/VPN authorization or device acceptance. Those remain separate verification tracks.

The user's live Windows proxy remains owned by Clash at the time of investigation. Read-only process endpoints confirm both desktop and app-server connections to that proxy. Historical Codex logs contain proxy-connection failures and connection resets but cannot establish historical Swirl ownership or a unique cause. CONNECT/TLS reachability and unauthenticated 403/421 responses are not Codex login or conversation acceptance. No account tokens, private subscription requests or system proxy/TUN/routes/DNS changes are used during development.

The public native Shadowsocks test retrieved a public HTTP body and a certificate-verified HTTPS 204, then failed the strict TLS orderly-close assertion. Its same-address direct-origin control failed at the same close stage with the same certificate. This failure remains visible; neither a successful HTTP status nor a direct-control failure converts it into a pass. Existing retained VMess peer-closure failures from S4 are outside these subscription repairs and must not be hidden or counted as passing.

Private supplier HTTP 400 reproduction, real private-protocol combinations, browser traffic through the final installed Swirl, and Codex login plus a real conversation through Swirl require user acceptance on the Windows machine. The branch does not claim those results from mock data or an open port.

## Primary design references

- [reqwest redirect policy](https://github.com/seanmonstar/reqwest/blob/master/src/redirect.rs): bounded redirect and credential boundary design.
- [clash-rs configuration schema](https://github.com/ibigbug/clash-rs/blob/master/clash-lib/src/config/def.rs): client DNS/group semantics; independently implemented mapping.
- [subconverter supported formats](https://github.com/tindy2013/subconverter): format inventory and interoperability research only.
- [sing-box route rule documentation](https://github.com/SagerNet/sing-box/blob/testing/docs/configuration/route/rule.md): preserve predicate combinations, reject unsupported semantics.
- [Qt Basic ComboBox](https://github.com/qt/qtdeclarative/blob/dev/src/quickcontrols/basic/ComboBox.qml): control/model/viewport behavior.
- [Qt NetworkError enumeration](https://doc.qt.io/qt-6/qnetworkreply.html#NetworkError-enum): distinguish the Qt namespace from HTTP status.
- [Rust OpenHarmony target requirements](https://doc.rust-lang.org/rustc/platform-support/openharmony.html): target artifacts and native SDK requirements, separate from commercial device permissions.

These are behavioral/design references, not copied implementations. Existing dependency provenance and licenses remain in the repository and package.
