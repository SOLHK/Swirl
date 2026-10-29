"""The production receiver admits only the bound source-sampling contract."""
import copy
import io
import json
from types import SimpleNamespace
import unittest
from unittest import mock

import test_verified_axis_oracle as prior
import test_native_protocol as protocol
import source_request_oracle as source
import verified_axis_oracle as legacy
import rebuild


class SourceConsumerTests(unittest.TestCase):
    setUp = prior.VerifiedAxisOracleTests.setUp
    request = prior.VerifiedAxisOracleTests.request
    metadata = prior.VerifiedAxisOracleTests.metadata

    def test_real_pipe_is_accepted_only_as_source_sampling_and_finishes(self):
        launcher = source.make_launcher(self.directory/'sampler', self.native)
        oracle = rebuild.NativeOracle(launcher, self.source, self.directory/'native.log')
        try:
            self.assertTrue(oracle.metadata['axis_observations_only'])
            self.assertNotIn('axis_verification_backend', oracle.metadata)
            request = self.request()
            rows = oracle.samples(0, request['glyph_ids'], request['location'])
            self.assertEqual(set(rows), {0, 1, 2})
            self.assertFalse(rows[0]['source_request_verification']['source_user_mapping_accepted'])
            summary = oracle.finish()
            self.assertEqual(summary['source_request_verification_backend'], source.BACKEND)
            self.assertEqual(summary['successful_glyph_count'], 3)
            self.assertEqual(summary['internal_native_glyph_count'], 6)
        finally:
            oracle.close()

    def test_downgraded_marker_or_forged_metadata_does_not_bypass_validation(self):
        native = source.verified_metadata(self.metadata(), self.digest, self.source.stat().st_size, self.identities)
        native['source_request_verification_dependency_binding'] = legacy.launcher_binding(
            self.native, source_request_replay=True)
        changes = [lambda m: m.__setitem__('axis_observations_only', False),
                   lambda m: m.__setitem__('source_request_verification_backend', 'unreviewed'),
                   lambda m: m['source_request_verification_policy'].__setitem__('target_mapping_accepted', True)]
        for index, change in enumerate(changes):
            metadata = copy.deepcopy(native)
            change(metadata)
            reader = mock.Mock()
            reader.readline.return_value = json.dumps(metadata)+'\n'
            output = SimpleNamespace(fileno=lambda: 0, close=lambda: None)
            process = SimpleNamespace(stdin=io.StringIO(), stdout=output, poll=lambda: 0)
            with mock.patch.object(rebuild.subprocess, 'Popen', return_value=process), \
                    mock.patch.object(rebuild, 'TimedLineReader', return_value=reader):
                with self.assertRaises(rebuild.ReconstructionError):
                    rebuild.NativeOracle(self.native, self.source, self.directory/f'rejected{index}.log')

    def test_each_proof_is_bound_before_counting_glyphs(self):
        request = self.request(request_id='1')
        rows = source.verify_batch(request, self.identities, self.digest,
            lambda r: [prior.native_record(r, gid) for gid in r['glyph_ids']], 1)
        changes = [lambda r: r.pop('source_request_verification'),
                   lambda r: r['source_request_verification'].__setitem__('verified_GID_list', [0]),
                   lambda r: r['source_request_verification'].__setitem__('strict_axis_echo_accepted', True)]
        for change in changes:
            modified = copy.deepcopy(rows)
            change(modified[-1])
            oracle = protocol.NativeProtocolTests().oracle(modified)
            oracle.metadata = {'source_sha256': self.digest}
            oracle.source_request_identities = self.identities
            oracle.source_request_strict_counts = dict.fromkeys(
                ('strict_axis_count', 'strict_axis_pass_count', 'strict_axis_failure_count'), 0)
            with self.assertRaises(rebuild.ReconstructionError):
                oracle.samples(0, request['glyph_ids'], request['location'])
            self.assertEqual(oracle.successful_glyph_count, 0)

    def test_final_strict_diagnostic_totals_cannot_hide_a_failure(self):
        summary = {'type': 'summary', 'source_sha256': self.digest, 'error_count': 0,
            'request_count': 1, 'successful_glyph_count': 3, 'source_unchanged': True,
            'source_request_verification_backend': source.BACKEND,
            'source_request_verification_policy': copy.deepcopy(source.POLICY), 'verified_batch_count': 1,
            'source_request_readback_diagnostic': {'strict_axis_count': 3,
                'strict_axis_pass_count': 3, 'strict_axis_failure_count': 0}}
        oracle = protocol.NativeProtocolTests().oracle([summary])
        oracle.metadata = {'source_sha256': self.digest}
        oracle.sequence, oracle.successful_glyph_count = 1, 3
        oracle.source_request_identities = self.identities
        oracle.source_request_strict_counts = {'strict_axis_count': 3,
            'strict_axis_pass_count': 2, 'strict_axis_failure_count': 1}
        with self.assertRaisesRegex(rebuild.ReconstructionError, 'final evidence is incomplete'):
            oracle.finish()


if __name__ == '__main__':
    unittest.main()
