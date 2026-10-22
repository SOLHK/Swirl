"""Exact comparator equivalence on independently authored finite geometry.

The retained scalar reference is the pre-optimization Swirl comparator. These
tests intentionally preserve its segment-count/type and cyclic-order semantics;
they do not remove degenerate segments or approximate a curve differently.
"""
from pathlib import Path
import random
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from calibrate_hvf_geometry import discrepancy


def scalar_reference(wanted, actual):
    """Unchanged scalar algorithm retained for a direct before/after check."""
    if len(wanted) != len(actual):
        raise ValueError('path_count_differs')
    max_error = 0.
    tested = 0
    for left, right in zip(wanted, actual):
        if len(left) != len(right):
            raise ValueError('segment_count_differs')
        if not left:
            continue
        candidates = []
        for shift in range(len(left)):
            errors = []
            for i, (kind, values) in enumerate(left):
                other, points = right[(i + shift) % len(right)]
                if kind != other:
                    break
                errors.append(float(np.abs(values - points).max()))
            else:
                candidates.append(max(errors, default=0.))
        if not candidates:
            raise ValueError('segment_types_differ')
        max_error = max(max_error, min(candidates))
        tested += len(left)
    return max_error, tested


def contour(rng, count, kinds=None):
    result = []
    for i in range(count):
        kind = kinds[i] if kinds else rng.choice(('L', 'Q'))
        values = np.asarray([rng.uniform(-1700, 1700) for _ in range(4 if kind == 'L' else 6)])
        result.append((kind, values))
    return result


class GeometryComparisonTests(unittest.TestCase):
    def equal_result(self, wanted, actual):
        try:
            expected = scalar_reference(wanted, actual)
        except ValueError as error:
            with self.assertRaisesRegex(ValueError, '^' + str(error) + '$'):
                discrepancy(wanted, actual)
        else:
            self.assertEqual(discrepancy(wanted, actual), expected)

    def test_all_cyclic_shifts_for_line_quad_and_mixed_contours(self):
        rng = random.Random(882120)
        for kinds in (['L'] * 19, ['Q'] * 23, ['L', 'Q', 'Q', 'L'] * 7):
            original = contour(rng, len(kinds), kinds)
            for shift in range(len(original)):
                actual = original[shift:] + original[:shift]
                self.assertEqual(discrepancy([original], [actual]), (0., len(original)))
                self.equal_result([original], [actual])

    def test_random_multiple_contours_and_unseen_perturbations_are_bit_equal(self):
        rng = random.Random(720610)
        for case in range(120):
            wanted, actual = [], []
            for _ in range(rng.randint(1, 4)):
                path = contour(rng, rng.randint(1, 24))
                perturbed = [(kind, points + np.asarray([rng.uniform(-.2, .2) for _ in points]))
                             for kind, points in path]
                shift = rng.randrange(len(path))
                wanted.append(path)
                actual.append(perturbed[shift:] + perturbed[:shift])
            with self.subTest(case=case):
                self.equal_result(wanted, actual)

    def test_lower_bound_ties_cannot_skip_the_correct_shift(self):
        # Every segment starts at the same point, but quadratic controls differ.
        # The first segment's full six-value bound still has repeated ties.
        path = [('Q', np.asarray([0., 0., i % 3, i // 3, 0., 0.])) for i in range(36)]
        actual = [(kind, values.copy()) for kind, values in path[17:] + path[:17]]
        actual[9][1][3] += .02734375
        self.equal_result([path], [actual])

    def test_small_error_and_exact_budget_boundaries_are_not_rounded(self):
        base = [('Q', np.asarray([0., 0., 32., 48., 64., 0.]))]
        for delta in (0., 1e-12, 1 / 32, np.nextafter(1 / 32, float('inf')), 1.75):
            altered = [('Q', base[0][1].copy())]
            altered[0][1][0] = delta
            self.equal_result([base], [altered])
            self.assertEqual(discrepancy([base], [altered])[0], delta)

    def test_path_segment_and_noncyclic_type_mismatches_keep_original_errors(self):
        rng = random.Random(87)
        line = contour(rng, 1, ['L'])
        for wanted, actual in (([], [line]), ([line], [[]]),
                               ([contour(rng, 4, ['L', 'L', 'Q', 'Q'])],
                                [contour(rng, 4, ['L', 'Q', 'L', 'Q'])]),
                               ([line], [contour(rng, 1, ['Q'])]),
                               ([contour(rng, 19, ['L'] * 19)],
                                [contour(rng, 19, ['Q'] * 19)]),
                               ([contour(rng, 20, ['L'] * 10 + ['Q'] * 10)],
                                [contour(rng, 20, ['L', 'Q'] * 10)])):
            self.equal_result(wanted, actual)

    def test_empty_contours_zero_length_segments_and_reverse_order_are_preserved(self):
        rng = random.Random(853)
        original = contour(rng, 13, ['Q'] * 13)
        self.equal_result([original], [list(reversed(original))])
        self.equal_result([], [])
        self.equal_result([[], []], [[], []])
        degenerate = [('L', np.zeros(4)), ('Q', np.zeros(6)), ('L', np.zeros(4))]
        self.equal_result([degenerate], [degenerate[1:] + degenerate[:1]])

    def test_noncanonical_numeric_inputs_retain_scalar_behavior(self):
        for dtype in (np.float32, np.int64):
            for count in (1, 19):
                original = [('L', np.asarray([10 + i, 20, 30, 40], dtype=dtype)) for i in range(count)]
                actual = [('L', np.asarray([11 + i, 21, 31, 41], dtype=dtype)) for i in range(count)]
                self.equal_result([original], [actual[7:] + actual[:7]])
        for count in (1, 21):
            self.equal_result([[('legacy', np.asarray([1. + i, 2., 3.])) for i in range(count)]],
                              [[('legacy', np.asarray([2. + i, 3., 4.])) for i in range(count)]])


if __name__ == '__main__':
    unittest.main()
