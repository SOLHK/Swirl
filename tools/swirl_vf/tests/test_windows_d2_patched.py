"""Portable negative tests for rebuilt-DLL gates; no mock is native evidence."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform' / 'win_axis_precision'))
import d2_patched as patched
from test_windows_d2_state import records, binding


def control(clean=False):
    rows = records('control')
    rows[0].update(raw_pixel_size=12, gid=2)
    for row in rows[1:-1]:
        row.update(cache_before=[], pixel_sha256='a'*64, width=128, height=128)
        if clean:
            for key in ('original_path', 'isolated_path', 'original_replay'):
                row[key] = copy.deepcopy(rows[0]['baseline_path'])
    if clean:
        rows[-1].update(original_path_mismatches=0, isolated_path_mismatches=0)
    return rows


class PatchedQtTests(unittest.TestCase):
    def test_frozen_48_control_scenarios(self):
        self.assertEqual(len(patched.SPECS), 48)
        self.assertEqual(len({patched.label(s) for s in patched.SPECS}), 48)
        self.assertTrue(all(patched.label(s).endswith('-control') for s in patched.SPECS))

    def test_baseline_failure_is_required_evidence_not_a_repair(self):
        self.assertEqual(patched.validate_control(control(), 'source', 'font', binding(), 'baseline')['original_mismatches'], 11)
        with self.assertRaises(ValueError):
            patched.validate_control(control(), 'source', 'font', binding(), 'patched')

    def test_clean_control_passes_patched_gate(self):
        self.assertEqual(patched.validate_control(control(True), 'source', 'font', binding(), 'patched')['original_mismatches'], 0)

    def test_wrapper_cannot_masquerade_as_dll_fix(self):
        with self.assertRaises(ValueError):
            patched.validate_control(records('guard'), 'source', 'font', binding(), 'patched')

    def test_reject_wrong_source(self):
        with self.assertRaises(ValueError):
            patched.validate_control(control(True), 'another', 'font', binding(), 'patched')

    def test_reject_incomplete_native_log(self):
        rows=control(True); rows.pop(3)
        with self.assertRaises(ValueError):
            patched.validate_control(rows, 'source', 'font', binding(), 'patched')

    def test_exact_ab_comparison(self):
        patched.compare_control_rows(control(), control(True))

    def test_reject_single_tiny_path_change(self):
        rows=control(True); rows[2]['original_path'][1][1] += 1/65536
        with self.assertRaises(ValueError): patched.compare_control_rows(control(), rows)

    def test_reject_changed_raster_or_cache_or_advance(self):
        for field, value in (('pixel_sha256', 'b'*64), ('cache_after', [{'x26_6': 16}]), ('advance', [3.01,0])):
            with self.subTest(field=field):
                rows=control(True); rows[2][field]=value
                with self.assertRaises(ValueError): patched.compare_control_rows(control(), rows)

    def test_reject_unrestored_delta_or_matrix(self):
        for field in ('delta_26_6','matrix_16_16','qt_cached_matrix_16_16'):
            with self.subTest(field=field):
                rows=control(True); rows[2]['after_guard'][field][0] += 1
                with self.assertRaises(ValueError): patched.compare_control_rows(control(), rows)

    def test_reject_changed_cold_reference(self):
        rows=control(True); rows[0]['baseline_path'][1][1] += 1/64
        with self.assertRaises(ValueError): patched.compare_control_rows(control(), rows)

    def test_reject_guarded_ab_logs(self):
        rows=control(True); rows[0]['mode']='guard'
        with self.assertRaises(ValueError): patched.compare_control_rows(control(), rows)

    def test_nonpath_projection_keeps_all_other_payload_fields(self):
        original={'glyphs':[{'path_px':[1], 'advance_px':[3,0]}],
                  'layout':{'runs':[{'paths_px':[2], 'advances_px':[3]}]}, 'raster':{'pixel_sha256':'a'}}
        result=patched.without_paths(original)
        self.assertEqual(result['glyphs'][0], {'advance_px':[3,0]})
        self.assertEqual(result['layout']['runs'][0], {'advances_px':[3]})
        self.assertEqual(result['raster'], original['raster'])
        self.assertIn('path_px', original['glyphs'][0])


if __name__ == '__main__': unittest.main()
