# Windows native DNS failure-cache stage

**Final verified source: `b903b8b1d9c5e0c40c3dee5033447900665d1835`.**
[Core 39097773884](https://github.com/SOLHK/Swirl/actions/runs/39097773884) and
[App 39097773891](https://github.com/SOLHK/Swirl/actions/runs/39097773891) both
finished **success**. The final handoff commit changes documentation/evidence
only; it is not a newly built source revision. [Structured evidence](evidence/RUST_DNS_FAILURE_CACHE_20261018_VERIFIED.json).

| Environment | Rust/checks/Release | Python | Qt |
|---|---|---|---|
| User Windows GNU | 128 passed; fmt/check/strict Clippy/Release passed | 205 unique cases: 202 passed, 3 explicit skips | Full app built; CTest 1/1; four independent peers passed |
| Hosted Linux | 128 passed; all build gates passed | 167 passed, four Qt skips | Not run |
| Hosted macOS | 128 passed; all build gates passed | 167 passed, four Qt skips | Not run |
| Hosted Windows MSVC | 128 passed; all build gates passed | 203/205 passed after four Qt followups; two optional skips remain | CTest 1/1, 6.69 seconds; four independent peers passed |

Actual implementation/test files changed:

- `core/crates/swirl-dns/src/lib.rs`: bounded failure cache and resolver tests.
- `core/crates/swirl-dns/src/wire.rs`: separate cached-failure outcome.
- `tools/tests/test_dns_negative.py`: independent failure/recovery and port-allocation tests.
- `tools/tests/dns_peer.py`: bounded Windows reserved-port handling in the test peer.
- Private repository `scripts/test_native_core.py` and `scripts/test_native_core_unit.py`:
  Windows executable discovery and identity/rejection tests. No Qt/C++/QML changes.

Private final documentation HEAD is `f0b69bc7324ff2972c29beaee26fe19c47d110d3`,
following code `0a92d17` and actual Linux failure-evidence commit `1374be0`.
All five ciphertexts match the earlier recorded hashes; no secure archive changed.

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

## First CI result and Windows fixture correction

Implementation commit `cafdd62a556165bb5796fcac7f9fd8ef95643143` was pushed and
read back. [Core run 39097322603](https://github.com/SOLHK/Swirl/actions/runs/39097322603)
finished **failure**: Linux and macOS passed, but Windows failed three existing
DNS tests while constructing the Python TCP listener (`WinError 10013`), before
any Rust DNS request. [App run 39097322594](https://github.com/SOLHK/Swirl/actions/runs/39097322594)
passed. These failures remain part of the record.

The paired UDP/TCP fixture already retried address-in-use eight times. Windows
can also reject the TCP half of a UDP-selected port with WSAEACCES when that port
is excluded or exclusively bound. The correction retries that specific Windows
error only after the UDP port was selected, retaining the eight-attempt bound,
socket cleanup, and all functional assertions. Initial UDP permission denial and
generic EACCES still fail immediately. No socket reuse, privileges, firewall or
product timeout changes were made. Synthetic tests cover recovery, exhaustion
and initial UDP denial, including resource release.

References consulted before the fixture correction:
[Microsoft SO_EXCLUSIVEADDRUSE](https://learn.microsoft.com/en-us/windows/win32/winsock/so-exclusiveaddruse),
[excluded-port WSAEACCES](https://learn.microsoft.com/en-us/troubleshoot/windows-server/networking/error-10013-wsaeacces-is-returned),
and [CPython socketserver](https://github.com/python/cpython/blob/main/Lib/socketserver.py).
The CI stack trace establishes a bind failure; it does not identify the runner's
specific reservation owner.

The full local desktop `Swirl` target also built successfully. Initial Python
regression was 204 cases / 197 passed / seven skipped; the four Qt peer followups
raised actual coverage to 201 passed. The remaining three skips are unavailable
symlink privilege, optional C++ importer, and opt-in real Codex CLI. The added
Windows allocation regression raises the independent DNS suite to 23 cases.

Local public DIRECT checks for example.com and www.rust-lang.org passed TLS 1.3,
HTTP 200/301, bidirectional accounting and orderly close. The native Cloudflare
DoH check failed at `DnsTlsTimeout`. Independent Python and Rust TCP controls to
the same public bootstrap endpoint both timed out within their shared ten-second
diagnostic budget. These are public-endpoint controls, not the private SS samples.

Private helper commit `0a92d1789e5ca8bc9b09f11cd7c62d7aaac7615b` fixes Windows
`.exe` discovery; 43 helper tests passed locally. Its automatic
[private run 39097562489](https://github.com/SOLHK/Swirl-Private-Tests/actions/runs/39097562489)
used the workflow's unchanged pinned source `44488e7`, successfully decrypted and
inspected all 16 cached subscriptions, then **failed** the three fixed SS TCP
comparisons (Python 0/3, Rust 0/3; no protocol probes). The fresh redacted evidence
is in private commit `1374be0cfe6f97884ab416c48515c0adf3ff2844`. This is a new hosted
Linux run, not Windows evidence; no subscriptions were refreshed. Original
encrypted archives and Secrets remain unchanged.

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
