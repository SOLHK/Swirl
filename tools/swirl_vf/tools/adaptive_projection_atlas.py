"""Error-driven local tricubics for unclamped projection component fields.

Training, refinement and independent acceptance are separate operations.
Source branch intersections propose splits; neither holdout values nor native
observations are available to the fitter. Boxes stay on the F2DOT14 lattice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import heapq
import json
from itertools import product
import numpy as np

from cff2_geometry import LIMIT, require
from joint_polynomial import interpolate, PolynomialBox, GRID, NODES
from hvf_piecewise_axes import segment_partition

GRID_PROBES = np.asarray(list(product((0., .125, .25, .5, .75, .875, 1.), repeat=3)))
JITTER_PROBES = np.random.default_rng(2026110379).uniform(0, 1, (64, 3))
PROBES = np.r_[GRID_PROBES, JITTER_PROBES]
AXIS_MASKS = [np.isin(PROBES[:, i], (.125, .5, .875)) &
              np.all(np.isin(PROBES[:, [j for j in range(3) if i != j]], NODES), axis=1)
              for i in range(3)]


def fingerprints(points):
    canonical = np.asarray(points, dtype='<f8').copy()
    canonical[canonical == 0] = 0.  # Signed zero is the same design location.
    return np.asarray([hashlib.blake2b(p.tobytes(), digest_size=16).digest()
                       for p in canonical], dtype='V16')


class RecordedSource:
    def __init__(self, source):
        self.source, self.receipts = source, []
    @property
    def closed_control_pairs(self): return self.source.closed_control_pairs
    def __call__(self, points):
        self.receipts.append(fingerprints(points))
        return self.source(points)


def source_events(source, start, end):
    return [row for row in segment_partition(source.table, source.gid, start, end)['events']
            if not row['kind'].startswith('tangent')]


def branch_probes(source, bounds):
    lo, hi = bounds.T
    mid = (lo+hi)/2
    segments = []
    for axis in range(3):
        a, b = mid.copy(), mid.copy()
        a[axis], b[axis] = lo[axis], hi[axis]
        segments.append((a, b))
    for corner in ((0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1)):
        segments.append((np.where(corner, hi, lo), np.where(corner, lo, hi)))
    points = set()
    for start, end in segments:
        for event in source_events(source, start, end):
            t = event['parameter']
            for u in (max(0, t-1e-7), t, min(1, t+1e-7)):
                points.add(tuple((1-u)*start+u*end))
    return np.asarray(sorted(points)).reshape(-1, 3)


def branch_split(source, evaluate, bounds, anchor, fallback_axis, budget):
    """Locate and measure actual source kinks before choosing a cut plane."""
    candidates, samples = [], []
    for axis in range(3):
        lo, hi = bounds[axis]
        a, b = anchor.copy(), anchor.copy()
        a[axis], b[axis] = lo, hi
        for event in source_events(source, a, b):
            t = event['parameter']
            if not .125 <= t <= .875:
                continue
            root = np.asarray(event['coordinates'])
            cut = np.floor(root[axis]*16384+.5)/16384
            if not lo < cut < hi:
                continue
            left, right = root.copy(), root.copy()
            radius = min(root[axis]-lo, hi-root[axis], (hi-lo)/16)
            left[axis] -= radius
            right[axis] += radius
            candidates.append((axis, cut))
            samples.extend((left, root, right))
    if candidates:
        values = evaluate(np.asarray(samples)).reshape(len(candidates), 3, -1)
        bend = source.errors((values[:, 0]+values[:, 2])/2, values[:, 1])
        selected = int(np.argmax(bend))
        if bend[selected] > budget/4:
            return (*candidates[selected], True)
    lo, hi = bounds[fallback_axis]
    return fallback_axis, np.floor((lo+hi)*8192+.5)/16384, False


@dataclass
class ProjectionAtlas:
    boxes: list[PolynomialBox]
    evidence: dict
    fitting_fingerprints: np.ndarray = field(repr=False)

    def save(self, path, identity):
        """Private coefficients and every fitting/refinement location receipt."""
        metadata = dict(schema=1, identity=identity, evidence=self.evidence,
                        operators=self.boxes[0].operators)
        np.savez_compressed(path, bounds=[b.bounds for b in self.boxes],
                            coefficients=[b.coefficients for b in self.boxes],
                            fitting_fingerprints=self.fitting_fingerprints,
                            metadata=json.dumps(metadata))

    @classmethod
    def load(cls, path, identity):
        with np.load(path, allow_pickle=False) as data:
            metadata = json.loads(str(data['metadata']))
            require(metadata['schema'] == 1 and metadata['identity'] == identity,
                    'projection_atlas_source_identity_mismatch')
            ops = tuple(tuple(item) for item in metadata['operators'])
            boxes = [PolynomialBox(b, ops, c, {'production_accepted': False})
                     for b, c in zip(data['bounds'], data['coefficients'])]
            require(bool(boxes) and len(boxes) == len(data['bounds']) == len(data['coefficients']),
                    'invalid_projection_atlas_storage')
            return cls(boxes, metadata['evidence'], data['fitting_fingerprints'].copy())

    def values(self, positions):
        positions = np.asarray(positions)
        result = np.empty((len(positions), self.boxes[0].coefficients.shape[-1]))
        covered = np.zeros(len(positions), dtype=bool)
        # Ordered first-match semantics agree with GSUB FeatureVariations at
        # shared closed boundaries. All neighbouring boxes are tested separately.
        for box in self.boxes:
            mask = ~covered & np.all((positions >= box.bounds[:, 0]) &
                                     (positions <= box.bounds[:, 1]), axis=1)
            if mask.any():
                result[mask] = box.values(positions[mask])
                covered[mask] = True
        require(covered.all(), 'projection_atlas_does_not_cover_request')
        return result


def fit(source, *, max_boxes=4096, budget=LIMIT/4, use_source_branches=True,
        source_aligned_cuts=True, progress=None):
    require(type(max_boxes) is int and 8 <= max_boxes <= 65532
            and 0 < budget <= LIMIT/2 and type(use_source_branches) is bool
            and type(source_aligned_cuts) is bool,
            'invalid_projection_atlas_budget')
    evaluate = RecordedSource(source)
    evaluate(np.zeros((1, 3)))
    queue, accepted = [], []
    serial = source_cuts = 0

    def cell(bounds):
        nonlocal serial
        model = interpolate(bounds, source.ops, evaluate)
        points = model.from_local(PROBES)
        errors = source.errors(model.values(points), evaluate(points))
        axis = int(np.argmax([errors[mask].max() for mask in AXIS_MASKS]))
        error = float(errors.max())
        anchor = points[int(np.argmax(errors))]
        if use_source_branches and error <= 2*budget:
            extra = branch_probes(source, bounds)
            if len(extra):
                e = source.errors(model.values(extra), evaluate(extra))
                if e.max() > error:
                    error = float(e.max()); anchor = extra[int(np.argmax(e))]
        serial += 1
        heapq.heappush(queue, (-error, serial, model, axis, anchor))

    for lo in product((-1., 0.), repeat=3):
        cell(np.c_[lo, np.asarray(lo)+1])
    while queue and len(queue)+len(accepted) < max_boxes:
        negative, _, model, axis, anchor = heapq.heappop(queue)
        if -negative <= budget:
            accepted.append((-negative, model))
            continue
        if use_source_branches and source_aligned_cuts:
            axis, cut, from_source = branch_split(source, evaluate, model.bounds, anchor, axis, budget)
        else:
            lo, hi = model.bounds[axis]
            cut, from_source = np.floor((lo+hi)*8192+.5)/16384, False
        lo, hi = model.bounds[axis]
        if not lo < cut < hi:
            accepted.append((-negative, model))
            continue
        source_cuts += from_source
        lower, upper = model.bounds.copy(), model.bounds.copy()
        lower[axis, 1] = upper[axis, 0] = cut
        cell(lower); cell(upper)
        if progress is not None and serial % 100 < 3:
            progress(dict(boxes=len(queue)+len(accepted), max_refinement_error=max(
                              -queue[0][0], max((e for e, _ in accepted), default=0)),
                          source_branch_cuts=source_cuts))
    entries = accepted + [(-item[0], item[2]) for item in queue]
    error = max(e for e, _ in entries)
    receipt = np.unique(np.concatenate(evaluate.receipts))
    evidence = dict(production_accepted=False, native_verification='NOT_RUN',
                    source_branch_probes=use_source_branches,
                    partition_strategy='source_aligned' if source_aligned_cuts and use_source_branches else 'midpoint',
                    max_refinement_error=error, source_branch_cuts=source_cuts,
                    refinement_budget=budget, refinement_budget_met=error <= budget,
                    training_and_refinement_unique_positions=len(receipt), boxes=len(entries))
    return ProjectionAtlas([m for _, m in entries], evidence, receipt)


def validate(atlas, source, heldout_positions):
    points = np.asarray(heldout_positions)
    require(points.ndim == 2 and points.shape[1] == 3 and len(points) > 0
            and np.isfinite(points).all() and np.all(np.abs(points) <= 1),
            'invalid_projection_atlas_holdouts')
    held = fingerprints(points)
    require(len(np.unique(held)) == len(held)
            and not np.intersect1d(held, atlas.fitting_fingerprints).size,
            'holdouts_overlap_training_or_refinement')
    expected, parameters = source.components(points)
    actual = atlas.values(points).reshape(expected.shape)
    clamp = np.clip(parameters, 0, 1)
    error = actual[:, 0]-expected[:, 0]+np.einsum('nf,nfp->np', clamp, actual[:, 1:]-expected[:, 1:])
    physical = np.linalg.norm(np.cumsum(error.reshape(len(error), -1, 2), axis=1), axis=2).max(axis=1)
    envelope = source.errors(actual.reshape(len(points), -1), expected.reshape(len(points), -1))
    return dict(holdout_count=len(points), max_physical_error=float(physical.max()),
                physical_failures=int((physical > LIMIT).sum()), max_envelope_error=float(envelope.max()),
                envelope_failures=int((envelope > LIMIT).sum()), holdouts_disjoint=True,
                production_accepted=False, source_projection_parameters_exact=True)
