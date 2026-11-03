"""Source-derived cuts and strict separation of fit/refinement/holdout data."""
from pathlib import Path
import sys
import unittest
import tempfile

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from adaptive_projection_atlas import fit, validate, branch_split, branch_probes, RecordedSource, ProjectionAtlas
from projection_factorization import ProjectionSource
from test_hvf_branch_cells import authored_table


class PolynomialSource:
    ops = base_ops = (('rmoveto', 2), ('rlineto', 2))
    closed_control_pairs = ()
    factors, width = 0, 4
    def __call__(self, points):
        x, y, z = np.asarray(points).T
        return np.asarray([10+x*x*y, 20+y*z*z*z, 30+x*y*z, 40+x*x*y*y*z*z]).T
    def components(self, points):
        return self(points)[:, None], np.empty((len(points), 0))
    def errors(self, a, b):
        return np.linalg.norm(np.cumsum((a-b).reshape(len(a), -1, 2), axis=1), axis=2).max(axis=1)


class AdaptiveProjectionTests(unittest.TestCase):
    def test_every_octant_and_independent_positions_preserve_the_cubic_field(self):
        source = PolynomialSource()
        atlas = fit(source, max_boxes=8, use_source_branches=False)
        self.assertEqual(len(atlas.boxes), 8)
        self.assertTrue(atlas.evidence['refinement_budget_met'])
        p = np.random.default_rng(811).uniform(-1, 1, (1024, 3))
        result = validate(atlas, source, p)
        self.assertEqual(result['physical_failures'], 0)
        self.assertLess(result['max_physical_error'], 1e-12)
        self.assertTrue(result['holdouts_disjoint'])
        self.assertFalse(result['production_accepted'])

    def test_refinement_samples_cannot_be_relabelled_as_independent_holdouts(self):
        source = PolynomialSource()
        atlas = fit(source, max_boxes=8, use_source_branches=False)
        for point in ([0., 0., 0.], [-0., 0., 0.], [.125, .5, .875]):
            with self.assertRaisesRegex(ValueError, 'overlap_training_or_refinement'):
                validate(atlas, source, [point])
        with self.assertRaisesRegex(ValueError, 'overlap_training_or_refinement'):
            validate(atlas, source, [[.12345, .23456, .34567]]*2)

    def test_source_kink_selects_a_quantized_branch_cut(self):
        source = ProjectionSource(authored_table(), 0)
        recorder = RecordedSource(source)
        recorder(np.zeros((1, 3)))
        bounds = np.array([[0., 1.]]*3)
        anchor = np.array([.5, .5, .5])
        axis, cut, from_source = branch_split(source, recorder, bounds, anchor, 0, 1/128)
        self.assertTrue(from_source)
        self.assertEqual(cut*16384, round(cut*16384))
        anchor[axis] = cut
        self.assertLess(abs(-.25+anchor @ [.5, .75, -.25]), 1/16384)
        points = branch_probes(source, bounds)
        self.assertGreater(len(points), 0)
        self.assertTrue(np.all((points >= 0) & (points <= 1)))

    def test_invalid_budgets_fail_before_fitting(self):
        for budget in (0, -1, 1/16):
            with self.assertRaisesRegex(ValueError, 'atlas_budget'):
                fit(PolynomialSource(), budget=budget)
        for cap in (1, 65533, 8.):
            with self.assertRaisesRegex(ValueError, 'atlas_budget'):
                fit(PolynomialSource(), max_boxes=cap)

    def test_resume_reassesses_cells_without_losing_previous_training_receipts(self):
        source=PolynomialSource();first=fit(source,max_boxes=8,use_source_branches=False)
        first.fitting_fingerprints=np.r_[first.fitting_fingerprints,np.asarray([b'previous-receipt!'],dtype='V16')]
        # Validation evidence is deliberately poisonous: it must not steer fit.
        first.evidence['component_holdout']={'max_envelope_error':12345.}
        resumed=fit(source,max_boxes=16,use_source_branches=False,initial_atlas=first)
        self.assertEqual(resumed.evidence['resumed_boxes'],8)
        self.assertEqual(len(resumed.boxes),8)
        self.assertFalse(np.setdiff1d(first.fitting_fingerprints,resumed.fitting_fingerprints).size)
        self.assertNotIn('component_holdout',resumed.evidence)
        np.testing.assert_array_equal(first.values([[.39,-.23,.71]]),resumed.values([[.39,-.23,.71]]))

    def test_private_roundtrip_retains_training_receipts_and_binds_source_identity(self):
        atlas = fit(PolynomialSource(), max_boxes=8, use_source_branches=False)
        identity = dict(source_sha256='authored', face_index=0, glyph_id=0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'atlas.npz'
            atlas.save(path, identity)
            loaded = ProjectionAtlas.load(path, identity)
            np.testing.assert_array_equal(loaded.fitting_fingerprints, atlas.fitting_fingerprints)
            np.testing.assert_array_equal(loaded.values([[.37, -.21, .58]]), atlas.values([[.37, -.21, .58]]))
            with self.assertRaisesRegex(ValueError, 'source_identity_mismatch'):
                ProjectionAtlas.load(path, dict(identity, glyph_id=1))
            with self.assertRaisesRegex(ValueError, 'overlap_training_or_refinement'):
                validate(loaded, PolynomialSource(), [[.125, .5, .875]])


if __name__ == '__main__':
    unittest.main()
