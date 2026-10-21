# P4: source design mapping and font-only representation

The current user contract prioritizes a portable font file independent of
Swirl/Qt. App-specific coordinate or placement compensation cannot qualify as
conversion. All original production guards, tolerances and failures remain.
Branch/worktree stay `work/vf-takeover-abc-20261021` / `vf-takeover-abc`.
Starting remote HEAD is6567f4aca310c7bd7d37cb828b6d12b9624ccb04.

PR23 remains draft/unmerged at54e579f; PR24 contains four takeover commits and
26 changed files relative to that unchanged base. Their actual differences
were read. The A3/B1/C1 source tips remain66594e9/7902cdb/c0fe6c4; their latest
original handoffs and implementation were re-read. A concurrently newer
integration PR base70a18d5 was observed; it is preserved and is not merged here.

## Implemented arithmetic, not a source-replay acceptance shortcut

`tools/target_axis_mapping.py` extracts the verified finite A3 ONCE_ALL
candidate from6d6a7b5 without importing a diagnostic runner. It keeps original
binary64 user input, one decimal design-stage truncation, the A3 endpoint
normalization arithmetic, signed normalized16 truncation, original ordered raw
avar evaluation and final nearest F2DOT14 q as separate values. Raw records
are never deduplicated or replaced with FontTools' lossy dictionary. Neither
observed readback nor a measured glyph is input to this algorithm.

An offline comparison against A3's exact Git-blob implementation reproduces
all140 previously declared vectors. This reuses prior evidence; it is not a
new native test or a global mapping proof. Ten new authored regressions pass,
including the complete163845-cell FLOAT/16.16 transport calculation over five
axis-range families. Source and target acceptance flags remain false.

The old96/384 strict readback failures are one decimal-quantization family,
32faces times three fractional-axis requests. Exact user echo is different
from the source design q. The A3 T1 design-stage arithmetic must not be
replaced with the later T2 readback value;415.09865 is a pre-existing witness.
No CoreText request, original font or strict tolerance is changed here.

## Actual legal font-level compiler

`tools/font_axis_mapping.py` evaluates the frozen hypothesis on all32769
nominal F2DOT14 input nodes, then removes only exactly collinear interior
points with integer arithmetic. It emits a detached legal avar v1 table with
unique increasing input records, nondecreasing outputs and mandatory anchors.
Nonmonotonic mappings and wrong required endpoints are refused rather than
silently repaired. Nine authored tests include actual serialization and raw
table re-reading; all pass. Node agreement is explicitly separate from
normalized16 quarter-node behavior and arbitrary binary64 user coordinates.

On the local exact original, all32WDTH and32HGHT axes compile to three identity
records. All32wght axes are refused because raw source post-avar endpoint q
does not equal the mandatory target design endpoint. This does not prove that
font conversion in every coordinate basis is impossible: it shows that simply
copying source-q space and rewriting avar is insufficient. A distinct target-r
basis must also reparameterize glyph/metric/layout variation data. Neither
compiler changes an existing glyph model or grants production acceptance.

An independent authored quarter-node witness is retained: every nominal F2
knot can match while user500.006103515625 yields source candidateq0 and a legal
avar candidateq17. No finite-knot certificate is presented as user-axis parity.

## Irrecoverable input boundary and optional representation control

The original face15 pair499.006199/499.006201 has identical FLOAT bits43f980cb
and user16.16 integer32702870, but native source advance differs by0.5474853515625.
Any deterministic font receiving only that same merged input must return one
output, so its worst endpoint error is at least0.27374267578125 source FUnit,
above1/32. This excludes strict1/32 equivalence on that pair under that entry
contract, regardless of avar/gvar/HVAR encoding. It is not a proof against the
separate existing1-FUnit reconstruction budget or all reparameterizations.

The optional q transport exposes what the target format *can* encode once q
is independently known: y=default+q*sideSpan/16384 is exactly FLOAT and16.16
for these integer axis families. It is explicitly an app-adapter control,
not a font-only solution. New self-authored32-face twin fonts exercise all
three axes without Apple outlines/data. Local HarfBuzz14.6.0 checks256requests
and5376metric/extents comparisons exactly. The twins use custom normalized
tags rather than an invalid negative registered wght user scale. All files
remain in ignored private build directories and are not delivery fonts.

The new DirectWrite C++ control checks actual submitted FLOAT/readback bits,
physical face/table identity, all glyph metrics and horizontal/sideways outline
points. Its Mac stub compiles and reports NOT_RUN; actual Windows Server CI is
pending at this checkpoint. It cannot grant Windows11/original-font acceptance.

## Fresh native evidence to collect

The dedicated P4 workflow freezes165 original positions before new native
observations:96 existing failing D2 fractions,32 new seeded mixed positions,
32 endpoint controls and five historical witnesses. It compares CoreText with
the declared q through the existing Apple HVF oracle and existing HVAR metrics,
retains the unchanged legacy/preserved-control comparators and1/32 threshold,
and exports only fixed aggregate summaries. Fonts, raw native records, source
tables, requests and private logs are never uploaded.

Checkpointd3a766f03e2b70033a775702d87ecb5ddab7fb42 passed all three jobs in
[P4 run39552431905](https://github.com/SOLHK/Swirl/actions/runs/39552431905).
Actual original39d42acd on macOS27.0.1/26A434:165/165 HVAR position checks
have zero residual;330/330 direct Apple HVF glyph checks have zero residual,
including both unchanged legacy and preserved-control comparators. Two native
sessions verified825 opposite-order glyph pairs and produced3300 internal
CoreText glyph records. All96 fractional requests still fail strict readback.
The new finite source-q support is separate from global/target/font acceptance.
Aggregate: [original q](evidence/SWIRL_VF_P4_SOURCE_Q_20261021.json).

Actual Windows Server2022 representation control:32faces,512requests,
3584glyph pairs,25088metric fields,7168outline pairs;22528/22528 outline
point pairs bit-exact and6144 actual FLOAT/readback bit checks pass. Both
maximum errors are zero. This is the explicitly optional authored q transport,
not a font-only conversion result.
[Target control](evidence/SWIRL_VF_P4_TARGET_CONTROL_20261021.json).

Formal original-face reconstruction remains NOT_RUN because mapping and metric
prerequisites remain unaccepted. No Swirl/Qt production source or existing
reconstruction safety gate has been changed.

## Font-only vertical precision experiment

`platform/font_vertical_precision.py` reuses FontTools scale_upem and the
existing GPOS encoder on authored controls. An even design-grid scale makes
half-width adjustment coefficients integral; serialized glyphs, gvar,
HVAR/VVAR, horizontal/vertical/global metrics scale together, preserving their
physical meaning. All comparisons are converted back to source design units.
The original fixed default origin is retained, including odd-width controls.
No application coordinate or layout compensation is involved.

Seven new tests and12 relevant existing GPOS tests pass. Eighteen authored
cases (three geometry/metric kinds times six original UPEM families),1296
frozen holdout glyph observations, have maximum layout error0.03125 source
FUnit and zero observations above the unchanged1/32 threshold. The unscaled
0.25/0.75/2-unit layout failures and raw API differences remain visible.
This is bounded HarfBuzz14.6.0 evidence, not a general/native-platform bound.
The helper's UPEM postcondition now correctly checks output against input
instead of incorrectly hardcoding1000; all protected-table checks remain.
Invalid UPEM/coordinate overflow and overwriting existing output are refused.

Scale8 is within the legal target UPEM range for all six source families;
scale16 would exceed the16384 limit on24/32faces. Entire original HVF
variation extrema have not been bounded, so scaling is not enabled for the
production builder. DirectWrite rounding can still create a distinct error
bound; its scaled-layout and Windows11 acceptance are NOT_RUN.
Aggregate: [font-only precision](evidence/SWIRL_VF_P4_FONT_VERTICAL_PRECISION_20261021.json).
The local generated8GID control at
`build/vf-takeover-private/font-only-precision-control-stage1/` is authored
data, not an original conversion candidate.

Primary references inspected before implementation:
[OpenType normalization](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview#coordinate-scales-and-normalization),
[avar record constraints](https://learn.microsoft.com/en-us/typography/opentype/spec/avar),
[FontTools avar4.61.1](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/tables/_a_v_a_r.py),
[HarfBuzz avar](https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-ot-var-avar-table.hh).
Existing project math and public APIs are reused; no upstream code is copied.
