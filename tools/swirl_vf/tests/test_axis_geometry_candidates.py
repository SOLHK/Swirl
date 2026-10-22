"""Original discontinuous mappings; no Apple tables, outlines or font assets."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from axis_geometry_candidates import (
    map_signed_zero_raw_order, one_sided_zero_limit,
    targeted_user_locations, trace_signed_zero_raw_order,
)


class AxisGeometryCandidateTests(unittest.TestCase):
    left_jump = ((-1., -.75), (0., -.25), (0., 0.), (.25, 0.), (1., 1.))
    right_jump = ((-1., -1.), (0., 0.), (0., .125), (1., .75))

    def test_original_left_limit_does_not_become_actual_default(self):
        result = trace_signed_zero_raw_order(-1 / 65536, self.left_jump)
        self.assertEqual(result["pre_avar_f2dot14"], 0)
        self.assertEqual(result["original_side"], -1)
        self.assertFalse(result["actual_default"])
        self.assertTrue(result["one_sided_zero_limit_used"])
        self.assertEqual(result["final_normalized"], -.25)
        self.assertEqual(map_signed_zero_raw_order(0., self.left_jump), 0.)
        self.assertEqual(map_signed_zero_raw_order(1 / 65536, self.left_jump), 0.)

    def test_original_right_limit_is_distinct_from_default_and_left_limit(self):
        self.assertEqual(one_sided_zero_limit(self.right_jump, -1), 0.)
        self.assertEqual(one_sided_zero_limit(self.right_jump, 1), .125)
        self.assertEqual(map_signed_zero_raw_order(-1 / 65536, self.right_jump), 0.)
        self.assertEqual(map_signed_zero_raw_order(0., self.right_jump), 0.)
        self.assertEqual(map_signed_zero_raw_order(1 / 65536, self.right_jump), .125)

    def test_unsorted_plateau_boundary_is_a_falsifiable_prequantization_rule(self):
        records = ((-1., -1.), (0., 0.), (1 / 128, 0.), (0., .125), (1., 1.))
        at_quarter_grid_past_knot = 1 / 128 + 1 / 65536
        result = trace_signed_zero_raw_order(at_quarter_grid_past_knot, records)
        self.assertEqual(result["pre_avar_f2dot14"], 128)
        self.assertEqual(result["final_normalized"], 0.)
        self.assertGreater(map_signed_zero_raw_order(1 / 128 + 1 / 16384, records), .125)

    def test_an_unsorted_later_exact_knot_is_not_given_priority(self):
        records = ((-1., -1.), (0., -.25), (-1 / 128, 0.), (0., 0.), (1., 1.))
        before = deepcopy(records)
        expected = float(-Fraction(1, 4) - Fraction(1, 128) * Fraction(3, 4))
        self.assertEqual(map_signed_zero_raw_order(-1 / 128, records), expected)
        self.assertEqual(one_sided_zero_limit(records, -1), -.25)
        self.assertEqual(one_sided_zero_limit(records, 1), 0.)
        self.assertEqual(records, before)

    def test_duplicate_nonidentity_endpoints_retain_raw_record_order(self):
        records = ((-1., -1.), (-1., -.75), (0., 0.), (1., .5), (1., 1.))
        self.assertEqual(map_signed_zero_raw_order(-1., records), -.75)
        self.assertEqual(map_signed_zero_raw_order(1., records), .5)

    def test_rounding_ties_keep_the_original_side(self):
        negative = trace_signed_zero_raw_order(-1 / 32768, self.left_jump)
        positive = trace_signed_zero_raw_order(1 / 32768, self.left_jump)
        self.assertEqual(negative["pre_avar_f2dot14"], 0)
        self.assertEqual(negative["final_normalized"], -.25)
        self.assertEqual(positive["pre_avar_f2dot14"], 1)

    def test_candidate_never_claims_geometry_or_metric_acceptance(self):
        result = trace_signed_zero_raw_order(.5, self.left_jump)
        self.assertEqual(result["geometry_acceptance"], "NOT_ESTABLISHED")
        self.assertFalse(result["metric_mapping_model"])

    def test_invalid_data_is_rejected_without_sorting_or_clamping(self):
        for value in (float("nan"), float("inf"), -1.01, 1.01, True):
            with self.assertRaises(ValueError):
                map_signed_zero_raw_order(value, self.left_jump)
        for side in (0, 2, True):
            with self.assertRaises(ValueError):
                one_sided_zero_limit(self.left_jump, side)
        for records in ((), ((0., 0.),), ((-1., -1.), (0., float("nan")))):
            with self.assertRaises(ValueError):
                map_signed_zero_raw_order(0., records)

    def test_probe_coverage_uses_original_ranges_and_all_three_tags(self):
        ranges = {"WDTH": (10., 50., 90.), "wght": (100., 450., 900.), "HGHT": (5., 70., 150.)}
        before = deepcopy(ranges)
        probes = targeted_user_locations(ranges)
        self.assertTrue(all(set(row["location"]) == set(ranges) for row in probes))
        weights = {row["location"]["wght"] for row in probes}
        self.assertIn(450 - 350 / 65536, weights)
        self.assertIn(450 + 450 / 65536, weights)
        widths = {row["location"]["WDTH"] for row in probes if row["location"]["wght"] == 400.01}
        self.assertEqual(widths, {10., 50., 90.})
        self.assertEqual(len({tuple(row["location"][tag] for tag in ranges) for row in probes}), len(probes))
        self.assertEqual(ranges, before)


if __name__ == "__main__":
    unittest.main()
