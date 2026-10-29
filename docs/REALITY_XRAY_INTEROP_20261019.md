# REALITY R3: pinned mature Xray / REALITY interoperability

This stage adds a reproducible, mandatory upstream-peer gate after the native
REALITY R2 implementation. Development and pushes use only
`work/core-completion-20261017`, starting from `271ed3f5d2abe185a7b3308dd77f00b904bc58be`.
The source SHA and completed Actions results are recorded below and in the
current handoff; local results and triggered workflows are recorded separately.

## Delivered code

| File | Actual responsibility |
| --- | --- |
| `tools/Build-XrayPeer.py` | Verify official source identity and lock files; build the full Xray executable and isolated peer from source; verify modules and repeat both builds with matching digests |
| `tools/tests/xray_peer/lock.json` | Exact upstream commit/tree, original module-file SHA-256, REALITY module checksums and Go version |
| `tools/tests/xray_peer/main.go` | Loopback fixture using the unmodified official Xray REALITY server wrapper; fresh credentials, actual wire observations and owned cleanup |
| `tools/tests/test_reality_xray.py` | Native Rust versus mature upstream TLS interoperability, strict identity checks and raw outcome/lifecycle artifacts |
| `core/crates/swirl-transport/examples/reality-client.rs` | Bounded caller-owned timeout/cancellation and portable socket timeout handling in the existing native test executable |
| Rust and Core implementation workflows | Mandatory source build and peer tests on Linux, macOS, Windows and the App validation job, with failure evidence uploaded unconditionally |
| `tools/ApplyCoreDevelopment.py`, its tests | Atomic, idempotent CI migration; reject missing, partial, duplicated or weakened upstream gates; actually execute a failing-build shell body to verify fail-before-peer behavior |

The App workflow checks out its triggering SHA. Its source archive now also
contains the builder and workflows, so those test inputs are retained alongside
the Rust/Go/Python sources. The existing Windows Qt and full native application
build remain required. No product UI, font, importer or runtime capability is
changed by this stage.

## Fixed independent counterpart

- Official Xray `v26.10.17`: `92ccc939aaf4f8965f369cf0b142e005aeaa11d5`.
- Official REALITY: `83f621788ca88b83179810b12baa7ae518aacb83`, module version
  `v0.0.0-20261014101318-83f621788ca8`.
- Go `1.27.2`, with automatic toolchain replacement disabled. The new setup-go
  action is pinned to `924ae3a1cded613372ab5595356fb5720e22ba16`.
- The original upstream `go.mod` and `go.sum` are unchanged. The builder checks
  their SHA-256, the exact Git tree and the REALITY ZIP/module `h1` sums, and runs
  `go mod verify` before and after compilation.
- Both executables are rebuilt to distinct output filenames. Same-platform,
  same-toolchain digests must match. Compiler-cache reuse is allowed and is
  explicitly not an independent cross-builder attestation.

No unidentified prebuilt Xray executable is accepted. The Go code is test-only
instrumentation around upstream APIs; it is neither a Rust product dependency
nor a replacement core in a product path. Detailed sources, licenses and the
fixture interface are in [the peer README](../tools/tests/xray_peer/README.md).

## What is exercised

The 12 test methods create 13 independent loopback sessions. Positive sessions
require native REALITY client authentication, the actual TLS 1.3 handshake and
both Finished messages, agreement on the wire-selected key-exchange group and
cipher suite, exact byte counts/digests in both directions, and both authenticated
TLS closes. They include X25519 and X25519MLKEM768, a 1 MiB binary payload,
small and single-byte socket operations, and an empty application session.

The negative cases reject wrong short IDs and static server keys before any
application bytes reach either the REALITY peer or its camouflage target.
Another case finishes a valid echo, then deliberately closes the raw server
socket without TLS `close_notify`: Rust must report `UnexpectedEof`. Four
cases expire or cancel handshake/data I/O, verify the peer observes transport
release, and require zero remaining tracked connections, reaped processes and
closed listeners. These are caller/harness lifetime tests; the production async
REALITY adapter is still a separate task.

The official server path does not fill `ConnectionState.CurveID`. The fixture
therefore reads the actual plaintext ServerHello emitted on its socket, using a
bounded observer, and cross-checks its TLS version and cipher against the
completed upstream connection. It never fills in the requested configuration
value as if it were a negotiated result. TLS EOF is also cross-checked against
an independent raw-socket EOF observation, because upstream tolerates certain
record-boundary TCP closes.

## Actual local checkpoint

The R3 Rust snapshot is isolated from concurrently developed Vision R2 files.
Cloud Linux, Rust 1.99.1, Python 3.12 and cryptography 50.0.2 were used.

| Gate | Result before the first source push |
| --- | --- |
| `cargo fmt --all -- --check` | Passed |
| `cargo check --workspace --locked` | Passed |
| Strict all-target Clippy | Passed |
| `cargo test --workspace --locked` | 239 unit/integration tests and one doctest passed; zero ignored/failed |
| Workspace Release and native REALITY example Release builds | Passed |
| Existing independent REALITY peer / TLS regression | 16 and 19 passed, no skips |
| CI anti-regression suite | 37 passed, no skips |
| New pinned Xray TLS interoperability suite | 12 passed, 13 sessions, no errors/failures/skips |
| Repeated upstream builds | Both actual executable SHA-256 comparisons matched |
| GitHub Actions | Pending at that local checkpoint; the subsequently completed exact-source runs are recorded below |

The first workspace test compilation exhausted the shared disk before tests
could execute. Its raw failure is preserved. After removing inactive,
rebuildable incremental caches, the same source passed with local debug symbols
and incremental compilation disabled; no test or assertion was removed.
The first real upstream run also failed at the missing CurveID observation;
that failure is preserved separately from the corrected wire-observed result.
Earlier source/binary mismatch refusals were provenance-gate failures and are
not counted as executed interoperability tests.

## Exact committed CI

Source [`5ad68bcb22a23573d462cbfd972c7120093f504a`](https://github.com/SOLHK/Swirl/commit/5ad68bcb22a23573d462cbfd972c7120093f504a),
tree `b82dc554aadd144f8745b9ec7763915cfbae4933`, passed
[Rust run 39239280852](https://github.com/SOLHK/Swirl/actions/runs/39239280852)
on Linux, macOS and Windows, and
[App run 39239280949](https://github.com/SOLHK/Swirl/actions/runs/39239280949).
Both workflows completed with `success`; each peer invocation passed all 12
tests / 13 sessions, with no failures, errors or skips. Downloaded evidence ZIPs
matched their GitHub artifact digests, and their test/source/build identities
matched this exact SHA. Both upstream executable rebuild comparisons matched.

Permanent result and lifecycle records:
[Linux](evidence/reality-r3/ci-linux.json),
[macOS](evidence/reality-r3/ci-macos.json),
[Windows](evidence/reality-r3/ci-windows.json), and
[App](evidence/reality-r3/ci-app.json).
Each Rust platform passed 239 unit/integration tests and one doctest. Windows
also completed its compatibility/native Qt tests, dedicated injected-peer
wrappers and the full native `Swirl.exe` build. Its generic Qt entry retained
six explicitly separate peer-injection skips; the subsequent five wrappers
exercised those six slots. This is not physical GUI or provider acceptance.
The App source archive's 226 files matched the exact commit's Git blobs and modes.

The complete local portable Python menu separately recorded 248 passes and
five explicit Qt-hook skips, before adding the 12 new Xray cases; its original
[suite results](evidence/reality-r3/local-regression-summary.json) are retained.
The local skips were not relabeled as passes.

## Deliberate remaining boundaries

The controlled camouflage target is a local TLS 1.3 Ed25519 chain with no tickets
or application traffic. The fixture initializes upstream's target-observation
cache with that known empty post-handshake record list, avoiding background
target probes. It does not test arbitrary public cover sites or ticket behavior.

This is mature Xray/REALITY **TLS component** interoperation. Building the full
Xray executable does not itself verify its VLESS configuration path. Browser
fingerprints, additional certificate profiles, complete VLESS/Vision forwarding,
subscription-to-IR-to-route-to-runtime-to-Qt execution and real providers remain
unaccepted. Existing explicit product refusal is preserved; there is no DIRECT
fallback, ordinary-TLS downgrade or private subscription request.

The fixed baseline remains **79 items, six fully accepted, weighted 10.83%**.
These component checks do not complete the full B13/B14 acceptance criteria.

