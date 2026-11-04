"""VariationRegionList's high bit is reserved, not an extra capacity bit."""
from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from sparse_projection import SparseParameters,encode_clamp_ramps


class JointCapacityTests(unittest.TestCase):
    def test_reserved_region_count_bit_is_rejected_before_serialization(self):
        def model(n):return SparseParameters(np.zeros((n,3,3)),np.ones((n,1))*.01,n)
        self.assertEqual(len(encode_clamp_ramps(model(32767)).supports),32767)
        with self.assertRaisesRegex(ValueError,'region_count_overflow'):
            encode_clamp_ramps(model(32768))


if __name__=='__main__':unittest.main()
