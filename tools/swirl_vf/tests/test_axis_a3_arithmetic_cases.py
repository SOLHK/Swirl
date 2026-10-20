"""A3 arithmetic/cohort contracts; passing tests do not certify Apple output."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from axis_a3_arithmetic_cases import (ALL_AXES_CONTROL, ALL_MODELS,
    BOUNDARY_N16_BY_FACE, BOUNDARY_USER_EPSILON, DEFAULT_FACES, DIVSUB,
    ENDPOINT, FRESH_SEED, HISTORICAL_CASES, MODEL_NAMES, NEW_MODELS, OFFSET,
    TAGS, arithmetic_cases, arithmetic_mappings, declare_readback)


WEIGHT_RECORDS = [(-1., -1.), (-1., -.81597900390625), (-.75, -.57196044921875),
    (-.5, -.387939453125), (-.25, -.18798828125), (-.00244140625, 0.),
    (0., 0.), (0., .00396728515625), (.25, .19598388671875),
    (.5, .39599609375), (.75, .5999755859375), (1., .79998779296875), (1., 1.)]
FOCUS = {"WDTH": 395.1762070327519, "wght": 493.5928547043863,
         "HGHT": 579.3731774437933}


def original_axes():
    result = {}
    for face in range(32):
        if face < 20:
            weight = (100., 501. if face % 10 < 5 else 499., 900.)
        elif face < 24:
            weight = (100., 500., 600.)
        else:
            weight = (100., 500., 900.)
        result[face] = {"WDTH": (1., 500., 1000.), "wght": weight,
                        "HGHT": (1., 500., 1000.)}
    return result


def fixture(face=18):
    axes = original_axes()[face]
    font = {"fvar": SimpleNamespace(axes=[SimpleNamespace(axisTag=tag,
        minValue=values[0], defaultValue=values[1], maxValue=values[2])
        for tag, values in axes.items()])}
    records = {tag: [(-1., -1.), (0., 0.), (1., 1.)] for tag in TAGS}
    records["wght"] = deepcopy(WEIGHT_RECORDS)
    return font, records


def quantized(mapping):
    return tuple(round(mapping[tag] * 16384) for tag in TAGS)


class ArithmeticModels(unittest.TestCase):
    def test_archived_focus_full_vector_and_original_record_sequence(self):
        font, records = fixture()
        before_records, before_location = deepcopy(records), dict(FOCUS)
        mappings = arithmetic_mappings(font, records, FOCUS)
        self.assertEqual(tuple(mappings), ALL_MODELS)
        self.assertEqual(quantized(mappings[MODEL_NAMES[0]]), (-3441, -138, 2601))
        for name in (ENDPOINT, OFFSET, DIVSUB):
            self.assertEqual(quantized(mappings[name]), (-3442, -138, 2601))
        self.assertEqual(records, before_records)
        self.assertEqual(FOCUS, before_location)

    def test_positive_native_counterexample_keeps_binary64_in_structural_candidates(self):
        font, records = fixture(12)
        location = {"WDTH": 812.4237777627202, "wght": 690.8750329989548,
                    "HGHT": 572.2184188469829}
        mappings = arithmetic_mappings(font, records, location)
        self.assertEqual(mappings[MODEL_NAMES[1]]["WDTH"] * 16384, 10238)
        for name in (ENDPOINT, OFFSET, DIVSUB):
            self.assertEqual(mappings[name]["WDTH"] * 16384, 10237)
        self.assertEqual(mappings[ALL_AXES_CONTROL]["WDTH"] * 16384, 10238)

    def test_negative_truncation_and_height_do_not_revert_to_direct14_rounding(self):
        font, records = fixture()
        for tag, value, expected in (("WDTH", 445.1015723732783, -1802),
                                     ("HGHT", 10.088478435611686, -16085)):
            location = {"WDTH": 500., "wght": 499., "HGHT": 500., tag: value}
            mappings = arithmetic_mappings(font, records, location)
            for name in (ENDPOINT, OFFSET, DIVSUB):
                self.assertEqual(mappings[name][tag] * 16384, expected)

    def test_new_boundary_discriminates_divsub_and_preselects_height_native_HVF(self):
        axes = original_axes()
        selected = {row["boundary_axis"]: row for row in arithmetic_cases(axes)
                    if row["label"].startswith("arithmetic_integer_0_")
                    and row["boundary_side"] == "above"}
        font, records = fixture(0)
        for tag in ("WDTH", "HGHT"):
            row = selected[tag]
            mappings = arithmetic_mappings(font, records, row["location"])
            self.assertTrue(row["direct_native_HVF"])
            self.assertEqual(mappings[ENDPOINT][tag] * 16384, -10634)
            self.assertEqual(mappings[OFFSET][tag] * 16384, -10634)
            self.assertEqual(mappings[DIVSUB][tag] * 16384, -10635)

    def test_original_binary64_collision_survives_candidates_and_refutes_control(self):
        font, records = fixture(15)
        result = []
        for value in (499.006199, 499.006201):
            result.append(arithmetic_mappings(font, records,
                {"WDTH": 500., "wght": value, "HGHT": 500.}))
        for name in (ENDPOINT, OFFSET, DIVSUB):
            self.assertEqual([row[name]["wght"] * 16384 for row in result], [0, 65])
        self.assertEqual([row[ALL_AXES_CONTROL]["wght"] * 16384 for row in result], [65, 65])

    def test_structural_detection_never_deduplicates_or_assumes_axis_names(self):
        font, records = fixture()
        records["WDTH"] = deepcopy(WEIGHT_RECORDS)
        records["HGHT"] = [(-1., -1.), (0., 0.), (0., 0.), (1., 1.)]
        before = deepcopy(records)
        mappings = arithmetic_mappings(font, records, FOCUS)
        for name in (ENDPOINT, OFFSET, DIVSUB):
            self.assertEqual(mappings[name], mappings[MODEL_NAMES[1]])
        self.assertEqual(records, before)

    def test_nonidentity_weight_always_retains_old_float32_mapping(self):
        font, records = fixture()
        for value in (100., 279.16583, 498.9999, 499., 499.006199, 499.006201, 900.):
            mappings = arithmetic_mappings(font, records,
                {"WDTH": 395.1762070327519, "wght": value, "HGHT": 812.4237777627202})
            for name in (ENDPOINT, OFFSET, DIVSUB):
                self.assertEqual(mappings[name]["wght"], mappings[MODEL_NAMES[1]]["wght"])

    def test_defaults_endpoints_and_axis_order_remain_original(self):
        font, records = fixture()
        axes = original_axes()[18]
        for index in range(3):
            mappings = arithmetic_mappings(font, records, {tag: axes[tag][index] for tag in TAGS})
            for name in ALL_MODELS:
                self.assertEqual(tuple(mappings[name]), TAGS)
                self.assertEqual(mappings[name]["WDTH"], (-1., 0., 1.)[index])
                self.assertEqual(mappings[name]["HGHT"], (-1., 0., 1.)[index])

    def test_invalid_coordinates_fail_before_model_evaluation(self):
        font, records = fixture()
        for value in (math.nan, math.inf, -math.inf, True, 0., 1000.1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                arithmetic_mappings(font, records, {**FOCUS, "WDTH": value})
        with self.assertRaises(ValueError):
            arithmetic_mappings(font, records, {"WDTH": 500.})
        with self.assertRaises(ValueError):
            arithmetic_mappings(font, {"WDTH": records["WDTH"]}, FOCUS)


class ArithmeticCohort(unittest.TestCase):
    def setUp(self):
        self.axes = original_axes()
        self.rows = arithmetic_cases(self.axes)

    def test_frozen_new_counts_and_native_selection(self):
        self.assertEqual(len(self.rows), 201)
        self.assertEqual(sum(row["is_holdout"] for row in self.rows), 160)
        self.assertEqual(Counter(row["group"] for row in self.rows), {
            "fresh_random_holdout": 64, "normalized16_integer_boundary_holdout": 36,
            "default_omission_boundary_holdout": 60, "historical_control": 41})
        self.assertEqual(sum(row["direct_native_HVF"] for row in self.rows), 93)
        for face in range(32):
            fresh = [row for row in self.rows if row["face_index"] == face
                     and row["group"] == "fresh_random_holdout"]
            self.assertEqual(len(fresh), 2)
            self.assertEqual([row["direct_native_HVF"] for row in fresh], [True, False])

    def test_only_deliberately_repeated_all_default_tuples_are_duplicated(self):
        grouped = {}
        for row in self.rows:
            key = (row["face_index"], *(row["location"][tag] for tag in TAGS))
            grouped.setdefault(key, []).append(row)
        repeats = [rows for rows in grouped.values() if len(rows) > 1]
        self.assertEqual(len(grouped), 193)
        self.assertEqual(len(repeats), 4)
        for rows in repeats:
            self.assertEqual(len(rows), 3)
            self.assertEqual({row["boundary_axis"] for row in rows}, set(TAGS))
            self.assertTrue(all(row["intentional_repeated_all_default"] for row in rows))
        self.assertEqual(len({row["label"] for row in self.rows}), 201)

    def test_integer_boundary_brackets_preserve_full_original_axis_tuple(self):
        rows = [row for row in self.rows if row["group"] == "normalized16_integer_boundary_holdout"]
        for index in range(0, len(rows), 3):
            low, center, high = rows[index:index + 3]
            face, tag = center["face_index"], center["boundary_axis"]
            minimum, default, maximum = self.axes[face][tag]
            n16 = center["boundary_n16"]
            self.assertIn((face, n16), BOUNDARY_N16_BY_FACE)
            span = default - minimum if n16 < 0 else maximum - default
            self.assertEqual(center["location"][tag], default + n16 * span / 65536)
            self.assertEqual([row["user_offset"] for row in (low, center, high)],
                             [-BOUNDARY_USER_EPSILON, 0., BOUNDARY_USER_EPSILON])
            self.assertLess(low["location"][tag], center["location"][tag])
            self.assertLess(center["location"][tag], high["location"][tag])
            self.assertTrue(center["direct_native_HVF"])
            for row in (low, center, high):
                self.assertEqual(set(row["location"]), set(TAGS))
                self.assertTrue(all(row["location"][other] == self.axes[face][other][1]
                                    for other in TAGS if other != tag))

    def test_default_omission_cases_retain_nextafter_and_decimal_input_bits(self):
        rows = [row for row in self.rows if row["group"] == "default_omission_boundary_holdout"]
        self.assertEqual({row["face_index"] for row in rows}, set(DEFAULT_FACES))
        for index in range(0, len(rows), 5):
            below, adjacent_below, exact, adjacent_above, above = rows[index:index + 5]
            face, tag = exact["face_index"], exact["boundary_axis"]
            default = self.axes[face][tag][1]
            self.assertEqual(adjacent_below["location"][tag], math.nextafter(default, -math.inf))
            self.assertEqual(adjacent_above["location"][tag], math.nextafter(default, math.inf))
            self.assertEqual(exact["location"][tag], default)
            self.assertEqual(below["location"][tag], default - .0001)
            self.assertEqual(above["location"][tag], default + .0001)
            # Requested nondefault inputs remain present even when their
            # declared decimal replay maps back to the default.
            self.assertNotEqual(adjacent_above["location"][tag], default)
            self.assertEqual(declare_readback(adjacent_above["location"])[tag]["canonical"], default)

    def test_all_prior_nonexact_positions_are_controls_and_native_HVF_selected(self):
        history = [row for row in self.rows if row["group"] == "historical_control"]
        self.assertEqual(len(HISTORICAL_CASES), 39)
        self.assertTrue(all(not row["is_holdout"] and row["direct_native_HVF"] for row in history))
        self.assertTrue(all(len(row["historical_reference"]["source_commit"]) == 40 for row in history))
        labels = {row["historical_reference"]["label"] for row in history}
        self.assertTrue({"identity_fresh_12_1", "identity_fresh_2_0", "identity_fresh_23_0",
            "a3_fresh_holdout_1", "a3_fresh_holdout_5", "archived_face18_fresh_triple_7"} <= labels)
        for face, label, coordinates, _, _ in HISTORICAL_CASES:
            row = next(row for row in history if row["face_index"] == face
                       and row["historical_reference"]["label"] == label)
            self.assertEqual(tuple(row["location"][tag] for tag in TAGS), coordinates)
        collision = [row for row in history if row["label"].startswith("arithmetic_original_collision_")]
        self.assertEqual([row["location"]["wght"] for row in collision], [499.006199, 499.006201])

    def test_generation_is_deterministic_isolated_and_does_not_mutate_global_random_state(self):
        before_axes, before_rng = deepcopy(self.axes), random.getstate()
        self.assertEqual(self.rows, arithmetic_cases(self.axes))
        self.assertEqual(self.axes, before_axes)
        self.assertEqual(random.getstate(), before_rng)
        self.rows[0]["location"]["WDTH"] = -999.
        self.assertGreater(arithmetic_cases(self.axes)[0]["location"]["WDTH"], 0.)
        self.assertNotIn(FRESH_SEED, (0xA31D2026, 0xA3F00D))

    def test_missing_faces_invalid_spans_and_missing_axes_fail_before_native(self):
        broken = deepcopy(self.axes); del broken[31]
        with self.assertRaises(ValueError):
            arithmetic_cases(broken)
        broken = deepcopy(self.axes); broken[20]["HGHT"] = (1., 500., 500.)
        with self.assertRaises(ValueError):
            arithmetic_cases(broken)
        broken = deepcopy(self.axes); del broken[4]["WDTH"]
        with self.assertRaises(ValueError):
            arithmetic_cases(broken)


class ArchivedExploratoryCompatibility(unittest.TestCase):
    """Read already measured safe artifacts; never report this as a native run."""
    ARCHIVES = (
        ("hvar_22a89a1", "hvar.json",
         "63f4f3c36a37a9690efcf2bdc754fad9d3659d6fb83c0ed9f8a6a91d1db542b1",
         "cfcab697ff93d6756e1fb2840d4836428f2bf8a37f85752a4d70f4be1a0ae84a",
         "22a89a154217c5a4ea65788d2994e99e816ffabf"),
        ("identity_0c603aa", "identity-avar.json",
         "eda7c6db0b3bfe09d40781feb4f8cb26ad074fa57c82f6d50b7dbfb78efeef14",
         "7fa5578a1b8f125e0d2fc07ae3dec64e02c2ddbc1a6e0411cd37992fa2841d65",
         "0c603aad04786d4e89cbb6399fc60b06cac7c58a"),
    )

    @classmethod
    def setUpClass(cls):
        cls.reports = []
        platform = Path(__file__).resolve().parents[1] / "platform"
        for identifier, member, zip_sha, json_sha, commit in cls.ARCHIVES:
            path = platform / f"axis_a3_native_{identifier}.zip"
            if hashlib.sha256(path.read_bytes()).hexdigest() != zip_sha:
                raise AssertionError("Archived A3 ZIP hash changed")
            with zipfile.ZipFile(path) as archive:
                if archive.namelist() != [member]:
                    raise AssertionError("Unexpected A3 evidence ZIP member")
                data = archive.read(member)
            if hashlib.sha256(data).hexdigest() != json_sha:
                raise AssertionError("Archived A3 report hash changed")
            report = json.loads(data)
            if report["source_commit"] != commit:
                raise AssertionError("Archived A3 report commit changed")
            cls.reports.append(report)

    def pairs(self, report):
        selected_face = report.get("selected_face")
        observations = {(row.get("face_index", selected_face), row["label"]): row
                        for row in report["modes"][0]["observations"]}
        self.assertEqual(len(observations), len(report["modes"][0]["observations"]))
        self.assertEqual(len(observations), len(report["cases"]))
        for case in report["cases"]:
            face = case.get("face_index", selected_face)
            observation = observations[face, case["label"]]
            self.assertEqual(case["location"], observation["location"])
            self.assertEqual(set(case["location"]), set(TAGS))
            yield face, case, observation

    def test_historical_controls_cover_every_archived_metric_or_native_HVF_failure(self):
        expected, seen = [], {}
        for report in self.reports:
            for face, case, observation in self.pairs(report):
                failures = tuple(name for name, check in observation["model_checks"].items()
                    if check["maximum_error"] != 0 or any(
                        row["maximum_point_error"] != 0 for row in check["native_HVF_geometry"]))
                if not failures:
                    continue
                coordinates = tuple(case["location"][tag] for tag in TAGS)
                key = (face, coordinates)
                if key in seen:
                    # The repeated focus is retained under its first original
                    # label; later evidence must not add a lost failure model.
                    self.assertTrue(set(failures) <= set(seen[key][-1]))
                    continue
                row = (face, case["label"], coordinates, report["source_commit"], failures)
                seen[key] = row
                expected.append(row)
        self.assertEqual(tuple(expected), HISTORICAL_CASES)
        self.assertEqual(len(expected), 39)
        focus = next(row for row in HISTORICAL_CASES if row[1] == "archived_face18_fresh_triple_7")
        self.assertIn(MODEL_NAMES[0], focus[-1])
        self.assertIn(MODEL_NAMES[1], focus[-1])

    def test_exploratory_candidates_reuse_exact_full_vectors_without_claiming_new_native_evidence(self):
        counts = {name: Counter() for name in (ENDPOINT, OFFSET, DIVSUB)}
        native_locations = {name: set() for name in counts}
        for report in self.reports:
            self.assertIs(report["mapping_accepted"], False)
            self.assertIs(report["continuous_space_accepted"], False)
            for face, case, observation in self.pairs(report):
                source = report["original_faces"][face] if "original_faces" in report else report
                axes = source["original_axes"]
                records = source["original_avar_records_in_table_order"]
                font = {"fvar": SimpleNamespace(axes=[SimpleNamespace(axisTag=tag,
                    minValue=limits[0], defaultValue=limits[1], maxValue=limits[2])
                    for tag, limits in axes.items()])}
                before_records = deepcopy(records)
                predictions = arithmetic_mappings(font, records, case["location"])
                self.assertEqual(records, before_records)
                for name in counts:
                    full_vector = predictions[name]
                    matching = [model for model, archived in case["declared_models"].items()
                                if archived == full_vector]
                    self.assertTrue(matching, (face, case["label"], name))
                    counts[name]["full_vector_metric_exact"] += 1
                    native = False
                    for model in matching:
                        check = observation["model_checks"][model]
                        self.assertEqual(check["maximum_error"], 0.)
                        self.assertIs(check["exact"], True)
                        if check["native_HVF_geometry"]:
                            native = True
                            self.assertEqual({row["glyph_id"] for row in check["native_HVF_geometry"]},
                                             {5, 19177})
                            self.assertTrue(all(row["maximum_point_error"] == 0
                                                for row in check["native_HVF_geometry"]))
                    if native:
                        counts[name]["full_vector_native_HVF_exact"] += 1
                        native_locations[name].add((face, *(case["location"][tag] for tag in TAGS)))
        for name in counts:
            self.assertEqual(counts[name], {"full_vector_metric_exact": 137,
                                           "full_vector_native_HVF_exact": 38})
            self.assertEqual(len(native_locations[name]), 36)


if __name__ == "__main__":
    unittest.main()
