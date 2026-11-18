# Windows acceptance collector and evidence contract

`tools/Collect-NativeTunAcceptance.ps1` runs on PowerShell 7. Its default is a
read-only Windows baseline. It neither enables TUN nor changes routes, DNS,
firewall, proxy, adapters, installed applications or private profile data.
Use a **fresh directory outside Git** for every run. The exported inventory has
counts and schema fingerprints, without addresses, SSIDs, interface aliases,
subscriptions, environment variables, process command lines or credentials.
Do not automatically upload evidence: inspect the output before sharing it.

```powershell
pwsh -NoProfile -File tools/Collect-NativeTunAcceptance.ps1 `
  -OutputDirectory D:/Codex/outputs/native-tun-baseline-20261101
python tools/Verify-NativeTunAcceptance.py `
  D:/Codex/outputs/native-tun-baseline-20261101 --expect-source (git rev-parse HEAD)
```

The collector records Windows version/build/product type, manufacturer/model,
operator-declared physical/virtual/unknown class, privilege, architecture,
source SHA and dirty state, collector hash, adapter/route/DNS summaries, firewall
service/profiles and actual visible owned DNS rules. Permission or provider
failures are `unavailable`, never successful observations. A Windows 11 caption,
operator machine classification or installed rule is not application, traffic,
leak or kill-switch acceptance. Rule visibility does not establish enforcement.

## Resource sampling with a frozen plan

Before starting load, record the scenario's exact generator/commands, throughput,
connection count, test endpoints in a private log, workload duration and acceptance
thresholds. `plan.json` is written before observations; `result.json` records its
hash. The collector does not start or infer load. To sample one explicitly
selected process while the independent workload runs:

```powershell
pwsh -NoProfile -File tools/Collect-NativeTunAcceptance.ps1 `
  -Mode Sample -ProcessId <actual-helper-or-worker-PID> `
  -DurationSeconds 1800 -IntervalSeconds 5 -MaxRssMiB 512 -MaxHandles 4096 `
  -MachineClass Physical -Wintun C:/approved-fixture/wintun.dll `
  -OutputDirectory D:/Codex/outputs/native-tun-resources-20261101
python tools/Verify-NativeTunAcceptance.py D:/Codex/outputs/native-tun-resources-20261101
```

The defaults define a 30-minute observation window, 5-second cadence, 512 MiB
RSS ceiling and 4096-handle ceiling. They are initial observation limits, not a
product performance promise or a replacement for device/workload-specific
pre-run criteria. Adjust them **before** the run and retain failed evidence.
The verifier checks every peak, duration, monotonic CPU/time and sampling gaps;
ending early, a process exit/reuse, missing samples or exceeded thresholds fails.
It reports CPU time, RSS/private bytes, handles and threads. It does not claim to
count sockets, Tokio tasks or Wintun rings, identify a leak from a short sample,
measure latency or throughput, or compare unmatched workloads.

## Existing scoped driver smoke: explicit opt-in only

This mode uses the existing [scoped smoke contract](NATIVE_TUN_SMOKE.md), with
loopback peers and exact test routes. Only run it on an explicitly authorized,
recoverable **disposable** elevated Windows machine. It creates/removes its own
temporary adapter and routes; this is an actual network mutation.

```powershell
$env:SWIRL_SOURCE_SHA = (git rev-parse HEAD).Trim()
cargo build --manifest-path core/Cargo.toml --locked --release `
  -p swirl-api --example windows-tun-smoke
pwsh -NoProfile -File tools/Collect-NativeTunAcceptance.ps1 `
  -Mode ScopedDriverSmoke -DisposableNetwork -MachineClass Virtual `
  -SmokeExecutable ./core/target/release/examples/windows-tun-smoke.exe `
  -Wintun C:/approved-fixture/wintun.dll `
  -OutputDirectory D:/Codex/outputs/native-tun-driver-20261101
python tools/Verify-NativeTunAcceptance.py D:/Codex/outputs/native-tun-driver-20261101 `
  --expect-source (git rev-parse HEAD)
```

The collector preserves the command's binary hash, arguments, exit code,
original stdout/stderr log, driver hash/version and before/after inventories.
The verifier requires the exact source in the original final JSON, packet
transfer, both families/protocols, cleanup assertions and original cleanup
markers. It rejects a dirty source, failed exit or missing final JSON. It never
upgrades scoped loopback evidence to Windows 11 physical capture. The wrapper
does not forcibly kill an in-flight smoke transaction: preserve its cleanup
path and inspect owned recovery state after any failure.

## Remaining physical acceptance

The collector/verifier deliberately cannot grant release approval. Independently
record actual TUN capture (including proof the system proxy is not carrying the
test), public dual-stack TCP/UDP, UDP/TCP DNS and leak observations, WebSocket/SSE,
HTTP/2 and HTTP/3/QUIC, Chrome/Edge/VS Code/Codex/GitHub; kill-switch and DNS guard
removal faults; unauthorized-helper IPC; egress loops and VPN/multi-NIC conflicts;
normal/forced/helper/worker exits, interface changes, suspend/resume and reboot;
long connections, short-connection/concurrent sustained load and node switching.

For each scenario retain source/binary/driver identity, exact private test command,
predeclared load/duration/thresholds, start/end timestamps, original packet or
application observations, failure/recovery logs, fix SHA and re-test artifacts.
Source-controlled tests here validate the **evidence contract**, not those real
scenarios. A hash is change detection, not a cryptographic signature proving that
an operator's machine declaration or supplied log is authentic.
