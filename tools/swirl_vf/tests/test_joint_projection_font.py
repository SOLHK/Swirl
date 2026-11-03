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
    def test_direct_shared_HOI_build_preserves_physical_fields_and_metric_axes(self):
        class CurvedDirections(AuthoredFields):
            def __call__(self, p):
                values = super().__call__(p)
                x, y, z = p.T
                values[:, 8] += 5*x*x*y+3*y*y*z*z
                values[:, 9] += 2*x*x*x*z
                return values
        source = CurvedDirections(); cells = refine(source, max_cells=16)
        parameters = lambda p: (.4+.5*p[:, 0]+.25*p[:, 1]-.25*p[:, 2])[:, None]
        ramps = encode_clamp_ramps(fit(parameters, 4), 4)
        from p7_validate_candidate import commands
        from probe_joint_representations import compare
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'fixture.ttc'; make_fixture(path)
            with TTCollection(path) as collection:
                original = collection.fonts[0]
                original['avar'].segments = {tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in TAGS}
                candidate = build(original, original, 2, cells, ramps, source, encoding='hoi', share_expressions=True)
                stream = io.BytesIO(); candidate.save(stream)
                self.assertGreater(candidate.joint_encoding_evidence['expression_pool']['shared_expressions'], 0)
                with TTFont(io.BytesIO(stream.getvalue())) as saved:
                    native = hb.Font(hb.Face(stream.getvalue())); hb.ot_font_set_funcs(native)
                    native.scale = (saved['head'].unitsPerEm*64,)*2
                    for p in np.random.default_rng(2026110449).uniform(-1, 1, (43, 3)):
                        user = {a.axisTag: a.defaultValue+float(q)*(a.defaultValue-a.minValue if q < 0
                                else a.maxValue-a.defaultValue) for a, q in zip(original['fvar'].axes, p)}
                        native.set_variations(user)
                        buffer = hb.Buffer(); buffer.add_str('A'); buffer.guess_segment_properties(); hb.shape(native, buffer)
                        gid = buffer.glyph_infos[0].codepoint
                        self.assertGreaterEqual(gid, 3)
                        fields = source(p[None]).reshape(2, -1)
                        expected = fields[0]+np.clip(parameters(p[None])[0, 0], 0, 1)*fields[1]
                        self.assertTrue(compare((source.base_ops, expected), commands(native, gid))['passed'])
                        glyph = saved.getGlyphSet(location=user)[saved.getGlyphOrder()[gid]]
                        self.assertLess(abs(glyph.width-original.getGlyphSet(location=user)['probe'].width), geometry.LIMIT)

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
