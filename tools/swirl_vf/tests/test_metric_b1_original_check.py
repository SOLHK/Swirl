"""Original B1 boundary tests; no Apple font data and no claimed native run."""
import copy
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import b1_original_metric_check as b1


def native_record(**changes):
    record = {"error": None, "advance_width": 800.0, "advance_height": 1000.0,
              "lsb": 70.0, "horizontal_origin_x": 0.0, "horizontal_origin_y": 0.0,
              "vertical_origin_x": 400.0, "vertical_origin_y": 850.0,
              "horizontal_advance_sum": 800.0, "vertical_advance_sum": 1000.0,
              "horizontal_advance_vector": [800.0, 0.0], "vertical_advance_vector": [1000.0, 0.0],
              "vertical_origin_translation": [-400.0, -850.0]}
    record.update(changes)
    return record


def stored_reference():
    return {"units": "serialized_font_design_units", "hmtx": {"advance_width": 1000, "lsb": 70},
            "vmtx": {"advance_height": 1000, "top_side_bearing": 200},
            "VORG": {"present": True, "default_y": 850, "glyph_y": 850, "explicit_glyph_override": False}}


class NodeFont(dict):
    def __init__(self, maps=None):
        super().__init__()
        self["fvar"] = SimpleNamespace(axes=[
            SimpleNamespace(axisTag="WDTH", minValue=1, defaultValue=501, maxValue=1000),
            SimpleNamespace(axisTag="wght", minValue=100, defaultValue=501, maxValue=900),
            SimpleNamespace(axisTag="HGHT", minValue=1, defaultValue=500, maxValue=1000)])
        self.reader = {}
        if maps is not None:
            self["avar"] = object()
            data = struct.pack(">4H", 1, 0, 0, 3)
            for records in maps:
                data += struct.pack(">H", len(records))
                data += b"".join(struct.pack(">hh", a, b) for a, b in records)
            self.reader["avar"] = data


IDENTITY = [(-16384, -16384), (0, 0), (16384, 16384)]


class B1OriginalMetricCheckTests(unittest.TestCase):
    def test_numeric_whitelist_discards_outline_bounds_paths_and_untrusted_nested_payloads(self):
        original = native_record(commands=[["PRIVATE_OUTLINE_SENTINEL"]],
                                 bounds=[1, 2, 3, 4], source_path="/private/secret",
                                 arbitrary={"advance_width": "PRIVATE_OUTLINE_SENTINEL"})
        actual = b1.metric_whitelist(original)
        self.assertEqual(set(actual), set(b1.SCALARS) | set(b1.VECTORS))
        self.assertNotIn("PRIVATE", json.dumps(actual))
        self.assertNotIn("bounds", actual)
        self.assertNotIn("commands", actual)
        actual["vertical_advance_vector"][0] = -3
        self.assertEqual(original["vertical_advance_vector"], [1000.0, 0.0])

    def test_whitelist_rejects_bool_nonfinite_missing_and_incomplete_vectors(self):
        for changes in ({"advance_height": True}, {"lsb": float("nan")},
                        {"advance_width": float("inf")}, {"advance_height": 10**10000},
                        {"vertical_advance_vector": [1000]},
                        {"vertical_origin_translation": [-400, "PRIVATE"]},
                        {"error": "PRIVATE failure payload"}):
            with self.subTest(fields=list(changes)), self.assertRaises(ValueError):
                b1.metric_whitelist(native_record(**changes))
        missing = native_record()
        del missing["horizontal_advance_sum"]
        with self.assertRaises(ValueError):
            b1.metric_whitelist(missing)

    def test_production_gate_rejects_both_signs_of_100_unit_vertical_x_offset(self):
        for shift in (-100, 100):
            record = native_record(vertical_origin_x=400 + shift)
            outcome = b1.representation_check(record, (1000, 70), (1000, 200))
            self.assertFalse(outcome["passed"])
            self.assertEqual(outcome["absolute_error_font_units"], 100)
            self.assertEqual(outcome["tolerance_font_units"], 1e-5)

    def test_matching_stored_half_width_does_not_override_production_failure(self):
        record = native_record(vertical_origin_x=500)
        before = copy.deepcopy(record)
        report = b1.observation(record, stored_reference(), native_record(), None,
                                {"available": False, "reason": "nonidentity_anchor"})
        self.assertEqual(report["vertical_x_candidates"]["half_stored_hmtx_advance"][
            "native_minus_prediction_font_units"], 0)
        self.assertFalse(report["production_representation"]["passed"])
        self.assertFalse(report["strict_source_table_comparison"]["passed"])
        self.assertEqual(record, before)

    def test_binary64_hex_is_exact_big_endian_bits_including_signed_zero(self):
        record = native_record(horizontal_origin_y=-0.0)
        row = b1.observation(record, stored_reference(), native_record(), None, {"available": False})
        bits = row["native_scalar_binary64_hex"]
        self.assertEqual(bits["advance_width"], "4089000000000000")
        self.assertEqual(bits["vertical_origin_x"], "4079000000000000")
        self.assertEqual(bits["horizontal_origin_y"], "8000000000000000")
        self.assertTrue(all(len(value) == 16 for value in bits.values()))
        self.assertEqual(struct.unpack(">d", bytes.fromhex(bits["advance_width"]))[0], 800.0)

    def test_public_ci_summary_retains_all_safe_row_evidence_and_omits_private_payloads(self):
        row = b1.observation(native_record(), stored_reference(), native_record(), None,
                             {"available": False, "reason": "nonidentity_anchor"})
        row.update(face_index=15, glyph_id=5, case="default", user_location={"WDTH": 501, "wght": 501, "HGHT": 500},
                   commands=["PRIVATE_OUTLINE_SENTINEL"], bounds=[1, 2, 3, 4])
        row["native_metrics"]["commands"] = ["PRIVATE_NESTED_NATIVE_SENTINEL"]
        row["native_scalar_binary64_hex"]["advance_width"] = "PRIVATE_HEX_SENTINEL"
        report = {"status": "STRICT_ORIGINAL_METRIC_CHECK_FAILED", "diagnostics_complete": True,
                  "native_finalization": {"request_count": 15, "successful_glyph_count": 60},
                  "strict_metric_failures": 0, "reference_unavailable_count": 60, "representation_failures": 4,
                  "physical_faces_verified": 32, "source_sha256": "a" * 64, "native_binary_sha256": "b" * 64,
                  "original_font_accepted": False, "original_faces_reconstructed": 0, "observations": [row],
                  "physical_face_identities": [{"private": "PRIVATE_TABLE_SENTINEL"}],
                  "started_utc": "PRIVATE_TIME_SENTINEL", "private_payload": "PRIVATE_TOP_SENTINEL"}
        saved = b1.public_log_summary(report)
        self.assertNotIn("PRIVATE", json.dumps(saved))
        self.assertNotIn("physical_face_identities", saved)
        self.assertEqual(saved["physical_faces_verified"], 32)
        self.assertEqual(saved["reference_unavailable_count"], 60)
        actual = saved["observations"][0]
        for key in ("stored_metrics", "vertical_x_candidates", "strict_source_table_comparison", "production_representation"):
            self.assertEqual(actual[key], row[key])
        self.assertEqual(actual["native_scalar_binary64_hex"]["advance_width"], "4089000000000000")
        self.assertFalse(saved["original_font_accepted"])
        self.assertEqual(saved["original_faces_reconstructed"], 0)

    def test_production_gate_accepts_correct_half_current_width_and_preserves_tight_budget(self):
        self.assertTrue(b1.representation_check(native_record(), (1000, 70), (1000, 200))["passed"])
        self.assertFalse(b1.representation_check(native_record(vertical_origin_x=400.001),
                                                (1000, 70), (1000, 200))["passed"])

    def test_849_850_remains_a_strict_failure_and_no_rounding_is_applied(self):
        reference = {field: native_record()[field] for field in b1.REFERENCE_FIELDS}
        reference["advance_height"] = 850.0
        result = b1.strict_comparison(native_record(advance_height=849), reference)
        self.assertEqual(result["signed_errors_font_units"]["advance_height"], -1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["failing_fields"], ["advance_height"])
        self.assertEqual(result["tolerance_font_units"], 1 / 32)
        fractional = b1.strict_comparison(native_record(advance_height=849.9908447265625), reference)
        self.assertEqual(fractional["signed_errors_font_units"]["advance_height"], -0.0091552734375)
        self.assertTrue(fractional["passed"])

    def test_metric_budget_boundary_is_unchanged(self):
        reference = {field: native_record()[field] for field in b1.REFERENCE_FIELDS}
        self.assertTrue(b1.strict_comparison(native_record(advance_height=1000 + 1/32), reference)["passed"])
        self.assertFalse(b1.strict_comparison(native_record(advance_height=1000 + 1/16), reference)["passed"])

    def test_fvar_defaults_and_endpoints_are_read_not_assumed(self):
        cases = b1.fixed_cases(NodeFont())
        self.assertEqual([row[0] for row in cases], ["default", "WDTH_min", "WDTH_max", "HGHT_min", "HGHT_max"])
        self.assertEqual(cases[0][1], {"WDTH": 501.0, "wght": 501.0, "HGHT": 500.0})
        self.assertEqual(cases[1][1], {"WDTH": 1.0, "wght": 501.0, "HGHT": 500.0})
        self.assertEqual(cases[3][2], {"WDTH": 0.0, "wght": 0.0, "HGHT": -1.0})
        self.assertTrue(all(row[2]["wght"] == 0 for row in cases))

    def test_default_nonzero_avar_target_is_not_silently_forced_to_zero(self):
        maps = [IDENTITY, [(-16384, -16384), (0, 100), (16384, 16384)], IDENTITY]
        result = b1.endpoint_reference_basis(NodeFont(maps), dict.fromkeys(b1.TAGS, 0.0))
        self.assertFalse(result["available"])
        self.assertEqual(result["anchor_checks"][1]["raw_target_f2dot14"], [100])
        self.assertNotIn("normalized_design_location", result)

    def test_duplicate_or_missing_requested_avar_anchor_stays_unavailable(self):
        for records in ([(-16384, -16384), (0, 100), (0, 0), (16384, 16384)],
                        [(-16384, -16384), (16384, 16384)]):
            result = b1.endpoint_reference_basis(NodeFont([IDENTITY, records, IDENTITY]),
                                                  dict.fromkeys(b1.TAGS, 0.0))
            self.assertFalse(result["available"])
        good = b1.endpoint_reference_basis(NodeFont([IDENTITY] * 3),
                                           {"WDTH": -1.0, "wght": 0.0, "HGHT": 1.0})
        self.assertTrue(good["available"])
        self.assertFalse(good["CoreText_mapping_equivalence_claimed"])

    def test_reference_refuses_interior_axis_mapping(self):
        with self.assertRaises(ValueError):
            b1.endpoint_reference_basis(NodeFont(), {"WDTH": .5, "wght": 0, "HGHT": 0})

    def report_and_summary(self, failed=True):
        report = {"source_sha256": "a" * 64, "diagnostics_complete": False,
                  "original_font_accepted": False, "original_faces_reconstructed": 0,
                  "observations": [{"strict_source_table_comparison": {"passed": not failed},
                                    "production_representation": {"passed": not failed}}]}
        summary = {"type": "summary", "source_sha256": "a" * 64, "request_count": 1,
                   "successful_glyph_count": 1, "error_count": 0, "verified_batch_count": 1,
                   "source_unchanged": True, "axis_verification_backend": b1.BACKEND}
        return report, summary

    def test_complete_protocol_can_remain_red_after_metric_failure(self):
        report, summary = self.report_and_summary()
        oracle = Mock()
        oracle.finish.return_value = summary
        self.assertEqual(b1.finish_observations(report, oracle, 1, 1), 1)
        oracle.finish.assert_called_once_with()
        self.assertTrue(report["diagnostics_complete"])
        self.assertEqual(report["status"], "STRICT_ORIGINAL_METRIC_CHECK_FAILED")
        self.assertEqual(report["representation_failures"], 1)
        self.assertFalse(report["original_font_accepted"])
        self.assertEqual(report["original_faces_reconstructed"], 0)

    def test_bad_summary_or_failed_eof_exit_never_grants_diagnostic_completion(self):
        report, summary = self.report_and_summary(False)
        oracle = Mock()
        oracle.finish.side_effect = b1.rebuild.ReconstructionError("native oracle failed after its final glyph")
        with self.assertRaises(b1.rebuild.ReconstructionError):
            b1.finish_observations(report, oracle, 1, 1)
        self.assertFalse(report["diagnostics_complete"])
        oracle.finish.side_effect = None
        summary["successful_glyph_count"] = 0
        oracle.finish.return_value = summary
        with self.assertRaises(b1.rebuild.ReconstructionError):
            b1.finish_observations(report, oracle, 1, 1)
        self.assertFalse(report["diagnostics_complete"])

    def test_successful_finite_sample_never_accepts_or_reconstructs_original(self):
        report, summary = self.report_and_summary(False)
        oracle = Mock()
        oracle.finish.return_value = summary
        self.assertEqual(b1.finish_observations(report, oracle, 1, 1), 0)
        self.assertEqual(report["status"], "FINITE_SAMPLE_CHECKS_PASS_NOT_ORIGINAL_ACCEPTANCE")
        self.assertFalse(report["original_font_accepted"])
        self.assertEqual(report["original_faces_reconstructed"], 0)

    def test_unavailable_reference_is_not_reported_as_measured_metric_difference(self):
        report, summary = self.report_and_summary(False)
        report["observations"][0]["strict_source_table_comparison"] = {
            "passed": False, "status": "REFERENCE_UNAVAILABLE_NOT_ACCEPTED"}
        oracle = Mock()
        oracle.finish.return_value = summary
        self.assertEqual(b1.finish_observations(report, oracle, 1, 1), 1)
        self.assertEqual(report["strict_metric_failures"], 0)
        self.assertEqual(report["reference_unavailable_count"], 1)
        self.assertFalse(report["original_font_accepted"])


if __name__ == "__main__":
    unittest.main()
