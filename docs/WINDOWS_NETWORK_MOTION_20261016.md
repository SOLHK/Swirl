# Windows network, motion and composition repair — acceptance record

Base: `ea047b7` (`main`, fetched again during this work). Qt 6.10.3, MinGW
13.1, Release, Windows 11, D3D11. This is an implementation and evidence
record, **not a declaration that Codex desktop authentication is fixed**.

## Causes and changes

| Area | Observed cause | Implementation |
| --- | --- | --- |
| Route white frame | `2*p-1` and `1-2*p` made both page trees transparent at the midpoint; a third route discarded an existing visible tree. | `SwirlPageHost.qml` snapshots all live opacities, cross-fades continuously, retains outgoing trees until completion and gives input only to the target. Cold main pages incubate while the previous page stays visible. |
| Interrupted shared motion | Geometry and content reveal had different restart semantics. | Node reversal/reopen retain both the current rectangle and reveal amount. Page geometry retargeting preserves opacities. Per-host registry ownership avoids one window clearing another window's busy state. |
| Settings | `animateRoutes:false` suppressed internal transitions. | Internal transitions restored. Native flight retains synchronous destination preparation so content and the unsaved-draft fingerprint become ready together. |
| Node clipping | Four fixed minima exceeded the list viewport; shared flight considered only Y visibility. Settled detail remained parented outside its ScrollView. | Responsive column minima, aligned header/body calculations, persistent overflow scrollbar, existing elision/tooltips retained; source rectangle intersects both axes and all clipping ancestors. Settled details return to scroll ownership. |
| Proxy navigation button | Quiet styling lacked a normal-state border. | Existing `SwirlButton` normal styling, hover/press/focus and dismissal/navigation retained. |
| Window corners | Integer HRGN masks cannot represent fractional edge coverage. | `WindowEdge` draws four small destination-out GPU quads at the final window corners. No full-window texture or glyph resampling. Accelerated exact windows no longer use an integer visual clip; software retains an explicitly limited binary fallback. Native-flight region reconstruction is avoided on GPU. |
| Background became opaque | Exact-radius branch disabled DWM Acrylic and forced shell alpha to 1. | Exact GPU contours now support restrained live alpha (light 0.92, dark 0.94) while retaining opaque content cards. Native Acrylic and alpha translucency are separate capability states. Windows/user transparency, high contrast, battery saver and renderer restrictions remain respected. |
| Card curvature | Activity connection card used a nested-card token beside primary cards. | It now uses the same primary-card radius token. The window token remains exactly `10*96/72` DIP, independent of content zoom. |
| GUI work | Profiler found synchronous interface enumeration inside even hidden overview/gateway bindings, with a roughly 9 ms individual binding sample. | One asynchronous interface snapshot in `EngineController`, shared by the overview, system network description and gateway selector. UI getters read cached values; gateway activation still performs its existing current safety checks. |
| Proxy latency missing | There was no independent sample for `latencies.proxy`; route-string equality also failed to distinguish A→B→A generations. | `ProxyLatencyProbe` performs bounded TCP/CONNECT/TLS/HTTP work through the running loopback entry and correlates source port, loopback address, host and raw node chain with real engine telemetry. Route mismatch/unverified, timeout, TLS, entry and HTTP failures remain distinct. Monotonic generations isolate obsolete replies. |

## Composition limits

Exact 10pt + the system's full-HWND Acrylic brush is not claimed to be solved.
The chosen exact contour uses **live alpha translucency, not Acrylic blur**.
The existing native Acrylic branch remains for windows using supported system
contours. Software rendering still has a binary region fallback and is not
represented as antialiased GPU output. No wallpaper substitution, desktop
capture loop, additional rendering process, or whole-window text texture was
introduced.

The real-desktop red/blue fixture measured a shell color delta of 31 with alpha
enabled, and no meaningful background-dependent change with transparency off.
The 65-check window behavior suite passed with this path. This tests actual
desktop composition as well as native-resolution alpha readback.

## Network evidence and boundaries

- Current WinINET explicit proxy: `127.0.0.1:7897`; WinHTTP reported direct.
  The collector's process/user/machine proxy variables and certificate override
  variables were unset. This does **not** inspect inherited environment blocks
  inside the already-running Codex processes.
- `Start-CodexWithSystemProxy.ps1`: 39 regression assertions passed. Its
  check-only mode correctly identified the current explicit proxy and refused
  a new desktop launch while existing Codex desktop processes were present.
- Unauthenticated probes through 7897 completed CONNECT and validated TLS,
  then received HTTP responses. 403/404/421 are not OAuth or streaming success.
  The inactive 7898 listener refused TCP at that observation time.
- A separate test GUI used an encrypted node-store copy, port 17988, no copied
  network-ownership settings and no system-proxy takeover. The original node
  store's SHA-256 was unchanged after the test; the test instance stopped
  normally. No credential contents were printed or exported.
- One real selected-node sample returned HTTP 204 in **5368 ms**, with source
  port/node-chain confirmation. The independent internet request was 2546 ms,
  DNS 5 ms and gateway ICMP 1 ms, demonstrating these are separate measures.
  Another independent node test failed. Several OpenAI hosts completed CONNECT
  but timed out during TLS on that same test exit; `ws.chatgpt.com` returned an
  HTTP response. This is evidence of remaining reachability problems, not a
  successful desktop-login acceptance.
- The earlier real Codex proxy A/B observations in `NETWORK_RELIABILITY_6A.md`
  remain historical evidence. This run did not repeat them or relabel them as
  new results. It did not stop the user's active Codex session, exchange an
  authorization code, inspect saved tokens, or disable TLS verification.

## Automated and visual evidence collected

- Telemetry: 17 passed, 0 failed. Includes real TLS through native and pinned
  Mihomo entries, selected-chain mismatch, rejection of an untrusted fixture
  certificate, closed listener, and A→B→A stale-reply isolation.
- Network CTest: five groups passed (`node-real-chain`, `stream-regression`,
  `native-engine`, `engine-contract`, `engine-real`), 190.04 seconds for the
  recorded run. Existing explicit online-subscription skips remain skips.
- Node UI: actual Windows input, 180 local fixture nodes, all columns at the
  minimum window, clipping intersection and final-row selection; native and
  compatibility network fixtures never use a user's production configuration.
- UI quality: real desktop fixtures, font/native-rendering audit and the
  visible proxy navigation button. One recorded run passed 181 checks.
- GPU motion: recorded final unprofiled sample has 359 frame intervals,
  p50/p95/p99 **4.10/5.80/19.73 ms**, zero intervals above 50 ms, 7 above the
  60 Hz budget and 11 above the 120 Hz budget. Warm p95 was 4.84 ms. Physical
  display was 240 Hz; these are budget comparisons, **not actual 60/120 Hz
  display-mode acceptance**. Retained-page revisit growth was 86,016 bytes.
- QML Profiler trace was captured separately; its overhead is excluded from
  the unprofiled numbers. Inclusive event durations overlap and must not be
  summed as elapsed CPU time. The initial trace exposed interface-enumeration
  bindings and cold route creation, prompting the changes above.
- A Windows firewall prompt triggered by an integration-test executable
  invalidated one DPI capture batch. Those captures are rejected as acceptance
  evidence. The user manually chose Allow; the agent did not change firewall
  rules. Unobstructed reruns and their exit codes must be used instead.

## Remaining release gates

Final unobstructed local reruns: all four process-scale corner runs passed
(100/125/150/200%), node UI passed 134 checks, and the final hero run passed
246 checks including matching translucent flight/native-window handoff.
The post-optimization profiler sample reduced the overview address binding
from 13 calls / 93.527 ms inclusive to 1 / 0.011 ms, and the gateway interface
binding from 13 / 48.095 ms to 1 / 0.037 ms. These compare two intermediate
builds in this run, not a controlled original-main benchmark. Cold settings
first-frame latency reached 133.95 ms in one run; cached rounds were
11.43–15.21 ms. This limitation is retained rather than hidden by the average.

Repository policy requires `fix -> test`, then an explicitly approved
`test -> main` promotion. PR #17 targets `test`; the initial direct-main draft
correctly failed the production guard and was retargeted, without changing the
guard or adding a release-approval label.

1. Complete desktop Codex restart with the intended proxy environment and real
   OAuth login, without interrupting the current working chat.
2. Real long-lived Responses, remote-control WebSocket, commercial-node switch
   continuity, and the remaining TUN/UAC cases. Controlled loopback tests do not
   establish these outcomes.
3. Physical cross-monitor DPI moves and actual 60/120 Hz display-mode testing;
   per-process 100/125/150/200% scale tests do not replace them.
4. Review final CI and the latest unobstructed visual reports before promotion.

The branch must not be represented as fully accepted or merged solely because
compilation and controlled tests pass. The current user task conditions merging
to `main` on completed acceptance; unresolved gates keep it in review.

## Follow-up: More-card frame continuity and sidebar blur

The user observed start/middle/end flashes despite earlier geometry checks.
An intermediate endpoint-snapshot handoff also crashed during frame readback;
that build and its incomplete capture batch are rejected. The implementation
now uses ONE native settings window for entry, live details and return. The
page never reparents to another window, and no endpoint screenshot is used.
The same inner surface animates within a fixed source/destination union;
at the endpoint the native bounds settle to the detail rectangle. The source
card stays painted while the first native frame prepares. Native window-state
operations settle synchronously. Existing expand/reverse animations remain.

The extra rounded workspace background and sidebar gutter were removed after
the user identified the unwanted two-panel appearance. Tint now transitions
continuously from the frosted sidebar to the workspace within one shell.
The sidebar now uses a separate non-activating, input-transparent compositor
blur surface inside the shell contour. DWM Desktop Acrylic on an inactive
helper became opaque in the actual desktop test, so the optional compositor
accent blur policy is resolved dynamically. This undocumented Windows policy
is capability-dependent; failure retains the explicit alpha fallback. This is
not an implementation of macOS materials. Foreground text never goes through
a blur texture. Light/dark tint alpha is 0.60/0.58, while the workspace remains
readable. Native desktop tests passed 65 checks: red/blue sidebar delta 146,
with 90 intermediate pixels across the controlled split-color edge; disabling
transparency removes the effect. Minimize, restore, resize and exact corners
also passed. No desktop image is sampled by the production implementation.

The selected Singapore exit completed verified TLS/HTTP responses to all six
OpenAI probe hosts. The independent route-verified proxy measurement was 632 ms
and HTTP 204. A separate ephemeral Codex CLI process, explicitly given the
isolated proxy environment, returned the expected sentinel in 6092 ms with
exit code 0. Raw CLI output and credentials were not retained. This proves that
request through that exit, not desktop OAuth or long-lived remote-control
WebSocket acceptance. The earlier UAE exit timeout remains valid evidence
about that exit. The isolated engine was stopped; the original encrypted node
store SHA-256 remained unchanged and system proxy ownership was not taken.

Final single-window follow-up: HeroChecks passed 229 checks with frame capture enabled; WindowChecks passed 65 checks. Earlier failed/crashed batches are retained only as rejected diagnostics, not acceptance. Physical display and desktop OAuth release gates remain open.
