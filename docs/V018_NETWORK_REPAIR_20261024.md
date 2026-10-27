# Swirl 0.1.8 network repair: first candidate

This independent branch starts at fetched upstream
`fad05a72070b5770708cf64af57936bc9f0e64a1`. The two supplied diagnostic bundles
identify that same source and Qt 6.11.3. The nine supplied screenshots are user
acceptance evidence: V2 import and some VMess browser traffic already work.
They are not proof of all-node, Codex-account or TUN acceptance.

## Existing work reused

S4 and v0.1.7/0.1.8 already provide the portable Rust proxy, subscription
inspection/import ABI, DPAPI transactional ownership, isolated outbound HEAD
measurement, system-proxy ownership/recovery, in-process engine control,
Codex child-process launcher and production package integrity checks. This
stage keeps these implementations and the existing UI geometry and motion.

## P0: Codex evidence and operational repair path

Read-only inspection of the existing desktop log at the screenshot times found
two distinct failures. Electron reports `ERR_PROXY_CONNECTION_FAILED`; the
app-server reports `account/read` / `workspace routing discovery failed`.
Subsequent `/settings/user` and `/accounts/check/{version}` calls report
`432` / `Workspace routing is unavailable`.

The installed desktop implementation wraps a `getBackendRequestAuth` failure
with that exact 432 message **before** executing its fetch. This instance of
432 is therefore a local workspace gate, not a returned OpenAI HTTP status.
Discovery failure can still result from networking or account state. These
logs do not establish which component originally caused discovery to fail,
or prove a Rust CONNECT/TLS defect. No TLS, global Windows security policy or
account state is changed to mask this error.

The report snapshots say WinINET and registry manual proxy are enabled,
owned by Swirl and consistent. That confirms the stores at collection time;
it does not prove every already-running process read them. Current-machine
inspection instead sees the user's existing Clash proxy; this later state
must not be substituted for the screenshot state. WinHTTP direct and empty
collector proxy environment are separately observed stores, not proof that
Chromium or the Rust app-server necessarily ignores system proxy.

Use the already-shipped Start Menu entry **通过 Swirl 启动 Codex** after the user
fully exits Codex and connects Swirl with system proxy enabled. It validates
the current explicit loopback proxy/listener, then supplies proxy environment
only to the new child and its descendants. It refuses to kill/reuse an existing
desktop process and does not change persistent Windows proxy/environment.
This is a concrete diagnostic/configuration path, not a claimed Codex fix.

`Collect-CodexNetworkEvidence.ps1` now adds a bounded offline category summary
through `CodexLogSummary.psm1`. It exports fixed categories/allowlisted route
patterns, counts and timestamps, never arbitrary log text, URLs, account
identifiers, tokens, browser storage or authentication files. Its collector
environment is explicitly not the environment of an already-running Codex.

## P1/P2: TFO, security diagnostics and truthful node states

The supplied bundles contain distinct TCP connection, timeout, target TLS,
WebSocket handshake and configuration failures. Report 2 contains repeated
tests from several sources: 11 `TcpFastOpenNotImplemented`, 9 upstream connect
failures, 1 upstream timeout, 5 target-TLS probe timeouts, 1 TLS handshake
failure, 2 WebSocket upgrade timeouts, 1 WebSocket upgrade read error and
4 Qt conversion-issue rejections. These are event counts, not 34 unique nodes
or an assignment of the 15 V2 failures. Older reports have no per-node reference,
so those 15 cannot be individually attributed from these bundles alone.

- Optional boolean TFO on known TCP node families now selects the identical
  ordinary-TCP candidate. Original input/parameters remain intact and the
  capability/import API explicitly warns `TcpFastOpenFallbackToTcp`. QUIC,
  malformed types, unknown fields and other unsupported requirements retain
  strict rejection. No authentication, TLS, WebSocket or UDP semantics change.
- Trojan security refusals identify fixed offending schema fields or local-file
  suffix classes without echoing private source values. `skip-cert-verify=true`
  stays rejected; malformed boolean representations are also rejected. The old
  generic report does not identify which field caused its Trojan rejection.
- A node's measurement success is separate from its selected live session.
  List/detail connection state comes from one controller path. Detail text
  separately identifies import, executability, measurement and current-session
  request verification. A successful test never sets a connected session.
- New reports preserve a stable opaque node reference plus protocol, execution
  eligibility, connection/request state, measurement phase/code, HTTP status,
  timestamps and actual outbound/TLS durations. They exclude node names,
  addresses, IDs, credentials and source configuration. The same reference is
  visible in node details and failure events, allowing each failure to be traced.

## Validation boundaries

Focused synthetic Rust inspection/API and Qt controlled-peer regressions cover
ordinary-TCP equivalence, retained original input, strict negative TLS/options,
actual outbounds, state consistency and private diagnostic export. Exact test
results and installer identity belong to the delivered candidate's CI artifact;
compilation and listening ports alone are not network acceptance.

The original strict public TLS orderly-close and VMess half-close failures
remain separately recorded. This stage does not lower or reclassify them.
Both bundles also include an append-only historical `0xc0000005` crash file
without a per-crash timestamp/stack. Their state snapshots show a live engine;
they do not establish when or why those historical crashes occurred. No crash
fix is claimed from that limited evidence.

Browser Google/YouTube, actual Codex services/workspace/login/chat, private
provider measurements, system-proxy/TUN comparison and DPI visual acceptance
are assigned to the user by the latest instruction. The existing Rust product
rejects unsupported TUN/gateway activation; a visible control is not proof of
a functioning tunnel. Do not request a TUN comparison as though this candidate
implemented it. Full foreign-profile support is limited to actually mapped
semantics; Swirl native-format development follows compatibility/network
stability rather than preceding it.

Build changes and actual prior timings are documented in
`V018_BUILD_EFFICIENCY_20261024.md`; after timings must come from real evidence.

Primary references: [Surge common policy parameters](https://manual.nssurge.com/policies/parameters.html)
(optional boolean TFO), [Microsoft per-connection proxy options](https://learn.microsoft.com/windows/win32/api/wininet/ns-wininet-internet_per_conn_optionw),
[Electron proxy resolution](https://www.electronjs.org/docs/latest/api/session#sesresolveproxyurl),
and [official OpenAI troubleshooting](https://learn.chatgpt.com/docs/reference/troubleshooting).
The installed implementation and timestamped logs supply the specific local
432 finding; general documentation is not evidence for that app version's
internal workspace behavior.
