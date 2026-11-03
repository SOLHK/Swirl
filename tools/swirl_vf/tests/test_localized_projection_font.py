"""Whole-font encoding tests use authored fields, never proprietary glyph data."""
import io
import itertools
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
import numpy as np
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import buildVarStore, buildVarData, buildVarRegionList

sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'tools'),
               str(Path(__file__).resolve().parents[1]/'platform')]
from test_coretext_extract import make_fixture
from probe_polynomial_clamp import source, delta, ops
from joint_polynomial import interpolate, TAGS
from adaptive_projection_atlas import ProjectionAtlas
from sparse_projection import fit
from localized_projection_font import build
from cff2_geometry import source_commands
from probe_joint_representations import compare
from probe_joint_seams import run as verify_seams
from probe_projection_selection import coordinate_font


class ProjectionFontTests(unittest.TestCase):
    def test_serialized_axes_clamp_fields_and_implicit_metric_indices(self):
        boxes = [interpolate(np.c_[lo, np.asarray(lo)+1], ops*2,
                             lambda p: np.c_[source(p), delta(p)])
                 for lo in itertools.product((-1., 0.), repeat=3)]
        atlas = ProjectionAtlas(boxes, dict(max_refinement_error=0.,
            component_holdout=dict(holdouts_disjoint=True, max_envelope_error=0.)), np.empty(0, dtype='V16'))
        parameters = fit(lambda p: (.25+.6*p[:, 0]+.4*p[:, 1]-.3*p[:, 2])[:, None], 1)
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)/'source.ttc'; make_fixture(fixture)
            with TTCollection(fixture) as collection:
                original = collection.fonts[0]
                hvar = newTable('HVAR'); hvar.table = otTables.HVAR(); hvar.table.Version = 0x10000
                hvar.table.VarStore = buildVarStore(buildVarRegionList([{'WDTH': (0, 1, 1)}], TAGS),
                    [buildVarData([0], [[11], [22], [33]], optimize=False)])
                hvar.table.AdvWidthMap = hvar.table.LsbMap = hvar.table.RsbMap = None
                original['HVAR'] = hvar
                result = build(original, 2, atlas, parameters)
                raw = io.BytesIO(); result.save(raw)
            with TTFont(io.BytesIO(raw.getvalue())) as font:
                self.assertEqual([a.axisTag for a in font['fvar'].axes[:3]], list(TAGS))
                self.assertTrue(all(a.flags & 1 for a in font['fvar'].axes[3:]))
                self.assertEqual(font['avar'].majorVersion, 2)
                self.assertEqual(set(font['HVAR'].table.AdvWidthMap.mapping.values()), {2})
                self.assertEqual(font['HVAR'].table.VarStore.VarRegionList.RegionAxisCount, 7)
                for p in np.random.default_rng(441).uniform(-1, 1, (128, 3)):
                    loc = dict(zip(TAGS, p)); loc.update({a.axisTag: 0. for a in font['fvar'].axes[3:]})
                    selected = next(i for i, box in enumerate(boxes)
                                    if np.all((p >= box.bounds[:, 0]) & (p <= box.bounds[:, 1])))
                    # normalized=False maps the real user axes through avar2.
                    profiles = ((1, 500, 1000), (100, 400, 900), (1, 500, 1000))
                    for tag, q, (lo, default, hi) in zip(TAGS, p, profiles):
                        loc[tag] = default+q*(default-lo if q < 0 else hi-default)
                    glyph = font.getGlyphSet(location=loc)[font.getGlyphOrder()[selected+3]]
                    expected = source(p[None])[0]+np.clip(.25+p @ [.6, .4, -.3], 0, 1)*delta(p[None])[0]
                    self.assertTrue(compare((ops, expected), source_commands(glyph))['passed'])
                    self.assertLess(abs(glyph.width-(700+33*max(p[0], 0))), .01)
                self.assertFalse(result._swirl_projection_receipt['production_accepted'])
                # This serializer uses post 3.0: a seam verifier must resolve
                # patch GIDs after reload rather than rely on discarded names.
                candidate = Path(directory)/'candidate.otf'; candidate.write_bytes(raw.getvalue())
                regions = Path(directory)/'regions.npz'
                np.savez(regions, bounds=np.array([box.bounds for box in boxes]))
                seam_report = verify_seams(SimpleNamespace(candidate=candidate, regions=regions,
                    private_output=Path(directory)/'seams', seed=991, count=8, first_patch_gid=3))
                self.assertTrue(seam_report['passed'])
                atlas.evidence['component_holdout']['holdouts_disjoint'] = False
                with self.assertRaisesRegex(ValueError, 'unverified_projection_component_fields'):
                    build(original, 2, atlas, parameters)

    def test_coordinate_diagnostic_exposes_all_three_effective_axes_after_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)/'source.ttc'; make_fixture(fixture)
            with TTCollection(fixture) as collection:
                source, template = collection.fonts[:2]
                result = coordinate_font(source, template)
                raw = io.BytesIO(); result.save(raw)
                with TTFont(io.BytesIO(raw.getvalue())) as saved:
                    for tag in ('fvar', 'avar'):
                        self.assertEqual(source.getTableData(tag), saved.getTableData(tag))
                    # The measured avar2 outputs are F2DOT14 values. On this
                    # actual transport domain the diagnostic is exactly
                    # reversible, with no numerical comparison tolerance.
                    points = np.round(np.random.default_rng(442).uniform(-1, 1, (37, 3))*16384)/16384
                    for p in points:
                        glyph = saved.getGlyphSet(location=dict(zip(TAGS, p)), normalized=True)['probe']
                        commands = source_commands(glyph)
                        q = np.array([commands[0][1], commands[0][2], commands[2][1]])/10000
                        np.testing.assert_array_equal(q, p)


if __name__ == '__main__': unittest.main()
