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
were reported as queued by REST at the S2 checkpoint. Later logs and artifacts
showed that Actions state propagation was delayed; the earlier REST observation
cannot establish whether a runner had actually executed. S1 ultimately failed
on Linux and Windows, with macOS and App success. The original failures are
described under S4 below and are not replaced by subsequent results.

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

S2 was actually pushed as
[`593e7cddc360cf7f51d9fdc988e6cf8fd99aea96`](https://github.com/SOLHK/Swirl/commit/593e7cddc360cf7f51d9fdc988e6cf8fd99aea96).
Its [Rust run 39281808343](https://github.com/SOLHK/Swirl/actions/runs/39281808343)
and [App run 39281808355](https://github.com/SOLHK/Swirl/actions/runs/39281808355)
were still reported as queued, without visible assigned runners or product
artifacts in those API responses, at 16:03 UTC. Later-retrieved artifacts showed
execution that had not yet appeared in those responses.
GitHub's [official status](https://www.githubstatus.com/api/v2/summary.json)
reported an Actions/workflow-processing incident beginning at 15:49 UTC. The
incident and individual job states are separate observations; neither supplies
an executed test result.

The full existing local menu was then rerun at exact S2 source: **24/24 commands
succeeded**, including the five Rust gates (**278 unit/integration tests plus
one doctest**), the Release REALITY example, both generated-vector checks and
all 16 existing Python suites (**261 passed / 5 explicit Windows Qt skips**).
[Its source-bound summary and 24 raw logs](evidence/subscription-product-chain/s2-existing/summary.json)
record every command, input/binary hash and skip reason. Mature Xray R3/Vision
and Windows Qt/full application remain CI gates; they were not replaced by this
local menu. Concurrent font-only commit `83efbaacac15fad711bdfa2107f7845bba0c8d3a`
was checked for non-overlap and retained before S3.

## S3: close the remaining explicit-DIRECT and SNI alias bypasses

Review of the connected product path found two further real conversion gaps.
An active explicit DIRECT mode legitimately bypasses proxy traffic, but must not
also bypass validation of the saved node selection. Both controller preflight
and native adapter selection now validate a temporary global candidate, then
retain the user's actual DIRECT mode. Unsupported extensions and Vision cannot
be confirmed as eligible selections. A supported B selection still leaves traffic
DIRECT until the user explicitly changes mode; subsequent global/rule traffic
must use B.

Qt previously extracted `sni`, then used `servername` whenever that extracted
string was empty. Conflicting `sni: ""` and nonempty `servername` could therefore
lose their conflict before native validation. The importer now rejects different
simultaneous aliases before either is extracted, without echoing their values.
Equal aliases remain accepted and the original object remains available.

These small Qt changes extend the existing regression slots rather than adding
a parallel configuration system. Source review and whitespace validation passed;
the new Qt assertions required the exact-source Windows CI run. The
official Actions incident is not a reason to waive that gate or claim success.

S3 was actually pushed as
[`41555465b72fd59d42bc473f0d097c93e210c240`](https://github.com/SOLHK/Swirl/commit/41555465b72fd59d42bc473f0d097c93e210c240),
with [Rust 39283305158](https://github.com/SOLHK/Swirl/actions/runs/39283305158)
and [App 39283305193](https://github.com/SOLHK/Swirl/actions/runs/39283305193).

## S4: repair observed fixture failures and require authenticated TLS closure

Three actual failures were retained and investigated before changing tests:

- S1 [Linux job 118152922265](https://github.com/SOLHK/Swirl/actions/runs/39280252948/job/118152922265)
  failed when an IPv6 fixture allocated a port and its later IPv4 reservation
  collided with an existing socket (`EADDRINUSE`). Dual-family fixtures now own
  the IPv4 OS allocation and the same IPv6 port before starting either server.
  The existing sockets are transferred directly to their servers. A refusal
  endpoint is still required to return actual connection refusal, not timeout.
- S1 [Windows job 118152921964](https://github.com/SOLHK/Swirl/actions/runs/39280252948/job/118152921964)
  failed binding SS fixture TCP port 49666 with WinError 10013. That port was
  **not** in the recorded excluded ranges; the log does not identify its owner.
  SS now asks the OS to allocate and retain an available TCP socket, verifies
  that actual port against the Windows TCP/UDP candidate table, and binds UDP
  while retaining TCP. Temporarily unsuitable reservations remain held until
  selection ends. Unknown access denial still fails immediately; only address
  collisions have the unchanged eight-attempt budget.
- S2 [Windows job 118157401880](https://github.com/SOLHK/Swirl/actions/runs/39281808343/job/118157401880)
  reached the separate origins through all four product protocol profiles, but
  the required wrapper failed with four independent HTTPS-origin teardown
  errors. The four Qt subprocess successes do not override this failure; the
  subsequent complete application build was skipped. A narrow Linux Qt client
  reproduction isolated missing TLS `close_notify` after QNAM HTTP completion.
  The HTTPS test client now owns a `QSslSocket`, verifies the fixture CA and
  hostname, and explicitly disconnects after reading the exact response. This
  changes the test client, not the product's proxy transport or TLS policy.

The independent HTTPS origin still requires successful `unwrap()` and raw EOF.
After a successful TLS close exchange, a redundant TCP write-shutdown may return
only the precisely identified `ENOTCONN` / WSAENOTCONN 10057; other errors remain
failures. Each Windows protocol case additionally requires exactly one completed
TLS close exchange. Error reports retain the fixture, exception type, errno and
source boundary without recording request bytes or credentials.

The final local dual-family menu passed **12/12** and the SS policy menu passed
**20/20**, with no failures or skips. New allocation regressions cover real
socket ownership, bounded collisions, denied access, rejected candidates and
descriptor exhaustion. The original forwarding/security assertions remain.
These are Linux execution and controlled Windows table branches, not native
Windows proof. The exact local source hashes and raw results are retained under
`evidence/subscription-product-chain/s4-local/`.
The final changed portable product class also passed **8/8**, with zero failures
or skips; that command explicitly selected the portable class and did not run
the Windows Qt class. The archived Qt client experiment is Linux diagnosis only.

At this source checkpoint, verified S2 and S3 portable product artifacts each
cover Linux, macOS, Windows and App: eight passes plus one explicit Qt skip in
each menu. S2 and S3's dedicated Windows product wrappers remain failures; S3's
[Windows log](https://github.com/SOLHK/Swirl/actions/runs/39283305158/job/118162194645)
records the same four origin-close errors at 16:31 UTC. S2 now has terminal
Linux/macOS/App success and Windows failure. New S4
Windows compilation, the dedicated wrapper, the complete application build and
all exact-source CI terminal results must still run before acceptance is claimed.
Concurrent font-only commit `5cb42619785c66317552867d251784df2b0323b9` was checked
for non-overlap and retained. Formal acceptance stays **79 / 6 / 10.83%**.

S4 was actually pushed as
[`a066f7d4c8acb96f5d6a46cee5700b2590328b64`](https://github.com/SOLHK/Swirl/commit/a066f7d4c8acb96f5d6a46cee5700b2590328b64).
Its exact runs are [Rust 39287922752](https://github.com/SOLHK/Swirl/actions/runs/39287922752)
and [App 39287923155](https://github.com/SOLHK/Swirl/actions/runs/39287923155).
The [S1–S3 final matrix, raw failures and product artifacts](evidence/subscription-product-chain/ci-s1-s3/README.md)
retain all earlier exact-source outcomes; they do not prove S4 passed.

## S5: verify the Qt client's close exchange through the real proxy path

The S4 local direct-to-origin Qt diagnostic was not sufficient to predict the
proxied Qt close sequence. An additional Qt HttpProxy → Rust → independent
relay experiment received the correct origin body but still failed strict TLS
closure. An explicit CONNECT on the same Qt socket reproduced that result too.
Both failed diagnostic variants remain evidence; neither is a product pass.
The exact S4 [Windows job 118180557286](https://github.com/SOLHK/Swirl/actions/runs/39287922752/job/118180557286)
then confirmed that failure: all four profiles recorded zero completed TLS
closes, and origin cleanup reported four `SSLEOFError` exceptions at `unwrap()`.
The wrapper ran one test with five failure records and zero skips; the complete
application build was skipped. S4 Linux, macOS and App completed successfully.

The Qt product fixture now gives the test client ownership of the positive
close sequence: after sending its complete response, the origin first requires
the client's authenticated TLS EOF, then sends its own close alert with
`unwrap()`, and finally requires raw TCP EOF. `suppress_ragged_eofs=False`
prevents bare TCP EOF from satisfying that first check. The close counter is
incremented only after both TLS and raw EOF complete, so a caught cancellation
cannot be counted as normal closure. The portable menu retains server-initiated
TLS closure. Both directions therefore keep independent authenticated-close
coverage. The S4 C++ client's HttpProxy and VerifyPeer configuration remain the
actual Qt product test client.

With the final fixture source, a Linux Qt/PySide client using the actual
subscription inspector and Rust harness passed all four HTTP CONNECT/SOCKS5/
SS AEAD/VLESS TCP profiles. Independent relays observed the expected positive
and wrong-name connections, correct SNI, one origin HTTP request, one complete
TLS/raw close and zero positive origin/relay errors per profile. Wrong-name
verification produced no additional HTTP request. A real bare-TCP-FIN negative
through the HTTP relay produced `SSLEOFError`, zero completed closes and a
failed origin cleanup, as required. This is a Qt-client/Rust diagnostic, not
Windows C++/DPAPI product-object acceptance. The changed portable class also
passed eight tests with no failures or skips; the Windows class was not selected.

S4 App validation also exposed an actual menu omission: its older independent
SOCKS4 subscription case skipped because that shell step did not export the
already-built Inspector. App now exports and preflights the Release Inspector
before the existing peers. The new guard failed on the previous workflow, then
all 45 guards passed with the correction. The updater remains idempotent and
keeps its existing single-workflow scope. The local SOCKS4 menu passed nine
tests, including the two protocol variants across five input representations;
its separate Windows Qt hook was explicitly skipped.

These local results and failed diagnostic controls are archived under
`evidence/subscription-product-chain/s5-local/`. Exact new-source Linux/macOS/
Windows/App CI, the mandatory Windows product wrapper and the complete native
application build must execute before this source is reported as passed.
Formal acceptance remains **79 / 6 / 10.83%**.

The concurrent font-only `b98850c3caaec7874f7e8c5a95866bbc4741df36` was fetched,
checked for non-overlap and retained before S5 publication.

## Actual field boundaries inspected

The audit used `swirl-subscription/src/{lib,inspect,inspect_boundaries}.rs`, the
existing normalizers, `NodeImporter`, `NodeStore`, `RustCoreEngine::configuration`
and `EngineController` import/selection/rule transactions. The following are
current code boundaries, not claims that every field has completed networking.

| Field family | Existing preservation / execution boundary |
| --- | --- |
| Protocol and version | Original node/document remains distinct from the typed `Outbound` enum. Supported aliases use existing normalizers; unrecognized version/extension fields cannot become another protocol silently. |
| Host, IPv4/IPv6 and port | Typed host and bounded native port; Rust checks both supplied port aliases. Qt keeps the server and final source-owned node ID. IPv6 round-trip and literal IPv6 reject routing have separate tests. |
| Username, password and UUID | Qt rejects non-string source/editor values; NodeStore encrypts original and extracted credentials. Runtime authentication uses the typed fields; wrong credentials in four proxy families produce no target request or alternate exit. |
| TLS enable and verification | Implicit TLS protocols retain TLS. Contradictory disable requests and insecure verification are rejected; supported runtime TLS has no insecure switch. |
| SNI, ALPN and certificates | SNI aliases cannot conflict; ordered ALPN is retained. Native `Tls` has explicit extra DER trust-anchor support, but an unmapped subscription certificate option is rejected instead of guessed. The new HTTPS origin fixture uses a private test CA only in its client. |
| REALITY public key, short ID, fingerprint and spiderX | Original options/URI retained; no normal-TLS substitution. Production async REALITY and combined Vision remain capability errors. |
| VLESS flow and transport | Nonempty Vision flow remains blocked. Missing supported default, explicit null and unrecognized transport are distinguished before conversion. |
| WS/WSS | Existing converter preserves supported host/path/Host header and TLS/HTTP-1.1 ALPN. Other headers/options or a TCP/WS conflict reject; S1 persistence test is not WS target-traffic evidence. |
| Shadowsocks | Three traditional AEAD ciphers, explicit UDP declaration and existing HTTP-obfs options retain their typed meanings. Other ciphers/plugins/options reject; the new full-origin matrix proves TCP, not UDP or obfs product completion. |
| gRPC/XHTTP and unknown extensions | Original values, including false/null, remain inspectable; no executable TCP candidate is synthesized. |
| DNS, ordered rules and groups | Existing native DNS configuration remains in use. This raw-document product profile rejects unmapped subscription DNS dialects; ordered basic rules resolve only source-owned nodes/groups. Advanced rule families remain explicit errors. |
| TFO, timeouts, IPv6 and network controls | TFO false retains the existing disabled meaning; true/null or unmapped network options cannot silently take effect. Native `Limits`, DNS family policy and socket targets keep their own typed validation. Complete external network-option dialect mapping remains unfinished. |

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
