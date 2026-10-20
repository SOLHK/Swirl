"""Pure model/cohort contracts; these tests are not new Apple measurements."""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys
from types import SimpleNamespace
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from axis_a3_prereadback_cases import (ALL_MODELS, ARITHMETIC_COMMIT,
    BOUNDARY_FACE_SIGNS, BOUNDARY_SEED, BOUNDARY_USER_EPSILON, DECIMAL_SEED,
    ENDPOINT, FRESH_SEED, GENERATION_ATTEMPTS, HISTORICAL_CASES, MODEL_DESCRIPTIONS,
    NEW_MODELS, ONCE_ALL, ONCE_IDENTITY, TAGS, arithmetic_mappings, declare_readback,
    normalize, prereadback_cases, prereadback_design_inputs, prereadback_mappings)
from verified_axis_oracle import effective_readback


@lru_cache(maxsize=1)
def archived_original_faces():
    """Use hash-bound original axis/avar metadata, never source glyph payloads."""
    path = (Path(__file__).resolve().parents[1] / "platform" /
            "axis_a3_native_identity_0c603aa.zip")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != "eda7c6db0b3bfe09d40781feb4f8cb26ad074fa57c82f6d50b7dbfb78efeef14":
        raise AssertionError("Archived A3 original-axis ZIP hash changed")
    with zipfile.ZipFile(path) as archive:
        if archive.namelist() != ["identity-avar.json"]:
            raise AssertionError("Unexpected archived A3 ZIP member")
        data = archive.read("identity-avar.json")
    if hashlib.sha256(data).hexdigest() != "7fa5578a1b8f125e0d2fc07ae3dec64e02c2ddbc1a6e0411cd37992fa2841d65":
        raise AssertionError("Archived A3 original-axis report hash changed")
    report = json.loads(data)
    if report["source_commit"] != "0c603aad04786d4e89cbb6399fc60b06cac7c58a":
        raise AssertionError("Archived A3 original-axis provenance changed")
    faces = report["original_faces"]
    if [row["face_index"] for row in faces] != list(range(32)):
        raise AssertionError("Original A3 face sequence changed")
    return faces


def original_axes():
    return {row["face_index"]: deepcopy(row["original_axes"])
            for row in archived_original_faces()}


def fixture(face):
    row = archived_original_faces()[face]
    font = {"fvar": SimpleNamespace(axes=[SimpleNamespace(axisTag=tag,
        minValue=values[0], defaultValue=values[1], maxValue=values[2])
        for tag, values in row["original_axes"].items()])}
    return font, deepcopy(row["original_avar_records_in_table_order"])


def historical(label):
    row = next(row for row in HISTORICAL_CASES if row[1] == label)
    return row[0], dict(zip(TAGS, row[2]))


def quantized(mapping):
    return tuple(round(mapping[tag] * 16384) for tag in TAGS)


class PrereadbackModels(unittest.TestCase):
    def test_face30_once_prediction_is_distinct_but_not_claimed_native_verified(self):
        face, raw = historical("arithmetic_fresh_30_0")
        font, records = fixture(face)
        stages = prereadback_design_inputs(font, records, raw)
        mappings = prereadback_mappings(font, records, raw)
        self.assertEqual(tuple(mappings), ALL_MODELS)
        self.assertEqual(tuple(stages), ALL_MODELS)
        self.assertEqual(tuple(MODEL_DESCRIPTIONS), ALL_MODELS)
        self.assertEqual(stages[ENDPOINT], {"WDTH": 729.2925, "wght": 660.9897, "HGHT": 303.5933})
        self.assertEqual(stages[ONCE_ALL], {"WDTH": 729.2925, "wght": 660.9898, "HGHT": 303.5934})
        self.assertEqual(stages[ONCE_IDENTITY], {"WDTH": 729.2925, "wght": 660.9897, "HGHT": 303.5934})
        self.assertEqual(quantized(mappings[ENDPOINT]), (7513, 5275, -6449))
        for name in NEW_MODELS:
            self.assertEqual(quantized(mappings[name]), (7513, 5275, -6448))
        # This is the new predeclared candidate to measure; this test contains
        # no comparison against a claimed CoreText measurement of q=-6448.

    def test_face22_readback_failure_remains_rejected_after_new_model_evaluation(self):
        face, raw = historical("arithmetic_fresh_22_0")
        font, records = fixture(face)
        before = declare_readback(raw)
        stages = prereadback_design_inputs(font, records, raw)
        prereadback_mappings(font, records, raw)
        self.assertEqual(before, declare_readback(raw))
        self.assertEqual(stages[ONCE_ALL]["HGHT"], 1.128)
        self.assertEqual(stages[ENDPOINT]["HGHT"], 1.1279)
        replay_request = {tag: row["canonical"] for tag, row in before.items()}
        identity = {"axes": [{"tag": axis.axisTag, "minimum": axis.minValue,
            "default": axis.defaultValue, "maximum": axis.maxValue}
            for axis in font["fvar"].axes]}
        observed_replay = {**replay_request, "HGHT": 1.1278}
        with self.assertRaisesRegex(ValueError, "native_readback_replay_not_exactly_stable"):
            effective_readback({"reported_location": observed_replay}, identity,
                               replay_request, replay=True, declaration=before)

    def test_original_collision_is_not_collapsed_by_either_new_model(self):
        font, records = fixture(15)
        values = (499.006199, 499.006201)
        self.assertEqual([math.floor(value * 65536 + .5) for value in values], [32702870] * 2)
        self.assertEqual([struct.pack(">f", value).hex() for value in values], ["43f980cb"] * 2)
        mappings = [prereadback_mappings(font, records,
                    {"WDTH": 500., "wght": value, "HGHT": 500.}) for value in values]
        for name in ALL_MODELS:
            self.assertEqual([row[name]["wght"] * 16384 for row in mappings], [0, 65])

    def test_original_focus_and_positive_float32_counterexample_full_vectors(self):
        expected = {"archived_face18_fresh_triple_7": (-3442, -138, 2601),
                    "identity_fresh_12_1": (10237, 6362, 2366)}
        for label, q in expected.items():
            face, location = historical(label)
            font, records = fixture(face)
            mappings = prereadback_mappings(font, records, location)
            for name in ALL_MODELS:
                with self.subTest(label=label, model=name):
                    self.assertEqual(quantized(mappings[name]), q)

    def test_old_control_is_exactly_retained_for_every_new_and_history_request(self):
        for row in prereadback_cases(original_axes()):
            font, records = fixture(row["face_index"])
            expected = arithmetic_mappings(font, records, row["location"])[ENDPOINT]
            actual = prereadback_mappings(font, records, row["location"])[ENDPOINT]
            self.assertEqual(actual, expected, row["label"])

    def test_identity_selection_is_structural_and_preserves_raw_duplicates(self):
        face, location = historical("arithmetic_fresh_30_0")
        font, records = fixture(face)
        records["WDTH"] = deepcopy(records["wght"])
        records["HGHT"] = [[-1., -1.], [0., 0.], [0., 0.], [1., 1.]]
        records["wght"] = [[-1., -1.], [0., 0.], [1., 1.]]
        before = deepcopy(records)
        stages = prereadback_design_inputs(font, records, location)
        self.assertEqual(stages[ONCE_IDENTITY]["HGHT"], stages[ENDPOINT]["HGHT"])
        self.assertNotEqual(stages[ONCE_IDENTITY]["HGHT"], stages[ONCE_ALL]["HGHT"])
        self.assertEqual(stages[ONCE_IDENTITY]["wght"], stages[ONCE_ALL]["wght"])
        self.assertNotEqual(stages[ONCE_IDENTITY]["wght"], stages[ENDPOINT]["wght"])
        prereadback_mappings(font, records, location)
        self.assertEqual(records, before)

    def test_new_boundary_cohort_can_distinguish_once_all_from_once_identity(self):
        differences = []
        for row in prereadback_cases(original_axes()):
            if not row["is_holdout"]:
                continue
            font, records = fixture(row["face_index"])
            mappings = prereadback_mappings(font, records, row["location"])
            for tag in ("WDTH", "HGHT"):
                self.assertEqual(mappings[ONCE_ALL][tag], mappings[ONCE_IDENTITY][tag])
            if mappings[ONCE_ALL] != mappings[ONCE_IDENTITY]:
                differences.append(row)
        self.assertTrue(differences, "New cohort must distinguish the two model scopes")
        self.assertTrue(any(row.get("boundary_axis") == "wght" for row in differences))

    def test_original_source_defaults_endpoints_and_table_order_remain_intact(self):
        axes = original_axes()
        for face in (0, 5, 12, 18, 20, 24, 30):
            font, records = fixture(face)
            before = deepcopy(records)
            for index in range(3):
                location = {tag: axes[face][tag][index] for tag in TAGS}
                mappings = prereadback_mappings(font, records, location)
                for name in ALL_MODELS:
                    self.assertEqual(tuple(mappings[name]), TAGS)
                    for tag in ("WDTH", "HGHT"):
                        self.assertEqual(mappings[name][tag], (-1., 0., 1.)[index])
            self.assertEqual(records, before)

    def test_model_inputs_records_and_readback_plan_are_not_mutated(self):
        face, location = historical("arithmetic_fresh_30_0")
        font, records = fixture(face)
        before_location, before_records = deepcopy(location), deepcopy(records)
        declaration = declare_readback(location)
        stages = prereadback_design_inputs(font, records, location)
        prereadback_mappings(font, records, location)
        stages[ONCE_ALL]["HGHT"] = -999.
        self.assertEqual(location, before_location)
        self.assertEqual(records, before_records)
        self.assertEqual(declare_readback(location), declaration)
        self.assertEqual(prereadback_design_inputs(font, records, location)[ONCE_ALL]["HGHT"], 303.5934)
        self.assertEqual(stages[ENDPOINT]["HGHT"], 303.5933)

    def test_invalid_coordinates_axis_sets_and_duplicate_fvar_axis_are_rejected(self):
        face, location = historical("arithmetic_fresh_30_0")
        font, records = fixture(face)
        for factory in (prereadback_mappings, prereadback_design_inputs):
            for value in (math.nan, math.inf, -math.inf, True, 0., 1000.1):
                with self.subTest(factory=factory.__name__, value=value), self.assertRaises(ValueError):
                    factory(font, records, {**location, "WDTH": value})
            with self.assertRaises(ValueError):
                factory(font, records, {"WDTH": 500.})
            with self.assertRaises(ValueError):
                factory(font, {"WDTH": records["WDTH"]}, location)
        font["fvar"].axes.append(deepcopy(font["fvar"].axes[0]))
        with self.assertRaises(ValueError):
            prereadback_mappings(font, records, location)


class PrereadbackCohort(unittest.TestCase):
    def setUp(self):
        self.axes = original_axes()
        self.rows = prereadback_cases(self.axes)

    def test_frozen_counts_native_budget_and_independent_random_seeds(self):
        self.assertEqual(len(self.rows), 140)
        self.assertEqual(sum(row["is_holdout"] for row in self.rows), 124)
        self.assertEqual(Counter(row["group"] for row in self.rows), {
            "fresh_random_holdout": 64, "decimal_stage_instability_holdout": 24,
            "normalized16_decimal_bracket_holdout": 36, "historical_control": 16})
        self.assertEqual(sum(row["direct_native_HVF"] for row in self.rows), 68)
        self.assertEqual(len({FRESH_SEED, DECIMAL_SEED, BOUNDARY_SEED}), 3)
        self.assertFalse({FRESH_SEED, DECIMAL_SEED, BOUNDARY_SEED} &
                         {0xA3A62026, 0xA31D2026, 0xA3F00D})
        for face in range(32):
            rows = [row for row in self.rows if row["face_index"] == face
                    and row["group"] == "fresh_random_holdout"]
            self.assertEqual(len(rows), 2)
            self.assertEqual([row["direct_native_HVF"] for row in rows], [True, False])

    def test_decimal_points_are_naturally_unstable_with_full_original_tuple(self):
        rows = [row for row in self.rows if row["group"] == "decimal_stage_instability_holdout"]
        self.assertEqual(Counter((row["face_index"], row["boundary_axis"]) for row in rows),
            {(face, tag): 2 for face, _ in BOUNDARY_FACE_SIGNS for tag in TAGS})
        for row in rows:
            face, tag = row["face_index"], row["boundary_axis"]
            plan = declare_readback(row["location"])[tag]
            self.assertNotEqual(plan["once"], plan["twice"])
            self.assertEqual(row["location"][tag], (row["decimal_cell_index"] + .5) / 10000)
            self.assertLessEqual(row["arithmetic_generation_attempt"], GENERATION_ATTEMPTS)
            self.assertEqual(set(row["location"]), set(TAGS))
            for other in TAGS:
                if other != tag:
                    self.assertEqual(row["location"][other], self.axes[face][other][1])

    def test_new_normalized16_centers_are_frozen_and_bracket_stage_loss(self):
        rows = [row for row in self.rows if row["group"] == "normalized16_decimal_bracket_holdout"]
        centers = [row for row in rows if row["boundary_side"] == "at"]
        self.assertEqual([(r["face_index"], r["boundary_axis"], r["boundary_n16"],
                           r["boundary_user_center"]) for r in centers], [
            (0, "WDTH", -40815, 189.22915), (0, "wght", -14039, 415.09865),
            (0, "HGHT", -55523, 77.24045), (5, "WDTH", 34250, 761.30685),
            (5, "wght", 19642, 619.18505), (5, "HGHT", 20510, 656.47895),
            (20, "WDTH", -39127, 202.08185), (20, "wght", -59171, 138.84895),
            (20, "HGHT", -18127, 361.97865), (24, "WDTH", 36862, 781.23485),
            (24, "wght", 51954, 817.10215), (24, "HGHT", 13342, 601.79145)])
        for index in range(0, len(rows), 3):
            low, center, high = rows[index:index + 3]
            face, tag, n16 = center["face_index"], center["boundary_axis"], center["boundary_n16"]
            axis = self.axes[face][tag]
            declaration = declare_readback(center["location"])[tag]
            self.assertLess(normalize(declaration["twice"], *axis) * 65536, n16)
            self.assertGreaterEqual(normalize(declaration["once"], *axis) * 65536, n16)
            self.assertEqual(n16 % 4, 1 if n16 < 0 else 2)
            self.assertLess(center["ideal_normalized16_user_boundary"], center["location"][tag])
            self.assertEqual([row["user_offset"] for row in (low, center, high)],
                             [-BOUNDARY_USER_EPSILON, 0., BOUNDARY_USER_EPSILON])
            self.assertLess(low["location"][tag], center["location"][tag])
            self.assertLess(center["location"][tag], high["location"][tag])
            self.assertTrue(center["direct_native_HVF"])
            if tag == "HGHT":
                self.assertTrue(all(row["direct_native_HVF"] for row in (low, center, high)))

    def test_all_history_and_replay_isolations_are_explicit_nonholdouts(self):
        rows = [row for row in self.rows if not row["is_holdout"]]
        self.assertEqual(len(HISTORICAL_CASES), 8)
        self.assertTrue(all(row["direct_native_HVF"] and row["participated_in_model_selection"] for row in rows))
        for face, label, coordinates, commit, observation in HISTORICAL_CASES:
            row = next(row for row in rows if row["face_index"] == face and
                       row["historical_reference"]["label"] == label and not row.get("derived_from_historical"))
            self.assertEqual(tuple(row["location"][tag] for tag in TAGS), coordinates)
            self.assertEqual(row["historical_reference"], {"source_commit": commit,
                "label": label, "prior_observation": observation})
        derived = {row["derivation"]: row for row in rows if row.get("derived_from_historical")}
        self.assertEqual(len(derived), 8)
        _, raw = historical("arithmetic_fresh_30_0")
        plans = declare_readback(raw)
        self.assertEqual(derived["tuple_once"]["location"], {tag: plans[tag]["once"] for tag in TAGS})
        self.assertEqual(derived["tuple_twice"]["location"], {tag: plans[tag]["twice"] for tag in TAGS})
        for row in derived.values():
            self.assertEqual(row["historical_reference"]["source_commit"], ARITHMETIC_COMMIT)
        for name, field in (("HGHT_only_raw", "requested"), ("HGHT_only_once", "once"),
                            ("HGHT_only_twice", "twice")):
            self.assertEqual(derived[name]["location"], {"WDTH": 500., "wght": 500.,
                                                        "HGHT": plans["HGHT"][field]})

    def test_raw_face22_and_face30_are_not_silently_replaced_with_replay_values(self):
        for label in ("arithmetic_fresh_22_0", "arithmetic_fresh_30_0"):
            face, raw = historical(label)
            row = next(row for row in self.rows if row["label"] == f"prereadback_history_{face}_{label}")
            self.assertEqual({tag: struct.pack(">d", row["location"][tag]) for tag in TAGS},
                             {tag: struct.pack(">d", raw[tag]) for tag in TAGS})
            canonical = {tag: plan["canonical"] for tag, plan in declare_readback(raw).items()}
            self.assertNotEqual(row["location"], canonical)

    def test_generation_is_deterministic_isolated_and_has_no_duplicate_requests(self):
        axes_before, random_before = deepcopy(self.axes), random.getstate()
        self.assertEqual(prereadback_cases(self.axes), self.rows)
        self.assertEqual(self.axes, axes_before)
        self.assertEqual(random.getstate(), random_before)
        self.assertEqual(len({row["label"] for row in self.rows}), 140)
        self.assertEqual(len({(row["face_index"], *(row["location"][tag] for tag in TAGS))
                              for row in self.rows}), 140)
        self.rows[0]["location"]["WDTH"] = -999.
        self.assertGreater(prereadback_cases(self.axes)[0]["location"]["WDTH"], 0.)

    def test_bad_face_sets_spans_and_axes_fail_before_native_execution(self):
        broken = deepcopy(self.axes); del broken[31]
        with self.assertRaises(ValueError):
            prereadback_cases(broken)
        broken = deepcopy(self.axes); broken[20]["HGHT"] = (1., 500., 500.)
        with self.assertRaises(ValueError):
            prereadback_cases(broken)
        broken = deepcopy(self.axes); del broken[4]["WDTH"]
        with self.assertRaises(ValueError):
            prereadback_cases(broken)


if __name__ == "__main__":
    unittest.main()
