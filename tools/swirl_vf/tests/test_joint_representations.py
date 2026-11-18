"""Serialized authored coordinate composition; no original-font acceptance."""
import io
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTCollection,TTFont

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from probe_joint_representations import controls,request_plan,expected,compare,geometry,implicit_closures
from test_coretext_extract import make_fixture


class JointRepresentationTests(unittest.TestCase):
    def test_explicit_closing_edge_is_exact_and_nearby_edge_is_not_removed(self):
        commands=[['moveTo',1,2],['lineTo',3,4],['lineTo',1,2],['closePath']]
        self.assertEqual(implicit_closures(commands),commands[:2]+[commands[-1]])
        commands[-2][1]+=1/65536
        self.assertEqual(implicit_closures(commands),commands)
        commands[-2]=['curveTo',2,3,3,4,1,2]
        self.assertEqual(implicit_closures(commands),commands)

    def test_roundtrip_both_models_at_all_independent_joint_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.ttc';make_fixture(path)
            with TTCollection(path) as source:
                for kind,font in controls(source.fonts[0]).items():
                    stream=io.BytesIO();font.save(stream)
                    with TTFont(io.BytesIO(stream.getvalue())) as saved:
                        self.assertEqual(tuple(a.axisTag for a in saved['fvar'].axes),('WDTH','wght','HGHT'))
                        gid=2 if kind=='avar2' else 0
                        for location in request_plan():
                            commands=geometry.source_commands(saved.getGlyphSet(location=location)[saved.getGlyphOrder()[gid]])
                            verdict=compare(expected(source.fonts[0],kind,location),commands)
                            self.assertTrue(verdict['passed'],(kind,location,verdict))

    def test_missing_varc_cannot_pass_on_fallback_cff2_outlines(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.ttc';make_fixture(path)
            with TTCollection(path) as source:
                font=controls(source.fonts[0])['VARC'];del font['VARC']
                for location in request_plan()[:7]:
                    commands=geometry.source_commands(font.getGlyphSet(location=location)[font.getGlyphOrder()[0]])
                    self.assertEqual(compare(expected(source.fonts[0],'VARC',location),commands),
                                     dict(passed=False,error=None,reason='topology_mismatch'))

    def test_fixtures_do_not_mutate_source_and_reject_other_fonts(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.ttc';make_fixture(path)
            with TTCollection(path) as source:
                f=source.fonts[0];before=io.BytesIO();f.save(before)
                controls(f);after=io.BytesIO();f.save(after)
                self.assertEqual(before.getvalue(),after.getvalue())
                f['head'].unitsPerEm=2048
                with self.assertRaisesRegex(ValueError,'authored_three_glyph'):
                    controls(f)


if __name__=='__main__':unittest.main()
