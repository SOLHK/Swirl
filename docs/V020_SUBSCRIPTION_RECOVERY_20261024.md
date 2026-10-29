# Swirl 0.2.0 subscription recovery candidate

Independent branch: `work/swirl-019-subscription-regression-20261024`, based on
remote `5abf999c2a72ec58ed94d359d6bad6e791ade33b`. The previous worktree was
clean; main, test and other development refs are unchanged. The user explicitly
selected 0.2.0 for this next test delivery, superseding the old 0.1.10 handoff.

## Evidence and attribution

The user's fourth report identifies the exporting application as 0.1.9,
source `5abf999`, Qt 6.11.3. Its latest session has four subscription failures
with actual **HTTP 400**, accompanied by Qt `ProtocolInvalidOperationError`
whose enum value is **302**. Those values are distinct namespaces. No parser
or Rust outbound request ran for those failed downloads. Older successful
imports in the same rotated log cannot be assigned to the exporting source.

`1c2e362` (the automatic-import/0.1.9 change) did not alter downloader headers,
URL construction, proxy selection or redirects. The first relevant wire
compatibility change is `b30d94468bbd7dac183d59f131c9a9f54e3814f9`, in the
0.1.8 ancestry: automatic User-Agent changed from
`Clash.Meta/1.19.32 Swirl/1.0` to `Swirl/<applicationVersion>`; Accept expanded.
A controlled strict-UA HTTP server reproduces the regression using the
baseline downloader. This establishes the compatibility defect, not the
reason the user's private provider returned 400. That provider's headers,
response reason and selected format were absent from the report. No private
subscription was refreshed by development.

## Bounded repair

Automatic requests retain Swirl's native identity first. An actual HTTP
400/406/415 permits one retry with the historical automatic User-Agent.
The original encoded QUrl is retained, including signed paths, duplicate
query keys, empty values and percent-encoded authentication. Current Accept
is retained; this is not a replay of every historical request header.

The proxy candidates, total 30-second deadline, aggregate redirect budget,
HTTPS validation, same-origin restriction, 4 MiB response bound, cancellation
generation and content/profile safety checks remain in force. No DIRECT
fallback is added. Authentication failures 401/403, rate limiting 429, server
500 and explicit format preferences do not trigger this negotiation. A final
failure retains existing nodes, selection and encrypted catalog bytes.

Successful compatibility negotiation is visible in the import result. Each
completed request emits fixed attempt/negotiation/format/proxy-policy/HTTP/Qt
metadata to the existing redacted diagnostic export. It contains no URL,
hostname, headers, response body or credentials. The response's actual content
still determines its format; a compatibility UA does not authorize scripts,
unsafe settings or certificate bypass.

## Local validation and reuse

Environment: Windows x64, Qt 6.10.3 MinGW, GCC 13.1, Rust 1.99.1 GNU.
An independent CMake directory preserves the old window's build tree; Cargo
dependencies reuse the idle existing target and `D:/Codex/cache/cargo`.
Initial focused compilation: 95.819 seconds. Four affected CTest suites passed
in 42.35 seconds: import/subscription, 17-format matrix, diagnostic redaction,
and native Qt HTTP/TLS policy. Import recorded 66 passes with no failures or
skips. Initial execution lacked MinGW runtime DLL search paths and failed
before tests with 0xc0000135; adding the compiler runtime path resolved it.
That failed invocation is retained locally and is not a product crash claim.

The added real-TCP tests cover 400/406/415 recovery, byte-identical signed URL,
bounded permanent failures, no authentication retries, explicit-format
retention, encrypted-state preservation, cancellation, cross-origin rejection,
and unsafe-profile rejection after a successful retry. Portable dependency
guard: 7 tests passed. Actionlint and whitespace checks passed.

Control comparison compiled the baseline `5abf999` downloader with the added
real-socket tests: all three 400/406/415 recovery rows failed (one request,
no recovery). Restoring the fix passed all 66 Import cases. The final Import
and Qt network-policy rerun passed 2/2 suites in 28.51 seconds after the last
proxy-label correction; the unchanged format/privacy suites reuse the first
run above. No baseline failure was converted into a skip.

Portable Rust product code, QML, font, DPI, geometry and motion are unchanged
from `5abf999`. Prior source evidence for those unchanged areas is run
40091514412 (725 Rust tests, 7 boundary tests, 3 independent Xray chains and
13 Windows suites); this is reused scope evidence, not an exact-new-source
pass. The new commit's Windows candidate reruns all required core/security,
proxy recovery and packaging gates; Linux Rust runs independently in CI.

## Remaining acceptance

Private Surge/Trojan/Clash downloads, user-node latency, Google/YouTube, actual
Codex workspace/login/chat and manual DPI remain unverified. Current Rust TUN
is unavailable. Earlier strict VMess/TLS closure limitations remain open.
Three untimestamped access-violation markers cannot be assigned to this build;
today's Windows event log supplied no matching Swirl crash.

Read-only Codex logs last recorded proxy-connection errors at 18:27:07 and
local workspace gate failures at 18:32:57, with no corresponding events in the
20:17–20:20 subscription failure window (Asia/Shanghai). At the later snapshot,
Codex and the browser were connected to Clash's local proxy. This is not
Swirl acceptance. Existing Codex launch integration is preserved; no Codex
process, system proxy, TUN, route, DNS or account state was changed.

## Delivery and manual check

Deliver only the exact committed candidate whose EXE/DLL/source identity,
startup, HTTP/SOCKS5/CONNECT roundtrips, disposable proxy recovery, installer
lifecycle and full file inventory/hashes pass. It is a **test candidate**.
Do not install it automatically over the user's current installation.

1. Download the 0.2.0 test installer. Save work, exit the old Swirl yourself,
   then run the installer and open Swirl. Confirm the sidebar says v0.2.0.
2. Open More → Subscription Management. Edit a failed Surge, Trojan Surge or
   Clash source, use Automatic request format, save, then Refresh that card.
   Expect saved nodes or an explicit actionable failure; do not delete old
   sources or working nodes. A recovered request mentions compatibility
   negotiation. Recheck the previously working V2Ray source once.
3. Select one previously working node and connect. Confirm connected status
   and that Swirl owns the enabled Windows system proxy.
4. Open Google and a YouTube video. For Codex, save work and exit it yourself,
   then use Start → Swirl → Launch Codex through Swirl; check the workspace
   and one chat. This existing startup path is still awaiting actual acceptance.
5. Measure that imported node. A measured millisecond value must come from a
   successful outbound probe; a timeout/error is failure, not zero latency.
6. If anything fails, note the time, screenshot the failed subscription/node
   and Codex error if relevant, then More → Logs → Export diagnostic report.
   Send the ZIP; export hides subscription URLs, credentials and tokens.
   No commands, full DPI pass or unrelated software retest is requested.

Primary behavior references:
[Qt request headers and redirects](https://doc.qt.io/qt-6/qnetworkrequest.html),
[Mihomo subscription UA](https://wiki.metacubex.one/en/config/general/),
[MetaCubeXD import usage](https://github.com/MetaCubeX/metacubexd/blob/main/README.md).
