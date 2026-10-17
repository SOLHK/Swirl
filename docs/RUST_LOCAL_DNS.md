# Rust system/custom DNS and local host mappings

**Scope update, 2026-10-17 UTC:** this document describes shared resolver/host behavior
and the original system/UDP/TCP DNS stage. Rust also implements strict DoT and
HTTP/1.1 DoH. See the [current encrypted-DNS overview](../core/README.md#encrypted-dns-dot-and-http11-doh),
the [historical DoT stage](RUST_DOT.md), and
[earlier DoH/public-network evidence](RUST_WS_VALIDATION_20261017.md).
The old DoT-only document's HTTPS exclusions belong to its earlier scope.
Current regression counts and source/CI identities are tracked in
[the policy-stage validation](RUST_POLICY_VALIDATION_20261017.md).

The existing DNS page can now configure the Rust runtime's system resolver and
exact local domain-to-IP mappings, or up to four custom IP DNS servers. The UI layout, controls and stored source
configuration are unchanged. This implementation does not write system DNS,
system hosts files, certificates, routes or proxy settings.

## Executed settings

- System DNS mode (`mode: 0`), with empty custom/encrypted server fields.
- Custom DNS mode (`mode: 2`): comma-separated IPv4/IPv6 servers, port 53 in the
  existing UI. Typed IR `dns.servers` accepts IP socket addresses, allowing
  isolated non-privileged test ports. DNS requests use Swirl's Rust wire parser
  and Tokio sockets, not the OS lookup API or an external proxy/resolver core.
- Strict encrypted DNS reuses the existing `mode: 0` settings container with
  traditional servers empty and an explicit `tls://` or `https://` URL. The Rust
  resolver then executes DoT/DoH rather than OS network lookup. IP endpoints or
  an exact local mapping for the resolver name supply bootstrap; details and
  separate authentication-name verification are in the current overview above.
- Exact domain names mapped to one IPv4 or IPv6 address, case-insensitively.
- Local mappings for DIRECT targets and for locally resolved proxy server names.
- The existing page's force-local-mapping toggle (`respectRules`) maps to the
  typed Rust setting `dns.force_proxy_hosts`. When true, a mapped proxy target
  is sent upstream as an IP. When false, a normal domain/port/default proxy route
  keeps its original domain so the upstream resolves it.
- An IP routing rule that explicitly requires resolution still uses the local
  mapping and pins the matched address, independently of that toggle.

The page labels this toggle as forcing local DNS mappings for proxy requests;
that is the behavior implemented here. It is not a claim that Rust implements
Mihomo's separately defined `respect-rules` DNS transport-routing setting.
The original domain remains in HTTP Host headers and connection diagnostics.
Application TLS bytes and the configured upstream TLS verification/SNI name are
not changed by an address override. No certificate verification is disabled.

The OS resolver still reads the OS hosts file, so `useHosts: false` is rejected
in pure system mode when encrypted DNS is absent. In custom or encrypted mode
the switch controls a bounded snapshot of the
OS hosts file read at configuration time; explicit application mappings take
precedence. No system lookup fallback is performed in custom mode.
Extra/system-combined server mode, simultaneous plaintext and encrypted servers,
per-entry DNS servers, wildcard/regex mappings and unknown fields are rejected
before startup. The plaintext custom-server path described below has no TCP-only
server URL; it uses TCP when a validated UDP response requests truncation retry.
DoT/DoH are separate implemented encrypted paths. Fake-IP and a local DNS listener
remain unimplemented.
Known entry IDs/comments are retained in the original stored configuration;
they are metadata, not execution instructions.

## Ownership, bounds and updates

The typed schema accepts at most 512 mappings. Names must be valid exact ASCII
domain names, not IP literals; address values must parse as IP addresses.
Duplicate names are rejected case-insensitively. Scoped IPv6 literals and
ambiguous/malformed options fail rather than being silently normalized away.

Each immutable runtime plan owns its configuration, mapping table and system
DNS cache together. A validated configure operation replaces this whole plan
atomically. New TCP/UDP associations use the new resolver; established streams
and UDP associations keep the old plan. Rejected updates keep the old plan and
generation. Node/group-only API selection shares the existing resolver.

Across all generations of one core, unresolved OS lookups share eight permits.
A timed-out/cancelled OS lookup holds its permit until the underlying lookup
actually finishes. Each plan's cache remains bounded to 256 entries, with a
30-second policy lifetime for system results and at most 16 addresses per query.
Custom/encrypted positive results instead use the bounded authoritative TTL;
DoH also applies its HTTP cache-age restrictions. Local
mappings are evaluated before the OS cache and do not consume lookup permits.
System-cache expiration is a policy bound rather than authoritative DNS TTL.

Cache identity is now the lowercase hostname, independent of the application's
destination port. Cached IP addresses receive the requested port on return, so
HTTP and HTTPS to the same hostname can share a lookup. Positive entries store
the available address set; an empty other family is not a claim that this
family's records do not exist. Configuration generations still own separate
caches, and local mappings still take precedence.

## Custom DNS wire behavior

`core/crates/swirl-dns/src/wire.rs` implements the query/response protocol in Rust.
ring supplies random transaction IDs only. Each lookup uses fresh connected UDP
sockets; responses must match the server peer, transaction ID and complete
question. A/AAAA queries are bounded and concurrent. Truncation triggers a framed
TCP exchange with the same explicit server and full response validation. Maximum
response size is 16 KiB, total records 128, addresses retained 16, compressed-name
decode steps 128, in-message CNAME chain 8 hops and CNAME follow-up queries 8 per
family. Cyclic/forward compression, conflicting aliases, unrelated addresses,
bad lengths and trailing data are rejected or excluded from the answer.

Server failures/timeouts may try the next explicitly configured server; NXDOMAIN
is terminal. No failed custom query falls through to the system resolver.
Each plaintext server gets at most 900 ms including its A/AAAA and CNAME/TCP work, and all
servers together are bounded to 3 seconds after admission. Both address-family
queries must complete successfully (NODATA is allowed); a broken family may make
the lookup fail even if the other family returned addresses. That is a current
availability limitation, not evidence of full DNS interoperability.

Positive cache lifetime is the minimum relevant address/CNAME TTL, capped at
300 seconds and reduced by lookup elapsed time. TTL zero is not cached.
Validated NXDOMAIN and combined A/AAAA NODATA can now use a negative cache:
only a structurally valid IN SOA in the authority section, covering the actual
CNAME terminal name, supplies the lifetime. It is bounded by both SOA TTL and
SOA MINIMUM, relevant CNAME TTLs and the 300-second local maximum. Absent,
unrelated, malformed or zero-lifetime SOA data cannot create a reusable negative
entry. Inconsistent A/AAAA answers fail rather than poisoning the cache.
DoT and DoH use the same DNS parsing and combination logic; DoH HTTP Age and
cache restrictions also constrain negative results.

Timeouts, SERVFAIL, REFUSED and transport errors remain failures, never
NXDOMAIN. RFC 9520 failure-cache suppression is not implemented by this stage;
neither are EDNS negotiation or DNSSEC validation. DNS split,
automatic domain bootstrap and proxy-routed encrypted DNS also remain separate
future work; the existence of DoT/DoH does not provide those features.
System-hosts snapshots are bounded to 1 MiB and 4096 names; comment encoding does
not invalidate otherwise ASCII entries. Reconfiguration replaces this snapshot.
The resolver does not modify any OS files or settings.

Custom DNS resolves DIRECT targets, proxy server names and rule-required local
lookups. Ordinary proxy target domain names still go to the proxy unless the
existing mapping or resolving-rule semantics require an IP; custom DNS alone
does not silently change remote target resolution into local resolution.

Primary references: [DNS wire format (RFC 1035)](https://www.rfc-editor.org/rfc/rfc1035.html),
[negative answers and SOA lifetime (RFC 2308)](https://www.rfc-editor.org/rfc/rfc2308.html),
and [the separate resolution-failure cache requirements (RFC 9520)](https://www.rfc-editor.org/rfc/rfc9520.html).
The implementation is independently written for the existing Swirl resolver.

## Verification

Rust tests verify case-insensitive mapping, IPv4/IPv6, independent caches with
shared concurrency budget, ambiguous configuration rejection and preservation
of UDP mappings/selector decisions across updates. Independent Python peers
verify both positions of the proxy toggle, mapped upstream hostnames with
verified TLS names, and live mapping updates while an old TCP stream stays open.
Qt tests exercise the actual DNS settings map, proxy/direct forwarding and
rejection of unsupported options through the existing engine facade.
An independent loopback Python DNS peer additionally covers positive expiration,
zero TTL, CNAME follow-up, fragmented TCP retry, declared-server failover,
NXDOMAIN, wrong identity/question, trailing data, silent timeouts and UDP target
resolution. Qt validates IP server mapping and host precedence without opening
port 53 or changing the host's DNS configuration.

All network fixtures use loopback and synthetic names/credentials. No private
subscription refresh, production DNS change or real-provider DNS acceptance is
implied by these tests. Complete product DNS migration remains unfinished.
The encrypted suites are `tools/tests/test_dns_tls.py` and
`tools/tests/test_dns_https.py`; their source presence is not itself a result for
a new commit. Earlier strict public DIRECT/DoH checks and current regression
execution are recorded separately in the validation documents linked above.
The new `tools/tests/test_dns_negative.py` exercises negative caching through
independent loopback DNS peers and actual native control/forwarding calls;
the current-stage results belong to the exact tested commit recorded in
`docs/CONTINUE_DEVELOPMENT.md`.
