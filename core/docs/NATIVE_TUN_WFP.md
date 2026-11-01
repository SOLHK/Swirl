# Scoped Windows Filtering Platform foundation

This is an implemented prerequisite for the Native TUN kill switch, **not the
system-wide feature**. Product lifecycle code does not call it and the GUI TUN
capability remains disabled. It uses the existing Windows platform adapter and
Windows SDK; no proxy core or alternate rule engine is introduced.

## Ownership and transaction contract

`swirl_platform::windows_wfp` accepts one local drive-absolute executable and
1–16 explicit loopback TCP/UDP endpoints. UNC/device paths, unspecified/public
addresses, zero ports and an empty owner identity are refused before WFP calls.
This deliberately bounded API cannot install a host-wide policy.

A fixed private provider/sublayer and owner-derived filter GUIDs identify the
objects. Each stores the exact versioned policy receipt. Installation uses an
explicit BFE transaction; any failed operation poisons it, so committing a partial
policy is refused and Drop aborts the transaction. Existing objects are never
adopted or overwritten. Removal verifies the complete policy, application ID,
conditions, action, flags, weight, owner and security descriptor before deleting
anything in the same transaction. A foreign child or ownership conflict aborts
removal instead of deleting unrelated objects. Repeated removal of an entirely
absent policy is idempotent; a partially absent policy is a conflict.

All objects use an explicit Administrators owner, protected DACL, Administrators
and SYSTEM WFP rights, and OWNER RIGHTS read-control only. The implementation
reads back the real BFE owner/DACL and compares the expected shape. This is
separate from authenticating a future GUI/helper channel. Ordinary local parsing
tests cannot prove BFE authorization or unauthorized-process refusal.

The engine session is non-dynamic and filters are persistent. Closing an engine
must not unlock them. Soft permits never set `CLEAR_ACTION_RIGHT`; they remain
overridable by other providers' blocks. No boot-time policy, startup service,
system capture, physical DNS protection or full existing-flow guarantee is
supplied by this module. ALE policy-change reauthorization occurs on subsequent
traffic; commit is not a claim that every old packet was synchronously revoked.

## Explicit disposable-runner enforcement command

Only execute the following on an authorized recoverable disposable elevated
Windows machine. The command affects its own executable and reserved loopback
ports; it does not alter physical DNS, default routes or other applications.
Use a fresh absolute receipt path outside Git. Compilation and normal tests do
not open WFP or install a policy.

```powershell
$env:SWIRL_SOURCE_SHA = (git rev-parse HEAD).Trim()
cargo build --manifest-path core/Cargo.toml --locked --release `
  -p swirl-platform --example windows-wfp-scoped-smoke
./core/target/release/examples/windows-wfp-scoped-smoke.exe `
  --disposable-network --receipt C:/approved-fixture/wfp-receipt.json
```

The command writes/syncs its receipt before installation, verifies transaction
rollback after an actual duplicate-object error, and exercises IPv4/IPv6 TCP/UDP
allow → block → engine close/reopen → owned removal → allow. It also checks an
unaffected port set, another executable's application ID and a refused foreign
owner. Existing TCP/UDP behavior after commit is recorded as observed booleans,
not automatically accepted. Exact WFP cleanup and restoration probes precede
joining all fixture threads; cleanup errors or a peer error/panic prevent the
success JSON. The final source SHA and explicit scope flags are checked by CI.

On failure preserve the original log and receipt. Explicit owned recovery is:

```powershell
./core/target/release/examples/windows-wfp-scoped-smoke.exe `
  --disposable-network --recover --receipt C:/approved-fixture/wfp-receipt.json
```

This rechecks every owned object and its ACL; it is not a blanket firewall reset.
It will not erase conflicting or foreign policy. Do not delete the receipt or
manually widen the rules to obtain a successful test.

## Evidence boundary

Local Windows GNU checks passed five model/SDDL tests, the peer-error join test,
Clippy with `-D warnings`, and actual Release linking. The accessible ordinary
Windows 11 process also confirmed missing opt-in and insufficient-elevation
preflights refuse execution before receipt/engine creation. No actual WFP rule
has been installed on that workstation. Real BFE readback, enforcement and
persistence require the explicit CI command; pending runs are not passes.

Before this can become a product kill switch, system-scope policy, tunnel and
physical interface changes, existing inbound-origin/raw/forwarded flows, LAN and
essential-system exceptions, helper/worker failures, boot/reboot behavior,
durable enable intent, authenticated control and administrator emergency unlock
still need implementation and independent physical acceptance. See the
[production matrix](NATIVE_TUN_PRODUCTION_AUDIT_20261101.md).
