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
        for domain, basis in itertools.product(domains, ('tent', 'ramp', 'hierarchical')):
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

    def serialized_case(self, basis, absolute_quantization=False):
        knots = [np.asarray([.25, .5, 1.]), np.asarray([-1., -.5, -.25]),
                 np.asarray([-.5, 0., .5])]
        random = np.random.default_rng(291779)
        values = random.uniform(-2, 2, (3, 3, 3, 14))
        absolute = None
        if absolute_quantization:
            absolute = values.reshape(3,3,3,7,2).copy()
            absolute[...,-1,:] = absolute[...,0,:]
            values = np.diff(absolute,axis=-2,
                             prepend=np.zeros((3,3,3,1,2))).reshape(3,3,3,14)
        model = encode(knots, values, OPS, TAGS, basis=basis,absolute_values=absolute)
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
                if absolute_quantization:
                    from cff2_certificate import certify
                    self.assertTrue(certify(saved,dict.fromkeys(saved.getGlyphOrder(),model))[
                        'all_simultaneous_design_coordinates'])
                regions = saved['CFF2'].cff.topDictIndex[0].VarStore.otVarStore.VarRegionList.Region
                self.assertEqual(len(regions), len(model.supports)-1)
                for p, row in zip(held, expected):
                    ops, actual = geometry.operands(geometry.source_commands(saved.getGlyphSet(
                        location=dict(zip(TAGS, map(float, p))), normalized=True)['probe']))
                    self.assertEqual(ops, OPS)
                    error = np.linalg.norm(geometry.control_points(ops, actual)-
                        geometry.control_points(OPS, row), axis=1).max()
                    self.assertLess(error, 1/32)
                    if absolute_quantization:
                        controls = geometry.control_points(ops,actual)
                        np.testing.assert_allclose(controls[0],controls[-1],rtol=0,atol=1e-10)

    def test_saved_font_keeps_local_knots_and_off_grid_controls(self):
        self.serialized_case('tent')

    def test_saved_ramp_font_keeps_off_grid_controls(self):
        self.serialized_case('ramp')

    def test_saved_hierarchical_font_keeps_off_grid_controls(self):
        self.serialized_case('hierarchical')

    def test_saved_absolute_control_coefficients_preserve_closure(self):
        self.serialized_case('hierarchical',absolute_quantization=True)

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

    def test_absolute_quantization_preserves_closed_and_coincident_controls(self):
        rng = np.random.default_rng(710449)
        knots = [np.array([0., .25, .5, 1.])]*3
        absolute = rng.uniform(-20, 20, (4, 4, 4, 7, 2))
        absolute[..., 3, :] = absolute[..., 0, :]
        absolute[..., 6, :] = absolute[..., 0, :]
        relative = np.diff(absolute, axis=-2,
                           prepend=np.zeros((4,4,4,1,2))).reshape(4,4,4,14)
        for basis in ('tent', 'ramp', 'hierarchical'):
            model = encode(knots,relative,OPS,TAGS,basis=basis,absolute_values=absolute)
            ticks = np.rint(model.deltas*65536).astype(np.int64)
            controls = np.cumsum(ticks.reshape(len(ticks),-1,2),axis=1)
            np.testing.assert_array_equal(controls[:,0],controls[:,3])
            np.testing.assert_array_equal(controls[:,0],controls[:,6])
            self.assertFalse(model.evidence['sampled_geometry_passed'])
            for p in rng.uniform(0,1,(32,3)):
                points = model.evaluate(dict(zip(TAGS,p)))
                np.testing.assert_allclose(points[0],points[-1],rtol=0,atol=1e-10)

    def test_absolute_quantization_avoids_long_contour_rounding_accumulation(self):
        # Each tiny but nonzero segment must survive in the nodal observations.
        # Independent relative rounding destroys their accumulated displacement.
        knots = [np.array([0.,1.])]*3
        point_count = 301
        operators = (('rmoveto',2),)+(('rrcurveto',6),)*100
        absolute = np.zeros((2,2,2,point_count,2))
        absolute[...,0] = np.arange(point_count)*(.49/65536)
        relative = np.diff(absolute,axis=-2,
                           prepend=np.zeros((2,2,2,1,2))).reshape(2,2,2,-1)
        legacy = encode(knots,relative,operators,TAGS,basis='hierarchical')
        model = encode(knots,relative,operators,TAGS,basis='hierarchical',absolute_values=absolute)
        target = absolute[0,0,0]
        self.assertGreater(np.max(np.linalg.norm(legacy.evaluate({})-target,axis=1)),.002)
        self.assertLessEqual(np.max(np.linalg.norm(model.evaluate({})-target,axis=1)),.5/65536)
        self.assertEqual(model.operators,operators)
        self.assertEqual(model.evidence['coefficient_quantization'],'absolute_then_exact_relative')

    def test_absolute_nodes_must_match_observed_relative_nodes_exactly(self):
        knots = [np.array([0.,1.])]*3
        absolute = np.zeros((2,2,2,7,2));relative = np.zeros((2,2,2,14))
        for invalid in (absolute+1.,absolute[...,0],np.full_like(absolute,np.nan)):
            with self.assertRaises(ValueError):
                encode(knots,relative,OPS,TAGS,absolute_values=invalid)


if __name__ == '__main__':
    unittest.main()
