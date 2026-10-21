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

At this checkpoint the actual new original native test is NOT_RUN. Formal
original-face reconstruction is NOT_RUN because mapping and metric prerequisites
remain unaccepted. No Swirl/Qt production source or existing reconstruction
safety gate has been changed.

Primary references inspected before implementation:
[OpenType normalization](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview#coordinate-scales-and-normalization),
[avar record constraints](https://learn.microsoft.com/en-us/typography/opentype/spec/avar),
[FontTools avar4.61.1](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/tables/_a_v_a_r.py),
[HarfBuzz avar](https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-ot-var-avar-table.hh).
Existing project math and public APIs are reused; no upstream code is copied.
