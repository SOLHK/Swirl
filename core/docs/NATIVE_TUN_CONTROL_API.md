# Native TUN control API, schema 1

This document describes the implemented Rust control boundary for the separate
Windows native TUN helper. It is intended for the later Qt integration and for
isolated backend tests. It does not enable the existing Qt TUN switch or certify
real Windows networking.

The authoritative implementations are
[`native_tun_control.rs`](../crates/swirl-api/src/native_tun_control.rs),
[`native_windows.rs`](../crates/swirl-api/src/native_windows.rs), and
[`swirl-tun-helper.rs`](../crates/swirl-api/src/bin/swirl-tun-helper.rs).
The platform transaction and its ownership rules are documented in
[`swirl-platform/README.md`](../crates/swirl-platform/README.md).

## Process ownership and C ABI

The existing ABI remains version `1`; there is no new TUN-specific exported
function and no new C-owned Rust allocation. The header is
[`crates/swirl-api/include/swirl_api.h`](../crates/swirl-api/include/swirl_api.h).
The relevant declaration is:

```c
intptr_t swirl_core_command(const uint8_t *input, size_t input_len,
                           uint8_t *output, size_t output_capacity);
```

The caller supplies valid, non-overlapping input and output buffers for the
entire call. Input is one UTF-8 JSON object, from 1 byte through 1 MiB. Output
capacity must be at least 1 MiB. A nonnegative result is the response byte count,
without a trailing NUL. Negative results are `-1` for invalid buffers or sizes,
`-2` for a caught panic, and `-3` for unavailable controller state or a
serialization failure. A JSON command error normally returns a positive byte
count with `"ok": false`.

The lifecycle ABI does **not** use the import ABI's size-query/repeat convention.
Do not execute a mutating lifecycle request twice to determine output length.
Serialize lifecycle calls and stop all owned handles before unloading a DLL.
`swirl_core_build_info` provides source/build identity using the existing
4096-byte buffer contract.

The process-global C ABI uses an ordinary `Controller::default()`. It permits
offline TUN validation and status for its own Core handles, but returns
`TunHelperRequired` for TUN start, stop, and recovery. It does not elevate the Qt
GUI. Its status cannot inspect a different process's helper-owned session.

The helper creates `Controller::for_native_tun_helper()` in its worker process.
That worker owns its V2 Core, packet stack, dispatcher, Wintun device, and network
transaction. A handle returned by the GUI's DLL cannot be passed to the helper.
Create the V2 Core through the helper's command stream and retain the returned
handle and epoch there. Both ingress modes inside that Core use the same rules,
DNS resolver, policy transactions, protocol outbounds, and session manager.

## Helper executable

`swirl-tun-helper` supports these modes:

| Argument | Behavior |
| --- | --- |
| `--capabilities` | Prints one capabilities object and exits. This is also the default mode; it does not load Wintun or change networking. |
| `--serve` | Runs a supervisor and a worker connected by private inherited standard streams. The worker consumes the existing Core commands and the native TUN commands below. |
| `--recover` | Attempts ownership-checked recovery of stale network journals in the protected, fixed state directory, then exits. |
| `--worker` | Internal child mode. Integrations must use `--serve` to retain supervision. |

Network operations require the helper to have already been launched with the
necessary administrative privilege. There is no automatic UAC prompt, service
installation, public RPC listener, named-pipe server, or arbitrary shell-command
endpoint in this implementation. Windows mutation scripts are fixed and receive
typed data. Production installation, an approved elevation mechanism, and
authenticated GUI-to-helper launch remain separate integration work.
The current worker also runs the Rust Core and packet pump under that helper
token. Splitting privileged OS configuration from an unelevated data-plane
process has not been implemented; moving the GUI out of the privileged process
alone is not a complete privilege-separation design.

Each worker request must be one complete JSON line followed by a newline. The
line, including its terminator, is limited to 1 MiB. Responses are UTF-8 JSON
lines. Drain stdout continuously and correlate ordinary responses by
`request_id`; helper failure and supervisor recovery messages may also appear.
A final unterminated line is not a command. Closing the command stream is the
worker's orderly shutdown signal. Do not use terminating the process as the
normal stop operation.

The supervisor attempts stale-journal recovery before accepting a worker and
after its worker exits. A worker receiving EOF stops its TUN sessions before Core
teardown. These mechanisms cover the implemented supervisor/worker failure
paths; simultaneous termination of both processes still requires a later
`--recover` or startup recovery. This is not an installed always-on recovery
service.

The worker uses one bounded response writer and waits at most two seconds for
each response to be written. A blocked or broken output poisons the connection;
the worker restores its owned network state and exits without attempting another
synchronous stdout write. The supervisor bounds both forwarding cleanup and its
final recovery report. A timed-out report was not delivered: inspect the exit
status and use explicit recovery as needed.

Each fixed PowerShell operation has a 30-second deadline covering redirected
stdin as well as execution. A command starts suspended, joins a private
kill-on-close Job Object, and then resumes; unowned execution is never a
fallback. Timeout or command-owner loss terminates its process tree. This does
not undo an operation already accepted by the external CIM/WMI service: callers
must still inspect recovery results and preserve a conflicting journal. A
crash in the small creation-to-assignment window can leave a suspended process
that has not executed the command, so atomic process creation is not claimed.

## Request envelope and identity

Every native TUN request contains:

```json
{
  "native_tun_schema": 1,
  "request_id": "60000000-0000-4000-8000-000000000001",
  "op": "native_tun_validate",
  "config": {
    "driver_path": "C:\\Program Files\\Swirl\\wintun.dll",
    "adapter_guid": "70000000-0000-4000-8000-000000000001",
    "adapter_name": "Swirl Native TUN"
  }
}
```

`native_tun_schema` is the integer `1`, independently versioned from
`control_schema: 2` used for V2 Core configuration transactions. Unknown fields,
unknown operations, invalid field types, and unsupported schemas fail explicitly;
they do not fall back to another command decoder or another proxy core.

`request_id` has the UUID text shape accepted by the existing Core identity
validator. It is echoed on parsed command responses, including failures. It is
a correlation identifier; native TUN commands do not provide a durable receipt
cache or promise deduplication of repeated request IDs. Malformed input can fail
before an ID is available and therefore return no `request_id`.

`handle` is a canonical decimal `u64` **string**, not a JSON number. Leading
zeroes are rejected except for the string `"0"`, which is not an allocated
handle. `engine_epoch` must exactly equal the epoch returned by that handle's
current V2 Core. The epoch is also a decimal `u64` string; it is **not a UUID**.
Keep both values as strings in Qt/JavaScript to avoid numeric precision loss.
A Core restart invalidates its previous handle/epoch pair. Never synthesize an
epoch or reuse a pair across worker processes.

## Configuration

| Field | Type/default | Validation and meaning |
| --- | --- | --- |
| `driver_path` | Required string | Nonempty; on Windows it must be absolute. Actual loading further requires a local-drive DLL with the pinned official Wintun 0.14.1 hash for the target architecture. The DLL is not downloaded or searched for automatically. |
| `adapter_guid` | Required string | Lowercase UUID text identifying the dedicated adapter. Use a stable, nonzero GUID reserved for this integration. Existing adapters and stale sessions are not adopted. |
| `adapter_name` | Required string | Nonempty, no NUL, at most 127 UTF-16 code units. An already-existing adapter name is a conflict. |
| `mtu` | Integer, `1500` | `1280..=9000`; used for both the packet stack and both Windows interface address families. |
| `max_tcp_flows` | Integer, `256` | `1..=1024`; admission limit for TUN TCP flows. |
| `max_udp_flows` | Integer, `128` | `1..=512`; passed to the stack's UDP endpoint limit and the bridge's bounded UDP flow admission. |

Other stack queue and buffer limits remain internal defaults. The dry-run
`socket_payload_budget_bytes` is a bound for the configured TCP/UDP socket
payload buffers, not a total process-memory measurement. Packet/datagram queues,
fragment buffers, metadata, Wintun rings, and existing native outbound state are
additional. No throughput or latency promise is inferred from these limits.

### `native_tun_validate`

Required operation field: `config`.

This operation validates the typed configuration and returns a fixed network
plan without loading a DLL, installing a driver, creating an adapter, reading
host network state, or changing routes/DNS/firewall. It does not require a Core
handle or helper privilege. On non-Windows hosts, Windows path absoluteness is
not checked by this portable validator.

A successful response includes:

```json
{
  "ok": true,
  "native_tun_schema": 1,
  "request_id": "60000000-0000-4000-8000-000000000001",
  "validated": true,
  "network_plan": {
    "ipv4_address": "198.18.0.1/30",
    "ipv6_address": "fd53:7769:726c::1/126",
    "dns": ["198.18.0.2", "fd53:7769:726c::2"],
    "mtu": 1500,
    "physical_dns_modified": false,
    "physical_routes_removed": false,
    "requires_encrypted_dns": true,
    "requires_privileged_helper": true,
    "socket_payload_budget_bytes": 83886080,
    "additional_memory": "packet/datagram queues, fragment buffers, metadata, Wintun rings and native outbounds"
  },
  "capabilities": {
    "schema": 1,
    "packet_backend": true,
    "windows_driver_compiled": true,
    "controller_requires_helper": true,
    "driver_version": "0.14.1",
    "tcp": true,
    "udp": true,
    "ipv4": true,
    "ipv6": true,
    "fake_ip": true,
    "encrypted_dns_required": true,
    "real_windows_11_acceptance": false,
    "icmp_relay": false,
    "arbitrary_ipv6_extensions": false,
    "automatic_gui_elevation": false,
    "system_kill_switch": false,
    "capture_continuous_during_network_restart": false
  }
}
```

The example shows a Windows build. `windows_driver_compiled` is `false` on a
non-Windows build. Validation is not evidence that the DLL exists, privileges
are available, physical egress is usable, firewall policy permits guards, the
Core has secure DNS, or a real connection can be established.

### `native_tun_start`

Required operation fields: `handle`, `engine_epoch`, `config`.

```json
{
  "native_tun_schema": 1,
  "request_id": "60000000-0000-4000-8000-000000000002",
  "op": "native_tun_start",
  "handle": "1",
  "engine_epoch": "17172364226732469411",
  "config": {
    "driver_path": "C:\\Program Files\\Swirl\\wintun.dll",
    "adapter_guid": "70000000-0000-4000-8000-000000000001",
    "adapter_name": "Swirl Native TUN",
    "mtu": 1500,
    "max_tcp_flows": 256,
    "max_udp_flows": 128
  }
}
```

The example's handle and epoch are illustrative; replace both with the values
actually returned by `start_v2` in the **same helper worker**. The V2 Core must
have explicit validated DoT/DoH upstreams with numeric bootstrap addresses.
System DNS or plaintext fallback is not permitted while the native lease is
held. The first TUN lease also requires a quiescent Core, with no existing
sessions or active probe. Pause admission from clients before enabling TUN;
the helper does not pretend that already-running unprotected connections are
safe to capture.

Only one native session is allowed per helper controller. Start obtains physical
egress protection before capture, creates its packet bridge and dedicated
adapter, persists a typed journal, and applies its owned network transaction.
The plan includes TCP/UDP port-53 guards on all known hardware adapters, the
TUN's MTU/address/DNS settings, and split default routes for both IP families.
It does not replace physical DNS settings or delete physical default routes.
The DNS guards are constrained to port 53; they are not a general traffic
kill-switch or an interception mechanism for application-owned encrypted DNS.

Success returns a session status object with the ordinary response envelope.
An error is not proof that every attempted OS operation was reversed: a
recovery conflict deliberately preserves third-party changes and retains the
journal for recovery. Do not respond by deleting journals or resetting physical
network settings.

### `native_tun_status`

Required operation fields: `handle`, `engine_epoch`.

```json
{
  "native_tun_schema": 1,
  "request_id": "60000000-0000-4000-8000-000000000003",
  "op": "native_tun_status",
  "handle": "1",
  "engine_epoch": "17172364226732469411"
}
```

With an owned session, the response includes `state`, `desired_enabled`,
`last_error`, `capture_active`, `dns_guard_active`, `core_egress_guard_owned`,
`statistics`, and `capabilities`. `last_error` is a code or null;
`statistics` is null while no packet device is active. Without a native session
for the valid handle, status reports `state: "stopped"` and
`desired_enabled: false`; session-specific fields need not be present.

| State | Meaning |
| --- | --- |
| `running` | The current adapter, bridge, and network transaction started successfully. This is lifecycle state, not a continuous reachability or leak-test result. |
| `waiting_for_network` | The desired setting remains enabled while the lifecycle retries after a network/pump change. Treat capture as unavailable during this interval. |
| `recovery_required` | A stop/recovery operation could not finish safely. Keep the error visible and preserve recovery evidence. |
| `stopped` | No active native session is reported for this handle, or stopping completed. |

`desired_enabled` describes requested intent. It does not assert that capture is
currently installed or that traffic is protected. Automatic rebuilding removes
the old owned capture transaction before installing a replacement. There is no
host-wide kill-switch during that gap; other applications may use the physical
network. Core outbound binding and strict DNS leases prevent Core routing loops
and DNS downgrades, but do not supply a Windows-wide zero-leak guarantee during
migration. Do not display `waiting_for_network` as a successfully connected TUN.

`capture_active` and `dns_guard_active` are true in `running`, false in
`waiting_for_network`/`stopped`, and null when the lifecycle cannot establish a
safe conclusion, including `recovery_required`. Null is unknown, not false or
success. These fields reflect the controller's transaction state, not an
independent audit of subsequent administrator/firewall changes.
`core_egress_guard_owned` reports the retained Core socket guard; its presence
does not mean system-wide capture is active.

The current packet statistics contain:

| Field | Interpretation |
| --- | --- |
| `interface_index` | Index of this session's dedicated adapter; ownership also records its GUID. |
| `packets`, `malformed_packets` | Stack ingress and malformed-packet counters. |
| `active_tcp_flows`, `active_udp_endpoints` | Current packet-stack resources, not all Core/system-proxy sessions. |
| `rejected_tcp_flows` | Packet-stack TCP admission/rejection counter. |
| `udp_dropped` | Stack and bridge UDP drop counters combined. |
| `packet_io_dropped` | Packet-device ingress/send-ring drops. |
| `tcp_failures`, `udp_failures`, `dns_failures` | Bridge operation failures; these do not establish a particular network diagnosis. |

These counters belong to the current active packet bridge and can reset when it
is rebuilt. They are not persistent lifetime totals.

### `native_tun_stop`

Required operation fields: `handle`, `engine_epoch`.

```json
{
  "native_tun_schema": 1,
  "request_id": "60000000-0000-4000-8000-000000000004",
  "op": "native_tun_stop",
  "handle": "1",
  "engine_epoch": "17172364226732469411"
}
```

The helper verifies ownership and restores its network transaction before
releasing the associated device/Core constraints. Successfully stopped state is
returned only after that operation succeeds. Stopping an already-stopped native
session on a still-valid Core handle is permitted. A successful stop response
includes `state: "stopped"` and `desired_enabled: false`.

When stop fails, do not discard the handle or report successful shutdown. Keep
the helper and recovery journal available, show the returned error, and retry
stop/recovery through the controlled interface. The existing Core `stop` command
also invokes native-session shutdown before removing a V2 Core; a native
recovery failure prevents that command from silently removing its Core.

### `native_tun_recover`

This operation accepts no handle, epoch, path, command, or configuration field:

```json
{
  "native_tun_schema": 1,
  "request_id": "60000000-0000-4000-8000-000000000005",
  "op": "native_tun_recover"
}
```

It runs only in a helper controller on Windows. It scans fixed-name journals in
the verified Windows CommonApplicationData/Swirl/NativeTun directory, respects
live file locks, and recovers only resources that still match the recorded
owner. A missing TUN adapter does not prevent recovery of that session's owned
persistent firewall rules. Successfully restored journals are archived;
conflicts are retained.

A successful response includes `state: "recovered"`, `journals_restored`, and
`active_owners`. Nonzero `active_owners` means live sessions were deliberately
left alone; it does not mean all TUN sessions were stopped. Recovery does not
restore a previously running Core or reconnect a TUN. A live suspended session
can retain its Core egress lease without a current network journal, in which
case recovery returns `TunEgressStillOwned`. Use `native_tun_stop` for a live
session first. Recovery can release an abandoned Core egress guard only after
its owned journals are safely restored; it never takes a live lease away.
Start a new session only after resolving stale state and obtaining a valid
handle/epoch in the current helper worker.

## Errors and integration behavior

Errors are codes for application logic, not arbitrary PowerShell commands or
text to execute. Examples from the implemented paths include:

| Codes | Integration response |
| --- | --- |
| `TunCommandInvalid`, `TunUnsupportedSchema`, `InvalidRequestId` | Correct the protocol envelope. Do not retry through legacy control schema. |
| `TunConfiguration`, `TunLimits`, `TunDriverAbsolutePathRequired`, `IdentityUuid`, `IdentityDecimal` | Correct the relevant configuration/identity input. |
| `UnknownHandle`, `EngineEpochMismatch` | Refresh the handle/epoch from the same helper worker; a stale reference must not control a new Core. |
| `TunHelperRequired`, `TunWindowsRequired`, `TunHelperPermission` | The operation is unavailable in the current process/platform/privilege context. Do not elevate the GUI as a fallback. |
| `DnsEncryptedUpstreamRequired`, `TunRequiresQuiescentCore`, `Reconfiguring` | Resolve Core preconditions through the existing V2 configuration/session workflow. |
| `TunAlreadyOwned`, `TunOwnedByAnotherHelper`, `TunEgressStillOwned`, `TunNetworkConflict` | Respect the current owner or conflicting network; do not replace an existing adapter/journal. |
| `TunPhysicalNetworkUnavailable`, `TunEgressUnavailable`, `TunWindowsNetworkOperation` | Report failure or pending retry. A generic Windows-operation code can cover a driver, firewall, or OS precondition failure. |
| `TunRecoveryRequired`, `TunRecoveryConflict`, `TunRecoveryFailed`, `TunRecoveryJournalInvalid` | Keep recovery evidence and use the owned recovery path. Never delete a journal to make a subsequent start appear successful. |

The list is explanatory, not a promise that no additional existing Core/DNS
error code can propagate. A parsed native error has this form:

```json
{
  "ok": false,
  "native_tun_schema": 1,
  "request_id": "60000000-0000-4000-8000-000000000002",
  "error": "TunHelperRequired"
}
```

## Later Qt integration and acceptance

The later integration should validate configuration first, verify the helper
binary's source/build identity against the shipped Rust Core, establish the
approved helper launch channel, and create/configure the V2 Core in that worker.
Use its returned handle/epoch for native commands. Continue to use existing V2
transactions for node/rule/policy changes; the TUN API does not accept a second
rule document or proxy-protocol configuration. Poll status without launching
network commands from the GUI and stop the native session before releasing the
helper Core. The existing ordinary capability `optional.tun` remains disabled
for the current UI until that separate integration and acceptance are complete.

Capabilities distinguish implemented packet support from acceptance:
`real_windows_11_acceptance` remains `false`. Portable control/transaction tests,
synthetic dual-stack L3 tests with real loopback peers, cross-compilation, and
Windows CI have different evidentiary scope. They do not certify driver-based
Windows 11 TCP/UDP internet access, Chrome/VS Code/Codex, DNS leakage, route loops,
Wi-Fi handoff, sleep/wake, crash recovery, sustained-load performance, or installer
integration. Those require separately recorded tests in an approved, recoverable
Windows environment. No API flag or successful dry-run changes that requirement.
