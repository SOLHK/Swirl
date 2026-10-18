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
- Other existing independent protocol, DNS, control and capture suites are being
  checked; exact conclusions and CI identities will be appended after completion.
- The new DNS-worker diagnostic first passed independently on all three platforms.
  Full macOS CI still reproduced the unchanged timeout-validation error: observed
  DNS time 158 ms for a 30 ms budget, no TCP attempted. The isolated macOS test
  measured 38 ms. Timing observations now separate worker startup and queue wait;
  production budgets and validator tolerance are unchanged. This is not yet fixed.

Offline replay of all 18 cached entries now parses 18/18, with 1558 node records
including duplicated sources and 450 TCP candidate records. The previously
unparsed local entry 15 now yields 90 HTTP-obfs SS candidates. This is not a
claim that all nodes connect or full configuration policy/DNS/routing executes.
The raw encrypted cache and provenance are unchanged by inspection.

Actual provider probes, final CI conclusions, final hashes and remaining work will
be recorded after validation. New proxy protocols and Windows TUN are not completed
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
Local diagnostic suite: 21 passed. Final three-platform results remain pending.
