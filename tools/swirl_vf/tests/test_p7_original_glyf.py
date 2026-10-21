"""Private experiment transport checks using only authored commands/files."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
from p7_original_glyf import events_to_commands, private_directory, sample
from rebuild import compatible_coordinates


class OriginalGlyfExperimentTests(unittest.TestCase):
    def test_native_quadratics_reach_existing_C1_without_line_canonicalization(self):
        events = [['begin_part', 1], ['begin_path'], ['move', 0., 0.],
                  ['quad', 25., 0., 50., 0.], ['line', 0., 50.],
                  ['close'], ['end_path'], ['end_part', 1]]
        commands = events_to_commands(events)
        self.assertEqual(commands[1], ['qCurveTo', 25., 0., 50., 0.])
        points, flags, ends, cubics = compatible_coordinates([{'commands': commands}])
        self.assertEqual((len(points[0]), flags, ends, cubics), (4, [1,0,1,1], [3], 0))
        with self.assertRaisesRegex(ValueError, 'unclosed'):
            events_to_commands([['begin_path'], ['move', 0, 0]])
        with self.assertRaisesRegex(ValueError, 'unknown_native_event'):
            events_to_commands([['unexpected']])

    def test_output_outside_ignored_private_root_is_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'must-not-be-created'
            with self.assertRaisesRegex(ValueError, 'private_build_output_required'):
                private_directory(target)
            self.assertFalse(target.exists())

    def test_wrong_source_identity_is_refused_before_any_native_or_output_write(self):
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory)/'source', Path(directory)/'oracle'
            source.write_bytes(b'authored wrong source')
            binary.write_bytes(b'never executable')
            target = Path(directory)/'not-created'
            with patch('p7_original_glyf.sys.platform', 'darwin'):
                with self.assertRaisesRegex(ValueError, 'exact_original_source_required'):
                    sample(source, binary, target, [12], 15)
            self.assertFalse(target.exists())
            self.assertEqual(source.read_bytes(), b'authored wrong source')

    def test_dot_segments_cannot_escape_private_root_before_mkdir(self):
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)/'private'
            private.mkdir()
            target = private/'..'/'must-not-be-created'
            with patch('p7_original_glyf.PRIVATE', private):
                with self.assertRaisesRegex(ValueError, 'private_build_output_required'):
                    private_directory(target)
            self.assertFalse((Path(directory)/'must-not-be-created').exists())

    def test_symlink_inside_private_root_cannot_redirect_font_output(self):
        with tempfile.TemporaryDirectory() as directory:
            private, outside = Path(directory)/'private', Path(directory)/'outside'
            private.mkdir()
            outside.mkdir()
            (private/'link').symlink_to(outside, target_is_directory=True)
            with patch('p7_original_glyf.PRIVATE', private):
                with self.assertRaisesRegex(ValueError, 'symlink_output_refused'):
                    private_directory(private/'link'/'must-not-be-created')
            self.assertFalse((outside/'must-not-be-created').exists())


if __name__=='__main__':
    unittest.main()
