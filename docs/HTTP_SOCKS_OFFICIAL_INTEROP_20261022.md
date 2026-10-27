# HTTP CONNECT and SOCKS4/4a/5: official Xray interoperability

## Result and scope

On 2026-10-22, `tools/tests/test_basic_proxies_xray.py` completed **8 tests,
0 failures, 0 errors, 0 skips** on Linux in **5.516 seconds**. The client is the
compiled Swirl Rust Core. The unmodified official Xray executable is used only
as an independent proxy server. HTTP, HTTPS, TCP echo and UDP DNS destinations
are independent local application services. This is Rust native interoperability;
it is not Windows Qt product acceptance or a public-Internet throughput result.

Raw receipts:

- [`official-xray.json`](evidence/x14-a6-basic-proxies/official-xray.json)
- [`official-xray.log`](evidence/x14-a6-basic-proxies/official-xray.log)

The JSON records the actual suite outcome, binary SHA-256 hashes, 75 observations,
18 independent server instances, redacted server configurations, startup commands
and hashes/counts of official server access logs. No skipped test is counted as a
pass. Missing binaries or a server version mismatch fail setup.

| Protocol combination | Real data and authentication evidence | Result |
| --- | --- | --- |
| HTTP CONNECT without authentication | Xray JSON import → unchanged native config → Core HTTP/SOCKS5 ingress → official server → HTTP/HTTPS target | Passed |
| HTTP CONNECT with Basic username/password | Same chain; target bytes verified; wrong username/password and absent authentication produce 502 and zero target requests | Passed |
| SOCKS5 without authentication | TCP HTTP/HTTPS through both Core ingress types; UDP echo and a real DNS wire request/reply | Passed |
| SOCKS5 username/password | TCP/UDP paths; wrong TCP and UDP credentials cannot reach their targets | Passed |
| SOCKS4 TCP CONNECT | V2Ray v4 JSON import → unchanged native config; IPv4 destination; empty and nonempty USERID; HTTP and HTTPS application data | Passed |
| SOCKS4a TCP CONNECT | V2Ray v4 JSON import → unchanged native config; `localhost` is sent as a remote domain; empty and nonempty USERID; HTTP and HTTPS application data | Passed |
| IPv6 proxy endpoint | Authenticated HTTP and SOCKS5 server on `::1`; fresh connections after official server restart | Passed |
| Node selection | Four live HTTP/SOCKS5 nodes; old connection survives switches; four concurrent new connections use the selected node | Passed |

There are 35 HTTP/HTTPS application exchanges, two additional 2 MiB uploads with
matching 2 MiB replies, and a TCP connection that remains usable across node
switches. The UDP success cases each send 1, 37, 1400 and 4000-byte payloads and
one DNS query; all application replies are checked. The official server's access
log and destination-side observations corroborate the relay path. Closing
associations and streams must return the native Core's active count to zero.

SOCKS4 USERID is an identifier, not password authentication. The suite does not
relabel it as an authenticated password handshake. The source `settings.version`
field for these cases is the V2Ray v4 JSON dialect documented since v4.42.2;
it is not a claim that Xray 26's SOCKS client schema has that field. Swirl's
existing Xray/V2Ray importer preserves the selected version and USERID, and the
actual official Xray **server** supports the resulting SOCKS4/4a wire handshake.

## Import semantics corrected during this verification

The first version of the additional suite exposed a real import gap: Xray JSON
SOCKS5 nodes were exported with `udp:false`, although upstream's SOCKS outbound
has no UDP opt-in field. Its client switches to UDP ASSOCIATE when the requested
destination network is UDP. The imported node therefore lost an existing source
capability before reaching the Rust connector.

`core/crates/swirl-subscription/src/xray/convert/native.rs` now emits
`udp: mapping.tls.is_none()` for the supported SOCKS5 mapping. The final suite
asserts that the imported node has UDP enabled, then passes the complete exported
configuration unchanged to Core for both UDP success and wrong-credential cases.
There is no post-export UDP, credential or transport mutation.

The existing boundary for TLS-protected SOCKS5 control remains unchanged: native
TLS SOCKS5 is TCP-only here; attaching an unverified plaintext UDP channel is not
enabled implicitly. Unknown source fields and invalid authentication continue to
be rejected by the importer.

Primary source checked at the pinned official commit:

- [Xray SOCKS client schema](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/socks.go)
- [Xray SOCKS outbound implementation](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/socks/client.go)
- [Xray SOCKS4/4a server handshake](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/socks/protocol.go)
- [Xray HTTP Basic account configuration](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/http.go)
- [V2Fly's SOCKS outbound version field](https://www.v2fly.org/config/protocols/socks.html#outboundconfigurationobject)

## Reproduction

The fixed peer is Xray **26.10.21**, commit
`1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`. The Linux executable SHA-256 used for
this run is `a27e3f95ab6ce270956d0cecd32eda4686a811afc71c64a6a734a3dede14883e`.
`tools/Fetch-TransportPeers.py` uses the committed archive hashes in
`tools/tests/transport-peer-lock.json` for Windows, macOS and Linux. The new suite
checks the peer version before it starts any protocol tests.

Build the actual client binaries with the committed lockfile:

```sh
cargo build --manifest-path core/Cargo.toml --workspace --bins --examples --locked
python tools/Fetch-TransportPeers.py --output out/peers/xray
```

Set `SWIRL_TRANSPORT_RUNTIME` to `transport-runtime`, `SWIRL_TRANSPORT_CLIENT` to
`transport-client`, `SWIRL_INSPECT_BINARY` to `swirl-inspect`, and
`SWIRL_XRAY_BINARY` to the downloaded `current/xray` (use `.exe` on Windows).
`SWIRL_TRANSPORT_CLIENT` is required by the shared fixture, while this suite's
traffic is driven through the actual `transport-runtime` Core ingress.

```sh
SWIRL_BASIC_PROXY_EVIDENCE=out/native-interop/basic-proxies.json \
  python tools/tests/test_basic_proxies_xray.py
```

Each isolated peer is started as `xray run -config <generated-peer.json>` with
only loopback TCP/UDP destinations allowed by its freedom outbound. Synthetic
credentials are defined in the test source. Process lifetime, sockets and native
Core shutdown are bounded; the official server is never used as a client engine.

## Timing and remaining scope

The 2 MiB each-way HTTP CONNECT exchange took **1226.267 ms**, and SOCKS5 took
**1286.444 ms** in the recorded run. These are complete application exchanges,
including connection establishment, Python payload generation and byte/hash
verification, in an unoptimized local build. They are neither pure TCP latency
nor protocol throughput benchmarks.

Normal application completion and closure passed. The suite does not establish
strict request-half-close-before-response semantics, maximum-size UDP delivery,
TLS-protected SOCKS5 UDP, SOCKS BIND, GSSAPI, or Qt product integration. Their
status must not be inferred from these results. Cross-platform CI results are
reported by the actual workflow runs rather than this Linux receipt.
