# Three-axis branch investigation — 2026-11-03

**Partial completion. Neither GID 1166 nor GID 19177 has an accepted joint
OpenType reconstruction. The limit remains 1/32 FUnit.** This checkpoint
implements simultaneous-axis branch extraction and mathematical failure
witnesses, and tests alternative encodings. It does not fix the source fit to
acceptance, install a failed model, or certify a complete font.

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
