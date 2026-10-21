# P4: source design mapping and font-only representation

The current user contract prioritizes a portable font file independent of
Swirl/Qt. App-specific coordinate or placement compensation cannot qualify as
conversion. All original production guards, tolerances and failures remain.
Branch/worktree stay `work/vf-takeover-abc-20261021` / `vf-takeover-abc`.
Starting remote HEAD is6567f4aca310c7bd7d37cb828b6d12b9624ccb04.

At the starting snapshot PR23 was draft/unmerged at54e579f; PR24 contained four takeover commits and
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

The DirectWrite C++ control checks actual submitted FLOAT/readback bits,
physical face/table identity, all glyph metrics and horizontal/sideways outline
points. Its Mac stub compiles and reports NOT_RUN; actual Windows Server results
are recorded below. It cannot grant Windows11/original-font acceptance.

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

## Font-file endpoint basis and actual variation-model reparameterization

The next implementation explicitly distinguishes source post-avar q from
target normalized r. `design_axis_basis.py` freezes each raw source axis's
actual candidate endpoint q, maps its two sides to target endpoints-16384/+16384,
and compiles legal standard avar in r. All32original profiles now serialize as
legal three-axis avar candidates; no original table is overwritten. Integer
q→r encoding is injective over the used q interval, but its fractional inverse
has nonzero coordinate error. The reported exact rational bound is in q-grid
units, never a claimed glyph error bound. Quarter-cell and input-collision
counterexamples still apply. Ten new basis tests and nine compiler tests pass.

`rebase_design_font.py` implements the previously missing transformation for
an already standard q-space glyph model. It reuses FontTools' partial instancer
with source q limits, converting actual gvar, HVAR/VVAR and layout variation
regions/coefficients before restoring the original axis tags/ranges and legal
avar. It accepts only explicit standard custom-axis q models, rejects
proprietary HVGL/HVPM, returns a distinct candidate, and is not enabled in the
production builder. Metadata is validated before the instancer can filter it:
unsupported named/STAT coordinates are refused instead of silently discarded.

Nine reparameterization regressions pass. They prove a clipped source peak
must produce20→10, while merely relabeling supports incorrectly preserves20;
actual HarfBuzz checks cover glyph extents/advance and a GDEF VarStore referenced
by GPOS. All three clipped axes are checked on mixed corners with VVAR. An odd
coefficient1 still has an explicitly measured0.5-FUnit endpoint discrepancy
after integer serialization, above1/32. This failure is retained, not reported
as lossless preservation or bypassed by a marker.

The new32-face authored font-file control uses unchanged nominal user inputs
on the target. The file itself contains reparameterized avar/gvar/HVAR/VVAR;
there is no application coordinate conversion. Its independent q-space font
is used solely as a reference. Local HarfBuzz checks256requests/5376glyph
metric-extents comparisons exactly; all32faces retain exact default glyf,
loca,hmtx,vmtx,cmap bytes. Both generated collections pass the existing C1
binary/table checks. The reference's custom normalized axis tags are legal,
and the target uses WDTH/wght/HGHT with the original numeric range families.
Aggregate: [rebased local font](evidence/SWIRL_VF_P4_REBASED_FONT_LOCAL_20261021.json).

The extended DirectWrite probe has a separate `--font-level` control mode:
it verifies legal target avar and default tables, then compares actual metrics
and full outline points at unchanged nominal inputs. The existing optional
q-transport control retains its stricter identical variation-table requirement.
Neither mode grants original/Windows11 acceptance.

The original165-position experiment is extended for a new reason: compare the
fractional q reconstructed from the quantized r against original CoreText/HVF.
This measures coordinate-composition error separately from coefficient
re-encoding; it does not pretend to be an original target-font build. Existing
comparators and all original96readback failures remain. No expensive full-GID
baseline is repeated. Formal original reconstruction remains NOT_RUN.

Checkpoint9f39f24acd0060e54e38302190bb72fe7300f245 passed all three jobs in
[run39556281421](https://github.com/SOLHK/Swirl/actions/runs/39556281421).
The Linux job passed38 targeted mapping/model regressions and both authored
HarfBuzz controls. The separately automatic existing takeover workflow also
passed at the same source commit; it was not manually dispatched again.

On the exact original/macOS27.0.1, baseline165HVAR positions and330HVF glyph
comparisons still have zero error. The new fractional-r composition has maximum
HVAR error0.0036952052687411197 and maximum HVF point error0.0025511955074080106
source FUnit; all165metric positions/330glyph comparisons remain inside1/32,
under both unchanged comparators.432unique native HVF calls suffice through
caching;825opposite-order pairs/3300internal CoreText records remain exact.
All96strict fractional readback failures remain. This experiment isolates
coordinate composition: it does not encode original glyph coefficients, run
the generated original avar on Windows, or establish a global input map.
Aggregate: [original rebased coordinates](evidence/SWIRL_VF_P4_REBASED_NATIVE_20261021.json).

The actual new font-only mode passed on Windows Server2022/build20348:
32authored faces,512requests,3584glyph pairs,25088metric fields,7168outline
pairs,22528bit-exact point pairs,6144FLOAT/readback checks. All maximum errors
are zero. The target receives unchanged nominal inputs; it contains the actual
reparameterized models, rather than relying on the optional q adapter.
Aggregate: [font-only DirectWrite](evidence/SWIRL_VF_P4_REBASED_WINDOWS_20261021.json).
Windows11/original font/third-party applications remain NOT_RUN.

P4 saved source checkpoints so far:
- d3a766f03e2b70033a775702d87ecb5ddab7fb42: separated mapping/legal compiler;
  actual original/native and Windows representation CI passed.
- b9823c481eefef8a980d1d6671460fdbf1c0f406: font-only physical scaling/GPOS
  control and input-bound UPEM postcondition; existing CI passed.
- 9f39f24acd0060e54e38302190bb72fe7300f245: legal endpoint-r basis and actual
  variation-model transformation; original finite coordinate and authored
  Windows Server font-file controls passed.
- 73e1d430374acbf95e1c8f39fdfd224960502a14: guarded precision8 coefficient
  candidate, packed-delta/MVAR/overflow safeguards and retained failure tests.

## Guarded fine-grid coefficient candidate

`rebase_design_font_precision8` scales the complete supported standard q font
before restriction, then serializes/reopens both scaled and rebased models.
It changes UPEM with geometry/metrics, not user inputs or application placement.
All16 targeted model/precision regressions pass locally (2.628s). The serialized odd-delta1/half-domain witness now reproduces the original
continuous gvar/HVAR/VVAR model exactly at seven mixed positions, rather than
rounding0.5 to an integer. All six source UPEM families fit the legal target
range. Input data and the default unscaled function remain unchanged.

This is not a universal fix: an authored3/16 endpoint needs coefficient1.5 on
the eightfold grid, rounds to2, and still differs by1/16 source FUnit. Also,
actual HarfBuzz raw advances on the unscaled reference round on its original
grid;42/49 authored advance comparisons differ by more than1/32 (maximum3/8)
despite the fine-grid target reproducing the continuous metric model at the
same output scale. Those native-equality failures are retained separately.
The earlier failed universal-equality assertion is preserved privately as
`build/vf-takeover-private/p4-precision8-regression.log`; no original data is
in that authored-only log. No original/native/production acceptance is added.

The candidate rejects overflow, hint bytecode, unknown/AAT/Graphite tables,
unreviewed VORG and MVAR. MVAR includes dimensionless caret-slope tags, so
blindly scaling every VarData delta changes an authored hcrn slope ratio from1
to0.125 while leaving the base unchanged. The independent regression proves
that wrong result and the candidate's refusal, with source bytes unchanged.
A tag-aware MVAR transformation is still required.
Successful FontTools roundtrip alone is insufficient: its packed-delta encoder
can emit0xC0 long runs, whereas the published standard gvar packed format uses
signed8/16-bit runs. This candidate explicitly refuses out-of-range gvar
coefficients instead of emitting that extension. Reference:
[OpenType packed deltas](https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats#packed-deltas).
No output or production gate is changed when a candidate is refused.
Aggregate: [fine-grid model and retained failures](evidence/SWIRL_VF_P4_PRECISION8_MODEL_20261021.json).

The original Swirl-VF production guard remains closed. Actual source-HVF to
standard glyph construction, full original metrics, font-level global input
mapping, Windows11 and third-party application acceptance are still distinct
outstanding gates. No proprietary source/derived font is uploaded.

## Final checkpoint and direct continuation

All six automatic CI jobs passed at source73e1d43:
[P4 run39558431396](https://github.com/SOLHK/Swirl/actions/runs/39558431396)
and [existing takeover run39558431497](https://github.com/SOLHK/Swirl/actions/runs/39558431497).
P4 has45targeted regressions; the existing portable suite has759passes and
6audit passes. These are test counts, not conversion acceptance counts.
Native original coordinate composition and authored font-only DirectWrite
results reproduce the earlier exact numbers. The precision8 path itself has
actual HarfBuzz/model evidence only; CoreText/DirectWrite precision8 are NOT_RUN.
Fixed machine evidence: [final CI](evidence/SWIRL_VF_P4_FINAL_CI_20261021.json).

Actual generated font-file control:
`~/Swirl-worktrees/vf-takeover-abc/build/vf-takeover-private/p4-font-level-controls/font-level.ttc`
(562696bytes,32authored faces/7GIDs, SHA256bac15ffe51c5b8b297acfaa46411bd420aa789ee5e270c79ca25d4e348e9b6ad).
It is neither an original conversion candidate nor a Swirl-VF delivery font.
The separate authored vertical precision control is at
`build/vf-takeover-private/font-only-precision-control-stage1/authored-scaled-gpos.ttf`.
No original-derived Swirl-VF.ttc was built; the production gate still refuses
source-only evidence. No Windows11, installation, real Qt/Swirl or third-party
Windows application acceptance is inferred from Server2022.

No other worktree/source branch was modified. Main and D1 worktrees are clean.
Final remote audit still observes A3=66594e9,B1=7902cdb,C1=c0fe6c4,
integration=f87b6f9; PR23's API separately reports base snapshot70a18d5.
Both observations are preserved, not resolved by rewriting integration.
PR23 remains draft/unmerged at54e579f; PR24 remains draft and stacked on that
same D1 base. No merge conflict was detected for PR24, and no automatic merge
was attempted. Only the integration owner may decide review/integration order.

Next work must close a real remaining gate rather than re-run a large baseline:

1. Bound font-level normalized16 behavior between F2 knots while preserving the
   quarter-cell witness and the same-FLOAT native collision. The latter rules
   out global1/32 parity under unchanged nominal input, independent of UPEM.
2. Establish a coefficient representation for actual source-HVF q models under
   serialized integer budgets. Precision8 repairs the half witness, not the
   retained3/16 or raw-native differences. A tag-aware MVAR path, hint/VORG
   handling and original variable extrema bounds are prerequisites for reuse.
3. Validate font-level vertical GPOS shaping in actual DirectWrite and target
   software, retaining the raw849/850 and original fixed-X/API failures. A
   shaping feature enabled in one engine is not universal application support.
4. Only independently accepted original target mapping/metric contracts may
   authorize the first original-face build. Keep resumable C1/model-byte gates.
   Windows11 and third-party applications then require their own actual runs.

Targeted commands (use the existing venv read-only):

```sh
PY=/Users/mac430/Swirl-worktrees/vf-macos-windows-d1/build/vf-d1-private/venv/bin/python
"$PY" -m unittest discover -s tools/swirl_vf/tests -p test_rebase_design_font.py -v
"$PY" -m unittest discover -s tools/swirl_vf/tests -p test_design_axis_basis.py -v
"$PY" tools/swirl_vf/platform/make_font_level_controls.py --output build/vf-takeover-private/p4-font-level-next
```

Use a new output suffix; generation refuses existing output. The original
native probe belongs on the verified macOS27 path in the workflow; this local
Mac26.3 cannot CoreText-load the exact original and must not substitute its
different system font. This documentation-only successor changes no tested
source or acceptance gate.

Primary references inspected before implementation:
[OpenType normalization](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview#coordinate-scales-and-normalization),
[avar record constraints](https://learn.microsoft.com/en-us/typography/opentype/spec/avar),
[FontTools avar4.61.1](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/tables/_a_v_a_r.py),
[HarfBuzz avar](https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-ot-var-avar-table.hh).
Existing project math and public APIs are reused; no upstream code is copied.
