"""Error-driven CFF2 interpolation on explicitly bounded design-space slices.

A slice is a diagnostic/reconstruction primitive, not a three-dimensional font.
Unlike a global least-squares fit, this preserves local samples and inserts both
F2DOT14 neighbours of detected HVF branch boundaries. Refinement uses separate
quarter/midpoint probes; held-out observations never select knots. All resulting
coefficients use ordinary CFF2 blends. No point, contour or tolerance is removed.
"""
from __future__ import annotations

import math
import numpy as np
from fontTools.varLib.models import supportScalar
from cff2_geometry import OutlineModel, LIMIT, fixed, require

GRID = 16384


def point_errors(a, b):
    """Maximum absolute cubic-control distance, not relative operand error."""
    difference = np.asarray(a)-np.asarray(b)
    require(difference.ndim == 2 and difference.shape[1] % 2 == 0,
            'invalid_slice_operand_matrix')
    return np.linalg.norm(np.cumsum(difference.reshape(len(difference), -1, 2), axis=1),
                          axis=2).max(axis=1, initial=0.)


def find_transitions(signature, *, divisions=64, iterations=32):
    """Bracket discrete regime changes, retaining every changed signature field.

    This is bounded discovery, not a proof that two transitions cannot occur
    between probes. The independent geometric refinement remains necessary.
    Values are tuples of integer branch states, supplied by the source adapter.
    """
    require(type(divisions) is int and 2 <= divisions <= 4096, 'invalid_branch_scan')
    require(type(iterations) is int and 1 <= iterations <= 48, 'invalid_branch_iterations')
    x = np.linspace(-1., 1., divisions+1)
    state = np.asarray(signature(x))
    require(state.ndim == 2 and len(state) == len(x) and
            np.issubdtype(state.dtype, np.integer), 'invalid_branch_signature')
    intervals = []
    for i, field in zip(*np.nonzero(state[1:] != state[:-1])):
        lo, hi = x[i], x[i+1]
        before = state[i, field]
        for _ in range(iterations):
            mid = (lo+hi)/2
            value = np.asarray(signature([mid]))
            require(value.shape == (1, state.shape[1]), 'branch_signature_topology_changed')
            if value[0, field] == before: lo = mid
            else: hi = mid
        intervals.append({'field': int(field), 'low': float(lo), 'high': float(hi),
                          'before': int(before), 'after': int(state[i+1, field])})
    return intervals


def fit_slice(evaluate, operators, axis_tags, varying_axis, fixed_location,
              holdout_coordinates, *, transitions=(), max_knots=507,
              refinement_budget=LIMIT/4):
    """Fit a slice and return an OutlineModel with an explicit non-global scope.

    evaluate(xs) returns unquantized relative CFF2 operands at those coordinates.
    fixed_location is recorded verbatim; it is NOT interpreted as zero for the
    inactive axes. The resulting font model is valid only on this slice.
    """
    tags = tuple(axis_tags)
    require(varying_axis in tags and set(fixed_location) == set(tags)-{varying_axis}
            and all(math.isfinite(v) and -1 <= v <= 1 for v in fixed_location.values()),
            'invalid_slice_domain')
    require(3 <= max_knots <= 507 and 0 < refinement_budget <= LIMIT/4,
            'invalid_slice_refinement_contract')
    held = np.asarray(holdout_coordinates, dtype=float)
    require(held.ndim == 1 and len(held) and np.isfinite(held).all()
            and (np.abs(held) <= 1).all(), 'independent_slice_holdouts_required')
    knots = {-GRID, 0, GRID}
    for transition in transitions:
        require(math.isfinite(transition) and -1 <= transition <= 1, 'invalid_slice_transition')
        knots.update((math.floor(transition*GRID), math.ceil(transition*GRID)))
    require(len(knots) <= max_knots, 'branch_boundaries_exceed_slice_capacity')
    cache = {}
    def sample(xs):
        xs = list(map(float, xs))
        missing = list(dict.fromkeys(v for v in xs if v not in cache))
        if missing:
            values = np.asarray(evaluate(missing), dtype=float)
            require(values.ndim == 2 and len(values) == len(missing)
                    and values.shape[1] == sum(n for _, n in operators)
                    and np.isfinite(values).all(), 'invalid_slice_observation')
            cache.update(zip(missing, values))
        return np.asarray([cache[v] for v in xs])
    history = []
    while True:
        ticks = np.asarray(sorted(knots)); xs = ticks/GRID
        ys = sample(xs)
        probes = (xs[:-1,None] + (xs[1:]-xs[:-1])[:,None]*np.asarray([.25,.5,.75])).ravel()
        expected = sample(probes)
        approximate = (ys[:-1,None,:]*(1-np.asarray([.25,.5,.75]))[None,:,None]
                       + ys[1:,None,:]*np.asarray([.25,.5,.75])[None,:,None]).reshape(len(probes), -1)
        errors = point_errors(expected, approximate).reshape(-1,3)
        worst = errors.max(axis=1)
        history.append({'knots': len(xs), 'max_probe_error': float(worst.max(initial=0.))})
        bad = np.flatnonzero(worst > refinement_budget)
        splittable = [i for i in bad if ticks[i+1]-ticks[i] > 1]
        if not splittable or len(knots) == max_knots: break
        # Local error drives refinement, not a regression over unrelated points.
        for i in sorted(splittable, key=lambda i: worst[i], reverse=True)[:max_knots-len(knots)]:
            knots.add(int((ticks[i]+ticks[i+1])//2))
    base = ys[np.flatnonzero(ticks == 0)[0]]
    supports, deltas = [{}], [base]
    for i, x in enumerate(xs):
        if x == 0: continue
        supports.append({varying_axis: (float(xs[max(0,i-1)]), float(x),
                                       float(xs[min(len(xs)-1,i+1)]))})
        deltas.append(ys[i]-base)
    encoded = np.asarray([[fixed(v) for v in row] for row in deltas])
    evidence = {'limit_source_font_units': LIMIT, 'domain_kind': 'one_dimensional_slice',
        'varying_axis': varying_axis, 'fixed_location': dict(fixed_location),
        'three_dimensional_acceptance': False, 'production_accepted': False,
        'refinement': history, 'knots': xs.tolist(), 'probe_count': len(cache),
        'holdout_count': len(held), 'failures': [], 'serialized_verification': 'NOT_RUN',
        'native_verification': 'NOT_RUN', 'sampled_geometry_passed': False}
    model = OutlineModel(tags, tuple(operators), supports, encoded, evidence)
    # Holdouts must be disjoint from ALL fitting/boundary/refinement observations.
    require(all(float(v) not in cache for v in held), 'holdout_used_during_slice_fit')
    for kind, positions in [('training', xs), ('refinement', probes), ('holdout', held)]:
        truth = sample(positions)
        prediction = np.asarray([np.asarray([1.] + [
            supportScalar({varying_axis:float(x)}, s) for s in supports[1:]]) @ encoded for x in positions])
        measured = point_errors(truth, prediction)
        evidence[f'max_{kind}_error'] = float(measured.max(initial=0.))
        evidence['failures'].extend({'sample_kind':kind,'coordinate':float(positions[i]),
            'error_source_units':float(measured[i])} for i in np.flatnonzero(measured > LIMIT))
    evidence['sampled_geometry_passed'] = not evidence['failures']
    evidence['refinement_budget_met'] = history[-1]['max_probe_error'] <= refinement_budget
    return model
