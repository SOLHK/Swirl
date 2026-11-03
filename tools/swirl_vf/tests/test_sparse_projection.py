"""Independent sparse hierarchy, format quantization, and clamp identities."""
from pathlib import Path
import sys
import unittest

import numpy as np
from fontTools.varLib.models import supportScalar
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from sparse_projection import axis_nodes, basis, fit, encode_clamp_ramps


class SparseProjectionTests(unittest.TestCase):
    def test_tensor_hierarchy_reproduces_mixed_linear_fields_off_grid(self):
        def source(p):
            x, y, z = p.T
            return np.asarray([.25+x/2-y/4+z/8, x*y*z/4-x*z/2+y]).T
        model = fit(source, 4)
        p = np.random.default_rng(2026110397).uniform(-1, 1, (257, 3))
        np.testing.assert_allclose(model.evaluate(p), source(p), rtol=0, atol=5e-16)
        self.assertEqual(model.training_nodes, len(model.supports))
        self.assertTrue(np.all(model.supports*16384 == np.rint(model.supports*16384)))

    def test_scalar_basis_agrees_with_OpenType_at_edges_and_arbitrary_points(self):
        model = fit(lambda p: p, 3)
        p = np.r_[np.random.default_rng(11).uniform(-1, 1, (31, 3)),
                  [[-1, -1, -1], [0, 0, 0], [1, 1, 1]]]
        expected = [[supportScalar(dict(zip(('A', 'B', 'C'), point)),
            {tag: tuple(support) for tag, support in zip(('A', 'B', 'C'), row) if support[1] != 0})
            for row in model.supports] for point in p]
        np.testing.assert_allclose(basis(model.supports, p), expected, rtol=0, atol=1e-15)

    def test_ramps_execute_both_clamps_and_preserve_integer_store_data(self):
        source = lambda p: (.25+p[:, 0]/2+p[:, 1]/2-p[:, 2]/4)[:, None]
        model = fit(source, 5)
        p = np.r_[np.random.default_rng(29).uniform(-1, 1, (513, 3)),
                  [[-1, -1, 1], [1, 1, -1], [0, 0, 0]]]
        for count in (1, 2, 4, 8):
            ramps = encode_clamp_ramps(model, count)
            self.assertEqual(len(ramps.supports), 7)
            error = np.abs(ramps.evaluate_clamped(p)-np.clip(source(p), 0, 1)).max()
            self.assertLessEqual(error, 1/(65536*count))
            hidden = [f'H{i:03d}' for i in range(count)]
            store, mapping = ramps.var_store(('WDTH', 'wght', 'HGHT'), hidden)
            self.assertEqual(store.VarRegionList.RegionAxisCount, 3+count)
            self.assertEqual(store.VarData[0].Item[3:], ramps.coefficients.T.tolist())
            # The identity axis-to-item map is represented by an absent map.
            self.assertIsNone(mapping)

    def test_budget_and_format_failures_are_explicit(self):
        with self.assertRaisesRegex(ValueError, 'node_budget'):
            fit(lambda p: p, 5, max_nodes=20)
        for level in (-1, 16, 1.5):
            with self.assertRaises(ValueError):
                axis_nodes(level)
        with self.assertRaisesRegex(ValueError, 'parameter_samples'):
            fit(lambda p: np.full((len(p), 1), np.nan), 1)
        model = fit(lambda p: p[:, :1], 2)
        for count in (0, 33, 1.5):
            with self.assertRaises(ValueError):
                encode_clamp_ramps(model, count)


if __name__ == '__main__':
    unittest.main()
