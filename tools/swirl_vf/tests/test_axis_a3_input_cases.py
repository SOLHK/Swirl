"""Original controls for A3 input representation; these are not native tests."""
from __future__ import annotations

import copy
from fractions import Fraction
import json
import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from axis_a3_input_cases import (FIXED_MAX, FIXED_MIN, RANDOM_SEED, TAGS,
    conditional_lower_bound, fixed16_input, input_cases, representations)


def axes():
    return {face: {"WDTH": (1., 500., 1000.), "wght": (1., weight, 1000.),
                   "HGHT": (1., 500., 1000.)}
            for face, weight in ((15, 499.), (18, 499.), (20, 700.))}


def raw_records():
    # Deliberately non-sorted and duplicated; neither condition is repaired.
    return {face: {tag: [(-16384, -16384), (4096, 3072), (0, 0),
                         (4096, 5120), (0, 256), (16384, 16384)] for tag in TAGS}
            for face in (15, 18, 20)}


class RepresentationTests(unittest.TestCase):
    def test_existing_counterexample_collides_in_both_public_input_types(self):
        low, high = [representations(v) for v in (499.006199, 499.006201)]
        self.assertEqual(low["binary64_bits"], "407f3019641f6449")
        self.assertEqual(high["binary64_bits"], "407f30196638433d")
        self.assertNotEqual(low["binary64_hex"], high["binary64_hex"])
        self.assertEqual(low["fixed16_integer"], 32702870)
        self.assertEqual(low["fixed16_integer"], high["fixed16_integer"])
        self.assertEqual(low["float32_bits"], "43f980cb")
        self.assertEqual(low["float32_bits"], high["float32_bits"])
        self.assertEqual(low["float32_value"], 499.006195068359375)
        self.assertEqual(low["fixed16_cell"], {
            "lower_inclusive": 499.00618743896484375,
            "upper_exclusive": 499.00620269775390625})
        self.assertFalse(low["native_observation"])

    def test_independent_controls_distinguish_fixed_and_single_precision(self):
        rows = input_cases(axes())
        for group, fixed_equal, single_equal in (
                ("fixed_only_collision", True, False),
                ("float32_only_collision", False, True)):
            pair = [representations(row["location"]["wght"]) for row in rows if row["group"] == group]
            self.assertEqual(len(pair), 2)
            self.assertEqual(pair[0]["fixed16_integer"] == pair[1]["fixed16_integer"], fixed_equal)
            self.assertEqual(pair[0]["float32_bits"] == pair[1]["float32_bits"], single_equal)
            self.assertNotEqual(pair[0]["binary64_bits"], pair[1]["binary64_bits"])

    def test_negative_halfway_rounding_is_toward_higher_integer(self):
        self.assertEqual(fixed16_input(-0.5 / 65536), 0)
        self.assertEqual(fixed16_input(-1.5 / 65536), -1)
        self.assertEqual(fixed16_input(0.5 / 65536), 1)
        self.assertEqual(fixed16_input(2.5 / 65536), 3)
        tie = -1.5 / 65536
        self.assertEqual(fixed16_input(math.nextafter(tie, -math.inf)), -2)
        self.assertEqual(fixed16_input(math.nextafter(tie, math.inf)), -1)

    def test_fixed_cell_open_upper_and_closed_lower_boundaries(self):
        cell = representations(499.006199)["fixed16_cell"]
        low, high = cell["lower_inclusive"], cell["upper_exclusive"]
        self.assertEqual(fixed16_input(low), 32702870)
        self.assertEqual(fixed16_input(math.nextafter(low, -math.inf)), 32702869)
        self.assertEqual(fixed16_input(math.nextafter(high, -math.inf)), 32702870)
        self.assertEqual(fixed16_input(high), 32702871)

    def test_large_negative_tie_neighbor_avoids_intermediate_rounding(self):
        tie = -30000 + 0.5 / 65536
        below = math.nextafter(tie, -math.inf)
        exact = math.floor(Fraction(below) * 65536 + Fraction(1, 2))
        self.assertEqual(fixed16_input(below), exact)
        self.assertEqual(fixed16_input(below), -1966080000)

    def test_valid_signed_range_and_rejected_values(self):
        self.assertEqual(fixed16_input(FIXED_MIN), -(2 ** 31))
        self.assertEqual(fixed16_input(FIXED_MAX), 2 ** 31 - 1)
        invalid = (True, False, None, "499", Fraction(1, 2), math.nan,
                   math.inf, -math.inf, -32769, 32768, 10 ** 1000)
        for value in invalid:
            with self.subTest(value=repr(value)[:60]), self.assertRaises(ValueError):
                representations(value)

    def test_signed_zero_preserves_binary_input_identity(self):
        negative, positive = representations(-0.), representations(0.)
        self.assertEqual(negative["binary64_bits"], "8000000000000000")
        self.assertEqual(negative["float32_bits"], "80000000")
        self.assertEqual(positive["binary64_bits"], "0000000000000000")
        self.assertEqual(negative["fixed16_integer"], positive["fixed16_integer"])
        json.dumps([negative, positive], allow_nan=False)


class ConditionalBoundTests(unittest.TestCase):
    def test_historical_delta_implies_conditional_strict_failure(self):
        result = conditional_lower_bound(0.5474853515625)
        self.assertEqual(result["minimum_worst_case_error"], 0.27374267578125)
        self.assertEqual(result["threshold_multiple"], 8.759765625)
        self.assertTrue(result["simultaneous_tolerance_impossible_if_inputs_collapse"])
        self.assertFalse(result["native_measurement_performed"])
        self.assertFalse(result["production_mapping_accepted"])
        self.assertFalse(result["continuous_space_accepted"])

    def test_tolerance_boundary_does_not_overclaim_impossibility(self):
        at_limit = 2 / 32
        self.assertFalse(conditional_lower_bound(at_limit)["simultaneous_tolerance_impossible_if_inputs_collapse"])
        self.assertTrue(conditional_lower_bound(math.nextafter(at_limit, math.inf))[
            "simultaneous_tolerance_impossible_if_inputs_collapse"])
        self.assertFalse(conditional_lower_bound(0)["simultaneous_tolerance_impossible_if_inputs_collapse"])

    def test_invalid_difference_or_limit_is_rejected(self):
        for delta, limit in ((-1, 1 / 32), (math.nan, 1 / 32), (True, 1 / 32),
                             (1, 0), (1, -1), (1, math.inf), (1, False)):
            with self.subTest(delta=delta, limit=limit), self.assertRaises(ValueError):
                conditional_lower_bound(delta, limit)


class InputPlanTests(unittest.TestCase):
    def test_plan_is_bounded_complete_and_preserves_original_ranges(self):
        source_axes, source_records = axes(), raw_records()
        before = copy.deepcopy((source_axes, source_records))
        rows = input_cases(source_axes, source_records)
        self.assertEqual(len(rows), 118)
        self.assertEqual((source_axes, source_records), before)
        self.assertEqual(len({(r["face_index"], r["label"]) for r in rows}), len(rows))
        for row in rows:
            self.assertEqual(set(row["location"]), set(TAGS))
            for tag, value in row["location"].items():
                low, _, high = source_axes[row["face_index"]][tag]
                self.assertGreaterEqual(value, low)
                self.assertLessEqual(value, high)
        json.dumps(rows, allow_nan=False)

    def test_duplicate_raw_records_keep_separate_ordinals_and_to_values(self):
        rows = input_cases(axes(), raw_records())
        selected = [row for row in rows if row["face_index"] == 18
                    and row["label"].startswith("WDTH_raw_avar_")
                    and row["label"].endswith("nearest")]
        self.assertEqual([row["avar_record_index"] for row in selected], [1, 3])
        self.assertEqual([row["avar_raw_to_f2dot14"] for row in selected], [3072, 5120])
        self.assertEqual(selected[0]["location"], selected[1]["location"])
        self.assertEqual([row["avar_original_record_count"] for row in selected], [6, 6])

    def test_decimal_triplets_straddle_exact_rational_boundaries(self):
        rows = input_cases(axes())
        for face in (15, 18, 20):
            for tag in TAGS:
                selected = [row for row in rows if row["face_index"] == face
                            and row["label"].startswith(tag + "_decimal_bin_")]
                self.assertEqual(len(selected), 3)
                numerator, denominator = selected[0]["intended_rational_boundary"]
                boundary = Fraction(int(numerator), int(denominator))
                self.assertLess(Fraction(selected[0]["location"][tag]), boundary)
                self.assertGreater(Fraction(selected[2]["location"][tag]), boundary)

    def test_seeded_holdouts_are_repeatable_and_not_a_global_rng_side_effect(self):
        random.seed(908)
        global_before = random.getstate()
        first = input_cases(axes(), raw_records())
        self.assertEqual(random.getstate(), global_before)
        second = input_cases(dict(reversed(list(axes().items()))), raw_records())
        self.assertEqual(first, second)
        selected = [row for row in first if row["group"] == "fresh_holdout"]
        self.assertEqual(len(selected), 9)
        for row in selected:
            self.assertEqual(row["random_seed"], RANDOM_SEED + row["face_index"])
            self.assertEqual(row["modeling_use"], "none_predeclared_input_only")
        self.assertNotIn(RANDOM_SEED, (20961020, 20861020))

    def test_historical_request_decimal_inputs_are_not_rewritten(self):
        rows = input_cases(axes())
        self.assertEqual([row["location"]["wght"] for row in rows[:2]], [499.006199, 499.006201])
        self.assertEqual([row["label"] for row in rows[:2]], ["existing_collision_low", "existing_collision_high"])
        self.assertEqual(rows[0]["location"]["WDTH"], 500.)
        self.assertEqual(rows[0]["location"]["HGHT"], 500.)

    def test_invalid_axes_source_identity_and_mandatory_ranges_are_rejected(self):
        cases = []
        missing = axes(); del missing[15]; cases.append(missing)
        bad = axes(); bad[True] = bad.pop(15); cases.append(bad)
        bad = axes(); del bad[15]["HGHT"]; cases.append(bad)
        bad = axes(); bad[15]["wght"] = (1., 500., 1000.); cases.append(bad)
        bad = axes(); bad[15]["wght"] = (1., 499., 499.0062); cases.append(bad)
        bad = axes(); bad[18]["WDTH"] = (1., math.nan, 1000.); cases.append(bad)
        bad = axes(); bad[18]["HGHT"] = (500., 400., 1000.); cases.append(bad)
        bad = axes(); bad[20]["WDTH"] = (1., True, 1000.); cases.append(bad)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                input_cases(value)

    def test_malformed_raw_records_are_rejected_without_mutation(self):
        for malformed in (None, [], [(0, True)], [(0, 32768)], [(0,)], "0,0"):
            source = raw_records(); source[15]["WDTH"] = malformed
            before = copy.deepcopy(source)
            with self.subTest(malformed=malformed), self.assertRaises(ValueError):
                input_cases(axes(), source)
            self.assertEqual(source, before)


if __name__ == "__main__":
    unittest.main()
