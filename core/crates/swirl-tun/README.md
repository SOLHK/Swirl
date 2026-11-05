# Native TUN packet stack

`swirl-tun` adapts IP packets to native Rust streams/datagrams. It never edits OS
network state and has no DNS, routing policy, proxy protocol or local SOCKS hop.
It retains the workspace's `unsafe_code = "forbid"` policy.

## Runtime interface

Call `spawn(TunConfig)` inside Tokio. `TunStack` exposes bounded ingress/egress,
TCP accept, UDP receive and UDP reply channels plus statistics and `TunControl`.
Move channel fields into the adapter/dispatcher tasks and retain `control`.
`control.shutdown().await` joins the stack. Dropping `control` cancels it.

`TcpFlow` contains original `source`, `destination`, and `TunTcpStream` (Tokio
AsyncRead/AsyncWrite). A completed write shutdown preserves queued bytes then
emits FIN; dropping an unfinished dispatcher operation resets the TCP socket.
`UdpDatagram` contains original source/destination and one complete payload,
including an empty payload. Replies reverse the original endpoints.

The stack task owns smoltcp's Interface/SocketSet and flow table. New SYNs are
admitted by tuple before allocation; duplicate SYNs reuse their socket. Listening
sockets bind the exact destination address and port. Routing happens outside the
packet loop, once per flow, using Swirl Core's dispatcher.

## Dependency decisions

The exact dependency is smoltcp 0.14.0, 0BSD, with Rust 1.91 required explicitly.
See its [manifest](https://github.com/smoltcp-rs/smoltcp/blob/v0.14.0/Cargo.toml)
and [change log](https://github.com/smoltcp-rs/smoltcp/blob/v0.14.0/CHANGELOG.md).
Version 0.12 was not selected because later versions fix TCP and malformed-input
handling. Tokio and ring's OS random source reuse existing workspace dependencies.
The license is retained in `licenses/SMOLTCP-0.14.0.txt`.

`netstack-smoltcp 0.2.4` was evaluated but not used: its TCP accept/device queues
are unbounded and its SYN admission allocates before deduplication. This crate
uses the mature smoltcp TCP state machine with its own bounded async adaptation.

smoltcp 0.14's L3 interface does not implement IPv6 Fragment-header processing or
oversized IPv6 egress fragmentation. `ipv6.rs` supplies only bounded framing and
reassembly adaptation using smoltcp's wire types and range assembler. Four
fragment sets expire after 60 seconds; overlaps invalidate the set until expiry.
TCP retransmission, sequence/window handling and congestion control remain in
smoltcp. IPv4 fragmentation/reassembly also stays in smoltcp.

## Resource bounds

Defaults provide 512 TCP flows, 128 UDP destination sockets, 64 KiB per buffer,
128 entries per channel, and MTU 1500. Logical queued payload bounds are:

- TCP: four directions/buffers across smoltcp and the duplex bridge, so
  `512 * 64 KiB * 4 = 128 MiB`.
- UDP socket storage: `128 * 64 KiB * 2 = 16 MiB`.
- UDP receive/reply channels: at most `128 * 65507 * 2`, approximately 16 MiB.
- Packet channels plus 32-packet staging: `(128 * 2 + 32) * 1500`, about 422 KiB.
- Four IPv4 and four IPv6 reassembly sets, plus outgoing fragmentation scratch,
  are bounded separately. Every admitted IP fragment has a length/offset bound.

These are payload limits, not a process RSS claim: allocator capacity, metadata,
Tokio tasks, Wintun rings and Core/protocol buffers are additional. Configuration
validation rejects a calculated buffered-payload budget above 1 GiB. The loop
uses bounded ingress/stream batches and cooperative yields. UDP overload drops
are counted; TCP buffer pressure stops reads and reaches TCP flow control.

## Executed verification

`cargo test -p swirl-tun` executes 14 packet integration tests and two IPv6
reassembly unit tests. Coverage includes IPv4/IPv6 TCP handshake/payload/FIN,
reply after peer half-close, dispatcher-failure RST, duplicate SYN admission,
connection limits, destination/source isolation, UDP empty messages/checksums,
bad-packet recovery, dual-stack fragmentation/out-of-order reassembly, overlapping
IPv6 fragments, slot expiry, blocked-output shutdown, and a byte-exact 1 MiB reply
with 4 KiB TCP buffers and queue capacity two. The latter is a correctness test,
not a throughput benchmark. `cargo clippy -p swirl-tun --all-targets -- -D warnings`
and `cargo fmt -p swirl-tun -- --check` are separate static gates.

These tests do not create a Windows adapter or prove Windows TUN acceptance.
Wintun packet I/O, real sockets through Core, routes/DNS, network recovery and
applications require their own integration and Windows evidence.

## Explicit boundaries

- ICMP echo auto-reply is disabled; the stack must not synthesize a successful
  ping to an unreachable Internet host. End-to-end ICMP/PMTU relay is not provided.
- A fragmented initial IPv4 TCP SYN cannot establish a new stream. Established
  TCP packet handling remains with smoltcp. IPv6 fragments are reassembled before
  admission and do not have that particular admission limitation.
- IPv6 extension support follows the upstream L3 implementation; arbitrary routing,
  IPsec, multicast, jumbograms and scoped link-local egress are not claimed.
- TCP idle and pending-handshake deadlines are configurable. Fragmentation and
  UDP endpoint limits deliberately discard excess state rather than grow memory.
- Domain association, DNS upstream selection, egress pinning, node changes and
  protocol support are Core/controller responsibilities, not duplicated here.

## Dependency audit: 2026-10-29

The final Cargo.lock passed `cargo-audit 0.22.2 --deny warnings` against official
RustSec database commit `ee1a49a2769a24a596afc1c20cb33748d2769586`: zero
vulnerability matches and zero warnings, with no ignored advisories or platform
filter. The review first found seven vulnerabilities and ten unsoundness warnings
in baseline dependencies; it then updated only ctutils, rustls-webpki,
webpki-roots and the three-package zstd family to their minimum fixed versions.
The unchanged MRS/routing suite passed all 25 tests after those updates.

The complete [dependency and security review](../../docs/NATIVE_TUN_DEPENDENCIES.md)
records every initial advisory and its actual call-path/feature applicability,
the before/after lockfile hashes, exact versions, licenses, upstream source
revisions, and reproduction commands. It also lists the 17 new third-party
packages separately from the security updates. `core/DEPENDENCIES.json` now
covers all 207 locked third-party packages, including build/target dependencies
and vendored rustls, plus the separately distributed Wintun runtime artifact.

Wintun 0.14.1's official signed DLL has its own binary license and verified
x64/ARM64 hashes; the Rust binding's MIT license does not replace those terms.
The missing c2rust-bitfields 0.18.0 archive notice is retained from its exact
upstream revision in `swirl-platform/licenses/C2RUST-BITFIELDS-0.18.0.txt`.
A passing dependency audit does not establish real Windows TUN acceptance.
