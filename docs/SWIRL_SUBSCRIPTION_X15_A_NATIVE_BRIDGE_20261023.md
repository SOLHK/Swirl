# X1.5-A: native JSON candidates reach the Qt subscription product chain

## Scope and preserved lineages

Development branch: `work/subscription-native-bridge-20261023`.

This stage integrates two published histories, preserving both as merge parents:

- Native converter, transports and protocols, including the existing A8 fixes:
  `21c562a7c7adc2654416636e4de2f038ffc220cd`, from
  `work/rust-native-protocols-x14a-20261022`.
- Qt import, preview, source replay, encrypted storage, catalog lifecycle and
  product acceptance: `506014d6386610411f48c939ab62cb93a3509431`, from
  `work/xray-v2ray-qt-import-20261022`.

Neither original branch, `main`, nor `test` is updated by this integration.
No protocol implementation is replaced. Hysteria2 A8 is inherited unchanged;
the other development window can continue on its original branch.

## Confirmed problem and implementation

The D branch's `swirl_import_xray_v1` export used a separate, older capability
projection. It called the old inspector only for VLESS/REALITY/TCP and reported
`NativeConversionPending` for other protocols. The completed native converter
therefore could not be reached through normal Qt JSON import.

That old projection also assigned one native candidate to each original
outbound. A single outbound can expand into several servers and accounts;
the original outbound index cannot select an expanded row's credentials.

`core/crates/swirl-api/src/xray_import.rs` now obtains the executable candidate
from each expanded `ValidatedOutbound::native_outbound()`. The converter remains
the single authority for validation, transport/security compatibility and
blocking diagnostics. The duplicate inspector path is removed.

The ABI stays schema 1 with the existing buffer, size, UTF-8, strict JSON and
panic boundaries. Three identities remain distinct:

| Field | Meaning |
| --- | --- |
| `index` / Qt `sourceNodeIndex` | Expanded node index used for exact account replay |
| `source.outbound_index` | Original outbound object shared by expanded siblings |
| `source.server_index` and `source.user_index` | Endpoint/account provenance inside the source |

Original outbound objects are emitted once. Local actions such as `freedom`
and `blackhole` remain non-node actions. Filtering them from the Qt list does
not renumber source identities. Invalid accounts stay blocked without disabling
or borrowing a valid sibling's configuration.

Qt reparses the original document before execution and when loading saved
nodes. Saved flags and cached native outbounds cannot grant capability. Source
bytes, original fields, selected IDs and shared source storage remain intact.

`XrayJsonBridge` preserves SOCKS4 and SOCKS4a identity using the Rust candidate's
type and `remote_dns`. Valid but otherwise blocked source versions can supply
a display label without granting execution. Public labels distinguish SOCKS4,
SOCKS4a and SOCKS5.

## Supported scope and limits

Eligible native JSON configurations for VLESS, VMess, Trojan, Shadowsocks,
SOCKS and HTTP now reach the Qt product chain. Eligible gRPC, HTTP/2,
HTTPUpgrade and XHTTP `stream-one` preserve the authoritative converter's
transport data. This does not enable every protocol/transport combination.
VMess with those four transports remains blocked by
`TransportProtocolUnsupported`. Unsupported mux, transport controls, unknown
security fields and nonempty global transport defaults remain blocked.

Imports retain `network_verified: false`. Parsing, native executability and
actual traffic are separate states. Imported inbounds, routing, scripts, file
paths and global configuration do not modify local product options. Supported
REALITY fixtures use the official source fingerprint `chrome`; the internal
`rustls` source alias remains explicitly rejected by the strict converter.

This stage does not establish private-provider acceptance, all 18 subscriptions,
UDP/TUN acceptance, physical Windows desktop acceptance or full-project
completion. Non-Windows production encrypted storage still fails closed.
Windows DPAPI is exercised by the Windows job. No supplier URL is refreshed
and no private credential enters source or public evidence. A cloud build or
GitHub push does not save files to the user's D drive.

## Regression gates

Rust ABI regression tests cover all six protocol categories, native Config
roundtrips, supported transport parameters, 2,000 expanded accounts with source
deduplication, mixed valid/invalid siblings, multiple servers and local actions
before remote nodes. The actual C import export feeds `swirl_core_command`
start/configure/snapshot/stop, including atomic rejection and listener release.
This lifecycle evidence is separate from upstream interoperability.

Qt regression suites cover six-protocol candidates, SOCKS versions/DNS labels,
expanded-node source replay, 1,000-account credential mapping and Windows DPAPI
save/destruction/reload. Selected account identity and blocked siblings must
survive reload; forged cached flags cannot promote an unsupported source.
The workflow checks mandatory method names in XML and rejects failures/skips.

The shared-source stress regression keeps three explicit cases: a real
32-account / 1 MiB unsupported input preserved as blocked, a real 1,000-account
unsupported input rejected at the unchanged diagnostic cap, and a synthetic
blocked 1,000-account / shared 1 MiB fixture that only exercises bounded
`NodeStore::prepareImport`. That synthetic source still fails execution replay.
No production diagnostic limit or guard is relaxed to make stress data pass.

## Real traffic acceptance

`tools/tests/test_xray_qt_import.py` exercises actual JSON file import, preview,
confirmation, source replay and the in-process Rust engine. Windows additionally
uses real product DPAPI save/reload. Seven profiles cover six protocol families:

| Profile | Independent server |
| --- | --- |
| HTTP, SOCKS5, Shadowsocks AEAD, VLESS TCP | Existing real-socket independent peers |
| VLESS/REALITY | Pinned source-built official Xray/REALITY, existing instrumentation |
| VMess AEAD, Trojan TLS | Hash-locked, unmodified official Xray release |

Every profile requires real HTTP and certificate-verified HTTPS through the
Qt-owned Rust listener. Body bytes, authenticated TLS shutdown, raw connection
closure, server acceptance, bidirectional counters and listener release are
checked. VMess/Trojan credentials and Trojan CA enter only through original
Xray JSON; no converted runtime configuration is injected after import.

The official release is checked against the committed lock, host platform,
archive receipt and binary SHA-256. Public reports contain allowlisted
booleans/counts/paths/hashes. Local dirty source is labeled explicitly; CI
requires a clean worktree whose HEAD equals `GITHUB_SHA`.

## Windows packaging gate repair

D head `506014d6` passed component, DPAPI and official traffic checks, then failed
its package identity check in [run 39728834368](https://github.com/SOLHK/Swirl/actions/runs/39728834368).
The full application build rebuilt `swirl_api.dll` after the component tests had
already copied and tested an earlier library.

The complete Windows application now builds before component tests copy their
final Rust library. The tested-versus-packaged SHA-256 equality gate remains
mandatory. Full `Swirl.exe`, mounted QML import at scales 1 and 1.5, all-page
smoke and external-core exclusion remain required. No equality or UI gate was
removed. The release build explicitly selects both `swirl-api` and
`swirl-protocol`, which owns the transport-client fixture example. Clean CI
runners therefore build the required executable without depending on a previous
workspace build. The example is not used as the Qt business client.

## Source-checkpoint verification

Fresh validation after recovery:

- Rust fmt, workspace check, all-target clippy with warnings denied: passed.
- Rust workspace tests: 660 unit/integration + 1 doctest, zero failures/ignored/filtered.
- Release library, CLI binaries and required protocol fixture example: built.
- All five Qt CTest suites passed in one run: 62 test functions, 72 pass incidents
  including lifecycle, zero failures/skips.
- Seven Qt real-traffic profiles passed: 14 actual HTTP/HTTPS requests with
  verified certificates, body bytes and authenticated TLS closure.
- Seven traffic-evidence guard tests passed.

The [local receipt](evidence/SUBSCRIPTION_X15_A_LOCAL_20261023.json) records
results for the restored source, source hashes and tested-library identity.
The precommit worktree HEAD is its native parent, not the new complete source
identity. Exact-source CI conclusions must use the actual published commit.
The [product workflow](../.github/workflows/xray-qt-import.yml) runs three OS
jobs on this independent branch.

Earlier in this task, the first worktree passed Rust 660 unit/integration tests
plus one doctest, five Qt suites and seven traffic profiles. Two interrupted
GitHub blob-write requests were followed by transient-workspace recreation
before any branch was published. Those old results are history. Production
bridge, Qt mapping, workflow and runtime fixture files were recovered and their
Git blob hashes matched the first implementation; the restored source is
verified again before publication. No old CI success is borrowed.

## Published checkpoint and mounted QML follow-up

The initial integration was published as
`7b35bb1474fa5827c3e184231e07d059609532a7`. Its tree is identical to the
locally verified checkpoint. [Run 39885164416](https://github.com/SOLHK/Swirl/actions/runs/39885164416)
passed all Linux and macOS gates: 661 Rust tests, 62 Qt test functions and
all seven actual-traffic profiles on each platform. Windows passed 662 Rust
tests, 76 Qt functions (including actual DPAPI account replay), seven traffic
profiles, the complete application build, tested/packaged DLL equality and
page smoke. It then failed `json-scale-1` at
`XRAY_UI_FAIL cancel-preview-button`; scale 1.5 did not execute. That run is
retained as a failure, not complete Windows acceptance.

The button-click driver previously used display text to locate cancellation
and sampled scene coordinates immediately. A standalone Qt 6.10.3 experiment
confirmed that making a footer button visible can leave positive but stale
geometry while its parent layout has pending polish. The button's own polish
flag can already be false, so the whole window must be considered. Linux
offscreen still delivered every immediate click successfully; this experiment
did not reproduce the Windows failure or prove its exact cause.

The follow-up gives the existing cancellation button a stable object name,
finds it within the actual import dialog, and calls Qt's public
`QQuickTest::qWaitForPolish(window)` before computing pointer coordinates.
It retains real pointer input, exactly one observed click, visibility,
enabled/geometry/bounds checks, and the read-only cancellation assertions.
Failures now identify the individual click phase. QuickTest is linked only
when the existing UI acceptance build option is enabled; the production UI
layout and import semantics are unchanged.

Local validation compiled the complete modified C++ acceptance driver against
Qt 6.10.3. Eighteen immediate/polished footer trials all observed the correct
click (no fail-before/pass-after claim), and twelve additional mounted-dialog
trials confirmed scoped lookup selects the actual visual button. See the
[failure and follow-up receipt](evidence/SUBSCRIPTION_X15_A_QML_FOLLOWUP_20261023.json).
The new exact commit must run the unchanged three-platform workflow through
both QML scales; earlier successes do not replace those gates.

## Primary references and reuse

- [Xray outbound structure](https://xtls.github.io/en/config/outbound.html): protocol and stream settings retain separate semantics.
- [Official SOCKS source](https://github.com/XTLS/Xray-core/blob/main/infra/conf/socks.go): explicit SOCKS version semantics survive display/runtime projection.
- [v2rayN subscription documentation](https://github.com/2dust/v2rayN/wiki/Description-of-subscription): imported profiles retain source-format identity.
- [Qt Quick Test polish synchronization](https://doc.qt.io/qt-6/qquicktest.html) and
  [Qt 6.10.3 implementation](https://github.com/qt/qtdeclarative/blob/v6.10.3/src/qmltest/quicktest.cpp): wait for all pending window layout work before input coordinates are sampled.
- Existing Swirl converter and pinned official-server infrastructure from the native B6/X14 histories.

The implementation reuses Swirl's authoritative converter and test servers.
No upstream client was copied and no external proxy core enters the shipped
Rust data path.
