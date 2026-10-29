"""Font-level removal of a rounding-threshold cause, with strict scope limits."""
from fractions import Fraction as F
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bounded_rebase import exact_rebase, RebasePrecisionError
from precision_metrics import scale_with_precision_metrics
from test_bounded_rebase import clipped_axes, q_font, serialize


class ExactRebaseTests(unittest.TestCase):
    def test_legal_exact_grid_removes_GID2_coefficient_rounding_mismatch(self):
        import uharfbuzz as hb
        source = q_font(1)
        source.recalcTimestamp = False
        before = serialize(source)
        target, report = exact_rebase(source, clipped_axes())
        self.assertEqual(serialize(source), before)
        self.assertEqual(report['selected_multiplier'], 16)
        self.assertEqual(target['head'].unitsPerEm, 16000)
        proof = report['continuous_model_certificate']
        self.assertEqual(proof['max_metric_error'], 0)
        self.assertEqual(proof['max_point_squared_error'], 0)
        self.assertTrue(report['zero_coefficient_error_required'])
        reference = scale_with_precision_metrics(source, 16000)
        values = []
        for font, coords in (
            (reference, {'XWDT': 63/16384, 'XWGT': 3/16, 'XHGT': 0}),
            (target, {'WDTH': 501.922607421875, 'wght': 900, 'HGHT': 500})):
            native = hb.Font(hb.Face(serialize(font)))
            hb.ot_font_set_funcs(native)
            native.scale = (64000, 64000)
            native.set_variations(coords)
            values.append(native.get_glyph_h_advance(2))
        self.assertEqual(values, [18720, 18720])
        self.assertEqual(F(abs(values[0]-values[1]), 64), 0)
        self.assertFalse(report['production_accepted'])
        self.assertFalse(report['font_only_equivalence_accepted'])

    def test_exact_grid_does_not_silently_accept_approximate_legal_grids(self):
        source = q_font(1)
        source['head'].unitsPerEm = 1144
        with self.assertRaisesRegex(RebasePrecisionError, 'no_exact_legal_integer_grid') as error:
            exact_rebase(source, clipped_axes())
        self.assertEqual(len(error.exception.attempts), 14)
        self.assertTrue(all(row['endpoint_metric_lower_bound'] > 0
                            for row in error.exception.attempts))

    def test_equal_scaled_reference_is_not_unscaled_source_native_acceptance(self):
        import uharfbuzz as hb
        source = q_font(1)
        target, report = exact_rebase(source, clipped_axes())
        values = []
        for font, coords in (
            (source, {'XWDT': 63/16384, 'XWGT': 3/16, 'XHGT': 0}),
            (target, {'WDTH': 501.922607421875, 'wght': 900, 'HGHT': 500})):
            native = hb.Font(hb.Face(serialize(font)))
            native.scale = (64000, 64000)
            native.set_variations(coords)
            values.append(native.get_glyph_h_advance(2))
        self.assertEqual(values, [18688, 18720])
        self.assertEqual(F(abs(values[0]-values[1]), 64), F(1, 2))
        self.assertGreater(F(abs(values[0]-values[1]), 64), F(1, 32))
        self.assertFalse(report['production_accepted'])


if __name__ == '__main__':
    unittest.main()
