# Explicit physical-network subscription download

This change adds a Windows-only, per-source download choice. Existing sources
default to `system` and retain the existing system/PAC behavior. `physical` is
an explicit privacy decision to use a physical network instead of the configured
proxy or captured TUN route. HTTP 401/403 never changes the selected route.
Non-Windows clients retain the setting but cannot save/use this Windows route.

## Transport and trust boundaries

- Qt continues to own the complete original HTTPS URL, HTTP/1 policy, certificate
  verification, manual same-origin redirect checks, 4-MiB response cap,
  30-second total deadline, cancellation and failed-update transaction. Physical
  mode explicitly rejects plain HTTP. No alternative HTTP/TLS implementation or
  external proxy program was introduced.
- `swirl_download_route_v1` accepts only `{op:start, host, port}` and
  `{op:stop, handle}`. A caller provides a fixed output buffer of at least 4096
  bytes in one call. Smaller buffers/size queries fail before listener/task
  creation. Start returns a positive signed-64-bit-compatible handle, ephemeral
  loopback port and random Basic-auth credentials. Stop is idempotent.
- The Rust bridge listens only on `127.0.0.1`, uses the existing bounded
  `swirl_protocol::accept` parser/authentication, and accepts CONNECT only for its
  exact host/port. IPv6 authorities compare as addresses, including equivalent
  compressed forms; domain comparison is case-insensitive. Authentication and
  target checks occur before DNS or outbound connection creation.
- DNS is initialized once inside the authenticated, cancellable task. The
  bridge uses read-only `GetAdaptersAddresses`, `GetIfEntry2` and
  `GetIpForwardTable2` snapshots to select an active hardware interface with a
  real default route, source address and minimum route-plus-interface metric.
  It uses that adapter's configured nameservers, pinned UDP, and same-server
  TCP when needed. DNS frames, question, transaction ID, truncation and response
  code remain bounded/checked through existing codecs. No public resolver is
  hardcoded as a fallback; DNS failure remains a failed download.
- Each outbound socket reuses the platform's `IP_UNICAST_IF` /
  `IPV6_UNICAST_IF` pin-and-readback operation, explicitly binds its physical
  source, and checks the connected source. Local/private, shared/CGNAT and
  fake-IP destination answers are rejected as a set, rather than selecting one
  address from a mixed unsafe answer. One immutable route cannot fall back to
  system proxy, the selected node or a different policy after failure.
- The independent bridge runtime has one worker, at most eight route handles,
  four active connections per route and sixteen accepted connections per route.
  Native lifetime is capped at 30 seconds. Stop/drop/deadline abort the listener
  and child tunnels. The Qt lease also cleans up late or discarded callbacks.
  No Core egress lease, host proxy, firewall, route, DNS or third-party TUN
  configuration is modified.

Winsock documents that binding a source resolves a scoped IPv6 destination with
scope ID zero; current code also pins and verifies the selected IPv6 interface.
The source snapshot excludes link-local sources. A real network using a
link-local DNS server has not been separately accepted.

## Validation and limits

The first three bridge tests were observed failing before implementation and
then passing through real loopback sockets. Final local GNU Windows checks ran:

- **12 native route tests passed:** authentication/target rejection without
  origin access; opaque bidirectional 128-KiB reply after FIN; cancellation;
  native deadline; four occupied slots blocking a fifth origin until release;
  pinned DNS source and transaction replay rejection; truncated UDP to the same
  TCP server; invalid/incomplete TCP framing; unsafe destination filtering;
  IPv6 authority equivalence; fixed-capacity ABI rejection and actual ABI
  startup/authentication/idempotent stop without system resolution.
- A final IPv6 site-local `fec0::/10` boundary correction was verified with an
  observed failing `fec0::1` case before the fix, followed by **12/12** native
  tests passing again. Scoped Clippy, workspace formatting and whitespace checks
  passed after that final production change.
- The two read-only firewall fixture-selector tests passed, and the two affected
  Core multi-address DIRECT DNS regressions passed.
- API/platform/Core library-and-test Clippy with `-D warnings`, workspace
  `cargo fmt --all -- --check`, portable source-boundary checks (11 tests) and
  whitespace checks passed. No physical firewall fixture was run locally.

Qt HTTPS integration, source-store/UI tests, source-identical Release pairing
and a fixed public control must be reported against their actual final build.
This native report does not claim a new provider fetch, real subscription
success from the new GUI route, physical IPv6/DNS acceptance, one-hour stability
or throughput parity. The authorized provider capture was not repeated here.

## Disabled firewall fixture correction

CI job 126630209776 failed during `New-NetFirewallRule`, after selecting the
first hidden-inclusive hardware Ethernet record. That selector did not require
a visible/up/current IPv4 interface. The corrected **test fixture only** joins
visible physical Ethernet `Up` adapters with connected ActiveStore IPv4 rows
whose index and alias agree. It still creates and verifies the same exact
disabled rule; production ownership, interface, type, address, port, profile,
security and readback checks are unchanged. New CI metadata records only
identity/hash and eligibility booleans.

The actual old selector was extracted from Git and failed under the controlled
cmdlet fixture; the current script selected the valid identity and rejected an
unavailable set. The Rust wrappers passed **2/2**. A new disposable CI run must
verify the real provider operation: the previous runner's hidden/disconnected
state was not recorded, so the selection explanation remains an inference.

Primary references consulted before implementation:
[Microsoft GetAdaptersAddresses](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getadaptersaddresses),
[MIB_IF_ROW2](https://learn.microsoft.com/en-us/windows/win32/api/netioapi/ns-netioapi-mib_if_row2),
[Winsock IPv6 scope rules](https://learn.microsoft.com/en-us/windows/win32/winsock/link-local-and-site-local-addresses-2),
[WinHTTP options](https://learn.microsoft.com/en-us/windows/win32/winhttp/option-flags),
[Microsoft Get-NetAdapter source](https://github.com/MicrosoftDocs/windows-powershell-docs/blob/main/docset/winserver2025-ps/NetAdapter/Get-NetAdapter.md),
[NetSecurity New-NetFirewallRule](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule?view=windowsserver2025-ps).
Existing Swirl parser, relay, pinning and DNS codecs were reused; no upstream
implementation was copied.
