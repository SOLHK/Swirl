"""Extend the unchanged archived axis requests with independent observations.

Only requested coordinates and provenance labels are returned. No glyph data,
inferred mapping or observed native result selects a position. Archive rows are
never deduplicated; a new probe at an existing coordinate adds labels to its
first occurrence. This is an observation plan, not font acceptance.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import itertools
import math
import random

from calibrate_avar_metrics import requests_for


TAGS = ("WDTH", "wght", "HGHT")
RANDOM_SEED = 20961020
FRESH_TRIPLES_PER_FACE = 8
ARCHIVE_GIDS = (5, 12, 56, 169)


def _ranges(fonts):
    if (not isinstance(fonts, Sequence) or isinstance(fonts, (str, bytes))
            or len(fonts) != 32):
        raise ValueError("all_original_physical_faces_required")
    result = {}
    for face, font in enumerate(fonts):
        try:
            axes = font["fvar"].axes
            tags = [axis.axisTag for axis in axes]
        except (KeyError, AttributeError, TypeError):
            raise ValueError("all_original_axis_tags_required") from None
        if len(tags) != 3 or set(tags) != set(TAGS):
            raise ValueError("all_original_axis_tags_required")
        ranges = {}
        for axis in axes:
            try:
                values = (axis.minValue, axis.defaultValue, axis.maxValue)
            except AttributeError:
                raise ValueError("invalid_source_axis_range") from None
            if any(type(value) not in (int, float) for value in values):
                raise ValueError("invalid_source_axis_range")
            try:
                low, default, high = map(float, values)
            except (OverflowError, ValueError):
                raise ValueError("invalid_source_axis_range") from None
            if (not all(math.isfinite(value) for value in (low, default, high))
                    or not low <= default <= high or not low < high
                    or not math.isfinite(high - low)):
                raise ValueError("invalid_source_axis_range")
            ranges[axis.axisTag] = (low, default, high)
        result[face] = ranges
    return result


def _valid_location(location, ranges):
    if not isinstance(location, Mapping) or set(location) != set(TAGS):
        return False
    for tag in TAGS:
        value = location[tag]
        if type(value) not in (int, float):
            return False
        try:
            if not math.isfinite(value) or not ranges[tag][0] <= value <= ranges[tag][2]:
                return False
        except OverflowError:
            return False
    return True


def closure_cases(fonts):
    """Return all 32 physical faces' archived rows followed by extra probes.

    ``requests_for(fonts)`` is called once, unchanged, to retain its old random
    sequence, request IDs, coordinates, order and duplicate observations. Each
    archived row has ``archive_id`` and ``archive_global_request_id`` equal to
    the original string request ID, and a zero-based face-local
    ``archive_position_index``. The caller verifies the exact source identity
    and its expected 3,048 archive rows; authored test fonts may have a different
    number of avar knots and therefore a different archive count.

    All rows have location/label/labels/cohort/cohorts. Additional out-of-range
    probes are omitted, never clamped; malformed archive rows are rejected.
    Glyph selection belongs to the driver and is not changed by this module.
    """
    ranges_by_face = _ranges(fonts)
    result = {face: [] for face in range(32)}
    seen = {face: {} for face in range(32)}
    archive = requests_for(fonts)
    if not isinstance(archive, list) or not archive:
        raise ValueError("archive_request_sequence_required")
    previous_face = -1
    for ordinal, request in enumerate(archive):
        if (not isinstance(request, Mapping)
                or set(request) != {"request_id", "face_index", "location", "glyph_ids"}
                or type(request["request_id"]) is not str
                or request["request_id"] != str(ordinal)
                or type(request["face_index"]) is not int
                or request["face_index"] not in result
                or request["face_index"] < previous_face
                or request["glyph_ids"] != list(ARCHIVE_GIDS)):
            raise ValueError("archive_request_identity_or_order_changed")
        face = request["face_index"]
        previous_face = face
        if not _valid_location(request["location"], ranges_by_face[face]):
            raise ValueError("invalid_archived_axis_location")
        request_id = request["request_id"]
        label = "archive_" + request_id
        row = {"label": label, "labels": [label], "cohort": "archive",
               "cohorts": ["archive"], "location": dict(request["location"]),
               "archive_id": request_id, "archive_global_request_id": request_id,
               "archive_position_index": len(result[face])}
        result[face].append(row)
        # Keep every archived duplicate, but attach future aliases only to the
        # first one. Neither the global nor face-local archive ordinal changes.
        seen[face].setdefault(tuple(row["location"][tag] for tag in TAGS), row)
    if any(not rows for rows in result.values()):
        raise ValueError("archive_all_physical_faces_required")

    for face, rows in result.items():
        ranges = ranges_by_face[face]
        defaults = {tag: ranges[tag][1] for tag in TAGS}

        def add(label, updates, cohort):
            location = {**defaults, **updates}
            if not _valid_location(location, ranges):
                return
            key = tuple(location[tag] for tag in TAGS)
            if key in seen[face]:
                existing = seen[face][key]
                if label not in existing["labels"]:
                    existing["labels"].append(label)
                if cohort not in existing["cohorts"]:
                    existing["cohorts"].append(cohort)
                return
            row = {"label": label, "labels": [label], "cohort": cohort,
                   "cohorts": [cohort], "location": location}
            rows.append(row)
            seen[face][key] = row

        add("default", {}, "baseline")
        names = ("minimum", "default", "maximum")
        for indices in itertools.product(range(3), repeat=3):
            label = "corner_" + "_".join(
                f"{tag}_{names[index]}" for tag, index in zip(TAGS, indices))
            add(label, {tag: ranges[tag][index] for tag, index in zip(TAGS, indices)}, "corners")

        for weight in (299.96, 299.9817, 300., 300.0062, 300.01, 300.03, 300.04):
            add(f"weight_300_control_{weight:.10g}", {"wght": weight}, "300_controls")
        for weight in (399.9, 399.96, 399.9601, 400., 400.01,
                       400.0399, 400.04, 400.0401, 400.1):
            add(f"weight_400_boundary_{weight:.10g}", {"wght": weight}, "400_boundaries")

        for tag in TAGS:
            low, default, high = ranges[tag]
            for offset in (.0001, .01, .06):
                for side, direction in (("below", -1), ("above", 1)):
                    add(f"{tag}_default_{side}_{offset:g}",
                        {tag: default + direction * offset}, "near_defaults")
            midpoint = low + (high - low) / 2
            for side, offset in (("below", -.0001), ("exact", 0.), ("above", .0001)):
                add(f"{tag}_midpoint_{side}", {tag: midpoint + offset}, "anchor_midpoints")

        for weight in (299.9817, 300.01, 399.96, 400.01, 400.04, 400.041, 500.01):
            add(f"mixed_axes_{weight:.10g}",
                {"WDTH": 600.5859375, "wght": weight, "HGHT": 250.}, "mixed_axes")
        add("historical_wdth_readback",
            {"WDTH": 600.5859375, "wght": 368.22259521484375, "HGHT": 975.7080078125},
            "mixed_axes")

        rng = random.Random(RANDOM_SEED + face)
        for index in range(FRESH_TRIPLES_PER_FACE):
            add(f"fresh_triple_{index}",
                {tag: rng.uniform(ranges[tag][0], ranges[tag][2]) for tag in TAGS},
                "fresh_random_triples")
    return result
