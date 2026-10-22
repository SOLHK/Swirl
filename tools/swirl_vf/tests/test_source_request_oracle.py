"""Authored countermodels and real-pipe checks for unchanged source sampling."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import source_request_oracle as source
import verified_axis_oracle as legacy
import test_verified_axis_oracle as prior


class SourceRequestOracleTests(unittest.TestCase):
    setUp = prior.VerifiedAxisOracleTests.setUp
    request = prior.VerifiedAxisOracleTests.request
    metadata = prior.VerifiedAxisOracleTests.metadata

    def exchange(self, reported=None, mutate=None, geometry_from_request=False):
        calls = []
        def run(request):
            calls.append(copy.deepcopy(request))
            rows = [prior.native_record(request, gid, reported) for gid in request['glyph_ids']]
            if geometry_from_request:
                for row in rows:
                    row['advance_width'] += request['location']['wght']
            if mutate:
                mutate(request, rows)
            return rows
        return calls, run

    def pipe(self, *, scenario='', request=None, **limits):
        # Preserve the authored double, changing only the new protocol suffix.
        self.native.write_text(self.native.read_text().replace("endswith('-reported')", "endswith('-replay')"))
        output = io.StringIO()
        with mock.patch.dict(os.environ, {'SWIRL_AXIS_ADAPTER_TEST': scenario}):
            status = source.serve(self.source, self.native,
                                  io.StringIO(json.dumps(request or self.request()) + '\n'), output, **limits)
        return status, [json.loads(line) for line in output.getvalue().splitlines()]

    def test_exact_original_request_preserves_coordinates_and_strict_numeric_failure(self):
        request = self.request(location={'WDTH': 612.3456789, 'wght': 400., 'HGHT': 500.})
        calls, exchange = self.exchange({'WDTH': 612.3456, 'wght': 400., 'HGHT': 500.})
        rows = source.verify_batch(request, self.identities, self.digest, exchange, 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual([call['location'] for call in calls], [request['location']] * 2)
        for row in rows:
            proof = source.validate_source_evidence(row, request, self.digest, self.identities[0])
            self.assertFalse(proof['strict_axis_echo_accepted'])
            self.assertFalse(proof['source_user_mapping_accepted'])
            self.assertEqual(proof['readback_diagnostic']['strict_axis_failure_count'], 1)
            self.assertEqual(proof['verified_GID_list'], [0, 1, 2])
            self.assertEqual(row['location'], request['location'])
            self.assertEqual(row['reported_location']['WDTH'], 612.3456)

    def test_same_echo_different_canonical_geometry_is_not_same_instance(self):
        request = self.request(location={'WDTH': 500., 'wght': 415.09865, 'HGHT': 500.})
        canonical = {tag: plan['canonical'] for tag, plan in legacy.declare_readback(request['location']).items()}
        calls, exchange = self.exchange(canonical, geometry_from_request=True)
        with self.assertRaisesRegex(legacy.VerificationError, 'native_replay_payload_not_exact'):
            legacy.verify_batch(request, self.identities, self.digest, exchange, 1)
        self.assertNotEqual(calls[0]['location'], calls[1]['location'])
        calls, exchange = self.exchange(canonical, geometry_from_request=True)
        rows = source.verify_batch(request, self.identities, self.digest, exchange, 1)
        self.assertEqual(calls[0]['location'], calls[1]['location'])
        self.assertEqual(rows[0]['advance_width'], 431.25 + 415.09865)
        self.assertNotIn('axis_verification', rows[0])

    def test_omitted_nondefault_readback_is_recorded_as_failed_echo_not_default_request(self):
        request = self.request(location={'WDTH': 500.00000001, 'wght': 400., 'HGHT': 500.})
        calls, exchange = self.exchange({})
        rows = source.verify_batch(request, self.identities, self.digest, exchange, 1)
        self.assertEqual(rows[0]['reported_location'], {})
        self.assertEqual(rows[0]['location'], request['location'])
        self.assertEqual(rows[0]['source_request_verification']['readback_diagnostic']['strict_axis_failure_count'], 1)
        self.assertEqual(calls[1]['location']['WDTH'], 500.00000001)
        _, exchange = self.exchange({})
        with self.assertRaisesRegex(legacy.VerificationError, 'nondefault_axis_not_reported'):
            legacy.verify_batch(request, self.identities, self.digest, exchange, 1)

    def test_raw_reported_dictionary_drift_is_not_hidden_by_equal_effective_values(self):
        def drift(request, rows):
            if request['request_id'].endswith('-replay'):
                for row in rows:
                    row['reported_location'].pop('WDTH')
        _, exchange = self.exchange(mutate=drift)
        with self.assertRaisesRegex(legacy.VerificationError, 'reported_dictionary_changed'):
            source.verify_batch(self.request(), self.identities, self.digest, exchange, 1)

    def test_nonfinite_boolean_out_of_range_and_unknown_reported_axes_still_fail(self):
        for reported in ({'WDTH': float('nan')}, {'WDTH': True}, {'WDTH': 1001.}, {'fake': 500.}):
            _, exchange = self.exchange(reported)
            with self.subTest(reported=reported), self.assertRaises(legacy.VerificationError):
                source.verify_batch(self.request(), self.identities, self.digest, exchange, 1)

    def test_frozen_input_bits_are_not_replaced_by_a_native_numeric_echo(self):
        identity = copy.deepcopy(self.identities[0]); identity['axes'][0]['minimum'] = -1.
        request = self.request(location={'WDTH': -0.0, 'wght': 400., 'HGHT': 500.})
        def mutate(native_request, rows):
            for row in rows:
                row['location']['WDTH'] = 0.0
        _, exchange = self.exchange(mutate=mutate)
        with self.assertRaisesRegex(legacy.VerificationError, 'binary64_changed'):
            source.verify_batch(request, [identity], self.digest, exchange, 1)

    def test_unknown_payload_field_numeric_mutation_and_signed_zero_are_rejected(self):
        for change in ('extension', 'metric', 'signed_zero', 'missing'):
            def mutate(request, rows):
                for row in rows:
                    row['future_native_field'] = {'complete': [0.0, True, 'x']}
                if request['request_id'].endswith('-replay'):
                    if change == 'extension': rows[-1]['future_native_field']['complete'][2] = 'changed'
                    if change == 'metric': rows[-1]['advance_height'] += 1e-12
                    if change == 'signed_zero': rows[-1]['future_native_field']['complete'][0] = -0.0
                    if change == 'missing': rows[-1].pop('future_native_field')
            _, exchange = self.exchange(mutate=mutate)
            with self.subTest(change=change), self.assertRaisesRegex(legacy.VerificationError, 'payload_'):
                source.verify_batch(self.request(), self.identities, self.digest, exchange, 1)

    def test_source_identity_policy_dependency_and_metadata_cannot_be_promoted(self):
        metadata = source.verified_metadata(self.metadata(), self.digest, self.source.stat().st_size, self.identities)
        metadata['source_request_verification_dependency_binding'] = legacy.launcher_binding(
            self.native, source_request_replay=True)
        source.validate_source_metadata(metadata, self.digest, self.source.stat().st_size, self.identities)
        self.assertTrue(metadata['axis_observations_only'])
        self.assertNotIn('axis_verification_backend', metadata)
        mutations = [lambda value: value.__setitem__('axis_observations_only', False),
                     lambda value: value['source_request_verification_policy'].__setitem__('source_user_mapping_accepted', True),
                     lambda value: value['faces'][0]['verified_table_sha256'].__setitem__('head', '0' * 64),
                     lambda value: value['source_request_verification_dependency_binding']['files'].__setitem__(
                         str(self.native), '0' * 64)]
        for change in mutations:
            value = copy.deepcopy(metadata); change(value)
            with self.assertRaises(legacy.VerificationError):
                source.validate_source_metadata(value, self.digest, self.source.stat().st_size, self.identities)

    def test_proof_rejects_missing_GIDs_wrong_input_counts_flags_and_unknown_fields(self):
        _, exchange = self.exchange()
        row = source.verify_batch(self.request(), self.identities, self.digest, exchange, 1)[0]
        mutations = [lambda p: p.__setitem__('verified_GID_list', [0, 1]),
                     lambda p: p.__setitem__('verified_GID_list', [0, True, 2]),
                     lambda p: p['input_binary64_bits'].__setitem__('WDTH', '0000000000000000'),
                     lambda p: p.__setitem__('verified_GIDs_in_batch', True),
                     lambda p: p.__setitem__('strict_axis_echo_accepted', True),
                     lambda p: p.__setitem__('unexpected_acceptance', True),
                     lambda p: p.__setitem__('upstream_replay_request_id', 'source-2-replay')]
        for change in mutations:
            modified = copy.deepcopy(row); change(modified['source_request_verification'])
            with self.assertRaises(legacy.VerificationError):
                source.validate_source_evidence(modified, self.request(), self.digest, self.identities[0])

    def test_real_pipe_summary_counts_eof_exit_and_source_identity_are_bound(self):
        status, rows = self.pipe()
        self.assertEqual(status, 0)
        self.assertTrue(rows[0]['axis_observations_only'])
        source.validate_source_metadata(rows[0], self.digest, self.source.stat().st_size, self.identities)
        for row in rows[1:-1]:
            source.validate_source_evidence(row, self.request(), self.digest, self.identities[0])
        summary = rows[-1]
        self.assertEqual(summary['source_request_verification_backend'], source.BACKEND)
        self.assertEqual(summary['source_request_verification_policy'], source.POLICY)
        self.assertEqual(summary['verified_batch_count'], summary['request_count'])
        self.assertEqual(summary['internal_native_request_count'], 2)
        self.assertEqual(summary['internal_native_glyph_count'], 6)
        self.assertTrue(summary['source_unchanged'])
        self.assertEqual(summary['source_request_readback_diagnostic']['strict_axis_pass_count'], 3)
        self.assertNotIn('ORIGINAL_OUTLINE_SENTINEL', json.dumps(rows))

    def test_late_batch_failure_releases_no_glyph_and_preserves_legacy_transport_failures(self):
        for scenario, limits in [('late_mismatch', {}), ('early_eof', {}), ('bad_summary', {}),
                                 ('timeout', {'response_timeout': .2}), ('', {'maximum_batch_bytes': 50})]:
            status, rows = self.pipe(scenario=scenario, **limits)
            self.assertNotEqual(status, 0)
            if scenario != 'bad_summary':
                self.assertFalse(any('commands' in row for row in rows))
            self.assertFalse(any(row.get('type') == 'summary' for row in rows))

    def test_launcher_binds_new_adapter_legacy_transport_native_runtime_and_refuses_changes(self):
        launcher = source.make_launcher(self.directory / 'source-sampler', self.native)
        content = launcher.read_text()
        self.assertIn('source_request_oracle.py', content)
        self.assertIn('verified_axis_oracle.py', content)
        self.assertIn('incremental_pipe.py', content)
        self.assertIn(legacy.source_hash(self.native), content)
        completed = subprocess.run([str(launcher), str(self.source)], input=json.dumps(self.request()) + '\n',
                                   text=True, capture_output=True, timeout=20)
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertEqual(completed.stderr, '')
        self.native.write_text(self.native.read_text() + '\n# authored mutation\n')
        changed = subprocess.run([str(launcher), str(self.source)], input='', text=True, capture_output=True, timeout=20)
        self.assertNotEqual(changed.returncode, 0)
        self.assertEqual(json.loads(changed.stdout)['error'], 'axis_launcher_dependency_changed')


if __name__ == '__main__':
    unittest.main()
