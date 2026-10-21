# D1 macOS source baseline and cross-platform delivery — 2026-10-21

D2 continuation is now complete for its bounded scope: 32 × 34 × 15 native
samples passed the existing combined comparison on both Mac hosts; all original
96 strict axis failures are diagnosed and retained; fresh-UPEM synthetic metric
failures are reproduced without a production fix. See the final D2 section and
[evidence](evidence/SWIRL_VF_D2_CI_20261021.json). Windows 11 remains NOT_RUN.

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

## D2 continuation — 32-face bounded native verification (2026-10-21)

Resumed from freshly fetched dedicated HEAD `ff2ed179fbbe5bc55a634a19ac597ad0604aa08c`;
worktree was clean, original source/hash and D1 environment/checkpoints retained.
No D1 full-GID run was repeated. A3 `66594e9`, B1 `7902cdb` and clean-output
containment `ba8039a` were reviewed read-only; none was merged. Their existing
UPEM1000/1024/phantom/size/layout conclusions are retained. W1 advanced to
`2be6c78` independently and was not changed.

The 32 faces share one exact HVGL blob, have no HVPM, and retain independent
native face-index selection. An 8-call native pilot took 0.12956 s and projected
about 249 s for 32 × 15 × 32 observations. The selected bounded plan instead uses
**34 GIDs**: the existing 32 representative GIDs plus two prior type-rejection
witnesses. Existing selection covers **13/13 Type-2 shapes**, tree depth **12**
and **4** rotation roots. The 15 normalized-design locations include all eight
three-axis corners, five weight-axis values at neutral width/height, and two
fractional mixed-axis locations. These are design coordinates supplied directly
to HVF; no user-coordinate/avar mapping is invented or accepted.

Actual native run on this macOS 26.3: **32/32 faces × 34 GIDs × 15 locations =
16,320 accepted native transcripts/comparisons**, **241.855 s**. Every observation
executes the existing Apple C oracle and its existing complete transcript/event/
counter checks. Only portable calculations may share an identical-HVGL cache;
no native face observation is replaced by a different face's result.

- Unchanged legacy comparator: **16,256 passes + 64 retained type rejections**.
- Existing preserved-Q companion: invoked only for those **64**, **64/64 pass**.
- Combined existing policy: **16,320 pass / 0 fail**; maximum point discrepancy
  **1.3073986337985843e-12 FUnit**, unchanged **1/32** threshold.
- Original input unchanged; no metrics, user mapping, TTC construction, Windows
  or UI acceptance inferred. No A3/B1/C1/W1 production file was modified.

New independent driver `platform/d2_hvf_faces.py` has face checkpoints bound to
source/binary/code/plan hashes. Five focused regression tests pass, including
JSON roundtrip/resumption, rejecting incomplete/substituted/falsified checkpoints,
and retaining a true numeric failure. A local interrupted pilot exposed a tuple
versus JSON-list resume-recipe mismatch; it was corrected and tested before the
complete run above, which uses a new output directory. The pilot's private log
and partial results were preserved; they are not added to the 16,320 count.

Private checkpoint/result directory: `build/vf-d2-private/faces-validated/`.
Public output is only aggregate counts/errors/hashes:
[evidence](evidence/SWIRL_VF_D2_FACES_20261021.json). Native outline callbacks stay
in memory and are never written to public logs or Git. Primary references read
before this continuation: [Apple HVGL](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html),
[fontTools gvar reader](https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/ttLib/tables/_g_v_a_r.py),
and [HarfBuzz CoreText integration](https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-coretext-font.cc).
Existing algorithms are reused unchanged; no upstream implementation was copied.

```sh
build/vf-d1-private/venv/bin/python tools/swirl_vf/platform/d2_hvf_faces.py \
  ~/Downloads/PingFangUI.ttc --binary build/vf-d1-private/original-hvf/hvf_oracle \
  --output build/vf-d2-private/faces-next
```

A completed output refuses overwrite; an unchanged incomplete recipe can resume.
The next D2 stage diagnoses the 96 readback rejections and independently tests
B1's frozen metric hypothesis on fresh UPEMs, preserving all strict failures.

## D2 saved 32-face checkpoint and independent failure diagnosis

The first D2 stage is saved remotely as
**`30ff0adc9ef358713a269b40a7f4be8dbdb754f1`**, preserving ff2ed17 as parent.
Its tree contains only this window's new sampling driver/tests/aggregate evidence
and this handoff. The integration branch independently advanced to `2c2992e`;
that change was fetched but not merged, modified or pushed by this window.

### A3-facing 96-request diagnosis

`d2_axis_readback.py` freezes the original D1 384 requests plus 96 additional
predeclared `T(T(x))` readback controls **before** native observation. It reuses
the production Swift prefix, `constructInstance` and strict
`validateReportedAxes` verbatim. It never calls a glyph metric/path API, and
never makes its observations an accepted reconstruction oracle.

A real local control on the installed macOS-26 font (SHA `7ea43219...`, **not**
the user's `39d42acd...` original) completed **480 native axis requests**:

- Original 384: **288 strict passes / 96 strict failures**.
- Exactly **32 failures per axis**, all at the fraction-index-1 request
  `minimum + .123456789 * (maximum - minimum)`; endpoints/midpoint pass.
- Maximum absolute user readback errors: WDTH/HGHT
  **0.000032211000004167545**, wght **0.00009450000001720582**; all rejected
  errors exceed the unchanged **1e-6** guard.
- All **96** failed original echoes match the **predeclared** T(T(x)) values;
  all **96/96** additional controls echo their requested values exactly and pass
  the unchanged guard. Original 96 failures remain failures.

This isolates finite readback quantization as the numerical reason for these
strict refusals. It does not prove where/when Apple quantizes interpolation,
original/replay outline equality or a universal user-axis mapping. The same
probe still requires macOS-27 execution against the exact original before these
control-font numbers can be assigned to that source. Existing A3 payload/replay
and input-resolution blockers are retained; no source axis, tolerance, constructor
or admission policy was changed. Public [control evidence](evidence/SWIRL_VF_D2_SYSTEM_AXIS_20261021.json)
contains only counts/errors/hashes; full native axis records remain private.

### B1-facing minimal reproduction and fresh UPEM holdouts

B1's existing UPEM1000/1024, phantom, VVAR, size and four-channel experiments
were read from its fixed `7902cdb` handoff; they were not reimplemented as a
production repair. The new `d2_metric_upem.py` is an independent small extension:
it uses the existing self-authored fixture, retains every source table byte,
and changes **only head.unitsPerEm plus the serialization checksum**. Protected
head bytes and all other tables are actually checked after save/reopen.

Two known controls (1000,1024) plus **six fresh UPEMs**
`1001,1023,2047,4093,8191,16383` are sampled at five HGHT values, with WDTH500 /
wght100. Every request is strictly identity/readback checked. Separate forward
and reverse native processes complete **80 records / 40 unique coordinate
observations / 40 exact complete-payload replay pairs**. Actual raw CoreText
values are never corrected. This is generated geometry, not original PingFang.

B1's already-frozen candidate is evaluated using exact rational arithmetic:
`H=1000+R(60*y)-R(-90*y)` (R: nearest, halves away from zero), followed by
`trunc(floor(H*65536/UPEM)*UPEM/65536)`. It matches **40/40** observed heights,
including **30/30 fresh-UPEM** observations, while **36/40** still fail the
unchanged strict continuous-height comparison. At minimum HGHT the known
1000/1024 pair still measures **849/850**, and every fresh odd UPEM measures 849.
At the 53/64 normalized-height control the observed height can exceed the
continuous ideal, so a universal minus-one correction remains false.

Five preregistered horizontal normalization candidates (6,14,16,20,24 fractional
bits) are also retained. Across 40 observations their exact-match counts are
**0,15,40,5,5** respectively. Among the **30 fresh** observations these become
**0,10,30,0,0**. This discriminates these finite candidates and gives independent
support to a 16-bit normalization explanation; it does not uniquely prove
Apple's internal representation or validate a production fix. UPEM4093's raw
horizontal width is 669.9464569091797 against continuous 670, demonstrating an
additional over-1/32 horizontal error in that control.

Public [UPEM evidence](evidence/SWIRL_VF_D2_UPEM_20261021.json) contains only
self-authored fixture measurements. Full synthetic native rows/fixtures stay
under `build/vf-d2-private/upem-final/`; no Apple font was opened by this test.
The source/core algorithms and the old strict 849/850 test remain unchanged.

### D2 regression and CI checkpoint

Thirteen D2 regression tests pass (five sampling/checkpoint tests plus eight
readback/metric tests). They include source/table substitution, duplicate and
missing rows, falsified strict passes, default/unavailable handling, frozen
replay not rescuing original failures, the known 849/850 distinction, a true
positive metric error, all-table/head invariance and complete-payload replay.
Full local suite: **611 discovered = 604 passed + 7 platform skips**, no failure;
audit **6/6**. These counts include the thirteen D2 tests, not an additional suite.

The dedicated workflow now runs these tests on Mac and Windows, the bounded
32-face HVF and exact-original 480-request diagnosis on `xcode-27`, and the
synthetic UPEM reproduction on the Mac control host. Windows records actual
product/build, face/raster counts and explicit synthetic-only scope after both
real DirectWrite probes; original, Windows-11-desktop, installation and Qt/Swirl
acceptance remain NOT_RUN/NOT_TESTED. The old strict native metric step and its
failure propagation remain intact. Only original aggregate `summary.json`
files are uploaded; private rows/logs/fonts are excluded. YAML parsing/branch
checks pass. New remote native CI has not executed at this source checkpoint.

## D2 final native CI, owner-facing evidence and review boundary

Second D2 source checkpoint:
**`a5bfb228522dff183074b25459a109dcc8b4a475`**, parent 30ff0ad.
[Run 39534374343](https://github.com/SOLHK/Swirl/actions/runs/39534374343)
completed **failure** at **2026-10-21 02:47:31 UTC**. All three actual terminal
job states and complete job logs were read. The following are execution results,
not predictions, running jobs, artifact metadata or a reused D1 run.

| Actual job | Terminal result | Independently verified scope |
| --- | --- | --- |
| Original D2 **119007488141** | **success** | Actual macOS **27.0.1 / 26A434**, exact original; 32/32 identities, original 384 axis requests plus 96 preregistered controls; all 32-face HVF comparisons executed |
| Synthetic Mac **119007487935** | **failure** | Actual macOS **15.7.9**; 8 D1 + 13 D2 regression tests pass; old strict 849/850 test fails; native/table reconstruction and new UPEM diagnosis execute successfully |
| Synthetic Windows **119007488171** | **success** | Server 2022 Datacenter **20348**; 13 D2 tests pass; actual DirectWrite standard **3/3** and metric **2/2** faces pass, **10 raster images each** |

Machine-readable safe summaries extracted from those actual logs are saved in
[D2 CI evidence](evidence/SWIRL_VF_D2_CI_20261021.json). Full private logs/font data
are not committed. New ZIP bytes were not downloaded or independently rehashed;
no ZIP-content verification is claimed. Original artifact metadata identifies
**12316713337**, 1,756 bytes, GitHub digest
`1fef57c5c31ba7bb65ebcf9bc4a098e2f65798afabdd6621f4dfd94d933e4dee`;
this is metadata only. The evidence here is bounded to actual terminal logs and
explicit summary fields, not unseen artifact members.

### A3 review: the original 96 failures are now classified

Against the exact `39d42acd...` original on macOS 27, the new diagnostic actually
confirms **288/384 strict passes**, **96/384 strict failures**; **32 failures per
axis**, all at the preselected fractional request. Every failed effective echo
matches its predeclared T(T(x)); all **96/96** independent controls echo that
coordinate exactly and pass. Maximum errors equal the local control values
above. Source unchanged; production extractor SHA remains
`8e5aaa0a921f24a656766c1e24a0d388397cdaddbdfebae1ab415c0d7c3f3bbf`;
new native harness SHA is
`4a708e294f630475313201555baa19a2fa658c6b72f91de33d04e753211dab33`.

Two compact numerical reproductions from the frozen plan explain the refusals:
`WDTH = 1 + 999*.123456789 = 124.333332211` has effective echo 124.3333;
the wght100..600 group requests `161.7283945` and has effective echo 161.7283.
The latter also distinguishes the observed truncation-like value from nearest
four-decimal rounding. Both differences exceed 1e-6. The unchanged Swift guard
computes its failure **before JSON serialization**, and the Python diagnostic
checks that verdict independently. These are actual numeric readback differences,
not cosmetic decimal printing or Python display truncation.

The accepted conclusion is narrowly that the **96 finite strict-readback
refusals** have this reproducible numeric explanation. It does not establish
original/replay glyph equivalence, Apple's internal interpolation coordinates,
a universal decimal rule or A3 production mapping. Existing every-GID exact
payload replay, omitted-nondefault handling and input-resolution obstructions
still apply. Do not admit a diagnostic oracle or replace source coordinates
because these 96 additional readback controls pass.

### B1 review: independent support, strict failure still present

The synthetic Mac CI repeats the final source script exactly (SHA
`3a13b4b88f591b042a701021dca4034872079f20962670ed812a2b568bbf664c`):
**40 unique fixture/height observations, 80 actual records, 40 exact reverse
pairs**, **40/40 frozen height predictions match**, **36 strict height failures**.
This agrees with the new local macOS-26 result; these fresh-UPEM experiments
were run on **15.7.9 and 26.3**, not falsely labelled as fresh macOS-27 measurements.
B1's prior matching-host 1000/1024 evidence remains its separately sourced result.

Horizontal values repeat over the five heights for each UPEM: there are **8
UPM bases, 6 fresh**, not 40 independent horizontal-width conditions. Likewise,
the 32 faces share a single HVGL table: there are **510 distinct portable
GID/design references**, with **16,320 actual native face observations** per
host, not 16,320 distinct source models. Counts are not doubled across native
replays or the local/CI repetitions.

The old raw metric gate remains FAIL at 849/850 with 1/32 tolerance. Frozen
arithmetic matching is not a source-API correction, and this window has not
changed B1 metric writers, compensation, vertical-origin representation or
reconstruction admission. A valid future repair still needs an independently
frozen strict holdout set and original/application acceptance.

### All-face confirmation and integration boundary

The macOS-27 job executed the entire same bounded **16,320** native set in
**325.703 s**: **16,256 legacy passes + 64 retained type rejections**, companion
**64/64**, combined **16,320/16,320**, zero numeric failures, identical maximum
point error **1.3073986337985843e-12**, unchanged 1/32 limit and source bytes.
No unmeasured face or untested legacy rejection was silently omitted.

D2 has therefore completed its independent bounded native validation and
failure diagnosis. Original production reconstruction is still **0/32 faces**;
no original-derived font was built in this continuation. The existing D1
3,424-byte file remains only a synthetic control. Windows Server evidence is
explicitly synthetic; Windows 11, original installation/DirectWrite, real
Qt/Swirl, mixed-text rendering and product performance remain NOT_RUN.

Integration review should focus on the new independent drivers, thirteen tests,
strict failure retention and original-summary-only CI export. A3/B1/C1/W1
algorithms and the UI are unchanged; no other development branch or integration
history was merged or updated. B1's documented system/private-copy startup
contrast also remains a confounder when interpreting D1's two-host loading
contrast: it is not proof that OS version alone causes the refusal.
This branch is a review candidate, not permission to merge or announce a font.

Small synthetic metric reproduction (fresh directory; no Apple font needed):

```sh
build/vf-d1-private/venv/bin/python tools/swirl_vf/platform/d2_metric_upem.py \
  --binary build/vf-d1-private/coretext/coretext_extract \
  --output build/vf-d2-private/upem-next
```

Original 480-request diagnosis on a matching host uses
`platform/d2_axis_readback.py SOURCE --expected-sha256 39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890 --output FRESH_PRIVATE_DIRECTORY`.
It intentionally requires exact source identity and cannot replace the Mac-26
source with a different system font under that hash. All result/raw/native
checkpoints remain available locally under `build/vf-d2-private/`.
