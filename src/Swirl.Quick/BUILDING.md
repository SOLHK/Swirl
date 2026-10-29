# Windows Rust-only product build

The desktop requires Windows x64, Qt 6.12.0, CMake 3.25+, Cargo and a C++23
compiler matching the Qt kit. Rust is the only product runtime. Importing a
Clash/Mihomo subscription does not install or execute an external core.

For the MSVC packaging wrapper, run
`scripts/build-quick-windows.ps1 -QtDir <Qt-MSVC-x64-directory> -OpenSslRoot <verified-runtime-directory>` from an x64
MSVC developer shell. This script currently requires an MSVC Qt kit and Rust
`x86_64-pc-windows-msvc`. Output defaults to `D:\Codex`; use fresh distribution
and output directories. `-InputTests` uses a separate test build;
`-PortableOnly` omits NSIS.

Direct CMake builds also support the Qt 6.12.0 GCC 15.1.0 MinGW kit, paired with
Rust `x86_64-pc-windows-gnu`. Use that kit's compiler environment and a separate
build cache. Do not pass a MinGW kit to the MSVC-only wrapper, mix Qt runtimes,
or copy a Rust DLL manually from another build.

## Windows TLS runtime

Build the pinned OpenSSL 3.5.9 runtime before deploying Qt. The repository's
`tools/openssl-runtime.lock.json` pins the official source archive URL, SHA256
and license hash. `tools/Build-OpenSslRuntime.py` verifies these inputs, builds
the unmodified shared libraries with assembly enabled and verifies the actual
DLL version and TLS initialization. Its receipt records compiler/tool hashes;
it is build evidence, not an independent signature attestation. Do not copy
OpenSSL from Git, Poppler, another application or an unrelated Qt kit.

For MSVC, enter an x64 Visual Studio developer shell with native Windows Perl,
NASM, `cl.exe` and `nmake.exe` on PATH, then run from the repository root:

```powershell
python tools/Build-OpenSslRuntime.py --output D:/Codex/build/swirl-openssl-msvc --target VC-WIN64A
./scripts/build-quick-windows.ps1 -QtDir <Qt-MSVC-x64-directory> -OpenSslRoot D:/Codex/build/swirl-openssl-msvc
```

The other packaging entry points (`Build-WindowsRustProductInstaller.ps1`,
`build-current-portable.ps1` and `build-network-candidate.ps1`) require the same
explicit `-OpenSslRoot`. The build reuses a runtime only when its source,
recipe and current toolchain identities match; it validates cached files again.

For a direct MinGW build, use MSYS2 Perl, GNU make and `sh.exe` with the native
Qt x64 MinGW `gcc.exe` and matching GNU assembler. Native Strawberry Perl is
for the MSVC target; it cannot configure the MinGW target. Build a separate
runtime with `--target mingw64`, then deploy into that build's application
directory:

```powershell
python tools/Build-OpenSslRuntime.py --output D:/Codex/build/swirl-openssl-mingw --target mingw64
./scripts/Copy-VerifiedOpenSslRuntime.ps1 -OpenSslRoot D:/Codex/build/swirl-openssl-mingw -ApplicationDirectory <application-directory> -Target mingw64
windeployqt --release --compiler-runtime --openssl-root D:/Codex/build/swirl-openssl-mingw --include-plugins qopensslbackend --qmldir src/Swirl.Quick/qml <application-directory>/Swirl.exe
```

`Copy-VerifiedOpenSslRuntime.ps1` validates the runtime with `--verify-only`
before copying the two DLLs, unchanged upstream license, provenance notice and
receipt. The application must include `Qt6Network.dll`,
`tls/qopensslbackend.dll`, `libssl-3-x64.dll` and `libcrypto-3-x64.dll` from
its own distribution. After staging, run
`Swirl.exe --tls-runtime-self-test <report-path>` with a clean PATH containing
only the application, matching compiler runtime and Windows system directories.
It performs no network requests and must report the expected default backend,
version and loaded module paths. This deployment check does not replace actual
HTTPS, certificate rejection or ALPN tests. Production staging and finalization
also require the fixed TLS file set, recorded hashes, source pin and matching
Rust/SSL compiler target; a manifest cannot omit these dependencies.

Cargo is mandatory: CMake pairs the Rust library with the product's source SHA
and content build ID on each incremental build. Configure QA with
`SWIRL_BUILD_UI_TESTS=ON` or `SWIRL_BUILD_CORE_TESTS=ON`, and select critical
tests for the changed components. Run OS proxy mutation tests only in disposable
environments; do not change the user's working proxy, TUN, routes or DNS.

Configure production in a different directory with both test options OFF.
Staging checks the actual loader/ABI and performs HTTP, CONNECT and SOCKS5
loopback requests using the real EXE. The GUI smoke check runs from an unrelated
working directory. Finalization verifies payload hashes and rejects external
proxy executables, test binaries and private data before NSIS packaging. Qt,
Rust and other required dependency notices remain part of the product.

Runtime boundaries are recorded in `docs/R1_RUNTIME_CAPABILITIES.md`; dated
reports retain their original source and scope. Delivery must report the final
commit, executed tests, failures, skips, remaining acceptance gaps and installer
hash. A local loopback request is not proof that a private subscription node or
Codex Desktop works. Native UI, taskbar and DPI checks require actual Windows
evidence; compilation and controlled scale renders alone do not accept them.

No external-core installer, archive, control API or compatibility runtime
exists. Clash YAML remains an accepted subscription data format.
