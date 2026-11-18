"""Independent serialized coefficient verification, including hidden regions."""
import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from fontTools.ttLib import TTCollection, TTFont

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'tools'),
               str(Path(__file__).resolve().parents[1] / 'platform')]
from cff2_certificate import certify, decode
from cff2_subroutines import pack
import cff2_geometry as geometry
from cff2_metrics import prepare_from_truetype
from make_cff2_fixture import convert, GRID
from test_coretext_extract import make_fixture


def reopened(font):
    buffer = io.BytesIO(); font.save(buffer)
    return TTFont(io.BytesIO(buffer.getvalue()))


class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / 'source.ttc'; make_fixture(path)
        self.source = TTCollection(path); self.addCleanup(self.source.close)

    def test_all_three_axes_and_empty_GIDs_certified_after_TTC_table_sharing(self):
        pairs = [convert(font, .25) for font in self.source.fonts]
        collection = TTCollection(); collection.fonts = [f for f, _ in pairs]
        buffer = io.BytesIO(); collection.save(buffer, shareTables=True)
        with TTCollection(io.BytesIO(buffer.getvalue())) as saved:
            for font, (_, models) in zip(saved.fonts, pairs):
                report = certify(font, models)
                self.assertEqual(report['glyphs'], 3)
                self.assertTrue(report['all_simultaneous_design_coordinates'])
                self.assertFalse(report['source_fit_accepted'])
                self.assertFalse(report['native_execution'])
                self.assertFalse(report['production_accepted'])

    def test_hidden_multiaxis_region_is_caught_when_all_27_grid_points_match(self):
        source = self.source.fonts[0]; font, models = convert(source, .25)
        changed = copy.deepcopy(models)
        model = changed['probe']
        model.supports.append({tag: (0, .125, .25) for tag in model.axis_tags})
        row = np.zeros((1, model.deltas.shape[1])); row[0, 0] = 1
        model.deltas = np.concatenate((model.deltas, row))
        for p in GRID:
            np.testing.assert_array_equal(model.evaluate(p), models['probe'].evaluate(p))
        mutated = geometry.install(prepare_from_truetype(source), changed)
        with reopened(mutated) as saved:
            with self.assertRaisesRegex(ValueError, 'serialized_coefficient_mismatch'):
                certify(saved, models)
            self.assertEqual(certify(saved, changed)['glyphs'], 3)

    def test_subroutine_packing_preserves_complete_coefficients(self):
        font, models = convert(self.source.fonts[0], .25)
        self.assertGreater(pack(font, byte_limit=256)['glyphs_repacked'], 0)
        with reopened(font) as saved:
            self.assertGreater(certify(saved, models)['decoded_tokens'], 0)

    def test_blend_across_subroutine_boundary_and_mixed_static_arguments(self):
        from diagnose_cff2_directwrite import move_blend_operator_to_subroutine
        font, models = convert(self.source.fonts[0], .25)
        move_blend_operator_to_subroutine(font['CFF2'].cff.topDictIndex[0])
        with reopened(font) as saved:
            self.assertEqual(certify(saved, models)['glyphs'], 3)

    def test_nested_blend_remains_explicitly_unsupported_by_certificate(self):
        from diagnose_cff2_directwrite import nest_identity_blends
        font, models = convert(self.source.fonts[0], .25)
        nest_identity_blends(font['CFF2'].cff.topDictIndex[0], 'nested_default')
        with reopened(font) as saved:
            with self.assertRaisesRegex(ValueError, 'nested_or_variable'):
                certify(saved, models)

    def test_incomplete_coverage_axes_and_unserialized_fonts_fail(self):
        font, models = convert(self.source.fonts[0], .25)
        # A detached converted font may retain a reader for its source. Its
        # generated CharStrings still have no serialized bytes to certify.
        with self.assertRaisesRegex(ValueError, 'reopened_CFF2_font'):
            certify(font, models)
        with reopened(font) as saved:
            with self.assertRaisesRegex(ValueError, 'complete_GID'):
                certify(saved, {'probe': models['probe']})
            bad = copy.deepcopy(models); bad['probe'].axis_tags = ('wdth', 'wght', 'HGHT')
            with self.assertRaisesRegex(ValueError, 'ordinary_model_axes'):
                certify(saved, bad)

    def test_changed_region_support_is_not_hidden_by_identical_coefficients(self):
        font, models = convert(self.source.fonts[0], .25)
        store = font['CFF2'].cff.topDictIndex[0].VarStore.otVarStore
        region = store.VarRegionList.Region[0].VarRegionAxis
        axis = next(a for a in region if a.PeakCoord != 0)
        axis.PeakCoord /= 2
        with reopened(font) as saved:
            with self.assertRaisesRegex(ValueError, 'serialized_coefficient_mismatch'):
                certify(saved, models)
            # Restoring an edited table in memory must not hide corruption in
            # the actual serialized file that a native engine would load.
            axes = saved['CFF2'].cff.topDictIndex[0].VarStore.otVarStore.VarRegionList.Region[0].VarRegionAxis
            next(a for a in axes if a.PeakCoord != 0).PeakCoord *= 2
            with self.assertRaisesRegex(ValueError, 'serialized_coefficient_mismatch'):
                certify(saved, models)
            self.assertFalse(saved.reader.file.closed)

    def test_budget_is_checked_and_unknown_operators_are_not_ignored(self):
        font, _ = convert(self.source.fonts[0], .25)
        with reopened(font) as saved:
            with self.assertRaisesRegex(ValueError, 'token_budget_exceeded'):
                decode(saved, 'probe', max_tokens=2)
        top = font['CFF2'].cff.topDictIndex[0]
        top.CharStrings['probe'].setProgram([10, 'hmoveto'])
        with reopened(font) as saved:
            with self.assertRaisesRegex(ValueError, 'unsupported_operator'):
                decode(saved, 'probe')


if __name__ == '__main__':
    unittest.main()
