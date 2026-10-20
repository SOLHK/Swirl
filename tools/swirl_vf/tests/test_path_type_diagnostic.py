"""Independent finite geometry for a diagnostic that cannot override the gate."""
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from calibrate_hvf_geometry import discrepancy, native_paths, portable_paths
from diagnose_path_types import (RawSegment, canonical_paths, compare_preserved_quadratics, diagnose_paths,
                                 raw_coretext_paths, raw_native_paths, raw_portable_paths)
from probe_user_axis_geometry import coretext_paths


def line(p, r):
    return RawSegment("L", (p, r))


def quad(p, q, r):
    return RawSegment("Q", (p, q, r))


class RawPathDiagnosticTests(unittest.TestCase):
    def test_raw_parsers_preserve_controls_and_legacy_close_policy(self):
        events = [["begin_part", 17], ["begin_path"], ["move", 1., 2.],
                  ["quad", 2., 7., 5., 2.], ["line", 6., 1.],
                  ["close"], ["end_path"], ["end_part", 17]]
        commands = [["moveTo", 1., 2.], ["qCurveTo", 2., 7., 5., 2.],
                    ["lineTo", 6., 1.], ["closePath"]]
        native = raw_native_paths(events)
        coretext = raw_coretext_paths(commands)
        self.assertEqual(native, coretext)
        self.assertEqual([x.kind for x in native[0]], ["Q", "L", "L"])
        self.assertEqual(native[0][0].points[1], (2., 7.))
        self.assertEqual(discrepancy(canonical_paths(native), native_paths(events)), (0., 3))
        self.assertEqual(discrepancy(canonical_paths(coretext), coretext_paths(commands)), (0., 3))
        points = [np.asarray([[1., 2.], [2., 7.], [5., 2.], [3., 2.]])]
        private = raw_portable_paths(points)
        self.assertEqual([x.kind for x in private[0]], ["Q", "Q"])
        self.assertEqual(discrepancy(canonical_paths(private), portable_paths(points)), (0., 2))

    def test_tiny_coincident_endpoints_do_not_hide_the_original_type_failure(self):
        # A tiny control perturbation crosses the pre-existing short-chord
        # branch. The raw difference is measured, not reclassified as a PASS.
        lhs = [[quad((0., 0.), (9.9e-11, 0.), (1e-12, 0.))]]
        rhs = [[quad((0., 0.), (1.01e-10, 0.), (1e-12, 0.))]]
        report = diagnose_paths(lhs, rhs)
        self.assertEqual(report["unchanged_strict_comparison"]["reason"], "segment_types_differ")
        self.assertEqual(report["correspondence_status"], "complete")
        self.assertLess(report["maximum_parametric_difference_upper_bound"], 2e-12)
        detail = report["paths"][0]["type_differences"][0]
        self.assertEqual((detail["left_canonical_kind"], detail["right_canonical_kind"]), ("L", "Q"))
        self.assertTrue(detail["left_shape"]["legacy_short_chord_branch"])
        self.assertTrue(detail["right_shape"]["legacy_short_chord_branch"])
        self.assertFalse(report["mapping_accepted"])

    def test_line_degree_elevation_is_exact_only_at_midpoint(self):
        straight = [[line((0., 0.), (2., 0.))]]
        midpoint = [[quad((0., 0.), (1., 0.), (2., 0.))]]
        biased = [[quad((0., 0.), (.25, 0.), (2., 0.))]]
        self.assertEqual(diagnose_paths(straight, midpoint)["maximum_parametric_difference_upper_bound"], 0.)
        report = diagnose_paths(straight, biased)
        self.assertEqual(report["maximum_parametric_difference_upper_bound"], .375)
        # The old canonicalizer considers collinear segments equal. The new
        # diagnostic preserves that result but does not erase parameter speed.
        self.assertEqual(report["unchanged_strict_comparison"]["maximum_point_error"], 0.)
        detail = report["paths"][0]["type_differences"][0]
        self.assertTrue(detail["right_shape"]["exact_collinearity"])
        self.assertEqual(detail["right_shape"]["same_parameter_chord_difference_upper_bound"], .375)

    def test_genuine_curvature_with_identical_endpoints_is_not_called_flat(self):
        report = diagnose_paths([[line((0., 0.), (2., 0.))]],
                                [[quad((0., 0.), (1., 20.), (2., 0.))]])
        self.assertEqual(report["maximum_parametric_difference_upper_bound"], 10.)
        self.assertEqual(report["unchanged_strict_comparison"]["reason"], "segment_types_differ")
        detail = report["paths"][0]["type_differences"][0]
        self.assertFalse(detail["right_shape"]["exact_collinearity"])
        self.assertEqual(detail["right_shape"]["control_line_distance_squared_upper_bound"], 400.)

    def test_collinearity_alone_does_not_hide_control_overshoot(self):
        report = diagnose_paths([[line((0., 0.), (2., 0.))]],
                                [[quad((0., 0.), (4., 0.), (2., 0.))]])
        self.assertEqual(report["maximum_parametric_difference_upper_bound"], 1.5)
        detail = report["paths"][0]["type_differences"][0]
        self.assertTrue(detail["right_shape"]["exact_collinearity"])
        self.assertFalse(detail["right_shape"]["control_projection_inside_chord"])
        self.assertFalse(detail["right_shape"]["legacy_linear"])
        self.assertEqual(report["unchanged_strict_comparison"]["reason"], "segment_types_differ")

    def test_exact_extremum_between_sample_locations_rounds_outward(self):
        # The x difference has its positive maximum 4/7 at t=3/7.
        # Neither endpoints nor a midpoint-only sample could prove this bound.
        lhs = [[quad((.25, 0.), (1., 1.), (0., 0.))]]
        rhs = [[quad((0., 0.), (0., 1.), (0., 0.))]]
        report = diagnose_paths(lhs, rhs, endpoint_limit=1.)
        bound = report["maximum_parametric_difference_upper_bound"]
        self.assertGreaterEqual(Fraction(bound), Fraction(4, 7))
        self.assertLess(Fraction(math.nextafter(bound, -math.inf)), Fraction(4, 7))
        self.assertEqual(report["unchanged_strict_comparison"]["limit"], 1 / 32)

    def test_closed_contour_forward_rotation_preserves_order(self):
        path = [line((0., 0.), (3., 0.)), line((3., 0.), (0., 4.)), line((0., 4.), (0., 0.))]
        report = diagnose_paths([path], [path[1:] + path[:1]])
        self.assertEqual(report["paths"][0]["right_cyclic_shift"], 2)
        self.assertEqual(report["paths"][0]["endpoint_candidate_count"], 1)
        self.assertEqual(report["maximum_parametric_difference_upper_bound"], 0.)
        reverse = [line(item.points[-1], item.points[0]) for item in reversed(path)]
        rejected = diagnose_paths([path], [reverse])
        self.assertEqual(rejected["paths"][0]["status"], "endpoint_correspondence_absent")
        self.assertIsNone(rejected["maximum_parametric_difference_upper_bound"])

    def test_count_and_ambiguous_correspondence_never_produce_a_bound(self):
        zero = line((0., 0.), (0., 0.))
        for left, right, status in (([], [[zero]], "path_count_differs"),
                                    ([[zero]], [[zero, zero]], "incomplete"),
                                    ([[zero, zero]], [[zero, zero]], "incomplete")):
            report = diagnose_paths(left, right)
            self.assertEqual(report["correspondence_status"], status)
            self.assertIsNone(report["maximum_parametric_difference_upper_bound"])
        ambiguous = diagnose_paths([[zero, zero]], [[zero, zero]])
        self.assertEqual(ambiguous["paths"][0]["status"], "endpoint_correspondence_ambiguous")
        self.assertEqual(ambiguous["paths"][0]["endpoint_candidate_count"], 2)

    def test_safe_report_contains_no_raw_point_fields_or_values(self):
        # Distinctive source-like values may live in private objects, but not in
        # the scalar-only result or the dataclass's default repr.
        path = [[quad((123456.789, 234567.891), (123457.789, 234568.891), (123456.789, 234567.891))]]
        report = diagnose_paths(path, path)
        encoded = json.dumps(report, allow_nan=False)
        self.assertNotIn("123456.789", encoded)
        self.assertNotIn("234567.891", encoded)
        self.assertNotIn("123456.789", repr(path[0][0]))
        def check(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & {"points", "start", "end", "control", "commands", "events"})
                for nested in value.values():
                    check(nested)
            elif isinstance(value, list):
                for nested in value:
                    check(nested)
        check(report)

    def test_invalid_and_nonfinite_inputs_fail_closed(self):
        for points in (((0., 0.), (math.nan, 0.)), ((0., 0.), (math.inf, 0.))):
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                RawSegment("L", points)
        for events in ((["begin_path"],), (["move", 0., 0.],),
                       (["begin_part", 3], ["end_part", 4]),
                       (["begin_path"], ["move", 0., 0.], ["cubic", 1., 2., 3., 4., 5., 6.]),
                       (["unknown"],), (["move", 0.],)):
            with self.assertRaises(ValueError):
                raw_native_paths(events)
        with self.assertRaisesRegex(ValueError, "unclosed"):
            raw_coretext_paths([["moveTo", 0., 0.]])
        with self.assertRaisesRegex(ValueError, "odd"):
            raw_portable_paths([[(0., 0.)]])
        with self.assertRaisesRegex(ValueError, "endpoint_limit"):
            diagnose_paths([], [], endpoint_limit=math.inf)


class PreservedQuadraticComparisonTests(unittest.TestCase):
    @staticmethod
    def projection_boundary_pair():
        # Both commands are genuinely Q. The second control is displaced only
        # 1e-13, but its projection on the 1e-6 chord crosses the old -1e-10 gate.
        return (quad((0., 0.), (0., 0.), (1e-6, 0.)),
                quad((0., 0.), (-1e-13, 0.), (1e-6, 0.)))

    def test_original_quadratic_controls_restore_a_type_only_failure(self):
        left, right = self.projection_boundary_pair()
        report = compare_preserved_quadratics([[left]], [[right]])
        self.assertEqual(report["legacy"]["status"], "rejected")
        self.assertEqual(report["legacy"]["reason"], "segment_types_differ")
        self.assertEqual(report["status"], "within_budget")
        self.assertEqual(report["maximum_point_error"], 1e-13)
        self.assertEqual(report["restored_segment_count"], 1)
        self.assertEqual(report["tested_segments"], 1)
        entry = report["restored_segments"][0]
        self.assertEqual((entry["path_index"], entry["left_segment_index"], entry["right_segment_index"]), (0, 0, 0))
        self.assertEqual((entry["left_raw_kind"], entry["right_raw_kind"]), ("Q", "Q"))
        self.assertEqual((entry["left_canonical_kind"], entry["right_canonical_kind"]), ("L", "Q"))
        self.assertFalse(report["mapping_accepted"])

    def test_full_control_point_gate_includes_exact_boundary_and_rejects_next_value(self):
        baseline = [[quad((0., 0.), (1., 0.), (2., 0.))]]
        for delta, status in ((1 / 32, "within_budget"),
                              (math.nextafter(1 / 32, math.inf), "outside_budget")):
            with self.subTest(delta=delta):
                report = compare_preserved_quadratics(baseline, [[quad((0., 0.), (1., delta), (2., 0.))]])
                self.assertEqual(report["status"], status)
                self.assertEqual(report["limit"], 1 / 32)
                self.assertEqual(report["maximum_point_error"], delta)
                self.assertEqual(report["legacy"]["reason"], "segment_types_differ")

    def test_curve_bound_below_budget_cannot_hide_a_control_point_failure(self):
        lhs = [[quad((0., 0.), (1., 0.), (2., 0.))]]
        rhs = [[quad((0., 0.), (1., .04), (2., 0.))]]
        self.assertEqual(diagnose_paths(lhs, rhs)["maximum_parametric_difference_upper_bound"], .02)
        report = compare_preserved_quadratics(lhs, rhs)
        self.assertEqual(report["status"], "outside_budget")
        self.assertEqual(report["maximum_point_error"], .04)

    def test_new_control_branch_cannot_round_an_exact_excess_down_onto_the_gate(self):
        gate, tiny = 1 / 32, 2. ** -60
        # Ordinary binary64 subtraction rounds this positive excess onto gate.
        self.assertEqual(gate - (-tiny), gate)
        lhs = [[quad((0., gate), (1., gate), (2., gate))]]
        rhs = [[quad((0., gate), (1., -tiny), (2., gate))]]
        report = compare_preserved_quadratics(lhs, rhs)
        self.assertEqual(report["status"], "outside_budget")
        self.assertEqual(report["maximum_point_error"], math.nextafter(gate, math.inf))
        self.assertEqual(report["restored_segment_count"], 1)

    def test_explicit_line_quadratic_type_mismatch_is_never_degree_elevated(self):
        lhs = [[line((0., 0.), (2., 0.))]]
        rhs = [[quad((0., 0.), (1., 2e-8), (2., 0.))]]
        for left, right in ((lhs, rhs), (rhs, lhs)):
            report = compare_preserved_quadratics(left, right)
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(report["reason"], "raw_segment_types_differ")
            self.assertIsNone(report["maximum_point_error"])
            self.assertEqual(report["restored_segments"], [])

    def test_existing_canonical_line_match_keeps_its_original_result(self):
        # Canonical L/L was already accepted even with nonmidpoint raw Q.
        # This patch does not change that pre-existing comparison rule.
        lhs = [[line((0., 0.), (2., 0.))]]
        rhs = [[quad((0., 0.), (.25, 0.), (2., 0.))]]
        report = compare_preserved_quadratics(lhs, rhs)
        self.assertEqual(report["status"], "within_budget")
        self.assertEqual(report["maximum_point_error"], 0.)
        self.assertEqual(report["restored_segment_count"], 0)
        self.assertEqual(report["paths"][0]["raw_control"]["method"], "legacy_unchanged")

    def test_forward_cycle_can_restore_but_reverse_order_gets_no_new_permission(self):
        original, perturbed = self.projection_boundary_pair()
        tail = [quad((1e-6, 0.), (2., 3.), (4., 0.)), quad((4., 0.), (2., -4.), (0., 0.))]
        lhs = [original, *tail]
        rhs = [perturbed, *tail]
        report = compare_preserved_quadratics([lhs], [rhs[1:] + rhs[:1]])
        self.assertEqual(report["status"], "within_budget")
        self.assertEqual(report["paths"][0]["raw_control"]["right_cyclic_shift"], 2)
        self.assertEqual(report["restored_segment_count"], 1)
        reversed_path = [quad(item.points[2], item.points[1], item.points[0]) for item in reversed(rhs)]
        reverse = compare_preserved_quadratics([lhs], [reversed_path])
        self.assertEqual(reverse["status"], "outside_budget")
        self.assertGreater(reverse["maximum_point_error"], 1 / 32)
        self.assertFalse(reverse["orientation_reversal_allowed"])

    def test_another_contours_numeric_failure_cannot_be_hidden_by_recovery(self):
        first, second = self.projection_boundary_pair()
        lhs = [[first], [line((10., 0.), (11., 0.))]]
        rhs = [[second], [line((10., .125), (11., .125))]]
        report = compare_preserved_quadratics(lhs, rhs)
        self.assertEqual(report["legacy"]["reason"], "segment_types_differ")
        self.assertEqual(report["restored_segment_count"], 1)
        self.assertEqual(report["paths"][1]["legacy"]["status"], "outside_budget")
        self.assertEqual(report["paths"][1]["raw_control"]["method"], "legacy_unchanged")
        self.assertEqual(report["status"], "outside_budget")
        self.assertEqual(report["maximum_point_error"], .125)

    def test_existing_matching_cycle_with_numeric_failure_is_not_reconsidered(self):
        # Shift 1 matches canonical L/Q types but has a large endpoint error.
        # Shift 0 has small raw-Q differences and *would* pass a generalized
        # recovery, which is intentionally forbidden for an old numeric fail.
        lhs = [[quad((0., 0.), (0., 0.), (1., 0.)),
                quad((1., 0.), (.5, 2e-8), (0., 0.))]]
        rhs = [[quad((0., 0.), (0., 2e-8), (1., 0.)),
                quad((1., 0.), (.5, 0.), (0., 0.))]]
        report = compare_preserved_quadratics(lhs, rhs)
        self.assertEqual(report["legacy"]["status"], "outside_budget")
        self.assertEqual(report["status"], "outside_budget")
        self.assertEqual(report["maximum_point_error"], report["legacy"]["maximum_point_error"])
        self.assertEqual(report["maximum_point_error"], 1.)
        self.assertEqual(report["restored_segment_count"], 0)
        self.assertEqual(report["paths"][0]["raw_control"]["method"], "legacy_unchanged")

    def test_count_mismatch_and_empty_paths_keep_the_original_policy(self):
        item = line((0., 0.), (0., 0.))
        for lhs, rhs, reason in (([], [[item]], "path_count_differs"),
                                  ([[item]], [[item, item]], "segment_count_differs")):
            report = compare_preserved_quadratics(lhs, rhs)
            self.assertEqual(report["status"], "rejected")
            self.assertEqual(report["legacy"]["reason"], reason)
            self.assertEqual(report["reason"], reason)
            self.assertIsNone(report["maximum_point_error"])
            self.assertEqual(report["restored_segment_count"], 0)
        for empty in ([], [[]], [[], []]):
            report = compare_preserved_quadratics(empty, empty)
            self.assertEqual(report["status"], "within_budget")
            self.assertEqual(report["maximum_point_error"], 0.)
            self.assertEqual(report["tested_segments"], 0)

    def test_numeric_failure_in_matching_segment_survives_same_contour_recovery(self):
        original, perturbed = self.projection_boundary_pair()
        lhs = [[original, quad((1e-6, 0.), (2., 3.), (4., 0.))]]
        rhs = [[perturbed, quad((1e-6, 0.), (2., 3.125), (4., 0.))]]
        report = compare_preserved_quadratics(lhs, rhs)
        self.assertEqual(report["legacy"]["reason"], "segment_types_differ")
        self.assertEqual(report["status"], "outside_budget")
        self.assertEqual(report["maximum_point_error"], .125)
        self.assertEqual(report["restored_segment_count"], 1)

    def test_recovery_report_contains_no_raw_geometry(self):
        lhs = [[quad((123456.789, 234567.891), (123457.789, 234567.891), (123458.789, 234567.891))]]
        rhs = [[quad((123456.789, 234567.891), (123457.789, 234567.901), (123458.789, 234567.891))]]
        report = compare_preserved_quadratics(lhs, rhs)
        self.assertEqual(report["restored_segment_count"], 1)
        encoded = json.dumps(report, allow_nan=False)
        for private in ("123456.789", "234567.891", '"points"', '"commands"', '"events"'):
            self.assertNotIn(private, encoded)


if __name__ == "__main__":
    unittest.main()
