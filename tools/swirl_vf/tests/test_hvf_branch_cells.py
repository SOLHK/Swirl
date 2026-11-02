"""Authored analytic three-dimensional branches, without source font data."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'tools'),
               str(Path(__file__).resolve().parents[1]/'platform')]
from hvf import HVGL
from batch_geometry import BatchGeometry
from hvf_branch_cells import branch_cell, affine_surface, dot_surface, BranchSurface, axis_has_kink
from probe_hvf_branch_cells import boundary_positions
from probe_transform_stages import composite
from probe_hierarchy_rules import shape_record, hvgl_table


def authored_table():
    return HVGL(hvgl_table([composite(1, axes=3, tree_axes=4,
        axis_master={0: -.25}, axis_extreme={(0,0):-.5,(0,1):.5,
            (0,2):-.75,(0,3):.75,(0,4):.25,(0,5):-.25}), shape_record()]))


class BranchCellTests(unittest.TestCase):
    def test_oblique_child_boundary_is_derived_from_source_coefficients(self):
        cell = branch_cell(authored_table(), 0, [.5,.5,.5])
        np.testing.assert_array_equal(cell.axis_expressions[(1,1)], [[-.25,.5,.75,-.25]])
        child = next(s for s in cell.surfaces if s.identity == (1,1,'axis_zero',0))
        np.testing.assert_allclose(child.value([[.5,.5,.5],[.1,.1,.1]]), [.25,-.15], atol=1e-16)
        self.assertEqual(cell.contains([[.5,.5,.5],[.1,.1,.1]]).tolist(), [True,False])

    def test_raw_axes_and_shapes_agree_inside_every_sampled_sign_cell(self):
        table = authored_table(); renderer = BatchGeometry(table, isolated_tangents=True)
        points = np.random.default_rng(17771).uniform(-1,1,(512,3))
        for anchor in ([.5,.5,.5], [.1,.1,.1], [-.25,.25,-.25], [-.25,-.5,-.75]):
            cell = branch_cell(table,0,anchor)
            selected = points[cell.contains(points)]
            self.assertGreater(len(selected), 5)
            batch = renderer.render(0,selected,capture_trace=True)
            h = np.column_stack((np.ones(len(selected)),selected))
            for node in batch.trace:
                key = (node.part_index,node.tree_part_offset)
                np.testing.assert_allclose(h @ cell.axis_expressions[key].T,node.axes,atol=1e-14,rtol=0)
                if node.shape_coordinates is not None:
                    np.testing.assert_allclose(np.einsum('nd,dsp->nsp',h,cell.shape_expressions[key]),
                        node.shape_coordinates,atol=1e-12,rtol=0)

    def test_exact_symmetric_extrema_remove_only_redundant_root_branches(self):
        table = authored_table(); cell = branch_cell(table, 0, [.5, .5, .5])
        self.assertFalse(any(s.identity[:3] == (0, 0, 'axis_zero') for s in cell.surfaces))
        self.assertTrue(any(s.identity[:3] == (1, 1, 'axis_zero') for s in cell.surfaces))
        points = np.asarray([[-.1, .8, .1], [.5, .5, -.1]])
        self.assertTrue(cell.contains(points).all())
        trace = BatchGeometry(table, isolated_tangents=True).render(0, points, capture_trace=True).trace
        h = np.column_stack((np.ones(len(points)), points))
        for node in trace:
            if node.shape_coordinates is not None:
                np.testing.assert_allclose(np.einsum('nd,dsp->nsp',h,
                    cell.shape_expressions[(node.part_index,node.tree_part_offset)]),
                    node.shape_coordinates,rtol=0,atol=1e-12)

    def test_small_nonzero_axis_extremum_does_not_disappear(self):
        from dataclasses import replace
        original = authored_table().part(0)
        self.assertFalse(axis_has_kink(original, 0))
        values = original.extreme_values.astype(float).copy()
        values[0] += 2**-40
        self.assertTrue(axis_has_kink(replace(original, extreme_values=values), 0))

    def test_glyph_without_root_axes_keeps_its_static_shape(self):
        table = HVGL(hvgl_table([shape_record(axes=0)]))
        cell = branch_cell(table, 0, [])
        self.assertEqual(cell.surfaces, [])
        self.assertEqual(boundary_positions(cell), [])
        self.assertEqual(cell.contains(np.empty((2,0))).tolist(), [True,True])
        np.testing.assert_array_equal(cell.shape_expressions[(0,0)][0],table.part(0).master)

    def test_boundary_probe_retains_both_quadratic_contacts(self):
        from hvf_branch_cells import BranchCell
        # Lift .16-x+x*x into 3D; anchor .1 gives a nonzero gradient.
        q = np.zeros((4,4)); q[0,0]=.16; q[0,1]=q[1,0]=-.5; q[1,1]=1
        cell = BranchCell(np.array([.1,0.,0.]),[BranchSurface(('test',),q,1)],{}, {})
        pairs = boundary_positions(cell)
        self.assertEqual(len(pairs),2)
        contacts = sorted(np.mean(b['positions'],axis=0)[0] for b in pairs)
        np.testing.assert_allclose(contacts,[.2,.8],atol=3e-16,rtol=0)
        for maximum in (0,-1,65,True):
            with self.assertRaises(ValueError):boundary_positions(cell,maximum)

    def test_quadratic_projection_detects_two_contacts_with_equal_endpoint_signs(self):
        # (P-A).(B-A) = .16-t+t*t. Both endpoints are positive, while
        # the projection changes its branch at t=.2 and t=.8.
        left = np.array([[.16,0.],[-1.,1.]])
        right = np.array([[1.,0.],[0.,1.]])
        surface = BranchSurface(('authored_projection',),dot_surface(left,right),1)
        np.testing.assert_allclose(surface.value([[0],[.2],[.5],[.8],[1]]),
            [.16,0,-.09,0,.16],atol=2e-16,rtol=0)

    def test_plane_coefficients_and_anchor_do_not_alias_source(self):
        coefficients = np.array([-.25,.5,.75,-.25])
        q = affine_surface(coefficients); coefficients[:] = 100
        np.testing.assert_array_equal(q[0], [-.25,.25,.375,-.125])
        table = authored_table(); data = bytes(table.data)
        anchor = np.array([.5,.5,.5]);cell = branch_cell(table,0,anchor);anchor[:] = 0
        np.testing.assert_array_equal(cell.anchor,[.5,.5,.5])
        self.assertEqual(table.data,data)

    def test_invalid_anchor_and_nonfinite_membership_fail(self):
        for point in ([0,0],[0,0,2],[0,0,float('nan')]):
            with self.assertRaises(ValueError):branch_cell(authored_table(),0,point)
        cell = branch_cell(authored_table(),0,[.5,.5,.5])
        with self.assertRaises(ValueError):cell.contains([[0,0,float('inf')]])
