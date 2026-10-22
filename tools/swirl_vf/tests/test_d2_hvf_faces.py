import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import d2_hvf_faces as probe


class FaceSamplingTests(unittest.TestCase):
    def test_bounded_locations_cover_corners_five_weights_and_decimals(self):
        points = probe.design_locations()
        self.assertEqual(len(points), len(set(points)), 15)
        self.assertTrue(all(-1 <= x <= 1 for p in points for x in p))
        self.assertEqual({p[1] for p in points if p[0] == p[2] == 0}, {-1, -.5, 0, .5, 1})
        self.assertEqual(sum(all(abs(x) == 1 for x in p) for p in points), 8)
        self.assertTrue(any(any(0 < abs(x) < 1 and x not in (-.5, .5) for x in p) for p in points))

    def row(self):
        return {'face_index': 31, 'recipe_sha256': 'bound', 'status': 'COMPLETED_FINITE_DESIGN_COMPARISON',
                'completed': 510, 'legacy_passed': 508, 'legacy_failed': 2, 'companion_calls': 2,
                'companion_passed': 1, 'combined_passed': 509, 'combined_failed': 1}

    def test_checkpoint_preserves_a_real_failure_and_old_rejections(self):
        row = self.row()
        self.assertIs(probe.validate_face(row, 31, 510, 'bound'), row)
        self.assertEqual(row['combined_failed'], 1)
        self.assertEqual(row['legacy_failed'], 2)

    def test_checkpoint_cannot_hide_failures_or_substitute_face_recipe(self):
        for change in ({'combined_failed': 0}, {'companion_calls': 1}, {'legacy_passed': 510},
                       {'completed': 509}, {'face_index': 0}, {'recipe_sha256': 'other'},
                       {'legacy_passed': True}, {'status': 'RUNNING'}):
            row = {**self.row(), **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                probe.validate_face(row, 31, 510, 'bound')

    def test_recipe_survives_a_real_json_roundtrip_for_resumption(self):
        p = Path(probe.__file__)
        recipe = probe.recipe_identity('source', p, [0, 1], {'covered': 2},
                                       [{'face_index': 0, 'hvgl_sha256': 'table'}])
        self.assertEqual(json.loads(json.dumps(recipe)), recipe)
        self.assertEqual(recipe['limit'], 1/32)

    def test_true_numeric_failure_is_not_rescued_by_companion(self):
        import numpy as np
        portable = [np.array([[0.,0.],[50.,0.],[100.,0.],[100.,50.],[100.,100.],[0.,100.]])]
        events = [['begin_path'],['move',1.,0.],['quad',51.,0.,101.,0.],
                  ['quad',101.,50.,101.,100.],['quad',1.,100.,1.,0.],['close'],['end_path']]
        result = probe.compare(portable, events)
        self.assertFalse(result['legacy_passed'])
        self.assertTrue(result['companion_called'])
        self.assertFalse(result['combined_passed'])


if __name__ == '__main__':
    unittest.main()
