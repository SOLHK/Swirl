# Product UI update: subscription import, node timing, and version

This change starts from the Windows Rust product source `b8aa4f6f40a091697e89ae4c8291789661edca60`.

- `src/Swirl.Quick/PRODUCT_VERSION.txt` is the product version source. Bump it before packaging each new source revision. The packaging script rejects a version that is not newer than the previous source revision, the installed product, or retained Rust product installers. The source SHA remains a separate build identity. This product update is `0.1.1` (`0.1.1.0` in Windows file and installer resources).
- The node list displays Rust's outbound establishment time after a successful HTTP HEAD probe. The number includes applicable DNS, connection, and node handshake work. It is neither an ICMP ping nor the complete time to the target response. The latter remains an internal success check and is not displayed as node latency.
- The one-click import UI now explicitly imports nodes only. New subscriptions default to node-only updates. Existing subscriptions retain their previous full-profile behavior until the user selects node-only in Edit or uses the action offered for an unsupported full profile. A node-only update validates the retained network policy against the candidate nodes and commits both atomically. Existing rules and DNS remain active; a dangling policy reference rejects the update.
- HTTP 400 is a response status. Qt network error 302 is `ProtocolInvalidOperationError`, not an HTTP redirect. These are reported separately; no supplier cause is inferred from them alone.

The implementation was informed by primary references, without copying their code:

- [Shotcut CMake](https://github.com/mltframework/shotcut/blob/master/CMakeLists.txt) and [application startup](https://github.com/mltframework/shotcut/blob/master/src/main.cpp) use one version for the build and Qt application.
- [Notepad++ NSIS installer](https://github.com/notepad-plus-plus/notepad-plus-plus/blob/master/PowerEditor/installer/nppSetup.nsi) injects release versions into Windows installer metadata; [NSIS documentation](https://nsis.sourceforge.io/Docs/Chapter4.html#4.8.3.2) specifies the four-part numeric version format.
- [Mihomo's URL test](https://github.com/MetaCubeX/mihomo/blob/Alpha/adapter/adapter.go) uses an HTTP HEAD request; [Surge's URL test](https://manual.nssurge.com/policy-groups/url-test.html) prefers a second HEAD on a reused connection; [Shadowrocket's announcement](https://t.me/s/ShadowrocketNews?before=330) describes selectable CONNECT, TCP, and ICMP methods. Their displayed milliseconds do not share one guaranteed measurement boundary.
- [Qt's QNetworkReply error list](https://doc.qt.io/qt-6/qnetworkreply.html) defines error 302.

Local synthetic checks and Windows Qt UI tests do not establish private supplier connectivity. No private subscription was refreshed for this change.
