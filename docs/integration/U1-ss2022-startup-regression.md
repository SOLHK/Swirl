# U1 SS2022 official-peer startup regression

## Observed failure

The macOS official-protocol job for integration commit
`208e50dbd5f0b05b607afab0386fd4bb0dae8b79` ran the original 12 SS2022
tests: 11 passed and `test_wrong_valid_key_and_invalid_parameters_rejected`
failed while starting its second official server, before protocol traffic.

- [Run 39900630419, job 120241157040](https://github.com/SOLHK/Swirl/actions/runs/39900630419/job/120241157040).
- Artifact ID: `12478797395`.
- Artifact name: `native-protocol-interop-macos-latest-208e50dbd5f0b05b607afab0386fd4bb0dae8b79-1`.
- Downloaded ZIP SHA-256: `e425f75fdb789c13c01d4dde73691c7aec0f4c3273acb8be33ef9c907ba85307`.
- Relevant entry: `shadowsocks2022/swirl-ss2022-6rcrvv2m/01-2022-blake3-aes-256-gcm-server.log`.

The log identifies the pinned official `shadowsocks-rust 1.25.0` server and
ends with `server aborted with Address already in use (os error 48)`;
the process exits with code 70. This establishes a listener binding conflict.
The log does not establish whether the TCP or UDP bind collided. The old
fixture checked only a TCP port and released that reservation before spawning
the server in `tcp_and_udp` mode. A TCP connection alone also could mistake
an unrelated listener for successful child startup.

## Repair and retained acceptance gates

`tools/tests/test_ss2022_official.py` now checks TCP and UDP availability on
the same address and port before spawning. Since the external server cannot
inherit those reservations, a remaining race is handled only before traffic:
at most four attempts may select a new random port, and only when the actual
child exits 70 and its startup log contains a platform `EADDRINUSE` code
(Darwin 48, Linux 98, Windows 10048). Fixed-port restart checks receive one
attempt. Other startup errors and timeouts fail immediately.

Readiness requires the pinned server's TCP **and** UDP listening messages for
the expected endpoint, followed by the TCP probe and a live-child check.
Each attempt, port, reason and exit code is recorded alongside all server
logs in the existing evidence artifact. No protocol failure is retried.

All original 12 tests and their data, authentication, replay, UDP, reconnect
and cleanup assertions are retained. Two additional actual-server tests:

1. Force a real occupied TCP port during allocation, require an observed
   binding failure and exactly one reselection, then pass real HTTP traffic
   through the Rust client and successful official server.
2. Occupy a fixed UDP port and reject that startup without retry; separately
   reject an invalid cipher without retry. These are expected negative
   assertions, not ignored test failures.

The official peer remains pinned to v1.25.0 and its existing platform archive
hashes in `tools/tests/ss2022-peer-lock.json`. No dependency version, Rust
protocol implementation or existing test expectation was changed.

## Component verification and remaining platform gate

Development verification used Linux x86_64, Python 3.12.14, the checksum-verified
official v1.25.0 Linux peer, and Rust release examples built from worktree
base `fe35499fd8bd8e0d02aac7ca3573903f0e6a9cfa` with this Python fixture change.
The existing pinned Linux archive SHA-256 is
`874f817fcf3e6d7681ec715a1c13c686c6eaae936524d102639b38364f3966ae`.

```sh
cargo build --manifest-path core/Cargo.toml --release --locked --offline --examples --bins
python tools/tests/fetch_ss2022_peer.py build/u1-ss2022-peer
# SWIRL_SS2022_SERVER points to the verified peer; SWIRL_TRANSPORT_CLIENT,
# SWIRL_TRANSPORT_RUNTIME, SWIRL_SS2022_CLIENT and SWIRL_INSPECT_BINARY point
# to the release binaries built above. SWIRL_SS2022_EVIDENCE selects output.
python tools/tests/test_ss2022_official.py
```

Result: **14 tests, 0 failures, 0 errors, 0 skips**, 4.738 seconds in the JSON
receipt; 14 per-case evidence directories. Local evidence is under
`build/u1-ss2022-full/`, including `summary.json`, `results.json` and server
logs. `git diff --check` also passed.

This is independent loopback protocol verification, not Qt product or public
network acceptance. The final integrated SHA must rerun the existing
Windows/macOS/Linux `rust-native-protocols.yml` matrix. In particular, the
macOS repair remains pending that platform's real CI execution; the Linux
result does not substitute for it.

## Windows binding and log-format follow-up

The availability probes and both intentionally occupied sockets set
`SO_EXCLUSIVEADDRUSE` before binding when Python exposes that Winsock option.
This prevents another listener's `SO_REUSEADDR` from making an occupied-port
test ambiguous. [Microsoft's option documentation](https://learn.microsoft.com/en-us/windows/win32/winsock/so-exclusiveaddruse)
explains both the required call order and how a sharing listener can otherwise
reuse the address.

The pinned v1.25.0 upstream [TCP implementation](https://github.com/shadowsocks/shadowsocks-rust/blob/v1.25.0/crates/shadowsocks/src/net/tcp.rs)
explicitly excludes Windows from `set_reuseaddr(true)`; its
[Windows UDP implementation](https://github.com/shadowsocks/shadowsocks-rust/blob/v1.25.0/crates/shadowsocks/src/net/sys/windows/mod.rs)
uses `UdpSocket::bind` for the explicit loopback address without setting reuse.
Consequently the startup classifier remains limited to the existing
`EADDRINUSE` codes. Permission errors such as 10013 are not generally retried.

Windows log-format evidence was checked against the actual artifact
`12478402830` from the same 208 run:

- Name: `native-protocol-interop-windows-latest-208e50dbd5f0b05b607afab0386fd4bb0dae8b79-1`.
- Downloaded ZIP SHA-256: `164c7a6462e2e25ce14e9e3ebfc22812778e946fadc3e322ea692f7d7c9a3c28`.
- All 22 SS2022 server logs contain both expected listening messages: 44
  matched TCP/UDP lines, including IPv6 `[::1]:64180` in
  `shadowsocks2022/swirl-ss2022-9wfaozqh/00-2022-blake3-aes-128-gcm-server.log`.
- That historical Windows receipt reports 12 tests with zero failures,
  errors or skips. It establishes the pinned binary's log format, not
  execution of this subsequent change.

Only the two new startup regression cases were rerun after this follow-up:
Linux, two passed in 0.149 seconds. The exclusive Windows option itself awaits
the final integrated Windows CI run; no Windows runtime result is inferred
from that Linux verification.
