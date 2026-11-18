# Observed curve bounds and native failure witnesses

This follows checkpoint `40f2fceef7aa7c5c1f636fe022c34d0ca9377c44` on PR #52.
The full-cube GID 1166 / 19177 reconstruction still fails the unchanged
1/32 FUnit requirement. No final font or universal CFF2 impossibility is claimed.

## Distinguish native path representation from geometric failure

The new `bezier_path_certificate` diagnostic preserves every curve and contour.
It searches an orientation-preserving monotone correspondence: paired cubics
use the maximum exact squared distance between Bernstein controls; an extra
curve is paired with a stationary endpoint and bounded over its entire length.
Convexity proves the bound between samples on the curve. Exact rational degree
elevation handles lines, and reported upper bounds round outward. There is no
flattening, threshold increase, endpoint snapping or removal of nonzero curves.

All **264** retained source Qt topology failures receive curve-distance bounds
below 0.03125. Maxima for GIDs 1166 / 19177 / 0 / 12 are respectively
0.008387563 / 0.010992068 / 0.009540072 / 0.011991431 FUnit. The blank GID 2
already passes the original gate. The original strict failures remain failures;
the new diagnostic cannot override them or accept a source font. These are
bounds on the supplied finite native observations, not every axis coordinate.

## The global interpolation error is real geometry

A separate experiment re-executes Apple libhvf at the retained worst grid cell:
eight corners plus the independent query, for **18** native extractions across
the two GIDs. It degree-elevates returned quadratics exactly and constructs the
65 x 65 x 33 grid's nodal interpolant using rational weights. A native source
curve point is then compared against **all** interpolated target curves.

`point_separation` recursively subdivides exact cubic controls. Convex-hull
bounding boxes give lower bounds on the query's distance to the whole target.
The native source point is provably more than **0.032385194 FUnit** from the
GID 1166 interpolant and **0.047058911 FUnit** from the GID 19177 interpolant.
Both exceed 0.03125. This rules out explaining these retained failures solely
as parameterization differences, serializer rounding or portable-HVF mismatch.
It does not rule out another grid, another fit or another legal representation.
No font was serialized for this deliberately unaccepted nodal experiment.

## Reproduction and checkpoint

```sh
python -m unittest discover -s tools/swirl_vf/tests -v
python tools/swirl_vf/platform/diagnose_qt_path_bounds.py \
  --inputs "$PRIVATE_QT_1166" "$PRIVATE_QT_19177" "$PRIVATE_QT_0" \
           "$PRIVATE_QT_2" "$PRIVATE_QT_12" \
  --private-output "$NEW_PRIVATE_BOUND_REPORT"
```

The final Python run executes 1,018 tests: 1,011 pass, seven platform skips,
zero failures. The 11 new unit checks include interior-curve excursions, true Euclidean
threshold boundaries, contour/orientation changes, nonzero closing edges,
resource exhaustion, forged native identity and inconsistent counts.
The actual private experiment and executable restart script are retained at
`three-axis-20261103/native_curve_witness.py`; its input hashes, native-oracle
hash and 18 transcripts are bound by the
[aggregate receipt](evidence/SWIRL_VF_PATH_BOUNDS_20261103.json). Source outlines,
coordinates and coefficients remain outside Git.

Qt Windows [run 41519477788](https://github.com/SOLHK/Swirl/actions/runs/41519477788)
tests head `40f2fceef7aa7c5c1f636fe022c34d0ca9377c44`, merge
`9cba41358f6b61971067bfdcbf047d00f94e9ba8`: 546 authored observations pass,
maximum 0.001171960 FUnit, Qt 6.12.0 / Windows Server 2022 x64. This is separate
from private source acceptance and physical Windows 11 x64 validation.

The unresolved work is still full-cube fitting under ordinary CFF2 capacity,
verified complete-font selection, source metrics/layout and Windows source-font
acceptance. The 512-box atlas remains unaccepted; increasing its coverage must
also respect the global region and glyph limits. Nested blends remain excluded
from production because the retained DirectWrite failures are real.
