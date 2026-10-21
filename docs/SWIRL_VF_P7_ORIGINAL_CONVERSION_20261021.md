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

Actual full-default-face execution finished successfully. Private outputs:

- `build/vf-takeover-private/p7-face-stage1/P7-Original-face0-EXPERIMENTAL.ttf`
  SHA256 `84fe084e3baba854ceed659f80a8e4abb4248fa78fab6372905b89ec3f722c76`.
- Its single-face TTC is34,890,808bytes, SHA256
  `43d164785847dfaf27a19175ef4f1e7a00112f6f073b73a26f126364c2372fd4`.

All47,102 measured default GIDs are present, including5 source-measured empty
glyphs. Five have sampled variable models;47,097 remain DEFAULT_ONLY. The C1
serialization verifier checked10,338,181 default points including phantoms and
93 gvar tuples exactly after reopening; its existing binary packer verified
one face,22 tables and table-payload preservation. These checks prove encoded
data consistency, not original equivalence. Default grid quantization has a
maximum0.0471366377656632 source-FUnit control-point error;2,770,607 default
points exceed1/32 and remain failed. No strict threshold is changed.

## Original nominal-axis experimental candidate

`p7_nominal_candidate.py` reuses the P4 `rebase_design_font` algorithm; it does
not introduce a second mapping algorithm. It applies the original WDTH/wght/
HGHT ranges and legal avar to the partial q-face, rebuilds HVAR/VVAR from final
phantoms, retains original cmap/GID order, and repeats C1 decoded-data and
verified-hash packing checks. It never grants source-user mapping acceptance.

Actual local outputs:

- `build/vf-takeover-private/p7-nominal-stage1/P7-Original-face0-NOMINAL-EXPERIMENTAL.ttf`,
  SHA256 `5e30320c0be56c8038b89ba8a86e6d25d0713952c006cc79071dc3f3386ab7bd`.
- Its single-face TTC is34,970,788bytes, SHA256
  `6be166ab88d5178a7697d14dcaaabe2e5d5b3690e18a4d58073cbfa3892ff0fa`.

These are original-derived, partial-variable experimental files. Original named
instances are not restored; metadata, retained unscaled trak/cidg/meta and
component semantics need further acceptance. Neither file is a released
`Swirl-VF.ttc`. A32-face expansion is not justified while one-face variable
completeness, precision, metrics and mapping gates remain unresolved.

## Actual closure-point encoding fix and current candidates

Independent comparison exposed a target-only terminal zero-length line: C1's
explicit final on-curve point duplicates each contour's first point. New
`hvf_glyf_closure.py` and the separate private `p7_compact_candidate.py` remove
only that redundant final point, with an exact proof: the base endpoint and
every complete gvar tuple endpoint delta must equal the first point. Therefore
their weighted sums are identical at every position in that encoded model.
Sparse/None tuples and differing endpoint deltas are skipped; instructions and
composites are refused. Internal zero-length segments remain. Point indices and
the final four phantom entries are remapped together. Production C1 and the
native comparator are unchanged.

The actual full face removes739,241 redundant terminal points in47,097 nonempty
GIDs, retaining all47,102 GIDs and93 tuples. hmtx/vmtx/HVAR/VVAR bytes are exactly
unchanged. Reopening verifies9,598,940 default/phantom points; C1 packing again
verifies22 tables. Current private candidates are:

- q TTF: `build/vf-takeover-private/p7-face-compact-stage1/P7-Original-face0-EXPERIMENTAL.ttf`,
  SHA256 `bcc46ae10835a9567684489d70428434c692f8b1a304506fbb3b307843bc4b78`.
  Single-face TTC32,452,320bytes, SHA256
  `5e0d59069c3ff782a01aef76877c109b00a9d6c791b6b31ae314266da56e5c6e`.
- nominal TTF: `build/vf-takeover-private/p7-nominal-compact-stage1/P7-Original-face0-NOMINAL-EXPERIMENTAL.ttf`,
  SHA256 `329ba65ca37085d4c5de0e689dade650ea4628169d0ece48bedb82c6f0c6a46a`.
  Single-face TTC32,532,300bytes, SHA256
  `e9db53ed7ff33c3f4a293cb6624e4021f2e898960b3a525a0bd19084230d020c`.

The q candidate's actual CoreText regression has32 records,16 exact reverse
pairs,12 strict axis comparisons and12 glyph draws into two private PNGs.
All16 matched prior native command/bounds/advance/vertical-translation records
and both PNG files are exactly equal before/after compaction. This is a bounded
candidate encoding regression, not original equivalence or cross-platform
pixel parity. The unchanged raw original-HVF/HB comparator now obtains numeric
comparisons for all32 requests:8 pass,24 fail `outside_budget`, with no remaining
segment-count failures or terminal zero lines. Selected nondefault maximum
control error is6.956634475799774; DEFAULT_ONLY nondefault samples reach
116.30857628945148. Earlier failure records remain saved, and strict numerical
failures are exposed rather than suppressed.

The compact nominal candidate also passed32 native CoreText records,16 exact
reverse pairs and12 strict effective-axis checks; its16 matched prior nominal
records have identical commands, bounds, advances, vertical translations and
axis readback. The separate unchanged HVF/HB comparator returns6/32 numeric
passes and26 `outside_budget` failures, zero segment-count failures. Selected
nondefault maximum control error is9.125873988903379; table/HB advance failures
are unchanged. All8 shaping GID/cluster sequences match, but119/640 position
fields remain above1/32. No nominal compact drawing was run.

A final bounded default check confirms real nonempty GID12 reaches the existing
preserved-quadratic1/32 check after standard encoding and actual HarfBuzz decode:
maximum control error0.022461404806222163. Its old legacy segment-type rejection
is still recorded, while the already-existing raw-quadratic companion compares
the original controls. GIDs0/1166/19177 at default still fail numerically. This
one-position result does not accept GID12's full variable model or the face.

Four authored closure regressions pass, including multi-contour remapping,
unchanged internal duplicates, phantom/delta preservation, sparse/differing
delta refusal and actual serialized HarfBuzz geometry/extents/advance before/
after comparisons. Existing fontTools
[TTGlyphPen](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/pens/ttGlyphPen.py)
and [point pen](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/pens/pointPen.py)
provide the mature duplicate-closure precedent; the gvar proof/remapping here
is independently implemented according to
[OpenType point/phantom numbering](https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats).
No upstream code is copied. All prior model/quantization/native failures remain
inherited; removing redundant encoded points does not re-judge their budgets.

## Actual native and independent checks

Both q and nominal candidates loaded through the existing generic CoreText
extractor on this Mac: each has64 actual glyph records,32 exact reverse replay
pairs,56 nonempty paths and8 source-proven empty records. All22 table identities
and candidate hashes were checked. Nominal axes expose WDTH1/500/1000,
wght100/501/900,HGHT1/500/1000;24 strict effective-axis comparisons passed at
four requested locations. Four nonempty selected variable GIDs change at all
three nondefault positions; the three sampled DEFAULT_ONLY GIDs do not.
The q candidate also completed24 actual CTFontDrawGlyphs draws into four private
nonempty PNGs. These prove candidate loading and bounded behavior, not original
CoreText parity: that original cannot load on this host.

Independent fontTools/C1 checks preserve full cmap/GID order,47,103 loca entries
and all22 table payloads between TTF/TTC. All94,204 HVAR/VVAR metric coefficient
models are exactly consistent. A bounded original-HVF/HarfBuzz comparison used
40 actual native glyph calls in explicit q coordinates. Selected-variable target vs original ideal TABLE
advances has0/50 fields above1/32, maximum0.020268354564905167. Original-HB vs
target-HB advances instead has6/50 fields above1/32, maximum0.328125: native
integer-grid equivalence remains failed, without relabeling it as coefficient
accuracy. Ten mixed CJK/Latin horizontal/vertical shaping runs preserve GIDs and
clusters;158/800 position fields fail, maximum159 sourceFUnits, including
DEFAULT_ONLY glyphs at nondefault positions. The raw contour comparator retains
35/40 failures (`segment_count_differs`); no numeric outline PASS is inferred
from incomparable paths. An additional target terminal zero-length closure is
observed separately and does not erase those failures.

`p7_validate_candidate.py` makes the bounded check reproducible with explicit
`--mode q|nominal`, full original identity and fresh private-only output. Actual
runs of each mode used32 native calls/four positions; all8 mixed shaping GID/
cluster sequences per mode match and94,204 metric models pass consistency.
Raw outline checks retain28/32 `segment_count_differs` failures per mode.
Nominal mode keeps the unaccepted P4 source-q hypothesis explicit: selected
nondefault HB source/target metrics fail3/30 fields, maximum0.46875; target vs
ideal TABLE metrics fail1/30, maximum0.03369140625, still above1/32. These new
nominal results do not replace the earlier q-scope samples. Raw path failures
are never converted to numeric PASS by dropping segments in the comparator.

Original-derived files and all private logs/raster/glyph records remain local.
Windows11, original-derived DirectWrite, real Qt/Swirl and installation are
NOT_RUN. Public CI cannot receive these proprietary candidates under the user's
no-upload constraint; authored controls are a separate validation scope.

Targeted authored regressions: glyph model4, original-driver safety5, nominal
driver integrity2 and face assembler11 PASS. The private-output guard now rejects
dot-segment escape before mkdir, as well as symlink redirection. Source-bound
sample recipes include driver hashes; old checkpoints remain historical evidence
and must not be silently reused after a driver change.
Tests contain only authored geometry; public CI never runs
this converter against or uploads an Apple-derived font.

First source checkpoint `b2f057e3420e192478c25862cbd9dc6eba78810a` is pushed.
Its [CI39585811589](https://github.com/SOLHK/Swirl/actions/runs/39585811589)
passed836 portable tests and6 audits, plus original-source macOS and authored
Windows Server C1 jobs. That Windows job says nothing about this original-derived
candidate or Windows11. Subsequent source/checkpoint hashes are in branch history.
The nominal-axis/source-guard checkpoint
`c13a57372ecb27145612094fe4704c5e0b8c3c69` is also pushed;
[CI39587343174](https://github.com/SOLHK/Swirl/actions/runs/39587343174)
passes840 portable tests and6 audits with the same separate native-job scopes.

## Resume commands (private outputs only)

Use the existing Python environment:
`~/Swirl-worktrees/vf-macos-windows-d1/build/vf-d1-private/venv/bin/python`.
Run from the isolated takeover worktree. Sample/native/model files are resumable
only under their exact recipe; use a fresh directory for changed code. Completed
face/nominal files are never overwritten.

```sh
python tools/swirl_vf/platform/p7_original_glyf.py sample \
  --source ~/Downloads/PingFangUI.ttc \
  --binary build/vf-takeover-private/p7-original-hvf-native/gid-00000-default/hvf_oracle \
  --output build/vf-takeover-private/p7-models-next
python tools/swirl_vf/platform/p7_original_glyf.py face \
  --source ~/Downloads/PingFangUI.ttc \
  --models build/vf-takeover-private/p7-models-next \
  --native-cache ~/Swirl-worktrees/vf-macos-windows-d1/build/vf-d1-private/original-hvf-all-default/hvf-run.json \
  --output build/vf-takeover-private/p7-face-next
python tools/swirl_vf/platform/p7_nominal_candidate.py \
  --source ~/Downloads/PingFangUI.ttc \
  --parent build/vf-takeover-private/p7-face-next \
  --output build/vf-takeover-private/p7-nominal-next
python tools/swirl_vf/platform/p7_compact_candidate.py \
  --source ~/Downloads/PingFangUI.ttc \
  --parent build/vf-takeover-private/p7-face-stage1 \
  --output build/vf-takeover-private/p7-face-compact-next
python tools/swirl_vf/platform/p7_validate_candidate.py \
  --source ~/Downloads/PingFangUI.ttc \
  --candidate build/vf-takeover-private/p7-nominal-stage1/P7-Original-face0-NOMINAL-EXPERIMENTAL.ttc \
  --binary build/vf-takeover-private/p7-original-hvf-native/gid-00000-default/hvf_oracle \
  --mode nominal \
  --expected-sha256 39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890 \
  --output build/vf-takeover-private/p7-validation-next
```

Next work should replace bounded sampled approximations with adequate original
variation models before extending all GIDs/faces. Keep source-user mapping,
native metric failures, phantom/vertical-origin semantics, unscaled tables,
component provenance and Windows font-level acceptance as separate gates.

Primary references reviewed before implementation: existing project HVF/C1
code; [Apple HVGL](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html),
[fontTools TTGlyphPen](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/pens/ttGlyphPen.py),
[VariationModel](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/varLib/models.py),
[public UPEM visitor](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/scaleUpem.py),
[OpenType glyf](https://learn.microsoft.com/en-us/typography/opentype/spec/glyf).
Existing algorithms/public APIs are reused; no upstream implementation copied.
