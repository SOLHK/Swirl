import copy,io,sys,tempfile,unittest
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTCollection,TTFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
import cff2_geometry as geometry
from layout_translation import translate_vertical_model
from test_coretext_extract import make_fixture
from make_cff2_fixture import convert
import experiment_origin_outline as experiment
from cff2_side_bearings import install_top_bearings
from fontTools.varLib.varStore import VarStoreInstancer
from fontTools.pens.boundsPen import BoundsPen


class LayoutTranslationTests(unittest.TestCase):
    def test_translation_moves_all_contours_once_and_requires_explicit_route(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.ttc';make_fixture(path)
            with TTCollection(path) as fonts:
                font,models=convert(fonts.fonts[0],0,repeat_contours=2)
            source=models['probe'];before=source.deltas.copy()
            translated=translate_vertical_model(source,(-100.125,24.0625),
                [{'WDTH':(0.,1.,1.),'HGHT':(0.,1.,1.)}], [(-10.25,7.5)])
            rng=np.random.default_rng(28137)
            for q in rng.uniform(-1,1,(64,3)):
                loc=dict(zip(source.axis_tags,q));w=max(q[0],0)*max(q[2],0)
                expected=np.asarray([-100.125-10.25*w,24.0625+7.5*w])
                delta=translated.evaluate(loc)-source.evaluate(loc)
                self.assertLess(float(np.abs(delta-expected).max()),1e-10)
            self.assertTrue(np.array_equal(source.deltas,before))
            models['probe']=translated
            with self.assertRaisesRegex(ValueError,'verified_GSUB_route'):
                geometry.install(font,models)
            candidate=geometry.install(font,models,experimental_layout=True)
            data=io.BytesIO();candidate.save(data);reopened=TTFont(io.BytesIO(data.getvalue()))
            self.assertEqual(reopened['maxp'].numGlyphs,3)
            partial=copy.deepcopy(source);partial.evidence['domain_kind']='one_dimensional_slice'
            with self.assertRaisesRegex(ValueError,'full_domain'):
                translate_vertical_model(partial,(0,0),[],[])
    def test_real_GSUB_vertical_targets_preserve_horizontal_geometry_and_metrics(self):
        before,after,result=experiment.build()
        self.assertEqual(result['checks'],len(experiment.POINTS)*8)
        self.assertLess(result['maximum_control_translation_error'],1e-10)
        a,b=TTFont(io.BytesIO(before)),TTFont(io.BytesIO(after))
        self.assertEqual(a.getGlyphOrder(),b.getGlyphOrder())
        for table in ('GSUB','cmap','HVAR','VVAR','VORG','hmtx','vmtx','fvar'):
            self.assertEqual(a.getTableData(table),b.getTableData(table))

    def test_translated_Y_bearing_matches_VORG_and_keeps_old_variation_maps(self):
        before,after,_=experiment.build(repair_y_bearing=True)
        a,b=TTFont(io.BytesIO(before)),TTFont(io.BytesIO(after))
        old,new=a['VVAR'].table,b['VVAR'].table
        self.assertEqual(old.AdvHeightMap.mapping,new.AdvHeightMap.mapping)
        self.assertEqual(old.VOrgMap.mapping,new.VOrgMap.mapping)
        for p in experiment.POINTS:
            location=dict(zip(('WDTH','wght','HGHT'),p))
            av=VarStoreInstancer(old.VarStore,a['fvar'].axes,location)
            bv=VarStoreInstancer(new.VarStore,b['fvar'].axes,location)
            for name in a.getGlyphOrder():
                for field in ('AdvHeightMap','VOrgMap'):
                    i=getattr(old,field).mapping[name]
                    self.assertEqual(av[i],bv[i])
            gs=b.getGlyphSet(location=location,normalized=True)
            for name in experiment.VERTICAL_NAMES:
                pen=BoundsPen(gs);gs[name].draw(pen)
                tsb=b['vmtx'].metrics[name][1]+bv[new.TsbMap.mapping[name]]
                origin=b['VORG'][name]+bv[new.VOrgMap.mapping[name]]
                self.assertAlmostEqual(pen.bounds[3]+tsb,origin,places=9)
        with self.assertRaisesRegex(ValueError,'existing_TsbMap'):
            install_top_bearings(b,{'han.vert':(0,[],[])})
        with self.assertRaisesRegex(ValueError,'not_int16'):
            install_top_bearings(a,{'han.vert':(.5,[],[])})
        self.assertIsNone(a['VVAR'].table.TsbMap)

    def test_hybrid_scaling_preserves_the_physical_source_before_placement(self):
        original=TTFont(io.BytesIO(experiment.build()[0]))
        before,after,_=experiment.build(hybrid_upm16=True)
        a,b=TTFont(io.BytesIO(before)),TTFont(io.BytesIO(after))
        self.assertEqual(a['head'].unitsPerEm,16000)
        for tag in ('HVAR','VVAR','VORG','hmtx','vmtx','GSUB','cmap'):
            self.assertEqual(a.getTableData(tag),b.getTableData(tag))
        self.assertNotIn('GPOS',a);self.assertIn('GPOS',b)
        for q in ((-1.,-1.,-1.),(0.,0.,0.),(.31,-.27,.43),(1.,1.,1.)):
            loc=dict(zip(('WDTH','wght','HGHT'),q))
            old,new=original.getGlyphSet(location=loc,normalized=True),a.getGlyphSet(location=loc,normalized=True)
            for name in original.getGlyphOrder():
                p,v=geometry.operands(geometry.source_commands(old[name]))
                r,w=geometry.operands(geometry.source_commands(new[name]))
                self.assertEqual(p,r);self.assertLess(float(np.abs(w/16-v).max(initial=0)),1e-9)
                self.assertAlmostEqual(new[name].width/16,old[name].width,places=9)


if __name__=='__main__':unittest.main()
