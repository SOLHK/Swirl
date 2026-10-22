# Vision R1: incremental framing and strict VLESS request Addons

## Source boundary

This independently testable stage follows REALITY TLS engine commit
`611edcff6c90d5f6e22637de1a24b4dfde494095` on
`work/core-completion-20261017`. It implements a native Rust Vision framing
component and exact VLESS request flow serialization. It does not enable a
Vision outbound or claim complete VLESS/REALITY/Vision interoperability.

The precommit remote reread found concurrent font-test change
`9984a5ddbae072bfec2aa5c7f94604ac77ca8471`, directly after `611edcff`. Its five
files do not overlap this stage. They were fast-forwarded and preserved; they
do not change the Rust or Python protocol sources used by the local gates.
New exact-source CI must verify the combined native application. The separate
font workflow for that parent remains a distinct source/evidence identity.

The existing subscription inspector, native IR and Qt startup gates continue
to reject executable Vision requirements. The normal VLESS request function
still passes `None` for flow, producing exactly its previous wire bytes. There
is no new DIRECT, ordinary TLS or non-Vision fallback.

| Source | Implemented responsibility |
| --- | --- |
| `core/crates/swirl-protocol/src/vision.rs` | Per-direction frame encoder, fixed-state incremental decoder, static errors and strict request Addons |
| `core/crates/swirl-protocol/src/vless.rs` | Internal `request_with_flow`; existing request delegates with no flow; full request byte regressions |
| `core/crates/swirl-protocol/src/lib.rs` | Public component module, without adding an executable outbound |
| `core/crates/swirl-protocol/tests/vision.rs` | Independent known answers, fragmentation, terminal boundaries, truncation and length tests |
| `core/crates/swirl-protocol/tests/fixtures/vision-v1.txt`, `flow-v1.txt` | Ten public synthetic frames and three complete Addons values |
| `tools/tests/generate_vision_vectors.py` | Separate Python/struct/protobuf construction; `--check` compares without modifying fixtures |

No new Cargo dependency, copied proxy implementation, font, animation or Qt
implementation is introduced.

## Wire and state contract

Each direction has its own encoder and decoder. Its first frame begins with
the 16-byte configured UUID. Every frame then contains a one-byte command,
two-byte big-endian content length and two-byte big-endian padding length,
followed by exactly those content and padding bytes. Subsequent frames in that
direction do not repeat the UUID.

The decoder checks the complete UUID before returning payload. This prefix
identifies Vision framing; it does not authenticate a server. It never searches
for a later UUID to resynchronize or interprets a UUID/header pattern inside
application bytes as framing.

| Command | Component result | Responsibility left to the transport owner |
| --- | --- | --- |
| `0` | `Continue`, then accept another frame | Continue the authenticated transport and preserve frame order |
| `1` | `EndPadding`, terminal framing boundary | Stop framing in this direction while keeping the outer TLS channel |
| `2` | `DirectRequested`, terminal framing boundary | Establish actual inner-TLS eligibility and perform an owned stream transition before any raw copy |

An event is returned only after all current content and padding have been
consumed. One decode call returns at most one event and a borrowed payload slice
from that call's input. Its `consumed` count excludes every following byte,
including data already read alongside a terminal frame. The caller must retain
that tail for the next frame or eventual transport transition. Nonempty input
either makes progress or returns an error; empty input does not mean EOF.

The decoder stores only its UUID, a five-byte header and fixed state counters.
A remote content or padding length does not allocate a body buffer. Each field
is limited by its unsigned 16-bit wire representation: 65,535 bytes. The largest
first frame is 131,091 bytes including UUID and header. The encoder checks both
limits before changing state and produces a bounded owned frame. The caller
supplies padding bytes and length; this component does not invent a production
padding distribution.

Unknown commands, UUID mismatches and incomplete EOF poison the decoder with
a static error. The first failure is retained. `finish()` distinguishes truncated
UUID, header, content and padding. Empty input and a complete frame boundary,
including a complete `Continue` frame, are legal framing EOF. A bare UUID has
already started a frame and is a truncated header. Successful framing EOF is
not proof of TLS `close_notify` or a completed proxy request.

The encoder advances when a complete frame is constructed. A future async
writer must retain that same frame and resume its exact partial-write offset.
Re-encoding after a short write would corrupt the first-frame or terminal state.
Cancellation must abort the owned attempt and must not replay an earlier frame.

## VLESS Addons contract

`request_addons(None)` and an explicit empty string return the complete empty
length-prefixed Addons byte `[0]`. Exact `xtls-rprx-vision` returns 19 bytes:
the one-byte Addons length `0x12`, protobuf field-one tag `0x0a`, the 16-byte
string length `0x10`, and the flow bytes. The independent fixture generator
constructs the protobuf tag and length rather than importing Rust output.

Every other flow fails. This includes `xtls-rprx-vision-udp443`, obsolete direct
flow, whitespace/case variants, NUL suffixes and unknown values. There is no
normalization to an executable no-flow request. The internal VLESS encoder maps
the component error to static `VlessFlow`, without returning the submitted value.

Two additional tests call the actual complete VLESS request encoder. Fixed
known-answer bytes cover IPv4, domain and IPv6 addresses, command, port, UUID,
the full Vision Addons, and byte-identical existing no-Addons requests. The
normal VLESS response `[0, 0]` remains valid. A response does not have to echo the
requested flow; adding that requirement would break the actual protocol.

## Actual local verification

On cloud Linux with Rust 1.99.1, the isolated protocol package passed 49 unit
tests and 21 Vision integration tests, with no failed or ignored tests. The
stage adds 23 Rust tests: 21 component tests and two complete-request tests.

The full workspace, built in a fresh target directory, passed 239 unit/integration
tests and one compile-fail ownership doctest. Cargo fmt, check and strict Clippy
also passed. Actual Rust 1.89.0 checked the workspace and all targets against
the locked offline dependency set. The fixed Python generator verified all ten
frame and three flow cases without modifying either file.

The actual Release workspace library/bin build and separate REALITY client
example both passed. Fifteen suites using those freshly built binaries passed
211 Python tests, with five explicit unavailable Qt hooks and no failures.
The separate workflow guard passed 33 tests without skips. Together these
account for 244 local Python passes and five explicit skips, retaining the
individual suite and binary hashes. The four new CI lines run the Vision
fixture check on Linux, macOS, Windows and the App job; Windows propagates the
generator's exit status immediately. The guard checks complete historical
migration, exact ordering, required files and fail-before-peer behavior.

The component tests cover every two-part split of the independent frames,
bytewise input, multiple frames in one read, separate direction state, all 253
unknown commands, every UUID mismatch position, every partial EOF position,
maximum content/padding lengths, terminal tails, empty/padding-only frames,
header lookalikes in payload, and the exact supported/unsupported flow boundary.

The first full-workspace attempt reused a local build cache and failed to locate
the required `swirl_core` rlib before running tests. Rebuilding the two affected
crate caches allowed all 239 unit/integration tests to pass, but rustdoc still
reported `E0463`. A completely fresh target directory then passed the entire
workspace including its doctest without a source or assertion change. Both
original failed logs are retained separately. An earlier isolated fmt invocation
from the repository root also failed to find `Cargo.toml`; its corrected command
ran from `core`. None of these failures is rewritten as a passed invocation.

The exact source commit, Release peer regression and corresponding Actions
results must be bound in the subsequent evidence checkpoint. Existing green
REALITY R2 or isolated-component runs are not CI evidence for a later commit.

## Next executable work and acceptance limits

The missing work is the inner TLS record/handshake classifier, eligibility
checks, production padding policy, bounded async framing I/O, partial-write
ownership, cancellation and the real TLS/TCP transition. The outer TLS version
alone cannot authorize direct copy. Neither this decoder nor `TlsClient` exposes
a raw-stream bypass.

After those pieces have an independent real Vision peer, implement the eligible
VLESS/REALITY/Vision combination through the existing subscription, routing and
Qt path. Until then, retain explicit startup rejection and preserve unsupported
parameters. Separate protocol interoperation, Qt integration, complete native
application builds, public nodes, authorized private providers/full subscriptions
and physical Windows acceptance remain distinct evidence levels.

The fixed baseline remains 79 items, six accepted and 10.83% accepted weight.
A tested framing component can support a partial B14 implementation record;
it cannot satisfy the complete Vision item or increase the accepted numerator.
No private node, subscription refresh, physical display or system network
configuration is involved in this stage.

## Primary behavior and licensing review

The implementation was written independently from the following public wire
behavior and schema, with fixed source identities reviewed before integration:

- [Xray Vision state and frame behavior, `92ccc939`](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/proxy/proxy.go).
- [VLESS Addons protobuf, the same Xray commit](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/proxy/vless/encoding/addons.proto).
- [Xray VLESS request/response encoding, the same commit](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/proxy/vless/encoding/encoding.go).
- [Xray license at the reviewed commit](https://github.com/XTLS/Xray-core/blob/92ccc939aaf4f8965f369cf0b142e005aeaa11d5/LICENSE), MPL-2.0.
- [sing-vmess, `9b95ab8c`](https://github.com/SagerNet/sing-vmess/tree/9b95ab8c9478f8e8ebe5758d325ec8cda8197c5c), reviewed as another behavioral reference under GPL-3.0-or-later; no implementation was copied or added as a product dependency.

The actual source, fixture checks and tests take precedence over any historical
handoff that called the entire Vision feature either implemented or absent.
