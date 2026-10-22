"""Authored protocol controls; these tests never assert that Windows ran."""
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTCollection

PLATFORM = Path(__file__).resolve().parents[1] / 'platform'
sys.path.insert(0, str(PLATFORM))
import p8_windows_local as probe
from rebuild_c1_fixture import make_face


class LocalDirectWriteTests(unittest.TestCase):
    def setUp(self):
        base = None
        if os.name == 'nt':
            base = Path(r'D:\Codex\Swirl-VF-private\P8-tests')
            base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.font = self.root / 'authored.ttf'
        font = make_face(0)
        font.save(self.font)
        font.close()
        self.sha = probe.digest(self.font)
        self.contract = probe.static_contract(self.font, self.sha, 7, 1)

    def authored_transcript(self):
        """Literal protocol rows are simulated evidence, never native results."""
        expected = self.contract['faces'][0]
        axes = expected['axes']
        defaults = {a['tag']: a['default'] for a in axes}
        jobs = [('default', defaults)]
        suffixes = ('0.000000', '0.173205', '0.381966', '0.618034', '0.826795', '1.000000')
        for axis in axes:
            for index, suffix in enumerate(suffixes):
                values = dict(defaults)
                values[axis['tag']] = axis['min'] if index % 2 else axis['max']
                jobs.append((f"sweep_{axis['tag']}_{suffix}", values))
        jobs.extend((f'grid_{index}', defaults) for index in range(27))
        jobs.extend((f'internal_{index}', defaults) for index in range(1, 17))
        rows = [{'record': 'header', 'input_sha256': self.sha,
                 'physical_face_count': 1, 'directwrite_supported': True},
                {'record': 'face', 'face_index': 0, 'glyph_count': 7,
                 'probed_glyph_count': 7, 'axes': axes,
                 'unicode_probes': expected['unicode_probes']}]
        for index, (name, values) in enumerate(jobs):
            rows.append({'record': 'instance', 'face_index': 0, 'case': name,
                         'requested': dict(values), 'applied': dict(values), 'status': 'PASS',
                         'geometry_points': 20, 'nonempty_glyphs': 5,
                         'total_horizontal_advance_design_units': 2000,
                         'outline_metrics_fnv1a64': str(index + 100)})
        rows.append({'record': 'face_result', 'face_index': 0,
                     'status': 'PASS_NATIVE_PROBE', 'positions': 62})
        for dpi in (96, 120, 144, 168, 192):
            for theme in ('light', 'dark'):
                name = f'face-0-default-dpi-{dpi}-{theme}.png'
                # Only the wrapper's signature gate is exercised. These files
                # are explicitly not genuine rendered PNG/native evidence.
                (self.root / name).write_bytes(b'\x89PNG\r\n\x1a\nsimulated protocol bytes')
                rows.append({'record': 'raster', 'face_index': 0,
                             'dpi': dpi, 'theme': theme, 'file': name,
                             'sizes_dip': [12, 16, 24, 36], 'antialiasing': 'grayscale'})
        rows.append({'record': 'summary', 'status': 'PASS_NATIVE_PROBE',
                     'faces_passed': 1, 'faces_failed': 0})
        report = {'status': 'PASS_NATIVE_PROBE', 'input_sha256': self.sha,
                  'input_sha256_after': self.sha, 'input_unchanged': True,
                  'source_sha256': probe.digest(PLATFORM / 'directwrite_probe.cpp')}
        return rows, report

    def validate(self, rows, report, exit_code=0):
        return probe.validate_transcript(self.contract, rows, report, exit_code, self.root)

    def test_exact_static_input_identity_and_collection_face_count(self):
        collection = TTCollection()
        collection.fonts = [make_face(0), make_face(1)]
        path = self.root / 'authored.ttc'
        collection.save(path)
        collection.close()
        before = path.read_bytes()
        contract = probe.static_contract(path, probe.digest(path), 7, 2)
        self.assertEqual(contract['container'], 'TTC')
        self.assertEqual(contract['physical_face_count'], 2)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'SHA256_mismatch'):
            probe.static_contract(path, '0' * 64, 7, 2)
        with self.assertRaisesRegex(ValueError, 'face_count_mismatch'):
            probe.static_contract(path, probe.digest(path), 7, 1)
        with self.assertRaisesRegex(ValueError, 'glyph_count_mismatch'):
            probe.static_contract(self.font, self.sha, 47102, 1)

    def test_complete_simulated_protocol_retains_non_acceptance_scope(self):
        rows, report = self.authored_transcript()
        result = self.validate(rows, report)
        self.assertEqual(result['strict_binary32_axis_comparisons'], 186)
        self.assertEqual(result['native_instances'], 62)
        self.assertEqual(result['cmap_probe_pairs'], 17)
        self.assertEqual(result['raster_captures'], 10)
        self.assertFalse(result['font_only_equivalence_accepted'])
        self.assertEqual(result['original_HVF_parity'], 'NOT_RUN')

    def test_truncated_or_wrong_input_evidence_is_rejected(self):
        original, report = self.authored_transcript()
        for change in ('summary_missing', 'wrong_sha', 'wrong_face', 'wrong_cmap',
                       'axis_readback', 'axis_boolean', 'missing_job', 'wrong_case',
                       'duplicate_job', 'native_failure'):
            with self.subTest(change=change):
                rows = copy.deepcopy(original)
                native_exit = 0
                if change == 'summary_missing': rows.pop()
                elif change == 'wrong_sha': rows[0]['input_sha256'] = '0' * 64
                elif change == 'wrong_face': rows[1]['face_index'] = 1
                elif change == 'wrong_cmap': rows[1]['unicode_probes'][0]['glyph_id'] = 0
                elif change == 'axis_readback': rows[2]['applied']['wght'] += .01
                elif change == 'axis_boolean': rows[1]['axes'][0]['min'] = True
                elif change == 'missing_job': rows.pop(3)
                elif change == 'wrong_case': rows[3]['case'] = 'unexpected_position'
                elif change == 'duplicate_job': rows[3]['case'] = rows[2]['case']
                elif change == 'native_failure': native_exit = 1
                with self.assertRaises(ValueError):
                    self.validate(rows, report, native_exit)

    def test_no_movement_and_missing_or_escaping_rasters_rejected(self):
        original, report = self.authored_transcript()
        cases = ('fixed_outlines', 'missing_raster', 'escape', 'backslash', 'wrong_signature')
        for change in cases:
            with self.subTest(change=change):
                rows = copy.deepcopy(original)
                if change == 'fixed_outlines':
                    for row in rows:
                        if row['record'] == 'instance': row['outline_metrics_fnv1a64'] = '123'
                elif change == 'missing_raster': rows.pop(-2)
                elif change == 'escape': rows[-2]['file'] = '../escape.png'
                elif change == 'backslash': rows[-2]['file'] = r'..\escape.png'
                elif change == 'wrong_signature': (self.root / rows[-2]['file']).write_bytes(b'not PNG')
                with self.assertRaises(ValueError): self.validate(rows, report)

    def test_json_axis_case_is_preserved_but_duplicates_and_nonfinite_rejected(self):
        self.assertEqual(set(probe.decode('{"WDTH":500,"wdth":100}')), {'WDTH', 'wdth'})
        for text in ('{"WDTH":500,"WDTH":100}', '{"value":NaN}', '{"value":Infinity}'):
            with self.assertRaises(ValueError): probe.decode(text)

    def test_windows_server_never_becomes_windows11_from_build_or_caption(self):
        for product in (2, 3):
            self.assertEqual(probe.windows_scope({'major': 10, 'minor': 0, 'build': 26100,
                                                  'product_type': product}, 'Windows 11'), 'WINDOWS_SERVER')
        client = {'major': 10, 'minor': 0, 'build': 26100, 'product_type': 1}
        self.assertEqual(probe.windows_scope(client, 'Microsoft Windows 11 Pro'), 'WINDOWS_11_CLIENT')
        self.assertEqual(probe.windows_scope(client, 'Microsoft Windows 10 Pro'),
                         'WINDOWS_CLIENT_OR_VERSION_UNRESOLVED')

    @unittest.skipIf(os.name == 'nt', 'This regression covers the real non-Windows NOT_RUN route.')
    def test_local_non_windows_route_writes_not_run_and_preserves_input(self):
        output = self.root / 'private-output'
        before = self.font.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()):
            code = probe.main(['--font', str(self.font), '--expected-sha256', self.sha,
                               '--font-scope', 'authored_control', '--expected-glyphs', '7',
                               '--output', str(output)])
        report = json.loads((output / 'p8-local-report.json').read_text())
        self.assertEqual(code, 77)
        self.assertEqual(report['status'], 'NOT_RUN')
        self.assertEqual(report['Windows11'], 'NOT_RUN')
        self.assertTrue(report['input_unchanged'])
        self.assertEqual(self.font.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
