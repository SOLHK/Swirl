# SwirlVF: branch admission, source caching, and seam validation

[Aggregate evidence](evidence/SWIRL_VF_BRANCH_AND_CACHE_20261103.json) accompanies
this tested checkpoint. The threshold remains 0.03125 original FUnit. All native
results here concern post-avar q-space geometry and reported metrics, not original
physical-axis mapping parity or production-font acceptance.

## Fix a branch-probe admission gap

The fitter's internal refinement budget is 1/128 FUnit. A capped atlas may still
proceed to independent validation at the final 1/32 limit. Previously, source
branch probes ran only if ordinary grid/jitter error was at most twice the
internal budget (1/64). Thus some cells eligible for final acceptance skipped
their branch check. `adaptive_projection_atlas.py` now probes every cell whose
ordinary error is at most the final limit. An authored clamp test reproduces
this gap without source font data.

GID 39285's retained 4,096-cell model failed an independent field holdout at
0.046913204542. Existing branch probes on the failing cell measured
0.0538409371; analytic plane/box contacts measured 0.0569215925. No new acceptance
coordinates were supplied to fitting. The corrected gate reassessed all old
cells, retained their training fingerprints, and refined to 4,608 cells.
The same old 4,096 holdouts now measure 0.019925503544; a new independent seed
measures 0.023941762628. The new 6,667-position serialized test passes:

| Engine | Observations | Maximum FUnit error |
|---|---:|---:|
| CoreText | 6667 | 0.027797183406 |
| HarfBuzz | 6667 | 0.026796384297 |
| fontTools | 256 | 0.023246460706 |

Topology, control points, direction, closure, selection, and advances also pass.
The compressed candidate is 87,520,336 bytes versus 186,906,548 before structural
compression; the remaining size is still excessive for a broadly populated font.
`branch_surface_probes.py` is a diagnostic plane-contact tool, not a universal
branch-coverage certificate or a new fitter dependency.

## Use one coordinate semantics for fontTools selection and drawing

The 1,221-cell, zero-projection-factor GID 46459 font uses avar1. HarfBuzz's
quantized coordinates and fontTools' continuous coordinates can lie on opposite
sides of an F2DOT14 cell boundary. The old verifier used the HarfBuzz GID with
fontTools' different coordinate, a mixed execution neither engine performs.
Five fontTools seam observations failed, maximum 20.138045908281 FUnits. These
original receipts remain retained.

`joint_gsub_selection.py` reads the **serialized** rvrn FeatureVariations and
SingleSubst data with ordered closed-boundary semantics. The fontTools route
now uses the same fontTools-normalized location for selection and drawing.
Unsupported feature/condition/lookup dialects fail explicitly; this is a narrow
research-font selector, not a general fontTools shaping engine. The exact old
6,939 requests were freshly executed again, including all five seam failures:
CoreText 0.014198547476, HarfBuzz 0.012293253979, fontTools 256 observations
0.006366228568 FUnit; all checks pass. The font bytes are unchanged.

## Cache immutable rigid-transform constants

Profiling a 32-cell GID 46461 fit found repeated assembly of sparse transform
constants inside source evaluation. `compile_transform_rows` retains stored
addition and extreme-column order. `BatchGeometry` keeps at most 512 plans,
checks part identity, and bypasses the cache for writable source arrays. Plans
contain read-only constants and never sampled values. Rotation-centre and
fractional-weight formulas are unchanged.

With cProfile enabled on both executions, total fit-command time fell from
67.508816 to 47.951045 seconds; source evaluation from 36.734584 to 25.095863.
Every bounds/column/coefficient/training-fingerprint array is exactly equal.
Both small profiling models still fail the accuracy threshold: this comparison
is solely a computation-preservation/performance test. The 16,384-position
separate-process field-byte comparisons also match for GIDs 1166, 19177 and
46461. Large-batch GID 46461 throughput barely changed (9.108837 vs 9.106655
seconds), and RSS slightly increased (532,955,136 vs 535,035,904 bytes). Cache
benefit is concentrated in repeated small fit batches; these single runs on a
shared host do not establish a stable speed distribution.

## Remaining field failures have a separate cause

At 2,048 cells, GID 35709's original independent field holdout has 1,113/4,096
failures, maximum 0.187777772053. A new diagnostic seed still fails 1,066/4,096,
maximum 0.163837308918, predominantly in the baseline field. Twenty descendant
axis-zero crossings occur along chords through that sample's current cell.
GID 4985's separate diagnostic has 13/4,096 physical failures, maximum
0.040480470682, with baseline and one direction both contributing.

`diagnose_projection_fields.py` measures these failures **before** avar2/CFF2
encoding and computes floating five-point cubic witnesses. The observed local
witnesses (0.017342756643 / 0.002486829378) do not prove impossibility at the
1/32 target. They identify unresolved source branches inside the retained
partition and rule out compression as the origin of these field errors. No
claim is made that another partition, basis, or OpenType representation fails.
A bounded branch-gate reassessment of GID 4985 is recorded separately in the
corpus results; no unbounded refit loop is used for GID 35709.

This checkpoint runs 1,061 regressions: 1,054 pass and seven platform skips.
The corpus-summary privacy/denominator tests add three separate passes.
