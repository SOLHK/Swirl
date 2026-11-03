"""No native response may alter the input plan or upgrade overlap to holdout."""
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'tools'),
               str(Path(__file__).resolve().parents[1]/'platform')]
from probe_projection_candidate import independence, contour_measure, declared_user_location
from adaptive_projection_atlas import fingerprints
from verified_axis_oracle import declare_readback


class ProjectionAcceptanceTests(unittest.TestCase):
    def test_training_refinement_and_duplicate_rows_are_not_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            a, p = Path(directory)/'atlas.npz', Path(directory)/'parameters.npz'
            np.savez(a, fitting_fingerprints=fingerprints([[.123, .234, .345]]))
            np.savez(p, supports=np.zeros((1, 3, 3)))
            points = np.array([[.123, .234, .345], [0, 0, 0], [.314, .159, .265], [.314, .159, .265]])
            report, held = independence(points, a, p)
            self.assertTrue(report['proven'])
            self.assertEqual(report['overlapping_observations'], 2)
            self.assertEqual(report['unique_independent_positions'], 1)
            self.assertEqual(held.tolist(), [False, False, True, False])
            np.savez(a, bounds=np.zeros((1, 3, 2)))
            report, held = independence(points, a, p)
            self.assertFalse(report['proven'])
            self.assertIsNone(report['unique_independent_positions'])
            self.assertFalse(held.any())

    def test_legacy_grid_exclusion_is_conservative_including_roundtrip_noise(self):
        with tempfile.TemporaryDirectory() as directory:
            a, p = Path(directory)/'atlas.npz', Path(directory)/'parameters.npz'
            np.savez(a, bounds=np.zeros((1, 3, 2))); np.savez(p, supports=np.zeros((1, 3, 3)))
            _, independent = independence(np.array([[.125+1e-16, -.25, .5], [.123, .234, .345]]),
                                          a, p, legacy_grid=True)
            self.assertEqual(independent.tolist(), [False, True])
            np.savez(a, fitting_fingerprints=fingerprints([[.125, -.25, .5]]))
            report, independent = independence(np.array([[.125+1e-16, -.25, .5], [.123, .234, .345]]), a, p)
            self.assertTrue(report['proven'])
            self.assertEqual(independent.tolist(), [False, True])

    def test_predeclared_fractional_requests_are_stable_without_native_feedback(self):
        rng = np.random.default_rng(551)
        for _ in range(4096):
            requested = dict(zip(('WDTH', 'wght', 'HGHT'), np.round(rng.uniform(1, 1000, 3)*8192)/8192))
            planned = declared_user_location(requested)
            self.assertTrue(all(r['canonical'] == planned[tag] for tag, r in declare_readback(planned).items()))
            self.assertTrue(all(abs(planned[tag]-requested[tag]) < .0005 for tag in requested))

    def test_closed_contour_direction_is_measured_from_the_actual_path(self):
        path = [['moveTo', 0, 0], ['lineTo', 2, 0], ['lineTo', 2, 1], ['lineTo', 0, 1], ['closePath']]
        areas, gap, closed = contour_measure(path)
        self.assertEqual(areas.tolist(), [2.]); self.assertTrue(closed); self.assertEqual(gap, 1.)
        reversed_path = [['moveTo', 0, 0], ['lineTo', 0, 1], ['lineTo', 2, 1], ['lineTo', 2, 0], ['closePath']]
        self.assertEqual(contour_measure(reversed_path)[0].tolist(), [-2.])
        with self.assertRaisesRegex(ValueError, 'unclosed_source_contour'):
            contour_measure(path[:-1])


if __name__ == '__main__': unittest.main()
