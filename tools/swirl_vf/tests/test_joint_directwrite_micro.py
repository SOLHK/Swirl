import contextlib,io,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from probe_joint_directwrite import run
from fontTools.ttLib import TTFont
class MicroControlTests(unittest.TestCase):
    def test_serialized_one_region_controls_and_nested_operands(self):
        with tempfile.TemporaryDirectory()as d,contextlib.redirect_stdout(io.StringIO()):
            for name in ('micro_linear_requested','micro_nested_base_requested','micro_nested_delta_requested'):
                out=Path(d)/name;r=run(out,variant=name)
                self.assertEqual(r['HarfBuzz']['observations'],762);self.assertEqual(r['HarfBuzz']['failures'],0)
                self.assertLessEqual(r['HarfBuzz']['max_error'],1/32);self.assertEqual(r['DirectWrite'],'NOT_RUN')
                with TTFont(out/'control.otf')as f:
                    self.assertEqual(f['avar'].majorVersion,1);self.assertEqual(len(f['CFF2'].cff.GlobalSubrs),0)
                    self.assertEqual(len(f['CFF2'].cff.topDictIndex[0].VarStore.otVarStore.VarRegionList.Region),1)
if __name__=='__main__':unittest.main()
