# X1.2-B3: SOCKS and HTTP account conversion

This stage extends the existing strict parser and B1/B2 conversion API. It does
not implement a second parser, start a proxy, or declare any provider verified.
The immutable original JSON and schema-1 archive remain the persistence authority.

## Behavior

- Expand every `settings.servers[i].users[j]` into its own selectable node, in
  source order, retaining both indices and complete source paths. Accounts from
  different servers are never cross-multiplied. Missing/empty `users` produces
  one explicit unauthenticated node per server.
- Support current Xray's flat `address`/`port`/`user`/`pass` fields without
  trimming credentials. Metadata `email` and `level` survives in raw JSON;
  `level` is also retained in the existing authentication projection. HTTP/SOCKS
  levels are uint32 in these upstream definitions. Nonzero policy levels are
  preserved with an unsupported-policy diagnostic.
- V2Ray SOCKS `version` accepts missing/empty/`5`, `4`, or case-insensitive `4a`.
  Preserve the source spelling. Unknown versions and wrong field types cannot
  silently become SOCKS5. SOCKS4/4a with a nonempty password is rejected.
- SOCKS5 RFC 1929 credentials require 1..255 UTF-8 bytes for each component.
  Explicit malformed account objects remain account objects; they do not
  become unauthenticated nodes. Native-only credential restrictions produce a
  separate unsupported diagnostic, without deleting the source value.
- HTTP represents a CONNECT tunnel with Basic account authentication. Empty
  Basic components or credentials exceeding Swirl's shared native bound remain
  data, with native execution explicitly blocked. A colon in the Basic username
  and control characters are rejected. No Digest/NTLM/Bearer mode is guessed.
- Validate Xray's HTTP `settings.headers` map (string values and valid header
  syntax). Nonempty headers remain fully preserved and are marked unsupported
  because this native HTTP CONNECT schema has no header map. They are never
  confused with WebSocket headers. An inbound-only `settings.auth` selector is
  preserved and explicitly unsupported for outbound execution.
- Flat endpoint fields mixed with a nonempty users array are retained and
  expanded, but blocked: the pinned Xray direct form would ignore that array.
  Direct credentials mixed with any users array are an explicit ambiguity.
- TLS and other stream settings remain in the original document unchanged.
  B4 validates transport/security; B5 must recheck actual runtime capability.

## Fixed primary references

Behavior was independently implemented after reading these versions. No upstream
proxy runtime, copied implementation, or new dependency was added.

- Xray `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`, MPL-2.0:
  [SOCKS](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/socks.go),
  [HTTP](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/http.go),
  [HTTP CONNECT client](https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/http/client.go).
- V2Ray `de610153d59ee0bc9222a17680061d732fa14e7b`, MIT:
  [SOCKS v4 JSON](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/socks.go),
  [HTTP v4 JSON](https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/http.go).
- [RFC 1929, section 2](https://www.rfc-editor.org/rfc/rfc1929#section-2):
  SOCKS username/password byte lengths.
- [RFC 7617, section 2](https://www.rfc-editor.org/rfc/rfc7617#section-2):
  HTTP Basic username/password syntax.

## Focused validation

The new `xray_conversion_auth.rs` has 19 tests covering account expansion,
no-auth/flat forms, credentials, byte lengths, SOCKS versions, HTTP headers,
ambiguous combinations, metadata, malformed types, redaction, and exact archive
round trips. All 171 `swirl-subscription` tests passed on Linux with Rust 1.99.1,
using `cargo test -p swirl-subscription --locked --offline`. Full workspace and
Windows/Linux/macOS exact-commit validation belongs to the integrated B6 stage.
