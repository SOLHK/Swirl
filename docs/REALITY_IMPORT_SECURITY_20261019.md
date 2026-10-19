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
results will be added after the source push; earlier green runs cannot substitute.

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
