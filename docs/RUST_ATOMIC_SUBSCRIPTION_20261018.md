# Stable subscription identity and atomic native configuration

This stage continues `064bfa3218758162dd3af89d3bf03b27a6cb3237` on
`work/core-completion-20261017`. No supplier subscription was refreshed. All
new local build, test and report files are under `D:\Codex`.

## Implemented scope

`NodeStore` prepares an immutable import with final UUIDs before publishing it.
The plan binds to one store/revision, exposes the imported-ID/name mapping and
rejects stale plans, duplicate identities and collisions with unrelated sources.
Existing stable source/name/protocol identities survive refresh. Cross-source
same-name nodes remain independent.

Nodes, subscription success metadata and network settings now use one DPAPI
snapshot committed by `QSaveFile`. Failed validation, encryption/size checks or
file replacement leave the prior in-memory/durable state intact. Network settings
migrate from the legacy `.network.json` only when an embedded snapshot is absent;
the old file is retained and can no longer override migrated settings. Selection
continues to use the existing non-secret sidecar, with invalid/stale IDs ignored.
This is not a claim of completed power-loss/crash testing for every product path.

The actual asynchronous Qt importer now applies a limited, self-contained Clash
YAML/JSON profile: `proxies`, supported `proxy-groups`, and native ordered `rules`
with an explicit terminal `MATCH`. It resolves original member/default names to
prepared UUIDs, rejects external UUID references, and validates the candidate with
the same native DNS/routing conversion used by the Rust adapter. Its original
global configuration is retained inside the encrypted snapshot. Unknown root,
node/transport or group semantics are not silently converted to DIRECT. External
DNS dialects, direct-node rule targets, providers and other client formats still
need their own semantic mapping; unsupported documents are explicitly rejected
without partially applying nodes.

Missing subscription DNS preserves the user's existing secure resolver/hosts
settings. A successful native document profile durably selects its validated
rules instead of the unimplemented builtin MRS path. A profile without a selected
node fails closed; it cannot accidentally start an implicit DIRECT session.
Running sessions reject full-document replacement. Node-only refresh still
preserves the existing live-session contract, but must also validate the retained
policy graph against the candidate nodes before saving. A canceled parse cannot
commit after shutdown. The compatibility build explicitly rejects full-document
execution and retains its existing node-only import behavior.

## Independent review and regressions

Review found and led to fixing cross-source name merging in the initial staged
validator, acceptance of unsupported PROCESS-NAME rules, clearing of omitted DNS,
legacy group-field loss, dangling graph references on node-only refresh, and UUID
aliases in both members and default selection. Regression coverage checks these
fail closed, stable identity, stale/foreign plans, unchanged snapshots after real
QSaveFile failure, legacy migration, original-name mapping, cancellation, durable
profile restoration and production-style startup flags.

The end-to-end controlled test downloads a subscription over loopback HTTP,
applies it through `NodeImportService`, connects the Rust adapter, and proves
`MATCH,route` reaches independent SOCKS exit B instead of globally selected A.
It also reopens the same encrypted store with production-style routing flags and
proves B again. These are real loopback protocol transfers, not provider-internet
verification. The new private corpus remains untested on real provider nodes.

## Windows test isolation and the startup incident

The earlier unfiltered CTest invocation timed out the appearance test at its
original 45-second limit and then encountered a missing Qt6Gui.dll startup dialog.
The existing Qt 6.10.3 x64 runtime is now supplied through process-local PATH.
No tool reinstall or global PATH change was needed. Qt's Windows test mode still
uses Known Folders under the user profile, so a separate explicit `SWIRL_TEST_ROOT`
now scopes application-owned test settings, data, temporary files and Qt caches.
Normal production paths are unchanged unless both test mode and that variable
are present. Invalid roots fail rather than falling back to user storage.

The original appearance assertions and 45-second limit are unchanged. Corrected
runtime/isolation passed in 5.68 seconds with zero appearance failures and a
successful fresh-process settings restore; the final rebuilt application was
checked again. The previous timeout is retained in evidence, not deleted. The
rerun resolves the reproducible startup/environment problem, but is not a claim
of exhaustive UI, OS-owned disk-I/O or installation lifecycle validation. No
user C-drive files were removed. The existing installed Swirl process was not
stopped or replaced.

## References and implementation boundary

- [Mihomo config structures](https://github.com/MetaCubeX/mihomo/blob/Meta/config/config.go)
  and [license](https://github.com/MetaCubeX/mihomo/blob/Meta/LICENSE) were used to
  identify document fields and avoid guessing DNS/strategy equivalence. Its
  GPLv3 source was consulted, not copied into Swirl.
- [Qt QSaveFile](https://doc.qt.io/qt-6/qsavefile.html) describes the existing
  atomic-file primitive reused here.
- [Qt Windows standard paths](https://github.com/qt/qtbase/blob/v6.10.3/src/corelib/io/qstandardpaths_win.cpp),
  [Windows Known Folders](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath)
  and [Qt QML disk cache](https://doc.qt.io/qt-6/qmldiskcache.html) informed the test
  environment fix.

All new Swirl logic was implemented independently. No third-party implementation
code, new dependency, new cryptographic primitive or complete proxy backend was
added. Existing standard Qt/Rust primitives and licenses remain in place.

## Acceptance boundaries and next work

Machine-readable results, source/produced-binary hashes, command/log hashes and
CI identity are recorded in `evidence/RUST_ATOMIC_SUBSCRIPTION_20261018_VERIFIED.json`.
The preceding implementation `4e993d6` has independently confirmed success for
Linux, macOS and Windows Rust/Qt CI in run 39106885139. That result cannot certify
this stage; this stage's precise commit must complete its own CI.

The fixed progress baseline is `SELF_DEVELOPMENT_PROGRESS.md` and
`evidence/SELF_DEVELOPMENT_PROGRESS_V1.json`: 79 items, fixed A-F weights, 10.83%
verified acceptance weight. This is not code implementation rate. This stage
advances A06/A07 to partial implementation; other formats, strict external DNS,
all-corpus execution, abrupt-process/power-loss matrices and installer behavior
remain. Protocol, format and network acceptance remain separate.

Next implement strict external DNS-to-native mapping without treating Mihomo
respect-rules as Qt force_proxy_hosts. Preserve whole-document provenance, add
other client formats and direct-node policy targets, then replay the encrypted
corpus and build the per-record authorized real-network ledger. Never refresh
providers outside a new explicit window.
