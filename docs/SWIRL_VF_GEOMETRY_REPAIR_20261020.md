# Swirl-VF: actual isolated-tangent and hierarchy corrections

This supersedes the pending-experiment status in
`SWIRL_VF_GEOMETRY_HANDOFF_20261020.md`, but does not announce a finished font.

## Native observations and two implemented corrections

The 22 original synthetic tangent experiments at commit
`5cb42619785c66317552867d251784df2b0323b9`, run `39285093026`, completed natively.
Artifact `12203091876` archive SHA-256:
`7272fc9cb483d58d2b4cb33570a0869a37eb244f9f548f1e1f53cb2047383250`.

They distinguish an isolated Type-2 tangent from an ordinary explicit corner.
For interpolated on-point P and its neighbouring quadratic controls A and B,
its observed on-point is the orthogonal projection of P onto the line AB:

`Q = A + (B-A) * dot(P-A, B-A) / dot(B-A, B-A)`.

`tangent_geometry.resolve_path()` implements this operation in float64, with
scaled arithmetic to avoid squaring extremely short/long control directions.
It also retains the Type-0 parallel-factor rule and unchanged Type-1 corners.
Types 3/4 and a collapsed Type-2 control line fail explicitly. Type-2 evaluation
is opt-in, not a silently promoted production/font-equivalence claim. The batch
and scalar evaluators both support it and preserve all emitted source contours.

The 28 original synthetic hierarchy experiments at commit
`b98850c3caaec7874f7e8c5a95866bbc4741df36`, run `39288598642`, also completed.
Artifact `12205148657` archive SHA-256:
`520de3b070358c76ff0679d7a299ef00b1e6b9600b442965db3bfb7204208fbb`.

Their unchanged gate FAILED in two cases: descendant translation combined with
a deeper rotation (errors 2.7793726171485815 and 3.2929610382974204 FUnits).
The other 26 cases passed. This disproved the previous additive-translation
hypothesis, including the temporary expected-formula adjustment in the earlier
local test. The native evidence, not a passing local assertion, is decisive.

Both `ExperimentalRenderer` and `BatchGeometry` now compose each deeper local
transform AFTER the inherited transform. Thus `T_new = R_delta * T_old + deltaT`
and `angle_new = angle_old + deltaAngle`. Sparse rows are processed without an
extra allocation of the entire structure tree. Axis deltas remain additive.
The regression's expected formula now matches the independent native result;
no error threshold, sample input or comparator was relaxed.

## Evidence obtained before this commit

After implementing both corrections, local comparison with the archived native
results passed 22/22 tangent experiments (maximum discrepancy 0) and 28/28
hierarchy experiments (maximum discrepancy 5.684341886080802e-14 FUnits).
These are re-comparisons of independently generated native records, not claims
that the new code already ran on macOS. The local focused suite passed 32 tests:
15 existing HVF, 8 hierarchy, and 9 projection/batch tests. The original native
failure records and initial local expected-formula failure are retained.

Fresh native CI runs the 22 original plus 48 independent transformed/perturbed
projection cases. It separately rechecks all 28 hierarchy experiments, then the
same 32 original-source GIDs at the same 34 design positions as the previous
1,088-observation calibration. It imports the prior sample selector and exact
comparator unchanged and keeps the 1/32 FUnit gate. A failing source comparison
returns nonzero; diagnostic completion alone is not accepted.

Only synthetic geometry may be logged in full. The exact resident Apple source
must match SHA-256
`39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890`;
its comparison publishes only counts, GIDs, error magnitudes and failure codes,
not original outlines or a font. The source is checked again after the run.

## Remaining acceptance boundary

The new geometry code does not resolve the original user-coordinate `avar`
semantics, original CoreText axis readback, metrics, all-face shaping, full
adaptive gvar reconstruction or Windows 11 installation/real UI/DPI performance.
A default-position traversal is only a portable execution/finite-coordinate
check and must not be labelled native glyph accuracy. No Apple-derived final
`Swirl-VF.ttc` is produced or published by these experiments.

The exact later CI results and any remaining source failures must be read before
promoting the new backend into a release build. Swirl UI and Rust Core are not
modified. The prior concurrent Core commit `a066f7d4` remains in ancestry.
