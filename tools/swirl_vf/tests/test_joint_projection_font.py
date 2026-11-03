"""A complete factored candidate must survive standard shaping and reload."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTCollection, TTFont
sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'tools'),
               str(Path(__file__).resolve().parents[1]/'platform')]
import cff2_geometry as geometry
from joint_cells import refine
from joint_projection_font import build
from joint_polynomial import TAGS
from sparse_projection import fit, encode_clamp_ramps
from test_coretext_extract import make_fixture


class AuthoredFields:
    base_ops = (('rmoveto', 2), ('rrcurveto', 6))
    ops = base_ops*2
    factors = 1
    count = 0
    def __call__(self, p):
        self.count += len(p)
        x, y, z = p.T
        base = np.asarray([100+10*x*x*y, 200+20*y*z, 10+0*x, 20+0*x,
                           10+0*x, -20+0*x, -20+0*x, 0*x]).T
        direction = np.tile([20, 10, 0, 0, 0, 0, 0, 0], (len(p), 1))
        return np.c_[base, direction]
    def errors(self, a, b):
        delta = (a-b).reshape(len(a), 2, -1, 2)
        return np.linalg.norm(np.cumsum(delta, axis=2), axis=3).sum(axis=1).max(axis=1)


class JointProjectionFontTests(unittest.TestCase):
    def test_complete_candidate_uses_native_region_selection_and_copied_metrics(self):
        fields_source = AuthoredFields(); fields = refine(fields_source, max_cells=16)
        parameters = lambda p: (.4+.5*p[:, 0]+.25*p[:, 1]-.25*p[:, 2])[:, None]
        ramps = encode_clamp_ramps(fit(parameters, 4), 4)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'template.ttc'; make_fixture(path)
            with TTCollection(path) as collection:
                original = collection.fonts[0]
                original['avar'].segments = {tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in TAGS}
                font = build(original, original, 2, fields, ramps, fields_source)
                data = io.BytesIO(); font.save(data)
                with TTFont(io.BytesIO(data.getvalue())) as saved:
                    native = hb.Font(hb.Face(data.getvalue())); hb.ot_font_set_funcs(native)
                    self.assertTrue(all(a.flags & 1 for a in saved['fvar'].axes[3:]))
                    for point in np.random.default_rng(71).uniform(-1, 1, (43, 3)):
                        user = {a.axisTag: a.defaultValue+q*(a.defaultValue-a.minValue if q < 0
                                else a.maxValue-a.defaultValue) for a, q in zip(original['fvar'].axes, point)}
                        native.set_variations(user)
                        buffer = hb.Buffer(); buffer.add_str('A'); buffer.guess_segment_properties(); hb.shape(native, buffer)
                        self.assertEqual(len(buffer.glyph_infos), 1)
                        gid = buffer.glyph_infos[0].codepoint
                        self.assertGreaterEqual(gid, 3)
                        glyph = saved.getGlyphSet(location=user)[saved.getGlyphOrder()[gid]]
                        ops, values = geometry.operands(geometry.source_commands(glyph))
                        expected = fields_source(point[None, :]).reshape(2, -1)
                        expected = expected[0]+np.clip(parameters(point[None, :])[0, 0], 0, 1)*expected[1]
                        self.assertEqual(ops, fields_source.base_ops)
                        self.assertLess(np.linalg.norm(geometry.control_points(ops, values)
                            - geometry.control_points(ops, expected), axis=1).max(), geometry.LIMIT)
                        original_width = original.getGlyphSet(location=user)['probe'].width
                        self.assertLess(abs(glyph.width-original_width), geometry.LIMIT)


if __name__ == '__main__':
    unittest.main()
