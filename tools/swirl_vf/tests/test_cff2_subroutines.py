"""Lossless large CharString encoding, including real 65,535-byte crossings."""
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
import cff2_geometry as geometry
from cff2_subroutines import MAX_BYTES, encode, pack
from make_cff2_fixture import GRID, HOLDOUTS, convert
from test_coretext_extract import make_fixture


class CFF2SubroutineTests(unittest.TestCase):
    def test_large_variable_contours_survive_serialization_without_point_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'source.ttc'; make_fixture(source)
            with TTCollection(source) as collection:
                source_bytes = source.read_bytes()
                font, models = convert(collection.fonts[0], .25, repeat_contours=512)
                top = font['CFF2'].cff.topDictIndex[0]
                globals_ = font['CFF2'].cff.GlobalSubrs
                self.assertGreater(len(globals_), 0)
                self.assertGreater(max(len(encode(model.charstring(0).program,
                    top.FDArray[0].Private, globals_).bytecode) for model in models.values()), MAX_BYTES)
                self.assertTrue(all(len(encode(cs.program,cs.private,globals_).bytecode) <= MAX_BYTES
                    for cs in top.CharStrings.values()))
                self.assertTrue(all(len(cs.bytecode) <= MAX_BYTES for cs in globals_))
                self.assertEqual(pack(font)['glyphs_repacked'], 0)
                stream = io.BytesIO(); font.save(stream)
                with TTFont(io.BytesIO(stream.getvalue())) as saved:
                    self.assertEqual(saved.getGlyphOrder(), collection.fonts[0].getGlyphOrder())
                    for tag in ('cmap', 'fvar', 'avar', 'hmtx', 'vmtx', 'HVAR', 'VVAR'):
                        self.assertEqual(saved.getTableData(tag), font.getTableData(tag))
                    for p in GRID + HOLDOUTS:
                        for name, model in models.items():
                            ops, values = geometry.operands(geometry.source_commands(
                                saved.getGlyphSet(location=p, normalized=True)[name]))
                            self.assertEqual(ops, model.operators)
                            np.testing.assert_allclose(geometry.control_points(ops,values),
                                                       model.evaluate(p), rtol=0, atol=1e-9)
                self.assertEqual(source.read_bytes(), source_bytes)

    def test_deduplicated_blocks_keep_call_bias_and_fractional_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttc'; make_fixture(source)
            with TTCollection(source) as collection:
                font,_=convert(collection.fonts[0],.25)
                top=font['CFF2'].cff.topDictIndex[0]
                # A smaller limit exercises many calls, reuse and the bias
                # without depending on source-font data or fitting artifacts.
                before=copy.deepcopy(font)
                report=pack(font,byte_limit=256)
                self.assertGreater(report['glyphs_repacked'],0)
                self.assertLessEqual(report['maximum_subroutine_bytes'],256)
                stream=io.BytesIO();font.save(stream)
                with TTFont(io.BytesIO(stream.getvalue())) as saved:
                    for p in GRID+HOLDOUTS:
                        for name in font.getGlyphOrder():
                            a=geometry.operands(geometry.source_commands(saved.getGlyphSet(location=p,normalized=True)[name]))
                            b=geometry.operands(geometry.source_commands(before.getGlyphSet(location=p,normalized=True)[name]))
                            self.assertEqual(a[0],b[0]);np.testing.assert_allclose(a[1],b[1],rtol=0,atol=1e-10)

    def test_unrepresentable_single_operation_fails_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttc'; make_fixture(source)
            with TTCollection(source) as collection:
                font,_=convert(collection.fonts[0],.25)
                top=font['CFF2'].cff.topDictIndex[0]
                programs={name:list(top.CharStrings[name].program) for name in font.getGlyphOrder()}
                with self.assertRaisesRegex(ValueError,'single_cff2_drawing_operation_too_large'):
                    pack(font,byte_limit=32)
                self.assertEqual(len(font['CFF2'].cff.GlobalSubrs),0)
                self.assertEqual(programs,{name:list(top.CharStrings[name].program) for name in font.getGlyphOrder()})

    def test_cannot_increase_the_format_limit(self):
        for limit in (0,31,65536,65535.0,True):
            with self.assertRaisesRegex(ValueError,'invalid_cff2_byte_limit'):
                pack(None,byte_limit=limit)
