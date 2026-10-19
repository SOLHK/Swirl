# Vision R2 substage: inner TLS inspection and bounded async framing

This stage extends the existing Vision R1 codec. It implements a component
client that negotiates the exact VLESS `xtls-rprx-vision` flow over a caller-owned,
already authenticated outer transport. It does not enable the native product
outbound and does not implement DirectReady or a raw TCP/TLS handoff.

The independent full Xray fixture exercises the working non-direct path with
an inner TLS 1.2 target. A separate inner TLS 1.3 case exercises a real peer's
direct request and the client's explicit refusal. These are separate outcomes:
the refusal is not TLS 1.3 Vision direct interoperability.

## Implemented source

| File | Responsibility |
| --- | --- |
| `core/crates/swirl-protocol/src/vision/tls.rs` | Two-direction incremental TLS record and Hello inspection |
| `core/crates/swirl-protocol/src/vision/stream.rs` | Async framing, random padding, bounded queues, cancellation and half-close |
| `core/crates/swirl-protocol/src/vision.rs` | Reused R1 codec, private early direct-request refusal check, component VLESS client |
| `core/crates/swirl-protocol/src/vless.rs` | Existing request-with-flow encoder exposed within the crate only |
| `core/crates/swirl-protocol/tests/vision_tls.rs` | Twelve structural, incremental and negative TLS inspection tests |
| `core/crates/swirl-protocol/tests/vision_stream.rs` | Sixteen async, ownership, buffering, cancellation and VLESS tests |
| `core/crates/swirl-protocol/examples/vision-client.rs` | Bounded synthetic loopback-only client; JSON stdin and redacted output |
| `tools/tests/test_vision_xray.py` | Four independent full Xray / Python OpenSSL positive and negative cases |

No new production dependency is added. The example adds the existing locked
`serde_json` workspace dependency as a dev dependency, with one corresponding
Cargo.lock dependency edge. No dependency version changes are required.

## Inner TLS inspection

The observer assembles ClientHello and ServerHello across arbitrary input
slices and across TLS record boundaries. It parses length-delimited fields and
extensions rather than searching for a `supported_versions` byte pattern in
the record or application payload. It checks the legacy version, compression,
session-ID bounds and echo, the client's actual offered suites, the server's
selected suite, extension uniqueness and structural lengths.

TLS 1.3 wire eligibility requires both complete hellos, an actual TLS 1.3 offer
and selection, matching session IDs and an offered selected suite. The reviewed
Xray implementation permits `0x1301` through `0x1304` for Vision eligibility;
the short-tag `0x1305` suite is excluded. A HelloRetryRequest is explicitly
ineligible in this stage, rather than being treated as the final ServerHello.
Unknown, malformed and oversized input is not resynchronized to a later fake
TLS header.

Each direction retains at most a 64 KiB Hello, including its handshake header.
The implementation bounds Vec capacity as well as length. It limits offered
suites and extensions to 256 each. Hello buffers are released on classification,
rejection, abort or fatal stream failure. The record tracker separately records
whether an encrypted application record has fully arrived and whether the
current direction is at a record boundary. A partial next record revokes that
boundary even after a previous encrypted record completed.

`Eligibility::Candidate` is descriptive. The observer has no inner TLS keys and
does not verify the inner Finished or authenticate a peer. The actual inner TLS
endpoints do that work. The candidate does not expose a raw socket and cannot
authorize a transport transition.

## Async stream and ownership

Each direction reuses the R1 framing state. The stream owns one outbound frame,
an 8 KiB wire read buffer and an 8 KiB decoded read buffer. Outbound application
acceptance is capped at 16 KiB per frame. A write acknowledges only bytes copied
into its owned frame, or bytes actually accepted by the unchanged outer stream
after padding ends. Before accepting another application slice it drains the
previous frame at the exact saved offset. It never re-encodes a partially sent
frame or acknowledges new bytes from a Pending poll.

This is an explicitly buffered writer: callers flush a request before waiting
for its response. The adapter does not implicitly flush writes from its read
poll. The example and the existing relay use explicit flushes.

Padding is generated with ring's cryptographic randomness and bounded rejection
sampling. Short TLS handshake content can receive the reviewed long-padding
length distribution; other frames use short padding. Ring also generates the
padding bytes. This makes padding independent of temporary deterministic test
vectors while keeping every frame bounded. It does not claim a browser/uTLS
fingerprint or traffic-analysis resistance has been fully reproduced.

| Received command | Actual adapter behavior |
| --- | --- |
| `0` | Keep decoding Vision frames over the supplied outer stream |
| `1` | End framing in that direction; preserve the decoded content and any already-read tail in their original order over the same outer stream |
| `2` | Reject with `PermissionDenied` / `VisionDirectOwnershipUnavailable` and drop the owned outer stream |

The adapter can refuse unsupported command `2` as soon as the complete header
is known, including when content or padding is still partial. It returns none
of that terminal frame's application content or following tail. This private
early refusal check does not change R1's public boundary event: the R1 decoder
still reports a completed terminal event only after all content and padding.

There is no DirectReady state, raw-stream getter, caller-supplied ownership
boolean, alternative DIRECT outbound, or downgrade to unframed raw TCP. A future
direct implementation must provide actual TLS/backend ownership and residual
buffer transfer before creating a usable direct channel. Record classification
and command reception alone cannot provide them.

Read/decode and partial-write loops use finite per-poll work budgets. They yield
without dropping positions, including through padding-only frames. Dropping an
individual read/write/flush future preserves pending state in the stream owner.
Dropping or aborting the owner releases the socket and all retained Hello/frame
buffers. No detached task or socket half is spawned by this adapter.

Upload shutdown drains acknowledged data, invokes the outer writer's shutdown,
and leaves the reader available for downstream data. Shutdown is idempotent;
the upload direction cannot be reopened after shutdown starts. External
deadlines cancel individual operations safely; the adapter does not impose an
arbitrary idle timeout on an otherwise valid long-lived stream.

The outer TLS implementation remains responsible for authenticating closure.
An `UnexpectedEof`, reset or timeout stays an error and poisons the connection.
Successful framing EOF alone never proves a TLS close_notify was received.

## Independent full Xray test contract

`test_vision_xray.py` uses the full, unmodified Xray executable produced by the
R3 source-locked builder. It verifies that executable's digest and build
manifest rather than accepting an arbitrary binary. It starts a real VLESS
Vision inbound with outer TLS 1.3, fresh synthetic UUID, CA and leaf certificates,
and restricts the reference outbound to the specific loopback target.

The independent target uses Python/OpenSSL with a fixed per-case inner TLS
version. Its evidence includes actual negotiated version, handshake result,
received/sent lengths and hashes, TLS closure outcomes, target thread cleanup
and reference-process/listener cleanup. The successful cases include normal
TLS 1.2, a 512 KiB transfer with a paused reader, and one-byte application reads
with seven-byte application writes. These are actual Xray VLESS/Vision paths,
not a second Swirl codec used as the peer.

The TLS 1.3 negative case uses a server-first probe. After the inner handshake,
the independent target sends a known greeting so that the real Xray server
requests direct mode before the client starts an application upload. The test
requires the actual direct rejection, a previously observed TLS 1.3 candidate,
zero application upload/receipt and an unusable direct channel. It separately
records the target's transmitted probe rather than hiding it in zero counters.
The rejection must have error kind `PermissionDenied` at `server_first_probe`.
A successful one-byte probe read or an EOF produces a different error kind and
cannot pass even if the harness has already observed a direct request and
reports the generic direct-refusal message. All zero-byte and probe-identity
assertions remain required.
The fixture then terminates the test reference process and verifies its target
connection and threads are released; a target timeout is an error.

An earlier echo-based negative experiment had an incorrect zero-upload premise:
the client had to send a legitimate framed echo request before the target could
produce the record that made Xray request direct mode. Its observed 38-byte
upload was not a raw handoff. That failed experiment is retained separately; the
server-first test establishes the stated pre-upload boundary without weakening
the direct refusal or using a synthetic command injector as the mature peer.

## Verification and acceptance boundary

The added Rust suites cover arbitrary record/input fragmentation, structural
extension lookalikes, suite/version/session mismatches, retry refusal, allocation
bounds, encrypted record boundaries, concurrent bidirectional transfers,
partial writes and read pauses, cancellation/resume, early direct rejection,
terminal-tail ordering, malformed frame/response refusal, TLS truncation, upload
half-close and actual resource release with a partial Hello still buffered.
Existing R1 vectors and tests remain unchanged and continue to run.

Local logs bind commands to actual source-file hashes and distinguish the
uncommitted local snapshot from subsequent committed CI. The integration handoff
must attach each source commit's exact Linux/macOS/Windows/App run IDs and their
actual conclusions; an older green run is not evidence for this stage.

The final cloud-Linux snapshot passed all five required workspace commands and
the separate Release `vision-client` build with Rust 1.99.1. The workspace ran
267 unit/integration tests and one doctest, with no failures or ignored tests.
That includes the 28 added cases; the 21 unchanged R1 integration tests also
passed. The final full-Xray suite passed all four cases without skips in 0.771
seconds against client SHA-256
`7b0785b18f3427f65c878ee1f7b5a296044586d9c319b8aa2f86eefc0287577e`.
That final rerun only strengthened the Python rejection assertions; the Rust
source hashes were checked before and after against the unchanged five-gate
snapshot, and the Rust gates were not rerun or relabeled as new results.
The [local evidence bundle](evidence/vision-r2/local-validation.json) retains
actual commands, source hashes before/after execution, raw Rust logs, the Xray
build/source identity and per-case client/target/lifecycle logs. Its checkout
base is `271ed3f5d2abe185a7b3308dd77f00b904bc58be` with local source changes;
it is explicitly not a green CI run or a new source commit under that old SHA.

The following remain incomplete: safe raw TLS/backend handoff, DirectReady,
direct bidirectional switching and buffered ciphertext transfer, successful
TLS 1.3 direct interoperability, HelloRetryRequest continuation, VLESS over
REALITY plus Vision as a complete combined product path, configuration/IR/
routing/Qt integration, supplier nodes, long-run/weak-network acceptance and
physical Windows testing. No private subscription was refreshed or read.

The [original failed experiments](evidence/vision-r2/initial-failures.json)
retain their original summaries, client/target outcomes and reference-server
logs, with hashes of the original files. The initial four blocked-loopback
failures and both later 38-byte echo-premise failures remain failures. Complete
unittest console tracebacks were not separately saved for those experiments;
the archive records that absence without reconstructing original output.

The frozen baseline remains **79 items, six fully accepted and 10.83% accepted
weight**. This component substage does not accept the complete Vision item or
increase that numerator or denominator.

## First committed CI failure: coalesced outer and inner TLS records

The first source commit is
[`f3ce257f14e59e82977d89ac4be436d08926c6b8`](https://github.com/SOLHK/Swirl/commit/f3ce257f14e59e82977d89ac4be436d08926c6b8).
Its [Rust run 39243009089](https://github.com/SOLHK/Swirl/actions/runs/39243009089)
**failed**: Linux completed successfully, while macOS and Windows each passed
the three TLS 1.2 Vision cases and failed the TLS 1.3 Direct-refusal case.
The later Windows Qt and full application steps did not run on that failed
commit. Its separate [App run 39243009132](https://github.com/SOLHK/Swirl/actions/runs/39243009132)
completed successfully; that result does not replace the two platform failures.

Both failing Xray logs contain the actual `command=2` padding event followed by
`bad record MAC`. The client returned `InvalidData` in `server_first_probe`
before observing `DirectRequested`. The target completed its TLS 1.3 handshake
and sent the 34-byte probe; no application upload started. The assertions
correctly rejected this outcome: a TLS error without observing the authenticated
Direct request cannot count as the required `PermissionDenied` refusal.

The locked tokio-rustls/rustls reader can read an outer TLS record carrying the
terminal Vision frame together with the following raw inner TLS record. It
processes the whole ciphertext buffer before returning authenticated plaintext,
so the foreign-key record can cause an error before Vision sees its command.
Its plaintext `AsyncRead` also attempts further reads after obtaining a chunk.
The repair therefore needs both ciphertext-record and plaintext-chunk boundaries;
timing delays, one-byte socket reads and relaxed error assertions are not a fix.

The original results and necessary raw logs are retained in
[first Linux CI](evidence/vision-r2/first-ci-linux.json),
[first App CI](evidence/vision-r2/first-ci-app.json),
[macOS failure](evidence/vision-r2/first-ci-macos-failure.json) and
[Windows failure](evidence/vision-r2/first-ci-windows-failure.json).
The failed runs remain failures even after a later source revision passes.

## Record-boundary repair

`vision/record.rs` provides two explicit adapters for an outer TLS transport.
`TlsRecordIo` sits below TLS and limits each read to the current five-byte header
or ciphertext body, retaining only that header and counters. It rejects record
lengths above 18 KiB and truncated headers/bodies; tighter TLS-version bounds
and authentication remain the TLS engine's responsibility. `PlaintextChunks`
sits above the engine and returns the current authenticated `AsyncBufRead`
chunk before polling it again. Neither adapter inserts a delay or artificial
`Pending`, decodes Vision commands, extracts the socket or grants DirectReady.

The loopback example explicitly combines both adapters with ordinary rustls
CA/name/signature/Finished verification. The default product `secure()` path
is unchanged. The example still closes its entire transport owner when Vision
rejects command 2; it never retries raw forwarding or treats that rejection as
a successful TLS shutdown.

Five deterministic Rust regressions use an actual TLS 1.3 handshake and enqueue
an authenticated terminal Vision frame followed by a record encrypted under
another session's keys in one available read. They compare all four adapter
combinations: the original ciphertext batching reproduces `InvalidData` and
`BadRecordMac`; ciphertext limits alone still allow plaintext read-ahead to
consume the raw suffix. Both boundaries produce the required `PermissionDenied`,
leave that suffix unread, preserve every application-output sentinel, avoid the
spurious fatal alert and release the underlying owner exactly once.

The remaining regressions require a tampered authentication tag to fail, valid
`close_notify` to succeed, boundary TCP EOF and truncated headers/bodies to fail,
partial-header cancellation and upload half-close to retain read state, and an
oversized record to be rejected. The mature Xray test assertions are unchanged.
Local execution and source hashes are retained in
[the repair evidence](evidence/vision-r2/record-boundary-local.json); exact
committed CI must be recorded separately from that local snapshot.

## Exact record-repair CI and Windows fixture failure

The record-boundary source is
[`0be68231b15c1e4f69b138cda7bae0a3930d956b`](https://github.com/SOLHK/Swirl/commit/0be68231b15c1e4f69b138cda7bae0a3930d956b),
tree `72cf2ebcb652baeefeb415be66ebe59184725697`.
The [Rust run 39246770262](https://github.com/SOLHK/Swirl/actions/runs/39246770262)
completed with Linux/macOS **success** and Windows **failure**. The separate
[App run 39246770049](https://github.com/SOLHK/Swirl/actions/runs/39246770049)
completed successfully. Linux, macOS and App each actually passed 272 Rust tests
plus one doctest, all five new record regressions, 41 CI guards, all 12 REALITY
cases/13 sessions and all four Vision cases. Their strict TLS 1.3 rejection is
`PermissionDenied` after an observed Direct request, with zero application bytes
and `DirectReady=false`. The App source archive contains 262 files, all matched
to the exact tree's Git blobs and modes.

Windows passed the Rust gates, including the five record regressions, but its
older DNS allocation guards failed before the mature REALITY/Vision and Qt/App
steps. Ten UDP binds returned `WinError 10013` for ports within `63203..63402`.
The same job's read-only `netsh` diagnostics reported those UDP exclusion ranges,
which differ from its TCP exclusions. A TCP-selected ephemeral port was not a
valid shared UDP/TCP candidate. Missing later peer artifacts are a consequence
of that first failure, not successful or skipped interoperability tests.

Exact records are preserved separately as
[Linux](evidence/vision-r2/record-ci-linux.json),
[macOS](evidence/vision-r2/record-ci-macos.json),
[App](evidence/vision-r2/record-ci-app.json) and
[Windows failure](evidence/vision-r2/record-ci-windows-failure.json).
The failed Windows job was not rerun to obtain a different host.

## Shared Windows UDP/TCP fixture port correction

`tools/tests/loopback_ports.py` reads the Windows TCP and UDP exclusion tables
once per address family/process. It validates the numeric table independently
of localized headings, then selects a private-range candidate outside their
union. The DNS and SS policy fixtures hold the actual TCP socket continuously
while binding UDP on the same port; both must exist before a server thread starts.
Other platforms continue to request an OS-selected port. No reservation, firewall
or host setting is changed.

The existing eight-attempt collision bound and original exception identity remain
intact. Unknown permission errors, query failures/timeouts, malformed tables and
an exhausted candidate range still fail; none becomes an ephemeral fallback or
a skipped test. A reservation added after the snapshot also remains a bind
failure. Fixture thread mocks now target their local imports so that they cannot
intercept Windows subprocess pipe-reader threads.

Six new selector tests cover the actual failed host's table shape, both protocol
exclusions and address families, valid empty tables, malformed output, query
errors/timeouts, all ports excluded and the portable path. Existing pair tests
retain real maximum-length DNS forwarding over UDP and fragmented TCP, both
address families, collision recovery, held-socket ownership, all failed-socket
cleanup, immediate permission rejection and the final eighth collision error.
The final local results and exact four-file hashes are recorded in
[port-pair local evidence](evidence/vision-r2/port-pair-local.json).
This fixture correction accompanies this source revision; its new exact CI
results must be recorded separately before claiming Windows interoperability.

## Primary references and independent implementation

- [Reviewed Xray Vision traffic/framing/TLS behavior at the fixed commit](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/proxy/proxy.go).
- [The same Xray VLESS inbound](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/proxy/vless/inbound/inbound.go).
- [TLS 1.3 Hello/extension/record wire format in RFC 8446](https://www.rfc-editor.org/rfc/rfc8446).

The Rust observer and async state machine were independently written for Swirl.
No Go proxy implementation was copied into the product, and no full proxy core
was added as a product dependency. The fixed Xray executable is an isolated
test-only reference.
