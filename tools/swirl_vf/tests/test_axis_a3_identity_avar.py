"""Arithmetic and cohort contract tests; never substitute for Apple evidence."""
from copy import deepcopy
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from probe_axis_a3_identity_avar import (ALL_MODELS, ANCHOR_MODES, BOUNDARY_EPSILON,
    BOUNDARY_Q, CANDIDATE, DOUBLE_CONTROL, FOCUS, LIMIT, MODEL_NAMES,
    PRIOR_NEAREST_FAILURES, TAGS, identity_cases, identity_mappings,
    identity_records, metric_summary, mode_case_indices)


RANGES = {"WDTH": (1., 500., 1000.), "wght": (100., 499., 900.),
          "HGHT": (1., 500., 1000.)}
WEIGHT_RECORDS = [(-1., -1.), (-1., -.81597900390625), (-.75, -.57196044921875),
    (-.5, -.387939453125), (-.25, -.18798828125), (-.00244140625, 0.),
    (0., 0.), (0., .00396728515625), (.25, .19598388671875),
    (.5, .39599609375), (.75, .5999755859375), (1., .79998779296875), (1., 1.)]


def fixture():
    font = {"fvar": SimpleNamespace(axes=[SimpleNamespace(axisTag=tag, minValue=a,
        defaultValue=b, maxValue=c) for tag, (a, b, c) in RANGES.items()])}
    records = {tag: [(-1., -1.), (0., 0.), (1., 1.)] for tag in TAGS}
    records["wght"] = deepcopy(WEIGHT_RECORDS)
    return font, records


class IdentityAvarRecognition(unittest.TestCase):
    def test_only_strict_raw_identity_maps_are_recognized(self):
        for rows in ([(-1., -1.), (0., 0.), (1., 1.)],
                     [(-1., -1.), (-.5, -.5), (0., 0.), (.25, .25), (1., 1.)]):
            self.assertTrue(identity_records(rows))

    def test_duplicates_order_nonidentity_and_invalid_values_are_not_normalized_away(self):
        for rows in (WEIGHT_RECORDS, [(-1., -1.), (0., 0.), (0., 0.), (1., 1.)],
                     [(-1., -1.), (1., 1.), (0., 0.)], [(-1., -1.), (1., 1.)],
                     [(-1., -1.), (.25, .25), (1., 1.)],
                     [(-1., -1.), (0., 0.), (1., .9)],
                     [(-1., -1.), (False, 0.), (1., 1.)],
                     [(-1., -1.), (math.nan, 0.), (1., 1.)],
                     [(-1., -1.), (0., 0.), (.1, .1), (1., 1.)]):
            before = repr(rows)
            with self.subTest(rows=rows):
                self.assertFalse(identity_records(rows))
                self.assertEqual(repr(rows), before)


class IdentityAvarMappings(unittest.TestCase):
    def test_focus_candidate_changes_identity_width_only_and_keeps_raw_records(self):
        font, records = fixture(); original = deepcopy(records)
        result = identity_mappings(font, records, FOCUS)
        self.assertEqual(set(result), set(ALL_MODELS))
        self.assertEqual(result[MODEL_NAMES[1]]["WDTH"], -3441 / 16384)
        self.assertEqual(result[CANDIDATE], {"WDTH": -3442 / 16384,
            "wght": -138 / 16384, "HGHT": 2601 / 16384})
        self.assertEqual(result[DOUBLE_CONTROL], result[CANDIDATE])
        self.assertEqual(records, original)

    def test_nonidentity_axes_always_reuse_previous_float32_truncate_rule(self):
        font, records = fixture()
        for location in (FOCUS, *(row["location"] for row in PRIOR_NEAREST_FAILURES),
                         {"WDTH": 500., "wght": 499.006199, "HGHT": 500.},
                         {"WDTH": 500., "wght": 499.006201, "HGHT": 500.}):
            result = identity_mappings(font, records, location)
            for name in (CANDIDATE, DOUBLE_CONTROL):
                self.assertEqual(result[name]["wght"], result[MODEL_NAMES[1]]["wght"])

    def test_candidate_does_not_claim_all_axes_are_identity_from_axis_names(self):
        font, records = fixture()
        records["WDTH"] = deepcopy(WEIGHT_RECORDS)
        records["HGHT"] = [(-1., -1.), (0., 0.), (0., 0.), (1., 1.)]
        result = identity_mappings(font, records, FOCUS)
        self.assertEqual(result[CANDIDATE], result[MODEL_NAMES[1]])
        self.assertEqual(result[DOUBLE_CONTROL], result[MODEL_NAMES[1]])

    def test_defaults_extrema_and_original_axis_order_are_retained(self):
        font, records = fixture()
        for offset in range(3):
            location = {tag: values[offset] for tag, values in RANGES.items()}
            result = identity_mappings(font, records, location)
            for name in ALL_MODELS:
                self.assertEqual(tuple(result[name]), TAGS)
                for tag in ("WDTH", "HGHT"):
                    self.assertEqual(result[name][tag], (-1., 0., 1.)[offset])


class IdentityAvarCohort(unittest.TestCase):
    def setUp(self):
        self.axes = {face: deepcopy(RANGES) for face in range(32)}

    def test_frozen_new_cohort_counts_and_distinctness(self):
        rows = identity_cases(self.axes)
        self.assertEqual(len(rows), 103)
        self.assertEqual(sum(row["is_holdout"] for row in rows), 100)
        self.assertEqual(sum(row["group"] == "fresh_random_holdout" for row in rows), 64)
        self.assertEqual(sum(row["group"] == "rounding_boundary_holdout" for row in rows), 36)
        self.assertEqual(sum(row["direct_native_HVF"] for row in rows), 35)
        for face in range(32):
            fresh = [row for row in rows if row["face_index"] == face and row["group"] == "fresh_random_holdout"]
            self.assertEqual(len(fresh), 2)
            self.assertTrue(fresh[0]["direct_native_HVF"])
        self.assertEqual(len({(row["face_index"], *(row["location"][tag] for tag in TAGS)) for row in rows}), 103)

    def test_old_failures_are_explicit_controls_and_not_holdouts(self):
        rows = [row for row in identity_cases(self.axes) if not row["is_holdout"]]
        self.assertEqual([row["location"] for row in rows],
                         [FOCUS, *(row["location"] for row in PRIOR_NEAREST_FAILURES)])
        self.assertTrue(all(row["group"] == "historical_control" and row["face_index"] == 18 for row in rows))

    def test_midpoint_cases_straddle_both_positive_and_negative_grid_boundaries(self):
        rows = [row for row in identity_cases(self.axes) if row["group"] == "rounding_boundary_holdout"]
        for index in range(0, len(rows), 3):
            lower, middle, upper = rows[index:index + 3]
            tag = middle["boundary_axis"]
            self.assertLess(lower["location"][tag], middle["location"][tag])
            self.assertLess(middle["location"][tag], upper["location"][tag])
            self.assertEqual(middle["location"][tag], middle["user_midpoint"])
            self.assertIn(middle["normalized_midpoint"] * 16384 - .5, BOUNDARY_Q)
            self.assertEqual([row["normalized_offset"] for row in (lower, middle, upper)],
                             [-BOUNDARY_EPSILON, 0., BOUNDARY_EPSILON])
            for row in (lower, middle, upper):
                self.assertTrue(all(row["location"][other] == RANGES[other][1] for other in TAGS if other != tag))

    def test_generation_is_repeatable_does_not_mutate_axes_and_randomness_ignores_defaults(self):
        before = deepcopy(self.axes); first = identity_cases(self.axes)
        self.assertEqual(first, identity_cases(self.axes)); self.assertEqual(before, self.axes)
        self.axes[0]["wght"] = (100., 450., 900.)
        self.assertEqual(first[:64], identity_cases(self.axes)[:64])

    def test_native_mode_scope_prevents_repeating_full_production_suite(self):
        rows = identity_cases(self.axes)
        for mode in ANCHOR_MODES:
            self.assertEqual(len(mode_case_indices(rows, mode)), 103)
        production = mode_case_indices(rows, "production")
        self.assertEqual(len(production), 3)
        self.assertTrue(all(not rows[index]["is_holdout"] for index in production))
        self.assertEqual(4 * 5 * (103 + 103 + 3), 4180)
        with self.assertRaises(ValueError):
            mode_case_indices(rows, "unknown")

    def test_invalid_axes_fail_before_native(self):
        missing = deepcopy(self.axes); del missing[0]
        with self.assertRaises(ValueError):
            identity_cases(missing)
        self.axes[20]["HGHT"] = (1., 500., 500.)
        with self.assertRaises(ValueError):
            identity_cases(self.axes)


class IdentityAvarEvidence(unittest.TestCase):
    def test_safe_summary_does_not_conflate_small_error_with_exactness(self):
        observations = []
        for label, error, holdout in (("exact", 0., True), ("small", .01220703125, True),
                                      ("threshold", LIMIT, False), ("outside", LIMIT * 2, False)):
            check = {"maximum_error": error, "exact": error == 0., "within_1_32": error <= LIMIT,
                "four_metric_residuals": [{"glyph_id": 5, "signed_error": -error, "absolute_error": error}]}
            observations.append({"face_index": 18, "label": label, "is_holdout": holdout,
                                 "model_checks": {CANDIDATE: check}})
        summary = metric_summary(observations, CANDIDATE)
        self.assertEqual(summary["holdouts"], {"checks": 2, "exact_matches": 1,
            "outside_1_32": 0, "maximum_error": .01220703125})
        self.assertEqual(summary["historical_controls"]["outside_1_32"], 1)
        self.assertEqual([row["label"] for row in summary["nonexact_observations"]],
                         ["small", "threshold", "outside"])
        self.assertEqual(summary["nonexact_observations"][0]["four_metric_residuals"][0]["signed_error"], -.01220703125)


if __name__ == "__main__":
    unittest.main()
