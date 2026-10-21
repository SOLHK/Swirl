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
