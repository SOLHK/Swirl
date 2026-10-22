"""Independent submission-audit rejection tests; native font evidence is separate."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from axis_a3_arithmetic_harness import MODES, PREFIX, check_entry_audit, diagnostic_failure, make_harness
from probe_axis_anchor import bits


PLATFORM = Path(__file__).resolve().parents[1] / "platform"


class ArithmeticHarnessTests(unittest.TestCase):
    def setUp(self):
        self.plan = [{"request_id": "1", "face_index": 15,
                      "location": {"WDTH": 500., "wght": 499.006199, "HGHT": 500.}},
                     {"request_id": "2", "face_index": 15,
                      "location": {"WDTH": 500., "wght": 499.006201, "HGHT": 500.}}]
        self.rows = [{"request_id": r["request_id"], "face_index": r["face_index"],
                      "mode": MODES[0], "binary64_bits": bits(r["location"])} for r in self.plan]

    def text(self, rows):
        return "runtime note is private\n" + "".join(PREFIX + json.dumps(r) + "\n" for r in rows)

    def test_complete_input_audit_preserves_the_collision_pair_bits(self):
        result = check_entry_audit(self.text(self.rows), self.plan, MODES[0])
        self.assertEqual(result["1"], bits(self.plan[0]["location"]))
        self.assertNotEqual(result["1"]["wght"], result["2"]["wght"])

    def test_missing_extra_duplicate_reordered_or_wrong_face_audits_reject(self):
        variants = [self.rows[:1], self.rows + self.rows[:1], list(reversed(self.rows)),
                    [self.rows[0], self.rows[0]]]
        for key, value in (("face_index", 14), ("face_index", True), ("request_id", 1),
                           ("mode", MODES[1]), ("extra", "must not be silently ignored")):
            rows = deepcopy(self.rows); rows[1][key] = value; variants.append(rows)
        for rows in variants:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                check_entry_audit(self.text(rows), self.plan, MODES[0])

    def test_rounded_missing_unknown_and_malformed_axis_bits_reject(self):
        variants = []
        for value in ("43f980cb", "g", "0" * 17, 0, False):
            rows = deepcopy(self.rows); rows[0]["binary64_bits"]["wght"] = value; variants.append(rows)
        rows = deepcopy(self.rows); del rows[0]["binary64_bits"]["HGHT"]; variants.append(rows)
        rows = deepcopy(self.rows); rows[0]["binary64_bits"]["wdth"] = "0"; variants.append(rows)
        for rows in variants:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                check_entry_audit(self.text(rows), self.plan, MODES[0])
        with self.assertRaisesRegex(ValueError, "json_invalid"):
            check_entry_audit(PREFIX + "not JSON", self.plan, MODES[0])

    def test_signed_zero_is_a_bit_difference(self):
        plan = deepcopy(self.plan); plan[0]["location"]["WDTH"] = -0.0
        rows = deepcopy(self.rows); rows[0]["binary64_bits"] = bits(plan[0]["location"])
        self.assertEqual(check_entry_audit(self.text(rows), plan, MODES[0])["1"]["WDTH"], "8000000000000000")
        rows[0]["binary64_bits"]["WDTH"] = "0"
        with self.assertRaisesRegex(ValueError, "input_bits_changed"):
            check_entry_audit(self.text(rows), plan, MODES[0])

    def test_new_native_failure_code_is_preserved_without_raw_error_details(self):
        code = "a3_invalid_constructor_entry_audit"
        self.assertEqual(diagnostic_failure(RuntimeError("native request 3 face 15 failed: " + code))
                         ["native_failure_code"], code)
        result = diagnostic_failure(RuntimeError("native request 3 face 15 failed: private_outline_123"))
        self.assertNotIn("native_failure_code", result)
        self.assertNotIn("private_outline_123", json.dumps(result))

    def test_native_prefix_and_anchor_body_are_unchanged_and_audit_precedes_call(self):
        source = (PLATFORM / "coretext_extract.swift").read_text()
        generated = make_harness(source)
        self.assertTrue(generated.startswith(source.split("\nfunc run() throws {")[0]))
        self.assertEqual(generated.count("try a3AuditConstructorEntry(request, mode)"), 1)
        self.assertIn("try a3AuditConstructorEntry(request, mode)\n"
                      "            let (font, location, reported) = try anchorInstance(state, request.location, mode)", generated)
        self.assertIn('"diagnostic_readback_observation_only": true', generated)
        with self.assertRaises(ValueError):
            make_harness(generated)
        with self.assertRaises(ValueError):
            make_harness(source.replace("func constructInstance(", "func changedConstructor(", 1))


if __name__ == "__main__":
    unittest.main()
