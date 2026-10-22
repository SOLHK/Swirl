# Local subscription window and legacy Loon Trojan import

On 2026-10-18 the owner opened a new ten-minute refresh window. Acquisition
used the existing DPAPI manifest read-only and stored new encrypted responses
under D:/Codex/work/private-capture-20261018-053145. The conservative authorization
interval was 05:31:45Z to 05:41:45Z, with the existing 30-second safety margin.
Acquisition finished early; no more supplier requests are required. Old local
cache files and all original private-repository ciphertext remain unchanged.

## Capture and native import

All 18 manifest entries (17 distinct URLs) have newly acquired encrypted data.
Raw and decoded integrity checks pass; there are 15 distinct decoded bodies.
Four responses were URI subscriptions carrying an HTML MIME type. The Python
capture gate now accepts only complete plain/Base64 URI lists under that MIME;
actual HTML, mixed lines, malformed encoding and recursive Base64 remain rejected.
Original bytes and headers stay encrypted and are never treated as active config.
The initial gate rejected those four; bounded retries retained their complete
responses encrypted, then offline validation added them to the new cache index.

An actual legacy Loon Trojan export used colon-separated TLS parameters after
the password. Rust now maps these through existing canonical keys, boolean checks,
TLS validation and duplicate-parameter rejection. Positional passwords containing
colons remain passwords; unknown options are preserved and remain unexecutable.
No TLS checks, timeout budgets, proxy engine or UI behavior were relaxed.

With the new Rust inspector, 17/18 entries parse: four Clash YAML, nine INI,
four Base64. The remaining legacy SS positional-options document is preserved
but rejected as DuplicateIniParameter. Parsed records total 1468 including
repeated subscriptions, not distinct nodes. Four entries produce 90 TCP candidates
each; candidates are not network acceptance. The recovered Trojan document still
has no executable candidates under its declared unsupported safety policy.
67 unapproved resource-reference hints and two cycles from the initial capture
were not followed; complete remote-resource/full-product execution is unverified.

## Independent references and implementation

Reviewed [Mihomo Base64 handling](https://github.com/MetaCubeX/mihomo/blob/Meta/common/convert/base64.go),
[Python strict Base64 decoding](https://docs.python.org/3/library/base64.html),
[Loon official node examples](https://github.com/Loon0x00/LoonManual/blob/master/docs/cn/node.md),
and the documented historical colon notation. Swirl code was independently written;
no reference implementation code or dependency was imported.

## Local validation

- cargo fmt/check/clippy with locked dependencies: passed.
- Rust workspace: 130 passed; Release native binaries built.
- Subscription capture: 25 passed, one optional C++ importer test skipped.
- Subscription import: seven tests passed, including native Trojan authentication,
  bidirectional transfer through the independent Python TLS peer, and rejection
  of an untrusted CA/wrong hostname for the legacy Loon syntax.
- Existing independent protocol/DNS/control suites passed before the Rust parser
  change; final changed-parser import and workspace tests were rerun afterward.
  The local workflow-management symlink test skipped because this Windows account
  lacks symlink-creation privilege; it was not counted as a pass.
- Rebuilt Windows Qt integration: passed; four independent Qt protocol peers passed.
- Exact-source Linux and Windows CI passed; macOS failed twice in an unchanged DNS diagnostic test. See the final CI record below.
- Existing MinGW linker emitted its known .drectve warning; builds succeeded.

## Verified local/private result

The final private [Windows run 39101597943](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39101597943)
completed successfully with workflow commit `aa44303bd906e73d04d7b2a23bf7b59c0bdf4c69`
and exact public source `4d2b26469ee1b2da765db4d188f9cba9d52ab487`.
All 52 synthetic helper tests passed. Decryption used the original Secret only in
memory on the previously authorized existing Windows runner. No supplier URL was
refreshed by this workflow and no local private input or key was uploaded.

The 18 manifest entries contain 17 distinct URLs. Sixteen exactly match the private
archive's 16 entries; the two additional local entries are one other URL repeated.
There are 17 cached acquisition records with all 18 source IDs preserved, and 15
unique decoded bodies. The remote archive still has seven distinct bodies.
No current local body is byte-identical to a remote body. Four exact-URL pairs have
equal nonempty executable candidate parameters; this does not make full configs equal.

The immutable old window #9 nodes 1/2/3 passed Python and Rust DNS/TCP on the user's
Windows network. Each engine resolved one IPv4/no IPv6, attempted one address and
had none remaining; paired durations were 266/250/264 ms within the ten-second
budget. Subsequent native SS/HTTP-obfs strict HTTPS checks passed TLS 1.3, HTTP 200,
bidirectional accounting and orderly TLS close, with active=0 and failed=0.
These are old fixed samples, not an all-node acceptance test of the new capture.
Previous hosted-Linux TCP timeouts remain valid separate evidence; their cause is
not inferred solely from Windows success.

The fresh capture was fully persisted by 05:33:55Z (13:33:55 Asia/Shanghai).
The old C-drive cache was read-only; generated project files stayed on D:.
The previous acquisition report remains intact. Four rejected-MIME responses are
also retained independently as encrypted retry records. The final cache metadata
preserves both source IDs for the duplicated URL. Active product config, current
system proxy, routing, adapters, UI and original private ciphertext were unchanged.


The distinct-body capability inventory is saved locally in D:/Codex/outputs/subscription-window-20261018-capabilities.json. It contains 540 SS, 630 Trojan and 59 VLESS records across parsed distinct bodies, not deduplicated nodes. Diagnostic totals are 270 TCP candidates, 540 certificate-verification-disabled rejections, 270 unsupported TCP Fast Open records, 90 unmapped/invalid records and 59 REALITY-unimplemented records. One additional legacy SS positional-options body remains unparsed. Future protocol prioritization should use these actual requirements; never silently disable their declared options.

## Final CI boundary

The [core validation run](https://github.com/SOLHK/Swirl/actions/runs/39101504705)
finished successfully on the exact source SHA above. The
[three-platform run, attempt 2](https://github.com/SOLHK/Swirl/actions/runs/39101504694/attempts/2)
finished **failure**: Linux and Windows (including cloud Qt integration) succeeded,
while macOS failed `test_permanently_stalled_dns_worker_does_not_hold_process_open`.
Its unchanged diagnostic validator raised `DiagnosticOutputInvalid` at line 328.
The single-job retry reproduced the same failure. The diagnostic's timing-envelope
check rejected a permanently stalled DNS test using a 30 ms DNS budget; raw timing
values were not printed by that fixture, so the exact scheduling cause is unproven.
No timeout, test assertion, certificate check or source file was changed for the retry.
This is a remaining reproducible macOS CI failure, not a recovered transient error.

Both macOS attempts passed Rust static/unit checks and Release build but stopped
before `test_subscription_import.py`; do not claim the new Loon independent-peer
integration ran on macOS. That test did pass locally, on Linux and on Windows.
The final conclusions and job IDs are in
[evidence/RUST_CI_SUBSCRIPTION_WINDOW_20261018.json](evidence/RUST_CI_SUBSCRIPTION_WINDOW_20261018.json).
The follow-up documentation commit is not a new tested product build.

This stage adds subscription capture/import compatibility. It does not implement
VMess, SS2022, REALITY, Vision, gRPC, XHTTP, Hysteria2, TUIC or Windows TUN.
