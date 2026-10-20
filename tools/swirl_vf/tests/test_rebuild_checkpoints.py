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


class OracleSessions:
    """Every constructor call is a fresh, explicitly synthetic oracle session."""

    def __init__(self, source, oracle_type=OriginalAnalyticOracle, configure=None):
        self.source = source
        self.oracle_type = oracle_type
        self.configure = configure
        self.sessions = []
        self.logs = []

    def __call__(self, executable, source, log):
        if source != self.source:
            raise AssertionError("source changed between original session fixtures")
        oracle = self.oracle_type(source)
        if self.configure is not None:
            self.configure(oracle, len(self.sessions))
        self.sessions.append(oracle)
        self.logs.append(log)
        return oracle

    @property
    def requests(self):
        return [request for oracle in self.sessions for request in oracle.requests]


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
        self.executable.write_text("original analytic oracle protocol identity\n", encoding="utf-8")

    def invoke(self, attempt, oracle, **kwargs):
        report = self.root / f"attempt-{attempt}" / "report.json"
        with mock.patch.object(rebuild, "NativeOracle", side_effect=oracle):
            result = rebuild.run(self.source, self.executable, self.output, report,
                                 batch_size=2, checkpoint_dir=self.checkpoints, **kwargs)
        return result

    def interrupted(self):
        oracle = OracleSessions(self.source, LaterFaceFailure)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "original-test-interruption"):
            self.invoke(1, oracle)
        self.assertFalse(self.output.exists())
        self.assertEqual(len(oracle.sessions), 2)
        self.assertTrue(all(session.close_count == 1 for session in oracle.sessions))
        self.assertEqual([session.finish_count for session in oracle.sessions], [1, 0])
        return json.loads((self.root / "attempt-1" / "report.json").read_text())

    def test_later_diagnostic_session_preserves_verified_face_and_blocks_new_sampling(self):
        before = self.source.read_bytes()
        def configure(oracle, index):
            if index == 1:
                oracle.metadata['diagnostic_readback_observation_only'] = True
        sessions = OracleSessions(self.source, configure=configure)
        with self.assertRaisesRegex(rebuild.ReconstructionError,
                                   'diagnostic-only native observations cannot be used for reconstruction'):
            self.invoke('diagnostic-session', sessions)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.output.exists())
        self.assertEqual(len(sessions.sessions), 2)
        self.assertTrue(all(session.close_count == 1 for session in sessions.sessions))
        self.assertEqual([session.finish_count for session in sessions.sessions], [1, 0])
        self.assertEqual(sessions.sessions[1].requests, [])
        self.assertTrue(all(face == 0 for face, _, _ in sessions.requests))
        manifest = json.loads((self.checkpoints / 'verified-faces.json').read_text())
        self.assertEqual(set(manifest['faces']), {'0'})
        saved = json.loads((self.root / 'attempt-diagnostic-session' / 'report.json').read_text())
        self.assertEqual(saved['status'], 'BLOCKED')
        self.assertFalse(saved['output_generated'])
        self.assertEqual(saved['failures'][0]['context'],
                         {'stage': 'native_session_metadata', 'face_index': 1})
        self.assertEqual(saved['faces'][0]['native_face_transcript']['status'], 'PASS')

    def test_verified_face_survives_and_resume_rechecks_complete_ttc(self):
        before = self.source.read_bytes()
        partial = self.interrupted()
        self.assertEqual(partial["faces"][0]["glyphs_completed"], 3)
        self.assertEqual(partial["faces"][1]["glyphs_completed"], 0)
        manifest = json.loads((self.checkpoints / "verified-faces.json").read_text())
        self.assertEqual(set(manifest["faces"]), {"0"})
        self.assertEqual(manifest["recipe"]["format"], 2)
        proof = manifest["faces"]["0"]["report"]["native_face_transcript"]
        self.assertEqual(proof["status"], "PASS")
        self.assertGreater(proof["request_count"], 0)
        self.assertEqual(proof["source_sha256"], manifest["recipe"]["source_sha256"])
        self.assertEqual(proof["source_face_identity_sha256"], manifest["recipe"]["source_face_identity_sha256"][0])
        self.assertEqual(len(list(self.checkpoints.glob("*.ttf"))), 1)
        oracle = OracleSessions(self.source)
        with mock.patch.object(rebuild, "verify_collection_tables", wraps=rebuild.verify_collection_tables) as packing:
            result = self.invoke(2, oracle)
        self.assertTrue(self.output.exists())
        self.assertFalse(result["lossless_conversion"])
        self.assertEqual(result["windows_acceptance"], "NOT_RUN")
        self.assertTrue(result["faces"][0]["restored_from_verified_checkpoint"])
        self.assertTrue(all(face != 0 for face, _, _ in oracle.requests))
        self.assertEqual({face for face, _, _ in oracle.requests}, {1, 2})
        self.assertEqual(len(oracle.sessions), 2)
        self.assertEqual(len(set(oracle.logs)), 2)
        self.assertEqual([{face for face, _, _ in session.requests} for session in oracle.sessions], [{1}, {2}])
        self.assertTrue(all(session.finish_count == session.close_count == 1 for session in oracle.sessions))
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

    def test_rejected_final_transcript_cannot_be_restored_with_a_zero_request_session(self):
        def reject_after_glyphs(oracle, index):
            original_finish = oracle.finish
            def fail():
                original_finish()
                raise rebuild.ReconstructionError("original-final-transcript-rejected")
            oracle.finish = fail
        first = OracleSessions(self.source, configure=reject_after_glyphs)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "original-final-transcript-rejected"):
            self.invoke(1, first)
        self.assertFalse(self.output.exists())
        partial = json.loads((self.root / "attempt-1" / "report.json").read_text())
        self.assertEqual(partial["faces"][0]["serialized_model_verification"]["status"], "PASS")
        self.assertEqual(partial["failures"][0]["context"],
                         {"stage": "native_face_finalization", "face_index": 0})
        manifest = json.loads((self.checkpoints / "verified-faces.json").read_text())
        self.assertEqual(manifest["faces"], {})
        self.assertFalse(list(self.checkpoints.glob("*.ttf")))
        self.assertEqual(first.sessions[0].close_count, 1)

        def refuse_resampling(oracle, index):
            oracle.samples = mock.Mock(side_effect=rebuild.ReconstructionError("first-face-must-be-resampled"))
        second = OracleSessions(self.source, configure=refuse_resampling)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "first-face-must-be-resampled"):
            self.invoke(2, second)
        self.assertFalse(self.output.exists())
        self.assertEqual(second.sessions[0].samples.call_args.args[0], 0)
        self.assertEqual(second.sessions[0].finish_count, 0)

    def test_every_restored_face_retains_prior_proof_and_new_empty_session_must_finish(self):
        original = OracleSessions(self.source)
        first = self.invoke(1, original)
        self.assertEqual(len(original.sessions), 3)
        self.assertEqual(len(set(original.logs)), 3)
        self.assertEqual([{face for face, _, _ in s.requests} for s in original.sessions], [{0}, {1}, {2}])
        self.assertTrue(all(s.finish_count == s.close_count == 1 for s in original.sessions))
        self.output = self.root / "restored-output" / "Swirl-VF.ttc"
        resumed = OracleSessions(self.source)
        second = self.invoke(2, resumed)
        self.assertTrue(second["output_generated"])
        self.assertEqual(resumed.requests, [])
        self.assertEqual(len(resumed.sessions), 1)
        self.assertEqual(resumed.sessions[0].finish_count, 1)
        self.assertEqual(resumed.sessions[0].close_count, 1)
        self.assertEqual(second["oracle_summary"]["request_count"], 0)
        self.assertEqual(second["oracle_summary"]["restored_face_transcripts"], 3)
        self.assertEqual([face["native_face_transcript"] for face in first["faces"]],
                         [face["native_face_transcript"] for face in second["faces"]])
        self.assertTrue(all(face["native_face_transcript"]["request_count"] > 0 for face in second["faces"]))

        self.output = self.root / "rejected-restore" / "Swirl-VF.ttc"
        def reject_empty_session(oracle, index):
            oracle.finish = mock.Mock(side_effect=rebuild.ReconstructionError("empty-session-transcript-rejected"))
        rejected = OracleSessions(self.source, configure=reject_empty_session)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "empty-session-transcript-rejected"):
            self.invoke(3, rejected)
        self.assertEqual(rejected.requests, [])
        self.assertFalse(self.output.exists())

    def test_new_session_rechecks_original_tables_in_every_physical_face(self):
        def change_later_identity(oracle, index):
            if index == 1:
                oracle.metadata["faces"][2]["verified_table_sha256"]["gvar"] = "0" * 64
        sessions = OracleSessions(self.source, configure=change_later_identity)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "original table identity differs on face 2"):
            self.invoke(1, sessions)
        self.assertFalse(self.output.exists())
        self.assertEqual(len(sessions.sessions), 2)
        self.assertEqual(sessions.sessions[1].requests, [])
        self.assertTrue(all(s.close_count == 1 for s in sessions.sessions))
        manifest = json.loads((self.checkpoints / "verified-faces.json").read_text())
        self.assertEqual(set(manifest["faces"]), {"0"})

    def test_mock_summary_counts_must_obey_the_same_strict_integer_contract(self):
        for index, changes in enumerate(({"request_count": 0}, {"successful_glyph_count": 0},
                                         {"error_count": False}, {"request_count": 1.0})):
            def change_summary(oracle, number, changes=changes):
                original_finish = oracle.finish
                oracle.finish = lambda: {**original_finish(), **changes}
            sessions = OracleSessions(self.source, configure=change_summary)
            with self.subTest(changes=changes), self.assertRaisesRegex(rebuild.ReconstructionError, "session summary disagrees"):
                self.invoke(index + 1, sessions)
            self.assertFalse(self.output.exists())
            manifest = json.loads((self.checkpoints / "verified-faces.json").read_text())
            self.assertEqual(manifest["faces"], {})

    def test_provisional_or_unbound_face_transcripts_cannot_be_restored(self):
        self.interrupted()
        path = self.checkpoints / "verified-faces.json"
        original = json.loads(path.read_text())
        alterations = ("missing", "source_sha256", "source_identity_sha256", "source_face_identity_sha256",
                       "oracle_sha256", "native_summary_eof_exit_accepted", "summary_count", "old_recipe")
        for number, alteration in enumerate(alterations, 2):
            changed = json.loads(json.dumps(original))
            proof = changed["faces"]["0"]["report"]["native_face_transcript"]
            if alteration == "missing":
                del changed["faces"]["0"]["report"]["native_face_transcript"]
            elif alteration == "old_recipe":
                changed["recipe"]["format"] = 1
            elif alteration == "summary_count":
                proof["summary"]["successful_glyph_count"] = 0
            else:
                proof[alteration] = False if alteration == "native_summary_eof_exit_accepted" else "0" * 64
            path.write_text(json.dumps(changed))
            sessions = OracleSessions(self.source)
            with self.subTest(alteration=alteration), self.assertRaises(rebuild.ReconstructionError):
                self.invoke(number, sessions)
            self.assertEqual(sessions.requests, [])
            self.assertFalse(self.output.exists())

    def test_source_change_after_last_glyph_blocks_checkpoint_publication(self):
        def change_source_after_glyphs(oracle, index):
            original_finish = oracle.finish
            def finish():
                summary = original_finish()
                self.source.write_bytes(self.source.read_bytes() + b"original-fixture-mutation")
                return summary
            oracle.finish = finish
        sessions = OracleSessions(self.source, configure=change_source_after_glyphs)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "source changed during native session"):
            self.invoke(1, sessions)
        self.assertFalse(self.output.exists())
        manifest = json.loads((self.checkpoints / "verified-faces.json").read_text())
        self.assertEqual(manifest["faces"], {})

    def test_changed_cached_bytes_block_resume_before_any_new_sampling(self):
        self.interrupted()
        face = next(self.checkpoints.glob("*.ttf"))
        face.write_bytes(face.read_bytes() + b"original corruption test")
        oracle = OracleSessions(self.source)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "verified font bytes changed"):
            self.invoke(2, oracle)
        self.assertFalse(self.output.exists())
        self.assertEqual(oracle.requests, [])

    def test_changed_error_budget_cannot_reuse_a_prior_acceptance(self):
        self.interrupted()
        oracle = OracleSessions(self.source)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "checkpoint recipe differs"):
            self.invoke(2, oracle, outline_limit=0.75)
        self.assertEqual(oracle.requests, [])
        self.assertFalse(self.output.exists())

    def test_changed_source_cannot_reuse_a_prior_acceptance(self):
        self.interrupted()
        self.source.write_bytes(self.source.read_bytes() + b"changed source identity")
        oracle = OracleSessions(self.source)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "checkpoint recipe differs"):
            self.invoke(2, oracle)
        self.assertEqual(oracle.requests, [])
        self.assertFalse(self.output.exists())

    def test_unowned_directory_is_not_overwritten(self):
        self.checkpoints.mkdir()
        sentinel = self.checkpoints / "existing-user-file"
        sentinel.write_text("preserve")
        oracle = OracleSessions(self.source)
        with self.assertRaisesRegex(rebuild.ReconstructionError, "no regular manifest"):
            self.invoke(1, oracle)
        self.assertEqual(sentinel.read_text(), "preserve")
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
