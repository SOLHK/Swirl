# Experimental packet worker using the shared Core

`swirl-tun-packet-worker --internal-packet-worker` reuses Controller schema 2,
the original packet bridge, FlowDispatcher, DNS/Fake-IP allocator, rules and
native protocols. No second Core or third-party package was added. This internal
endpoint is not enabled in the GUI, product helper, installer or WFP exemptions.

It requires an actual restricted Low token, no elevation, Administrators
deny-only and at most the allowed change-notify privilege. These checks do not
authenticate a broker or SCM principal. Physical egress is suspended before any
Core is created and is never released here; loopback remains available for the
scoped fixture. Start/prepare candidates must use a loopback listener on port
zero. Other listeners are rejected, not rewritten. There is no physical binding,
OS configuration, pathname RPC or DIRECT fallback command.

## Resource and wire boundaries

The existing launcher inherits exactly six resources: stdio, two directional
packet pipe ends and one approved Fake-IP file. Init borrows the three numeric
resource identifiers and duplicates them non-inheritably with fixed minimum
rights. It checks pipe/disk type, regular-file metadata and object identity,
including aliases to stdio. It does not take ownership of untrusted identifiers.
The original handles close at process exit. Fake-IP uses the same durable parser,
lock, bound, conflict handling and sync. Epochs/handles are not credentials.

Control is newline-delimited JSON, bounded to 1 MiB including newline. Each
request contains `packet_worker_schema:1`, UUID `request_id`, fixed nonzero
`epoch` and `command`. Replies contain schema, request ID, epoch, `ok`, `result`.

| op | Payload/behavior |
| --- | --- |
| `init` | Once: `mtu`, `max_tcp_flows`, `max_udp_flows`, `resources:{packet_input,packet_output,fake_ip_journal}` |
| `core` | `json`: original schema-2 command string with matching request ID; only validate/start/prepare/activate/finish/rollback/status, at most one Core |
| `bridge_start` | Decimal `handle`/`engine_epoch` bind the existing Core, once |
| `status` | Actual token profile and bridge/packet counters, explicit capability boundaries |
| `stop` | Stop bridge and Core; no OS restoration claim |

The original V2 string/result are preserved; duplicate nested fields cannot
disappear through re-encoding. Unknown/duplicate fields, changed epoch and
command errors terminate the connection after bounded reporting where possible.
Status/stop use empty struct variants: a reproduced regression showed serde's
internally tagged unit variants otherwise accepted extra fields.

One-second heartbeat events have `event:"heartbeat"` and no request ID. Shared
single-writer output preserves the helper's two-second poison-on-stall contract
and eight original tests. Two dedicated OS threads do framed packet IO, never
blocking Tokio workers. Full ingress queues count/drop packets; IO failure stops
the session. Stop reports packet threads as unjoined: the parent must reap its
job before joining pumps. NativeTunLease remains held through Core.stop.

## Validation and explicit disposable gate

Local frozen Windows GNU checks passed 330 tests in 24 all-target groups across
Core/API/TUN/platform, zero failed/ignored/filtered; targeted Clippy and fmt
passed. Included: six worker boundary tests, three temporary-file/pipe handle
tests, eight original helper tests and three packet-fixture tests. The local
scenario uses actual shared Core and independent loopback peers: both IP
families preserve empty/1,200-byte UDP; A/AAAA Fake-IP reaches real TCP, with
1,024-byte upload/FIN followed by exact 128 KiB reply/FIN. No restricted child
or desktop is created by these local tests.

Only on an authorized elevated disposable Windows environment:

```powershell
$env:SWIRL_SOURCE_SHA = (git rev-parse HEAD).Trim()
cargo build --manifest-path core/Cargo.toml --locked --release -p swirl-api `
  --bin swirl-tun-packet-worker --example windows-packet-worker-smoke
./core/target/release/examples/windows-packet-worker-smoke.exe `
  --disposable-environment `
  --worker (Resolve-Path ./core/target/release/swirl-tun-packet-worker.exe) `
  --directory C:/approved-fixture/fresh-packet-worker
```

Before spawn, source/image identity, exact workloads, 15-second IO/stop bounds
and output limits are synced in plan.json. The fixture retains child output,
checks actual token/counter observations, reaps the job before bounded pipe joins,
then reopens Fake-IP persistence to check both mappings. CI runs it independently
after Wintun and retains both failures. A binary or local scenario pass does not
prove restricted-process acceptance. At `35847e9` the original A/B children still
failed before main despite correct desktop access; real startup remains required.

Wintun-to-child wiring, physical egress binding, kernel service identity,
authenticated IPC/UAC/GUI, system kill switch, recovery, public/Win11 application
traffic and long-load acceptance remain separate required work.
