"""Analytic metric inversion tests; not Apple source-coordinate acceptance."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
from calibrate_avar_metrics import infer_weight_from_metrics, LIMIT


class AxisInferenceTests(unittest.TestCase):
    base = np.array([500., 600., 700., 1000.])
    low = base - [37., 53., 29., 0.]
    high = base + [131., 107., 79., 0.]

    def test_independent_fractional_coordinates_and_endpoints(self):
        for coordinate in (-1., -.7319, -.17, 0., .217, .6931, 1.):
            slope = self.low-self.base if coordinate < 0 else self.high-self.base
            data = self.base + abs(coordinate)*slope
            before = data.copy()
            result = infer_weight_from_metrics(data, self.low, self.base, self.high)
            self.assertTrue(result['within_unchanged_metric_budget'])
            self.assertAlmostEqual(result['best_fit']['normalized_weight'], coordinate, places=12)
            self.assertFalse(result['geometry_mapping_accepted'])
            np.testing.assert_array_equal(data, before)

    def test_multiple_metrics_reject_non_equivalent_mapping(self):
        observed = self.base + .5*(self.high-self.base)
        observed[3] += .1
        result = infer_weight_from_metrics(observed, self.low, self.base, self.high)
        self.assertFalse(result['within_unchanged_metric_budget'])
        self.assertGreater(result['best_fit']['max_metric_residual'], LIMIT)

    def test_outside_axis_domain_is_not_extrapolated_to_a_pass(self):
        observed = self.base + 2*(self.high-self.base)
        result = infer_weight_from_metrics(observed, self.low, self.base, self.high)
        self.assertFalse(result['within_unchanged_metric_budget'])
        self.assertEqual(result['best_fit']['normalized_weight'], 1.)

    def test_flat_axis_stays_ambiguous(self):
        result = infer_weight_from_metrics(self.base, self.base, self.base, self.base)
        self.assertEqual(len(result['consistent_branches']), 2)
        self.assertTrue(all(c['normalized_weight'] is None for c in result['consistent_branches']))
        self.assertEqual([c['possible_interval'] for c in result['consistent_branches']], [[-1., 0.], [0., 1.]])

    def test_invalid_or_nonfinite_observations_fail(self):
        for observed in ([1, 2, 3], [1, 2, 3, float('nan')], [1, 2, 3, float('inf')]):
            with self.assertRaises(ValueError):
                infer_weight_from_metrics(observed, self.low, self.base, self.high)


if __name__ == '__main__':
    unittest.main()
