# P7 real original HVF to standard glyf experiment

Branch `work/vf-takeover-abc-20261021`, isolated worktree
`~/Swirl-worktrees/vf-takeover-abc`; initial/remote HEAD
`f7611c69c8768f890318a3490248e2f56f4e4226`. Earlier D1–P6 evidence and strict
production gates remain intact. No other branch is merged or changed.

## First actual original GIDs

The exact user original SHA256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`
is read locally without modification. Apple HVF1.0.2 renders its original
face0 on this macOS26.3 even though CoreText cannot load that original.
Face0 UPEM is1028: the experiment's legal15x grid has UPEM15420, not16000.

`p7_original_glyf.py sample` actually completed five real source GIDs:
0,2,12,1166,19177. Each has27 q-space training nodes and4 independent
holdouts,155 actual original Apple HVF render comparisons in total. Existing
D2 geometry comparison and its preserved-quadratic companion are unchanged.
All155 portable/native comparisons pass the existing1/32 geometry check.

Standard binary `glyf` entries were written locally and decoded again, checking
the actual encoded coordinates and contour endpoints. Actual gvar tuples are
generated through existing C1 `reconstruct_glyph`/fontTools VariationModel:

| Original GID | Contours | Points | Variation tuples | Strict sampled outline bound, source FUnits |
| --- | ---: | ---: | ---: | ---: |
|0|4|52|26|0.04567399828164197|
|2|0|0|2|0|
|12|2|26|13|0.04359029836313155|
|1166|6|104|26|15.94437590306295|
|19177|18|238|26|5.403840164681962|

These are REAL original-derived glyph models, not authored controls. The large
nonlinear sampling errors and quantization failures remain FAIL. Only the
empty-outline GID2 meets both current sampled model limits; no full original
variable conversion is accepted. This is sample reconstruction, not direct
translation of all HVF coefficients or a continuous-domain proof.

Source contours are obtained from existing BatchGeometry with explicit tangent
support and independently checked against Apple HVF. Stable on/off-point
topology and source part/path provenance are retained privately. HVF component
trees are expanded into standard simple glyphs; original composite relations
are NOT preserved as TrueType components. The source DAG remains provenance,
not a claim of preserved composite semantics.

HVF has no metric API in this path. Existing SourceMetrics supplies separately
labelled HVAR/hmtx/vmtx/VORG values in the explicit design q frame. Four phantom
points are reconstructed from those table values. Original CoreText advances,
baseline and independent vertical-origin X are NOT measured or corrected.
No native metric acceptance follows from table consistency.

Private outputs: `build/vf-takeover-private/p7-models-stage2/` contains the five
real `.glyf` entries, model JSON, native observations and source/code/binary-bound
receipt. These files contain proprietary data and must NEVER be committed,
published or uploaded as CI artifacts. Completed model checkpoints were rerun
without repeating native rendering; changed recipes or bytes are refused.

## Full-default experimental face path

The separate `face` mode requires every original default GID from the existing
source-bound Apple HVF cache (47,102 native records,529,152,062 bytes, SHA256
`201b1a16efae40ac28f908148801645956211a0d85803b2fe5a1cd9b265f27f3`).
It never fills missing GIDs with blank stand-ins. Source cmap/GID order stay
intact. Only the five declared GIDs have experimental variable models; all
other GIDs remain explicitly DEFAULT_ONLY, not completely reconstructed.

The assembler scales float geometry before its first integer encoding, derives
coherent standard phantoms, uses the existing metric writer and C1 verified-hash
packer. Old HVGL/variation metadata replacements are explicitly listed. AAT
trak/proprietary cidg/meta, if present, remain byte-retained but UNSCALED and
UNVERIFIED; this is not production table support. Unsupported tables, point-index
layout anchors, overflow, incomplete GIDs and wrong model grids are refused.
No production builder admission or whole-face production checkpoint is reused.

Actual full-face execution is running at this first source checkpoint; its
outcome will be appended. No Windows claim or completed face is implied here.
Original-derived files remain strictly local and experimental. Windows11,
original-derived DirectWrite, real Qt/Swirl and installation are NOT_RUN.

Targeted authored regressions: glyph model4, original-driver safety3 and face
assembler11 PASS. Tests contain only authored geometry; public CI never runs
this converter against or uploads an Apple-derived font.

Primary references reviewed before implementation: existing project HVF/C1
code; [Apple HVGL](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html),
[fontTools TTGlyphPen](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/pens/ttGlyphPen.py),
[VariationModel](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/varLib/models.py),
[public UPEM visitor](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/scaleUpem.py),
[OpenType glyf](https://learn.microsoft.com/en-us/typography/opentype/spec/glyf).
Existing algorithms/public APIs are reused; no upstream implementation copied.
