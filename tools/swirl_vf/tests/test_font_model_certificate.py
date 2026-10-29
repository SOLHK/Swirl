"""Actual serialized authored fonts, exact continuous model certificates."""
import copy
from fractions import Fraction as F
import io
from pathlib import Path
import sys
import unittest
from unittest import mock

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from continuous_model import EndpointTransform
import font_model_certificate as certificate
from font_model_certificate import advance_models, certify_font_models
from precision_metrics import scale_with_precision_metrics
from rebase_design_font import rebase_design_font, rebase_design_font_precision8
from target_axis_mapping import SourceAxis
from test_rebase_design_font import q_font, serialize, source_axes


THREE_SIXTEENTHS = ((-16384, -16384), (-16384, -3072), (0, 0),
                   (16384, 3072), (16384, 16384))
TRANSFORM = EndpointTransform((F(1), F(3, 16), F(1)), (F(1), F(3, 16), F(1)))


def clipped_axes():
    return tuple(SourceAxis(a.tag, a.minimum, a.default, a.maximum,
                  THREE_SIXTEENTHS if a.tag == 'wght' else a.records) for a in source_axes())


class FontModelCertificateTests(unittest.TestCase):
    def test_actual_serialized_precision8_retains_continuous_one_sixteenth_failure(self):
        source = q_font(weight_delta=1)
        target, _ = rebase_design_font_precision8(source, clipped_axes())
        proof = certify_font_models(source, target, TRANSFORM, target_upem_multiplier=8)
        self.assertEqual(proof['max_metric_error'], F(1, 16))
        self.assertFalse(proof['within_1_32'])
        self.assertGreater(proof['max_point_squared_error'], F(1, 1024))
        self.assertEqual(proof['glyphs_checked'], 7)
        self.assertEqual(proof['phantom_points_checked'], 28)
        self.assertEqual(proof['metric_models_checked'], 14)

    def test_actual_fivefold_serialized_candidate_has_global_one_eightieth_error(self):
        source = q_font(weight_delta=1)
        before = serialize(source)
        scaled = scale_with_precision_metrics(source, source['head'].unitsPerEm * 5)
        target, _ = rebase_design_font(scaled, clipped_axes())
        proof = certify_font_models(source, target, TRANSFORM, target_upem_multiplier=5)
        self.assertEqual(serialize(source), before)
        self.assertEqual(proof['max_metric_error'], F(1, 80))
        self.assertEqual(proof['max_point_squared_error'], F(1, 6400))
        self.assertTrue(proof['within_1_32'])
        self.assertTrue(proof['design_domain_only'])
        self.assertTrue(proof['metric_encodings_exactly_consistent'])
        self.assertFalse(proof['native_execution'])
        self.assertFalse(proof['source_user_mapping_accepted'])
        self.assertFalse(proof['avar_user_mapping_accepted'])
        self.assertFalse(proof['whole_font_equivalence_accepted'])

    def test_mixed_nonmonotonic_region_interior_maximum_is_not_missed(self):
        source = q_font()
        target = copy.deepcopy(source)
        name = 'A'
        count = len(source['gvar'].variations[name][0].coordinates)
        delta = [(3, -4)] + [(0, 0)] * (count - 1)
        source['gvar'].variations[name].append(TupleVariation(
            {'XWDT': (0, .5, 1), 'XWGT': (-1, -.5, 0), 'XHGT': (0, .25, 1)}, delta))
        proof = certify_font_models(source, target)
        self.assertEqual(proof['max_point_squared_error'], 25)
        self.assertEqual(proof['max_metric_error'], 0)
        self.assertFalse(proof['within_1_32'])
        self.assertGreater(proof['vertex_evaluations'], 27 * proof['points_checked'])

    def test_empty_glyphs_zero_models_and_every_phantom_are_counted(self):
        source = q_font()
        proof = certify_font_models(source, source)
        self.assertTrue(proof['within_1_32'])
        expected = sum(len(source['glyf'][name].getCoordinates(source['glyf'])[0]) + 4
                       for name in source.getGlyphOrder())
        self.assertEqual(proof['points_checked'], expected)
        self.assertEqual(proof['phantom_points_checked'], 4 * len(source.getGlyphOrder()))
        self.assertEqual(proof['max_point_squared_error'], 0)
        self.assertEqual(proof['max_metric_error'], 0)
        reopened = TTFont(io.BytesIO(serialize(source)), recalcTimestamp=False)
        try:
            models = advance_models(reopened)
            self.assertEqual(len(models), 14)
            self.assertIn(('HVAR', 'space'), models)
            self.assertIn(('VVAR', '.notdef'), models)
        finally:
            reopened.close()

    def test_inconsistent_HVAR_is_rejected_before_any_continuous_evaluation(self):
        source = q_font()
        target = copy.deepcopy(source)
        table = target['HVAR'].table
        index = table.AdvWidthMap.mapping['A']
        table.VarStore.VarData[index >> 16].Item[index & 0xffff][0] += 1
        with mock.patch.object(certificate, 'certify_difference', side_effect=AssertionError('must not evaluate')):
            with self.assertRaisesRegex(ValueError, 'coefficients differ'):
                certify_font_models(source, target)

    def test_budget_and_unsupported_IUP_do_not_result_in_partial_acceptance(self):
        source = q_font()
        with mock.patch.object(certificate, 'certify_difference', side_effect=AssertionError('must not evaluate')):
            with self.assertRaisesRegex(ValueError, 'point_budget'):
                certify_font_models(source, source, max_points=4)
            with self.assertRaisesRegex(ValueError, 'global_vertex_budget'):
                certify_font_models(source, source, max_vertices=1)
        source['gvar'].variations['A'][0].coordinates[0] = None
        with self.assertRaisesRegex(ValueError, 'IUP_or_omitted'):
            certify_font_models(source, source)

    def test_changed_same_gid_topology_and_wrong_axis_order_are_rejected(self):
        source = q_font()
        target = copy.deepcopy(source)
        target['glyf']['A'].flags[0] ^= 1
        with self.assertRaisesRegex(ValueError, 'topology_differs'):
            certify_font_models(source, target)
        target = copy.deepcopy(source)
        target['fvar'].axes.reverse()
        with self.assertRaisesRegex(ValueError, 'fixed_three_axis_order'):
            certify_font_models(source, target)

    def test_composites_and_optional_bearing_maps_are_not_silently_ignored(self):
        from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent
        source = q_font()
        composite = Glyph()
        composite.numberOfContours = -1
        component = GlyphComponent()
        component.glyphName = '.notdef'
        component.x = component.y = component.flags = 0
        composite.components = [component]
        source['glyf']['A'] = composite
        with self.assertRaisesRegex(ValueError, 'expanded_simple'):
            certify_font_models(source, source)
        source = q_font()
        target = copy.deepcopy(source)
        target['HVAR'].table.LsbMap = copy.deepcopy(target['HVAR'].table.AdvWidthMap)
        with self.assertRaisesRegex(ValueError, 'unexpected HVAR.LsbMap'):
            certify_font_models(source, target)

    def test_declared_upem_ratio_and_unbounded_or_boolean_budgets_are_refused(self):
        source = q_font()
        with self.assertRaisesRegex(ValueError, 'upem_ratio'):
            certify_font_models(source, source, target_upem_multiplier=2)
        for options in ({'max_vertices': False}, {'max_points': 0}, {'max_points': 4.},
                        {'target_upem_multiplier': 1.}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                certify_font_models(source, source, **options)
        with self.assertRaisesRegex(ValueError, 'reopened_font'):
            advance_models(source)


if __name__ == '__main__':
    unittest.main()
