"""Original geometric and sampling regressions; no Apple outlines are fixtures."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from probe_user_axis_geometry import (MODELS, axis_records, coretext_paths, discrepancy,
    make_harness, map_location, new_stats, record_check, requests_for_face)
from compare_axis_construction import GUARD
from test_coretext_extract import make_fixture


class UserAxisGeometryTests(unittest.TestCase):
    def test_closed_quadratic_geometry_keeps_fractional_points(self):
        commands = [["moveTo", 10.125, 0.], ["qCurveTo", 20., 40.25, 30., 0.], ["closePath"]]
        paths = coretext_paths(commands)
        self.assertEqual(paths[0][0][0], "Q")
        np.testing.assert_array_equal(paths[0][0][1], [10.125, 0., 20., 40.25, 30., 0.])
        self.assertEqual(len(paths[0]), 2)
        self.assertEqual(discrepancy(paths, paths)[0], 0.)

    def test_invalid_paths_do_not_become_blank_glyphs(self):
        for commands in ([["lineTo", 2, 3]], [["moveTo", 1, 2]], [["bogus"]],
                         [["moveTo", 0, 0], ["qCurveTo", 1, 2], ["closePath"]]):
            with self.assertRaises(ValueError):
                coretext_paths(commands)
        self.assertEqual(coretext_paths([]), [])

    def test_diagnostic_guard_is_explicit_and_original_is_unchanged(self):
        source = (Path(__file__).resolve().parents[1] / "platform/coretext_extract.swift").read_text()
        self.assertIn(GUARD, source)
        harness = make_harness(source)
        self.assertNotIn(GUARD, harness)
        self.assertIn('"diagnostic_readback_observation_only": true', harness)
        self.assertIn('verifyIdentity(font, raw, allTables: false)', harness)
        self.assertIn('axis_value_out_of_source_range', harness)
        self.assertEqual(source, (Path(__file__).resolve().parents[1] / "platform/coretext_extract.swift").read_text())
        with self.assertRaises(ValueError):
            make_harness(source.replace(GUARD, ""))

    def test_all_axes_endpoints_defaults_fractional_and_mixed_are_sampled(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "fixture.ttc"; make_fixture(p)
            with TTCollection(p) as c:
                font = c.fonts[0]; points = requests_for_face(font, 0)
                axes = font["fvar"].axes; tags = [a.axisTag for a in axes]
                defaults = {a.axisTag: a.defaultValue for a in axes}
                self.assertIn(defaults, points)
                for axis in axes:
                    for v in (axis.minValue, axis.maxValue):
                        self.assertIn({**defaults, axis.axisTag: v}, points)
                self.assertTrue(any(sum(p[t] != defaults[t] for t in tags) == 3 for p in points))
                self.assertEqual(len(points), len({tuple(p[t] for t in tags) for p in points}))
                records = axis_records(font)
                for model in MODELS:
                    self.assertEqual(map_location(font, records, defaults, model), dict.fromkeys(tags, 0.))

    def test_models_never_mix_to_turn_failures_into_acceptance(self):
        a, b = new_stats(), new_stats()
        record_check(a, 0, 2, {"WDTH": 1.}, lambda: .04)
        record_check(b, 0, 2, {"WDTH": 1.}, lambda: 0.)
        record_check(a, 0, 2, {"WDTH": 2.}, lambda: 0.)
        record_check(b, 0, 2, {"WDTH": 2.}, lambda: .04)
        self.assertEqual((a["checks"], b["checks"]), (2, 2))
        self.assertEqual((a["failures"], b["failures"]), (1, 1))
        self.assertEqual(a["maximum_point_error"], .04)
        self.assertEqual(a["examples"][0]["glyph_id"], 2)


if __name__ == "__main__":
    unittest.main()
