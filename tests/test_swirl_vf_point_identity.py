import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.swirl_vf_point_identity import (
    AmbiguousPointIdentityError, InvalidOutlineError, Outline, OutlinePoint,
    UnmatchedContourError, match_point_identity,
)


def ring(*xy):
    return tuple(OutlinePoint(x, y, on) for x, y, on in xy)


class PointIdentityTests(unittest.TestCase):
    def test_empty_outline_matches_empty_outline(self):
        self.assertEqual(match_point_identity(Outline((), ()), Outline((), ())), ())

    def test_cyclic_start_change_maps_indices(self):
        src = Outline.from_contours([ring((0, 0, True), (4, 0, False), (8, 0, True))])
        dst = Outline.from_contours([ring((8, 0, True), (0, 0, True), (4, 0, False))])
        self.assertEqual(match_point_identity(src, dst), (2, 0, 1))

    def test_reversed_winding_maps_indices(self):
        src = Outline.from_contours([ring((0, 0, True), (4, 0, False), (8, 0, True))])
        dst = Outline.from_contours([ring((8, 0, True), (4, 0, False), (0, 0, True))])
        self.assertEqual(match_point_identity(src, dst), (2, 1, 0))

    def test_contour_permutation_maps_global_indices(self):
        a = ring((0, 0, True), (1, 0, True))
        b = ring((10, 0, True), (11, 0, True), (12, 0, True))
        src, dst = Outline.from_contours([a, b]), Outline.from_contours([b, a])
        self.assertEqual(match_point_identity(src, dst), (2, 3, 4, 0, 1))

    def test_on_curve_identity_is_part_of_signature(self):
        src = Outline.from_contours([ring((0, 0, True), (5, 3, False), (8, 0, True))])
        dst = Outline.from_contours([ring((0, 0, True), (5, 3, True), (8, 0, True))])
        with self.assertRaises(UnmatchedContourError):
            match_point_identity(src, dst)

    def test_different_point_count_is_rejected(self):
        src = Outline.from_contours([ring((0, 0, True), (1, 0, True))])
        dst = Outline.from_contours([ring((0, 0, True), (1, 0, True), (2, 0, True))])
        with self.assertRaises(UnmatchedContourError):
            match_point_identity(src, dst)

    def test_duplicate_identical_contours_are_ambiguous(self):
        c = ring((0, 0, True), (2, 0, True), (1, 1, True))
        with self.assertRaises(AmbiguousPointIdentityError):
            match_point_identity(Outline.from_contours([c, c]), Outline.from_contours([c, c]))

    def test_repeated_symmetric_points_are_ambiguous(self):
        c = ring((0, 0, True), (1, 0, True), (0, 0, True), (-1, 0, True))
        with self.assertRaises(AmbiguousPointIdentityError):
            match_point_identity(Outline.from_contours([c]), Outline.from_contours([c]))

    def test_bad_endpoints_are_rejected(self):
        with self.assertRaises(InvalidOutlineError):
            Outline((OutlinePoint(0, 0, True),), (1,))

    def test_empty_contour_is_not_silently_accepted(self):
        with self.assertRaises(InvalidOutlineError):
            Outline.from_contours([()])


if __name__ == "__main__":
    unittest.main()
