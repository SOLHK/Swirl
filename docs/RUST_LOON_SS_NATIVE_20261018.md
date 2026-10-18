# Native Loon SS export to Rust and Qt forwarding

This stage continues the existing Rust kernel on work/core-completion-20261017.
It uses only the authorized cached local capture; supplier refresh requests are zero.

## Implemented behavior

The remaining cached Loon export has 90 Shadowsocks AEAD records with seven
positional fields: type, endpoint, port, cipher, password, HTTP obfuscation mode,
and obfuscation host. Rust now maps the complete trailing pair to its existing
native SS/HTTP-obfs implementation. The modern obfs-name alias maps to obfs.
Incomplete pairs, unsupported modes, custom obfs paths, extra options and duplicate
canonical parameters remain rejected/preserved; no fields are dropped to connect.

The Qt subscription normalizer now maps the same two formats and no longer writes
extra SS positional fields over the password. Named/positional cipher/password and
obfuscation collisions fail closed. Unknown positional fields preserve the password
and retain an explicit conversion issue. Unsupported obfs-uri is retained and blocked.
This changes import/control behavior only; QML and appearance are untouched.

Independent design references: [Loon node examples](https://github.com/Loon0x00/LoonManual/blob/master/docs/cn/node.md),
[historical Loon SS conversion shape](https://github.com/KOP-XIAO/QuantumultX/blob/master/Scripts/resource-parser.js),
and [Shadowsocks AEAD](https://shadowsocks.org/doc/aead.html). Only documented behavior
and wire formats were studied; no reference code was copied or new dependency added.

## Validation boundaries

- Rust fmt/check/clippy -D warnings and workspace tests: 132 tests passed.
- Release native library/API/inspector/diagnostic built on Windows.
- Nine subscription import tests pass, including both Loon export forms over all
  three supported AEAD ciphers, fragmented encrypted responses, bidirectional
  payload, half-close and corrupted/authentication/header rejection.
- Rebuilt Qt CTest passed. The independent Python SS test now drives both Loon
  imports through NodeImporter -> RustCoreEngine -> Rust SS and HTTP obfs -> peer,
  as well as the previous explicitly configured SS case. All three sessions passed.
- Other existing independent protocol, DNS, control and capture suites passed;
  exact results and CI identities appear below.
- The new DNS-worker diagnostic first passed independently on all three platforms.
  Full macOS CI still reproduced the unchanged timeout-validation error: observed
  DNS time 158 ms for a 30 ms budget, no TCP attempted. The isolated macOS test
  measured 38 ms. Timing observations now separate worker startup and queue wait;
  production budgets and validator tolerance are unchanged. This observation preceded the test-contract correction documented below.

Offline replay of all 18 cached entries now parses 18/18, with 1558 node records
including duplicated sources and 450 TCP candidate records. The previously
unparsed local entry 15 now yields 90 HTTP-obfs SS candidates. This is not a
claim that all nodes connect or full configuration policy/DNS/routing executes.
The raw encrypted cache and provenance are unchanged by inspection.

Provider results, final CI conclusions, hashes and remaining work are recorded below. New proxy protocols and Windows TUN are not completed
by this import and forwarding stage.

## DNS lifecycle and deadline test correction

The focused real stalled-worker test passed on macOS while the same test after
full-suite execution measured DNS=158ms (budget=30ms), with no TCP. The existing
validator correctly rejected this sample. Additional instrumentation separates
thread startup from condition-wait duration; observed isolated runs had 0ms thread
startup and variable wait duration. The exact scheduler source is not established.

The process-lifecycle regression now always asserts DNS timeout, no TCP/no attempts,
unchanged raw elapsed measurements and exit inside the original three-second parent
timeout. When the real OS observation exceeds the original validation envelope,
it must produce DiagnosticOutputInvalid, rather than falsely claiming a compliant
measurement. A deterministic additional test exercises both a stalled queue and
a successful DNS answer delivered at 158ms: neither may dial; both must retain
158ms and fail the unchanged validator. This corrects the test's assumption that
an OS wakeup always falls inside a 100ms scheduling allowance. No product timeout,
TIMING_SLACK_MS, DNS implementation or validation condition is changed.

References reviewed: CPython's [condition wait implementation](https://github.com/python/cpython/blob/3.14/Python/parking_lot.c)
and [queue deadline loop](https://github.com/python/cpython/blob/3.14/Lib/queue.py).
Local diagnostic suite: 21 passed. Final three-platform results are verified below.

## Final local and provider evidence

The native product change is `4ea41397386bed2678f8af41ba110965037f421d`.
Validation source `d7e79df2f1519da97507d2d3a1a92ff869543017` adds only diagnostic
regressions/documentation; Rust/Qt product sources, production diagnostic code and
native HTTPS verifier are identical. The local Release binary hashes are in the
structured evidence. This is not a new proxy-protocol implementation.

All 18 cached entries parse; 1558 records and 450 TCP candidate records include
repeated exports. Local entry 15 contributes 90 newly usable SS/HTTP-obfs candidates.
Its first three original-order nodes passed independent Python and Rust DNS/TCP
on the user's Windows network: one IPv4/no IPv6 per engine, one attempted address,
none remaining, paired durations 328/375/266ms. Native SS HTTP-obfs/AEAD strict HTTPS
then passed TLS1.3, HTTP200, bidirectional accounting, orderly close and
active=0/failed=0 for all three. They were not substituted for the older fixed samples.

The [final private Windows run](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39104294687)
was success, with private workflow source `381f3c608e4363870e57529437650efa53ad8cfd`
and exact public source `d7e79df2f1519da97507d2d3a1a92ff869543017`.
It passed 52 private helper tests, exact 16/16 remote URL matching against 18 local
entries, and five nonempty equal executable-candidate parameter groups. No local
body is byte-identical to the remote body, so source configurations remain separate.
The immutable old #9 nodes 1/2/3 again passed both TCP engines and strict native HTTPS.
The documentation-only private follow-up is `7ac895141a29ce3aa86f6afba7a3b7a9fce972d8`.
Secrets and ciphertext are unchanged; no supplier refresh or plaintext upload occurred.

Local validation: 132 Rust tests, fmt/check/Clippy -D warnings, Release, rebuilt Qt
CTest, four independent Qt peer suites, and 208 Python tests passed after the Qt
reruns. Three explicit local skips remain: optional real Codex CLI, optional C++
DPAPI importer, and symlink creation without Windows privilege. An initial local
workflow-test subprocess decoded output using GBK; rerunning with process-local
PYTHONUTF8=1 passed without that decoding exception. No global environment was changed.
The existing MinGW .drectve linker warning remains, with successful linking.

UI/QML, active user config, system proxy, routes, firewall and adapters were untouched.
Full subscription policy/DNS/routing execution and all-node/UDP acceptance are not
implied. REALITY/Vision, VMess, SS2022, gRPC/XHTTP, Hysteria2/TUIC and Windows TUN remain
separate incomplete stages. The new protocol priority should use real cached demand,
including the 59 VLESS/REALITY records, rather than claiming those can execute.

## Exact-source final CI

All final runs completed successfully on `d7e79df2f1519da97507d2d3a1a92ff869543017`:

- [Rust Core: Linux, macOS, Windows](https://github.com/SOLHK/Swirl/actions/runs/39104085584).
- [Core implementation validation](https://github.com/SOLHK/Swirl/actions/runs/39104085583).
- [Focused DNS worker diagnostic](https://github.com/SOLHK/Swirl/actions/runs/39104085580).

Each platform passed 132 Rust tests, static gates and native Release build. Linux
and macOS each ran 174 Python cases: 170 passed and four Qt-only cases skipped.
Windows completed 209 Python passes after the four separate Qt peer reruns; two
optional cases remain skipped (real Codex CLI and the standalone C++ DPAPI importer).
Cloud Windows Qt CTest and all four Python-driven Qt peer suites passed, including
both new Loon imports in the SS peer suite. Full application packaging, GUI visual
acceptance and long-duration performance were not run in this stage.

Earlier runs 39103115921 and 39103629123 failed on the original macOS timing test;
those failures and measured 158/151ms waits remain in the structured record.
Final macOS recorded a 46ms real wait and passed the new deterministic 158ms
late-answer/no-dial/validator-rejection cases. Scheduling latency was not hidden or
reclassified as a valid budget observation; the original product checks remain intact.

[Machine-readable source, binary and test evidence](evidence/RUST_LOON_SS_20261018_VERIFIED.json)
contains exact revisions, local artifact hashes, anonymous counts and bounded network
outcomes only. The subsequent handoff commit is documentation-only and is not claimed
as a separately built or tested product revision.
