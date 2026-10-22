# X1.4-A3: native Hysteria 2 implementation and independent interoperability

## Result and acceptance boundary

On 2026-10-22, Swirl's Rust client completed real Hysteria 2 authentication and
bidirectional TCP/UDP transfer through the fixed official Hysteria v2.13.0
server. The client does not launch or embed Hysteria, Xray, sing-box, Mihomo, or
another complete proxy core. The official executable runs only as the remote
protocol peer. Separate Python TCP echo, UDP echo, DNS, and HTTPS origins supply
the destination traffic.

The final direct-protocol run executed 17 test groups containing 41 client
invocations: 29 successful data-transfer cases, 10 expected credential/security/
configuration rejections, and 2 explicit upstream-limitation probes. Both
limitation probes retain `ok: false`; they are not successful half-close or
4096-byte UDP interoperability. No test group was skipped in this Linux run.

This document does **not** establish Windows Qt product acceptance. The direct
protocol fixture also does not establish the separate Core SOCKS5 ingress
integration result; that is recorded by `tools/tests/test_quic_core.py` and its
own receipts. Cross-platform CI must be assessed from the actual workflow run.

## Implemented path

`hy2://` / `hysteria2://` or Clash node -> subscription inspection ->
`Outbound::Hysteria2` -> unified Rust protocol connector -> resolver ->
Quinn/rustls QUIC/TLS 1.3 -> HTTP/3 authentication -> Hysteria TCP stream or
fragmented QUIC datagrams -> independent destination.

The native implementation includes:

- Strict configuration validation and import alias checking, including default
  port 443, UUID-independent password credentials, IPv6 authorities, SNI, ALPN
  `h3`, explicit insecure mode, and SHA-256 certificate pins.
- HTTP/3 `POST https://hysteria/auth`, authentication status 233, UDP negotiation,
  random padding, and response bounds. H3 ownership and its driver remain alive
  for the lifetime of the authenticated session.
- Hysteria TCP request type `0x401`, bounded response parsing, bidirectional
  stream I/O, error response handling, and clean close after complete transfer.
- UDP session IDs and packet IDs, QUIC Datagram fragmentation, out-of-order
  reassembly, duplicate/conflict rejection, and bounded assembly storage.
- Salamander's random eight-byte salt and BLAKE2b-256 mask on actual QUIC UDP
  packets. Kernel GRO segments are decoded independently. Obfuscation keys use
  zeroizing owned buffers and are omitted from diagnostics.
- Decimal Mbps -> bytes/s conversion. `down_mbps` is sent in the authentication
  receive-rate header. The client upload ceiling and the server receive ceiling
  are enforced by a nonblocking datagram pacer. Cubic remains the congestion
  controller. This is **not an implementation of Brutal** and does not claim
  equivalent congestion behavior on lossy WAN paths.
- A handshake deadline shared by resolution, QUIC/TLS, HTTP/3, authentication,
  and target TCP setup. Resolved server addresses are tried through the common
  QUIC connector. Dropping the final session owner closes its endpoint and
  aborts the H3 driver.

The sender pacer has no packet queue or independent background task. It uses
Quinn's existing writable poller and a Tokio timer; idle time does not build an
unbounded transmission allowance. Salamander salt bytes count toward the wire
upload limit. The common wrapped-socket QUIC path uses a 1200-byte initial MTU
with probing disabled to preserve outer-header room.

### Import and security rules

Mihomo's Hysteria `fingerprint` field is a certificate SHA-256 digest and maps
to `pin_sha256`. It is not a browser ClientHello profile. Unknown critical
fields, conflicting aliases, malformed pins, malformed certificate input,
invalid ALPN, unsupported obfuscation, or overflowing bandwidth values fail
before a connector is started. A configured certificate pin is checked even
when the user explicitly sets `insecure`.

Normal connections validate the certificate chain and server name. Test
certificates use an ephemeral local CA passed explicitly to the Rust client;
the positive TLS cases do not depend on silently disabling verification.
Native import of the test CA uses the explicit `ca-der-base64` extension.

## Fixed official peer

Repository: <https://github.com/HyNetworks/hysteria>

- Release/tag: `app/v2.13.0` / `v2.13.0`.
- Source commit: `ca8fbd874fd6ca82413948de6dc5924405e103e1`.
- Release download base:
  <https://github.com/HyNetworks/hysteria/releases/tag/app/v2.13.0>.

| Official asset | SHA-256 |
| --- | --- |
| `hysteria-linux-amd64` | `907ba8c9693edb104b20582681fb7dc15639d5b64a9cbb616a7b539190a86691` |
| `hysteria-darwin-amd64` | `7a155230ae4bbffc92657f486484a48ed703bd828abf7a3e19287fea1f9ca74a` |
| `hysteria-darwin-arm64` | `c8c3589239ce4ecf335c07a3f6ec11b3ef8fbdfe9e5a5ea0ef8ba8ce50d2bb90` |
| `hysteria-windows-amd64.exe` | `162ef8fe55dc7ec810dda662908f8e65ec36bd6da39cb87c3bd66184ab68f067` |

The test checks the binary digest and actual `version` output before starting
it. Each server is launched with `hysteria server -c <temporary-config.json>`.
Configuration, generated CA/private keys, and synthetic passwords exist only
inside the temporary test directory. The fixture records safe fixed error
codes, transfer sizes, hashes, versions, and timings; it does not copy secrets
or server logs into the receipt.

## Actual tested combinations

| Combination or property | Linux native result |
| --- | --- |
| QUIC + TLS 1.3 + H3 password authentication + TCP | Passed |
| TCP 4 MiB upload and identical 4 MiB return | Passed; SHA-256 checked |
| TCP close after complete bidirectional transfer | Passed |
| UDP payloads 200, 3072, and 4000 bytes | Passed; fragmented messages checked |
| DNS request and response over native UDP | Passed |
| HTTPS with independent target certificate verification | Passed, including TLS close-notify |
| Incorrect Hysteria password | Rejected |
| Untrusted server certificate and wrong SNI | Rejected |
| Correct and incorrect certificate pins | Correct accepted; incorrect rejected |
| Explicit insecure plus certificate pin | Pin still enforced |
| Clash JSON and both Hysteria URI spellings | Imported configuration ran through Rust |
| Node A/B switching and a fresh session after server restart | Passed |
| Salamander TCP 1 MiB and UDP 3072 bytes | Passed |
| Incorrect Salamander password | Connection rejected/timed out |
| Upload limit, server receive limit, download negotiation at 1 Mbps | Passed with actual measured transfers |
| IPv6 QUIC server and IPv6 TCP/UDP destinations | Passed |
| Four simultaneous TCP connections | Passed; each returned its full 256 KiB |
| `localhost` multi-address server lookup to an IPv4 listener | Passed |
| Unsupported/malformed security and transport options | Rejected with explicit codes |
| Write half-close followed by delayed reverse data | **Not passed**, retained upstream limitation |
| 4096-byte UDP echo reply through official v2.13.0 | **Not passed**, retained upstream limitation |

### Measured values, with their scope

These are unoptimized Linux loopback observations from
`bandwidth-ipv6-concurrency.json`, not WAN benchmarks or pure TCP latency.

| Measurement | Observation |
| --- | --- |
| 4 MiB upload plus identical return and normal close | 442.256 ms total; 18.921 ms combined DNS/QUIC/auth/target setup |
| Salamander 1 MiB upload plus return | 169.532 ms total |
| Client upload ceiling 1 Mbps, 256 KiB echo | 2446.725 ms total |
| Server receive ceiling 1 Mbps, 256 KiB echo | 2437.669 ms total |
| Negotiated download ceiling 1 Mbps, 256 KiB echo | 2146.431 ms total |
| Four concurrent 256 KiB echoes | Each completed, 45.213–76.612 ms client total |

The example names its setup measurement `dns_quic_auth_tcp_us` or
`dns_quic_auth_us`. It intentionally does not label that combined interval as
pure TCP latency. Separate DNS/TLS/auth telemetry for the product-wide speed
test API remains integration work.

## Reproduction

Build with the repository's locked dependencies:

```sh
cd core
cargo build -p swirl-protocol --example hysteria2-client --locked
cargo test -p swirl-protocol --lib hysteria2 --locked
cargo test -p swirl-subscription --lib hysteria2 --locked
```

Run the independent-peer fixture from the repository root, with Python's
`cryptography` package installed and the verified server binary downloaded:

```sh
HY2_SERVER=/absolute/path/hysteria-linux-amd64 \
HY2_CLIENT=/absolute/path/target/debug/examples/hysteria2-client \
HY2_EVIDENCE=/absolute/path/hysteria2-result.json \
python tools/tests/test_hysteria2_official.py
```

On Windows, point `HY2_CLIENT` and `HY2_SERVER` at their `.exe` files. The script
accepts the pinned platform asset digests listed above, but only an executed
platform run is evidence for that platform. An unavailable IPv6 loopback is
reported explicitly as an unexecuted case and a skipped test.

The focused Rust result was 8 protocol tests and 5 configuration tests passed.
The final official fixture result was `Ran 17 tests in 18.661s / OK`. The
focused Clippy invocation initially encountered an unrelated, concurrently
developed `ss2022::HeaderCipher` large-enum warning; the final workspace Clippy
status belongs in the integration report, not a fabricated per-protocol pass.

## Retained failures and current limitations

1. **Half-close:** official v2.13.0 `copyTwoWay` returns when either copy
   direction ends, and the server then closes both sides. A destination that
   waits for FIN before replying therefore loses the reverse data. The original
   failed test and a dedicated delayed-origin probe are retained. The positive
   normal-close test completes both directions before closing; it does not
   reclassify the half-close failure.
2. **UDP reply buffer:** official v2.13.0 allocates 4096 bytes for an encoded
   UDP message. For an address length `A`, an echo reply must satisfy
   `payload + 8 + QUIC-varint-length(A) + A <= 4096` to fit that buffer before
   its fragmentation retry. The 4096-byte payload demonstrably reached the
   independent UDP target, but the official reply was dropped. The receipt
   records both the timeout and origin receipt. Payloads 3072 and 4000 passed;
   the general 65507-byte native bound is a resource limit, not an official-peer
   acceptance claim for that full range.
3. **Empty UDP:** the pinned official parser requires at least one payload
   byte. Swirl rejects zero-length Hysteria datagrams explicitly.
4. **Port hopping/multiple server ports, ECH, Gecko, browser fingerprint
   emulation, and explicit network migration:** not implemented and not marked
   accepted. Configurations requesting unsupported options are retained by the
   import layer and blocked with a diagnostic rather than silently downgraded.
5. **Brutal and WAN tuning:** not implemented. Current bandwidth ceilings work
   with Cubic; no performance equivalence with the official Brutal controller
   is claimed. Cross-connection TCP pooling is also not established by this
   fixture, although an authenticated `Session` can open multiple streams.
6. **Qt product end to end:** not executed by this fixture. Product launch,
   QML selection, Windows DLL use, and product HTTPS browsing remain separate
   acceptance gates.

The first failed attempt also exposed missing TLS close-notify in the HTTPS
origin fixture. The independent origin was corrected to send and receive TLS
shutdown properly. Subsequent HTTPS tests passed with certificate verification
and checked that the origin recorded no TLS shutdown errors.

## Evidence and sources

Receipts are kept unchanged under `docs/evidence/x14-a3-hysteria2/`:

- `attempt-1.json`: original failures, including half-close, large UDP reply,
  and the HTTPS fixture close-notify problem.
- `normal-close.json`: corrected normal-close/HTTPS fixture run with the two
  upstream limitations retained as negative probes.
- `salamander.json`: independently verified obfuscation and pin enforcement.
- `bandwidth-ipv6-concurrency.json`: final 41-invocation run. Client binary
  SHA-256: `3d5e852e6a7f263f6cee2f6095b13e3f6fd0710e0951613d0a60970a22e967b6`.

Primary references used for independent implementation and limit diagnosis:

- [Official Hysteria 2 protocol](https://v2.hysteria.network/docs/developers/Protocol/).
- [Official Hysteria URI scheme](https://v2.hysteria.network/docs/developers/URI-Scheme/).
- [Mihomo Hysteria2 configuration](https://wiki.metacubex.one/en/config/proxies/hysteria2/).
- [Pinned upstream TCP copying](https://github.com/HyNetworks/hysteria/blob/app/v2.13.0/core/server/copy.go).
- [Pinned server stream lifetime](https://github.com/HyNetworks/hysteria/blob/app/v2.13.0/core/server/server.go).
- [Pinned UDP reply handling](https://github.com/HyNetworks/hysteria/blob/app/v2.13.0/core/server/udp.go).
- [Pinned wire constants/parser/serializer](https://github.com/HyNetworks/hysteria/blob/app/v2.13.0/core/internal/protocol/proxy.go).
- [Pinned Salamander implementation](https://github.com/HyNetworks/hysteria/blob/app/v2.13.0/extras/obfs/salamander.go).

New general-purpose dependencies were reviewed through their published crate
manifests: Quinn `0.11.12` (MIT OR Apache-2.0), h3 `0.0.8` (MIT), h3-quinn
`0.0.10` (MIT), and RustCrypto blake2 `0.10.6` (MIT OR Apache-2.0). They provide
QUIC, HTTP/3, and hashing; Hysteria authentication, proxy framing, configuration,
UDP sessions, obfuscation integration, and bandwidth policy are Swirl Rust code.
