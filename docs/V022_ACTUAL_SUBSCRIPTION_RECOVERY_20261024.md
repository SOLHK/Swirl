# Swirl 0.2.2 actual subscription regression

The user retested 0.2.0 and reported continued failures across client formats.
0.2.1 changed only the build graph. Neither is evidence that the actual provider
or Codex issue was fixed. Continue on `work/swirl-019-subscription-regression-20261024`;
main/test/other development branches remain unchanged.

## Evidence and actual causes

The new report identifies 0.2.0 / `4fa690d`. Fifteen automatic downloads made
both native and legacy-UA requests and still returned HTTP 400 / Qt enum 302.
Three HTTP-200 responses then failed full-profile projection. This disproves
the earlier missing-retry hypothesis. An explicitly authorized read-only GET
of each existing saved source subsequently returned 200 with matching request
headers and proxy policy; those two requests are consumed. Their failure-time
HTTP 400 is not reproduced or declared fixed. No URL/authentication edits or
additional guessed UA sweep were made. Private responses are cached only with
current-user DPAPI, outside Git and deliverables.

Two concrete importer defects were reproduced against actual data:

1. Automatic fallback still treated foreign global capability declarations as
   permission to apply them. The existing manual nodes-only path did not apply
   them. The actual Surge body contains General/listener settings, URL rewrites,
   Script and MITM sections; the old automatic whole-document gate rejected all
   nodes even though the strict node parser found 90 valid records.
2. The newly supplied URI subscription contains 59 records, merging to 56
   VLESS/REALITY nodes. Every URI has `type=tcp`, `headerType=none` and empty
   `host`, `path`, `serviceName`. Presence of those inactive empty placeholders
   was incorrectly treated as an unmapped TCP transport requirement. All nodes
   were therefore blocked before a runtime attempt.

## Correct trust boundary

Strict compatible full-profile projection is unchanged. If it cannot apply,
automatic import reuses the existing manual nodes-only boundary: canonical
nodes are validated independently and merged atomically into the current Swirl
DNS/rules/groups. Every foreign non-node setting is opaque encrypted provenance.
Scripts, rewrites, MITM, file/provider declarations, listeners and TUN are refused
execution/application. No file read, script evaluation, additional provider GET,
listener or host change is authorized by retaining that source data. Retained
originals cannot be promoted into the runtime during reload. A persistent
nodes-with-warning outcome explains this restricted result and retains a fixed
compatibility code, without describing the successful node update as a failure.

Node authentication, TLS/REALITY, unknown security parameters, nonempty transport
requirements and runtime activation remain closed. The URI repair accepts only
literal empty inactive TCP fields. Whitespace, nonempty paths including `/`,
nonempty hosts/services, unknown extensions, conflicting aliases, empty transport
types and missing required fingerprint values retain their existing rejection.
Exact original URIs and encrypted provenance are preserved.

## Actual private acceptance performed locally

Windows x64 / Qt 6.10.3 MinGW / Rust 1.99.1 GNU, isolated test storage, unchanged
system proxy/TUN/routes/DNS and current apps:

| Cached actual source | Parsed records | Saved after merge | Native eligible | Import result |
|---|---:|---:|---:|---|
| Existing Clash | 90 | 88 | 88 | nodes-with-warning |
| Existing Surge | 90 | 88 | 88 | nodes-with-warning |
| User-supplied URI source | 59 | 56 | 55 | nodes |

The first two pass encrypted reload and retain the inert foreign configuration;
all three preserve the exact current native DNS/rules/groups. Actual source
content, URLs, credentials and raw logs were not committed or uploaded.
The newly supplied source downloaded through native Qt with HTTP 200 and a
negotiated TLS session. Original saved URLs roundtrip byte-identically through
Qt encoding; no authentication/query transformation was observed offline.

Two isolated real Rust probes through eligible URI-source nodes failed with
`RealityHandshakeTimeout` and `RealityAuthenticationOrHandshake` in
`outbound_handshake`. Independent official Xray 26.10.21 controls on the same
two node ordinals also failed to obtain Google HTTPS (curl 35 / HTTP 0).
These failures are retained: successful import and runtime eligibility are not
successful provider traffic. Additional REALITY diagnosis is separate work;
no latency or network result is fabricated. Real browser/YouTube/Codex account
acceptance and manual DPI remain assigned to the user. Current Rust TUN is
unavailable.

## Validation

- 147 portable subscription tests and 4 Profile ABI tests passed; scoped Clippy,
  format and portable dependency guard passed.
- Import suite passed with the new 48-combination empty/absent URI matrix,
  exact canonical outbound equality, original URI and DPAPI reload checks.
- New Qt controlled-peer cases prove opaque globals do not change native policy,
  can reach a real SOCKS exit, retain encrypted provenance and never become full
  execution. Manual full application still rejects unsafe profiles without a
  disk write. Running-session/dangling-source rejection and strict network
  assertions remain in place.
- The broad Core run exposed three old whole-source rejection expectations.
  They were replaced with stronger assertions for the new explicit restricted
  mapping: unchanged canonical nodes/policy, encrypted inert originals, no
  private values in messages and strict manual full rejection. The affected
  three cases passed on rerun; the original failed output remains local.
- Exact-source CI reruns the required complete Core and security suites before
  packaging. QML/DPI/font/geometry and the successful incremental build graph
  are unchanged from 0.2.1.

## Primary implementation references

These sources guided an independent implementation; no external core is bundled:

- [Mihomo provider parses its node schema independently](https://github.com/MetaCubeX/mihomo/blob/3f27ef39f8c96bbfbc8b0b9bb10f5c9ef60149d8/adapter/provider/provider.go#L320-L438).
- [v2rayN separates full configuration from outbound extraction](https://github.com/2dust/v2rayN/blob/57f17d5939e88c8e643ab49b90869d637765e75a/v2rayN/ServiceLib/Handler/Fmt/SingboxFmt.cs#L4-L156).
- [Clash Verge keeps host control settings owned by the application](https://github.com/clash-verge-rev/clash-verge-rev/blob/4337bd85758d54d7b9044b2da3c9ac1176eae1f3/src-tauri/src/enhance/mod.rs#L286-L434).
- [v2rayN URI defaults use empty transport strings](https://github.com/2dust/v2rayN/blob/57f17d5939e88c8e643ab49b90869d637765e75a/v2rayN/ServiceLib/Handler/Fmt/BaseFmt.cs#L243).
- [Xray TCP config activates its declared header](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/transport_method.go#L247).
