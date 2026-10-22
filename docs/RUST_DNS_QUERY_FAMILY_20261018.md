# Native DNS query family: bounded implementation, 2026-10-18

A native explicit DNS configuration can now request only A records through UDP, validated TC-to-TCP retry, DoT or DoH. Existing configurations keep A+AAAA. This is a prerequisite for defined subscription DNS mappings, not complete Clash or other client DNS compatibility.

## Contract

`dns.query_family` is a strict string: `dual` (default, omitted on serialization) or `ipv4_only`. Objects, booleans, null, unknown values and duplicate fields are rejected. Both Config validation and direct Resolver construction reject nondefault policy without an explicit upstream. The implementation never calls OS lookup and filters afterward to simulate A-only. IPv6 literals, exact custom/system-host mappings and IPv6 resolver endpoints retain their separate meanings; proxy-side remote resolution is not controlled by this local resolver option.

Single-family resolution uses only the actual A response. Valid SOA NODATA and NXDOMAIN retain their real TTL, including CNAME minima and DoH Age/no-store. Unproven empty NODATA can fail over; NXDOMAIN without SOA is terminal but not cached; valid zero-TTL denials are terminal but queried again. Dual-family combination and existing timeout, cancellation, capacity, authentication and fallback boundaries are unchanged. Each immutable configuration receives a fresh cache while retaining the shared lookup permit budget.

Qt maps `queryFamily` without new controls. Legacy DNS-page partial edits preserve the current policy; raw input is validated before normalization or persistence. Invalid edits keep memory and the DPAPI/QSaveFile store unchanged. Full configuration replacement uses its own defaults. The retained compatibility build refuses a persisted native policy both on settings Apply and at adapter startup; it cannot silently ignore or delete it.

## Executed validation

- Rust fmt/check/clippy with warnings denied and full workspace tests: 138 passed, 0 failed.
- Independent Python DNS suite: 30 passed, 0 failed, all loopback. New paths include A-only over UDP, TCP retry, DoT/DoH, actual IPv6 upstream bindings, CNAME, SOA expiry, no-SOA NXDOMAIN, zero TTL, DoH Age/no-store and same-host configuration changes. Existing dual tests remain.
- Existing independent strict DoT 11 and DoH 9 tests passed.
- Full Windows Swirl and native Qt tests built; Qt 38 passed, 0 failed, 5 separate-peer hooks skipped. No new Qt wire-level DNS peer fixture was added; Qt mapping/persistence and native resolver wire tests are distinct evidence.
- Compatibility settings/startup protection: 4 Qt results passed (including init/cleanup), and its new CTest passed. CI includes this guard before its unchanged final native peer suite.
- Development workflow checks: 19 ran, 1 existing symlink-privilege skip, 0 failures.

[Structured evidence](evidence/RUST_DNS_QUERY_FAMILY_20261018_VERIFIED.json) includes source, binary and log hashes. Implementation commit `f81eab6e2eaf5a2d9f1f538a4ce04cde268797c0` passed all three platforms in [Rust CI 39113224090](https://github.com/SOLHK/Swirl/actions/runs/39113224090) and [implementation validation 39113224086](https://github.com/SOLHK/Swirl/actions/runs/39113224086). MinGW's existing release linker warning is recorded, not suppressed.

## Failures found and repaired

The initial test correctly failed on the old implementation (4 transport cases rejected the unknown field). Read-only review found serde's object-form unit enum acceptance and the compatibility build's persisted-policy bypass; both received regressions. A fixture edit mistakenly referenced an undefined ipv6 variable in the port-allocation test and left the new UDP peer on IPv4. The initial IPv6 test therefore did not prove IPv6 UDP; its evidence is superseded by explicit ::1 socket assertions and the successful full 30-test rerun. The failure log remains. The workflow validator also rejected an appended step after its strict final Qt menu; the new step was moved before that menu and the unchanged validator passed.

## References and remaining work

Reviewed [RFC 3596](https://www.rfc-editor.org/rfc/rfc3596.html), [RFC 2308](https://www.rfc-editor.org/rfc/rfc2308.html), [RFC 7766](https://www.rfc-editor.org/rfc/rfc7766.html), [RFC 8484](https://www.rfc-editor.org/rfc/rfc8484.html), [Hickory's query-family strategies](https://docs.rs/hickory-resolver/0.26.3/hickory_resolver/config/enum.LookupIpStrategy.html) (MIT OR Apache-2.0) and [Tokio lookup_host](https://docs.rs/tokio/latest/tokio/net/fn.lookup_host.html). This change independently implements Swirl logic; no resolver/proxy engine or source was copied, and no dependency/license was added.

Complete subscription DNS still needs explicit hosts/localhost precedence, routing/no-resolve behavior, bootstrap and upstream policy mapping. Fake-IP, DNS split and TUN remain incomplete. No provider refresh or real-node request occurred here. The 08:25:51 window ended with 0 requests/0 captures due execution approval failure; the existing encrypted cache remains intact. Fixed weighted acceptance remains 10.83%.

Next user-directed task: use mature converter architectures as references, then reproduce and fix concrete Qt/Rust subscription-validation discrepancies (typed boolean values and canonical alias conflicts in Trojan INI/URI) before expanding formats. Preserve existing IR and atomic import; implement supported semantics rather than only accumulating rejection paths.

Compatibility protection applies to binaries built from this implementation or later. Historical older releases cannot be assumed to recognize the new field. Complete configuration replacement deliberately uses the replacement defaults when the policy is omitted.
