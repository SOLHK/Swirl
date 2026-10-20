# Production REALITY Runtime continuation — 2026-10-20

Branch: `work/core-completion-20261017`. The source baseline was
`b5a84bfacc48e6b2a8be8f0797f34639530766c9`; subsequent font commits are preserved.
This file describes the production integration, not private-provider acceptance.
Frozen acceptance remains **79 items / 6 accepted / 10.83% weighted**.

## Executable changes

The existing `swirl_protocol::connect` now carries an explicitly validated
VLESS/REALITY outbound into `swirl_transport::reality::connect`, then the existing
VLESS request/response decoder and Runtime relay. The single original connection
deadline covers DNS, TCP, REALITY and request writing. Authentication failure
has no plain-TLS, plain-TCP, spare-node or DIRECT fallback.

The asynchronous transport owns the existing exact-record `TlsClient` and socket.
No detached task or second proxy engine is created. Each write admits at most
16 KiB after draining the preceding ciphertext; partial operations retain their
offsets. Returning from connect requires authenticated server Finished and a
flushed client Finished. Cancellation drops the owner. Normal non-Direct closure
requires outer TLS close_notify, with independent TCP half-close and continued
reverse reads. Bare EOF remains an error.

Typed `reality` parameters carry SNI, public key, short ID, fingerprint and ALPN.
URI, Clash JSON/YAML and native IR retain their source values. The Qt converter
uses the same field meanings after actual NodeImporter and NodeStore persistence.
Malformed/unknown parameters are rejected. An empty URI ALPN element is retained
and rejected instead of being silently removed during Qt normalization.

**Supported fingerprint is explicitly `rustls`.** It describes the implemented
native ClientHello. `chrome`, `firefox`, `random`, absent fingerprint, uTLS and
other unsupported declarations remain blocked. Neither this integration nor its
controlled peer results changes the historical 59 private-node executable count.
No private subscription was opened, refreshed, decrypted or tested in this work.
Current native client-version bytes are Swirl's `[0, 1, 0]`; server minimum-version
restrictions are not bypassed. HRR and incompatible REALITY certificate profiles
fail closed. General public camouflage/ticket-cache compatibility remains separate.

The Vision ownership adapter is present and has local component coverage, but
nonempty flow is still rejected at this P0 checkpoint. It is not counted as
combined Vision Runtime interoperability until the explicit P1 gate is enabled
and actually passes against full Xray.

## Independent end-to-end gate

`tools/tests/test_reality_runtime.py` uses the full official Xray executable
from the existing reproducible builder and exact lock. It does not seed or alter
the official target-observation cache. A separate TLS 1.3 camouflage listener has
no tickets; independent HTTP, verified HTTPS and echo listeners record actual
origin requests and authenticated inner TLS closure. Only per-run synthetic
credentials are used. Raw configs/debug logs are temporary, outside artifacts.

The test records import formats, real REALITY and VLESS session observations,
origin requests, routing, A/B selection with a pinned old session, six concurrent
segmented streams, authentication negatives, timeout and cancellation. Its `--qt`
mode requires the existing real Qt/DPAPI product test slot; absence is an error.
Rust Linux/macOS/Windows and App workflows run the new required gate; Windows
also runs the Qt path before building the complete native application.

Two initial real-network failures informed the corrected independent fixture:

- OpenSSL initially omitted the standard SNI acknowledgement. Official REALITY
  generated an EncryptedExtensions record four bytes longer than the observed
  target and rejected negative padding. Installing a standard SNI callback on
  the actual target fixes the observed record profile; authentication, Finished
  checks and the upstream observation cache are unchanged. This proves this
  controlled target profile, not arbitrary public camouflage servers.
- Official Xray freedom does not immediately propagate an upload EOF as target
  TCP CloseWrite. The independent echo target now uses an explicit length and
  releases a delayed tail only after the caller has really shut down upload.
  The test proves continued Swirl downlink after local half-close; it does not
  claim target FIN propagation through Xray. The Qt mode signals only after
  native `shutdown(SHUT_WR/SD_SEND)` succeeds. The older protocol fixtures retain
  their original EOF behavior.

MATCH/DOMAIN tests preserve the target hostname for the proxy. Existing routing
that explicitly needs target IP resolution still uses the configured Resolver,
which may use system DNS. This checkpoint is not a blanket DNS leak assertion.

## Primary references and implementation boundary

- [Xray v26.10.17, commit 92ccc939](https://github.com/XTLS/Xray-core/tree/92ccc939aaf4f8965f369cf0b142e005aeaa11d5): VLESS/REALITY/Vision peer, MPL-2.0, isolated test executable only.
- [REALITY 83f62178](https://github.com/XTLS/REALITY/tree/83f621788ca88b83179810b12baa7ae518aacb83): authentication/target observation and directional shutdown behavior; MPL-2.0 with retained BSD Go notices.
- [rustls 0.23.46](https://docs.rs/rustls/0.23.46/rustls/): existing certificate/transcript/record engine, Apache-2.0 OR ISC OR MIT.
- [tokio 1.53.3 AsyncRead](https://docs.rs/tokio/1.53.3/tokio/io/trait.AsyncRead.html): Pending ownership/wakeup semantics, MIT.
- [sing-box](https://github.com/SagerNet/sing-box): architecture research only; GPL-3.0-or-later source is not copied or added to the product.

All new protocol integration is independently implemented in existing Rust crates.
No dependencies, external-core fallback, font assets or UI appearance changes are added.

## Evidence checkpoint

The final corrected P0 local Runtime menu passed **7/7, zero failures, errors or
skips**, in 15.508 seconds. Its separate process reports counted 20 authenticated
REALITY sessions (one intentionally wrong VLESS UUID), 19 accepted VLESS sessions,
eight HTTP origin requests (one explicitly DIRECT), four verified HTTPS normal
closes, 1,573,026 echo payload bytes and seven tails received after real client
upload half-close. Earlier failing runs are retained as failures, not relabelled.
The portable driver is the existing production Rust control ABI; this result is
not Windows DPAPI/Qt execution or private-provider acceptance.

A fresh Release build then succeeded, and the final current-source P0 menu again
passed 7/7 in 21.294 seconds. fmt/check/strict all-target Clippy and the complete
workspace test menu passed on one identical Core tree: 295 unit/integration
tests plus one doctest, zero failures/ignored/filtered tests. The compact
[local evidence](evidence/REALITY_RUNTIME_P0_LOCAL_20261020.json) preserves binary
hashes, actual peer/origin observations, source identity and prior failures.
These final local checks used the working tree based on `ff3b591`, preserving
concurrent font work. One byte-I/O fixture's watchdog was increased from 10 to
30 seconds after loaded-host failure and an unchanged 7.49-second isolated pass;
payload, partial-I/O assertions and all production timeouts remain unchanged.

Source was a working checkout based on `b5a84bf` for those local binaries; the
build/test manifests record the dirty tree and executable hashes. Exact source
CI links and terminal results must be appended after execution. Pending CI is
not success. Frozen acceptance remains **79 / 6 / 10.83%**.
