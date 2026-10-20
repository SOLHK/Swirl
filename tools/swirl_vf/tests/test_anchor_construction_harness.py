"""Generator contracts and independent range proofs, not native acceptance."""
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys
import unittest
from unittest.mock import patch

PLATFORM = Path(__file__).resolve().parents[1] / "platform"
sys.path.insert(0, str(PLATFORM))
import anchor_construction_harness as anchor
import plateau_construction_harness as plateau
from compare_axis_construction import EXPECTED, GUARD, SWIFT


class AnchorConstructionHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (PLATFORM / "coretext_extract.swift").read_text(encoding="utf-8")
        cls.generated = anchor.make_harness(cls.source)

    def test_exact_reviewed_production_prefix_and_strict_guard_are_preserved(self):
        prefix = self.source.split("\nfunc run() throws {")[0]
        self.assertEqual(hashlib.sha256(prefix.encode()).hexdigest(), anchor.REVIEWED_PRODUCTION_PREFIX_SHA256)
        self.assertEqual(self.generated[:len(prefix)], prefix)
        self.assertEqual(self.generated.count(GUARD), 1)
        for name in ("constructInstance", "makeInstance", "validateReportedAxes", "locateDescriptors", "extractGlyph"):
            self.assertEqual(self.generated.count(f"func {name}("), 1)
        self.assertIn("try validateReportedAxes(state.raw.axes, location, reported)", self.generated)
        self.assertIn(SWIFT.split("\nfunc compareConstructionMain() throws {")[0], self.generated)

    def test_unreviewed_prefix_changes_and_already_generated_sources_fail_closed(self):
        # Even an unchanged signature with a changed body must be re-reviewed.
        changed = self.source.replace("let opticalSize = location[\"opsz\"]", "let opticalSize = location[\"xxxx\"]", 1)
        with self.assertRaisesRegex(ValueError, "review_changed_anchor_production_prefix"):
            anchor.make_harness(changed)
        for source in (self.generated, plateau.make_harness(self.source),
                       self.source.replace(GUARD, "", 1), "// unreviewed prefix\n" + self.source):
            with self.subTest(source_length=len(source)):
                with self.assertRaisesRegex(ValueError, "review_changed_anchor_production_prefix"):
                    anchor.make_harness(source)

    def test_five_modes_are_allowlisted_and_unknown_modes_fail_closed(self):
        expected = ("production", "anchor_endpoint_original", "anchor_endpoint_300",
                    "anchor_endpoint_500", "anchor_quarter_original")
        self.assertEqual(anchor.MODES, expected)
        self.assertEqual(anchor.MODE_ENV, "SWIRL_VF_ANCHOR_MODE")
        mode = self.generated.split("\nfunc anchorMode() throws -> String {")[1].split("\nfunc anchorOpticalMetadata(")[0]
        allowed = re.search(r"let allowed = Set\((\[.*\])\)", mode)
        self.assertIsNotNone(allowed)
        self.assertEqual(json.loads(allowed.group(1)), list(expected))
        self.assertIn('environment["SWIRL_VF_ANCHOR_MODE"]', mode)
        self.assertIn("allowed.contains(mode)", mode)
        self.assertIn('throw OracleError.invalid("anchor_mode_missing_or_unknown")', mode)
        self.assertNotIn('environment["SWIRL_VF_PLATEAU_MODE"]', self.generated)
        self.assertNotIn('"plateau_mode"', self.generated)

    def test_production_dispatch_does_not_create_anchor_or_seed(self):
        instance = self.generated.split("\nfunc anchorInstance(")[1].split("\nfunc run() throws {")[0]
        production = instance.split('    if mode == "production" {')[1].split("    }", 1)[0]
        self.assertEqual(production.strip(), "return try constructInstance(state, requested)")
        prepare = self.generated.split("\nfunc anchorPrepareStates(")[1].split("\nfunc anchorInstance(")[0]
        self.assertIn('if mode == "anchor_endpoint_300" || mode == "anchor_endpoint_500" {', prepare)
        self.assertNotIn('if mode == "production"', prepare)
        self.assertEqual(prepare.count("try constructInstance("), 1)

    def test_target_validation_and_anchor_plan_are_complete_and_feedback_free(self):
        location = self.generated.split("\nfunc anchorLocation(")[1].split("\nfunc anchorCoordinate(")[0]
        old_location = plateau.make_harness(self.source).split("\nfunc plateauLocation(")[1].split("\nfunc plateauPrepareStates(")[0]
        self.assertEqual(location, old_location)
        self.assertNotIn("CTFont", location)
        self.assertNotIn("constructInstance", location)
        instance = self.generated.split("\nfunc anchorInstance(")[1].split("\nfunc run() throws {")[0]
        nonproduction = instance.split('    guard mode == "anchor_endpoint_original"')[1]
        self.assertLess(nonproduction.index("try anchorLocation(state, requested)"),
                        nonproduction.index("try constructInstance(state, planned)"))
        self.assertIn("var planned: [String: Double] = [:]", nonproduction)
        self.assertIn("for axis in state.raw.axes {", nonproduction)
        self.assertIn("anchorCoordinate(value, axis.minimum, axis.maximum, quarter)", nonproduction)
        self.assertIn("let (anchor, _, anchorReported) = try constructInstance(state, planned)", nonproduction)
        self.assertIn("try anchorRequireReadback(state.raw.axes, planned, anchorReported)", nonproduction)
        self.assertIn("FaceState(raw: state.raw, baseFont: anchor, metadata: state.metadata)", nonproduction)
        self.assertIn("let result = try constructInstance(anchored, location)", nonproduction)
        self.assertEqual(nonproduction.count("try constructInstance("), 2)
        after_validation = nonproduction.split("try anchorRequireReadback(state.raw.axes, planned, anchorReported)")[1]
        self.assertNotIn("anchorReported", after_validation)
        for forbidden in ("alternativeFont(", "while ", "repeat {", "previousFont", "cache["):
            self.assertNotIn(forbidden, nonproduction)

    def test_anchor_echo_must_equal_plan_and_only_exact_default_may_be_omitted(self):
        guard = self.generated.split("\nfunc anchorRequireReadback(")[1].split("\nfunc anchorPrepareStates(")[0]
        self.assertIn("Set(planned.keys) == tags", guard)
        self.assertIn("reported.keys.allSatisfy({ tags.contains($0) })", guard)
        self.assertIn("(reported[axis.tag] != nil || expected == axis.defaultValue)", guard)
        self.assertIn("let effective = reported[axis.tag] ?? axis.defaultValue", guard)
        self.assertIn("effective.isFinite, effective == expected", guard)
        self.assertIn('"anchor_readback_not_exactly_predeclared"', guard)
        self.assertNotIn("1e-6", guard)
        self.assertNotIn("abs(", guard)

    def test_scalar_helper_checks_range_and_the_required_distance(self):
        rule = anchor.COORDINATE_SWIFT
        self.assertEqual(self.generated.count(rule), 1)
        for required in ("target.isFinite, minimum.isFinite, maximum.isFinite, span.isFinite",
                         "span > 0, target >= minimum, target <= maximum",
                         "let midpoint = minimum + span * 0.5", "if target <= midpoint",
                         "value = quarter ? minimum + span * 0.75 : maximum",
                         "value = quarter ? minimum + span * 0.25 : minimum",
                         "let separation = span * (quarter ? 0.25 : 0.5)",
                         "value.isFinite, value >= minimum, value <= maximum",
                         "abs(value - target) >= separation"):
            self.assertIn(required, rule)
        self.assertNotIn("CTFont", rule)
        self.assertNotIn("reported", rule)

    def test_independent_exact_range_proof_at_boundaries_midpoints_and_mixed_axes(self):
        # This proves the predeclared recipe, not Swift execution. Choose the
        # farther of two candidate points independently, resolving a tie upward.
        # Published source ranges and additional authored ranges are exact dyadics.
        ranges = ((1., 1000.), (100., 900.), (-13., 23.), (0., 1.))
        rng = random.Random(91320261020)
        checked = 0
        for minimum, maximum in ranges:
            a, b = Fraction(minimum), Fraction(maximum)
            midpoint = (a + b) / 2
            targets = [minimum, maximum, float(midpoint), math.nextafter(float(midpoint), -math.inf),
                       math.nextafter(float(midpoint), math.inf)]
            targets += [rng.uniform(minimum, maximum) for _ in range(32)]
            for target in targets:
                t = Fraction(target)
                for quarter in (False, True):
                    candidates = ((3 * a + b) / 4, (a + 3 * b) / 4) if quarter else (a, b)
                    independently_farthest = max(candidates, key=lambda p: (abs(p - t), p))
                    declared = candidates[1] if t <= midpoint else candidates[0]
                    self.assertEqual(declared, independently_farthest)
                    self.assertLessEqual(a, declared)
                    self.assertLessEqual(declared, b)
                    self.assertGreaterEqual(abs(declared - t), (b - a) / (4 if quarter else 2))
                    self.assertEqual(Fraction(float(declared)), declared)
                    checked += 1
        self.assertEqual(checked, 296)
        for quarter in (False, True):
            for target in ((600.5859375, 400.01, 250.), (500., 501., 500.), (1., 100., 1000.)):
                for value, (minimum, maximum) in zip(target, ((1., 1000.), (100., 900.), (1., 1000.))):
                    a, b, t = Fraction(minimum), Fraction(maximum), Fraction(value)
                    candidates = ((3 * a + b) / 4, (a + 3 * b) / 4) if quarter else (a, b)
                    planned = max(candidates, key=lambda p: (abs(p - t), p))
                    self.assertGreaterEqual(abs(planned - t), (b - a) / (4 if quarter else 2))

    def test_base_metadata_and_seed_identity_are_preserved_with_optical_receipts(self):
        prepare = self.generated.split("\nfunc anchorPrepareStates(")[1].split("\nfunc anchorInstance(")[0]
        self.assertIn("originals.count == 32", prepare)
        self.assertIn("var metadata = original.metadata", prepare)
        self.assertIn("original.raw.axes.map { ($0.tag, $0.defaultValue) }", prepare)
        self.assertIn('location["wght"] = mode == "anchor_endpoint_300" ? 300.0 : 500.0', prepare)
        self.assertIn("try verifyIdentity(font, original.raw, allTables: true)", prepare)
        self.assertIn("try anchorRequireOptical(font, expectedOptical)", prepare)
        for phase in ("original", "seeded"):
            for name in ("axes", "name", "size", "optical"):
                self.assertIn(f'metadata["anchor_{phase}_base_{name}"]', prepare)
        optical = self.generated.split("\nfunc anchorOpticalMetadata(")[1].split("\nfunc anchorExpectedOptical(")[0]
        self.assertIn("return NSNull()", optical)
        self.assertIn("value.isFinite", optical)

    def test_both_hops_require_original_production_optical_inheritance(self):
        expected = self.generated.split("\nfunc anchorExpectedOptical(")[1].split("\nfunc anchorRequireOptical(")[0]
        original = self.source.split("\nfunc constructInstance(")[1].split("\nfunc validateReportedAxes(")[0]
        for line in expected.splitlines():
            if line.strip().startswith(("let baseOpticalSize =", "let opticalSize =")):
                self.assertIn(line, original)
        optical = self.generated.split("\nfunc anchorRequireOptical(")[1].split("\nfunc anchorRequireReadback(")[0]
        self.assertIn("let actual = (CTFontCopyAttribute(font, kCTFontOpticalSizeAttribute) as? NSNumber)?.doubleValue", optical)
        self.assertIn("actual.isFinite, actual == expected", optical)
        self.assertNotIn("??", optical)
        instance = self.generated.split("\nfunc anchorInstance(")[1].split("\nfunc run() throws {")[0]
        for required in ("let firstOptical = try anchorExpectedOptical(base, planned)",
                         "try anchorRequireOptical(anchor, firstOptical)",
                         "let secondOptical = try anchorExpectedOptical(anchor, location)",
                         "try anchorRequireOptical(result.0, secondOptical)"):
            self.assertIn(required, instance)

    def test_original_extraction_transport_and_not_accepted_markers_are_retained(self):
        marker = "            for glyph in request.glyph_ids {"
        self.assertEqual(self.generated.split(marker)[1], self.source.split(marker)[1])
        self.assertIn(f'guard sha256(data) == "{EXPECTED}"', self.generated)
        self.assertIn('"diagnostic_readback_observation_only": true', self.generated)
        self.assertIn('"axis_observations_only": false', self.generated)
        self.assertIn('"NOT_ACCEPTED_diagnostic_anchor_construction_only"', self.generated)
        self.assertIn('"anchor_mode": mode', self.generated)
        self.assertNotIn('"strict_reported_coordinate_check"', self.generated)
        run = self.generated.split("\nfunc run() throws {")[1]
        self.assertNotIn("observationsOnly", run)
        self.assertNotIn("--axis-observations", run)

    def test_missing_duplicate_or_changed_generation_anchors_are_rejected(self):
        source_anchors = ("\nfunc run() throws {", '    let states = try locateDescriptors(rawFaces, url: url)',
                          '              "axis_observations_only": observationsOnly,')
        for text in source_anchors:
            for source in (self.source.replace(text, "", 1), self.source + "\n" + text):
                with self.subTest(anchor=text):
                    with self.assertRaises(ValueError):
                        anchor.make_harness(source)
        base = plateau.make_harness(self.source)
        generated_anchors = ("// SWIRL_VF_PLATEAU_CONSTRUCTION_DIAGNOSTIC", "\nfunc plateauLocation(",
                             "\nfunc plateauPrepareStates(", "    let mode = try plateauMode()",
                             '"plateau_mode": mode',
                             "            let (font, location, reported) = try plateauInstance(state, request.location, mode)")
        for text in generated_anchors:
            for mutated in (base.replace(text, "", 1), base + "\n" + text):
                with self.subTest(anchor=text):
                    with patch.object(plateau, "make_harness", return_value=mutated):
                        with self.assertRaisesRegex(ValueError, "review_changed_anchor"):
                            anchor.make_harness(self.source)
        with patch.object(plateau, "make_harness", return_value=base.replace("import Foundation", "import Changed", 1)):
            with self.assertRaisesRegex(ValueError, "review_changed_anchor_production_prefix"):
                anchor.make_harness(self.source)


if __name__ == "__main__":
    unittest.main()
