# D1 macOS source baseline and cross-platform delivery — 2026-10-21

## Isolation and ownership

This window uses only `work/vf-macos-windows-d1-20261021` in
`~/Swirl-worktrees/vf-macos-windows-d1`, created from freshly fetched integration
HEAD `6b9628e6a9a5a864e5a7e210cd916868804564c8`. The original `~/Swirl` worktree was clean on
`work/vf-macos-native`, HEAD `e6b44f83cd92e4b8082d54a84d4a98bef1cd5b28`.
No other worktree, branch, history, App configuration or secret is changed.
Only explicit pushes of this window's branch are authorized here.

Fetched parallel tips at entry: A3 `66594e9`, B1 `7902cdb`, C1 `c0fe6c4`,
Windows D1 `844544f`, W1 `134298b`. They are read-only references, not merged.
The existing integration handoff rejects portions of B1/C1/Windows D1;
branch existence or a green synthetic test is not acceptance of their work.
The older macOS-native branch already contains a source-identity diagnostic;
this work does not copy its commit into integration or change that branch.

## Verified local baseline

Host: **macOS 26.3 build 25D125, arm64**, Swift **6.3.3**.
It is not the macOS 27 / xcode-27 host recorded by earlier native CI.
Python 3.12, fontTools 4.61.1, NumPy 2.2.6, uharfbuzz 0.56.3 are installed
in this worktree's ignored `build/vf-d1-private/venv`.

The user original exists at `~/Downloads/PingFangUI.ttc`:

- 61,473,880 bytes; SHA-256
  `39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
- 32 faces, each 47,102 GIDs; 1,507,264 face/glyph slots.
- Five distinct cmap sets; Unicode union **35,741** codepoints. Per-face coverage
  counts range from 30,906 to 34,555. Coverage is metadata, not rendered equality.
- Original tables: `head meta name OS/2 hhea avar BASE cidg GSUB cmap fvar VORG
  post maxp vhea STAT trak HVAR vmtx hmtx hvgl`.
  It has HVGL outlines; no standard `glyf/loca/gvar`, `VVAR` or `MVAR`.
- Original `WDTH` and `HGHT`: 1..1000, default 500, hidden. Original `wght`:
  100..900, with per-face defaults retained by the report, not forced to 400.
- The existing `audit_font.py` ran read-only, retained raw avar order/duplicates,
  saved full private metadata, and confirmed input unchanged. Its issues are
  retained; an audit run is not OpenType conformance or native rendering PASS.

**Original native result: BLOCKED_SOURCE_IDENTITY, 0/32 faces verified.**
CoreText URL descriptors: 0; data descriptors: 0; CGFont creation: false.
No original axes, glyph metrics or outlines were measured. The existing
production builder was actually executed, with private checkpoint support,
and exited 2: `native oracle could not verify every requested physical face`.
It completed zero models/faces and generated no TTC. This occurs before the
macOS-27 axis/origin blockers; it neither resolves nor contradicts those results.

A separate control used this Mac's installed font at the existing system path:
61,081,560 bytes, SHA-256
`7ea432196657d83d2675521224be420f9aeb0d7e9def7da6cb2b4c364d8e0983`.
It has 32 faces with **47,098** GIDs each. CoreText returned 268 URL descriptors;
the production full-table identity test verified all 32 physical faces.
384 fixed axis requests produced 288 strict passes and 96 strict failures.
Default global font metrics were recorded privately only after identity checks.
Data descriptors and CGFont creation were unavailable even for this control;
those two APIs alone cannot decide CoreText support. This control must never
substitute for the exact user original. A newer-HVGL/host incompatibility is a
hypothesis, not an isolated causal finding; do not modify font version bytes or
system security to bypass it.

## Implementation and validation

`tools/swirl_vf/platform/macos_source_baseline.py` reuses the production Swift
prefix verbatim, including parser, full-table identity and strict axis validator.
It adds only a no-outline native main plus read-only fontTools coverage metadata.
Existing outputs and wrong expected source hashes are refused. Reports include
source/extractor/harness hashes; stdout contains a fixed aggregate summary.
Full reports/logs stay in a fresh private directory and are not CI artifacts.
Native identity failure returns nonzero and records zero measurements.

Eight new tests pass: source substitution, wrong source, duplicate/missing faces,
malformed/falsified counts, missing native identity, preserving existing output,
real two-face metadata and unchanged production prefix. Existing full Python
suite: **590 discovered = 583 passed + 7 platform-specific skips**, 27.227 s.
Five skipped cases require real Linux HarfBuzz C APIs; two require explicit
native integration. These are not missing uharfbuzz: the seven existing Python
HarfBuzz GPOS tests executed. Existing audit suite: **6/6**.

Existing real `test_coretext_extract.py` compiled and ran. The production Swift
axis validator passed **22/22**. Strict synthetic metrics **FAIL**, face0 / GID2,
vertical advance **849 vs 850.0**, unchanged tolerance **0.03125**. Extraction exit
0 does not turn the validating test green. Raw results remain private locally.
No B1 compensation, A3 mapping, C1 builder or W1 UI algorithm has been changed.

## Primary references reviewed before implementation

- [fontTools TTC reader](https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/ttLib/ttCollection.py)
  (MIT): collection/face reading through its API; avoid sharing mutable table objects.
- [HarfBuzz](https://github.com/harfbuzz/harfbuzz) (MIT) and
  [FreeType](https://github.com/freetype/freetype) (FTL/GPL): independent shaping
  and outline engines; existing project probes retained.
- [Microsoft DirectWrite custom font set sample](https://github.com/microsoft/Windows-classic-samples/tree/main/Samples/DirectWriteCustomFontSets)
  (MIT): explicit local custom-font identity and face enumeration; reuse Swirl's probe.
- [OpenType collection format](https://learn.microsoft.com/en-us/typography/opentype/spec/otff)
  and [CoreText URL descriptors](https://developer.apple.com/documentation/coretext/ctfontmanagercreatefontdescriptorsfromurl(_:)):
  container metadata and actual native API loading are separate observations.
- [Qt text engines](https://github.com/qt/qtbase/tree/dev/src/gui/text): existing
  Qt 6 application path is preserved; no new UI framework or font substitution.

No upstream implementation was copied. Original/derived fonts, table payloads,
per-GID observations, drawings, credentials and full original audit are excluded
from commits and public Actions.

## Reproduction and outstanding acceptance

From this isolated worktree, use a **new** output directory each run:

```sh
build/vf-d1-private/venv/bin/python tools/swirl_vf/platform/macos_source_baseline.py \
  ~/Downloads/PingFangUI.ttc --output build/vf-d1-private/original-baseline-next \
  --expected-sha256 39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890
build/vf-d1-private/venv/bin/python tools/swirl_vf/platform/test_coretext_extract.py \
  --output build/vf-d1-private/coretext-next --require-native
```

Local private evidence: `build/vf-d1-private/original-audit/`,
`original-baseline/baseline.json`, `system-baseline/baseline.json`,
`original-build/reconstruction.json`, `coretext/`, and associated `*.log`.
**No accepted `Swirl-VF.ttc` exists.** Windows 11 desktop, system installation,
original equivalence, real Qt/Swirl, mixed-text/DPI/performance acceptance remain
NOT_RUN. Integration owner must review this branch; this window does not merge it.
Next independent work: generated-fixture native reconstruction/structural tests
and actual Windows Server DirectWrite CI, preserving the synthetic/original and
Server/Windows-11 distinctions. Exact-original native testing requires the
matching supported host; keep the existing macOS-27 evidence, do not relabel this
Mac as macOS 27.
