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
- Rebuilt Windows Qt integration: passed; four independent Qt protocol peers passed.
- Exact-source three-platform CI: pending final record.
- Existing MinGW linker emitted its known .drectve warning; builds succeeded.

Private dual-source comparison and immutable fixed SS diagnostics will run with
the unchanged original GitHub Secret injected only into the existing authorized
Windows runner. No local plaintext/key is exported or uploaded. Final run identities
and conclusions will be recorded after completion, not inferred from dispatch.

This stage adds subscription capture/import compatibility. It does not implement
VMess, SS2022, REALITY, Vision, gRPC, XHTTP, Hysteria2, TUIC or Windows TUN.
