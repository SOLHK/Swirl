"""Exclusion certificates must retain every possible refinement family."""
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from midpoint_sample_exclusion import excluded


class ExclusionTests(unittest.TestCase):
    def test_generated_jitter_and_arbitrary_branch_contacts_are_never_certified(self):
        rng = np.random.default_rng(827)
        stencil = rng.uniform(0, 1, (64, 3)); samples = []
        for _ in range(100):
            widths = 2.**-rng.integers(0, 15, 3)
            lo = rng.integers(0, 16384, 3)/16384
            lo = np.minimum(lo, 1-widths); hi = lo+widths
            offset = rng.integers(0, 2, 3); lo -= offset; hi -= offset
            sign = rng.choice((-1., 1.), 3)
            samples.extend(np.where(sign > 0, lo+stencil*widths, hi-stencil*widths))
            for axis in range(3):
                p = (lo+hi)/2; p[axis] = rng.uniform(lo[axis], hi[axis]); samples.append(p)
            for _ in range(3):
                t = rng.uniform(0, 1)
                a = np.where(sign > 0, lo, hi); b = np.where(sign > 0, hi, lo)
                for u in (max(0, t-1e-7), t, min(1, t+1e-7)):
                    samples.append((1-u)*a+u*b)
        self.assertFalse(excluded(samples, [stencil]).any())

    def test_independent_random_triples_can_be_certified_without_fitting(self):
        rng = np.random.default_rng(829)
        points = rng.uniform(-1, 1, (2048, 3))
        stencil = np.random.default_rng(827).uniform(0, 1, (64, 3))
        self.assertGreater(int(excluded(points, [stencil]).sum()), 2000)


if __name__ == '__main__':
    unittest.main()
