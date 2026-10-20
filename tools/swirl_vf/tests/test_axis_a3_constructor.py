"""Fail-closed generation contracts for A3, separate from native acceptance.

These tests perturb reviewed inputs and transport anchors, rather than claiming
that compiling a string proves any CoreText behavior. The unchanged Swift
scalar helper and full generated harness are executed by the dedicated macOS CI.
"""
from fractions import Fraction
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import unittest
from unittest.mock import patch

PLATFORM = Path(__file__).resolve().parents[1] / "platform"
sys.path.insert(0, str(PLATFORM))
import axis_a3_constructor_harness as a3
import anchor_construction_harness as anchor
from compare_axis_construction import EXPECTED, GUARD
from axis_a3_input_cases import fixed16_input
from probe_axis_a3_construction import (check_scalar_report, compare_records,
                                       diagnostic_failure, submitted_location)
from rebuild import ReconstructionError
from test_verified_axis_oracle import native_record


class AxisA3ConstructorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (PLATFORM / "coretext_extract.swift").read_text(encoding="utf-8")
        cls.generated = a3.make_harness(cls.source)
        cls.anchor_generated = anchor.make_harness(cls.source)

    def test_identity_extraction_strict_guard_and_transport_are_byte_preserved(self):
        prefix = self.source.split("\nfunc run() throws {")[0]
        self.assertEqual(hashlib.sha256(prefix.encode()).hexdigest(), anchor.REVIEWED_PRODUCTION_PREFIX_SHA256)
        self.assertEqual(self.generated[:len(prefix)], prefix)
        self.assertEqual(self.generated.count(GUARD), 1)
        for function in ("constructInstance", "makeInstance", "validateReportedAxes", "locateDescriptors",
                         "extractGlyph", "a3Mode", "a3Alternative", "a3Instance", "a3ScalarMain", "run"):
            self.assertEqual(self.generated.count(f"func {function}("), 1, function)
        # The complete post-construction loop includes exception accounting,
        # summary, EOF and exit behavior. It is not rewritten by A3.
        extraction = "            for glyph in request.glyph_ids {"
        self.assertEqual(self.generated.split(extraction)[1], self.source.split(extraction)[1])
        self.assertEqual(self.generated, a3.make_harness(self.source))

    def test_a_changed_constructor_body_or_identity_guard_cannot_silently_rebind(self):
        mutations = (
            self.source.replace('let opticalSize = location["opsz"]', 'let opticalSize = location["xxxx"]', 1),
            self.source.replace("func verifyIdentity(", "func changedVerifyIdentity(", 1),
            self.source.replace(GUARD, "", 1),
            "// changed production prefix\n" + self.source,
        )
        for source in mutations:
            self.assertTrue(source != self.source, "test mutation did not touch the production prefix")
            with self.subTest(length=len(source)), self.assertRaises(ValueError):
                a3.make_harness(source)

    def test_already_generated_sources_are_rejected_instead_of_nested(self):
        with self.assertRaisesRegex(ValueError, "a3_refuses_already_generated_harness"):
            a3.make_harness(self.generated)
        with self.assertRaises(ValueError):
            a3.make_harness(self.anchor_generated)

    def test_upstream_dispatch_missing_or_duplicated_anchors_fail_closed(self):
        anchors = (
            "    let mode = try anchorMode()",
            "    let states = try anchorPrepareStates(locateDescriptors(rawFaces, url: url), mode)",
            '"anchor_mode": mode, "diagnostic_readback_observation_only": true,',
            '"NOT_ACCEPTED_diagnostic_anchor_construction_only"',
            "            let (font, location, reported) = try anchorInstance(state, request.location, mode)",
        )
        for token in anchors:
            for changed in (self.anchor_generated.replace(token, "", 1), self.anchor_generated + "\n" + token):
                with self.subTest(token=token), patch.object(anchor, "make_harness", return_value=changed):
                    with self.assertRaisesRegex(ValueError, "a3_review_changed_native_dispatch"):
                        a3.make_harness(self.source)

    def test_upstream_attempt_to_remove_diagnostic_marker_is_rejected(self):
        changed = self.anchor_generated.replace('"diagnostic_readback_observation_only": true',
                                                '"diagnostic_readback_observation_only": false', 1)
        with patch.object(anchor, "make_harness", return_value=changed):
            with self.assertRaisesRegex(ValueError, "a3_review_changed_native_dispatch"):
                a3.make_harness(self.source)
        changed = self.anchor_generated.replace("import Foundation", "import Other", 1)
        with patch.object(anchor, "make_harness", return_value=changed):
            with self.assertRaisesRegex(ValueError, "a3_production_prefix_not_preserved"):
                a3.make_harness(self.source)

    def test_number_modes_are_allowlisted_and_covered_by_explicit_dispatch(self):
        mode_helper = self.generated.split("\nfunc a3Mode() throws -> String {")[1].split("\nfunc a3Alternative(")[0]
        matched = re.search(r"let allowed = Set\((\[.*\])\)", mode_helper)
        self.assertIsNotNone(matched)
        allowed = json.loads(matched.group(1))
        self.assertEqual(allowed, list(a3.MODES))
        self.assertEqual(len(allowed), len(set(allowed)))
        self.assertEqual(len(allowed), 9)
        instance = self.generated.split("\nfunc a3Instance(")[1].split("\nfunc a3ScalarMain(")[0]
        dispatched = []
        for line in instance.splitlines():
            if line.strip().startswith("case "):
                dispatched.extend(re.findall(r'"([a-zA-Z0-9_]+)"', line))
        self.assertCountEqual(dispatched, allowed)
        self.assertIn("allowed.contains(mode)", mode_helper)
        self.assertIn('throw OracleError.invalid("a3_constructor_mode_missing_or_unknown")', instance)

    def test_font_requests_remain_diagnostic_and_scalar_mode_is_font_free(self):
        run = self.generated.split("\nfunc run() throws {")[1]
        scalar_position = run.index('CommandLine.arguments[1] == "--a3-scalars"')
        self.assertLess(scalar_position, run.index("let mode = try a3Mode()"))
        self.assertLess(scalar_position, run.index("Data(contentsOf: url"))
        self.assertIn("try a3ScalarMain(); return", run)
        self.assertIn(f'guard sha256(data) == "{EXPECTED}"', run)
        self.assertIn('"diagnostic_readback_observation_only": true', run)
        self.assertIn('"axis_observations_only": false', run)
        self.assertIn('"NOT_ACCEPTED_A3_input_construction_only"', run)
        self.assertNotIn("try makeInstance(", run)
        scalar = self.generated.split("\nfunc a3ScalarMain() throws {")[1].split("\nfunc run() throws {")[0]
        for forbidden in ("Data(contentsOf:", "CTFont", "locateDescriptors", "parseFaces", "source_sha256"):
            self.assertNotIn(forbidden, scalar)
        self.assertIn("values.count <= 10000", scalar)

    def test_exact_half_cell_controls_distinguish_floor_fraction_from_add_half(self):
        # This is an independent numeric contract test, not Swift execution.
        # It demonstrates why the generated helper splits integral/fractional
        # parts before rounding. The near-half input genuinely breaks x+0.5.
        below = math.nextafter(1 / 131072, -math.inf)
        self.assertEqual(fixed16_input(below), 0)
        self.assertEqual(math.floor(below * 65536 + .5), 1)
        values = (below, 1 / 131072, math.nextafter(1 / 131072, math.inf),
                  -1 / 131072, math.nextafter(-1 / 131072, -math.inf),
                  -32768., 32767 + 65535 / 65536, 499.006199, 499.006201)
        for value in values:
            scaled = value * 65536
            integral = math.floor(scaled)
            split_result = integral + int(scaled - integral >= .5)
            rational_result = math.floor(Fraction.from_float(value) * 65536 + Fraction(1, 2))
            self.assertEqual(split_result, rational_result)


def authored_records():
    request = {"request_id": "authored_a3_request", "face_index": 15,
               "location": {"WDTH": 500., "wght": 499.006199, "HGHT": 500.}}
    rows = {gid: native_record(request, gid) for gid in (0, 1)}
    # The preserved-Q comparator deliberately rejects arbitrary cubic
    # correspondence. Author a quadratic here; keep the second glyph blank.
    rows[0]["commands"] = [["moveTo", 0., 0.], ["qCurveTo", 2., 4., 5., 0.], ["closePath"]]
    rows[0]["bounds"] = [0., 0., 5., 2.]
    return rows


def authored_scalar_report(values):
    """Protocol double authored from IEEE packing, not claimed native output."""
    rows = []
    for value in values:
        value = float(value)
        packed32 = struct.pack(">f", value)
        single = struct.unpack(">f", packed32)[0]
        fixed = math.floor(Fraction.from_float(value) * 65536 + Fraction(1, 2))
        def number(item):
            bits = struct.pack(">d", item).hex()
            return {"binary64_hex": bits, "cf_number_float64_binary64_hex": bits,
                    "cf_number_and_nsnumber_bits_equal": True,
                    "cf_number_float64_conversion_exact": True,
                    "objc_type": "d", "cf_number_byte_size": 8}
        rows.append({"binary64_bits": struct.pack(">d", value).hex(),
                     "float32_bits": packed32.hex(), "float32_value": single,
                     "fixed16_integer": fixed, "fixed16_value": fixed / 65536,
                     "NSNumber_double": number(value), "NSNumber_float": number(single)})
    return {"status": "NATIVE_SCALAR_REPRESENTATIONS_NOT_FONT_ACCEPTANCE", "records": rows,
            "CGFloat_bytes": 8, "Double_bytes": 8, "Float_bytes": 4,
            "test_only_authored_not_native": True}


class AxisA3DriverComparisons(unittest.TestCase):
    def test_different_request_locations_do_not_invent_a_payload_difference(self):
        left = authored_records(); right = deepcopy(left)
        for row in right.values():
            row["request_id"] = "another_authored_request"
            row["location"]["wght"] = 499.006201
        before = deepcopy((left, right))
        result = compare_records(left, right)
        self.assertEqual(result["glyph_count"], 2)
        self.assertEqual(result["payload_different_glyphs"], 0)
        self.assertEqual(result["maximum_advance_difference"], 0.)
        self.assertEqual((left, right), before)

    def test_unknown_payload_difference_is_detected_without_revealing_field_or_value(self):
        left = authored_records(); right = deepcopy(left)
        right[1]["PRIVATE_NEW_FIELD"] = "PRIVATE_A3_PAYLOAD_SENTINEL"
        result = compare_records(left, right)
        self.assertEqual(result["payload_different_glyphs"], 1)
        self.assertFalse(result["glyphs"][1]["payload_identical"])
        serialized = json.dumps(result)
        self.assertNotIn("PRIVATE_NEW_FIELD", serialized)
        self.assertNotIn("PRIVATE_A3_PAYLOAD_SENTINEL", serialized)
        self.assertNotIn('"commands"', serialized)
        self.assertNotIn('"location"', serialized)

    def test_readback_change_is_separate_from_unchanged_glyph_payload(self):
        left = authored_records(); right = deepcopy(left)
        right[0]["reported_location"]["wght"] = 499.0062
        result = compare_records(left, right)
        self.assertEqual(result["payload_different_glyphs"], 0)
        self.assertEqual(result["readback_different_glyphs"], 1)
        self.assertTrue(result["glyphs"][0]["raw_commands_identical"])

    def test_only_metric_differences_are_emitted_including_blank_glyphs(self):
        left = authored_records(); right = deepcopy(left)
        right[1]["advance_width"] += .125
        right[1]["vertical_origin_translation"][0] -= .0625
        right[0]["bounds"][2] += .03125
        result = compare_records(left, right)
        self.assertEqual(result["maximum_advance_difference"], .125)
        self.assertEqual(result["glyphs"][1]["metric_differences"]["vertical_origin_translation"], .0625)
        self.assertEqual(result["glyphs"][0]["metric_differences"]["bounds"], .03125)
        self.assertNotIn("432.5", json.dumps(result))
        self.assertEqual(result["payload_different_glyphs"], 2)

    def test_nonfinite_scalars_vectors_and_wrong_identity_fail_closed(self):
        mutations = (
            ("advance_width", math.nan), ("vertical_origin_y", math.inf),
            ("vertical_advance_sum", True), ("face_index", 16), ("glyph_id", 2),
            ("bounds", [0., 0., 0.]), ("horizontal_advance_vector", [math.nan, 0.]),
        )
        for field, value in mutations:
            left = authored_records(); right = deepcopy(left); right[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                compare_records(left, right)
        with self.assertRaisesRegex(ValueError, "a3_comparison_glyph_set_mismatch"):
            compare_records({}, {})
        with self.assertRaisesRegex(ValueError, "a3_comparison_glyph_set_mismatch"):
            compare_records(authored_records(), {0: authored_records()[0]})

    def test_submitted_coordinates_are_new_dicts_and_only_explicit_lossy_modes_quantize(self):
        location = {"WDTH": 500., "wght": 499.006199, "HGHT": 500.}
        before = deepcopy(location)
        for mode in a3.MODES:
            result = submitted_location(location, mode)
            self.assertIsNot(result, location)
            self.assertEqual(set(result), set(location))
            if mode in ("anchor_binary32", "copy_cfnumber_float32"):
                self.assertEqual(result["wght"], 499.006195068359375)
            elif mode == "anchor_fixed16":
                self.assertEqual(result["wght"], 32702870 / 65536)
            else:
                self.assertEqual(result, location)
        self.assertEqual(location, before)
        with self.assertRaisesRegex(ValueError, "a3_unknown_constructor_mode"):
            submitted_location(location, "typo_unknown_mode")
        with self.assertRaisesRegex(ValueError, "a3_complete_three_axes_required"):
            submitted_location({"wght": 499.006199}, "copy_binary64")


class AxisA3FailureEvidence(unittest.TestCase):
    def test_new_native_guard_codes_survive_request_and_startup_wrappers(self):
        # Use real transport exception objects and independently name the
        # guards. The expected result must not depend on the allowlist itself.
        codes = ("a3_value_outside_fixed16_range", "a3_nonfinite_input",
                 "a3_nonfinite_float32_input", "a3_constructor_mode_missing_or_unknown",
                 "a3_unverified_base", "a3_axis_missing", "a3_size_or_matrix_changed",
                 "a3_scalar_count_invalid")
        for prefix in ("native request 31 face 15 failed: ", "native oracle startup failed: "):
            for code in codes:
                with self.subTest(prefix=prefix, code=code):
                    error = ReconstructionError(prefix + code, native_observation={
                        "commands": [["moveTo", 1234.56789, 8765.4321]],
                        "advance_width": 432.5, "source": "PRIVATE_A3_SOURCE_SENTINEL"})
                    self.assertEqual(diagnostic_failure(error), {
                        "failure_type": "ReconstructionError", "native_failure_code": code})

    def test_upstream_named_native_and_local_failures_remain_classified(self):
        error = ReconstructionError("native request 1 face 15 failed: anchor_optical_inheritance_mismatch")
        self.assertEqual(diagnostic_failure(error), {
            "failure_type": "ReconstructionError", "native_failure_code": "anchor_optical_inheritance_mismatch"})
        self.assertEqual(diagnostic_failure(ValueError("a3_native_scalar_count_mismatch")), {
            "failure_type": "ValueError", "failure_code": "a3_native_scalar_count_mismatch"})

    def test_unknown_wrapped_codes_and_raw_payloads_are_not_published(self):
        messages = (
            "native request 1 face 15 failed: a3_future_unknown_code",
            "native oracle startup failed: a3_future_unknown_code",
            "native request 1 face 15 failed: a3_size_or_matrix_changed_extra",
            "native request 1 face 15 failed: a3_size_or_matrix_changed: 432.5",
            'native request 1 face 15 failed: {"advance_width":432.5,"commands":[["moveTo",1234.56789,8765.4321]]}',
            "native request 1 face 15 failed: a3_size_or_matrix_changed\nPRIVATE_A3_SOURCE_SENTINEL",
            "PRIVATE_A3_SOURCE_SENTINEL a3_size_or_matrix_changed",
            "native oracle startup failed: /private/PRIVATE_A3_SOURCE_SENTINEL.ttf",
        )
        for message in messages:
            with self.subTest(message=message):
                error = ReconstructionError(message, native_observation={"source": "PRIVATE_A3_SOURCE_SENTINEL"})
                self.assertEqual(diagnostic_failure(error), {"failure_type": "ReconstructionError"})


class AxisA3ScalarReportControls(unittest.TestCase):
    VALUES = (499.006199, 499.006201, -1.5 / 65536, .5 / 65536, 0., 500.)

    def test_packed_reference_controls_pass_without_assuming_nsnumber_objctype(self):
        report = authored_scalar_report(self.VALUES)
        # Positive integral values may be stored in an optimized integer form.
        for row in report["records"][-2:]:
            for name in ("NSNumber_double", "NSNumber_float"):
                row[name]["objc_type"] = "q"
                row[name]["cf_number_byte_size"] = 4
        result = check_scalar_report(self.VALUES, report)
        self.assertEqual(result["checked_values"], len(self.VALUES))
        self.assertTrue(result["all_python_reference_bits_match"])
        self.assertTrue(result["all_nonzero_input_bits_match"])
        self.assertEqual(result["signed_zero_storage_changes"], [])
        self.assertNotIn("actual_native_result", result)

    def test_single_bit_pollution_at_each_conversion_stage_is_rejected(self):
        for field in ("binary64_bits", "float32_bits"):
            report = authored_scalar_report(self.VALUES)
            bits = report["records"][0][field]
            report["records"][0][field] = f"{int(bits, 16) ^ 1:0{len(bits)}x}"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "a3_native_scalar_bits_or_values_mismatch"):
                check_scalar_report(self.VALUES, report)
        for object_key in ("NSNumber_double", "NSNumber_float"):
            for field in ("binary64_hex", "cf_number_float64_binary64_hex"):
                report = authored_scalar_report(self.VALUES)
                item = report["records"][0][object_key]
                item[field] = f"{int(item[field], 16) ^ 1:016x}"
                with self.subTest(object_key=object_key, field=field), self.assertRaisesRegex(ValueError, "a3_native_CFNumber_lost_input_bits"):
                    check_scalar_report(self.VALUES, report)

    def test_value_count_and_platform_contract_mismatches_are_rejected(self):
        report = authored_scalar_report(self.VALUES); report["records"].pop()
        with self.assertRaisesRegex(ValueError, "a3_native_scalar_count_mismatch"):
            check_scalar_report(self.VALUES, report)
        report = authored_scalar_report(self.VALUES); report["Float_bytes"] = 8
        with self.assertRaisesRegex(ValueError, "a3_native_scalar_platform_contract"):
            check_scalar_report(self.VALUES, report)
        for field, value in (("fixed16_integer", 32702871), ("fixed16_value", 500.), ("float32_value", 499.)):
            report = authored_scalar_report(self.VALUES); report["records"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "a3_native_scalar_bits_or_values_mismatch"):
                check_scalar_report(self.VALUES, report)

    def test_number_conversion_loss_boolean_cannot_be_silently_accepted(self):
        for field in ("cf_number_and_nsnumber_bits_equal", "cf_number_float64_conversion_exact"):
            report = authored_scalar_report(self.VALUES)
            report["records"][0]["NSNumber_double"][field] = False
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "a3_native_CFNumber_lost_input_bits"):
                check_scalar_report(self.VALUES, report)

    def test_negative_zero_storage_sign_loss_is_retained_as_a_distinct_nonexact_observation(self):
        report = authored_scalar_report((-0.,))
        self.assertTrue(check_scalar_report((-0.,), report)["all_python_reference_bits_match"])
        for key in ("NSNumber_double", "NSNumber_float"):
            item = report["records"][0][key]
            item["binary64_hex"] = item["cf_number_float64_binary64_hex"] = "0000000000000000"
        result = check_scalar_report((-0.,), report)
        self.assertFalse(result["all_python_reference_bits_match"])
        self.assertTrue(result["all_nonzero_input_bits_match"])
        self.assertTrue(result["raw_swift_conversion_bits_match"])
        self.assertEqual(len(result["signed_zero_storage_changes"]), 2)
        self.assertIn("WITH_SIGNED_ZERO_STORAGE_CHANGES", result["status"])
        self.assertEqual({x["number_object"] for x in result["signed_zero_storage_changes"]},
                         {"NSNumber_double", "NSNumber_float"})
        self.assertEqual(report["records"][0]["binary64_bits"], "8000000000000000")

    def test_zero_exception_cannot_mask_changed_swift_bits_or_contradictory_number_objects(self):
        report = authored_scalar_report((-0.,)); report["records"][0]["binary64_bits"] = "0000000000000000"
        with self.assertRaisesRegex(ValueError, "a3_native_scalar_bits_or_values_mismatch"):
            check_scalar_report((-0.,), report)
        report = authored_scalar_report((-0.,))
        report["records"][0]["NSNumber_double"]["binary64_hex"] = "0000000000000000"
        with self.assertRaisesRegex(ValueError, "a3_native_CFNumber_lost_input_bits"):
            check_scalar_report((-0.,), report)
        report = authored_scalar_report((0.,))
        for field in ("binary64_hex", "cf_number_float64_binary64_hex"):
            report["records"][0]["NSNumber_double"][field] = "8000000000000000"
        with self.assertRaisesRegex(ValueError, "a3_native_CFNumber_lost_input_bits"):
            check_scalar_report((0.,), report)


if __name__ == "__main__":
    unittest.main()
