"""Original controls for the observational constructor/axis plateau experiment."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from probe_axis_plateau import MODES, TAGS, compare_payloads, constructor_mode, plateau_cases, safe_failure
from test_verified_axis_oracle import native_record


class AxisPlateauTests(unittest.TestCase):
    def test_predeclared_cases_keep_boundaries_and_mixed_source_axes(self):
        ranges = {face: {"WDTH": (1., 500., 1000.), "wght": (100., 500., 900.),
                        "HGHT": (1., 500., 1000.)} for face in range(32)}
        before = deepcopy(ranges)
        cases = plateau_cases(ranges)
        self.assertEqual(ranges, before)
        self.assertEqual(cases, plateau_cases(ranges))
        self.assertEqual(set(cases), {0, 5, 10, 15, 20, 24, 31})
        for face, rows in cases.items():
            locations = {tuple(row["location"][tag] for tag in TAGS) for row in rows}
            self.assertEqual(len(locations), len(rows))
            for weight in (399.96, 399.9633, 400.04, 400.041, 299.9817, 300.01):
                self.assertIn((500., weight, 500.), locations)
            self.assertIn((600.5859375, 400.01, 250.), locations)
        missing = deepcopy(ranges); missing.pop(31)
        with self.assertRaises(ValueError):
            plateau_cases(missing)
        clipped = deepcopy(ranges); clipped[20]["wght"] = (100., 500., 399.)
        with self.assertRaises(ValueError):
            plateau_cases(clipped)

    def test_constructor_environment_is_restored_after_normal_and_failed_launches(self):
        key = "SWIRL_VF_PLATEAU_MODE"
        with patch.dict(os.environ, {key: "prior_value"}):
            for mode in MODES:
                with constructor_mode(mode):
                    self.assertEqual(os.environ[key], mode)
                self.assertEqual(os.environ[key], "prior_value")
            with self.assertRaisesRegex(RuntimeError, "authored_launch_failure"):
                with constructor_mode(MODES[0]):
                    raise RuntimeError("authored_launch_failure")
            self.assertEqual(os.environ[key], "prior_value")
            with self.assertRaises(ValueError):
                with constructor_mode("unknown"):
                    self.fail("invalid constructor was launched")
        with patch.dict(os.environ, clear=True):
            with constructor_mode(MODES[0]):
                self.assertIn(key, os.environ)
            self.assertNotIn(key, os.environ)

    def test_complete_payload_differences_are_not_hidden_by_metric_or_path_equality(self):
        request = {"request_id": "1", "face_index": 0, "location": dict.fromkeys(TAGS, 500.)}
        left = native_record(request, 0)
        left["commands"] = [["moveTo", 0., 0.], ["qCurveTo", 2., 4., 5., 0.], ["closePath"]]
        right = deepcopy(left); right["request_id"] = "another-process"
        same = compare_payloads(left, right)
        self.assertTrue(same["complete_payload_equal"])
        self.assertEqual(same["canonical_geometry"]["maximum_point_error"], 0.)
        right["advance_height"] -= 1
        changed = compare_payloads(left, right)
        self.assertFalse(changed["complete_payload_equal"])
        self.assertEqual(changed["maximum_metric_difference"], 1.)
        self.assertTrue(changed["raw_commands_equal"])
        right = deepcopy(left); right["unexpected_field"] = "authored_difference"
        self.assertFalse(compare_payloads(left, right)["complete_payload_equal"])
        right = deepcopy(left); right["commands"][1][2] += .25
        geometry = compare_payloads(left, right)
        self.assertFalse(geometry["raw_commands_equal"])
        self.assertEqual(geometry["canonical_geometry"]["status"], "outside_budget")
        text = json.dumps(geometry, allow_nan=False)
        self.assertNotIn('"commands"', text)
        self.assertNotIn('"points"', text)

    def test_failure_reports_do_not_publish_untrusted_native_payload_text(self):
        self.assertEqual(safe_failure(ValueError("known_code")),
                         {"failure_type": "ValueError", "failure_code": "known_code"})
        failure = safe_failure(ValueError("private points: [123456.789, 999999.321]"))
        self.assertEqual(failure, {"failure_type": "ValueError"})


if __name__ == "__main__":
    unittest.main()
