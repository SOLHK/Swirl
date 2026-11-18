"""Non-Windows execution cannot imply DirectWrite success."""
from pathlib import Path
import sys,tempfile,unittest
from fontTools.ttLib import TTFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from probe_joint_directwrite import run


class DirectWriteControlTests(unittest.TestCase):
    def test_authored_hidden_default_control_and_valid_axis_names(self):
        with tempfile.TemporaryDirectory() as root:
            output=Path(root)/'authored';report=run(output)
            self.assertEqual(report['DirectWrite'],'NOT_RUN')
            self.assertEqual(report['HarfBuzz']['observations'],762)
            self.assertEqual(report['HarfBuzz']['failures'],0)
            with TTFont(output/'control.otf') as font:
                for axis in font['fvar'].axes:
                    self.assertIsNotNone(font['name'].getDebugName(axis.axisNameID))
            self.assertFalse(report['original_font_acceptance'])


if __name__=='__main__':unittest.main()
