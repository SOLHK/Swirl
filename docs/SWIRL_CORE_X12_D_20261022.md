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
- [Qt QAbstractItemModel](https://doc.qt.io/qt-6/qabstractitemmodel.html): thread/selection guidance; existing QVariantList model retained.
- [Qt implementation](https://github.com/qt/qtbase/blob/dev/src/corelib/io/qsavefile.cpp): atomic-save design reference.
- [Xray outbound structure](https://xtls.github.io/en/config/outbound.html) and [V2Fly outbounds](https://www.v2fly.org/config/outbounds.html).
- [Rust FFI](https://doc.rust-lang.org/stable/nomicon/ffi.html) and [catch_unwind](https://doc.rust-lang.org/std/panic/fn.catch_unwind.html).

No upstream implementation was copied, no new protocol handshake was
implemented, and no external proxy runtime was introduced.
