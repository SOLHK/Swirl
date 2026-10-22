"""Source substitution and unavailable-native evidence must fail closed."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import macos_source_baseline as baseline
from test_coretext_extract import make_fixture


class SourceBaselineTests(unittest.TestCase):
    def setUp(self):
        self.faces = [{'face_index': 0, 'axes': [{'tag': 'wght'}],
                       'tables': {'head': {'sha256': 'source-head'}, 'cmap': {'sha256': 'source-cmap'}}}]
        self.native = {'source_sha256': 'original', 'faces': [
            {'face_index': 0, 'identity_verified': True,
             'verified_table_sha256': {'head': 'source-head', 'cmap': 'source-cmap'},
             'axis_requests': 4, 'axis_strict_passes': 3,
             'axis_failure_counts': {'strict_readback_failed': 1}}]}

    def test_axis_failure_does_not_become_conversion_or_windows_acceptance(self):
        report = baseline.summarize_native(self.native, 'original', self.faces)
        self.assertEqual((report['axis_requests'], report['axis_strict_passes']), (4, 3))
        self.assertFalse(report['font_generated'])
        self.assertEqual(report['windows11_acceptance'], 'NOT_RUN')

    def test_unavailable_face_has_zero_observations_and_stays_blocked(self):
        row = self.native['faces'][0]
        row.update(identity_verified=False, verified_table_sha256={}, axis_requests=0,
                   axis_strict_passes=0, axis_failure_counts={})
        result = baseline.summarize_native(self.native, 'original', self.faces)
        self.assertEqual(result['status'], 'BLOCKED_SOURCE_IDENTITY')
        self.assertEqual(result['physical_faces_verified'], 0)
        row['default_global_metrics'] = {'ascent': 800}
        with self.assertRaises(ValueError):
            baseline.summarize_native(self.native, 'original', self.faces)

    def test_system_font_substitution_rejected_even_when_shape_counts_agree(self):
        for key in ('head', 'cmap'):
            report = copy.deepcopy(self.native)
            report['faces'][0]['verified_table_sha256'][key] = 'installed-fallback'
            with self.subTest(table=key), self.assertRaises(ValueError):
                baseline.summarize_native(report, 'original', self.faces)
        with self.assertRaises(ValueError):
            baseline.summarize_native(self.native, 'other-release', self.faces)

    def test_missing_or_duplicate_physical_faces_rejected(self):
        for rows in ([], self.native['faces'] * 2, [dict(self.native['faces'][0], face_index=True)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                baseline.summarize_native(dict(self.native, faces=rows), 'original', self.faces)

    def test_failed_requests_cannot_disappear_from_counts(self):
        for update in ({'axis_strict_passes': 4}, {'axis_requests': 3},
                       {'axis_failure_counts': {'failed': -1}}, {'identity_verified': 1}):
            report = copy.deepcopy(self.native)
            report['faces'][0].update(update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                baseline.summarize_native(report, 'original', self.faces)

    def test_existing_output_or_wrong_source_rejected_before_compiler_and_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / 'input.ttc', Path(tmp) / 'result'
            make_fixture(source)
            original = source.read_bytes()
            with mock.patch.object(baseline.subprocess, 'run') as compiler:
                with self.assertRaises(ValueError):
                    baseline.run(source, output, 'wrong-source')
                self.assertFalse(output.exists())
                output.mkdir()
                marker = output / 'valuable-result'
                marker.write_text('keep')
                with self.assertRaises(ValueError):
                    baseline.run(source, output)
                self.assertEqual(marker.read_text(), 'keep')
                compiler.assert_not_called()
            self.assertEqual(source.read_bytes(), original)

    def test_real_collection_metadata_preserves_faces_and_three_original_axes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'fixture.ttc'
            make_fixture(source)
            before = baseline.digest(source)
            faces = baseline.inspect_source(source)
            self.assertEqual([f['upm'] for f in faces], [1000, 1128])
            self.assertEqual([f['unicode_codepoint_count'] for f in faces], [2, 2])
            for face in faces:
                self.assertEqual([a['tag'] for a in face['axes']], ['WDTH', 'wght', 'HGHT'])
                self.assertIn('gvar', face['tables'])
                self.assertGreater(face['windows_name_record_count'], 0)
            self.assertEqual(baseline.digest(source), before)

    def test_harness_preserves_production_prefix_and_has_no_glyph_measurement_calls(self):
        extractor = Path(baseline.__file__).with_name('coretext_extract.swift')
        prefix = extractor.read_text().split('\nfunc run() throws {')[0]
        self.assertTrue(baseline.harness(extractor).startswith(prefix))
        self.assertNotIn('CTFontCreatePathForGlyph', baseline.MAIN)
        self.assertNotIn('CTFontGetAdvancesForGlyphs', baseline.MAIN)
        self.assertIn('try makeInstance', baseline.MAIN)


if __name__ == '__main__':
    unittest.main()
