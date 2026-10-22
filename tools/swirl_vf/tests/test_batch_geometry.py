"""Independent analytic fixtures plus explicit scalar/batch equivalence checks."""
import struct
import sys
from pathlib import Path
import unittest

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from batch_geometry import BatchGeometry
from hvf import HVGL, ExperimentalRenderer, FormatError, UnsupportedRendering
from test_hvf import table, shape, composite


class BatchGeometryTests(unittest.TestCase):
    def test_independent_fractional_shape_coordinates_and_trace(self):
        font = HVGL(table([shape()]))
        points = BatchGeometry(font).render(0, [[-.5], [0], [.25], [1]])
        np.testing.assert_array_equal(points.paths[0][:, 0], [[-5, 0], [0, 0], [5, 0], [20, 0]])
        self.assertEqual(points.sample_count, 4)
        self.assertEqual(points.sources[0].part_index, 0)
        self.assertEqual(points.sources[0].source_path_index, 0)
        self.assertEqual(points.sources[0].source_segment_start, 0)

    def test_analytic_rotation_translation_and_child_axis(self):
        font = HVGL(table([composite(rotation=np.pi/2), shape()], visible=1))
        font.validate()
        points = BatchGeometry(font).render(0, [[-.5], [0], [.5], [1]])
        np.testing.assert_allclose(points.paths[0][:, 0], [[30,45], [30,45], [30,50], [30,55]], atol=1e-5)
        self.assertEqual(points.sources[0].part_index, 1)
        self.assertEqual(points.sources[0].tree_part_offset, 1)

    def test_parallel_factor_preserves_source_parameter(self):
        font = HVGL(table([shape(blends=(0,1,1), parallel=True)]))
        result = BatchGeometry(font).render(0, [[0], [.25]])
        # Both neighboring off-curve controls translate by .25 * 20 = 5.
        # Their convex combination therefore also translates by exactly 5.
        np.testing.assert_allclose(result.paths[0][:,0], [[12.5,37.5],[17.5,37.5]], atol=1e-12)

    def test_scalar_equivalence_at_seeded_heldout_positions(self):
        rng = np.random.default_rng(7234)
        for font in (HVGL(table([shape()])),
                     HVGL(table([shape(blends=(0,1,1), parallel=True)])),
                     HVGL(table([composite(rotation=.317), shape()], visible=1))):
            locations = rng.uniform(-1, 1, (64, 1))
            result = BatchGeometry(font).render(0, locations)
            for n, location in enumerate(locations):
                expected = ExperimentalRenderer(font).render(0, location)
                self.assertEqual(len(expected), len(result.paths))
                for path, actual in zip(expected, result.paths):
                    np.testing.assert_allclose(actual[n], path, atol=1e-12, rtol=1e-12)

    def test_remapped_part_identity_is_retained(self):
        mapping = struct.pack('<HHIIIII',1,0,8,1,1,1,2)
        font = HVGL(table([composite(),shape(),shape()],visible=1), mapping)
        font.validate()
        result = BatchGeometry(font).render(0, [[0], [1]])
        self.assertEqual(result.sources[0].part_index, 2)

    def test_unsupported_tangents_not_silently_accepted(self):
        for kind in (2,3,4):
            font = HVGL(table([shape(blends=(kind,1,1))]))
            with self.assertRaises(UnsupportedRendering):
                BatchGeometry(font).render(0, [[0]])

    def test_shape_with_no_axes_and_empty_shape(self):
        font = HVGL(table([shape(axes=0)]))
        result = BatchGeometry(font).render(0, np.empty((3,0)))
        self.assertEqual(result.paths[0].shape,(3,6,2))
        np.testing.assert_array_equal(result.paths[0][0],result.paths[0][2])
        font = HVGL(table([struct.pack('<4H',0,0,0,0)]))
        result = BatchGeometry(font).render(0,np.empty((2,0)))
        self.assertEqual((result.paths,result.sources,result.sample_count),([],[],2))

    def test_invalid_shape_location_and_resource_budget(self):
        renderer = BatchGeometry(HVGL(table([shape()])))
        for location in ([[2]], [[float('nan')]], [[float('inf')]], [], [0], [[0,1]], [[0]]*1025):
            with self.assertRaises(FormatError):
                renderer.render(0,location)


if __name__=='__main__':
    unittest.main()
