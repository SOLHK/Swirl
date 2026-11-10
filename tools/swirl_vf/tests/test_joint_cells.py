"""Local cell coverage, resource failures and lossless sparse-column storage."""
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from joint_cells import refine, load


class Source:
    ops = (('rmoveto', 2), ('rrcurveto', 6))
    count = 0
    def __call__(self, p):
        self.count += len(p)
        x, y, z = np.asarray(p).T
        return np.asarray([10+x*y, 20+y*z*z, x*0, y*0, z*0, x*0, x*0, z*0]).T
    def errors(self, a, b):
        return np.linalg.norm(np.cumsum((a-b).reshape(len(a), -1, 2), axis=1), axis=2).max(axis=1)


class JointCellTests(unittest.TestCase):
    def test_partition_and_sparse_archive_reproduce_unseen_joint_points(self):
        source = Source(); model = refine(source, max_cells=32)
        self.assertEqual(len(model.cells), 8)
        points = np.random.default_rng(234).uniform(-1, 1, (57, 3))
        np.testing.assert_allclose(model.evaluate(points), source(points), atol=1e-12, rtol=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'cells.npz'; model.save(path)
            with np.load(path, allow_pickle=False) as data:
                self.assertEqual(data['coefficients'].shape[-1], 2)
            saved = load(path, source.ops)
            np.testing.assert_array_equal(saved.evaluate(points), model.evaluate(points))
            self.assertLessEqual(saved.maximum_error, model.budget)

    def test_exhausted_refinement_budget_remains_failed(self):
        class Clamped(Source):
            def __call__(self, p):
                result = super().__call__(p)
                result[:, 0] += 100*np.maximum(0, p[:, 0]+p[:, 1]+p[:, 2]-.2)
                return result
        model = refine(Clamped(), max_cells=8)
        self.assertGreater(model.maximum_error, model.budget)
        self.assertTrue(any(not cell.model(model.operators).evidence['sampled_geometry_passed']
                            for cell in model.cells))


if __name__ == '__main__':
    unittest.main()
