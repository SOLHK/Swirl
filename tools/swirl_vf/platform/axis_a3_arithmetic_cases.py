"""Frozen A3 arithmetic hypotheses and new cases, independent of native output.

These are diagnostic models selected after inspecting earlier A3 evidence.
Matching an archived design vector is not a new CoreText measurement and does
not establish Apple's internal implementation. New holdouts are generated here
without native metrics, outlines, inferred coordinates, face-specific formulas,
or observed errors as inputs to any model.

Primary design references, independently implemented rather than copied:
https://github.com/freetype/freetype/blob/master/src/truetype/ttgxvar.c
https://skia.googlesource.com/third_party/freetype2/+/fd92af79d801880faf070c84d0c274081369eb76/src/truetype/ttgxvar.c
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview
FreeType's separate normalization and avar stages motivate keeping those
operations separately testable; none of these references specifies this Apple
negative-side float32 hypothesis. Original axis bounds, raw avar record order,
duplicate records, signed truncation and the strict 1/32 error budget stay intact.
"""
from __future__ import annotations

import math
import random

from analyze_axis_quantization import ordered_map
from probe_axis_anchor import (MODEL_NAMES, TAGS, declare_readback,
    declared_mappings, float32, normalize, require)
from probe_axis_a3_hvar import validate_axes
from probe_axis_a3_identity_avar import identity_records
from verified_axis_oracle import finite_number


FRESH_SEED = 0xA3A62026
ENDPOINT = "canonical_identity_negative_endpoint32_positive64_normalized16_truncate"
OFFSET = "canonical_identity_negative_offset32_positive64_normalized16_truncate"
DIVSUB = "canonical_identity_negative_divsub32_positive64_normalized16_truncate"
ALL_AXES_CONTROL = "canonical_all_axes_float32_offset_normalized16_truncate"
NEW_MODELS = (ENDPOINT, OFFSET, DIVSUB, ALL_AXES_CONTROL)
ALL_MODELS = MODEL_NAMES + NEW_MODELS
MODEL_DESCRIPTIONS = {
    MODEL_NAMES[0]: "Existing C=T(T(x)); binary64 normalization, normalized16 truncate, ordered raw avar, nearest F2DOT14.",
    MODEL_NAMES[1]: "Existing C=T(T(x)); binary64 normalization then float32 result, normalized16 truncate, ordered raw avar, nearest F2DOT14.",
    ENDPOINT: "Strict identity avar only: C<default uses float32((C-min)/(default-min))-1; C>=default uses binary64 (C-default)/(max-default). Nonidentity axes retain the old canonical float32 normalized16 truncate rule. All axes then truncate normalized16 and map the original avar records before nearest F2DOT14.",
    OFFSET: "As endpoint candidate, but identity C<default uses float32(1+binary64((C-default)/(default-min)))-1. This deliberately retains a distinct binary64 expression before float32 conversion.",
    DIVSUB: "As endpoint candidate, but identity C<default uses float32(float32(C/span)-float32(default/span)), span=default-min. Each division is binary64 with its own float32 result; C itself is not converted to float32 first.",
    ALL_AXES_CONTROL: "Known-risk control: every axis and both signs use float32(1+binary64_normalize(C))-1 before normalized16 truncate and ordered raw avar. It changes scope and positive-side arithmetic together; this control alone cannot identify which difference causes an error.",
}

# Four original axis families. Negative n16 values are 1 mod 4; positive
# values are 2 mod 4, so their truncation boundaries can affect final F2DOT14.
# Values and cases are frozen before the next native run, without searching
# or fitting against any of its observations.
BOUNDARY_N16_BY_FACE = ((0, -42539), (5, -21563), (20, 35862), (24, 17018))
BOUNDARY_USER_EPSILON = .0001
DEFAULT_FACES = (0, 5, 20, 24)

# Filled with safe coordinates from the two already archived A3 reports.
# These controls are never counted as new holdouts. Tuple form prevents a
# returned mutable case from changing the frozen coordinates for later calls.
HISTORICAL_CASES = ((18,
  'archived_face18_fresh_triple_7',
  (395.1762070327519, 493.5928547043863, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'WDTH_only',
  (395.1762070327519, 499.0, 500.0),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'WDTH_binary64_below',
  (395.17620703275185, 493.5928547043863, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'WDTH_binary64_above',
  (395.17620703275196, 493.5928547043863, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'WDTH_user_fixed16_above',
  (395.17622229154097, 493.5928547043863, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'wght_reset_to_default',
  (395.1762070327519, 499.0, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'wght_binary64_below',
  (395.1762070327519, 493.59285470438624, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'wght_user_fixed16_below',
  (395.1762070327519, 493.59283944559724, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'wght_normalized16_below',
  (395.1762070327519, 493.58676644755036, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'wght_binary64_above',
  (395.1762070327519, 493.59285470438635, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'wght_user_fixed16_above',
  (395.1762070327519, 493.59286996317536, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'wght_normalized16_above',
  (395.1762070327519, 493.59894296122224, 579.3731774437933),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'HGHT_reset_to_default',
  (395.1762070327519, 493.5928547043863, 500.0),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'HGHT_binary64_below',
  (395.1762070327519, 493.5928547043863, 579.3731774437932),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'HGHT_user_fixed16_below',
  (395.1762070327519, 493.5928547043863, 579.3731621850043),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'HGHT_normalized16_below',
  (395.1762070327519, 493.5928547043863, 579.3655480492621),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'HGHT_binary64_above',
  (395.1762070327519, 493.5928547043863, 579.3731774437935),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'HGHT_user_fixed16_above',
  (395.1762070327519, 493.5928547043863, 579.3731927025824),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'HGHT_normalized16_above',
  (395.1762070327519, 493.5928547043863, 579.3808068383246),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_normalized16_truncate',
   'canonical_float32_normalized16_truncate',
   'canonical_float32_user_sub_div_normalized16_truncate',
   'canonical_float32_delta_div_normalized16_truncate',
   'canonical_float32_reciprocal_mul_normalized16_truncate',
   'request_float32_result_normalized16_truncate')),
 (18,
  'a3_fresh_holdout_1',
  (506.0136563804356, 271.5572090688256, 647.3836060029549),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_float32_result_normalized16_nearest',)),
 (18,
  'a3_fresh_holdout_5',
  (733.8074261111074, 520.4531783300665, 72.83509247991965),
  '22a89a154217c5a4ea65788d2994e99e816ffabf',
  ('canonical_float32_result_normalized16_nearest',)),
 (2,
  'identity_fresh_2_0',
  (180.7568526190835, 728.5226223501476, 10.088478435611686),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (2,
  'identity_fresh_2_1',
  (473.6058827297113, 798.7719228211618, 285.55667146206486),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (3,
  'identity_fresh_3_0',
  (365.4617129243315, 712.5775427590515, 398.8042535324259),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (7,
  'identity_fresh_7_0',
  (907.0036628813695, 222.32407956928427, 48.341661745702076),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (12,
  'identity_fresh_12_1',
  (812.4237777627202, 690.8750329989548, 572.2184188469829),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_float32_normalized16_truncate', 'canonical_identity_avar_float32_direct_f2dot14')),
 (16,
  'identity_fresh_16_1',
  (242.86462991377107, 894.0557886960983, 282.58736370883344),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (18,
  'identity_fresh_18_1',
  (412.4200766859538, 422.89534457077247, 786.6921442990428),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (19,
  'identity_fresh_19_1',
  (495.65431347246744, 288.13433030098867, 731.7776059049271),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (23,
  'identity_fresh_23_0',
  (445.1015723732783, 356.79453207845853, 498.73873997851086),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (23,
  'identity_fresh_23_1',
  (18.70326214587261, 313.9930562375539, 735.7399795098224),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (24,
  'identity_fresh_24_1',
  (110.07642126071624, 723.606382040417, 139.18768106693653),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (28,
  'identity_fresh_28_1',
  (496.2982636456745, 323.5148530666104, 28.54556236194678),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (15,
  'identity_boundary_15_WDTH_-7311_below',
  (277.34696674346924, 499.0, 500.0),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (15,
  'identity_boundary_15_WDTH_-7311_at',
  (277.3474426269531, 499.0, 500.0),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (18,
  'identity_boundary_18_WDTH_-7311_below',
  (277.34696674346924, 499.0, 500.0),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (18,
  'identity_boundary_18_WDTH_-7311_at',
  (277.3474426269531, 499.0, 500.0),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (20,
  'identity_boundary_20_WDTH_-7311_below',
  (277.34696674346924, 500.0, 500.0),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')),
 (20,
  'identity_boundary_20_WDTH_-7311_at',
  (277.3474426269531, 500.0, 500.0),
  '0c603aad04786d4e89cbb6399fc60b06cac7c58a',
  ('canonical_identity_avar_float32_direct_f2dot14', 'canonical_identity_avar_binary64_direct_f2dot14')))


def arithmetic_mappings(font, records, location):
    """Return six predeclared models; no native observation is accepted here."""
    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue)
            for a in font["fvar"].axes}
    validate_axes(axes)
    require(set(records) == set(TAGS) and set(location) == set(TAGS),
            "a3_arithmetic_original_three_axes_required")
    require(all(finite_number(location[tag]) and axes[tag][0] <= location[tag] <= axes[tag][2]
                for tag in TAGS), "a3_arithmetic_location_outside_original_axes")
    result = declared_mappings(font, records, location)
    canonical = {tag: plan["canonical"] for tag, plan in declare_readback(location).items()}
    for name in NEW_MODELS:
        mapped = dict(result[MODEL_NAMES[1]])
        for axis in font["fvar"].axes:
            tag = axis.axisTag
            if name != ALL_AXES_CONTROL and not identity_records(records[tag]):
                continue
            value = canonical[tag]
            minimum, default, maximum = axes[tag]
            normalized = normalize(value, minimum, default, maximum)
            if name == ALL_AXES_CONTROL:
                normalized = float32(1 + normalized) - 1
            elif value < default:
                span = default - minimum
                if name == ENDPOINT:
                    normalized = float32((value - minimum) / span) - 1
                elif name == OFFSET:
                    normalized = float32(1 + normalized) - 1
                elif name == DIVSUB:
                    normalized = float32(float32(value / span) - float32(default / span))
            normalized = math.trunc(normalized * 65536) / 65536
            raw = tuple((int(x * 16384), int(y * 16384)) for x, y in records[tag])
            design = ordered_map(normalized, raw)
            mapped[tag] = math.floor(design * 16384 + .5) / 16384
        require(tuple(mapped) == tuple(a.axisTag for a in font["fvar"].axes)
                and set(mapped) == set(TAGS)
                and all(finite_number(value) and -1 <= value <= 1 for value in mapped.values()),
                "a3_arithmetic_mapping_outside_design_space")
        result[name] = mapped
    return result


def arithmetic_cases(face_axes):
    """201 requests: 160 new holdouts and 41 explicit historical controls.

The default cohort intentionally repeats each face's exact all-default tuple
once per named axis. Request labels, not coordinates alone, identify controls.
All other repeated tuples are rejected. Native-HVF selection is frozen here.
"""
    require(set(face_axes) == set(range(32)), "a3_arithmetic_all_32_faces_required")
    for axes in face_axes.values():
        validate_axes(axes)
    cases = []

    def add(face, label, group, location, *, direct_native_HVF, **metadata):
        axes = face_axes[face]
        require(set(location) == set(TAGS) and all(finite_number(location[tag])
                and axes[tag][0] <= location[tag] <= axes[tag][2] for tag in TAGS),
                "a3_arithmetic_case_outside_original_axes")
        cases.append({"face_index": face, "label": label, "group": group,
                      "is_holdout": group != "historical_control",
                      "location": dict(location), "direct_native_HVF": direct_native_HVF,
                      **metadata})

    rng = random.Random(FRESH_SEED)
    for face in range(32):
        axes = face_axes[face]
        for index in range(2):
            add(face, f"arithmetic_fresh_{face}_{index}", "fresh_random_holdout",
                {tag: rng.uniform(axes[tag][0], axes[tag][2]) for tag in TAGS},
                direct_native_HVF=index == 0)

    for face, n16 in BOUNDARY_N16_BY_FACE:
        axes = face_axes[face]
        defaults = {tag: axes[tag][1] for tag in TAGS}
        for tag in TAGS:
            minimum, default, maximum = axes[tag]
            span = default - minimum if n16 < 0 else maximum - default
            center = default + n16 / 65536 * span
            for side, offset in (("below", -BOUNDARY_USER_EPSILON), ("at", 0.),
                                 ("above", BOUNDARY_USER_EPSILON)):
                add(face, f"arithmetic_integer_{face}_{tag}_{n16}_{side}",
                    "normalized16_integer_boundary_holdout", {**defaults, tag: center + offset},
                    direct_native_HVF=side == "at" or (n16 < 0 and side == "above" and tag in ("WDTH", "HGHT")),
                    boundary_axis=tag, boundary_n16=n16, boundary_user_center=center,
                    user_offset=offset, boundary_side=side)

    for face in DEFAULT_FACES:
        axes = face_axes[face]
        defaults = {tag: axes[tag][1] for tag in TAGS}
        for tag in TAGS:
            default = axes[tag][1]
            points = (("decimal_below", default - .0001),
                      ("nextafter_below", math.nextafter(default, -math.inf)),
                      ("exact", default),
                      ("nextafter_above", math.nextafter(default, math.inf)),
                      ("decimal_above", default + .0001))
            for side, value in points:
                add(face, f"arithmetic_default_{face}_{tag}_{side}",
                    "default_omission_boundary_holdout", {**defaults, tag: value},
                    direct_native_HVF=tag == "wght" and side == "nextafter_above",
                    boundary_axis=tag, default_side=side,
                    intentional_repeated_all_default=side == "exact")

    for face, old_label, coordinates, commit, failed_models in HISTORICAL_CASES:
        add(face, f"arithmetic_history_{face}_{old_label}", "historical_control",
            dict(zip(TAGS, coordinates)), direct_native_HVF=True,
            historical_reference={"source_commit": commit, "label": old_label,
                                  "known_nonexact_models": list(failed_models)})
    for side, value in (("low", 499.006199), ("high", 499.006201)):
        add(15, f"arithmetic_original_collision_{side}", "historical_control",
            {"WDTH": 500., "wght": value, "HGHT": 500.}, direct_native_HVF=True,
            historical_reference={"source_commit": "53ca5ff74e17bfc65e338b460fa2fc4df3801c1d",
                                  "label": f"same_fixed16_collision_{side}"})

    require(len(cases) == 201 and sum(row["is_holdout"] for row in cases) == 160
            and len({(row["face_index"], row["label"]) for row in cases}) == len(cases),
            "a3_arithmetic_cohort_count_changed")
    groups = {}
    for row in cases:
        key = (row["face_index"], *(row["location"][tag] for tag in TAGS))
        groups.setdefault(key, []).append(row)
    require(all(len(rows) == 1 or (len(rows) == 3
                and all(row.get("intentional_repeated_all_default") for row in rows)
                and {row["boundary_axis"] for row in rows} == set(TAGS))
                for rows in groups.values()), "a3_arithmetic_undeclared_duplicate_location")
    return cases
