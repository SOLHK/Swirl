"""Fractional geometry and actual CFF2/TTC serialization, never font acceptance."""
import copy
import io
import itertools
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib.varStore import VarStoreInstancer

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'tools'),
               str(Path(__file__).resolve().parents[1] / 'platform')]
import cff2_geometry as geometry
from cff2_metrics import prepare_from_truetype
from test_coretext_extract import make_fixture
from make_cff2_fixture import TAGS, GRID, HOLDOUTS, records, convert


class CFF2GeometryTests(unittest.TestCase):
    def test_fractional_default_and_three_axis_models_survive_collection_serialization(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'source.ttc'; make_fixture(source)
            with TTCollection(source) as collection:
                original = source.read_bytes()
                converted = [convert(font, .25) for font in collection.fonts]
                target = TTCollection(); target.fonts = [font for font, _ in converted]
                stream = io.BytesIO(); target.save(stream, shareTables=True)
                with TTCollection(io.BytesIO(stream.getvalue())) as saved:
                    self.assertEqual(len(saved.fonts), 2)
                    for font, (expected_font, models), reference in zip(saved.fonts, converted, collection.fonts):
                        self.assertEqual(font.sfntVersion, 'OTTO')
                        self.assertEqual(font.getGlyphOrder(), reference.getGlyphOrder())
                        self.assertIn('CFF2', font)
                        self.assertNotIn('glyf', font)
                        self.assertEqual(font['head'].indexToLocFormat, 0)
                        self.assertEqual(font['head'].glyphDataFormat, 0)
                        self.assertEqual((font['head'].xMin, font['head'].xMax), (50, 501))
                        self.assertEqual([axis.axisTag for axis in font['fvar'].axes], list(TAGS))
                        for name in font.getGlyphOrder():
                            for location in GRID + HOLDOUTS:
                                commands = geometry.source_commands(font.getGlyphSet(location=location,
                                    normalized=True)[name])
                                ops, values = geometry.operands(commands)
                                expected = models[name].evaluate(location)
                                self.assertEqual(ops, models[name].operators)
                                actual = geometry.control_points(ops, values)
                                self.assertLessEqual(float(np.linalg.norm(actual-expected, axis=1).max(initial=0)), 1/32)
                        for tag in ('cmap', 'fvar', 'hmtx', 'vmtx'):
                            self.assertEqual(font.getTableData(tag), reference.getTableData(tag))
                self.assertEqual(source.read_bytes(), original)

    def test_CFF2_vertical_origin_map_matches_original_phantoms(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as collection:
                for source in collection.fonts:
                    font = prepare_from_truetype(source)
                    vvar = font['VVAR'].table
                    for p in GRID + HOLDOUTS:
                        store = VarStoreInstancer(vvar.VarStore, font['fvar'].axes, p)
                        for gid, name in enumerate(font.getGlyphOrder()):
                            height = font['vmtx'].metrics[name][0] + store[vvar.AdvHeightMap.mapping[name]]
                            origin = font['VORG'][name] + store[vvar.VOrgMap.mapping[name]]
                            self.assertAlmostEqual(height, 1000 + (150*p['HGHT'] if gid==2 else 0))
                            self.assertAlmostEqual(origin, 820 + (60*p['HGHT'] if gid==2 else 0))

    def test_changed_topology_missing_glyphs_and_nonfinite_values_are_rejected(self):
        square = [['moveTo', .25, 0], ['lineTo', 20.25, 20], ['closePath']]
        with self.assertRaisesRegex(geometry.CFF2GeometryError, 'topology_changed'):
            geometry.fit([square, square[:-1]+[['lineTo', 2, 3], ['closePath']]],
                [{}, {'WDTH':1}], [square], [{'WDTH':.5}], TAGS)
        bad = copy.deepcopy(square); bad[0][1] = float('nan')
        with self.assertRaisesRegex(geometry.CFF2GeometryError, 'nonfinite'):
            geometry.operands(bad)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as collection:
                with self.assertRaisesRegex(geometry.CFF2GeometryError, 'complete_original_GID'):
                    geometry.install(collection.fonts[0], {})

    def test_holdout_failure_is_retained_and_cannot_be_installed(self):
        a=[['moveTo',0,0],['lineTo',100,200],['closePath']]
        b=[['moveTo',0,0],['lineTo',100.25,200],['closePath']]
        model=geometry.fit([a,a],[{}, {'WDTH':1}],[b],[{'WDTH':.5}],TAGS)
        self.assertFalse(model.evidence['sampled_geometry_passed'])
        self.assertEqual(model.evidence['failures'][0]['error_source_units'], .25)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as collection:
                font=collection.fonts[0]
                with self.assertRaisesRegex(geometry.CFF2GeometryError, 'unaccepted'):
                    geometry.install(font, dict.fromkeys(font.getGlyphOrder(), model))

    def test_factored_blends_preserve_dense_three_axis_function_after_serialization(self):
        # 729 Cartesian masters exceed a flat blend's 513-entry operand stack.
        # Piecewise affine factors give a separately defined exact reference at
        # both masters and off-grid points; nested blends must preserve it.
        nodes=[float(v) for v in np.linspace(-1,1,9)]
        locations=[dict(zip(TAGS,p)) for p in itertools.product(nodes,repeat=3)]
        def command(p):
            def ramp(x): return sum((i+1)*max(0,x-v) for i,v in enumerate(nodes[1:-1]))/8
            x,y,z=(ramp(p[t]) for t in TAGS)
            return [['moveTo',10.25+2*x*y*z,20.125],
                    ['lineTo',110.25+3*x*y+z,220.125],['closePath']]
        held=[dict(zip(TAGS,p)) for p in ((.17,-.31,.79),(-.77,.42,.57),(.92,.83,.74))]
        model=geometry.fit([command(p) for p in locations],locations,
                           [command(p) for p in held],held,TAGS)
        self.assertTrue(model.evidence['sampled_geometry_passed'])
        with self.assertRaisesRegex(geometry.CFF2GeometryError, 'stack_overflow'):
            model.charstring(0)
        factored=geometry.factor(model)
        self.assertLess(len(factored.supports),len(model.supports))
        for p in held+locations[::100]:
            np.testing.assert_allclose(factored.evaluate(p),model.evaluate(p),atol=1e-10)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.ttc';make_fixture(path)
            with TTCollection(path) as source:
                font=source.fonts[0]
                candidate=geometry.install(prepare_from_truetype(font),
                                           dict.fromkeys(font.getGlyphOrder(),factored))
                stream=io.BytesIO();candidate.save(stream)
            with TTFont(io.BytesIO(stream.getvalue())) as font:
                for p in held+locations[::100]:
                    actual=geometry.operands(geometry.source_commands(font.getGlyphSet(
                        location=p,normalized=True)['probe']))
                    expected=geometry.operands(command(p))
                    self.assertEqual(actual[0],expected[0])
                    error=np.linalg.norm(geometry.control_points(*actual)-
                                         geometry.control_points(*expected),axis=1).max()
                    self.assertLessEqual(float(error),1/32)
