"""Original sampling regressions using authored axis ranges, without fonts."""
from copy import deepcopy
import itertools
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from axis_threshold_cases import threshold_cases


TAGS = ("WDTH", "wght", "HGHT")
RANGES = {"WDTH": (200., 500., 900.), "wght": (100., 500., 900.),
          "HGHT": (300., 500., 800.)}


def by_label(rows):
    return {label: row for row in rows for label in row["labels"]}


class AxisThresholdCaseTests(unittest.TestCase):
    def test_all_27_corners_and_six_single_axis_endpoints(self):
        rows = threshold_cases(RANGES, 0)
        actual = {tuple(row["location"][tag] for tag in TAGS) for row in rows}
        self.assertTrue(set(itertools.product(*[RANGES[tag] for tag in TAGS])).issubset(actual))
        self.assertEqual(sum(label.startswith("corner_") for row in rows for label in row["labels"]), 27)
        self.assertEqual(rows[0]["label"], "default")
        self.assertEqual(rows[0]["cohort"], "baseline")
        self.assertIn("corners", rows[0]["cohorts"])
        for tag in TAGS:
            for endpoint in (RANGES[tag][0], RANGES[tag][2]):
                expected = {name: RANGES[name][1] for name in TAGS}
                expected[tag] = endpoint
                self.assertIn(expected, [row["location"] for row in rows])

    def test_neighbours_are_distinct_adjacent_user_binary64_values(self):
        rows = by_label(threshold_cases(RANGES, 20))
        # This exact fraction would be lost if nextafter were applied to delta
        # before adding 500. Expected endpoints are constructed analytically.
        center = 500 + 25 / 4096
        values = [rows[f"default_positive_1_over_65536_{side}"]["location"]["wght"]
                  for side in ("left", "exact", "right")]
        self.assertEqual(values[1], center)
        self.assertLess(values[0], center)
        self.assertGreater(values[2], center)
        self.assertEqual(math.nextafter(values[0], math.inf), center)
        self.assertEqual(math.nextafter(values[2], -math.inf), center)
        self.assertEqual(500 + math.nextafter(25 / 4096, math.inf), center)
        for side, expected in (("negative", 500 - 25 / 1024), ("positive", 500 + 25 / 1024)):
            self.assertEqual(rows[f"default_{side}_1_over_16384_exact"]["location"]["wght"], expected)

    def test_asymmetric_original_spans_and_decimal_default_controls(self):
        ranges = {**RANGES, "wght": (100., 499., 900.)}
        rows = by_label(threshold_cases(ranges, 15))
        self.assertEqual(rows["default_negative_1_over_65536_exact"]["location"]["wght"], 499 - 399 / 65536)
        self.assertEqual(rows["default_positive_1_over_65536_exact"]["location"]["wght"], 499 + 401 / 65536)
        self.assertEqual(rows["default_negative_decimal_0001"]["location"]["wght"], 498.9999)
        self.assertEqual(rows["default_positive_decimal_0001"]["location"]["wght"], 499.0001)

    def test_target_thresholds_have_binary_and_decimal_neighbours(self):
        for face in (20, 24, 31):
            rows = by_label(threshold_cases(RANGES, face))
            for center in (300, 400):
                for name, expected, decimal_low in (("normalized16", center + 25 / 4096, center + .0061),
                                                    ("direct_half14", center + 10 / 983, center + .0101)):
                    label = f"weight_{center}_{name}"
                    values = [rows[f"{label}_{side}"]["location"]["wght"]
                              for side in ("left", "exact", "right")]
                    self.assertEqual(values[1], expected)
                    self.assertEqual(math.nextafter(values[0], math.inf), expected)
                    self.assertEqual(math.nextafter(values[2], -math.inf), expected)
                    lower = rows[f"{label}_decimal4_lower"]["location"]["wght"]
                    upper = rows[f"{label}_decimal4_upper"]["location"]["wght"]
                    self.assertEqual(lower, decimal_low)
                    self.assertLess(lower, expected)
                    self.assertGreater(upper, expected)
                    self.assertAlmostEqual(upper - lower, .0001)
        self.assertFalse(any("targeted_thresholds" in row["cohorts"] for row in threshold_cases(RANGES, 19)))

    def test_controls_and_width_readback_are_only_added_inside_original_ranges(self):
        rows = by_label(threshold_cases(RANGES, 0))
        for weight in (300., 300.01, 400., 400.01):
            self.assertEqual(rows[f"historical_weight_{weight:g}"]["location"],
                             {"WDTH": 500., "wght": weight, "HGHT": 500.})
        self.assertEqual(rows["wdth_600_5859375"]["location"],
                         {"WDTH": 600.5859375, "wght": 500., "HGHT": 500.})
        restricted = {"WDTH": (10., 15., 20.), "wght": (350., 370., 390.), "HGHT": (1., 2., 3.)}
        rows = threshold_cases(restricted, 20)
        self.assertFalse(any("historical_controls" in row["cohorts"] or "wdth_readback" in row["cohorts"]
                             or "targeted_thresholds" in row["cohorts"] for row in rows))
        for row in rows:
            self.assertEqual(set(row["location"]), set(TAGS))
            for tag, value in row["location"].items():
                self.assertLessEqual(restricted[tag][0], value)
                self.assertLessEqual(value, restricted[tag][2])

    def test_random_holdouts_repeat_by_face_and_do_not_reuse_prior_cases(self):
        rows = threshold_cases(RANGES, 20)
        self.assertEqual(rows, threshold_cases(RANGES, 20))
        triples = [row for row in rows if row["cohort"] == "random_triples"]
        weights = [row for row in rows if row["cohort"] == "random_weights"]
        self.assertEqual((len(triples), len(weights)), (3, 3))
        for row in triples + weights:
            self.assertEqual(len(row["labels"]), 1)
        for row in triples:
            self.assertTrue(all(row["location"][tag] != RANGES[tag][1] for tag in TAGS))
        for row in weights:
            self.assertEqual(row["location"]["WDTH"], 500.)
            self.assertEqual(row["location"]["HGHT"], 500.)
            self.assertNotEqual(row["location"]["wght"], 500.)
        other = [row["location"] for row in threshold_cases(RANGES, 24)
                 if row["cohort"] in ("random_triples", "random_weights")]
        self.assertFalse(any(row["location"] in other for row in triples + weights))

    def test_exact_location_deduplication_preserves_aliases_and_source(self):
        ranges = {tag: list(values) for tag, values in RANGES.items()}
        original = deepcopy(ranges)
        rows = threshold_cases(ranges, 20)
        self.assertEqual(ranges, original)
        self.assertEqual(len(rows), len({tuple(row["location"][tag] for tag in TAGS) for row in rows}))
        for row in rows:
            self.assertEqual(row["label"], row["labels"][0])
            self.assertEqual(row["cohort"], row["cohorts"][0])
        ranges["wght"][1] = 300.
        rows = threshold_cases(ranges, 20)
        self.assertIn("historical_weight_300", rows[0]["labels"])
        self.assertIn("historical_controls", rows[0]["cohorts"])

    def test_invalid_ranges_tags_and_face_are_rejected(self):
        for ranges in ({"WDTH": (0, 1, 2)}, {**RANGES, "wght": (0, 0, 0)},
                       {**RANGES, "HGHT": (0, math.nan, 1)},
                       {**RANGES, "HGHT": (2, 1, 0)},
                       {**RANGES, "HGHT": (0, True, 2)}):
            with self.assertRaises(ValueError):
                threshold_cases(ranges, 0)
        for face in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                threshold_cases(RANGES, face)


if __name__ == "__main__":
    unittest.main()
