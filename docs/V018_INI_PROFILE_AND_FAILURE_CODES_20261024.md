# Swirl 0.1.8: restricted complete INI and useful failure codes

This stage follows the first network candidate `2a30ba0df8f233388ef9ad4f30a92fcf775bff61`.
It does not replace the user's browser, Codex account or private-provider
acceptance, and does not claim general support for every Surge/Loon/Surfboard
profile.

The first candidate's Windows run `40082951005` stopped because its script
created the isolated root path variable but not the directory. Tests correctly
refused that invalid root. No installer was produced or accepted. The script
now creates the directory first. Existing compilation and failure evidence are
kept; a successful re-run on the final commit is required.

The read-only current Codex configuration also already has
`respect_system_proxy = true`. Re-enabling that existing value is not a fix,
and its current file value does not prove an older running process reread it.
The existing fresh-child launcher remains the user-operated diagnostic path.

## Complete profiles

The complete original INI document now reaches portable Rust for network
semantics. The former Qt-only projection is removed. The restricted mapping
uses the existing Rust DNS/rule/group schema and validates atomically before
persisting/applying nodes and network configuration together.

Supported explicit semantics include:

- Ordinary proxy node parameters through the existing strict node importer.
- Plain DNS **or** supported encrypted DNS, with an explicitly specified IPv6
  family. Exact host-to-IP mappings are supported; wildcard/alias host entries
  remain rejected.
- Manual `select` groups with exact local references, uniqueness, bounded
  nesting and cycle checks.
- Existing supported domain, IP/CIDR and port rules, plus an explicit final
  rule. Quoted fields cannot inject additional comma-delimited native grammar.
- Clash `allow-lan: false` as the explicit restriction already met by the
  fixed loopback Rust listener. True, strings, numbers and null remain rejected.

Source DNS fields retain their transport requirement: `dns-server` accepts
literal IPs, `doh-server` accepts HTTPS only, and `encrypted-dns-server` accepts
supported HTTPS/TLS resolvers only. A bare IP in an encrypted field is rejected,
not converted into UDP. Encrypted resolvers still require validated bootstrap
and TLS settings. Mixed plaintext/encrypted fallback behavior and custom
plaintext ports remain unsupported. Independent review caught the initial
cross-channel ambiguity before commit; the final guard has positive encrypted
projection and negative cross-channel/bootstrap regressions.

Unknown general/section fields, scripts/MITM/rewrites, local files, additional
listeners, interface/TUN/route modifications, remote include/updater directives,
mixed/fallback DNS requirements and unsupported automatic group semantics
remain explicit import failures. In particular, a downloaded `MANAGED-CONFIG`
URL is not silently followed or substituted for the subscription the user
authorized. Subscription refresh continues using the existing user-configured
source and schedule. Generic INI parsing does not guess different clients'
default IPv6 or URL-test scoring/timeout behavior.

The node-only path retains the existing DNS/rules/groups. Rejection of a full
profile retains the old durable network snapshot and source-owned nodes.

After durable subscription updates, messages now distinguish parsed records
from saved nodes after semantic duplicate merging. The unsupported count uses
the same actual Rust eligibility rows as the node list. Manual imports describe
processed records rather than incorrectly counting all pre-existing manual
nodes as newly saved.

## Failure classification

TCP failures retain typed fixed codes for refusal, reset, abort, timeout,
unreachable network/host and permission denial. If different resolved addresses
fail for different reasons, the result remains `UpstreamConnectFailed`; it does
not select whichever OS error happened to finish last. Address scheduling,
deadlines and cancellation are unchanged.

TLS failures distinguish invalid certificate name, expiry, not-yet-valid,
unknown issuer, revocation and other invalid-certificate states. Handshake EOF,
reset, abort, refusal, I/O timeout and broken pipe are separate fixed codes.
Unrecognized errors retain the existing generic code. Classification uses typed
Rustls/I/O errors only, never their Display/Debug text, which may contain
private names. No certificate validation is disabled.

The standalone connectivity diagnostic's closed output allowlist recognizes
the new fixed TCP codes without admitting arbitrary strings. Its Python-only
fallback keeps its existing generic scheduler results. Independent peer tests
assert the specific code only when the observed cause is unambiguous.

These codes identify observed failure layers. A refused or reset connection
alone does not prove that a provider's server is unavailable; intermediaries,
local policy and routing still need correlation. Old diagnostic bundles cannot
retroactively acquire these new distinctions or per-node references.

## Verification

Rust inspection/profile/API tests cover cross-format TCP equivalence, raw INI
projection, unsupported fields and safety boundaries. TCP tests check mixed
failure ordering. Real controlled TLS probes exercise an unknown issuer and a
trusted chain with the wrong host name, without delivering HTTP application
bytes. Qt tests cover profile import, real controlled outbound traffic,
atomic update/rejection, source ownership and accurate deduplicated counts.
Exact final CI artifacts remain authoritative for the packaged commit.

Primary references: [Surge general settings](https://manual.nssurge.com/profile/general.html),
[Surge manual groups](https://manual.nssurge.com/policy-groups/select.html),
[Loon general settings](https://nsloon.app/en/docs/General/), and the pinned
Rustls/Tokio-Rustls typed error definitions in `core/vendor/rustls` and the
locked dependencies. Source dialect differences are kept explicit rather
than normalized to invented defaults.
