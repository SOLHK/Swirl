# X1.4-A8: preserve Hysteria2 authentication responses after normal STOP_SENDING

## Separate defect found during final interoperability checks

The stack-dispatch correction at
`5d6b9e370ae29add8ed11d8c8ebf9e54c2ea2611` passed all six jobs in
[run 39804698115](https://github.com/SOLHK/Swirl/actions/runs/39804698115).
The Windows log contains all original 17 Hysteria2 methods, each successful.
Linux additionally ran those same 17 methods with a measured 1 MiB main stack.
The job receipts are retained in
[ci-stack-fix-39804698115.json](evidence/x14-a8/ci-stack-fix-39804698115.json).

A separate local full-suite run exposed an intermittent authentication error:
the wrong-password case and an imported valid-credential case could return
`Hysteria2AuthenticationWrite`. This was not a stack overflow. A subsequent
120-connection diagnostic run did not reproduce it; that passing run was not
used to dismiss the observed failures.

## Cause and narrowly scoped correction

The pinned Hysteria2 server authenticates the HTTP/3 request headers, returns
233 or a rejection response, and does not need a request body. Its pinned
quic-go server flushes the response, calls `CancelRead(H3_NO_ERROR)`, then
closes the response direction. The client can receive this legitimate
`STOP_SENDING(0x100)` while `h3` writes its final GREASE frame in `finish()`.

Previously every `finish()` error ended authentication before reading the
response. The correction accepts only the exact error variant
`StreamError::RemoteTerminate { code: H3_NO_ERROR, .. }` from `finish()`.
The request write, all other finish errors, connection errors, authentication
deadline, response read, 233 status, UDP header and congestion header checks
remain strict. A normal stop merely permits reading the authentication result.
It cannot authorize a session or convert a 404 into success.

`StreamError::is_h3_no_error()` is deliberately not used: in h3 0.0.8 it does
not cover this remote-stream variant and also includes connection-level cases.
Sending FIN is not moved after the response; no retry, timeout extension,
production sleep, logging hook, extra task or allocation is introduced.

Primary sources checked:

- [RFC 9114 section 4.1](https://www.rfc-editor.org/rfc/rfc9114.html#section-4.1),
  permitting an early complete response and a normal stop of the request
  direction while requiring the client to preserve that response.
- [Hysteria app/v2.13.0 handler](https://github.com/HyNetworks/hysteria/blob/app/v2.13.0/core/server/server.go).
- [Pinned quic-go server cleanup](https://github.com/HyNetworks/quic-go/blob/a10df75c260cee8161f3261d63a37bd125a6bb2a/http3/server_conn.go).
- Locked h3 0.0.8 `connection.rs::RequestStream::finish` and
  `connection_error_creators.rs::handle_quic_stream_error` in `core/Cargo.lock`.

## Real official-peer before/after experiment

The server was the unchanged pinned Hysteria v2.13.0 executable, SHA256
`907ba8c9693edb104b20582681fb7dc15639d5b64a9cbb616a7b539190a86691`.
Disposable synthetic credentials and an independent TCP echo target were used.
Four clients ran concurrently, alternating correct and incorrect passwords;
successful sessions exchanged 65,536 bytes. Incorrect credentials had to return
exactly `Hysteria2AuthenticationRejected` with a failing process exit code.

To make the already observed race deterministic, a temporary diagnostic build
yielded for 20 ms between sending request headers and calling `finish()`.
The same scheduling change was used before and after the correction. It is
absent from committed production code and is not an increased test timeout.

| Executable condition | Attempts | Correct outcome | Observation |
| --- | ---: | ---: | --- |
| Original finish handling, diagnostic scheduling | 12 | 0 | All 12 actually returned `RemoteTerminate { code: H3_NO_ERROR }`; both credential classes were misreported as write errors |
| Exact normal-stop handling, same scheduling | 12 | 12 | 6 authenticated 64 KiB echoes, 6 explicit authentication rejections |
| Final production build, no diagnostic delay or logging | 120 | 120 | 60 authenticated echoes, 60 explicit rejections |

Executable identities and per-attempt results for the deterministic comparison
are in [auth-delayed-before.json](evidence/x14-a8/auth-delayed-before.json) and
[auth-delayed-after.json](evidence/x14-a8/auth-delayed-after.json).
These diagnostic receipts are distinct from the final production test results.

The permanent Rust regression uses actual local Quinn/HTTP3 connections and
real STOP_SENDING errors. It covers successful and rejected responses after a
normal stop, and requires a non-normal stop to retain the write failure. The
original 17 official-peer tests remain the independent interoperability gate.
The final accepted source SHA and three-platform completion record are recorded
in the separate A8 protocol acceptance report after those jobs finish.

## Verified local gate for the authentication correction

`cargo fmt --all -- --check`, `cargo check --workspace --locked`,
`cargo clippy --workspace --all-targets --locked -- -D warnings`, and
`cargo test --workspace --locked` all passed with Rust 1.99.1. The populated
cache allowed the additional `--offline` flag on the latter three commands.
Workspace tests reported **644 passed, 0 failed, 0 ignored**, including the
four new QUIC/H3 regressions and the existing doctest. The workspace libraries,
executables and examples were rebuilt successfully as well.

| Final production official-peer invocation | Executed / passed |
| --- | ---: |
| `python tools/tests/run_hysteria2_official.py` | 17 / 17, zero skips |
| Same command with `HY2_CONSTRAINED_STACK=1` | 17 / 17, measured 1,048,576-byte main stack, zero skips |
| `python -m unittest -v test_hysteria2_lifecycle` | 1 / 1 |
| Same lifecycle command with `HY2_CONSTRAINED_STACK=1` | 1 / 1 |
| `python -m unittest -v test_tuic_reference` | 9 / 9 |
| `python -m unittest -v test_quic_core` | 6 / 6 |
| `python tools/tests/test_quic_ffi.py` | 6 / 6 |
| `python -m unittest -v test_native_timing` | 3 / 3 |

The production executable hash is identical before and after the final formatting
and complete workspace gate. Source hashes, initial unmodified-suite race failures,
local command receipts and lifecycle counters are retained in
[auth-finish-regression.json](evidence/x14-a8/auth-finish-regression.json).
The complete final 17-method records are retained for
[default stack](evidence/x14-a8/hy2-auth-fixed-default.json) and
[1 MiB stack](evidence/x14-a8/hy2-auth-fixed-small-stack.json).
