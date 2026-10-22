"""Independent GPOS mechanics, engine precision and font serialization examples.

HarfBuzz-dependent checks require the experiment's explicitly pinned optional
uharfbuzz dependency. The codec/static tests run without that dependency.
"""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import experiment_vertical_gpos as experiment

try:
    import uharfbuzz
except ImportError:
    uharfbuzz = None


class VerticalGPOSCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.symbols = experiment.original_fixture()

    def font(self, data):
        return TTFont(io.BytesIO(data), recalcTimestamp=False)

    def test_gpos_retains_original_mapping_axes_metrics_and_geometric_symbols(self):
        source = self.font(self.source)
        self.assertEqual(source['maxp'].numGlyphs, 8)
        self.assertEqual(source['cmap'].getBestCmap(),
                         {32: 'space', 65: 'latinA', 66: 'latinB', 0x4E2D: 'han'})
        self.assertEqual([(a.axisTag, a.minValue, a.defaultValue, a.maxValue)
                          for a in source['fvar'].axes], list(experiment.AXES))
        self.assertTrue(source['head'].flags & 2)
        self.assertEqual(source['glyf']['space'].numberOfContours, 0)
        for route in ('vert', 'vrt2', 'vkrn'):
            with self.subTest(route=route):
                candidate, failures = experiment.add_adjustment(self.source, self.symbols, route)
                font = self.font(candidate)
                self.assertFalse(failures)
                self.assertEqual(font.getGlyphOrder(), source.getGlyphOrder())
                self.assertEqual(font['head'].unitsPerEm, 1000)
                for tag in experiment.PROTECTED:
                    self.assertEqual(font.getTableData(tag), source.getTableData(tag), tag)
                self.assertEqual(font['GDEF'].table.Version, 0x10003)
                self.assertEqual(font['GPOS'].table.LookupList.Lookup[0].LookupType, 1)

    def test_serialized_multi_axis_compensation_has_independent_numerical_values(self):
        candidate, _ = experiment.add_adjustment(self.source, self.symbols, 'vert')
        for location, wanted in [((0, 0, 0), 0), ((1, 0, 0), 68),
                                 ((1, 1, -1), 86), ((-1, -1, -1), -78),
                                 ((.25, -.5, .75), 13.25)]:
            with self.subTest(location=location):
                actual = experiment.table_adjustments(candidate, self.symbols, location)
                self.assertEqual(actual['han.hk.vert'], wanted)

    def test_true_type_static_instancing_retains_advance_variations_and_original_contours(self):
        source = self.font(self.source)
        locations = ((0, 0, 0), (1, 1, -1), (-1, -1, -1), (.25, -.5, .75))
        for normalized in locations:
            with self.subTest(location=normalized):
                static = instantiateVariableFont(self.font(self.source),
                    experiment.requested_location(normalized), inplace=False, overlap=False)
                self.assertFalse({'fvar', 'gvar', 'HVAR'} & set(static.keys()))
                # Re-read the serialized static file, including the void glyph.
                reread = self.font(experiment.serialize(static))
                for symbol in self.symbols:
                    glyph = symbol.name
                    wanted = otRound(experiment.analytic_width(symbol, normalized))
                    self.assertEqual(reread['hmtx'][glyph][0], wanted)
                    self.assertEqual(reread['vmtx'][glyph], source['vmtx'][glyph])
                    old = source['glyf'][glyph].getCoordinates(source['glyf'])
                    new = reread['glyf'][glyph].getCoordinates(reread['glyf'])
                    self.assertEqual(new, old)
                if normalized == (1, 1, -1):
                    self.assertEqual(reread['hmtx']['space'][0], 492)
                    self.assertEqual(reread['hmtx']['han.hk.vert'][0], 1052)

    def test_odd_default_width_is_rejected_by_exact_value_record_encoder(self):
        source, symbols = experiment.original_fixture('odd_width')
        with self.assertRaises(experiment.UnrepresentableAdjustment) as caught:
            experiment.add_adjustment(source, symbols, 'vert')
        self.assertEqual(json.loads(str(caught.exception)),
                         [{'glyph': 'latinB', 'field': 'default_xPlacement', 'value': .5}])

    def test_odd_region_deltas_are_rejected_instead_of_silently_accumulating_rounding(self):
        source, symbols = experiment.original_fixture('odd_delta')
        with self.assertRaises(experiment.UnrepresentableAdjustment) as caught:
            experiment.add_adjustment(source, symbols, 'vert')
        failures = json.loads(str(caught.exception))
        self.assertEqual(len(failures), 10)
        candidate, recorded = experiment.add_adjustment(source, symbols, 'vert', diagnostic_rounding=True)
        self.assertEqual(recorded, failures)
        # Independent arithmetic: required shift is (418 / 2) - 240 = -31.
        # Rounding each active half-delta produces -27 -4 -2 +4 = -29.
        actual = experiment.table_adjustments(candidate, symbols, (-1, -1, -1))
        self.assertEqual(actual['latinB'], -29)
        self.assertEqual(actual['latinB'] - (-31), 2)


@unittest.skipIf(uharfbuzz is None, 'optional uharfbuzz dependency unavailable; native shaping NOT RUN')
class VerticalGPOSHarfBuzzTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.symbols = experiment.original_fixture()
        cls.candidates = {route: experiment.add_adjustment(cls.source, cls.symbols, route)[0]
                          for route in experiment.ROUTES}

    def test_default_feature_routing_keeps_horizontal_layout_and_exposes_missing_vertical_activation(self):
        for route, candidate in self.candidates.items():
            with self.subTest(route=route):
                before = experiment.shape(self.source, (1, 0, 0), 'ltr', 'zh-hk')
                after = experiment.shape(candidate, (1, 0, 0), 'ltr', 'zh-hk')
                self.assertEqual(before, after)
                self.assertEqual(after['glyphs'][0]['gid'], 3)
                vertical = experiment.shape(candidate, (1, 0, 0), 'ttb', 'zh-hk')
                glyph = vertical['glyphs'][0]
                self.assertEqual(glyph['gid'], 5)
                self.assertEqual(glyph['metric_width'], 1016)
                self.assertEqual(glyph['metric_vertical_origin'], [508, 860])
                self.assertEqual(glyph['x_offset'], -440 if route == 'vert' else -508)

    def test_explicit_enable_applies_the_same_cartesian_x_placement_in_both_directions(self):
        for route, candidate in self.candidates.items():
            features = experiment.feature_settings(route, 'enabled')
            for direction in ('ltr', 'ttb'):
                with self.subTest(route=route, direction=direction):
                    before = experiment.shape(self.source, (1, 0, 0), direction, 'zh-hk', features)
                    after = experiment.shape(candidate, (1, 0, 0), direction, 'zh-hk', features)
                    for b, a in zip(before['glyphs'], after['glyphs']):
                        for field in ('gid', 'cluster', 'metric_width', 'metric_height',
                                      'metric_vertical_origin', 'x_advance', 'y_advance', 'y_offset'):
                            self.assertEqual(a[field], b[field], field)
                    # Enabling vkrn in horizontal text does not enable GSUB vert.
                    # The horizontal HK glyph has a different advance delta.
                    is_horizontal_hk = route == 'vkrn' and direction == 'ltr'
                    self.assertEqual(after['glyphs'][0]['gid'], 3 if is_horizontal_hk else 5)
                    self.assertEqual(after['glyphs'][0]['x_offset']-before['glyphs'][0]['x_offset'],
                                     80 if is_horizontal_hk else 68)

    def test_disabling_feature_preserves_source_including_regional_and_vertical_substitutions(self):
        for route, candidate in self.candidates.items():
            for language in ('zh-cn', 'zh-hk'):
                features = experiment.feature_settings(route, 'disabled')
                self.assertEqual(experiment.shape(self.source, (1, -1, 1), 'ttb', language, features),
                                 experiment.shape(candidate, (1, -1, 1), 'ttb', language, features))

    def test_fractional_gpos_application_and_hvar_integer_rounding_are_distinct_observations(self):
        normalized = (.25, -.5, .75)
        before = experiment.shape(self.source, normalized, 'ttb', 'zh-cn')['glyphs'][1]
        after = experiment.shape(self.candidates['vert'], normalized, 'ttb', 'zh-cn')['glyphs'][1]
        self.assertEqual(before['gid'], 1)
        # The original space width is 400+20-8+6-.5 = 417.5.
        self.assertEqual(before['metric_width'], 418)
        self.assertEqual(before['metric_vertical_origin'], [209, 860])
        self.assertEqual(after['x_offset'] - before['x_offset'], 8.75)
        self.assertEqual(after['x_offset'] + 200, -.25)
        self.assertGreater(abs(after['x_offset'] + 200), experiment.LIMIT)
        self.assertLess(abs(after['x_offset'] + 200), experiment.RECONSTRUCTION_LIMIT)

    def test_static_serialized_gpos_keeps_compensation_including_empty_space(self):
        for location in ((0, 0, 0), (1, 1, -1), (-1, -1, -1), (.25, -.5, .75)):
            static = instantiateVariableFont(TTFont(io.BytesIO(self.candidates['vert'])),
                experiment.requested_location(location), inplace=False)
            data = experiment.serialize(static)
            shaped = experiment.shape(data, location, 'ttb', 'zh-hk')
            self.assertEqual(shaped['observed_normalized'], [])
            for glyph in shaped['glyphs']:
                wanted = self.symbols[glyph['gid']].width // 2
                self.assertLessEqual(abs(glyph['x_offset'] + wanted), .5)
                self.assertEqual(glyph['y_offset'], -860)
                self.assertEqual(glyph['y_advance'], -1000)
            if location == (1, 1, -1):
                self.assertEqual([g['x_offset'] for g in shaped['glyphs']], [-440, -200, -310, -240])

    def test_rounded_counterexamples_preserve_both_exact_failure_and_reconstruction_budget(self):
        for kind, location, error in [('odd_width', (0, 0, 0), .5),
                                      ('odd_delta', (-1, -1, -1), 2)]:
            source, symbols = experiment.original_fixture(kind)
            candidate, _ = experiment.add_adjustment(source, symbols, 'vert', diagnostic_rounding=True)
            glyph = experiment.shape(candidate, location, 'ttb', 'zh-cn')['glyphs'][-1]
            self.assertEqual(glyph['x_offset'] + symbols[-1].width//2, error)
            self.assertGreater(error, experiment.LIMIT)
            self.assertEqual(error > experiment.RECONSTRUCTION_LIMIT, kind == 'odd_delta')

    def test_failed_serialized_compensation_keeps_measured_evidence_in_safe_report(self):
        real_add = experiment.add_adjustment

        def corrupt(*args, **kwargs):
            data, failures = real_add(*args, **kwargs)
            font = TTFont(io.BytesIO(data), recalcTimestamp=False)
            table = font['GPOS'].table.LookupList.Lookup[0].SubTable[0]
            index = table.Coverage.glyphs.index('space')
            table.Value[index].XPlacement += 10
            return experiment.serialize(font), failures

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'failure.json'
            with mock.patch.object(experiment, 'add_adjustment', side_effect=corrupt):
                with self.assertRaisesRegex(ValueError, 'serialized_GPOS_table_equation_failed'):
                    experiment.run(output)
            report = json.loads(output.read_text())
            self.assertEqual(report['status'], 'HARFBUZZ_GPOS_EXPERIMENT_FAILED')
            self.assertFalse(report['font_binary_published'])
            self.assertFalse(report['source_or_production_modified'])
            measured = report['feature_routes']['vert']
            self.assertGreater(measured['shape_calls'], 0)
            self.assertAlmostEqual(measured['table_equation']['xPlacement_minus_required_compensation']
                                   ['max_abs_error'], 10, places=10)
            self.assertGreater(measured['policies']['enabled']['ttb']['fixed_origin_layout_error']
                               ['above_reconstruction_1_FUnit'], 0)
            saved = output.read_bytes()
            with self.assertRaisesRegex(ValueError, 'new_report_path_required'):
                experiment.run(output)
            self.assertEqual(output.read_bytes(), saved)


if __name__ == '__main__':
    unittest.main()
