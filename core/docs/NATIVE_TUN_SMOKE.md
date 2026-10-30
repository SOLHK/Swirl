# Scoped Windows Wintun smoke

[`windows-tun-smoke.rs`](../crates/swirl-api/examples/windows-tun-smoke.rs) is an
explicit integration executable for an authorized, disposable Windows machine.
It exercises the actual signed Wintun driver and Windows TCP/UDP sockets. It is
separate from both portable packet simulation and Windows 11 product acceptance.

## Invocation and execution boundary

From the repository's `core/` directory, build the example with the locked
dependencies on Windows:

```powershell
cargo build --locked -p swirl-api --example windows-tun-smoke
```

Only an explicit invocation with both arguments enters the Windows integration
path:

```powershell
& .\target\debug\examples\windows-tun-smoke.exe `
  --disposable-network `
  --wintun 'C:\approved-disposable-fixture\wintun.dll'
if ($LASTEXITCODE -ne 0) { throw 'Scoped Wintun smoke failed' }
```

The path must name the official Wintun 0.14.1 DLL for the architecture. The
platform loader independently verifies its pinned SHA-256 and restricts loading
to an explicit local absolute path. It does not download a DLL or probe PATH.
The driver license and provenance are in
[`swirl-platform/README.md`](../crates/swirl-platform/README.md).

The process must already have the administrative privilege required by Wintun
and NetTCPIP. The flag acknowledges the scope; it does not elevate a process or
prove that the machine is disposable. A GitHub-hosted Windows runner is suitable
only when its workflow explicitly authorizes this step. Do not run this command
on a shared developer workstation or a runner attached to a user's live VPN.

Without `--disposable-network`, execution fails before any network operation.
`--help` only prints usage. A non-Windows invocation fails explicitly.
`cargo test --all-targets` compiles the example with the test harness and does
not execute its network-changing `main`.

Wintun can stage/load its driver when it creates the adapter. The smoke restores
its network resources and closes the adapter; it does not claim to uninstall a
Windows driver package from DriverStore. Dispose of the runner afterward.

## Actual data path and resolver phases

The executable starts one ordinary V2 Core and uses the existing
`FlowDispatcher`, `TunDns`, `native_tun::spawn`, protocol dispatch and session
bookkeeping. The same Core remains alive while its policies change through the
normal V2 transaction API. There is no added ingress proxy hop or alternative
proxy engine. The protocol servers below are test peers selected by the native
Core outbounds; they do not replace the TUN packet path.

The initial DIRECT data tests use exact static hosts mapping two `.invalid`
fixture names to `127.0.0.1` and `::1`. This initial configuration includes the
encrypted upstream `192.0.2.1:853` to satisfy native DNS configuration validation;
the hosts resolver satisfies the names without dialing that documentation-only
address. These initial Windows DNS tests do not by themselves prove encrypted
upstream transport.

The later policy tests replace that DNS configuration with an actual loopback
DoT server, an empty static-hosts list and `use_system_hosts: false`. The
production resolver verifies the fixture certificate and server name, then
sends A followed by AAAA on the same TLS connection. A preliminary resolution
asserts that each fixture name returns exactly its intended loopback address
family. The subsequent Core policy configurations create their own resolvers
and use the same live DoT server. Removing static hosts is necessary here:
preselecting a loopback address would activate the built-in local/DIRECT rule
before the intended PROXY or REJECT decision.

The process holds a suspended Core egress lease during the smoke. Explicit
loopback outbounds work, while an accidental non-loopback Core connection
fails instead of contacting a physical network. All target servers, the HTTP
CONNECT proxy fixture and the DoT server are local loopback peers. This smoke
does not establish external target or DoT/DoH reachability.

The real Windows client sends to a fake destination selected by the existing
DNS allocator. Windows routes that packet into Wintun. The existing Rust packet
stack turns it into a stream/datagram, the bridge recovers the domain identity,
and the shared Core reaches the corresponding real loopback server. Replies go
through the same packet stack and Wintun back to the original Windows socket.

### Fake-IP persistence, DNS, TCP and UDP

Before creating the adapter, identity allocation runs through `TunDns` and the
same Core resolver, allowing the exact fake host routes to be journaled. The
smoke drops the original `TunDns`/`FakeIpStore` owner, reopens its actual journal
file, and requires both reverse domain mappings and repeated A/AAAA answers to
retain their fake identities. The Wintun bridge uses this reopened store. This
is close/reopen persistence coverage, not a simulated in-memory reconstruction
or a process-crash recovery test.

The smoke then verifies each IP family independently:

| Case | Required observations |
| --- | --- |
| UDP DNS | A real Windows UDP query to the owned DNS endpoint returns the expected fake A/AAAA address. Response identity, success code, exact question/answer counts, question bytes, answer name pointer, type/class, address length, sender endpoint and the exact `ANSWER_TTL` value (currently 30 seconds) are checked. |
| TCP DNS | A real Windows TCP connection uses the owned TUN source address. Two length-prefixed DNS messages on the same connection return the same checked fake identity and TTL; client write-half close must be followed by EOF. |
| TCP payload and half-close | A Windows TCP client selects the owned TUN source, sends a deterministic 256 KiB payload, and closes only its write half. The loopback server must receive every byte and EOF, then return the complete payload plus a final marker. The client must receive that reply and EOF after its own half-close. |
| TCP reuse and independent RST | One connection exchanges 64 ordered, checked 4,096-byte request/reply frames while keeping the same local endpoint. At round 32, a second Windows socket exchanges setup markers and closes with verified `SO_LINGER=0`. The Wintun reader must observe that second socket's exact source/destination RST tuple, and the packet stack must return to one active TCP flow. The first connection must continue its remaining frames and complete its final half-close reply. |
| Empty and full UDP | A Windows UDP client bound to the owned TUN address sends zero-byte and deterministic 1,200-byte datagrams. The loopback server and client check payload bytes, datagram boundaries, fake reply endpoint and successful send lengths. |

The RST assertion concerns the packet emitted by the actual Windows socket and
the packet stack's cleanup. The loopback upstream may observe EOF or a reset
when that flow is released; the test does not require the same RST packet to be
forwarded across the separate Core TCP connection. The 64-round case verifies
connection reuse and isolation from another flow's reset, not a long-duration
soak. DNS assertions check the advertised TTL, not expiration after elapsed
wall-clock time.

### TCP policy and native protocol controls

Both IPv4 and IPv6 run the following cases through Wintun. The proxy cases use
the existing native HTTP CONNECT implementation. These policy cases cover
**TCP only**; the UDP data cases above use DIRECT.

| Case | Required Core terminal record and peer behavior |
| --- | --- |
| PROXY success | Category `proxy`, the selected fixture node ID, and an empty error. The proxy checks the exact CONNECT authority and Host header, then completes the same 256 KiB payload and half-close exchange. |
| REJECT | Rule mode uses a custom domain-suffix REJECT rule and the repository's existing pinned MRS assets. The Windows client must observe rejection/reset; Core must record category `reject` and `Rejected`. Neither the DIRECT target nor unused proxy listener may accept traffic. |
| Proxy returns HTTP 403 | Category `proxy`, the same selected node, and `UpstreamRejected`. The Windows client must observe rejection/reset, with no DIRECT target acceptance. |
| Proxy unavailable | A socket remains bound to the chosen loopback port without listening for the entire case. An explicit control first requires `ConnectionRefused`. The Wintun flow must terminate with category `proxy`, the same selected node, and `UpstreamConnectionRefused`, with no DIRECT target acceptance. |

The unavailable case is a deterministic connection-refused fixture, not an
additional unreachable-network or handshake-timeout case. A graceful EOF alone
does not satisfy the rejection/reset check. Each expected flow must produce one
matching Core admission after the captured admission counter and reach its
exact terminal category/error; every proxy result must retain the selected
node ID.

Each policy case is bracketed by successful DIRECT controls against the same
hostname, port and still-open target listener. Both controls must pass through
the owned TUN source. The listener must have no unexpected pending connection
after the policy case, proving that absence of DIRECT traffic was not caused by
an unreachable trap. The live DoT query counter must also remain unchanged
during the PROXY/REJECT attempt: those paths must not unexpectedly resolve the
target through DIRECT DNS.

Policy changes use `prepare`, `activate` and `finish`, with the candidate and its
durable receipt written to a run-specific file and synced before `finish`.
They do not replace a dispatcher or bypass policy admission. Rule mode resolves
the checked-in `src/Swirl.Quick/packaging/rules` directory from the compiled
manifest path; those source assets must remain available when running this
acceptance executable. This checks Rule-mode loading for the REJECT case, not
the classification behavior of every MRS rule.

### UDP policy and native SOCKS5 controls

The additional UDP policy cases run for both IPv4 and IPv6 through real Windows
client sockets and the same exact fake-address routes, Wintun bridge and V2 Core.
The selected PROXY node uses the existing native SOCKS5 UDP implementation.
Its loopback TCP control server and UDP relay are bounded protocol fixtures;
the TUN is not forwarded wholesale to a local system proxy. The encrypted DNS
fixture still has no static-host entries, so PROXY and REJECT are selected
before any loopback target resolution can select the built-in local rule.

| UDP case | Required observations |
| --- | --- |
| PROXY data and established-node failure | One native SOCKS5 UDP association carries an empty datagram and a checked 1,200-byte datagram. The relay validates the original domain, port, source family, stable association endpoint and complete payload. Windows receives both replies from the original fake endpoint. Core first records the selected proxy node, no error and exactly 1,200 upload/download bytes. Only then does the test signal the peer to close TCP control; Core must terminate that same record with `Socks5UdpControlClosed`, preserving both byte counters. |
| REJECT | The existing Rule-mode domain-suffix rule returns category `reject`, node `SWIRL_V2_REJECT`, error `Rejected`, and zero upload/download bytes. Neither the DIRECT trap nor the unused UDP relay or TCP proxy listener may receive traffic. |
| Proxy denies UDP ASSOCIATE | The real SOCKS5 peer reads the expected greeting and UDP ASSOCIATE request and writes REP `0x02`. Core must terminate with category `proxy`, the selected node, `UpstreamRejected`, and zero byte counters. No UDP relay or DIRECT traffic is allowed. |
| Proxy unavailable | A loopback TCP port remains bound without listening, and an explicit connection control first verifies `ConnectionRefused`. Core must terminate the UDP admission with category `proxy`, the selected node, `UpstreamConnectionRefused`, and zero byte counters. This is a refused control connection, not a claim about UDP unreachable-network behavior. |

Every case has a successful DIRECT control before and after against the same
hostname, target port and still-open UDP trap. Those controls use different
Windows source sockets, retained until all cases finish so their ports cannot
be reused accidentally. UDP has no FIN: an existing source tuple intentionally
retains its original Core association rather than adopting a newly selected
policy. Each DIRECT control checks the real trap request/reply and an active
Core record with its exact source endpoint, DIRECT node and four-byte counters.
Those control flows are cleaned up with the bridge at the end of the smoke.

After each case's exact terminal record is observed, the policy switches to
DIRECT and the original failed source tuple sends a 1,200-byte retry. Within
the bridge's existing failed-tuple retention window, its dropped-datagram
counter must advance by exactly one and Core's admission counter must remain
unchanged. The trap, relay and client must have no unexpected queued datagram,
including an empty one, and the proxy listener must have no new connection.
Only a fresh source tuple may then complete the final DIRECT control. This
tests the failed tuple's prohibition on redial or DIRECT fallback; a receive
timeout by itself cannot satisfy the negative case. The DoT query counter must
also remain unchanged during each PROXY/REJECT attempt.

The fixture reserves 32 bounded UDP slots for the two initial DIRECT tuples
plus two families × four policy cases × three retained source tuples: 26 in
total. This accommodates the additional controls and failed-tuple entries
without evicting them or changing the production capacity checks.

Each passing case emits `Wintun smoke: PASS UDP policy` with its source endpoint,
actual Core record ID, category, node, terminal error and byte counters. Final
JSON distinguishes `additional_cases.tcp_policy` from
`additional_cases.udp_policy`; the latter contains all eight case results and
their retry/control evidence. These are implemented assertions pending a
successful driver run for the exact source, not acceptance inferred from a
portable fixture or compilation result.

Core server-side peers must observe loopback sources. Both Wintun receive and
send counters must be nonzero. A successful final result requires all packet
stack TCP/UDP resources to be released after shutdown.

## Restricted network transaction

The program creates an adapter with a random GUID and a distinct
`Swirl TUN Smoke ...` name. It does not open or adopt an existing adapter.
The typed journal contains only:

| Resource | Scope |
| --- | --- |
| IPv4 and IPv6 MTU | `1500`, on the owned interface only |
| IPv4 address | `198.18.0.1/30`, on the owned interface only |
| IPv6 address | `fd53:7769:726c::1/126`, on the owned interface only |
| IPv4 test route | Exactly the allocated fake address, `/32`, on-link through the owned interface |
| IPv6 test route | Exactly the allocated fake address, `/128`, on-link through the owned interface |

Windows also creates the connected routes belonging to the assigned interface
addresses. DNS queries are sent explicitly to `198.18.0.2:53` or
`[fd53:7769:726c::2]:53`; no Windows DNS-server setting is changed.

The example never requests a default route, `/1` capture, physical interface
change, physical DNS change, firewall rule, persistent service, or GUI
elevation. Its Core egress lease remains suspended, so no physical-interface
binding is selected. The two specific fake routes cannot capture Core's real
loopback destinations. Physical egress binding and full-system capture remain
separate validation work.

State files are written under the platform's protected fixed
CommonApplicationData/Swirl/NativeTun directory. The network journal uses the
same GUID filename convention and ownership checks as the normal helper.
The fake-address journal and policy receipt files are specific to this smoke
run.

Normal completion and returned errors attempt compare-and-restore before
stopping the packet bridge and closing the adapter. Before deletion can hide
the original resources, every one of the journal's six resources is read back
and compared with its exact captured `before` value. Recovery must report no
conflicts, the journal must be restored, and every value must match. Raw MTU is
read from the actual CIM `MSFT_NetIPInterface.NlMtu` property; a missing/null
property is an error. Captured MTU is preserved without truncation or clamping,
independently of the requested TUN MTU of 1500.

The smoke then stops the bridge and packet pumps, waits for their handles to be
released and closes the adapter. Even if a data test failed, it still checks
zero active TCP/UDP packet resources, absence of the owned adapter and unchanged
preexisting default/split-default routes. `Drop` retries cleanup after an
earlier failure. Any recovery conflict, readback mismatch, shutdown error or
post-cleanup verification failure causes a nonzero exit; successful traffic
alone cannot produce a pass.

### Complete original configuration comparison

A separate read-only snapshot is captured before adapter creation and after
cleanup. It does not extend the journal's mutation resources. It records all
interfaces enumerated by `Get-NetAdapter -IncludeHidden`, including their GUID,
index, name and hardware flag; this avoids an empty physical-only selection on
a virtualized runner. An empty adapter enumeration is an error.

For those adapters it compares both families' raw MTU, DHCP mode, automatic and
explicit interface metrics, address identities/prefixes/source flags/origins,
and DNS server lists. It also compares all enumerated ActiveStore routes across
network compartments, including provider identity, interface, family, prefix,
next hop, metric, protocol and publish mode. Lifetimes, ages and counters that
change merely with elapsed time are excluded. Enumeration and typed-decoding
errors fail the test; a genuinely absent family may have an empty list.

Record order is normalized for comparison without discarding duplicates. DNS
server order retains resolver priority, and address strings retain IPv6 scope
information. The adapter and route collections must each be exactly equal.
The log reports equality and before/after counts, not original physical-network
addresses or DNS values. It separately prints before/observed values only for
the temporary adapter's owned resources.

Windows does not supply an atomic snapshot across these cmdlets. An independent
network change during the smoke may therefore make this strict comparison fail;
such a mismatch is retained for investigation. No differences are ignored to
turn a run green. Because the smoke does not change Windows DNS-server settings,
DNS equality proves preservation during this test, not a DNS-mutation rollback
or a DNS-leak test.

A hard process termination or OS failure cannot run Rust destructors. Preserve
an unarchived `.network.json` record and use the existing helper's explicit
`--recover` operation in that disposable environment. Never delete an unresolved
journal merely to clear a failed test. The example installs no watchdog service.

## Evidence and remaining limits

The successful stdout JSON includes the compiled source SHA, Wintun version and
hash, each family/transport result, payload sizes, actual driver packet counts,
the `additional_cases` results, and verified network restoration. It is emitted
only after data and cleanup checks succeed. `SWIRL_SOURCE_SHA` must identify the
source used to build acceptance evidence; an `unknown` value does not establish
source identity. Preserve the complete CI log, exact tested SHA and JSON.

Failure exits nonzero and writes its cause to stderr. Family/case markers precede
policy attempts. Background peer failures retain fixture labels and their
original errors even when the client first observes a reset. Core record
assertions report the limited expected/observed test fields. Recovery errors
are aggregated with data errors so failed traffic cannot suppress cleanup
evidence.

This document describes implemented assertions, **not a claim that the expanded
Windows run has passed**. Compilation, lint, unit tests, portable packet
simulation and ordinary loopback Socket tests do not execute this Wintun path.
A Windows MSVC build is a separate gate. Only a completed successful explicit
Windows driver run for the exact source can be recorded as a scoped Wintun
loopback smoke pass, with a link to that run. A Windows Server runner pass cannot
be substituted for Windows 11 product acceptance.

This test does **not** certify Windows 11 Chrome/VS Code/Codex, internet proxy
protocol interoperability, full-system routing, DNS leakage, physical-interface
loop prevention, firewall enforcement, Wi-Fi switching, suspend/resume, abrupt
termination recovery, long-duration streaming, or throughput/CPU/memory limits.
The UDP policy extension covers native SOCKS5 UDP, not every supported proxy
protocol or arbitrary UDP endpoint failure mode.
Network rebuilding still has a period without capture and no complete
kill-switch; this smoke cannot establish zero-leak switching. It always reports
`windows_11_application_acceptance: false` and
`additional_cases.long_duration_soak_acceptance: false`.

Its intended Stage B evidence is specific: real Windows L3 packets traverse
Wintun, the existing Rust stack and Core, reach controlled loopback peers, and
return correctly for both IP families, with the stated TCP/UDP policy cases and
verified cleanup. The broader acceptance items remain open until independently
executed and recorded.
