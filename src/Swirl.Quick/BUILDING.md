# Swirl Quick: Windows UI-only preview

This subproject coexists with the original Swirl WPF/.NET solution and does not
start or modify any networking engine. All HTTP, proxy, connection, node,
traffic and log data in the preview are synthetic demonstration fixtures.

## Requirements
Windows 10 2004+ / Windows 11 x64, CMake 3.25+, C++23-capable MSVC v143,
Qt 6.8+ desktop x64 SDK with Qt Quick and Qt Quick Controls 2.
Recommended kit: Qt 6.10.x + Visual Studio 2022 x64.

## Build (Developer PowerShell, x64)
From the repository root:

```powershell
cmake -S src/Swirl.Quick -B build/swirl-quick -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="C:/Qt/6.10.3/msvc2022_64"
cmake --build build/swirl-quick --config Release
./build/swirl-quick/Swirl.exe
```

For a Visual Studio solution use -G "Visual Studio 17 2022" -A x64 instead.
For shipping, use windeployqt against the built exe to gather Qt dependencies.

The existing brand PNG is embedded from ../../AdShield/Assets/swirl-256.png.
DWM system Mica on supported Windows 11 is window backdrop only: it is not
per-panel backdrop blur or Apple's proprietary glass. On Windows 10 or when
disabled the UI uses readable opaque panels.

## Verification and release status

An isolated GitHub Actions pipeline builds this preview on Windows 2022 with
Visual Studio 2022 (MSVC x64) and Qt 6.10.3, deploys dependencies with
`windeployqt`, and runs an offscreen startup smoke test that navigates all
24 UI modules. See the workflow:
https://github.com/SOLHK/Swirl/actions/workflows/build-qt-quick-ui.yml

A successful pipeline confirms compilation, packaging and basic QML loading,
**not** visual correctness on a physical Windows desktop. Manual tests remain
necessary for Windows 10/11, DPI 100/125/150/200%, system theme changes,
screen-reader usability, lower GPU performance and real 60 FPS frame rates.
The JavaScript editor uses a native QSyntaxHighlighter for local formatting.

All proxy, interception, MITM, scripts, DNS lookups, gateways and automation
actions are explicit local demonstrations. They cannot affect network
settings or stored WPF configuration.

## UI acceptance checklist

1. Navigate all 24 modules in the sidebar. Verify no empty page or load error.
2. Collapse/expand sidebar, resize window to its minimum, and use search.
3. Change light, dark and system themes, transparency and reduced-motion modes.
4. Change interface scale, and check text and tables at high DPI.
5. Select, filter and sort Connections; select nodes in Proxies.
6. Inspect Headers, Body, XML, image fixture, TLS, WebSocket and waterfall tabs.
7. Check DNS, Rules, Profiles, Subscriptions, Scripts and Automation forms.
8. From the UI DEMO menu, show loading, empty and error states, then restore.
9. Verify the original WPF app, system proxy and user files are unchanged.
10. Use the GitHub Actions artifact named `Swirl-Windows-Installer-EXE`
    from a successful run for packaged Windows testing.

## Future backend adapter strategy

Keep DemoDataProvider as a replaceable read-only source. Introduce
`ISwirlDataSource` (model snapshot/event interface) for profiles,
connections, policies, DNS and HTTP flows. Add a Qt-side client or IPC bridge
to the existing .NET process only after the UI contracts are stable. Real
network-core ownership, certificate actions, script execution and privileged
Windows changes must remain explicitly user-authorized.

## Optional headless UI snapshots

The CI workflow attempts to save `Swirl-Overview-preview.png` and
`Swirl-Inspector-preview.png` alongside the packaged EXE. These screenshots
come from the Qt offscreen software renderer and may be unavailable if its
window-grab capability is unsupported. They are **not** substitutes for
testing native DWM blur or typography on a real Windows 11 desktop.

## Chinese installer

The test branch CI produces a standalone `Swirl-Setup.exe` with a Simplified Chinese NSIS wizard, per-user installation under `%LOCALAPPDATA%\\Programs\\Swirl`, a desktop/start-menu shortcut and an uninstaller. No administrator permission is requested. Keep this installer on `test` until the user explicitly authorizes promotion to `main`.
