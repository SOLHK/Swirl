"""Windows baseline: three-axis tensor interpolation -> integer glyf/gvar.

Independent tensor finite differences preserve mixed-axis interactions. The
OpenType support and binary writers are fontTools public APIs. This is a
bounded candidate compiler, not an HVF or whole-design-space acceptance gate.
"""
from __future__ import annotations

import array
from itertools import product
import math

import numpy as np
from fontTools.misc.roundTools import otRound
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables.ttProgram import Program
from fontTools.varLib.iup import iup_delta
from fontTools.varLib.models import supportScalar

TAGS = ('wdth', 'wght', 'HGHT')
LIMIT = 1 / 32


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


class TensorModel:
    """Anchored tensor hats: base + single + double + triple differences.

    At each axis, nonzero knots have cardinal hats that vanish at zero. The
    zero-knot hat equals 1 minus their sum. Substituting that identity in the
    nodal tensor interpolant gives mixed differences against the zero planes.
    Unlike a sum of three axis slices, this reproduces every grid vertex and
    all trilinear interactions. No inversion or O(N**2) support fit is needed.
    """
    def __init__(self, knots):
        grids = [knots]*3 if np.ndim(knots[0]) == 0 else knots
        require(len(grids) == 3, 'three_axis_grids_required')
        self.knots = tuple(np.asarray(k, dtype=float) for k in grids)
        for k in self.knots:
            require(k.ndim == 1 and 3 <= len(k) <= 65 and k[0] == -1 and k[-1] == 1
                and np.isfinite(k).all() and np.all(np.diff(k) > 0)
                and np.count_nonzero(k == 0) == 1 and np.all(k*16384 == np.round(k*16384)),
                'ordered_F2DOT14_grid_with_zero_and_endpoints_required')
        self.zero = tuple(int(np.where(k == 0)[0][0]) for k in self.knots)
        self.indices = list(product(*(range(len(k)) for k in self.knots)))
        self.locations = np.asarray([tuple(k[i] for k, i in zip(self.knots, ix)) for ix in self.indices])
        self.supports = []
        for ix in self.indices:
            support = {}
            for tag, k, z, i in zip(TAGS, self.knots, self.zero, ix):
                if i != z:
                    support[tag] = (float(k[max(0, i-1)]), float(k[i]), float(k[min(len(k)-1, i+1)]))
            self.supports.append(support)

    def coefficients(self, values):
        v = np.asarray(values, dtype=float)
        require(v.ndim >= 2 and v.shape[0] == len(self.indices) and np.isfinite(v).all(),
                'finite_grid_values_required')
        result = v.reshape(tuple(map(len, self.knots)) + v.shape[1:]).copy()
        for axis in range(3):
            anchor = np.take(result, self.zero[axis], axis=axis).copy()
            result -= np.expand_dims(anchor, axis)
            selection = [slice(None)]*result.ndim
            selection[axis] = self.zero[axis]
            result[tuple(selection)] = anchor
        return result.reshape(v.shape)

    def evaluate(self, coefficients, locations):
        points = np.asarray(locations, dtype=float)
        c = np.asarray(coefficients, dtype=float)
        require(points.ndim == 2 and points.shape[1] == 3 and np.isfinite(points).all()
                and np.all(np.abs(points) <= 1) and c.shape[0] == len(self.supports),
                'invalid_tensor_evaluation')
        weights = np.asarray([[supportScalar(dict(zip(TAGS, p)), s) for s in self.supports] for p in points])
        return np.tensordot(weights, c, axes=(1, 0))


def compile_glyph(model, values, flags, ends, *, optimize=True):
    """values include four explicit phantom points, already in target units.

    Quantize vertices ONCE, then take integer anchored differences. This keeps
    the encoded surface equal to interpolation of quantized masters: no sum
    of separately rounded high-dimensional residuals is introduced. IUP is
    admitted only after exact coefficient reconstruction, at tolerance zero.
    """
    values = np.asarray(values, dtype=float)
    require(values.shape == (len(model.indices), len(flags)+4, 2)
            and np.isfinite(values).all(), 'invalid_glyph_tensor_values')
    require((not flags and not ends) or (ends and ends[-1] == len(flags)-1
            and all(a < b for a, b in zip([-1]+list(ends), ends))), 'invalid_contour_endpoints')
    integer_vertices = np.floor(values + .5)
    integer = model.coefficients(integer_vertices)
    default = model.indices.index(model.zero)
    base = integer[default]
    require(np.all(base[:-4] >= -32768) and np.all(base[:-4] <= 32767), 'glyf_coordinate_overflow')
    glyph = Glyph()
    glyph.numberOfContours = len(ends)
    glyph.coordinates = GlyphCoordinates(base[:-4].tolist())
    glyph.flags = array.array('B', flags)
    if flags:
        glyph.flags[0] |= 0x40
    glyph.endPtsOfContours = list(ends)
    glyph.program = Program()
    glyph.program.fromBytecode([])
    glyph.recalcBounds(None)
    tuples, inferred, rejected_iup = [], 0, 0
    for support, delta in zip(model.supports, integer):
        if not support or not np.any(delta):
            continue
        require(np.all(delta >= -32768) and np.all(delta <= 32767), 'gvar_delta_overflow')
        points = [(int(x), int(y)) for x, y in delta]
        variation = TupleVariation(support, points)
        if optimize and flags:
            candidate = TupleVariation(support, points.copy())
            candidate.optimize(GlyphCoordinates(base.tolist()), list(ends), tolerance=0.0)
            reconstructed = iup_delta(candidate.coordinates, base.tolist(), list(ends))
            if np.array_equal(np.asarray(reconstructed), delta):
                variation = candidate
                inferred += sum(p is None for p in variation.coordinates)
            else:
                rejected_iup += 1
        tuples.append(variation)
    require(len(tuples) <= 4095, 'gvar_tuple_count_exceeds_4095')
    # Worst case without shared peaks: tuple header + peak + intermediate ends.
    # Actual compiler may share peaks; never rely on that to exceed Offset16.
    require(4 + len(tuples)*(4 + 6*len(TAGS)) <= 65535, 'gvar_header_Offset16_capacity')
    require(base[-4, 0] == 0 and np.all(integer[:, -4, 0] == 0), 'zero_horizontal_origin_required')
    horizontal = (int(base[-3, 0]-base[-4, 0]), int(getattr(glyph, 'xMin', 0)-base[-4, 0]))
    vertical = (int(base[-2, 1]-base[-1, 1]), int(base[-2, 1]-getattr(glyph, 'yMax', 0)))
    require(all(0 <= v[0] <= 65535 and -32768 <= v[1] <= 32767 for v in (horizontal, vertical)),
            'metric_storage_overflow')
    report = dict(grid_vertices=len(values), tuples=len(tuples),
                  tuple_dimensions={str(n): sum(len(t.axes) == n for t in tuples) for n in (1, 2, 3)},
                  inferred_points=inferred, rejected_inexact_iup=rejected_iup,
                  max_vertex_rounding=float(np.linalg.norm(integer_vertices-values, axis=-1).max()),
                  production_accepted=False)
    return glyph, tuples, horizontal, vertical, integer, report


def observed_errors(predicted, reference):
    """Point discrepancy bounds matching quadratic curves by convexity."""
    delta = np.asarray(predicted)-np.asarray(reference)
    require(delta.ndim == 3 and delta.shape[-1] == 2 and delta.shape[1] >= 4, 'invalid_comparison')
    return dict(max_outline_control_bound=float(np.linalg.norm(delta[:, :-4], axis=-1).max(initial=0)),
                max_advance_width_error=float(np.abs(delta[:, -3, 0]-delta[:, -4, 0]).max(initial=0)),
                max_advance_height_error=float(np.abs(delta[:, -2, 1]-delta[:, -1, 1]).max(initial=0)),
                max_phantom_error=float(np.abs(delta[:, -4:]).max(initial=0)))
