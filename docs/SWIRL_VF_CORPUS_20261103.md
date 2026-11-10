# SwirlVF representative corpus and measured scaling costs

The preselected corpus has **14 face/GID cases, 12 unique GIDs**. All cases
have completed their prescribed pipeline or stopped at a recorded failure.
**Nine cases, eight unique GIDs pass the joint post-avar q-space geometry and
reported-metrics contract; six unique GIDs are new beyond the two anchors.**
Five cases fail. None is removed from the denominator. This is not original
physical-user-axis equivalence, complete font coverage, or production acceptance.

[Corpus receipts](evidence/SWIRL_VF_CORPUS_20261103.json),
[stage resource ledger](evidence/SWIRL_VF_CORPUS_RESOURCES_20261103.json),
[serialized table profiles](evidence/SWIRL_VF_CORPUS_PROFILES_20261103.json), and
[field diagnostics](evidence/SWIRL_VF_CORPUS_FIELD_DIAGNOSTICS_20261103.json)
contain only aggregate evidence and hashes. Source fonts, outlines, polynomial
coefficients, coordinates and native transcripts remain private.

## Selection precedes fitting

`select_joint_corpus.py`, seed 2026110607, scans all 47,102 face-0 roots:
47,097 are nonempty three-axis roots and five are empty. It chooses structural
extremes, a middle-complexity case, width/height extremes, both anchors, and
the strongest measured three-way interaction in a 75-glyph probe pool
(structural candidates plus 64 seeded choices). That interaction ranking is
**not** a whole-font nonlinear ranking. A second face from the opposite end
of the collection is selected before acceptance.

The full structural inventory has curve count min/median/p95/max
4/97/160/452; contour count 1/15/26/72; Type-2 factor count 0/0/4/12;
and graph depth 2/7/9/12. All 32 faces have identical hvgl geometry bytes and
no hvpm table in this input; their axis profiles and metrics still require
separate validation. Geometry identity alone is not a face-acceptance result.

| Face | GID | Selection coverage | Final cells | Default compressed bytes | Result |
| ---: | ---: | --- | ---: | ---: | --- |
| 0 | 1166 | Retained anchor, clamp/projection | 2048 | 32,200,320 | PASS_JOINT_Q |
| 0 | 19177 | Retained anchor, clamp/projection | 4096 | 89,678,604 | PASS_JOINT_Q |
| 0 | 50 | Minimum curve count, one contour | 8 | 5,316 | FAIL: HB advance |
| 0 | 46459 | Maximum curves/contours: 452/72 | 1221 | 68,870,804 | PASS_JOINT_Q |
| 0 | 30592 | Next contour extreme: 380 curves/64 contours | 50 | 975,332 | PASS_JOINT_Q |
| 0 | 35709 | Maximum Type-2 factors: 12 | 2048 | Not built | FAIL: fields |
| 0 | 46461 | Maximum Type-0 nodes: 144 | 2048 | Not built | FAIL: fields |
| 0 | 4985 | Maximum graph depth: 12 | 3072 | 86,553,280 | PASS_JOINT_Q |
| 0 | 117 | Minimum advance / height extreme | 8 | 7,616 | FAIL: HB advance |
| 0 | 0 | Maximum advance, four contours | 8 | 29,896 | PASS_JOINT_Q |
| 0 | 39285 | Middle complexity, two projections | 4608 | 87,520,336 | PASS_JOINT_Q |
| 0 | 39903 | Strongest three-way interaction in probe pool | 2048 | 20,575,616 | PASS_JOINT_Q |
| 31 | 50 | Second-face simple extreme | 8 | 5,312 | FAIL: HB advance |
| 31 | 19177 | Second-face clamp extreme | 4096 | 89,678,600 | PASS_JOINT_Q |

The table uses the default 215-helper encoding actually used by this corpus.
The two anchors additionally have the independently tested optional
[extended dictionary](SWIRL_VF_EXTENDED_DICTIONARY_20261103.md); its receipts
and smaller font hashes are kept separately. No size from an untested encoding
is substituted for a corpus observation.

## New real-glyph native results

Every new case uses 4,096 seeded random triples independent of fitting,
single/dual-axis samples, boundaries, source branch and clamp contacts,
patch seams and fractional physical requests. Repeated or training-overlapping
requests are still tested but excluded from independent counts. Native paths
are compared against fresh Apple libhvf source observations after serialization
and reload, including topology, control points, direction, closure, selection
and advances. fontTools uses 256 requests per case and its own consistent
serialized GSUB selection. All errors below are original FUnits; limit 0.03125.

| New face-0 GID | CT/HB observations each | CoreText maximum | HarfBuzz maximum | fontTools maximum |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 4735 | 0.014690008731 | 0.009527608981 | 0.000119563642 |
| 30592 | 5491 | 0.011216386232 | 0.009519824745 | 0.002950185266 |
| 39903 | 5757 | 0.015686234512 | 0.012339432996 | 0.007352788493 |
| 46459 | 6939 | 0.014198547477 | 0.012293253980 | 0.006366228569 |
| 39285 | 6667 | 0.027797183407 | 0.026796384298 | 0.023246460707 |
| 4985 | 6873 | 0.026157605213 | 0.025796744194 | 0.025533352298 |

Face 31 GID 19177 separately passes 7,472 CT/HB observations:
0.021873662405 / 0.015834344183, and fontTools 0.012417686045. Source-identity
checked model reuse takes 20.570556 seconds, then new target-face serialization
and native tests run. This is an extra face case, not a ninth unique GID.

Two general fixes were necessary. The source-branch admission gate now covers
every cell eligible at the final error threshold, rather than only cells below
twice the stricter internal budget. GID 39285 needed 4,608 cells; GID 4985's
old 2,048-cell holdout failed at 0.04350154325, whereas the corrected 3,072-cell
model's new 4,096 holdouts pass at 0.024814213716. No failing holdout coordinate
was supplied to fitting. Its parameter holdout reaches 0.012689543855; only
the combined native test establishes final success, not adding or ignoring
separate component maxima. The GID 46459 verifier fix uses consistent
fontTools coordinates for both serialized selection and drawing, replaying all
6,939 original requests including the five old seam failures. Neither fix
raises the threshold or deletes old failures. See
[branch/cache evidence](SWIRL_VF_BRANCH_AND_CACHE_20261103.md).

## Retained failures and their causes

GID 50 face 0, GID 117 face 0 and GID 50 face 31 pass sampled outline geometry
but have respectively 1,594 / 1,510 / 880 HarfBuzz advance failures, maxima
15 / 23 / 10 FUnits. The raw source weight map has conflicting duplicate
records; dictionary serialization loses that distinction and lacks a required
identity endpoint. Blind raw-map copying does not repair both native geometry
and metrics. The axis-contract qualification in the
[main scaling report](SWIRL_VF_SCALING_20261103.md) remains unresolved.

GID 35709's 2,048-cell field holdout fails 1,113/4,096 points, maximum
0.187777772053. GID 46461 fails 179/4,096, maximum 0.075976751980, despite
1,328 source-branch cuts. Fresh diagnostic seeds still measure
0.163837308918 / 0.067930048397, with 20 / 25 descendant axis-zero events
along chords through the respective worst retained cells. GID 46461's
baseline dominates; both projection-direction field errors are below 0.000019.
These failures precede avar2, CFF2 and compression. A larger local dictionary
cannot fix them. The floating cubic-slice witnesses, 0.017342756643 and
0.008916356498, are below 1/32 and **do not prove format or repartitioning
impossibility**. No native font is claimed for either failed model.

## Resource distribution and batch accounting

Each compiler/native stage runs in an isolated process. macOS `time -l`
measures process wall time and maximum RSS; internal timers separate source
initialization, field fitting/holdouts, source evaluation, parameter fitting,
encoding and saving. Source evaluation time is a subset of fitting time,
not an additional phase to sum. The ledger retains failed attempts and resumed
fits; reused stages are not charged twice. OS cache and concurrent host work
are uncontrolled. Some expensive fits preceded later exact cache optimizations.

| New accepted GID | Recorded compilation seconds, including failed fits/resumes | Maximum compiler RSS bytes |
| ---: | ---: | ---: |
| 0 | 1.226 | 195,624,960 |
| 30592 | 64.525 | 410,124,288 |
| 39903 | 1,200.849 | 1,293,058,048 |
| 4985 | 4,024.773 | 3,228,893,184 |
| 46459 | 4,043.426 | 2,601,795,584 |
| 39285 | 4,159.381 | 3,752,280,064 |

The six accepted new GIDs consume a measured sum of 13,494.180 compiler-stage
seconds, including unsuccessful precursor fits. This is an experiment ledger,
not six cold builds using one identical software revision. All listed corpus
attempts sum to 20,883.003 compiler-stage seconds (5.80 hours) and 26,799.942
seconds including recorded native rechecks (7.44 hours); inherited anchor model
construction and separate exploratory profiling are excluded. Parallel jobs
overlap, so neither sum is elapsed session time or a serial-runtime prediction.

Complexity is not monotonic in contour count: the 380-curve GID 30592 uses
50 cells and under 1 MB, while the 97-curve GID 39285 needs 4,608 cells and
87.5 MB. Branch structure and local polynomial complexity dominate. The
selected extremes, failed cases and differing optimization checkpoints cannot
yield a defensible population-average full-font time or size. Extrapolating
two anchors or these six survivors across 47,097 glyphs would be misleading.
Moreover the current patch-per-glyph scheme already exceeds the uint16 glyph
capacity under its minimum-eight-cell assumption. A full-font cost estimate
requires a new capacity-valid representation and a newly measured corpus.

## Reproduction and remaining integration limits

The source-bound tools are `select_joint_corpus.py`, `run_joint_corpus.py`,
`summarize_joint_corpus.py`, `profile_joint_font.py`, `benchmark_joint_font.py`
and `diagnose_projection_fields.py` under `tools/swirl_vf/platform`.
For example, with the authorized source and Apple oracle available locally:

```sh
python tools/swirl_vf/platform/select_joint_corpus.py \
  --source "$SWIRL_SOURCE_FONT" --source-sha256 "$SWIRL_SOURCE_SHA256" \
  --private-output "$SWIRL_PRIVATE_OUT/selection" --seed 2026110607
python tools/swirl_vf/platform/run_joint_corpus.py \
  --source "$SWIRL_SOURCE_FONT" --source-sha256 "$SWIRL_SOURCE_SHA256" \
  --selection "$SWIRL_PRIVATE_OUT/selection/selection.json" \
  --hvf-oracle "$SWIRL_HVF_ORACLE" --case 0:30592 \
  --private-output "$SWIRL_PRIVATE_OUT/case30592"
```

This short example runs one preselected case, not the full corpus. The summary
tool leaves unrun selected cases in its denominator. Source-bound successful
archives can be supplied with `--fields-directory` / `--parameters-directory`;
fit resumption separately retains prior training fingerprints and fresh holdouts.

The local delivery regression runs 1,069 tests: 1,062 pass and seven platform
skips; six parser audits pass. Actual Windows research controls retain their
failures. [Compatibility evidence](SWIRL_VF_SCALING_COMPATIBILITY_20261103.md)
covers DirectWrite Server 2022/2025, exact table identity, hidden defaults,
direct GID access, and text subsetting. The fractional glyf control passes
those Windows servers but fails CoreText. Windows 11 client and original-source
Windows font acceptance remain NOT_RUN. The current corpus supports wider
applicability of the mathematical compiler; capacity, mapping, unresolved
branches and engine behavior still block a complete installed font. PR #53
remains Draft, with no main/test merge or full-font release.
