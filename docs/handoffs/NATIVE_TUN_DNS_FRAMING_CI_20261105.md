# Native TUN DNS framing fixture isolation

Source under test before the change: `76d40dbb96eb5a2333b1213c3cb383da7d8e237c`.

The [Linux isolated TUN job](https://github.com/SOLHK/Swirl/actions/runs/41864797154/job/126696150023)
failed one of 142 Core unit tests:
`packet_bridge_ipv4_tcp_dns_frames_finish_and_truncation_resets`.
The next case's handshake expected destination port 44001 but consumed a queued
packet for the completed port-44000 flow. Waiting for `active_tcp_flows == 0`
does not establish that the bridge's output channel has been drained. The
[upstream smoltcp socket implementation](https://github.com/smoltcp-rs/smoltcp/blob/main/src/socket/tcp.rs)
also has independent per-socket packet and close state; the fixture must not
assume a global packet order across completed flows.

Each complete-frame, partial-prefix and partial-payload case now creates its
own PacketBridge and FakeIpStore, resolves its own fixture address, and shuts
down and joins that bridge before the next case. The original exact packet
tuple, TCP sequence, FIN/RST, absence of invalid responses, and two complete
DNS-response byte assertions remain. Failure counters are checked per bridge:
zero for the complete case and exactly one for each truncated case. Malformed
packet and shutdown completion checks apply to every case. Runtime and packet
parsing code are unchanged; no arbitrary packets are skipped.

Local Windows GNU validation on 2026-11-05:

- Built the actual `swirl-core` native-TUN test binary, with locked dependencies
  and Cargo offline mode.
- Ran both IPv4 and IPv6 entry points 50 times each, with two concurrent test
  processes: all 100 tests / 300 framing cases passed. The existing toolchain
  does not contain cargo-nextest; a bounded harness repeated the actual libtest
  executable instead, without installing tools.
- Full `swirl-core --features native-tun`: 171 passed, zero failures or skips.
- Full `swirl-tun`: 37 passed, zero failures or skips.
- `swirl-core --features native-tun --all-targets` Clippy with warnings denied,
  workspace formatting, and changed-file whitespace checks passed.

This local result does not replace a new-head Linux CI run. All execution used
controlled packet/loopback fixtures; no provider, real node, driver installation,
host route, system proxy, DNS, or TUN setting was changed.

## Follow-up: portable TCP/UDP allocation contract

The new-head Linux isolated packet/Core step passed on `8ad5f8507e0afdb9440317ea6767e03d0c0dd75b`.
Its [Windows Rust Core job](https://github.com/SOLHK/Swirl/actions/runs/41869694887/job/126713076163)
then exposed an independent Python fixture assertion in
`test_portable_pairs_use_os_allocation_without_querying_netsh`: a valid bind
collision led to two TCP port-zero requests, but the test required exactly one.
The allocator already permits bounded EADDRINUSE/10048 retries. Its final pair
had succeeded; the primary failure was this assertion, while later missing
artifact steps were consequences of the early exit.

The fixture now requires every TCP request to use the correct loopback host and
port zero, then verifies both live sockets have the same actual endpoint and
close afterward. A deterministic first-UDP-EADDRINUSE case covers Linux/Darwin
selection and both IP families, proves prior socket owners are closed, and
proves the successful pair stays owned without querying netsh. The existing
eight-collision budget, exclusion ownership, and unknown-access-denial checks
remain. `loopback_ports.py` and production code are unchanged. This follows
the [CPython socket-test approach](https://github.com/python/cpython/issues/82878)
of retaining a bound OS-allocated socket rather than assuming an available port.

The exact original `8ad5f850` fixture was executed with a controlled first UDP
collision: all four platform/family subcases failed its one-request assertion,
with no errors. The current two portable tests passed. The complete DNS-negative,
DoT, DoH and Shadowsocks modules executed 73 tests: 72 passed and one existing
Qt Shadowsocks integration test was skipped because no Qt executable was supplied.
The native Shadowsocks cases ran. These loopback-only tests used the frozen
exact-`8ad5f850` Rust harness, with no Cargo/Ninja build or external node traffic;
the run lasted 133.809 seconds and completed at 2026-11-05 01:09:14 +08.
New-head Windows CI remains required before claiming the CI failure resolved.
