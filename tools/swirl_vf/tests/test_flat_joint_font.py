from pathlib import Path
import sys,unittest,tempfile
from itertools import product
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from flat_joint_font import collapse,bernstein_control_bound,build
from adaptive_projection_atlas import fit,validate
from test_adaptive_projection_atlas import PolynomialSource


class FlatJointTests(unittest.TestCase):
    def test_serialized_direct_gid_and_native_shaping_use_same_flat_field(self):
        from fontTools.ttLib import TTCollection,TTFont
        import uharfbuzz as hb
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
        from test_coretext_extract import make_fixture
        from sparse_projection import SparseParameters
        from p7_validate_candidate import commands
        from cff2_geometry import operands,control_points
        class Rectangle(PolynomialSource):
            ops=base_ops=(('rmoveto',2),)+(('rlineto',2),)*4
            width=10
            def __call__(self,p):
                x,y,z=np.asarray(p).T;o=np.zeros(len(p))
                return np.asarray([100+x,100+y,100+z,o,o,100+x,-100-z,o,o,-100-x]).T
        source=Rectangle();atlas=fit(source,max_boxes=8,use_source_branches=False)
        atlas.evidence['component_holdout']=validate(atlas,source,np.random.default_rng(553).uniform(-1,1,(129,3)))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);make_fixture(root/'fixture.ttc')
            with TTCollection(root/'fixture.ttc') as c:
                f=build(c.fonts[0],2,atlas,SparseParameters(np.zeros((1,3,3)),np.zeros((1,0)),1))
            f.save(root/'flat.otf')
            with TTFont(root/'flat.otf') as f:
                self.assertNotIn('GSUB',f);self.assertEqual(len(f.getGlyphOrder()),3)
                axes=f['fvar'].axes
            native=hb.Font(hb.Face((root/'flat.otf').read_bytes()));hb.ot_font_set_funcs(native);native.scale=(64000,64000)
            for p in np.random.default_rng(554).uniform(-1,1,(71,3)):
                loc={a.axisTag:a.defaultValue+x*(a.defaultValue-a.minValue if x<0 else a.maxValue-a.defaultValue) for a,x in zip(axes,p)}
                native.set_variations(loc);buf=hb.Buffer();buf.add_str('A');buf.guess_segment_properties();hb.shape(native,buf)
                self.assertEqual(buf.glyph_infos[0].codepoint,2)
                actual=control_points(*operands(commands(native,2)))
                expected=control_points(source.ops,source(p[None])[0])
                self.assertEqual(actual.shape,expected.shape)
                np.testing.assert_allclose(actual,expected,atol=1/32,rtol=0)

    def test_global_multilinear_field_preserves_every_octant_and_mixed_axis(self):
        class Linear(PolynomialSource):
            def __call__(self,p):
                x,y,z=np.asarray(p).T
                return np.asarray([10+2*x+3*y*z,20+x*y*z,30-4*y,40+z]).T
        source=Linear();atlas=fit(source,max_boxes=8,use_source_branches=False);model=collapse(atlas)
        self.assertLess(model.evidence['representation_change_control_bound'],1e-10)
        for p in np.random.default_rng(551).uniform(-1,1,(113,3)):
            actual=model.evaluate(dict(zip(model.axis_tags,p)))
            expected=np.cumsum(source(p[None]).reshape(-1,2),axis=0)
            np.testing.assert_allclose(actual,expected,atol=1e-12,rtol=0)
    def test_cubic_deviation_is_rejected_without_relaxing_budget(self):
        atlas=fit(PolynomialSource(),max_boxes=8,use_source_branches=False)
        with self.assertRaisesRegex(ValueError,'representation_bound_exceeded'):collapse(atlas)
    def test_interval_bound_covers_dense_independent_polynomial_controls(self):
        rng=np.random.default_rng(552);a=rng.normal(size=(4,4,4,12))
        bound=bernstein_control_bound(a)
        p=rng.uniform(0,1,(2000,3));v=[p[:,i,None]**np.arange(4) for i in range(3)]
        controls=np.cumsum(np.einsum('ni,nj,nk,ijkp->np',*v,a).reshape(len(p),-1,2),axis=1)
        self.assertGreaterEqual(bound,np.linalg.norm(controls,axis=2).max())
        self.assertGreaterEqual(bernstein_control_bound(np.zeros_like(a)),0.)


if __name__=='__main__':unittest.main()
