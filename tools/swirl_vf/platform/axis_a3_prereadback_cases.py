"""Frozen A3 hypotheses for design input before the final decimal readback.

T is the existing positive-coordinate decimal truncation, not a claimed
CoreText algorithm. The old endpoint model uses C=T(T(x)). Two new models
instead use T(x) for all axes or only for strict identity avar axes. They do
not change native requests, the declared C readback, or strict native replay.
In particular, a failed replay remains failed even if a design model matches.

These hypotheses were selected after the arithmetic-stage face 30 failure.
Its derived controls are therefore historical, never fresh holdouts. New cases
depend only on fixed seeds, original axis bounds and explicit arithmetic
predicates. No native metrics, outlines, inferred q or observed errors enter
their generation or any model.

Primary design references, independently implemented rather than copied:
https://github.com/freetype/freetype/blob/master/src/truetype/ttgxvar.c
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview
The separation of input, normalization and avar stages is useful here; these
references do not establish Apple's decimal stages or operation order.
"""
from __future__ import annotations

import math
import random

from analyze_axis_quantization import ordered_map
from axis_a3_arithmetic_cases import ENDPOINT, arithmetic_mappings
from probe_axis_anchor import TAGS, declare_readback, float32, normalize, require
from probe_axis_a3_hvar import validate_axes
from probe_axis_a3_identity_avar import identity_records
from verified_axis_oracle import finite_number


FRESH_SEED = 0xA3B42026
DECIMAL_SEED = 0xA3B4DEC1
BOUNDARY_SEED = 0xA3B4B016
ONCE_ALL = "prereadback_once_all_axes_endpoint_normalized16_truncate"
ONCE_IDENTITY = "prereadback_once_identity_axes_endpoint_normalized16_truncate"
NEW_MODELS = (ONCE_ALL, ONCE_IDENTITY)
ALL_MODELS = (ENDPOINT,) + NEW_MODELS
MODEL_DESCRIPTIONS = {
    ENDPOINT: "Unchanged control: design input C=T(T(x)); strict identity negative side uses float32((C-min)/(default-min))-1, positive side uses binary64 normalization. Nonidentity axes use float32(binary64_normalize(C)). Then normalized16 truncate, original ordered avar, nearest F2DOT14.",
    ONCE_ALL: "Design-stage hypothesis only: input T(x) on every axis, followed by the same endpoint/identity and nonidentity arithmetic as the control. Actual native request x, declared readback C=T(T(x)), and strict replay are unchanged.",
    ONCE_IDENTITY: "Design-stage hypothesis only: strict identity avar axes use T(x); every other raw avar uses C=T(T(x)). The endpoint arithmetic, actual native request x, declared C readback and strict replay are unchanged. Identity detection preserves raw order and rejects duplicates.",
}
BOUNDARY_FACE_SIGNS = ((0, -1), (5, 1), (20, -1), (24, 1))
BOUNDARY_USER_EPSILON = .0002
GENERATION_ATTEMPTS = 4096
ARITHMETIC_COMMIT = "eda37d1c733cb1ced283583434e4123824a2147c"

# These safe original coordinates participated in model selection or are
# retained earlier controls. Neither these nor their derived replay/isolation
# requests count as new holdouts. Error classifications preserve observations;
# they do not assert that either new design vector is already native-verified.
HISTORICAL_CASES = (
    (18, "archived_face18_fresh_triple_7",
     (395.1762070327519, 493.5928547043863, 579.3731774437933),
     "22a89a154217c5a4ea65788d2994e99e816ffabf", "old_normalization_HVAR_and_HVF_nonzero"),
    (12, "identity_fresh_12_1",
     (812.4237777627202, 690.8750329989548, 572.2184188469829),
     "0c603aad04786d4e89cbb6399fc60b06cac7c58a", "old_float32_HVAR_nonzero_later_direct_HVF_nonzero"),
    (30, "arithmetic_fresh_30_0",
     (729.2925740388073, 660.9898707384746, 303.5934274824121),
     ARITHMETIC_COMMIT, "endpoint_HVAR_zero_HVF_nonzero_and_payload_only_replay_failure"),
    (22, "arithmetic_fresh_22_0",
     (208.47406722792215, 300.3333369872149, 1.1280770592536593),
     ARITHMETIC_COMMIT, "readback_only_replay_failure_payload_unchanged"),
    (15, "same_fixed16_collision_low", (500., 499.006199, 500.),
     "53ca5ff74e17bfc65e338b460fa2fc4df3801c1d", "binary64_source_q_zero"),
    (15, "same_fixed16_collision_high", (500., 499.006201, 500.),
     "53ca5ff74e17bfc65e338b460fa2fc4df3801c1d", "binary64_source_q_65"),
    (0, "arithmetic_integer_0_WDTH_-42539_above", (176.10237966308594, 501., 500.),
     ARITHMETIC_COMMIT, "DIVSUB_HVAR_and_HVF_nonzero"),
    (0, "arithmetic_integer_0_HGHT_-42539_above", (500., 501., 176.10237966308594),
     ARITHMETIC_COMMIT, "DIVSUB_HVAR_zero_HVF_nonzero"),
)


def _validated_stages(font, records, location):
    tags = tuple(axis.axisTag for axis in font["fvar"].axes)
    axes = {axis.axisTag: (axis.minValue, axis.defaultValue, axis.maxValue)
            for axis in font["fvar"].axes}
    validate_axes(axes)
    require(len(tags) == 3 and set(tags) == set(TAGS)
            and set(records) == set(TAGS) and set(location) == set(TAGS),
            "a3_prereadback_original_three_axes_required")
    require(all(finite_number(location[tag]) and axes[tag][0] <= location[tag] <= axes[tag][2]
                for tag in TAGS), "a3_prereadback_location_outside_original_axes")
    plans = declare_readback(location)
    identities = {tag: identity_records(records[tag]) for tag in tags}
    once = {tag: plans[tag].get("once", plans[tag]["requested"]) for tag in tags}
    twice = {tag: plans[tag]["canonical"] for tag in tags}
    stages = {ENDPOINT: twice, ONCE_ALL: once,
              ONCE_IDENTITY: {tag: once[tag] if identities[tag] else twice[tag] for tag in tags}}
    return axes, identities, stages


def prereadback_design_inputs(font, records, location):
    """Pre-native model inputs only; this never replaces the readback plan."""
    return _validated_stages(font, records, location)[2]


def prereadback_mappings(font, records, location):
    """Three frozen full design vectors, with no native observation input."""
    axes, identities, stages = _validated_stages(font, records, location)
    # Reuse the exact prior control rather than silently reimplementing it.
    result = {ENDPOINT: arithmetic_mappings(font, records, location)[ENDPOINT]}
    for name in NEW_MODELS:
        mapped = {}
        for axis in font["fvar"].axes:
            tag, value = axis.axisTag, stages[name][axis.axisTag]
            minimum, default, maximum = axes[tag]
            normalized = normalize(value, minimum, default, maximum)
            if identities[tag]:
                if value < default:
                    normalized = float32((value - minimum) / (default - minimum)) - 1
            else:
                normalized = float32(normalized)
            normalized = math.trunc(normalized * 65536) / 65536
            raw = tuple((int(x * 16384), int(y * 16384)) for x, y in records[tag])
            design = ordered_map(normalized, raw)
            mapped[tag] = math.floor(design * 16384 + .5) / 16384
        require(tuple(mapped) == tuple(axis.axisTag for axis in font["fvar"].axes)
                and all(finite_number(value) and -1 <= value <= 1 for value in mapped.values()),
                "a3_prereadback_mapping_outside_design_space")
        result[name] = mapped
    return result


def _decimal_unstable_points(axes, tag, rng):
    """Select two raw decimal-cell midpoints using only T1 != T2."""
    minimum, _, maximum = axes[tag]
    low, high = math.ceil((minimum + 1) * 10000), math.floor((maximum - 1) * 10000)
    require(low < high, "a3_prereadback_decimal_generation_range_invalid")
    found = []
    for attempt in range(1, GENERATION_ATTEMPTS + 1):
        cell = rng.randint(low, high)
        value = (cell + .5) / 10000
        plan = declare_readback({tag: value})[tag]
        if plan.get("once") != plan.get("twice") and value not in [row[0] for row in found]:
            found.append((value, cell, attempt))
            if len(found) == 2:
                return found
    raise ValueError("a3_prereadback_decimal_generation_exhausted")


def _normalized_boundary(axes, tag, sign, rng):
    """Find an arithmetic T2 < integer <= T1 bracket, not a native fit.

    The normalized16 integer residue is fixed by sign: negative 1 mod 4,
    positive 2 mod 4. This makes signed truncation potentially observable at
    final F2DOT14. The raw cell midpoint is above the ideal normalized16 user
    boundary; T1 and T2 must straddle that ideal value. This search sees no
    avar mapping or candidate design vector, much less any Apple result.
    """
    minimum, default, maximum = axes[tag]
    span = default - minimum if sign < 0 else maximum - default
    for attempt in range(1, GENERATION_ATTEMPTS + 1):
        index = rng.randint(1024, 15000)
        n16 = -4 * index + 1 if sign < 0 else 4 * index + 2
        ideal = default + n16 * span / 65536
        cell = math.ceil(ideal * 10000)
        center = (cell + .5) / 10000
        plan = declare_readback({tag: center})[tag]
        once = normalize(plan.get("once", center), minimum, default, maximum) * 65536
        twice = normalize(plan["canonical"], minimum, default, maximum) * 65536
        if (plan.get("once") != plan.get("twice") and twice < n16 <= once
                and minimum < center - BOUNDARY_USER_EPSILON
                and center + BOUNDARY_USER_EPSILON < maximum):
            return n16, ideal, center, cell, attempt
    raise ValueError("a3_prereadback_boundary_generation_exhausted")


def prereadback_cases(face_axes):
    """140 requests: 124 new holdouts and 16 historical/derived controls.

    Direct HVF is preselected for 68: the first random point per face, every
    history/derived control, every normalized16 center, and its HGHT neighbors.
    Every request keeps the original full three-axis tuple. No coordinate is
    silently replaced with T1 or T2: those are separate labeled controls.
    """
    require(set(face_axes) == set(range(32)), "a3_prereadback_all_32_faces_required")
    for axes in face_axes.values():
        validate_axes(axes)
        require(all(values[0] < values[1] < values[2] for values in axes.values()),
                "a3_prereadback_original_interior_defaults_required")
    cases = []

    def add(face, label, group, location, *, direct_native_HVF, **metadata):
        axes = face_axes[face]
        require(set(location) == set(TAGS) and all(finite_number(location[tag])
                and axes[tag][0] <= location[tag] <= axes[tag][2] for tag in TAGS),
                "a3_prereadback_case_outside_original_axes")
        cases.append({"face_index": face, "label": label, "group": group,
                      "is_holdout": group != "historical_control", "location": dict(location),
                      "direct_native_HVF": direct_native_HVF, **metadata})

    rng = random.Random(FRESH_SEED)
    for face in range(32):
        axes = face_axes[face]
        for index in range(2):
            add(face, f"prereadback_fresh_{face}_{index}", "fresh_random_holdout",
                {tag: rng.uniform(axes[tag][0], axes[tag][2]) for tag in TAGS},
                direct_native_HVF=index == 0)

    rng = random.Random(DECIMAL_SEED)
    for face, _ in BOUNDARY_FACE_SIGNS:
        axes = face_axes[face]
        defaults = {tag: axes[tag][1] for tag in TAGS}
        for tag in TAGS:
            for index, (value, cell, attempt) in enumerate(_decimal_unstable_points(axes, tag, rng)):
                add(face, f"prereadback_decimal_{face}_{tag}_{index}", "decimal_stage_instability_holdout",
                    {**defaults, tag: value}, direct_native_HVF=False,
                    boundary_axis=tag, decimal_cell_index=cell, arithmetic_generation_attempt=attempt,
                    selection_predicate="T1 != T2 only; no native result or model design input")

    rng = random.Random(BOUNDARY_SEED)
    for face, sign in BOUNDARY_FACE_SIGNS:
        axes = face_axes[face]
        defaults = {tag: axes[tag][1] for tag in TAGS}
        for tag in TAGS:
            n16, ideal, center, cell, attempt = _normalized_boundary(axes, tag, sign, rng)
            for side, offset in (("below", -BOUNDARY_USER_EPSILON), ("at", 0.),
                                 ("above", BOUNDARY_USER_EPSILON)):
                add(face, f"prereadback_integer_{face}_{tag}_{n16}_{side}",
                    "normalized16_decimal_bracket_holdout", {**defaults, tag: center + offset},
                    direct_native_HVF=side == "at" or tag == "HGHT", boundary_axis=tag,
                    boundary_n16=n16, ideal_normalized16_user_boundary=ideal,
                    boundary_user_center=center, decimal_cell_index=cell, boundary_side=side,
                    user_offset=offset, arithmetic_generation_attempt=attempt,
                    selection_predicate="At center: normalize(T2)*65536 < n16 <= normalize(T1)*65536; no native result or avar/design fit")

    for face, old_label, coordinates, commit, prior_failure in HISTORICAL_CASES:
        add(face, f"prereadback_history_{face}_{old_label}", "historical_control",
            dict(zip(TAGS, coordinates)), direct_native_HVF=True,
            participated_in_model_selection=True,
            historical_reference={"source_commit": commit, "label": old_label,
                                  "prior_observation": prior_failure})

    # Follow the already observed face 30 failure without relabeling these
    # replay-stage and axis-isolation controls as independent fresh evidence.
    raw = dict(zip(TAGS, HISTORICAL_CASES[2][2]))
    plans = declare_readback(raw)
    once = {tag: plans[tag]["once"] for tag in TAGS}
    twice = {tag: plans[tag]["canonical"] for tag in TAGS}
    defaults = {tag: face_axes[30][tag][1] for tag in TAGS}
    derived = (
        ("tuple_once", once), ("tuple_twice", twice),
        ("raw_WDTH_wght_HGHT_once", {**raw, "HGHT": once["HGHT"]}),
        ("raw_WDTH_wght_HGHT_twice", {**raw, "HGHT": twice["HGHT"]}),
        ("twice_WDTH_wght_HGHT_raw", {**twice, "HGHT": raw["HGHT"]}),
        ("HGHT_only_raw", {**defaults, "HGHT": raw["HGHT"]}),
        ("HGHT_only_once", {**defaults, "HGHT": once["HGHT"]}),
        ("HGHT_only_twice", {**defaults, "HGHT": twice["HGHT"]}),
    )
    for name, location in derived:
        add(30, f"prereadback_derived_30_{name}", "historical_control", location,
            direct_native_HVF=True, participated_in_model_selection=True,
            derived_from_historical=True, derivation=name,
            historical_reference={"source_commit": ARITHMETIC_COMMIT,
                                  "label": "arithmetic_fresh_30_0",
                                  "prior_observation": "derived_control_not_previously_measured_at_this_request"})

    require(len(cases) == 140 and sum(row["is_holdout"] for row in cases) == 124
            and sum(row["direct_native_HVF"] for row in cases) == 68
            and len({(row["face_index"], row["label"]) for row in cases}) == len(cases),
            "a3_prereadback_cohort_count_changed")
    require(len({(row["face_index"], *(row["location"][tag] for tag in TAGS))
                 for row in cases}) == len(cases), "a3_prereadback_duplicate_location")
    return cases
