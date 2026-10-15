# Phase 3 final integration

Swirl keeps its existing Qt Quick application and owned Mihomo v1.19.32 engine. The overview, process, connection and traffic pages now share real traffic/connection samples with bounded local history, daily aggregation and retained ended connections. Idle and uncollected states are distinct. Process discovery uses Mihomo's `always` mode; only traffic that traverses Swirl is observable.

The grouped Chinese sidebar scrolls independently, with fixed window controls and bottom actions. Global event/system-proxy/TUN capsules use actual state. TUN remains explicitly unavailable. Cards share radius/spacing tokens; scroll indicators follow the Windows accessibility preference. Subscription cards expand inline without a second detail panel.

Node tests use up to three separate owned engine instances, each with only its selected node and explicit dialer dependencies. Delay and actual HTTP request results are recorded separately from connection state. Tests can time out or be cancelled without changing the running node or Windows proxy. Subscription redirects are bounded and HTTPS downgrade is rejected; failed updates retain stored nodes.

Diagnostics collect only Swirl-observable events, with redaction, bounded rotation, acknowledgement and a local ZIP export. The canonical knot SVG is unchanged. Runtime and installer icons share cropped-artboard rasterization at native Windows sizes; a versioned icon filename refreshes owned shortcuts without changing unrelated applications.

## Validation on Windows

- Release build with C++23 / Qt 6.10.3 / MinGW x64, final production build excludes the runtime evidence driver and QtTest.
- CTest: 12/12, including actual Mihomo chains, imported subscriptions, accounting/reset/persistence, ZIP redaction/rotation, HTTP capture, navigation and motion.
- System proxy recovery: 9/9, including independent WinINET and registry state, external edits, GUI/engine termination and encrypted journals.
- Real encrypted node-store copy: all imported nodes independently tested; exact per-node outcomes remain local and are not committed.
- Actual Google search, YouTube homepage and OpenAI auth discovery HTTPS requests returned HTTP 200 through Swirl. A paced real HTTPS download ran longer than 30 seconds with real rate/connection/process samples.
- Installed native Codex app-server, with isolated ephemeral auth storage and a deliberately invalid diagnostic code, reached the token endpoint and received HTTP 401. This proves transport reachability only; actual user authentication is unverified.
- Actual FP16 HDR GPU readback and native motion checks passed. Native window compositor/DPR checks were blocked by target-window occlusion; no passing result is asserted. OS display settings were not changed.
- Isolated install, same-directory upgrade, production navigation and uninstall passed; user node store remained unchanged.

## Remaining acceptance items

The original Surge reference screenshot was not attached. Real browser Google interaction and YouTube video playback for 30 seconds remain unverified after browser URL verification failed and computer use stopped. Full account authentication requires the user. The real subscription server returns HTTP 400 indicating its upstream link has no valid node information; this is not an HTTP 302 redirect, and stored nodes are preserved. Direct Internet TCP latency can fail while proxied HTTPS succeeds, and the UI reports those independently. Native window/DPI acceptance needs an unobscured desktop; Qt DPR checks do not substitute for changing Windows display scaling.

PR #12 remains a draft targeting `test`. No merge, main-branch change or formal release is authorized before user acceptance. Local evidence, subscription URLs, credentials, raw connection history and auth state are never committed.
