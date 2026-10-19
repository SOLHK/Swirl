# REALITY handshake foundation: owned keys, transcript and server authentication

## Scope and product boundary

This is a bounded native Rust foundation, developed after the import-security
repair `4d73f6574bf9884dc4e173b58708ae543b2303bd` on
`work/core-completion-20261017`. It is not an executable REALITY/Vision outbound.
The existing runtime and Qt native configuration gates still reject these
options. Neither DIRECT nor ordinary TLS is used as a fallback.

The implementation lives in `core/crates/swirl-transport/src/reality/`:

| File | Implemented responsibility |
| --- | --- |
| `kx.rs` | One owner of fresh X25519 and ML-KEM-768 secrets, RFC 10024 share layout, hybrid decapsulation, noncontributory-key rejection, opt-in client-only rustls group |
| `hello.rs` | Bounded first ClientHello/ServerHello parsing, exact random/key/SNI/session-ID binding, TLS 1.3 selection, unique extensions/groups and ordered key shares |
| `mod.rs` | HKDF-SHA256 authentication key, AES-256-GCM SessionID finalization, immutable final handshake bytes and SHA-256/SHA-384 transcript checkpoint |
| `certificate.rs` | Strict DER profile, HMAC-SHA512 authentication of the Ed25519 public key, genuine TLS 1.3 CertificateVerify verification; no cover-certificate fallback |
| `tests.rs` and certificate tests | Independent known answers, malformed-message and authentication failures, key ownership, actual stock-rustls integration |

Generic TLS in `secure.rs`, DNS, routing, runtime outbounds, and existing
supported VLESS TCP/TLS/WS execution are unchanged. No QML or font code is
modified by this foundation. The earlier unintegrated Windows R0/R1 directory
has not been accessed from this cloud workspace.

## Protocol decisions

The current pinned REALITY server requires an X25519MLKEM768 client share before
an optional X25519 share. A legacy X25519-only authentication vector is retained
as a primitive test, but the modern public foundation API explicitly rejects
that first-flight structure. ML-KEM data is genuine, not a padded placeholder.

The client hybrid share is the 1184-byte ML-KEM public key followed by 32 bytes
of X25519. The server share is the 1088-byte ML-KEM ciphertext followed by its
32-byte X25519 public key; the TLS shared secret concatenates the 32-byte ML-KEM
secret before the 32-byte X25519 secret. Optional classical negotiation consumes
the same X25519 owner whose public component was sent in the hybrid share.
The rustls provider rejects server-side use rather than using the DH-oriented
default implementation for a KEM.

REALITY client authentication uses the configured server static X25519 key,
HKDF-SHA256 with `client_random[0..20]` as salt and `REALITY` as info, followed
by AES-256-GCM. The nonce is `client_random[20..32]`; the 16-byte plaintext is
version, reserved zero, big-endian timestamp and zero-padded short ID. The
complete handshake message with a 32-byte zero SessionID is authenticated as
AAD, then the resulting 32-byte ciphertext/tag replaces that field. TLS record
headers never enter this transcript. Random, SNI and both key-share bindings
are checked before the owned message is changed.

`ClientKeys::authenticate` consumes its sole key owner on both success and
failure. A retry must generate fresh keys/random; the public API cannot clone
or export private seeds. Secret buffers use zeroization and the authentication
key is redacted from Debug. An authenticated ClientHello exposes immutable
bytes, and the first ServerHello transition consumes the same key owner.

The bounded profile rejects HRR, TLS 1.2, PSK, early data, cookies, ECH, duplicate
extensions/groups, unowned shares, unoffered/reordered share selections and
invalid session-ID echoes. SNI forbids the wire-invalid terminal dot even
though the generic DNS-name type accepts it. GREASE remains opaque but must
have a nonempty key-exchange vector and obey the supported-group order.
Correctly sized corrupted ML-KEM ciphertext uses
FIPS 203 implicit rejection: it yields a different secret and still requires
the TLS Finished check to fail. Decapsulation success is never treated as
handshake success.

## Server authentication and the actual certificate format

REALITY's certificate outer signature is an HMAC-SHA512 over the raw Ed25519
public key. Authenticating that key does not replace the separate Ed25519
CertificateVerify signature or TLS Finished. All three algorithm identifiers
must be Ed25519 with absent parameters; key/MAC sizes and BIT STRING alignment
are exact. DER is fully consumed, including nested sequences, with bounded
certificate input and no nonminimal-length or trailing-field acceptance.

The upstream minimal certificate can contain empty names, serial number zero
and `00010101000000Z` dates. The ordinary `x509-cert` time type cannot represent
the year-0001 placeholder. A small borrowed schema using maintained RustCrypto
DER/X.509 field types admits that one exact canonical placeholder while
continuing to validate other time encodings. Received certificate bytes are
never rewritten. Names and validity are not REALITY's trust anchor: the pinned
server key and authenticated handshake provide that binding.

This first profile requires an extension-free V3 certificate. ML-DSA extensions,
other extensions, chains and OCSP are explicitly rejected. This is a documented
compatibility limit, not a claim that every genuine REALITY certificate uses
this profile. Ordinary CA certificates never fall back to normal TLS acceptance.

## Independent evidence and verification

`tools/tests/generate_reality_vectors.py` uses Python cryptography 50.0.2 and its
OpenSSL backend, independently of Rust's ring/dalek/RustCrypto implementation.
The checked-in JSON is marked public synthetic material. Its fixed keys,
certificates and domains are generated test inputs, not provider credentials.
The check command makes no network requests:

```text
python tools/tests/generate_reality_vectors.py --check
```

It verifies three authentication cases, genuine ML-KEM decapsulation, two TLS
transcripts (SHA-256 and SHA-384) and 22 negative checks. Rust compares exact
SessionID ciphertext/tag, authenticated ClientHello bytes, hybrid shared
secret, transcript checkpoints and independent CertificateVerify signatures.
The Python fixture also includes TLS key-schedule and Finished known answers;
their existence does not mean this Swirl foundation already implements that
TLS record/state machine.

Three in-memory integration tests use actual stock-rustls client/server states.
The client opts into Swirl's hybrid provider and ring X25519; the test inspects
the emitted ClientHello and proves its classical share equals the hybrid tail.
A ring server selects that classical component and uses the synthetic REALITY
HMAC certificate. The successful case completes CertificateVerify and Finished,
transfers bytes in both directions, then verifies both close_notify messages.
Wrong authentication keys and a modified encrypted server flight fail before
any application plaintext is readable. These are verifier/provider integration
tests; their ClientHello has not been REALITY-authenticated and the server is
not a complete independent REALITY peer.

Local environment: cloud Linux, Rust 1.99.1, GCC 13.3, Python 3.12.14,
cryptography 50.0.2. The declared Rust 1.89 minimum was additionally checked with
the actual isolated Rust 1.89.0 toolchain, not inferred from crate metadata.

| Gate | Observed local result |
| --- | --- |
| `cargo fmt --all -- --check` | Passed |
| `cargo check --workspace --locked --offline` | Passed |
| `cargo clippy --workspace --all-targets --locked --offline -- -D warnings` | Passed |
| `cargo test --workspace --locked --offline` | 188 unit/integration tests + 1 compile-fail doctest passed; 0 failed, 0 ignored |
| New REALITY module tests | 34 passed, 0 failed, 0 ignored |
| `cargo build --release --locked --offline --workspace --lib --bins` | Passed, including actual libraries and three CLI executables |
| `cargo +1.89.0 check --workspace --all-targets --locked --offline` | Passed |
| Independent fixture generator | 3 authentication cases, genuine decapsulation, 2 transcripts, 22 negative checks passed |
| Existing independent protocol/diagnostic/import suites | 197 passed, 0 failed; 5 Qt hooks explicitly skipped in cloud Linux |
| CI update guard | Existing 25 safety tests passed; update produced exactly the same workflow bytes |

An initial local focused transport run hit the sandbox's socket prohibition in
two existing UDP tests; all REALITY tests passed. The complete authorized
loopback test run above passed without changing those tests. A strict Clippy
warning about fixed-size chunks was fixed in the new parser. Original failure
logs are retained in the development evidence; no assertion, timeout or skip
was relaxed to obtain a passing gate.
A later incremental Release link reported a missing `rlib` form despite an
existing artifact. The failing log was retained; cleaning only the generated
Release target and rebuilding the exact source succeeded in 34.54 seconds.
No product or compiler-security setting was changed for that retry.

Independent review also identified three first-flight parser gaps before commit:
empty GREASE key-exchange vectors, wire SNI with a terminal dot, and an ECH
compressed-inner extension appearing in an ordinary wire ClientHello. All now
fail with explicit validation, with positive GREASE/name cases retained.

The fixture check is mandatory in both portable Rust jobs, the Windows Rust
job and the existing App validation job. Existing protocol, public-network,
Windows native/compatibility Qt, independent Qt peers and full application
gates remain in place. Exact-commit CI outcomes are recorded after pushing;
prior green runs do not establish verification of this source.

## Dependencies, provenance and remaining implementation

No source was copied from another proxy core. Public protocol behavior was
reviewed against the following pinned sources:

- [Xray-core REALITY client](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/transport/internet/reality/reality.go), MPL-2.0, read only.
- [REALITY server](https://github.com/XTLS/REALITY/tree/83f621788ca88b83179810b12baa7ae518aacb83), MPL-2.0 under that revision's [repository LICENSE](https://github.com/XTLS/REALITY/blob/83f621788ca88b83179810b12baa7ae518aacb83/LICENSE), read only; its `tls.go` and `handshake_server_tls13.go` define the current share/authentication behavior. Go-derived files retain their separate original notices; the repository is not generally BSD-3-Clause. No source from this project was copied into Swirl.
- [RFC 10024](https://www.rfc-editor.org/rfc/rfc10024.html), hybrid TLS key layout, and [RFC 9954](https://www.rfc-editor.org/rfc/rfc9954.html), component reuse within one ClientHello.
- [TLS 1.3 RFC 9846](https://www.rfc-editor.org/rfc/rfc9846.html), transcript, certificate proof and Finished semantics.
- [rustls 0.23.46](https://github.com/rustls/rustls/tree/f04804fa13341a9b1dc02b5d1dd8a746f2c4b7fb), existing TLS dependency and public key-exchange/verifier contracts.

New pinned direct primitives are `x25519-dalek 3.0.0` (BSD-3-Clause),
`ml-kem 0.3.3`, `x509-cert 0.3.0` and `der 0.8.2` (Apache-2.0 OR MIT).
The ML-KEM selection includes the upstream CBD timing fix; 0.3.2 is not used.
The pinned RustCrypto ML-KEM README still reports no independent security audit;
this dependency review and the tests must not be described as such an audit.
`core/DEPENDENCIES.json` and the packaged `rust-reality-dependencies.txt`
retain new transitive dependency and license evidence. Swirl owns the proxy
protocol state/validation; maintained libraries supply cryptographic primitives.
The inventory contains 130 packages; 29 newly resolved package versions have
58 complete license/notice texts in the new artifact. One upstream license
line's trailing space is preserved verbatim rather than rewriting its contents.

The next blocking step is a TLS backend adapter that installs the finalized
authenticated ClientHello before its encoded bytes enter the transcript buffer
and send queue, using the same live key owner. The currently pinned rustls
public API has no direct single-construction hook for this. Rewriting bytes at the
socket boundary would desynchronize the transcript and is not a valid solution.
The subsequent integration must verify the actual server CertificateVerify and
Finished over that transcript, implement configured fingerprint/ALPN semantics,
bounded record IO/cancellation/closure, then implement Vision framing and its
eligible VLESS combinations. A full independent REALITY peer and the Qt product
path must then be tested before any outbound capability is enabled.

The fixed 79-item acceptance scope, six accepted items and 10.83% accepted
weight remain unchanged. This foundation can justify B13 being partially
implemented after exact-source verification; B14 is still unimplemented.
No complete protocol profile, private provider, complete subscription, TUN or
Windows physical display acceptance is established. Supplier refreshes and
private-node attempts in this session remain zero.


## Exact-source CI and follow-up verification

The foundation was pushed as `daad7a057ab2c4b347c3ab142ce88af6528cb8f6`,
tree `70ccc46a5d938ba524e11f35f9e07531e1b0ede8`.
[Rust CI 39200717679](https://github.com/SOLHK/Swirl/actions/runs/39200717679)
passed fmt/check/Clippy, 188 unit/integration tests plus one doctest, Release and
the independent REALITY generator on **all three platforms**. Linux/macOS jobs
completed successfully with 197 Python passes and 5 explicit Qt-hook skips each.
The Windows job failed later in the existing DNS peer's same-port TCP allocation;
its 30-function suite reported 20 error incidents and one consequent failure.
Windows Qt, separate Qt peers and the complete native application were not run.
The successful cryptographic checks do not turn that job into a successful job.

[App validation 39200717693](https://github.com/SOLHK/Swirl/actions/runs/39200717693)
passed against the actual `daad7a0` source: 189 Rust, 69 independent-network and
25 workflow-guard passes, with 5 explicit skips in its narrower menu. It is not
a substitute for the skipped Windows gates.

The subsequent sing-box import commit `e0534f4` did not change Rust source and
again passed the three-platform Rust/REALITY gates; its original Windows peer
job instead failed inside an SS fixture which had swallowed the original socket
error. Both failure histories are preserved in
[the bounded allocation repair](LOOPBACK_PAIR_ALLOCATION_20261019.md).
Repair source `a429d5bc2efe31f10cfb61d16b16ffbde2a8fc40` has passed local
Rust/Release and the complete affected DNS/policy suites. Its exact-source
[Rust run 39202767158](https://github.com/SOLHK/Swirl/actions/runs/39202767158)
and [App run 39202767154](https://github.com/SOLHK/Swirl/actions/runs/39202767154)
both completed successfully and are bound in
[the permanent session evidence](evidence/REALITY_FOUNDATION_AND_IMPORT_20261019.json).
Each platform passed 189 Rust tests and 201 common Python tests with 5 explicit
skips. Windows native/compatibility CTest passed 3/3 and 2/2; four original XMLs
contain 71 substantive passes, no failures and 6 skips. Five separate Python Qt
hooks passed, and the complete native `Swirl.exe` compiled successfully.
The App's narrower menu passed 189 Rust, 25 guard and 69 network tests, with
5 skips; its actual tested SHA and archived source match `a429d5b`. This final
follow-up does not erase either original failed Windows run.

B13 is now recorded as partially implemented solely for this tested foundation.
B14, executable REALITY/Vision, complete independent REALITY interoperability,
provider nodes and whole private profiles remain unverified or unimplemented as
specified above; the 79-item scope and 10.83% accepted weight do not change.
