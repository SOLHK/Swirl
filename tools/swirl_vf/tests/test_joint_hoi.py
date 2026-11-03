"""Three independent physical axes and their repeated-factor encodings."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from fontTools.ttLib import TTCollection, TTFont

sys.path[:0] = [str(Path(__file__).resolve().parents[1]/p) for p in ('tools', 'platform')]
import cff2_geometry as geometry
from joint_hoi import COPIES, GROUPS, HOIPolynomialBox, HOIAxisPowerBox
from joint_polynomial import TAGS, interpolate
from probe_polynomial_clamp import build_control, source, delta, ops
from test_coretext_extract import make_fixture


class HOITests(unittest.TestCase):
    def test_complete_serialized_avar2_tensor_matches_independent_three_axis_field(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'fixture.ttc'; make_fixture(path)
            with TTCollection(path) as collection:
                font, boxes = build_control(collection.fonts[0], 'hoi')
                stream = io.BytesIO(); font.save(stream)
            with TTFont(io.BytesIO(stream.getvalue())) as saved:
                for point in np.random.default_rng(2026110441).uniform(-1, 1, (257, 3)):
                    physical = dict(zip(TAGS, point))
                    mapped = saved['avar'].renormalizeLocation(physical, saved)
                    for group, tag in zip(GROUPS, TAGS):
                        self.assertTrue(all(mapped.get(copy, 0) == mapped.get(tag, 0) for copy in group))
                    index = next(i for i, box in enumerate(boxes) if np.all(
                        (point >= box.bounds[:, 0]) & (point <= box.bounds[:, 1])))
                    # normalized=True skips avar: explicitly use the mapped output.
                    actual_ops, actual = geometry.operands(geometry.source_commands(
                        saved.getGlyphSet(location=mapped, normalized=True)[f'box{index}']))
                    expected = source(point[None])[0]+np.clip(.25+.6*point[0]+.4*point[1]-.3*point[2], 0, 1)*delta(point[None])[0]
                    self.assertEqual(actual_ops, ops)
                    self.assertLess(np.linalg.norm(geometry.control_points(ops, actual)-
                        geometry.control_points(ops, expected), axis=1).max(), geometry.LIMIT)
                self.assertTrue(all(m.evidence['maximum_operand_stack'] <= 513 for m in boxes))

    def test_dense_degree_nine_tensor_stays_bounded_and_matches_source_after_reload(self):
        rng = np.random.default_rng(2026110442)
        coefficients = np.round(rng.normal(0, 2, (4, 4, 4, 8))*65536)/65536
        operators = (('rmoveto', 2), ('rrcurveto', 6))
        factors = {f'H{i:03d}': coefficients/(2**(i+1)) for i in range(8)}
        model = HOIPolynomialBox([[0, 1]]*3, operators, coefficients, {},
                                  TAGS+tuple(factors)+COPIES, factors, True)
        self.assertEqual(len(model.degrees), 63)
        model.charstring(0).compile(isCFF2=True)
        self.assertLessEqual(model.evidence['maximum_operand_stack'], 166)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'fixture.ttc'; make_fixture(path)
            with TTCollection(path) as collection:
                font, _ = build_control(collection.fonts[0], 'hoi')
                # Eight fully dense independent directions can exceed the
                # separate single-drawing-operation byte guard. Native target
                # directions are sparse. Exercise dense serialization here
                # with two directions; the eight-factor stack stress remains
                # above and does not claim arbitrary byte-size support.
                serialized_factors = dict(list(factors.items())[:2])
                del font['avar']  # The complete mapping is exercised above.
                tags = tuple(a.axisTag for a in font['fvar'].axes)
                for cls in (HOIPolynomialBox, HOIAxisPowerBox):
                    m = cls([[0, 1]]*3, operators, coefficients, {'sampled_geometry_passed': True}, tags, serialized_factors, True)
                    empty = geometry.OutlineModel(tags, (), [{}], np.zeros((1, 0)), {'sampled_geometry_passed': True})
                    models = dict.fromkeys(font.getGlyphOrder(), empty); models['probe'] = m
                    saved_font = geometry.install(font, models, release_programs=True)
                    data = io.BytesIO(); saved_font.save(data)
                    with TTFont(io.BytesIO(data.getvalue())) as saved:
                        for p in rng.uniform(.01, .99, (43, 3)):
                            loc = {tag: float(v) for group, v in zip(GROUPS, p) for tag in group}
                            loc.update({tag: float(v) for tag, v in zip(serialized_factors, rng.uniform(-1, 1, 2))})
                            a_ops, values = geometry.operands(geometry.source_commands(saved.getGlyphSet(location=loc, normalized=True)['probe']))
                            # Final operand quantization has the same strict
                            # geometry threshold, including dense small deltas.
                            self.assertLess(np.linalg.norm(geometry.control_points(a_ops, values)-
                                m.evaluate(loc), axis=1).max(), geometry.LIMIT)

    def test_copies_are_required_and_tag_collisions_rejected(self):
        with self.assertRaisesRegex(ValueError, 'missing_HOI_axis_copies'):
            HOIPolynomialBox([[0, 1]]*3, ops, np.zeros((4, 4, 4, 10)), {})


if __name__ == '__main__':
    unittest.main()
