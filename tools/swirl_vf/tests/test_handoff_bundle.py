"""Authored data only: runnable on Windows without CoreText or Apple libraries."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import TTFont, TTCollection, newTable

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'platform')]
from handoff_bundle import Reference, digest, read_rows, relative_file, seal, verify, write_json, write_rows
from export_mac_handoff import compare, font_integrity
from make_synthetic_hvf import create


def authored_bundle(root):
    root.mkdir()
    seed = root/'seed.ttf'
    create(seed)
    font = TTFont(seed, recalcTimestamp=False)
    builder = FontBuilder(font=font)
    builder.setupVerticalMetrics({'.notdef': (1000, 400)})
    builder.setupVerticalHeader(ascent=800, descent=-200)
    vorg = newTable('VORG'); vorg.majorVersion = 1; vorg.minorVersion = 0
    vorg.defaultVertOriginY = 800; vorg.VOriginRecords = {}; font['VORG'] = vorg
    collection = TTCollection(); collection.fonts = [font]
    source = root/'source.ttc'; collection.save(source); collection.close(); seed.unlink()
    write_json(root/'catalog.json', {'glyph_count': 1, 'faces': [{'source_index': 0, 'glyph_index': 'index.jsonl.gz'}]})
    write_rows(root/'index.jsonl.gz', [{'gid': 0, 'name': '.notdef', 'unicode': []}])
    write_json(root/'package.json', {'schema': 1, 'source': {'path': source.name, 'sha256': digest(source)},
        'catalog': 'catalog.json', 'defaults': [{'path': 'default.jsonl.gz', 'start': 0, 'count': 1}]})
    reference = Reference(root)
    try: row = reference.evaluate(0, 0, [0., 0., 0.])
    finally: reference.close()
    write_rows(root/'default.jsonl.gz', [row])
    return row


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base/'bundle'
        self.default = authored_bundle(self.root)

    def test_seal_relocate_and_evaluate_without_mac(self):
        report = seal(self.root); self.assertEqual(report['default_glyphs'], 1)
        moved = self.base/'Windows path with spaces'; shutil.copytree(self.root, moved)
        self.assertEqual(verify(moved), report)
        reference = Reference(moved); self.addCleanup(reference.close)
        q = [.375, -.25, .625]
        value = reference.evaluate(0, 0, q)
        expected = np.array(self.default['paths'][0])
        expected[:, 0] *= 1+q[0]/4
        expected[:, 1] = expected[:, 1]*(1+q[2]/4)+q[1]*20
        np.testing.assert_array_equal(value['paths'][0], expected)
        self.assertEqual(reference.default(0), self.default)
        self.assertFalse(value['native_observation'])
        self.assertFalse(value['metrics']['vertical_origin_x_is_native_observation'])

    def test_all_axis_sign_combinations(self):
        reference = Reference(self.root); self.addCleanup(reference.close)
        import itertools
        for q in itertools.product((-1., 0., 1.), repeat=3):
            result = np.array(reference.evaluate(0, 0, q)['paths'][0])
            expected = np.array(self.default['paths'][0])
            expected[:, 0] *= 1+q[0]/4
            expected[:, 1] = expected[:, 1]*(1+q[2]/4)+q[1]*20
            np.testing.assert_array_equal(result, expected)

    def test_offline_replay_runs_without_apple_engine(self):
        from validate_handoff_reference import replay
        seal(self.root)
        result = replay(self.root)
        self.assertEqual(result['status'], 'PASS_FINITE_REFERENCE_REPLAY')
        self.assertEqual(result['geometry_replayed'], 1)
        self.assertFalse(result['Apple_library_called'])
        self.assertEqual(result['CoreText'], 'NOT_RUN')

    def test_invalid_axis_or_gid_rejected(self):
        reference = Reference(self.root); self.addCleanup(reference.close)
        for q in ([1.01, 0, 0], [float('nan'), 0, 0], [0, 0], [True, 0, 0]):
            with self.assertRaises(ValueError): reference.evaluate(0, 0, q)
        for gid in (-1, 1, True):
            with self.assertRaises(ValueError): reference.evaluate(0, gid, [0, 0, 0])

    def test_tamper_and_unlisted_files_rejected(self):
        seal(self.root)
        (self.root/'extra').write_text('unlisted')
        with self.assertRaisesRegex(ValueError, 'unlisted'): verify(self.root)
        (self.root/'extra').unlink()
        with (self.root/'source.ttc').open('ab') as stream: stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'integrity'): verify(self.root)
        with self.assertRaisesRegex(ValueError, 'source_identity'): Reference(self.root)

    def test_default_duplicate_coverage_rejected_even_with_valid_hash(self):
        (self.root/'default.jsonl.gz').unlink()
        write_rows(self.root/'default.jsonl.gz', [self.default, self.default])
        with self.assertRaisesRegex(ValueError, 'gid_gap_or_duplicate'): seal(self.root)

    def test_portable_path_policy(self):
        for name in ('../outside', '/absolute', 'C:/font', 'a\\b', 'a/../b', './a', 'a//b'):
            with self.assertRaises(ValueError): relative_file(self.root, name)

    def test_gzip_crc_and_nonfinite_rejected(self):
        path = self.root/'default.jsonl.gz'
        data = bytearray(path.read_bytes()); data[-8] ^= 1; path.write_bytes(data)
        with self.assertRaises((OSError, EOFError)): list(read_rows(path))
        with self.assertRaises(ValueError): write_rows(self.root/'bad.jsonl.gz', [{'x': float('nan')}])

    def test_gzip_deterministic_and_no_clobber(self):
        write_rows(self.root/'a.gz', [{'x': 1.2345678901234567}])
        write_rows(self.root/'b.gz', [{'x': 1.2345678901234567}])
        self.assertEqual((self.root/'a.gz').read_bytes(), (self.root/'b.gz').read_bytes())
        with self.assertRaises(FileExistsError): write_rows(self.root/'a.gz', [])

    def test_sfnt_bounds_checksum_and_no_mutation(self):
        path = self.root/'source.ttc'; before = digest(path)
        self.assertEqual(font_integrity(path)['status'], 'PASS')
        self.assertEqual(before, digest(path))
        with path.open('r+b') as stream: stream.seek(-1, 2); stream.truncate()
        with self.assertRaises(ValueError): font_integrity(path)

    def test_quadratic_controls_rotation_and_winding(self):
        points = np.asarray(self.default['paths'][0])
        def events(p):
            result = [['begin_part', 0], ['begin_path'], ['move', *p[0]]]
            for i in range(0, len(p), 2): result.append(['quad', *p[i+1], *p[(i+2) % len(p)]])
            return result+[['close'], ['end_path'], ['end_part', 0]]
        self.assertEqual(compare([points], events(np.roll(points, 2, axis=0)))['maximum_control_coordinate_error'], 0)
        damaged = points.copy(); damaged[1, 0] += 1
        self.assertEqual(compare([points], events(damaged))['status'], 'FAILED')
        self.assertEqual(compare([points], events(points[::-1]))['status'], 'FAILED')


if __name__ == '__main__': unittest.main()
