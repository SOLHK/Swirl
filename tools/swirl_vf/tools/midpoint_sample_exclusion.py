"""Conservative exclusion from a declared dyadic refinement sampling protocol.

This is for the midpoint fitter, not the source-aligned atlas. It overapproximates
samples from *every possible* F2DOT14 dyadic box: eighth-grid probes, specified
local jitter stencils, axial midlines and body diagonals (including arbitrary
branch roots and their two neighbours). False negatives are allowed: an
uncertified point is still tested, never silently discarded. A True result
means the point cannot belong to any of these sample families.
"""
from __future__ import annotations
import numpy as np
from cff2_geometry import require


def excluded(points, stencils=()):
    points = np.asarray(points, dtype=float)
    require(points.ndim == 2 and points.shape[1] == 3 and np.isfinite(points).all()
            and np.all(np.abs(points) <= 1), 'invalid_exclusion_positions')
    near_integer = lambda x, tolerance: np.abs(x-np.round(x)) <= tolerance
    grid = np.all(near_integer(points*131072, 1e-7), axis=1)
    # An axial midpoint chord has at least two dyadic coordinates.
    axial = np.sum(near_integer(points*32768, 1e-7), axis=1) >= 2
    # Body diagonal slopes are signed powers of two. Taking both coordinate
    # orders avoids fractions in the constant intercept, which is F2DOT14.
    pair_possible = []
    for left, right in ((0, 1), (0, 2), (1, 2)):
        possible = np.zeros(len(points), dtype=bool)
        for a, b in ((left, right), (right, left)):
            for exponent in range(15):
                for sign in (-1, 1):
                    value = (points[:, a]*(2**exponent)+sign*points[:, b])*16384
                    possible |= near_integer(value, 1e-5)
        pair_possible.append(possible)
    diagonal = np.logical_and.reduce(pair_possible)
    jitter = np.zeros(len(points), dtype=bool)
    for stencil in stencils:
        stencil = np.asarray(stencil)
        require(stencil.ndim == 2 and stencil.shape[1] == 3 and np.isfinite(stencil).all()
                and np.all((stencil >= 0) & (stencil <= 1)), 'invalid_local_refinement_stencil')
        # Independently allowing any stencil member on each axis is a safe
        # superset of the actual three-coordinate local probes.
        component_possible = []
        for axis in range(3):
            possible = np.zeros(len(points), dtype=bool)
            for exponent in range(15):
                for sign in (-1, 1):
                    values = (points[:, axis, None]+sign*(2.**-exponent)*stencil[:, axis])*16384
                    possible |= np.any(near_integer(values, 1e-7), axis=1)
            component_possible.append(possible)
        jitter |= np.logical_and.reduce(component_possible)
    return ~(grid | axial | diagonal | jitter)
