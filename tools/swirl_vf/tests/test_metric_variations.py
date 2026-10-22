"""Exact metric encodings; all fixtures are original geometric test fonts."""
import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib.varStore import VarStoreInstancer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from metric_variations import add_metric_variations, verify_metric_variations, MetricVariationError
from test_coretext_extract import make_fixture, normalized
from rebuild import verify_serialized_face, ReconstructionError


class MetricVariationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name) / 'original-geometry.ttc'
        make_fixture(path)
        self.collection = TTCollection(path)
        self.addCleanup(self.collection.close)

    def roundtrip(self, font):
        output = io.BytesIO()
        font.recalcTimestamp = False
        font.save(output)
        output.seek(0)
        saved = TTFont(output)
        self.addCleanup(saved.close)
        return saved

    def test_all_faces_three_axes_independent_fractional_metric_formulas(self):
        for face in self.collection.fonts:
            before = {tag: face.getTableData(tag) for tag in ('glyf', 'gvar', 'hmtx', 'vmtx', 'fvar')}
            face['head'].flags = 0  # Uploaded HVF source also has bit 1 unset.
            report = add_metric_variations(face)
            self.assertEqual(report['glyph_metric_models_checked'], 6)
            self.assertTrue(face['head'].flags & 2)
            for tag, data in before.items():
                self.assertEqual(face.getTableData(tag), data, tag)
            saved = self.roundtrip(face)
            verify_metric_variations(saved)
            for location in ({'WDTH': -1, 'wght': -1, 'HGHT': -1},
                             {'WDTH': 1, 'wght': 1, 'HGHT': 1},
                             {'WDTH': 0, 'wght': 0, 'HGHT': 0},
                             {'WDTH': .27113, 'wght': -.62127, 'HGHT': .37519},
                             {'WDTH': -.71337, 'wght': .35797, 'HGHT': -.47449}):
                x, w, y = (location[tag] for tag in ('WDTH', 'wght', 'HGHT'))
                want = {'HVAR': 100*x + 30*w + 10*max(0,x)*max(0,y), 'VVAR': 150*y}
                for tag, field in (('HVAR', 'AdvWidthMap'), ('VVAR', 'AdvHeightMap')):
                    table = saved[tag].table
                    inst = VarStoreInstancer(table.VarStore, saved['fvar'].axes, location)
                    for name in saved.getGlyphOrder():
                        actual = inst[getattr(table, field).mapping[name]]
                        self.assertAlmostEqual(actual, want[tag] if name == 'probe' else 0, places=9)
            self.assertIsNone(saved['VVAR'].table.VOrgMap)
            self.assertIsNone(saved['VVAR'].table.TsbMap)
            self.assertIsNone(saved['HVAR'].table.LsbMap)

    def test_horizontal_only_font_does_not_gain_vertical_tables(self):
        face = self.collection.fonts[0]
        del face['vmtx']; del face['vhea']
        result = add_metric_variations(face)
        self.assertEqual(result['tables'], ['HVAR'])
        self.assertNotIn('VVAR', face)
        verify_metric_variations(self.roundtrip(face))

    def test_no_variations_and_blank_glyph_keep_metrics(self):
        face = self.collection.fonts[0]
        face['gvar'].variations = {name: [] for name in face.getGlyphOrder()}
        add_metric_variations(face)
        verify_metric_variations(self.roundtrip(face))

    def test_omitted_phantoms_are_zero_not_interpolated(self):
        face = self.collection.fonts[0]
        for v in face['gvar'].variations['probe']:
            v.coordinates[-4:] = [None] * 4
        add_metric_variations(face)
        verify_metric_variations(self.roundtrip(face))
        table = face['HVAR'].table
        self.assertEqual(VarStoreInstancer(table.VarStore, face['fvar'].axes, {'wght':1})[
            table.AdvWidthMap.mapping['probe']], 0)

    def test_repeated_supports_are_added_not_overwritten(self):
        face = self.collection.fonts[0]
        face['gvar'].variations['probe'] *= 2
        add_metric_variations(face)
        verify_metric_variations(self.roundtrip(face))
        table = face['HVAR'].table
        self.assertEqual(VarStoreInstancer(table.VarStore, face['fvar'].axes, {'WDTH':1})[
            table.AdvWidthMap.mapping['probe']], 200)

    def test_existing_tables_are_not_silently_replaced(self):
        face = self.collection.fonts[0]
        add_metric_variations(face)
        hvar = face.getTableData('HVAR')
        with self.assertRaisesRegex(MetricVariationError, 'explicitly'):
            add_metric_variations(face)
        self.assertEqual(face.getTableData('HVAR'), hvar)

    def test_bad_origin_rejected_before_any_font_mutation(self):
        face = self.collection.fonts[0]
        face['hmtx'].metrics['probe'] = (700, 99)
        flags = face['head'].flags
        with self.assertRaisesRegex(MetricVariationError, 'LSB equal'):
            add_metric_variations(face)
        self.assertNotIn('HVAR', face); self.assertNotIn('VVAR', face)
        self.assertEqual(face['head'].flags, flags)

    def test_nonzero_left_phantom_is_rejected(self):
        face = self.collection.fonts[0]
        face['gvar'].variations['probe'][0].coordinates[-4] = (1, 0)
        with self.assertRaisesRegex(MetricVariationError, 'left phantom'):
            add_metric_variations(face)
        self.assertNotIn('HVAR', face)

    def test_nonrepresentable_support_is_rejected_without_rounding(self):
        face = self.collection.fonts[0]
        face['gvar'].variations['probe'][0].axes = {'WDTH': (0, .123456789, 1)}
        with self.assertRaisesRegex(MetricVariationError, 'F2DOT14'):
            add_metric_variations(face)
        self.assertNotIn('HVAR', face)

    def test_mutated_metric_coefficients_are_rejected(self):
        face = self.collection.fonts[0]
        add_metric_variations(face)
        saved = self.roundtrip(face)
        table = saved['HVAR'].table
        idx = table.AdvWidthMap.mapping['probe']
        table.VarStore.VarData[idx >> 16].Item[idx & 65535][0] += 1
        with self.assertRaisesRegex(MetricVariationError, 'coefficients differ'):
            verify_metric_variations(saved)
        with self.assertRaisesRegex(ReconstructionError, 'serialized HVAR'):
            verify_serialized_face(face, saved)

    def test_missing_or_corrupt_head_flag_is_not_a_pass(self):
        face = self.collection.fonts[0]
        add_metric_variations(face)
        saved = self.roundtrip(face)
        saved['head'].flags &= ~2
        with self.assertRaisesRegex(MetricVariationError, 'head.flags'):
            verify_serialized_face(face, saved)
        del face['VVAR']
        with self.assertRaisesRegex(MetricVariationError, 'missing rebuilt'):
            verify_metric_variations(face)


if __name__ == '__main__':
    unittest.main()
