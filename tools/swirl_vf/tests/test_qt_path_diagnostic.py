import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from diagnose_qt_path_bounds import diagnose


class QtPathDiagnosticTests(unittest.TestCase):
    def report(self):
        path=[[0,0.,0.],[1,3.,0.],[1,0.,0.]]
        return dict(schema=1,scope='private_source_local_box_only',limit_source_units=1/32,
                    source_font_acceptance=False,source_glyph_id=12,source_sha256='a'*64,
                    font_sha256='b'*64,status='FAIL',observations=1,failures=1,
                    rows=[dict(identity=True,passed=False,actual_path=path,reference_path=copy.deepcopy(path))])

    def test_bound_cannot_override_original_failure_or_font_identity(self):
        report=self.report();result=diagnose(report)
        self.assertEqual(result['original_strict_status'],'FAIL')
        self.assertEqual(result['original_strict_failures'],1)
        self.assertEqual(result['bounded_failed_observations'],1)
        self.assertFalse(result['strict_path_gate_overridden'])
        report['rows'][0]['identity']=False
        self.assertEqual(diagnose(report)['bounded_failed_observations'],0)

    def test_inconsistent_counts_and_changed_contract_are_rejected(self):
        for key,value in [('failures',0),('observations',0),('limit_source_units',.1),
                          ('source_font_acceptance',True)]:
            report=self.report();report[key]=value
            with self.assertRaises(ValueError):diagnose(report)
