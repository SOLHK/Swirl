"""Original numeric predictions and protocol controls, not native acceptance.

No source font asset, Apple outline or measured native metric is used here.
Synthetic quadratic/blank records exercise safe comparisons. The two nearby
binary64 inputs sharing a proposed Fixed 16.16 value are a falsifiable
observation plan; these tests cannot establish native equivalence.
"""
from copy import deepcopy
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from probe_axis_input_resolution import fixed16_input, resolution_cases, summarize_pair
from test_verified_axis_oracle import native_record


TAGS = ("WDTH", "wght", "HGHT")
RANGES = {"WDTH": (1., 500., 1000.), "wght": (100., 499., 900.),
          "HGHT": (1., 500., 1000.)}
DECLARED = (
    ("collision_low", 499.006199),
    ("collision_high", 499.006201),
    ("default", 499.),
    ("canonical_low", 499.0061),
    ("canonical_high", 499.0062),
    ("shared_fixed_input", 32702870 / 65536),
)


def authored_pair():
    """Two distinct requests with the same authored quadratic and blank glyph."""
    batches = []
    for label, weight in DECLARED[:2]:
        request = {"request_id": "authored_" + label, "face_index": 15,
                   "location": {"WDTH": 500., "wght": weight, "HGHT": 500.}}
        records = {gid: native_record(request, gid) for gid in (0, 1)}
        records[0].update(commands=[["moveTo", 0., 0.],
                                    ["qCurveTo", 2., 4., 5., 0.], ["closePath"]],
                          bounds=[0., 0., 5., 2.], lsb=0.)
        batches.append(records)
    return tuple(batches)


class AxisInputResolutionTests(unittest.TestCase):
    def test_exact_half_grid_rounds_toward_positive_infinity_for_both_signs(self):
        # These fractions are exactly representable in binary64. Explicit
        # expected integers distinguish ties-to-positive from ties-to-even or
        # ties-away-from-zero without reusing the implementation's expression.
        cases = ((Fraction(1, 131072), 1), (Fraction(-1, 131072), 0),
                 (Fraction(3, 131072), 2), (Fraction(-3, 131072), -1),
                 (Fraction(5, 131072), 3), (Fraction(-5, 131072), -2),
                 (Fraction(17) + Fraction(1, 131072), 1114113),
                 (Fraction(-17) - Fraction(1, 131072), -1114112))
        for value, expected in cases:
            with self.subTest(value=value):
                actual = fixed16_input(float(value))
                self.assertIs(type(actual), int)
                self.assertEqual(actual, expected)

    def test_integer_grid_and_nontie_controls(self):
        cases = ((0, 0), (-0., 0), (2, 131072), (-2, -131072),
                 (1 / 65536, 1), (-1 / 65536, -1),
                 (1 / 262144, 0), (-1 / 262144, 0),
                 (3 / 262144, 1), (-3 / 262144, -1))
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(fixed16_input(value), expected)

    def test_invalid_fixed_inputs_are_refused(self):
        for value in (True, False, math.nan, math.inf, -math.inf,
                      None, "499.0062", [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                fixed16_input(value)

    def test_all_six_predeclared_points_keep_order_and_every_original_axis(self):
        rows = resolution_cases(RANGES)
        self.assertIs(type(rows), list)
        self.assertEqual([row["label"] for row in rows], [label for label, _ in DECLARED])
        self.assertEqual(len(rows), 6)
        self.assertEqual(len({tuple(row["location"][tag] for tag in TAGS) for row in rows}), 6)
        for row, (_, weight) in zip(rows, DECLARED):
            point = row["location"]
            self.assertEqual(set(point), set(TAGS))
            self.assertEqual(point, {"WDTH": 500., "wght": weight, "HGHT": 500.})
            self.assertTrue(all(type(value) in (int, float) and math.isfinite(value)
                                and RANGES[tag][0] <= value <= RANGES[tag][2]
                                for tag, value in point.items()))

    def test_distinct_binary64_collision_inputs_share_the_declared_fixed_integer(self):
        rows = {row["label"]: row["location"] for row in resolution_cases(RANGES)}
        low, high = rows["collision_low"]["wght"], rows["collision_high"]["wght"]
        self.assertLess(low, high)
        self.assertNotEqual(low.hex(), high.hex())
        for value in (low, high):
            # Independent rational bounds establish membership of one nearest
            # rounding cell; equality of two function results alone would not.
            scaled = Fraction.from_float(value) * 65536
            self.assertLess(Fraction(65405739, 2), scaled)
            self.assertLess(scaled, Fraction(65405741, 2))
            self.assertEqual(fixed16_input(value), 32702870)
        shared = rows["shared_fixed_input"]["wght"]
        self.assertEqual(Fraction.from_float(shared) * 65536, 32702870)
        self.assertEqual(fixed16_input(shared), 32702870)
        self.assertNotEqual(shared, low)
        self.assertNotEqual(shared, high)

    def test_input_ranges_and_returned_locations_are_not_mutated_or_aliased(self):
        axes = {tag: list(values) for tag, values in RANGES.items()}
        before = deepcopy(axes)
        rows = resolution_cases(axes)
        self.assertEqual(axes, before)
        self.assertEqual(rows, resolution_cases(axes))
        untouched = deepcopy(rows[1:])
        rows[0]["location"]["wght"] = -123.
        self.assertEqual(rows[1:], untouched)
        self.assertEqual(axes, before)
        self.assertEqual(resolution_cases(axes)[0]["location"]["wght"], 499.006199)

    def test_wrong_defaults_axis_sets_and_invalid_or_excluding_ranges_are_refused(self):
        invalid = [None, {}, {tag: value for tag, value in RANGES.items() if tag != "HGHT"},
                   {**RANGES, "wdth": RANGES["WDTH"]}]
        for tag in TAGS:
            low, default, high = RANGES[tag]
            invalid.append({**RANGES, tag: (low, default + 1, high)})
        for bounds in ((900., 499., 100.), (500., 499., 900.),
                       (100., 499., 498.), (499., 499., 499.),
                       (100., 499., 499.00619), (math.nan, 499., 900.),
                       (100., 499., math.inf), (False, 499., 900.),
                       (100., "499", 900.), (100., 499.), None):
            invalid.append({**RANGES, "wght": bounds})
        for axes in invalid:
            before = deepcopy(axes)
            with self.subTest(axes=axes), self.assertRaises(ValueError):
                resolution_cases(axes)
            self.assertEqual(axes, before)

    def test_distinct_request_locations_do_not_become_payload_differences(self):
        left, right = authored_pair()
        before = deepcopy((left, right))
        self.assertNotEqual(left[0]["location"], right[0]["location"])
        rows = summarize_pair(left, right)
        self.assertEqual([row["glyph_id"] for row in rows], [0, 1])
        for row in rows:
            self.assertTrue(row["payload_identical"])
            self.assertTrue(row["raw_commands_identical"])
            self.assertFalse(row["readback_identical"])
            self.assertEqual(row["metric_max_error"], 0.)
            self.assertTrue(all(value == 0. for value in row["metric_differences"].values()))
            self.assertEqual(row["numeric_geometry"]["status"], "within_budget")
            self.assertEqual(row["numeric_geometry"]["maximum_point_error"], 0.)
            self.assertEqual(row["numeric_geometry"]["legacy"]["status"], "within_budget")
        self.assertEqual((left, right), before)
        serialized = json.dumps(rows, allow_nan=False)
        for raw_key in ('"commands"', '"points"', '"location"', '"reported_location"'):
            self.assertNotIn(raw_key, serialized)

    def test_unknown_private_payload_difference_is_detected_without_value_disclosure(self):
        sentinel = "AUTHORED_PRIVATE_SENTINEL_914782.375"
        for present_on_left in (False, True):
            with self.subTest(present_on_left=present_on_left):
                left, right = authored_pair()
                if present_on_left:
                    left[1]["authored_unknown_payload"] = {"nested": "unchanged_authored_value"}
                right[1]["authored_unknown_payload"] = {"nested": sentinel}
                before = deepcopy((left, right))
                rows = summarize_pair(left, right)
                self.assertTrue(rows[0]["payload_identical"])
                self.assertFalse(rows[1]["payload_identical"])
                self.assertTrue(rows[1]["raw_commands_identical"])
                self.assertEqual(rows[1]["metric_max_error"], 0.)
                self.assertEqual(rows[1]["numeric_geometry"]["maximum_point_error"], 0.)
                serialized = json.dumps(rows, allow_nan=False)
                self.assertNotIn(sentinel, serialized)
                self.assertNotIn("authored_unknown_payload", serialized)
                self.assertEqual((left, right), before)

    def test_tiny_vertical_origin_difference_remains_exact_even_for_blank_glyph(self):
        left, right = authored_pair()
        delta = 2 ** -20
        right[1]["vertical_origin_x"] += delta
        row = summarize_pair(left, right)[1]
        self.assertFalse(row["payload_identical"])
        self.assertTrue(row["raw_commands_identical"])
        self.assertEqual(row["metric_max_error"], delta)
        self.assertEqual(row["metric_differences"]["vertical_origin_x"], delta)
        self.assertTrue(all(value == 0. for key, value in row["metric_differences"].items()
                            if key != "vertical_origin_x"))
        self.assertEqual(row["numeric_geometry"]["maximum_point_error"], 0.)

    def test_pair_requires_matching_gid_sets_and_actual_face_gid_identity(self):
        left, right = authored_pair()
        for a, b in (({}, {}), (left, {}), (left, {0: right[0]}),
                     ({0: left[0]}, {1: right[1]})):
            with self.subTest(left_gids=list(a), right_gids=list(b)):
                with self.assertRaisesRegex(ValueError, "input_pair_glyph_sets_differ"):
                    summarize_pair(a, b)
        for field, value, both in (("face_index", 14, False), ("face_index", 14, True),
                                   ("glyph_id", 1, False), ("glyph_id", 1, True)):
            a, b = authored_pair()
            b[0][field] = value
            if both:
                a[0][field] = value
            with self.subTest(field=field, both=both):
                with self.assertRaisesRegex(ValueError, "input_pair_identity_mismatch"):
                    summarize_pair(a, b)

    def test_quadratic_control_difference_remains_outside_budget_in_legacy_and_raw(self):
        left, right = authored_pair()
        right[0]["commands"][1][2] += .5
        before = deepcopy((left, right))
        row = summarize_pair(left, right)[0]
        self.assertFalse(row["payload_identical"])
        self.assertFalse(row["raw_commands_identical"])
        self.assertEqual(row["metric_max_error"], 0.)
        geometry = row["numeric_geometry"]
        self.assertEqual(geometry["status"], "outside_budget")
        self.assertEqual(geometry["maximum_point_error"], .5)
        self.assertEqual(geometry["legacy"]["status"], "outside_budget")
        self.assertEqual(geometry["legacy"]["maximum_point_error"], .5)
        self.assertEqual(geometry["restored_segment_count"], 0)
        self.assertEqual((left, right), before)
        serialized = json.dumps(row, allow_nan=False)
        self.assertNotIn('"commands"', serialized)
        self.assertNotIn('"points"', serialized)


if __name__ == "__main__":
    unittest.main()
