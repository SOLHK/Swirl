"""Independent exact analytic examples for continuous model certificates."""
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import continuous_model as model
from continuous_model import (AxisSupport, ContinuousCertificate, EndpointTransform,
                              VectorModel, VectorRegion, certify_difference, evaluate_model)


POSITIVE = AxisSupport(0, 1, 1)
NEGATIVE = AxisSupport(-1, -1, 0)


def region(delta, *supports):
    return VectorRegion(supports or (POSITIVE, None, None), delta)


class ContinuousModelTests(unittest.TestCase):
    def test_even_coefficient_rebase_is_identical_on_the_entire_continuum(self):
        source = VectorModel((11, -9), (region((1, -2)),))
        target = VectorModel((88, -72), (region((4, -8)),))
        transform = EndpointTransform((F(1, 2), F(1), F(1)), (F(1, 2), F(1), F(1)))
        certificate = certify_difference(source, target, transform, target_upem_multiplier=8)
        self.assertIsInstance(certificate, ContinuousCertificate)
        self.assertEqual(certificate.max_abs_components, (0, 0))
        self.assertEqual(certificate.max_squared_norm, 0)
        self.assertEqual(certificate.vertex_count, 27)
        self.assertEqual(certificate.cell_count, 8)
        self.assertTrue(certificate.ideal_model_arithmetic_only)
        self.assertFalse(certificate.native_execution)
        self.assertFalse(certificate.source_user_mapping_accepted)
        self.assertFalse(certificate.whole_font_equivalence_accepted)

    def test_eightfold_precision_retains_exact_nonuniversal_three_sixteenths_error(self):
        source = VectorModel((0,), (region((1,)),))
        target = VectorModel((0,), (region((2,)),))
        transform = EndpointTransform((F(1),) * 3, (F(3, 16), F(1), F(1)))
        result = certify_difference(source, target, transform, target_upem_multiplier=8)
        self.assertEqual(result.max_abs_component, F(1, 16))
        self.assertEqual(result.max_squared_norm, F(1, 256))
        self.assertGreater(result.max_abs_component, F(1, 32))
        self.assertEqual(result.component_witnesses[0][0], 1)

    def test_interior_peak_missed_by_domain_endpoints_is_included(self):
        triangle = AxisSupport(0, F(1, 2), 1)
        source = VectorModel((0,), (region((10,), triangle, None, None),))
        target = VectorModel((0,))
        for x in (-1, 0, 1):
            self.assertEqual(evaluate_model(source, (x, 0, 0)), (0,))
        result = certify_difference(source, target)
        self.assertEqual(result.max_abs_component, 10)
        self.assertEqual(result.component_witnesses[0][0], F(1, 2))
        self.assertIn(F(1, 2), result.breakplanes[0])

    def test_source_knots_are_inverted_through_asymmetric_endpoint_basis(self):
        source = VectorModel((0,), (region((7,), AxisSupport(0, F(1, 4), 1), None, None),))
        target = VectorModel((0,))
        transform = EndpointTransform((F(3, 4), F(1), F(1)), (F(1, 2), F(1), F(1)))
        result = certify_difference(source, target, transform)
        self.assertIn(F(1, 2), result.breakplanes[0])
        self.assertEqual(result.max_abs_component, 7)
        self.assertEqual(result.component_witnesses[0][0], F(1, 2))
        # The old source end at+1 maps outside target domain and is clipped,
        # while its rising/falling branches still participate inside the box.
        self.assertNotIn(F(2), result.breakplanes[0])

    def test_mixed_three_axis_nonmonotonic_vector_model_has_exact_interior_maximum(self):
        supports = (AxisSupport(0, F(1, 2), 1), AxisSupport(-1, F(-1, 2), 0),
                    AxisSupport(0, F(1, 4), 1))
        source = VectorModel((0, 0), (VectorRegion(supports, (3, -4)),))
        target = VectorModel((0, 0))
        for point in product((-1, 1), repeat=3):
            self.assertEqual(evaluate_model(source, point), (0, 0))
        result = certify_difference(source, target)
        self.assertEqual(result.max_abs_components, (3, 4))
        self.assertEqual(result.max_squared_norm, 25)
        self.assertEqual(result.norm_witness, (F(1, 2), F(-1, 2), F(1, 4)))

    def test_nonmonotonic_sum_target_knots_and_fractional_max_are_not_endpoint_fitted(self):
        source = VectorModel((0,), (
            region((4,), AxisSupport(0, F(1, 4), F(1, 2)), None, None),
            region((-3,), AxisSupport(F(1, 2), F(3, 4), 1), None, None)))
        target = VectorModel((1,), (region((1,), AxisSupport(0, F(1, 3), 1), None, None),))
        result = certify_difference(source, target, target_upem_multiplier=3)
        # At x=3/4, source=-3 and target=(1+3/8)/3=11/24.
        self.assertEqual(result.max_abs_component, F(83, 24))
        self.assertEqual(result.max_squared_norm, F(6889, 576))
        self.assertEqual(result.component_witnesses[0][0], F(3, 4))
        self.assertIn(F(1, 3), result.breakplanes[0])

    def test_components_and_squared_norm_have_separate_witnesses(self):
        x = AxisSupport(0, F(1, 2), 1)
        source = VectorModel((0, 0), (region((3, 0), x, None, None),
                                      region((0, 4), None, POSITIVE, None)))
        result = certify_difference(source, VectorModel((0, 0)))
        self.assertEqual(result.max_abs_components, (3, 4))
        self.assertEqual(result.max_squared_norm, 25)
        self.assertEqual(result.norm_witness[:2], (F(1, 2), F(1)))

    def test_peak_zero_is_a_neutral_axis_and_endpoint_plateaus_are_exact(self):
        neutral = AxisSupport(-1, 0, 1)
        source = VectorModel((0,), (region((2,), neutral, NEGATIVE, None),))
        for x in (-1, F(1, 7), 1):
            self.assertEqual(evaluate_model(source, (x, -1, 0)), (2,))
        result = certify_difference(source, VectorModel((0,)))
        self.assertEqual(result.max_abs_component, 2)
        self.assertEqual(result.component_witnesses[0][1], -1)

    def test_vertex_budget_fails_before_any_model_evaluation(self):
        source = VectorModel((0,), (region((1,), AxisSupport(0, F(1, 2), 1), None, None),))
        with mock.patch.object(model, '_evaluate', side_effect=AssertionError('must not evaluate')):
            with self.assertRaisesRegex(ValueError, 'vertex_budget_exceeded'):
                certify_difference(source, VectorModel((0,)), max_vertices=35)

    def test_unsupported_shapes_float_coefficients_and_malformed_dimensions_are_rejected(self):
        for support in ((0, F(1, 2), F(1, 2)), (F(1, 2), F(1, 2), 1),
                        (-1, 1, 0), (-1, F(1, 2), 1), (-2, -1, 0), (0., 1, 1)):
            with self.subTest(support=support), self.assertRaises(ValueError):
                AxisSupport(*support)
        for base in ((True,), (1.,), (), [1]):
            with self.assertRaises(ValueError): VectorModel(base)
        with self.assertRaises(ValueError): VectorRegion((POSITIVE,), (1,))
        with self.assertRaises(ValueError): VectorRegion((None,) * 3, (F(1, 2),))
        with self.assertRaises(ValueError): VectorModel((0,), (VectorRegion((None,) * 3, (1, 2)),))
        with self.assertRaises(ValueError): EndpointTransform((0, 1, 1), (1, 1, 1))
        with self.assertRaises(ValueError): EndpointTransform((1, 1, 1), (2, 1, 1))
        source = VectorModel((0,))
        for options in ({'target_upem_multiplier': 0}, {'target_upem_multiplier': 8.},
                        {'max_vertices': True}, {'max_vertices': 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                certify_difference(source, source, **options)


if __name__ == '__main__':
    unittest.main()
