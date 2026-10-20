"""Private whole-face resume and exact failure context using original fixtures.

No Apple data or native platform is used. The production reconstruction,
serialization and TTC checks run, with only the oracle replaced analytically.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import rebuild
from test_rebuild import write_fixture
from test_rebuild_pipeline import OriginalAnalyticOracle


class LaterFaceFailure(OriginalAnalyticOracle):
    def samples(self, face, glyph_ids, location):
        if face == 1:
            raise rebuild.ReconstructionError("original-test-interruption")
        return super().samples(face, glyph_ids, location)


class RebuildCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="original-checkpoint-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "original-three-face.ttc"
        write_fixture(self.source, faces=3)
        self.output = self.root / "Swirl-VF.ttc"
        self.checkpoints = self.root / "private-checkpoints"
        self.executable = self.root / "original-oracle-double"

    def invoke(self, attempt, oracle, **kwargs):
        report = self.root / f"attempt-{attempt}" / "report.json"
        with mock.patch.object(rebuild, "NativeOracle", return_value=oracle):
            result = rebuild.run(self.source, self.executable, self.output, report,
                                 batch_size=2, checkpoint_dir=self.checkpoints, **kwargs)
        return result

    def interrupted(self):
        oracle = LaterFaceFailure(self.source)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "original-test-interruption"):
            self.invoke(1, oracle)
        self.assertFalse(self.output.exists())
        self.assertEqual(oracle.close_count, 1)
        return json.loads((self.root / "attempt-1" / "report.json").read_text())

    def test_verified_face_survives_and_resume_rechecks_complete_ttc(self):
        before = self.source.read_bytes()
        partial = self.interrupted()
        self.assertEqual(partial["faces"][0]["glyphs_completed"], 3)
        self.assertEqual(partial["faces"][1]["glyphs_completed"], 0)
        manifest = json.loads((self.checkpoints / "verified-faces.json").read_text())
        self.assertEqual(set(manifest["faces"]), {"0"})
        self.assertEqual(len(list(self.checkpoints.glob("*.ttf"))), 1)
        oracle = OriginalAnalyticOracle(self.source)
        with mock.patch.object(rebuild, "verify_collection_tables", wraps=rebuild.verify_collection_tables) as packing:
            result = self.invoke(2, oracle)
        self.assertTrue(self.output.exists())
        self.assertFalse(result["lossless_conversion"])
        self.assertEqual(result["windows_acceptance"], "NOT_RUN")
        self.assertTrue(result["faces"][0]["restored_from_verified_checkpoint"])
        self.assertTrue(all(face != 0 for face, _, _ in oracle.requests))
        self.assertEqual({face for face, _, _ in oracle.requests}, {1, 2})
        self.assertEqual(packing.call_count, 1)
        self.assertEqual(result["collection_verification"]["faces_checked"], 3)
        self.assertEqual(self.source.read_bytes(), before)

    def test_native_batch_failure_records_face_gid_range_and_user_location(self):
        partial = self.interrupted()
        context = partial["failures"][0]["context"]
        self.assertEqual(context["stage"], "native_batch")
        self.assertEqual(context["face_index"], 1)
        self.assertEqual((context["gid_first"], context["gid_last"]), (0, 1))
        self.assertEqual(context["sample_number"], 0)
        self.assertEqual(context["user_location"], {"WDTH": 500, "wght": 500, "HGHT": 500})

    def test_changed_cached_bytes_block_resume_before_any_new_sampling(self):
        self.interrupted()
        face = next(self.checkpoints.glob("*.ttf"))
        face.write_bytes(face.read_bytes() + b"original corruption test")
        oracle = OriginalAnalyticOracle(self.source)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "verified font bytes changed"):
            self.invoke(2, oracle)
        self.assertFalse(self.output.exists())
        self.assertEqual(oracle.requests, [])

    def test_changed_error_budget_cannot_reuse_a_prior_acceptance(self):
        self.interrupted()
        oracle = OriginalAnalyticOracle(self.source)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "checkpoint recipe differs"):
            self.invoke(2, oracle, outline_limit=0.75)
        self.assertEqual(oracle.requests, [])
        self.assertFalse(self.output.exists())

    def test_changed_source_cannot_reuse_a_prior_acceptance(self):
        self.interrupted()
        self.source.write_bytes(self.source.read_bytes() + b"changed source identity")
        oracle = OriginalAnalyticOracle(self.source)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "checkpoint recipe differs"):
            self.invoke(2, oracle)
        self.assertEqual(oracle.requests, [])
        self.assertFalse(self.output.exists())

    def test_unowned_directory_is_not_overwritten(self):
        self.checkpoints.mkdir()
        sentinel = self.checkpoints / "existing-user-file"
        sentinel.write_text("preserve")
        oracle = OriginalAnalyticOracle(self.source)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "no regular manifest"):
            self.invoke(1, oracle)
        self.assertEqual(sentinel.read_text(), "preserve")
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
