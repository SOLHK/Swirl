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

The command selects an unused sublayer weight while holding its exclusive BFE
write transaction, then writes/syncs the schema-2 receipt before installation.
The transaction binds that complete receipt and refuses any later change.
Installation and all subsequent verification/removal compare the exact recorded
weight; they do not accept arbitrary BFE adjustments. The command verifies transaction
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

Local Windows GNU checks passed nine model/SDDL/diagnostic tests, the peer-error join test,
Clippy with `-D warnings`, and actual Release linking. The accessible ordinary
Windows 11 process also confirmed missing opt-in and insufficient-elevation
preflights refuse execution before receipt/engine creation. No actual WFP rule
has been installed on that workstation. Real BFE readback, enforcement and
persistence require the explicit CI command; pending runs are not passes.

The first real Server run at development `ef74bc0`, actual PR checkout
`b7986bb`, **failed** with `scoped WFP ownership or policy differs` (exit 1).
Its Wintun step had passed, but the Native workflow as a whole did not. The
original full job log, WFP log, exact receipt and failure ZIP are retained.
That message alone does not identify an ACL, provider or filter difference;
no specific SDK cause is inferred from it. The follow-up diagnostic patch
retains every acceptance comparison, ACL/flags and error kind, adding fixed SDK
operation/code and privacy-preserving field/condition differences. It does not
print paths, application IDs, receipt contents, endpoint values or private SIDs.
Fresh real-run evidence is still required before any enforcement success claim.

The next real run at `d1bdea0`, actual PR checkout `c46e3ba`, failed specifically
at provider/sublayer verification: expected weight 256, actual 258. Provider
and sublayer flags, receipt metadata and provider link matched; preceding ACL
checks passed. Installation returned before commit and its transaction guard
attempts abort; the original log has no independent post-failure absence readback.
Original [log](native-tun-evidence/windows-wfp-d1bdea0.log) and
[receipt](native-tun-evidence/windows-wfp-d1bdea0-receipt.json) remain unchanged.
Microsoft's [provider installation example](https://learn.microsoft.com/en-us/windows/win32/fwp/installing-a-provider)
explicitly lets BFE assign the closest available sublayer weight. Assuming a
requested occupied weight would be returned unchanged was an incorrect API
contract. Preparation now enumerates occupied weights under the same write
transaction, selects a free value and persists it before any installation.
SDK errors, exhaustion, unexpected readback or receipt mutation still fail
closed. Legacy schema-1 receipts are explicitly refused rather than adopted
without a recorded weight. Thirteen model/SDDL/diagnostic tests and the scoped
example's cleanup regression passed locally; fresh BFE execution is pending.

At `88e9fdf` / PR checkout `6d81b38`, the real BFE test passed sublayer
verification and reached filter 0. Its actual flags were `0x41`, expected `0x1`;
all four displayed conditions, action, weight, keys and metadata matched.
The [original log](native-tun-evidence/windows-wfp-88e9fdf.log) is retained.
The [FWPM_FILTER0 SDK contract](https://learn.microsoft.com/en-us/windows/win32/api/fwpmtypes/ns-fwpmtypes-fwpm_filter0)
defines `INDEXED` as classification lookup indexing, supported since Windows 8.
Filters now explicitly request `PERSISTENT | INDEXED`; the verifier still
requires exact flags. Fourteen local WFP tests passed, including both families,
protocols and actions rejecting missing flags or extra DISABLED,
CLEAR_ACTION_RIGHT and unknown bits. This is not evidence of real enforcement
recovery until the next exact-source BFE test completes.

That next real test at `744d10a` / PR checkout `fedd409` **passed**: all four
IPv4/IPv6 TCP/UDP scoped blocks, staged-error rollback, foreign-owner refusal,
engine reopen, other application/control isolation and exact owned removal.
The [original success log](native-tun-evidence/windows-wfp-744d10a-passed.log),
[receipt](native-tun-evidence/windows-wfp-744d10a-receipt.json) and
[source/result manifest](native-tun-evidence/windows-744d10a-sdk-results.json)
are retained. The overall Native job still failed its independent restricted
child probe. Existing-flow echo observations were false in both families but
remain observations, not a revocation guarantee. Boot, system kill switch and
physical Windows 11 acceptance stayed explicitly false.

An optional service-SID condition now further narrows an individual scoped rule
to `ALE_APP_ID AND ALE_USER_ID`; absent SID preserves schema-2 metadata. The
[service identity fixture](NATIVE_TUN_SERVICE_IDENTITY.md) first validates real
SCM principals and OS AccessCheck. Fifteen local WFP models passed, but actual
five-condition BFE enforcement has not executed and is not inferred from the
four-condition success above.

Before this can become a product kill switch, system-scope policy, tunnel and
physical interface changes, existing inbound-origin/raw/forwarded flows, LAN and
essential-system exceptions, helper/worker failures, boot/reboot behavior,
durable enable intent, authenticated control and administrator emergency unlock
still need implementation and independent physical acceptance. See the
[production matrix](NATIVE_TUN_PRODUCTION_AUDIT_20261101.md).
