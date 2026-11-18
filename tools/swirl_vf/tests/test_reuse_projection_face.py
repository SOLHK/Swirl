import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from reuse_projection_face import equal_geometry_tables


class Face(dict):
    def __init__(self,raw=b'authored geometry',tags=('WDTH','wght','HGHT'),pm=True):
        super().__init__(fvar=SimpleNamespace(axes=[SimpleNamespace(axisTag=t) for t in tags]),hvgl=True)
        self.reader={'hvgl':raw}
        if pm:self['hvpm']=True;self.reader['hvpm']=b'authored points'


class FaceReuseTests(unittest.TestCase):
    def test_only_exact_geometry_and_axis_order_authorize_model_reuse(self):
        a=Face();b=Face();b['hmtx']='independent metrics';b['avar']='independent mapping'
        self.assertEqual(set(equal_geometry_tables(a,b)),{'hvgl','hvpm'})
        for other in (Face(raw=b'different'),Face(tags=('wght','WDTH','HGHT')),Face(pm=False)):
            with self.assertRaises(ValueError):equal_geometry_tables(a,other)


if __name__=='__main__':unittest.main()
