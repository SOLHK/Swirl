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


if __name__=='__main__':unittest.main()
