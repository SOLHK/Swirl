"""Independent sampling contracts with authored ranges and no font assets."""
from copy import deepcopy
from fractions import Fraction
import itertools
import math
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from axis_anchor_cases import anchor_cases
from axis_threshold_cases import threshold_cases


TAGS = ("WDTH", "wght", "HGHT")
FACES = (0, 5, 10, 15, 20, 24, 31)
RANGES = {"WDTH": (200., 500., 900.), "wght": (100., 499., 900.), "HGHT": (100., 500., 900.)}


def source_ranges(axes=RANGES):
    return {face: deepcopy(axes) for face in range(32)}


def by_label(rows):
    return {label: row for row in rows for label in row["labels"]}


class AxisAnchorCaseTests(unittest.TestCase):
    def test_all_selected_faces_and_27_original_axis_combinations(self):
        cases = anchor_cases(source_ranges())
        self.assertEqual(tuple(cases), FACES)
        expected = set(itertools.product(*(RANGES[tag] for tag in TAGS)))
        for rows in cases.values():
            points = {tuple(row["location"][tag] for tag in TAGS) for row in rows}
            self.assertTrue(expected <= points)
            self.assertEqual(sum(label.startswith("corner_") for row in rows for label in row["labels"]), 27)
            self.assertEqual(rows[0]["location"], {tag: RANGES[tag][1] for tag in TAGS})
            self.assertTrue(all(tuple(row["location"]) == TAGS for row in rows))

    def test_declared_boundary_controls_and_all_seven_mixed_positions(self):
        rows = anchor_cases(source_ranges())[20]
        for cohort, expected in (
                ("400_boundaries", {399.9, 399.96, 399.9601, 400., 400.0399, 400.04, 400.0401, 400.1}),
                ("300_controls", {299.96, 299.9817, 300., 300.0062, 300.01, 300.03, 300.04}),
                ("mixed_axes", {299.9817, 300.01, 399.96, 400.01, 400.04, 400.041, 500.01})):
            actual = [row["location"] for row in rows if cohort in row["cohorts"]]
            self.assertEqual({point["wght"] for point in actual}, expected)
            for point in actual:
                self.assertEqual(point["WDTH"], 600.5859375 if cohort == "mixed_axes" else 500.)
                self.assertEqual(point["HGHT"], 250. if cohort == "mixed_axes" else 500.)

    def test_near_defaults_and_midpoints_use_each_actual_original_range(self):
        rows = by_label(anchor_cases(source_ranges())[15])
        for tag, (low, default, high) in RANGES.items():
            for delta in (.0001, .01, .06):
                for side, sign in (("below", -1), ("above", 1)):
                    self.assertEqual(rows[f"{tag}_default_{side}_{delta:g}"]["location"][tag], default + sign * delta)
            for side, offset in (("below", -.0001), ("exact", 0), ("above", .0001)):
                self.assertEqual(rows[f"{tag}_midpoint_{side}"]["location"][tag], (low + high) / 2 + offset)
        self.assertEqual(rows["wght_midpoint_exact"]["location"]["wght"], 500.)
        self.assertEqual(rows["HGHT_midpoint_exact"]["label"], "default")

    def test_endpoint_steps_and_binary64_neighbours_are_not_lost_in_delta(self):
        rows = by_label(anchor_cases(source_ranges())[0])
        expected = {
            ("WDTH", "minimum"): 200 + Fraction(75, 16384),
            ("WDTH", "maximum"): 900 - Fraction(25, 4096),
            ("wght", "minimum"): 100 + Fraction(399, 65536),
            ("wght", "maximum"): 900 - Fraction(401, 65536),
            ("HGHT", "minimum"): 100 + Fraction(25, 4096),
            ("HGHT", "maximum"): 900 - Fraction(25, 4096),
        }
        for (tag, end), value in expected.items():
            values = [rows[f"{tag}_{end}_inward_normalized16_{side}"]["location"][tag]
                      for side in ("left", "exact", "right")]
            self.assertEqual(values[1], float(value))
            self.assertLess(values[0], values[1])
            self.assertGreater(values[2], values[1])
            self.assertEqual(math.nextafter(values[0], math.inf), values[1])
            self.assertEqual(math.nextafter(values[2], -math.inf), values[1])
            self.assertTrue(all(RANGES[tag][0] < v < RANGES[tag][2] for v in values))
        self.assertEqual(200 + math.nextafter(75 / 16384, math.inf), 200 + 75 / 16384)

    def test_holdouts_are_deterministic_fresh_and_independent_by_face(self):
        cases = anchor_cases(source_ranges())
        self.assertEqual(cases, anchor_cases(source_ranges()))
        seen = set()
        for face, rows in cases.items():
            triples = [row for row in rows if row["cohort"] == "random_triples"]
            weights = [row for row in rows if row["cohort"] == "random_weights"]
            self.assertEqual((len(triples), len(weights)), (6, 6))
            old = {tuple(row["location"][tag] for tag in TAGS) for row in threshold_cases(RANGES, face)}
            # Prior counterexample holdouts used this separate seed and domain.
            prior_rng = random.Random(20561020 + face)
            old.update((500., prior_rng.uniform(440., 495.), 500.) for _ in range(8))
            for row in triples + weights:
                point = tuple(row["location"][tag] for tag in TAGS)
                self.assertNotIn(point, old)
                self.assertNotIn(point, seen)
                seen.add(point)
            self.assertTrue(all(all(row["location"][tag] != RANGES[tag][1] for tag in TAGS) for row in triples))
            self.assertTrue(all(row["location"]["WDTH"] == 500. and row["location"]["HGHT"] == 500. for row in weights))

    def test_duplicate_locations_keep_aliases_and_input_is_unchanged(self):
        source = source_ranges({**RANGES, "wght": [100., 300., 900.]})
        before = deepcopy(source)
        cases = anchor_cases(source)
        self.assertEqual(source, before)
        for rows in cases.values():
            self.assertEqual(len(rows), len({tuple(row["location"][tag] for tag in TAGS) for row in rows}))
            labels = [label for row in rows for label in row["labels"]]
            self.assertEqual(len(labels), len(set(labels)))
            self.assertEqual(rows[0]["label"], "default")
            self.assertIn("weight_300_control_300", rows[0]["labels"])
            self.assertIn("300_controls", rows[0]["cohorts"])
            for row in rows:
                self.assertEqual(row["label"], row["labels"][0])
                self.assertEqual(row["cohort"], row["cohorts"][0])

    def test_outside_candidates_are_omitted_without_clamping(self):
        narrow = {"WDTH": (10., 10., 10.01), "wght": (20., 20.005, 20.01), "HGHT": (30., 30.01, 30.01)}
        rows = anchor_cases(source_ranges(narrow))[24]
        labels = by_label(rows)
        self.assertNotIn("WDTH_default_below_0.0001", labels)
        self.assertNotIn("HGHT_default_above_0.0001", labels)
        self.assertNotIn("wght_default_above_0.06", labels)
        self.assertFalse(any(cohort in row["cohorts"] for row in rows
                             for cohort in ("300_controls", "400_boundaries", "mixed_axes")))
        for row in rows:
            self.assertTrue(all(narrow[tag][0] <= value <= narrow[tag][2] for tag, value in row["location"].items()))

    def test_invalid_face_sets_tags_and_even_unselected_ranges_are_rejected(self):
        bad_sources = [{}, {face: RANGES for face in range(31)}, {face: RANGES for face in range(33)}]
        for key in (False, 0.):
            source = source_ranges(); del source[0]; source[key] = deepcopy(RANGES)
            bad_sources.append(source)
        for bad in ((0, 0, 0), (2, 1, 0), (0, 3, 2), (0, math.nan, 2),
                    (0, 1, math.inf), (0, True, 2), (0, 1), (0, 1, 10**400), None):
            source = source_ranges(); source[1]["wght"] = bad
            bad_sources.append(source)
        source = source_ranges(); source[31] = {"wght": (0, 1, 2)}
        bad_sources.append(source)
        for source in bad_sources:
            with self.subTest(source_type=type(source)):
                with self.assertRaises(ValueError):
                    anchor_cases(source)


if __name__ == "__main__":
    unittest.main()
