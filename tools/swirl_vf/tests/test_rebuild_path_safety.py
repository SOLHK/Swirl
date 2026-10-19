"""Never let a report or native stderr path truncate the source or oracle."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import rebuild


class RebuildPathSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source.ttc'
        self.source.write_bytes(b'private-source-sentinel-not-a-font')
        self.before = self.source.read_bytes()
        self.oracle = self.root / 'native-oracle'
        self.output = self.root / 'Swirl-VF.ttc'
        self.report = self.root / 'report.json'

    def assert_early_block(self, report):
        with mock.patch.object(rebuild, 'NativeOracle') as native:
            with self.assertRaises(rebuild.ReconstructionError):
                rebuild.run(self.source, self.oracle, self.output, report)
            native.assert_not_called()
        self.assertEqual(self.source.read_bytes(), self.before)
        self.assertFalse(self.output.exists())

    def test_report_cannot_be_source(self):
        self.assert_early_block(self.source)

    def test_report_cannot_be_output(self):
        self.assert_early_block(self.output)

    def test_report_cannot_be_stderr_log(self):
        self.assert_early_block(self.root / 'native-oracle.log')

    def test_report_hardlink_cannot_truncate_source(self):
        os.link(self.source, self.report)
        self.assert_early_block(self.report)

    def test_log_hardlink_cannot_truncate_source(self):
        os.link(self.source, self.root / 'native-oracle.log')
        self.assert_early_block(self.report)

    def test_source_named_native_log_is_protected(self):
        renamed = self.root / 'native-oracle.log'
        self.source.rename(renamed)
        self.source = renamed
        self.assert_early_block(self.report)

    def test_oracle_executable_cannot_be_the_report(self):
        self.oracle.write_bytes(b'fake-executable')
        self.assert_early_block(self.oracle)
        self.assertEqual(self.oracle.read_bytes(), b'fake-executable')

    def test_existing_report_is_preserved(self):
        self.report.write_text('earlier evidence', encoding='utf-8')
        self.assert_early_block(self.report)
        self.assertEqual(self.report.read_text(), 'earlier evidence')

    def test_broken_output_symlink_is_not_overwritten(self):
        try:
            self.output.symlink_to(self.root / 'missing-target')
        except OSError as error:
            self.skipTest(f'local symlink capability unavailable: {error}')
        self.assert_early_block(self.report)
        self.assertTrue(self.output.is_symlink())


if __name__ == '__main__':
    unittest.main()
