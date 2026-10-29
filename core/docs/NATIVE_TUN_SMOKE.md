# Scoped Windows Wintun smoke

[`windows-tun-smoke.rs`](../crates/swirl-api/examples/windows-tun-smoke.rs) is an
explicit integration executable for an authorized, disposable Windows machine.
It exercises the actual signed Wintun driver and Windows TCP/UDP sockets. It is
separate from both portable packet simulation and Windows 11 product acceptance.

## Invocation and execution boundary

Build the example with the repository's locked dependencies on Windows:

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

## Actual data path

The executable starts one ordinary V2 Core with DIRECT policy and exact static
hosts mapping two `.invalid` fixture names to `127.0.0.1` and `::1`. It uses the
same `FlowDispatcher`, `TunDns`, `native_tun::spawn`, protocol dispatch and
session bookkeeping as native TUN ingress. There is no local SOCKS relay or
alternative proxy engine.

The Core configuration includes a validated encrypted DNS upstream because the
native lease requires it. Both fixture names are satisfied by the existing
hosts resolver. The documentation-only upstream `192.0.2.1:853` is not needed
by the test; this smoke does not establish external DoT/DoH reachability.
The process holds a suspended Core egress lease during the smoke: explicitly
bound loopback outbounds work, while an accidental non-loopback Core connection
fails instead of contacting a physical network.

The real Windows client sends to a fake destination selected by the existing
DNS allocator. Windows routes that packet into Wintun. The existing Rust packet
stack turns it into a stream/datagram, the bridge recovers the domain identity,
and the shared Core reaches the corresponding real loopback server. Replies go
through the same packet stack and Wintun back to the original Windows socket.

The smoke verifies each family independently:

1. A UDP DNS query to the owned adapter's DNS endpoint returns the expected
   A/AAAA fake identity. The response ID, question, record type/class, endpoint,
   and address are checked. Identity allocation was first performed through the
   same Core resolver so the exact host route can be journaled before testing.
2. A real Windows TCP client connects to that fake IP. Its selected local
   address must be the owned TUN address. The client sends a deterministic
   256 KiB payload and closes only its write half. A real loopback server reads
   the full payload and EOF, then echoes the data plus a final marker. The
   client must receive the complete reply and EOF after its own half-close.
3. A real Windows UDP client sends an empty datagram and a deterministic
   1,200-byte datagram. The real loopback server and client check bytes,
   boundaries, endpoint identity, and successful send lengths.

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
The fake-address journal is specific to this smoke run.

Normal completion and returned errors attempt compare-and-restore before
stopping the packet bridge and closing the adapter. `Drop` retries cleanup if
an earlier path fails. A recovery conflict or error causes a nonzero exit;
the test cannot report success solely because traffic worked. Success also
requires the adapter to be absent and the preexisting default/split-default
route snapshot to remain unchanged.

A hard process termination or OS failure cannot run Rust destructors. Preserve
an unarchived `.network.json` record and use the existing helper's explicit
`--recover` operation in that disposable environment. Never delete an unresolved
journal merely to clear a failed test. The example installs no watchdog service.

## Evidence and remaining limits

The successful stdout JSON includes the compiled source SHA, Wintun version and
hash, each family/transport result, payload sizes, actual driver packet counts,
and verified network restoration. Failure exits nonzero and writes its cause to
stderr. Preserve the complete CI log and its exact tested SHA alongside the JSON.

At introduction, Linux compilation/lint and the explicit execution guard can be
checked locally. The Windows implementation and driver path require their own
MSVC build and explicit runner execution; neither is implied by a Linux pass.
Only a completed successful Windows run can be recorded as a scoped Wintun
loopback smoke pass.

This test does **not** certify Windows 11 Chrome/VS Code/Codex, internet proxy
protocol interoperability, full-system routing, DNS leakage, physical-interface
loop prevention, firewall enforcement, Wi-Fi switching, suspend/resume, abrupt
termination recovery, long-duration streaming, or throughput/CPU/memory limits.
It always reports `windows_11_application_acceptance: false`. Its purpose is
specific Stage B evidence: actual Windows L3 packets pass through Wintun, the
existing Rust stack and Core, and return correctly for both IP families.
