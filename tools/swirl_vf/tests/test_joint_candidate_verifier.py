"""Acceptance must retain topology, winding and source-unit coordinates."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

import numpy as np
sys.path[:0] = [str(Path(__file__).resolve().parents[1]/'tools'),
               str(Path(__file__).resolve().parents[1]/'platform')]
from verify_joint_candidate import winding, requested_location, source_location


class JointCandidateVerifierTests(unittest.TestCase):
    def test_winding_checks_curves_and_each_closed_contour(self):
        square = [['moveTo', 0, 0], ['lineTo', 10, 0], ['lineTo', 10, 10],
                  ['lineTo', 0, 10], ['closePath']]
        clockwise = [['moveTo', 0, 0], ['qCurveTo', 0, 10, 10, 10], ['lineTo', 10, 0], ['closePath']]
        cubic = [['moveTo', 0, 0], ['curveTo', 0, 10, 10, 10, 10, 0], ['closePath']]
        self.assertEqual(winding(square+clockwise+cubic), [1, -1, -1])
        for bad in (square[:-1], [['lineTo', 1, 1]], square[:-1]+square):
            with self.assertRaises(ValueError):
                winding(bad)

    def test_physical_fractional_requests_are_declared_before_native_execution(self):
        tags = ('WDTH', 'wght', 'HGHT')
        axes = [SimpleNamespace(axisTag=t, minValue=1., defaultValue=500., maxValue=1000.) for t in tags]
        source = {'fvar': SimpleNamespace(axes=axes), 'avar': SimpleNamespace(
            segments={tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in tags})}
        for point in ([0., 0., 0.], [-.25, .37, .91], [1., -1., 1.]):
            user = requested_location(source, point)
            self.assertEqual(tuple(user), tags)
            np.testing.assert_allclose(source_location(source, user), point, atol=1e-6, rtol=0)

        source['avar'].segments['wght'] = {-1.: -1., 0.: 0., .125: 0., 1.: 1.}
        for point in ([0., 0., 0.], [.15, .2, -.35]):
            user = requested_location(source, point)
            np.testing.assert_allclose(source_location(source, user), point, atol=1e-6, rtol=0)
        self.assertEqual(requested_location(source, [0., 0., 0.])['wght'], 500.)


if __name__ == '__main__':
    unittest.main()
