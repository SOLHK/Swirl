# Native TUN dependency and security review

Reviewed on 2026-10-29 against the Rust-only baseline `4ad8a23`. This review covers
the exact Cargo lockfile, the added packet-stack and Windows-binding packages,
and the separately distributed Wintun binary. It does not claim that Windows
adapter, network recovery, installer or application acceptance tests have run.

## Result and scope

The final lockfile passed `cargo-audit 0.22.2` with **zero vulnerability matches
and zero warnings**, with `--deny warnings`, no ignored advisories, no target
filter and yanked-package checking enabled. The official RustSec database used
was commit `ee1a49a2769a24a596afc1c20cb33748d2769586`, containing 1386 advisories.
Its commit timestamp is `2026-10-29T15:05:38+01:00`. This is a database-based
dependency check, not a claim that the code contains no undiscovered defects.

| Lockfile state | SHA-256 | Audit result |
| --- | --- | --- |
| TUN integration before the security updates | `bf1cfb27b617c7bee95a814e6948ee5e4cfd946080694136748aaed412005d3c` | Exit 1: 7 vulnerabilities, 10 unsoundness warnings |
| After the six minimum fixed-version updates below | `a2adc62304af61b3d9c4faf7935b5572783f295510719f45fef9d74185175941` | Exit 0: 0 vulnerabilities, 0 warnings |

All 17 initial findings applied to package versions already present in baseline
`4ad8a23`. None applied to one of the 17 newly added third-party packages. The
initial findings were still investigated and fixed because the TUN dispatcher
reuses these TLS, cryptography and MRS rule-loading paths. No advisories were
suppressed and no dependency feature was disabled to make the audit pass.

## Minimum security updates

| Package | Previous version | Selected fixed version | Declared license | Declared MSRV |
| --- | --- | --- | --- | --- |
| ctutils | 0.4.3 | 0.4.4 | Apache-2.0 OR MIT | 1.87 |
| rustls-webpki | 0.103.15 | 0.103.16 | ISC | 1.71 |
| webpki-roots | 1.0.9 | 1.0.10 | CDLA-Permissive-2.0 | 1.71 |
| zstd | 0.13.3 | 0.14.3 | BSD-3-Clause | 1.64 |
| zstd-safe | 7.2.4 | 8.2.0 | BSD-3-Clause | 1.64 |
| zstd-sys | 2.0.16+zstd.1.5.7 | 2.1.2+zstd.1.5.7 | BSD-3-Clause | 1.64 |

Only these six package versions changed in the security update; no package was
added or removed. The workspace's `webpki-roots` minimum is now `1.0.10`, and
`swirl-routing` requests `zstd = "0.14.3"`. The existing vendored rustls source
already accepts the fixed WebPKI release, so it required no source or dependency
constraint change. The new zstd family declares BSD-3-Clause; the dependency
inventory reflects the exact new declarations rather than retaining the old
MIT declarations.

The selected crates were downloaded from crates.io and their packaged manifests,
source and `.cargo_vcs_info.json` were inspected. Their recorded upstream
revisions are:

- [ctutils 0.4.4](https://github.com/RustCrypto/utils/tree/a993c0ba50db6510d8db15a6219572de65115438/ctutils).
  Mask conversion now goes through `Choice::to_u8()`'s optimization barrier;
  the 32-bit `u128` comparison special case is present.
- [rustls-webpki 0.103.16](https://github.com/rustls/webpki/tree/8ecdcc76f56b68fda67a6adf7976f5eed5006a4c).
  Certificate-path verification uses the distrusted-SPKI list, including the
  affected emSign intermediate keys, and includes a distrust regression test.
- [webpki-roots 1.0.10](https://github.com/rustls/webpki-roots/tree/70760478b9d3ea729b22faa0b5324da38a297c1c/webpki-roots).
  The affected emSign ECC Root CA G3 is absent from the generated roots.
- [zstd family](https://github.com/gyscos/zstd-rs/tree/75bc74045a2f6ea0439aeed7e159a266da20aac0).
  The zstd wrapper requires zstd-safe 8.2.0, which requires zstd-sys 2.1.2.
  Reused raw encoder/decoder contexts are reset on construction. The C zstd
  implementation remains version 1.5.7; the Rust wrapper/binding fixes are the
  relevant change.

### Actual Swirl call paths

`cargo tree -i ctutils` reaches `swirl-transport` through `hybrid-array`,
`module-lattice` and `ml-kem`. Both TLS certificate-verification and root-store
packages are in the existing production transport graph. Those findings cannot
be dismissed as unused test dependencies or as universally 32-bit-only issues.

The sole production zstd use is
[`ChinaRules::parse`](../crates/swirl-routing/src/mrs.rs): each invocation
creates a fresh `zstd::stream::read::Decoder`, then enforces the existing
decompressed-size bound while reading it. No Swirl production call uses shared
zstd contexts, dictionary training, seekable archives or the experimental API.
The resolved zstd-safe features before and after the update are `arrays`,
`legacy`, `std` and `zdict_builder`; `seekable`, `experimental` and `zstdmt` are
absent. In particular, legacy decoding was retained. These observations limit
the applicability of some findings, but do not remove any finding from the
unfiltered audit or justify retaining the vulnerable versions.

## Every initial RustSec finding

The following tables preserve all seven vulnerability findings and all ten
unsoundness warnings. The applicability statements describe the inspected Swirl
call sites and feature set; they are not a proof that every possible downstream
consumer of these crates was safe. Each advisory link is an official RustSec
source. All listed findings are resolved in the final lockfile.

### Seven vulnerability findings

| Advisory | Affected locked package | What was checked in Swirl | Fix selected |
| --- | --- | --- | --- |
| [RUSTSEC-2026-0385](https://rustsec.org/advisories/RUSTSEC-2026-0385.html) | ctutils 0.4.3 | Nonconstant-time masks can affect commonly used platforms; the additional `u128` issue affects 32-bit targets. The ML-KEM dependency path is active, so the issue is relevant to reused transport cryptography. | 0.4.4; advisory patched range `>=0.4.4` |
| [RUSTSEC-2026-0382](https://rustsec.org/advisories/RUSTSEC-2026-0382.html) | rustls-webpki 0.103.15 | Active TLS verifier could accept certificates chaining through distrusted emSign intermediates whose private keys are known. | 0.103.16; patched `>=0.103.16, <0.104.0-alpha.1` or `>=0.104.0-alpha.8` |
| [RUSTSEC-2026-0381](https://rustsec.org/advisories/RUSTSEC-2026-0381.html) | webpki-roots 1.0.9 | Active bundled root store permitted trust through the affected emSign root/intermediates. Updating both roots and verifier avoids relying on either change alone. | 1.0.10; patched `>=1.0.10` |
| [RUSTSEC-2026-0391](https://rustsec.org/advisories/RUSTSEC-2026-0391.html) | zstd 0.13.3 | Reusing an abandoned encoder/decoder context could expose earlier-stream bytes. MRS creates a new read decoder each time and does not use `with_context`; that specific trigger is absent. | 0.14.3; patched `>=0.14.3` |
| [RUSTSEC-2026-0398](https://rustsec.org/advisories/RUSTSEC-2026-0398.html) | zstd-safe 7.2.4 | `Seekable::decompress` could set a Vec length beyond capacity for invalid offsets. The seekable feature is absent and MRS has no seekable calls. | 8.2.0; patched `>=8.2.0` |
| [RUSTSEC-2026-0403](https://rustsec.org/advisories/RUSTSEC-2026-0403.html) | zstd-safe 7.2.4 | Failed legacy-frame streaming output can expose uninitialized bytes through the write decoder. Legacy support is enabled, but MRS uses the read decoder, which the advisory explicitly identifies as unaffected. | 8.2.0; patched `>=8.2.0` |
| [RUSTSEC-2026-0410](https://rustsec.org/advisories/RUSTSEC-2026-0410.html) | zstd-sys 2.0.16+zstd.1.5.7 | Allocation failure in the WebAssembly allocator shim can corrupt memory. That shim is not the Windows x64/ARM64 allocator path. It was still updated as part of the coherent fixed zstd family. | 2.1.2+zstd.1.5.7; patched `>=2.1.2` |

### Ten unsoundness warnings

All ten below refer to zstd-safe 7.2.4 and have the official patched range
`>=8.2.0`. The final version is 8.2.0. None was placed in an ignore list.

| Advisory | Unsafe behavior reachable through a safe API | Applicability to inspected Swirl path |
| --- | --- | --- |
| [RUSTSEC-2026-0405](https://rustsec.org/advisories/RUSTSEC-2026-0405.html) | Out-of-range `InBuffer::pos` causes an out-of-bounds read in seekable stream compression. | The seekable feature is absent; MRS does not use `SeekableCStream`. |
| [RUSTSEC-2026-0397](https://rustsec.org/advisories/RUSTSEC-2026-0397.html) | `OutBuffer::around_pos` can leave an uninitialized gap in a Vec. | Swirl does not call this API; the inspected zstd read-decoder implementation uses `OutBuffer::around`, not `around_pos`. |
| [RUSTSEC-2026-0401](https://rustsec.org/advisories/RUSTSEC-2026-0401.html) | Overflowing sample sizes passed to `train_from_buffer` cause an out-of-bounds read. | `zdict_builder` is enabled, so this is not dismissed on feature grounds. Swirl does not train dictionaries or pass sample-size arrays to this API. |
| [RUSTSEC-2026-0404](https://rustsec.org/advisories/RUSTSEC-2026-0404.html) | `DCtx::try_clone` can double-free the decompression context. | The experimental feature is absent; MRS creates fresh contexts and does not clone them. |
| [RUSTSEC-2026-0396](https://rustsec.org/advisories/RUSTSEC-2026-0396.html) | Seekable/seek-table access can dereference null or read outside the seek table. | The seekable feature is absent and there are no Swirl seek-table calls. |
| [RUSTSEC-2026-0399](https://rustsec.org/advisories/RUSTSEC-2026-0399.html) | `init_using_cdict` / `init_using_ddict` fail to retain dictionary lifetimes. | The affected experimental APIs are not enabled or called; MRS uses no dictionary. |
| [RUSTSEC-2026-0395](https://rustsec.org/advisories/RUSTSEC-2026-0395.html) | `StableInBuffer` lets the C encoder retain a borrowed input buffer after its lifetime. | The experimental feature is absent; Swirl never enables `StableInBuffer`. |
| [RUSTSEC-2026-0402](https://rustsec.org/advisories/RUSTSEC-2026-0402.html) | Cloning a multithreaded compression context can cause a heap buffer overflow. | Neither experimental APIs nor `zstdmt` are enabled; Swirl does not clone compression contexts. |
| [RUSTSEC-2026-0406](https://rustsec.org/advisories/RUSTSEC-2026-0406.html) | Changing a multithreaded context with an unfinished frame can free data still used by workers. | `zstdmt` is absent and there is no Swirl context/dictionary reconfiguration path. |
| [RUSTSEC-2026-0400](https://rustsec.org/advisories/RUSTSEC-2026-0400.html) | Mixing a one-shot decompression call into an open streaming context can leave a dictionary dangling. | MRS uses a fresh streaming decoder without a dictionary and does not mix one-shot/context-reuse calls. |

## New TUN dependencies

This is the exact third-party addition set against `4ad8a23`, independent of the
six security updates above. The feature graph was checked using the Windows
production target with `cargo tree -e normal,build`; the three defmt packages are
locked optional dependencies and are not in that production graph.

| Package | Version | Declared license | Use |
| --- | --- | --- | --- |
| smoltcp | 0.14.0 | 0BSD | TCP/IP state machine |
| managed | 0.8.0 | 0BSD | Stack storage adapter |
| heapless | 0.9.3 | MIT OR Apache-2.0 | Bounded stack collections |
| hash32 | 0.3.1 | MIT OR Apache-2.0 | Stack collection hashing |
| byteorder | 1.5.0 | Unlicense OR MIT | Wire/storage helpers |
| bitflags | 1.3.2 | MIT/Apache-2.0 | Stack flags |
| wintun | 0.5.1 | MIT | Windows driver binding |
| libloading | 0.8.9 | ISC | Controlled DLL loading |
| log | 0.4.34 | MIT OR Apache-2.0 | Binding diagnostics |
| c2rust-bitfields | 0.18.0 | BSD-3-Clause | Windows binding field layout |
| c2rust-bitfields-derive | 0.18.0 | BSD-3-Clause | Compile-time macro |
| syn | 1.0.109 | MIT OR Apache-2.0 | Compile-time macro support |
| thiserror | 1.0.69 | MIT OR Apache-2.0 | Binding error types |
| thiserror-impl | 1.0.69 | MIT OR Apache-2.0 | Compile-time macro |
| defmt | 1.2.0 | MIT OR Apache-2.0 | Optional; inactive in Windows production graph |
| defmt-macros | 1.2.0 | MIT OR Apache-2.0 | Optional; inactive in Windows production graph |
| defmt-parser | 1.1.0 | MIT OR Apache-2.0 | Optional; inactive in Windows production graph |

smoltcp is pinned exactly to 0.14.0 and its Rust 1.91 requirement is declared by
`swirl-tun`. Its source and release history were reviewed instead of retaining
an older stack solely to match the prior workspace minimum. The mature TCP
state machine handles sequence numbers, windows, retransmission and congestion
control. Swirl supplies bounded packet/stream admission and async adaptation.
See the [stack README](../crates/swirl-tun/README.md) for the separate IPv6
fragment adapter and explicit protocol boundaries. A version with no RustSec
matches still needs packet and Windows integration tests.

`netstack-smoltcp 0.2.4` was evaluated but not selected: its inspected implementation
uses unbounded accept/device queues, allocates on SYN before tuple deduplication,
and uses an older smoltcp series. The chosen adapter keeps memory admission and
backpressure in Swirl while leaving the TCP/IP protocol implementation upstream.

## Notice inventory and Wintun distribution

[`DEPENDENCIES.json`](../DEPENDENCIES.json) preserves the existing package schema
and now lists 207 third-party packages, including target/build dependencies and
vendored rustls. The initial refresh added 73 previously missing entries: the
17 new TUN packages and 56 packages already in the baseline lockfile. The security
update then replaced exactly six version entries. Nine workspace packages are
excluded from the third-party list. The complete lockfile audit counts all 216
packages.

The repository's [`Collect-RustDependencies.py`](../../tools/Collect-RustDependencies.py)
was run against `cargo metadata --locked --format-version 1` into a temporary
inventory/notice directory. The refreshed inventory retains its schema and
contains the same 207 packages and all of its recursively collected notices,
including ring's nested third-party notices. The refresh additionally records
the UNLICENSE files in byteorder and memchr, which the current collector's
filename patterns omit, and the Wintun/C2Rust supplemental records below.
Archive-local notice filenames do not assert that every file in an upstream
source archive is linked into Swirl.

The current collector does not preserve `runtime_artifacts`, `notice_sources`
or `supplemental_notices` when regenerating an inventory, and does not stage the
separate runtime/supplemental notices. Future generation and installer assembly
must retain those records/files explicitly or extend the collector. This review
does not modify that packaging tool or claim installer-license completeness.

The published archives for `c2rust-bitfields` and `c2rust-bitfields-derive` 0.18.0
omit the license file. Both identify upstream revision
`308da97f8ea6f76fc63d39e0fa84f0b28ee17622`. The complete
[upstream LICENSE](https://github.com/immunant/c2rust/blob/308da97f8ea6f76fc63d39e0fa84f0b28ee17622/LICENSE)
was saved as
[`C2RUST-BITFIELDS-0.18.0.txt`](../crates/swirl-platform/licenses/C2RUST-BITFIELDS-0.18.0.txt).
Its Git blob SHA-1 is `3c28b39d798e8b3cf69dbc284dcba7bf8ac3e0db`, matching the
upstream blob. Both metadata entries record the upstream URL and the supplemental
local notice. Their BSD conditions require keeping the copyright, conditions and
disclaimer with binary distributions; an empty archive-local notice list is not
permission to omit those terms.

The [official Wintun 0.14.1 ZIP](https://www.wintun.net/builds/wintun-0.14.1.zip)
was downloaded and its archive hash was checked before independently hashing its
DLLs. The Windows x64/ARM64 DLL hashes are part of the controlled loader's
allowlist and are recorded separately as runtime artifacts in the inventory.

| Artifact | SHA-256 |
| --- | --- |
| Official ZIP | `07c256185d6ee3652e09fa55c0b673e2624b565e02c4b9091c79ca7d2f24ef51` |
| `wintun/bin/amd64/wintun.dll` | `e5da8447dc2c320edc0fc52fa01885c103de8c118481f683643cacc3220dafce` |
| `wintun/bin/arm64/wintun.dll` | `f7ba89005544be9d85231a9e0d5f23b2d15b3311667e2dad0debd344918a3f80` |

The Rust `wintun` crate's MIT license does not cover the driver binary. The
official prebuilt-binary terms are preserved in
[`WINTUN-0.14.1.txt`](../crates/swirl-platform/licenses/WINTUN-0.14.1.txt). They
allow redistribution of the unmodified official binary alongside an application
using the permitted API, with the required notices. The driver source's GPL
license and the prebuilt-binary permission are different distribution choices.
No DLL was added to the repository. Installer distribution must include the
applicable notices and verify the selected official artifact; this review does
not assert that a final installer was produced or verified.

## Executed checks and reproduction

The dependency update required no MRS source changes. The unchanged routing test
suite passed **25 tests, zero failed and zero ignored**, including bundled MRS
parsing, ordered DIRECT/PROXY/REJECT behavior, IPv4/IPv6 CIDR rules, invalid
containers and the existing 64 MiB decompression-boundary test. These were local
Linux tests using the final lockfile. Windows build and whole-Core/TUN integration
results are recorded separately; a clean audit does not substitute for them.

Run from the repository root:

```sh
cargo test --manifest-path core/Cargo.toml -p swirl-routing --locked
cargo metadata --manifest-path core/Cargo.toml --format-version 1 --locked
cargo tree --manifest-path core/Cargo.toml --locked \
  --target x86_64-pc-windows-msvc -e normal,build
cargo tree --manifest-path core/Cargo.toml --locked \
  --target x86_64-pc-windows-msvc -e features -i zstd-safe

cargo install cargo-audit --version 0.22.2 --locked --no-default-features
git clone https://github.com/RustSec/advisory-db.git audit-db
git -C audit-db checkout ee1a49a2769a24a596afc1c20cb33748d2769586
cargo audit --file core/Cargo.lock --db audit-db --no-fetch --deny warnings --json
```

To reproduce the existing collector's package/notice portion without replacing
the reviewed inventory, redirect Cargo metadata to a temporary JSON file and run
`python3 tools/Collect-RustDependencies.py --metadata <metadata.json> --inventory
<temporary-inventory.json> --notices <temporary-notices-directory>`. Compare the
result while retaining the supplemental records described above.

`--no-default-features` on the audit-tool installation disables optional
executable-binary scanning support, not Cargo.lock security checks. `--no-fetch`
uses the reviewed advisory checkout; registry/yanked checks were not disabled.
For future acceptance, also run with the then-current official advisory database
and retain both the tool version and database revision in the evidence.
