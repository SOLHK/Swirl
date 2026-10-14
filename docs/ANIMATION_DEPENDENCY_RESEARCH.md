# Animation dependency and tool verification

Verified 2026-10-14 against Swirl's Windows x64 / Qt 6.10.3 / MinGW 13.1 / C++23 Release environment. Candidate clones and tools are separate from Swirl's source/build. No candidate runtime or marketplace animation is shipped.

| Candidate | Version inspected | Result | Production decision |
| --- | --- | --- | --- |
| [Qt Quick animations](https://doc.qt.io/qt-6/qtquick-statesanimations-animations.html) | Installed Qt 6.10.3 | Existing Behavior, SpringAnimation, NumberAnimation, SmoothedAnimation and Transition compile/run in Release | Main motion architecture; no second animation system |
| [RiveQtQuickPlugin2](https://github.com/jebos/RiveQtQuickPlugin2) | `4ff14b434400cc2a32b4dd3e45bc20f9d657389a` | Dependency bootstrap completed; real MinGW/Qt configuration stops because `fxc.exe` is absent | Native QML fallback; Rive is not enabled or linked |
| [Qt Quick Effect Maker](https://github.com/qt/qtquickeffectmaker/tree/v6.10.3) | v6.10.3, commit `3e8b0f9` | Tool compiles with the same Qt/MinGW kit; original SwirlClickLight.qep loads, bakes and exports .vert/.frag/.qsb, exit 0 | Development tool only; small generated shaders compiled into Swirl through Qt ShaderTools |
| [FluentUI for QML](https://github.com/zhuzichu520/FluentUI) | `7e33a2f672d18239ef49ab960075b1137a1d18e7` | Qt6 FluButton/ToggleSwitch/TextBox/ComboBox interaction code inspected | Adopt interaction ideas (bounded thumb travel, disabled feedback, visible focus, interruptible transitions); retain Surge geometry and existing controls; no copied runtime |

## Rive compatibility and licenses

The plugin requires Qt >=6.6 and Qt GuiPrivate. This kit supplies both. It also unconditionally requires a Windows SDK `fxc.exe` shader compiler and enables D3D12 on Windows. After fetching its pinned runtime and dependencies, CMake failed at `cmake/RiveThirdParty.cmake:109`, `fxc.exe was not found`. This is a concrete missing prerequisite, not proof that all MinGW compilation/linking would succeed if the SDK were supplied. MinGW ABI/build and actual Rive rendering are therefore unverified. No SDK was installed, no MSVC kit substituted, and the production build has no Rive dependency. This follows the requested native fallback when a stable integration cannot be verified.

License files actually inspected:

| Source | License observed |
| --- | --- |
| Plugin LICENSE | MIT, 2026 Jeremias Bosch |
| rive-cpp LICENSE and renderer/LICENSE, runtime revision `3ccf0d9d7c2cf8bee0553245acaffe21ae3314b6` | MIT, Rive |
| HarfBuzz COPYING | Old MIT; individual test/asset subdirectories have additional notices |
| SheenBidi LICENSE | Apache-2.0 |
| Yoga LICENSE | MIT |
| Luau LICENSE.txt / lua_LICENSE.txt | MIT / Lua notices |
| libhydrogen LICENSE | ISC |
| miniaudio LICENSE | Alternative Unlicense or MIT |
| DirectX-Headers LICENSE | MIT |
| PLY 3.11 metadata | BSD |

No `.riv`, font, sample audio or marketplace asset is included in Swirl. Their resource-specific redistribution rights were not established, so no blanket permission is inferred from the plugin's MIT license. Bootstrap also encountered long-path omissions in HarfBuzz's test fonts; runtime source and license checks succeeded, but this reinforces why the candidate is not reported as a verified production integration.

## Effect Maker provenance and packaging

Effect Maker's dev branch currently requests a newer Qt version. The verification deliberately checks out the matching v6.10.3 tag rather than changing Swirl's kit. `qqem.exe` was built as a development tool. A local headless harness calls its existing EffectManager/NodeView load, bake and export APIs to make the export reproducible without changing app UI. The tool and local harness are not part of the Swirl runtime or delivered binaries.

The tool source is GPL-3.0-only or Qt commercial; build system is BSD-3-Clause; its example assets have per-file BSD/commercial annotations. Swirl's `.qep` contains original shader math and headings, without imported Qt example nodes/assets. Only generated minimal GLSL source is retained; Swirl's normal Qt ShaderTools build creates its own backend shader packs. Existing dynamically linked Qt licensing remains in the third-party notices. There are no new DLLs, network services, fonts or animation assets.

The effect is a small, premultiplied click highlight, confined to a button. It has no time uniform, loop, texture capture, or large-area shader layer. Its Loader exists only while the bounded click pulse is visible and GPU effects are supported; software/adaptive fallback uses the existing QML surface. Reduced motion disables the pulse. Tests check that the selected backend is correct and the shader unloads when idle. Exported development shader packs total 2,930 bytes; final packaged sizes are recorded with the Release deliverable.

Native material reference: [Microsoft DWM system backdrop types](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwm_systembackdrop_type). Swirl uses Desktop Acrylic only when DWM accepts it, and retains an explicit fallback. Native Windows corners/shadows differ from macOS; matching the screenshot's geometry does not imply identical material implementation.
