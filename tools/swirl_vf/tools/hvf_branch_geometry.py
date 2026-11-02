"""Identify interpolation regimes from the actual batched HVF evaluator.

Signatures have stable source-node/axis/path/segment identities. They describe
axis extrema, Type-0 clamping and Type-2 segment projection in local coordinates,
not outlines rounded into an inferred root-space grid. No source data is edited.
"""
from __future__ import annotations
import numpy as np
from hvf import require


def regimes(table, batch):
    require(batch.trace is not None, 'HVF_branch_trace_required')
    keys, values, states = [], [], []
    def append(key, raw, clamp=False):
        require(np.isfinite(raw).all(), 'nonfinite_HVF_branch_parameter')
        keys.append(key); values.append(raw)
        states.append((raw > 0).astype(np.int8) + (raw >= 1).astype(np.int8)
                      if clamp else np.sign(raw).astype(np.int8))
    for node in batch.trace:
        for axis in range(node.axes.shape[1]):
            append((node.part_index, node.tree_part_offset, 'axis', axis), node.axes[:,axis])
        if node.shape_coordinates is None: continue
        part = table.part(node.part_index)
        start = 0
        for path, size in enumerate(part.path_sizes):
            data = node.shape_coordinates[:,start:start+size]
            for i, kind in enumerate(part.blends[start:start+size]):
                if size < 3 or kind not in (0,2): continue
                if kind == 0: parameter = data[:,i,0]
                else:
                    origin = data[:,i-1,2:4]
                    direction = data[:,i,2:4]-origin
                    scale = np.max(np.abs(direction), axis=1)
                    require((scale > 0).all(), 'collapsed_HVF_projection_branch')
                    unit = direction/scale[:,None]
                    parameter = np.sum((data[:,i,:2]-origin)*unit,axis=1) / np.sum(unit*unit,axis=1) / scale
                append((node.part_index,node.tree_part_offset,'curve' if kind==0 else 'tangent',path,i),
                       parameter, True)
            start += size
    shape = (batch.sample_count,0)
    return (tuple(keys), np.stack(values,axis=1) if values else np.empty(shape),
            np.stack(states,axis=1) if states else np.empty(shape,dtype=np.int8))
