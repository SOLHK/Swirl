# 0.2.13 desktop compatibility candidate

This is a diagnostic candidate, not a claim that the user's Codex workspace or TUN has been repaired.

## Reproduced changes

1. The inbound proxy rejected valid HTTP/1.0 CONNECT requests before routing. Accept that tunnel handshake while preserving authority, authentication, framing, body and version validation. Ordinary HTTP/1.0 forwarding and unknown versions remain rejected. Four new regression cases produced two failures before the fix and all passed afterwards. The full `swirl-protocol` suite passed 182 tests.
2. Product system-proxy acquisition now yields while waiting for the recovery guard or journal lock. Cancellation and engine-generation changes revoke preparation before OS writes. Guard acknowledgements carry the session identity. Restoration contention retries without sleeping on the UI thread; a still-current acquisition request resumes after release. Native Windows read/write/DPAPI calls remain synchronous and must be profiled separately. The independent recovery guard and encrypted snapshot remain in place.
3. Offline Codex diagnostics discover both unpackaged and Store log roots and use UTC date folders across midnight. Duplicate mirrored logs count once. Explicit challenge markers, proxy errors, timeout and the local workspace gate have separate fixed categories; no arbitrary error text or authentication material is exported. 31 assertions passed.

## Current observed evidence

On 2026-10-26 (Asia/Shanghai), the installed Swirl executable/manifest identifies 0.2.12, source `8e3fc98`; an old uninstall-registry version is stale. Swirl was not running during the initial snapshot. The current WinINet proxy was a listening Clash process; WinHTTP was Direct, no PAC or proxy environment variables were configured in the inspected scopes. These observations do not inspect the environment inherited by every existing process.

Available Codex logs contain `ERR_PROXY_CONNECTION_FAILED` and local `432 / Workspace routing is unavailable` for `/settings/user` and `/accounts/check`. That exact 432 wrapper occurs before the authenticated fetch; it is not an OpenAI HTTP 432 response. No explicit `cloudflare_challenge` marker was found in the inspected logs. Current live logs were not all readable, so historical events cannot establish the current request state.

Two encrypted cached node samples were reused without refreshing their sources or changing OS networking. The installed 0.2.12 DLL's REALITY sample completed schema-2 HTTPS 204 and a CONNECT/strict-TLS HTTPS 204 chain. The SS sample failed at origin TLS with `TlsHandshakeEof`. This differs from a previous successful sample run, and is retained as a failure. Neither result establishes all-provider or new-package acceptance.

## Reference review

- [Codex #51917](https://github.com/openai/codex/issues/51917), [#52790](https://github.com/openai/codex/issues/52790) and [#51691](https://github.com/openai/codex/issues/51691) were investigated as comparison reports, not local diagnoses.
- [curl proxy1.0](https://curl.se/docs/manpage.html#--proxy1.0) documents the legacy CONNECT mode, and [RFC 9110 CONNECT](https://datatracker.ietf.org/doc/html/rfc9110#section-9.3.6) specifies authority-based tunnel semantics.
- Architecture/skill references and their license review are recorded in `V3_IMPLEMENTATION.md`.

## Still unverified or unsupported

- Real Codex workspace creation, authenticated response and long-lived streaming through this candidate.
- The failed SS provider sample, all subscription nodes, and real browser/CLI/Qt/Electron parity under this package.
- TUN forwarding: the baseline has a capability gate, not a working Windows tunnel adapter. No TUN success is claimed.
- Physical 60/120 Hz motion acceptance, DPI visual acceptance and long-duration memory behavior.

Account storage, TLS validation and Cloudflare checks were not bypassed or cleared. No operating-system network change was made on the user's machine. Native proxy mutation/lifecycle checks run only on the disposable Windows CI runner.

## Newly authorized subscription validation

The two newly authorized sources were fetched only in an isolated local harness.
Source URLs, responses and node credentials are retained locally with current-user
DPAPI protection; none are CI inputs or published artifacts.

Source 1 returned HTTP 200 with verified TLS on a direct diagnostic path. The
production Qt importer saved and reloaded 56 deduplicated nodes, of which 55 were
executable and one lacked a valid REALITY server name. Its 59 raw URI records
exposed a separate portable-parser inconsistency: exact empty TCP `host`, `path`
and `serviceName` placeholders and neutral `quicSecurity` values were already
handled by Qt but rejected by Rust inspection. The narrow URI normalization now
matches, retaining rejection of nonempty, whitespace, duplicate and unknown
fields. The Rust subscription suite passed 302 tests plus formatting and Clippy.

An actual representative source-1 node returned HTTPS 204 through both versions
for native probe, HTTP/1.1 CONNECT and independent curl with certificate checks.
The installed 0.2.12 DLL returned 400 for HTTP/1.0 CONNECT; the candidate DLL
returned CONNECT 200 followed by certificate-verified HTTPS 204.

One actual ephemeral, read-only Codex CLI request through that isolated Swirl
listener completed and returned `OK`. Owner-PID TCP observations and Swirl's
connection/byte counters correlated the request to Swirl. Only that subprocess's
proxy environment and `respect_system_proxy=false` override were used; no global
Codex setting or desktop session changed. Six background streams still reported
`StreamUnexpectedEof`; successful inference does not establish all-stream health
or desktop workspace acceptance.

Source 2 returned HTTP 403 both directly and through the verified isolated Swirl
exit, after successful CONNECT and certificate verification. No explicit
Cloudflare challenge header was observed. The provider's rejection trigger is
unknown; no source-2 nodes or successful import are claimed.
