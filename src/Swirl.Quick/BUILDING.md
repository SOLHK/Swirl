# Windows Rust-only product build

The desktop requires Windows x64, Qt 6.12.0, CMake 3.25+, Cargo and a C++23
compiler matching the Qt kit. Rust is the only product runtime. Importing a
Clash/Mihomo subscription does not install or execute an external core.

For the MSVC packaging wrapper, run
`scripts/build-quick-windows.ps1 -QtDir <Qt-MSVC-x64-directory>` from an x64
MSVC developer shell. This script currently requires an MSVC Qt kit and Rust
`x86_64-pc-windows-msvc`. Output defaults to `D:\Codex`; use fresh distribution
and output directories. `-InputTests` uses a separate test build;
`-PortableOnly` omits NSIS.

Direct CMake builds also support the Qt 6.12.0 GCC 15.1.0 MinGW kit, paired with
Rust `x86_64-pc-windows-gnu`. Use that kit's compiler environment and a separate
build cache. Do not pass a MinGW kit to the MSVC-only wrapper, mix Qt runtimes,
or copy a Rust DLL manually from another build.

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
