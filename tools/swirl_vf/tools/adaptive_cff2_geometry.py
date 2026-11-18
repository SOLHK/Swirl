"""Bounded three-axis tensor refinement using ordinary CFF2 region blends.

Refinement evaluates complete cell midpoint planes, including mixed-axis
interactions that vanish on each individual axis. Independent holdouts never
choose a split. Every knot is exact F2DOT14; the unchanged 1/32 absolute cubic
control-point bound includes accumulation and 16.16 coefficient quantization.
This is a sampled model, not a proof over a continuous design space.
"""
from __future__ import annotations

import itertools
import numpy as np
from fontTools.varLib.models import VariationModel, supportScalar

from cff2_geometry import OutlineModel, LIMIT, fixed, require
from piecewise_geometry import point_errors

GRID = 16384


def fit_tensor(evaluate, operators, axis_tags, holdout_locations, *,
               max_nodes=507, refinement_budget=LIMIT/4):
    tags = tuple(axis_tags)
    require(len(tags) == 3 and len(set(tags)) == 3 and all(
        isinstance(t, str) and len(t) == 4 for t in tags), 'three_tensor_axes_required')
    require(type(max_nodes) is int and 27 <= max_nodes <= 4096
        and 0 < refinement_budget <= LIMIT/4, 'invalid_tensor_refinement_budget')
    held = np.asarray(holdout_locations, dtype=float)
    require(held.ndim == 2 and held.shape[1] == 3 and len(held) > 0
        and np.isfinite(held).all() and (np.abs(held) <= 1).all(), 'independent_tensor_holdouts_required')
    require(len({tuple(p) for p in held}) == len(held), 'duplicate_tensor_holdouts')
    axes = [np.asarray([-GRID, 0, GRID], dtype=int) for _ in tags]
    cache = {}

    def sample(points):
        keys = [tuple(map(float, p)) for p in points]
        missing = list(dict.fromkeys(p for p in keys if p not in cache))
        for start in range(0, len(missing), 256):
            batch = missing[start:start+256]
            values = np.asarray(evaluate(np.asarray(batch)), dtype=float)
            require(values.shape == (len(batch), sum(n for _, n in operators))
                    and np.isfinite(values).all(), 'invalid_tensor_source_observation')
            cache.update(zip(batch, values))
        return np.asarray([cache[k] for k in keys])

    def interpolate(points, nodes, values):
        indices = [np.clip(np.searchsorted(axis, points[:, i], side='right')-1, 0, len(axis)-2)
                   for i, axis in enumerate(nodes)]
        fractions = [(points[:, i]-axis[index])/(axis[index+1]-axis[index])
                     for i, (axis, index) in enumerate(zip(nodes, indices))]
        answer = np.zeros((len(points), values.shape[-1]))
        for corner in itertools.product((0, 1), repeat=3):
            weight = np.prod([v if bit else 1-v for v, bit in zip(fractions, corner)], axis=0)
            answer += weight[:, None]*values[tuple(index+bit for index, bit in zip(indices, corner))]
        return answer

    history = []
    while True:
        nodes = [a/GRID for a in axes]
        training = np.asarray(list(itertools.product(*nodes)))
        values = sample(training).reshape(*(len(a) for a in axes), -1)
        half = [np.sort(np.concatenate((a, (a[:-1]+a[1:])/2))) for a in nodes]
        probes = np.asarray(list(itertools.product(*half)))
        truth = sample(probes)
        predicted = interpolate(probes, nodes, values)
        errors = point_errors(predicted, truth)
        maximum = float(errors.max(initial=0))
        history.append(dict(nodes=[len(a) for a in axes], total_nodes=len(training),
                            max_probe_error=maximum))
        if maximum <= refinement_budget:
            break
        candidates = []
        for dimension, axis in enumerate(axes):
            if (len(axis)+1)*int(np.prod([len(a) for i, a in enumerate(axes) if i != dimension])) > max_nodes:
                continue
            # Compare each midpoint plane with the two parallel boundary planes
            # at identical values of the other axes. Cross-axis defects remain
            # visible, rather than being inferred from three isolated sweeps.
            for interval in range(len(axis)-1):
                tick = int((axis[interval]+axis[interval+1])//2)
                if tick in axis:
                    continue
                center = (nodes[dimension][interval]+nodes[dimension][interval+1])/2
                mask = probes[:, dimension] == center
                mid = probes[mask]
                lo, hi = mid.copy(), mid.copy()
                lo[:, dimension] = nodes[dimension][interval]
                hi[:, dimension] = nodes[dimension][interval+1]
                defect = point_errors((sample(lo)+sample(hi))/2, truth[mask])
                candidates.append((float(defect.max(initial=0)), dimension, tick))
        if not candidates:
            break
        _, dimension, tick = max(candidates, key=lambda item: (item[0], -item[1], -item[2]))
        axes[dimension] = np.sort(np.append(axes[dimension], tick))

    # Keep fitting/refinement observations and independent holdouts disjoint.
    require(all(tuple(map(float, p)) not in cache for p in held), 'tensor_holdout_used_during_fit')
    locations = [dict(zip(tags, map(float, p))) for p in training]
    variation = VariationModel(locations, axisOrder=list(tags))
    rows = variation.getDeltas([v.copy() for v in values.reshape(len(training), -1)])
    encoded = np.asarray([[fixed(v) for v in row] for row in rows])
    evidence = dict(domain_kind='three_dimensional_cube', continuous_space_proof=False,
        limit_source_font_units=LIMIT, refinement_budget=refinement_budget,
        refinement=history, training_count=len(training), holdout_count=len(held),
        refinement_budget_met=maximum <= refinement_budget, failures=[],
        sampled_geometry_passed=False, production_accepted=False,
        serialized_verification='NOT_RUN', native_verification='NOT_RUN')
    model = OutlineModel(tags, tuple(operators), variation.supports, encoded, evidence)
    for kind, points in (('training', training), ('refinement', probes), ('holdout', held)):
        measured = []
        for start in range(0, len(points), 128):
            chunk = points[start:start+128]
            scalars = np.asarray([[supportScalar(dict(zip(tags, p)), support)
                                   for support in model.supports] for p in chunk])
            measured.append(point_errors(scalars @ encoded, sample(chunk)))
        errors = np.concatenate(measured)
        evidence[f'max_{kind}_error'] = float(errors.max(initial=0))
        evidence['failures'].extend(dict(sample_kind=kind, sample_index=int(i),
            error_source_units=float(errors[i])) for i in np.flatnonzero(errors > LIMIT))
    evidence['sampled_geometry_passed'] = not evidence['failures']
    # Models larger than the flat-blend stack may still compact losslessly.
    # Record the actual encoding result; never remove small nonzero deltas.
    from cff2_geometry import compact
    packed = compact(model)
    evidence['nonzero_regions'] = len(packed.supports)-1
    try:
        packed.charstring(0).compile(isCFF2=True)
        evidence['flat_blend_stack_encodable'] = True
    except ValueError as error:
        evidence['flat_blend_stack_encodable'] = False
        evidence['encoding_error'] = str(error)
    return model
