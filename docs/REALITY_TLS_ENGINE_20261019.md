# REALITY R2: authenticated native TLS 1.3 record channel

## Implemented boundary

This stage continues from remote HEAD
`a7e872d0f046dcd66614704555cd0b569ac4a7a4` on
`work/core-completion-20261017`. The branch, history and Actions were reread
before development. No newer commit was present at that checkpoint.

The final precommit reread found concurrent font change
`1102f31a1fadc706794a17366ff45cb675669449`. It was fast-forwarded and preserved
before committing R2. Its 12 files do not overlap the 16 R2 files; none changes
the Rust or Python peer sources used by the local checks. New exact-source CI
must verify the combined application, including that concurrent font code.

`swirl_transport::reality::TlsClient` now constructs an authenticated REALITY
ClientHello, completes the actual TLS 1.3 key schedule, authenticates the server,
and exchanges protected application records with an independent Python peer.
This is an executable native TLS engine. The existing Qt, subscription, routing
and runtime gates still reject REALITY/Vision outbounds: the engine does not
claim a Chrome fingerprint, implement VLESS/Vision, or enable a product node.
No failure falls back to DIRECT or ordinary TLS.

| File | Responsibility |
| --- | --- |
| `core/crates/swirl-transport/src/reality/backend.rs` | Two offline rustls constructions with one real key owner, authenticated first-flight identity and a bounded native TLS 1.3 profile |
| `core/crates/swirl-transport/src/reality/client.rs` | First ServerHello gate, exact-record input, actual TLS processing, Finished-gated application I/O, backpressure and close state |
| `backend_tests.rs`, `client_tests.rs` | Ownership, transcript, authentic TLS server exchange, malformed input, fragmentation and terminal failure regressions |
| `core/crates/swirl-transport/examples/reality-client.rs` | Bounded loopback-only test executable, structured input and redacted outcome |
| `tools/tests/reality_peer.py` | Independently implemented Python/OpenSSL REALITY authentication, hybrid/classical TLS 1.3, record encryption and echo peer |
| `tools/tests/test_reality_peer.py`, `test_reality_tls.py` | Independent known answers and real Rust-to-Python socket interoperability |

Generic TLS remains in the existing `secure()` function in
`core/crates/swirl-transport/src/lib.rs`. No Rust dependency, proxy-core
dependency, Qt/QML implementation or font implementation is added by R2.

## ClientHello and ownership

The locked rustls 0.23.46 constructor creates its ClientHello transcript and
send queue synchronously. It has no direct single-construction public setter
for the REALITY SessionID. Rewriting already generated socket bytes would give
the peer and the client different transcripts.

The adapter first constructs a preview entirely in memory. Its key-exchange
object contains public bytes only and refuses both completion methods. The real
fresh X25519/ML-KEM key owner remains in Swirl. After the preview is discarded,
the existing authentication API consumes that owner and seals the SessionID.
The final constructor receives the sealed ID, identical random/order bytes and
the sole live key object, moved by value exactly once. Both the complete final
handshake and its full TLS first flight must match the expected bytes before
anything can be returned to a caller or written to a socket.

A private synchronous thread-local construction scope supplies exactly the
constructor's three entropy requests: 32-byte SessionID, 2-byte extension order,
32-byte ClientRandom, then one key start. Incorrect shape/order, extra calls,
missing calls or reentry fail. Its RAII guard cannot cross threads and clears
the state on success, error or unwind. There is no global session queue, cloned
private key, exported secret seed or per-connection leaked provider. Four-thread
tests verify isolation of fresh random bytes, SessionIDs and key shares.

This explicit dependency contract is intentionally checked by tests and at
runtime. A future rustls change must be reviewed; bypassing these checks is not
a supported upgrade strategy. Swirl's bounded ServerHello validator runs before
rustls can consume the real key owner, enforcing SessionID echo, offered suite
and group, exact lengths, TLS 1.3 and the explicit refusal of HelloRetryRequest.

## Authentication, records and closure

The engine uses the existing pinned-server authentication key and strict
REALITY HMAC certificate verifier. Ed25519 CertificateVerify signs the genuine
TLS transcript; rustls separately verifies server Finished before this API
accepts application writes or releases application plaintext. An authenticated
certificate alone cannot make the session ready.

The native profile supports the three existing ring TLS 1.3 suites:
AES-128-GCM/SHA-256, AES-256-GCM/SHA-384 and ChaCha20-Poly1305/SHA-256. The first
offer contains genuine X25519MLKEM768 and its same-owner X25519 component.
Either offered group can be selected; an unoffered group cannot. Session
resumption, early data, certificate compression, ticket requests and client
authentication are disabled. TLS 1.2 and HRR are explicitly unsupported.

ALPN is preserved as ordered bytes, with at most 16 distinct protocols, each
1–255 bytes, and at most 1024 protocol bytes in total. Server selection must be
offered. SNI remains an explicit DNS name under the prior narrow foundation
profile. Browser fingerprint emulation, ML-DSA certificate extensions, other
certificate extensions/chains/OCSP and ordinary CA-cover fallback remain
unsupported. The native ClientHello must never be renamed `chrome` to satisfy
an imported fingerprint requirement.

The caller owns the transport, timeout and cancellation. The engine reads only
the remainder of one record header or body; it never reads into the next record.
It permits at most 16 KiB of plaintext record content or 16 KiB + 256 bytes of
ciphertext, a 64-record/16 KiB first ServerHello budget, and a 128-record/256 KiB
handshake input budget. rustls receives complete, previously bounded input with
at most 16 positive-progress deframer steps per record; its buffer limit is
64 KiB. Input is not allocated from an unchecked length.

Partial reads/writes, `WouldBlock` and `Interrupted` retain exact offsets.
Non-retryable I/O errors preserve their first error and poison the connection.
A zero write with pending output returns `WriteZero`; a failed attempt cannot
later release data. Application writes after local `close_notify` are refused,
while the reverse direction can still be read. EOF in a handshake/partial record
fails; application EOF without authenticated `close_notify` remains an explicit
unclean-close error. Cancellation drops the attempt and all its owned state.

The loopback test executable has a separate 15-second I/O deadline, bounded
input/payload and I/O counts, and no subscription or arbitrary-host access. Its
large echo transfers interleave reads and writes to avoid an all-write-first
backpressure deadlock. These harness bounds do not imply that the future async
product adapter has already implemented timeout, cancellation or Vision handoff.

## Independent tests and actual local checkpoint

Python cryptography 50.0.2/OpenSSL supplies a distinct implementation of X25519,
ML-KEM encapsulation, HKDF, AEAD and Ed25519 for the peer. It authenticates the
actual ClientHello received from Rust, creates a fresh server exchange, checks
the client's real Finished, echoes application bytes and validates both closes.
The 16 peer self-checks include prior independently generated authentication and
SHA-256/SHA-384 transcript vectors plus the exact TLS Finished record from
RFC 8448. No expected wire output is generated by invoking the Rust client.

The 19 live test methods cover six suite/group combinations, exact ALPN,
1/3/7-byte socket operations, encrypted handshake fragmentation, empty payload,
16 KiB and 32,769-byte payloads. Negative cases require the client's precise
failure stage and error as well as zero Finished/application acceptance on the
peer: wrong static key, authenticated wrong short ID, wrong certificate HMAC,
wrong CertificateVerify, wrong Finished, wrong SessionID echo, HRR and unoffered
ALPN. A separate case proves that successful echo followed by TCP EOF is not
authenticated TLS closure.

This native profile advertises Ed25519 signatures only. A real camouflage TLS
target must support that offer; a target with only an RSA/ECDSA certificate is
outside this profile. Supporting cover-target signature offers while retaining
strict REALITY authentication is a separate negotiation task, not a reason to
accept an ordinary certificate or claim a browser fingerprint.

Initial local gates on cloud Linux, Rust 1.99.1 and Python 3.12.14:

| Gate | Observed result |
| --- | --- |
| Cargo fmt/check/Clippy with `-D warnings` | Passed |
| Workspace tests | 216 unit/integration tests + 1 compile-fail doctest passed; zero failures or ignored tests |
| New Rust tests | 28 passed, including 13 backend and 15 record/API tests |
| Workspace Release library/bin build | Passed |
| Separate Release `reality-client` example build | Passed |
| Debug example with independent Python peer | 19 passed, zero failures/skips |
| Release example with independent Python peer | The same 19 passed, zero failures/skips; separately built and hashed binary |
| Independent Python peer self-checks | 16 passed, zero failures/skips |
| Release protocol, DNS, policy and subscription peer menu | 211 passed, zero failures; five explicit unavailable Qt hooks (workflow-guard tests recorded separately) |
| Actual Rust 1.89.0 minimum-version check | Workspace and all targets passed with the locked, offline dependency set |
| CI workflow guard | 28 passed, zero failures/skips; checked-in Rust workflow update is byte-for-byte idempotent |

Two existing UDP tests initially hit the cloud sandbox's socket prohibition;
the complete authorized loopback run passed without modifying those tests.
The first strict Clippy run found a fixed-size `chunks_exact(2)` in the new test
executable; it was corrected to `as_chunks::<2>()`. Original failed logs remain
in the stage evidence. No test was deleted, skipped or weakened to obtain green.
The local Release peer result covers 15 suites; it does not include the separate
CI-update guard or claim local Qt availability. Exact-commit Actions are recorded
in the follow-up evidence after they actually finish; prior green Actions are
not R2 evidence.

Reproduction from `core/` after installing the existing test dependency:

```text
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
cargo build --release --locked --workspace --lib --bins
cargo build --release --locked -p swirl-transport --example reality-client
python ../tools/tests/generate_reality_vectors.py --check
```

Set `SWIRL_REALITY_CLIENT` to the built Release example (with `.exe` on Windows),
then run both `tools/tests/test_reality_peer.py` and `test_reality_tls.py` from the
repository root. A missing executable is a test error, never a skip. The CI update
requires the Release target, binary preflight and both suites together on all
three platforms and in the existing App job, preserving the earlier Qt and full
native application gates.

## Provenance and remaining gates

The implementation was written independently, using public protocol behavior
and the existing generic TLS dependency. No upstream proxy source was copied.
The reviewed fixed sources include:

- [rustls 0.23.46 constructor](https://github.com/rustls/rustls/blob/f04804fa13341a9b1dc02b5d1dd8a746f2c4b7fb/rustls/src/client/hs.rs) and [package/license](https://github.com/rustls/rustls/blob/f04804fa13341a9b1dc02b5d1dd8a746f2c4b7fb/rustls/Cargo.toml), Apache-2.0 OR ISC OR MIT.
- [Xray REALITY client](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/transport/internet/reality/reality.go), MPL-2.0, read for authentication behavior.
- [REALITY server](https://github.com/XTLS/REALITY/tree/83f621788ca88b83179810b12baa7ae518aacb83), whose repository license is MPL-2.0; original Go-derived notices remain distinct.
- [TLS 1.3 RFC 9846](https://www.rfc-editor.org/rfc/rfc9846.html), [hybrid key exchange RFC 10024](https://www.rfc-editor.org/rfc/rfc10024.html), [component reuse RFC 9954](https://www.rfc-editor.org/rfc/rfc9954.html), and [TLS vectors RFC 8448](https://www.rfc-editor.org/rfc/rfc8448.html).

Independent Python-peer success is not mature REALITY-server interoperability,
browser fingerprint compatibility, VLESS/Vision forwarding, a Qt product node,
public-network success or private-provider acceptance. The next components are
Vision framing and flow semantics, inner TLS eligibility and an owned TLS/TCP
transition preserving pending bytes and both directions. Configured fingerprint
and certificate-extension semantics must be implemented before enabling a
corresponding subscription/runtime/Qt profile.

The fixed **79 items, six accepted items and 10.83% accepted weight** remain
unchanged. B13 remains partial; R2 alone does not change B14 from unimplemented.
No private URL was refreshed, no private node was attempted, and no physical
Windows display/DPI/240 Hz acceptance is claimed.
