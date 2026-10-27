# Qt 6.12 toolchain upgrade evidence

Scope: the `work/swirl-apec-v3-20261027` candidate, inspected on 2026-10-27 (Asia/Shanghai). This records toolchain and installer verification. It does not certify the complete Swirl 3.0 UI, a full application build, CI, an installer, or physical display performance.

## Version and source

Qt announced [Qt 6.12 LTS on 2026-09-30](https://www.qt.io/blog/qt-6.12-released). The [official release directory](https://download.qt.io/official_releases/qt/6.12/) inspected for this work contains stable 6.12.0. The application's CMake Qt requirements now select 6.12 or newer; the candidate's local/CI SDK is pinned to 6.12.0.

The Windows repository changed to architecture-specific metadata paths. `aqtinstall==3.3.0` discovered the wrong nested directory for this version in the actual installation attempt. `tools/Install-QtSdk.py` reads the official split repository directly, checks metadata and each archive against the official SHA256 sidecars, interprets only the allowlisted `Extract` destinations, and uses aqt's local relocation code after extraction. It never executes a downloaded Qt installer script.

- MinGW metadata: <https://download.qt.io/online/qtsdkrepository/windows_x86/desktop/qt6_6120/qt6_6120_mingw/Updates.xml>
- MSVC metadata: <https://download.qt.io/online/qtsdkrepository/windows_x86/desktop/qt6_6120/qt6_6120_msvc2022_64/Updates.xml>
- Verified MinGW metadata SHA256: `da865f86f4e2ec62ba24bcab10efd187b7ba2426255a82943c6f1cfba4c6578a`.
- Local installation: `D:/Codex/toolchains/Qt-6.12.0/6.12.0/mingw_64`.
- Actual installed qmake and CMake package version: **6.12.0**.
- The completed local SDK result contains **10 verified archives** and hashes of the checked SDK files in `D:/Codex/toolchains/Qt-6.12.0/sdk-install-result.json`.

The installation completed and an independent repeated installer invocation reported `Verified cached Qt 6.12.0 SDK`. This checked the current official metadata, package selection, installed version and stored key-file fingerprints. It did not claim every extracted SDK file was rehashed during the cache hit.

## Matching local compiler

The SDK metadata still mentions MinGW 13.1 and ships an archive with that runtime name. Its actual `config_qtbase.summary` reports **GCC 15.1.0**, consistent with the [Qt 6.12 supported-platform documentation](https://doc.qt.io/qt-6.12/supported-platforms.html). The compiler was therefore selected from Qt's own [6.12 Windows provisioning script](https://github.com/qt/qt5/blob/6.12/coin/provisioning/qtci-windows-11_24H2-x86_64/09-install-mingw1510_64.ps1), rather than inferred from the stale package dependency.

The matching toolchain is installed at `D:/Codex/toolchains/Qt-6.12.0/Tools/mingw64`; its actual `g++ -dumpfullversion` result is **15.1.0**. The archive source and Qt-provided integrity value are recorded by the installation research. The compiler archive uses Qt's published checksum; SDK metadata and SDK archives use the stricter SHA256 verification described above.

Local validation scripts put this compiler's `bin` ahead of Qt in the process PATH. After `windeployqt`, the three GNU runtime DLLs must be staged from the 15.1 toolchain into the new build directory and their hashes checked. The official Qt SDK directory remains unchanged for provenance. An executable-directory DLL takes precedence over PATH, so PATH ordering alone does not validate an already deployed runtime.

The old Qt 6.10.3 installation, old worktree and old CMake cache are preserved. The new application build uses an independent CMake directory and a separate reusable Cargo target directory. Local MinGW validation is separate from the repository's release policy, which requires x64 MSVC.

## Installer security validation

The final Python dependency pin is `py7zr==1.1.4`. Its [2026-10-13 release](https://github.com/miurahr/py7zr/releases/tag/v1.1.4) fixes a symlink-chain write escape and two archive parser/decoder denial-of-service issues that still affected 1.1.3. The installer enforces this minimum before processing archives. `requests` retains TLS certificate verification; XML is parsed with `defusedxml`.

`tools/tests/test_qt_sdk_installer.py` passed **7 tests** on the local Windows host, with all fixture paths beneath this task's `work/sdk-security` directory:

1. Parent traversal archive names are rejected before extraction.
2. Absolute, UNC, drive and Windows ADS archive names are rejected.
3. A symlink archive entry is rejected before extraction.
4. A normal small 7z fixture extracts successfully inside the selected root.
5. A real pre-existing Windows junction cannot redirect the installation destination or an archive member outside that root.
6. Metadata cannot choose an arbitrary or parent-relative extraction destination.
7. XML external entities are rejected without reading the referenced fixture.

The malicious member-list checks use a controlled archive metadata stub to verify refusal before `extractall`; the ordinary archive roundtrip and filesystem junction are real. The tests never attempt to write outside their task fixture or modify an installed SDK. The audit identified the pre-existing-junction boundary and the py7zr dependency issue; both are addressed in the current source and covered by these checks.

## CI and delivery gates

`.github/workflows/build-qt-quick-ui.yml` adds only this development branch to its existing push scope. The separate network-candidate workflow does not add this branch, avoiding a duplicate package job. The UI workflow uses the same official SDK downloader with `win64_msvc2022_64`, separately builds UI-test and production executables, and preserves its existing CTest, interaction, capture and all-page smoke gates.

The workflow also checks all six generated brand SVG variants, runs the installer boundary tests, includes the missing 175% preview alongside 100/125/150/200%, and records source SHA, SDK version, application/installer version equality and installer SHA256. Cached Qt and compiler outputs use Qt- and toolchain-specific keys; tracked input timestamps are reused only after content verification. The production staging policy remains unchanged and rejects UI-test builds or mismatched MSVC Rust identities.

Workflow validation actually completed: `actionlint` passed and all 15 multiline PowerShell blocks in the Windows build job parsed successfully. The local build scripts also parsed successfully. These are syntax and boundary checks, not a successful GitHub Actions run.

The new local Qt 6.12/GCC 15.1 CMake configure and `swirl-generate-icon` compilation subsequently passed. The integrated brand checks inspected 36 native ICO frames across four variants, checking dimensions and alpha and producing a visual contact sheet. Full Swirl compilation is still in progress at the time of this document; broad application regression, Windows EXE packaging and new-commit CI remain pending. Physical 60/120Hz rendering, GPU measurements and desktop/DPI visual acceptance remain separate manual or hardware tests. The candidate must not be reported as a finished Swirl 3.0 release from this toolchain evidence alone.
