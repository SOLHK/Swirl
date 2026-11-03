from pathlib import Path
import sys,unittest
from types import SimpleNamespace as S
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from joint_gsub_selection import select_glyph

class Font(dict):
    def getBestCmap(self):return {65:'probe'}
    def getGlyphID(self,name):return {'probe':2,'left':3,'right':4}[name]

class SelectionTests(unittest.TestCase):
    def font(self):
        def region(lo,hi,index):
            return S(ConditionSet=S(ConditionTable=[S(Format=1,AxisIndex=0,FilterRangeMinValue=lo,FilterRangeMaxValue=hi)]),
                     FeatureTableSubstitution=S(SubstitutionRecord=[S(FeatureIndex=0,Feature=S(LookupListIndex=[index]))]))
        table=S(FeatureList=S(FeatureRecord=[S(FeatureTag='rvrn',Feature=S(LookupListIndex=[]))]),
            FeatureVariations=S(FeatureVariationRecord=[region(-1,0,0),region(0,1,1)]),
            LookupList=S(Lookup=[S(LookupType=1,LookupFlag=0,SubTable=[S(mapping={'probe':n})]) for n in ('left','right')]))
        return Font(fvar=S(axes=[S(axisTag='wght')]),GSUB=S(table=table))
    def test_closed_boundary_first_match_and_unquantized_neighbour(self):
        f=self.font()
        self.assertEqual(select_glyph(f,{'wght':0}),3)
        self.assertEqual(select_glyph(f,{'wght':1e-9}),4)
        self.assertEqual(select_glyph(f,{'wght':-1e-9}),3)
    def test_no_gsub_direct_access(self):
        f=self.font();del f['GSUB'];self.assertEqual(select_glyph(f,{}),2)
    def test_unsupported_lookup_is_not_silently_ignored(self):
        f=self.font();f['GSUB'].table.LookupList.Lookup[0].LookupType=6
        with self.assertRaisesRegex(ValueError,'unsupported_joint_gsub_lookup'):select_glyph(f,{'wght':0})

if __name__=='__main__':unittest.main()
