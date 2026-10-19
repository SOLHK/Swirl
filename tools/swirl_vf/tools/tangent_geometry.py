"""Bounded HVF curve/corner/isolated-tangent evaluation after interpolation.

Type 2 uses orthogonal projection onto the line through the two neighbouring
quadratic control points. This rule was inferred from 22 independently executed
Apple libhvf experiments using ONLY self-authored geometry. Agreement on those
experiments does not prove every Apple glyph or degenerate case is supported.
Types 3/4 and a collapsed Type-2 control line remain explicit errors.

Input is one path (segments, 4), or batches (..., segments, 4), in the original
shape coordinate system. No boolean operation, rounding, faux weight or scale
is applied here. This operation is nonlinear in the interpolated coordinates.
"""
from __future__ import annotations

import numpy as np


class TangentGeometryError(ValueError):
    """Geometry requires an unsupported or numerically undefined interpretation."""


def resolve_path(segments, blends) -> np.ndarray:
    data = np.asarray(segments, dtype=np.float64)
    tags = tuple(blends)
    if data.ndim < 2 or data.shape[-1] != 4 or data.shape[-2] != len(tags):
        raise TangentGeometryError('expected (..., segment_count, 4) coordinates')
    if data.size > 8_000_000 or not np.isfinite(data).all():
        raise TangentGeometryError('nonfinite or excessive path coordinates')
    if any(type(tag) is not int or tag not in (0, 1, 2) for tag in tags):
        raise TangentGeometryError('only curve, corner and isolated Type-2 tangents are supported')
    result = data.copy()
    controls = data[..., 2:4]
    for index, tag in enumerate(tags):
        if tag == 0:
            factor = data[..., index, 0, None]
            result[..., index, :2] = ((1-factor) * controls[..., index-1, :]
                                      + factor * controls[..., index, :])
        elif tag == 2:
            origin = controls[..., index-1, :]
            direction = controls[..., index, :] - origin
            # Normalising by the largest component avoids square overflow and
            # underflow. No arbitrary epsilon discards a valid short tangent.
            scale = np.max(np.abs(direction), axis=-1, keepdims=True)
            if not np.isfinite(direction).all() or np.any(scale == 0):
                raise TangentGeometryError('collapsed or overflowing isolated-tangent control line')
            unit = direction / scale
            displacement = data[..., index, :2] - origin
            parameter = (np.sum(displacement * unit, axis=-1, keepdims=True)
                         / np.sum(unit * unit, axis=-1, keepdims=True))
            result[..., index, :2] = origin + parameter * unit
    if not np.isfinite(result).all():
        raise TangentGeometryError('nonfinite resolved geometry')
    return result.reshape(*data.shape[:-2], -1, 2)
