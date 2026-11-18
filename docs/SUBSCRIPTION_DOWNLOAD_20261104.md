# Subscription download investigation — 2026-11-04

## Scope and result

The initial Swirl 0.2.32 screenshots show two failures during download, before
format parsing: source A returned HTTP 403 and source B closed the connection
without an HTTP response. A later owner screenshot shows source B successfully
updated with 50 saved nodes, while source A still returns HTTP 403. The earlier
TLS failure is a historical observation, not proof of a permanent endpoint
failure.

The owner subsequently supplied source A's complete link and clarified that
the same link imports in Loon, with the phone and Windows computer on the same
Wi-Fi and using the same selected proxy node. This supersedes the earlier
statement that other clients also fail. The supplied link and the encrypted
Swirl source URL were compared locally after removing only trailing whitespace
from the supplied text; their UTF-8 SHA256 values match exactly.

The latest owner follow-up identifies the Loon version as “3.53” and confirms
that a manual refresh has just succeeded. The owner is not using any known
custom download settings. A stale cached profile is therefore not an
established explanation for the reported success. The public App Store history
lists Loon 3.5.3, but neither that listing nor the reported version alone proves
the exact CFNetwork build or headers used by this phone.

The Windows checks below still reproduce HTTP 403. They do not explain the
reported Loon success, prove that the link is invalid, or establish a permanent
provider fault. This work does **not** claim that source A's actual download or
its real Shadowsocks subscription import has been restored.

Existing GitHub subscription branches are already ancestors of `test`.
The newer Windows proxy compatibility branch does not change the subscription
downloader. Its separate network/runtime fixes are not evidence of a fix for
these two provider endpoints.

## Initial local observations

The two current encrypted source definitions were read under the same Windows
user and decrypted only in memory. No URL, token, provider response, node
credential or decrypted profile is included in this report or committed.
The existing source store was not modified by these checks.

| Initial check | Source A | Source B |
| --- | --- | --- |
| Windows curl, verified TLS, HTTP/1.1, four client identities | HTTP 403 each time; 3,065 response bytes | TLS handshake failure, curl exit 35; no HTTP response |
| Same requests through the existing system proxy, native and compatibility identities | Same HTTP 403 | Same TLS handshake failure |
| IPv4 and TLS 1.2 transport comparisons | Same HTTP 403 | Same TLS handshake failure |
| Independent Python/OpenSSL 3.5.9, normal certificate verification | TLS 1.3 completes, then HTTP 403; local classification identifies a CDN/security HTML page | `SSLEOFError` / `UNEXPECTED_EOF_WHILE_READING` during handshake |

The installed Windows alternative client's saved source URL differs from these
Swirl definitions. That local cached profile was not a successful comparison of
the same link. It does not contradict the owner's later Loon evidence.

## Follow-up after the Loon success report

The following bounded requests used the owner's confirmed source A link. Its
explicit nested original subscription URL was also tested after the owner
authorized that comparison; it was not sent to a new conversion service. Saved
URLs were not rewritten, and redirects were not followed. Original-link
comparisons used those URLs verbatim; the final outer-target-only diagnostic
is described separately below.

| Controlled comparison | Observed Windows result |
| --- | --- |
| Published complete Loon/991 CFNetwork identity, HTTP/1.1, original conversion link and nested original link, direct and existing system-proxy routes | HTTP 403 and 3,065-byte HTML responses in all four cases |
| Isolated curl_cffi 0.17.0, Safari 27 iOS TLS fingerprint with that Loon identity, HTTP/2 and HTTP/1.1; direct and proxy comparisons | HTTP 403; no subscription INI returned |
| Chrome 152 TLS/HTTP fingerprint over HTTP/2 | HTTP 403; no subscription body returned |
| Nested original link, Safari 27 iOS TLS fingerprint and Loon identity over HTTP/2, direct and proxy routes | HTTP 403; no subscription body returned |
| Current Windows resolution compared with trusted HTTPS DNS | Windows returned a Clash fake-IP and no IPv6 address; the trusted A-address set differed |
| Individual direct requests pinned to a trusted HTTPS-DNS address, preserving hostname, SNI and certificate verification | Both original conversion and nested original links still returned HTTP 403 |
| One HTTP/3-only comparison using the same Safari 27 iOS profile and published Loon identity, through the existing port 7897 SOCKS5 UDP association | Connection failure, curl code 7; no HTTP response or subscription body, and no fallback to HTTP/2 or HTTP/1.1 |
| One explicitly authorized same-service output-format comparison, changing only the outer `target` value from `loon` to `clash` | HTTP 403, 3,065-byte HTML; normal certificate verification succeeded; no subscription body or parser input |

For the last output-format comparison, the official subconverter contract was
checked first: `target` selects the generated configuration type. The outer
query contained only the expected format/conversion parameters, one nested
source URL and no signature/HMAC or unknown parameter. Only that outer target
value was replaced in memory; every other raw query field and the encoded
nested source URL were checked byte-for-byte unchanged. The existing saved
subscription was checked unchanged. This was one diagnostic request to the same
authorized conversion service, not automatic product rewriting or a saved URL
change. It also returned HTTP 403, so no working alternative-format path was
established and no response body was retained or imported.

The 403 responses carried Cloudflare server/CF-Ray headers and HTML access-denial
content. Dynamic response data prevents treating equal body lengths as identical
response bytes. Those observations identify the response layer, not the exact
access rule or the reason the phone succeeds. Safari/Chrome fingerprint
comparisons are diagnostic approximations, not execution of Loon's actual
CFNetwork implementation.

The live production Mihomo instance was inspected through its existing Windows
named-pipe API using read-only GET requests. During one source A request through
port 7897, its connection record matched the destination host and reported:

- Current mode: `rule`; existing TUN: enabled.
- Matched rule type: `Match`; transport: TCP.
- Three entries in the actual proxy chain; `DIRECT` was absent.

Thus this observed request really used a proxy chain. A hypothetical rule-based
DIRECT bypass is not an established cause, and no bootstrap or alternate-core
fallback was added on that premise. The phone's actual per-request route,
headers, resource cache and protocol negotiation have not been captured, so the
owner's same-Wi-Fi/same-node report does not by itself supply an identical wire
request for comparison.

The one HTTP/3-only attempt also produced a live UDP connection record matching
the destination host: `Match`, a three-entry proxy chain, and no `DIRECT` entry.
It did not establish a working HTTP/3 connection. That failure can reflect the
tested QUIC/UDP route or client stack and does not prove which protocol Loon
used, or rule out a phone-specific transport difference. The test was not
repeated with guessed identities or silent protocol fallbacks.

HTTP version, the tested TLS fingerprints, the tested identities and the
individual DNS-address comparisons have not explained the difference. The
investigation remains open: the owner has supplied the version and a fresh
successful manual update, while the phone's exact successful resource request
has not been reproduced on Windows. The published Loon/991 identity used in the
controlled tests is not claimed to be the actual identity of the reported
“3.53” installation. Further requests require a specific remaining hypothesis
rather than repeating this matrix or asking the owner to guess headers.

None of these checks changed the Windows system proxy, routes, DNS, TUN,
Mihomo rules/mode, selected node, current installation or running Swirl process.

## Mature references reviewed before implementation

- [Clash Verge Rev issue #7752](https://github.com/clash-verge-rev/clash-verge-rev/issues/7752): independently compare the same subscription across HTTP clients and routes before attributing HTTP 403 to credentials or User-Agent negotiation.
- [Clash Verge Rev profile update flow](https://github.com/clash-verge-rev/clash-verge-rev/blob/dev/src-tauri/src/feat/profile.rs): distinguish the configured download route from explicit alternative routes and retain a failed update as a failure.
- [Qt 6.12 QNetworkRequest](https://doc.qt.io/qt-6.12/qnetworkrequest.html): HTTP response attributes and request policy are distinct from Qt network error enums.
- [Loon's published client identities](https://github.com/Loon0x00/Loon4Mac/releases): use a documented complete resource-download identity for controlled comparison instead of guessing arbitrary User-Agent strings.
- [Loon's official App Store version history](https://apps.apple.com/nl/app/loon/id1373567447?platform=watch): version 3.5.3 is listed; this does not expose the phone's build-specific network request.
- [Sub-Store's Loon resource-parser notes](https://github.com/sub-store-org/Sub-Store/wiki/Loon-%E8%B5%84%E6%BA%90%E8%A7%A3%E6%9E%90%E5%99%A8%E8%AF%B4%E6%98%8E): client identity and client-side resource handling can affect a subscription request; successful parsing and successful resource download are separate observations.
- [curl_cffi](https://github.com/lexiforest/curl_cffi): use an isolated existing HTTP/TLS implementation for fingerprint and HTTP/2 comparisons. This diagnostic dependency is outside the product and is not bundled with Swirl.
- [curl_cffi HTTP/3 proxy documentation](https://github.com/lexiforest/curl_cffi/blob/main/docs/advanced.rst): use one explicit HTTP/3-only SOCKS5 UDP-association comparison and distinguish connection failure from an HTTP response.
- [Mihomo control API documentation](https://github.com/MetaCubeX/Meta-Docs/blob/main/docs/config/general.en.md): inspect the existing named-pipe API without changing the live network configuration.
- [Official subconverter parameter contract](https://github.com/tindy2013/subconverter/blob/master/README-cn.md): `target` chooses the output configuration type; check that contract and preserve the nested source before one explicitly authorized format comparison.

Only these design and diagnostic principles were used. The Swirl changes were
independently written; no implementation was copied from these projects.

## Software corrections

- A real HTTP 403 remains labeled HTTP 403 and is described as a server/CDN
  access refusal. Qt error codes are explicitly labeled separately; the former
  misleading phrase “not an HTTP status code” no longer follows a real HTTP
  status.
- A remote close has its own description. When no status was received, the UI
  says that no HTTP response arrived instead of displaying `HTTP 0`.
- A failed source with no saved nodes no longer claims to retain an earlier
  valid node set. A source that does retain nodes reports the actual saved
  count. Saved nodes are not represented as verified live connectivity.
- Download failure continues to preserve the encrypted source/catalog and
  existing nodes. Certificate verification, HTTP/1 policy, signed URL handling,
  origin restrictions, size/time limits and bounded negotiation are unchanged.
  No extra retry is added for HTTP 401/403 or a TLS failure.

## Validation scope

The following Windows Qt 6.12/MinGW component suites were compiled and executed
with the verified pinned OpenSSL 3.5.9 runtime and an isolated local test root:

| Suite | Passed | Failed | Skipped |
| --- | ---: | ---: | ---: |
| SwirlImportTests | 78 | 0 | 0 |
| SwirlXrayDownloadTests | 35 | 0 | 0 |
| SwirlSubscriptionFormatTests | 7 | 0 | 0 |
| SwirlQtNetworkPolicyTests | 11 | 0 | 0 |
| Total | 131 | 0 | 0 |

The Qt XML reports were parsed to verify the absence of failures and skips.
Both new first-failure rows (HTTP 403 and remote close without HTTP) passed.
The component coverage checks exact encrypted-file retention, absence of private
request data in diagnostics, HTTP/Qt error namespaces, bounded negotiation,
certificate rejection, origin/redirect boundaries and the existing HTTP policy.

At this build the paired runtime reported source SHA
`34740282937fdf25178db1e02b311fdd8b755af2` and build ID
`5d97ce27fc18a2a2ea0e1e361abe5f20366c7282679559d08e81799a6364a6e1`;
the subscription diagnostic/UI edits were present in the working tree.
The final integrated delivery must state its own source/runtime identity and
any later relevant rebuilds or targeted reruns. These results do not certify
later parser edits automatically.

The added real-UI assertions cover a failed refresh retaining one saved node
and a first failed source with zero saved nodes. Their execution result must be
reported separately from these four component suites. No successful real source
A response has reached the parser in this investigation; anonymous format
fixtures cannot be represented as a restored real Shadowsocks import.
