"""B1 evidence-integrity tests using fabricated records, never native claims."""
from copy import deepcopy
from fractions import Fraction
import json
import math
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from b1_metric_discriminator import (
    RAW_STATUS, load_native_json, measured, observe, summarize, validate_raw, verify_bits, verify_replay,
)
from b1_metric_fixture import fixture_requests


def record_bits(value, path="$", result=None):
    """Test serializer's declared Double provenance, independent of validator."""
    if result is None: result = {}
    if type(value) is float:
        result[path] = struct.pack(">d", value).hex()
    elif isinstance(value, dict):
        for key, item in value.items(): record_bits(item, path + "." + key, result)
    elif isinstance(value, list):
        for index, item in enumerate(value): record_bits(item, f"{path}[{index}]", result)
    return result


def example_report(height=849.0, count=1, variant="gvar"):
    """Shape-matched synthetic evidence; no subprocess or CoreText invoked."""
    entry = {"fixture_id": "upem1000-" + variant, "upem": 1000, "variant": variant,
             "phantom_shift": 0, "sha256": "a"*64, "table_sha256": {"head": "b"*64}}
    all_requests = fixture_requests(1000, variant)
    source = next(r for r in all_requests if r["axes"] == {"WDTH": 0.0, "HGHT": -1.0})
    requests, rows = [], []
    for index in range(count):
        request = deepcopy(source)
        request["id"] += f"-record{index}"
        request["point_size"] = float(request["point_size"])
        requests.append(request)
        identity = {"all_source_tables_verified": True, "axes_size_and_matrix_verified": True,
                    "verified_table_sha256": deepcopy(entry["table_sha256"])}
        bounds = request["expected"]["witness_bounds"]
        row = {"id": request["id"], "status": "COMPLETE", "requested_axes": deepcopy(request["axes"]),
               "point_size": 1000.0, "upem": 1000, "nominal_glyph_id": 2,
               "font_identity": deepcopy(identity),
               "direct_advances": {"vertical_vector": [float(height), 0.0], "vertical_sum": float(height),
                                    "horizontal_vector": [1000.0, 0.0], "horizontal_sum": 1000.0},
               "vertical_translation": {"raw_vector": [-500.0, -760.0]},
               "witness_path": {"geometric_bounds_xywh": list(bounds),
                                "commands": [["moveTo", 100.0, -90.0], ["lineTo", 700.0, 760.0]]},
               "vertical_layout": {
                   "both_nominal_glyphs_and_all_source_tables_verified": True,
                   "glyphs": [{"glyph_id": 2, "string_index": n, "line": 0, "run": 0,
                               "position": [0.0, -float(height)*n]} for n in (0, 1)],
                   "runs": [{"font_identity": deepcopy(identity)}]},
               "global_font_metrics": {"ascent": 800.0, "descent": 200.0, "leading": 0.0},
               "cgfont_horizontal_auxiliary": {"advance_int32": 1000, "orientation": "horizontal_only"}}
        rows.append(row)
    report = {"status": RAW_STATUS, "backend": "CoreText_B1_independent_diagnostic_only",
              "source_unchanged_after_measurement": True,
              "source": {"sha256": entry["sha256"], "upem": 1000, "glyph_count": 3,
                         "table_sha256": deepcopy(entry["table_sha256"])},
              "completed_request_count": count, "expected_request_count": count, "observations": rows}
    report["binary64_hex_by_json_path"] = record_bits(report)
    return entry, requests, report


def reverse_report(report):
    reversed_report = deepcopy(report)
    del reversed_report["binary64_hex_by_json_path"]
    reversed_report["observations"].reverse()
    reversed_report["binary64_hex_by_json_path"] = record_bits(reversed_report)
    return reversed_report


class B1DiscriminatorTests(unittest.TestCase):
    def test_raw_decimal_and_binary64_survive_json_roundtrip(self):
        entry, requests, report = example_report(849.9908447265625)
        encoded = json.dumps(report, allow_nan=False)
        decoded = json.loads(encoded)
        result = validate_raw(decoded, entry, requests)
        self.assertEqual(result["records"], 1)
        self.assertGreater(result["binary64_values_verified"], 8)
        self.assertEqual(decoded["observations"][0]["direct_advances"]["vertical_vector"][0], 849.9908447265625)

    def test_required_raw_bit_provenance_cannot_be_removed(self):
        for suffix in ("point_size", "direct_advances.vertical_vector[0]",
                       "vertical_translation.raw_vector[1]", "witness_path.geometric_bounds_xywh[3]"):
            with self.subTest(suffix=suffix):
                _, _, report = example_report()
                del report["binary64_hex_by_json_path"]["$.observations[0]." + suffix]
                with self.assertRaisesRegex(ValueError, "required_raw_scalar_bits_missing"):
                    verify_bits(report)

    def test_missing_whole_bit_map_is_rejected(self):
        _, _, report = example_report()
        del report["binary64_hex_by_json_path"]
        with self.assertRaisesRegex(ValueError, "native_binary64_map_missing"):
            verify_bits(report)

    def test_identical_missing_layout_path_or_global_bits_still_fail_completeness(self):
        for suffix in ("vertical_layout.glyphs[1].position[1]", "witness_path.commands[0][1]",
                       "global_font_metrics.ascent"):
            with self.subTest(suffix=suffix):
                _, _, forward = example_report()
                reverse = reverse_report(forward)
                path = "$.observations[0]." + suffix
                for report in (forward, reverse):
                    del report["binary64_hex_by_json_path"][path]
                # Two identically incomplete records can replay exactly; that
                # equality cannot substitute for independent evidence admission.
                self.assertEqual(verify_replay(forward, reverse), 1)
                for report in (forward, reverse):
                    with self.assertRaisesRegex(ValueError, "required_raw_scalar_bits_missing"):
                        verify_bits(report)

    def test_altered_scalar_or_forged_bits_are_rejected(self):
        _, _, report = example_report()
        report["observations"][0]["direct_advances"]["vertical_vector"][0] = 850.0
        with self.assertRaisesRegex(ValueError, "did_not_roundtrip"):
            verify_bits(report)
        _, _, report = example_report()
        report["binary64_hex_by_json_path"]["$.observations[0].point_size"] = struct.pack(">d", 1001.0).hex()
        with self.assertRaisesRegex(ValueError, "did_not_roundtrip"):
            verify_bits(report)
        _, _, report = example_report()
        report["binary64_hex_by_json_path"]["$.observations[0].point_size"] = "not-hex"
        with self.assertRaisesRegex(ValueError, "bad_native_binary64_bits"):
            verify_bits(report)

    def test_nonfinite_raw_values_never_enter_evidence(self):
        for value in (math.nan, math.inf, -math.inf, True):
            with self.subTest(value=value):
                _, _, report = example_report()
                report["observations"][0]["direct_advances"]["vertical_vector"][0] = value
                with self.assertRaisesRegex(ValueError, "finite_native_number_required"):
                    verify_bits(report)

    def test_negative_zero_raw_bits_are_retained(self):
        record = measured(-0.0, 1000, 1000.0)
        self.assertEqual(record["raw_binary64_hex"], "8000000000000000")
        self.assertEqual(record["raw_exact"]["numerator"], 0)
        self.assertFalse(record["rounding_applied"])

    def test_native_json_integer_spelling_of_negative_zero_keeps_ieee_sign(self):
        entry, requests, report = example_report()
        report["observations"][0]["direct_advances"]["vertical_vector"][1] = -0.0
        del report["binary64_hex_by_json_path"]
        report["binary64_hex_by_json_path"] = record_bits(report)
        # Swift JSONEncoder can emit typed Double(-0.0) as the token -0.
        wire_text = json.dumps(report, allow_nan=False).replace("-0.0", "-0")
        decoded = load_native_json(wire_text)
        value = decoded["observations"][0]["direct_advances"]["vertical_vector"][1]
        self.assertEqual(struct.pack(">d", value).hex(), "8000000000000000")
        self.assertEqual(validate_raw(decoded, entry, requests)["records"], 1)
        with self.assertRaisesRegex(ValueError, "did_not_roundtrip"):
            verify_bits(json.loads(wire_text))
        ordinary = load_native_json('{"negative_integer": -7, "zero_integer": 0}')
        self.assertIs(type(ordinary["negative_integer"]), int)
        self.assertIs(type(ordinary["zero_integer"]), int)

    def test_unit_conversion_uses_exact_raw_rational_once(self):
        record = measured(0.1, 1000, 3.0)
        exact = Fraction(0.1) * 1000 / 3
        reconstructed = Fraction(record["design_units_exact"]["numerator"], record["design_units_exact"]["denominator"])
        self.assertEqual(reconstructed, exact)
        self.assertNotEqual(reconstructed, Fraction(0.1 * 1000 / 3))
        self.assertEqual(record["conversion"]["numerator_upem"], 1000)
        self.assertEqual(record["conversion"]["denominator_point_size_exact"]["value"], 3.0)
        self.assertFalse(record["rounding_applied"])

    def test_invalid_unit_basis_is_rejected(self):
        for upem, size in ((0, 1000), (-1, 1000), (1000.0, 1000), (True, 1000), (1000, 0), (1000, -1), (1000, math.inf)):
            with self.subTest(upem=upem, size=size), self.assertRaises(ValueError):
                measured(850.0, upem, size)

    def test_reverse_process_replay_ignores_order_but_covers_every_field(self):
        entry, requests, report = example_report(count=2)
        reverse = reverse_report(report)
        self.assertEqual(validate_raw(reverse, entry, list(reversed(requests)))["records"], 2)
        self.assertEqual(verify_replay(report, reverse), 2)
        for key, mutate in (
            ("path", lambda r: r["observations"][0]["witness_path"]["commands"][0].__setitem__(1, 101.0)),
            ("layout", lambda r: r["observations"][0]["vertical_layout"]["glyphs"][1]["position"].__setitem__(1, -848.0)),
            ("missing", lambda r: r["observations"][0].pop("cgfont_horizontal_auxiliary")),
            ("added", lambda r: r["observations"][0].__setitem__("new_observation", 1.0)),
        ):
            with self.subTest(field=key):
                changed = deepcopy(reverse)
                mutate(changed)
                with self.assertRaisesRegex(ValueError, "native_reverse_process_replay_changed"):
                    verify_replay(report, changed)

    def test_replay_rejects_lost_request_or_binary64_provenance(self):
        _, _, forward = example_report(count=2)
        reverse = reverse_report(forward)
        reverse["observations"].pop()
        with self.assertRaisesRegex(ValueError, "native_replay_id_set_mismatch"):
            verify_replay(forward, reverse)
        reverse = reverse_report(forward)
        del reverse["binary64_hex_by_json_path"]["$.observations[0].vertical_layout.glyphs[1].position[1]"]
        with self.assertRaisesRegex(ValueError, "native_reverse_process_replay_changed"):
            verify_replay(forward, reverse)

    def test_source_fallback_duplicate_and_incomplete_records_fail_validation(self):
        for problem in ("source", "fallback", "duplicate", "incomplete"):
            with self.subTest(problem=problem):
                entry, requests, report = example_report(count=2)
                if problem == "source": report["source"]["glyph_count"] = 47102
                if problem == "fallback": report["observations"][0]["vertical_layout"]["runs"][0]["font_identity"]["verified_table_sha256"] = {"head": "c"*64}
                if problem == "duplicate": report["observations"][1]["id"] = report["observations"][0]["id"]
                if problem == "incomplete": report["status"] = "B1_DISCRIMINATOR_FAILED"
                with self.assertRaises(ValueError): validate_raw(report, entry, requests)

    def test_complete_diagnosis_with_correct_witness_still_retains_849_failure(self):
        entry, requests, report = example_report(height=849.0)
        self.assertEqual(validate_raw(report, entry, requests)["records"], 1)
        observation = observe(entry, requests[0], report["observations"][0])
        self.assertTrue(observation["witness_pass"])
        self.assertTrue(observation["layout_step_equals_direct_height"])
        self.assertFalse(observation["strict_metrics_pass"])
        self.assertEqual(observation["strict_metric_comparisons"]["advance_height"]["signed_error_design_units"], -1)
        summary = summarize([observation])[entry["fixture_id"]]
        self.assertEqual(summary["strict_metric_failures"], 1)
        self.assertEqual(summary["witness_failures"], 0)
        self.assertEqual(summary["layout_vs_direct_disagreements"], 0)

    def test_fixed_outline_control_is_compared_with_its_own_model(self):
        entry, requests, report = example_report(height=850.0, variant="phantom_only")
        observation = observe(entry, requests[0], report["observations"][0])
        self.assertTrue(observation["witness_pass"])
        self.assertTrue(observation["strict_metrics_pass"])
        self.assertEqual(observation["witness_bounds"][3]["design_units"], 1000)
        self.assertEqual(observation["measured_design_units"]["advance_height"], 850)

    def test_holdout_failure_is_counted_separately_from_training(self):
        entry, requests, report = example_report(height=849.0)
        training = observe(entry, requests[0], report["observations"][0])
        holdout = deepcopy(training)
        holdout["partition"], holdout["request_id"] = "holdout", "independent-heldout-record"
        summary = summarize([training, holdout])[entry["fixture_id"]]
        self.assertEqual(summary["strict_metric_failures"], 2)
        self.assertEqual(summary["partitions"]["training"]["strict_metric_failures"], 1)
        self.assertEqual(summary["partitions"]["holdout"]["strict_metric_failures"], 1)
        self.assertEqual(summary["hypotheses"]["difference_first_em16_then_trunc"], {"training_matches": 1, "holdout_matches": 1})


if __name__ == "__main__":
    unittest.main()
