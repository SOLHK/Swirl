"""Original A3 diagnostics controls; no Apple observations are invented here."""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from probe_axis_a3_hvar import (ALL_MODELS, EXTRA_MODELS, FOCUS, LIMIT,
    METRIC_GIDS, MODEL_NAMES, TAGS, a3_mappings, conditional_grid, hvar_cases,
    metric_residuals)


RANGES = {"WDTH": (1., 500., 1000.), "wght": (100., 499., 900.),
          "HGHT": (1., 500., 1000.)}


def fixture(ranges=RANGES):
    font = {"fvar": SimpleNamespace(axes=[SimpleNamespace(axisTag=tag, minValue=a,
        defaultValue=b, maxValue=c) for tag, (a, b, c) in ranges.items()])}
    records = {tag: [(-1., -1.), (0., 0.), (1., 1.)] for tag in TAGS}
    return font, records


class AxisA3HvarCases(unittest.TestCase):
    def test_archived_point_is_preserved_exactly_and_every_case_keeps_three_axes(self):
        before = deepcopy(RANGES)
        rows = hvar_cases(RANGES)
        self.assertEqual(len(rows), 34)
        self.assertEqual(rows[0]["location"], FOCUS)
        self.assertEqual(rows[0]["label"], "archived_face18_fresh_triple_7")
        for row in rows:
            self.assertEqual(set(row["location"]), set(TAGS))
            for tag, value in row["location"].items():
                self.assertLessEqual(RANGES[tag][0], value)
                self.assertLessEqual(value, RANGES[tag][2])
        self.assertEqual(RANGES, before)
        rows[0]["location"]["WDTH"] = 1.
        self.assertEqual(hvar_cases(RANGES)[0]["location"]["WDTH"], 395.1762070327519)

    def test_reset_controls_separate_width_weight_and_height(self):
        rows = {row["label"]: row for row in hvar_cases(RANGES)}
        defaults = {tag: RANGES[tag][1] for tag in TAGS}
        for tag in TAGS:
            expected = dict(FOCUS); expected[tag] = defaults[tag]
            self.assertEqual(rows[f"{tag}_reset_to_default"]["location"], expected)
            expected = dict(defaults); expected[tag] = FOCUS[tag]
            self.assertEqual(rows[f"{tag}_only"]["location"], expected)

    def test_nextafter_and_grid_steps_do_not_round_back_into_original_request(self):
        rows = {row["label"]: row for row in hvar_cases(RANGES)}
        for tag in TAGS:
            lower = rows[f"{tag}_binary64_below"]["location"][tag]
            upper = rows[f"{tag}_binary64_above"]["location"][tag]
            self.assertLess(lower, FOCUS[tag]); self.assertGreater(upper, FOCUS[tag])
            self.assertEqual(math.nextafter(lower, math.inf), FOCUS[tag])
            self.assertEqual(math.nextafter(upper, -math.inf), FOCUS[tag])
            self.assertEqual(rows[f"{tag}_user_fixed16_above"]["location"][tag] - FOCUS[tag], 1 / 65536)
        self.assertEqual(len({tuple(row["location"][tag] for tag in TAGS)
                              for row in rows.values()}), 34)

    def test_fresh_holdouts_are_deterministic_and_not_derived_from_the_failure(self):
        rows = hvar_cases(RANGES)
        fresh = [row for row in rows if row["group"] == "fresh_holdout"]
        self.assertEqual(len(fresh), 8)
        self.assertEqual(rows, hvar_cases(RANGES))
        self.assertTrue(all(row["location"] != FOCUS for row in fresh))
        # A changed default affects normalization/control positions but cannot
        # move random holdouts; they depend only on the frozen seed and bounds.
        changed = deepcopy(RANGES); changed["wght"] = (100., 450., 900.)
        self.assertEqual(fresh, [row for row in hvar_cases(changed) if row["group"] == "fresh_holdout"])

    def test_invalid_axis_contracts_fail_before_native_execution(self):
        for changed in ({"WDTH": RANGES["WDTH"]}, {**RANGES, "wght": (100., True, 900.)},
                        {**RANGES, "WDTH": (math.nan, 500., 1000.)},
                        {**RANGES, "HGHT": (0., 1., 2.)},
                        {**RANGES, "WDTH": (500., 500., 500.)}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                hvar_cases(changed)


class AxisA3HvarModels(unittest.TestCase):
    def test_all_global_models_preserve_raw_record_order_and_duplicates(self):
        font, records = fixture()
        for tag in TAGS:
            records[tag] = [(-1., -1.), (0., 0.), (1., .5), (1., 1.)]
        before = deepcopy(records)
        location = {tag: RANGES[tag][2] for tag in TAGS}
        result = a3_mappings(font, records, location)
        self.assertEqual(set(result), set(ALL_MODELS))
        self.assertEqual(len(result), 7)
        for design in result.values():
            self.assertEqual(design, dict.fromkeys(TAGS, .5))
        self.assertEqual(records, before)

    def test_default_is_zero_and_no_axis_is_dropped(self):
        font, records = fixture()
        for design in a3_mappings(font, records, {tag: RANGES[tag][1] for tag in TAGS}).values():
            self.assertEqual(design, dict.fromkeys(TAGS, 0.))

    def test_negative_normalized_rounding_alternative_is_falsifiable_at_focus_width(self):
        font, records = fixture()
        result = a3_mappings(font, records, FOCUS)
        # This is an authored identity-avar numeric result, not a new native
        # observation of the Apple sample. The alternatives deliberately make
        # different predictions instead of choosing whichever later fits.
        self.assertEqual(result[MODEL_NAMES[0]]["WDTH"], -3441 / 16384)
        self.assertEqual(result[MODEL_NAMES[1]]["WDTH"], -3441 / 16384)
        self.assertEqual(result[EXTRA_MODELS[4]]["WDTH"], -3442 / 16384)
        self.assertEqual(result[MODEL_NAMES[1]]["HGHT"], 2601 / 16384)

    def test_one_global_operation_order_can_differ_without_changing_source_axes(self):
        ranges = {tag: (37., 437., 837.) for tag in TAGS}
        font, records = fixture(ranges)
        location = dict.fromkeys(TAGS, 437.); location["wght"] = 236.9817
        result = a3_mappings(font, records, location)
        self.assertEqual(result[MODEL_NAMES[0]]["wght"], -8192 / 16384)
        self.assertEqual(result[MODEL_NAMES[1]]["wght"], -8193 / 16384)
        for name in ALL_MODELS:
            self.assertEqual(result[name]["WDTH"], 0.)
            self.assertEqual(result[name]["HGHT"], 0.)

    def test_conditional_lattice_contains_all_27_predeclared_neighbors(self):
        center = {"WDTH": -3441 / 16384, "wght": -138 / 16384, "HGHT": 2601 / 16384}
        original = deepcopy(center)
        cells = conditional_grid(center)
        self.assertEqual(len(cells), 27)
        self.assertEqual(len({tuple(row["design_location"][tag] for tag in TAGS) for row in cells}), 27)
        self.assertEqual(cells[13]["design_location"], center)
        self.assertEqual(cells[13]["offset_f2dot14"], dict.fromkeys(TAGS, 0))
        self.assertEqual(center, original)
        for tag in TAGS:
            self.assertEqual({row["offset_f2dot14"][tag] for row in cells}, {-1, 0, 1})

    def test_lattice_refuses_non_grid_inputs_and_never_escapes_design_space(self):
        for invalid in ({"WDTH": .1, "wght": 0., "HGHT": 0.},
                        {"WDTH": False, "wght": 0., "HGHT": 0.},
                        {"WDTH": math.inf, "wght": 0., "HGHT": 0.},
                        {"WDTH": 2., "wght": 0., "HGHT": 0.}):
            with self.assertRaises(ValueError):
                conditional_grid(invalid)
        cells = conditional_grid(dict.fromkeys(TAGS, 1.))
        self.assertEqual(len(cells), 8)
        self.assertTrue(all(-1 <= value <= 1 for row in cells for value in row["design_location"].values()))


class AxisA3HvarResiduals(unittest.TestCase):
    class Metrics:
        def at(self, gid, design):
            return {"advance_width": 1000. + gid + 200 * design["WDTH"] + gid * design["wght"]}

    def test_small_real_error_is_retained_without_being_renamed_exact(self):
        metrics = self.Metrics()
        design = dict.fromkeys(TAGS, 0.)
        actual = {gid: {"advance_width": metrics.at(gid, design)["advance_width"]} for gid in METRIC_GIDS}
        actual[5]["advance_width"] += .01220703125
        actual[12]["advance_width"] -= .00390625
        result = metric_residuals(metrics, actual, design)
        self.assertEqual(result["maximum_error"], .01220703125)
        self.assertTrue(result["within_1_32"])
        self.assertFalse(result["exact"])
        self.assertEqual(result["four_metric_residuals"][0]["signed_error"], .01220703125)
        self.assertEqual(result["four_metric_residuals"][1]["signed_error"], -.00390625)
        serialized = json.dumps(result)
        self.assertNotIn("advance_width", serialized)
        self.assertNotIn("1005", serialized)
        self.assertNotIn("commands", serialized)

    def test_unchanged_threshold_distinguishes_exact_within_and_outside(self):
        metrics = self.Metrics(); design = dict.fromkeys(TAGS, 0.)
        actual = {gid: {"advance_width": metrics.at(gid, design)["advance_width"]} for gid in METRIC_GIDS}
        self.assertTrue(metric_residuals(metrics, actual, design)["exact"])
        actual[5]["advance_width"] += LIMIT
        self.assertTrue(metric_residuals(metrics, actual, design)["within_1_32"])
        actual[5]["advance_width"] = math.nextafter(actual[5]["advance_width"], math.inf)
        self.assertFalse(metric_residuals(metrics, actual, design)["within_1_32"])

    def test_nonfinite_residual_cannot_be_a_success(self):
        actual = {gid: {"advance_width": math.nan} for gid in METRIC_GIDS}
        with self.assertRaisesRegex(ValueError, "a3_nonfinite_HVAR_residual"):
            metric_residuals(self.Metrics(), actual, dict.fromkeys(TAGS, 0.))


if __name__ == "__main__":
    unittest.main()
