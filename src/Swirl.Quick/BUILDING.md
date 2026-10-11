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
Windows uses a single frameless Qt Quick window and native DWM Desktop Acrylic
where available. Native activation, window controls and system work-area
maximization are explicitly handled; the OS owns the outer corner/backdrop
when native composition is active. Unsupported systems or renderers receive
an opaque fallback. See docs/UI_1_0_VALIDATION.md.

## Design and scope

- Theme.qml centralizes colors, fonts, gaps, animation and radius tokens.
- SwirlPillSurface remains shared by buttons, combo boxes and segmented selections.
  Navigation uses stable 42-pixel rows and a neutral rounded selection; sidebar
  search and content cards have their own purpose-specific radius tokens.
- The current overview reference is 1464 x 930 logical pixels with a 252-pixel full sidebar. Below
  width 1160 the sidebar becomes an icon rail. At narrower main widths the
  bottom cards stack and scroll so every row remains reachable.
- Light content uses opaque neutral white (#F7F7F8), white cards
  (#FFFFFF), subtle borders (#E5E5E8) and sidebar tint (#E9E9EC).
  The sidebar tint uses 0.82 opacity only when native DWM composition is active;
  otherwise it is opaque. The content area always remains opaque. Dark mode
  uses corresponding neutral tokens and the same capability-based fallback.
- Only the selected download/upload/cumulative series is drawn. Offline
  endpoints and current counters are zero. History and event times share the
  session clock. Cumulative GB stays historical and increases only while the
  demonstration connection is active.
- The transparent wave SVG `assets/icons/swirl_wave_mark.svg` is used directly
  as the sidebar brand mark without icon cradle, frame or shadow. The app and
  installer use the corresponding wave-based icon resource, with SVG glyphs
  under `assets/icons/ui/` for interface actions. No legacy kite icon is
  presented as the current Qt brand.
- Existing specialized pages remain available by search and overview links.
  The HTTP capture page is real; remaining proxy backend integration and further
  visual refinement of other pages remain future work.

For isolated deployment validation, launch the installer with `/ISOLATED /S`
and a final `/D=<absolute test directory>` argument. This extracts the same
runtime and uninstaller but leaves existing Swirl shortcuts and registry
entries alone. The isolated marker also makes its uninstaller skip shared
entries. Never use an existing user installation directory for this test.

The GitHub workflow builds Windows MSVC, runs the input checks and all-page
smoke, checks Qt Quick previews at 100/125/150/200% effective offscreen scaling,
and checks 1000x650, 1464x930 and 1920x1219 logical windows before packaging
the production EXE. Preview warnings/errors fail the job, and per-preview logs
are uploaded as Swirl-Quick-Preview-Diagnostics. These software previews do not
replace native Windows GPU/DWM or multi-monitor checks. Its existing release
step publishes a test-only prerelease. All work stays on `test`; promotion to
`main` requires an explicit user instruction.

## Module drafts and in-place upgrades

The catalog exposes 56 public capability entries. Thirty-two new draft pages offer configuration, ordered records, local persistence and JSON import/export. These do not start network services. See `docs/UI_MODULE_COVERAGE.md`. Tests use QStandardPaths test mode and never overwrite user drafts.

The installer reuses the registered install directory and overwrites application files. It retains configuration/data and refuses a silent update when the existing executable is still running or unwritable (exit 2). Interactive setup offers retry after quitting Swirl. Test an old installer followed by the new installer using the SAME fresh isolated test directory; verify the new EXE hash and startup before uninstalling.

The latest native Windows screenshots, tests and compositor limitations are documented
in `docs/UI_1_0_VALIDATION.md`. `docs/UI_VISUAL_VALIDATION.md` and
`docs/UI_BACKGROUND_VALIDATION.md` record previous visual iterations only.

## Native 1.0 UI validation

`--window-test --window-test-output=C:/Swirl-validation` requires a test-enabled build and an unlocked native Windows desktop. It uses separate color windows to verify changing composition, movement, a blurred edge, opacity fallback, window controls, title double-click, native hit testing and work-area maximization. It temporarily brings only its own test window forward. Do not run this test on offscreen CI.

Use `scripts/build-quick-windows.ps1 -InputTests -NativeBackdropTests` for native checks before producing the installer. Normal input/capture/smoke checks remain available offscreen. Production builds omit Qt Test. `--capture-native-frame=...` explicitly brings the target window forward briefly; it fails if the target cannot be activated or a composed frame cannot be saved. See `docs/UI_1_0_VALIDATION.md` for measured results and unverified environments.
