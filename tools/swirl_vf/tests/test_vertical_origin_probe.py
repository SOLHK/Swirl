"""Independent origin hypotheses must retain discrepancies and source scope."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from compare_axis_construction import GUARD
from probe_vertical_origins import GLYPHS, LIMIT, hypotheses, make_harness, new_stats, record_stat


class VerticalOriginProbeTests(unittest.TestCase):
    def row(self):
        return {'advance_width': 760., 'vertical_origin_x': 500., 'font_upm': 1128,
                'font_size': 1128., 'graphics_units_per_em': 1000,
                'graphics_advance_success': True, 'graphics_advance': 674,
                'default_native_metrics': {'advance_width': 1000., 'vertical_origin_x': 500.}}

    def test_static_origin_is_not_mistaken_for_half_current_advance(self):
        models = hypotheses(self.row(), 1000)
        self.assertEqual(models['half_current_native_advance'], 380)
        self.assertEqual(models['half_stored_hmtx_advance'], 500)
        self.assertEqual(models['half_default_native_advance'], 500)
        self.assertEqual(models['unchanged_default_native_origin'], 500)
        self.assertAlmostEqual(models['half_current_CGFont_advance_scaled_to_CT_size'], 380.136)
        self.assertNotEqual(models['half_source_upm'], 500)

    def test_unavailable_CGFont_advance_is_not_fabricated(self):
        row = self.row()
        row['graphics_advance_success'] = False
        del row['graphics_advance']
        models = hypotheses(row, 1000)
        self.assertFalse(any('CGFont' in key for key in models))
        row['graphics_advance_success'] = True
        row['graphics_advance'] = 674
        row['graphics_units_per_em'] = 0
        with self.assertRaisesRegex(ValueError, 'invalid_graphics_units_per_em'):
            hypotheses(row, 1000)

    def test_all_samples_contribute_even_if_different_models_fit_each_one(self):
        stat = new_stats()
        record_stat(stat, 500, 500, {'face_index': 0, 'glyph_id': 5, 'case': 'default'})
        record_stat(stat, 500, 380, {'face_index': 0, 'glyph_id': 5, 'case': 'width'})
        record_stat(stat, 500, 499.99, {'face_index': 1, 'glyph_id': 5, 'case': 'weight'})
        self.assertEqual(stat['checks'], 3)
        self.assertEqual(stat['over_budget'], 1)
        self.assertEqual(stat['maximum_error'], 120)
        self.assertEqual(stat['maximum_error_example']['expected_for_this_model'], 380)
        self.assertEqual(stat['maximum_error_example']['signed_error'], 120)
        self.assertEqual(LIMIT, 1/32)
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            record_stat(stat, float('nan'), 500, {})

    def test_diagnostic_harness_cannot_be_fed_to_reconstruction_oracle(self):
        source = Path(__file__).resolve().parents[1] / 'platform' / 'coretext_extract.swift'
        production = source.read_text()
        harness = make_harness(production)
        self.assertEqual(production.count(GUARD), 1)
        self.assertNotIn(GUARD, harness)
        self.assertNotIn('func run() throws {', harness)
        self.assertNotIn('try run()', harness)
        self.assertIn('CoreText_origin_diagnostic_only', harness)
        self.assertIn('origin_diagnostic_glyph', harness)
        self.assertIn('observationInstance(state, requested)', harness)
        self.assertIn(str(list(GLYPHS)), harness)
        # The independent main does not call path extraction or emit commands.
        main = harness.split('func verticalOriginDiagnosticMain() throws {', 1)[1]
        self.assertNotIn('extractGlyph(', main)
        self.assertNotIn('pathCommands(', main)
        self.assertNotIn('"commands"', main)
        self.assertEqual(source.read_text(), production)
        with self.assertRaisesRegex(ValueError, 'review_changed'):
            make_harness(production.replace(GUARD, 'changed guard'))


if __name__ == '__main__':
    unittest.main()
