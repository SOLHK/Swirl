"""Authored cubic tensors and actual serialized nested CFF2 blends."""
import io
from itertools import product
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables._f_v_a_r import Axis

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'tools'),
               str(Path(__file__).resolve().parents[1] / 'platform')]
from joint_polynomial import PolynomialBox, interpolate, TAGS, GRID
import cff2_geometry as geometry
from test_coretext_extract import make_fixture

OPS = (('rmoveto', 2), ('rrcurveto', 6), ('rlineto', 2))


def authored(p):
    x, y, z = p.T
    return np.asarray([100+20*x*x*y, 100+30*y*z*z*z, 10+0*x,
        50+15*x*y*z, 20+0*x, 50+0*x, 60+0*x, 20*x*x*y*y*z*z,
        -85+0*x, -95-20*x*x*y*y*z*z]).T


class JointPolynomialTests(unittest.TestCase):
    def test_serialized_polynomials_and_signed_factors_in_every_octant(self):
        rng = np.random.default_rng(2026110371)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'template.ttc'; make_fixture(path)
            with TTCollection(path) as template:
                font = template.fonts[0]
                axis = Axis(); axis.axisTag = 'H000'; axis.minValue = -1
                axis.defaultValue = 0; axis.maxValue = 1; axis.flags = 1
                axis.axisNameID = font['name'].addName('Authored factor')
                font['fvar'].axes.append(axis)
                font['avar'].segments['H000'] = {-1.: -1., 0.: 0., 1.: 1.}
                tags = TAGS + ('H000',)
                for lo in product((-1, 0), repeat=3):
                    bounds = np.c_[lo, np.asarray(lo)+1]
                    model = interpolate(bounds, OPS, authored)
                    held = model.from_local(rng.uniform(0, 1, (32, 3)))
                    self.assertFalse(any(np.array_equal(a, b) for a in held
                                         for b in model.from_local(GRID)))
                    np.testing.assert_allclose(model.values(held), authored(held), atol=1e-9, rtol=0)
                    model.axis_tags = tags
                    model.factors = {'H000': model.coefficients/8}
                    model.signed_factors = True
                    model.evidence['sampled_geometry_passed'] = True
                    empty = geometry.OutlineModel(tags, (), [{}], np.zeros((1, 0)),
                                                  {'sampled_geometry_passed': True})
                    candidate = geometry.install(font, {'.notdef': empty, 'space': empty, 'probe': model})
                    stream = io.BytesIO(); candidate.save(stream)
                    with TTFont(io.BytesIO(stream.getvalue())) as saved:
                        for p, factor in zip(held, rng.uniform(-1, 1, len(held))):
                            location = dict(zip(TAGS, map(float, p))); location['H000'] = float(factor)
                            commands = geometry.source_commands(saved.getGlyphSet(
                                location=location, normalized=True)['probe'])
                            ops, actual = geometry.operands(commands)
                            self.assertEqual(ops, OPS)
                            expected = authored(p[None, :])[0]*(1+factor/8)
                            np.testing.assert_allclose(geometry.control_points(ops, actual),
                                geometry.control_points(OPS, expected), atol=1e-8, rtol=0)
                    self.assertLess(model.evidence['maximum_operand_stack'], 64)

    def test_bounds_cannot_cross_default_or_move_off_F2DOT14(self):
        for bounds in ([[-1, 1]]*3, [[.00001, 1]]*3, [[0, 0]]*3):
            with self.assertRaisesRegex(ValueError, 'octant_bounds'):
                interpolate(bounds, OPS, authored)

    def test_local_model_does_not_extrapolate_as_an_accepted_global_model(self):
        model = interpolate([[0, 1]]*3, OPS, authored)
        with self.assertRaisesRegex(ValueError, 'outside_declared_box'):
            model.values([[-.01, .5, .5]])
        self.assertFalse(model.evidence['sampled_geometry_passed'])
        self.assertFalse(model.evidence['production_accepted'])

    def test_absolute_quantization_preserves_certified_closed_controls(self):
        ops = (('rmoveto', 2), ('rrcurveto', 6))
        class Closed:
            closed_control_pairs = [(0, 3)]
            def __call__(self, p):
                x, y, z = p.T
                a = 1/7+x*y/11; b = 1/13+y*z/17
                return np.array([a, b, a, b, a, b, -2*a, -2*b]).T
        model = interpolate([[0, 1]]*3, ops, Closed())
        absolute = np.cumsum(model.coefficients.reshape(4, 4, 4, -1, 2), axis=3)
        np.testing.assert_array_equal(absolute[..., 0, :], absolute[..., 3, :])
        for p in np.random.default_rng(7).uniform(0, 1, (32, 3)):
            actual = model.values([p])[0]
            expected = Closed()(p[None, :])[0]
            self.assertLess(np.linalg.norm(geometry.control_points(ops, actual)
                                          - geometry.control_points(ops, expected), axis=1).max(), 1/32)

    def test_rounded_away_trees_are_removed_without_changing_signed_half_ticks(self):
        coefficients = np.full((4, 4, 4, 10), .49/65536)
        coefficients[0, 0, 0] = authored(np.zeros((1, 3)))[0]
        model = PolynomialBox(np.array([[0., 1.]]*3), OPS, coefficients,
                              {'sampled_geometry_passed': True})
        self.assertNotIn('blend', model.charstring(0).program)
        direction = np.zeros_like(coefficients); direction[3, 3, 3, 1] = .5/65536
        model.axis_tags = TAGS+('H000',)
        model.factors, model.signed_factors = {'H000': direction}, True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'template.ttc'; make_fixture(path)
            with TTCollection(path) as collection:
                font = collection.fonts[0]
                axis = Axis(); axis.axisTag = 'H000'; axis.minValue = -1
                axis.defaultValue = 0; axis.maxValue = 1; axis.flags = 1
                axis.axisNameID = font['name'].addName('Signed half tick')
                font['fvar'].axes.append(axis)
                font['avar'].segments['H000'] = {-1.: -1., 0.: 0., 1.: 1.}
                empty = geometry.OutlineModel(model.axis_tags, (), [{}], np.zeros((1, 0)),
                                              {'sampled_geometry_passed': True})
                candidate = geometry.install(font, {'.notdef': empty, 'space': empty, 'probe': model})
                stream = io.BytesIO(); candidate.save(stream)
            with TTFont(io.BytesIO(stream.getvalue())) as saved:
                for hidden in (-1., -.5, 0., .5, 1.):
                    location = dict(WDTH=.75, wght=.5, HGHT=.25, H000=hidden)
                    actual = geometry.operands(geometry.source_commands(saved.getGlyphSet(
                        location=location, normalized=True)['probe']))
                    expected = authored(np.zeros((1, 3)))[0]
                    expected[1] += max(hidden, 0)*(.75*.5*.25)**3/65536
                    np.testing.assert_allclose(actual[1], expected, rtol=0, atol=1e-12)


if __name__ == '__main__':
    unittest.main()
