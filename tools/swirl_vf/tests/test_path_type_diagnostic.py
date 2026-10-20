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
from diagnose_path_types import (RawSegment, canonical_paths, diagnose_paths,
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


if __name__ == "__main__":
    unittest.main()
