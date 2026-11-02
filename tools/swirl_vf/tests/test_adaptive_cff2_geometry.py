import io
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from fontTools.ttLib import TTCollection, TTFont

sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'tools'),
               str(Path(__file__).resolve().parents[1]/'platform')]
from adaptive_cff2_geometry import fit_tensor
from piecewise_geometry import point_errors
from probe_hvf_cff2_geometry import positions, compare_commands
from test_coretext_extract import make_fixture
from make_cff2_fixture import convert, records
from cff2_metrics import prepare_from_truetype
import cff2_geometry as geometry

TAGS = ('WDTH', 'wght', 'HGHT')
OPS = (('rmoveto', 2), ('rrcurveto', 6), ('rlineto', 2))


def mixed_curve(points):
    x, y, z = np.asarray(points).T
    # This nonlinear interaction vanishes on every single-axis sweep.
    cross = .11*x*x*y*y*z
    return np.stack((10+x, 20+y, 100+x*y, 10+cross, 40+x*z,
                     25+cross, 40+y*z, 30-cross, -10+x, -20+z), axis=1)


class AdaptiveTensorTests(unittest.TestCase):
    def held(self):
        return np.random.default_rng(1641).uniform(-1, 1, (256, 3))

    def test_refinement_detects_nonadditive_three_axis_geometry(self):
        coarse=fit_tensor(mixed_curve, OPS, TAGS, self.held(), max_nodes=27)
        refined=fit_tensor(mixed_curve, OPS, TAGS, self.held())
        self.assertFalse(coarse.evidence['sampled_geometry_passed'])
        self.assertTrue(refined.evidence['sampled_geometry_passed'])
        self.assertGreater(refined.evidence['training_count'], 27)
        self.assertLessEqual(refined.evidence['training_count'], 507)
        self.assertLessEqual(refined.evidence['max_holdout_error'], 1/32)
        self.assertFalse(refined.evidence['production_accepted'])
        self.assertFalse(refined.evidence['continuous_space_proof'])
        self.assertGreater(len(refined.evidence['refinement']), 1)

    def test_native_plan_and_holdouts_remain_independent(self):
        grid, held=positions()
        self.assertEqual(grid.shape, (27, 3)); self.assertEqual(held.shape, (32, 3))
        self.assertTrue((held != 0).all())
        self.assertTrue(((held*16384).astype(int) % 2 != 0).all())
        with self.assertRaisesRegex(ValueError, 'holdout_used'):
            fit_tensor(mixed_curve, OPS, TAGS, [[0, 0, 0]])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            fit_tensor(mixed_curve, OPS, TAGS, [[.1, .2, .3]]*2)

    def test_serialized_ordinary_blends_preserve_curves_at_mixed_positions(self):
        model=fit_tensor(mixed_curve, OPS, TAGS, self.held())
        for support in model.supports:
            for triple in support.values():
                self.assertTrue(all(v*16384 == int(v*16384) for v in triple))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'authored.ttc';make_fixture(path)
            with TTCollection(path) as original:
                source=original.fonts[0]; _, models=convert(source)
                models[source.getGlyphOrder()[2]]=model
                candidate=geometry.install(prepare_from_truetype(source), models)
                data=io.BytesIO();candidate.save(data)
            with TTFont(io.BytesIO(data.getvalue())) as saved:
                for point in self.held()[::8]:
                    location=dict(zip(TAGS, map(float, point)))
                    ops, values=geometry.operands(geometry.source_commands(
                        saved.getGlyphSet(location=location, normalized=True)['probe']))
                    self.assertEqual(ops, OPS)
                    self.assertLessEqual(point_errors(values[None,:], mixed_curve([point]))[0], 1/32)
                    np.testing.assert_allclose(geometry.control_points(ops, values), model.evaluate(location), atol=1e-9)

    def test_missing_curve_and_control_accumulation_cannot_be_hidden(self):
        wanted=[['moveTo',0,0],['qCurveTo',100,200,300,0],['closePath']]
        changed=[['moveTo',0,0],['qCurveTo',100,200.1,300,0],['closePath']]
        self.assertFalse(compare_commands(wanted, [])['passed'])
        self.assertFalse(compare_commands(wanted, changed)['passed'])
        self.assertTrue(compare_commands(wanted, wanted)['passed'])

    def test_authored_native_fixture_keeps_every_GID_and_nonlinear_cross_term(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'authored.ttc'; make_fixture(path)
            with TTCollection(path) as original:
                source=original.fonts[0]
                candidate,models=convert(source,.25,adaptive=True)
                self.assertEqual(candidate.getGlyphOrder(),source.getGlyphOrder())
                for tag in ('cmap','fvar','hmtx','vmtx'):
                    self.assertEqual(candidate.getTableData(tag),source.getTableData(tag))
                cross=dict(zip(TAGS,(1.,1.,1.)))
                a=records(source,'probe',[cross],.25)[0]
                b=records(source,'probe',[cross],.25,nonlinear=True)[0]
                original_curve=next(c for c in a if c[0]=='qCurveTo')
                changed_curve=next(c for c in b if c[0]=='qCurveTo')
                self.assertAlmostEqual(changed_curve[2]-original_curve[2],.11)
                data=io.BytesIO();candidate.save(data)
                with TTFont(io.BytesIO(data.getvalue())) as saved:
                    for p in self.held()[::16]:
                        loc=dict(zip(TAGS,map(float,p)))
                        for name in source.getGlyphOrder():
                            expected=records(source,name,[loc],.25,nonlinear=True)[0]
                            actual=geometry.source_commands(saved.getGlyphSet(location=loc,normalized=True)[name])
                            self.assertTrue(compare_commands(expected,actual)['passed'])
                self.assertTrue(all(m.evidence['sampled_geometry_passed'] for m in models.values()))

    def test_failed_capacity_is_not_installable_and_empty_geometry_is_retained(self):
        coarse=fit_tensor(mixed_curve, OPS, TAGS, self.held(), max_nodes=27)
        self.assertTrue(coarse.evidence['failures'])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'authored.ttc';make_fixture(path)
            with TTCollection(path) as original:
                source=original.fonts[0]
                with self.assertRaisesRegex(ValueError, 'unaccepted'):
                    geometry.install(source, dict.fromkeys(source.getGlyphOrder(), coarse))
        empty=fit_tensor(lambda p: np.empty((len(p),0)), (), TAGS, self.held())
        self.assertTrue(empty.evidence['sampled_geometry_passed'])
        self.assertEqual(empty.charstring(0).program, [])
