"""Original numerical controls for CoreText GPOS drawing diagnostics."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import probe_coretext_vertical_gpos as probe


class CoreTextGPOSProbeTests(unittest.TestCase):
    def row(self, x=1000, y=1200, glyph=4):
        ink = {'has_ink': True, 'border_ink_pixels': 0, 'centroid': [x, y]}
        return {'raster_executed': True,
            'glyphs': [{'gid': glyph, 'text_matrix': [1, 0, 0, 1, 0, 0],
                        'font_matrix': [1, 0, 0, 1, 0, 0]}],
            'frame_ink': copy.deepcopy(ink), 'run_ink': copy.deepcopy(ink),
            'path_ink': {'has_ink': True, 'border_ink_pixels': 0, 'centroid': [800, 900]}}

    def test_correct_gpos_effect_and_final_fixed_origin_are_independent_checks(self):
        default = self.row()
        source = self.row(x=950)
        candidate = self.row()
        result = probe.drawing_comparisons(default, source, candidate, 50, [1, 1])
        self.assertEqual(result['status'], 'ACTUAL_DRAWING_MODELS_MEASURED')
        fields = result['fields']
        self.assertEqual(fields['frame_ink/candidate_minus_source'], [50, 0])
        self.assertEqual(fields['frame_ink/upright/GPOS_effect_minus_encoded'], [0, 0])
        self.assertEqual(fields['frame_ink/candidate_minus_source_default'], [0, 0])
        self.assertEqual(fields['frame_ink/source_minus_source_default'], [-50, 0])
        self.assertEqual(fields['path_ink/candidate_minus_source'], [0, 0])

    def test_already_fixed_source_exposes_double_compensation_even_when_gpos_applies_correctly(self):
        default = self.row()
        source = self.row()
        candidate = self.row(x=1050)
        fields = probe.drawing_comparisons(default, source, candidate, 50, [1, 1])['fields']
        self.assertEqual(fields['frame_ink/upright/GPOS_effect_minus_encoded'], [0, 0])
        self.assertEqual(fields['frame_ink/source_minus_source_default'], [0, 0])
        self.assertEqual(fields['frame_ink/candidate_minus_source_default'], [50, 0])
        self.assertEqual(fields['frame_ink/upright/GPOS_effect_minus_twice_encoded'], [-50, 0])

    def test_ignored_feature_is_visible_without_claiming_compensation_succeeded(self):
        default = self.row()
        source = self.row(x=950)
        fields = probe.drawing_comparisons(default, source, copy.deepcopy(source), 50, [1, 1])['fields']
        self.assertEqual(fields['frame_ink/candidate_minus_source'], [0, 0])
        self.assertEqual(fields['frame_ink/upright/GPOS_effect_minus_encoded'], [-50, 0])
        self.assertEqual(fields['frame_ink/candidate_minus_source_default'], [-50, 0])

    def test_every_predeclared_rotation_model_is_preserved(self):
        default, source, candidate = self.row(), self.row(), self.row(y=1250)
        for row in (default, source, candidate):
            row['glyphs'][0]['text_matrix'] = [0, 1, -1, 0, 0, 0]
        fields = probe.drawing_comparisons(default, source, candidate, 50, [1, 1])['fields']
        self.assertEqual(fields['run_ink/run_matrix/GPOS_effect_minus_encoded'], [0, 0])
        self.assertEqual(fields['run_ink/upright/GPOS_effect_minus_encoded'], [-50, 50])
        self.assertIn('frame_ink/frame_clockwise_run_matrix/GPOS_effect_minus_encoded', fields)
        self.assertIn('frame_ink/frame_counterclockwise_run_matrix/GPOS_effect_minus_encoded', fields)

    def test_changed_glyph_matrix_clipping_or_missing_ink_are_not_hidden(self):
        base = self.row()
        changed = self.row(glyph=5)
        self.assertEqual(probe.drawing_comparisons(base, base, changed, 50, [1, 1])['status'],
                         'GSUB_GLYPH_CHANGED')
        changed = self.row()
        changed['glyphs'][0]['text_matrix'][0] = 2
        self.assertEqual(probe.drawing_comparisons(base, base, changed, 50, [1, 1])['status'],
                         'DRAWING_MATRIX_CHANGED')
        changed = self.row(); changed['frame_ink']['border_ink_pixels'] = 1
        self.assertEqual(probe.drawing_comparisons(base, base, changed, 50, [1, 1])['status'],
                         'RASTER_CLIPPED')
        changed = self.row(); changed['run_ink']['has_ink'] = False
        self.assertEqual(probe.drawing_comparisons(base, base, changed, 50, [1, 1])['status'], 'INK_MISSING')
        changed = self.row(); changed['raster_executed'] = False
        self.assertEqual(probe.drawing_comparisons(base, base, changed, 50, [1, 1])['status'],
                         'LAYOUT_RETAINED_WITHOUT_RASTER')

    def test_request_grid_keeps_feature_policies_languages_spaces_and_axes(self):
        for route in ('vert', 'vrt2', 'vkrn'):
            records = probe.requests(route)
            self.assertEqual(len(records), 336)
            self.assertEqual(len({probe.key(r) for r in records}), 336)
            self.assertEqual({r['text'] for r in records}, {'single_han', 'single_latin', 'single_space', 'mixed'})
            self.assertEqual({r['direction'] for r in records}, {'ltr', 'ttb'})
            self.assertEqual({r['language'] for r in records}, {'zh-CN', 'zh-HK'})
            for record in records:
                self.assertEqual(set(record['requested']), {'WDTH', 'wght', 'HGHT'})
                if record['policy'] == 'default':
                    self.assertEqual(record['features'], {})
                elif record['policy'] == 'disabled':
                    self.assertEqual(record['features'], {route: 0})
                elif route == 'vrt2':
                    self.assertEqual(record['features'], {'vrt2': 1, 'vert': 0})
                else:
                    self.assertEqual(record['features'], {route: 1})

    def test_raster_calibration_and_both_comparison_limits_remain_explicit(self):
        meta = {'raster_calibration': {'before': {'has_ink': True, 'border_ink_pixels': 0, 'centroid': [400, 500]},
            'after': {'has_ink': True, 'border_ink_pixels': 0, 'centroid': [537.25, 573.5]},
            'requested_translation': [137.25, -73.5]}}
        self.assertEqual(probe.raster_sign(meta), ([1, -1], [0, 0]))
        stats = {}
        probe.stat(stats, 'x', [.25, 0], {})
        probe.stat(stats, 'x', [2, 0], {})
        self.assertEqual(stats['x']['checks'], 2)
        self.assertEqual(stats['x']['above_1_over_32'], 2)
        self.assertEqual(stats['x']['above_reconstruction_1_FUnit'], 1)
        with self.assertRaisesRegex(ValueError, 'nonfinite_CoreText_GPOS'):
            probe.stat(stats, 'x', [float('nan')], {})

    def test_native_harness_checks_actual_font_and_draws_without_exporting_paths_or_images(self):
        source = probe.make_harness()
        self.assertNotIn('BITMAP_PIXELS', source)
        self.assertNotIn('RASTER_SCALE', source)
        self.assertIn('try verifyFixture(runFont, expected, absent)', source)
        self.assertIn('observedAxes(runFont) == observedAxes(font)', source)
        self.assertIn('kCTFontOpenTypeFeatureTag as String: tag', source)
        self.assertIn('CTFrameDraw(frame, $0)', source)
        self.assertIn('CTRunDraw(run, context', source)
        self.assertIn('CTRunGetBaseAdvancesAndOrigins', source)
        self.assertNotIn('CGImageDestination', source)
        self.assertNotIn('.session', source)
        self.assertNotIn('.persistent', source)
        self.assertNotIn('PingFang', source)
        self.assertNotIn('kCTKernAttributeName as String:', source)

    def test_registration_cleanup_requires_same_fixture_process_scope_and_actual_success(self):
        success = {'type': 'fixture_registration_cleanup', 'scope': 'process',
                   'font_sha256': 'original-fixture', 'unregistered': True}
        self.assertEqual(probe.require_registration_cleanup([success], 'original-fixture'), success)
        invalid_records = [[], [success, success],
            [{**success, 'unregistered': False, 'error': 'native_in_use'}],
            [{**success, 'unregistered': 'true'}],
            [{**success, 'scope': 'session'}],
            [{**success, 'font_sha256': 'another-candidate'}]]
        for records in invalid_records:
            with self.subTest(records=records), self.assertRaisesRegex(ValueError, 'registration_cleanup'):
                probe.require_registration_cleanup(records, 'original-fixture')

    def test_linux_run_is_explicitly_not_native_and_never_overwrites_existing_evidence(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(probe.sys, 'platform', 'linux'):
            output = Path(folder)/'not-run.json'
            with self.assertRaisesRegex(ValueError, 'CoreText_unavailable_native_layout_NOT_RUN'):
                probe.run(output)
            report = json.loads(output.read_text())
            self.assertEqual(report['status'], 'CORETEXT_NATIVE_LAYOUT_NOT_RUN')
            self.assertFalse(report['Apple_font_input'])
            self.assertFalse(report['native_font_acceptance'])
            self.assertFalse(report['native_processes'])
            saved = output.read_bytes()
            with self.assertRaisesRegex(ValueError, 'new_report_path_required'):
                probe.run(output)
            self.assertEqual(output.read_bytes(), saved)


if __name__ == '__main__':
    unittest.main()
