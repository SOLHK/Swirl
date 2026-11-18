"""Vectorized exact quadratic degree elevation for existing HVGL batches.

Every source contour and its explicit closing endpoint is retained. The output
uses the same unoptimized rmoveto/rrcurveto stream as cff2_geometry.operands,
without a per-sample pen round trip. No coordinate rounding is performed.
"""
from __future__ import annotations
import numpy as np
from cff2_geometry import require


def cubic_batch(batch):
    operators, paths = [], []
    count = batch.sample_count
    require(type(count) is int and 0 < count <= 1024, 'invalid_cubic_batch_size')
    for path in batch.paths:
        p = np.asarray(path, dtype=float)
        require(p.ndim == 3 and p.shape[0] == count and p.shape[2] == 2
                and p.shape[1] >= 6 and p.shape[1] % 2 == 0 and np.isfinite(p).all(),
                'invalid_HVF_quadratic_path')
        on, off = p[:, ::2], p[:, 1::2]
        end = np.roll(on, -1, axis=1)
        controls = np.stack((on+(off-on)*(2/3), end+(off-end)*(2/3), end), axis=2)
        paths.append(np.concatenate((on[:, :1], controls.reshape(count, -1, 2)), axis=1))
        operators.extend([('rmoveto', 2), *[('rrcurveto', 6)]*on.shape[1]])
    if not paths:
        return (), np.empty((count, 0)), np.empty((count, 0, 2))
    absolute = np.concatenate(paths, axis=1)
    relative = np.diff(absolute, axis=1, prepend=np.zeros((count, 1, 2))).reshape(count, -1)
    return tuple(operators), relative, absolute
