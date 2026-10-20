"""Independent controls for the observation-only anchor diagnosis driver."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from probe_axis_anchor import (MODES, MODE_ENV, MODEL_NAMES, TAGS, add_control,
    control_stats, declare_readback, declared_mappings, diagnostic_failure, replay_audit, selected_mode)
from diagnose_path_types import RawSegment
from test_verified_axis_oracle import native_record


def records():
    point = dict(WDTH=600.5859375, wght=500., HGHT=500.)
    plan = declare_readback(point)
    canonical = {tag: item["canonical"] for tag, item in plan.items()}
    identity = {"face_index": 0, "axes": [{"tag": tag, "minimum": 1., "default": 500., "maximum": 1000.}
                                            for tag in TAGS]}
    original = {gid: native_record({"request_id": "original", "face_index": 0, "location": point}, gid,
                                  reported=canonical) for gid in (0, 1)}
    replay = {gid: native_record({"request_id": "replay", "face_index": 0, "location": canonical}, gid,
                                reported=canonical) for gid in (0, 1)}
    return identity, point, original, replay, plan


class AxisAnchorTests(unittest.TestCase):
    def test_replay_uses_existing_axis_policy_and_complete_blank_glyph_payload(self):
        args = records()
        before = deepcopy(args)
        result = replay_audit(*args)
        self.assertEqual(result["status"], "PASS_FINITE_REPLAY")
        self.assertEqual(result["glyph_pairs"], 2)
        self.assertEqual(args, before)
        args[3][1]["vertical_origin_x"] += 2 ** -30
        result = replay_audit(*args)
        self.assertEqual(result["status"], "FAILED_FINITE_REPLAY")
        self.assertEqual(result["payload_differences"], [{"glyph_id": 1, "fields": ["vertical_origin_x"]}])
        self.assertEqual(result["readback_failures"], [])

    def test_omitted_nondefault_and_unstable_replay_are_retained_separately(self):
        args = records()
        del args[2][0]["reported_location"]["WDTH"]
        args[3][1]["reported_location"]["WDTH"] += .0001
        result = replay_audit(*args)
        self.assertEqual(result["status"], "FAILED_FINITE_REPLAY")
        self.assertEqual({r["failure_code"] for r in result["readback_failures"]},
            {"native_nondefault_axis_not_reported", "native_readback_replay_not_exactly_stable"})
        self.assertEqual(result["payload_differences"], [])
        self.assertNotIn('"commands"', json.dumps(result))
        self.assertNotIn('"advance_width"', json.dumps(result))

    def test_unknown_payload_fields_and_identity_mismatches_cannot_pass(self):
        args = records()
        args[3][0]["authored_extra_payload"] = 123456.789
        result = replay_audit(*args)
        self.assertEqual(result["status"], "FAILED_FINITE_REPLAY")
        self.assertEqual(result["payload_differences"], [{"glyph_id": 0, "fields": ["authored_extra_payload"]}])
        self.assertNotIn("123456.789", json.dumps(result))
        args = records()
        args[3][0]["face_index"] = 1
        with self.assertRaisesRegex(ValueError, "replay_record_identity_mismatch"):
            replay_audit(*args)
        args = records(); args[3].pop(1)
        with self.assertRaisesRegex(ValueError, "replay_glyph_sets_differ"):
            replay_audit(*args)

    def test_predeclared_cast_location_and_original_record_order_are_distinct(self):
        axes = [SimpleNamespace(axisTag=tag, minValue=37., defaultValue=437., maxValue=837.) for tag in TAGS]
        font = {"fvar": SimpleNamespace(axes=axes)}
        raw = {tag: [(-1., -1.), (0., 0.), (1., .5), (1., 1.)] for tag in TAGS}
        before = deepcopy(raw)
        point = dict.fromkeys(TAGS, 437.); point["wght"] = 236.9817
        result = declared_mappings(font, raw, point)
        self.assertEqual(result[MODEL_NAMES[0]]["wght"], -8192 / 16384)
        self.assertEqual(result[MODEL_NAMES[1]]["wght"], -8193 / 16384)
        self.assertEqual(result[MODEL_NAMES[0]]["WDTH"], 0.)
        self.assertEqual(result[MODEL_NAMES[1]]["HGHT"], 0.)
        for model in declared_mappings(font, raw, dict.fromkeys(TAGS, 837.)).values():
            self.assertEqual(model, dict.fromkeys(TAGS, .5))
        self.assertEqual(raw, before)

    def test_numeric_control_failure_is_counted_in_both_verdicts(self):
        left = [[RawSegment("Q", ((0., 0.), (2., 5.), (4., 0.)))]]
        right = [[RawSegment("Q", ((0., 0.), (2., 5.25), (4., 0.)))]]
        stats = control_stats()
        result = add_control(stats, left, right, 0, 7, dict.fromkeys(TAGS, 500.))
        self.assertEqual(result["status"], "outside_budget")
        self.assertEqual(stats["legacy"]["failures"], 1)
        self.assertEqual(stats["preserved_controls"]["failures"], 1)
        self.assertEqual(stats["glyphs_with_restored_Q"], 0)
        self.assertNotIn('"points"', json.dumps(stats))

    def test_anchor_selector_restores_prior_environment_on_launch_failure(self):
        with patch.dict(os.environ, {MODE_ENV: "previous"}):
            with self.assertRaisesRegex(RuntimeError, "authored_failure"):
                with selected_mode(MODES[1]):
                    self.assertEqual(os.environ[MODE_ENV], MODES[1])
                    raise RuntimeError("authored_failure")
            self.assertEqual(os.environ[MODE_ENV], "previous")
            with self.assertRaisesRegex(ValueError, "unknown_anchor_mode"):
                with selected_mode("invalid"):
                    self.fail("unknown mode accepted")

    def test_native_failure_wrapper_retains_only_explicit_public_codes(self):
        for prefix in ("native request 17 face 2 failed", "native oracle startup failed"):
            result = diagnostic_failure(RuntimeError(prefix + ": anchor_optical_inheritance_mismatch"))
            self.assertEqual(result["native_failure_code"], "anchor_optical_inheritance_mismatch")
            for tail in ("raw_outline_123456_789", "anchor_private_metric_123456", "[123456.789, 9]",
                         "anchor_optical_inheritance_mismatch\nprivate payload"):
                result = diagnostic_failure(RuntimeError(prefix + ": " + tail))
                self.assertEqual(result, {"failure_type": "RuntimeError"})
        self.assertEqual(diagnostic_failure(ValueError("authored_public_code")),
                         {"failure_type": "ValueError", "failure_code": "authored_public_code"})


if __name__ == "__main__":
    unittest.main()
