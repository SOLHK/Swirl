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

Exactly three anonymous stdio pipe ends are inherited through the explicit
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
