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
