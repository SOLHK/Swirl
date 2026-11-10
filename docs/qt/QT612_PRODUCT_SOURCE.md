# Qt 6.12.0 source accompanying the Swirl Windows runtime

The accompanying `Swirl-Qt-6.12.0-<source>-corresponding-source.zip` contains
actual source files, build material and license texts. The installed
`licenses/qt/SOURCE-BUNDLE.json` identifies that ZIP by its complete SHA256 and
byte count. The ZIP's `bundle-manifest.json` binds the Qt files to their measured
runtime hashes and the Swirl source commit. A separate `package-binding.json`
checks these files and installed notices against the final package manifest and
records the actual installer delivery receipt. This binding is not a substitute
for the final conclusion of the complete build and test workflow.
The package-binding directory retains the original packaging-time delivery
and package-manifest bytes. Installation tests may later update the workflow's
main delivery receipt; compare the stable source, installer and source-archive
identity fields, and separately preserve that final receipt and workflow result.

## Included source

| Module | Role | Source identity |
| --- | --- | --- |
| QtBase | Core, GUI, Network, OpenGL and deployed platform, image and TLS plugins | Official 6.12.0 source archive; commit `025bdad181de241e81bf853c8a2d7bf3d19261a9` |
| QtDeclarative | QML, Quick, controls, dialogs, layouts, QML files and plugins | Complete tracked library source at `4332fbbb4c340463dc8cee36dda0c85d932122d8`, with the modification below |
| QtSvg | SVG library, image and icon plugins | Official 6.12.0 source archive; commit `883a58532078d003cefef0a549bfe9f885ce41f5` |
| QtTranslations | Source catalogs for the deployed translations | Official 6.12.0 source archive; commit `2811457ceff8f0c24a1c4d14f947a283a17239d0` |
| QtShaderTools | Build dependency for Qt Quick shaders; not a deployed Swirl DLL | Official 6.12.0 source archive; commit `bccd516b990a6396900051470ac86cc27a7042ea` |
| QtTools | Build and catalog tools, including `lconvert`; not a deployed Swirl DLL | Official 6.12.0 source archive; commit `613a6fbf0a7998010ab2fda260b64066d66a021d` |

The five unmodified upstream `.tar.xz` files retain their original bytes and
are verified against Qt's fixed release checksums. Their internal `.tag` files
must match the commits above. QtDeclarative is the exact modified source ZIP
used for the selected `Qt6Qml.dll`, including its build files and licenses.
Its file-by-file manifest is included. It omits only the explicitly recorded,
unbuilt test262 Git submodule; neither the Qml nor BuiltinsOutput build uses
that test suite. The one upstream-forced CRLF test fixture retains its original
checkout bytes. No general newline conversion is performed.

## Modification and actual build material

Only `src/qml/memory/qv4mm.cpp` has the recorded library-source modification:
the allocator sweeping change from the official Qt commit
[`8c92fe01338c76885f412a68fd39238147e21a81`](https://github.com/qt/qtdeclarative/commit/8c92fe01338c76885f412a68fd39238147e21a81).
The exact patch is included under
`sdk-build-evidence/reproduction/tools/patches/qt612-qv4-sweep-8c92fe0.patch`.
Its SHA256 is
`9729ad5b706ea02def9a036bf0f32508143f69e4fcdbff386b2873326d7ca3ac`.
The patched source-file SHA256 is
`baa35a86e41990d2b5170d0ac426a837c77a08148f69c35a88e80a8f2e1a1525`.

The archived build material is historical evidence of how this DLL was made;
it retains its original source, run and diagnostic scope labels. Product
selection does not rewrite that earlier workflow's conclusion. The archive
includes:

- the complete builder and its imported Python helpers and locked SDK inputs;
- `configure-module.ps1`, `msvc-initial-cache.cmake`, `config.opt`,
  `config.summary`, `CMakeCache.txt` and `compile_commands.json`;
- the compiler/tool identities and exact configure, build and install command
  records, including their standard output and error logs;
- the restricted Qml install script, exported symbol/dependency checks,
  module install manifest and stock/derived SDK inventories;
- the explicit stock-header retention review for source EOL and generated
  parser source-location differences.

All paths in the historical command records describe the original CI machine.
They need to be replaced by corresponding local paths when rebuilding. They
are not commands that the source-delivery tool executes.

## Rebuilding the modified Qml library

Use an x64 MSVC developer environment and the fixed official Qt 6.12.0
`msvc2022_64` SDK described in the archived SDK lock. The recorded build uses
Release, Ninja, `/MD` (`MultiThreadedDLL`), and separate source, build and install
directories. Extract `sources/qtdeclarative-corresponding-source.zip`; it already
contains the patch, so do not apply the patch a second time. Retain the supplied
license files and build metadata.

The complete authoritative arguments are in the archived
`configure-module.ps1` and configure command record. The structure is:

```powershell
# Run from a fresh build-qml directory in an x64 MSVC developer shell.
& "$QtSdk/bin/qt-configure-module.bat" "$Source/qtdeclarative" -- -G Ninja `
  -C "$Recipe/msvc-initial-cache.cmake" `
  "-DCMAKE_PREFIX_PATH:PATH=$QtSdk" `
  -DCMAKE_BUILD_TYPE=Release `
  "-DCMAKE_INSTALL_PREFIX:PATH=$Stage" `
  -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL `
  -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF `
  -DQT_BUILD_TOOLS_BY_DEFAULT=OFF -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
# The original recipe also pins the absolute cl/link/lib/rc/mt/ninja paths.
cmake --build . --target Qml BuiltinsOutput --parallel 2
```

Use the included `install-qml-only.cmake` structure with paths rewritten to the
new build and staging directories. It invokes only the built Qml install
closure; invoking a whole-module install without building the other targets
does not reproduce this recipe. The original builder verifies that this
install script cannot recursively install other modules. Inspect and compare
the resulting DLL, import library, exports, dependencies and header retention
before composing a replacement SDK. Compiler versions and paths can change
binary hashes; the bundle does not promise a bit-identical rebuild on arbitrary
toolchains.

For the unmodified modules, the upstream archives retain their own configure,
CMake and build instructions. Build QtBase first, then the required module
dependencies. The included QtTools and QtShaderTools sources provide the
module tools needed by the corresponding build and translation paths. The
official platform instructions are at
[Building Qt 6 from Git](https://wiki.qt.io/Building_Qt_6_from_Git) and
[Qt for Windows](https://doc.qt.io/qt-6/windows.html).

## Generated translations

The installed `translations/qt_<locale>.qm` files are merged catalogs produced
by QtBase's `src/tools/windeployqt/main.cpp::deployTranslations`, using
QtTools `lconvert` and the catalogs from QtTranslations. They are not direct
copies of the SDK's same-named dependency-index files. The source lock contains
the measured deployed hashes from the actual Release package. A changed or
unknown catalog fails the bundle gate instead of being accepted as an
unverified SDK copy.

## Delivery and scope

Provide the complete source ZIP together with the actual EXE and preserve both
files with their SHA256 values. GitHub Actions artifacts in this workflow have
a finite retention period; an expiring artifact URL is not durable delivery.
No promise of a separate multi-year hosting service is made by this document.

This bundle covers the measured Qt module closure and its identified build
tools. OpenSSL, Microsoft runtime/compiler redistributables, Mesa
`opengl32sw.dll`, Wintun, fonts, Rust dependencies and Swirl's own code have
separate source and license provenance. Their presence is reported separately;
this Qt bundle does not claim that every product dependency or every legal
obligation has been verified.
