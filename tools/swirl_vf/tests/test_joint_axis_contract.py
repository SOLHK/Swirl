"""Authored raw records: dictionary equality cannot establish axis identity."""
from pathlib import Path
import struct,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from audit_joint_axis_contract import summarize_records


class AxisContractTests(unittest.TestCase):
    def test_duplicate_source_and_missing_anchor_are_visible_in_aggregate(self):
        def audit(records):
            data=struct.pack('>5H',1,0,0,1,len(records))+b''.join(struct.pack('>hh',*p) for p in records)
            return summarize_records(data,['wght'],{'wght':dict(records)})['axes'][0]
        records=[(-16384,-16384),(-16384,-16000),(0,0),(16384,16384)]
        source=audit(records);candidate=audit(list(dict(records).items()))
        self.assertEqual(source['raw_records'],4)
        self.assertEqual(source['dictionary_records'],3)
        self.assertEqual(source['violations'],{'duplicate_from_coordinate':1})
        self.assertEqual(candidate['violations'],{'missing_required_anchor':1})
        self.assertEqual(audit([])['violations'],{'insufficient_segment_records':1})
        self.assertNotIn('records',source)


if __name__=='__main__':unittest.main()
