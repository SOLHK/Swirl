"""Original synthetic geometry and mapping hypotheses, not native acceptance."""
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
import calibrate_hvf_geometry as geometry
import calibrate_avar_metrics as mapping
from compare_axis_construction import GUARD


class NativeCalibrationHelperTests(unittest.TestCase):
    def test_normalization_distinguishes_source_default_from_numeric_midpoint(self):
        self.assertEqual(mapping.normalize(501,100,501,900),0.)
        self.assertEqual(mapping.normalize(501,100,500,900),.0025)
        self.assertEqual(mapping.normalize(300,100,500,900),-.5)
        self.assertEqual(mapping.normalize(900,100,501,900),1.)

    def test_duplicate_records_remain_falsifiable_alternatives(self):
        records=[(-1,-1),(-1,-.8),(0,-.1),(0,0),(.5,.4),(1,.8),(1,1)]
        before=list(records)
        self.assertEqual(mapping.ordered_intervals(records,-1),-.8)
        self.assertEqual(mapping.ordered_intervals(records,1),.8)
        self.assertEqual(mapping.candidate_map(records,0,'ordered_intervals',True),0)
        self.assertAlmostEqual(mapping.candidate_map(records,0,'ordered_intervals',False),-.1)
        self.assertEqual(mapping.candidate_map(records,1,'last_sorted',False),1)
        self.assertEqual(mapping.candidate_map(records,1,'first_sorted',False),.8)
        self.assertEqual(mapping.candidate_map(records,-1,'nonidentity_anchor_sorted',False),-.8)
        self.assertEqual(records,before)
        with self.assertRaises(ValueError):
            mapping.candidate_map(records,.2,'unknown',False)

    def test_changed_native_source_is_rejected_not_blindly_patched(self):
        for source in ('','func run() throws {',GUARD+GUARD+'\nfunc run() throws {'):
            with self.assertRaises(ValueError): mapping.harness(source)
        source='func makeInstance() {}\n'+GUARD+'\nfunc run() throws {}'
        result=mapping.harness(source)
        self.assertIn('func metricObservationInstance()',result)
        self.assertIn('Diagnostic observation only',result)
        self.assertNotIn(GUARD,result)
        self.assertIn(GUARD,source)  # Caller source was never overwritten.

    def paths(self):
        points=np.array([[0,0],[50,0],[100,0],[100,50],[100,100],[50,100],[0,100],[0,50]],float)
        events=[['begin_path'],['move',0,0],['line',100,0],['line',100,100],['line',0,100],['close'],['end_path']]
        return geometry.portable_paths([points]),geometry.native_paths(events)

    def test_line_parameterization_and_cyclic_start_are_not_geometry_changes(self):
        expected,actual=self.paths()
        self.assertEqual(geometry.discrepancy(expected,actual),(0.,4))
        actual[0]=actual[0][2:]+actual[0][:2]
        self.assertEqual(geometry.discrepancy(expected,actual),(0.,4))

    def test_coordinate_error_is_detected(self):
        expected,actual=self.paths()
        actual=[[(kind,points+3) for kind,points in path] for path in actual]
        self.assertEqual(geometry.discrepancy(expected,actual),(3.,4))

    def test_native_unhandled_cubic_and_broken_topology_rejected(self):
        with self.assertRaisesRegex(ValueError,'native_cubic'):
            geometry.native_paths([['cubic',0,0,1,1,2,2]])
        with self.assertRaisesRegex(ValueError,'segment_count'):
            expected,actual=self.paths();actual[0].pop();geometry.discrepancy(expected,actual)


if __name__=='__main__': unittest.main()
