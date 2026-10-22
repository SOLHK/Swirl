"""Fail-closed generator contracts using actual production Swift, without fonts.

Native execution and original-font comparisons are separate CI evidence; these
tests ensure that diagnostics cannot silently drift away from those helpers.
"""
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

PLATFORM = Path(__file__).resolve().parents[1] / "platform"
sys.path.insert(0, str(PLATFORM))
import plateau_construction_harness as plateau
from compare_axis_construction import EXPECTED, GUARD, SWIFT


class PlateauConstructionHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (PLATFORM / "coretext_extract.swift").read_text(encoding="utf-8")
        cls.generated = plateau.make_harness(cls.source)

    def test_all_production_helpers_and_strict_validator_are_unchanged(self):
        prefix = self.source.split("\nfunc run() throws {")[0]
        self.assertTrue(self.generated.startswith(prefix))
        self.assertEqual(self.generated.count(GUARD), 1)
        self.assertEqual(self.generated.count("func constructInstance("), 1)
        self.assertEqual(self.generated.count("func makeInstance("), 1)
        self.assertEqual(self.generated.count("func locateDescriptors("), 1)
        self.assertEqual(self.generated.count("func validateReportedAxes("), 1)
        self.assertIn("try validateReportedAxes(state.raw.axes, location, reported)", self.generated)

    def test_existing_public_api_helpers_are_reused_without_comparison_main(self):
        helpers = SWIFT.split("\nfunc compareConstructionMain() throws {")[0]
        self.assertIn(helpers, self.generated)
        self.assertNotIn("compareConstructionMain", self.generated)
        self.assertNotIn("observationInstance", self.generated)
        self.assertNotIn("let (baseline,", self.generated)

    def test_modes_are_exact_allowlist_and_unknown_modes_fail_closed(self):
        expected = {"production", "descriptor_copy", "graphics_copy_tracking",
                    "rebase_300", "rebase_500"}
        self.assertEqual(set(plateau.MODES), expected)
        allowed = re.search(r"let allowed = Set\((\[.*\])\)", self.generated)
        self.assertIsNotNone(allowed)
        self.assertEqual(json.loads(allowed.group(1)), list(plateau.MODES))
        self.assertEqual(plateau.MODE_ENV, "SWIRL_VF_PLATEAU_MODE")
        self.assertIn(f'environment["{plateau.MODE_ENV}"]', self.generated)
        self.assertIn("allowed.contains(mode)", self.generated)
        self.assertIn('default:\n        throw OracleError.invalid("plateau_mode_missing_or_unknown")', self.generated)
        self.assertNotIn("--axis-observations", self.generated.split("\nfunc run() throws {")[1])

    def test_alternates_never_preconstruct_production_baseline(self):
        dispatch = self.generated.split("\nfunc plateauInstance(")[1].split("\nfunc run() throws {")[0]
        alternate = dispatch.split('case "descriptor_copy", "graphics_copy_tracking":')[1].split("    default:")[0]
        self.assertNotIn("constructInstance", alternate)
        self.assertIn("let location = try plateauLocation(state, requested)", alternate)
        self.assertIn("let font = try alternativeFont(state, location, mode)", alternate)
        location = self.generated.split("\nfunc plateauLocation(")[1].split("\nfunc plateauPrepareStates(")[0]
        self.assertNotIn("CTFont", location)
        self.assertIn("requested.keys.allSatisfy", location)
        self.assertIn("requested[axis.tag] ?? axis.defaultValue", location)
        self.assertIn("value.isFinite, value >= axis.minimum, value <= axis.maximum", location)

    def test_rebase_uses_original_defaults_and_verifies_complete_seed_identity(self):
        prepare = self.generated.split("\nfunc plateauPrepareStates(")[1].split("\nfunc plateauInstance(")[0]
        self.assertIn("originals.count == 32", prepare)
        self.assertIn("var metadata = original.metadata", prepare)
        self.assertIn("original.raw.axes.map { ($0.tag, $0.defaultValue) }", prepare)
        self.assertIn('location["wght"] = mode == "rebase_300" ? 300.0 : 500.0', prepare)
        self.assertIn("try constructInstance(original, location)", prepare)
        self.assertIn("try verifyIdentity(font, original.raw, allTables: true)", prepare)
        self.assertIn("FaceState(raw: original.raw, baseFont: seeded, metadata: metadata)", prepare)
        for phase in ("original", "seeded"):
            for field in ("axes", "name", "size"):
                self.assertIn(f'metadata["plateau_{phase}_base_{field}"]', prepare)

    def test_protocol_remains_full_payload_with_original_eof_and_error_accounting(self):
        source_tail = self.source.split("            for glyph in request.glyph_ids {")[1]
        generated_tail = self.generated.split("            for glyph in request.glyph_ids {")[1]
        self.assertEqual(generated_tail, source_tail)
        for source_key in ('"source_byte_size": data.count', '"faces": states.map(\\.metadata)',
                           '"source_sha256": sha256(data)', '"schema_version": 1'):
            self.assertIn(source_key, self.generated)
        self.assertIn(f'guard sha256(data) == "{EXPECTED}"', self.generated)
        self.assertIn('"diagnostic_readback_observation_only": true', self.generated)
        self.assertIn('"axis_observations_only": false', self.generated)
        self.assertIn('"plateau_mode": mode', self.generated)
        self.assertIn('"NOT_ACCEPTED_diagnostic_construction_comparison_only"', self.generated)
        self.assertNotIn('"strict_reported_coordinate_check"', self.generated)

    def test_missing_duplicate_or_changed_run_anchors_are_rejected(self):
        anchors = (
            "\nfunc run() throws {",
            GUARD,
            "func constructInstance(",
            "func locateDescriptors(",
            '    let data = try Data(contentsOf: url, options: [.mappedIfSafe])',
            '    let states = try locateDescriptors(rawFaces, url: url)',
            '              "axis_observations_only": observationsOnly,',
            '              "axis_observation_acceptance": observationsOnly ? "NOT_ACCEPTED_requires_independent_per_request_verification" : "strict_reported_coordinate_check",',
            '            let (font, location, reported) = try (observationsOnly\n'
            '                ? constructInstance(state, request.location) : makeInstance(state, request.location))',
        )
        for anchor in anchors:
            with self.subTest(anchor=anchor):
                with self.assertRaisesRegex(ValueError, "review_changed_plateau"):
                    plateau.make_harness(self.source.replace(anchor, "", 1))
                with self.assertRaisesRegex(ValueError, "review_changed_plateau"):
                    plateau.make_harness(self.source + "\n" + anchor)

    def test_comparison_helper_drift_and_already_generated_source_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "review_changed_plateau"):
            plateau.make_harness(self.generated)
        for mutation in (SWIFT.replace("\nfunc compareConstructionMain() throws {", ""),
                         SWIFT.replace("func alternativeFont(", "func replacedAlternative("),
                         SWIFT + "\nfunc compareConstructionMain() throws {"):
            with patch.object(plateau, "CONSTRUCTION_SWIFT", mutation):
                with self.assertRaisesRegex(ValueError, "review_changed_plateau"):
                    plateau.make_harness(self.source)


if __name__ == "__main__":
    unittest.main()
