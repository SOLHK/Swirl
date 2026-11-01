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
This five-condition kernel enforcement has not yet run.

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
