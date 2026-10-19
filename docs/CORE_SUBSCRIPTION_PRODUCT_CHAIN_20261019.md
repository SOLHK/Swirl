# Subscription → saved selection → native forwarding (2026-10-19)

## Current scope and branch

Continue only on `work/core-completion-20261017`. The starting remote source was
`292bcb29cbcd9a1b35d33380c0fd4e0fe07b499b`; concurrent font change
`8e0f07eed972b814a00bc3581960b423ecf699be` was fetched and retained before the
first source delivery. No UI/font source is part of this Core change.

The fixed acceptance remains **79 items / 6 accepted / weighted 10.83%**.
Individual import, runtime and peer tests do not complete an entire frozen item.
REALITY R3 and Vision R2 component work is retained. The production async
REALITY adapter, DirectReady, TLS/socket ownership transfer and combined
REALITY/Vision product path remain unsupported.

The user expressly authorized one new subscription on 2026-10-19, independently
of the older ten-minute capture window. It was fetched once into private scratch,
outside Git, without a conversion service. Redacted inspection found 59 VLESS
TCP/REALITY nodes, 55 also declaring Vision. All 59 remain non-executable native
candidates. No credentials, URLs, original documents or provider node requests
are published or embedded in CI. Parsed is not authenticated or connected.

## S1: parameter boundaries and reliable Windows test fixtures

Actual changes use existing importer/IR/adapter code:

- Explicit invalid `network` values no longer become default TCP.
- Both `port` and `server_port` are checked; conflicting aliases fail.
- Nested/top-level ALPN cannot hide a conflicting value or ordered list. URI
  comma-separated ALPN becomes the ordered native list while raw URI is retained.
- Implicit HTTPS/SOCKS TLS/Trojan TLS cannot be silently removed or contradicted.
- Trojan username declarations that cannot be represented by password-only
  authentication fail with a capability error; original values remain available.
- Qt rejects null/non-string credentials, cipher and TLS names before scalar
  extraction can erase their types. Unsupported non-SS cipher/Trojan username
  parameters fail native conversion instead of disappearing.
- New Windows Qt tests destroy/recreate the encrypted NodeStore and compare
  supported WSS/IPv6/SNI/ALPN/false/empty values and retained unknown null/false
  extensions through native configuration. These are conversion tests, not a
  claim that the tested WSS endpoint was contacted.
- Pure SS/DNS port-allocation error tests no longer combine a mocked exclusion
  table with real random Windows binds. They retain real unbound descriptors for
  close/ownership assertions. Actual socket forwarding tests remain actual;
  access denial is not turned into a retry or ignored exception.

Six new Rust regressions reproduce previous defects before the fixes. The final
subscription crate has 64 tests. Full workspace and independent-peer local
commands/results are recorded in `evidence/subscription-product-chain/s1-local.json`.
Windows Qt validation requires the corresponding new-source Actions run.

## Baseline CI is not new-source evidence

At source `292bcb29cbcd9a1b35d33380c0fd4e0fe07b499b`,
[Rust 39263795753](https://github.com/SOLHK/Swirl/actions/runs/39263795753)
had Linux/macOS success and Windows failure. Windows Rust fmt/check/clippy/test/
release succeeded, then the SS allocation test hit WinError 10013 on a real
synthetic TCP bind. Subsequent Qt/native application steps were skipped.
[Core validation 39263795738](https://github.com/SOLHK/Swirl/actions/runs/39263795738)
succeeded but does not replace Windows Qt evidence. Original failure is retained;
new-source CI identities and terminal results are added after their actual runs.

## Next integration steps

Connect the existing Qt controller to independent Python proxy A/B and separate
HTTP/HTTPS targets, starting with real raw subscription text. Verify actual
encrypted persistence/object recreation, selection rollback, existing-session
isolation, declared node-name/group rules and explicit DIRECT/REJECT. The portable
Rust-host suite must be identified separately from the Windows product-object
suite. Keep strict certificate checks and never fall back on request failure.

## Primary references consulted

- [Mihomo parser](https://github.com/MetaCubeX/mihomo/blob/Meta/adapter/parser.go)
  and [HTTP outbound](https://github.com/MetaCubeX/mihomo/blob/Meta/adapter/outbound/http.go):
  protocol dispatch and TLS boundary; no source copied.
- [XTLS share-link ALPN](https://github.com/XTLS/Xray-core/discussions/716):
  ordered comma-delimited URI ALPN.
- [sing-box TLS](https://sing-box.sagernet.org/configuration/shared/tls/) and
  [transport](https://sing-box.sagernet.org/configuration/shared/v2ray-transport/):
  explicit TLS names, ALPN and transport type semantics.
- [sing-box selector](https://sing-box.sagernet.org/configuration/outbound/selector/):
  member identity and explicit existing-connection interruption policy.
- [Trojan protocol](https://trojan-gfw.github.io/trojan/protocol): password-hash
  authentication; extra username has no mapped wire meaning.
- CPython `unittest.mock` and its socket error tests: isolate injected OS errors
  while retaining ownership/cleanup assertions and separate integration tests.
