# Swirl Windows Qt UI

This is the existing Swirl repository's C++23 / Qt 6 Quick UI subproject on
`test`. The original WPF/.NET network implementation, configuration and brand
assets are preserved. Most Qt pages use demonstration data. The separate opt-in CaptureService
forwards real HTTP requests and CONNECT tunnels; it never changes the system
proxy, starts Mihomo or accesses certificate stores. See CAPTURE.md.

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

The script first builds and runs the mouse/keyboard checks, rebuilds a
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
checks actual mouse/keyboard input, node metadata, offline counters, chart
selectors, Ctrl+K, search, history and bottom-row reachability. The smoke test
visits the 24 retained modules, the capture page and the external-tools placeholder, waits
for lazy delegate creation and exits nonzero on QML loading warnings/timeouts.
CTest runs these checks with the offscreen software platform; on that platform
set QT_QPA_FONTDIR to a temporary font-fixture directory. Normal Windows
startup uses installed Windows fonts automatically.

## Screenshot verification

```powershell
./build/swirl-quick/Swirl.exe --capture-preview=C:/temp/overview.png --preview-size=1450x884 --preview-theme=light
./build/swirl-quick/Swirl.exe --capture-preview=C:/temp/connected.png --preview-size=1450x884 --preview-connected
./build/swirl-quick/Swirl.exe --capture-preview=C:/temp/minimum-bottom.png --preview-size=1000x650 --preview-scroll-bottom
```

These render the real QML window, not a reference-image background. The normal
Windows platform uses the GPU renderer. Native preview resolution is logical
size multiplied by the effective device-pixel ratio. QT_SCALE_FACTOR multiplies
the OS scale; factors 2/3, 5/6, 1 and 4/3 on a 150% desktop check effective
100/125/150/200% scaling without modifying system settings. Screenshots do not
verify touch, multi-monitor transitions or OS snap gestures; those remain
manual checks. Buttons call Qt native close/minimize/maximize APIs, dragging
uses startSystemMove, and all eight resize edges use startSystemResize.
Windows uses the QML antialiased alpha silhouette only. Native DWM border/
non-client rounding and the integer region mask are disabled to eliminate
gray corner remnants at high DPI.

## Design and scope

- Theme.qml centralizes colors, fonts, gaps, animation and radius tokens.
- SwirlPillSurface is shared by navigation, the connection pill, buttons,
  search, combo boxes and segmented selections; its radius is always height/2.
- Reference size is 1450 x 884 logical pixels with a 243-pixel sidebar. Below
  width 1160 the sidebar becomes an icon rail. At narrower main widths the
  bottom cards stack and scroll so every row remains reachable.
- Cards are matte pale blue with subtle borders; a translucent DWM acrylic
  backdrop is deliberately not enabled for this reference style.
- Only the selected download/upload/cumulative series is drawn. Offline
  endpoints and current counters are zero. History and event times share the
  session clock. Cumulative GB stays historical and increases only while the
  demonstration connection is active.
- The user-provided flat blue kite replaces the app/installer icon and sidebar
  mark. The transparent mark sits on a QML pale-blue tile; outline UI icons
  remain Canvas drawings.
- Existing specialized pages remain available by search and overview links.
  The HTTP capture page is real; remaining proxy backend integration and further
  visual refinement of other pages remain future work.

For isolated deployment validation, launch the installer with `/ISOLATED /S`
and a final `/D=<absolute test directory>` argument. This extracts the same
runtime and uninstaller but leaves existing Swirl shortcuts and registry
entries alone. The isolated marker also makes its uninstaller skip shared
entries. Never use an existing user installation directory for this test.

The GitHub workflow builds Windows MSVC, runs the input checks and all-page
smoke, captures previews and packages the production EXE. Its existing release
step publishes a test-only prerelease. All work stays on `test`; promotion to
`main` requires an explicit user instruction.
