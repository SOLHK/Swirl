import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from hvf import HVGL
from hvf_piecewise_axes import LinearPieces,projection_roots,line_partition
from test_hvf import table,shape,composite

class PiecewiseAxisTests(unittest.TestCase):
    def test_nested_extrema_retain_internal_axis_zero(self):
        font=HVGL(table([composite(master=-.25,positive=.5),shape()],visible=1))
        result=line_partition(font,0,0,[0.])
        self.assertIn(.5,result['knots'])
        self.assertTrue(any(r['kind']=='axis_zero' and r['part']==1 and r['coordinate']==.5 for r in result['events']))
    def test_positive_part_preserves_flat_and_negative_pieces(self):
        a=LinearPieces(np.asarray([-1.,0.,1.]),np.asarray([-1.,.3,-1.]))
        b=a.positive();x=np.random.default_rng(834).uniform(-1,1,500)
        np.testing.assert_allclose(b.at(x),np.maximum(a.at(x),0),atol=1e-15)
        self.assertEqual(len(b.knots),5)
    def test_two_projection_crossings_inside_one_interval_are_not_missed(self):
        # N(t)=.16-t+t*t, endpoints have the same sign. Endpoint-only branch
        # scanning misses both contacts, while the quadratic equation finds both.
        roots=projection_roots(([[0,0],[0,0]],[[1,0],[1,1]],[[.16,0],[-.84,1]]))
        values=sorted(t for side,t in roots if side=='lower')
        np.testing.assert_allclose(values,[.2,.8],atol=1e-14)
    def test_constant_contact_does_not_add_every_coordinate(self):
        self.assertEqual(projection_roots(([[0,0],[0,0]],[[1,0],[2,0]],[[0,0],[0,0]])),[])
    def test_curve_parameter_clamp_keeps_authored_topology(self):
        font=HVGL(table([shape(blends=(0,1,1),parallel=True)]))
        result=line_partition(font,0,0,[0.])
        self.assertEqual(result['node_count'],1)
        self.assertFalse(result['three_dimensional_acceptance'])

if __name__=='__main__':unittest.main()
