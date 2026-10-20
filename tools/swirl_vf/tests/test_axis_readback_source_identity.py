"""Retain unreadable-source evidence without simulating native acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import diagnose_axis_readback as diagnostic


class AxisReadbackSourceIdentityTests(unittest.TestCase):
    def blocked(self, verified=0):
        return {'status': 'BLOCKED_SOURCE_IDENTITY', 'source_face_count': 32,
                'physical_faces_verified': verified,
                'unavailable_face_indices': list(range(verified, 32)),
                'observations': [], 'glyph_extraction_performed': False}

    def test_zero_and_partial_identity_have_no_axis_acceptance(self):
        for verified in (0, 1, 31):
            native = self.blocked(verified)
            before = copy.deepcopy(native)
            report = diagnostic.summarize(native)
            self.assertEqual(native, before)
            self.assertEqual(report['physical_faces_verified'], verified)
            self.assertEqual(report['source_face_count'], 32)
            self.assertEqual(report['position_count'], 0)
            self.assertEqual(report['faces'], [])
            self.assertEqual(report['status'], 'BLOCKED_SOURCE_IDENTITY')
            self.assertFalse(report['glyph_extraction_performed'])

    def test_inconsistent_blocked_identity_cannot_discard_observations(self):
        for key, value in [('observations', [{'requested': {'wght': 500}}]),
                           ('physical_faces_verified', 32),
                           ('unavailable_face_indices', [0] * 32),
                           ('unavailable_face_indices', list(range(1, 33))),
                           ('source_face_count', True)]:
            native = self.blocked()
            native[key] = value
            with self.assertRaisesRegex(ValueError, 'inconsistent blocked'):
                diagnostic.summarize(native)

    def test_original_axis_errors_are_still_reported_without_relaxing_tolerance(self):
        rows = [{'face_index': 0, 'signed_errors': {'WDTH': 0, 'wght': error, 'HGHT': 0}}
                for error in (0, 1e-6, 1.1e-6)]
        native = {'status': 'AXIS_READBACK_DIAGNOSIS_NOT_ACCEPTANCE',
                  'source_face_count': 1, 'physical_faces_verified': 1, 'observations': rows}
        report = diagnostic.summarize(native)
        self.assertEqual(report['position_count'], 3)
        self.assertEqual(report['faces'][0]['positions_outside_unchanged_axis_tolerance'], 1)
        self.assertEqual(report['faces'][0]['maximum_absolute_errors']['wght'], 1.1e-6)
        native['physical_faces_verified'] = 0
        with self.assertRaisesRegex(ValueError, 'every physical source face'):
            diagnostic.summarize(native)

    def test_blocked_result_is_saved_and_bound_to_actual_generated_harness(self):
        # An original non-font input and process double test only report plumbing.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / 'original-not-a-font', root / 'report.json'
            source.write_bytes(b'original-source-identity-report-test')
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            native = {**self.blocked(), 'source_sha256': expected}
            executions = [subprocess.CompletedProcess([], 0, '', ''),
                          subprocess.CompletedProcess([], 0, json.dumps(native), '')]
            with patch.object(diagnostic, 'EXPECTED', expected), \
                    patch.object(diagnostic.subprocess, 'run', side_effect=executions):
                report = diagnostic.diagnose(source, output)
                original = Path(diagnostic.__file__).with_name('coretext_extract.swift')
                wanted = hashlib.sha256(diagnostic.harness(original).encode()).hexdigest()
            self.assertEqual(json.loads(output.read_text()), report)
            self.assertEqual(report['diagnostic_harness_sha256'], wanted)
            self.assertEqual(report['status'], 'BLOCKED_SOURCE_IDENTITY')
            with self.assertRaisesRegex(ValueError, 'fresh diagnostic report'):
                with patch.object(diagnostic, 'EXPECTED', expected):
                    diagnostic.diagnose(source, output)

    def test_generated_swift_returns_before_instance_requests_if_any_face_is_unavailable(self):
        original = Path(diagnostic.__file__).with_name('coretext_extract.swift')
        swift = diagnostic.harness(original)
        main = swift.split('func diagnosticMain() throws {')[1]
        block = main.split('var observations:')[0]
        self.assertIn('BLOCKED_SOURCE_IDENTITY', block)
        self.assertIn('return', block)
        self.assertNotIn('diagnosticInstance(', block)
        self.assertNotIn('try diagnosticMain()\n', swift)
        self.assertIn('exit(2)', swift)


if __name__ == '__main__':
    unittest.main()
