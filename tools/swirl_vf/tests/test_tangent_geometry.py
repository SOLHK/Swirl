"""Analytic Type-2 checks; optional archived native evidence is separate."""
import math
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from tangent_geometry import resolve_path, TangentGeometryError
from probe_tangent_rules import cases, encode_shape
from hvf import HVGL, ExperimentalRenderer, UnsupportedRendering


class TangentGeometryTests(unittest.TestCase):
    def test_native_observed_perturbations_match_measured_on_points(self):
        # Measurements from artifact 12203091876, SHA256
        # 7272fc9cb483d58d2b4cb33570a0869a37eb244f9f548f1e1f53cb2047383250.
        # These are ORIGINAL synthetic points, not any Apple glyph's outline.
        observed = {
            'incoming_x': (197.42738589211618, 164.6473029045643),
            'outgoing_x': (199.91701244813277, 154.68879668049794),
            'tangent_x': (180, 160), 'tangent_y': (180, 200),
            'mixed': (193.17774178423767, 166.23673330207578),
            'opposite_outgoing_40': (197.42738589211618, 135.3526970954357),
        }
        for name, blends, data in cases():
            if name in observed:
                result = resolve_path(data, blends).reshape(-1, 2, 2)
                index = blends.index(2)
                np.testing.assert_allclose(result[index, 0], observed[name], rtol=0, atol=1e-12)

    def test_projection_orthogonality_and_control_collinearity(self):
        rng = np.random.default_rng(873201)
        for _ in range(200):
            data = rng.normal(0, 500, (6, 4))
            result = resolve_path(data, [1,1,1,2,1,1]).reshape(-1,2,2)
            p, a, b = data[3,:2], data[2,2:], data[3,2:]
            actual = result[3,0]
            self.assertAlmostEqual(float(np.dot(p-actual,b-a)), 0, delta=1e-8)
            self.assertAlmostEqual(float(np.linalg.det(np.stack([actual-a,b-a]))), 0, delta=1e-8)
            np.testing.assert_array_equal(result[:,1], data[:,2:])
            np.testing.assert_array_equal(result[[0,1,2,4,5],0], data[[0,1,2,4,5],:2])

    def test_projection_is_on_infinite_line_not_clamped_segment(self):
        data = np.zeros((3,4));data[0,2:]=[0,0];data[1,2:]=[10,0];data[1,:2]=[30,17]
        result = resolve_path(data, [1,2,1])
        np.testing.assert_allclose(result[2], [30,0], rtol=0, atol=1e-12)

    def test_batch_matches_scalar_and_does_not_mutate_input(self):
        _, blends, base = cases()[2]
        batch = np.stack([base + np.array([0,0,d,-d]) for d in (-30,0,17.5)])
        saved=batch.copy();expected=np.stack([resolve_path(x,blends) for x in batch])
        np.testing.assert_array_equal(resolve_path(batch,blends),expected)
        np.testing.assert_array_equal(batch,saved)

    def test_rigid_transform_equivariance(self):
        _, blends, data = cases()[2]
        original = resolve_path(data, blends)
        for angle in (-2.1, 0.371, math.pi/2):
            c,s=math.cos(angle),math.sin(angle);matrix=np.array([[c,-s],[s,c]])
            moved=data.copy()
            for i,tag in enumerate(blends):
                if tag != 0: moved[i,:2]=data[i,:2]@matrix.T+[19,-21]
            moved[:,2:]=data[:,2:]@matrix.T+[19,-21]
            np.testing.assert_allclose(resolve_path(moved,blends),original@matrix.T+[19,-21],rtol=0,atol=1e-10)

    def test_short_nonzero_lines_are_not_discarded(self):
        data = np.zeros((3,4));data[1,2:]=[1e-150,0];data[1,:2]=[3e-150,2e-150]
        result=resolve_path(data,[1,2,1]);np.testing.assert_allclose(result[2],[3e-150,0],rtol=1e-12,atol=0)

    def test_degenerate_unsupported_and_malformed_paths_fail_explicitly(self):
        for tags in ([1,3,4], [1,2,1], [1,True,1]):
            with self.assertRaises(TangentGeometryError): resolve_path(np.zeros((3,4)),tags)
        for data in (np.zeros((3,3)), np.full((3,4),np.nan), np.full((3,4),np.inf)):
            with self.assertRaises(TangentGeometryError): resolve_path(data,[1,2,1])

    def test_batch_renderer_matches_scalar_and_retains_source_trace(self):
        from batch_geometry import BatchGeometry
        from probe_hierarchy_rules import cases as hierarchy_cases, hvgl_table
        from verify_tangent_projection import extra_cases
        for name, parts, _ in hierarchy_cases():
            table = HVGL(hvgl_table(parts))
            positions = [[-.75], [0], [.375], [1]]
            batch = BatchGeometry(table, isolated_tangents=True).render(0, positions)
            scalar = ExperimentalRenderer(table, isolated_tangents=True)
            for n, position in enumerate(positions):
                expected = scalar.render(0, position)
                self.assertEqual(len(batch.paths), len(expected))
                for actual, wanted in zip(batch.paths, expected):
                    np.testing.assert_allclose(actual[n], wanted, rtol=0, atol=1e-10)
            self.assertEqual(batch.sources[0].part_index, len(parts)-1)
        for name, blends, data in cases() + list(extra_cases()):
            table = HVGL(encode_shape(blends, data))
            actual = BatchGeometry(table, isolated_tangents=True).render(0, [[0,0,0]])
            np.testing.assert_allclose(actual.paths[0][0], resolve_path(data,blends), rtol=0, atol=1e-10)
            self.assertEqual(actual.sources[0].source_segment_start, 0)

    def test_legacy_renderer_still_requires_explicit_tangent_mode(self):
        for name,blends,data in cases():
            table=HVGL(encode_shape(blends,data))
            if 2 in blends:
                with self.assertRaises(UnsupportedRendering): ExperimentalRenderer(table).render(0,[0,0,0])
            expected=resolve_path(data,blends)
            actual=ExperimentalRenderer(table,isolated_tangents=True).render(0,[0,0,0])
            np.testing.assert_allclose(actual[0],expected,rtol=0,atol=1e-12)


if __name__ == '__main__': unittest.main()
