"""Public controls for serialization, Medium, mapping and bounded scheduling."""
import contextlib
import io
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from fontTools.pens.recordingPen import RecordingPointPen
from fontTools.ttLib import TTCollection
from fontTools.varLib.models import piecewiseLinearMap

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'platform')]
from windows_font_builder import bounded_map, rebased_avar, source_locations
from target_axis_mapping import SourceAxis
from windows_gvar_control import make, formula, face_axes, SCALE, verify


class DeliveryTests(unittest.TestCase):
    def test_serialized_four_faces_match_independent_joint_formula(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'authored.ttc'
            make(path)
            with TTCollection(path) as fonts:
                self.assertEqual(len(fonts.fonts), 4)
                for index, font in enumerate(fonts.fonts):
                    self.assertEqual(font['fvar'].axes[1].defaultValue, 499 if index % 2 else 501)
                    medium = [i for i in font['fvar'].instances if font['name'].getDebugName(i.subfamilyNameID) == 'Medium']
                    self.assertEqual(len(medium), 1)
                    self.assertEqual(medium[0].coordinates['wght'], 500)
                    for location in [(-.75, .25, .5), (.25, -.5, .75), (0., 0., 0.)]:
                        pen = RecordingPointPen()
                        font.getGlyphSet(location=dict(zip(('wdth', 'wght', 'HGHT'), location)), normalized=True)['A'].drawPoints(pen)
                        actual = np.asarray([args[0] for op, args, kwargs in pen.value if op == 'addPoint'])/SCALE
                        np.testing.assert_allclose(actual, formula(location, index), rtol=0, atol=1e-10)

    def test_native_verifier_retains_small_research_failures(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            path = Path(directory)
            rows = []
            for index in range(4):
                axes = {t: d for t, _, d, _, _ in face_axes(index)}
                for case in range(100):
                    points = formula((0, 0, 0), index)*SCALE
                    commands = [[('moveTo' if j == 0 else 'lineTo'), float(x), float(-y)] for j, (x, y) in enumerate(points)]
                    rows.append(dict(record='outline', face_index=index, axes=axes, commands=commands, case=str(case), axis_readback_mismatches=1))
            rows.append(dict(record='summary', axis_readback_mismatches=400))
            transcript = path/'outline-coordinates.jsonl'
            transcript.write_text('\n'.join(map(json.dumps, rows)))
            self.assertTrue(verify(path, path/'report.json'))
            self.assertEqual(json.loads((path/'report.json').read_text())['axis_readback_mismatches'], 400)
            rows[0]['commands'][0][1] += SCALE/8
            transcript.write_text('\n'.join(map(json.dumps, rows)))
            self.assertFalse(verify(path, path/'report.json'))

    def test_rebased_avar_uses_reachable_source_interval(self):
        # Independently authored repeated endpoints, not private source records.
        records = ((-16384, -16384), (-16384, -8192), (0, 0), (16384, 8192), (16384, 16384))
        axes = tuple(SourceAxis(tag, 100, 500, 900, records) for tag in ('WDTH', 'wght', 'HGHT'))
        with patch('windows_font_builder.axes_from_font', return_value=axes):
            table = rebased_avar(None)
            np.testing.assert_equal(source_locations(None, np.asarray([[-1., 0., 1.]])), [[-.5, 0., .5]])
        for mapping in table.segments.values():
            self.assertEqual([mapping[x] for x in (-1, 0, 1)], [-1, 0, 1])
            samples = np.arange(-16384, 16385)/16384
            actual = np.asarray([piecewiseLinearMap(x, mapping) for x in samples])
            self.assertLessEqual(float(np.max(np.abs(actual-samples))), 2/16384)
            self.assertTrue(np.all(np.diff(actual) >= 0))

    def test_bounded_scheduler_preserves_order_and_exceptions(self):
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(list(bounded_map(pool, lambda x: x*x, range(8), 3)), [x*x for x in range(8)])
            with self.assertRaises(ZeroDivisionError):
                list(bounded_map(pool, lambda x: 1/x, (2, 0, 1), 2))


if __name__ == '__main__':
    unittest.main()
