"""Fabricated comparison cases; no manufactured native acceptance evidence."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import b1_metric_unit_comparison as b1
from test_metric_b1_discriminator import example_report, record_bits


def refresh_bits(report):
    report.pop("binary64_hex_by_json_path", None)
    report["binary64_hex_by_json_path"] = record_bits(report)


def pair():
    base_entry, requests, complete = example_report(count=2)
    base_entry["requests"] = deepcopy(requests)
    baseline = deepcopy(complete)
    baseline["status"] = "NATIVE_DIAGNOSTIC_FAILED"
    baseline["completed_request_count"] = 1
    baseline.pop("source_unchanged_after_measurement")
    baseline["observations"][1] = {key: baseline["observations"][1][key]
                                     for key in ("id", "requested_axes", "point_size", "upem")}
    baseline["observations"][1].update(status="FAILED", error="native_axis_readback_not_exact:HGHT")
    scaled_entry, scaled = deepcopy(base_entry), deepcopy(complete)
    scaled_entry["sha256"] = "c" * 64
    scaled_entry["table_sha256"] = {"head": "d" * 64}
    scaled["source"].update(sha256=scaled_entry["sha256"], table_sha256=deepcopy(scaled_entry["table_sha256"]))
    for request, row in zip(scaled_entry["requests"], scaled["observations"]):
        request["normalized_design_axes"] = deepcopy(request["axes"])
        request["native_user_axes"] = {"WDTH": request["axes"]["WDTH"], "HGHT": request["axes"]["HGHT"] * 16384}
        row["requested_axes"] = deepcopy(request["native_user_axes"])
        for identity in (row["font_identity"], row["vertical_layout"]["runs"][0]["font_identity"]):
            identity["verified_table_sha256"] = deepcopy(scaled_entry["table_sha256"])
            identity["postscript_name"] = "SCALED_TEST_IDENTITY"
    for raw, scale in ((baseline, 1), (scaled, 16384)):
        raw["source"]["axes"] = [{"tag": "WDTH", "minimum": -1, "default": 0, "maximum": 1},
                                   {"tag": "HGHT", "minimum": -scale, "default": 0, "maximum": scale}]
        refresh_bits(raw)
    return baseline, scaled, base_entry, scaled_entry


class UnitChannelComparisonTests(unittest.TestCase):
    def test_failed_partial_baseline_is_not_promoted_and_channels_are_exact(self):
        args = pair()
        before = deepcopy(args)
        result = b1.compare_unit_channels(*args)
        self.assertEqual(result["same_count"], 1)
        self.assertEqual(result["not_compared_count"], 1)
        self.assertEqual(result["mismatch_count"], 0)
        self.assertEqual(result["baseline"]["classification"], "partial_no_reverse")
        self.assertFalse(result["baseline"]["baseline_promoted_to_accepted_report"])
        self.assertFalse(result["baseline"]["reverse_replay_verified"])
        self.assertFalse(result["baseline"]["source_final_reverification_present"])
        self.assertFalse(result["native_acceptance"])
        self.assertEqual(args, before)

    def test_source_hash_upem_table_hash_and_axis_domains_must_match(self):
        for source_key, value in (("sha256", "x" * 64), ("upem", 1024), ("table_sha256", {})):
            args = pair()
            args[0]["source"][source_key] = value
            with self.subTest(field=source_key), self.assertRaisesRegex(ValueError, "source_identity"):
                b1.compare_unit_channels(*args)
        args = pair()
        args[1]["source"]["axes"][1]["maximum"] = 1
        with self.assertRaisesRegex(ValueError, "axis_domains"):
            b1.compare_unit_channels(*args)

    def test_duplicate_extra_and_missing_request_are_not_ignored(self):
        for problem in ("duplicate", "extra", "missing"):
            args = pair()
            if problem == "missing":
                args[0]["observations"].pop()
            else:
                args[0]["observations"][1]["id"] = args[0]["observations"][0]["id"] if problem == "duplicate" else "EXTRA"
            with self.subTest(problem=problem), self.assertRaises(ValueError):
                b1.compare_unit_channels(*args)

    def test_complete_failed_status_and_count_confusion_is_rejected(self):
        for problem in ("status", "count", "failed_channels", "complete_error"):
            args = pair()
            if problem == "status":
                args[0]["status"] = "NATIVE_DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE"
            elif problem == "count":
                args[0]["completed_request_count"] = 2
            elif problem == "failed_channels":
                args[0]["observations"][0]["status"] = "FAILED"
                args[0]["observations"][0]["error"] = "test failure"
            else:
                args[0]["observations"][0]["error"] = "test failure"
            with self.subTest(problem=problem), self.assertRaises(ValueError):
                b1.compare_unit_channels(*args)

    def test_every_channel_numeric_leaf_requires_native_bits(self):
        suffixes = ("direct_advances.horizontal_sum", "vertical_translation.raw_vector[0]",
                    "witness_path.commands[0][1]", "vertical_layout.glyphs[1].position[1]",
                    "point_size", "requested_axes.HGHT")
        for suffix in suffixes:
            args = pair()
            del args[0]["binary64_hex_by_json_path"]["$.observations[0]." + suffix]
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, "bits_missing"):
                b1.compare_unit_channels(*args)

    def test_integral_raw_double_and_forged_bits_cannot_evade_validation(self):
        args = pair()
        args[0]["observations"][0]["direct_advances"]["vertical_sum"] = 849
        self.assertEqual(b1.compare_unit_channels(*args)["same_count"], 1)
        args[0]["binary64_hex_by_json_path"]["$.observations[0].direct_advances.vertical_sum"] = "0000000000000000"
        with self.assertRaisesRegex(ValueError, "roundtrip"):
            b1.compare_unit_channels(*args)

    def test_signed_zero_is_a_bits_mismatch_without_numeric_tolerance(self):
        args = pair()
        args[1]["observations"][0]["direct_advances"]["vertical_vector"][1] = -0.0
        refresh_bits(args[1])
        result = b1.compare_unit_channels(*args)
        channel = result["observations"][0]["channels"]["direct_advances"]
        self.assertTrue(channel["values_exact_match"])
        self.assertFalse(channel["binary64_exact_match"])
        self.assertEqual(result["mismatch_count"], 1)

    def test_nonidentity_channel_fields_and_missing_values_are_not_dropped(self):
        args = pair()
        args[1]["observations"][0]["witness_path"]["new_field"] = "must compare"
        self.assertEqual(b1.compare_unit_channels(*args)["mismatch_count"], 1)
        args = pair()
        args[1]["observations"][0]["direct_advances"].pop("horizontal_sum")
        refresh_bits(args[1])
        self.assertEqual(b1.compare_unit_channels(*args)["mismatch_count"], 1)

    def test_manifest_normalized_and_user_unit_semantics_cannot_be_guessed(self):
        args = pair()
        args[3]["requests"][0]["normalized_design_axes"]["HGHT"] = -0.5
        with self.assertRaisesRegex(ValueError, "normalized_manifest_axes"):
            b1.compare_unit_channels(*args)
        args = pair()
        args[3]["requests"][0].pop("native_user_axes")
        with self.assertRaisesRegex(ValueError, "unit_basis"):
            b1.compare_unit_channels(*args)


class WitnessInferenceTests(unittest.TestCase):
    def test_fraction_conversion_recovers_axes_without_intermediate_rounding(self):
        request = {"axes": {"WDTH": 0.375, "HGHT": -0.875}, "point_size": 16.0,
                   "normalized_design_axes": {"WDTH": 0.375, "HGHT": -0.875},
                   "native_user_axes": {"WDTH": 0.375, "HGHT": -14336.0}}
        design = [100, -101.25, 675, 868.75]
        row = {"status": "COMPLETE", "requested_axes": request["native_user_axes"], "point_size": 16.0,
               "upem": 1024, "witness_path": {"geometric_bounds_xywh": [v / 64 for v in design]}}
        result = b1.infer_witness_axes(row, request, "gvar")
        self.assertTrue(result["all_axes_exact_match"])
        self.assertEqual(result["HGHT"]["from_top_exact"]["numerator"], -7)
        self.assertEqual(result["HGHT"]["from_top_exact"]["denominator"], 8)
        self.assertEqual(result["WDTH"]["inferred_exact"]["numerator"], 3)
        self.assertEqual(result["WDTH"]["inferred_exact"]["denominator"], 8)
        self.assertFalse(result["basis"]["rounding_applied"])

    def test_disagreeing_visible_top_and_bottom_are_reported_without_fitting(self):
        request = {"axes": {"WDTH": 0.0, "HGHT": 0.0}, "point_size": 1000}
        row = {"status": "COMPLETE", "requested_axes": request["axes"], "point_size": 1000,
               "upem": 1000, "witness_path": {"geometric_bounds_xywh": [100, -180, 600, 1001]}}
        result = b1.infer_witness_axes(row, request, "gvar")
        self.assertFalse(result["HGHT"]["top_bottom_exact_agreement"])
        self.assertFalse(result["all_axes_exact_match"])
        self.assertEqual(result["HGHT"]["from_top_exact"]["denominator"], 60)

    def test_fixed_phantom_only_outline_cannot_identify_height_axis(self):
        request = {"axes": {"WDTH": 0.0, "HGHT": -0.875}, "point_size": 1000}
        row = {"status": "COMPLETE", "requested_axes": request["axes"], "point_size": 1000,
               "upem": 1000, "witness_path": {"geometric_bounds_xywh": [100, -180, 600, 1000]}}
        result = b1.infer_witness_axes(row, request, "phantom_only")
        self.assertFalse(result["HGHT"]["available"])
        self.assertTrue(result["HGHT"]["fixed_top_and_bottom_exact"])
        self.assertIsNone(result["all_axes_exact_match"])
        self.assertNotIn("from_top_exact", result["HGHT"])


if __name__ == "__main__":
    unittest.main()
