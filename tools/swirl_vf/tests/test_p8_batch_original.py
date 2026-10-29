"""Authored batch identity and honest progress accounting guards."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
from p8_batch_original import checked_gids, summarize, run, EXPECTED


class OriginalBatchTests(unittest.TestCase):
    def test_source_face_and_unique_real_GIDs_required(self):
        plan = dict(source_sha256=EXPECTED, source_face_index=0, gids=[0, 2, 12])
        self.assertEqual(checked_gids(plan), [0, 2, 12])
        for changes in (dict(source_sha256='0'*64), dict(source_face_index=1),
                        dict(gids=[0, 0]), dict(gids=[True]), dict(gids=[47102]), dict(gids=[])):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                checked_gids(dict(plan, **changes))

    def test_failed_and_constant_models_never_count_as_nonzero_variation_or_native_acceptance(self):
        constant = dict(status='ENCODED_EXPERIMENTAL', outline_varies=False, metric_varies=False,
                        tuple_count=0, strict_outline_pass=True, strict_table_metric_pass=True,
                        source_native_geometry_pass=True)
        failed_quality = dict(constant, outline_varies=True, tuple_count=3, strict_outline_pass=False)
        result = summarize({'0': constant, '1': failed_quality,
                            '2': dict(status='FAILED', failure_category='UnsupportedRendering')}, 5)
        self.assertEqual(result['encoded_GIDs'], 2)
        self.assertEqual(result['nonzero_outline_variation_GIDs'], 1)
        self.assertEqual(result['strict_sampled_model_outline_pass_GIDs'], 1)
        self.assertEqual(result['failed_GIDs'], 1)
        self.assertEqual(result['pending_GIDs'], 2)
        self.assertEqual(result['native_equivalence_accepted_GIDs'], 0)
        self.assertFalse(result['production_accepted'])

    def test_wrong_original_rejected_before_plan_read_or_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, binary, plan = (root/name for name in ('source', 'oracle', 'plan'))
            for path in (source, binary, plan): path.write_bytes(b'authored control')
            output = root/'not-created'
            with patch('p8_batch_original.sample') as native:
                with self.assertRaisesRegex(ValueError, 'exact_original_source_required'):
                    run(source, binary, plan, output)
            native.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
