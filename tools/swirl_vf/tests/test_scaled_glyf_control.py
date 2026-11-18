import contextlib,io,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from fontTools.ttLib import TTFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from probe_scaled_glyf import run
class ScaledGlyfTests(unittest.TestCase):
    def test_serialized_standard_component_preserves_authored_three_axis_function(self):
        with tempfile.TemporaryDirectory()as d,contextlib.redirect_stdout(io.StringIO()):
            p=Path(d)/'control';r=run(SimpleNamespace(output=p,coretext=False,binary=None))
            self.assertTrue(r['sampled_control_passed']);self.assertEqual(r['source_glyphs_accepted'],0)
            self.assertEqual(r['DirectWrite'],'NOT_RUN');self.assertNotIn('CoreText',r['engines'])
            for e in r['engines'].values():self.assertEqual(e['observations'],283);self.assertEqual(e['failures'],0)
            with TTFont(p/'control.ttf')as f:
                self.assertEqual(len(f['fvar'].axes),3);self.assertNotIn('GSUB',f);self.assertNotIn('CFF2',f)
                self.assertEqual(f['glyf']['probe'].components[0].flags&4,0)
                self.assertEqual(len(f['gvar'].variations['detail']),22)
if __name__=='__main__':unittest.main()
