"""Exact-zero storage must preserve tiny terms, receipts and bounded sampling."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from adaptive_projection_atlas import ProjectionAtlas,fit,validate
from sparse_polynomial_fields import SparseFieldBox
from joint_polynomial import PolynomialBox
from test_adaptive_projection_atlas import PolynomialSource


class SparseFieldTests(unittest.TestCase):
    def test_zero_only_compaction_and_both_archive_versions_are_exact(self):
        c=np.zeros((4,4,4,200));c[0,0,0,7]=3.;c[2,1,3,91]=1e-200
        model=PolynomialBox(np.array([[-1.,0.]]*3),(('rmoveto',200),),c,{})
        sparse=SparseFieldBox.from_model(model)
        self.assertEqual(sparse.columns.tolist(),[7,91])
        np.testing.assert_array_equal(sparse.coefficients,c)
        points=np.random.default_rng(7721).uniform(-1,0,(129,3))
        np.testing.assert_array_equal(sparse.values(points),model.values(points))
        identity=dict(source_sha256='authored',face_index=0,glyph_id=0)
        atlas=ProjectionAtlas([sparse],{},np.zeros(0,dtype='V16'))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'atlas.npz';atlas.save(path,identity)
            for version in (2,1):
                if version==1:
                    np.savez_compressed(path,bounds=[model.bounds],coefficients=[c],
                        metadata=json.dumps(dict(schema=1,identity=identity,evidence={},operators=model.operators)),
                        fitting_fingerprints=atlas.fitting_fingerprints)
                loaded=ProjectionAtlas.load(path,identity)
                np.testing.assert_array_equal(loaded.boxes[0].coefficients,c)
                np.testing.assert_array_equal(loaded.values(points),atlas.values(points))
            np.savez_compressed(path,bounds=[model.bounds],coefficients=[c,c],
                metadata=json.dumps(dict(schema=1,identity=identity,evidence={},operators=model.operators)),
                fitting_fingerprints=atlas.fitting_fingerprints)
            with self.assertRaisesRegex(ValueError,'storage'):ProjectionAtlas.load(path,identity)

    def test_independent_validation_streams_every_position(self):
        class Bounded(PolynomialSource):
            seen=[]
            def components(self,p):
                if len(p)>64:raise AssertionError('unbounded sample allocation')
                self.seen.extend(map(tuple,p));return super().components(p)
        source=Bounded();atlas=fit(source,max_boxes=8,use_source_branches=False)
        points=np.random.default_rng(7719).uniform(-1,1,(1031,3))
        proof=validate(atlas,source,points)
        self.assertEqual(proof['holdout_count'],len(points))
        np.testing.assert_array_equal(source.seen,points)
        self.assertLess(proof['max_envelope_error'],1e-12)


if __name__=='__main__':unittest.main()
