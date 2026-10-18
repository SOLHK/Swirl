# Windows native DNS failure-cache stage

Baseline: `126d9f6fa8fc92aebabaa2ee0f971865cfa2520c`, branch
`work/core-completion-20261017`. Work, dependencies copied for reuse, build output
and diagnostics are under `D:\Codex`; existing C-drive tools are read in place.
No system proxy, route, adapter, firewall or UI settings were changed.

## Behavior and references

A completed resolution failure is retained for one second, measured from the
failure's completion. Repeated requests for the same case-insensitive hostname,
including different destination ports, receive the original static error without
querying the upstream again. Configured server failover runs before caching the
final failure. Expiration permits recovery; replacing the immutable DNS
configuration clears its cache. The existing 256-entry bound and eight lookup
permits remain. Requests waiting for a permit recheck the cache after admission.

Failure entries do not assert NXDOMAIN/NODATA and cannot overwrite an unexpired
successful/negative result or extend an existing failure's deadline. Admission
errors, cancellation, invalid packets, inconsistent answers and unproven empty
answers are excluded. TLS validation and product connection timeouts are unchanged.
The OS resolver and explicit UDP/TCP/DoT/DoH paths preserve their own error codes.

Primary research, consulted before implementation:

- [RFC 9520 sections 2 and 3.2](https://www.rfc-editor.org/rfc/rfc9520.html#section-3.2)
  distinguishes failed resolution from NXDOMAIN/NODATA, and specifies a failure
  cache duration between one second and five minutes.
- [Unbound iterator](https://github.com/NLnetLabs/unbound/blob/master/iterator/iterator.c)
  retains short-lived server failures without replacing a usable cached answer.
- [shadowsocks-rust TCP relay](https://github.com/shadowsocks/shadowsocks-rust/blob/master/crates/shadowsocks-service/src/server/tcprelay.rs)
  was also consulted for the separate TCP/protocol diagnostic boundary.

Swirl code is independently implemented; no copied implementation or new
dependency. This is a bounded stub-resolver improvement, not a claim of full
RFC 9520 recursive-resolver/DNSSEC compliance or in-flight query coalescing.
Already-running identical queries remain bounded by the existing permit pool.

## Local validation

- Existing Windows Rust GNU 1.99.1 and Python 3.12.14 / cryptography 50.0.2 reused.
- `cargo fmt --all -- --check`, locked/offline workspace check, strict all-target
  Clippy, workspace tests (128 passed), and Release library/binaries passed.
- New independent regression failed on the unmodified baseline binary: the
  repeated SERVFAIL request queried again and attempted TCP instead of returning
  the cached DNS failure. Subsequent subtest CoreLimit failures were cascading
  fixture effects, not additional product findings.
- DNS independent suite: 22/22 passed. UDP/DoT/DoH SERVFAIL and REFUSED suppression,
  expiry followed by real bidirectional TCP echo, server failover, UDP timeout
  recovery, configuration replacement, and prior SOA/invalid-packet cases passed.
- Qt Rust integration CTest: 1/1 passed, 6.71 seconds. Independent Qt SS HTTP obfs,
  VLESS, SOCKS4/4a and VLESS WebSocket tests each passed against local peers.
- Initial CMake Python-wrapper lookup failed; reused its installed native binary.
  Initial icon builder lacked Qt DLLs on PATH; supplied the existing Qt SDK bin
  directory and resumed the build. Neither required installation or code changes.
- GNU Release retains the existing linker `.drectve` warning; it was not hidden.

Full regression totals, desktop build completion and final CI identities are
recorded in the follow-up evidence commit after their actual completion.

## Subscription evidence boundary

The current private repository HEAD was verified as
`ee99c85064ca2688a35e30dc714ae56da68fad07`. Its current report contains 16 entries,
14 Clash YAML and two Base64 bodies, 1440 node records and seven distinct current
body hashes. Reading this report is not a fresh decryption of the archive.

With explicit permission, the old local DPAPI capture directory was read without
modification. Its manifest has 18 entries / 17 distinct URLs. Fourteen cached
bodies passed raw and decoded integrity checks, with 12 distinct decoded bodies.
None matches a current private-report body hash or the immutable old-window #9
body hash. The current native inspector parses 12 cache records; two are unknown.
This is not evidence that URLs, credentials or underlying node identities differ.

Exact URL normalization, node comparison and the three fixed Windows SS sample
tests remain blocked on access to the existing archive key. It is absent from
the current process environment and the authorized capture directory listing;
no key was rotated or generated. No substitute samples were called the fixed
samples. Raw local subscriptions, credentials and fingerprints were not uploaded.
Supplier subscription refresh requests: **zero**. No Linux SS failure is
reclassified as a protocol failure or a Windows test result.

## Remaining work

Finish the authorized dual-source comparison and fixed old SS Windows diagnostics
when the original key is accessible. The local corpus also exposes explicit
TCP Fast Open rejection and insecure-TLS rejection; neither was silently relaxed.
Full subscription policy/DNS/routing execution, new proxy protocols, Windows
TUN/Fake-IP and provider SS interoperability are not completed by this stage.
