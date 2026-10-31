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

For a proxy-routed LAN hostname, the existing configured DoH/DoT resolver
travels through the already selected native outbound. Every returned address
must pass the same target boundary before a literal destination is passed to
the proxy protocol. Routing and the client's HTTP Host/TLS payload keep the
original hostname. The upstream proxy cannot choose a different destination
address by resolving that hostname again. This also closes the case where an
upstream proxy on the same LAN could otherwise resolve a name back to Swirl's
protected management services.

This requires configured encrypted DNS for proxy-routed LAN hostnames. Missing
configuration returns `LanTargetDnsPolicyRequired`; failure or a protected DNS
endpoint/answer rejects the flow. It never silently introduces system or plain
UDP DNS to make a remote-only request succeed, never creates a second resolver,
and never authorizes DIRECT fallback. Literal targets and authorized DIRECT
routing retain their existing behavior. Core policy updates and existing
sessions keep their original lifecycle.

Ingress restrictions also apply before routing-time classification, mandatory
IP-rule resolution and proxy-hostname bootstrap. A scoped view of the same
Resolver shares its cache and query budget; it checks configured UDP/DoT/DoH
server addresses only before actual network I/O. Literal, static-host and
cached answers do not cause an extra lookup. A denied endpoint is not a
classification failure eligible for fallback and is never written to the
shared negative cache. Ordinary host requests retain their original resolver
and system-DNS policy. Only the selected classification proxy is prepared;
an unused node cannot make an otherwise valid request fail.

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

The development container has no Rust/Qt toolchain. Compilation and runtime
results below come from actual GitHub Actions logs, not local execution or
configuration flags. Each row identifies the source revision it verifies;
subsequent changes require their own run.

| Source | Evidence | Observed result |
| --- | --- | --- |
| `8a808c18c08187e09faeca8acaadbb707828748c` | [Native LAN run 41193987404](https://github.com/SOLHK/Swirl/actions/runs/41193987404) | All four strict Rust gates, real socket workspace tests and six independent ABI checks passed on Windows, Linux and macOS. |
| `81bd69128122d02f791d9173ed470c8872770555` | [Native LAN run 41193550079](https://github.com/SOLHK/Swirl/actions/runs/41193550079) | All five added encrypted-DNS/target-pinning socket regressions passed on all three systems. Workspace totals: Windows 838, Linux 837, macOS 836; zero failures or ignored Rust tests. This run still failed formatting; `8a808c18` applies its exact rustfmt patch and reruns the gates. |
| `5c3ae925528b3064a552d2a01e98d4333ca8ce04` | [Original Rust Core run 41191607693](https://github.com/SOLHK/Swirl/actions/runs/41191607693) | The original Windows, Linux and macOS jobs passed, including the Windows Qt-to-Rust integration. Platform-specific skipped public-network cases remain skipped, not accepted evidence. |
| `5c3ae925528b3064a552d2a01e98d4333ca8ce04` | [Qt security run 41191607821](https://github.com/SOLHK/Swirl/actions/runs/41191607821) | All seven jobs passed, including the actual Qt 6.12 Windows application build, deployment checks, DPAPI checks and existing product regressions. The tested PR merge tree was source-identical to this commit. This is a regression build with UI tests enabled, not a production installer. |
| `81bd69128122d02f791d9173ed470c8872770555` | [Qt security run 41193550109](https://github.com/SOLHK/Swirl/actions/runs/41193550109) | All seven jobs passed. The actual Windows Qt 6.12 product and LAN test executable built; all 13 required LAN validation/lifecycle cases executed without skips, followed by the existing DPAPI and product network checks. Tested merge `4369b858b6534d852e6819611d427a599bc1de83` was source-identical. |

The new real scoped Windows firewall fixture is a separate gate; the previous
Qt successes above do not establish its result. It compiles the same COM rule
and DPAPI cleanup primitives into a
separate test executable. Its unique rules are disabled, limited to that
executable and loopback addresses, and never open a listener. Tests verify
readback, duplicate refusal, retained external edits and independent-session
ownership. The test-only entry point is absent from the product. It does not
establish live-LAN firewall admission, guard-crash or reboot acceptance.
Formatting diagnostics never override a failed format gate: a formatter patch
is committed as source and all requested checks run again.

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
