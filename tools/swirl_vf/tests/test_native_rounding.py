"""Exact arithmetic and actual authored HB advance rounding; no Apple data."""
from fractions import Fraction as F
import io
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from native_rounding import (LIMIT, advance_reference, binary32, hb_multiplier_fixed16,
    legal_upem_gap_summary, round_away, scale_integer_advance, threshold_gap_bound)


class NativeRoundingTests(unittest.TestCase):
    def test_GID2_exact_two_stage_calculation_retains_three_sixteenths_failure(self):
        reference = advance_reference(1460, F(2535, 1024),
            font_upem=5000, source_upem=1000, output_scale=64000)
        candidate = advance_reference(1460, F(2599, 1024),
            font_upem=5000, source_upem=1000, output_scale=64000)
        self.assertEqual(reference.ideal_source_value, F(299515, 1024))
        self.assertEqual(candidate.ideal_source_value, F(1497639, 5120))
        self.assertEqual(candidate.ideal_source_value - reference.ideal_source_value, F(1, 80))
        self.assertEqual((reference.rounded_design_advance, candidate.rounded_design_advance), (1462, 1463))
        self.assertEqual(reference.multiplier_fixed16, 838860)
        self.assertEqual((reference.output_position, candidate.output_position), (18714, 18726))
        self.assertEqual(candidate.output_source_value - reference.output_source_value, F(3, 16))
        self.assertGreater(candidate.output_source_value - reference.output_source_value, LIMIT)
        self.assertFalse(reference.native_execution)

    def test_actual_authored_HarfBuzz_matches_reference_not_direct_ideal_scale(self):
        import uharfbuzz as hb
        from bounded_rebase import bounded_rebase
        from precision_metrics import scale_with_precision_metrics
        from test_bounded_rebase import clipped_axes
        from test_rebase_design_font import q_font
        source = q_font(weight_delta=1)
        target, _ = bounded_rebase(source, clipped_axes())
        reference = scale_with_precision_metrics(source, 5000)
        actual = []
        try:
            for font, location in (
                (reference, {'XWDT': 63 / 16384, 'XWGT': 3 / 16, 'XHGT': 0.}),
                (target, {'WDTH': 500 + 500 * 63 / 16384, 'wght': 900., 'HGHT': 500.})):
                buffer = io.BytesIO(); font.save(buffer)
                native = hb.Font(hb.Face(buffer.getvalue()))
                hb.ot_font_set_funcs(native)
                native.scale = (64000, 64000)
                native.set_variations(location)
                actual.append(native.get_glyph_h_advance(2))
            expected = [advance_reference(1460, delta, font_upem=5000, source_upem=1000,
                        output_scale=64000).output_position for delta in (F(2535, 1024), F(2599, 1024))]
            self.assertEqual(actual, expected)
        finally:
            reference.close(); target.close(); source.close()

    def test_small_coefficient_error_does_not_bound_a_retained_threshold_mismatch(self):
        epsilon = F(1, 1 << 20)
        a, b = (advance_reference(100, F(1, 2) + sign * epsilon,
                   font_upem=5000, source_upem=1000, output_scale=64000) for sign in (-1, 1))
        self.assertLess(abs(a.ideal_source_value - b.ideal_source_value), F(1, 1000000))
        self.assertEqual((a.rounded_delta, b.rounded_delta), (0, 1))
        bound = threshold_gap_bound(font_upem=5000, source_upem=1000, output_scale=64000)
        self.assertEqual(bound.minimum_source_unit_gap, F(3, 16))
        self.assertGreaterEqual(abs(a.output_source_value - b.output_source_value), bound.minimum_source_unit_gap)
        self.assertTrue(bound.necessarily_exceeds_limit)

    def test_exact_sixteenfold_models_still_expose_F2_coordinate_quantization(self):
        import uharfbuzz as hb
        from bounded_rebase import exact_rebase
        from precision_metrics import scale_with_precision_metrics
        from test_bounded_rebase import clipped_axes
        from test_rebase_design_font import q_font, serialize
        # Diagnostic counterexample selected by a bounded integer search, not
        # a fitting rule. Fixed vectors are submitted to two native font objects.
        a, b, c = 9522, 6290, 8581
        k = (3 * b + 8) // 16
        self.assertEqual(k, 1179)
        self.assertEqual(F(3 * b, 16) - k, F(3, 8))
        denominator = 4194304
        target_delta = F(327680 * a + 768 * b + 3 * a * c, denominator)
        reference_delta = F(327680 * a + 4096 * k + 3 * a * c, denominator)
        self.assertEqual(target_delta - reference_delta, F(3, 8192))
        expected = [advance_reference(4672, delta, font_upem=16000, source_upem=1000,
                    output_scale=64000) for delta in (reference_delta, target_delta)]
        self.assertEqual([row.rounded_delta for row in expected], [803, 804])
        self.assertEqual([row.output_position for row in expected], [21900, 21904])
        source = q_font(weight_delta=1)
        target, report = exact_rebase(source, clipped_axes())
        reference = scale_with_precision_metrics(source, 16000)
        actual = []
        try:
            self.assertEqual(report['selected_multiplier'], 16)
            self.assertEqual(report['continuous_model_certificate']['max_metric_error'], 0)
            for font, coords in ((reference, (a, k, c)), (target, (a, b, c))):
                native = hb.Font(hb.Face(serialize(font)))
                hb.ot_font_set_funcs(native)
                native.scale = (64000, 64000)
                native.set_var_coords_normalized([value / 16384 for value in coords])
                self.assertEqual(native.get_var_coords_normalized(), [value / 16384 for value in coords])
                actual.append(native.get_glyph_h_advance(2))
            self.assertEqual(actual, [21900, 21904])
            self.assertEqual(F(actual[1] - actual[0], 64), F(1, 16))
            self.assertGreater(F(actual[1] - actual[0], 64), LIMIT)
            self.assertFalse(report['font_only_equivalence_accepted'])
        finally:
            reference.close(); target.close(); source.close()

    def test_nominal_users_and_compiled_avar_retain_a_sixteenfold_rounding_failure(self):
        import uharfbuzz as hb
        from bounded_rebase import exact_rebase
        from precision_metrics import scale_with_precision_metrics
        from target_axis_mapping import source_axis_plan
        from test_bounded_rebase import clipped_axes
        from test_rebase_design_font import q_font, serialize
        # This separate witness uses the serialized target's actual nominal-user
        # interface, including its compiled avar. Direct normalized input alone
        # does not establish failure at any particular nominal-user request.
        a, k, r, c = 1141, 1453, 7749, 10955
        self.assertEqual(r, (16 * k + 1) // 3)
        self.assertEqual(3 * r - 16 * k, -1)
        location = {'WDTH': 500 + 500 * a / 16384,
                    'wght': 500 + 400 * r / 16384,
                    'HGHT': 500 + 500 * c / 16384}
        axes = clipped_axes()
        self.assertEqual([source_axis_plan(axis, location[axis.tag])['source_q']
                          for axis in axes], [a, k, c])
        denominator = 4194304
        reference_delta = F(327680 * a + 4096 * k + 3 * a * c, denominator)
        target_delta = F(327680 * a + 768 * r + 3 * a * c, denominator)
        self.assertEqual(reference_delta, F(417333333, denominator))
        self.assertEqual(target_delta, F(417333077, denominator))
        self.assertEqual(target_delta - reference_delta, F(-1, 16384))
        expected = [advance_reference(4672, delta, font_upem=16000, source_upem=1000,
                    output_scale=64000) for delta in (reference_delta, target_delta)]
        self.assertEqual([row.rounded_delta for row in expected], [100, 99])
        self.assertEqual([row.output_position for row in expected], [19088, 19084])
        source = q_font(weight_delta=1)
        target, report = exact_rebase(source, axes)
        reference = scale_with_precision_metrics(source, 16000)
        actual = []
        try:
            self.assertEqual(report['selected_multiplier'], 16)
            self.assertEqual(report['continuous_model_certificate']['max_metric_error'], 0)
            for font, request, coords in (
                (reference, dict(zip(('XWDT', 'XWGT', 'XHGT'),
                                    (a / 16384, k / 16384, c / 16384))), (a, k, c)),
                (target, location, (a, r, c))):
                native = hb.Font(hb.Face(serialize(font)))
                hb.ot_font_set_funcs(native)
                native.scale = (64000, 64000)
                native.set_variations(request)
                self.assertEqual(native.get_var_coords_normalized(),
                                 [value / 16384 for value in coords])
                actual.append(native.get_glyph_h_advance(2))
            self.assertEqual(actual, [19088, 19084])
            self.assertEqual(F(abs(actual[1] - actual[0]), 64), F(1, 16))
            self.assertGreater(F(abs(actual[1] - actual[0]), 64), LIMIT)
            self.assertFalse(report['font_only_equivalence_accepted'])
        finally:
            reference.close(); target.close(); source.close()

    def test_design_delta_ties_are_away_from_zero_before_integer_base_is_added(self):
        self.assertEqual(round_away(F(1, 2)), 1)
        self.assertEqual(round_away(F(-1, 2)), -1)
        observed = advance_reference(100, F(-1, 2), font_upem=1000, source_upem=1000, output_scale=64000)
        self.assertEqual(observed.rounded_design_advance, 99)
        # Rounding the positive total99.5 instead would give100, a wrong model.
        self.assertNotEqual(observed.rounded_design_advance, round_away(F(199, 2)))

    def test_binary32_reference_has_ties_even_and_correct_subnormal_boundary(self):
        for value in (F(2535, 1024), F(2599, 1024), F(64000), F(1, 3), F(-1, 3)):
            native = F(struct.unpack('>f', struct.pack('>f', float(value)))[0])
            self.assertEqual(binary32(value), native)
        self.assertEqual(binary32(1 + F(1, 1 << 24)), 1)
        self.assertEqual(binary32(1 + F(3, 1 << 24)), 1 + F(1, 1 << 22))
        self.assertEqual(binary32(F(1, 1 << 150)), 0)
        self.assertEqual(binary32(F(3, 1 << 150)), F(1, 1 << 148))

    def test_fixed_multiplier_is_not_direct_infinite_precision_output_scaling(self):
        multiplier = hb_multiplier_fixed16(5000, 64000)
        self.assertEqual(multiplier, 838860)
        self.assertNotEqual(F(multiplier, 65536), F(64000, 5000))
        # A larger authored design advance exposes the distinct rounding phase.
        advance = 65535
        self.assertEqual(scale_integer_advance(advance, multiplier), 838847)
        self.assertEqual(round_away(F(advance * 64000, 5000)), 838848)

    def test_complete_legal_UPEM_field_includes_noninteger_ratios_and_retains_conditional_gap(self):
        summary = legal_upem_gap_summary(source_upem=1000, output_scale=64000)
        self.assertEqual(summary['legal_integer_UPEM_count'], 16369)
        self.assertEqual(summary['minimum_conditional_gap'], F(3, 64))
        self.assertTrue(summary['noninteger_target_source_ratios_included'])
        self.assertTrue(summary['all_legal_grids_exceed_limit_if_same_UPM_threshold_mismatch_persists'])
        self.assertEqual(summary['different_UPM_native_pair_equivalence'], 'NOT_ESTABLISHED')
        self.assertFalse(summary['font_equivalence_accepted'])
        self.assertNotEqual(F(16384, 1000).denominator, 1)

    def test_output_resolution_changes_conditional_bound_without_changing_font_tolerance(self):
        coarse = threshold_gap_bound(font_upem=16384, source_upem=1000, output_scale=1000)
        self.assertEqual(coarse.minimum_source_unit_gap, 0)
        self.assertFalse(coarse.necessarily_exceeds_limit)
        self.assertEqual(coarse.tolerance, LIMIT)
        self.assertIn('same_UPM', coarse.condition)
        self.assertFalse(coarse.font_equivalence_accepted)

    def test_invalid_types_illegal_UPEM_and_overflow_are_refused(self):
        for value in (1., True, float('nan')):
            with self.assertRaises(ValueError): binary32(value)
        with self.assertRaisesRegex(ValueError, 'overflow'): binary32(1 << 128)
        for upem in (15, 16385, 1000., True):
            with self.assertRaises(ValueError): hb_multiplier_fixed16(upem, 64000)
        for scale in (0, -1, 1., True, 1 << 31):
            with self.assertRaises(ValueError): hb_multiplier_fixed16(1000, scale)
        with self.assertRaisesRegex(ValueError, 'overflow'): scale_integer_advance(1 << 30, 1 << 20)
        with self.assertRaises(ValueError): threshold_gap_bound(font_upem=1000, source_upem=1000,
                                                              output_scale=64000, design_unit_gap=True)


if __name__ == '__main__':
    unittest.main()
