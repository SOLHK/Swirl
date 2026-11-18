"""Exact bounds on ALL observed curve points, with strict failures preserved."""
from fractions import Fraction
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from bezier_path_certificate import certify_qt_paths,qt_contours,point_separation


def rectangle():
    return [[0,0.,0.],[1,3.,0.],[1,3.,3.],[1,0.,3.],[1,0.,0.]]


class BezierPathCertificateTests(unittest.TestCase):
    def test_identical_paths_and_exact_line_degree_elevation(self):
        line=[[0,0.,0.],[1,3.,0.],[1,0.,0.]]
        cubic=[[0,0.,0.],[2,1.,0.],[3,2.,0.],[3,3.,0.],
               [2,2.,0.],[3,1.,0.],[3,0.,0.]]
        result=certify_qt_paths(line,cubic)
        self.assertEqual(result['status'],'BOUND_WITHIN_LIMIT')
        self.assertEqual(result['max_curve_distance_bound'],0.)
        self.assertEqual(result['contours'][0]['paired'],2)
        self.assertFalse(result['strict_path_gate_overridden'])

    def test_short_curve_is_fully_bounded_by_a_pause_not_removed(self):
        reference=rectangle()
        with_curve=[reference[0],[2,0.,.01],[3,0.,-.01],[3,0.,0.],*reference[1:]]
        result=certify_qt_paths(with_curve,reference)
        self.assertEqual(result['status'],'BOUND_WITHIN_LIMIT')
        self.assertGreaterEqual(result['max_curve_distance_bound'],.01)
        self.assertEqual(result['contours'][0]['left_segments'],5)
        self.assertEqual(result['contours'][0]['left_only'],1)
        self.assertEqual(len(qt_contours(with_curve)[0][1]),5)
        reversed_result=certify_qt_paths(reference,with_curve)
        self.assertEqual(reversed_result['contours'][0]['right_only'],1)

    def test_interior_curve_excursion_cannot_hide_behind_equal_endpoints(self):
        reference=rectangle()
        excursion=[reference[0],[2,0.,.2],[3,0.,.2],[3,0.,0.],*reference[1:]]
        result=certify_qt_paths(excursion,reference)
        self.assertEqual(result['status'],'NO_CERTIFICATE')
        self.assertFalse(result['production_accepted'])

    def test_implicit_closing_edge_is_included_in_bound(self):
        reference=rectangle()
        changed=[*reference[:-1],[1,.001,0.],[1,0.,0.]]
        result=certify_qt_paths(changed,reference)
        self.assertEqual(result['status'],'BOUND_WITHIN_LIMIT')
        self.assertEqual(result['contours'][0]['left_only'],1)
        self.assertGreaterEqual(result['max_curve_distance_bound'],.001)

    def test_euclidean_boundary_is_exact_and_outward_reported(self):
        original=rectangle()
        moved=[[k,x+1/32,y] for k,x,y in original]
        result=certify_qt_paths(original,moved)
        self.assertEqual(result['status'],'BOUND_WITHIN_LIMIT')
        self.assertEqual(Fraction(result['squared_bound_numerator'])/
                         Fraction(result['squared_bound_denominator']),Fraction(1,32)**2)
        farther=[[k,x+1/32,y+1/65536] for k,x,y in original]
        self.assertEqual(certify_qt_paths(original,farther)['status'],'NO_CERTIFICATE')
        diagonal=[[k,x+.01,y+.01] for k,x,y in original]
        d=certify_qt_paths(original,diagonal)
        self.assertEqual(d['status'],'BOUND_WITHIN_LIMIT')
        q=Fraction(d['squared_bound_numerator'])/Fraction(d['squared_bound_denominator'])
        self.assertGreaterEqual(Fraction(d['max_curve_distance_bound'])**2,q)

    def test_contours_orientation_and_parse_errors_are_not_normalized_away(self):
        original=rectangle()
        self.assertEqual(certify_qt_paths(original,original+original)['reason'],'contour_count_differs')
        backwards=[original[0],original[-2],original[-3],original[-4],original[-1]]
        self.assertEqual(certify_qt_paths(original,backwards)['status'],'NO_CERTIFICATE')
        for bad in ([[1,0.,0.]],[[0,0.,0.],[2,0.,0.]],original[:-1],
                    [[0,math.nan,0.]],[[0,0.,0.],[3,0.,0.]]):
            with self.assertRaises(ValueError):qt_contours(bad)

    def test_resource_limit_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'state_budget'):
            certify_qt_paths(rectangle(),rectangle(),max_states=1)
        for limit in (-1.,math.nan,True):
            with self.assertRaises(ValueError):certify_qt_paths([],[],limit=limit)

    def test_separation_bound_includes_all_curves_and_rounds_down(self):
        far=[(0.,1.),(1.,1.),(2.,1.),(3.,1.)]
        near=[(0.,.01),(1.,.01),(2.,.01),(3.,.01)]
        result=point_separation((1.,0.),[far])
        self.assertEqual(result['status'],'SEPARATED_BEYOND_LIMIT')
        q=Fraction(result['squared_lower_numerator'])/Fraction(result['squared_lower_denominator'])
        self.assertLessEqual(Fraction(result['distance_lower_bound'])**2,q)
        self.assertEqual(point_separation((0.,0.),[far,near])['status'],'NOT_SEPARATED')

    def test_separation_does_not_use_only_cubic_endpoints(self):
        # Endpoints are far; the actual cubic midpoint is exactly the query.
        curve=[(-1.,1.),(-1.,-1.),(1.,-1.),(1.,1.)]
        self.assertEqual(point_separation((0.,-.5),[curve])['status'],'NOT_SEPARATED')
        result=point_separation((0.,0.),[curve])
        self.assertEqual(result['status'],'SEPARATED_BEYOND_LIMIT')
        self.assertGreater(result['subdivisions'],0)
        self.assertEqual(point_separation((0.,0.),[curve],max_states=1)['status'],
                         'NO_SEPARATION_CERTIFICATE')


if __name__=='__main__':unittest.main()
