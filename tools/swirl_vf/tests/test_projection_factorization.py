"""Analytic projection decomposition, with rigid placement and closed cubics."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from batch_geometry import GeometryBatch, GeometryNodeTrace, ContourSource
from projection_factorization import factor_geometry, ProjectionSource, relative_cubics, parameter_entries
from tangent_geometry import resolve_path
from hvf_glyph_model import _commands
from cff2_geometry import operands
from test_hvf_branch_cells import authored_table


class ProjectionFactorTests(unittest.TestCase):
    def test_sparse_directions_equal_dense_elevation_at_every_contour_boundary(self):
        rng=np.random.default_rng(491)
        paths=[];sources=[];traces=[];parts={}
        for pi,count in enumerate((3,5,7)):
            raw=rng.normal(size=(19,count,4))*101
            kinds=(2,)*count
            path=resolve_path(raw,kinds)+[pi*200,-pi*50]
            paths.append(path);sources.append(ContourSource(pi,pi,0,0))
            traces.append(GeometryNodeTrace(pi,pi,np.empty((19,0)),
                np.tile(np.eye(2),(19,1,1)),np.zeros((19,2)),raw))
            parts[pi]=SimpleNamespace(blends=kinds)
        table=SimpleNamespace(part=parts.__getitem__)
        batch=GeometryBatch(paths,sources,19,traces)
        baseline=[p.copy() for p in paths];directions=[]
        for pi,k,_,_ in parameter_entries(table,batch):
            count=paths[pi].shape[1]//2
            a=paths[pi][:,2*((k-1)%count)+1];b=paths[pi][:,2*k+1]
            baseline[pi][:,2*k]=a
            delta=[np.zeros_like(p) for p in paths];delta[pi][:,2*k]=b-a
            directions.append(relative_cubics(delta)[1])
        expected=np.stack([relative_cubics(baseline)[1]]+directions,axis=1)
        actual=factor_geometry(table,batch)
        np.testing.assert_array_equal(actual.values,expected)
        self.assertEqual(actual.values.tobytes(),expected.tobytes())

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

    def test_parameter_only_sampling_keeps_exact_rational_values(self):
        table,batch,_=self.authored()
        source=ProjectionSource(authored_table(),0)
        source.table=table
        positions=np.zeros((batch.sample_count,3))
        with patch.object(source.renderer,'render',return_value=batch):
            _,expected=source.components(positions)
            actual=source.parameter_values(positions)
        np.testing.assert_array_equal(actual,expected)
        self.assertEqual(source.count,2*batch.sample_count)

    def test_batched_no_tangent_source_preserves_all_commands_and_closures(self):
        table = authored_table()
        source = ProjectionSource(table, 0, batch_size=17)
        p = np.random.default_rng(71).uniform(-1, 1, (67, 3))
        values, parameters = source.components(p)
        self.assertEqual(source.factors, 0)
        self.assertEqual(parameters.shape, (67, 0))
        np.testing.assert_array_equal(source.parameter_values(p),parameters)
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
