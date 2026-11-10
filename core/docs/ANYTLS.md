# Native AnyTLS

The product uses Rust for AnyTLS TCP and connected UDP-over-TCP v2. The wire
implementation is written from the public [AnyTLS protocol specification](https://github.com/anytls/anytls-go/blob/fd6167acd6d73b9fa3e607659951847fbc9e6c50/docs/protocol.md)
and [UoT specification](https://sing-box.sagernet.org/configuration/shared/udp-over-tcp/).
No external proxy process or downloaded peer binary is part of the product.

The native adapter accepts the supported Clash/Surge fields: endpoint, password,
SNI, ALPN, UDP enablement, and ordinary TCP. TLS chain, date, name and handshake
verification remain mandatory. Unknown transport/fingerprint options and
nonempty certificate-pin requirements fail closed. The existing importer may
project a source request to skip certificate checking to strict verification,
with its persistent notice and encrypted original preserved. Direct native
configuration cannot disable verification. An empty `pcs` has no pin to enforce.

Each TLS session authenticates with the password digest and current padding
scheme, sends client settings, and accepts bounded server padding updates.
The client negotiates v2 while retaining v1 compatibility. First-session setup
does not claim authentication success until target data returns; an already
negotiated v2 session waits for SYNACK. UoT v2 includes its connect request with
the initial target so it cannot deadlock waiting for that acknowledgement.
FIN closes a logical stream; the protocol does not provide TCP half-close.

Session reuse follows the reference client's newest-idle-session policy, with
one active logical stream per session. Each client permits at most 16 sessions
including pending sockets. Queues, stream buffers, control frames and padding
schemes are bounded. Partial frames and writes have five-second deadlines;
v2 SYNACK has a three-second deadline; idle sessions expire after 60 seconds
by default (native configuration allows 5–300 seconds). Cancellation before
stream admission retires the reserved session. Slow readers eventually close
their session rather than retaining an unbounded buffer.

Pools are scoped by immutable configuration owner, Tokio runtime, captured TUN
egress epoch, credentials, TLS policy and the resolved proxy addresses. The
registry holds no strong configuration-owner reference. Releasing the last
owner aborts every owned session and its reader task. Existing egress socket
admission and TLS transport remain in the dial path. A process with the optional
private acceptance quota cannot use AnyTLS pooling; it fails before DNS or a
socket attempt. Beginning normal AnyTLS use also prevents installing that
process-wide guard later, so a pooled socket cannot cross a billing boundary.
An explicit inherited physical-probe context preserves the caller's verified
scope identity in its socket-owning actor. Every actor write/flush checks that
scope and the current egress epoch. Actor retirement also releases empty client
entries; 160 sequential resolved identities exercise reuse of the bounded
registry rather than consuming a lifetime counter of previous probes.

## Verification

`cargo test --locked -p swirl-protocol -p swirl-subscription --lib anytls`
checks parser requirements, frame fragmentation, timeouts, TLS-handshake
cancellation, reuse acknowledgement, stale stream IDs, pool isolation and
owner cleanup. The independent process guard regression is:

```text
cargo test --locked -p swirl-protocol --features private-acceptance --test anytls_private_guard
```

The strict official peer gate is:

```text
python scripts/Test-AnyTlsInterop.py --work-dir <isolated-evidence-directory>
```

It fetches the exact upstream revision above, verifies Go modules, and builds a
test-only peer with Go >=1.24.0. Only test certificate selection, readiness and
read-only counters are patched; upstream authentication, framing, padding,
session and TCP/UDP forwarding code remain unchanged. All listeners bind
loopback. The gate requires the Rust test to actually run, retires its own peer,
and writes a sanitized JSON receipt with revision, Go version, executable and
module-lock hashes. CI binds that receipt to its source/run and never packages
the fixture.

The peer test covers strict TLS, incorrect CA/name/password rejection, large
TCP echo, two concurrent sessions, idle reuse, padding updates, short and
1400-byte UDP packets, the session limit and final socket retirement. The pinned
upstream peer's `sing v0.5.1` dependency panics on a zero-length UDP datagram;
this upstream limitation is not patched or counted as interoperability success.
Loopback results do not establish provider connectivity, complete subscription
configuration execution or system-wide TUN acceptance.
