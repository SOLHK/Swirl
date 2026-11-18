from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from branch_surface_probes import plane_box_contacts,surface_probes
from projection_factorization import ProjectionSource
from test_hvf_branch_cells import authored_table


class SurfaceProbeTests(unittest.TestCase):
    def test_oblique_plane_contacts_all_six_box_edges(self):
        bounds=np.array([[-1.,1.]]*3)
        p=plane_box_contacts([0,1,1,1],bounds)
        self.assertEqual(len(p),6)
        np.testing.assert_array_equal(p.sum(axis=1),0.)
        self.assertTrue(np.all(np.sum(np.abs(p)==1,axis=1)==2))
        self.assertEqual(len(plane_box_contacts([4,1,1,1],bounds)),0)
    def test_real_authored_branch_planes_need_no_holdout_input(self):
        source=ProjectionSource(authored_table(),0);bounds=np.array([[0.,1.]]*3)
        p=surface_probes(source,bounds)
        self.assertTrue(len(p)>0)
        self.assertTrue(np.all((p>=0)&(p<=1)))
        # The authored nested-axis plane has edge contacts away from the
        # old centre chords; no empirical failure location defines them.
        self.assertTrue(np.any(np.all(np.isclose(p,[.5,0.,0.],atol=1e-14),axis=1)))


if __name__=='__main__':unittest.main()
