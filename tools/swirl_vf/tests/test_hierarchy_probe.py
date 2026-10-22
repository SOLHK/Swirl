"""Original analytic tests for the native hierarchy diagnosis, not Apple evidence."""
import math
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from probe_hierarchy_rules import (LIMIT, HVGL, ExperimentalRenderer, cases,
                                   composite_record, hvgl_table, native_quadratics,
                                   point_error, shape_record)
from probe_tangent_rules import cases as tangent_cases, encode_shape


def analytic_leaf(axis, factor=0.25):
    slope = max(axis, 0.0)
    negative = max(-axis, 0.0)
    a = np.array([150 + 40*slope - 20*negative, 20.0])
    b = np.array([-60.0, 140 + 30*slope - 10*negative])
    return np.array([(1-factor)*b + factor*a, a,
                     [300 + 80*slope - 40*negative, 80], [210, 220],
                     [20, 300], b])


def rigid(points, angle, shift):
    angle = float(np.float32(angle))
    c, s = math.cos(angle), math.sin(angle)
    return points @ np.array([[c, -s], [s, c]]).T + np.asarray(shift, dtype=np.float32)


def events_for(points, shift=0):
    pairs = np.roll(points.reshape(-1, 2, 2), shift, axis=0)
    result = [['begin_path'], ['move', *pairs[0, 0]]]
    for i, pair in enumerate(pairs):
        result.append(['quad', *pair[1], *pairs[(i+1) % len(pairs), 0]])
    return result + [['close'], ['end_path']]


class HierarchyProbeTests(unittest.TestCase):
    def test_all28_encoded_hierarchies_have_correct_structure(self):
        fixtures = list(cases())
        self.assertEqual(len(fixtures), 28)
        self.assertEqual(len({name for name, _, _ in fixtures}), 28)
        for name, parts, coordinate in fixtures:
            with self.subTest(name=name):
                parsed = HVGL(hvgl_table(parts))
                self.assertEqual(parsed.validate()['binary_and_structure_validation'], 'PASS')
                self.assertEqual(parsed.glyph_count, 1)
                self.assertEqual(parsed.part_count, len(parts))
                self.assertEqual(parsed.part(0).tree_parts, len(parts))
                self.assertEqual(len(ExperimentalRenderer(parsed).render(0, coordinate)), 1)

    def test_unequal_parallel_factors_match_independent_formula(self):
        for factor in (0.25, 0.75):
            parsed = HVGL(hvgl_table([shape_record(parallel=factor)]))
            for axis in (-1.0, 0.0, 0.375, 1.0):
                actual = ExperimentalRenderer(parsed).render(0, [axis])[0]
                np.testing.assert_allclose(actual, analytic_leaf(axis, factor), rtol=0, atol=1e-12)

    def test_single_rotation_and_translation_match_independent_formula(self):
        for angle in (0.0, math.pi/2, -math.pi/2, 0.371):
            parsed = HVGL(hvgl_table([composite_record(1, 1, 1, rotation=angle), shape_record()]))
            for axis in (-1.0, 0.0, 0.375, 1.0):
                expected = rigid(analytic_leaf(0.125 + axis*0.5), angle, [30, 40])
                actual = ExperimentalRenderer(parsed).render(0, [axis])[0]
                np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-10)

    def test_nested_rotation_and_deep_translation_do_not_commute(self):
        parsed = HVGL(hvgl_table([
            composite_record(1, 2, 2, rotation=0.371, deep_translation=(13, -7)),
            composite_record(2, 1, 1, rotation=-0.23, translation=(-25, 17)), shape_record()]))
        child_axis = 0.125 + 0.5*0.375
        leaf_axis = 0.125 + 0.5*child_axis
        leaf = analytic_leaf(leaf_axis)
        # Independent native artifact 12205148657 proves the deeper local
        # rotation also rotates an inherited descendant translation. Only the
        # newly contributed (-25,17) translation is applied after that rotation.
        expected = rigid(rigid(leaf + [13, -7], -0.23, [-25, 17]), 0.371, [30, 40])
        actual = ExperimentalRenderer(parsed).render(0, [0.375])[0]
        np.testing.assert_allclose(actual, expected, rtol=0, atol=1e-10)
        wrong = rigid(rigid(leaf, -0.23, [-12, 10]), 0.371, [30, 40])
        self.assertGreater(np.max(np.abs(wrong-actual)), LIMIT)

    def test_internal_axis_cases_expose_current_extrapolation_hypothesis(self):
        # This assertion tests the existing portable model; native agreement is
        # deliberately not presumed and will be a separate recorded result.
        for master in (-1.25, 1.25):
            parsed = HVGL(hvgl_table([composite_record(1,1,1,master=master), shape_record()]))
            actual = ExperimentalRenderer(parsed).render(0, [0])[0]
            np.testing.assert_allclose(actual, analytic_leaf(master) + [30,40], rtol=0, atol=1e-10)

    def test_native_event_comparator_accepts_exact_cycles_only(self):
        points = analytic_leaf(0.375)
        for shift in range(3):
            native = native_quadratics(events_for(points, shift))
            self.assertLessEqual(point_error([points], native), 1e-12)
            native[1][1][0] += 0.1
            self.assertGreater(point_error([points], native), LIMIT)

    def test_native_event_comparator_rejects_malformed_or_cubic_data(self):
        for events in ([], [['quad',1,2,3,4]], [['cubic',0,0,1,1,2,2]]):
            with self.assertRaises(ValueError):
                native_quadratics(events)
        with self.assertRaises(ValueError):
            point_error([analytic_leaf(0)], native_quadratics(events_for(analytic_leaf(0)))[:-1])

    def test_tangent_experiments_decode_all22_and_do_not_enter_renderer(self):
        fixtures = tangent_cases()
        self.assertEqual(len(fixtures), 22)
        for name, types, data in fixtures:
            with self.subTest(name=name):
                parsed = HVGL(encode_shape(types, data))
                self.assertEqual(parsed.validate()['binary_and_structure_validation'], 'PASS')
                self.assertEqual(parsed.part(0).blends, tuple(types))
                np.testing.assert_array_equal(parsed.part(0).master, data)


if __name__ == '__main__':
    unittest.main()
