# Rust system DNS and local host mappings

The existing DNS page can now configure the Rust runtime's system resolver and
exact local domain-to-IP mappings. The UI layout, controls and stored source
configuration are unchanged. This implementation does not write system DNS,
system hosts files, certificates, routes or proxy settings.

## Executed settings

- System DNS mode (`mode: 0`), with empty custom/encrypted server fields.
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

The OS resolver still reads the OS hosts file, so `useHosts: false` is rejected.
Custom server mode, extra server mode, nonempty custom/encrypted server fields,
per-entry DNS servers, wildcard/regex mappings and unknown fields are rejected
before startup. There is no DoH, DoT, DNS-over-TCP, Fake-IP or DNS listener here.
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
These are policy bounds, not authoritative DNS TTL handling.

## Verification

Rust tests verify case-insensitive mapping, IPv4/IPv6, independent caches with
shared concurrency budget, ambiguous configuration rejection and preservation
of UDP mappings/selector decisions across updates. Independent Python peers
verify both positions of the proxy toggle, mapped upstream hostnames with
verified TLS names, and live mapping updates while an old TCP stream stays open.
Qt tests exercise the actual DNS settings map, proxy/direct forwarding and
rejection of unsupported options through the existing engine facade.

All network fixtures use loopback and synthetic names/credentials. No private
subscription refresh, production DNS change or real-provider DNS acceptance is
implied by these tests. Complete product DNS migration remains unfinished.
