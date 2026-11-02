"""Local tensors, with nonzero anchors, serialized as ordinary CFF2."""
import itertools
import io
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from fontTools.ttLib import TTCollection, TTFont
sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'tools'),
               str(Path(__file__).resolve().parents[1]/'platform')]
import cff2_geometry as geometry
from local_cff2_geometry import encode, interpolate
from cff2_metrics import prepare_from_truetype
from test_coretext_extract import make_fixture

TAGS = ('WDTH', 'wght', 'HGHT')
OPS = (('rmoveto', 2), ('rrcurveto', 6), ('rrcurveto', 6))


class LocalTensorTests(unittest.TestCase):
    def test_all_octants_and_zero_crossing_rebase_without_extrapolation(self):
        random = np.random.default_rng(137711)
        domains = list(itertools.product(((-1., -.25), (.25, 1.)), repeat=3))
        domains.append(((-1., 1.),)*3)
        for domain, basis in itertools.product(domains, ('tent', 'ramp')):
            knots = [np.linspace(a, b, 5) for a, b in domain]
            values = random.uniform(-20, 20, (5, 5, 5, 14))
            model = encode(knots, values, OPS, TAGS, basis=basis)
            held = np.asarray([random.uniform(a, b, 64) for a, b in domain]).T
            expected = interpolate(knots, values, held)
            actual = np.asarray([model.evaluate(dict(zip(TAGS, p))) for p in held])
            reference = np.cumsum(expected.reshape(len(held), -1, 2), axis=1)
            self.assertLess(np.linalg.norm(actual-reference, axis=2).max(), .002)
            self.assertLessEqual(len(model.supports), 125)
            self.assertFalse(model.evidence['sampled_geometry_passed'])
            self.assertEqual(model.evidence['box_selection'], 'NOT_IMPLEMENTED')
            model.charstring(0).compile(isCFF2=True)

    def serialized_case(self, basis):
        knots = [np.asarray([.25, .5, 1.]), np.asarray([-1., -.5, -.25]),
                 np.asarray([-.5, 0., .5])]
        random = np.random.default_rng(291779)
        values = random.uniform(-2, 2, (3, 3, 3, 14))
        model = encode(knots, values, OPS, TAGS, basis=basis)
        held = random.uniform([.25, -1., -.5], [1., -.25, .5], (64, 3))
        expected = interpolate(knots, values, held)
        errors = [np.linalg.norm(model.evaluate(dict(zip(TAGS, p)))-
                  geometry.control_points(OPS, row), axis=1).max()
                  for p, row in zip(held, expected)]
        self.assertLess(max(errors), 1/32)
        # This evidence authorizes only an authored local serialization fixture.
        model.evidence.update(sampled_geometry_passed=True,
                              fixture_scope='authored_local_box_only', failures=[])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as collection:
                original = collection.fonts[0]
                with self.assertRaisesRegex(ValueError, 'local_box_requires_verified_selection'):
                    geometry.install(prepare_from_truetype(original),
                        dict.fromkeys(original.getGlyphOrder(), model))
                font = geometry.install(prepare_from_truetype(original),
                    dict.fromkeys(original.getGlyphOrder(), model), experimental_local=True)
                stream = io.BytesIO(); font.save(stream)
            with TTFont(io.BytesIO(stream.getvalue())) as saved:
                regions = saved['CFF2'].cff.topDictIndex[0].VarStore.otVarStore.VarRegionList.Region
                self.assertEqual(len(regions), len(model.supports)-1)
                for p, row in zip(held, expected):
                    ops, actual = geometry.operands(geometry.source_commands(saved.getGlyphSet(
                        location=dict(zip(TAGS, map(float, p))), normalized=True)['probe']))
                    self.assertEqual(ops, OPS)
                    error = np.linalg.norm(geometry.control_points(ops, actual)-
                        geometry.control_points(OPS, row), axis=1).max()
                    self.assertLess(error, 1/32)

    def test_saved_font_keeps_local_knots_and_off_grid_controls(self):
        self.serialized_case('tent')

    def test_saved_ramp_font_keeps_off_grid_controls(self):
        self.serialized_case('ramp')

    def test_ramps_remove_affine_span_redundancy_without_changing_the_function(self):
        knots = [np.linspace(0, 1, 9)]*3
        x,y,z = np.meshgrid(*knots,indexing='ij')
        values = np.zeros((9,9,9,14))
        values[...,0] = 10+2*x+3*y+4*z+8*x*y*z
        values[...,1] = 20+6*x*y
        tent = encode(knots,values,OPS,TAGS)
        ramp = encode(knots,values,OPS,TAGS,basis='ramp')
        self.assertGreater(len(tent.supports), 507)
        self.assertEqual(len(ramp.supports), 6)
        for p in np.random.default_rng(112779).uniform(0,1,(64,3)):
            np.testing.assert_allclose(ramp.evaluate(dict(zip(TAGS,p))),
                                       tent.evaluate(dict(zip(TAGS,p))),rtol=0,atol=1e-12)
        with self.assertRaisesRegex(ValueError,'stack_overflow'):tent.charstring(0)
        ramp.charstring(0).compile(isCFF2=True)

    def test_invalid_knots_and_extrapolation_are_rejected(self):
        knots = [np.asarray([.25, .5, 1.])]*3
        values = np.zeros((3, 3, 3, 14))
        for bad in ([.1, .5, 1.], [-1., -.25, 1.], [.25, .25, 1.]):
            with self.assertRaises(ValueError): encode([bad, *knots[1:]], values, OPS, TAGS)
        with self.assertRaisesRegex(ValueError, 'extrapolation'):
            interpolate(knots, values, [[0, .5, .5]])


if __name__ == '__main__':
    unittest.main()
