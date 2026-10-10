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
./build/swirl-quick/SwirlQuick.exe
```

For a Visual Studio solution use -G "Visual Studio 17 2022" -A x64 instead.
For shipping, use windeployqt against the built exe to gather Qt dependencies.

The existing brand PNG is embedded from ../../AdShield/Assets/swirl-256.png.
DWM system Mica on supported Windows 11 is window backdrop only: it is not
per-panel backdrop blur or Apple's proprietary glass. On Windows 10 or when
disabled the UI uses readable opaque panels.

Build verification: source is authored for the listed toolchain but has NOT
been compiled on Windows in the authoring environment. No Qt desktop kit or
Windows compiler is available here. JavaScript editor uses a native QSyntaxHighlighter for local formatting.
All network/automation operations are UI
demonstrations and cannot affect system settings or stored user config.
