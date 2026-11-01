# Native TUN production audit — 2026-11-01

## Release decision

**Development stage. Do not merge PR #42 into `test` or promote it to `main`
under the production acceptance criteria yet.** System-wide kill switch,
restricted-token data plane, authenticated GUI/UAC integration and physical
Windows 11 full-tunnel/fault/long-load acceptance remain blocking work. No
capability flag has been changed to imply their completion.

This is a continuation of the existing Wintun / smoltcp / shared FlowDispatcher
implementation. It adds no external proxy core, alternate rule engine or new
production package or version. Existing-package feature extensions are Tokio's
development-only virtual clock, smoltcp's raw socket for post-reassembly UDP
admission, and Windows SDK bindings for the scoped WFP transaction foundation.
Their purpose and security/maintenance boundaries are recorded in the
[dependency review](NATIVE_TUN_DEPENDENCIES.md).

## Source and remote baseline

Remote refs were fetched and PR/Actions were queried again before editing:

| Ref | Observed SHA |
| --- | --- |
| `work/native-tun-windows-20261030-isolated` | `930c3f5fc2cbcfb99de4769c44f1682f4fc2e01d` |
| `test` | `63dde8812f85839aa6024cbba6c498c96cae022d` |
| `main` | `bd4d60cf42322cf62aa49fa09f219d800c128c30` |
| Other owner's `work/native-tun-windows-20261030` | `4d2162a9eb3e64a91aea39faae82342dfffd1925` |

[PR #42](https://github.com/SOLHK/Swirl/pull/42) was open, Draft, unmerged and
conflicting. `git rev-list --left-right --count origin/test...HEAD` returned
48 test-only / 36 TUN-only commits; main comparison returned 5 / 36.
`git merge-tree --write-tree --name-only origin/test HEAD` identified one
conflicting file, `.github/workflows/build-qt-quick-ui.yml`. This was an object-only
merge preview, not a worktree merge. UI/LAN/activity changes on `test` were not
overwritten. The other Native TUN branch was not modified.

The public Actions API independently returned six completed successful latest
attempts for baseline `930c3f5`: Native TUN
[41001028590](https://github.com/SOLHK/Swirl/actions/runs/41001028590) and
[41001023735 attempt 2](https://github.com/SOLHK/Swirl/actions/runs/41001023735/attempts/2),
Rust Core [41001028595](https://github.com/SOLHK/Swirl/actions/runs/41001028595),
Native Protocols [41001023770](https://github.com/SOLHK/Swirl/actions/runs/41001023770),
Qt [41001028582](https://github.com/SOLHK/Swirl/actions/runs/41001028582), and
source guard [41001028571](https://github.com/SOLHK/Swirl/actions/runs/41001028571).
These remain **baseline-source results**, not validation of later fixes.
Historical original driver/failure logs and manifests remain under
[`native-tun-evidence/`](native-tun-evidence/); no old failure record was deleted.

## Capability matrix

"Implemented" describes source, not physical application acceptance. Controlled
packet/loopback tests, real Server Wintun, Windows 11 read-only observations and
Windows 11 full-network acceptance are separate evidence classes.

| Area | Existing implementation / defect | Current acceptance boundary |
| --- | --- | --- |
| IPv4/IPv6 TCP | Existing smoltcp state machine, bounded sockets/queues, shared Core, FIN/RST, half-close, retransmission/SYN deduplication and byte-exact transfers. A task-owned abort guard now resets cancelled/failed forwarding even after its write half has sent FIN. | Real dual-stack Core node-revocation/HTTP CONNECT and packet task-abort regressions passed locally; normal write-only FIN and 1 MiB tail draining remain intact. Historical scoped Server Wintun is separate. Public Win11 TCP/long-lived/HTTP2/WS/SSE/app acceptance not run. |
| IPv4/IPv6 UDP | Existing sessions, replies, fragments, timeouts and native outbound integration. Malformed datagrams and incomplete IPv4 first fragments previously consumed endpoint capacity. Admission now requires a complete, valid UDP packet; IPv6 zero checksums are refused. | Original checksum tests and new first-fragment/bad-reassembly/correct-first-delivery regressions passed. Reassembly remains in the same smoltcp Interface; no second assembler exists. Real full-system QUIC/TUIC/HY2 applications are not accepted. |
| Failed UDP tuple identity | Existing failed-slot tombstones prevented immediate policy fallback but expired from failure time even while packets continued arriving. Retention now follows actual idle time. | Both virtual-clock shared-Core REJECT-to-DIRECT trap regressions passed; full idle may intentionally admit a new session. This does not migrate live QUIC sessions. |
| DNS/Fake-IP | Existing UDP/TCP A/AAAA, durable dual-stack Fake-IP identity, TTL/cache and rule mapping. Non-A/AAAA support remains deliberately limited. | Controlled tests and historical scoped driver DNS; no independent physical DNS/IPv6 leakage trial. Durable reopen is not crash/reboot acceptance. |
| DNS guard | Existing port-53 physical-adapter block rules and ownership journal. Previously status equalled capture state. Added initial/effective ActiveStore audit, bounded background verification and age/unknown status; security drift retains capture and requests explicit recovery. | Production script exercised against PowerShell fault mocks; no actual firewall deletion/service-stop/packet-capture trial. Polling leaves a detection window. DoH/DoT/application DNS and bypass/IPsec policies remain boundaries. |
| Routes/egress | Existing dual-stack split defaults, physical binding, known VPN conflict preflight, network notifications and rebuild. | Rebuild still removes the old capture transaction; no system-wide zero-leak protection during that interval. Multi-NIC/handoff/sleep/public egress not accepted. |
| Kill switch | **System-wide feature not implemented.** A new explicitly scoped WFP transaction foundation is limited to one executable's reserved loopback TCP/UDP endpoints and is not called by product lifecycle code. Core socket binding and DNS guard do not block other applications' physical egress. | Formal release blocker. Pure model/SDDL checks and a separate opt-in disposable-runner enforcement command are distinct from actual system protection. Helper crash, reboot, existing flows, interface changes, DNS and explicit unlock all require full tests. |
| Privilege/IPC | Existing ordinary GUI mutation refusal, private inherited stdio, bounded commands/output, protected journal directory and PowerShell Job Objects. Worker still inherits elevated helper token. | Restricted-token packet/protocol worker, authenticated product launch/IPC, signed installed payload and unauthorized-local-process acceptance missing. |
| Recovery | Existing durable typed journal, GUID/index ownership, readback, conflict preservation, explicit recovery and supervisor child-exit handling. Added control-loop heartbeat, bounded stall termination/reaping before recovery and explicit worker-error reporting. | Real finite child-process stall/progress and original recovery-ordering tests passed. Normal scoped Server teardown passed historically. Actual driver-hang/crash restoration is unaccepted; simultaneous helper/worker failure and reboot require a surviving/restarted process and no startup recovery service exists. |
| Rules/protocols | Existing FlowDispatcher reuses MRS, policy groups and native outbounds; no independent TUN rules. Existing failure paths are fail-closed. | Historical native protocol matrix is not blanket interoperability. VMess strict half-close, TUIC empty UDP and HY2 half-close/large UDP limitations remain recorded in architecture/PR. |
| GUI/product | GUI TUN capability remains disabled in EngineController, RustCoreEngine and settings QML. | No safe GUI/UAC/worker connection or helper/driver installer integration yet. Enabling a flag would conceal missing lifecycle/security work. No unrelated visual/module files changed. |
| Performance | Existing bounded buffers and exact synthetic transfers. | No matched throughput/latency before/after data, sustained physical load, task/socket/handle leak proof or mature-client comparison. No performance improvement is claimed. |
| CI | Existing workspace/Windows/driver/native-protocol/Qt/product workflows. Native workflow lacked post-merge `test`/`main` push and tooling-path coverage. Conflicting PRs cannot rely on `pull_request` jobs. | Added native trigger coverage/evidence tests and isolated-branch push triggers for Rust Core and Qt. Native workflow Actions are pinned to the live-resolved commit SHAs; checkout does not retain credentials. New source requires its own Actions results. Server driver smoke remains explicitly scoped loopback. |

## Observed Windows 11 failure and targeted fixes

The accessible host is Windows 11 Home Insider Preview, build **29698**, Lenovo
model **83NN**, ordinary medium-integrity process. It has not been used for
privileged full-tunnel testing. A default read-only acceptance inventory recorded
12 adapters / 43 routes / 3 firewall profiles and no owned Native TUN DNS rules;
inventory counts can change with the host's network state.

The first local `cargo test --locked -p swirl-platform -p swirl-tun -p swirl-dns
--all-targets` failed in
`configuration_snapshot_reads_system_state_without_network_writes`: a real
connected CIM row had a **present null `InterfaceMetric`**. The previous required
`u32` decoder rejected the entire snapshot. The fix preserves a required-nullable
`Option<u32>`; missing/wrong-type fields still fail, null and zero remain distinct,
and PowerShell explicitly requires the property to exist. The corrected platform
suite passed its actual read-only snapshot and the null/zero/missing/type tests.
No fake zero, interface exclusion, schema skip or fallback was introduced.

The new UDP capacity/checksum tests first reproduced the defects on the original
implementation. Reporting checksum-invalid packets earlier intentionally changes
the existing roundtrip fixture's exact malformed count from 1 to 2: it injects one
truncated IP packet and one invalid-checksum UDP packet. Tuple/content/no-forward
assertions remain intact; this is additional malformed-packet accounting.

DNS guard regressions execute the unchanged production fixed PowerShell script
against child-local mocks for healthy state and eleven faults: removed rule,
stopped firewall, disabled profile, rejected local policy, exempt interface,
uncovered new hardware, degraded status, incomplete enforcement, port/protocol
change and IPv4-only scope. Three monitor tests cover failed initial audit,
independent subsequent rule loss, stale success and cancellation. These are
explicitly **not live physical DNS leakage tests**.

Raw local command logs and read-only inventories stay outside Git. The
[collector/verifier contract](NATIVE_TUN_WINDOWS_ACCEPTANCE.md) provides fresh,
source-bound baseline/resource/scoped-driver collection with original outputs,
pre-run thresholds and artifact hashes. Its validator never grants release or
physical Win11 acceptance from flags, hashes or operator declarations.

## Local validation and change identities

| Change | Commit |
| --- | --- |
| UDP integrity before endpoint admission | `9f2bb94` |
| Failed UDP identity retained through continuing traffic | `6aaeb89` |
| Effective DNS guard audit and real Windows 11 null-metric snapshot correction | `edfbbed` |
| Bound evidence tooling, CI trigger coverage and Native Action pins | `9ca8917` |

The final frozen Rust changes passed these local Windows GNU checks with Rust
1.99.1; this is not MSVC or an installed Qt product claim:

- `cargo fmt --all -- --check` — passed.
- `cargo clippy --locked --workspace --all-targets -- -D warnings` — passed.
- `cargo test --locked --workspace --all-targets` — **934 passed, 0 failed,
  0 ignored, 0 filtered; 49 target result blocks**. The source was the frozen
  working tree subsequently committed in the changes above; standalone Cargo
  identity is explicitly distinguishable from a paired product DLL.
- `cargo test --locked --workspace --doc` — **1 passed, 0 failed/ignored/filtered**
  across nine crate result blocks; separate from the all-targets count.
- `python scripts/tests/Test-NativeTunAcceptance.py` — **24 passed**.
- `actionlint` on the three touched workflows and `git diff --check` — passed.
- Four archived Windows original-log manifests were checked against Git blob
  bytes for exact SHA-256 and recorded byte length, including failed runs.

Original failing evidence is retained locally: real CIM null-metric decoding,
malformed UDP capacity / IPv6 zero-checksum admission, and both corrected-domain
UDP tombstone regressions on the old implementation. An early tombstone fixture
was invalid because built-in LAN routing takes precedence over a loopback
custom REJECT rule; its initial timeout/hang is recorded as a **fixture failure**,
not production failure proof. The corrected fixture uses Fake-IP domain identity,
an actual Core transaction and a real UDP trap. It then reproduces both policy
identity defects before the fix, without waiting 60 wall-clock seconds.

No modified test was deleted, ignored or given a larger production timeout to
obtain these results. Changes to the exact malformed counter are explained above.
No driver was installed or host route/DNS/firewall/proxy changed by these local
checks. CI and product build results must be attached separately to their exact
remote HEAD; old `930c3f5` runs cannot be reused as these changes' acceptance.

### CI continuation after the first push

The exact-source Native Protocols run
[41273855056](https://github.com/SOLHK/Swirl/actions/runs/41273855056) passed all
six jobs at `305a182`; its Windows unit command reported 935 tests including the
doctest, while Linux/macOS each reported 896. The separate Qt/Core local build at
that source passed four selected CTests (storage, loader, Rust integration and
import boundaries). Generic Qt integration reported 95 pass / 10 existing
dedicated-fixture skips. A separate real authenticated/unauthenticated SOCKS5 UDP
reference-peer Qt test passed; the other skipped fixtures are not silently counted.

Rust Core Linux/macOS CI correctly failed in the legacy development updater's
exact workflow branch-list check: the newly authorized TUN branch was not yet a
recognized current form. The correction recognizes exactly that reviewed form
and tests idempotent preservation, unknown/duplicate branch refusal and ambiguous
push-section refusal. It does not remove drift detection or the new TUN gate.

An additional portable-boundary run then found two separate issues inherited
from the existing TUN implementation: a serialized `wintun.dll` filename was
mistaken for an SDK call, and Unix file-creation mode was implemented directly
inside shared DNS. The guard now distinguishes module imports/qualified calls
from bare data names, with import/alias/raw-identifier/FFI/link regressions; it
does not exempt source files or remove actual OS-call bans. The existing Unix
0600 read/write/nontruncate journal-opening operation moves into the already-used
`swirl-platform` adapter. DNS lock, durable append, torn-tail repair and permission
semantics are preserved. Portable behavior and Unix permission tests cover this
boundary, and Native CI now executes the boundary guard explicitly.

These follow-up changes require their own affected Rust checks and exact-head CI
results; the earlier successful runs and diagnostic bundle remain identified by
their original SHA. No previous failed CI record is removed or relabelled.
Local affected checks after the adapter move passed 49 platform and 27 DNS tests;
the portable guard passed 10 tests and the updater reported 58 passed / 2 existing
Windows platform skips out of 60. A subsequent local all-workspace Clippy run
reported `missing_const_for_thread_local` in the unchanged REALITY backend,
whose initializer already contains `const { ... }`; this new lint result is
not recorded as a successful latest check. An independent tiny crate reproduced
it with the same compiler/std binary hashes: GNU with matching `rust-src` fails,
an isolated copy without optional sources passes, adding those same sources back
fails again, and checking the Linux target passes. The Windows GNU std TLS macro
emits a non-const wrapper around an already-const body;
[this version's Clippy check](https://github.com/rust-lang/rust/blob/58cf8f9c35b355199727627d07ae34a4e2846d67/src/tools/clippy/clippy_lints/src/missing_const_for_thread_local.rs#L95)
still flags that wrapper when source snippets are available. The installed
toolchain and protocol source were not altered and no lint allowance was added.
Fresh Windows MSVC Clippy passed in both Native and Rust Core jobs at `1e624b2`.

The first `1e624b2` macOS Rust Core run then failed the new missing-parent journal
test with `NotADirectory`, where `NotFound` was required. Its fixture names used
only PID and timestamp; parallel tests can observe the same macOS clock tick and
create the same pathname as a file. A per-process monotonic atomic suffix now
separates fixture ownership. The exact `NotFound`, no implicit parent creation,
nontruncate repair and Unix permission assertions remain unchanged. This is a
test-fixture collision correction, not a file-open fallback or broadened accepted
error set. Its new-source macOS result remains a required re-test.

## Kill-switch architecture constraints still to implement

The [scoped WFP foundation](NATIVE_TUN_WFP.md) now provides owned persistent
objects, explicit ACLs, atomic poisoned-on-error transactions, exact readback and
receipt-based removal for one local application's loopback endpoints. It is not
connected to `NativeSession`, cannot install host-wide rules and does not change
the kill-switch capability. Its real enforcement command runs only with explicit
disposable-network authorization and elevation; model tests are not enforcement.

### Further reproduced backend repairs

Dual-stack Core/HTTP CONNECT regressions then exposed a TCP cancellation gap:
after the upstream sent FIN, revoking the node completed the Core transaction
and removed its session, but the packet socket did not reset or release its
remaining upload side. A stream's successful write shutdown had been mistaken
for proof that its containing operation completed. A task-owned `TcpAbortGuard`
now retains the original abort/wake state across the entire TCP/DNS operation;
only overall success disarms it. Errors, node revocation, panic unwinding and
outer task cancellation can reset the flow even after local FIN.

The first attempted two-direction EOF heuristic was rejected by the unchanged
1 MiB write-only regression: normal `write_all -> shutdown -> drop` must retain
buffered tail data even if the client has not yet sent FIN. That attempt was
reverted, not committed or rescued by changing its old assertion. The final
guard preserves those stream semantics. Original dual-stack Core red tests and
the failed heuristic log are retained; the initial bare-stream Drop probe alone
was not sufficient to distinguish legitimate write-only completion from task
cancellation. The real Core cancellation reproducer supplies that distinction.
Final local checks passed two unit plus 24 packet tests and 11 Native TUN API
tests, including actual polled-task abort, empty ReadBuf, `SessionRevoked`, RST
and zero active packet-flow state.

Two new actual-packet regressions reproduced premature IPv4 UDP admission:
with endpoint capacity one, either an isolated first fragment or a complete
bad-checksum fragmented datagram prevented a subsequent valid destination from
being received. Four legitimate controls passed on the old implementation.
The fix uses the existing smoltcp Interface's post-reassembly raw receive path,
then validates UDP before allocating an endpoint. A first valid datagram is
published once; existing endpoint copies are discarded from the raw path and
continue through their original UDP sockets. There is no reinjection or second
reassembler. Both fragment orders, exact payload/tuple, empty datagrams and
ordered markers pass. The additional fixed buffer is in the memory ceiling;
the extra IPv4 UDP copy has no measured performance claim.

The helper's unbounded `child.wait()` also reproduced a live-stalled-worker
regression using a real finite child process. The control loop now emits a
private heartbeat; five minutes without progress kills and reaps the worker
before attempting the existing journal recovery. Ordinary responses remain
byte-exact and internal heartbeats never reach the client. Four new tests and
the four existing output/recovery-ordering tests pass, including real child
progress/stall behavior. A first positive fixture accidentally emitted CRLF
heartbeats through PowerShell instead of the production Rust stream's LF; that
fixture failure was preserved and corrected without broadening frame acceptance
or any deadline. Local Release CLI checks also verified both internal worker
modes return the unchanged command response and exit on EOF without OS mutation.

After these changes and the scoped WFP module were frozen, local affected
`cargo test --locked -p swirl-platform -p swirl-tun -p swirl-dns -p swirl-core
-p swirl-api --all-targets` passed **286 tests across 20 result groups**, zero
failed/ignored/filtered. A subsequent focused example test passed the added
peer-error/panic cleanup regression. TUN alone is two unit plus 21 packet tests.
Focused platform/TUN/API all-target Clippy with `--no-deps -D warnings`, workspace
formatting, portable boundary 11/11, evidence contract 24/24 and Native actionlint
passed. The scoped WFP example linked in Release. These do not replace a final
full-workspace/MSVC/product run or the previously recorded normal GNU workspace
Clippy toolchain failure. No local WFP engine or rule was used by these checks.

### Reconciliation with current product history

At `b9b190f16289954e0643867d5ea155cb2cbd3f77`, Native TUN
[41276477070](https://github.com/SOLHK/Swirl/actions/runs/41276477070)
passed 2/2 jobs and Native Protocols
[41276477051](https://github.com/SOLHK/Swirl/actions/runs/41276477051)
passed 6/6. The Wintun test received/sent 2,012/1,737 packets and restored six
owned resources with zero conflicts. Its Server/loopback scope did not change.
A separately built local Windows 11 Qt/Core pair at that source also passed
the six existing independent TUIC/Hysteria2 product-chain tests (TCP/UDP,
authentication rejection and Salamander). These exercise configuration import,
encrypted reopen and native Core forwarding, not system-wide TUN or browser
HTTP/3 acceptance.

The same source's full Qt run
[41276477118](https://github.com/SOLHK/Swirl/actions/runs/41276477118)
**failed**: critical UI 8/9, network/security 10/10, with no skipped tests in
either JUnit group. Both failing appearance assertions were Dark-mode press
responses: `reviewButton` had no changed admissible frame within 40 ms;
`reviewNavigation` reached scale 0.996403 within that window, above the original
strict 0.995 threshold. Later deadline observations were not valid frame
callbacks and did not satisfy the contract. The remaining regression and
installer were blocked. Original logs, JUnit and artifact bytes are retained;
this failure is not relabelled as passed.

The current remote `test` history (`63dde8812f85839aa6024cbba6c498c96cae022d`)
already contains monotonic input-time press sampling and paired native
render-sync transforms (`3c3778b`, `f5512cb`, `842c78d`). It is being reconciled
into the existing TUN development branch with an ordinary merge, preserving
all product changes rather than authoring another UI repair. The sole manual
conflict is the Qt workflow step header; its combined UI/network failure gate
retains `critical_ui` identity for the newer diagnostics. Both sides' test,
inventory, diagnostic, cache and evidence steps remain. Product UI sources
match `test` exactly; the existing TUN dependency-notice addition is retained.
This is not a merge into `test` or `main`, and requires fresh exact-merge-SHA CI.

Before committing the merge, the paired Qt/Rust test targets compiled and all
four selected CTests passed (storage paths, library loader, Rust/Qt integration,
import boundaries). The first invocation lacked the explicitly required
isolated storage directory and failed before import execution; after creating
that fixture the unchanged tests passed. The development updater contract
reported 58 passed / two existing Windows platform skips out of 60. No host
proxy, physical route, DNS or firewall setting was changed.

Evaluated WFP and existing Windows Firewall integration against Microsoft's
[filter arbitration](https://learn.microsoft.com/en-us/windows/win32/fwp/filter-arbitration)
and [object lifetime/transactions](https://learn.microsoft.com/en-us/windows/win32/fwp/object-management).
A blanket Windows Firewall block plus an ordinary application allow rule is not
a sufficient design. A WFP implementation must isolate its own sublayer and
exceptions while preserving other providers' security policy; indiscriminate
hard permits could bypass other firewall decisions. Dynamic session objects
disappear on process death, so they cannot provide persistent crash protection.
Persistent runtime filters and boot-time filters have distinct lifetimes.

Before enabling this feature, implement and verify owned atomic WFP policy,
exact helper/worker identity, IPv4/IPv6 and already-established/forwarded/raw-flow
coverage, tunnel/physical-interface changes, explicit LAN and essential-system
exceptions, durable enable intent, crash/reboot behavior, independent readback,
administrator-only emergency unlock, installation/uninstallation and concurrent
recovery ownership. Filters must outlive capture rebuild and unexpected helper
exit, but explicit user disable must remove only Swirl-owned protection. No
prototype policy was installed on this host or represented as a completed kill
switch.

## Unperformed acceptance and integration gates

Full system capture, real public IPv4/IPv6 TCP/UDP, independent DNS/IPv6 packet
leakage, Chrome/Edge/VS Code/Codex/GitHub, WebSocket/SSE/HTTP2/HTTP3, kill switch,
unauthorized IPC, helper/worker force-kill, Wi-Fi/Ethernet handoff, suspend/resume,
machine reboot and sustained load remain **not run**. A recoverable dedicated
Windows 11 environment and the missing implementations are prerequisites.
Passing a read-only test on a physical Windows 11 host does not change these
statuses. Neither `test` nor `main` may be merged merely because a Server
workflow or a backend build is green.
