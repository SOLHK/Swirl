"""Authored analytic fixtures; no Apple data in this test module."""
from pathlib import Path
import sys
import unittest

import numpy as np
from fontTools.varLib.iup import iup_delta

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from windows_gvar import TensorModel, compile_glyph, observed_errors


def analytic(p):
    x, y, z = np.asarray(p).T
    return np.stack((3+2*x+5*y+7*z+11*x*y+13*x*z+17*y*z+19*x*y*z,
                     23+29*x-31*y+37*z-41*x*y+43*x*z-47*y*z+53*x*y*z), axis=-1)


class WindowsTensorTests(unittest.TestCase):
    def test_all_mixed_terms_survive_irregular_grid(self):
        model = TensorModel(([-1, 0, .25, 1], [-1, -.5, 0, 1], [-1, 0, .5, 1]))
        coefficients = model.coefficients(analytic(model.locations))
        p = np.random.default_rng(3703).uniform(-1, 1, (200, 3))
        np.testing.assert_allclose(model.evaluate(coefficients, p), analytic(p), atol=2e-13, rtol=0)
        dimensions = {len(s) for s, c in zip(model.supports, coefficients) if np.any(c)}
        self.assertEqual(dimensions, {0, 1, 2, 3})

    def test_vertex_quantization_does_not_accumulate_residual_rounding(self):
        model = TensorModel([-1, 0, 1])
        rectangle = np.asarray([(0, 0), (100, 0), (100, 200), (0, 200)])
        values = np.asarray([np.vstack((rectangle+analytic([p])[0]/7,
                            [(0, 0), (300, 0), (0, 880), (0, -120)])) for p in model.locations])
        glyph, tuples, hm, vm, encoded, report = compile_glyph(model, values, [1]*4, [3])
        np.testing.assert_array_equal(model.evaluate(encoded, model.locations), np.floor(values+.5))
        self.assertGreater(report['tuple_dimensions']['3'], 0)
        self.assertEqual(hm[0], 300)
        self.assertEqual(vm[0], 1000)
        base = encoded[model.indices.index(model.zero)]
        for variation in tuples:
            complete = iup_delta(variation.coordinates, base.tolist(), [3])
            position = model.supports.index(variation.axes)
            np.testing.assert_array_equal(complete, encoded[position])

    def test_default_rounding_is_reported_as_a_real_error(self):
        model = TensorModel([-1, 0, 1])
        points = np.asarray([(.4, .4), (100.4, .4), (100.4, 100.4), (.4, 100.4),
                             (0, 0), (300, 0), (0, 880), (0, -120)])
        values = np.broadcast_to(points, (27, 8, 2)).copy()
        *_, encoded, report = compile_glyph(model, values, [1]*4, [3])
        errors = observed_errors(model.evaluate(encoded, [[0, 0, 0]]), values[:1])
        self.assertAlmostEqual(errors['max_outline_control_bound'], np.sqrt(.32))
        self.assertFalse(report['production_accepted'])

    def test_nonrepresentable_knots_and_bad_phantoms_fail(self):
        with self.assertRaisesRegex(ValueError, 'F2DOT14'):
            TensorModel([-1, 0, .1, 1])
        model = TensorModel([-1, 0, 1])
        values = np.zeros((27, 4, 2)); values[:, -4, 0] = 3
        with self.assertRaisesRegex(ValueError, 'horizontal_origin'):
            compile_glyph(model, values, [], [])


if __name__ == '__main__':
    unittest.main()
