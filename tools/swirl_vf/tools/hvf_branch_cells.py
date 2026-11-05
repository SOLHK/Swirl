"""Local analytic HVGL branch surfaces in the complete root design space.

Inside an internal-axis sign cell, every descendant axis and raw shape
coordinate is affine in the root coordinates. This propagates that expression
directly from source coefficients, without finite-difference fitting. Axis and
Type-0 clamp boundaries are planes; Type-2 projection boundaries are quadrics.
Expressions are valid only while all ancestor branch inequalities hold.
Rigid transforms and resolved outline geometry remain the source evaluator's
responsibility. A branch cell is not an OpenType-encodable region certificate.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from hvf import Composite, require


@dataclass
class BranchSurface:
    identity: tuple
    coefficients: np.ndarray  # homogeneous quadratic, [1, root axes]
    state: int

    def value(self, points):
        p = np.asarray(points, dtype=float)
        h = np.column_stack((np.ones(len(p)), p))
        return np.einsum('ni,ij,nj->n', h, self.coefficients, h)


@dataclass
class BranchCell:
    anchor: np.ndarray
    surfaces: list[BranchSurface]
    axis_expressions: dict
    shape_expressions: dict

    def contains(self, points):
        p = np.asarray(points, dtype=float)
        require(p.ndim == 2 and p.shape[1] == len(self.anchor)
                and np.isfinite(p).all(), 'invalid_branch_cell_points')
        valid = (np.abs(p) <= 1).all(axis=1)
        for surface in self.surfaces:
            # Equality belongs to either adjacent closed piece. Both source
            # positive/negative parts agree there; no epsilon moves a boundary.
            value = surface.value(p)
            valid &= value >= 0 if surface.state >= 0 else value <= 0
        return valid


def affine_surface(expression):
    expression = np.asarray(expression, dtype=float)
    q = np.zeros((len(expression), len(expression)))
    q[0, 0] = expression[0]
    q[0, 1:] = q[1:, 0] = expression[1:]/2
    return q


def dot_surface(left, right):
    """Dot of two vector-valued affine expressions, no sampled regression."""
    q = np.asarray(left) @ np.asarray(right).T
    return (q+q.T)/2


def axis_has_kink(part, axis):
    """Conservative exact test, including outgoing transforms.

    N*max(-a,0)+P*max(a,0) = -N*a+(N+P)*max(a,0).
    Only exactly cancelling stored coefficients remove the sign condition.
    Rotations are ordered rigid-transform products, not additive coordinates;
    an active rotation therefore always retains its branch.
    """
    negative, positive = 2*axis, 2*axis+1
    if not isinstance(part, Composite):
        return bool(np.any(part.delta[negative]+part.delta[positive]))
    totals = {}
    for column in (negative, positive):
        first, last = map(int, part.column_starts[column:column+2])
        for row, value in zip(part.extreme_rows[first:last], part.extreme_values[first:last]):
            totals[int(row)] = totals.get(int(row), 0.)+float(value)
    if any(totals.values()):
        return True
    totals = {}
    for (row, column), value in zip(part.translations.extreme_indices, part.translations.extreme_values):
        if column in (negative, positive):
            totals[int(row)] = totals.get(int(row), np.zeros(2))+value
    if any(np.any(value) for value in totals.values()):
        return True
    return any(column in (negative, positive) and np.any(value)
               for (_, column), value in zip(part.rotations.extreme_indices, part.rotations.extreme_values))


def branch_cell(table, gid, anchor):
    root = table.part(gid)
    anchor = np.asarray(anchor, dtype=float)
    require(anchor.shape == (root.axis_count,) and len(anchor) <= 3
            and np.isfinite(anchor).all() and (np.abs(anchor) <= 1).all(),
            'invalid_root_branch_anchor')
    dim = len(anchor)+1
    h = np.r_[1., anchor]
    values = np.zeros((root.tree_axes, dim))
    values[:len(anchor), 1:] = np.eye(len(anchor))
    result = BranchCell(anchor.copy(), [], {}, {})
    active = set()

    def surface(identity, q):
        require(np.isfinite(q).all(), 'nonfinite_branch_surface')
        at = float(h @ q @ h)
        state = 1 if at >= 0 else -1
        # Constant branches need no spatial constraint, but retain their axis
        # expression separately for source identity and evaluation checks.
        if np.any(q[1:]) or np.any(q[:, 1:]):
            result.surfaces.append(BranchSurface(identity, q, state))
        return state

    def visit(index, part_base, axis_base, depth):
        require(index not in active and depth <= 256, 'cyclic_branch_cell_hierarchy')
        active.add(index)
        part = table.part(index)
        axes = values[axis_base:axis_base+part.axis_count].copy()
        require(len(axes) == part.axis_count, 'invalid_branch_cell_axis_range')
        result.axis_expressions[(part.index, part_base)] = axes
        weights = np.zeros((part.axis_count*2, dim))
        for axis, expression in enumerate(axes):
            if axis_has_kink(part, axis):
                sign = surface((part.index, part_base, 'axis_zero', axis), affine_surface(expression))
            else:
                # Either affine continuation is identical across zero. Keep
                # the observed side without adding an artificial partition.
                sign = 1 if h @ expression >= 0 else -1
            weights[2*axis+(sign > 0)] = sign*expression
        if isinstance(part, Composite):
            base = axis_base+part.axis_count
            values[base+part.master_rows, 0] += part.master_values
            for col, expression in enumerate(weights):
                first, last = map(int, part.column_starts[col:col+2])
                values[base+part.extreme_rows[first:last]] += part.extreme_values[first:last, None]*expression
            for child, part_row, axis_row in part.subparts:
                visit(child, part_base+1+part_row, base+axis_row, depth+1)
        else:
            raw = np.zeros((dim, *part.master.shape))
            raw[0] = part.master
            raw += np.einsum('ad,asp->dsp', weights, part.delta)
            result.shape_expressions[(part.index, part_base)] = raw
            start = 0
            for path, size in enumerate(part.path_sizes):
                if size >= 3:
                    for i, kind in enumerate(part.blends[start:start+size]):
                        key = (part.index, part_base, path, i)
                        if kind == 0:
                            factor = raw[:, start+i, 0]
                            surface((*key, 'curve_lower'), affine_surface(factor))
                            upper = factor.copy(); upper[0] -= 1
                            surface((*key, 'curve_upper'), affine_surface(upper))
                        elif kind == 2:
                            a = raw[:, start+(i-1)%size, 2:4]
                            b = raw[:, start+i, 2:4]
                            p = raw[:, start+i, :2]
                            direction = b-a
                            require(np.any(h @ direction), 'collapsed_branch_projection')
                            surface((*key, 'tangent_lower'), dot_surface(p-a, direction))
                            surface((*key, 'tangent_upper'), dot_surface(p-b, direction))
                        else:
                            require(kind == 1, 'unsupported_branch_cell_tangent')
                start += size
        active.remove(index)

    visit(gid, 0, 0, 0)
    return result
