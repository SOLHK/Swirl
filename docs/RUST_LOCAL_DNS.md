# Rust system/custom DNS and local host mappings

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
in system mode. In custom mode the switch controls a bounded snapshot of the
OS hosts file read at configuration time; explicit application mappings take
precedence. No system lookup fallback is performed in custom mode.
Extra/system-combined server mode, nonempty encrypted server fields,
per-entry DNS servers, wildcard/regex mappings and unknown fields are rejected
before startup. There is no DoH, DoT, TCP-only server URL, Fake-IP or DNS listener here.
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
actually finishes. Each plan's cache remains bounded to 256 entries, with the
existing 30-second policy lifetime and at most 16 addresses per query. Local
mappings are evaluated before the OS cache and do not consume lookup permits.
System-cache expiration is a policy bound rather than authoritative DNS TTL.

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
Each server gets at most 900 ms including its A/AAAA and CNAME/TCP work, and all
servers together are bounded to 3 seconds after admission. Both address-family
queries must complete successfully (NODATA is allowed); a broken family may make
the lookup fail even if the other family returned addresses. That is a current
availability limitation, not evidence of full DNS interoperability.

Positive cache lifetime is the minimum relevant address/CNAME TTL, capped at
300 seconds and reduced by lookup elapsed time. TTL zero is not cached. There
is no negative/SOA cache, EDNS negotiation, DNSSEC validation or encrypted DNS.
System-hosts snapshots are bounded to 1 MiB and 4096 names; comment encoding does
not invalidate otherwise ASCII entries. Reconfiguration replaces this snapshot.
The resolver does not modify any OS files or settings.

Custom DNS resolves DIRECT targets, proxy server names and rule-required local
lookups. Ordinary proxy target domain names still go to the proxy unless the
existing mapping or resolving-rule semantics require an IP; custom DNS alone
does not silently change remote target resolution into local resolution.

Wire-format reference: https://www.rfc-editor.org/rfc/rfc1035.html .

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
