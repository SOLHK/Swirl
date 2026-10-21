# P8 original variable-GID batch conversion

Worktree `~/Swirl-worktrees/vf-takeover-abc`, only writable/pushable branch
`work/vf-takeover-abc-20261021`. Fresh local/remote parent is
`0aee48913ca7baec8cb2771c54552317153a7c36`; clean start. P4–P7 source,
handoffs and C1 verified-byte packing are reused. Production gates, original
1/32 limits and all old failure evidence remain unchanged.

## A1 actual first batch

The exact original source SHA is
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
Face0 has47,102 GIDs and UPEM1028. The experiment uses legal15x/UPEM15420.
The original and P7 candidates remain unchanged and strictly local.

`hvf_representatives.py` deterministically selected100 original GIDs from the
real cmap and cached HVGL DAG metadata, without a new full native sweep. The
private plan includes historical failures, simple/complex outlines, up to904
on/off points,72 contours and depth12; Latin, digits, punctuation, CJK regions,
rotations and tangent types0/1/2 are represented. It includes all five genuinely
empty original glyphs; these are measured cases, not fallback placeholders.

`p8_batch_original.py` invokes the existing P7 converter independently per GID,
binds each checkpoint to original/source/recipe/code/oracle bytes, verifies
saved glyph/model/native hashes on resume, and isolates exceptions. No failed
model is substituted with a static default and counted as variable success.
The full-face path shares the existing P7/C1 assembler and gates. Native-default
cache and model-receipt hashes are also checked after assembly.

The bounded `tensor5` profile uses125 exact F2 training nodes and the SAME four
independent P7 holdouts. The unchanged P7 default remains27 nodes. No holdout is
promoted or removed. Reusing C1 VariationModel, actual original portable models
improve fixed holdout error at GID1166 from15.9443759031 to5.76582403008 and at
GID19177 from5.40384016468 to1.20298182408. Default quantization failures remain;
this is finite interpolation improvement, not continuous-domain acceptance.
The investigated axis-line-only critical-node prototype was not selected:
it worsened one holdout and exceeded its budget on complex cases. That unused
prototype and observations remain private, not a second conversion engine.

Actual first checkpoint:10 GIDs encoded,0 exceptions,1,290 actual Apple HVF
comparisons PASS against the unchanged portable/native geometry check. Six
GIDs have nonzero outline variations; all10 have nonzero metric variations.
Four empty-outline models pass the strict sampled outline bound, six models
pass the strict sampled TABLE-metric bound. These are independent counts;
NONE is accepted as native target equivalence. Maximum sampled outline error
is8.51977856738663 and TABLE metric error1/30 FUnit; strict failures are retained.
The first10 took18.997seconds; this does not justify an unmeasured all-face run.

Private plan: `build/vf-takeover-private/p8-representatives-stage1.json`.
Private checkpoints: `build/vf-takeover-private/p8-models-100-tensor-stage1/`.
Every GID has a resumable P7 receipt and actual glyf/gvar model/native samples.
All proprietary files/raw observations/execution logs remain under the ignored
private build root and MUST NOT enter GitHub/Artifacts. Public evidence contains
only whitelisted counts/scalars, not the full private receipt.

Targeted authored regressions at A1: representative selector8, tensor grid3,
batch identity/counting3 and existing P7 transport/integrity9 PASS.

Primary implementations reviewed/reused:
[fontTools4.61.1 VariationModel](https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/varLib/models.py),
[OpenType gvar/phantoms](https://learn.microsoft.com/en-us/typography/opentype/spec/gvar),
[Apple HVGL](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html).
No upstream code copied; only existing project algorithms and public APIs reused.

## A2 actual100 GIDs and independent candidate validation

All100 selected GIDs completed,0 build exceptions,12,900 actual Apple HVF
source-extraction comparisons PASS. There are95 nonzero outline-variation
models and100 nonzero metric-variation models; five genuinely empty outlines
are separately identified. All100 have nonzero gvar data,10,281 tuples total.
At all125 training plus4 frozen holdouts,5/100 pass the strict model outline
bound (ALL five are empty) and85/100 pass TABLE metric bounds. No nonempty
outline passes that broader bound. Maximum model errors remain8.51977856738663
outline and1/30 TABLE FUnit. The resumed90 took207.458seconds.

The actual assembled/compacted q candidate is local:
`build/vf-takeover-private/p8-face-100-compact-stage1/P7-Original-face0-EXPERIMENTAL.ttc`.
Its legacy P7 filename reflects the reused builder; this is the P8 batch output.
TTC35,252,464bytes, SHA256
`ee1c81a5efc9393aff92e648569bf3ab862c0890d7c629650fbfdbfb1bb66d74`;
TTF SHA256 `e99aac02392e4c4d2e223a922abad6e3f720e72513d7714f85c281b32ff249c2`.
All47,102 default GIDs/cmap remain; ONLY100 have selected variable models and
47,002 remain DEFAULT_ONLY. C1 exactly reopens9,598,940 default/phantom points,
10,281 tuples and22 table references. Closure compaction again removes739,241
redundant points without changing hmtx/vmtx/HVAR/VVAR bytes. These are structure
and serialized-model checks, not native original equivalence.

`p8_validate_models.py` independently binds the actual candidate SHA to the
assembly receipt, exact batch receipt SHA/selected model set and serialized
verification. It verifies every model/glyf/native-cache hash; it does not simply
assume an old five-model font contains the new100 models. Seven cached original
native cases per GID (default, wght extremes, four unchanged holdouts) are then
compared with ACTUAL decoded candidate HarfBuzz paths and advances. It makes
ZERO new Apple calls while checking all12,900 native cache hashes.

Actual independent result:100 GIDs/700 cases;167 outline cases pass,533 fail
`outside_budget`, with maximum8.521084573934047 sourceFUnits.12 GIDs pass all
SEVEN sampled outlines, including the five empty ones. TABLE metrics fail8 of
1,400 advance fields, maximum0.0625;93 GIDs pass all seven TABLE-metric checks.
Original-HB-reference metrics fail227/1,400, maximum0.53125;0 GIDs pass every
HB-reference metric check. These seven-position results do NOT replace the
broader129-position model checks. Source API, coefficient error, F2 coordinate
quantization and native integer/output scaling remain separate;300 requested-q
quantization observations are explicitly recorded. All original/native target
acceptance flags remainfalse. No comparator/threshold/failed case was changed.

Actual CoreText q-candidate extraction:600 records across100 GIDs, four locations
and reverse default/mixed requests;200 exact reverse pairs,18 strict effective
axis checks,22 table identities,570 nonempty paths and30 proven-empty records.
95 GIDs show native outline movement and100 show raw metric movement. Actual
bounded drawing also completes14 glyph draws into two private nonempty PNGs.
Two earlier private scratch attempts exited139 BEFORE drawing because the
harness incorrectly cast unboxed CoreText table tags to NSNumber. Those logs
remain saved; using Apple's documented CFArrayGetValueAtIndex tag extraction
fixes the private harness. No candidate raster failure is inferred from that
bridge error. Original CoreText parity remains unavailable on this host.

## Windows preparation and full-plan checkpoints

P8 source checkpoints `d75b1b72951baaef17d4d66af3c8920ce4a8b4a1` (A1 batch)
and `3a4ec7ab57481c09ffc0646347d9142b109e0bab` (local Windows gate) are pushed.
The actual [Windows authored smoke39592789402](https://github.com/SOLHK/Swirl/actions/runs/39592789402)
passes on Server2022/kernel20348/product_type3:1 authored face/7 GIDs,62 native
instances,186 strict binary32 axis comparisons,17 cmap pairs and10 DPI/theme
rasters. Only its fixed aggregate is published. Original-derived DirectWrite,
Windows11, Qt/Swirl and installation are still NOT_RUN. See the separate
[local Windows guide](SWIRL_VF_P8_WINDOWS_LOCAL_20261021.md).

The original100 q-model build succeeds; nominal reparameterization exposed a
new real block: interior gvar supports are not F2-exact before serialization,
and the P7 frontend called the strict metric writer before that encoding step.
First failure log `build/vf-takeover-private/p8-nominal-100-stage1.log` is preserved;
no file was produced there and no guard was removed. The minimal fix and fresh
nominal candidate will be recorded separately after actual verification.

The all47,102-GID source-bound plan is initialized under
`build/vf-takeover-private/p8-models-full-tensor-stage1/`.
`p8_seed_batch.py` verifies and exclusively copies the immutable100 per-GID
checkpoints into that larger plan, skipping its already valid GID0. It changes
ONLY the exclusively owned target receipt after byte/recipe checks;0 native
calls and no original100 checkpoint changes. The target RUNNER MUST BE STOPPED
during seeding: current runner/seeder do not share a lock. Copies interrupted
before confirmation remain uncounted and cause an explicit refusal on resume.
The next bounded128-new-GID run is in progress, not a complete-face claim.

Targeted additions at A2: independent validator12 and seeder5 authored regressions
PASS. Global regression CI is automatic; no manual repetition of the old846
baseline is used to claim original conversion progress.

A new parallel branch `work/vf-p8-gvar-pro` was observed at
`7ff8d17cb18c624b50895cda00216a2f3a86f844` and read only. Its point-ring identity
helper has no file overlap or validated gvar mesh fix to reuse here. It is not
merged or modified; all parallel history remains intact.

## Actual nominal support-encoding repair

The minimal frontend fix is in `p7_nominal_candidate.serialized_metric_candidate`.
After range restriction, an interior support may be2/3, which is not F2DOT14.
The strict metric writer correctly refuses that transient value. The frontend
now serializes/reopens gvar FIRST using the existing packed-delta/overflow
validator, then derives HVAR/VVAR from the actual encoded supports and phantoms.
The writer's exact-F2 check is unchanged; no tolerance is enlarged. The normalized
support encoding difference is explicitly recorded in normalized-axis units,
not relabelled as a glyph-FUnit accuracy result.

The first repaired attempt exposed an additional wrapper assumption: fontTools
instancer removes empty gvar dictionary entries, whereas reopening the binary
table restores empty slots for every GID. The audit now captures all original
GID slots with explicit empty lists. This was not a glyph-name/post-format
change; that early hypothesis was ruled out by the actual instancer source.
Default-only GIDs are still not counted as variable. Both failed private build
logs at nominal100 stage1 and stage2 are preserved.

Actual successful output:
`build/vf-takeover-private/p8-nominal-100-stage3/P7-Original-face0-NOMINAL-EXPERIMENTAL.ttc`,
35,315,848bytes, SHA256
`ac721ddf2522db374ba2b873c4fc1c79e2d3b6a49798825f99bdb00c97051ead`;
TTF SHA256 `48e49a8369b06bc6f98ce6776b836719965e5282c0022e0bda1892ecb3b49a44`.
There are8,352 quantized support coordinates, maximum change
0.000028316827352048435 normalized-axis units (< half an F2 cell). All94,204
HVAR/VVAR metric models exactly match final gvar phantoms; C1 decoded-byte and
22-table packing gates pass. All inherited source-model/native precision
failures and every production acceptance flag remain unchanged/false.

Actual CoreText nominal100 probe uses16 GIDs from the exact100 plan (all5 empty
plus11 spread nonempty), four nominal positions and two reverse requests:
96 records,32 exact reverse pairs,18 strict effective-axis checks,22 table
identities,66 paths and30 source-proven empty records,0 terminal errors.
All11 nonempty samples change outlines; all16 change raw metrics. Original and
candidate hashes remain unchanged. No nominal raster, original CoreText parity,
DirectWrite original or Windows11 acceptance is implied.

Five focused nominal regressions pass, including the authored2/3 support failure
before repair, actual encoded10923/16384 support after repair, exact metric
consistency, packed-delta overflow rejection and default-only-slot handling.
The original P7 identity/integrity tests remain intact.

## Resume current batch

```sh
SWIRL_VF_PY="$HOME/Swirl-worktrees/vf-macos-windows-d1/build/vf-d1-private/venv/bin/python"
"$SWIRL_VF_PY" tools/swirl_vf/platform/p8_batch_original.py run \
  --source ~/Downloads/PingFangUI.ttc \
  --binary build/vf-takeover-private/p7-original-hvf-native/gid-00000-default/hvf_oracle \
  --plan build/vf-takeover-private/p8-representatives-stage1.json \
  --output build/vf-takeover-private/p8-models-100-tensor-stage1 \
  --profile tensor5 --max-new-gids 90
```

Changing source, plan or code requires a fresh output; old checkpoints are never
overwritten. Existing strict source/target mapping, native metrics, component,
metadata/table and full-variable-model gates remain unresolved. Real original
DirectWrite/Windows11 and a complete47,102-variable-GID face are NOT_RUN/NOT_BUILT
at this first checkpoint. PR24 remains draft/unmerged; no other branch is changed.
