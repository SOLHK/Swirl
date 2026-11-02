"""Authored analytic three-dimensional branches, without source font data."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'tools'),
               str(Path(__file__).resolve().parents[1]/'platform')]
from hvf import HVGL
from batch_geometry import BatchGeometry
from hvf_branch_cells import branch_cell, affine_surface, dot_surface, BranchSurface
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
