from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from hvf import Shape
from hvf_clamp_bounds import raw_curve_bounds, certify_no_type0_contacts


class ClampBoundTests(unittest.TestCase):
    def table(self, amplitude):
        master = np.zeros((3, 4)); master[0, 0] = .5
        delta = np.zeros((6, 3, 4)); delta[::2, 0, 0] = -amplitude; delta[1::2, 0, 0] = amplitude
        shape = Shape(0, 3, (3,), (0, 1, 1), master, delta)
        return SimpleNamespace(part=lambda gid: shape)

    def test_safe_factor_interval_is_a_covering_proof(self):
        table = self.table(.1)
        result = certify_no_type0_contacts(table, 0)
        self.assertTrue(result['proved_absent'])
        self.assertLessEqual(result['lower'], .2)
        self.assertGreaterEqual(result['upper'], .8)
        interval = raw_curve_bounds(table, 0, [[-1, 1]]*3)[0]
        self.assertLessEqual(interval[0], .2)
        self.assertGreaterEqual(interval[1], .8)

    def test_possible_clamp_and_exhausted_budget_cannot_claim_absence(self):
        result = certify_no_type0_contacts(self.table(.5), 0, max_depth=3)
        self.assertFalse(result['proved_absent'])
        self.assertGreater(result['unresolved_boxes'], 0)
        result = certify_no_type0_contacts(self.table(.5), 0, max_boxes=1)
        self.assertFalse(result['proved_absent'])


if __name__ == '__main__':
    unittest.main()
