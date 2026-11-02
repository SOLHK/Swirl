"""Authored oblique branches and polynomial impossibility witnesses."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'tools'),
             str(Path(__file__).resolve().parents[1]/'platform')]
from hvf_piecewise_axes import line_partition,segment_partition
from hvf_branch_cells import branch_cell
from interpolation_witness import polynomial_witness,flat_cell_degree
from test_hvf_branch_cells import authored_table


class JointBranchTests(unittest.TestCase):
    def test_simultaneous_chord_finds_oblique_child_crossing(self):
        # Child axis = -.25+.5*x+.75*y-.25*z, with all root axes changing.
        table=authored_table();a=np.array([.1,.1,.1]);b=np.array([.7,.5,.3])
        result=segment_partition(table,0,a,b)
        event=next(r for r in result['events'] if r['part']==1
                   and r['kind']=='axis_zero')
        self.assertAlmostEqual(event['parameter'],3/11)
        point=np.asarray(event['coordinates'])
        self.assertAlmostEqual(-.25+point@[.5,.75,-.25],0.)
        cell=branch_cell(table,0,a)
        self.assertTrue(cell.contains([a])[0]);self.assertFalse(cell.contains([b])[0])
        self.assertFalse(result['three_dimensional_acceptance'])

    def test_axis_sweep_legacy_partition_and_reversed_chord_agree(self):
        table=authored_table();a=[-1.,.37,-.13];b=[1.,.37,-.13]
        old=line_partition(table,0,0,a)
        new=segment_partition(table,0,a,b)
        reverse=segment_partition(table,0,b,a)
        np.testing.assert_allclose(sorted((e['coordinate']+1)/2 for e in old['events']),
                                   sorted(e['parameter'] for e in new['events']),atol=1e-15)
        np.testing.assert_allclose(new['parameters'],
                                   sorted(1-x for x in reverse['parameters']),atol=1e-15)

    def test_invalid_segments_are_rejected(self):
        for a,b in (([0,0],[1,1]),([0,0,0],[0,0,0]),
                    ([0,0,0],[0,2,0]),([0,0,0],[0,np.nan,0])):
            with self.assertRaises(ValueError):segment_partition(authored_table(),0,a,b)


class PolynomialWitnessTests(unittest.TestCase):
    def test_every_cubic_annihilated_on_three_axis_chord(self):
        t=np.arange(5)/4
        p=np.stack((7+4*t+2*t*t-8*t**3,2-t+12*t*t+t**3),axis=1)[:,None,:]
        self.assertEqual(polynomial_witness(t,p,3)['lower_bound'],0.)

    def test_hidden_branch_excludes_all_linear_fits(self):
        t=np.array([0.,.5,1.]);p=np.zeros((3,1,2));p[:,0,0]=np.maximum(t-.5,0)
        result=polynomial_witness(t,p,1)
        self.assertEqual(result['lower_bound'],.125)
        self.assertTrue(result['exceeds_limit'])
        # The minimax line t/2-1/8 attains the certified bound at all samples.
        self.assertEqual(np.abs(t/2-.125-p[:,0,0]).max(),result['lower_bound'])

    def test_oblique_clamp_excludes_all_multiaffine_fits(self):
        t=np.arange(5)/4;p=np.zeros((5,2,2));p[:,1,1]=8*np.maximum(t-.5,0)
        result=polynomial_witness(t,p,3)
        self.assertEqual(result['control_index'],1)
        self.assertEqual(result['lower_bound'],.25)
        self.assertTrue(result['exceeds_limit'])

    def test_support_crossing_cannot_be_mislabelled_polynomial(self):
        tags=('WDTH','wght','HGHT');supports=[{}, {'WDTH':(0,.5,1)}]
        self.assertEqual(flat_cell_degree(tags,supports,[.1,.1,.1],[.4,.3,.2]),3)
        self.assertEqual(flat_cell_degree(tags,supports,[.1,.1,.1],[.4,.1,.1]),1)
        with self.assertRaisesRegex(ValueError,'crosses_support_knot'):
            flat_cell_degree(tags,supports,[.1,.1,.1],[.9,.3,.2])

    def test_exact_threshold_and_invalid_observations(self):
        t=np.array([0.,.5,1.]);p=np.zeros((3,1,2));p[1,0,0]=1/16
        self.assertFalse(polynomial_witness(t,p,1)['exceeds_limit'])
        p[1,0,0]=np.nextafter(1/16,1.)
        self.assertTrue(polynomial_witness(t,p,1)['exceeds_limit'])
        for parameters in ([0,0,1],[0,.5,np.nan],[-.1,.5,1]):
            with self.assertRaises(ValueError):polynomial_witness(parameters,p,1)


if __name__=='__main__':unittest.main()
