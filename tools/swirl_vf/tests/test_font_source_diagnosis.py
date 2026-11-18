"""Authored controls for native-source identity and minimal format isolation."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import diagnose_font_sources as sources
from diagnose_coretext_formats import fixtures, directory_check


class FontSourceDiagnosisTests(unittest.TestCase):
    def test_discovery_uses_API_urls_and_scan_roots_and_deduplicates_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unusual = root / 'asset-with-non-font-name'; unusual.write_bytes(b'font')
            named = root / 'PiNgFaNgUI.ttc'; named.write_bytes(b'font')
            (root / 'PingFang.fontinfo').write_bytes(b'metadata')
            (root / 'PingFang-symlink.ttc').symlink_to(named)
            paths, errors = sources.discover({'fonts': [{'url': str(unusual)}]}, [root])
            self.assertEqual(set(paths), {unusual.resolve(), named.resolve()})
            self.assertFalse(errors)

    def test_equal_face_counts_never_allow_different_source_hash_or_tables(self):
        metadata = {'sha256': 'original', 'bytes': 100, 'faces': [{'face_index': 0,
            'glyph_count': 2, 'upem': 1000, 'tables': {'name': 'exact-name', 'hvgl': 'exact-outline'}}]}
        native = {'sha256': 'original', 'bytes': 100, 'source_unchanged': True, 'physical_faces': 1,
            'native_identity_faces': 1, 'registered': False, 'cgfont': False, 'url_descriptors': 1,
            'data_descriptors': 0, 'post_registration_url_descriptors': 1, 'faces': [
                {'face_index': 0, 'glyph_count': 2, 'upm': 1000, 'status': 'identity_verified',
                 'verified_table_sha256': metadata['faces'][0]['tables'].copy()}]}
        self.assertEqual(sources.validate_native(native, metadata), 1)
        for mutate in (lambda n: n.update(sha256='different-system-version'),
            lambda n: n['faces'][0]['verified_table_sha256'].update(hvgl='different-outlines'),
            lambda n: n.update(native_identity_faces=True),
            lambda n: n.update(registered=True, unregistered=False)):
            bad = copy.deepcopy(native); mutate(bad)
            with self.assertRaises(ValueError):
                sources.validate_native(bad, metadata)

    def test_copy_control_requires_identical_bytes_before_attributing_location(self):
        original = {'sha256': 'same', 'bytes': 100, 'source_unchanged': True,
                    'physical_faces': 32, 'native_identity_faces': 32, 'url_descriptors': 268}
        copied = dict(original, native_identity_faces=0, url_descriptors=0, register_error_code=103)
        report = sources.compare_copy(original, copied)
        self.assertTrue(report['byte_identical'])
        self.assertEqual(report['private_platform_implementation_cause'], 'NOT_PROVEN')
        self.assertEqual(report['location_dependent_api_differences']['native_identity_faces'], [32, 0])
        copied['sha256'] = 'another-release'
        with self.assertRaises(ValueError):
            sources.compare_copy(original, copied)

    def test_minimal_controls_preserve_axes_names_cmap_and_metrics_and_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = fixtures(Path(tmp))
            all_tables = {}
            for mode, path in paths.items():
                self.assertEqual(directory_check(path)['status'], 'PASS')
                metadata = sources.inspect(path)
                self.assertEqual(metadata['faces'][0]['glyph_count'], 2)
                self.assertEqual([a['tag'] for a in metadata['faces'][0]['axes']], ['WDTH', 'wght', 'HGHT'])
                with TTFont(path) as font:
                    all_tables[mode] = {str(tag): font.reader[tag] for tag in font.reader.keys()}
            for mode in ('both', 'hvgl-only'):
                for tag, data in all_tables['standard'].items():
                    if tag in ('glyf', 'loca', 'gvar', 'head'):
                        continue
                    self.assertEqual(all_tables[mode][tag], data, (mode, tag))
            self.assertEqual(set(all_tables['both']) - set(all_tables['standard']), {'hvgl'})
            self.assertEqual(set(all_tables['both']) - set(all_tables['hvgl-only']), {'glyf', 'loca', 'gvar'})
            self.assertEqual(all_tables['both']['hvgl'], all_tables['hvgl-only']['hvgl'])

    def test_sfnt_checker_detects_payload_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = fixtures(Path(tmp))['standard']
            data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
            with self.assertRaises(ValueError):
                directory_check(path)

    def test_probe_keeps_existing_identity_and_axis_helpers(self):
        extractor = Path(sources.__file__).with_name('coretext_extract.swift').read_text()
        self.assertTrue(sources.harness().startswith(extractor.split('\nfunc run() throws {')[0]))
        self.assertNotIn('CTFontCreateWithName', sources.MAIN)
        self.assertIn('CTFontManagerCopyAvailablePostScriptNames', sources.MAIN)
        self.assertIn('.process', sources.MAIN)

    def test_public_report_does_not_export_private_paths_or_unlisted_payloads(self):
        parsed = {'sha256': 'source', 'bytes': 20, 'faces': [{'glyph_count': 2, 'version': 'Version 1.0',
                  'tables': {'private': 'SENSITIVE_TABLE_PAYLOAD'}}]}
        native = {'native_identity_faces': 0, 'url_descriptors': 0, 'data_descriptors': 0,
                  'cgfont': False, 'registered': False, 'register_error_code': 103, 'source_unchanged': True,
                  'path': 'PRIVATE_SOURCE_PATH', 'faces': ['PRIVATE_OUTLINES']}
        report = {'status': 'DIAGNOSIS_COMPLETE_NOT_FONT_ACCEPTANCE', 'host': 'test',
                  'source_sha256': 'source', 'source_unchanged': True,
                  'inventory': 'PRIVATE_INVENTORY', 'commands': ['PRIVATE_SOURCE_PATH'], 'copy_controls': {},
                  'cases': {'supplied-source': {'path': 'PRIVATE_SOURCE_PATH', 'parsed': parsed, 'native': native}}}
        summary = sources.public_summary(report)
        for forbidden in ('PRIVATE', 'SENSITIVE'):
            self.assertNotIn(forbidden, repr(summary))
        self.assertFalse(summary['production_accepted'])


if __name__ == '__main__':
    unittest.main()
