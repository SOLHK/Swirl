"""Predeclared A3 input-representation controls, never a source-axis model.

The distinct roles of user-coordinate precision and normalized-coordinate
precision follow the public OpenType normalization specification and the
HarfBuzz design/normalized API declarations. No upstream implementation is
copied, no native output selects a case, and no Apple payload is embedded.

Primary references reviewed before implementation:
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview#coordinate-scales-and-normalization
https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-font.h

The numeric evidence returned here is not a CoreText/DirectWrite observation.
The caller must separately bind source identity, execute native requests, and
compare complete glyph payloads. Original axis order/records are not repaired.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
import math
import random
import struct


TAGS = ("WDTH", "wght", "HGHT")
SELECTED_FACES = (15, 18, 20)
RANDOM_SEED = 310202610
FRESH_TRIPLES_PER_FACE = 3
FIXED_MIN = -32768.0
FIXED_MAX = 32767 + 65535 / 65536


def _finite(value, code="finite_numeric_input_required"):
    if type(value) not in (int, float):
        raise ValueError(code)
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise ValueError(code) from None
    if not math.isfinite(result):
        raise ValueError(code)
    return result


def fixed16_input(value):
    """Convert binary64 to signed 16.16, nearest with ties toward +infinity.

    Fraction arithmetic avoids the extra rounding caused by adding 0.5 in
    binary64 near a large integer. Values outside the representable user range
    are rejected; this diagnostic neither clamps nor wraps an input.
    """
    value = _finite(value)
    if not FIXED_MIN <= value <= FIXED_MAX:
        raise ValueError("input_outside_signed_fixed16_range")
    return math.floor(Fraction(value) * 65536 + Fraction(1, 2))


def representations(value):
    """Return JSON-safe exact identities for three input representations.

    ``fixed16_cell`` is an abstract nearest/ties-up rounding interval, before
    intersecting it with the API's valid signed range. Its lower boundary is
    included and its upper boundary excluded. binary32 uses IEEE nearest-even.
    """
    original = value
    value = _finite(value)
    fixed = fixed16_input(value)
    packed32 = struct.pack(">f", value)
    single = struct.unpack(">f", packed32)[0]
    return {
        "original_decimal": repr(original),
        "binary64_value": value,
        "binary64_hex": value.hex(),
        "binary64_bits": struct.pack(">d", value).hex(),
        "float32_value": single,
        "float32_bits": packed32.hex(),
        "fixed16_integer": fixed,
        "fixed16_value": fixed / 65536,
        "fixed16_cell": {
            "lower_inclusive": float(Fraction(2 * fixed - 1, 131072)),
            "upper_exclusive": float(Fraction(2 * fixed + 1, 131072)),
        },
        "fixed16_rounding": "nearest_ties_toward_positive_infinity",
        "float32_rounding": "IEEE754_nearest_ties_to_even",
        "native_observation": False,
    }


def conditional_lower_bound(delta, limit=1 / 32):
    """Triangle-inequality bound conditional on identical target input state.

    The supplied nonnegative delta is evidence supplied by the caller; this
    helper does not measure it. Comparisons use exact rationals corresponding
    to the supplied binary64 numbers, including the equality-at-2*limit case.
    """
    delta = _finite(delta, "finite_nonnegative_difference_required")
    limit = _finite(limit, "finite_positive_limit_required")
    if delta < 0:
        raise ValueError("finite_nonnegative_difference_required")
    if limit <= 0:
        raise ValueError("finite_positive_limit_required")
    bound = Fraction(delta) / 2
    threshold = Fraction(limit)
    multiple = bound / threshold
    try:
        multiple_float = float(multiple)
    except OverflowError:
        multiple_float = None
    return {
        "supplied_absolute_difference": delta,
        "limit_font_units": limit,
        "minimum_worst_case_error": float(bound),
        "exact_bound_fraction": [str(bound.numerator), str(bound.denominator)],
        "threshold_multiple": multiple_float,
        "exact_multiple_fraction": [str(multiple.numerator), str(multiple.denominator)],
        "simultaneous_tolerance_impossible_if_inputs_collapse": bound > threshold,
        "condition": "deterministic_target_receives_identical_state_without_extra_discriminating_information",
        "native_measurement_performed": False,
        "production_mapping_accepted": False,
        "continuous_space_accepted": False,
    }


def _ranges(axes_by_face):
    if not isinstance(axes_by_face, Mapping) or 15 not in axes_by_face:
        raise ValueError("a3_collision_face15_required")
    if any(type(face) is not int or not 0 <= face < 32 for face in axes_by_face):
        raise ValueError("invalid_physical_face_index")
    result = {}
    for face in SELECTED_FACES:
        if face not in axes_by_face:
            continue
        axes = axes_by_face[face]
        if not isinstance(axes, Mapping) or set(axes) != set(TAGS):
            raise ValueError("all_original_axis_tags_required")
        ranges = {}
        for tag in TAGS:
            values = axes[tag]
            if (not isinstance(values, Sequence) or isinstance(values, (str, bytes))
                    or len(values) != 3):
                raise ValueError("invalid_source_axis_range")
            low, default, high = (_finite(value, "invalid_source_axis_range") for value in values)
            if not FIXED_MIN <= low <= default <= high <= FIXED_MAX or low >= high:
                raise ValueError("invalid_source_axis_range")
            ranges[tag] = (low, default, high)
        result[face] = ranges
    if {tag: values[1] for tag, values in result[15].items()} != {
            "WDTH": 500.0, "wght": 499.0, "HGHT": 500.0}:
        raise ValueError("review_changed_collision_face_defaults")
    return result


def _record_indices(records):
    """Select at most two raw ordinals; retain duplicate-record provenance.

    Prefer the first repeated interior from-coordinate and its first earlier
    occurrence. Otherwise select the first two interior records in table order.
    The original sequence is never sorted, deduplicated, or changed.
    """
    if (not isinstance(records, Sequence) or isinstance(records, (str, bytes))
            or not records):
        raise ValueError("ordered_raw_avar_records_required")
    first = {}
    interior = []
    repeated = None
    for index, pair in enumerate(records):
        if (not isinstance(pair, Sequence) or isinstance(pair, (str, bytes))
                or len(pair) != 2
                or any(type(value) is not int or not -32768 <= value <= 32767 for value in pair)):
            raise ValueError("raw_avar_signed_f2dot14_records_required")
        x, _ = pair
        if -16384 < x < 16384:
            interior.append(index)
            if x in first and repeated is None:
                repeated = (first[x], index)
            first.setdefault(x, index)
    return list(repeated) if repeated is not None else interior[:2]


def input_cases(axes_by_face, raw_records_by_face=None):
    """Freeze at most 118 cases on faces 15/18/20 before native observation.

    ``axes_by_face[face][tag]`` is (minimum, default, maximum).
    ``raw_records_by_face[face][tag]`` is the original ordered sequence of raw
    integer F2DOT14 pairs. Repeated selected knots produce distinct labeled
    cases even when their coordinates coincide. Complete tables belong in the
    caller's source-identity evidence; this finite sampler never replaces them.

    Out-of-range generated neighbors are omitted, never clamped. The mandatory
    existing collision/control inputs must all fit the original face15 range.
    A fresh local RNG is seeded independently of every earlier sampling cohort;
    no fitted model or native result is accepted by this interface.
    """
    ranges_by_face = _ranges(axes_by_face)
    if raw_records_by_face is not None and not isinstance(raw_records_by_face, Mapping):
        raise ValueError("ordered_raw_avar_records_required")
    result = []

    def add(face, label, group, updates, *, mandatory=False, **metadata):
        ranges = ranges_by_face[face]
        location = {tag: ranges[tag][1] for tag in TAGS}
        location.update(updates)
        if set(location) != set(TAGS) or any(
                not math.isfinite(value) or not ranges[tag][0] <= value <= ranges[tag][2]
                for tag, value in location.items()):
            if mandatory:
                raise ValueError("mandatory_collision_control_outside_original_axis_range")
            return
        result.append({"face_index": face, "label": label, "group": group,
                       "location": location, **metadata})

    # Fixed values are intentionally not selected from any new native outcome.
    # The first two retain the measured historical counterexample verbatim.
    midpoint = 499.0062103271484375
    controls = (
        ("existing_collision_low", "existing_collision", 499.006199),
        ("existing_collision_high", "existing_collision", 499.006201),
        ("shared_quantized_input", "shared_quantized_control", 32702870 / 65536),
        ("fixed_only_collision_low", "fixed_only_collision", math.nextafter(midpoint, -math.inf)),
        ("fixed_only_collision_high", "fixed_only_collision", math.nextafter(midpoint, math.inf)),
        ("float32_only_collision_low", "float32_only_collision", 499.006181),
        ("float32_only_collision_high", "float32_only_collision", 499.006199),
    )
    for label, group, weight in controls:
        add(15, label, group, {"wght": weight}, mandatory=True)

    for face, ranges in ranges_by_face.items():
        add(face, "original_default", "original_default", {})
        for tag in TAGS:
            low, default, high = ranges[tag]
            for side, direction in (("below", -math.inf), ("above", math.inf)):
                add(face, f"{tag}_default_binary64_{side}", "binary64_default_neighbor",
                    {tag: math.nextafter(default, direction)})
            direction = 1 if default < high else -1
            rational_center = Fraction(default) + direction * Fraction(1, 10000)
            center = float(rational_center)
            for side, value in (("below", math.nextafter(center, -math.inf)),
                                ("nearest", center), ("above", math.nextafter(center, math.inf))):
                add(face, f"{tag}_decimal_bin_{side}", "decimal_bin_boundary", {tag: value},
                    intended_rational_boundary=[str(rational_center.numerator), str(rational_center.denominator)])
            if raw_records_by_face is not None:
                records_by_tag = raw_records_by_face.get(face)
                if not isinstance(records_by_tag, Mapping) or set(records_by_tag) != set(TAGS):
                    raise ValueError("all_original_raw_avar_axes_required")
                records = records_by_tag[tag]
                for ordinal in _record_indices(records):
                    x, y = records[ordinal]
                    span = Fraction(default) - Fraction(low) if x < 0 else Fraction(high) - Fraction(default)
                    knot = Fraction(default) + Fraction(x, 16384) * span
                    value = float(knot)
                    for side, neighbor in (("below", math.nextafter(value, -math.inf)),
                                           ("nearest", value), ("above", math.nextafter(value, math.inf))):
                        add(face, f"{tag}_raw_avar_{ordinal}_{side}", "avar_record_boundary", {tag: neighbor},
                            avar_record_index=ordinal, avar_raw_from_f2dot14=x,
                            avar_raw_to_f2dot14=y, avar_original_record_count=len(records),
                            intended_rational_boundary=[str(knot.numerator), str(knot.denominator)])
        rng = random.Random(RANDOM_SEED + face)
        for ordinal in range(FRESH_TRIPLES_PER_FACE):
            add(face, f"fresh_holdout_{ordinal}", "fresh_holdout",
                {tag: rng.uniform(ranges[tag][0], ranges[tag][2]) for tag in TAGS},
                random_seed=RANDOM_SEED + face, modeling_use="none_predeclared_input_only")
    return result
