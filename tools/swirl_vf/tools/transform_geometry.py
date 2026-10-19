"""Sparse HVF rigid-transform interpolation, calibrated on original native tests.

A row is master * extreme_0**weight_0 * ... in stored column order.
A fractional rigid transform follows its rotation centre, not a straight-line
translation. This helper changes no source coordinate, axis or error budget.
The same float64 function serves scalar and batch evaluators.
"""
from __future__ import annotations
import numpy as np


def fractional_translation(translation, angle: float, weights):
    """Translation of a fractional planar rigid transform, including theta=0.

    sin(w*theta/2)/sin(theta/2) R((w-1)*theta/2) t. The sinc expression
    avoids cancellation at small angles, and has the translation-only limit w*t.
    Internal HVF weights may exceed one; they must not be clipped here.
    """
    t = np.asarray(translation, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    if t.shape != (2,) or not np.isfinite(t).all() or not np.isfinite(angle) or not np.isfinite(w).all():
        raise ValueError('invalid rigid-transform input')
    half = angle / 2
    ratio = w * np.sinc(w * half / np.pi) / np.sinc(half / np.pi)
    phase = (w - 1) * half
    c, s = np.cos(phase), np.sin(phase)
    result = np.stack((c * t[0] - s * t[1], s * t[0] + c * t[1]), axis=-1) * ratio[..., None]
    if not np.isfinite(result).all():
        raise ValueError('nonfinite fractional rigid transform')
    return result


def blend_transform_rows(part, weights):
    """Return sparse row -> (..., tx/ty/angle), without mutating any input."""
    w = np.asarray(weights, dtype=np.float64)
    if w.ndim not in (1, 2) or w.shape[-1] != 2 * part.axis_count or not np.isfinite(w).all():
        raise ValueError('invalid extremum weights')
    master, extremes = {}, {}
    for record, section in ((part.translations, slice(0, 2)), (part.rotations, slice(2, 3))):
        for row, vector in zip(record.master_rows, record.master_values):
            master.setdefault(int(row), np.zeros(3))[section] += vector
        for (row, col), vector in zip(record.extreme_indices, record.extreme_values):
            extremes.setdefault(int(row), {}).setdefault(int(col), np.zeros(3))[section] += vector
    result = {}
    for row in sorted(master.keys() | extremes.keys()):
        current = np.broadcast_to(master.get(row, np.zeros(3)), (*w.shape[:-1], 3)).copy()
        for column, value in sorted(extremes.get(row, {}).items()):
            weight = w[..., column]
            delta = fractional_translation(value[:2], float(value[2]), weight)
            c, s = np.cos(current[..., 2]), np.sin(current[..., 2])
            current[..., 0] += c * delta[..., 0] - s * delta[..., 1]
            current[..., 1] += s * delta[..., 0] + c * delta[..., 1]
            current[..., 2] += weight * value[2]
        if not np.isfinite(current).all():
            raise ValueError('nonfinite blended rigid transform')
        result[row] = current
    return result
