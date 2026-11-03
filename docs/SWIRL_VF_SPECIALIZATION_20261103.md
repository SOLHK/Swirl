# SwirlVF: bounded specialization and source-field costs

This checkpoint preserves the rational-projection/local-tricubic algorithm and
its 0.03125 FUnit limit. [Aggregate receipt](evidence/SWIRL_VF_SPECIALIZATION_20261103.json)
contains measurements, hashes and failure counts; source geometry stays private.
It does not establish original physical-user-axis equivalence or full-font acceptance.

## Exact sparse projection directions

A Type-2 on-curve displacement affects two elevated cubic controls, one endpoint,
and sometimes the contour move. `projection_factorization.py` now writes only
these absolute fields and their adjacent differences. It preserves subtraction
order (in particular, `delta - delta/3` is not replaced by `2*delta/3`). This removes
whole-glyph zero-outline allocation and degree elevation for every factor.

Separate processes measured 16,384 fixed-seed positions per implementation:

| GID | Factors | Dense seconds | Sparse seconds | Dense peak RSS bytes | Sparse peak RSS bytes |
|---|---:|---:|---:|---:|---:|
| 1166 | 2 | 0.901795 | 0.817811 | 178995200 | 182435840 |
| 19177 | 4 | 3.298331 | 2.504337 | 235569152 | 228687872 |
| 35709 | 12 | 12.551210 | 7.226201 | 505839616 | 441516032 |

All field and parameter bytes match the retained implementation at commit
`8c156168570fff9cbdd66d96853c53dd3e59cfc0`. A synthetic test covers every point
including adjacent factors and transitions between contours. Measurements are
single runs on a concurrently used host; the small RSS increase on GID 1166 is
retained. This is not a claimed end-to-end compiler speed distribution.
`benchmark_projection_directions.py` extracts an explicit Git reference into a
private directory and reproduces the isolated-process comparison.

## Optional ordinary-CFF2 specialization

`flat_joint_font.py` accepts only complete eight-octant, zero-projection-factor
atlases. It constructs a 27-node multilinear field, quantizes ordinary CFF2
coefficients to 16.16, and bounds its change from the retained tricubic field
throughout every cell. Outward-rounded interval Bernstein coefficients bound
absolute control-point L1 distance, hence Euclidean distance. The separate
representation budget is 1/1024 FUnit. This is a representation-change bound,
not a whole-source interpolation certificate. Existing models remain the default.

GID 50 qualifies: 5,316 -> **3,208 bytes**, 11 -> **3 GIDs**, six nonzero variation
regions, maximum stack 13, build 0.189082 seconds. All 9,506 before/after HarfBuzz
outlines and advances are exactly equal. Fresh CoreText/HarfBuzz geometry maxima
are 0.010553075173 / 0.008157006903 FUnit. Its pre-existing source advance mismatch
remains: 3,162 HarfBuzz observations fail, maximum 15 FUnits. It is **not** a newly
accepted glyph. GID 0 is rejected by the bound (0.090113321940 > 1/1024) and keeps
its accepted local model. No controls, failures or precision requirements are removed.

This path removes GSUB selection for eligible glyphs. Its full-font eligibility
fraction has not been measured. The earlier eight-patches-per-nonempty-glyph
capacity calculation is conditional on the local-patch architecture; it does
not apply to glyphs successfully specialized this way. It remains an unresolved
capacity issue for the unspecialized population. No original-source Windows
acceptance is claimed.

## Reuse across byte-identical HVF geometry tables

`reuse_projection_face.py` checks the source hash, GID, three-axis order, and
exact hvgl/hvpm table bytes and presence before reusing q-space fields. It retains
all training fingerprints, executes new independent component and parameter
holdouts, and binds new archives to the target face. Each face keeps its own
axis profile and metrics and must pass a fresh native test.

Face 0 -> face 31, GID 19177 reused 4,096 cells with **zero refit samples** in
20.570556 seconds. The new 4,096-point component and parameter holdouts pass.
A newly serialized target-face font passes **7,472** observations per native
engine: CoreText 0.021873662405, HarfBuzz 0.015834344182, fontTools 256 observations
0.012417686045 FUnit. This is one additional face/GID case, not an additional
unique GID or proof about all 32 faces' physical-axis behavior.

The public benchmark driver was also executed on GID 35709: 18.477398 ->
10.890170 seconds, peak RSS 488,931,328 -> 394,117,120 bytes, with the same exact
field and parameter hashes. Both runs are retained because host contention
changes elapsed time. The checkpoint runs 1,058 regressions: 1,051 pass and seven
platform skips; all six parser audits pass.
