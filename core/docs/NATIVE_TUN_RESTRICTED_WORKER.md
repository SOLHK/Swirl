# Windows restricted process foundation

This is a process-launch primitive in the existing platform adapter, not a
completed broker/worker split. The product still runs packet parsing and Core
inside its elevated worker. No GUI capability or product lifecycle calls this
primitive yet.

The launcher accepts an approved drive-local executable and structured arguments.
It uses a restricted version of the elevated interactive user's token, makes the
Administrators SID deny-only, disables maximum privileges and sets low integrity.
It refuses a SYSTEM source token; a future service must obtain an authenticated
user token rather than restrict SYSTEM in place. It verifies the actual suspended
child's token before resuming it. There is no ordinary-process fallback.

The ordinary `spawn` inherits exactly three anonymous stdio pipe ends through the explicit
`PROC_THREAD_ATTRIBUTE_HANDLE_LIST`. Ambient handles, credentials and environment
variables are not copied. The environment contains only the Windows directory
and its System32 search path. A private low-label desktop and job UI restrictions
separate the child from the interactive desktop. The launcher never switches the
user's visible desktop. Because `CreateDesktopW` can bind its calling thread,
a dedicated creator thread saves/restores its own binding and joins before
returning the desktop. The broker's thread binding is verified unchanged. A
kill-on-close job contains the suspended child before its first
instruction and includes descendants; timeout, explicit stop and owner loss
terminate the job. Cleanup waits are bounded and failures are reported.

`spawn_data_plane` is the explicit six-resource variant: the same three stdio
ends, two internally created directional packet pipe ends, and one approved
already-open Fake-IP file. Its duplicate grants only read/write data, read
attributes and synchronization; deletion, attribute writes, owner and DACL
changes are excluded. It accepts no arbitrary inherited-handle list or worker
pathname request. The broker must stop using the shared file cursor/allocator
lock during delegation. `FakeIpStore::from_file` consumes that file and reuses
the original bounds, exclusive lock, sequence/conflict checks, torn-tail repair
and durable append/sync logic. The inherited cursor is reset before replay.

The separate packet framing primitive has a 24-byte versioned header, nonzero
launch epoch, exact per-direction sequence and validated MTU. Bad/truncated
frames poison the channel; allocation follows header checks. Epoch/sequence
are not authentication. Control/heartbeat remain on independent stdio, and
the owner must still cancel blocked packet IO. The resource smoke transfers
128 raw bytes and a bounded file update; it does not claim framing, Core,
network, backpressure or product cancellation acceptance.

This is not an AppContainer or a complete sandbox. The child can still read
ordinary user-accessible files and use the network. Trusted installed payloads,
GUI/broker authentication, typed bounded packet IPC, broker-owned Wintun and OS
configuration, delegation of Fake-IP persistence, shared Core forwarding and
network compatibility remain required integration work. The protected journal's
ACL must not be relaxed to make a low-integrity worker write it.

Normal module tests query only the current token and test serialization/quoting;
they do not create restricted tokens, desktops or child processes. The separate
smoke must run only on an authorized elevated disposable Windows environment:

```powershell
$env:SWIRL_SOURCE_SHA = (git rev-parse HEAD).Trim()
cargo run --manifest-path core/Cargo.toml --locked --release `
  -p swirl-platform --example windows-restricted-worker-smoke -- `
  --disposable-environment --directory C:/approved-fixture/fresh-worker-test
```

The directory must be fresh. This command creates only fixture files, a private
desktop and child jobs. It checks the real child token, desktop, three pipes,
minimum environment, inability to write a protected Administrators/SYSTEM file,
absence of an intentionally inheritable privileged token handle, and actual
grandchild termination when its job owner is dropped. Child output is retained
before assertions. It also verifies the broker's desktop remains unchanged and
the exact private desktops cannot be reopened after cleanup. A successful process smoke does not accept product packet
IPC, network forwarding, UAC, reboot recovery or Windows 11 system TUN.

The accessible medium-integrity Windows 11 workstation has not run that privileged
command. Its local checks are compilation, linking and read-only/model tests;
the explicit disposable CI command must provide real process-isolation evidence.

The first real process smoke at `88e9fdf` / PR `6d81b38` failed its child exit
check with genuinely empty stdout/stderr. The original fixture omitted the
exit value, so the cause is unresolved. Original outputs and hashes remain in
[the failure record](native-tun-evidence/windows-88e9fdf-failed.json). A fixed
Rust-main-entry marker, exact unsigned/hex exit and original child output now
separate startup and application failure; no token, desktop ACL or job
restriction was relaxed on the basis of empty output.

At `744d10a` / PR `fedd409`, the original probe exited with unsigned
3221225794 (`0xc0000142`) and never emitted its fixed Rust-main marker.
Its real MSVC image statically imports USER32; this establishes pre-main DLL
initialization failure, not which DLL or access check failed. The next run
records only observational AccessCheck/MIC results for the actual restricted
token, chosen private desktop and current window station. Unknown queries remain
unknown; no ACL, token, Job or start decision changes. It also launches a tiny
headless comparison through the same three-pipe launcher before propagating the
original failure. GNU static inspection found no USER32/GDI32 imports in that
comparison; MSVC imports and real startup still need their own evidence. B's
success cannot replace A's desktop/token/handle gate, and neither proves Core
forwarding. Original source-bound evidence is in the
[SDK result record](native-tun-evidence/windows-744d10a-sdk-results.json).

At `6e71aaf` / PR `6676423`, both probes failed before Rust main with
`0xc0000142`. The actual MSVC comparison imports neither USER32 nor GDI32;
USER32 alone therefore does not explain the failure. Observational AccessCheck
reported full current-window-station access (`0xf037f`), but denied the full
private-desktop request: maximum allowed was `0x20083`. Both object labels
were Low with no-write-up, and the worker mandatory policy was 3. This identifies
a mismatch with the documented CreateProcessAsUser desktop startup contract;
it is not a captured loader access request or proof that this is the only cause.

The correction grants the verified target user `0xf01ff` only on the newly
created private Low desktop. It does not alter any existing/global desktop or
window-station ACL, token, handle list or Job UI restriction. The protected DACL,
Administrators owner, SYSTEM/Administrators grants, owner-rights limitation and
Low label are checked against the actual generated descriptor in a pure SDK
test. That test first reproduced the old `0x20083` grant and then passed the
corrected mask; six access-preflight regressions passed. Actual child startup
and resource isolation must still pass a new disposable CI run.

## Product authorization boundary

An application-path-only WFP permit is insufficient to authorize this worker.
Windows gives a process creator broad access to its newly created process,
including modification/injection rights. From those documented rights we infer
that an ordinary user could create their own instance of the same image and
change its self-checks; a trusted path and parent check alone cannot make an
AppID permit exclusive to the broker's instance. This has not been tested by
injecting into a process on the workstation. See Microsoft's
[process rights](https://learn.microsoft.com/en-us/windows/win32/procthread/process-security-and-access-rights)
and [memory-write access](https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-writeprocessmemory).

Product exemption must additionally bind an OS-managed principal an ordinary
user cannot create, such as an appropriately isolated SCM service identity,
or equivalent trusted kernel instance enforcement. A same-user SID, random
restricting SID or CLI nonce is insufficient. The generic helper's existing
Core-command entry must not receive a system egress exemption. This remains
design/integration work; the process foundation does not enable a product
capability or claim authenticated GUI/broker isolation.

## Independent loader diagnosis

At `35847e9`, both required and headless children still exited `0xc0000142`
before Rust main, despite full desktop/window-station access preflight. The
grant satisfies the SDK contract but is not a demonstrated startup repair.
[Original source-bound results](native-tun-evidence/windows-35847e9-sdk-results.json)
retain the failure. No token/Job restriction was removed.

An optional disposable diagnostic now reuses the same token, private desktop,
minimum environment, Job UI flags and six fixed inherited resources. Only that
entrypoint adds `DEBUG_ONLY_THIS_PROCESS`. Its creating thread receives and
continues bounded debug events: module basenames, original bounded debug strings,
first/second-chance exception and exit values. Only the initial first-chance
loader breakpoint is handled; other exceptions remain unhandled. SDK event file
handles close once; process/thread event handles remain SDK-owned. The diagnostic
keeps a separate process handle and drains exit events before reaping its job.

```powershell
cargo run --manifest-path core/Cargo.toml --locked --release -p swirl-platform `
  --example windows-restricted-loader-trace -- --disposable-environment `
  --probe (Resolve-Path ./core/target/release/examples/windows-headless-worker-probe.exe) `
  --directory C:/approved-fixture/fresh-loader-trace
```

This explicit command requires an authorized elevated disposable Windows host.
It records source/copied image hashes before launch, synced bounded JSONL events,
independent child stdout/stderr and a result separating collection, cleanup and
startup. Limits are 256 events, 512 KiB trace/output, 4 KiB per debug string and
a 10-second event deadline. Debugging changes scheduling; collection success or
debugged startup never replaces the original non-debugged A/B gate. No global
registry flag, external debugger, new privilege or inherited handle is added.
Four local pure/temp-log regressions, all-target Clippy and GNU linking passed;
no restricted process or debug session ran on the workstation. Actual DLL
initialization messages may still require further diagnosis after CI.
