# Subscription → saved selection → native forwarding (2026-10-19)

## Current scope and branch

Continue only on `work/core-completion-20261017`. The starting remote source was
`292bcb29cbcd9a1b35d33380c0fd4e0fe07b499b`; concurrent font change
`8e0f07eed972b814a00bc3581960b423ecf699be` was fetched and retained before the
first source delivery. The later concurrent font history through
`e228268dc779ed23cf674deb6fbfa249a6c8e60d` was also retained when publishing S1.
No UI/font source is part of this Core change.

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

S1 was actually pushed as
[`292df3ba9763414947ec9b5dffa7886c45a00879`](https://github.com/SOLHK/Swirl/commit/292df3ba9763414947ec9b5dffa7886c45a00879).
Its exact [Rust run 39280252948](https://github.com/SOLHK/Swirl/actions/runs/39280252948)
and [App run 39280253098](https://github.com/SOLHK/Swirl/actions/runs/39280253098)
were queued at the S2 checkpoint. Queued means unexecuted, not passed.

## S2: selected exits, ordered document rules and actual origins

The existing Qt controller, encrypted NodeStore, subscription import transaction,
Rust configuration converter and runtime are the product path. No alternate
configuration service was added.

- Selection validates the selected node against the active immutable node
  snapshot. Missing, unsupported or empty active selections cannot replace the
  current exit. A native configure failure restores the saved selection; the
  original session remains alive. Pending selection blocks the empty-ID
  reconnect entrypoint as well as named-node operations.
- New connections follow the acknowledged selection. Existing tunnels retain
  their original runtime snapshot. A subscription refresh that removes the
  selection cannot start implicit DIRECT. Leaving explicit direct mode clears
  its cached flag before native validation, so global/rule mode uses the saved
  node instead of retaining a hidden direct outbound.
- Imported rule leaves now resolve node names to the final stored UUIDs from
  the same import plan. Ordered rules may reference declared nodes, declared
  groups, DIRECT or REJECT. Foreign stored IDs/names and the editor-only selected
  node alias are rejected. Original document rules remain separately retained.
- Both rule leaves and group members reuse the existing selected-node converter,
  so routing cannot bypass its credential, transport or TLS capability checks.
  Node edits also reject scalar coercion before rewriting an encrypted snapshot.

### Test scope and executable menus

`tools/tests/test_product_subscription_chain.py` creates independent authenticated
Python proxy A/B and separately listening HTTP, HTTPS and echo origins. Positive
tests compare exact origin response bodies and peer traffic; a proxy-generated
success response alone cannot pass. Credentials and the per-run CA are synthetic.
HTTPS clients verify the CA and hostname, send SNI, and exercise TLS closure;
wrong-name TLS must fail without an origin HTTP request.

| Menu | Subscription and persistence scope | Protocol / behavior scope |
| --- | --- | --- |
| `ProductChainIntegration` | Real Rust subscription inspector; source plus typed IR saved/reloaded by a portable JSON test host, **not Qt** | Clash-shaped JSON: HTTP CONNECT, SOCKS4/4a/5, SS AES-128-GCM, VLESS TCP; SS URI/Base64 for AES-128-GCM, AES-256-GCM and ChaCha20-Poly1305; all six families reach independent HTTP and verified HTTPS |
| `ProductQtIntegration` | Real raw document → NodeImportService/NodeImporter → DPAPI NodeStore → object destruction/recreation → EngineController/ThreadedEngine → in-process Rust; **not physical GUI automation** | Separate HTTP CONNECT, SOCKS5, SS AES-128-GCM and VLESS TCP A/B fixtures; HTTP/HTTPS, saved selection recovery, old A tunnel after selecting B, imported domain/direct/reject/final rules and manual group |

Portable cases additionally verify ordered domain/suffix/keyword/IP/IPv6 CIDR/
destination-port/source rules, explicit final/manual selection, failed selection
and configure rollback, wrong authentication without another exit or origin
request, retained but unexecutable REALITY/Vision/gRPC/XHTTP/unknown fields, and
six concurrent segmented streams of 256 KiB + 17 bytes each with exact counters,
upload half-close, response tail, cancellation and cleanup. Those portable rules
are native rule fixtures on subscription-derived nodes; the Windows menu is the
proof for raw-document rule translation through Qt.

The Windows wrapper requires the optional Qt slot to actually run, rejects SKIP,
checks A/B identity and every origin path, and writes raw Qt logs plus redacted
peer records. Ordinary CTest may explicitly skip that slot without its fixture;
the dedicated wrapper is a separate required CI step. Existing URL-test,
fallback, load-balance, DNS and protocol suites remain required, with their
original scopes; their presence is not a new full-document product acceptance.

### CI and evidence rules

Both portable OS jobs, Windows Rust and App/Core validation run the new portable
menu. Windows additionally runs the actual product-object wrapper before the
complete native application build. Missing binaries, failed communication or
skipped dedicated Qt execution fail the required step. Artifacts retain exact
checked-out source SHA, binary hashes, raw test logs, counts and explicit skips.
The App menu is portable Core validation, not a Qt/full-GUI run.

The S2 local test checkpoint and final exact-source CI results must be recorded
separately. The local `/tmp` toolchain disappeared between stages; the initial
S2 rerun therefore failed before networking with missing-executable errors.
That environment failure is not a protocol result. Rebuilt binaries and their
source identity are required for the subsequent result.

The rebuilt local Release suite passed **8 portable cases**, with **1 explicit
Windows Qt skip**, in 4.584 seconds. All **44 CI regression guards** passed and
the workflow updater was idempotent. Exact S2 source blobs, binary hashes,
commands, original local logs and the earlier environment-failure limitation are
in [the S2 checkpoint](evidence/subscription-product-chain/s2-local.json).
Core source is unchanged from S1, whose five required Rust gates passed with
278 tests plus one doctest. These local results do not supply Windows Qt evidence.

## Baseline CI is not new-source evidence

At source `292bcb29cbcd9a1b35d33380c0fd4e0fe07b499b`,
[Rust 39263795753](https://github.com/SOLHK/Swirl/actions/runs/39263795753)
had Linux/macOS success and Windows failure. Windows Rust fmt/check/clippy/test/
release succeeded, then the SS allocation test hit WinError 10013 on a real
synthetic TCP bind. Subsequent Qt/native application steps were skipped.
[Core validation 39263795738](https://github.com/SOLHK/Swirl/actions/runs/39263795738)
succeeded but does not replace Windows Qt evidence. Original failure is retained;
new-source CI identities and terminal results are added after their actual runs.

## Remaining integration boundaries

Obtain terminal CI for the exact new source, especially Windows compilation,
DPAPI/object lifecycle and the independent product wrapper. Keep the frozen
79-item acceptance unchanged. This new matrix does not prove Trojan TLS,
VLESS TLS/WS/WSS, HTTPS/SOCKS TLS proxy hops, UDP, advanced subscription DNS,
every group mode through raw document import, all ten formats or arbitrary
provider compatibility. Existing isolated protocol results retain their scope.
The user's REALITY/Vision subscription remains preserved and explicitly blocked
until the production async and ownership/DirectReady boundaries are satisfied.

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
