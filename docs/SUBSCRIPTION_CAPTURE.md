# Subscription acquisition before the ten-minute window

This is the initial acquisition utility, implemented with Python 3.11+ standard
library on Windows. It is not a replacement networking core and is not yet wired
into `NodeImportService` or the installer. The existing C++ importer can be used
offline through the explicit isolated replay operation below. No UI files change.

## One-time intake (keep website switches OFF)

Run `tools/New-PrivateCaptureManifest.ps1 -PrivateDirectory <local-private-folder>`.
Use a folder outside any Git checkout, build artifact or cloud-synced folder.
The helper restricts inherited ACLs to the current Windows user and SYSTEM and
creates `subscriptions.private` and `opening.json`. Edit the former in a local
editor, not a terminal command containing URLs. It is initially plaintext inside
that private folder; the seal command replaces it with DPAPI ciphertext. Avoid
editors with cloud sync or shared backup. Python cannot guarantee removal of all
plaintext copies from process memory, filesystem history or editor recovery files.

Fill all exports available from all platforms in this single manifest:

- Clash/Mihomo (including Verge Rev, FlClash, Meta), sing-box/Hiddify,
  v2rayN/v2rayNG/V2Ray/Xray, NekoBox/NekoRay.
- Surge, Shadowrocket, Quantumult X, Loon, Stash, Surfboard, Egern,
  Karing, Streisand, V2Box and other exports offered by the provider.
- Related provider lists, rule sets, remote DNS/config resources and exact
  redirect targets if known. Each URL is a separate entry; kind is `resource`.
- Client/export version, known protocols and transports. Unknown is acceptable.
- `exportOf`: same subscription/account exported for multiple clients (use an
  anonymous group label). Identical URL + headers + window group downloads once;
  different User-Agent/authorization stays separate. Provenance stays encrypted.
- `group`: which URLs share a website switch; add g2, g3, etc. to `groups` for
  independent switches. Each actual duration must be <=600 seconds.
- Required legitimate request headers: User-Agent, Authorization, Cookie or
  provider-specific fields, only when required. No website account login needed.
- Test permission: download/offline analysis; optional node TCP/UDP connectivity,
  throughput limits, accounts/regions or destinations excluded. System proxy and
  TUN changes default to false. This tool only downloads; permission flags do not
  automatically initiate any other action.

Leave unavailable export URLs empty: `seal` removes those rows and retains the
client names under `notProvided`. Do not buy missing protocols or create new
accounts merely to fill this list. Public specifications and isolated servers
cover what they can; remaining sample gaps are reported together.

Set `proxy` to `{ "mode": "http-loopback", "host": "127.0.0.1", "port": ACTUAL_PORT }`
when using the existing local proxy to download, or `{ "mode": "direct" }`.
No system or persistent proxy settings are changed. This acquisition path is
not evidence that Swirl's native implementation carried the traffic.

```
py -3 tools/SubscriptionCapture.py seal <private-folder>/subscriptions.private
py -3 tools/SubscriptionCapture.py check <private-folder>/subscriptions.private
```

`check` does no network I/O. Output contains counts and fixed error codes only.
Keep private manifests/caches out of Git, CI, Gemini and deliverable ZIPs.

## One explicit opening confirmation

Only after downloader verification and manifest checks, open all required
switches and provide each actual opening timestamp, including timezone. Example
format: `YYYY-MM-DDTHH:MM:SS+08:00`; this example is not an opening confirmation.
Record these in `opening.json` with `confirmed: true` and the matching group names.
Never set an opening time to message receipt time or capture start time.

```
py -3 tools/SubscriptionCapture.py capture <private-folder>/subscriptions.private <private-folder>/opening.json <private-folder>/cache
```

Deadlines are actual opening + duration - 30 seconds. Both wall and monotonic
clocks are checked; clock rollback cannot extend the window. Up to four workers,
two attempts per URL, three redirects; each request has a 20-second total timer
and a <=5-second socket timeout. No retry of 401/403; bounded 429 Retry-After.
Pending requests check the original grant when they reach a worker. A DNS call
may take time to return on Windows; it must recheck the deadline before opening
any socket. No automatic reopening, polling or post-window background updater.

All roots are queued before known resources; no speed tests run in the window.
Requests are limited to exact URLs in the local manifest, including redirects.
Custom request headers never cross origins. TLS uses normal platform certificate
validation. Direct targets resolving to nonpublic IPs are rejected. Through a
user-selected loopback proxy, remote DNS resolution belongs to that proxy; exact
URL authorization still applies, with literal private addresses blocked.

## Cache and validation boundaries

Wire response body (including gzip/deflate), relevant headers, source mapping,
timestamps and SHA-256 hashes are saved using current-user DPAPI and atomic file
replacement. Max raw/decoded body 8 MiB each, aggregate wire transfer 64 MiB,
128 manifest entries. Gzip/deflate decoding is bounded and rejects truncated or
concatenated/trailing streams. Unknown formats are retained as
`CapturedUnvalidated`; HTML/common error documents are rejected.

`CapturedUnvalidated` is transport acquisition, NOT valid node conversion,
successful native handshake or full-config compatibility. Login/error detection
is a conservative heuristic; unknown error formats can still be cached. Offline
semantic parsing is mandatory before use. The original bytes are retained even
when later parsing fails.

Known YAML `url:`, JSON `url`/`download_url`, and INI resource URL lines are
discovered as hints. Unlisted URLs are reported only in the encrypted details;
they are never fetched. Cycles and depth >3 are reported. All declared resources
are downloaded once independently; no recursive network traversal occurs.
Reference discovery is not a complete parser for every client format, and scripts
are never executed. A later necessary acquisition of missing resources requires
a new opening confirmation, requested as one consolidated list.

Each batch has immutable encrypted responses and a redacted JSON report. The
encrypted last-good cache index changes atomically after verified saves. Failed
entries retain their previous pointers. Partial batches remain explicit; this
index is NOT the active application configuration. Swirl nodes/settings are not
modified by capture. Concurrent capture runs are rejected. After a hard process
crash, inspect for an active run before manually removing its stale capture.lock.

## Offline integrity and C++ import

```
py -3 tools/SubscriptionCapture.py replay <cache-response.dpapi>
py -3 tools/SubscriptionCapture.py replay <cache-response.dpapi> --inspector <SwirlPrivateSubscriptionInspect.exe> --store <new-isolated-nodes.dpapi>
```

Replay performs no download and checks both compressed and decoded hashes. The
optional inspector is the project's real `NodeImporter` + `NodeStore` path;
the target store must not exist, preventing accidental overwrite of live nodes.
Its temporary handoff is also DPAPI encrypted. Current importer size limits and
format/protocol gaps still apply (e.g. 4 MiB input, 1 MiB NodeStore). Unsupported
formats remain recoverable in the acquisition cache. Expiry of the download
window does not expire cached bytes or node credentials.

## Verification and references

Run `py -3 tools/tests/test_subscription_capture.py` on Windows. Fixtures are
synthetic and bound to random loopback ports; `localFixtures` is false in the
intake template. Public HTTPS acquisition is tested separately and does not
establish private-provider availability.

- Microsoft DPAPI contract: https://learn.microsoft.com/en-us/windows/win32/SecCrypto/example-c-program-using-cryptprotectdata
- Qt decompression safety limitations, relevant to later C++ integration:
  https://doc.qt.io/qt-6/qnetworkrequest.html#setDecompressedSafetyCheckThreshold
- Public structural JSON used for acquisition verification:
  https://sing-box.sagernet.org/schema.json
