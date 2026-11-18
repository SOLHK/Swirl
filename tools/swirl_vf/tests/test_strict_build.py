"""Exercise the real serializer and quantization gate at product precision."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys

from test_rebuild_pipeline import OriginalAnalyticOracle
from test_rebuild import analytic_record, write_fixture
import build_swirlvf
import rebuild

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from attempt_strict_rebuild import public_report


class StrictBuildTests(unittest.TestCase):
    def attempt(self, root, transform=None, *, strict=True):
        root.mkdir()
        source = root / 'authored-source.ttc'
        write_fixture(source, faces=3)
        oracle = OriginalAnalyticOracle(source)
        sample = oracle.samples
        if transform:
            def samples(face, gids, location):
                return {gid: transform(record) for gid, record in sample(face, gids, location).items()}
            oracle.samples = samples
        output, report = root / 'SwirlVF.ttc', root / 'report.json'
        with mock.patch.object(rebuild, 'NativeOracle', return_value=oracle):
            if strict:
                return build_swirlvf.run(source, root / 'analytic-oracle', output, report,
                    expected_source_sha256=rebuild.sha256(source), batch_size=2)
            return rebuild.run(source, root / 'analytic-oracle', output, report, batch_size=2)

    def test_complete_authored_collection_passes_strict_serialized_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.attempt(Path(tmp) / 'strict')
            self.assertTrue(result['output_generated'])
            self.assertEqual(result['outline_limit_font_units'], 1 / 32)
            self.assertEqual(result['metric_limit_font_units'], 1 / 32)
            self.assertEqual(result['collection_verification']['faces_checked'], 3)
            self.assertEqual(result['windows_acceptance'], 'NOT_RUN')

    def test_quarter_unit_error_cannot_inherit_historical_experiment_budget(self):
        def translated(record):
            for command in record['commands']:
                for i in range(1, len(command), 2):
                    command[i] += .25
            record['lsb'] += .25
            return record
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            historical = self.attempt(root / 'experiment', translated, strict=False)
            self.assertTrue(historical['output_generated'])
            with self.assertRaisesRegex(rebuild.ReconstructionError, 'quantization exceeds error budget'):
                self.attempt(root / 'strict', translated)
            self.assertFalse((root / 'strict' / 'SwirlVF.ttc').exists())
            saved = json.loads((root / 'strict' / 'report.json').read_text())
            self.assertEqual(saved['status'], 'BLOCKED')
            self.assertEqual(saved['failures'][0]['context']['max_outline_error'], .25)
            self.assertEqual(saved['outline_limit_font_units'], 1 / 32)

    def test_exact_cubic_is_not_rejected_by_old_point_zero_five_approximation_budget(self):
        def cubic(_record):
            record = analytic_record({})
            record['commands'] = [['moveTo', 20, -20],
                ['curveTo', 120, -20, 220, -20, 320, -20],
                ['lineTo', 320, 480], ['lineTo', 20, 480], ['closePath']]
            return record
        with tempfile.TemporaryDirectory() as tmp:
            result = self.attempt(Path(tmp) / 'strict-cubic', cubic)
            self.assertTrue(result['output_generated'])
            self.assertEqual(result['cubic_approximation_limit_font_units'], 1 / 64)
            self.assertTrue(all(face['max_outline_error'] <= 1 / 32 for face in result['faces']))

    def test_source_hash_mismatch_stops_before_native_process_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.ttc'; write_fixture(source)
            with mock.patch.object(rebuild, 'NativeOracle') as native:
                with self.assertRaisesRegex(rebuild.ReconstructionError, 'source SHA-256 differs'):
                    build_swirlvf.run(source, root / 'oracle', root / 'SwirlVF.ttc', root / 'report.json',
                                      expected_source_sha256='0' * 64)
                native.assert_not_called()
            self.assertFalse((root / 'SwirlVF.ttc').exists())

    def test_public_failure_keeps_numeric_cause_and_omits_private_payloads(self):
        secret = '/private/PRIVATE-RAW-OUTLINE'
        result = public_report({'status': 'BLOCKED', 'output_generated': False,
            'oracle': {'faces': [{}, {}], 'path': secret}, 'stdout': secret,
            'failures': [{'message': 'training/default quantization exceeds error budget ' + secret,
                'context': {'stage': 'glyph_reconstruction', 'glyph_id': 2,
                    'max_outline_error': .25, 'path': secret, 'commands': [secret],
                    'user_location': {'WDTH': 1, 'wght': 100, 'HGHT': 1, 'secret': secret}}}]})
        self.assertNotIn(secret, json.dumps(result))
        self.assertEqual(result['failures'][0]['context']['max_outline_error'], .25)
        self.assertEqual(result['native_faces_verified'], 2)
