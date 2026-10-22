"""Original rotation-centre formulas and regression fixtures; no Apple outlines."""
import math
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from transform_geometry import fractional_translation, blend_transform_rows
from probe_transform_stages import composite, rotation, direct_cases
from probe_hierarchy_rules import shape_record, hvgl_table, HVGL, ExperimentalRenderer
from batch_geometry import BatchGeometry
from tangent_geometry import resolve_path


class TransformGeometryTests(unittest.TestCase):
    def test_rotation_centre_formula_at_independent_fractional_weights(self):
        centre = np.array([37., -53.])
        for theta in (-1.31, -.017, .19, 2.17):
            translation = centre - rotation(theta) @ centre
            weights = np.array([-1.25, -.23, 0., .137, .61, 1., 1.7])
            expected = np.array([centre - rotation(w * theta) @ centre for w in weights])
            np.testing.assert_allclose(fractional_translation(translation, theta, weights),
                                       expected, rtol=0, atol=1e-12)

    def test_zero_and_tiny_angles_keep_translation_limit(self):
        weights = np.array([0., .137, .61, 1., 1.7]); t = np.array([17., -23.])
        np.testing.assert_array_equal(fractional_translation(t, 0., weights), weights[:, None] * t)
        for theta in (-1e-12, 1e-12):
            np.testing.assert_allclose(fractional_translation(t, theta, weights), weights[:, None] * t,
                                       rtol=0, atol=2e-11)

    def test_native_observed_fraction_is_not_straight_translation(self):
        # Original fixture from native run 39304868120; no source-font data.
        theta = float(np.float32(.16))
        actual = fractional_translation([-5., 23.], theta, .375)
        np.testing.assert_allclose(actual, [-1.4429087901135, 8.7159198056211], atol=1e-8, rtol=0)
        self.assertGreater(np.max(np.abs(actual - np.array([-5., 23.]) * .375)), .4)

    def test_master_rotation_and_ordered_extrema_do_not_commute(self):
        p = HVGL(hvgl_table([composite(1, axes=3, tree_axes=4,
            tm={0: [30., -40.]}, rm={0: [.371]},
            te={(0, 1): [-5., 23.], (0, 3): [11., -3.], (0, 5): [3., -17.]},
            re={(0, 1): [.16], (0, 3): [-.07], (0, 5): [.23]}), shape_record()])).part(0)
        weights = np.array([0., .37, 0., .59, 0., .83])
        expected = np.eye(3); expected[:2, :2] = rotation(float(p.rotations.master_values[0, 0]))
        expected[:2, 2] = p.translations.master_values[0]
        for (_, col), t in zip(p.translations.extreme_indices, p.translations.extreme_values):
            angle = float(next(v[0] for rc, v in zip(p.rotations.extreme_indices,
                                                   p.rotations.extreme_values) if rc[1] == col))
            centre = np.linalg.solve(np.eye(2) - rotation(angle), t.astype(float))
            step = np.eye(3); step[:2, :2] = rotation(weights[col] * angle)
            step[:2, 2] = centre - step[:2, :2] @ centre
            expected = expected @ step
        actual = blend_transform_rows(p, weights)[0]
        np.testing.assert_allclose(actual[:2], expected[:2, 2], rtol=0, atol=1e-11)
        np.testing.assert_allclose(rotation(actual[2]), expected[:2, :2], rtol=0, atol=1e-12)

    def test_sparse_zero_rows_do_not_require_dense_structure_allocations(self):
        p = HVGL(hvgl_table([composite(1, tm={0: [17., -3.]}), shape_record()])).part(0)
        actual = blend_transform_rows(p, np.array([[0., 0.], [1., 0.]]))
        self.assertEqual(set(actual), {0})
        np.testing.assert_array_equal(actual[0], [[17., -3., 0.], [17., -3., 0.]])

    def test_scalar_batch_and_source_immutability(self):
        for name, kwargs, coordinates in direct_cases():
            raw = hvgl_table([composite(1, **kwargs), shape_record()]); table = HVGL(raw)
            before = bytes(table.data); point = np.asarray(coordinates); saved = point.copy()
            batch = BatchGeometry(table).render(0, [point, np.zeros(len(point))])
            for n, loc in enumerate((point, np.zeros(len(point)))):
                scalar = ExperimentalRenderer(table).render(0, loc)
                for a, b in zip(scalar, batch.paths):
                    np.testing.assert_allclose(a, b[n], rtol=0, atol=1e-10)
            self.assertEqual(table.data, before)
            np.testing.assert_array_equal(point, saved)

    def test_native_observed_curve_factor_bounds_in_all_renderers(self):
        for factor in (-2., -.25, 0., .25, 1., 1.25, 3.):
            raw = hvgl_table([shape_record(parallel=factor)]); table = HVGL(raw)
            master = table.part(0).master.copy(); saved = master.copy()
            f = min(1., max(0., factor)); expected = (1-f) * master[-1, 2:] + f * master[0, 2:]
            np.testing.assert_array_equal(resolve_path(master, [0, 1, 1])[0], expected)
            np.testing.assert_array_equal(master, saved)
            for tangents in (False, True):
                np.testing.assert_array_equal(ExperimentalRenderer(table, isolated_tangents=tangents).render(0, [0.])[0][0], expected)
                np.testing.assert_array_equal(BatchGeometry(table, isolated_tangents=tangents).render(0, [[0.]]).paths[0][0, 0], expected)

    def test_nonfinite_and_malformed_inputs_fail(self):
        for translation, angle, weight in (([0., float('nan')], 0., .5),
                ([1., 2.], float('inf'), .5), ([1., 2.], .3, float('nan')), ([1.], .3, .5)):
            with self.assertRaises(ValueError):
                fractional_translation(translation, angle, weight)


if __name__ == '__main__':
    unittest.main()
