"""The original-axis experiment must reject unauthenticated inputs pre-write."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
from p7_nominal_candidate import run
from rebuild import sha256


class NominalCandidateInputTests(unittest.TestCase):
    def test_wrong_original_is_rejected_before_output_or_font_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'authored-source'
            source.write_bytes(b'authored control, not an Apple font')
            output = root/'must-not-be-created'
            with patch('p7_nominal_candidate.TTCollection') as parse:
                with self.assertRaisesRegex(ValueError, 'exact_original_source_required'):
                    run(source, root, output)
            parse.assert_not_called()
            self.assertFalse(output.exists())

    def test_parent_byte_change_is_rejected_before_output_or_rebase(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'authored-source'
            source.write_bytes(b'authored control')
            candidate = root/'P7-Original-face0-EXPERIMENTAL.ttf'
            candidate.write_bytes(b'original authored candidate bytes')
            receipt = dict(source_sha256=sha256(source), production_accepted=False,
                           axis_models_partial=True, glyph_count=47102,
                           candidate_sha256=sha256(candidate))
            (root/'face-report.json').write_text(json.dumps(receipt))
            candidate.write_bytes(b'changed authored candidate bytes')
            output = root/'must-not-be-created'
            with patch('p7_nominal_candidate.EXPECTED', sha256(source)), \
                 patch('p7_nominal_candidate.rebase_design_font') as rebase:
                with self.assertRaisesRegex(ValueError, 'verified_private_P7_parent_required'):
                    run(source, root, output)
            rebase.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
