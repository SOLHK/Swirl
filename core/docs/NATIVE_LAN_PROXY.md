# Native LAN Proxy integration candidate

This branch extends the existing V2 Rust runtime. It does not depend on the
unmerged Native TUN PR #42 and does not enable transparent gateway forwarding.
Its base is LAN audit commit `762ba16d9568bf7a40de49f903c1fb0236f203fe`, on test
`56948e4d6044154f1c5d91c6d817099d1c01a87f`. The original loopback listener and
configuration transaction protocol remain authoritative.

## Runtime and control boundary

`swirl-core::lan::LanConfig` describes a separately owned IPv4 ingress. The
runtime refuses wildcard, loopback, public and IPv6 listener addresses. The
production entry point requires a specific RFC1918 address, a nonempty private
CIDR allowlist, username/password, bounded TCP sessions, a bounded UDP relay
port pool, authentication attempts and an idle timeout. Binding is performed
before a running state can be returned. Socket errors are not saved settings.

HTTP proxy, HTTP CONNECT and SOCKS5 CONNECT use the existing protocol parser,
V2 admission, policy selection, resolver, native outbound and relay. SOCKS5 UDP
ASSOCIATE uses that same routing path per destination. The old peer-IP bind
was incorrect: the relay now binds the accepted connection's **local** address.
A LAN association additionally owns a port from the configured local UDP pool.
The reply contains the bound address and port. Only the TCP peer's IP and the
association's pinned UDP endpoint are accepted. Nonzero FRAG is rejected.
Closing the TCP control stream or LAN runtime cancels associated workers and
returns its relay port only after the socket is closed.

LAN stop revokes LAN sessions and releases its listeners; it does not restart
the original Core. Existing configuration transactions, node selection,
subscription import and probe logic continue to own policy changes. Statistics
join the original Core counters and connection records, with an explicit
`ingress` field and a bounded per-client snapshot. No second routing graph,
node selector, DNS service or external proxy executable is introduced.

The exported C ABI stays at version 1. The additive JSON controls require
`control_schema=2`, a UUID `request_id`, and capability negotiation:

| Capability | Meaning |
| --- | --- |
| `optional.lan_proxy` | LAN controls are implemented in this runtime |
| `optional.lan_proxy_control_schema = 1` | LAN configuration/snapshot contract |
| `optional.lan_proxy_ipv6_listener = false` | IPv6 inbound is not enabled |
| `optional.lan_proxy_ipv6_targets = true` | Valid IPv6 destinations use existing native outbound |
| `optional.gateway = false` | This branch does not implement an accepted transparent gateway |

| Operation | Additional input | Result |
| --- | --- | --- |
| `lan_validate` | `config` | Pure validation; `network_preflight_required=true` |
| `lan_start` | canonical string `handle`, `engine_epoch`, `config` | Actual listener status |
| `lan_stop` | canonical string `handle`, `engine_epoch` | Stopped snapshot after owned cleanup |
| `lan_status` | canonical string `handle`, `engine_epoch` | Running state, addresses, counters, clients and error code |

Callers must preserve the existing serialized lifecycle/buffer ownership
contract in `swirl_api.h`. Validation is not a port reservation, firewall check
or connectivity test. Credentials are input-only; do not log command buffers.

## Windows product boundary

The device/Gateway page contains the LAN configuration and state. The switch
reflects Rust status and pending lifecycle phases, never a persisted boolean.
Starting the application does not automatically expose LAN listeners. The
selected interface must exist and be up. Credentials reuse Windows DPAPI;
the QML configuration/status views do not return the stored password.

`LanProxySession` coordinates firewall preparation, listener start, stop and
owned-rule recovery. `LanFirewall` checks the current interface identity,
address inventory and network profile, and creates exact program/interface/
local-address/port/source rules. Journal data is DPAPI protected. A guard
checks the process identity and recovers only rules whose complete observed
properties match the owned journal. Externally edited rules and unreadable
state remain explicit conflicts rather than being overwritten or deleted.

This candidate requires administrator privileges for Windows firewall
mutation. It does not silently elevate the GUI or claim a completed
least-privilege helper deployment. Public network profiles and a disabled or
permissive default inbound firewall are rejected. An address-change callback
requests stop; periodic verification additionally checks interface, profile and
rule identity. Those checks do not prove zero reaction time after an external
administrator changes Windows state. A firewall or Core acknowledgement
failure is shown as unconfirmed/error state, not a successful stopped service.

HTTP Basic and SOCKS5 username/password do **not** encrypt transport. The UI
explicitly requires a trusted LAN. The port range, ACL and authentication are
not a substitute for encrypted transport on hostile shared networks.

## Destination protection and DNS

LAN clients cannot request local host addresses, loopback, link-local,
multicast, unspecified or other unusable special destinations. The final
DIRECT address is checked after the existing resolver/policy path. Upstream
connection addresses are also checked and pinned for the connection so a
second resolution cannot rebind to a local listener or management service.

Remote-outbound DNS keeps its existing semantics: a remote proxy resolves
remote destination names. It must not be silently replaced by local DNS just
to classify a LAN request. Local protection covers sockets opened on this
host; it does not promise to enforce the remote server's own network access
policy. Policy rejection or proxy failure never authorizes a DIRECT fallback.

## Evidence and acceptance

The new `Swirl Native LAN` workflow executes the unchanged strict commands on
Linux, macOS and Windows:

```text
cargo fmt --all -- --check
cargo check --workspace --locked
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
```

Rust fixtures use real loopback sockets, with a `cfg(test)`-only address
admission seam. This does not create a public control option to bypass private
address validation. `tools/tests/test_native_lan_abi.py` independently loads the
compiled shared library and checks capability, buffer, validation and Core
lifecycle behavior. The Qt `swirl-lan-proxy-control` tests exercise validation,
ownership and lifecycle fault handling; injected firewall backends are not
evidence of real Windows firewall mutation. The existing full Qt workflow
builds the application and runs the new registered test alongside prior tests.

At initial source submission, this cloud environment has no Rust/Qt toolchain.
Only source/static checks and Python syntax checks have run locally. Compile,
Clippy, Rust sockets, DLL and Qt results must be read from their actual Actions
run at the submitted commit. Formatting diagnostics never override a failed
format gate; the formatter patch requires a new source commit and rerun.

The following remain distinct release gates:

- Windows 11 real interfaces, exact firewall creation/recovery and elevation.
- Independent Android, iPhone and Windows clients using HTTP/HTTPS and UDP.
- Multiple clients, disconnect/reconnect, sleep/wake and sustained resource use.
- Real configured MRS/default/custom policy and node updates without dropping
  unrelated established sessions.
- Public IPv4/IPv6 targets and the selected DNS strategy on real networks.
- Crash, reboot and external firewall/interface-change behavior.

A Server CI success or simulated lifecycle test is not Windows 11 hardware
acceptance. Keep this PR Draft until the missing evidence is supplied. Do not
merge it into test/main or enable Gateway on the strength of these unit tests.
