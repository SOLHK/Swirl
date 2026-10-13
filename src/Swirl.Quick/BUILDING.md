# Swirl Windows Qt UI

This is Swirl's only maintained Windows application project, using C++23 / Qt 6
Quick/QML and Windows NSIS. The old WPF/.NET program is no longer present in
current branches. Most Qt pages use demonstration data. The separate opt-in CaptureService
forwards real HTTP requests and CONNECT tunnels; it never changes the system
proxy or accesses certificate stores. See CAPTURE.md. Settings > Proxy now
supports the independent, verified Mihomo lifecycle described in ENGINE_PHASE1.md.

## Windows Release build and installer

Requirements: Qt 6.8+ (validated with 6.10.3), CMake 3.25+, Ninja, either
MSVC 2022 x64 or MinGW-w64 13.1, and NSIS 3.11+. Put the compiler, CMake and
Ninja on PATH. Do not mix an MSVC Qt SDK with a MinGW compiler.

From the repository root in a developer PowerShell:

```powershell
# MSVC: run from the VS 2022 x64 developer shell.
./scripts/build-quick-windows.ps1 -QtDir C:/Qt/6.10.3/msvc2022_64 -InputTests

# MinGW: add C:/Qt/Tools/mingw1310_64/bin to PATH first.
./scripts/build-quick-windows.ps1 -QtDir C:/Qt/6.10.3/mingw_64 -InputTests
```

The script stages a pinned Mihomo release only after archive and executable
SHA-256 verification, runs engine contract/real-process/QML checks and existing
mouse/keyboard checks, then rebuilds a
production Release EXE without the test harness, deploys Qt/QML plugins using
`windeployqt`, and produces **out/Swirl-Setup.exe**. The installer creates a
start-menu shortcut, a desktop shortcut and a per-user uninstaller. A fresh
DistDir is required to avoid packaging stale plugins. Windows fonts are
provided by the OS and are never included in the installer.

For direct builds:

```powershell
cmake -S src/Swirl.Quick -B build/swirl-quick -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH=C:/Qt/6.10.3/mingw_64 -DSWIRL_BUILD_UI_TESTS=ON
cmake --build build/swirl-quick --parallel
./build/swirl-quick/Swirl.exe --interaction-test
./build/swirl-quick/Swirl.exe --smoke-test
```

Tests log to Swirl-diagnostics.txt beside the EXE. `--interaction-test`
checks actual mouse/keyboard input, scrolling targets into view, node metadata, offline counters, chart
selectors, Ctrl+K, search, history and bottom-row reachability. The smoke test
visits all 61 pages, including 32 dedicated configuration draft pages and the module catalog, waits
for lazy delegate creation and exits nonzero on QML loading warnings/timeouts.
CTest runs these checks with the offscreen software platform; on that platform
set QT_QPA_FONTDIR to a temporary font-fixture directory. Normal Windows
startup uses installed Windows fonts automatically.

## Screenshot verification

```powershell
./build/swirl-quick/Swirl.exe --capture-preview=C:/temp/overview.png --preview-size=1464x930 --preview-theme=light
./build/swirl-quick/Swirl.exe --capture-preview=C:/temp/connected.png --preview-size=1464x930 --preview-connected
./build/swirl-quick/Swirl.exe --capture-preview=C:/temp/minimum-bottom.png --preview-size=800x560 --preview-scroll-bottom
```

These render the real QML window, not a reference-image background. The normal
Windows platform uses the GPU renderer. Native preview resolution is logical
size multiplied by the effective device-pixel ratio. QT_SCALE_FACTOR multiplies
the OS scale; factors 2/3, 5/6, 1 and 4/3 on a 150% desktop check effective
100/125/150/200% scaling without modifying system settings. Screenshots do not
verify touch, multi-monitor transitions or OS snap gestures; those remain
manual checks. Buttons call Qt native close/minimize/maximize APIs, dragging
uses startSystemMove, and all eight resize edges use startSystemResize.
Windows uses a single frameless Qt Quick window and native per-pixel transparency
where available. The QML shell uses a scalable 14-unit logical radius on the native per-pixel alpha surface.
Large containers use 12, cards and popups 10, fields 8, and rectangular buttons 10.
These are visual design units, not physical pixels or an OS specification. Qt
handles screen DPI and Theme.dp handles user UI zoom independently.
The QML content mask preserves antialiased edge coverage without a binary Win32 region; system DWM
Acrylic fills transparent corner pixels and is therefore disabled. Activation, window controls and
work-area maximization are explicitly handled. Unsupported systems or renderers receive
an opaque fallback. See docs/UI_1_0_VALIDATION.md.

## Design and scope

- The initial route is Activity (活动). The reference window is 1144×840 DIP,
  with a 242 DIP sidebar, 20 DIP margins/gaps and a shared 24 DIP card radius.
- Navigation follows the supplied Surge Activity reference. Additional features
  remain available in More (更多) and through Ctrl+K. Overview keeps global
  configuration, node selection and system summaries.
- Native Windows 11 DWM Acrylic supplies real desktop blur. Sidebar and main
  content use different alpha tints; unavailable composition falls back to
  opaque surfaces. Qt applies system DPI and Theme.dp applies user UI zoom.
- Activity samples the owned Mihomo's authenticated API. No reference-image
  data is fabricated. Unavailable router/DHCP/public-IP values remain blank.
- Diagnostics tests explicit direct and proxy routes independently, tries
  multiple HTTPS 204 endpoints and classifies actual DNS/TCP/TLS/HTTP errors.
- Detailed architecture, measurements and scope: docs/SURGE_ACTIVITY_PHASE1.md.

## Module drafts and in-place upgrades

The catalog exposes 56 public capability entries. Thirty-two new draft pages offer configuration, ordered records, local persistence and JSON import/export. These do not start network services. See `docs/UI_MODULE_COVERAGE.md`. Tests use QStandardPaths test mode and never overwrite user drafts.

The installer reuses the registered install directory and overwrites application files. It retains configuration/data and refuses a silent update when the existing executable is still running or unwritable (exit 2). Interactive setup offers retry after quitting Swirl. Test an old installer followed by the new installer using the SAME fresh isolated test directory; verify the new EXE hash and startup before uninstalling.

The latest native Windows screenshots, tests and compositor limitations are documented
in `docs/UI_1_0_VALIDATION.md`. `docs/UI_VISUAL_VALIDATION.md` and
`docs/UI_BACKGROUND_VALIDATION.md` record previous visual iterations only.

## Native 1.0 UI validation

`--window-test --window-test-output=C:/Swirl-validation` requires a test-enabled build and an unlocked native Windows desktop. It uses separate color windows to verify changing composition, movement, a blurred edge, opacity fallback, window controls, title double-click, native hit testing and work-area maximization. It temporarily brings only its own test window forward. Do not run this test on offscreen CI.

Use `scripts/build-quick-windows.ps1 -InputTests -NativeBackdropTests` for native checks before producing the installer. Normal input/capture/smoke checks remain available offscreen. Production builds omit Qt Test. `--capture-native-frame=...` explicitly brings the target window forward briefly; it fails if the target cannot be activated or a composed frame cannot be saved. See `docs/UI_1_0_VALIDATION.md` for measured results and unverified environments.


## Branding and window controls

The application and About page use the abstract S data-flow SVG mark. Existing
asset filenames are retained for installer/resource compatibility. The sidebar
has no brand block. The three 12 DIP window buttons invoke native close,
minimize and maximize/restore APIs. The shell uses SDR and no emissive traffic
light pass. Previous HDR shader diagnostics remain in the tree but are not
the production window's visual treatment.

System proxy lease tests run in `swirl-system-proxy` without changing Windows
settings. To temporarily verify real WinINet routing against an already running
loopback proxy, set `SWIRL_NATIVE_PROXY_TEST=1` and `SWIRL_NATIVE_PROXY_PORT` then
run `SwirlSystemProxyTests nativeInternetRequest`. This restores the previous
settings before reporting success. Production enables the native backend only
for ordinary interactive runs, never for preview or test modes.
