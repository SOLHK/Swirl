"""Finite source sampling cannot authorize production target reconstruction.

The source/analytic fixture is authored. Only the NativeOracle boundary is
replaced; run(), session cleanup, failure reporting and checkpoint publication
are production code. No Apple font or native platform executes here.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import rebuild
from source_request_oracle import BACKEND, POLICY
from test_rebuild import write_fixture
from test_rebuild_pipeline import OriginalAnalyticOracle
from test_rebuild_checkpoints import OracleSessions


def source_sampling_metadata(oracle, marker=True):
    oracle.metadata.update(
        axis_observations_only=marker,
        source_request_verification_backend=BACKEND,
        source_request_verification_policy=copy.deepcopy(POLICY))


class SourceRequestBuildGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='source-only-build-refusal-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'authored-three-face.ttc'
        write_fixture(self.source, faces=3)
        self.before = self.source.read_bytes()
        self.executable = self.root / 'analytic-oracle-double'
        self.executable.write_text('authored analytic protocol identity\n')
        self.output = self.root / 'Swirl-VF.ttc'
        self.checkpoints = self.root / 'private-checkpoints'

    def test_first_source_only_session_cannot_sample_checkpoint_or_publish(self):
        # Downgrading the observation boolean cannot grant target acceptance;
        # the explicit source-only contract itself must be refused by run().
        for index, marker in enumerate((True, False)):
            oracle = OriginalAnalyticOracle(self.source)
            source_sampling_metadata(oracle, marker)
            report = self.root / f'initial-{index}' / 'report.json'
            with mock.patch.object(rebuild, 'NativeOracle', return_value=oracle), \
                    self.assertRaisesRegex(rebuild.ReconstructionError, 'source-request replay cannot authorize target reconstruction'):
                rebuild.run(self.source, self.executable, self.output, report,
                            checkpoint_dir=self.checkpoints)
            self.assertEqual(oracle.requests, [])
            self.assertEqual(oracle.finish_count, 0)
            self.assertEqual(oracle.close_count, 1)
            self.assertFalse(self.output.exists())
            self.assertFalse(self.checkpoints.exists())
            self.assertEqual(self.source.read_bytes(), self.before)
            self.assertFalse(list(self.root.glob('swirl-vf-*')))
            saved = json.loads(report.read_text())
            self.assertEqual(saved['status'], 'BLOCKED')
            self.assertFalse(saved['output_generated'])
            self.assertEqual(saved['faces'], [])
            self.assertEqual(saved['native_observation_progress']['attempted_batches_this_run'], 0)
            self.assertEqual(saved['failures'][0]['context'], {'stage': 'native_metadata'})

    def test_new_source_only_session_preserves_completed_face_without_new_sampling(self):
        def configure(oracle, session):
            if session == 1:
                source_sampling_metadata(oracle)
        sessions = OracleSessions(self.source, configure=configure)
        report = self.root / 'later-session' / 'report.json'
        with mock.patch.object(rebuild, 'NativeOracle', side_effect=sessions), \
                self.assertRaisesRegex(rebuild.ReconstructionError, 'source-request replay cannot authorize target reconstruction'):
            rebuild.run(self.source, self.executable, self.output, report,
                        batch_size=2, checkpoint_dir=self.checkpoints)
        self.assertEqual(len(sessions.sessions), 2)
        first, refused = sessions.sessions
        self.assertTrue(first.requests)
        self.assertEqual(first.finish_count, 1)
        self.assertEqual(first.close_count, 1)
        self.assertEqual(refused.requests, [])
        self.assertEqual(refused.finish_count, 0)
        self.assertEqual(refused.close_count, 1)
        manifest = json.loads((self.checkpoints / 'verified-faces.json').read_text())
        self.assertEqual(set(manifest['faces']), {'0'})
        self.assertEqual(len(list(self.checkpoints.glob('*.ttf'))), 1)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.before)
        saved = json.loads(report.read_text())
        self.assertEqual(saved['status'], 'BLOCKED')
        self.assertFalse(saved['output_generated'])
        self.assertEqual(saved['failures'][0]['context'],
                         {'stage': 'native_session_metadata', 'face_index': 1})
        self.assertEqual(saved['faces'][0]['native_face_transcript']['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
