"""Independent analytic metrics; no platform output or Apple data is a fixture."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTCollection, newTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from source_metrics import SourceMetrics, SourceMetricError
from metric_variations import add_metric_variations
from diagnose_coretext_metrics import add_metric_tables
from test_coretext_extract import make_fixture


class SourceMetricsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'original-metric-source.ttc'
        make_fixture(path)
        self.collection = TTCollection(path)
        self.addCleanup(self.collection.close)

    def assert_metrics(self, metric, x, w, y, gid=2):
        if gid == 2:
            cross = max(0, x) * max(0, y)
            width, height, top = 700 + 100*x + 30*w + 10*cross, 1000 + 150*y, 820 + 60*y
        else:
            width, height, top = (550 if gid == 0 else 400), 1000, 820
        for key, expected in [('advance_width', width), ('advance_height', height),
                              ('horizontal_origin_x', 0), ('vertical_origin_x', width / 2),
                              ('vertical_origin_y', top)]:
            self.assertAlmostEqual(metric[key], expected, places=9, msg=key)
        self.assertEqual(metric['metric_source'], 'unhinted_standard_source_tables_not_CoreText_API')

    def test_gvar_phantoms_preserve_fractional_metrics_and_empty_origins(self):
        for font in self.collection.fonts:
            provider = SourceMetrics(font)
            for point in [(-1, -1, -1), (0, 0, 0), (1, 1, 1),
                          (.2625, .2475, .42225), (-.37, .813, -.29)]:
                for gid in range(3):
                    actual = provider.at(gid, dict(zip(('WDTH', 'wght', 'HGHT'), point)))
                    self.assert_metrics(actual, *point, gid)
            fractional = provider.at(2, {'WDTH': .2625, 'wght': .2475, 'HGHT': .42225})
            self.assertAlmostEqual(fractional['advance_height'], 1063.3375)
            self.assertAlmostEqual(fractional['vertical_origin_y'], 845.335)
            self.assertNotEqual(fractional['advance_height'], 1063)

    def test_serialized_HVAR_VVAR_and_phantoms_are_equivalent(self):
        for font in self.collection.fonts:
            add_metric_variations(font)
            provider = SourceMetrics(font)
            for point in [(-1, 0, 1), (0, 0, 0), (.513, -.321, .733)]:
                for gid in range(3):
                    self.assert_metrics(provider.at(gid, dict(zip(provider.tags, point))), *point, gid)

    def test_optional_bearing_maps_use_control_bounds_and_can_change_origins(self):
        font = self.collection.fonts[0]
        add_metric_tables(font)
        provider = SourceMetrics(font)
        self.assert_metrics(provider.at(2, {'WDTH': 1, 'wght': 1, 'HGHT': 1}), 1, 1, 1)
        # Deliberately change the independent bearing model, not the contours.
        # This must affect the source origin; it may not be silently ignored.
        table = font['HVAR'].table
        index = table.LsbMap.mapping['probe']
        table.VarStore.VarData[index >> 16].Item[index & 65535][0] += 3
        table = font['VVAR'].table
        index = table.TsbMap.mapping['probe']
        table.VarStore.VarData[index >> 16].Item[index & 65535][0] += 7
        actual = SourceMetrics(font).at(2, {'WDTH': 1, 'wght': 1, 'HGHT': 1})
        self.assertEqual(actual['horizontal_origin_x'], -3)
        self.assertEqual(actual['vertical_origin_x'], 417)
        self.assertEqual(actual['vertical_origin_y'], 887)

    def test_VORG_default_and_per_glyph_override_without_glyf(self):
        font = self.collection.fonts[0]
        add_metric_variations(font)
        for tag in ('glyf', 'loca', 'gvar', 'VVAR'):
            del font[tag]
        font['hvgl'] = newTable('hvgl')
        font['hvgl'].data = b''  # No outline is used or claimed by this metric-only test.
        vorg = newTable('VORG')
        vorg.majorVersion, vorg.minorVersion = 1, 0
        vorg.defaultVertOriginY = 860
        vorg.VOriginRecords = {'probe': 877}
        font['VORG'] = vorg
        provider = SourceMetrics(font)
        for gid, top in [(0, 860), (1, 860), (2, 877)]:
            actual = provider.at(gid, {'WDTH': .5, 'wght': -.5, 'HGHT': .75})
            self.assertEqual(actual['vertical_origin_y'], top)
            self.assertEqual(actual['advance_height'], 1000)
            self.assertEqual(actual['vertical_origin_basis'], 'source_VORG')
        self.assertAlmostEqual(provider.at(2, {'WDTH': .5, 'wght': -.5, 'HGHT': .75})[
            'advance_width'], 738.75)

    def test_static_odd_width_keeps_half_unit_vertical_origin(self):
        font = self.collection.fonts[0]
        del font['fvar']; del font['gvar']; del font['avar']
        font['hmtx'].metrics['probe'] = (735, 100)
        provider = SourceMetrics(font)
        actual = provider.at(2, {})
        self.assertEqual(actual['advance_width'], 735)
        self.assertEqual(actual['vertical_origin_x'], 367.5)
        blank = provider.at(1, {})
        self.assertEqual((blank['vertical_origin_x'], blank['vertical_origin_y']), (200, 820))

    def test_omitted_phantoms_are_zero_and_do_not_copy_outline_deltas(self):
        font = self.collection.fonts[0]
        for variation in font['gvar'].variations['probe']:
            variation.coordinates[-4:] = [None] * 4
        actual = SourceMetrics(font).at(2, {'WDTH': 1, 'wght': 1, 'HGHT': 1})
        self.assertEqual((actual['advance_width'], actual['advance_height'], actual['vertical_origin_y']),
                         (700, 1000, 820))

    def test_HVAR_precedes_gvar_advance_without_double_application(self):
        font = self.collection.fonts[0]
        add_metric_variations(font)
        font['gvar'].variations['probe'][0].coordinates[-3] = (333, 0)
        actual = SourceMetrics(font).at(2, {'WDTH': 1, 'wght': 0, 'HGHT': 0})
        self.assertEqual(actual['advance_width'], 800)

    def test_all_source_table_bytes_remain_unchanged(self):
        font = self.collection.fonts[0]
        font.recalcTimestamp = False
        add_metric_tables(font)
        before = {tag: font.getTableData(tag) for tag in font.keys() if tag != 'GlyphOrder'}
        provider = SourceMetrics(font)
        for gid in range(3):
            provider.at(gid, {'WDTH': .317, 'wght': -.732, 'HGHT': .219})
        self.assertEqual(before, {tag: font.getTableData(tag) for tag in font.keys() if tag != 'GlyphOrder'})

    def test_invalid_coordinates_and_glyphs_are_rejected(self):
        provider = SourceMetrics(self.collection.fonts[0])
        for coordinates in ({}, {'WDTH': 0, 'wght': 0, 'HGHT': 0, 'bad': 0},
                            {'WDTH': 0, 'wght': float('nan'), 'HGHT': 0},
                            {'WDTH': 0, 'wght': 1.01, 'HGHT': 0},
                            {'WDTH': True, 'wght': 0, 'HGHT': 0}):
            with self.assertRaises(SourceMetricError):
                provider.at(2, coordinates)
        for gid in (-1, 3, True, 1.5):
            with self.assertRaises(SourceMetricError):
                provider.at(gid, {'WDTH': 0, 'wght': 0, 'HGHT': 0})

    def test_unknown_outline_or_variation_version_fails_explicitly(self):
        font = self.collection.fonts[0]
        original = copy.deepcopy(font)
        del font['glyf']
        with self.assertRaisesRegex(SourceMetricError, 'supported explicit origin'):
            SourceMetrics(font)
        add_metric_variations(original)
        original['HVAR'].table.Version += 1
        with self.assertRaisesRegex(SourceMetricError, 'unsupported HVAR'):
            SourceMetrics(original).at(2, {'WDTH': 0, 'wght': 0, 'HGHT': 0})


if __name__ == '__main__':
    unittest.main()
