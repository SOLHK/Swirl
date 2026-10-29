#!/usr/bin/env python3
"""Falsifiable user-axis geometry candidates, never a production mapper.

The signed-zero candidate addresses discontinuous raw avar records: quantizing
a nondefault normalized value to zero must not erase which side it approached
from. Its proposed pre-avar F2DOT14 stage is NOT established for Apple HVGL.
In particular, this candidate fails 240 of the existing 3,048 HVAR-inferred
observations. Geometry and HVAR therefore remain independent experiments.

Raw records retain order and duplicates. No exact-knot priority is introduced:
HarfBuzz's extended avar recovery is useful context, but an unsorted record that
it selects can be bypassed by this source's measured CoreText HVAR behavior.
References:
https://learn.microsoft.com/en-us/typography/opentype/spec/avar
https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-ot-var-avar-table.hh
"""
from __future__ import annotations

import math


def _pairs(records):
    pairs = tuple(tuple(pair) for pair in records)
    if len(pairs) < 2 or any(len(pair) != 2 or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not -1 <= value <= 1
            for value in pair) for pair in pairs):
        raise ValueError("invalid_raw_normalized_avar_records")
    return pairs


def _ordered_value(value, records, zero_side=0):
    # zero_side is symbolic: no empirical epsilon or distance threshold is used
    # to approximate either one-sided limit at a discontinuity.
    first_x, first_y = records[0]
    if value < first_x or (value == first_x and zero_side < 0):
        return first_y
    for (start, low), (end, high) in zip(records, records[1:]):
        if value < end or (value == end and zero_side <= 0):
            return high if start == end else low + (value - start) * (high - low) / (end - start)
    return records[-1][1]


def one_sided_zero_limit(records, side):
    """Return the raw-order left/right limit exactly, without moving a knot."""
    if side not in (-1, 1) or isinstance(side, bool):
        raise ValueError("zero_limit_side_must_be_minus_or_plus_one")
    return _ordered_value(0., _pairs(records), zero_side=side)


def trace_signed_zero_raw_order(normalized, records):
    """Describe the unaccepted geometry hypothesis at each numerical stage.

    ``normalized`` must be computed from the original user value and original
    fvar minimum/default/maximum, before any F2DOT14 rounding. Records are raw
    pairs expressed as normalized numbers, e.g. integer F2DOT14 divided by 16384.
    Only an actually zero input takes the explicit default fast path.
    """
    if (isinstance(normalized, bool) or not isinstance(normalized, (int, float))
            or not math.isfinite(normalized) or not -1 <= normalized <= 1):
        raise ValueError("invalid_original_normalized_coordinate")
    pairs = _pairs(records)
    quantized = math.floor(normalized * 16384 + .5) / 16384
    side = 0 if normalized == 0 else -1 if normalized < 0 else 1
    if side == 0:
        mapped = 0.
    elif quantized == 0:
        mapped = _ordered_value(0., pairs, zero_side=side)
    else:
        mapped = _ordered_value(quantized, pairs)
    if not math.isfinite(mapped) or not -1 <= mapped <= 1:
        raise ValueError("candidate_mapped_coordinate_out_of_range")
    final = math.floor(mapped * 16384 + .5)
    return {"original_normalized": normalized, "pre_avar_f2dot14": quantized * 16384,
            "original_side": side, "actual_default": side == 0,
            "one_sided_zero_limit_used": side != 0 and quantized == 0,
            "mapped_before_final_quantization": mapped,
            "final_f2dot14": final, "final_normalized": final / 16384,
            "geometry_acceptance": "NOT_ESTABLISHED",
            "metric_mapping_model": False}


def map_signed_zero_raw_order(normalized, records):
    """Return the candidate coordinate for an independent HVGL comparison."""
    return trace_signed_zero_raw_order(normalized, records)["final_normalized"]


def targeted_user_locations(axis_ranges):
    """Small per-face probe set, including the existing 36 HVAR counterexamples.

    ``axis_ranges`` maps each original tag to (minimum, default, maximum).
    Apply this list to all 32 source faces. On faces 20..31 its width endpoint
    requests cover all 36 old wght=400.01 disagreements; the other faces serve
    as controls. Measurement coverage is independent of the mapping algorithm.
    """
    tags = ("WDTH", "wght", "HGHT")
    if set(axis_ranges) != set(tags):
        raise ValueError("all_original_axis_tags_required")
    for values in axis_ranges.values():
        if (len(values) != 3 or not all(math.isfinite(v) for v in values)
                or not values[0] <= values[1] <= values[2] or values[0] == values[2]):
            raise ValueError("invalid_source_axis_range")
    defaults = {tag: axis_ranges[tag][1] for tag in tags}
    minimum, default, maximum = axis_ranges["wght"]
    result, seen = [], set()
    def add(label, updates):
        location = {**defaults, **updates}
        if any(not axis_ranges[tag][0] <= location[tag] <= axis_ranges[tag][2] for tag in tags):
            return
        key = tuple(location[tag] for tag in tags)
        if key not in seen:
            result.append({"probe": label, "location": location})
            seen.add(key)
    for label, center in (("default", 0.), ("positive_raw_knot", 40 / 16384),
                          ("negative_raw_knot", -40 / 16384)):
        for suffix, offset in (("left_16", -1 / 65536), ("exact", 0.), ("right_16", 1 / 65536)):
            normalized = center + offset
            user = default + normalized * (default - minimum if normalized < 0 else maximum - default)
            add(f"{label}_{suffix}", {"wght": user})
    for user in (300., 300.01, 400., 400.01, 499.01, 501.01):
        add(f"user_weight_{user}", {"wght": user})
    for label, width in zip(("minimum", "default", "maximum"), axis_ranges["WDTH"]):
        add(f"old_hvar_400_01_width_{label}", {"wght": 400.01, "WDTH": width})
    return result
