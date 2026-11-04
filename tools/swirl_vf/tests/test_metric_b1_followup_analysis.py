"""Analysis-admission tests with fabricated records; no native evidence here."""
from contextlib import redirect_stdout
from copy import deepcopy
from fractions import Fraction
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import b1_metric_followup as analysis
from b1_metric_discriminator import validate_raw
from b1_metric_fixture import fixture_requests
from b1_metric_followup_fixture import MODEL_STATUS, build_suite, delta_predictions
from test_metric_b1_discriminator import example_report


ROW_TEMPLATE = example_report()[2]["observations"][0]


def fabricated_row(entry, request, *, height=None, origin_x=None, origin_y=None):
    """Fabricate values to test analysis logic, not to simulate CoreText truth."""
    row = deepcopy(ROW_TEMPLATE)
    row["evidence_kind"] = "FABRICATED_UNIT_TEST_RECORD_NOT_NATIVE"
    row["id"] = request["id"]
    row["requested_axes"] = deepcopy(request["axes"])
    row["point_size"], row["upem"] = float(entry["upem"]), entry["upem"]
    row["font_identity"]["verified_table_sha256"] = deepcopy(entry["table_sha256"])
    prediction = entry["predictions_round_delta"][request["id"]]
    if height is None:
        height = (prediction["vvar_truncate_continuous"]["prediction"] if "VVAR" in entry["table_sha256"]
                  else prediction["prediction"])
    if origin_x is None:
        origin_x = request["expected"]["vertical_origin_x_current_half_width"]
    if origin_y is None:
        origin_y = analysis.fraction_record(entry["predictions_origin_y"][request["id"]]["selected_prediction"])
    row["direct_advances"] = {"horizontal_vector": [float(request["expected"]["advance_width"]), 0.0],
                              "horizontal_sum": float(request["expected"]["advance_width"]),
                              "vertical_vector": [float(height), 0.0], "vertical_sum": float(height)}
    row["vertical_translation"] = {"raw_vector": [-float(origin_x), -float(origin_y)]}
    row["witness_path"]["geometric_bounds_xywh"] = list(request["expected"]["witness_bounds"])
    for index, glyph in enumerate(row["vertical_layout"]["glyphs"]):
        glyph["position"] = [0.0, -float(height)*index]
    row["vertical_layout"]["runs"][0]["font_identity"]["verified_table_sha256"] = deepcopy(entry["table_sha256"])
    return row


class B1FollowupAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.path = Path(cls.directory.name)
        cls.before_freeze = build_suite(cls.path / "fixtures")
        cls.manifest = analysis.freeze_origin_predictions(deepcopy(cls.before_freeze))
        cls.entries = {(e["upem"], e["variant"]): e for e in cls.manifest["entries"]}
        cls.observations = [analysis.observe_followup(entry, request, fabricated_row(entry, request))
                            for entry in cls.manifest["entries"] for request in entry["requests"]]

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def case(self, upem, variant, y, x=0.0):
        entry = self.entries[upem, variant]
        request = next(r for r in entry["requests"] if r["axes"] == {"WDTH": x, "HGHT": y})
        return entry, request

    def test_origin_predictions_are_frozen_from_predeclared_source_not_observations(self):
        self.assertEqual(self.manifest["origin_y_model_status"], MODEL_STATUS)
        self.assertIn("not an assertion", self.manifest["origin_y_model_scope"].lower())
        for before, after in zip(self.before_freeze["entries"], self.manifest["entries"]):
            self.assertEqual(before["requests"], after["requests"])
            self.assertEqual(before["predictions_round_delta"], after["predictions_round_delta"])
            self.assertEqual(set(after["predictions_origin_y"]), {r["id"] for r in after["requests"]})
        with mock.patch.object(analysis.subprocess, "run", side_effect=AssertionError("unexpected native execution")):
            repeated = analysis.freeze_origin_predictions(deepcopy(self.before_freeze))
        self.assertEqual(repeated, self.manifest)

    def test_predeclared_negative_tie_and_sixteenth_origins_separate_candidates(self):
        expected = {
            -0.875: (Fraction(1533, 2), Fraction(1533, 2), Fraction(1535, 2)),
            -0.0625: (Fraction(3261, 4), Fraction(3265, 4), Fraction(3265, 4)),
            0.0625: (Fraction(3295, 4), Fraction(3295, 4), Fraction(3295, 4)),
            0.1875: (Fraction(3321, 4), Fraction(3325, 4), Fraction(3325, 4)),
        }
        for y, predictions in expected.items():
            with self.subTest(y=y):
                entry, request = self.case(1024, "gvar", y)
                frozen = entry["predictions_origin_y"][request["id"]]
                actual = tuple(analysis.fraction_record(frozen[name]) for name in
                               ("ceil_bbox_candidate", "nearest_bbox_candidate", "continuous_candidate"))
                self.assertEqual(actual, predictions)

    def test_ceil_bbox_and_floor_bearing_are_algebraic_candidates_not_proven_sources(self):
        for entry in self.manifest["entries"]:
            for prediction in entry["predictions_origin_y"].values():
                visible = analysis.fraction_record(prediction["visible_control_ymax_exact"])
                top = prediction["top_after_delta_round"]
                floor_bearing_form = visible + math.floor(Fraction(top) - visible)
                self.assertEqual(analysis.fraction_record(prediction["ceil_bbox_candidate"]), floor_bearing_form)
        self.assertEqual(self.manifest["native_acceptance"], "NOT_RUN")
        self.assertEqual(self.manifest["original_font_acceptance"], "NOT_ESTABLISHED")

    def test_gvar_and_vvar_height_candidates_are_selected_by_actual_table_presence(self):
        for variant, raw_height, should_match in (("gvar", 1010, True), ("gvar", 1009, False),
                                                  ("vvar", 1009, True), ("vvar", 1010, False)):
            with self.subTest(variant=variant, raw=raw_height):
                entry, request = self.case(1024, variant, 0.0625)
                result = analysis.observe_followup(entry, request, fabricated_row(entry, request, height=raw_height))
                self.assertEqual(result["fresh_height_candidate"]["exact_match"], should_match)
                self.assertEqual(result["fresh_height_candidate"]["source_candidate"],
                                 "VVAR_truncate_continuous" if variant == "vvar" else "gvar_delta_round_then_quantize")
                self.assertFalse(result["strict_metrics_pass"])

    def test_vorg_origin_source_has_priority_without_becoming_a_strict_override(self):
        entry, request = self.case(1024, "hvar_vvar_vorg", 0.0625)
        prediction = entry["predictions_origin_y"][request["id"]]
        self.assertEqual(prediction["selected_source_candidate"], "stored_VORG_y")
        self.assertEqual(analysis.fraction_record(prediction["selected_prediction"]), 911)
        self.assertEqual(analysis.fraction_record(prediction["continuous_candidate"]), Fraction(3295, 4))
        result = analysis.observe_followup(entry, request, fabricated_row(entry, request))
        self.assertTrue(result["fresh_origin_y_candidates"]["selected_prediction"]["exact_match"])
        self.assertFalse(result["strict_metric_comparisons"]["vertical_origin_y"]["within_unchanged_1_over_32"])

    def test_849_candidate_match_does_not_change_the_original_850_strict_reference(self):
        # A fabricated unit-only case outside the fresh native plan retains the
        # original failure through the new analyzer; it is not a new native run.
        entry = deepcopy(self.entries[1000, "gvar"])
        request = next(r for r in fixture_requests(1000, "gvar") if r["axes"] == {"WDTH": 0.0, "HGHT": -1.0})
        request["id"] = "unit-only-original-849-control"
        request["case_group"], request["partition"] = "fabricated_unit_control", "holdout"
        entry["requests"] = [request]
        entry["predictions_round_delta"] = {request["id"]: delta_predictions(-1, 1000)}
        analysis.freeze_origin_predictions({"entries": [entry]})
        row = analysis.observe_followup(entry, request, fabricated_row(entry, request, height=849))
        self.assertTrue(row["fresh_height_candidate"]["exact_match"])
        self.assertFalse(row["strict_metrics_pass"])
        self.assertEqual(row["strict_metric_comparisons"]["advance_height"]["signed_error_exact"],
                         {"numerator": -1, "denominator": 1, "value": -1.0})
        summary = analysis.followup_summary([row])[entry["fixture_id"]]
        self.assertEqual(summary["fresh_height_candidate_matches"], 1)
        self.assertEqual(summary["strict_metric_failures"], 1)

    def test_odd_stored_half_width_distinguishes_500_from_500_point_5(self):
        entry, request = self.case(1024, "hvar_vvar_odd_default_vorg", 0.0625)
        for origin_x in (500.0, 500.5):
            row = analysis.observe_followup(entry, request, fabricated_row(entry, request, origin_x=origin_x))
            candidates = row["origin_x_relationships"]
            self.assertEqual(candidates["half_stored_advance_exact"]["exact_match"], origin_x == 500.5)
            self.assertEqual(candidates["half_stored_advance_truncated"]["exact_match"], origin_x == 500.0)
            self.assertEqual(row["strict_metric_comparisons"]["vertical_origin_x_current_half_width"]["signed_error_design_units"],
                             origin_x - 500.5)

    def test_paired_effects_cover_every_declared_nonreference_request(self):
        effects = analysis.paired_table_effects(self.manifest, self.observations)
        expected = {(entry["fixture_id"], request["id"]) for entry in self.manifest["entries"]
                    if entry["variant"] != entry["comparison_variant"] for request in entry["requests"]}
        self.assertEqual(len(effects), 446)
        self.assertEqual({(r["fixture"], r["request_id"]) for r in effects}, expected)
        for effect in effects:
            entry = next(e for e in self.manifest["entries"] if e["fixture_id"] == effect["fixture"])
            request = next(r for r in entry["requests"] if r["id"] == effect["request_id"])
            self.assertEqual(effect["axes"], request["axes"])

    def test_paired_effects_reject_wrong_coordinate_even_when_request_id_matches(self):
        rows = deepcopy(self.observations)
        rows[0]["axes"]["HGHT"] = 0.0
        with self.assertRaises(ValueError): analysis.paired_table_effects(self.manifest, rows)

    def test_paired_effects_reject_duplicate_extra_or_missing_observations(self):
        for problem in ("duplicate", "extra", "missing"):
            with self.subTest(problem=problem):
                rows = deepcopy(self.observations)
                if problem == "duplicate": rows.append(deepcopy(rows[0]))
                elif problem == "extra":
                    extra = deepcopy(rows[0]); extra["request_id"] = "not-preregistered"; rows.append(extra)
                else: rows.pop(0)
                with self.assertRaises(ValueError): analysis.paired_table_effects(self.manifest, rows)

    def test_origin_freeze_rejects_duplicate_requests_instead_of_overwriting(self):
        manifest = deepcopy(self.before_freeze)
        manifest["entries"][0]["requests"].append(deepcopy(manifest["entries"][0]["requests"][0]))
        with self.assertRaises(ValueError): analysis.freeze_origin_predictions(manifest)

    def test_fabricated_record_marker_cannot_be_admitted_as_native_completion(self):
        entry, requests, report = example_report()
        report["status"] = "FABRICATED_UNIT_TEST_RECORD_NOT_NATIVE"
        with self.assertRaisesRegex(ValueError, "native_diagnostic_incomplete"):
            validate_raw(report, entry, requests)

    def test_non_macos_pipeline_emits_not_run_and_never_invokes_native_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "not-native"
            def prepared_manifest(path):
                path.mkdir(parents=True)
                return deepcopy(self.before_freeze)
            with mock.patch.object(analysis.sys, "platform", "linux"), \
                    mock.patch.object(analysis.platform, "platform", return_value="Linux fabricated unit-test environment"), \
                    mock.patch.object(analysis.sys, "argv", ["b1_metric_followup.py", "--output", str(out), "--require-native"]), \
                    mock.patch.object(analysis, "build_suite", side_effect=prepared_manifest), \
                    mock.patch.object(analysis.subprocess, "run", side_effect=AssertionError("native process must not run")), \
                    redirect_stdout(io.StringIO()):
                code = analysis.main()
            result = json.loads((out / "followup-report.json").read_text())
            self.assertEqual(code, 2)
            self.assertEqual(result["status"], "NOT_RUN")
            self.assertEqual(result["native_executions"], [])
            self.assertEqual(result["observations"], [])
            self.assertEqual(result["original_faces_reconstructed"], 0)
            self.assertEqual(result["original_font_acceptance"], "NOT_ESTABLISHED")
            self.assertNotIn("height_candidate_independent_validation", result)


if __name__ == "__main__":
    unittest.main()
