# Native protocol acceptance baseline — 2026-11-04

Source inspected: `f4efe047858c9470b64071aeb620809316e75db7` on `test`.
This inventory describes implemented paths and existing checks, not blanket
provider, desktop, performance or physical Windows acceptance. The follow-up
packet-fixture correction below is an uncommitted change after that source.

## Existing native runtime and format boundaries

All runtime paths remain Rust. Independent peer programs below are test servers,
not shipped or invoked as substitute Swirl cores.

| Area | Existing implementation | Explicit limits / acceptance still needed |
| --- | --- | --- |
| HTTP CONNECT, SOCKS4/4a, SOCKS5 | Native TCP; HTTP and SOCKS5 can use the represented TLS options. SOCKS5 UDP exists. | SOCKS5 UDP over TLS is rejected. Provider and real application acceptance is separate. |
| Shadowsocks | Native supported AEAD TCP/UDP, plus native SS2022 TCP/UDP. | SS2022 supports its represented AES methods; optional ciphers and identity chains are rejected. Unsupported plugins are not silently removed. |
| VMess | AEAD, `alterId=0`, supported ciphers, TCP/WS/WSS. | Legacy alterId, UDP, unsupported fingerprints/transports and unmapped requirements are rejected. |
| VLESS / Trojan | Native TCP and supported stream UDP; WS and typed gRPC/HTTP2/HTTPUpgrade/XHTTP transports; VLESS REALITY/Vision paths already exist. | Transport constraints remain checked. XHTTP is `stream-one`; Vision UDP/transport combinations and unsupported options are rejected. Pinned Xray interoperability is narrower than arbitrary current Xray compatibility. |
| Hysteria2 | Native QUIC, HTTP/3 authentication, TCP, UDP fragmentation, Salamander, certificate/pin handling and cancellation cleanup. | Port hopping, ECH and unsupported obfuscation are explicitly blocked. TCP currently creates a new session for each connect; measure this before deciding whether a bounded reuse design is justified. |
| TUIC | Native v5 UUID/password exporter authentication, TCP, native/QUIC UDP relay modes, heartbeat, egress-isolated bounded weak TCP-session cache. | v4/token and unsupported options remain rejected. The historical official reference server's empty-UDP-reply limitation is recorded rather than counted as a pass. |
| Other catalog protocols | The inspector recognizes SSR, Hysteria1, AnyTLS, Snell, Mieru, WireGuard, SSH and Naive names. | Recognition/provenance is not native execution. These have no corresponding executable `Outbound` variant. Other requested protocol families may be unknown rather than merely unsupported. |
| Imported formats | Content inspection for Clash YAML/JSON, sing-box JSON, Xray/V2Ray JSON, URI lists, supported INI dialects and Base64 wrappers. Loon positional VMess and HTTP(S) now map through the actual typed Rust boundary. | Entire foreign configurations are not interchangeable runtime profiles. Strict supported Clash/INI/sing-box projection is distinct from data-only nodes; scripts, providers, listeners and unmapped global semantics remain inert or rejected. Original source is retained privately. |

Owning sources: `core/crates/swirl-subscription/src/lib.rs`, `inspect.rs`,
`profile.rs`, `stream_transport.rs`, protocol-specific mapping modules,
`core/crates/swirl-protocol/src/{lib,hysteria2,tuic}.rs`, and
`core/crates/swirl-core/src/v2.rs` UDP admission/dispatch.

## Reuse existing evidence instead of duplicating implementations

- `rust-core.yml` already runs native interoperability against pinned independent
  Hysteria2, historical TUIC v5 and Xray servers. Its Windows Qt QUIC step checks
  six exact positive/rejection cases through Qt import, DPAPI persistence and
  source-paired Rust, including Hysteria2 Salamander and both TUIC UDP modes.
  Fixture hashes and scope are in `tools/tests/native-protocol-peer-lock.json`
  and `test_singbox_quic_product.py`.
- Existing Hysteria2 official/lifecycle, TUIC reference, QUIC Core/FFI and
  REALITY/Vision suites cover more than the GUI protocol catalog. Their existence
  does not mean the current SHA has passed every job.
- `tools/tests/test_proxy_stream_soak.py` supports 60–3600 seconds, but current CI
  invokes 120 seconds with eight connections. It observes controlled local
  authenticated SOCKS5 + verified TLS/SSE traffic, RSS/FD samples and cleanup.
  It does not establish a one-hour real provider run, Codex Desktop acceptance,
  leak absence or throughput relative to another client.
- The expanded goal still needs actual per-protocol TCP/UDP/DNS/IPv6 results,
  real application behavior, equivalent-node reference comparisons, repeated
  performance measurements and at least one hour of stability evidence. Preserve
  failures, missing samples and unrun scope explicitly.

Official primary references checked before this audit/fix:
[Hysteria protocol](https://github.com/HyNetworks/hysteria/blob/master/PROTOCOL.md),
[TUIC protocol](https://github.com/tuic-protocol/tuic/blob/master/SPEC.md),
[smoltcp TCP/example](https://github.com/smoltcp-rs/smoltcp/blob/main/examples/server.rs),
[Rust socket2 socket state](https://github.com/rust-lang/socket2/blob/master/src/socket.rs),
[Microsoft FIONBIO documentation](https://github.com/MicrosoftDocs/win32/blob/docs/desktop-src/WinSock/winsock-ioctls.md).
No upstream implementation was copied.

## CI observations for head f4efe047

| Check | Observed result | Scope / outstanding action |
| --- | --- | --- |
| [Swirl Native LAN](https://github.com/SOLHK/Swirl/actions/runs/41839437415) | Windows, Linux and macOS jobs passed. | Push run at exact head; owned/disposable fixture evidence, not physical LAN acceptance. |
| [Legacy Native TUN](https://github.com/SOLHK/Swirl/actions/runs/41839450813) | Passed. | PR run for this head. The obsolete-package workflow correction did not remove stronger native checks. |
| [Isolated Native TUN](https://github.com/SOLHK/Swirl/actions/runs/41839450830) | Linux passed; Windows backend and security jobs failed. | PR run checks its synthetic merge commit. Backend failed the real shared-Core packet half-close fixture. Security still had required and headless children exit `0xc0000142` before producing output. Security remains unaccepted. |
| Full font authored suite | No font run was triggered at this CI-only head. Earlier e073 font runs were cancelled. | A new Linux authored-suite run is required; cancelled Windows/Unix fixture results are not passes. |

## Windows packet fixture correction and evidence

The half-close failure was reproduced locally against the real shared Core and
loopback peers using the GNU Windows build. Added diagnostics report only the
fixture's IP-family flag, byte counts and TCP sequence/FIN positions; peer and
transfer failures are preserved together. In 200 executions before the fix,
five failed with zero reply bytes (early FIN or RST). A further 100 diagnostic
executions failed five times; every failing peer reported Winsock `10035`.

The fixture used a nonblocking accept loop and then assumed its accepted socket
was blocking. On Windows the inherited mode let the first ordinary read return
`WouldBlock` before request bytes arrived. Dropping that failed test peer caused
the apparent data-plane failure. The correction explicitly calls
`stream.set_nonblocking(false)` after accept, retaining the 15-second read/write
timeouts, exact 1024-byte request followed by FIN and exact 128-KiB reply followed
by FIN. No runtime, TCP stack or security boundary changed.

After the correction, the complete `windows-packet-worker-smoke` example suite
passed **3/3** and the real packet scenario passed **200/200 separate executions**,
each exercising both IPv4 and IPv6. The runner verified one test executed in
each iteration, so an empty filter cannot count as a pass. Scoped rustfmt,
`cargo clippy --locked -p swirl-api --example windows-packet-worker-smoke --target
x86_64-pc-windows-gnu -- -D warnings`, and changed-file whitespace checks passed.
This is local GNU evidence; rerun the original Windows CI gate at the final
commit. It does not fix or satisfy restricted-worker loader isolation.
