import io,itertools,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTCollection,TTFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from piecewise_geometry import find_transitions,fit_slice,point_errors
from hvf_branch_geometry import regimes
from batch_geometry import BatchGeometry
from hvf import HVGL
from test_hvf import table,shape,composite
import cff2_geometry as geometry
from test_coretext_extract import make_fixture
from make_cff2_fixture import convert
from cff2_metrics import prepare_from_truetype

TAGS=('WDTH','wght','HGHT')
OPS=(('rmoveto',2),('rrcurveto',6),('rlineto',2))
# Rational tangent projection with off-grid moving contact, plus smooth curvature.
def fixture(xs):
    x=np.asarray(xs);t=np.clip((x-.16436)/(1+x*x*.2),0,1)
    return np.stack((30+x,20+x*x,100+x,10+t*113,30+x*x,20+x,40+x,30-x,10-x,20+x*x),axis=1)

class PiecewiseTests(unittest.TestCase):
    def model(self,**kw):
        return fit_slice(fixture,OPS,TAGS,'wght',{'WDTH':-.73,'HGHT':.27},
            np.random.default_rng(821).uniform(-1,1,300),transitions=[.16436],**kw)
    def test_independent_rational_contact_holdouts_and_no_nested_blends(self):
        model=self.model()
        self.assertTrue(model.evidence['sampled_geometry_passed'])
        self.assertLessEqual(model.evidence['max_holdout_error'],1/32)
        self.assertFalse(model.evidence['three_dimensional_acceptance'])
        model.charstring(0).compile(isCFF2=True)
        self.assertLess(len(model.supports),507)
    def test_capacity_failure_remains_visible(self):
        model=self.model(max_knots=5)
        self.assertFalse(model.evidence['sampled_geometry_passed'])
        self.assertTrue(model.evidence['failures'])
    def test_holdout_cannot_be_a_probe(self):
        with self.assertRaisesRegex(ValueError,'holdout_used'):
            fit_slice(fixture,OPS,TAGS,'wght',{'WDTH':0,'HGHT':0},[0.])
    def test_trace_does_not_modify_actual_geometry_and_detaches_axes(self):
        f=HVGL(table([composite(),shape()],visible=1));r=BatchGeometry(f)
        a=r.render(0,[[-.5],[.3]]);b=r.render(0,[[-.5],[.3]],capture_trace=True)
        for left,right in zip(a.paths,b.paths):np.testing.assert_array_equal(left,right)
        keys,raw,state=regimes(f,b)
        self.assertEqual(state.shape,(2,len(keys)));self.assertEqual(raw.shape,state.shape)
        b.trace[0].axes[:]=99
        np.testing.assert_array_equal(r.render(0,[[-.5],[.3]]).paths[0],a.paths[0])
    def test_branch_bisection_keeps_field_identity(self):
        rows=find_transitions(lambda xs:np.stack([np.sign(np.asarray(xs)+.038461538),
            (np.asarray(xs)>.16436).astype(int)],axis=1).astype(int))
        self.assertEqual({r['field'] for r in rows},{0,1})
        for r in rows:self.assertLess(r['high']-r['low'],1e-10)
    def test_slice_requires_explicit_opt_in_and_roundtrips_every_point(self):
        model=self.model()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'template.ttc';make_fixture(p)
            with TTCollection(p) as c:
                font=c.fonts[0];_,models=convert(font)
                models[font.getGlyphOrder()[2]]=model
                with self.assertRaisesRegex(ValueError,'slice_model'):
                    geometry.install(prepare_from_truetype(font),models)
                f=geometry.install(prepare_from_truetype(font),models,experimental_slice=True)
                b=io.BytesIO();f.save(b);f=TTFont(io.BytesIO(b.getvalue()))
                for x in np.random.default_rng(932).uniform(-1,1,90):
                    glyph=f.getGlyphSet(location={'wght':float(x)},normalized=True)[f.getGlyphOrder()[2]]
                    ops,values=geometry.operands(geometry.source_commands(glyph))
                    np.testing.assert_allclose(geometry.control_points(ops,values),model.evaluate({'wght':x}),atol=1e-8)
    def test_absolute_control_error_accounts_for_accumulation(self):
        self.assertEqual(point_errors([[.02,0,.02,0]],[[0,0,0,0]])[0],.04)

if __name__=='__main__':unittest.main()
