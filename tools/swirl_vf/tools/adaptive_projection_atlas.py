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
from sparse_polynomial_fields import SparseFieldBox, save_arrays, legacy_coefficient_slices

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
    # Type-2 clamps are handled by the separate parameter field. Do not solve
    # their quadratic contacts here only to discard them. Identical chord
    # parameters imply identical coordinates and split probes; keep the first.
    result=[];seen=set()
    for row in segment_partition(source.table,source.gid,start,end,include_tangents=False)['events']:
        if row['parameter'] not in seen:
            result.append(row);seen.add(row['parameter'])
    return result


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
        metadata = dict(schema=2, identity=identity, evidence=self.evidence,
                        operators=self.boxes[0].operators)
        boxes=[SparseFieldBox.from_model(b) for b in self.boxes]
        offsets=np.r_[0,np.cumsum([len(b.columns) for b in boxes])]
        save_arrays(path,dict(bounds=np.asarray([b.bounds for b in boxes]),column_offsets=offsets,
            fitting_fingerprints=self.fitting_fingerprints,metadata=json.dumps(metadata)),
            dict(columns=((int(offsets[-1]),),'<i8',(b.columns for b in boxes)),
                 coefficient_values=((int(offsets[-1]),64),'<f8',(b.data.reshape(64,-1).T for b in boxes))))

    @classmethod
    def load(cls, path, identity):
        with np.load(path, allow_pickle=False) as data:
            metadata = json.loads(str(data['metadata']))
            require(metadata['schema'] in (1,2) and metadata['identity'] == identity,
                    'projection_atlas_source_identity_mismatch')
            ops = tuple(tuple(item) for item in metadata['operators'])
            if metadata['schema']==1:
                bounds=data['bounds']
                coefficients=legacy_coefficient_slices(path,(len(bounds),4,4,4,sum(n for _,n in ops)))
                boxes=[SparseFieldBox.from_model(PolynomialBox(b,ops,c,{'production_accepted':False}))
                       for b,c in zip(bounds,coefficients)]
                # Exhaust the generator's trailing-data check as zip stops when
                # bounds is exhausted before requesting another coefficient row.
                require(next(coefficients,None) is None,'invalid_projection_atlas_storage')
            else:
                offsets,columns,values=data['column_offsets'],data['columns'],data['coefficient_values']
                require(len(offsets)==len(data['bounds'])+1 and offsets[0]==0
                    and np.all(np.diff(offsets)>=0) and offsets[-1]==len(columns)
                    and values.shape==(len(columns),64),'invalid_sparse_atlas_storage')
                boxes=[SparseFieldBox(b,ops,columns[a:z],values[a:z].T.reshape(4,4,4,z-a),{'production_accepted':False})
                       for b,a,z in zip(data['bounds'],offsets[:-1],offsets[1:])]
            require(bool(boxes) and len(boxes) == len(data['bounds']),
                    'invalid_projection_atlas_storage')
            return cls(boxes, metadata['evidence'], data['fitting_fingerprints'].copy())

    def values(self, positions):
        positions = np.asarray(positions)
        result = np.empty((len(positions), sum(n for _,n in self.boxes[0].operators)))
        # Ordered first-match semantics agree with GSUB FeatureVariations at
        # shared closed boundaries. All neighbouring boxes are tested separately.
        bounds=np.asarray([b.bounds for b in self.boxes])
        for start in range(0,len(positions),64):
            p=positions[start:start+64]
            matches=np.all((p[:,None,:]>=bounds[None,:,:,0])&(p[:,None,:]<=bounds[None,:,:,1]),axis=2)
            require(matches.any(axis=1).all(),'projection_atlas_does_not_cover_request')
            chosen=np.argmax(matches,axis=1)
            for index in np.unique(chosen):
                where=np.flatnonzero(chosen==index)
                result[start+where]=self.boxes[index].values(p[where])
        return result


def fit(source, *, max_boxes=4096, budget=LIMIT/4, use_source_branches=True,
        source_aligned_cuts=True, progress=None, initial_atlas=None):
    require(type(max_boxes) is int and 8 <= max_boxes <= 65532
            and 0 < budget <= LIMIT/2 and type(use_source_branches) is bool
            and type(source_aligned_cuts) is bool,
            'invalid_projection_atlas_budget')
    evaluate = RecordedSource(source)
    evaluate(np.zeros((1, 3)))
    if initial_atlas is not None:
        require(len(initial_atlas.boxes)<=max_boxes and
                all(b.operators==source.ops for b in initial_atlas.boxes),
                'incompatible_resumed_projection_atlas')
        # Preserve every prior training/refinement receipt; no prior holdout
        # value or failure location is supplied to refinement.
        evaluate.receipts.append(initial_atlas.fitting_fingerprints)
    queue, accepted = [], []
    serial = source_cuts = 0

    def cell(bounds, previous=None):
        nonlocal serial
        model = previous or SparseFieldBox.from_model(interpolate(bounds, source.ops, evaluate))
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

    if initial_atlas is None:
        for lo in product((-1., 0.), repeat=3):
            cell(np.c_[lo, np.asarray(lo)+1])
    else:
        for previous in initial_atlas.boxes:
            cell(previous.bounds,previous)
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
                    resumed_boxes=0 if initial_atlas is None else len(initial_atlas.boxes),
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
    maxima=[0.,0.];failures=[0,0]
    for start in range(0,len(points),64):
        p=points[start:start+64];expected,parameters=source.components(p)
        actual=atlas.values(p).reshape(expected.shape)
        error=actual[:,0]-expected[:,0]+np.einsum('nf,nfp->np',np.clip(parameters,0,1),actual[:,1:]-expected[:,1:])
        physical=np.linalg.norm(np.cumsum(error.reshape(len(p),-1,2),axis=1),axis=2).max(axis=1)
        envelope=source.errors(actual.reshape(len(p),-1),expected.reshape(len(p),-1))
        for i,values in enumerate((physical,envelope)):
            maxima[i]=max(maxima[i],float(values.max()));failures[i]+=int((values>LIMIT).sum())
    return dict(holdout_count=len(points), max_physical_error=maxima[0],
                physical_failures=failures[0], max_envelope_error=maxima[1],
                envelope_failures=failures[1], holdouts_disjoint=True,
                production_accepted=False, source_projection_parameters_exact=True)
