# Three-axis branch investigation — 2026-11-03

**Both targets now pass the independent sampled native acceptance below.**
The limit remains 1/32 FUnit. Earlier sections retain the failed models and
intermediate checkpoints; their pending status describes those earlier runs.
These are single-glyph research fonts using standard shaping, not complete
fonts or release artifacts. A continuous-space error bound is not claimed.

## Latest two-target sampled native acceptance

The final serialized candidates use factored rational projections, adaptive
local tricubic fields, sparse unclamped-parameter maps and simultaneous avar2
clamp ramps. Two hidden copies of each physical input provide repeated factors
for cubic powers without coupling the three independent physical controls to
one diagonal. CFF2 tensor blends, bounded axis-power fallback and shared operand
subroutines encode those fields; required GSUB FeatureVariations select the
local outline in ordinary native shaping. This changes representation, not
just the coefficients inside the original obstructed support cells.

Independent seed `2026110445` gives the following maximum Euclidean control
errors in original source FUnits, against fresh Apple libhvf observations:

| Source GID | CoreText observations / maximum | HarfBuzz observations / maximum | fontTools observations / maximum |
| --- | --- | --- | --- |
| 1166 | 3,153 / **0.025831485558** | 3,153 / **0.023699382672** | 271 / **0.018391232668** |
| 19177 | 3,123 / **0.016495875619** | 3,123 / **0.014905942892** | 269 / **0.011886939910** |

Every listed engine has zero outline, topology, winding and advance-comparison
failures. Closed paths are checked; only an exactly redundant closing line is
canonicalized. Source and candidate hashes remain unchanged. CoreText verifies
the actual run's font tables and exact user-axis readback for every request.
HarfBuzz 14.6.0 and fontTools 4.61.1 independently reopen the saved fonts. The
fontTools subset is fixed before errors are measured and spans every category.

There are 3,134 / 3,108 distinct physical user positions. Each glyph includes
2,048 random triples, 192 single-axis requests, 192 requests over all dual-axis
pairs, 125 cube-grid checks, analytic branch/clamp contacts, 384 seam-neighbour
requests and 128 requests derived from the previous dense-model holdouts.
All inputs are predeclared, including fractional user coordinates. The actual
coordinates after original normalization define the source reference.

All 2,048 random triples per glyph are excluded from every declared midpoint
fitting/refinement sampling family, including local jitter and analytic chord
contacts. The conservative exclusion certificate covers 2,836 / 2,806 total
observations. Boundary checks that can overlap training are retained and are
not relabelled as independent holdouts. The separate source-aligned atlas has
its own explicit sample receipts; this midpoint certificate does not cover it.

Additional comparisons draw both adjacent local glyphs at a common exact
post-avar2 coordinate vector: 256 pairs per glyph pass in both engines. Maximum
jumps are 0.017333984375 / 0.006652832031 FUnit in HarfBuzz and
0.017302664490 / 0.006635054331 in fontTools. This is a patch-continuity check,
not a replacement for physical-coordinate source accuracy.

CoreText advances differ from unrounded original-source metric tables by at
most 0.012224449 FUnit. HarfBuzz advances exactly match original-source
HarfBuzz; its existing integer HVAR rounding differs from unrounded tables by
up to 0.507054109 FUnit. The latter is explicitly not claimed as 1/32-accurate
reproduction of ideal unrounded advances. fontTools metric errors remain
below 0.006085 FUnit.

| Source GID | Candidate bytes | Local cells | Maximum CFF2 stack | CFF2 regions | Global subroutines |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1166 | 62,247,684 | 2,048 | 165 | 59,582 | 32,768 |
| 19177 | 256,080,332 | 4,096 | 197 | 43,444 | 35,302 |

All main strings and subroutines stay within 65,535 bytes; added call depth is
at most two. GID 19177 serializes directly from freshly rechecked fields in
594.36 seconds, avoiding an uncompressed Horner intermediate. The earlier
unfinished Horner build was superseded, not reported as a native pass. No
field coefficients were refitted during the encoding change.

The actual source, algorithms, tests and licenses of both requested upstream
projects were inspected and their controls rebuilt and executed; see the
[open-source comparison](SWIRL_VF_OPEN_SOURCE_INTERPOLATION_20261103.md).
The axis-copy mechanism is useful, while neither upstream project supplies a
more accurate HVF fitter. Swirl's factorization and adaptive fields are retained.
No upstream source code, font contours or binaries are incorporated.

The final code regression has **1,021 tests: 1,014 passed, seven skipped**;
six parser audits also pass. Five skips require Linux-specific native APIs and
two are separate native integration gates. The actual macOS native runs above
are separate executed evidence, not inferred from those unit tests. Remote CI
is not claimed. Public aggregate counts, hashes and per-engine diagnostics are
in the [acceptance receipt](evidence/SWIRL_VF_JOINT_ACCEPTANCE_20261103.json).

Remaining limits: these large one-source-glyph fonts do not establish full-font
scalability. Hidden computational axes must stay at their defaults, and direct
access to the unselected base GID is outside the standard-shaping acceptance.
Arbitrary binary64 input transport and an error bound over the entire continuous
design space remain uncertified. PR #53 stays Draft; no release, main/test
integration, source font, extracted outline or raw private record is published.

## Historical investigation and intermediate checkpoints

Work starts at PR #52's `b9d8cebf1de19acb31a3e54533419b9645c47e0d` in a separate
worktree and `work/swirlvf-joint-acceptance-20261103`. PR #49 and #51 were read
and their branches preserved. The four original worktrees were clean at the
initial inspection. No changes were made to main, test, UI, metrics, installers
or the network runtime. The physical axis tags remain `WDTH`, `wght`, `HGHT`.

## Reproduced failure and isolated cause

The existing adaptive tensor fitter was rerun with its 507-node budget, 27 grid
positions and 128 independent simultaneous-axis holdouts per glyph. All **310**
source/native comparisons pass, with maximum portable/Apple libhvf discrepancy
`5.684342e-13` FUnit. The fitted functions still fail:

| Source GID | Actual training nodes | Maximum independent joint error | Native model failures |
| --- | ---: | ---: | ---: |
| 1166 | 486 | 2.595998748 | 125 / 155 |
| 19177 | 504 | 1.696680398 | 121 / 155 |

The retained dense models were then evaluated on **new**, non-grid samples:
maximum errors are **0.879969819 / 0.561059751**; 106 / 66 of 128 samples fail.
Their 4,041 / 4,031 nonzero regions both still trigger
`cff2_blend_operand_stack_overflow`. These are failed models, not candidates.

The new source probe executes **887** Apple HVF comparisons on face 0: single
axes, every dual-axis pair, 256 new random triple-axis positions in total, cube
boundaries, actual internal-axis and tangent-projection contacts and their two
neighbours, and polynomial witnesses. All portable/native comparisons pass;
the maximum discrepancy is **7.190187e-13**. No source samples fit a new model.
The retained fitter's entire F2DOT14 and midpoint grids are explicitly excluded
from the new dense-model holdouts. Type-0 contacts were not found on the eight
random chords per glyph; their coverage must not be inferred from these tests.

`segment_partition` generalizes the existing source-coefficient propagation to
any chord on which all three root axes change. Descendant sign changes are
propagated before clamp/projection roots are calculated. It retains identities,
direction reversal and the existing single-axis API. The symbolic work remains
bounded by the existing 65,536-knot and 8,000,000-coordinate limits; it does not
construct a full three-dimensional cell atlas.

`interpolation_witness` computes divided-difference bounds using exact rational
arithmetic on the supplied binary64 observations. Inside an ordinary CFF2
support cell, a one-axis restriction is linear and a three-axis chord has degree
at most three. The annihilating weighted sum of observed controls, divided by
the weight L1 norm, bounds the maximum error of **any** such polynomial. This
rules out coefficient-only refitting in the retained cells:

| GID | Conditional single-axis lower bound | Simultaneous three-axis lower bound |
| --- | ---: | ---: |
| 1166 | 0.449737811 | 0.059676177 |
| 19177 | 0.322685662 | 0.048439274 |

All four bounds are independently reproduced from Apple observations. They
describe the existing support cells and ideal polynomial arithmetic. They do
not prove that all CFF2 models, different regions, nonlinear axis mappings or
other formats are incapable of meeting the tolerance. Native rounding itself
is not certified by this algebraic argument.

## Alternative representations actually tested

Independent contour fitting passes only 4 of 6 contours for GID 1166 and 2 of
18 for GID 19177. Its maximum holdout errors remain 2.595992443 and 1.215582531.
Thus a contour decomposition alone does not resolve the branch problem.

The new authored representation probe reuses the existing CFF2 fixture and
exact-axis native adapter. Both controls preserve three physical input axes and
are serialized and reopened. Its 71 positions include fractional user values
whose exact native readback can be verified. Reference geometry comes from the
authored source formula, not from the fitted target.

| Authored control | fontTools reload | CoreText | HarfBuzz 14.6.0 |
| --- | --- | --- | --- |
| Coupled `avar` v2 + ordinary CFF2 | Pass, max 0.006285123 | Pass, max 0.008936914 | Pass, max 0.006948067 |
| Coupled VARC component + CFF2 | Pass, max 0.000010173 | 71 / 71 topology failures | 71 / 71 topology failures |

HarfBuzz explicitly emits the closing edge that the source pen and CoreText
leave implicit. The comparison canonicalizes only an exact line to the contour
start immediately before `closePath`. A regression retains near-but-not-equal
edges and closing curves. This does not move controls or relax the threshold.
VARC produces the underlying CFF2 placeholder outline in the tested engines,
rather than the specified component. Engine/version scope matters; this does
not claim universal lack of VARC support.

An earlier arbitrary-binary64 user-coordinate control batch failed the existing
exact native payload replay at request 27 (`advance_width`). That failure is
retained in the receipt. Passing the subsequent explicitly representable user
positions does not certify every coordinate or original-source axis transport.
The first partial-axis VARC fixture also exposed fontTools' CFF2 location-stack
inheritance limitation. The final authored control explicitly copies all three
coordinates; no installed library or source glyph was patched.

`avar` v2 therefore warrants further source-hierarchy work, but it is not yet a
compiler for the source's nested axes, clamps, rational projections and rigid
transforms. The source exposes many distinct oblique branch directions. A
single successful affine remap does not establish whole-font axis/region
capacity. The proposed [avar2](https://github.com/harfbuzz/boring-expansion-spec/blob/main/avar2.md)
mapping computes its output coordinates from one common input vector; it does
not sequentially evaluate an arbitrary HVF hierarchy. The tested
[VARC](https://github.com/harfbuzz/boring-expansion-spec/blob/main/VARC.md) route
cannot currently replace that hierarchy in these native engines.

## Executed checks and reproduction

Local environment: macOS 26.5.1 ARM64, Python 3.12.16, fontTools 4.61.1,
NumPy 2.2.6, HarfBuzz 14.6.0. The final Python run executes **984 tests: 977
pass, seven platform skips, zero failures/errors**; six parser audits pass.
The two native diagnostic commands below deliberately return **1** because the
retained model and VARC failures remain visible. Unit-test success is not font
acceptance. Remote CI has not been claimed as executed for this checkpoint.

```sh
python -m unittest discover -s tools/swirl_vf/tests -v
python -m unittest discover -s tools/swirl_vf/audit -p 'test_*.py' -v
python tools/swirl_vf/platform/probe_joint_boundaries.py \
  --source "$PRIVATE_SOURCE" --source-sha256 "$SOURCE_SHA256" \
  --binary "$HVF_ORACLE" --private-output "$NEW_PRIVATE_OUTPUT" \
  --dense-models "$RETAINED_DENSE_MODEL_DIRECTORY"
python tools/swirl_vf/platform/probe_joint_representations.py \
  --private-output "$ANOTHER_NEW_PRIVATE_OUTPUT"
```

The dense directory contains the previously retained `dense-1166.json/.npz`
and `dense-19177.json/.npz`; their hashes are in the
[aggregate receipt](evidence/SWIRL_VF_JOINT_20261103.json). Private fonts,
coefficients, root coordinates and raw transcripts are excluded from Git.
The receipt binds the actual code, test log, sample plans and native transcripts.

## Acceptance boundary

Actual source coverage is **face 0, GIDs 1166 and 19177**, out of 32 faces with
47,102 GIDs each. Accepted source glyphs and accepted complete faces both remain
**zero**. Stage E was not entered because the two primary targets still fail
the joint CFF2 fit and serialized/native source-font requirements. No complete
font, all-face applicability proof or continuous-space equivalence is claimed.

Command-line push lacked a local HTTPS credential; the connected GitHub Git
data API published the tested tree without force updating an existing branch.
The first remote commit is `3a583f7bd1f3a4787cabd9276480acf452d6e8bd`, tree
`c90ce889e40c1f02b10712347761a700d45bbf94`, matching local commit `ff1bf82f`.
Subsequent commits preserve that ancestry. Main and test were not changed.

## Continuation: factored projection and local polynomial encoding

The continuation preserves the uncommitted research found in this worktree and
adds public regression coverage. `projection_factorization` separates a Type-2
point into its neighbouring control, direction, and unclamped rational parameter.
Clamping is applied to the scalar, after interpolation, rather than fitting the
kink into the same ordinary multilinear region. `joint_polynomial` encodes local
tricubic tensors by nested Horner blends with one `vsindex`. Absolute-control
coefficient quantization preserves explicitly certified closing controls.
These are reusable components, not yet an accepted compiler for both targets.

On this continuation, seven polynomial/projection regression tests pass. A new
serialized, self-authored clamp/polynomial/GSUB control passes **155 positions per
engine**, with no outline or region-selection failures: CoreText maximum
**0.004202047**, HarfBuzz **0.002863535**, fontTools **0.003309031** FUnit.
The control keeps the three physical axes and uses four hidden computational
axes. Its success does not certify original HVF glyphs, all user coordinates,
metrics, or other engines. The native observer verifies the actual shaping-run
tables and exact axis readback. All control artifacts remain outside Git.

The CFF2 packer also supports releasing decoded programs after encoding, to
bound memory while assembling many polynomial regions. Its bytecode mode is
checked through serialization and reload, including subroutine call bias.
Both source GIDs remain **not finally accepted**; PR #53 remains Draft.

## Continuation: reusable source-field compiler and independent acceptance

`joint_cells` adaptively subdivides three-dimensional octants on the exact
F2DOT14 grid. Tricubic field probes include source-derived internal-axis and
Type-0 contacts. Type-2 projection clamps are handled separately: a sparse
hierarchical tensor interpolates the unclamped rational parameter, and four
simultaneous avar2 ramps implement each clipped scalar. The original three
physical axes and their first-stage avar maps remain intact. The polynomial
fields are selected through required GSUB FeatureVariations in ordinary
CoreText/HarfBuzz shaping. Absolute control quantization preserves closure.

The new builder rechecks imported fields against the current evaluator before
admitting serialization; old acceptance flags are not sufficient. Sparse
column storage removes only exact zeros. A separate verifier consumes no fit
samples and compares reloaded fonts to Apple libhvf, including control points,
topology, closed contours, winding, advances, actual run tables and exact axis
readback. It covers every single/dual-axis combination, random triples,
boundaries, analytic branch contacts, region seams and all previous dense-model
holdouts. Boundary checks can coincide with training endpoints; the random
acceptance seed is separate from every training/refinement seed.

For the 2,048-cell GID 1166 font, seed `2026110443` gives:

| Engine | Observations | Maximum outline error | Failures |
| --- | ---: | ---: | ---: |
| CoreText | 3,140 | 0.019208595256 | 0 |
| HarfBuzz 14.6.0 | 3,140 | 0.018971427426 | 0 |
| fontTools 4.61.1 | 269 | 0.012548240657 | 0 |

The fontTools subset is selected before comparison and spans every category.
The 3,140 requests contain 3,121 distinct user positions. Of the observations,
3,065 lie off the common dyadic training grid, including all 2,048 independent
random triples. The remaining boundary/contact checks are not relabelled as
independent training-disjoint samples.
CoreText/standard-table advances differ by at most 0.014308618 FUnit; HarfBuzz
advances match original-source HarfBuzz exactly. HarfBuzz versus the unrounded
source tables differs by up to 0.50184 FUnit, an explicitly retained diagnostic:
the original engine already rounds HVAR advances. This is not reported as a
1/32-accurate reproduction of ideal unrounded advances by HarfBuzz.

The measured font is 166,353,412 bytes, with a maximum CFF2 operand stack of
60 and 2,977 global subroutines. Eight computational axes are hidden but still
exist in fvar and must remain at their defaults. Required shaping selects the
local outline; direct access to the unselected base GID is outside this scope.
The size is not acceptable evidence for full-font scalability. Public aggregate
counts, hashes and limitations are in the [factored receipt](evidence/SWIRL_VF_FACTORED_20261103.json);
fonts, coefficients, coordinates and raw records remain private.

An outward-rounded interval pass certifies that no emitted Type-0 factor
reaches 0 or 1 anywhere in either target's root cube (20/30 factors, zero
unresolved boxes). This is a clamp-coverage certificate, not a bound on final
font error. Independent new source-field checks for the 4,096-cell GID 19177
model reach 0.010775925 FUnit over 4,096 held-out positions; serialization and
native acceptance remain separate and pending at this checkpoint.

The first full continuation run executed **1,005 tests: 998 pass, seven skips**,
and all six parser audits pass. No remote CI result is inferred. The input
sampler predeclares fractional decimal coordinates with stable native transport;
the exact readback guard remains unchanged. Arbitrary binary64 transport and
continuous-space error bounds have not been certified. PR #53 remains Draft.

## Lossless polynomial operand sharing checkpoint

`cff2_expression_pool` interns complete operand expressions, including their
variation-region count, and calls them through CFF2 global subroutines. Helpers
contain neither `vsindex` nor calls; drawing chunks may call helpers, with at
most two additional call levels. The final subroutine count determines call
bias before any caller is encoded. Main strings and subroutines are bounded
to 65,535 bytes. No coefficients or samples are removed or refitted.

Three new unit tests cover serialized arithmetic identity, region-state
isolation, and oversized drawing chunks. The shared authored control repeats
all 155 positions in CoreText, HarfBuzz and fontTools with exactly the previous
maximum errors. Its font is 5,976 bytes, with 20 operand helpers.

For the private face-0 GID 1166 candidate, sharing reduces the file from
165,773,884 to **104,063,548 bytes**. It uses 2,048 polynomial boxes, 8,051
quantized avar2 regions, three physical and eight hidden computational axes.
Reloaded, shared encoding repeats 2,006 observations against retained validated
Apple libhvf transcripts at the identical requests:

| Engine | Observations | Maximum control error (FUnit) | Outline/topology/selection failures |
|---|---:|---:|---:|
| CoreText | 2,006 | 0.018987351765994864 | 0 |
| HarfBuzz | 2,006 | 0.020539522817323415 | 0 |
| fontTools | 59 | 0.007295238302643026 | 0 |

CoreText controls are identical to the unshared candidate (maximum change 0).
The 2,006 observations are **not 2,006 independent positions**: the earlier
grid/parameter-node audit counts 1,756 unique positions, of which 1,706 are
distinct from fitting/refinement nodes. Both native engines preserve contour
direction; maximum explicit closure gaps are 0.002081 FUnit or less. HarfBuzz
candidate advances equal original-source HarfBuzz advances at every request.
HarfBuzz rounds source advances to integral FUnits, so agreement with the
unrounded table evaluator is a separate metric and is not claimed.

The complete regression checkpoint has **1,005 tests: 998 passed, seven
platform skips**. Source fonts, coefficients, coordinates and native transcripts
remain private. Larger fresh acceptance sets and the GID 19177 native candidate
are still in progress; this checkpoint is not joint-task completion or proof
of full-font scalability. These large diagnostic fonts are not release assets.

## Sparse clamp maps and source-aware component partitions

`sparse_projection` fits the **unclamped** rational projection parameter with
hierarchical tensor hats. It takes mixed hierarchical differences using cached
parents; it does not solve a dense tensor system. For M ramps, the exact scalar
identity is `clamp(t,0,1) = sum(clip(2*M*t-(2*j+1),-1,1)+1)/(2*M)`.
The compiler quantizes avar2 deltas first, then removes only exact zero rows.
Physical output-axis deltas stay zero. Region coordinates, delta capacity,
training-node budget and hidden-axis counts have explicit format guards.

`adaptive_projection_atlas` fits baseline/direction fields, retaining source
axis-zero and Type-0 branches. Analytic branch intersections propose cut planes;
measured field bends choose among them. Midpoint cuts remain an explicit
reproduction option. Both modes test source branch intersections and nearby
positions in refinement, independently of held-out acceptance. Every source
evaluation used for fitting/refinement receives a location fingerprint, saved
with the private atlas and bound to source SHA/face/GID. Holdouts overlapping
these receipts or each other are rejected. No native result enters the fitter.

Nine authored regression tests cover sparse mixed-axis fields, OpenType scalar
agreement, clamp quantization, capacity failures, source-derived cut positions,
all octants, source identity and training/holdout separation. The source-aware
cut heuristic is still being evaluated on real glyphs; these tests do not
certify its resource cost or arbitrary-space precision on the complete font.
