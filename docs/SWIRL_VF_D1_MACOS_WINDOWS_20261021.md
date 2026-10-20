# D1 macOS source baseline and cross-platform delivery — 2026-10-21

Latest evidence: exact original loads on macOS 27.0.1 CI (32/32 identities), but
has 96/384 strict axis-readback failures. Local macOS 26.3 refuses that source in
CoreText while Apple HVF works. Full-GID default-design comparison completes
47,102 GIDs using existing comparison rules; 38 legacy type rejections are
retained and their existing raw-Q companion checks pass. Original production
faces remain 0/32. Windows Server synthetic DirectWrite passes; Windows 11 and
actual Qt/Swirl acceptance are NOT_RUN. There is no accepted Apple-derived TTC.
Machine-readable counts: [D1 evidence](evidence/SWIRL_VF_D1_MACOS_WINDOWS_20261021.json).

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

## D1 saved checkpoint and D2/D3 controls

D1 is saved remotely as **`ab4394b836cce7934c28e4e9493bda6e1e3c3842`**,
parent `6b9628e6a9a5a864e5a7e210cd916868804564c8`, exact tree
`de9ed45868af871436cd66ac695ba0185f3497b5`.
The local HTTPS push failed because no terminal credentials were configured.
The existing connected GitHub tools created the same reviewed tree and commit
without changing any App/Secret. The local-only commit `986b4be` is preserved on
`work/vf-macos-windows-d1-20261021-local-snapshot`; the task branch follows the
remote commit with the identical tree. No local history was reset or rebased.
A concurrent W1 advance to `127e9fc` was fetched and left untouched.

The new baseline also ran natively on the self-authored two-face fixture:
2/2 physical faces verified, 24 fixed axis requests, 18 strict passes / 6 retained
strict failures. Thus the blocked original result is distinguished from both a
working installed system source and a working portable fixture on this host.

With all eight added tests, the full local suite is now **598 discovered = 591
passed + 7 platform-specific skips**, 23.141 s; no failure/error. This includes
the actual HarfBuzz GPOS tests. The separate unmodified strict native
reconstruction test actually ran and failed at the retained 849/850 assertion.
The independent existing `test_native_table_metrics.py` actually completed:

- Self-authored 2-face / 3-GID reconstruction, 3 original axes, distinct UPEM
  1000/1128, serialized TTC **3,424 bytes** generated and re-opened.
- Original native paths plus explicit source-table metrics: 174 records pass.
- Candidate native remeasurement: 58 requests / 174 records, maximum control
  point, table metric and bounds differences all **0** against the fixture.
- The old raw CoreText gate remains **FAIL** in the same report. Source-table
  metric success does not represent native API metric success.
- The existing integration test removes its temporary fonts by design; full
  reports are under `build/vf-d1-private/native-table-metrics/`. This generated
  fixture is not an Apple conversion and is never the original deliverable.

`.github/workflows/swirl-vf-macos-windows-d1.yml` is limited to this dedicated
branch. It reuses existing fixture generators, strict native tests, table-metric
reconstruction and DirectWrite C++/PowerShell probes. It runs macOS-15 and
Windows Server 2022 controls, preserves native failures without continue-on-error,
and uploads only self-authored synthetic reports/images. It never opens an
Apple font or uploads any font binary. YAML parsing and whitespace checks pass;
actual remote CI is pending at this source checkpoint. Windows 11 remains
NOT_RUN even if Windows Server DirectWrite succeeds.

## D3 actual CI terminal result and retained synthetic build

Source checkpoint **`ce33013b4841beff21ca6e4de2b85547d6bab163`** was saved with
parent ab4394b and exact tree `3259676faa479327ea40a626a6ab302f084a42de`, then
synchronized locally by a normal fast-forward. No other branch was updated.
[Run 39474695780](https://github.com/SOLHK/Swirl/actions/runs/39474695780)
completed **failure** at 2026-10-20 18:27:05 UTC. Actual job steps and both
complete job logs were read; no running job is counted as passed.

- Windows job **118807512454**: **success**, Windows **Server 2022 / 10.0.20348**.
  Both actual DirectWrite invocations returned `PASS_NATIVE_PROBE`; the original
  three-face control and two-face production HVAR/VVAR control were requested
  with `-AllGlyphs -Render` (five DPI scales). This is a synthetic Server result,
  not an original-derived TTC, system install, Windows 11, Qt or Swirl result.
- macOS job **118807513515**: **failure**. All eight new tests passed, baseline
  verified 2/2 faces and recorded 18/24 strict axis passes. The unchanged native
  metric gate failed at **849 versus 850.0**, tolerance **0.03125**. The independent
  table-metric native reconstruction subsequently completed successfully. Its
  success does not hide the failed step or make the overall run green.
- Artifact metadata was read: Windows **12287859189**, 39,840 bytes, GitHub digest
  `92652651d527bdd78ad49deb21c792bb4d1b891e7ddc65f4f06ff21f6b8a8494`;
  macOS **12289470936**, 15,243 bytes, GitHub digest
  `0bc2279e61bde84773538f8ecc3d0c46d94e0e9a0b2ab278d0fea6dfdf04535d`.
  **ZIPs were not downloaded/rehash-verified**: the connected download tool
  failed connecting to its blob-storage host. These digests are API metadata,
  not locally verified bytes. Detailed native face/raster counts inside ZIPs
  remain unaudited; the claims above are bounded to actual executed job logs.

A separate local run of the existing builder plus existing verified-axis and
explicit-table-metric adapters retained a **self-authored synthetic** candidate:
`build/vf-d1-private/retained-synthetic-control/Swirl-VF.ttc`, 3,424 bytes,
SHA-256 `74168ffac87764d52b388d37b1868efb044bd119dd0757c0b6df4a0e21327485`.
It has two faces / three GIDs per face; it is **not the Apple deliverable**.
All source/candidate/checkpoint material stays local and ignored.

Existing independent validators checked GIDs/cmap/three axes/defaults/hidden flags,
fvar bytes, tracking, horizontal and vertical metrics, native transcript,
serialized model and TTC table preservation. Native reread compared 58 requests /
174 records with zero observed contour, table-metric and bounds difference.
HarfBuzz **14.6.0** completed **16** source/candidate comparisons (2 faces × 4
locations × horizontal/vertical) with exact glyph/advance/offset equality.
fontTools generated/saved/reopened **8** static instances, all fully instantiated.
The read-only audit found **0 issues / 0 parser errors** on this synthetic TTC.
None of these static/finite checks proves continuous-space or Apple equivalence.

## D2 original HVF control: distinguish the API layers

The existing `run_hvf_oracle.py` and unmodified C oracle compiled and actually
ran on macOS 26.3. Apple **libhvf 1.0.2** accepted the exact user original's
HVGL 3.1 and extracted face 0 / GIDs 0..19 at normalized design `[0,0,0]`,
20/20 with native exit 0, valid summary and unchanged source. A subsequent run
extracted **all 47,102 GIDs**, zero native failures, matching header/summary counts,
unchanged source. These private callback outlines are never uploaded.
This is extraction, not yet comparison, user-coordinate mapping or metrics.

An isolated process-scoped registration probe also ran on the original and
returned false, domain `com.apple.CoreText.CTFontManagerErrorDomain`, code **103**,
with zero identity-verified faces. The local SDK names 103
`kCTFontManagerErrorUnrecognizedFormat` (104 is InvalidFontData).
No successful registration or system font installation occurred. The observation
therefore narrows the issue to CoreText's source-loading path; it does not prove
the HVGL decoder is generally unavailable or identify the exact causal table.
Do not infer that changing the font header would be a valid repair.

The full-GID **comparison** is separate from extraction and runs with the existing
renderer, unchanged 1/32 comparator and existing preserved-Q companion. It has
private checkpoints every 512 GIDs, bound to source, native-output and relevant
code hashes. It does not perform a production rebuild or change A3/B1/C1.
Its terminal result will be recorded separately; no incomplete comparison is
counted as full-GID PASS here. Private commands/scripts remain under
`build/vf-d1-private/`; original source data and native logs are not public CI input.

## D2 fresh design coordinates and matching-host CoreText follow-up

A predeclared `random.Random(20261021)` sample of 64 GIDs at three new mixed
normalized design locations completed **192/192** comparisons with Apple HVF.
Locations: `[-.9375,.8125,-.6875]`, `[.123456789,-.7654321,.3456789]`,
`[.9999,-.9999,.0001]`. Legacy comparator failures: **0**; unchanged 1/32 budget;
maximum point error **4.547473508864641e-13 FUnit**; input unchanged.
This extends finite design-space coverage; it is not user-coordinate mapping,
metrics, all-axis continuity or Windows acceptance. Private reproducible driver
and safe result: `build/vf-d1-private/compare_fresh_design.py` and
`fresh-design-comparison.json`. No algorithms were altered for this result.

The dedicated workflow now additionally reuses the repository's existing
`xcode-27` host to run the **same** baseline on the exact-hash original, using its
existing system file. This does not replace or upgrade this local macOS 26.3.
Only explicit aggregate keys (counts/status/source and code hashes/OS version)
can reach stdout and the original-summary artifact. Full original baseline,
font-level metrics, table identities and fonts are excluded. No private per-GID
observations are requested. Existing synthetic jobs and the strict failing gate
remain intact. YAML parsing/branch checks pass; this added native job has not
executed at this checkpoint. Source mismatch/missing font/identity failure remains
nonzero, not a fallback to a different installed font.

## D2 terminal all-GID result and D5 delivery boundary

The local default-design comparison completed **47,102/47,102 GIDs** at face 0 /
normalized `[0,0,0]`, 395.200 s, unchanged source, complete native header/summary,
source/output/code bindings checked. The **unmodified legacy comparator** passed
**47,064**, retaining **38 `segment_types_differ` rejections**. Only these 38
were sent to the existing preserved-raw-Q companion; all **38/38** passed. Thus
47,102 pass the existing combined comparison policy, with zero numeric failures
and maximum point discrepancy **9.890754881780595e-12 FUnit**, unchanged limit
**0.03125**. This is not 47,102 separate companion calls. No old rejection was
removed, comparator changed, glyph model built or user-axis mapping accepted.
One face/default design is not 32-face user-space or continuous-space equivalence.

Private result/checkpoints: `build/vf-d1-private/original-hvf-all-default/`.
The independent driver `build/vf-d1-private/compare_all_default.py` binds its own
SHA-256 `b65f3079e5f41e120bdeb04a308d70481d39a322a4ad92807772bc3e2d81e32f`.
Its checkpoints every 512 GIDs allow an interrupted run to resume without
accepting changed source/native output/renderer/comparator code. Native callback
JSONL (~505 MiB), all font data and full private logs remain ignored/local only.

The exact-source matching-host follow-up is saved at source
**`d10354fa02495d63e141b301ffb14be3c1941ac1`**. [Run 39476027356](https://github.com/SOLHK/Swirl/actions/runs/39476027356)
completed **failure** at 2026-10-20 18:36:11 UTC; all three terminal job states
and all three actual logs have been read:

| Actual job | Result and scope |
| --- | --- |
| Original baseline 118812091949 | **success**, actual macOS **27.0.1 build 26A434**, exact original SHA/size, **32/32 physical identities**, **384 strict axis requests / 288 passed / 96 retained failures**, input unchanged |
| Windows 118812092483 | **success**, Server 2022 / 20348, both actual DirectWrite controls `PASS_NATIVE_PROBE` |
| macOS synthetic 118812092557 | **failure**, eight new tests pass, strict **849/850** failure retained; independent native/table reconstruction step succeeds |

Native extractor SHA `8e5aaa0a921f24a656766c1e24a0d388397cdaddbdfebae1ab415c0d7c3f3bbf`
and generated baseline harness SHA
`7c8d6c01b30d19d5a106d4840c299d513f6c072ffe5117625c0614b3fc8367ad`
were independently recalculated locally and match the original CI summary.
Original CI success specifically means source identity, not all requested axes
or production acceptance. This establishes different source-loading outcomes on
the two measured hosts; it does not isolate the internal OS cause.

Existing Swirl source was reviewed read-only: `FontFileInspection.h` retains the
128 MiB limit, physical TTC directory/axis guards and explicit rejection of
HVGL-only fonts; `FontManager.cpp` uses `QFontDatabase::addApplicationFont` only
after that gate. Width adaptation and Qt implementation remain owned by W1/D1
Windows work. No UI or font-loader file was changed, and no real Qt/Swirl result
is inferred from these source checks.

**Delivery is blocked, with evidence preserved:** original production models
and faces **0/32**, no accepted Apple-derived `Swirl-VF.ttc`; A3 user-coordinate
mapping, B1 strict metrics/vertical origin and C1 full rebuild gates remain
open. Original Windows 11 installation/DirectWrite/Qt/Swirl, complex mixed-text
layout, visual/DPI quality and performance remain unvalidated. The 3,424-byte
local file above is only an original synthetic control. Integration owner must
review/merge this isolated branch; no merge was performed and no source-file
conflict was encountered. W1 advanced concurrently to `82541d4` and was preserved.

For a new local native extraction (fresh directory):

```sh
build/vf-d1-private/venv/bin/python tools/swirl_vf/platform/run_hvf_oracle.py \
  --font ~/Downloads/PingFangUI.ttc \
  --binary build/vf-d1-private/original-hvf/hvf_oracle \
  --out build/vf-d1-private/original-hvf-next --face 0 --coords=0,0,0 --count 0
# After interruption, resume the existing bound comparison checkpoint:
build/vf-d1-private/venv/bin/python build/vf-d1-private/compare_all_default.py
```

A completed comparison intentionally refuses overwrite. The primary next code
work belongs to the existing A3/B1/C1 owners, using the matching-host and new
all-GID/fresh-design evidence; do not bypass their acceptance gates to manufacture
a final font. The next Windows 11 check requires an actual original candidate
and Windows 11 desktop, not another Server synthetic result.
