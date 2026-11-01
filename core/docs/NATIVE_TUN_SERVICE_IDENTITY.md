# Disposable service identity proof

The product cannot authorize its packet worker using an executable path alone.
The existing [process boundary](NATIVE_TUN_RESTRICTED_WORKER.md) explains that
limitation. This fixture checks the next OS identity boundary without enabling
system capture, a product service or a kill switch.

The existing scoped WFP rule can now additionally require a canonical service
SID through `ALE_USER_ID`, alongside its exact application and endpoint.
Its condition descriptor grants only that SID `FWP_ACTRL_MATCH_FILTER` (1).
It never grants SYSTEM, Administrators, Everyone or the ordinary user's SID.
The optional field is omitted when absent, preserving schema-2 receipt bytes.
When present, verification requires the fifth condition and exact descriptor
owner, protected DACL, single grant, mask and SID. A block without the identity
condition and a higher-weight soft permit with it can later test both sides.
The five-condition kernel fixture below has not yet run.

Only on an authorized elevated disposable Windows environment:

```powershell
$env:SWIRL_SOURCE_SHA = (git rev-parse HEAD).Trim()
cargo run --manifest-path core/Cargo.toml --locked --release `
  -p swirl-platform --example windows-service-identity-smoke -- `
  --disposable-services --directory C:/approved-fixture/fresh-service-test
```

The directory must be fresh and local. Before SCM mutation the fixture syncs an
exact receipt with a unique service name, copied image hash and fixed command.
It creates only that virtual-account own-process service, configures restricted
service SID and the sole ChangeNotify privilege, and checks the real SCM
configuration, protected ownership/DACL, live process image and token. It runs
an actual loopback TCP exchange. Windows AccessCheck must accept the real
service principal and refuse administrator, standard and forged-restricting-SID
tokens. Those checks are identity-descriptor tests, not WFP network enforcement
or actual unauthorized GUI/helper IPC tests.

The fixture grants the service only its own temporary payload/result access;
no network journal or product directory ACL is changed. Result data is synced
before a separate completion marker. All status/report/cleanup waits use the
predeclared 20-second bound. Exact owned stop/delete and absence readback must
succeed before final success JSON. Failure preserves diagnostics and its receipt.
Explicit recovery uses the original fixture directory:

```powershell
./core/target/release/examples/windows-service-identity-smoke.exe `
  --disposable-services --recover C:/approved-fixture/fresh-service-test
```

Recovery checks the same receipt, image and SCM configuration; it does not erase
another service or reset Windows service/firewall policy. The fixture is demand
start and supplies no boot protection. Kernel WFP identity enforcement, low
integrity Core launch, Session 0 desktop leases and the real product broker
remain separate unverified work. Its success JSON explicitly marks them false.

Local validation is 15 WFP model tests, two service-fixture pure tests, compiled
SDK paths and a no-arguments refusal. The frozen platform suite passed 82 library
tests and three example tests with zero failures/ignored tests. No service,
restricted token, desktop or WFP operation was executed on the workstation.

The first real run at `6e71aaf` / PR `6676423` failed the parent's
`OpenProcessToken` with access denied (5). It unnecessarily requested both
query and duplicate rights on the other account's live SCM token; the report
also performed a hidden duplication for AccessCheck. The service's subsequent
loopback timeout (10060) is retained as a secondary failure, not substituted
for the parent's first error.

The parent now requests only `TOKEN_QUERY` and reports GetTokenInformation
results. The real service still performs its own duplicate-based AccessCheck;
negative identity checks remain unchanged. A read-only current-token regression
failed under the original duplicate attempt with error 5 and passed after the
change; all three service example tests passed. No debug privilege or token/SCM
ACL was added. At `35847e9` / PR `255208f`, the real SCM fixture then passed:
owned configuration/ACL, live image/token, all three AccessCheck refusal cases,
loopback exchange and owned service removal. The actual service token was
non-elevated/non-admin, session zero, only change-notify privilege and integrity
RID 12288. It is not a restricted Low Core child or kernel WFP proof. The
[source-bound manifest](native-tun-evidence/windows-35847e9-sdk-results.json)
retains both that success and the still-failed restricted-process gate.

## Optional scoped kernel identity fixture

Append `--scoped-wfp` to the disposable command above. The extended fixture
uses the same copied image and exact loopback TCP endpoint, with an app-only
block (weight 100) and higher-weight soft permit (200) requiring the real
service SID as fifth condition. It persists/protects an exact WFP receipt before
adding filters, reads back the full policy, and verifies owned removal. Recovery
derives expected principal from the owned service name, not a SID asserted in
the WFP receipt; it captures this identity before deleting the service account.

Before install and after removal, three same-image socket controls must all
reach the independent listener and exchange exact labels. While installed,
administrator, standard effective token and a forged restricting-SID effective
token must each return WSAEACCES (10013), with zero accepted origin traffic.
Timeout/refusal/missing observations do not pass. Effective thread tokens remain
impersonated through socket creation/connect/IO and are queried in the raw
report. They are not separate primary-process-token or Low-child acceptance,
and these observations alone do not establish which token ALE selected.
The real SCM service must still complete its original exchange through the
same AppID under the block and identity-constrained permit.

Seven local example model/read-only tests and targeted Clippy passed. No BFE or
SCM change was made on the workstation. New real kernel enforcement remains
pending CI; its required flag/gate retains original failures. Even if it passes,
it accepts only this exact image/endpoint/SCM condition, not a system kill switch,
boot policy, product authorization or low-integrity packet Core.
