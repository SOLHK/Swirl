import io,sys,unittest
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.varLib.varStore import VarStoreInstancer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
import probe_feature_conditions as probe
import experiment_vertical_gpos as fixture


class FeatureConditionTests(unittest.TestCase):
    def test_serialized_standard_axis_and_experimental_oblique_selection(self):
        for kind in ('axis_range','coupled_value'):
            data=probe.build(kind)
            for point in probe.POINTS:
                shaped=fixture.shape(data,point,'ltr','zh-cn')
                self.assertEqual(shaped['glyphs'][0]['gid'],7 if probe.selected(point,kind) else 2)
                self.assertEqual([r['gid'] for r in shaped['glyphs'][1:]],[1,6,7])
    def test_coupled_condition_is_decoded_not_replaced_by_axis_box(self):
        font=TTFont(io.BytesIO(probe.build('coupled_value')))
        condition=font['GSUB'].table.FeatureVariations.FeatureVariationRecord[0].ConditionSet.ConditionTable[0]
        self.assertEqual(condition.Format,2)
        for point in probe.POINTS:
            store=VarStoreInstancer(font['GDEF'].table.VarStore,font['fvar'].axes,
                                   dict(zip(('WDTH','wght','HGHT'),point)))
            self.assertEqual(condition.DefaultValue+store[condition.VarIdx],4096*(point[0]+point[2]-.25))
        self.assertFalse(probe.selected((.5,0,-.5),'coupled_value'))
        self.assertTrue(probe.selected((-.5,0,.9),'coupled_value'))


if __name__=='__main__':unittest.main()
