# X1.2-D: Qt Xray/V2Ray import product chain

This work uses `work/xray-v2ray-qt-import-20261022` in its own Linux
worktree. It does not modify main, another development branch, private
subscriptions, font code or routing rules. The cloud checkout is not the
user's Windows D drive.

## Verified starting references

| Branch | Observed remote HEAD at task start |
| --- | --- |
| work/xray-v2ray-json-import-20261021 | ff2e2ad76022a2742b1eb256fdb8058873ca1a3e |
| work/xray-v2ray-json-b-20261022 | f82ae8c81abc9d289474453724e0b8df71a87271 |
| work/xray-v2ray-native-20261021 | b88bb978d31fad1865e1b648cecd4f230bc3487c |
| work/xray-v2ray-transport-20261022 | 4ad768303f4dbea289d87714974e752f544c2542 |
| work/subscription-import-20261021 | bf40f6dd639b0a9583a0dbea8e50851ac0c9ed29 |
| work/rust-core-network-fixes-20261021 | b8aa4f6f40a091697e89ae4c8291789661edca60 |
| work/core-completion-20261017 | f87b6f98eb7018c4a5e86f281fe707764565ce58 |

The D branch initially selected A, then fast-forwarded to published B1 to
reuse its getters instead of implementing another converter. B's published
formatting-only follow-up `4606b6df484cd0504014b9bdac6cb237a813c9b3`
is also included. No uncommitted B/C source is used.

## D1: strict file import

The new `swirl_import_xray_v1` C ABI calls the original A parser and B1
converter with the original bounded bytes. It has no runtime, filesystem or
network side effects. Duplicate keys, nesting/value budgets and structural
checks stay in Rust. An explicit size query, complete-buffer writes, panic
boundary and 64 MiB response ceiling protect the C++ caller.

`XrayJsonBridge` only projects those typed results. It retains exact source
bytes and the expanded-node index, including unsupported nodes. Local
freedom/blackhole/dns/loopback actions are not imported as remote servers.
Third-party inbounds, local ports, scripts and global settings stay inert.
File I/O and parsing run on the existing worker pool. JSON files enter a
redacted preview; only explicit confirmation calls the store transaction.
Cancellation and parser/save failure leave the old catalog intact.

DPAPI persistence groundwork is part of D1 because confirming an import
must not lose its source at restart. A shared source-document table retains
exact bytes, references are hash checked, and reload recomputes capabilities
through the current Rust parser. The existing DPAPI entropy/scope and atomic
QSaveFile behavior are retained; there is no plaintext fallback. Advanced
roundtrip and identity tests are completed in D5/D6.

Local D1 tests use actual Qt 6.10.3, GCC 13.3 and the newly built Rust shared
library. They cover file preview/confirm/cancel, Unicode filenames,
duplicate keys, multiple envelopes, Base64 wrapping, invalid parameters,
unsupported transport preservation, credential-free summaries, size limits
and unchanged source files. Linux has no secure storage backend in this
repository, so its real-store case verifies refusal without a plaintext
file. The Windows CI variant performs actual DPAPI save/destruction/reload.
Windows/macOS results must be read from the exact commit's workflow; they
are not implied by the local Linux tests.

## Runtime boundaries at D1

B1 publishes VLESS/VMess projection but has not yet published its full
native converter. The ABI can reuse the pre-existing closed VLESS REALITY
TCP inspector subset; other cases remain explicitly pending. No imported
node is marked network verified. Display, parameter validation, native
capability and real traffic evidence are separate. D7 connects executable
outbounds to the product controller and D8 supplies real traffic evidence.

## D2: text and clipboard

Text and clipboard JSON now use the same original-byte Rust parser and
explicit preview/confirm/cancel flow as files. UTF-8 encoding and parsing
run on the worker pool after a cheap UTF-16 length bound. The actual byte
ceiling remains 4 MiB, including multibyte Unicode. Source labels contain
only `text` or `clipboard`; clipboard content is never logged or retained
in UI messages. Generation checks discard canceled worker results.

The real Qt/Rust library suite passes 17 test methods (plus init/cleanup),
including Unicode multiple-node text, actual Qt clipboard retrieval,
strict duplicate-key rejection, oversized Unicode, cancellation, and
repeated imports. The Windows store path additionally checks that repeated
confirmation does not duplicate the catalog and malformed input preserves
it; Linux verifies encrypted-storage refusal. Broader identity updates and
subscription refresh semantics are covered in D6.

## D3: HTTPS JSON URL

The existing subscription downloader now gives manual JSON URLs the same
preview boundary. It retains the existing explicit download-proxy policy:
direct download unless Swirl supplies its active local HTTP proxy; the
operating system proxy is neither inherited nor modified. Default TLS
certificate verification remains enabled. Redirects are manual, limited to
five, and restricted to the same scheme, hostname and effective port.
Cross-origin targets, HTTPS downgrade, embedded URL credentials and local
file URLs are rejected without echoing either URL into errors.

Downloads retain a 15-second idle timeout and 30-second overall deadline.
Response metadata rejects declared bodies above 4 MiB before reading them;
64 KiB bounded reads enforce the same ceiling for streaming/decompressed
data. Interruption, malformed JSON, TLS failure and cancellation do not
apply nodes. Auto-refresh reuses this path with its existing transaction.

The actual Qt HTTPS fixture suite passes 15 cases on Linux, including
trusted/untrusted certificates, zero requests to cross-origin targets,
same-origin redirect, redirect limit, downgrade/file rejection, oversized
headers and streamed bodies, truncation, strict malformed JSON, cancellation,
token-free public state/logs, and the real 15-second idle timeout. These are
real TLS download tests, not proxy-protocol connectivity claims.

## D4: node model and existing QML page

The node model exposes separate safe roles for JSON syntax, Rust parameter
validation, Rust executable capability and unverified business traffic.
Display labels distinguish VLESS, VMess, Trojan, Shadowsocks, SOCKS5 and
HTTP, plus TCP/WebSocket/gRPC/HTTP2/HTTPUpgrade/XHTTP and TLS/REALITY.
Vision is a boolean display hint; its full flow remains private. Source
labels show input kind and a short document fingerprint, never token URLs
or source contents. Runtime capability and reasons come from the Rust FFI
result, with no fallback to a different engine.

The existing QML table/preview/details render these roles and disable
connect/test for unavailable nodes. Imported JSON can be renamed without
editing derived protocol fields; connection changes require reimporting the
authoritative source. Long diagnostics wrap as plain text. Global/inbound
credential values are also prevented from being reflected as outbound names.

The real Qt/Rust importer suite passes 19 methods, including the six labels,
REALITY versus TLS, Vision and WebSocket preservation, four-state separation,
and credential-free public model. `qmlformat` parses the updated page
successfully. This is model/syntax validation; complete Windows application
compilation and UI acceptance remain separate CI evidence.

## D5: asynchronous encrypted snapshots and replay

JSON rows persist only safe catalog metadata and an expanded-node reference;
the exact original bytes live once in a shared document table. Derived
credentials, normalized parameters and raw outbounds are reconstructed by the
same strict Rust bridge on reload. This preserves every original field,
including UUID/password/cipher, TLS/SNI/ALPN/fingerprint, REALITY
publicKey/shortId/spiderX, Vision flow, WebSocket Host/Path, gRPC serviceName,
HTTP2, HTTPUpgrade, XHTTP and unknown extensions. It avoids duplicating a
large multi-account outbound once for every account.

Confirmed JSON imports and subscription updates serialize, encrypt and
QSaveFile-commit on a worker. A store write lease blocks concurrent edits,
selection changes and other commits until the owning thread adopts the
successful snapshot. Failure releases the lease without changing nodes,
selection or the old ciphertext. Canceling an unconfirmed preview discards
it; a confirmed atomic write completes independently of closing its dialog.
No worker mutates a QObject or falls back to plaintext. Store size is bounded
at 32 MiB; source files retain the smaller 4 MiB limit.

Schema-1 legacy data remains readable and safely migrates on the next
successful write. Corrupt document hashes are rejected without overwriting
the file. A valid stored document that today's parser/DLL cannot replay is
retained as a disabled node; saved capability flags cannot authorize it.

Linux local validation passes all 20 importer, 15 real HTTPS downloader and
7 applicable store methods. Store tests exercise a 1000-account source,
aggregate size rejection, corrupted-file protection, unavailable encryption,
asynchronous write lease/callback thread, wrong-store plans and destruction
before a queued write. Windows-only tests additionally require real DPAPI
semantic roundtrip after object destruction, shared-document storage size,
legacy migration, source-hash corruption, replay failure/forged capabilities
and locked-file atomic rollback. Those platform results are reported from CI,
not inferred from Linux. macOS/Linux have no credential-storage backend in
the existing Windows product and deliberately refuse persistence.

## D6: identities, refresh and selection ownership

Deduplication compares connection semantics within the existing source scope,
not the display name. A rename retains the stored ID; different endpoints or
credentials with the same name remain distinct. A subscription can retain an
ID across credential/address updates only through its unique original source
alias and account position. Exact semantic matches take priority, including
when accounts are reordered. Manual endpoint/credential changes do not gain
permission to replace another node merely by reusing its name. Ambiguous names
are rejected before a full configuration can bind policy references to them.

The non-secret selection sidecar is now bound to the exact encrypted snapshot
digest, so an older sidecar cannot restore a stale choice after refresh. A
removed selected node clears selection; no replacement is silently selected.
The running Rust engine owns its start snapshot. A refresh may update or remove
its catalog row while established sessions continue with that snapshot until
the user disconnects; the UI explicitly explains this state. Manual deletion
during a running session remains guarded. Catalog mutation cancels independent
node probes and clears their old parameter-dependent results, including queued
callbacks. Failed writes leave those results and all prior state intact.

Unavailable nodes can now be inspected in the existing details panel without
changing the runtime selection. Connect/test still requires the current Rust
capability, and inspection is never represented as successful connectivity.

D6 is verified against an isolated source copy using the committed D5
RustCoreEngine, excluding uncommitted D7 runtime changes. The Linux suite runs
20 importer, 15 HTTPS download, 11 store and 6 catalog methods. The catalog
tests use the real in-process Rust engine and real loopback HTTP CONNECT
endpoints to check cancellation and immutable state; their deliberate rejected
requests do not count as useful HTTP/HTTPS business traffic. Windows-only
catalog cases additionally exercise actual DPAPI confirmation, live refresh,
credential/address changes, running-row removal, manual reconnect and reload.
Those Windows cases require CI execution; Linux syntax checks are not a
substitute for them.

The earlier D1 commit passed all three platform jobs, including the complete
Windows application build. D5's Windows DPAPI tests passed, while its macOS
HTTPS fixture exposed a SecureTransport compatibility issue; D8 tracks and
retests that issue rather than treating the failed run as a pass.

## D7: authoritative native configuration and real traffic

D7 merges B's published password-getter commit
`4e9f6ea0411c03bba418bb46884748ba7e0ba03b` as a second parent. Its Trojan
and Shadowsocks password/method validation is reused without a Qt converter.
The B branch still lacks a general native-outbound conversion interface.
C's observed published head is
`4f3f0caba8f20e7fa776ea7a710864a685215d44`; this stage does not borrow its
uncommitted work or implement its transport connectors.

Every JSON node entering a selected or rule route is replayed from its exact
bounded source through the Rust bridge. The resulting native outbound is the
only executable configuration. Persisted capability flags, modified public
fields and forged cached outbounds cannot authorize execution. Third-party
listeners, routes and DNS settings cannot replace Swirl's locally owned
options. Failure returns a bounded diagnostic and does not start another core.

Actual Qt/Rust tests cover source replay against a forged cache, rejected
invalid or unsupported sources, inert imported listeners/rules, invalid
selection and start rollback, and Rust listener-port conflicts. The importer
suite now has 22 methods, including B2 passwords containing Unicode, NUL and
surrounding whitespace, exact Shadowsocks methods and credential-like tags.
Display normalization cannot reveal a credential that previously contained
control characters. These tests compare secrets without printing their values
on assertion failure. The Rust workspace passes formatting, locked check,
all-target Clippy with warnings denied, and 444 tests with zero failures or
ignored tests. A local incremental compiler-cache failure was resolved by
disabling incremental compilation; no protocol source was changed for it.

`tools/tests/test_xray_qt_import.py` drives the actual Qt executable, which
loads the actual Rust shared library in-process. It uses the repository's
repeat-verified pinned official Xray peer and independent HTTP/HTTPS origins.
The accepted profile is VLESS REALITY TCP, without Vision flow. The Qt process
imports a Unicode-path JSON file, starts the selected Rust node, and launches
a Python standard-library SSL business client through the Rust local proxy.
The business client receives loopback URLs and its test CA, not node credentials
or proxy-protocol configuration; it is not an alternative proxy engine.

The gate requires valid HTTP and HTTPS responses and exact bodies, verified
HTTPS certificates, successful official-peer REALITY authentication and VLESS
requests, bidirectional Rust session counters, TLS close-notify in both
directions, closed sessions, and a stopped/freed local listener. Seven evidence
guard tests reject missing or contradictory proof. This controlled loopback
chain passed on Linux against the merged B2 source. It proves real protocol
traffic, not a connection to a user's remote provider. Linux's missing secure
storage backend is explicitly reported; only Windows can additionally require
DPAPI confirmation, object destruction, reload and selection before traffic.

An optional QtNetwork business-client profile remains diagnostic: it received
the HTTP/HTTPS responses but did not satisfy the independent authenticated
TLS-shutdown gate. It is not reported as a complete successful chain. The
default standard-library client satisfies the unchanged strict shutdown gate.
No tested node is globally marked network verified from this fixture evidence.
Other protocol/transport combinations await B/C/VMess integration; their
successful display or parameter validation is not a native-connectivity claim.

## D8: executable acceptance gates and platform evidence

The dedicated workflow now requires all five real Qt suites on Ubuntu 24.04,
macOS 14 and Windows Server 2022. A missing, truncated, empty, failed or skipped
XML report fails the job. Windows additionally requires the actual DPAPI
roundtrip and the catalog cases for committed imports and running refresh.
The independent official-peer HTTP/HTTPS gate runs on all three platforms;
Windows must prove persistence/reload before starting the native runtime.
Evidence uploads are allowlisted and exclude private peer configurations,
raw subscription contents and unredacted protocol logs.

The full Windows application builds against the same Rust DLL as the component
tests; CI compares their SHA-256 values and rejects external proxy executables
in the application output. It deploys the actual QML application and runs the
existing load-aware page smoke plus an isolated JSON acceptance profile at
device-pixel ratios 1 and 1.5. The new profile clicks the mounted import,
confirmation and node-row controls; tests text, clipboard and Unicode-file
previews; checks six protocol labels and REALITY/Vision details; confirms a
real encrypted save/reload; checks repeat-import identity and strict malformed
input rollback; and checks unsupported-row inspection without changing the
selected executable row. It verifies actual DPR values, disabled unsupported
actions, credential-free public text, process exit and QML-warning status.
The acceptance flag is compiled only when explicitly enabled with the Rust
application. No unrelated page or font implementation is changed.

The earlier macOS downloader run failed before issuing a verified request.
Fixture review found that the old CA certificate was also used as a server
leaf and lacked a serverAuth EKU. The downloader fixture now uses a dedicated
CA-signed, 730-day localhost
server leaf with SANs and serverAuth, while clients explicitly trust only the
test CA and retain VerifyPeer. The macOS test process enables Qt's temporary
keychain path before TLS initialization, avoiding a login-keychain prompt.
A bounded verified-handshake preflight exposes setup failure immediately;
certificate validation is never disabled. The new test leaf expires in 2028
and must be rotated before then.

Local Linux acceptance on the cumulative D8 source passes 5/5 CTest suites:
22 import, 15 HTTPS download, 11 applicable store, 5 runtime and 6 catalog
methods, with zero failures or skips. All five complete XML documents were
parsed immediately in the same test command. One earlier copy of the download
report was observed truncated despite a successful process/text log; two
isolated runs and the final complete suite did not reproduce it. That report
was rejected, no gate was weakened, and the underlying cause remains unproven.
The mounted UI helper and main entry pass C++23 syntax compilation against the
real Qt SDK; workflow YAML, Bash and embedded Python also pass local syntax
validation. Full Windows execution and macOS certificate acceptance require
the exact published D8 workflow result, not these Linux checks.

Previously obtained immutable evidence:

| Commit/run | Actual evidence |
| --- | --- |
| D1 `38131212`, run [39720162765](https://github.com/SOLHK/Swirl/actions/runs/39720162765) | All three platform jobs passed, including the full Windows application. |
| D5 `32354980`, run [39721951577](https://github.com/SOLHK/Swirl/actions/runs/39721951577) | Linux and Windows passed; Windows import 20, download 15 and store 13 methods, zero skips; old macOS HTTPS fixture failed. |
| D6 `6ddf5312`, run [39723494413](https://github.com/SOLHK/Swirl/actions/runs/39723494413) | Linux and Windows passed, including the complete Windows application build. Windows XML proves import 20, download 15, store 23 and catalog 7 methods, zero failures/skips. Old macOS fixture failed. |
| D8 `b60b9fb6` | Clean published source was used to repeat-verify the official peer and rerun the real Qt/Rust HTTP/HTTPS chain on Linux: passed. This local result is not a three-platform CI result. |
| D8 follow-up `514bf757`, run [39727257693](https://github.com/SOLHK/Swirl/actions/runs/39727257693) | Linux and macOS passed all gates, including authenticated HTTP/HTTPS traffic. Windows passed 72 Qt methods (including DPAPI) and 444 Rust tests plus one doctest, but its separate traffic process exited before producing XML; the full application/UI gates were not reached. |

The latter Windows failure matches Qt 6.10.3's narrow-character test logger:
[`qExec(QStringList)`](https://github.com/qt/qtbase/blob/v6.10.3/src/testlib/qtestcase.cpp#L2101-L2115)
converts arguments with `toLocal8Bit()`, and the MSVC
[`QAbstractTestLogger`](https://github.com/qt/qtbase/blob/v6.10.3/src/testlib/qabstracttestlogger.cpp#L115-L128)
uses `fopen_s()` and exits with code 1 when its path cannot be opened. The
private stderr was not uploaded, so this is a source-supported diagnosis, not
a claim that the failed run's exact message was captured. The harness now
requests XML on stdout and lets Python open the Unicode report path. All
Unicode product/configuration/store paths and traffic assertions remain in
place; empty output explicitly fails. Only the subsequent Windows workflow
can confirm that this change restores the complete product chain.

The official actionlint v1.7.7 validator also accepts the D8 workflow. GitHub
reported the workflow active but created no run/check suite for its initial
D8 push after more than five minutes. A normal follow-up documentation commit
records the newly completed D6 evidence and supplies a new push event; no
source rollback, force push, or change to main is used. Final CI must be
associated with the resulting exact branch head.

### Published stage ledger

| Stage | Immutable commit |
| --- | --- |
| D1 file preview and strict ABI | [38131212c56f72b3108fa5324ce9f8b106f5eb58](https://github.com/SOLHK/Swirl/commit/38131212c56f72b3108fa5324ce9f8b106f5eb58) |
| D2 text and clipboard | [e3ed5d82ada558f1960b838516d3a9d8a97892c1](https://github.com/SOLHK/Swirl/commit/e3ed5d82ada558f1960b838516d3a9d8a97892c1) |
| D3 HTTPS configuration URL | [e048dd6c17968865465ad726aa46303344327e0e](https://github.com/SOLHK/Swirl/commit/e048dd6c17968865465ad726aa46303344327e0e) |
| D4 truthful node model | [e6e3174a13dae6e115cfaec9555e66249d355d8e](https://github.com/SOLHK/Swirl/commit/e6e3174a13dae6e115cfaec9555e66249d355d8e) |
| D5 encrypted atomic snapshots | [323549800227460c7dd1035a5ccab37a55d91260](https://github.com/SOLHK/Swirl/commit/323549800227460c7dd1035a5ccab37a55d91260) |
| D6 identity and running refresh | [6ddf53128a6ebceaf62a45a1bc5842659ff538aa](https://github.com/SOLHK/Swirl/commit/6ddf53128a6ebceaf62a45a1bc5842659ff538aa) |
| D7 Rust execution and business traffic | [148757627e8ac8d310e75e1af850b9598a18e072](https://github.com/SOLHK/Swirl/commit/148757627e8ac8d310e75e1af850b9598a18e072) |
| D8 platform and mounted-QML gates | [b60b9fb6a551bbaf7b687a43987788dd10b1f059](https://github.com/SOLHK/Swirl/commit/b60b9fb6a551bbaf7b687a43987788dd10b1f059) |

Remaining boundaries are explicit: there is no Linux/macOS secure storage
backend or full native application package in this Windows-focused product;
those store paths fail closed. Offscreen Windows Server CI does not certify a
physical Windows 11 display or its native file-picker interaction. No real
provider subscription or public-internet proxy node was supplied. VMess AEAD,
general B native conversion and C transport integration are not implemented in
this window. No external core masks these limitations. New pushes supersede
older CI runs so runners validate the newest cumulative source.

## Applied engineering guidance

Read repository `AGENTS.md`, `CONTINUE_DEVELOPMENT.md` and
`SWIRL_CORE_DEVELOPMENT_CONTRACT.md`; the user's current dedicated-branch
instruction supersedes their older destination. Applied
`.agents/skills/ui-ux-pro-max/SKILL.md`, including its focused
`error summary validation --domain ux` search. The existing QML dialog is
retained, with inline errors, keyboard-operable confirm/cancel buttons,
plain-text wrapping, bounded scrolling and no new animation/framework.
These are adaptations of accessibility outcomes to Qt, not copied web code.

Primary references consulted before implementation:

- [Qt QJsonDocument](https://doc.qt.io/qt-6/qjsondocument.html): response decoding, not the strict-input authority.
- [Qt QSaveFile](https://doc.qt.io/qt-6/qsavefile.html): atomic commit without direct-write fallback.
- [Qt QNetworkRequest](https://doc.qt.io/qt-6/qnetworkrequest.html): bounded asynchronous downloads and redirects.
- [Qt 6.10 QSslSocket](https://doc.qt.io/qt-6.10/qsslsocket.html#setLocalCertificate) and [Qt 6.10.3 SecureTransport](https://github.com/qt/qtbase/blob/v6.10.3/src/plugins/tls/securetransport/qtls_st.cpp): temporary-keychain behavior and explicit test trust anchors.
- [Apple TLS server-certificate requirements](https://support.apple.com/en-us/103769): serverAuth EKU and certificate validity requirements for the HTTPS fixture.
- [Qt QAbstractItemModel](https://doc.qt.io/qt-6/qabstractitemmodel.html): thread/selection guidance; existing QVariantList model retained.
- [Qt implementation](https://github.com/qt/qtbase/blob/dev/src/corelib/io/qsavefile.cpp): atomic-save design reference.
- [Xray outbound structure](https://xtls.github.io/en/config/outbound.html) and [V2Fly outbounds](https://www.v2fly.org/config/outbounds.html).
- [Rust FFI](https://doc.rust-lang.org/stable/nomicon/ffi.html) and [catch_unwind](https://doc.rust-lang.org/std/panic/fn.catch_unwind.html).

No upstream implementation was copied, no new protocol handshake was
implemented, and no external proxy runtime was introduced.
