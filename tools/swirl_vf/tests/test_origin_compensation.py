import io,sys,unittest
from fractions import Fraction
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.varLib.varStore import VarStoreInstancer
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from vertical_metrics import Metrics,placement_correction,origin_coefficients,raw_origin_feasibility
from origin_gpos import append_origin_compensation
import experiment_vertical_gpos as fixture

class OriginTests(unittest.TestCase):
    def test_independent_origin_does_not_become_a_phantom_coordinate(self):
        source=Metrics(800,850,(0,0),(500,760));target=Metrics(800,850,(0,0),(400,760))
        self.assertEqual(source.phantom_points(),((0,0),(800,0),(0,760),(0,-90)))
        self.assertEqual(placement_correction(source,target),(-100,0))
        self.assertFalse(raw_origin_feasibility(source)['necessary_condition_satisfied'])
        self.assertFalse(raw_origin_feasibility(source)['layout_or_visual_impossibility_asserted'])
        self.assertEqual(source.bearings((30,-5,700,700)),dict(lsb=30,rsb=100,tsb=60,bsb=85))
    def test_same_frame_translation_cancels_and_y_sign_is_explicit(self):
        a=Metrics(800,850,(7,3),(507,763));b=Metrics(800,850,(7,3),(407,783))
        self.assertEqual(placement_correction(a,b),(-100,20))
        self.assertEqual(a.independent_origin_x_gap,100)
    def test_half_fraction_is_rejected_not_rounded(self):
        with self.assertRaisesRegex(ValueError,'fractional_GPOS'):
            origin_coefficients((0,0),(0,0),[(Fraction(1,2),0)],[(0,0)])
        self.assertEqual(origin_coefficients((400,760),(500,760),[(20,3)],[(1,2)]),((-100,0),[(19,1)]))
    def fixture(self):
        data,symbols=fixture.original_fixture();return TTFont(io.BytesIO(data)),symbols
    def test_appends_without_losing_existing_lookups_or_store(self):
        source,symbols=self.fixture()
        # An existing variable placement and unrelated feature must survive the
        # new feature's alphabetic insertion and appended GDEF rows.
        data,_=fixture.add_adjustment(fixture.serialize(source),symbols,'vert')
        source=TTFont(io.BytesIO(data));before=source['GDEF'].table.VarStore
        axes=source['fvar'].axes;q={a.axisTag:.25 for a in axes}
        old=[VarStoreInstancer(before,axes,q)[i] for i in range(len(symbols))]
        glyph=source.getGlyphOrder()[2]
        corrections={glyph:((-100,7),[{'wght':(0,1,1)}],[(20,-4)])}
        changed=append_origin_compensation(source,corrections,feature='vkrn')
        result=TTFont(io.BytesIO(fixture.serialize(changed)))
        for tag in fixture.PROTECTED:self.assertEqual(source.getTableData(tag),result.getTableData(tag))
        after=VarStoreInstancer(result['GDEF'].table.VarStore,axes,q)
        self.assertEqual([after[i] for i in range(len(symbols))],old)
        records=result['GPOS'].table.FeatureList.FeatureRecord
        self.assertEqual([r.FeatureTag for r in records],['vert','vkrn'])
        self.assertEqual(records[0].Feature.LookupListIndex,[0])
        sub=result['GPOS'].table.LookupList.Lookup[1].SubTable[0];v=sub.Value
        self.assertEqual(v.XPlacement+after[(v.XPlaDevice.StartSize<<16)|v.XPlaDevice.EndSize],-95)
        self.assertEqual(v.YPlacement+after[(v.YPlaDevice.StartSize<<16)|v.YPlaDevice.EndSize],6)
        self.assertEqual(len(source['GPOS'].table.LookupList.Lookup),1)
    def test_harfbuzz_origin_shift_preserves_raw_metrics_and_advances(self):
        source,symbols=self.fixture();raw=fixture.serialize(source)
        changed=append_origin_compensation(source,{s.name:((-100,0),[],[]) for s in symbols})
        data=fixture.serialize(changed)
        for p in ((0,0,0),(-1,1,-1),(.201171875,.2475,.42225)):
            for direction in ('ltr','ttb'):
                before=fixture.shape(raw,p,direction,'zh-cn');after=fixture.shape(data,p,direction,'zh-cn')
                for a,b in zip(after['glyphs'],before['glyphs']):
                    for field in ('gid','cluster','x_advance','y_advance','metric_width','metric_height','metric_vertical_origin'):
                        self.assertEqual(a[field],b[field])
                    self.assertEqual(a['x_offset']-b['x_offset'],-100 if direction=='ttb' else 0)
    def test_duplicate_feature_and_fractional_delta_fail_transactionally(self):
        font,symbols=self.fixture();name=symbols[2].name
        with self.assertRaisesRegex(ValueError,'exact_integer'):
            append_origin_compensation(font,{name:((0,0),[{'wght':(0,1,1)}],[(.5,0)])})
        self.assertNotIn('GPOS',font)
        changed=append_origin_compensation(font,{name:((-100,0),[],[])})
        with self.assertRaisesRegex(ValueError,'already_present'):
            append_origin_compensation(changed,{name:((-100,0),[],[])})

if __name__=='__main__':unittest.main()
