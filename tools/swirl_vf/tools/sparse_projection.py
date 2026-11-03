"""Hierarchical three-axis parameter fields and quantized avar2 clamp ramps.

The basis is a tensor product of dyadic, piecewise-linear hat functions.
Hierarchical differences use only already sampled parents, so no dense linear
system or all-pairs fitting matrix is built. This approximates the *unclamped*
projection parameter; the font's avar2 output clamp supplies the branch.
Native geometry validation is a separate, mandatory acceptance step.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import numpy as np

from cff2_geometry import require


def axis_nodes(level):
    require(type(level) is int and 0 <= level <= 15, 'invalid_sparse_axis_level')
    if level == 0:
        return [(0., (0., 0., 0.), [(0., 1.)])]
    if level == 1:
        return [(p, (min(p, 0), p, max(p, 0)), [(p, 1.), (0., -1.)]) for p in (-1., 1.)]
    step = 2.**(1-level)
    return [(p, (p-step, p, p+step), [(p, 1.), (p-step, -.5), (p+step, -.5)])
            for p in np.arange(-1+step, 1, 2*step)]


def basis(supports, points):
    supports, points = np.asarray(supports), np.asarray(points)
    require(supports.ndim == 3 and supports.shape[1:] == (3, 3)
            and points.ndim == 2 and points.shape[1] == 3
            and np.isfinite(supports).all() and np.isfinite(points).all()
            and np.all(np.abs(points) <= 1), 'invalid_sparse_basis_inputs')
    require(len(points)*len(supports) <= 16_000_000, 'sparse_evaluation_batch_too_large')
    result = np.ones((len(points), len(supports)))
    for axis in range(3):
        lo, peak, hi = supports[:, axis, :].T
        x = points[:, axis, None]
        left = np.divide(x-lo, peak-lo, out=np.ones_like(result), where=(peak != lo))
        right = np.divide(hi-x, hi-peak, out=np.ones_like(result), where=(peak != hi))
        result *= np.where(peak == 0, 1, np.maximum(0, np.minimum(1, np.minimum(left, right))))
    return result


@dataclass
class SparseParameters:
    supports: np.ndarray
    coefficients: np.ndarray
    training_nodes: int

    def evaluate(self, points):
        points = np.asarray(points)
        batch = max(1, min(128, 16_000_000//max(1, len(self.supports))))
        return np.concatenate([basis(self.supports, points[i:i+batch]) @ self.coefficients
                               for i in range(0, len(points), batch)])


def fit(evaluate, max_level, *, max_nodes=1_000_000, batch_size=256, progress=None):
    require(type(max_level) is int and 0 <= max_level <= 15
            and type(max_nodes) is int and max_nodes > 0
            and type(batch_size) is int and 1 <= batch_size <= 1024,
            'invalid_sparse_fit_budget')
    cache, supports, coefficients = {}, [], []
    width = None
    for total in range(max_level+1):
        layer = []
        for levels in product(range(total+1), repeat=3):
            if sum(levels) == total:
                for nodes in product(*(axis_nodes(level) for level in levels)):
                    require(len(cache)+len(layer) < max_nodes, 'sparse_training_node_budget_exceeded')
                    layer.append(nodes)
        points = np.asarray([[node[0] for node in nodes] for nodes in layer])
        for start in range(0, len(points), batch_size):
            selected = points[start:start+batch_size]
            values = np.asarray(evaluate(selected), dtype=float)
            require(values.ndim == 2 and len(values) == len(selected) and values.shape[1] > 0
                    and np.isfinite(values).all(), 'invalid_sparse_parameter_samples')
            width = values.shape[1] if width is None else width
            require(values.shape[1] == width, 'sparse_parameter_count_changed')
            cache.update((tuple(p), v.copy()) for p, v in zip(selected, values))
        for nodes in layer:
            coefficient = np.zeros(width)
            for stencil in product(*(node[2] for node in nodes)):
                coefficient += np.prod([item[1] for item in stencil]) * cache[tuple(item[0] for item in stencil)]
            coefficients.append(coefficient)
            supports.append([node[1] for node in nodes])
        if progress is not None:
            progress(dict(level=total, training_nodes=len(cache)))
    return SparseParameters(np.asarray(supports), np.asarray(coefficients), len(cache))


@dataclass
class ClampRamps:
    supports: np.ndarray
    coefficients: np.ndarray  # signed integer F2DOT14 deltas, regions x hidden axes
    parameter_count: int
    ramps: int
    source_region_count: int

    def evaluate_axes(self, points):
        # avar2 maps every output simultaneously from the original physical
        # coordinates, then rounds to F2DOT14 and clips to [-1,1].
        values = SparseParameters(self.supports, self.coefficients, 0).evaluate(points)
        return np.clip(np.floor(values+.5), -16384, 16384)/16384

    def evaluate_clamped(self, points):
        axes = self.evaluate_axes(points).reshape(len(points), self.parameter_count, self.ramps)
        return (axes+1).sum(axis=2)/(2*self.ramps)

    def constant_axes(self, bounds, *, padding=2/16384):
        """Certify saturated outputs over a whole padded box, without sampling.

        Each nonnegative tensor hat is bounded by its endpoint minima and
        peak-inclusive maxima. Signed interval accumulation bounds the stored
        integer delta field. A conservative floating-point sum error is added
        before declaring a clamp constant. NaN means no certificate.
        Padding covers a pair of F2DOT14 ticks between an engine's mapped
        coordinates and its region-selection coordinates; native verification
        remains required for the supported engines.
        """
        bounds = np.asarray(bounds, dtype=float)
        require(bounds.shape == (3, 2) and np.isfinite(bounds).all()
                and np.all(bounds[:, 0] <= bounds[:, 1]) and np.all(np.abs(bounds) <= 1)
                and np.isfinite(padding) and padding >= 0, 'invalid_clamp_interval_box')
        box = np.clip(bounds+np.array([-padding, padding]), -1, 1)
        low, high = np.ones(len(self.supports)), np.ones(len(self.supports))
        for axis in range(3):
            lo, peak, hi = self.supports[:, axis].T
            def at(x):
                left = np.divide(x-lo, peak-lo, out=np.ones_like(lo), where=peak != lo)
                right = np.divide(hi-x, hi-peak, out=np.ones_like(lo), where=peak != hi)
                return np.where(peak == 0, 1, np.clip(np.minimum(left, right), 0, 1))
            a, b = at(box[axis, 0]), at(box[axis, 1])
            low *= np.minimum(a, b)
            high *= np.where((peak >= box[axis, 0]) & (peak <= box[axis, 1]), 1, np.maximum(a, b))
        positive, negative = np.maximum(self.coefficients, 0), np.minimum(self.coefficients, 0)
        lower = low @ positive+high @ negative
        upper = high @ positive+low @ negative
        neps = (len(self.supports)+16)*np.finfo(float).eps
        margin = 2*neps/(1-neps)*np.abs(self.coefficients).sum(axis=0)+1e-9
        result = np.full(self.coefficients.shape[1], np.nan)
        result[upper+margin <= -16384] = -1.
        result[lower-margin >= 16384] = 1.
        return result

    def var_store(self, physical_tags, hidden_tags):
        from fontTools.varLib.builder import buildVarStore, buildVarRegionList, buildVarData, buildDeltaSetIndexMap
        tags = tuple(physical_tags)+tuple(hidden_tags)
        require(len(physical_tags) == 3 and len(hidden_tags) == self.coefficients.shape[1]
                and len(set(tags)) == len(tags), 'invalid_clamp_ramp_axis_order')
        regions = [{tag: tuple(triple) for tag, triple in zip(physical_tags, row) if triple[1] != 0}
                   for row in self.supports]
        rows = np.r_[np.zeros((3, len(regions)), dtype=np.int64), self.coefficients.T].tolist()
        store = buildVarStore(buildVarRegionList(regions, tags),
                             [buildVarData(list(range(len(regions))), rows, optimize=False)])
        return store, buildDeltaSetIndexMap(list(range(len(tags))))


def encode_clamp_ramps(model, ramps=4):
    """clamp(t,0,1) = sum_j(clip(2*M*t-(2*j+1),-1,1)+1)/(2*M).

    Only one ramp is unsaturated except at shared boundaries. This improves
    parameter output resolution without a private runtime or cascaded avar2.
    Remove only coefficients that are exactly zero *after* format quantization.
    """
    require(type(ramps) is int and 1 <= ramps <= 32, 'invalid_clamp_ramp_count')
    require(model.supports.shape == (len(model.coefficients), 3, 3)
            and model.coefficients.ndim == 2 and model.coefficients.shape[1] > 0
            and np.isfinite(model.coefficients).all()
            and np.isfinite(model.supports).all()
            and np.all(model.supports[0] == 0), 'invalid_sparse_parameter_model')
    require(model.coefficients.shape[1]*ramps <= 65532, 'clamp_axis_count_overflow')
    supports = model.supports
    require(np.all(np.abs(supports) <= 1)
            and np.all(supports*16384 == np.rint(supports*16384))
            and np.all(supports[:, :, 0] <= supports[:, :, 1])
            and np.all(supports[:, :, 1] <= supports[:, :, 2])
            and np.all(supports[:, :, 0]*supports[:, :, 2] >= 0)
            and np.all((supports[:, :, 1] != 0) | np.all(supports == 0, axis=2)),
            'invalid_F2DOT14_parameter_supports')
    quantized = np.floor(model.coefficients*(32768*ramps)+.5)
    keep = np.any(quantized != 0, axis=1)
    keep[0] = True
    require(np.count_nonzero(keep) <= 65535, 'avar2_region_count_overflow')
    columns = []
    for k in range(model.coefficients.shape[1]):
        for j in range(ramps):
            row = quantized[keep, k].copy()
            row[0] -= (2*j+1)*16384
            columns.append(row)
    encoded = np.asarray(columns).T
    require(np.all(encoded >= -(2**31)) and np.all(encoded < 2**31), 'avar2_delta_overflow')
    return ClampRamps(model.supports[keep], encoded.astype(np.int64),
                      model.coefficients.shape[1], ramps, len(model.supports))
