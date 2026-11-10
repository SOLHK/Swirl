"""Follow-up preregistration/storage checks, never substituted native evidence."""
from fractions import Fraction
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.varLib.varStore import VarStoreInstancer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from b1_metric_fixture import HOLDOUT_Y, TRAINING_Y, comparison_table_bytes
from b1_metric_followup_fixture import (
    EXACT_NORMALIZATION_Y, FOLLOWUP_X, FOLLOWUP_Y, HEIGHT_VARIANTS, MODEL_STATUS, ORIGIN_VARIANTS, UPMS, VARIANTS,
    build_followup_fixture, build_suite, delta_predictions, followup_expected, round_delta_away,
)


class B1MetricFollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.path = Path(cls.directory.name)
        cls.manifest = build_suite(cls.path)
        cls.entries = {(e["upem"], e["variant"]): e for e in cls.manifest["entries"]}

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def font(self, upem, variant):
        return TTFont(self.path / self.entries[upem, variant]["path"], recalcTimestamp=False)

    def test_minimal_plan_preserves_546_cases_and_appends_four_normalization_controls(self):
        self.assertEqual(len(self.entries), 16)
        counts = {"fresh_height_discriminator": 0, "vorg_storage_control": 0, "exact_normalization_grid_control": 0}
        for entry in self.entries.values():
            original_count = 51 if entry["variant"] in HEIGHT_VARIANTS else 6
            added_count = 1 if entry["variant"] in ("gvar", "vvar") else 0
            self.assertEqual(len(entry["requests"]), original_count + added_count)
            for index, request in enumerate(entry["requests"][:original_count]):
                self.assertNotEqual(request["case_group"], "exact_normalization_grid_control")
            if added_count:
                self.assertEqual(entry["requests"][-1]["axes"], {"WDTH": 0.0, "HGHT": EXACT_NORMALIZATION_Y})
                self.assertEqual(entry["requests"][-1]["case_group"], "exact_normalization_grid_control")
            for request in entry["requests"]:
                counts[request["case_group"]] += 1
                self.assertEqual(request["partition"], "holdout")
        self.assertEqual(counts, {"fresh_height_discriminator": 510, "vorg_storage_control": 36,
                                  "exact_normalization_grid_control": 4})

    def test_exact_normalization_control_rejects_universal_nondefault_minus_one(self):
        self.assertNotIn(EXACT_NORMALIZATION_Y, set(TRAINING_Y) | set(HOLDOUT_Y) | set(FOLLOWUP_Y))
        for upem in UPMS:
            prediction = delta_predictions(EXACT_NORMALIZATION_Y, upem)
            self.assertEqual(prediction["phantom_height_integer"], 1125)
            self.assertEqual(prediction["before_final_truncation"], {"numerator": 1125, "denominator": 1, "value": 1125.0})
            self.assertEqual(prediction["prediction"], 1125)
            self.assertNotEqual(prediction["prediction"], prediction["phantom_height_integer"] - 1)
            self.assertEqual(prediction["vvar_truncate_continuous"]["prediction"], 1124)

    def test_fresh_coordinates_do_not_reuse_any_first_stage_height(self):
        self.assertFalse(set(FOLLOWUP_Y) & (set(TRAINING_Y) | set(HOLDOUT_Y)))
        self.assertEqual(len(set(FOLLOWUP_Y)), 17)
        self.assertEqual(FOLLOWUP_X, (-0.375, 0.0, 0.375))
        for coordinate in (*FOLLOWUP_Y, *FOLLOWUP_X, EXACT_NORMALIZATION_Y):
            self.assertEqual((Fraction(coordinate) * 16384).denominator, 1)
            self.assertEqual((Fraction(coordinate) * 65536).denominator, 1)

    def test_delta_half_ties_are_away_from_zero_and_sign_symmetric(self):
        for value, expected in ((Fraction(1, 2), 1), (Fraction(-1, 2), -1),
                                (Fraction(105, 2), 53), (Fraction(-105, 2), -53),
                                (Fraction(7, 16), 0), (Fraction(-7, 16), 0)):
            self.assertEqual(round_delta_away(value), expected)
        for y in FOLLOWUP_Y:
            a, b = delta_predictions(y, 1024), delta_predictions(-y, 1024)
            self.assertEqual(a["phantom_height_integer"] + b["phantom_height_integer"], 2000)

    def test_negative_half_tie_discriminates_from_absolute_phantom_rounding(self):
        entry = self.entries[1024, "gvar"]
        request = next(r for r in entry["requests"] if r["axes"] == {"WDTH": 0.0, "HGHT": -0.875})
        candidate = entry["predictions_round_delta"][request["id"]]
        self.assertEqual(candidate["top_delta"], {"numerator": -105, "denominator": 2, "value": -52.5})
        self.assertEqual(candidate["round_away_top"], -53)
        self.assertEqual(candidate["round_away_bottom"], 79)
        self.assertEqual(candidate["phantom_height_integer"], 868)
        self.assertEqual(candidate["prediction"], 868)
        self.assertEqual(request["hypotheses"]["round_each_phantom"], 869)
        self.assertEqual(delta_predictions(-0.875, 1000)["prediction"], 867)

    def test_prediction_retains_exact_em_quantization_basis(self):
        prediction = delta_predictions(0.0625, 1000)
        self.assertEqual(prediction["phantom_height_integer"], 1010)
        self.assertEqual(prediction["em16_16_integer"], 66191)
        value = prediction["before_final_truncation"]
        self.assertEqual(Fraction(value["numerator"], value["denominator"]), Fraction(66191 * 1000, 65536))
        self.assertEqual(prediction["prediction"], 1009)
        self.assertEqual(delta_predictions(0.0625, 1024)["prediction"], 1010)
        self.assertEqual(prediction["vvar_truncate_continuous"]["prediction"], 1009)

    def test_new_delta_candidate_is_shift_invariant_but_old_candidates_are_retained(self):
        for upem in UPMS:
            baseline, shifted = self.entries[upem, "gvar"], self.entries[upem, "phantom_shift_91"]
            common_predictions = {key: baseline["predictions_round_delta"][key]
                                  for key in shifted["predictions_round_delta"]}
            self.assertEqual(common_predictions, shifted["predictions_round_delta"])
            for left, right in zip(baseline["requests"], shifted["requests"]):
                self.assertEqual(left["hypotheses"]["height"], right["hypotheses"]["height"])
                self.assertEqual(right["hypotheses"]["top"]["value"] - left["hypotheses"]["top"]["value"], 91)
                self.assertIn("coordinate_first", right["hypotheses"])

    def test_serialized_outline_follows_its_own_unrounded_model(self):
        for upem in UPMS:
            for variant in ("gvar", "phantom_only", "hvar_vvar_odd_default_vorg"):
                with self.font(upem, variant) as font:
                    for request in self.entries[upem, variant]["requests"]:
                        glyph_set = font.getGlyphSet(location=request["axes"], normalized=True)
                        pen = BoundsPen(glyph_set); glyph_set["witness"].draw(pen)
                        x, y, width, height = request["expected"]["witness_bounds"]
                        self.assertEqual(pen.bounds, (x, y, x+width, y+height))
                        if variant == "phantom_only":
                            self.assertEqual(height, 1000)
                            self.assertNotEqual(request["expected"]["advance_height"], height)

    def test_metric_variation_coefficients_stay_equivalent_with_odd_base_and_vorg(self):
        checks = 0
        for upem in UPMS:
            for variant in ("vvar", "hvar_vvar", *ORIGIN_VARIANTS):
                with self.font(upem, variant) as font:
                    for request in self.entries[upem, variant]["requests"]:
                        x, y = request["axes"]["WDTH"], request["axes"]["HGHT"]
                        for tag, field, expected in (("HVAR", "AdvWidthMap", 200*x), ("VVAR", "AdvHeightMap", 150*y)):
                            if tag not in font: continue
                            table = font[tag].table
                            instance = VarStoreInstancer(table.VarStore, font["fvar"].axes, request["axes"])
                            self.assertEqual(instance[getattr(table, field).mapping["witness"]], expected)
                            if tag == "VVAR": self.assertIsNone(table.VOrgMap)
                            checks += 1
        self.assertEqual(checks, 380)

    def test_vorg_addition_changes_only_vorg_and_no_x_is_stored(self):
        for upem in UPMS:
            for variant in ("hvar_vvar_vorg", "hvar_vvar_odd_default_vorg"):
                entry = self.entries[upem, variant]
                self.assertEqual(entry["changed_tables_vs_comparison"], ["VORG"])
                self.assertEqual(entry["changed_fields"], [{"field": "VORG", "before": None, "after": {"defaultVertOriginY": 911}}])
                with self.font(upem, variant) as font:
                    self.assertEqual(font["VORG"].defaultVertOriginY, 911)
                    self.assertEqual(font["VORG"].VOriginRecords, {})
                    self.assertEqual(len(font.reader["VORG"]), 8)

    def test_odd_default_changes_only_stored_advance_and_derived_header(self):
        for upem in UPMS:
            entry = self.entries[upem, "hvar_vvar_odd_default"]
            self.assertEqual(entry["comparison_variant"], "hvar_vvar")
            self.assertEqual(entry["changed_tables_vs_comparison"], ["hhea", "hmtx"])
            self.assertEqual(entry["changed_fields"], [
                {"field": "hhea.advanceWidthMax", "before": 1000, "after": 1001},
                {"field": "hmtx.witness[0]", "before": 1000, "after": 1001},
            ])
            hypotheses = entry["origin_x_storage_hypotheses"]
            self.assertEqual(hypotheses["exact_stored_half"], {"numerator": 1001, "denominator": 2, "value": 500.5})
            self.assertEqual(hypotheses["truncated_stored_half"], 500)
            for request in entry["requests"]:
                x, y = request["axes"]["WDTH"], request["axes"]["HGHT"]
                even = followup_expected(x, y, "hvar_vvar")
                odd = request["expected"]
                self.assertEqual(odd["advance_width"], even["advance_width"] + 1)
                self.assertEqual(odd["vertical_origin_x_current_half_width"], even["vertical_origin_x_current_half_width"] + 0.5)
                self.assertEqual(odd["vertical_origin_x_default_half_width"], 500.5)
                self.assertEqual(odd["witness_bounds"], even["witness_bounds"])

    def test_upem_pairs_are_identical_except_upem_and_required_checksum(self):
        for variant in VARIANTS:
            with self.font(1000, variant) as a, self.font(1024, variant) as b:
                left, right = comparison_table_bytes(a), comparison_table_bytes(b)
                self.assertEqual(left.keys(), right.keys())
                for tag in left:
                    x, y = left[tag], right[tag]
                    if tag == "head": x, y = x[:18] + bytes(2) + x[20:], y[:18] + bytes(2) + y[20:]
                    self.assertEqual(x, y, (variant, tag))

    def test_models_are_inferences_and_manifest_never_claims_native_pass(self):
        self.assertEqual(self.manifest["model_status"], MODEL_STATUS)
        self.assertEqual(self.manifest["native_acceptance"], "NOT_RUN")
        self.assertEqual(self.manifest["original_font_acceptance"], "NOT_ESTABLISHED")
        self.assertFalse(self.manifest["measurement_correction_applied"])
        self.assertEqual(self.manifest["strict_budget_font_units"], 1/32)
        for entry in self.entries.values():
            self.assertEqual(set(entry["predictions_round_delta"]), {r["id"] for r in entry["requests"]})
            self.assertEqual(entry["sha256"], hashlib.sha256((self.path / entry["path"]).read_bytes()).hexdigest())
            for prediction in entry["predictions_round_delta"].values():
                self.assertEqual(prediction["status"], MODEL_STATUS)

    def test_invalid_candidate_inputs_and_variants_fail(self):
        for value in (math.inf, -math.inf, math.nan, True, "0.0625"):
            with self.subTest(value=value), self.assertRaises(ValueError): delta_predictions(value, 1000)
        with self.assertRaises(ValueError): delta_predictions(2, 1000)
        with self.assertRaises(ValueError): delta_predictions(0, 1128)
        with self.assertRaises(ValueError): build_followup_fixture(1000, "unregistered")
        with self.assertRaises(ValueError): followup_expected(0, 0, "unregistered")


if __name__ == "__main__":
    unittest.main()
