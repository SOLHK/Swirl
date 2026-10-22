"""Independent affine inequalities; no native font or mapping hypothesis."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from calibrate_avar_metrics import LIMIT, infer_weight_from_metrics


class AxisInferenceIntervalTests(unittest.TestCase):
    def test_exact_positive_fit_has_a_nonzero_tolerance_interval(self):
        # |4(t-1/4)| <= 1/32 is strongest: t lies in [31/128,33/128].
        result = infer_weight_from_metrics([.25, .5, -1, 0], [-2, 1, 0, 0],
                                          [0, 0, 0, 0], [1, 2, -4, 0])
        best = result["best_fit"]
        self.assertEqual(best["normalized_weight"], .25)
        self.assertEqual(best["possible_interval"], [.25, .25])
        self.assertEqual(best["max_metric_residual"], 0)
        self.assertEqual(best["tolerance_consistent_interval"], [31 / 128, 33 / 128])
        self.assertTrue(result["within_unchanged_metric_budget"])
        self.assertFalse(result["geometry_mapping_accepted"])

    def test_negative_branch_reverses_bounds_and_mixed_slope_signs(self):
        # The factor interval [95/128,97/128] becomes [-97/128,-95/128].
        inputs = ([13, 18.5, 30.75, 40], [14, 18, 31, 40],
                  [10, 20, 30, 40], [8, 24, 30, 40])
        before = deepcopy(inputs)
        result = infer_weight_from_metrics(*inputs)
        self.assertEqual(result["best_fit"]["normalized_weight"], -.75)
        self.assertEqual(result["best_fit"]["possible_interval"], [-.75, -.75])
        self.assertEqual(result["best_fit"]["tolerance_consistent_interval"], [-97 / 128, -95 / 128])
        self.assertEqual(inputs, before)

    def test_nonzero_residual_retains_the_analytic_intersection(self):
        # Constant component error 1/64 is allowed. The third component still
        # imposes [31/128,33/128]; no best-fit-centred approximate radius is used.
        result = infer_weight_from_metrics([17 / 64, .5, -1, 1 / 64], [-2, 1, 0, 0],
                                          [0, 0, 0, 0], [1, 2, -4, 0])
        self.assertGreater(result["best_fit"]["max_metric_residual"], 0)
        self.assertEqual(result["best_fit"]["tolerance_consistent_interval"], [31 / 128, 33 / 128])
        self.assertTrue(result["within_unchanged_metric_budget"])

    def test_closed_intervals_clip_to_each_branch_domain(self):
        endpoints = ([-4, 0, 0, 0], [0, 0, 0, 0], [4, 0, 0, 0])
        for observed, expected in (([-4, 0, 0, 0], [-1, -127 / 128]),
                                   ([4, 0, 0, 0], [127 / 128, 1])):
            result = infer_weight_from_metrics(observed, *endpoints)
            self.assertEqual(result["best_fit"]["tolerance_consistent_interval"], expected)
        result = infer_weight_from_metrics([0, 0, 0, 0], *endpoints)
        self.assertEqual([branch["tolerance_consistent_interval"] for branch in result["consistent_branches"]],
                         [[-1 / 128, 0], [0, 1 / 128]])

    def test_flat_branches_preserve_full_domain_at_the_exact_tolerance(self):
        base = [0, 0, 0, 0]
        result = infer_weight_from_metrics([LIMIT, -LIMIT, 0, 0], base, base, base)
        self.assertTrue(result["within_unchanged_metric_budget"])
        for branch, expected in zip(result["consistent_branches"], ([-1., 0.], [0., 1.])):
            self.assertIsNone(branch["normalized_weight"])
            self.assertEqual(branch["possible_interval"], expected)
            self.assertEqual(branch["tolerance_consistent_interval"], expected)
        result = infer_weight_from_metrics([2 * LIMIT, 0, 0, 0], base, base, base)
        self.assertFalse(result["within_unchanged_metric_budget"])
        self.assertIsNone(result["best_fit"]["tolerance_consistent_interval"])
        self.assertEqual(result["best_fit"]["possible_interval"], [-1., 0.])

    def test_disjoint_nonflat_constraints_have_no_interval(self):
        result = infer_weight_from_metrics([.25, .5, 0, 0], [-1, -1, 0, 0],
                                          [0, 0, 0, 0], [1, 1, 0, 0])
        self.assertEqual(result["best_fit"]["possible_interval"], [.375, .375])
        self.assertIsNone(result["best_fit"]["tolerance_consistent_interval"])
        self.assertFalse(result["within_unchanged_metric_budget"])

    def test_one_constant_metric_contradiction_rejects_the_whole_interval(self):
        result = infer_weight_from_metrics([.25, .5, -1, 2 * LIMIT], [-2, 1, 0, 0],
                                          [0, 0, 0, 0], [1, 2, -4, 0])
        self.assertIsNone(result["best_fit"]["tolerance_consistent_interval"])
        self.assertFalse(result["within_unchanged_metric_budget"])

    def test_feasible_interval_does_not_reclassify_old_least_squares_failure(self):
        # |t|<=1/32 and |4t-5/32|<=1/32 meet only at t=1/32.
        # Least squares chooses 5/136, outside the first metric's budget. This
        # diagnostic addition must retain the old rejection and point estimate.
        result = infer_weight_from_metrics([0, 5 / 32, 0, 0], [-1, -4, 0, 0],
                                          [0, 0, 0, 0], [1, 4, 0, 0])
        best = result["best_fit"]
        self.assertEqual(best["normalized_weight"], 5 / 136)
        self.assertEqual(best["possible_interval"], [5 / 136, 5 / 136])
        self.assertEqual(best["tolerance_consistent_interval"], [1 / 32, 1 / 32])
        self.assertGreater(best["max_metric_residual"], LIMIT)
        self.assertEqual(result["consistent_branches"], [])
        self.assertFalse(result["within_unchanged_metric_budget"])
        self.assertFalse(result["geometry_mapping_accepted"])


if __name__ == "__main__":
    unittest.main()
