# v0.1.9 Codex proxy-chain follow-up

## Evidence and scope

The user's third failure report identifies the tested build as
`a28258e16ebd6e45e63f802b12f262f2293bf4b0`, Swirl 0.1.8 / Qt 6.11.3.
The report was exported after the engine had stopped. That final snapshot cannot
establish which proxy was active during the failure. Its earlier operation log
does establish matching, Swirl-owned Windows proxy settings at 18:22:58,
18:26:27, 18:28:52 and 18:30:58 (Asia/Shanghai, 2026-10-24).

Existing Codex desktop logs, read without starting or changing Codex, contain
`ERR_PROXY_CONNECTION_FAILED` at 18:24:19 and 18:27:07, and workspace routing
discovery failures in both startups. The exact synthetic 432 workspace message
is produced by Codex's local workspace gate before the backend fetch. It is
not evidence of a remote HTTP 432 or an invalid account. A proxy-connection
failure is evidence of a failed proxy connection; these logs do not disclose
which endpoint the failing client actually selected. They do not prove a
particular Rust protocol, TLS certificate, route or account defect.

The five node-test failures recorded by this report are all
`origin_tls / UrlTestTimeout`. They are separate probes, not five proved Codex
failures. The report's new opaque references allow later per-node correlation.

## Bounded integration change

The existing native **通过 Swirl 启动 Codex** launcher already starts a fresh
desktop with child-only `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` and a local-only
`NO_PROXY`. It now also passes Chromium's explicit `--proxy-server` and a
local-only `--proxy-bypass-list`. The desktop's Electron requests and its native
app-server therefore receive the same checked loopback endpoint at startup.

Electron documents that `--proxy-server` overrides system proxy settings for
HTTP, HTTPS and WebSocket requests:
<https://www.electronjs.org/docs/latest/api/command-line-switches#--proxy-serveraddressport>.
This design uses its documented switch; it does not patch Codex, disable HTTP/2
or TLS verification, or change global environment variables. Existing desktop
processes must still be exited by the user. The launcher never terminates them.
PAC, ambiguous proxy maps, remote proxy endpoints and unverified desktop paths
remain rejected. The PowerShell helper follows the same startup contract.

This is a controlled startup path for user retesting. It is not a claim that
normal Codex startup, workspace loading, authenticated chat or the user's node
now passes. Those tests remain assigned to the user.

## Forwarding evidence retained after disconnect

Previously the Qt adapter discarded `error` and `failure_stage` from real Rust
connection records. Stopping the engine cleared those rows, so an exported
report could contain successful system-proxy ownership and node-probe failures
without the real forwarding failures needed to investigate Codex.

The adapter now emits one redacted `ForwardingFailed` diagnostic for each failed
connection, capturing the final snapshot before stopping as well. It retains
only a session-local connection ordinal, an opaque node reference and fixed
code/stage categories. It exports no host, path, request, credentials, node name
or raw node ID. Repeated polling does not duplicate the event. Storage is capped
at 256 such events per session, with an explicit cap message. A new session
resets the dedup state because Rust connection ordinals restart.

Rust forwarding no longer flattens every I/O error into `StreamIo`. Observed
reset, aborted connection, unexpected EOF, timeout, broken pipe, invalid data,
zero-length write and permission failure retain fixed codes. These describe
what happened; they do not assign blame to the server, node or local core.

## User retest

1. Connect the known working node in Swirl and confirm system proxy ownership.
2. Save work and completely exit Codex yourself.
3. Open **通过 Swirl 启动 Codex** from the Swirl Start menu folder.
4. Try workspace loading and an ordinary chat. Live account tests remain manual.
5. If it fails, note the time, capture the Codex error and immediately export
   Swirl's diagnostic report. `ForwardingFailed` events and the Codex offline
   summary can then distinguish proxy connection, forwarding and local workspace
   discovery layers without exposing private request data.

The existing strict VMess target-half-close limitation and public-traffic
acceptance are tracked separately. No assertion is weakened or marked passed
by this launcher/diagnostic change.

## Focused local validation

- Native launcher: 37 assertions, including a real synthetic child receiving
  both Chromium arguments and the scoped environment; parent environment kept.
- PowerShell helper: 41 assertions; no real application started.
- Fixed Rust forwarding-error kinds: 1 privacy/category regression passed.
- Independent official WSS VMess server, real Core CONNECT, verified target
  HTTPS, persistent requests, 12 KiB headers and idle beyond handshake budget:
  the new regression passed in 1.576 seconds. Existing target TLS and established
  session switching regressions passed as well. The candidate workflow now runs
  these three focused tests and preserves their controlled-peer evidence.
- A real TCP reset after HTTP 200 still produces `NativeRelayFailed`, now with
  `StreamConnectionReset / stream_io`; that strict negative test passed.
- Qt's actual Rust-backed failure/redaction/dedup/final-stop/new-session test
  passed (1 method plus initialization and cleanup, 0 failures, 0 skips).
- Actionlint, Rustfmt and diff whitespace checks passed.

These are local modified-source checks. The delivered package must additionally
use the final committed SHA and its successful CI/package identity checks.
