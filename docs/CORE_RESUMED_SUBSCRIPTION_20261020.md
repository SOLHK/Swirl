# Resumed subscription boundary and cache validation (2026-10-20)

## Source recovery and preserved ancestry

The new session queried GitHub before changing source. The initial remote was
`cf99f2c5a1664879ce1e3ad5e6669388ca10a3a3`, a descendant of both the exact Core
baseline `5d3ec74d212276726e96be8ecbd4c2f92adc4e53` and font checkpoint
`f72187f70d0af20fb197fb3e49389b53e8ce31a0`. The subscription and public Qt
changes were found as actual uncommitted files in the surviving previous
workspace. They were recovered into an independent checkout, not reinvented
or represented as an earlier successful push.

Concurrent font commits through `72f1c20a52241c9f506ad601902c9b895c289cda`
were inspected and fast-forwarded intact. This stage changes only subscription
boundaries, NodeStore reload validation, their tests and these Core records.
The separate Windows public Qt gate is the next source checkpoint.

## Recovered behavior and two additional reproduced defects

- Rust accepts the explicit neutral `headerType=none` for the supported
  VLESS/REALITY TCP URI profile. It retains the complete original URI, with
  fingerprint, REALITY keys, flow and other options still subject to current
  capability checks. Arbitrary JSON/YAML raw-uri metadata grants no exemption.
- Qt retains and blocks unmapped TCP `path`, `host` and `serviceName`, including
  explicitly empty values. Empty explicit transport is distinct from omission.
  WebSocket path/Host mapping and valid omitted defaults are preserved.
- Both parsers block extra VLESS authority passwords and non-neutral URL paths.
  The resumed review additionally reproduced URL dot-segment normalization
  erasing a forbidden path in Rust; validation now examines the original path
  before `/private/..`, `/.` or encoded dot segments can become a neutral `/`.
- The resumed Qt review additionally reproduced silent acceptance of empty
  `headerType=` and inappropriate WebSocket headerType. They now produce
  preserved conversion diagnostics; legal TCP `headerType=none` remains valid.
- NodeStore reload rechecks preserved URI source with the current importer and
  adds bounded diagnostics in memory. It retains IDs, parameters, originals,
  selection and existing conversion diagnostics without rewriting ciphertext.
  Native capability is computed by the current mapper, not restored from an
  obsolete candidate count. Missing REALITY fingerprint still fails closed.

Manual node editing intentionally retains the original source while changing
options. This fix does not reject every edited node by comparing all current
fields with that historical source; it blocks unimplemented source requirements
and preserves the existing explicit editing semantics.

## Actual local verification of this stage

The final source passed Rust `fmt --check`, workspace `check`, warnings-as-errors
`clippy --all-targets`, and **324 regular tests plus one doctest** (82 in the
subscription crate), zero failures and zero ignored tests. Dependencies were
locked and offline, with an independent Cargo target directory. The first
restricted run failed at loopback UDP bind with EPERM; that original log is
retained. The unchanged network suite passed with local socket access enabled.
The final gate was rerun after the original-path correction.

The production Qt importer was freshly compiled against Linux Qt 6.4.2. The
expanded matrix has **58 malformed URI/Base64 cases**: recovered source blocked
54/58, corrected source blocked 58/58 and retained all 58 original URIs. Five
valid-default cases, eight neutral authority/path controls, WebSocket mapping
and duplicate/conflicting option controls passed. Four new production test
slots passed moc and C++23 syntax checks against actual engine declarations.

The old local Qt SDK cannot compile the complete current application because
its QStandardPaths lacks existing newer StateLocation enum values. That SDK
limitation was retained, not patched around. Full current Qt compilation and
Windows DPAPI execution remain exact-new-SHA CI requirements.

Compact final file hashes, commands, results and failure identities are in
[the stage evidence](evidence/CORE_RESUMED_SUBSCRIPTION_LOCAL_20261020.json).

## Rechecked old CI: scope remains exact

[Rust run 39373075184](https://github.com/SOLHK/Swirl/actions/runs/39373075184)
and [App run 39373075143](https://github.com/SOLHK/Swirl/actions/runs/39373075143)
were re-read from GitHub. Both belong to **5d3ec74d212276726e96be8ecbd4c2f92adc4e53**;
Linux, macOS, Windows and App jobs finished successfully. That old source has
320 regular tests plus one doctest, not this stage's count. Windows actually
linked Swirl.exe, and its dedicated Qt/DPAPI REALITY/Vision/Chrome133 fixtures
passed. The generic Qt suite had 60 passes and seven explicit fixture skips.

Old Windows Qt origins were controlled localhost targets. Its A peer had one
bidirectional Vision Direct HTTPS case; B had no HTTPS case. Four old Linux
Rust profiles reached public HTTP 200 and certificate-verified HTTPS 301.
Those observations do not establish Windows Qt public access, A/B HTTPS Direct,
the newly recovered source, private supplier authentication or physical Windows.

## Primary references and limits

- [v2rayN BaseFmt.cs at 66dd7da6](https://github.com/2dust/v2rayN/blob/66dd7da6e69b3bcad51115d1c7d5e017b7ef0dd0/v2rayN/ServiceLib/Handler/Fmt/BaseFmt.cs),
  GPL-3.0: official exporter emits `headerType=none` for RAW/TCP.
- [Xray sharing specification](https://github.com/XTLS/Xray-core/discussions/716)
  and [RAW transport documentation](https://xtls.github.io/config/transports/raw.html):
  explicit transport/security fields must retain their meaning.

The changes are independently written boundary checks with no copied upstream
code or additional dependency. No private manifest, subscription, cache or
provider node was accessed; the current candidate count for the user's 59 nodes
is unknown. The source fixes do not prove authentication or Internet access.
Historical DNS, DoH TLS and health-probe timeouts remain unresolved. The formal
acceptance baseline is unchanged: **79 items, 6 fully passed, 10.83% weighted**.
