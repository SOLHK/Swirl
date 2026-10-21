# Swirl Core X1.2-A: strict Xray/V2Ray JSON parser

Date: 2026-10-22 (Asia/Singapore). Delivery branch:
`work/xray-v2ray-json-import-20261021`.
Verified remote starting HEAD: `b88bb978d31fad1865e1b648cecd4f230bc3487c`.

## Recovery and scope

The remote branch was checked through the authorized GitHub connector. It did
not contain the previous parser. The X1 branch had the same HEAD, one
documentation commit ahead of subscription import
`bf40f6dd639b0a9583a0dbea8e50851ac0c9ed29`.

Actual local recovery sources were inspected:

- `/tmp/Swirl-X12-stage-a`: clean detached local commit
  `fde69c539a40c974c9244ca93f2e58851f0715ae`, containing the recovered strict
  parser, seven new unit tests and eleven adversarial tests, but not published.
- `/workspace/scratch/c325d1bf9da0/Swirl-json-import` and
  `/tmp/Swirl-X1-native`: mixed pending X1.2, Qt and protocol work. Their files
  and indexes were left intact.

This stage uses a new independent worktree at
`/workspace/scratch/e55b57034add/Swirl-X12-A`, based on the verified remote
starting HEAD. The parser-related candidate was restored there, reviewed and
corrected. Unused future normalized-node/execution/adapter types were removed:
this is an input parser, not a redesign of Swirl IR. No main update, force push,
private subscription refresh, Qt/UI integration, VMess implementation, routing
change or font work is part of this stage. The cloud workspace cannot save to
the user's Windows D drive.

## Public API for X1.2-B

The independent Rust API is `swirl_subscription::xray`:

```rust
use swirl_subscription::xray::{InputSource, parse_document_with_source};

let parsed = parse_document_with_source(
    br#"{"outbounds":[{"protocol":"http","settings":{}}]}"#,
    InputSource::File,
)?;
assert_eq!(parsed.input_kind, "configuration");
assert_eq!(parsed.outbound_paths, ["outbounds[0]"]);
// parsed.raw_json() is private source data, not a logging/reporting interface.
# Ok::<(), swirl_subscription::xray::Diagnostic>(())
```

`parse_document(bytes)` supplies `InputSource::Unknown`. Caller provenance can
be `Unknown`, `File`, `Clipboard` or `Subscription`; it deliberately carries no
URL or filename. Shared JSON does not reliably identify its original producer.

`ParsedDocument` provides:

- `input_kind`: `configuration`, `outbound`, or `swirl-outbound-array`.
- `source`: the safe caller-supplied source category.
- `configuration`: the parsed JSON view, retaining known and unknown fields.
- `outbounds` and aligned `outbound_paths`: all selected client objects in
  source order, without extracting a server inbound or choosing one endpoint.
- `global_sections` and `global_transport`: recognized root sections and the
  unchanged global transport value; no global defaults are applied.
- `diagnostics`: structured static error codes, safe paths and severity.
- `raw_json()`: exact bounded input bytes, including optional UTF-8 BOM,
  whitespace, key order and numeric spelling/precision. Ordinary
  `serde_json::Value` can round large integers/long decimals; exact-preservation
  consumers must use these bytes, not reserialize that view.

No native Outbound, conversion status or executable configuration is created.
The API performs no file/network access and has no Qt or proxy-runtime
dependency. Parsed documents have a redacted `Debug` implementation and no
automatic serialization; accessing raw values is an explicit private-data
operation.

## Recognized input and structural validation

- Current Xray/V2Ray full configurations with one or many `outbounds`.
- A single outbound object and a bare outbound array. The latter receives the
  explicit `SwirlOutboundArrayExtension` diagnostic.
- V2Ray historical full configurations: `outbound`, then `outboundDetour[]`,
  then `outbounds[]`, in the pinned upstream Build order. Paths retain their
  original envelope; global transport is not merged.
- `log`, `dns`, `inbounds`, `outbounds`, `routing`, `policy`, `transport`,
  `stats`, additional common globals, and V2Ray v5 root containers are retained.
  Unapplied globals receive `unsupported` diagnostics. Unknown root fields
  receive `UnknownGlobalFieldPreserved` with a masked name.
- Known nested `settings.vnext/servers/users`, stream/TLS/gRPC/WebSocket,
  common DNS/routing/policy/log and inbound envelopes are type-checked.
  Xray flat settings, StringList alternatives and signed gRPC parameters are
  preserved. Known outbound ports are uint16; inbound ports may be strings.
- Missing `protocol`, non-string `protocol` and empty/whitespace `protocol`
  fail distinctly. Optional values are never filled with defaults. Missing,
  null, false, empty strings, arrays and objects remain distinct in raw fields.
- Empty outbound lists return `EmptyOutbounds`; full configurations without a
  client envelope return `MissingClientOutbounds`. Neither falls back to
  server listeners. Single/array outbound entries with inbound-only markers
  (`listen`, root `port`, `sniffing`, `allocate`, `settings.clients/accounts`)
  are rejected. A marker-free single object follows the explicit
  single-outbound input convention.

These are structural checks for documented fields, not an exhaustive validator
for every protocol/extension schema. Unknown/future settings remain data;
UUID/password validity, protocol combinations, alias conflicts, required
endpoint/user fields, v5 plugin schemas, source conversion and runtime
capabilities must be checked by X1.2-B before anything becomes executable.

## Strict syntax and resource boundaries

| Resource | Default hard limit |
| --- | ---: |
| Input bytes, including BOM | 4 MiB (4,194,304 bytes) |
| Value depth, root = 0 | 32 |
| All values, including unselected/unknown sections | 100,000 |
| Combined outbounds across all envelopes | 2,000 |
| Retained document diagnostics | 64 |

Limits are checked before the relevant allocation/recursion or outbound clone.
No unbounded custom limits are exposed. Input is UTF-8 only, with at most one
optional leading UTF-8 BOM; malformed encoding returns `InvalidUtf8`. Empty,
whitespace-only and BOM-only files return `EmptyJsonInput`. JSONC comments,
single quotes, trailing commas, trailing roots, invalid escapes/surrogates,
NaN/Infinity and numbers outside serde_json's finite representation are rejected.
The exact-size, exact-depth and exact-count boundaries are tested.

Duplicate detection uses a custom recursive `DeserializeSeed`/`Visitor`.
Every object compares decoded keys against its existing map **before** reading
and inserting the next value. Thus `id` and `\u0069d`, and Unicode escape
equivalents, conflict at every depth, including unused globals and unknown
metadata. This does not rely on serde_json's default last-key-wins behavior.

Syntax errors expose numeric line/column where available, never the underlying
parser's Display message. Paths use a fixed schema-name allowlist and numeric
array indices; arbitrary keys become `[unknown]` because keys can themselves
contain secrets. Diagnostic `Display`, `Debug`, JSON encoding and successful
document `Debug` are tested against synthetic UUID/password, subscription
token, Authorization and credential-bearing URL canaries.

## Applied instructions, skills and provenance

Read and applied `AGENTS.md`, the latest `docs/CONTINUE_DEVELOPMENT.md` guidance,
and the full `docs/SWIRL_CORE_DEVELOPMENT_CONTRACT.md`. The user's explicit
X1.2-A branch/scope supersedes older branch/scheduling instructions.

Installed skills were discovered through the executor catalog and local
`SKILL.md` files. No Rust-specific implementation skill was present. The
installed `review-agent` engineering skill at
`/root/.codex/skills/.system/review-agent/SKILL.md` was read completely and
applied to independent, read-only, defect-first reviews. It identified the
candidate's missing nested checks, wrong CI trigger branch and loss of raw
numeric representation; all were addressed with independent public API
regressions. Final review found no remaining actionable defect. No unrelated
UI/design skill was claimed or applied. The Personal Context skill was used
only to locate the prior handoff; actual Git/worktree inspection determined
the recovery facts.

Official sources, exact commits, compatible field types and licenses are in
[the upstream record](SWIRL_CORE_X12_A_UPSTREAM_20261022.md): Xray
`1b1647cd9ddf0abc34b981d4611fc03bcac1ca74` (MPL-2.0), V2Ray
`de610153d59ee0bc9222a17680061d732fa14e7b` (MIT). Implementation is independent;
no upstream proxy implementation or runtime was copied or linked. Existing
serde/serde_json dependencies and Cargo.lock remain unchanged.

## Validation and delivery

Environment: Linux x86_64, rustc 1.99.1, cargo 1.99.1. All parser fixtures are
synthetic and offline. Historical test counts are not substituted for current
execution. The complete existing Rust workflow is preserved, with only its
reviewed branch allowlist and generator guard updated for this branch.

| Executed gate | Actual result |
| --- | --- |
| `cargo fmt --all -- --check` | Pass, exit 0 |
| `cargo check --workspace --locked` | Pass, exit 0 |
| `cargo clippy --workspace --all-targets --locked -- -D warnings` | Pass, exit 0 |
| `cargo test --workspace --locked` | 404 unit/integration tests + 1 doctest passed; 0 failed/ignored |
| `python tools/tests/test_core_development.py` | 57 passed |
| `git diff --cached --check` | Pass |

The subscription crate has 89 unit tests, 11 adversarial integration tests and
27 independent public API integration tests: 127 passes. Relative to the
verified remote baseline, this stage adds 45 Rust tests (7 recovered unit +
11 recovered adversarial + 27 additional public API) and one workflow guard.
These cover all 17 requested test categories and exact resource boundaries.

The first full workspace attempt failed at the existing FFI probe start test.
A separate minimal socket check reproduced `Operation not permitted` when
binding both IPv4 and IPv6 loopback in the default sandbox. The authorized
broader test execution then ran the same unmodified command and source to
completion, with all 405 tests passing. No test was skipped, weakened or
changed to conceal the environmental failure. The first failure remains in
the validation record; it is not counted as a pass.

Source hashes, exact command outcomes and the retained environmental failure
are in [the validation record](evidence/CORE_X12_A_VALIDATION_20261022.json).
These are Linux test results, not Windows/macOS/Qt or real-node acceptance.
Remote delivery requires a non-forced branch update and a separate GitHub
HEAD/tree verification. GitHub Actions outcomes must be reported for that
exact published commit; they are not inferred from these local checks.
