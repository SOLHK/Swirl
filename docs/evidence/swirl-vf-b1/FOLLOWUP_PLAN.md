# B1 follow-up: frozen before its first native execution

This plan is inferred from [stage 1](STAGE1_RESULTS.md), run 39399674995.
All first-stage training and holdout points are now seen data for the new
candidate. Neither the old fixture nor its rejected hypotheses is rewritten.
The production oracle/rebuilder and both strict tolerances remain unchanged.

## Independent numeric samples

The first block contains 510 positions: two UPEMs (1000, 1024), five variants
(`gvar`, `phantom_only`, `phantom_shift_91`, `vvar`, `hvar_vvar`), three widths
(-0.375, 0, +0.375), and these 17 previously unseen heights:

`-0.9375, -0.875, -0.8125, -0.6875, -0.5625, -0.4375, -0.3125,
-0.1875, -0.0625, +0.0625, +0.1875, +0.3125, +0.4375, +0.5625,
+0.6875, +0.8125, +0.9375`.

The second block contains 36 positions: the same two UPEMs and three widths,
heights -0.0625 and +0.0625, and three storage controls. `hvar_vvar_vorg`
adds only VORG to `hvar_vvar`; `hvar_vvar_odd_default` changes only stored
witness advance 1000 to 1001 (and derived hhea maximum); the last variant adds
only VORG to that odd-width control. VORG Y is 911 and stores no X. The X
comparisons separately retain current-advance half, continuous-advance half,
exact stored half (500.5 for the odd case), and truncated stored half (500).

Before native execution, review identified that all integer phantom heights in
those 17 new locations are not divisible by 125. Four additional, separately
labeled exact-normalization-grid controls therefore append WDTH=0, HGHT=53/64
to gvar and vvar at both UPEMs. The original 546 requests remain unchanged.
Here the rounded-delta height is 1125: the candidate UPEM-1000 normalization is
exact and predicts 1125, while a uniform minus-one rule predicts 1124. The VVAR
continuous-height truncation candidate independently predicts 1124. This is
a preregistered discriminator, never a proposed correction.

Total: **16 fonts, 550 positions, 32 independent native processes, 1,100 raw
records and 550 exact forward/reverse replay pairs**. The fixture and extra
origin-model manifest are written and hashed before launching any native
process. Each observation retains its raw values, binary64 bits, exact unit
conversion and full computation basis in the report/artifact.

## Falsifiable candidates and interpretive limits

For gvar advance, the new candidate is:

`H = 1000 + roundHalfAway(60*y) - roundHalfAway(-90*y)`;
`trunc(floor(H*65536/UPEM)*UPEM/65536)`.

For VVAR advance the separate candidate is `trunc(1000+150*y)`.
At y=-7/8, gvar UPEM1024 predicts 868, whereas whole-height, half-up absolute
phantom, and ties-to-even alternatives predict 869. At y=+1/16 the gvar
UPEM1024 prediction is 1010, versus 1009 for whole-height truncation/rounding.
These are raw API predictions; strict comparisons still use continuous height.

The vertical integers alone cannot uniquely identify 16.16 as the internal
normalization bit width. Other power-of-two denominators can yield the same
final truncations. A match establishes a finite behavioral model only.

For ordinary gvar origin Y, let B be continuous visible top and P be the integer
top obtained by rounding the signed phantom delta. Compare `B+P-ceil(B)` against
`B+P-round(B)` and the continuous top. For integer P the first expression is
identically `B+floor(P-B)`: the observations cannot decide whether the internal
operation is bbox ceiling or bearing flooring. At y=+3/16 the first predicts
830.25 while the nearest-bbox alternative predicts 831.25. The fixed-outline
and translated-phantom controls test separate visible-geometry dependence.
VVAR and VORG source candidates remain explicitly separate.

Candidate failures are recorded as rejections. Candidate successes never change
native observations, turn strict metric failures into passes, or establish
continuous-design-space or original-font acceptance.

## Original-font VORG ablation and strict gate

The original source is SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`.
Create a private temporary copy using raw TTC directory edits: remove each VORG
directory record and update only directory count/search fields. Every retained
table payload, including raw avar ordering and private HVGL payloads, must remain
byte-for-byte identical. The original file remains read-only and is rehashed.

Three independent oracle sessions measure original, temporary copy, and original
again, each binding all 32 face identities. Each samples the same 15 requests /
60 records used by the original bounded check. A refusal of the modified source
is evidence of refusal, not X-origin measurements. The original repeat still
runs; both numeric equality and scalar binary64 equality are required.

Only finite whitelisted numeric metrics, identities and byte-audit summaries
leave the temporary directory. No original or modified font, private outline,
or native protocol transcript is published. The comparison does not claim
native outline equality across variants merely because table payloads match.

The two original sessions reuse their measured records for the unmodified
production `with_phantoms` X-representation check. Any original strict failure
keeps the CI job red even when the ablation experiment completes. The frozen
first-stage workflow is limited to its original code paths so this follow-up
does not rerun the unchanged 624-position matrix. The original 849/850 failure
logs remain preserved as the strict reference.
