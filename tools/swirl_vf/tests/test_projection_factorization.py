"""Analytic projection decomposition, with rigid placement and closed cubics."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from batch_geometry import GeometryBatch, GeometryNodeTrace, ContourSource
from projection_factorization import factor_geometry, ProjectionSource
from tangent_geometry import resolve_path
from hvf_glyph_model import _commands
from cff2_geometry import operands
from test_hvf_branch_cells import authored_table


class ProjectionFactorTests(unittest.TestCase):
    def authored(self):
        t = np.linspace(-1, 2, 101)
        raw = np.tile([[.3, 0, 0, 0], [0, 0, 100, 40],
                       [120, 100, 130, 120], [0, 100, -20, 70]], (len(t), 1, 1)).astype(float)
        raw[:, 1, :2] = t[:, None]*[100, 40] + [-8, 20]
        kinds = (0, 2, 1, 1)
        angle = .63
        matrix = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        path = resolve_path(raw, kinds) @ matrix.T + [50, -80]
        node = GeometryNodeTrace(1, 2, np.empty((len(t), 0)),
            np.tile(matrix, (len(t), 1, 1)), np.tile([50, -80], (len(t), 1)), raw)
        batch = GeometryBatch([path], [ContourSource(1, 2, 0, 0)], len(t), [node])
        table = SimpleNamespace(part=lambda index: SimpleNamespace(blends=kinds))
        return table, batch, t

    def test_decomposition_survives_both_clamps_rotation_and_degree_elevation(self):
        table, batch, t = self.authored()
        before = batch.paths[0].copy()
        result = factor_geometry(table, batch)
        self.assertEqual(result.identities, ((1, 2, 0, 1),))
        np.testing.assert_allclose(result.parameters[:, 0], t, rtol=0, atol=5e-16)
        actual = result.combine()
        for i in range(len(t)):
            ops, expected = operands(_commands(batch.paths, i, 1))
            self.assertEqual(ops, result.operators)
            np.testing.assert_allclose(actual[i], expected, rtol=0, atol=1e-12)
        np.testing.assert_array_equal(batch.paths[0], before)

    def test_missing_trace_and_collapsed_projection_fail_explicitly(self):
        table, batch, _ = self.authored()
        batch.trace[0].shape_coordinates[:, 1, 2:4] = batch.trace[0].shape_coordinates[:, 0, 2:4]
        with self.assertRaisesRegex(ValueError, 'collapsed_projection'):
            factor_geometry(table, batch)
        batch.trace = None
        with self.assertRaisesRegex(ValueError, 'requires_source_geometry_trace'):
            factor_geometry(table, batch)

    def test_batched_no_tangent_source_preserves_all_commands_and_closures(self):
        table = authored_table()
        source = ProjectionSource(table, 0, batch_size=17)
        p = np.random.default_rng(71).uniform(-1, 1, (67, 3))
        values, parameters = source.components(p)
        self.assertEqual(source.factors, 0)
        self.assertEqual(parameters.shape, (67, 0))
        batch = source.renderer.render(0, p)
        for i in range(len(p)):
            ops, expected = operands(_commands(batch.paths, i, 1))
            self.assertEqual(ops, source.ops)
            np.testing.assert_allclose(values[i, 0], expected, rtol=0, atol=1e-12)
        absolute = np.cumsum(values[:, 0].reshape(len(p), -1, 2), axis=1)
        for start, end in source.closed_control_pairs:
            np.testing.assert_allclose(absolute[:, start], absolute[:, end], rtol=0, atol=1e-12)
        np.testing.assert_array_equal(source.errors(values.reshape(len(p), -1),
                                                    values.reshape(len(p), -1)), np.zeros(len(p)))


if __name__ == '__main__':
    unittest.main()
