# Native Gateway integration candidate

This branch contains runtime integration, not an accepted Windows 11 gateway.
The product Gateway switch stays disabled. Native LAN Proxy is independent and
continues to use its own listener lifecycle without requiring TUN.

## Exact ancestry and review boundary

- Target `test`: `56948e4d6044154f1c5d91c6d817099d1c01a87f` when rechecked.
- LAN PR [#46](https://github.com/SOLHK/Swirl/pull/46), dependency
  `5c3ae925528b3064a552d2a01e98d4333ca8ce04` at initial integration.
  Subsequent integration includes `c162e7d8697fd50ffac175f149069e36a376e2e0`,
  whose three-platform strict LAN gates passed, and the independently added
  exclusive-socket commit `3e9d58f7dd4dd439e19956c795ce33886284548c`.
  The latter was fetched and preserved before applying the Qt SDK platform
  plugin fix `daa16f56bc0b63a686136f7dee7d905236e79d3b`. These newer changes
  require their own CI results; ancestor passes are recorded separately.
- TUN PR [#42](https://github.com/SOLHK/Swirl/pull/42), dependency
  `930c3f5fc2cbcfb99de4769c44f1682f4fc2e01d`, still Draft and unmerged.
- TUN/test merge base: `4ad8a23b7fd59f0f8c09f1e3547548b16baaf4e9`.
- The Gateway integration commit has the LAN and TUN commits as parents.
  Neither dependency branch is rewritten; `test` and `main` are not modified.

The merge preserves newer test workflow/UI regression changes. Conflicts in
`build-qt-quick-ui.yml` retain the critical UI and network checks as independent
gates and diagnostics. Core conflicts use one shared connection semaphore and
session registry for loopback, LAN and native TUN. Transport conflicts preserve
physical egress constraints for outbound sockets while keeping LAN UDP listener
binding independent. After both prerequisite PRs are accepted, merge the current
test branch into this candidate normally and rerun all gates; do not force-push
or silently treat the original TUN PR as production ready.

## Runtime path

The existing Wintun device and `swirl-tun` TCP/UDP stack deliver flows to the
existing `FlowDispatcher`. Its policy snapshots, MRS/custom rules, resolver,
Fake-IP identity, native protocol outbounds, connection records and traffic
counters remain the only data plane. No second node selector, proxy kernel or
NAT service is added. The existing stack retains original client TCP tuples and
UDP association keys and reconstructs replies to the original client.

`GatewayIngress` admits only IPv4 clients from the configured private subnet and
allowlist. It excludes subnet/broadcast, spoofed host addresses and protected
destinations, rejects unauthorized DNS destinations and bounds TCP, UDP and DNS
work per client. Local host flows retain their existing path. Shared global
admission spans LAN and TUN; stopping the explicit LAN listener does not stop an
established native flow. Direct destination resolution and actual locally dialed
proxy/UDP relay endpoints are checked and pinned. Proxy-routed Gateway client
hostnames, including Fake-IP reverse mappings, are resolved by the configured
DoH/DoT service through the already selected outbound and pinned to an admitted
literal destination. Missing encrypted DNS returns
`GatewayTargetDnsPolicyRequired`; no local-system or DIRECT fallback is added.
Native host TUN behavior remains unchanged. See NATIVE_LAN_PROXY.md.

Gateway ingress uses the same scoped Resolver boundary for classification,
mandatory-rule and DIRECT lookups, and proxy-hostname bootstrap. Configured
DNS endpoint refusals occur before I/O and shared failure-cache writes; ordinary
host/system-DNS behavior is preserved. IPv4-only LAN AAAA requests return NODATA
before upstream resolution or IPv6 Fake-IP allocation; native host dual-stack
DNS remains unchanged.

Windows IPv4 forwarding alone is not evidence that a packet entered Rust.
`windows_gateway` verifies a dedicated, already statically configured private
LAN, selected physical WAN and separately owned TUN. Persistent WFP objects
restrict authorized LAN forwarding to that TUN, return forwarding to authorized
LAN clients, local host access and IPv6 traffic. Owned object names, provider,
sublayer, exact compiled conditions and policy digest are checked before removal.
The TUN IPv4 interface also enables forwarding for packets injected back toward
the LAN. Every outbound socket retains the original TUN physical egress lease.

The actual LAN NIC -> WFP -> Windows route -> Wintun packet path and its return
path still require an independent-client Windows network trial. Packet-stack
tests and WFP API readback are narrower evidence, not substitutes.

The separate `windows-gateway-forward-smoke` example adds an explicitly
disposable Windows routing mechanism test. Two temporary owned Wintun adapters
stand in for ingress A and Core capture B. A client IPv4 address is deliberately
not assigned to Windows. Injection into A must emerge from B's real driver read
before it enters the existing `PacketBridge` and `FlowDispatcher`; responses must
travel from B through Windows back to A. Each hop checks the complete IP packet
identity, allowing only the router's TTL decrement and corresponding header
checksum update. Forwarding-disabled negative controls run before and after.

This fixture uses exact test `/32` routes, existing durable network transactions
and forwarding only on its two new adapters. It checks DNS UDP/TCP, shared
persisted Fake-IP identities, IPv4-only AAAA NODATA, and protected-target TCP/UDP
refusal with live host traps. It does not modify physical forwarding, default
routes, DNS settings, firewall rules or DHCP. Restoration requires individual
before-value readbacks and the original complete adapter/route inventories.
The fixture is committed for actual Windows execution; its existence alone is
not a passing result. Even a pass would leave physical LAN, production WFP
interface metadata and positive external TCP/UDP acceptance open.

## Helper control and lifecycle

The existing C ABI version stays at 1. A separate JSON envelope uses
`native_gateway_schema: 1`, a UUID `request_id`, and these operations:

| Operation | Effect |
| --- | --- |
| `gateway_validate` | Pure typed validation; returns `network_preflight_required: true`. |
| `gateway_prepare` | Helper-only; validates Core handle/epoch, prepares persistent LAN isolation, starts the existing TUN, and returns an expiring preparation identity and actual helper worker PID. LAN forwarding remains off. |
| `gateway_activate` | Helper-only; rechecks capture, topology and optional real DHCP socket ownership; applies and verifies the owned DHCP firewall exception when needed, then enables LAN forwarding last. |
| `gateway_status` | Actual observed state, identities, IPv4-only scope and preparation/running/recovery information. |
| `gateway_stop` | Quiesces LAN forwarding before restoring capture/routes/DNS; removes isolation only after dependent restoration succeeds. |
| `gateway_recover` | Helper-only; locks and quiesces all stale Gateway journals before restoring TUN journals, then removes fully owned guards. |

Mutation uses the existing private-stdio `swirl-tun-helper --serve` controller.
The ordinary GUI/DLL controller rejects mutation with `GatewayHelperRequired`.
This adds no network RPC endpoint, shell-command parameter or automatic UAC.
Core creation/policy publication still use existing schema 2 commands on the
same helper controller; there is no separate Gateway policy configuration.

Gateway configuration contains `tun` (the existing NativeTunConfig) and `lan`:

```json
{
  "lan": {"index": 11, "guid": "70000000-0000-4000-8000-000000000002"},
  "subnet": "192.168.77.0/24",
  "gateway": "192.168.77.1",
  "allowed_sources": ["192.168.77.0/24"],
  "dedicated_lan_confirmed": true,
  "dhcp": false
}
```

These are documentation values, not usable interface identities. Preflight must
observe the real GUID/index/static address and safe topology. A successful pure
validation does not authorize an arbitrary home, public-Wi-Fi or WAN interface.
Manual static clients are supported by the native coordinator without DHCP.
Clients use the existing intercepted DNS address `198.18.0.2`.

## Transaction and failure semantics

Gateway `.gateway.json` and TUN `.network.json` journals stay locked under the
existing protected helper journal directory. Journaled prefix application installs
isolation before capture and defers LAN forwarding until activation. DHCP-enabled
plans use journal version 2 for the ordered isolation/exception/forwarding stages;
existing version-1 journals remain recoverable. An operation
is durably marked Applying before its OS mutation and checked after application.
Stopping first disables forwarding and restores the exact owned DHCP exception;
capture stays alive on a conflict. The persistent isolation guard remains until
the dependent TUN resources have been restored.
Recovery never resets the whole Windows network or deletes foreign VPN routes.

Changed GUID/LUID, host addresses, network profile, routes, forwarding, physical
egress or DHCP ownership cause a controlled stop and retained error/recovery state.
Gateway does not inherit the TUN-only autonomous restart path: each new activation
requires a fresh dedicated-LAN preflight. The monitor provides bounded reactive
verification, not a claim that every OS topology change is observed instantaneously.

An ambiguous crash between a shared Forwarding-bit write and its durable receipt
cannot prove exclusive ownership. Such a journal retains isolation and reports a
conflict rather than overwriting an indistinguishable external change. A failed
restore similarly retains records and guards. Legacy Qt schema-1 journals carry
only interface indices/aliases; they are preserved for ownership review and never
used as authority to modify potentially recycled interfaces.

Helper supervision and next-helper-start recovery are implemented. There is no
installed boot-time recovery service or scheduled task. Simultaneous helper crash,
machine restart, adapter recreation and unattended boot recovery are open product
gates. Persistent WFP objects alone do not establish those gates.

## DHCP integration

The existing Qt DHCP parser/server is reused. Real socket fixtures cover
DISCOVER/OFFER, REQUEST/ACK, renewal, release, conflicting reservations, malformed
options and client identifiers. Lease and decline-quarantine storage is atomic;
invalid persisted times/identities fail closed. Rediscovery does not shorten a
committed lease. Per-MAC/global request limits and pool/lease counts are bounded.

On Windows a production UDP67 socket is exclusive. Before binding its wildcard
broadcast address, it enables `IP_IFLIST` with exactly the dedicated LAN index and
sets `IP_UNICAST_IF`; readback, receive packet-info and explicit outgoing
interface/source address enforce the same constraint. This is needed for initial
DHCP broadcasts from clients without an address. Unsupported constraints fail
closed. Isolated tests bind only an ephemeral loopback port.

`DhcpServer::ownerReceipt(helperWorkerPid)` produces a one-use
`WSADuplicateSocketW` token. The helper validates process PID/start time and the
sibling product image, imports the token once, checks the actual socket protocol,
UDP67 endpoint, exclusivity and exact receive/send interface constraints, then
closes its duplicate without receiving, sending or changing notification state.
Only stable process identity is retained for periodic UDP67 ownership checks; the
opaque socket token is not persisted or logged. A caller-supplied ready boolean
does not satisfy activation. Native preflight performs a bounded DHCP-server
conflict probe on the confirmed dedicated LAN before any server is attached.

Socket attestation alone does not admit DHCP through Windows Firewall's default
inbound block. A nonce-owned ordinary allow rule therefore accompanies the
attested socket. It is restricted to the exact sibling `Swirl.exe`, the captured
LAN interface alias and identity, Wired interface type, Private profile, UDP
local port 67 and remote port 68. Local addresses are the gateway and the two
applicable broadcast addresses; remote addresses are the configured allowlist
plus the single pre-lease source `0.0.0.0/32`, never a wildcard network.
The rule cannot override external block rules or change firewall profile/default
settings. Activation requires matching PersistentStore and ActiveStore readback
and local inbound-rule merging to be permitted.

The transaction snapshots the full scope before applying isolation, creates the
exception only after the actual one-use socket receipt, and rechecks the DHCP
owner before enabling forwarding. Recovery compares the original rule name,
owner, program, interface, profile, addresses, ports and security filters. A
foreign edit preserves both the rule and recovery evidence. Exact removal does
not require the original executable or LAN alias to remain available. A separate
explicit Windows fixture creates only a disabled rule, exercises a foreign
program edit and exact cleanup, and never starts DHCP or enables forwarding.
Its results are tracked independently from real DHCP broadcast acceptance.

The formal Qt Gateway start path remains closed. End-to-end Qt helper orchestration
and real client DHCP broadcast/renewal tests are not yet accepted. Saving a Gateway
configuration neither starts DHCP nor changes interface addresses or forwarding.
The GUI DLL and helper have separate Controller handle maps. Product integration
must select one helper-hosted Core transport before starting it; passing an
existing DLL handle to the helper is invalid. Live Core/session migration,
administrative launch and helper/driver product packaging are not implemented.

## Evidence and remaining gates

Local Rust/Qt tools are unavailable. Actual candidate evidence is recorded below
by source revision, independently of local whitespace/YAML/Python checks and
the ancestor LAN evidence in NATIVE_LAN_PROXY.md.

| Source | Run | Actual observation |
| --- | --- | --- |
| `6101cd2bbde5d304805f15e231201de01f3b917d` | [Native LAN candidate 41193986434](https://github.com/SOLHK/Swirl/actions/runs/41193986434) | Linux/macOS strict Rust and ABI gates passed. Windows fmt/check/Clippy/workspace/LAN+Gateway ABI passed; the real UDP67 attestation/replay fixture passed. The WFP fixture failed and kept the job red. |
| Same source | [Windows WFP job 124516336234](https://github.com/SOLHK/Swirl/actions/runs/41193986434/job/124516336234) | BFE returned `PERSISTENT | INDEXED` (`0x41`) for a requested `PERSISTENT` (`0x1`) filter. The exact flags comparison rejected the engine indexing bit. The correction accepts only that additional bit; disabled/unknown flags and all other ownership fields remain checked. This original failed run remains recorded. |
| `3a42a2f62aedc9d0bfd9fd98a0ab96016e06bb6f` | [Windows WFP rerun 124520441401](https://github.com/SOLHK/Swirl/actions/runs/41195401753/job/124520441401) | Actual persistent WFP install/readback/ownership-preserving removal passed, as did actual UDP67 attestation/replay. All three platforms passed check, Clippy, workspace tests and LAN/Gateway ABI; only rustfmt failed. Its exact patch is committed in `ccd134a4`; this does not validate the subsequent DHCP firewall addition. |
| Same source; tested merge `8b613d80063860f49c30f16f9fd9ce2016436b8f` | [Native TUN 41193989282](https://github.com/SOLHK/Swirl/actions/runs/41193989282) | Linux and Windows jobs passed. The merge tree is source-identical to the branch commit. Windows Server 2025 actually executed the Wintun TCP/UDP/DNS smoke, not just compilation. |

The successful scoped Wintun run recorded 1,986 received and 1,735 sent driver
packets, IPv4/IPv6 TCP and UDP, DNS A/AAAA and TCP, native HTTP CONNECT and SOCKS5
UDP, rejection/upstream-failure cases without DIRECT fallback, and 64 rounds of
4,096-byte TCP payloads per family. Six network resources were restored with no
conflicts and exact readbacks; the original eight adapters and 26 routes remained
equal and the temporary adapter was removed. The
[backend artifact](https://github.com/SOLHK/Swirl/actions/runs/41193989282/artifacts/13040780474)
contains the actual helper/library and driver log. It is not a Qt installer.
The test explicitly reports Windows 11 and long-duration acceptance as false.
It does not exercise physical LAN ingress, LAN return-interface metadata or
the new Gateway DHCP/WFP transaction together.

The additive candidate CI runs all requested locked workspace gates, independent
LAN/Gateway ctypes checks, and three explicitly scoped Windows fixtures: persistent
WFP install/readback/ownership-preserving removal on absent synthetic interface
IDs, loopback UDP67 socket attestation, and disabled DHCP firewall ownership and
foreign-edit preservation. The existing isolated TUN workflow
retains its real scoped Wintun TCP/UDP/DNS smoke. No original test gate is removed.

Still required: actual LAN NIC ingress and return packets, independent Windows 11
Android/iPhone/Windows clients, concurrent TCP/UDP and DNS/Fake-IP policy switching,
no direct leak during node failure/teardown, DHCP conflict/renewal on a dedicated
network, interface/profile changes, normal/failed/crash/reboot recovery, and a
source-identical Windows product/installer build. Windows Server CI is not Windows
11 hardware acceptance; neither PR should be merged merely because CI is green.
