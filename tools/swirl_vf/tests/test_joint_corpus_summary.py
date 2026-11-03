import sys,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from summarize_joint_corpus import summarize,metrics,native_pass,FAILURES
class SummaryTests(unittest.TestCase):
    def test_failures_and_missing_cases_stay_in_denominator(self):
        s={'source_sha256':'authored','seed':77,'selection':[{'face':0,'gid':i,'reasons':[]}for i in (1,2)]}
        r={'identity':{'source_sha256':'authored','face_index':0,'glyph_id':1},'stage_passed':False,'coordinates':['PRIVATE']}
        result=summarize(s,[r]);self.assertEqual(result['selected_cases'],2);self.assertEqual(result['passed_cases'],0)
        self.assertEqual(result['cases'][0]['status'],'FAIL_FIELDS');self.assertEqual(result['cases'][1]['status'],'NOT_RUN')
        self.assertNotIn('PRIVATE',json.dumps(result))
    def test_claimed_pass_with_empty_or_failed_engine_is_rejected(self):
        r={'strict_independent_native_passed':True,'limit':1/32,'independence':{'proven':True},
           'engines':{e:dict(observations=10,independent_observations=10,max_error=.01,**dict.fromkeys(FAILURES,0))for e in ('CoreText','HarfBuzz')}}
        self.assertTrue(native_pass(r));r['engines']['CoreText']['observations']=0;self.assertFalse(native_pass(r))
        r['engines']['CoreText']['observations']=10;r['engines']['HarfBuzz']['advance_failures']=1;self.assertFalse(native_pass(r))
    def test_unlisted_case_rejected(self):
        s={'source_sha256':'authored','seed':77,'selection':[]}
        with self.assertRaisesRegex(ValueError,'unselected'):summarize(s,[{'identity':{'source_sha256':'authored','face_index':0,'glyph_id':3}}])
if __name__=='__main__':unittest.main()
