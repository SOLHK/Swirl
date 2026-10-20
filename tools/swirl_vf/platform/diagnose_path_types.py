"""Explain raw L/Q differences without changing the strict geometry gate.

Raw control points remain in private Python objects. ``diagnose_paths`` returns
only counts, segment indices, types and scalar discrepancies. It never returns
an outline or accepts a mapping. The existing canonicalizer/comparator executes
unchanged and its result is retained even when a separate curve bound is small.

Primary reference reviewed: fontTools' ``misc/bezierTools.py`` quadratic bounds
(https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/misc/bezierTools.py).
This independent diagnostic uses exact rational arithmetic on supplied binary64
coordinates, including derivative roots, then rounds its reported upper bounds
outward. It does not sample curves or copy the upstream implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math

import numpy as np

from calibrate_hvf_geometry import LIMIT, discrepancy, linear, segment


@dataclass(frozen=True, repr=False)
class RawSegment:
    """Private geometry. ``L`` has start/end; ``Q`` has start/control/end."""

    kind: str
    points: tuple

    def __post_init__(self):
        count = {"L": 2, "Q": 3}.get(self.kind)
        if count is None or len(self.points) != count:
            raise ValueError("invalid_raw_segment")
        values = tuple(tuple(float(v) for v in point) for point in self.points)
        if any(len(point) != 2 or not all(math.isfinite(v) for v in point) for point in values):
            raise ValueError("nonfinite_or_invalid_raw_point")
        object.__setattr__(self, "points", values)


def raw_portable_paths(paths):
    result = []
    for points in paths:
        if len(points) % 2:
            raise ValueError("odd_portable_point_count")
        pairs = np.asarray(points, dtype=float).reshape(-1, 2, 2)
        result.append([RawSegment("Q", (pair[0], pair[1], pairs[(i + 1) % len(pairs), 0]))
                       for i, pair in enumerate(pairs)])
    return result


def raw_native_paths(events):
    """Retain explicit L/Q controls and the existing close-segment policy."""
    arities = {"begin_part": 1, "end_part": 1, "begin_path": 0, "end_path": 0,
               "close": 0, "stop": 0, "move": 2, "line": 2, "quad": 4, "cubic": 6}
    paths, parts = [], []
    current = start = previous = None
    for item in events:
        if not isinstance(item, (list, tuple)) or not item or item[0] not in arities:
            raise ValueError("unknown_native_event")
        kind = item[0]
        if len(item) != arities[kind] + 1:
            raise ValueError("invalid_native_event_arity")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                   for v in item[1:]):
            raise ValueError("invalid_native_event_number")
        if kind == "begin_part":
            if type(item[1]) is not int or item[1] < 0:
                raise ValueError("invalid_native_part_id")
            parts.append(item[1])
        elif kind == "end_part":
            if not parts or parts.pop() != item[1]:
                raise ValueError("unbalanced_native_parts")
        elif kind == "begin_path":
            if current is not None:
                raise ValueError("nested_native_path")
            current, start, previous = [], None, None
        elif kind == "move":
            if current is None or start is not None:
                raise ValueError("invalid_native_move")
            start = previous = np.asarray(item[1:], dtype=float)
        elif kind in ("line", "quad"):
            if current is None or start is None:
                raise ValueError("native_segment_without_move")
            point = np.asarray(item[-2:], dtype=float)
            values = (previous, point) if kind == "line" else (previous, item[1:3], point)
            current.append(RawSegment("L" if kind == "line" else "Q", values))
            previous = point
        elif kind == "cubic":
            raise ValueError("native_cubic_needs_separate_correspondence")
        elif kind == "close":
            if current is None or start is None:
                raise ValueError("native_close_without_move")
            if np.linalg.norm(previous - start) > 1e-10:
                current.append(RawSegment("L", (previous, start)))
                previous = start
        elif kind == "end_path":
            if current is None:
                raise ValueError("native_path_end_without_begin")
            if current and np.linalg.norm(previous - start) > 1e-8:
                raise ValueError("native_path_not_closed")
            if current:
                paths.append(current)
            current = start = previous = None
    if current is not None or parts:
        raise ValueError("native_unclosed_event_stream")
    return paths


def raw_coretext_paths(commands):
    events, opened = [], False
    for command in commands:
        if not isinstance(command, (list, tuple)) or not command:
            raise ValueError("invalid_coretext_command")
        name, *values = command
        if name == "moveTo":
            if opened or len(values) != 2:
                raise ValueError("invalid_coretext_move")
            events.extend([["begin_path"], ["move", *values]])
            opened = True
        elif name in ("lineTo", "qCurveTo", "curveTo"):
            kind, count = {"lineTo": ("line", 2), "qCurveTo": ("quad", 4),
                           "curveTo": ("cubic", 6)}[name]
            if not opened or len(values) != count:
                raise ValueError("invalid_coretext_segment")
            events.append([kind, *values])
        elif name == "closePath":
            if not opened or values:
                raise ValueError("invalid_coretext_close")
            events.extend([["close"], ["end_path"]])
            opened = False
        else:
            raise ValueError("unknown_coretext_command")
    if opened:
        raise ValueError("unclosed_coretext_contour")
    return raw_native_paths(events)


def canonical_paths(paths):
    """Run the exact existing L/Q canonicalizer without discarding raw inputs."""
    result = []
    for path in paths:
        converted = []
        for item in path:
            p, r = np.asarray(item.points[0]), np.asarray(item.points[-1])
            q = (p + r) / 2 if item.kind == "L" else np.asarray(item.points[1])
            converted.append(segment(p, q, r))
        result.append(converted)
    return result


def _upper(value):
    """Smallest enclosing binary64 at or above a nonnegative rational."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("diagnostic_bound_overflow")
    return math.nextafter(result, math.inf) if Fraction(result) < value else result


def _quadratic(item):
    values = [tuple(Fraction(v) for v in point) for point in item.points]
    if item.kind == "L":
        # Degree elevation is exact in this separate parametric diagnostic.
        # A collinear Q with another control point retains its parameter speed.
        values.insert(1, tuple((p + r) / 2 for p, r in zip(values[0], values[1])))
    return values


def _difference(left, right):
    """Exact max_t ||left(t)-right(t)||_inf, t in [0,1]."""
    lhs, rhs = _quadratic(left), _quadratic(right)
    maximum = Fraction(0)
    for axis in range(2):
        d0, d1, d2 = [p[axis] - q[axis] for p, q in zip(lhs, rhs)]
        maximum = max(maximum, abs(d0), abs(d2))
        a, b = d0 - 2 * d1 + d2, 2 * (d1 - d0)
        if a:
            t = -b / (2 * a)
            if 0 < t < 1:
                maximum = max(maximum, abs((a * t + b) * t + d0))
    return maximum


def _endpoint_difference(left, right):
    return max(abs(Fraction(a) - Fraction(b))
               for p, q in ((left.points[0], right.points[0]), (left.points[-1], right.points[-1]))
               for a, b in zip(p, q))


def _shape_diagnostics(item):
    p, q, r = _quadratic(item)
    d, v = tuple(b - a for a, b in zip(p, r)), tuple(b - a for a, b in zip(p, q))
    squared = sum(a * a for a in d)
    cross = d[0] * v[1] - d[1] * v[0]
    projection = sum(a * b for a, b in zip(d, v)) / squared if squared else None
    floating = [np.asarray([float(v) for v in point]) for point in (p, q, r)]
    return {
        "legacy_linear": bool(linear(*floating)),
        "legacy_short_chord_branch": float(np.dot(floating[2] - floating[0], floating[2] - floating[0])) < 1e-20,
        "exact_collinearity": cross == 0,
        "control_projection_inside_chord": projection is not None and 0 <= projection <= 1,
        "control_line_distance_squared_upper_bound": _upper(cross * cross / squared) if squared else None,
        "same_parameter_chord_difference_upper_bound": _upper(_difference(item, RawSegment("L", (item.points[0], item.points[-1])))),
    }


def diagnose_paths(left, right, endpoint_limit=LIMIT):
    """Return safe evidence; no pass override, reversed paths or segment merges.

    Correspondence requires exactly one orientation-preserving cyclic shift
    whose segment endpoints all lie within ``endpoint_limit``. Ambiguous or
    absent correspondence yields no curve bound. The bound is parametric, not
    a claim about optimal reparameterization or continuous axis-space behavior.
    """
    if not math.isfinite(endpoint_limit) or endpoint_limit < 0:
        raise ValueError("invalid_endpoint_limit")
    result = {"diagnostic_only": True, "mapping_accepted": False,
              "raw_geometry_published": False, "orientation_reversal_allowed": False,
              "left_path_count": len(left), "right_path_count": len(right),
              "endpoint_correspondence_limit": endpoint_limit, "paths": [],
              "maximum_parametric_difference_upper_bound": None}
    left_canonical, right_canonical = canonical_paths(left), canonical_paths(right)
    try:
        error, count = discrepancy(left_canonical, right_canonical)
        result["unchanged_strict_comparison"] = {"status": "within_budget" if error <= LIMIT else "outside_budget",
            "maximum_point_error": error, "tested_segments": count, "limit": LIMIT}
    except ValueError as error:
        result["unchanged_strict_comparison"] = {"status": "rejected", "reason": str(error), "limit": LIMIT}
    if len(left) != len(right):
        result["correspondence_status"] = "path_count_differs"
        return result
    complete, maximum = True, Fraction(0)
    for path_index, (lhs, rhs) in enumerate(zip(left, right)):
        row = {"path_index": path_index, "left_segments": len(lhs), "right_segments": len(rhs)}
        result["paths"].append(row)
        if len(lhs) != len(rhs):
            row["status"], complete = "segment_count_differs", False
            continue
        if not lhs:
            row.update(status="empty", maximum_parametric_difference_upper_bound=0.)
            continue
        candidates = []
        minimum = None
        for shift in range(len(lhs)):
            error = max(_endpoint_difference(item, rhs[(i + shift) % len(rhs)]) for i, item in enumerate(lhs))
            minimum = error if minimum is None else min(minimum, error)
            if error <= Fraction(endpoint_limit):
                candidates.append((shift, error))
        row.update(endpoint_candidate_count=len(candidates), minimum_endpoint_error_upper_bound=_upper(minimum))
        if len(candidates) != 1:
            row["status"] = "endpoint_correspondence_ambiguous" if candidates else "endpoint_correspondence_absent"
            complete = False
            continue
        shift, endpoint_error = candidates[0]
        row.update(status="unique_forward_endpoint_correspondence", right_cyclic_shift=shift,
                   endpoint_error_upper_bound=_upper(endpoint_error), type_differences=[])
        path_maximum = Fraction(0)
        for index, item in enumerate(lhs):
            other_index = (index + shift) % len(rhs)
            other = rhs[other_index]
            difference = _difference(item, other)
            path_maximum = max(path_maximum, difference)
            kinds = left_canonical[path_index][index][0], right_canonical[path_index][other_index][0]
            if item.kind != other.kind or kinds[0] != kinds[1]:
                row["type_differences"].append({"left_segment_index": index, "right_segment_index": other_index,
                    "left_raw_kind": item.kind, "right_raw_kind": other.kind,
                    "left_canonical_kind": kinds[0], "right_canonical_kind": kinds[1],
                    "parametric_difference_upper_bound": _upper(difference),
                    "left_shape": _shape_diagnostics(item), "right_shape": _shape_diagnostics(other)})
        row["maximum_parametric_difference_upper_bound"] = _upper(path_maximum)
        maximum = max(maximum, path_maximum)
    result["correspondence_status"] = "complete" if complete else "incomplete"
    if complete:
        result["maximum_parametric_difference_upper_bound"] = _upper(maximum)
    return result


def _preserved_legacy_result(left, right):
    """Capture the unmodified canonical comparator, without hiding a failure."""
    result = {"limit": LIMIT, "maximum_point_error": None, "tested_segments": None}
    try:
        error, count = discrepancy(left, right)
        if not math.isfinite(error) or error < 0:
            result.update(status="rejected", reason="nonfinite_legacy_difference")
        else:
            result.update(status="within_budget" if error <= LIMIT else "outside_budget",
                          maximum_point_error=error, tested_segments=count)
    except ValueError as error:
        result.update(status="rejected", reason=str(error))
    return result


def _preserved_quadratic_cycle(left, right, left_canonical, right_canonical):
    """Recover only original Q/Q controls at a canonical type mismatch."""
    best = None
    valid_candidates = 0
    for shift in range(len(left)):
        maximum, restored = 0., []
        for index, (kind, values) in enumerate(left_canonical):
            other_index = (index + shift) % len(right)
            other_kind, other_values = right_canonical[other_index]
            if kind == other_kind:
                error = float(np.abs(values - other_values).max())
            else:
                lhs, rhs = left[index], right[other_index]
                if lhs.kind != "Q" or rhs.kind != "Q":
                    break
                # Compare all six original coordinates, not the curve's sampled
                # positions, its parametric bound, or degree-elevated lines.
                # Exact binary64 differences round outward, so this new branch
                # cannot round a value just above the fixed gate down onto it.
                error = _upper(max(abs(Fraction(a) - Fraction(b))
                    for p, q in zip(lhs.points, rhs.points) for a, b in zip(p, q)))
                restored.append({"left_segment_index": index, "right_segment_index": other_index,
                    "left_raw_kind": "Q", "right_raw_kind": "Q",
                    "left_canonical_kind": kind, "right_canonical_kind": other_kind,
                    "maximum_control_point_error": error})
            if not math.isfinite(error) or error < 0:
                break
            maximum = max(maximum, error)
        else:
            valid_candidates += 1
            if best is None or maximum < best[0]:
                best = maximum, shift, restored
    if best is None:
        return {"status": "rejected", "reason": "raw_segment_types_differ",
                "maximum_point_error": None, "tested_segments": None,
                "valid_forward_candidates": 0, "restored_segments": []}
    error, shift, restored = best
    return {"status": "within_budget" if error <= LIMIT else "outside_budget",
            "maximum_point_error": error, "tested_segments": len(left),
            "right_cyclic_shift": shift, "valid_forward_candidates": valid_candidates,
            "restored_segments": restored}


def compare_preserved_quadratics(left, right):
    """Compare contours while retaining raw-Q evidence for type-only failures.

    The old comparison remains in ``legacy`` and in every path's ``legacy``.
    An old numeric failure never enters the recovery branch. Only a contour
    rejected for ``segment_types_differ`` can recover original Q/Q controls;
    canonical-matching segments keep the old fields and error calculation.
    Original L/Q mismatches are never degree-elevated or reparameterized.

    This is a finite outline/control-point result. It does not accept a user-axis
    mapping, metrics, an entire font, or continuous-space reconstruction.
    """
    left_canonical, right_canonical = canonical_paths(left), canonical_paths(right)
    legacy = _preserved_legacy_result(left_canonical, right_canonical)
    result = {"status": "rejected", "maximum_point_error": None, "limit": LIMIT,
              "legacy": legacy, "paths": [], "restored_segments": [],
              "restored_segment_count": 0, "tested_segments": None,
              "mapping_accepted": False, "raw_geometry_published": False,
              "orientation_reversal_allowed": False,
              "restored_control_error_arithmetic": "exact_binary64_difference_rounded_up"}
    if len(left) != len(right):
        result["reason"] = "path_count_differs"
        return result
    errors, rejected, tested = [], [], 0
    for path_index, (lhs, rhs, lc, rc) in enumerate(zip(left, right, left_canonical, right_canonical)):
        prior = _preserved_legacy_result([lc], [rc])
        if prior["status"] == "rejected" and prior.get("reason") == "segment_types_differ":
            current = _preserved_quadratic_cycle(lhs, rhs, lc, rc)
            current["method"] = "preserved_raw_quadratic_controls"
        else:
            current = {**prior, "method": "legacy_unchanged", "restored_segments": []}
        current["limit"] = LIMIT
        result["paths"].append({"path_index": path_index, "legacy": prior, "raw_control": current})
        result["restored_segments"].extend({"path_index": path_index, **entry}
                                             for entry in current["restored_segments"])
        if current["status"] == "rejected":
            rejected.append(current["reason"])
        else:
            errors.append(current["maximum_point_error"])
            tested += current["tested_segments"]
    result["restored_segment_count"] = len(result["restored_segments"])
    if rejected:
        result["reason"] = rejected[0]
    else:
        error = max(errors, default=0.)
        result.update(status="within_budget" if error <= LIMIT else "outside_budget",
                      maximum_point_error=error, tested_segments=tested)
    return result
