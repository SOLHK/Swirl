"""Outward-rounded interval bounds for Type-0 clamp reachability.

This proves absence of a Type-0 clamp contact only when every covering box
keeps every raw factor strictly between zero and one. An unresolved interval
is not evidence that a contact exists or that the glyph is unrepresentable.
Type-2 rational projections and final geometry require their own validation.
"""
from __future__ import annotations
import numpy as np
from hvf import Composite, require


def add(left, right):
    result = left+right
    return np.stack((np.nextafter(result[..., 0], -np.inf),
                     np.nextafter(result[..., 1], np.inf)), axis=-1)


def scale(interval, coefficient):
    product = interval*np.asarray(coefficient)[..., None]
    return np.stack((np.nextafter(product.min(axis=-1), -np.inf),
                     np.nextafter(product.max(axis=-1), np.inf)), axis=-1)


def raw_curve_bounds(table, gid, bounds):
    root = table.part(gid)
    bounds = np.asarray(bounds, dtype=float)
    require(bounds.shape == (root.axis_count, 2) and np.isfinite(bounds).all()
            and np.all(bounds[:, 0] <= bounds[:, 1]), 'invalid_clamp_interval_domain')
    values = np.zeros((root.tree_axes, 2)); values[:root.axis_count] = bounds
    factors = []
    active = set()
    def visit(index, axis_base, depth):
        require(index not in active and depth <= 256, 'cyclic_clamp_interval_hierarchy')
        active.add(index)
        part = table.part(index)
        axes = values[axis_base:axis_base+part.axis_count]
        weights = np.empty((2*part.axis_count, 2))
        weights[::2] = np.maximum(-axes[:, ::-1], 0)
        weights[1::2] = np.maximum(axes, 0)
        if isinstance(part, Composite):
            base = axis_base+part.axis_count
            if len(part.master_rows):
                rows = base+part.master_rows
                values[rows] = add(values[rows], np.repeat(part.master_values[:, None], 2, axis=1))
            for col, weight in enumerate(weights):
                first, last = map(int, part.column_starts[col:col+2])
                rows = base+part.extreme_rows[first:last]
                if len(rows):
                    values[rows] = add(values[rows], scale(weight, part.extreme_values[first:last]))
            for child, _, axis_row in part.subparts:
                visit(child, base+axis_row, depth+1)
        else:
            # Ignore source paths the documented renderer does not emit.
            mask = []
            start = 0
            for size in part.path_sizes:
                mask.extend(start+i for i, kind in enumerate(part.blends[start:start+size])
                            if size >= 3 and kind == 0)
                start += size
            if mask:
                result = np.repeat(part.master[mask, 0, None], 2, axis=1)
                for col, weight in enumerate(weights):
                    result = add(result, scale(weight, part.delta[col, mask, 0]))
                factors.extend(result)
        active.remove(index)
    visit(gid, 0, 0)
    return np.asarray(factors).reshape(-1, 2)


def certify_no_type0_contacts(table, gid, *, max_depth=12, max_boxes=8192):
    require(type(max_depth) is int and 0 <= max_depth <= 30 and
            type(max_boxes) is int and max_boxes > 0, 'invalid_clamp_bound_budget')
    count = table.part(gid).axis_count
    queue = [(np.tile([-1., 1.], (count, 1)), 0)]
    accepted, unresolved, visits = [], [], 0
    factors = 0
    while queue and visits < max_boxes:
        bounds, depth = queue.pop(); visits += 1
        intervals = raw_curve_bounds(table, gid, bounds); factors = len(intervals)
        if np.all((intervals[:, 0] > 0) & (intervals[:, 1] < 1)):
            accepted.append(intervals)
        elif depth >= max_depth:
            unresolved.append(bounds)
        else:
            axis = int(np.argmax(bounds[:, 1]-bounds[:, 0]))
            middle = sum(bounds[axis])/2
            left, right = bounds.copy(), bounds.copy()
            left[axis, 1] = right[axis, 0] = middle
            queue.extend(((right, depth+1), (left, depth+1)))
    unresolved.extend(bounds for bounds, _ in queue)
    proved = not unresolved
    result = dict(proved_absent=proved, curve_factors=factors, boxes_visited=visits,
                  accepted_boxes=len(accepted), unresolved_boxes=len(unresolved),
                  domain='entire_post_avar_root_cube', arithmetic='outward_rounded_binary64_intervals')
    if proved and factors:
        result.update(lower=min(float(a[:, 0].min()) for a in accepted),
                      upper=max(float(a[:, 1].max()) for a in accepted))
    return result
