"""Authored preflight guards: no native calls or escaping private writes."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
import p7_validate_candidate as validator
from rebuild import sha256


class CandidateValidationPreflightTests(unittest.TestCase):
    def test_wrong_original_never_executes_oracle_or_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, candidate, oracle = (root/name for name in ('source', 'candidate', 'oracle'))
            for path in (source, candidate, oracle):
                path.write_bytes(b'authored preflight control')
            output = root/'not-created'
            with patch.object(validator, 'hvf_events') as native:
                with self.assertRaisesRegex(ValueError, 'exact_original_source_required'):
                    validator.validate(source, candidate, oracle, output, 'q', validator.EXPECTED)
            native.assert_not_called()
            self.assertFalse(output.exists())

    def test_dot_segment_escape_is_rejected_before_native_or_mkdir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            private = root/'private'
            private.mkdir()
            source, candidate, oracle = root/'source', private/'candidate', root/'oracle'
            for path in (source, candidate, oracle):
                path.write_bytes(b'authored preflight control')
            with patch.object(validator, 'EXPECTED', sha256(source)), \
                 patch.object(validator, 'PRIVATE', private), \
                 patch('p7_original_glyf.PRIVATE', private), \
                 patch.object(validator, 'hvf_events') as native:
                with self.assertRaisesRegex(ValueError, 'private_build_output_required'):
                    validator.validate(source, candidate, oracle, private/'..'/'outside', 'q', sha256(source))
            native.assert_not_called()
            self.assertFalse((root/'outside').exists())


if __name__ == '__main__':
    unittest.main()
