"""Separate HVF Type-2 projection clamps from smooth outline fields.

For A=previous off-curve control, B=current off-curve control and raw on-curve
P, the resolved point is A + clamp(dot(P-A,B-A)/|B-A|², 0, 1)*(B-A).
Affine placement and quadratic-to-cubic elevation preserve this factorization.
This module extracts the factors; it does not approximate, serialize or accept
the source font. Type-0 clamps and descendant-axis branches remain in the
baseline and direction fields, and still require independent validation.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from batch_geometry import BatchGeometry
from cff2_geometry import require


def relative_cubics(paths):
    """Exact quadratic degree elevation, including explicit closing curves."""
    require(bool(paths), 'nonempty_factor_geometry_required')
    n = len(paths[0])
    points, operators = [], []
    for path in paths:
        require(path.ndim == 3 and path.shape[0] == n and path.shape[2] == 2
                and path.shape[1] >= 6 and path.shape[1] % 2 == 0,
                'invalid_factor_path_topology')
        on, off = path[:, ::2], path[:, 1::2]
        next_on = np.roll(on, -1, axis=1)
        curves = np.stack(((on+2*off)/3, (next_on+2*off)/3, next_on), axis=2)
        points.extend((on[:, :1], curves.reshape(n, -1, 2)))
        operators.extend([('rmoveto', 2)] + [('rrcurveto', 6)]*len(on[0]))
    absolute = np.concatenate(points, axis=1)
    values = np.diff(absolute, axis=1, prepend=np.zeros((n, 1, 2))).reshape(n, -1)
    return tuple(operators), values


@dataclass
class ProjectionFactors:
    operators: tuple
    values: np.ndarray  # samples x (baseline + factors) x relative operands
    parameters: np.ndarray  # unclamped projection parameters
    identities: tuple

    def combine(self, parameters=None):
        t = self.parameters if parameters is None else np.asarray(parameters)
        require(t.shape == self.parameters.shape and np.isfinite(t).all(),
                'invalid_factor_parameters')
        return self.values[:, 0] + np.einsum('nf,nfp->np', np.clip(t, 0, 1), self.values[:, 1:])


def factor_geometry(table, batch):
    require(batch.trace is not None and len(batch.paths) == len(batch.sources),
            'factorization_requires_source_geometry_trace')
    traces = {(node.part_index, node.tree_part_offset): node for node in batch.trace}
    require(len(traces) == len(batch.trace), 'duplicate_factor_trace_identity')
    paths = [path.copy() for path in batch.paths]
    factors, parameters, identities = [], [], []
    for pi, (path, identity) in enumerate(zip(paths, batch.sources)):
        node = traces[(identity.part_index, identity.tree_part_offset)]
        part = table.part(identity.part_index)
        first = identity.source_segment_start
        count = path.shape[1]//2
        require(node.shape_coordinates is not None, 'missing_factor_shape_coordinates')
        raw = node.shape_coordinates[:, first:first+count]
        for k, kind in enumerate(part.blends[first:first+count]):
            if kind != 2:
                continue
            a, b = raw[:, (k-1) % count, 2:4], raw[:, k, 2:4]
            direction = b-a
            scale = np.max(np.abs(direction), axis=1)
            require(np.isfinite(direction).all() and np.all(scale > 0),
                    'collapsed_projection_factor_direction')
            unit = direction/scale[:, None]
            t = (np.sum((raw[:, k, :2]-a)*unit, axis=1)
                 / np.sum(unit*unit, axis=1))/scale
            require(np.isfinite(t).all(), 'nonfinite_projection_factor')
            world_a = path[:, 2*((k-1) % count)+1]
            world_b = path[:, 2*k+1]
            path[:, 2*k] = world_a
            delta = [np.zeros_like(p) for p in paths]
            delta[pi][:, 2*k] = world_b-world_a
            factors.append(delta)
            parameters.append(t)
            identities.append((identity.part_index, identity.tree_part_offset,
                               identity.source_path_index, k))
    operators, baseline = relative_cubics(paths)
    values = np.stack([baseline] + [relative_cubics(p)[1] for p in factors], axis=1)
    t = np.asarray(parameters).T if parameters else np.empty((batch.sample_count, 0))
    return ProjectionFactors(operators, values, t, tuple(identities))


class ProjectionSource:
    """Batched adapter for existing local fitters; no native acceptance claim."""
    def __init__(self, table, glyph_id, *, batch_size=256):
        require(type(batch_size) is int and 1 <= batch_size <= 1024,
                'invalid_projection_batch_size')
        self.table, self.gid = table, glyph_id
        self.renderer = BatchGeometry(table, isolated_tangents=True)
        self.batch_size, self.count = batch_size, 0
        self.base_ops = self.ops = self.identities = None
        self.closed_control_pairs = []

    def components(self, positions):
        require(len(positions) > 0, 'nonempty_projection_positions_required')
        values, parameters = [], []
        for start in range(0, len(positions), self.batch_size):
            batch = self.renderer.render(self.gid, positions[start:start+self.batch_size], capture_trace=True)
            result = factor_geometry(self.table, batch)
            self.count += batch.sample_count
            if self.base_ops is None:
                self.base_ops, self.identities = result.operators, result.identities
                self.factors, self.width = len(result.identities), result.values.shape[-1]
                self.ops = self.base_ops*(self.factors+1)
                point = 0
                for operator, count in self.ops:
                    if operator == 'rmoveto':
                        if point:
                            self.closed_control_pairs.append((begin, point-1))
                        begin = point
                    point += count//2
                self.closed_control_pairs.append((begin, point-1))
            require(self.base_ops == result.operators and self.identities == result.identities,
                    'projection_factor_topology_changed')
            values.append(result.values)
            parameters.append(result.parameters)
        return np.concatenate(values), np.concatenate(parameters)

    def __call__(self, positions):
        values, _ = self.components(positions)
        return values.reshape(len(positions), -1)

    def errors(self, left, right):
        """Bound every clamp combination in [0,1], at every cubic control."""
        delta = (np.asarray(left)-np.asarray(right)).reshape(len(left), self.factors+1, -1, 2)
        return np.linalg.norm(np.cumsum(delta, axis=2), axis=3).sum(axis=1).max(axis=1)
