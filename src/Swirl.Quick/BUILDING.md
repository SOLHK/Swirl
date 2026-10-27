# Windows Rust-only product build

Run `scripts/build-quick-windows.ps1 -QtDir <Qt-MSVC-x64-directory>` in an x64
MSVC developer shell. Output defaults to `D:\Codex`; use a fresh distribution
and output directory. The product requires Cargo, Rust x86_64-pc-windows-msvc,
the pinned Qt 6.12.0 MSVC x64 SDK (or a newer validated compatible SDK), CMake, and Ninja. `-InputTests` uses a separate test build.
`-PortableOnly` omits NSIS. Never copy a DLL manually from an older build.

Cargo is a mandatory dependency of Swirl. The DLL and EXE carry a shared
content build ID and source revision. Staging checks their actual loader/ABI
and performs HTTP, CONNECT and SOCKS5 loopback requests using the real EXE.
The GUI smoke check then runs from an unrelated working directory.

Windows/public protocol acceptance and limitations are recorded in
`docs/R1_RUNTIME_CAPABILITIES.md` and the R1 workflow's exact-SHA evidence.
A local loopback request is not proof that a private subscription node works.

No external-core installer, archive, control API or compatibility runtime
exists. Clash YAML remains an accepted subscription data format.
