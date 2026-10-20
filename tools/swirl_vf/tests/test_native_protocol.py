"""Protocol regressions with original message doubles and temporary original fonts.

No Apple source, native CoreText or production font data is used.
"""
import io
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rebuild import NativeOracle, ReconstructionError, native_failure_details
from test_rebuild import write_fixture


class NativeProtocolTests(unittest.TestCase):
    location = {'WDTH':600.5859375, 'wght':368.22259521484375, 'HGHT':975.7080078125}

    def oracle(self, rows):
        oracle = object.__new__(NativeOracle)
        oracle.proc = SimpleNamespace(stdin=io.StringIO())
        oracle.sequence = 0
        oracle.successful_glyph_count = 0
        oracle.summary = None
        oracle.response_timeout = 2.0
        oracle.reader = Mock()
        oracle.reader.readline.side_effect = [json.dumps(row) + '\n' for row in rows]
        return oracle

    def success(self, gid=0, **changes):
        row = {'request_id':'1','face_index':0,'glyph_id':gid,
               'location':dict(self.location),'reported_location':dict(self.location),
               'error':None,'commands':[]}
        row.update(changes)
        return row

    def test_request_error_preserves_native_reason_before_missing_location(self):
        oracle = self.oracle([{'type':'request_error','request_id':'1','face_index':0,
                               'error':'native_axis_calibration_failed'}])
        with self.assertRaisesRegex(ReconstructionError, 'native_axis_calibration_failed'):
            oracle.samples(0,[0],self.location)

    def test_glyph_failure_is_not_relabelled_as_missing_coordinates(self):
        oracle = self.oracle([self.success(error='native_path_unavailable', location=None)])
        with self.assertRaisesRegex(ReconstructionError, 'native_path_unavailable'):
            oracle.samples(0,[0],self.location)

    def test_failure_context_keeps_axis_evidence_and_excludes_private_payloads(self):
        row = {'type': 'request_error', 'request_id': '1', 'face_index': 0,
               'error': 'native_readback_replay_not_exactly_stable', 'phase': 'replay', 'axis': 'wght',
               'glyph_id': 1, 'requested_value': 612.3456, 'reported_value': 612.3455,
               'source_requested_value': 612.3456789, 'reported_value_hex': 'untrusted free text',
               'reported_axis_present': True, 'commands': ['PRIVATE_OUTLINE_SENTINEL'],
               'native_error': '/private/native/diagnostics', 'field': 'commands'}
        oracle = self.oracle([row])
        with self.assertRaises(ReconstructionError) as raised:
            oracle.samples(0, [0, 1], self.location)
        details = raised.exception.context['native_observation']
        self.assertEqual(details['axis'], 'wght')
        self.assertEqual(details['phase'], 'replay')
        self.assertEqual(details['glyph_id'], 1)
        self.assertEqual(details['reported_value'], 612.3455)
        self.assertEqual(details['reported_value_hex'], float(612.3455).hex())
        self.assertTrue(details['reported_axis_present'])
        self.assertNotIn('PRIVATE_OUTLINE_SENTINEL', json.dumps(details))
        self.assertNotIn('private', json.dumps(details))
        self.assertEqual(oracle.successful_glyph_count, 0)

    def test_failure_context_filter_rejects_invalid_types_and_nonfinite_values(self):
        for value in (None, [], 'untrusted'):
            self.assertEqual(native_failure_details(value), {})
        self.assertEqual(native_failure_details({'axis': '/private', 'phase': 'arbitrary',
            'glyph_id': True, 'requested_value': True, 'reported_value': float('nan'),
            'expected_candidate_value': float('inf'), 'source_requested_value': 10 ** 10000,
            'reported_axis_present': 1, 'field': ['commands']}), {})

    def test_successful_location_mismatch_remains_strict(self):
        wrong = dict(self.location); wrong['wght'] += 1e-10
        oracle = self.oracle([self.success(location=wrong)])
        with self.assertRaisesRegex(ReconstructionError, 'axis location mismatch:.*requested.*received'):
            oracle.samples(0,[0],self.location)

    def test_wrong_identity_is_rejected_before_reading_error(self):
        oracle = self.oracle([self.success(face_index=1, error='untrusted_error')])
        with self.assertRaisesRegex(ReconstructionError, 'response identity mismatch'):
            oracle.samples(0,[0],self.location)

    def test_missing_request_error_message_cannot_be_a_success(self):
        oracle = self.oracle([self.success(type='request_error')])
        with self.assertRaisesRegex(ReconstructionError, 'request_error without error detail'):
            oracle.samples(0,[0],self.location)

    def test_duplicate_glyph_responses_are_rejected(self):
        oracle = self.oracle([self.success(0),self.success(0)])
        with self.assertRaisesRegex(ReconstructionError, 'duplicate'):
            oracle.samples(0,[0,1],self.location)

    def test_exact_fractional_success_echoes_full_request(self):
        oracle = self.oracle([self.success(0),self.success(1)])
        rows = oracle.samples(0,[0,1],self.location)
        self.assertEqual(set(rows),{0,1})
        request = json.loads(oracle.proc.stdin.getvalue())
        self.assertEqual(request,{'request_id':'1','face_index':0,
                                 'location':self.location,'glyph_ids':[0,1]})
        self.assertTrue(all(row['location'] == self.location for row in rows.values()))
        self.assertEqual(oracle.reader.readline.call_count,2)
        oracle.reader.readline.assert_called_with(timeout=2.0)

    def test_real_protocol_cannot_admit_unverified_axis_observation_mode(self):
        # Execute an original protocol fixture, not a fake native font or path.
        # A valid source digest and face status cannot override this marker.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'protocol-source'
            source.write_bytes(b'original observation-only protocol fixture')
            metadata = {'type': 'metadata', 'backend': 'CoreText',
                        'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'faces': [{'face_index': 0, 'status': 'identity_verified'}],
                        'axis_observations_only': True}
            executable = root / 'observation-protocol'
            executable.write_text('#!' + sys.executable + '\n'
                                  + 'print(' + repr(json.dumps(metadata)) + ', flush=True)\n',
                                  encoding='utf-8')
            executable.chmod(0o700)
            with self.assertRaisesRegex(ReconstructionError, 'unverified native axis observations'):
                NativeOracle(executable, source, root / 'native.log')

    def production_cli_fixture(self, root, marker):
        """A real CLI/process boundary with an original, temporary two-face TTC."""
        source = root / 'original-protocol-fixture.ttc'
        write_fixture(source, faces=2)
        metadata = {'type': 'metadata', 'backend': 'CoreText',
                    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                    'source_byte_size': source.stat().st_size,
                    'axis_observations_only': False,
                    'synthetic_protocol_fixture_only': True,
                    'apple_or_coretext_executed': False}
        with TTCollection(source, lazy=True) as collection:
            metadata['faces'] = [
                {'face_index': i, 'status': 'identity_verified',
                 'upm': font['head'].unitsPerEm, 'glyph_count': font['maxp'].numGlyphs,
                 'verified_table_sha256': {tag: hashlib.sha256(font.reader[tag]).hexdigest()
                                           for tag in font.reader.tables}}
                for i, font in enumerate(collection.fonts)]
        if marker != 'absent':
            metadata['diagnostic_readback_observation_only'] = marker
        received = root / 'received-requests.jsonl'
        executable = root / 'original-protocol'
        lines = ['#!' + sys.executable, 'import json, pathlib, sys',
                 'print(' + repr(json.dumps(metadata)) + ', flush=True)',
                 'for line in sys.stdin:',
                 '    pathlib.Path(' + repr(str(received)) + ').write_text(line)',
                 '    request = json.loads(line)',
                 "    print(json.dumps({'type': 'request_error', 'request_id': request['request_id'],",
                 "                      'face_index': request['face_index'],",
                 "                      'error': 'original_protocol_reached_sampling'}), flush=True)"]
        executable.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        executable.chmod(0o700)
        output, report = root / 'Swirl-VF.ttc', root / 'report.json'
        command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'tools' / 'rebuild.py'),
                   str(source), '--oracle', str(executable), '--output', str(output), '--report', str(report)]
        return source, executable, received, output, report, command

    def test_production_cli_rejects_diagnostic_and_malformed_markers_before_sampling(self):
        for marker in (True, 1, 0, None, 'false'):
            for checkpointed in (False, True):
                with self.subTest(marker=marker, checkpointed=checkpointed), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source, _, received, output, report, command = self.production_cli_fixture(root, marker)
                    before = source.read_bytes()
                    checkpoint = root / 'private-checkpoints'
                    if checkpointed:
                        command += ['--checkpoint-dir', str(checkpoint)]
                    result = subprocess.run(command, text=True, capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn('diagnostic-only native observations cannot be used for reconstruction', result.stderr)
                    saved = json.loads(report.read_text(encoding='utf-8'))
                    self.assertEqual(saved['status'], 'BLOCKED')
                    self.assertEqual(saved['failures'][0]['context']['stage'], 'native_metadata')
                    self.assertEqual(saved['native_observation_progress']['attempted_batches_this_run'], 0)
                    self.assertEqual(saved['faces'], [])
                    self.assertFalse(saved['output_generated'])
                    self.assertFalse(output.exists())
                    self.assertFalse(received.exists())
                    self.assertFalse(checkpoint.exists())
                    self.assertEqual(source.read_bytes(), before)

    def test_production_cli_preserves_legacy_and_explicit_nondiagnostic_metadata(self):
        for marker in ('absent', False):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                _, _, received, output, report, command = self.production_cli_fixture(root, marker)
                result = subprocess.run(command, text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('original_protocol_reached_sampling', result.stderr)
                saved = json.loads(report.read_text(encoding='utf-8'))
                self.assertEqual(saved['native_observation_progress']['attempted_batches_this_run'], 1)
                self.assertTrue(received.exists())
                self.assertFalse(output.exists())

    def test_diagnostic_transport_remains_available_outside_production_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, executable, received, _, _, _ = self.production_cli_fixture(root, True)
            oracle = NativeOracle(executable, source, root / 'diagnostic.log')
            try:
                self.assertIs(oracle.metadata['diagnostic_readback_observation_only'], True)
            finally:
                oracle.close()
            self.assertFalse(received.exists())

    def test_complete_transcript_requires_summary_eof_and_successful_process_exit(self):
        # Separate real child processes exercise errors arriving after all glyph
        # records. These are protocol messages, never claimed native font data.
        cases = [('complete', {}, 0, None, None),
                 ('missing', None, 0, None, 'without a final summary'),
                 ('wrong_count', {'request_count': 1}, 0, None, 'final summary is incomplete'),
                 ('boolean_count', {'successful_glyph_count': False}, 0, None, 'final summary is incomplete'),
                 ('late_failure', {}, 3, None, 'failed after its final glyph'),
                 ('extra_data', {}, 0, {'type': 'unexpected'}, 'after its final summary')]
        for name, changes, code, trailer, message in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'protocol-source'
                source.write_bytes(b'original final-transcript protocol fixture')
                digest = hashlib.sha256(source.read_bytes()).hexdigest()
                metadata = {'type': 'metadata', 'backend': 'CoreText', 'source_sha256': digest,
                            'faces': [{'face_index': 0, 'status': 'identity_verified'}]}
                summary = {'type': 'summary', 'source_sha256': digest, 'request_count': 0,
                           'successful_glyph_count': 0, 'error_count': 0}
                lines = ['#!' + sys.executable, 'import sys',
                         'print(' + repr(json.dumps(metadata)) + ', flush=True)', 'sys.stdin.read()']
                if changes is not None:
                    lines.append('print(' + repr(json.dumps({**summary, **changes})) + ', flush=True)')
                if trailer is not None:
                    lines.append('print(' + repr(json.dumps(trailer)) + ', flush=True)')
                lines.append('raise SystemExit(' + str(code) + ')')
                executable = root / 'finish-protocol'
                executable.write_text('\n'.join(lines) + '\n', encoding='utf-8')
                executable.chmod(0o700)
                oracle = NativeOracle(executable, source, root / 'native.log')
                try:
                    if message:
                        with self.assertRaisesRegex(ReconstructionError, message):
                            oracle.finish()
                    else:
                        self.assertEqual(oracle.finish(), summary)
                        self.assertEqual(oracle.finish(), summary)
                finally:
                    oracle.close()


if __name__ == '__main__':
    unittest.main()
