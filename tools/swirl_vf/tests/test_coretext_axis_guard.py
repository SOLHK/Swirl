"""Harness integrity tests; only execution of compiled Swift grants native PASS."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from compare_axis_construction import GUARD, make_harness as make_observation_harness
from check_coretext_axis_guard import make_harness
from diagnose_axis_readback import harness as make_readback_harness


class CoreTextAxisGuardHarnessTests(unittest.TestCase):
    def source(self):
        return (Path(__file__).resolve().parents[1] / "platform" / "coretext_extract.swift").read_text()

    def test_actual_production_validator_and_caller_are_preserved_verbatim(self):
        source = self.source()
        prefix = source.split("\nfunc run() throws {")[0]
        harness = make_harness(source)
        self.assertTrue(harness.startswith(prefix))
        self.assertEqual(harness.count(GUARD), 1)
        self.assertEqual(harness.count("func validateReportedAxes("), 1)
        self.assertIn("try validateReportedAxes(axes, location, reported)", harness)
        self.assertNotIn("try run()", harness)
        self.assertIn("known_decimal4_mismatch_still_rejected", harness)
        self.assertEqual(source, self.source())

    def test_changed_guard_or_unbound_production_caller_requires_review(self):
        source = self.source()
        for changed in (source.replace(GUARD, ""), source + GUARD,
                        source.replace("try validateReportedAxes(state.raw.axes, location, reported)", ""),
                        source.replace("func validateReportedAxes(", "func unrelatedValidator(")):
            with self.assertRaisesRegex(ValueError, "review_changed_production_axis_validator"):
                make_harness(changed)

    def test_diagnostic_guard_removal_also_removes_the_new_presence_requirement(self):
        source = self.source()
        observation = make_observation_harness(source)
        self.assertNotIn(GUARD, observation)
        self.assertNotIn("reported[axis.tag] != nil || expected == axis.defaultValue", observation)
        self.assertIn("Baseline observation only, never builder input.", observation)
        self.assertEqual(source.count(GUARD), 1)

    def test_legacy_readback_diagnosis_uses_the_same_reviewed_guard(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "original-production-helper.swift"
            path.write_text(source)
            observation = make_readback_harness(path)
            self.assertNotIn(GUARD, observation)
            self.assertNotIn("reported[axis.tag] != nil || expected == axis.defaultValue", observation)
            self.assertIn("func diagnosticInstance(", observation)
            self.assertIn("Observation only; no acceptance verdict.", observation)
            self.assertEqual(path.read_text(), source)
            path.write_text(source.replace(GUARD, ""))
            with self.assertRaisesRegex(ValueError, "production guard changed"):
                make_readback_harness(path)


if __name__ == "__main__":
    unittest.main()
