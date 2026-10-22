# REALITY import intent cannot become ordinary TLS

## Source and reproduced defects

This bounded stage starts from `df7fd069fafaaf7e767946617d22ae7270d3b09c`
on `work/core-completion-20261017`. The remote HEAD and Actions were reread
before development; no newer commit existed. No private source was refreshed.

The Qt URI importer could discard `security=reality` when its public-key field
was absent, leaving an executable ordinary TLS node. The sing-box importer
silently converted malformed TLS/reality/uTLS objects or boolean values to
empty objects/false. An enabled uTLS configuration with no fingerprint lost
its fingerprint requirement rather than retaining sing-box's Chrome default.

`SubscriptionNormalizer.cpp` now rejects malformed/conflicting security inputs,
requires a nonempty REALITY credential, and preserves the explicit fingerprint.
Valid REALITY and Vision options remain in the existing source-preserving import
path. Current native configuration rejects them before opening a socket.
This change does not implement either REALITY or Vision.

Two `ImportTests` slots cover URI/Base64 ordering, mixed lists, malformed JSON
types, defaults, accepted field preservation and redacted diagnostics. They are
registered in the existing native and compatibility `swirl-import-boundaries`
CTest. A `RustCoreTests` slot verifies actual native startup returns
`InvalidOptions`, leaves no process/API alive and makes zero endpoint connections.
The existing persistence rejection test additionally covers these malformed
documents; the complete persistence cases require Windows CI.

## Local verification

Cloud Linux, Rust 1.99.1, Qt 6.10.3, GCC 13.3. Public synthetic fixtures only.

| Gate | Observed result |
| --- | --- |
| Same three Qt regression slots with original `df7fd06` normalizer | 3 failed, 0 skipped |
| Same slots with repaired production normalizer | 3 passed, 0 failed, 0 skipped; 38 ms |
| `cargo fmt --all -- --check` | Passed |
| `cargo check --workspace --locked --offline` | Passed |
| `cargo clippy --workspace --all-targets --locked --offline -- -D warnings` | Passed |
| `cargo test --workspace --locked --offline` | 154 passed, 0 failed, 0 ignored |
| `cargo build --release --locked --offline --workspace --lib --bins` | Passed; actual Release libraries and executables |

The Qt subset uses verbatim test slots and real NodeImporter/Normalizer/Registry/
RustCoreEngine sources. Lifecycle init/cleanup are not counted as substantive
regressions. It is not the complete Windows product test. Baseline XML SHA-256:
`039eae83ae273e5d3d79d0932bc25718d5f96e8bdd26cce660f8ac7bf4e26eaf`.
Repaired XML SHA-256:
`cebd7a455406457c20dd1575a26968613e8c07cd116fa2796ac641c8be3e9420`.

Two environment failures remain recorded: initial sandbox socket denial, and
a shared Cargo target-directory collision between separate source checkouts.
Granting local test socket access and using an isolated target directory resolved
them without changing product code, timeouts or assertions. Exact-commit Actions
results are recorded below; earlier green runs cannot substitute.

## References and ownership

- [Xray share-link field contract](https://github.com/XTLS/Xray-core/discussions/716):
  explicit security selection, required REALITY public key and query ordering.
- [sing-box TLS schema](https://sing-box.sagernet.org/configuration/shared/tls/):
  typed objects/booleans and enabled-uTLS fingerprint default.
- [Pinned sing-box REALITY semantics](https://github.com/SagerNet/sing-box/blob/dfb80349bf5779ec0a3f834c9ec2794345bff8f0/common/tls/reality_client.go).
  This GPL-3.0-or-later project was read only for observable behavior; no source
  was copied or linked. No dependency was added by this repair.

The fixed acceptance baseline remains 79 items, 6 accepted, 10.83% accepted
weight. No protocol, complete private profile, provider or physical-device
acceptance is claimed. Font implementation and physical DPI/240 Hz checklist
remain unchanged. Follow-up work is the separately bounded REALITY cryptographic
foundation and the TLS backend's pre-transcript ClientHello integration.


## Exact-source CI verification

Implementation commit `4d73f6574bf9884dc4e173b58708ae543b2303bd`, tree
`5830fc0fa64a8444232b4a05b16cd252722aa2e2`, passed
[Rust CI 39198976897](https://github.com/SOLHK/Swirl/actions/runs/39198976897),
[App validation 39198976919](https://github.com/SOLHK/Swirl/actions/runs/39198976919)
and [font validation 39198976888](https://github.com/SOLHK/Swirl/actions/runs/39198976888).
Actual checkout logs, App tested-commit identity and downloaded Qt/font reports
were checked, not only workflow badges.

| Gate | Exact observed result |
| --- | --- |
| Linux and macOS, each | 154 Rust passes; 197 Python passes, 5 explicit Qt-hook skips; no failures |
| Windows Rust | 154 passes; fmt/check/Clippy/Release succeeded |
| Windows native integration XML | 46 substantive passes, 6 explicit independent-peer skips, no failures |
| Native / compatibility import XML | 10 passes in each mode; both new import functions and persistent-invalid-input regression passed |
| Compatibility native-DNS guard XML | 2 passes, no failures |
| Native / compatibility CTest | 3/3 and 2/2 passed respectively |
| Separate Python Qt peer hooks | All 5 passed; they exercise 6 Qt peer slots separately from the unmodified XML skip counts |
| Complete native application | `Swirl.exe` built successfully on Windows 2022, Qt 6.10.3 / MSVC x64 |
| App validation | Actual source `4d73f65`; 154 Rust and 94 Python passes including 25 workflow guards, 5 skips; the narrower App menu is not the full portable menu |
| Font / compatibility application | 50 substantive font passes, 8 explicit skips, 61/61 ready navigation requests and application build success; physical display acceptance remains false |

The Qt artifact `12163931998` ZIP SHA-256 is
`e79caec9559b4db1600cba20e9ec8037096f20fec5c7c5b24e78d8ae4798d8a7`.
The source-specific font artifact `12163377916` ZIP SHA-256 is
`a6bbb0bb222129771a45e043a06386ac012c052a427409a8c49121cd334ae370`.
Per-report hashes, all explicit skips and later source-stage failures are retained
in [the permanent session evidence](evidence/REALITY_FOUNDATION_AND_IMPORT_20261019.json).
This CI proves the import refusal and existing supported paths, not REALITY/Vision
execution or complete private-subscription compatibility.
