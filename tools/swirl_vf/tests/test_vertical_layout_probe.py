"""Original numerical examples for independent vertical-drawing diagnosis."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from compare_axis_construction import GUARD
from probe_vertical_layout import (
    CASES, CODEPOINTS, EXPECTED, FACES, FONT_ACCEPTANCE_LIMIT, RASTER_SCALE,
    add_stat, analyze, calibration_sign,
    drawing_hypotheses, make_harness,
)


class VerticalLayoutProbeTests(unittest.TestCase):
    def row(self):
        glyph = {'glyph_id': 8, 'text_matrix': [1, 0, 0, 1, 0, 0],
                 'font_matrix': [1, 0, 0, 1, 0, 0], 'line_origin': [1200, 700],
                 'position': [0, 0], 'base_origin': [0, 0], 'advance_width': 1000}
        result = {'glyphs': [glyph]}
        for field, centroid in [('path_ink', [900, 1200]), ('run_ink', [1800, 1900]),
                                ('frame_ink', [2200, 1500])]:
            result[field] = {'has_ink': True, 'border_ink_pixels': 0, 'centroid': centroid}
        return result

    def change(self, before, draw_shift):
        after = copy.deepcopy(before)
        after['glyphs'][0]['advance_width'] = 800
        # Original glyph centroid moves independently of placement by -40,+15.
        after['path_ink']['centroid'] = [860, 1215]
        for field in ('run_ink', 'frame_ink'):
            old = before[field]['centroid']
            after[field]['centroid'] = [old[0]-40+draw_shift, old[1]+15]
        return after

    def test_fixed_origin_drawing_is_distinguished_from_half_advance(self):
        before = self.row()
        status, models = drawing_hypotheses(before, self.change(before, 0), [1, 1])
        self.assertEqual(status, 'MEASURED_RELATIVE_DRAWING')
        self.assertEqual(len(models), 16)
        for drawing in ('run_ink', 'frame_ink'):
            self.assertEqual(models[f'{drawing}/upright/unchanged_origin']['residual'], [0, 0])
            self.assertEqual(models[f'{drawing}/upright/half_current_advance']['residual'], [-100, 0])

    def test_current_half_advance_drawing_is_not_classified_as_fixed_origin(self):
        before = self.row()
        _, models = drawing_hypotheses(before, self.change(before, 100), [1, 1])
        self.assertEqual(models['frame_ink/upright/unchanged_origin']['residual'], [100, 0])
        self.assertEqual(models['frame_ink/upright/half_current_advance']['residual'], [0, 0])

    def test_measured_rotation_preserves_its_own_explicit_hypothesis(self):
        before = self.row()
        before['glyphs'][0]['text_matrix'] = [0, -1, 1, 0, 0, 0]
        after = self.change(before, 0)
        for field in ('frame_ink', 'run_ink'):
            old = before[field]['centroid']
            after[field]['centroid'] = [old[0]+15, old[1]+40]
        _, models = drawing_hypotheses(before, after, [1, 1])
        self.assertEqual(models['run_ink/run_matrix/unchanged_origin']['residual'], [0, 0])
        self.assertNotEqual(models['run_ink/upright/unchanged_origin']['residual'], [0, 0])

    def test_real_layout_changes_are_retained_instead_of_guessed_away(self):
        before = self.row()
        for key, value, status in [('glyph_id', 9, 'SHAPED_GLYPH_CHANGED'),
                ('text_matrix', [1, 0, 0, 1, 1, 0], 'DRAWING_MATRIX_CHANGED'),
                ('font_matrix', [1, 0, 0, 1, 0, 2], 'DRAWING_MATRIX_CHANGED'),
                ('base_origin', [100, 0], 'LAYOUT_ORIGIN_CHANGED'),
                ('position', [0, -850], 'LAYOUT_ORIGIN_CHANGED')]:
            after = self.change(before, 0)
            after['glyphs'][0][key] = value
            self.assertEqual(drawing_hypotheses(before, after, [1, 1]), (status, {}))

    def test_empty_space_clipping_and_missing_ink_do_not_fabricate_positions(self):
        before = self.row()
        after = self.change(before, 0)
        after['frame_ink']['border_ink_pixels'] = 1
        self.assertEqual(drawing_hypotheses(before, after, [1, 1]), ('RASTER_CLIPPED', {}))
        after['frame_ink'] = {'has_ink': False, 'border_ink_pixels': 0}
        self.assertEqual(drawing_hypotheses(before, after, [1, 1]), ('PATH_AND_DRAWING_INK_DISAGREE', {}))
        for row in (before, after):
            for field in ('frame_ink', 'run_ink', 'path_ink'):
                row[field] = {'has_ink': False, 'border_ink_pixels': 0}
        self.assertEqual(drawing_hypotheses(before, after, [1, 1]), ('EMPTY_GLYPH_LAYOUT_RETAINED', {}))

    def test_bitmap_coordinate_calibration_is_separate_from_font_acceptance(self):
        data = {'before': {'has_ink': True, 'border_ink_pixels': 0, 'centroid': [100, 100]},
                'after': {'has_ink': True, 'border_ink_pixels': 0, 'centroid': [237.25, 173.5]},
                'requested_translation': [137.25, -73.5]}
        self.assertEqual(calibration_sign(data), ([1, -1], [0, 0]))
        data['after']['centroid'][0] += 10
        with self.assertRaisesRegex(ValueError, 'raster_instrument_translation_failed'):
            calibration_sign(data)
        self.assertEqual(FONT_ACCEPTANCE_LIMIT, 1/32)
        self.assertGreater(1/RASTER_SCALE, FONT_ACCEPTANCE_LIMIT)

    def test_aggregation_keeps_mismatch_instead_of_choosing_per_point_models(self):
        stats = {}
        add_stat(stats, 'fixed', [0, 0], {'case': 'first'})
        add_stat(stats, 'fixed', [100, 0], {'case': 'second'})
        add_stat(stats, 'half', [-100, 0], {'case': 'first'})
        add_stat(stats, 'half', [0, 0], {'case': 'second'})
        for value in stats.values():
            self.assertEqual(value['checks'], 2)
            self.assertEqual(value['maximum_magnitude'], 100)
        with self.assertRaisesRegex(ValueError, 'nonfinite_layout'):
            add_stat(stats, 'fixed', [float('nan'), 0], {})

    def test_harness_preserves_the_production_guard_and_never_exports_images_or_paths(self):
        path = Path(__file__).resolve().parents[1] / 'platform' / 'coretext_extract.swift'
        production = path.read_text()
        harness = make_harness(production)
        self.assertEqual(harness.count(GUARD), 1)
        self.assertTrue(harness.startswith(production.split('\nfunc run() throws {', 1)[0]))
        self.assertIn('CoreText_vertical_layout_diagnostic_only', harness)
        self.assertIn('CTRunGetBaseAdvancesAndOrigins', harness)
        self.assertIn('CTRunDraw(run, context', harness)
        self.assertIn('CTFrameDraw(frame, context)', harness)
        diagnostic = harness.split('let layoutPixels', 1)[1]
        self.assertIn('try constructInstance(state, requested)', diagnostic)
        self.assertNotIn('try makeInstance(', diagnostic)
        for forbidden in ('pathCommands(', 'extractGlyph(', 'makeImage(', 'CGImageDestination', '"commands"'):
            self.assertNotIn(forbidden, diagnostic)
        self.assertNotIn('func run() throws {', harness)
        self.assertEqual(path.read_text(), production)
        with self.assertRaisesRegex(ValueError, 'review_changed_production_helper'):
            make_harness(production.replace(GUARD, 'changed'))

    def test_complete_report_rejects_missing_duplicate_or_unverified_observations(self):
        class OriginalProtocolShape:
            # Only protocol dimensions, using independently invented metrics.
            # No source font bytes, outlines or source cmap are required here.
            def __getitem__(self, table):
                if table == 'head':
                    return SimpleNamespace(unitsPerEm=1000)
                return SimpleNamespace(axes=[SimpleNamespace(axisTag=tag, minValue=100,
                    defaultValue=500, maxValue=900) for tag in ('WDTH', 'wght', 'HGHT')])

            def getGlyphOrder(self):
                return range(47102)

            def getBestCmap(self):
                return {cp: 'glyph' + str(i+1) for i, cp in enumerate(CODEPOINTS)}

            def getGlyphID(self, name):
                return int(name[5:])

        fonts = [OriginalProtocolShape() for _ in range(32)]
        metadata = {'type': 'vertical_layout_metadata', 'source_sha256': EXPECTED,
                    'backend': 'CoreText_vertical_layout_diagnostic_only',
                    'production_readback_guard_unchanged': True, 'axis_observations_accepted': False,
                    'paths_or_images_emitted': False, 'os_version': 'independent_test_only',
                    'faces': [{'face_index': i, 'status': 'identity_verified', 'upm': 1000,
                               'glyph_count': 47102} for i in range(32)],
                    'raster_calibration': {'before': {'has_ink': True, 'border_ink_pixels': 0, 'centroid': [100, 200]},
                        'after': {'has_ink': True, 'border_ink_pixels': 0, 'centroid': [237.25, 126.5]},
                        'requested_translation': [137.25, -73.5]}}
        rows = [metadata]
        for face in FACES:
            for label in CASES:
                mixed = []
                for i, cp in enumerate(CODEPOINTS):
                    row = self.row()
                    row['glyphs'][0].update({'glyph_id': i+1, 'advance_height': 1000,
                        'vertical_origin_x': 500, 'vertical_origin_y': 860,
                        'advance': [1000, 0], 'base_advance': [1000, 0]})
                    if label != 'default':
                        row = self.change(row, 0)
                    if cp in (0x20, 0x3000):
                        for field in ('frame_ink', 'run_ink', 'path_ink'):
                            row[field] = {'has_ink': False, 'border_ink_pixels': 0}
                    row.update({'type': 'vertical_layout_character', 'face_index': face, 'case': label,
                        'physical_face_and_observed_axes_verified': True, 'nominal_glyph_id': i+1,
                        'codepoints': [cp], 'location': {'WDTH': 500, 'wght': 500, 'HGHT': 500},
                        'reported_location': {}})
                    rows.append(row)
                    mixed.extend(copy.deepcopy(row['glyphs']))
                rows.append({'type': 'vertical_layout_mixed', 'face_index': face, 'case': label,
                    'physical_face_and_observed_axes_verified': True, 'codepoints': list(CODEPOINTS),
                    'location': {'WDTH': 500, 'wght': 500, 'HGHT': 500}, 'reported_location': {}, 'glyphs': mixed})
        rows.append({'type': 'vertical_layout_summary', 'records': 420, 'error_count': 0})
        report = analyze(rows, fonts)
        self.assertEqual(report['character_records'], 378)
        self.assertEqual(report['mixed_text_records'], 42)
        self.assertEqual(report['raster_comparison_status'],
                         {'MEASURED_RELATIVE_DRAWING': 245, 'EMPTY_GLYPH_LAYOUT_RETAINED': 70})
        self.assertEqual(report['drawing_hypotheses']['frame_ink/upright/unchanged_origin']['maximum_magnitude'], 0)
        self.assertEqual(report['drawing_hypotheses']['frame_ink/upright/half_current_advance']['maximum_magnitude'], 100)
        json.dumps(report, allow_nan=False)
        with self.assertRaisesRegex(ValueError, 'incomplete_vertical_layout_diagnostic'):
            analyze(rows[:-2] + rows[-1:], fonts)
        with self.assertRaisesRegex(ValueError, 'duplicate_vertical_layout_case'):
            analyze(rows[:-1] + [rows[1], rows[-1]], fonts)
        rows[1]['nominal_glyph_id'] = 999
        with self.assertRaisesRegex(ValueError, 'native_nominal_cmap_changed'):
            analyze(rows, fonts)
        rows[1]['nominal_glyph_id'] = 1
        rows[0]['axis_observations_accepted'] = True
        with self.assertRaisesRegex(ValueError, 'unsafe_vertical_layout_scope'):
            analyze(rows, fonts)


if __name__ == '__main__':
    unittest.main()
