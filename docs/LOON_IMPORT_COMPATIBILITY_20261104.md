# Loon node import compatibility — 2026-11-04

## Verified references and scope

Before implementation, the following primary GitHub sources were read:

- [Loon's node manual](https://github.com/Loon0x00/LoonManual/blob/master/docs/cn/node.md).
- [Loon's example configuration](https://github.com/Loon0x00/LoonExampleConfig/blob/master/example.conf).
- [subconverter format support](https://github.com/tindy2013/subconverter/blob/master/README.md).

The field mapping was independently implemented from the documented grammar;
no third-party implementation was copied. All regression data is synthetic,
using reserved `.invalid` hosts and authored credentials. No private subscription
URL, provider response or decrypted cache is included.

This fixes actual node-format gaps. An HTTP 403 response occurs before parsing
and cannot be explained or certified repaired by this change alone.

## Resulting behavior

- Loon VMess's positional cipher followed by UUID now maps correctly in Qt and
  the Rust INI inspector. The prior Qt mapping treated the cipher as the UUID;
  Rust had no mapping for either positional field. Existing named Surge-style
  credentials and legacy single-UUID entries are retained.
- Standard Loon WebSocket `path` and `host` fields reach the existing native
  WebSocket transport. TLS name, cipher and UUID retain their exact meanings.
  Duplicate aliases do not overwrite authentication or transport requirements.
- Rust's raw INI inspector now maps positional HTTP/HTTPS authentication.
  Qt already mapped these credentials; its tests now exercise quoted delimiters
  through the actual Rust projection. An HTTP Basic username containing a colon
  remains rejected, while legal quoted commas/percent signs and password
  delimiters remain unchanged.
- Malformed VMess `alterId` no longer becomes zero through Qt's `toInt()`
  conversion. Unknown options, unsupported transport/UDP requirements and
  duplicate authentication aliases remain non-executable or fail parsing.
- Complete original lines remain in provenance. The existing VMess strict
  allowlist recognizes `raw-ini` as provenance metadata; it does not interpret
  that text as executable configuration. No protocol, certificate policy or
  network fallback was added.

## Validation

The new anonymous Rust cases failed against the previous mapper before the
production change. Qt's new VMess case likewise failed at UUID validation before
the mapping was repaired. Positive cases compare typed outbound data, including
authentication, TLS and WebSocket fields; negative cases preserve source bytes
and reject conflicting or unsupported requirements.

After the Rust changes, the complete `swirl-subscription` package actually ran:
**305 tests passed, zero failed or ignored** (163 unit tests and 142 integration
tests). `cargo clippy -p swirl-subscription --all-targets -- -D warnings`, scoped
formatting and changed-file whitespace checks passed. After rebuilding the
paired Rust DLL and Qt test executable, the delivery owner ran the complete
`SwirlSubscriptionFormatTests` suite: **9/9 passed**, including both new Loon
cases through the typed Rust projection. The related Node UI suite subsequently
passed **645 checks, zero failures**. This report does not claim a real node connection,
provider download success or full Loon configuration compatibility.
