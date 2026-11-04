from pathlib import Path
import sys,tempfile,unittest
from fontTools.ttLib import TTCollection
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'platform'),str(Path(__file__).resolve().parents[1]/'tools')]
from test_coretext_extract import make_fixture
from probe_polynomial_clamp import build_control
from cff2_structural_pool import compress
from probe_joint_subset import run


class JointSubsettingTests(unittest.TestCase):
    def test_actual_subset_keeps_patch_closure_and_mutable_instance_geometry(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);make_fixture(root/'authored.ttc')
            with TTCollection(root/'authored.ttc') as c:font,_=build_control(c.fonts[0],share_expressions=True)
            compress(font);font.save(root/'control.otf')
            r=run(root/'control.otf',root/'subset',samples=71,seed=918)
            self.assertTrue(r['passed'])
            self.assertEqual(r['subset_glyphs'],10)
            self.assertEqual(r['HarfBuzz']['observations'],71)
            self.assertEqual(r['HarfBuzz']['exact_outline_mismatches'],0)
            self.assertFalse(r['original_source_accuracy'])


if __name__=='__main__':unittest.main()
