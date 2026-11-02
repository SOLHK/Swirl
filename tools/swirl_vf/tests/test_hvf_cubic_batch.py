import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np

sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'tools')]
from hvf_cubic_batch import cubic_batch
from hvf_glyph_model import _commands
from cff2_geometry import operands, control_points


class CubicBatchTests(unittest.TestCase):
    def test_multiple_contours_and_explicit_closing_points_match_pen(self):
        rng = np.random.default_rng(33771)
        paths = [rng.uniform(-500,1500,(19,2*segments,2)) for segments in (3,7,17)]
        batch = SimpleNamespace(paths=paths, sample_count=19)
        ops, relative, absolute = cubic_batch(batch)
        for i in range(19):
            reference_ops, reference = operands(_commands(paths,i,1))
            self.assertEqual(ops,reference_ops)
            np.testing.assert_allclose(relative[i],reference,rtol=0,atol=1e-12)
            np.testing.assert_allclose(absolute[i],control_points(reference_ops,reference),rtol=0,atol=2e-12)
        start = 0
        for path in paths:
            end = start+path.shape[1]//2*3
            np.testing.assert_array_equal(absolute[:,start],absolute[:,end])
            start = end+1

    def test_empty_glyph_retains_all_samples(self):
        ops,relative,absolute = cubic_batch(SimpleNamespace(paths=[],sample_count=3))
        self.assertEqual(ops,())
        self.assertEqual(relative.shape,(3,0))
        self.assertEqual(absolute.shape,(3,0,2))

    def test_malformed_or_nonfinite_path_is_rejected(self):
        for p in (np.zeros((2,5,2)),np.zeros((2,8,3)),np.full((2,8,2),np.nan)):
            with self.assertRaises(ValueError):
                cubic_batch(SimpleNamespace(paths=[p],sample_count=2))
