# X1.2-B upstream field and semantic research

Observed 2026-10-22 Asia/Singapore. This is a read-only intermediate research note, not an implementation or a test result. All implementation should be independent; no upstream proxy kernel or source copying is proposed.

## Fixed reference versions and license review

| Project | Pinned commit | Observed release/version | License read |
| --- | --- | --- | --- |
| XTLS/Xray-core | `1b1647cd9ddf0abc34b981d4611fc03bcac1ca74` | v26.10.21 | Mozilla Public License 2.0 |
| v2fly/v2ray-core | `de610153d59ee0bc9222a17680061d732fa14e7b` | v5.55.0 (v4 JSON configuration compatibility path examined) | MIT |
| SagerNet/sing-box | `dfb80349bf5779ec0a3f834c9ec2794345bff8f0` | HEAD, commit title: Batch loopback hairpin writes in go stack | GPL 3.0 or later; LICENSE also contains application-name/association restriction |

Licenses were fetched and read at each exact commit. Xray MPL protects covered source on a file basis; V2Ray MIT requires preservation of notices for copied material; sing-box is not suitable for unreviewed code copying into this project. The work should learn externally observable field semantics only and implement Swirl's conversion independently.

License links:

- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/LICENSE
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/LICENSE
- https://github.com/SagerNet/sing-box/blob/dfb80349bf5779ec0a3f834c9ec2794345bff8f0/LICENSE

## Shared structural distinctions

The pinned Xray release supports a simplified `settings` object with direct `address`, `port`, and protocol authentication fields. It also retains the earlier `vnext`/`servers` forms, but now checks that exactly one server exists and one VLESS/VMess user exists (at most one HTTP/SOCKS user). Pinned V2Ray's v4 JSON compatibility parser still accepts arrays of multiple servers and multiple users. This is a real dialect difference, not a reason to truncate arrays.

Swirl's requested import expansion can enumerate every `(outbound, server, user)` tuple into an explicit selectable node. Store source document/outbound path, server index, user index, original raw JSON, and tag. For zero HTTP/SOCKS users create one unauthenticated node; for missing/empty VLESS/VMess users emit a missing-authentication diagnostic. Preserve all array entries, including invalid entries, in the raw source. Expansion is a documented Swirl import policy and does not reproduce V2Ray runtime balancing/user selection semantics automatically.

An ambiguous mixture of simplified direct fields and array fields must not silently select one or discard the other. Preserve both and reject execution until disambiguated. Current Xray overwrites array fields when direct `address` is present; Swirl should not silently copy that lossy precedence.

## VLESS

Old-style path: `settings.vnext[i].address`, `.port`, `.users[j]`. User fields include `id`, `encryption`, `flow`; common user metadata is `level`, `email`. The pinned Xray simplified form also has `reverse` (configuration for reverse proxy) and other contemporary extensions; unsupported extensions must remain in the preserved object and block execution when behavior matters.

`encryption` is required. Pinned V2Ray requires the explicit value `none`. Current Xray also accepts a post-quantum encryption configuration beginning with `mlkem768x25519plus`, followed by native/xorpub/random appearance and 0rtt/1rtt plus key/padding configuration. A non-`none` value is therefore not necessarily invalid; if Swirl lacks that implementation, preserve it and state unsupported encryption. Do not rewrite to `none`.

Current Xray flow supports empty, `xtls-rprx-vision`, and `xtls-rprx-vision-udp443`. Preserve the original string. The UDP443 variant changes QUIC behavior and must not be collapsed into plain Vision without a supported semantic equivalent.

The Xray documentation says Vision is available over raw/TCP + TLS/REALITY, and also with VLESS Encryption over more transport combinations. A converter without VLESS Encryption support can reject those combinations explicitly, but should avoid calling all such official configurations universally invalid.

UUID dialect distinction: pinned Xray `common/uuid/uuid.go` accepts a nonempty custom string of up to 30 UTF-8 bytes and maps it to a UUIDv5 using the nil namespace. Other candidate strings of 32 through 36 bytes go through its UUID hex parser. V2Ray's official VMess documentation specifies a UUID. If Swirl deliberately supports only canonical UUIDs in this stage, diagnose custom Xray IDs as unsupported ID representation and preserve them, rather than reporting that Xray never accepts them. A malformed 36-byte UUID is an unambiguous invalid-UUID test fixture.

References:

- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/vless.go
- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/common/uuid/uuid.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/vless.go
- https://xtls.github.io/config/outbounds/vless.html

## VMess

Old-style structure mirrors VLESS: `settings.vnext[].address/port/users[]`. Preserve `id`, `alterId`, `security`, `experiments`, `level`, `email` independently. `alterId` is uint16 in pinned V2Ray's parser: 0 through 65535; absent defaults to zero. Never clamp legacy nonzero values to zero.

Pinned V2Ray account encryption accepts `auto`, `aes-128-gcm`, `chacha20-poly1305`, `none`, `zero`; `none` and `zero` are different packet semantics. VMess AEAD is a header authentication selection; it must not be inferred merely from the body cipher being AES-GCM. V2Ray documentation identifies `alterId=0` with AEAD in ordinary modern operation, while the historical AEAD-disabled environment variable can change legacy behavior. Swirl should not claim support for that environment-dependent compatibility unless implemented.

Pinned Xray's VMess account no longer contains `alterId`, and its cipher switch now explicitly recognizes only auto/AES128GCM/ChaCha20Poly1305. Unknown strings fall to AUTO in that upstream implementation. Swirl must not reproduce that fallback, because it would violate this task's lossless requirement; V2Ray none/zero/legacy parameters must survive and remain blocked unless the native connector supports them.

V2Ray experimental `experiments` is a string (documented examples include authenticated length and no-termination behavior). Preserve it; unsupported behavior blocks execution. sing-box's `alter_id`, `global_padding`, `authenticated_length`, `packet_encoding`, `multiplex`, `transport` belong to sing-box's schema and are not aliases for Xray settings without an explicit separate dialect converter.

References:

- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/vmess.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/vmess.go
- https://github.com/SagerNet/sing-box/blob/dfb80349bf5779ec0a3f834c9ec2794345bff8f0/option/vmess.go
- https://www.v2fly.org/config/protocols/vmess.html

## Trojan

Array form: `settings.servers[].address/port/password/level/email`. Password is a string and cannot be empty in the pinned Xray/V2Ray build paths. Preserve Unicode and complete bytes; no trimming or clipping. Pinned Xray includes an old `flow` field in its JSON structure but rejects any nonempty value because Trojan flow was removed. Preserve it and block execution, rather than converting it into VLESS or dropping it.

TLS, SNI, ALPN and WebSocket are stream settings; they do not change the Trojan authentication type. Never infer TLS solely from port 443 or silently add a security layer absent from the configuration.

References:

- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/trojan.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/trojan.go

## Shadowsocks

Array form: `settings.servers[].address/port/method/password/level/email`. Pinned V2Ray additionally recognizes `ivCheck` and parses legacy `ota`; the latter is retained in the JSON structure but not applied by its shown outbound build. Treat source intent conservatively and preserve these parameters. An unknown/unsupported field should not be represented as successfully applied.

Pinned V2Ray supports AES128GCM, AES256GCM, ChaCha20Poly1305, and none/plain, with documented source aliases. Pinned Xray supports the AEAD algorithms plus XChaCha20Poly1305 and delegates recognized Shadowsocks 2022 methods to a separate implementation. Native Swirl capability, not those upstream lists, decides executability.

Do not automatically replace cipher methods. Known spelling aliases may have an explicit canonical execution mapping while retaining the exact source spelling and semantic equivalence; an unimplemented method should stay unchanged and blocked. Shadowsocks 2022 credentials can have distinct key formats; do not feed them into the legacy password-derived AEAD implementation.

References:

- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/shadowsocks.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/shadowsocks.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/proxy/shadowsocks/config.go
- https://github.com/SagerNet/sing-box/blob/dfb80349bf5779ec0a3f834c9ec2794345bff8f0/option/shadowsocks.go

## SOCKS

Array form: `settings.servers[].address/port/users[].user/pass/level/email`. An absent or empty users array indicates unauthenticated SOCKS. A populated users array indicates credentials, so do not silently treat a malformed username/password object as no-auth.

Pinned V2Ray `settings.version` is a string: `4`, `4a`, `5`, with absent/empty defaulting to SOCKS5. SOCKS4/4a can carry a user ID but no nonempty password; V2Ray explicitly rejects passwords for those versions. SOCKS5 authentication has byte-length constraints (one-byte username/password lengths), so native validation should reject oversized values without logging them.

Pinned Xray socks settings no longer has a version selector and uses SOCKS5. A V2Ray version field must be handled as that dialect's field; unsupported combinations must not be relabeled SOCKS5.

References:

- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/socks.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/socks.go
- https://www.v2fly.org/config/protocols/socks.html

## HTTP

Array form: `settings.servers[].address/port/users[].user/pass/level/email`. Xray additionally has settings-level `headers` (map string to string) that are applied to proxy requests. Preserve and validate those separately from WebSocket headers. Header values can contain authentication material and must be redacted from logs.

Both pinned Xray and V2Ray outbound implementations create a tunnel using HTTP CONNECT. `protocol=http` is not a promise to forward requests with the ordinary absolute-URL HTTP proxy request form. Source `streamSettings.security=tls` configures TLS to the proxy endpoint (HTTPS proxy), not TLS to the eventual destination. Preserve security and use the native HTTP CONNECT outbound only if it supports the requested layering/authentication.

References:

- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/http.go
- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/proxy/http/client.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/http.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/proxy/http/client.go
- https://xtls.github.io/config/outbounds/http.html

## Security and transports

Preserve the full original `streamSettings`, all its known and unknown child objects, and the outbound-level `mux`. Typed extraction must never be the only retained copy.

Current Xray has `method` as a newer transport selector alongside `network`. `raw`/`tcp`, `ws`/`websocket`, and `xhttp`/`splithttp` have specific aliases in its parser. V2Ray HTTP/2 is selected by its http/h2 transport rather than the HTTP outbound protocol. Unsupported gRPC, HTTP/2, HTTPUpgrade, XHTTP, KCP, QUIC, and newer methods must not become TCP.

TLS fields across examined versions include serverName, alpn, allowInsecure, certificates and disableSystemRoot. Certificate entries include certificateFile/certificate/keyFile/key/usage; Xray adds OCSP/loading/chain options. Additional behavior includes session resumption, TLS version/cipher/curve choices, fingerprints, verification names, pins and ECH. Pinned V2Ray uses `pinnedPeerCertificateChainSha256` (array), `echConfig` and `echDohServer`; pinned Xray has `pinnedPeerCertSha256` (string), `verifyPeerCertByName`, `echConfigList`, `echServerKeys`, and `useSystemCA`. These are not interchangeable simply because their purpose resembles one another.

REALITY client fields in pinned Xray include `fingerprint`, `serverName`, `password`, legacy alias `publicKey`, `shortId`, `mldsa65Verify`, `spiderX`, `show`, `masterKeyLog`. `password` if nonempty takes precedence over publicKey upstream, so conflicting values should be preserved and explicitly rejected by a strict lossless adapter. Public key/password decodes as unpadded base64url to 32 bytes. shortId is hexadecimal, even length, at most 16 characters; empty is accepted and represents zero padding. mldsa65Verify is a separate post-quantum verification parameter. Do not downgrade REALITY to ordinary TLS. Server-only REALITY fields found on a client import should be preserved and diagnosed rather than silently accepted as applied.

WebSocket differences:

- Pinned Xray: `host`, `path`, `headers`, `acceptProxyProtocol`, `heartbeatPeriod`; early data is embedded in path's `ed` query parameter and removed from the actual path by upstream. Independent host takes precedence over Host in headers. Case-insensitive conflicting Host entries should be diagnosed.
- Pinned V2Ray: `path`, `headers`, `acceptProxyProtocol`, `maxEarlyData`, `earlyDataHeaderName`, `useBrowserForwarding`, `parseXForwardedFor`. `maxEarlyData` is int32 in its parser. Its documentation says acceptProxyProtocol is inbound-only. It does not mean the outbound should send a PROXY header.
- sing-box: `max_early_data` and `early_data_header_name` use its own schema. They are not standard Xray field spellings. An unrecognized `earlyData` field should survive as an extension and be diagnosed; no universal official Xray/V2Ray `earlyData` member was found in the pinned structs.

If Swirl lacks early-data support, a path containing a recognized `ed` control query must be blocked instead of sent as a literal path while claiming equivalence. Save the exact source path for round-trip restoration.

References:

- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/transport_internet.go
- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/transport_security.go
- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/infra/conf/transport_method.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/v4/transport_internet.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/infra/conf/cfgcommon/tlscfg/tls.go
- https://github.com/SagerNet/sing-box/blob/dfb80349bf5779ec0a3f834c9ec2794345bff8f0/option/v2ray_transport.go
- https://xtls.github.io/config/transport.html
- https://www.v2fly.org/config/transport/websocket.html

## Suggested strict adapter cases

Validate field types before applying defaults; absent and explicit null are not automatically equivalent. Require nonempty endpoint and integer port 1..65535. Preserve enum values without automatic fallback. Cap expanded node count and cumulative diagnostics so a large but within-size input does not amplify memory via repeated raw JSON copies; share a document/source object where practical.

Use exact structural paths in diagnostics, but never include raw UUID, password, subscription URL, token, custom header values, or user-controlled tag text in the diagnostic message. Unknown object keys can themselves contain secrets, so do not render arbitrary keys into logs without masking/bounding. Round-trip tests should compare semantic fields and raw restored source, then independently confirm executable conversion succeeds or is refused for every unsupported meaningful field.

This research did not inspect or validate Swirl's native runtime; runtime support conclusions must come from its source, capability checks and executed tests.

## Runtime-default follow-up

Read runtime files as well as JSON structures to avoid replacing omitted settings with the wrong defaults:

- Both stream builders default to TCP; absent/empty security has no security layer. Xray's newer method selector overrides network, and rawSettings overrides tcpSettings. A strict adapter should flag conflicting aliases.
- Both examined TLS runtimes set absent/empty ALPN to h2 plus http/1.1 in the general TLS path; WebSocket dialers supply http/1.1 for an otherwise empty ALPN. An explicit TLS serverName overrides the destination; absent serverName falls back to the destination.
- Xray's current GetFingerprint maps an absent/empty fingerprint to Chrome Auto, including REALITY. V2Ray does not expose the same JSON fingerprint field. Therefore an unlabelled generic JSON importer cannot promise identical implicit ClientHello behavior for both dialects merely by choosing one fingerprint default. Explicit unsupported fingerprints must remain blocked.
- Xray WS host precedence is independent host, then header Host at build time, then explicit TLS serverName, then endpoint address. V2Ray uses the request URL endpoint (including non-default port) unless a Host header was specified; it does not use TLS serverName as the implicit Host. If the source is not tagged with a dialect and has different endpoint/SNI without an explicit Host, the implicit behavior is ambiguous. Preserve source and diagnose or apply a documented importer dialect policy.
- Empty WS paths normalize to slash; relative nonempty WS paths receive a leading slash in both runtimes. The exact source path should still survive round-trip storage.
- REALITY defaults serverName to destination, spiderX to slash, and show to false. Custom spiderX drives a fallback crawler after an authenticated connection is not established. show=true enables debug outputs including auth bytes in Xray; unsupported debug/crawler behavior is not semantically equivalent if silently discarded.
- Current pinned Xray TLS builder rejects allowInsecure=true as a removed feature and directs users toward pinning/verification options; pinned V2Ray still supports it. A compatibility importer can retain legacy/V2Ray semantics without falsely describing them as current Xray behavior.

Additional fixed references:

- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/transport/internet/tls/config.go
- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/transport/internet/tls/tls.go
- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/transport/internet/websocket/dialer.go
- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/transport/internet/websocket/config.go
- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/transport/internet/reality/reality.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/transport/internet/tls/config.go
- https://github.com/v2fly/v2ray-core/blob/de610153d59ee0bc9222a17680061d732fa14e7b/transport/internet/websocket/dialer.go

## B4 implementation and recovery checkpoint (2026-10-22 Asia/Singapore)

The research note above was recovered from the previous X1.2-B worktree; it was
not present in the verified remote B1 tree `4606b6df484cd0504014b9bdac6cb237a813c9b3`.
Its former safety/transport draft was reviewed and adapted to B1's actual
`ValidatedOutbound`/`Sink` API. The old alternate converter was not installed.
X1.2-A's parser, duplicate-key checks, depth/size bounds and raw-byte archive
remain the only parsing and restoration authority.

The new `xray/security.rs` computes bounded TLS, REALITY and WebSocket candidate
parameters. Every stream object, unknown field, source enum spelling and mux
object remains in the immutable original; the public projected parameter views
are explicitly private-data candidate views, not execution permissions.
Restoration always reparses and revalidates the original bytes.

Implemented decisions:

- TCP/raw and WS/websocket aliases are recognized, including Xray's newer
  `method`; conflicting aliases are errors. gRPC, HTTP/2, HTTPUpgrade and XHTTP
  stay identified and carry `TransportUnsupported`, never a TCP fallback.
- TCP HTTP disguise, nonempty inactive stream settings, socket extensions and
  unknown settings block execution. Equal tcpSettings/rawSettings no-op objects
  remain accepted; unequal objects are explicit conflicts.
- TLS preserves source SNI, ALPN representation, fingerprints, verification
  flags and certificates. The native subset uses verified rustls with the
  existing bundled roots, endpoint SNI when absent, h2 plus http/1.1 when ALPN
  is absent/empty, and HTTP/1.1 for WS. Explicit fingerprints, custom
  certificates/pins, insecure mode, disabling roots, TLS-version/cipher/ECH
  extensions, and session-resumption requests remain preserved but blocked.
  The native candidate does not claim a byte-identical browser ClientHello or
  equivalence to a producer's platform root store. HTTPS CONNECT requires
  explicit HTTP/1.1 ALPN because this branch has no native HTTP/2 CONNECT.
- REALITY retains the actual layer, checks unpadded base64url key material and
  short-ID syntax, rejects contradictory publicKey/password aliases, and uses
  only the existing native fingerprint profiles. `hellochrome_133` has an
  explicit equivalent mapping to Swirl's fixed `chrome_133` profile; source text
  is unchanged. The existing native `chrome` profile remains fixed Chrome 133,
  not a promise to track upstream Chrome Auto. Absent/empty fingerprint is
  blocked. Explicit crawler/debug/PQ-verification/key-log/server-only options
  are retained and blocked rather than silently dropped. This is native
  authenticated handshake support; it does not implement Xray's fallback crawler.
- Vision remains `xtls-rprx-vision`. Current native support is TCP + REALITY;
  ordinary TLS Vision and the UDP443 variant are preserved and blocked.
- WS retains full Host/path/headers and early-data controls. The representable
  subset projects one unambiguous Host and a normalized request path. Any other
  HTTP header, enabled early data/browser forwarding/heartbeat, or conflicting
  Host values blocks execution. Xray `ed` query controls are recognized even
  for `ed=0`; they are never sent as ordinary paths while claiming equivalence.
  Dialect-dependent implicit Host choices (SNI mismatch or nondefault port)
  require explicit source Host. V2Ray maxEarlyData is bounded by signed int32.
- Enabled mux, XUDP changes and unknown mux extensions are preserved and blocked.
  Explicitly disabled ordinary mux with an in-range concurrency is a no-op.
  Nonempty global transport defaults block each affected node; they cannot be
  ignored while claiming that an outbound is executable. The shared diagnostic
  budget remains enforced.

Fresh checks of Xray source used the exact local checkout at
`1b1647cd9ddf0abc34b981d4611fc03bcac1ca74`: `infra/conf/transport_internet.go`,
`infra/conf/transport_security.go`, `infra/conf/transport_method.go`,
`infra/conf/xray.go`, `transport/internet/tls/config.go`,
`transport/internet/tls/tls.go`, and `transport/internet/websocket/{dialer,config}.go`.
The MPL-2.0 license was read. The primary documentation at
https://xtls.github.io/config/transport.html and
https://www.v2fly.org/config/transport/websocket.html was checked in this session.
No upstream implementation or complete proxy runtime was copied or embedded.

Local B4 validation uses Linux Rust 1.99.1 and an isolated memory worktree.
All 170 swirl-subscription tests passed (89 module tests, 11 adversarial,
18 existing B1 conversion, 25 new B4 conversion, and 27 structure tests; no
skips). `cargo fmt --all -- --check`, package `cargo check --locked --offline`
and `cargo clippy --all-targets --locked --offline -- -D warnings` passed.
Final workspace and exact-commit three-platform CI belong to B6 and must be
reported from their actual results. These offline conversion tests are not
network tests.

B4 semantic-status follow-up: unknown extension schemas and unimplemented
transports are `Unverified` as well as execution-blocked. A known field whose
semantics were checked can still be `Valid` with an unsupported-runtime
diagnostic. Neither status alone grants native execution.

## B4 execution-boundary audit follow-up

The pinned Xray dependency is uTLS
`aa6edf4b11af82e110eea845bb2983d30138d651`; its `u_common.go` defines
`HelloChrome_Auto = HelloChrome_133`. The existing native Chrome133 wire profile
uses that same fixed reference. Thus the source `chrome` selector is compatible
with the selected version here, but it is not a promise to follow future changes
to an upstream Auto profile. `hellochrome_133` has the explicit native projection
`chrome_133`; the original remains unchanged. The source names `rustls` and
`chrome_133` are not in pinned Xray's fingerprint registry. They now remain
`Unverified` with `RealitySourceFingerprintUnsupported`, even though Swirl's
native IR itself can validate those names. An internal IR alias cannot expand
the official JSON dialect. The positive source-profile set is `chrome` and
`hellochrome_133`; other preserved profiles remain unverified and blocked until
an explicit source-to-native mapping is implemented.

When `spiderX` is absent, the pinned upstream defaults it to `/` and may invoke
its HTTP/2 fallback crawler when a valid decoy certificate is received without
REALITY authentication. The native runtime instead rejects the handshake and
closes the connection. The new informational
`RealityNativeAuthenticationOnly` diagnostic makes this execution scope visible
for otherwise supported fingerprint projections: the native authenticated proxy
path is available; the failure crawler is not an equivalent behavior. An
explicit `spiderX`, including empty string or `/`, remains execution-blocked.
This does not weaken server authentication, enable a TLS fallback, or claim
that an imported node has connected successfully.

The native browser profile's empty IR ALPN selects `h2,http/1.1`, matching the
pinned uTLS profile. An explicit source REALITY `alpn` extension stays preserved
and blocked because the pinned official REALITY JSON schema does not apply it.
Ordinary TLS fingerprints remain blocked rather than translated into a REALITY
profile. The review also checked raw/tcp alias conflicts, inactive layers,
WebSocket custom headers and ambiguous default Host, and global defaults at the
B5 adapter boundary. All of those paths remain blocked when they cannot be
represented.

Primary fixed dependency source:

- https://github.com/refraction-networking/utls/blob/aa6edf4b11af82e110eea845bb2983d30138d651/u_common.go
- https://github.com/XTLS/Xray-core/blob/1b1647cd9ddf0abc34b981d4611fc03bcac1ca74/go.mod

Two regression cases verify native-only fingerprint rejection and visible
default crawler scope through archive restoration, including explicit empty
crawler values and uppercase fingerprint spellings.

The fixed uTLS `LICENSE` was read and is BSD-3-Clause (Go Authors); this audit
only consulted its profile identifier and did not copy or introduce its runtime.
The audit follow-up passed all 172 subscription tests (27 B4 security tests),
`cargo fmt --all -- --check` and package clippy with `-D warnings`, using the
locked offline dependency set. The new info diagnostic is included in the
existing shared diagnostic budget; exceeding that bound still fails explicitly
with `DiagnosticLimit`.
