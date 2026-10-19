"""Native protocol regression with explicit original message doubles, no fonts."""
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rebuild import NativeOracle, ReconstructionError


class NativeProtocolTests(unittest.TestCase):
    location = {'WDTH':600.5859375, 'wght':368.22259521484375, 'HGHT':975.7080078125}

    def oracle(self, rows):
        oracle = object.__new__(NativeOracle)
        oracle.proc = SimpleNamespace(stdin=io.StringIO())
        oracle.sequence = 0
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


if __name__ == '__main__':
    unittest.main()
