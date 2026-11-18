import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from diagnose_projection_fields import cubic_witness

class WitnessTests(unittest.TestCase):
    def test_all_vector_cubics_annihilate(self):
        x=np.arange(5)/4
        values=np.stack((3*x**3-2*x+7,-5*x*x+x),axis=-1)
        self.assertEqual(float(cubic_witness(values)),0.)
    def test_clamp_witness_bounds_every_cubic_approximation(self):
        x=np.arange(5)/4;v=np.stack((np.maximum(x-.5,0),np.zeros(5)),axis=-1)
        bound=float(cubic_witness(v));self.assertEqual(bound,1/32)
        for degree in range(4):
            p=np.stack((x**degree,np.zeros(5)),axis=-1)
            self.assertGreaterEqual(np.linalg.norm(v-p,axis=-1).max(),bound)

if __name__=='__main__':unittest.main()
