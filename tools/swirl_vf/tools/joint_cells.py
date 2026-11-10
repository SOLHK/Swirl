"""Error-driven local tricubic cells for factored three-axis source fields.

Refinement is independent of acceptance samples. Source-derived axis/Type-0
contacts augment interior and face probes; Type-2 clamps belong to the separate
parameter representation. Leaf coefficients retain only exactly nonzero
columns in memory and on disk. No small coefficient is discarded.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
from itertools import product
import numpy as np

from cff2_geometry import LIMIT, require, CFF2GeometryError
from joint_polynomial import PolynomialBox, interpolate, NODES
from hvf_piecewise_axes import segment_partition

PROBES = np.asarray(list(product((0., .125, .25, .5, .75, .875, 1.), repeat=3)))
AXIS_MASKS = [np.isin(PROBES[:, axis], (.125, .5, .875)) &
              np.all(np.isin(PROBES[:, [j for j in range(3) if j != axis]], NODES), axis=1)
              for axis in range(3)]


def branch_probes(table, gid, bounds):
    lo, hi = np.asarray(bounds).T
    middle = (lo+hi)/2
    chords = []
    for axis in range(3):
        a, b = middle.copy(), middle.copy()
        a[axis], b[axis] = lo[axis], hi[axis]
        chords.append((a, b))
    for bits in product((0, 1), repeat=2):
        choice = np.asarray((0, *bits))
        chords.append((np.where(choice, hi, lo), np.where(choice, lo, hi)))
    points = set()
    for a, b in chords:
        for event in segment_partition(table, gid, a, b)['events']:
            if event['kind'].startswith('tangent'):
                continue
            t = event['parameter']
            for u in (max(0., t-1e-7), t, min(1., t+1e-7)):
                points.add(tuple((1-u)*a+u*b))
    return np.asarray(sorted(points)).reshape(-1, 3)


@dataclass
class Cell:
    bounds: np.ndarray
    columns: np.ndarray
    coefficients: np.ndarray
    error: float
    axis_scores: np.ndarray

    @classmethod
    def from_model(cls, model, error, scores):
        columns = np.flatnonzero(np.any(model.coefficients != 0, axis=(0, 1, 2)))
        return cls(model.bounds.copy(), columns, model.coefficients[..., columns].copy(),
                   float(error), np.asarray(scores))

    def model(self, operators):
        data = np.zeros((4, 4, 4, sum(n for _, n in operators)))
        data[..., self.columns] = self.coefficients
        return PolynomialBox(self.bounds, tuple(operators), data, dict(
            domain_kind='local_polynomial_box', max_refinement_error=self.error,
            sampled_geometry_passed=self.error <= LIMIT, production_accepted=False))


@dataclass
class CellPartition:
    operators: tuple
    cells: list[Cell]
    budget: float
    samples: int

    @property
    def maximum_error(self):
        return max(cell.error for cell in self.cells)

    def evaluate(self, points):
        points = np.asarray(points)
        values = np.empty((len(points), sum(n for _, n in self.operators)))
        seen = np.zeros(len(points), bool)
        # Closed-box first match has exactly the serialized FeatureVariations
        # tie order. Independent seam tests must still examine both neighbours.
        for cell in self.cells:
            selected = (~seen) & np.all((points >= cell.bounds[:, 0]) & (points <= cell.bounds[:, 1]), axis=1)
            if np.any(selected):
                values[selected] = cell.model(self.operators).values(points[selected])
                seen[selected] = True
        require(seen.all(), 'joint_partition_does_not_cover_requested_points')
        return values

    def save(self, path):
        columns = np.unique(np.concatenate([cell.columns for cell in self.cells]))
        indices = {int(column): i for i, column in enumerate(columns)}
        values = np.zeros((len(self.cells), 4, 4, 4, len(columns)))
        for i, cell in enumerate(self.cells):
            values[i][..., [indices[int(c)] for c in cell.columns]] = cell.coefficients
        np.savez_compressed(path, bounds=[cell.bounds for cell in self.cells], columns=columns,
                            coefficients=values, errors=[cell.error for cell in self.cells],
                            axis_scores=[cell.axis_scores for cell in self.cells])


def refine(source, *, max_cells=4096, budget=LIMIT/4, seed=2026110379,
           initial=None, progress=None):
    """Refine from the eight octants or a previous partition; no held-out input.

    Source returns relative cubic fields, an error bound in source units, and
    optionally analytic local branch probes. Exceeding a resource cap returns
    failed evidence; it never changes the acceptance budget.
    """
    require(type(max_cells) is int and 8 <= max_cells <= 32768 and
            0 < budget <= LIMIT/4, 'invalid_joint_cell_budget')
    source(np.zeros((1, 3)))
    probes = np.r_[PROBES, np.random.default_rng(seed).uniform(0, 1, (64, 3))]
    queue, accepted, serial = [], [], 0

    def visit(bounds):
        nonlocal serial
        try:
            model = interpolate(bounds, source.ops, source)
        except CFF2GeometryError as error:
            if str(error) != 'polynomial_fixed_coefficient_overflow':
                raise
            # A coarse kink can have large power-basis coefficients even when
            # its outline fits the numeric range. Subdivide it; if the resource
            # cap prevents that, retain an explicitly failed/unencodable leaf.
            corners = np.asarray(list(product(*np.asarray(bounds))))
            values = source(corners).reshape(2, 2, 2, -1)
            scores = np.asarray([np.max(np.abs(np.diff(values, axis=a))) for a in range(3)])
            cell = Cell(np.asarray(bounds).copy(), np.empty(0, dtype=int),
                        np.empty((4, 4, 4, 0)), np.inf, scores)
            serial += 1
            heapq.heappush(queue, (-np.inf, serial, cell))
            return
        points = model.from_local(probes)
        errors = source.errors(model.values(points), source(points))
        scores = np.asarray([errors[:len(PROBES)][mask].max() for mask in AXIS_MASKS])
        error = float(errors.max())
        if error <= 2*budget and hasattr(source, 'local_probes'):
            extra = source.local_probes(bounds)
            if len(extra):
                error = max(error, float(source.errors(model.values(extra), source(extra)).max()))
        cell = Cell.from_model(model, error, scores)
        serial += 1
        heapq.heappush(queue, (-error, serial, cell))

    if initial is None:
        for lo in product((-1., 0.), repeat=3):
            visit(np.c_[lo, np.asarray(lo)+1])
    else:
        require(tuple(source.ops) == initial.operators, 'resumed_joint_topology_mismatch')
        for cell in initial.cells:
            visit(cell.bounds)
    while queue:
        error, _, cell = heapq.heappop(queue)
        if -error <= budget:
            accepted.append(cell)
            continue
        if len(accepted)+len(queue)+1 >= max_cells:
            accepted.append(cell)
            break
        choices = sorted(range(3), key=lambda axis: (-cell.axis_scores[axis], axis))
        split = None
        for axis in choices:
            lo, hi = cell.bounds[axis]
            middle = round((lo+hi)*8192)/16384
            if lo < middle < hi:
                split = axis, middle
                break
        if split is None:
            accepted.append(cell)
            continue
        axis, middle = split
        left, right = cell.bounds.copy(), cell.bounds.copy()
        left[axis, 1] = right[axis, 0] = middle
        visit(left); visit(right)
        if progress is not None and serial % 200 < 2:
            progress(dict(cells=len(accepted)+len(queue), samples=source.count,
                          max_probe=max([-r[0] for r in queue]+[c.error for c in accepted])))
    return CellPartition(tuple(source.ops), accepted+[item[2] for item in queue], budget, source.count)


def load(path, operators, *, budget=LIMIT/4):
    """Load bounded numeric archives, including prior dense-column experiments."""
    with np.load(path, allow_pickle=False) as archive:
        bounds, values = archive['bounds'], archive['coefficients']
        columns = archive['columns'] if 'columns' in archive else np.arange(values.shape[-1])
        errors = archive['errors'] if 'errors' in archive else np.full(len(bounds), np.inf)
        scores = archive['axis_scores'] if 'axis_scores' in archive else np.zeros((len(bounds), 3))
        require(values.shape[:4] == (len(bounds), 4, 4, 4) and
                bounds.shape[1:] == (3, 2) and len(columns) == values.shape[-1] and
                np.isfinite(values).all() and np.isfinite(bounds).all(), 'invalid_joint_cell_archive')
        cells = []
        for b, v, e, s in zip(bounds, values, errors, scores):
            keep = np.any(v != 0, axis=(0, 1, 2))
            cells.append(Cell(b.copy(), columns[keep].copy(), v[..., keep].copy(), float(e), s.copy()))
    return CellPartition(tuple(operators), cells, budget, 0)
