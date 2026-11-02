import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from probe_local_cff2_basis import native_plan


class LocalNativePlanTests(unittest.TestCase):
    def test_fractional_native_plan_stays_in_declared_domain(self):
        profiles = [(1,500,1000),(100,400,900),(1,500,1000)]
        box = np.asarray([[.25,.26],[-.5,-.49],[-1.,-.99]])
        plan = native_plan(box,profiles,61173)
        self.assertEqual(plan,native_plan(box,profiles,61173))
        self.assertEqual(len(plan),len(set(plan)))
        self.assertGreaterEqual(len(plan),64)
        p=np.asarray([[(v-d)/(d-lo if v<d else hi-d) for v,(lo,d,hi) in zip(row,profiles)] for row in plan])
        self.assertTrue(((p>=box[:,0])&(p<=box[:,1])).all())
        self.assertTrue(np.equal(np.asarray(plan)*16,np.round(np.asarray(plan)*16)).all())

    def test_unrepresentable_box_is_rejected_without_substituting_a_point(self):
        with self.assertRaisesRegex(ValueError,'no_representable'):
            native_plan([[.0000001,.0000002]]*3,[(0,1,2)]*3,1)
