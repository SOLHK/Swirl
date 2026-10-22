"""Predeclared observations for testing distant native construction anchors.

The caller supplies all original fvar ranges. These cases are diagnostic inputs,
not a coordinate mapping, anchor-selection policy, or font acceptance result.
No source glyphs, outlines, or avar records are embedded in this module.
"""
from __future__ import annotations

from collections.abc import Mapping
import itertools
import math
import random


TAGS = ("WDTH", "wght", "HGHT")
SELECTED_FACES = (0, 5, 10, 15, 20, 24, 31)
RANDOM_SEED = 20861020


def anchor_cases(ranges_by_face):
    """Return ``{face: rows}`` for seven independently observed physical faces.

    Each input face maps the three original tags to (minimum, default, maximum).
    Rows contain label/location/cohort; exact duplicate locations keep the first
    label and preserve additional labels/cohorts as aliases. Out-of-range probe
    candidates are omitted, never clamped. Invalid input ranges are rejected.
    """
    if (not isinstance(ranges_by_face, Mapping)
            or set(ranges_by_face) != set(range(32))
            or any(type(face) is not int for face in ranges_by_face)):
        raise ValueError("all_original_physical_faces_required")
    verified = {}
    for face, axes in ranges_by_face.items():
        if not isinstance(axes, Mapping) or set(axes) != set(TAGS):
            raise ValueError("all_original_axis_tags_required")
        ranges = {}
        for tag in TAGS:
            values = axes[tag]
            if (not isinstance(values, (tuple, list)) or len(values) != 3
                    or any(type(value) not in (int, float) for value in values)):
                raise ValueError("invalid_source_axis_range")
            try:
                low, default, high = (float(value) for value in values)
            except (OverflowError, ValueError):
                raise ValueError("invalid_source_axis_range") from None
            if (not all(math.isfinite(value) for value in (low, default, high))
                    or not low <= default <= high or not low < high
                    or not math.isfinite(high - low)):
                raise ValueError("invalid_source_axis_range")
            ranges[tag] = (low, default, high)
        verified[face] = ranges

    result = {}
    for face in SELECTED_FACES:
        ranges = verified[face]
        defaults = {tag: ranges[tag][1] for tag in TAGS}
        rows, seen = [], {}

        def add(label, updates, cohort):
            location = {**defaults, **updates}
            if any(not math.isfinite(location[tag])
                   or not ranges[tag][0] <= location[tag] <= ranges[tag][2] for tag in TAGS):
                return
            key = tuple(location[tag] for tag in TAGS)
            if key in seen:
                previous = seen[key]
                if label not in previous["labels"]:
                    previous["labels"].append(label)
                if cohort not in previous["cohorts"]:
                    previous["cohorts"].append(cohort)
                return
            row = {"label": label, "location": location, "cohort": cohort,
                   "labels": [label], "cohorts": [cohort]}
            rows.append(row)
            seen[key] = row

        add("default", {}, "baseline")
        names = ("minimum", "default", "maximum")
        for indices in itertools.product(range(3), repeat=3):
            label = "corner_" + "_".join(f"{tag}_{names[index]}" for tag, index in zip(TAGS, indices))
            add(label, {tag: ranges[tag][index] for tag, index in zip(TAGS, indices)}, "corners")

        for weight in (399.9, 399.96, 399.9601, 400., 400.0399, 400.04, 400.0401, 400.1):
            add(f"weight_400_boundary_{weight:.10g}", {"wght": weight}, "400_boundaries")
        for weight in (299.96, 299.9817, 300., 300.0062, 300.01, 300.03, 300.04):
            add(f"weight_300_control_{weight:.10g}", {"wght": weight}, "300_controls")

        for tag in TAGS:
            low, default, high = ranges[tag]
            for offset in (.0001, .01, .06):
                for side, direction in (("below", -1), ("above", 1)):
                    add(f"{tag}_default_{side}_{offset:g}", {tag: default + direction * offset}, "near_defaults")
            midpoint = low + (high - low) / 2
            for side, offset in (("below", -.0001), ("exact", 0.), ("above", .0001)):
                add(f"{tag}_midpoint_{side}", {tag: midpoint + offset}, "anchor_midpoints")

            # A normalized16 step uses the corresponding original fvar half-span.
            # If default is an endpoint, the inward direction uses the only
            # nonempty half-span. Nextafter is applied to the final user value.
            lower_span = default - low if default > low else high - default
            upper_span = high - default if high > default else default - low
            for end, user in (("minimum", low + lower_span / 65536),
                              ("maximum", high - upper_span / 65536)):
                for side, value in (("left", math.nextafter(user, -math.inf)),
                                    ("exact", user), ("right", math.nextafter(user, math.inf))):
                    add(f"{tag}_{end}_inward_normalized16_{side}", {tag: value}, "endpoint_neighbours")

        rng = random.Random(RANDOM_SEED + face)
        for index in range(6):
            add(f"random_triple_{index}", {tag: rng.uniform(ranges[tag][0], ranges[tag][2])
                                          for tag in TAGS}, "random_triples")
        for index in range(6):
            add(f"random_weight_{index}", {"wght": rng.uniform(ranges["wght"][0], ranges["wght"][2])}, "random_weights")
        for weight in (299.9817, 300.01, 399.96, 400.01, 400.04, 400.041, 500.01):
            add(f"mixed_axes_{weight:.10g}", {"WDTH": 600.5859375, "wght": weight, "HGHT": 250.}, "mixed_axes")
        result[face] = rows
    return result
