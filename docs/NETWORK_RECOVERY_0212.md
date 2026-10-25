# Swirl 0.2.12 subscription recovery

The 0.2.11 downloader forced every non-loopback subscription request through the
running Swirl listener. A failed exit therefore prevented updating its own source;
deleting its nodes left the core running with a missing default target, and the
replacement import still depended on that listener.

The downloader now resolves the platform's proxy policy independently of core
state. External proxies and ordered alternatives are retained. Known Swirl core
and capture listeners are excluded; when they are the only configured route, only
the subscription request bootstraps directly. A failed external proxy does not
trigger a direct retry. TLS validation, same-origin redirects, signed query bytes,
the total deadline, cancellation generations and atomic source updates remain.

Import does not choose a runtime exit. When the default target is missing or has
not been chosen, successful V2 import explains how to choose an exit in Strategy.
The runtime status adapter explains `MissingTarget` and `DefaultUnconfigured` as
configuration failures without declaring an untested node unavailable. Deleted
source identities remain revoked and are not silently reattached to new imports.

## Evidence and limits

- The supplied diagnostic archive identifies installed 0.2.11 source `fd5fd50`.
  Historical direct download succeeded; later loopback-proxy attempts returned
  HTTP 400 or timed out. The current encrypted store was inspected read-only:
  zero nodes, one subscription and a default node target listed as missing.
- Existing encrypted caches were reused without subscription requests. One SS
  node and one VLESS REALITY node each returned HTTPS 204 through the installed
  Rust DLL in isolated schema-1 and schema-2 sessions. No system proxy, TUN,
  Both also completed HTTP CONNECT and certificate-verified HTTPS 204 through
  the schema-2 loopback proxy listener.
  routing, DNS, active catalog or credential store was changed. These are two
  sampled nodes, not acceptance of every source/node or the user's browser/Codex.
- Older TLS certificate failures and individual handshake/timeouts in the archive
  cannot be assigned a single cause from that archive. No certificate validation
  was disabled, no private source was refreshed, and these historical failures
  are not claimed resolved merely because the sampled nodes passed.
- The existing HTTPS download fixture is now a standalone CTest target included
  in Windows candidate packaging. It covers external proxies, strict certificate
  verification, cancellation, deadlines, redirects, size limits and secret
  redaction. Its legacy bare-store update test now explicitly supplies the atomic
  configuration owner required by current production code.
- Import persistence regression covers deleting and re-adding the exact source
  URL, a fresh source identity, encrypted reload, and no revival of the old exit.
- Development attempts retained locally include an incorrect test target name,
  a missing isolated test directory, a missing QJsonArray include, and an initial
  status fixture which attempted to start an intentionally invalid configuration.
  The status test now exercises the core-response-to-UI boundary for a session
  whose source was removed after startup. Final test/package evidence is recorded
  separately; interrupted or failed attempts are not counted as passes.

## Primary references

- [Qt QNetworkAccessManager](https://doc.qt.io/qt-6.10/qnetworkaccessmanager.html):
  per-manager proxy factories and request routing, without application-wide or
  operating-system proxy mutation.
- [v2rayN SubscriptionHandler](https://github.com/2dust/v2rayN/blob/master/v2rayN/ServiceLib/Handler/SubscriptionHandler.cs):
  subscription retrieval has an independent recovery path when its selected proxy
  fails. Swirl's implementation is independent and narrower: external proxy
  failures do not automatically authorize direct access.

Work remains on `work/swirl-ui-v2-20261024`; main/test and the 0.2.11 visual,
font-initialization and motion behavior are preserved.

Final local checks: 7/7 CTest suites passed (policy configuration, catalog
transactions, Rust/Qt integration, subscription download, Qt network policy,
subscription import and import boundaries), plus 7/7 portable-core boundary
checks. The same-source Windows/MSVC production installer remains a separate
CI gate. Private sample reports and diagnostic input stay in ignored local work
directories and are never part of the commit or CI inputs.
