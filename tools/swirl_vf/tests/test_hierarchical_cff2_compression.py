import itertools
from fractions import Fraction
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from local_cff2_geometry import encode
from hierarchical_cff2_compression import compress

TAGS=('WDTH','wght','HGHT')
OPS=(('rmoveto',2),('rrcurveto',6))


class HierarchicalCompressionTests(unittest.TestCase):
    def test_omitted_nonzero_terms_have_uniform_absolute_control_bound(self):
        knots=[np.linspace(-1,1,9)]*3;x,y,z=np.meshgrid(*knots,indexing='ij')
        v=np.zeros((9,9,9,8));v[...,0]=10+30*x+.002*x*x*y*y*z;v[...,1]=20+7*y
        model=encode(knots,v,OPS,TAGS,basis='hierarchical');before=model.deltas.copy()
        model.evidence['sampled_geometry_passed']=True
        reduced=compress(model,max_regions=8,error_budget=1/256)
        proof=reduced.evidence['uniform_model_compression']
        self.assertTrue(proof['within_budget'])
        self.assertLess(len(reduced.supports),len(model.supports))
        self.assertFalse(reduced.evidence['sampled_geometry_passed'])
        self.assertFalse(proof['source_error_certified'])
        points=np.random.default_rng(173773).integers(-127,128,(128,3))/128
        for p in points:
            location=dict(zip(TAGS,p))
            error=np.linalg.norm(model.evaluate(location)-reduced.evaluate(location),axis=1).max()
            self.assertLessEqual(error,proof['max_control_error_bound'])
        np.testing.assert_array_equal(model.deltas,before)

    def test_small_relative_operands_cannot_hide_accumulated_control_failure(self):
        knots=[np.array([0.,.5,1.])]*3;x,y,z=np.meshgrid(*knots,indexing='ij')
        ops=(('rmoveto',2),)+(('rlineto',2),)*63
        v=np.zeros((3,3,3,128));v[...,::2]=x[...,None]/1024;v[...,1::2]=y[...,None]/1024
        model=encode(knots,v,ops,TAGS,basis='hierarchical')
        reduced=compress(model,max_regions=1,error_budget=1/128)
        proof=reduced.evidence['uniform_model_compression']
        self.assertFalse(proof['within_budget'])
        self.assertGreaterEqual(proof['max_control_error_bound'],1/16)
        self.assertFalse(reduced.evidence['sampled_geometry_passed'])

    def test_nonuniform_grid_interval_bound_encloses_exact_rational_vertices(self):
        knots=[np.array([0.,.125,.25,.5,1.]),np.array([-.5,-.375,0.]),np.array([0.,.5,1.])]
        values=np.random.default_rng(62391).integers(-50,51,(5,3,3,8))/65536
        model=encode(knots,values,OPS,TAGS,basis='hierarchical')
        reduced=compress(model,max_regions=4,error_budget=0.)
        removed=[(s,d) for s,d in zip(model.supports,model.deltas) if s not in reduced.supports]
        bound=Fraction(reduced.evidence['uniform_model_compression']['max_control_error_bound'])**2
        def scalar(point,support):
            out=Fraction(1)
            for tag,(lo,peak,hi) in support.items():
                x=Fraction(point[TAGS.index(tag)]);lo,peak,hi=map(Fraction,(lo,peak,hi))
                if x==peak:continue
                if x<=lo or x>=hi:return Fraction(0)
                out*=((x-lo)/(peak-lo) if x<peak else (hi-x)/(hi-peak))
            return out
        for point in itertools.product(*knots):
            operands=[Fraction(0)]*8
            for support,delta in removed:
                weight=scalar(point,support)
                operands=[a+weight*Fraction(float(v)) for a,v in zip(operands,delta)]
            x=y=Fraction(0)
            for i in range(0,8,2):
                x+=operands[i];y+=operands[i+1]
                self.assertLessEqual(x*x+y*y,bound)

    def test_empty_and_nonhierarchical_models_are_not_fabricated(self):
        knots=[np.array([0.,1.])]*3
        empty=encode(knots,np.zeros((2,2,2,0)),(),TAGS,basis='hierarchical')
        reduced=compress(empty)
        self.assertEqual(reduced.evidence['uniform_model_compression']['max_control_error_bound'],0)
        self.assertEqual(reduced.deltas.shape,(1,0))
        with self.assertRaisesRegex(ValueError,'hierarchical_local'):
            compress(encode(knots,np.zeros((2,2,2,8)),OPS,TAGS))
