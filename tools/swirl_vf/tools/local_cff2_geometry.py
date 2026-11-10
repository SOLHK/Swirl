"""Ordinary CFF2 interpolation restricted to a declared design-space box.

Unlike a global VariationModel, a local box need not contain the default. Its
nodal basis is rebased to the node nearest zero on each axis. That node has the
constant basis function; all other basis functions are legal OpenType tents.
Tensor differences supply the exact coefficients, without fitted inverses or
nested blends. The caller must arrange and verify native selection of the box.
An accurate local model alone is NOT a usable three-axis font.
"""
from __future__ import annotations
import itertools
import numpy as np
from cff2_geometry import OutlineModel, require

GRID = 16384


def validate_knots(knots):
    require(len(knots) == 3, 'three_local_axes_required')
    result = [np.asarray(k, dtype=float).copy() for k in knots]
    for k in result:
        require(k.ndim == 1 and 2 <= len(k) <= 128 and np.isfinite(k).all()
                and (np.abs(k) <= 1).all() and (np.diff(k) > 0).all()
                and np.equal(k*GRID, np.round(k*GRID)).all(), 'invalid_local_F2DOT14_knots')
        require(not (k[0] < 0 < k[-1]) or 0 in k, 'local_zero_crossing_requires_zero_knot')
    return result


def interpolate(knots, values, points):
    """Unquantized nodal interpolation; reject extrapolation explicitly."""
    axes = validate_knots(knots)
    p = np.asarray(points, dtype=float)
    v = np.asarray(values, dtype=float)
    require(p.ndim == 2 and p.shape[1] == 3 and np.isfinite(p).all(), 'invalid_local_points')
    require(v.ndim == 4 and v.shape[:3] == tuple(map(len, axes)) and np.isfinite(v).all(),
            'invalid_local_nodal_values')
    require(all(((p[:, a] >= k[0]) & (p[:, a] <= k[-1])).all()
                for a, k in enumerate(axes)), 'local_model_extrapolation')
    index = [np.minimum(np.searchsorted(k, p[:, a], side='right')-1, len(k)-2)
             for a, k in enumerate(axes)]
    fraction = [(p[:, a]-k[i])/(k[i+1]-k[i]) for a, (k, i) in enumerate(zip(axes, index))]
    result = np.zeros((len(p), v.shape[-1]))
    for corner in itertools.product((0, 1), repeat=3):
        weight = np.prod([f if bit else 1-f for f, bit in zip(fraction, corner)], axis=0)
        result += weight[:, None]*v[tuple(i+bit for i, bit in zip(index, corner))]
    return result


def encode(knots, values, operators, axis_tags, *, basis='tent', absolute_values=None):
    """Encode every coefficient, then remove only exactly encoded zero rows.

    With independently retained absolute nodes, quantize absolute control
    coefficients once and difference their integer ticks. Equal source control
    columns then remain equal for EVERY encoded region, including explicit
    closing endpoints. Rounding relative coefficients separately loses this
    invariant and accumulates error along long contours. The supplied absolute
    nodes must reproduce the relative input exactly; they are not a repair of
    the source observations. Omitting them retains the historical encoding.

    Coefficient quantization happens once, to signed 16.16. Sample validation,
    disk/native verification and selection coverage are deliberately not
    inferred from this algebraic conversion.
    """
    axes = validate_knots(knots)
    require(basis in ('tent', 'ramp', 'hierarchical'), 'unknown_local_basis')
    tags = tuple(axis_tags)
    require(len(tags) == 3 and len(set(tags)) == 3 and all(
        isinstance(t, str) and len(t) == 4 for t in tags), 'invalid_local_axis_tags')
    v = np.asarray(values, dtype=float)
    require(v.shape == (*map(len, axes), sum(n for _, n in operators))
            and np.isfinite(v).all(), 'invalid_local_encoding_values')
    anchors = [int(np.argmin(np.abs(k))) for k in axes]
    coefficient = v.copy()
    if absolute_values is not None:
        absolute = np.asarray(absolute_values, dtype=float)
        require(v.shape[-1] % 2 == 0 and
                absolute.shape == (*v.shape[:3], v.shape[-1]//2, 2) and
                np.isfinite(absolute).all(), 'invalid_absolute_encoding_values')
        relative = np.diff(absolute, axis=-2,
                           prepend=np.zeros((*v.shape[:3], 1, 2))).reshape(v.shape)
        require(np.array_equal(relative, v), 'absolute_relative_node_mismatch')
        coefficient = absolute.reshape(v.shape).copy()
    hierarchical_supports = []
    for a, anchor in enumerate(anchors):
        # The matrix at nodes has a column of ones and one unit column for
        # every non-anchor node. Its inverse subtracts the anchor row.
        if basis == 'tent':
            base = np.take(coefficient, [anchor], axis=a).copy()
            coefficient -= base
            slices = [slice(None)]*4; slices[a] = slice(anchor, anchor+1)
            coefficient[tuple(slices)] = base
        elif basis == 'ramp':
            # A truncated-power basis: second divided differences annihilate
            # affine spans exactly in real arithmetic. Unlike a fitted sparse
            # approximation, this transforms the SAME nodal interpolant.
            rows = np.moveaxis(coefficient, a, 0)
            slopes = np.diff(rows, axis=0)/np.diff(axes[a])[:, None, None, None]
            changed = np.empty_like(rows); changed[anchor] = rows[anchor]
            for i in range(anchor+1, len(rows)):
                slope = slopes[i-1] if i == anchor+1 else slopes[i-1]-slopes[i-2]
                changed[i] = slope*(axes[a][-1]-axes[a][i-1])
            for i in range(anchor-1, -1, -1):
                slope = -slopes[i] if i == anchor-1 else slopes[i+1]-slopes[i]
                changed[i] = slope*(axes[a][i+1]-axes[a][0])
            coefficient = np.moveaxis(changed, 0, a)
        else:
            # Dyadic-by-index hierarchical tents also handle nonuniform F2
            # knots. Each surplus is measured against its two ancestors,
            # instead of subtracting nearly cancelling large ramp slopes.
            rows = np.moveaxis(coefficient, a, 0)
            changed = np.empty_like(rows); changed[anchor] = rows[anchor]
            supports = {}
            k = axes[a]
            def interval(lo,hi):
                if hi-lo <= 1:
                    return
                mid = (lo+hi)//2; fraction = (k[mid]-k[lo])/(k[hi]-k[lo])
                changed[mid] = rows[mid]-((1-fraction)*rows[lo]+fraction*rows[hi])
                supports[mid] = (k[lo],k[mid],k[hi])
                interval(lo,mid); interval(mid,hi)
            if anchor:
                changed[0] = rows[0]-rows[anchor]
                supports[0] = (k[0],k[0],k[anchor]); interval(0,anchor)
            if anchor < len(rows)-1:
                changed[-1] = rows[-1]-rows[anchor]
                supports[len(rows)-1] = (k[anchor],k[-1],k[-1]); interval(anchor,len(rows)-1)
            hierarchical_supports.append(supports)
            coefficient = np.moveaxis(changed, 0, a)
    # Match otRound/fixed exactly, without materializing Python objects for
    # every operand of a mostly zero tensor. The input checks above do not
    # imply finite transformed coefficients (e.g. extreme divided slopes).
    require(np.isfinite(coefficient).all(), 'nonfinite_cff2_coefficient')
    with np.errstate(over='ignore'):
        ticks = np.floor(coefficient*65536+.5)
    if absolute_values is not None:
        # A double represents these integers and their differences exactly.
        # Check before casting, including nonfinite products from huge input.
        require((np.abs(ticks) < 2**51).all(), 'absolute_coefficient_tick_overflow')
        pairs = ticks.astype(np.int64).reshape(*v.shape[:3], v.shape[-1]//2, 2)
        ticks = np.diff(pairs, axis=-2,
                        prepend=np.zeros((*v.shape[:3], 1, 2), dtype=np.int64)).reshape(v.shape)
    encoded = ticks/65536
    require(((encoded >= -32768) & (encoded < 32768)).all(),
            'cff2_fixed_coefficient_overflow')
    flat = encoded.reshape(int(np.prod(encoded.shape[:3])), encoded.shape[-1])
    anchor_index = np.ravel_multi_index(tuple(anchors), encoded.shape[:3])
    keep = np.flatnonzero(np.any(flat != 0, axis=1)).tolist()
    if anchor_index in keep:
        keep.remove(anchor_index)
    keep.insert(0, int(anchor_index))
    supports = []
    for flat_index in keep:
        index = np.unravel_index(flat_index, encoded.shape[:3])
        support = {}
        for a, i in enumerate(index):
            if i == anchors[a]:
                continue
            k = axes[a]
            if basis == 'tent':
                triple = (k[max(i-1, 0)], k[i], k[min(i+1, len(k)-1)])
            elif basis == 'hierarchical':
                triple = hierarchical_supports[a][i]
            elif i > anchors[a]:
                triple = (k[i-1], k[-1], k[-1])
            else:
                triple = (k[0], k[0], k[i+1])
            support[tags[a]] = tuple(map(float, triple))
        supports.append(support)
    evidence = dict(domain_kind='local_box_only', basis=basis,
        coefficient_quantization=('absolute_then_exact_relative' if absolute_values is not None
                                  else 'relative_legacy'),
        box=[[float(k[0]), float(k[-1])] for k in axes],
        knots=[k.tolist() for k in axes], sampled_geometry_passed=False,
        production_accepted=False, serialized_verification='NOT_RUN',
        native_verification='NOT_RUN', box_selection='NOT_IMPLEMENTED',
        lossless_compaction=dict(input_regions=len(flat)-1, output_regions=len(keep)-1))
    return OutlineModel(tags, tuple(operators), supports, flat[keep].copy(), evidence)
