#!/usr/bin/env python3
"""Deterministic observational axis probes, never a fitted mapping policy.

Ranges are supplied from the source's original fvar axes. No font data or avar
records are embedded here. Binary neighbours are taken after constructing the
user coordinate: nextafter of a tiny delta can disappear when added to default.
"""
from __future__ import annotations

import itertools
import math
import random


TAGS = ("WDTH", "wght", "HGHT")


def threshold_cases(axis_ranges, face):
    """Return original user locations for an independent native observation.

    ``axis_ranges`` maps each original tag to (minimum, default, maximum).
    Rows contain ``label``, ``location`` and ``cohort``. Exact duplicate triples
    retain the first label/cohort; ``labels`` and ``cohorts`` retain all aliases.
    No outcome of these probes establishes a production mapping or acceptance.
    """
    if set(axis_ranges) != set(TAGS):
        raise ValueError("all_original_axis_tags_required")
    if isinstance(face, bool) or not isinstance(face, int) or face < 0:
        raise ValueError("invalid_face_index")
    ranges = {}
    for tag in TAGS:
        values = axis_ranges[tag]
        if (len(values) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float))
                or not math.isfinite(v) for v in values)
                or not values[0] <= values[1] <= values[2] or values[0] == values[2]):
            raise ValueError("invalid_source_axis_range")
        ranges[tag] = tuple(float(value) for value in values)
    defaults = {tag: ranges[tag][1] for tag in TAGS}
    result, seen = [], {}

    def add(label, updates, cohort):
        location = {**defaults, **updates}
        if any(not ranges[tag][0] <= location[tag] <= ranges[tag][2] for tag in TAGS):
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
        result.append(row)
        seen[key] = row

    def around_weight(label, value, cohort):
        for suffix, user in (("left", math.nextafter(value, -math.inf)),
                             ("exact", value), ("right", math.nextafter(value, math.inf))):
            add(f"{label}_{suffix}", {"wght": user}, cohort)

    add("default", {}, "baseline")
    names = ("minimum", "default", "maximum")
    for tag in TAGS:
        for index in (0, 2):
            add(f"{tag}_{names[index]}", {tag: ranges[tag][index]}, "baseline")
    for indices in itertools.product(range(3), repeat=3):
        label = "corner_" + "_".join(f"{tag}_{names[index]}" for tag, index in zip(TAGS, indices))
        add(label, {tag: ranges[tag][index] for tag, index in zip(TAGS, indices)}, "corners")

    minimum, default, maximum = ranges["wght"]
    for side, span, direction in (("negative", default - minimum, -1),
                                  ("positive", maximum - default, 1)):
        if span:
            for denominator in (65536, 16384):
                user = default + direction * span / denominator
                around_weight(f"default_{side}_1_over_{denominator}", user, "default_thresholds")
        add(f"default_{side}_decimal_0001", {"wght": default + direction * .0001}, "default_decimal")
    for user in (300., 300.01, 400., 400.01):
        add(f"historical_weight_{user:g}", {"wght": user}, "historical_controls")

    if face in (20, 24, 31):
        for center in (300., 400.):
            for name, delta in (("normalized16", 400 / 65536),
                                ("direct_half14", .5 / (4915 / 100))):
                user = center + delta
                label = f"weight_{center:g}_{name}"
                around_weight(label, user, "targeted_thresholds")
                decimal_bin = math.floor(user * 10000)
                for suffix, index in (("decimal4_lower", decimal_bin),
                                      ("decimal4_upper", decimal_bin + 1)):
                    add(f"{label}_{suffix}", {"wght": index / 10000}, "targeted_thresholds")

    rng = random.Random(20461020 + face)
    for index in range(3):
        add(f"random_triple_{index}", {tag: rng.uniform(ranges[tag][0], ranges[tag][2])
                                      for tag in TAGS}, "random_triples")
    for index in range(3):
        add(f"random_weight_{index}", {"wght": rng.uniform(minimum, maximum)}, "random_weights")
    add("wdth_600_5859375", {"WDTH": 600.5859375}, "wdth_readback")
    return result
