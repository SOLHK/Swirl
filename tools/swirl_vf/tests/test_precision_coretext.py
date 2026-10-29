"""Bounded CoreText witness units/protocol; native execution stays separate."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
from probe_precision_coretext import outline_error, run_pair, source_units, validate_rows
from make_target_axis_controls import authored_axes, authored_control_face


class PrecisionCoreTextProtocolTests(unittest.TestCase):
    def test_physical_normalization_uses_actual_grid_and_point_size(self):
        for grid in (5, 16):
            for size in (12, 48, 1000, 5000):
                row = {'font_upem': 1000*grid, 'point_size': size,
                    'commands': [['moveTo', size*.125, size*.25], ['closePath']],
                    'horizontal_vector': [size*.3,0], 'vertical_vector': [size,0],
                    'vertical_translation': [-size*.15,-size*.9],
                    'font_ascent': size*.9, 'font_descent': size*.1, 'font_leading': 0,
                    'horizontal_layout': {'position': [0,0]}, 'vertical_layout': {'position': [0,0]}}
                actual = source_units(row, grid)
                self.assertAlmostEqual(actual['horizontal_advance'], 300)
                self.assertAlmostEqual(actual['vertical_advance'], 1000)
                self.assertAlmostEqual(actual['vertical_origin'][0], 150)
                self.assertAlmostEqual(actual['commands'][0][1], 125)
                self.assertEqual(actual['source_upem'], 1000)

    def test_complete_identity_and_successful_cleanup_are_required(self):
        row = {'type':'measurement','source_sha256':'a','point_size':12,
            'face_index':0,'glyph_id':2,'physical_face_verified':True,
            'horizontal_layout':{'physical_run_face_verified':True},
            'vertical_layout':{'physical_run_face_verified':True}}
        cleanup = {'type':'cleanup','source_sha256':'a','process_unregistered':True}
        self.assertEqual(validate_rows([row,cleanup], 'a', [12]), [row])
        for which in ('cleanup','source','face','glyph','run','duplicate','native_error'):
            rows = copy.deepcopy([row,cleanup])
            if which == 'cleanup': rows[1]['process_unregistered'] = False
            elif which == 'source': rows[0]['source_sha256'] = 'other'
            elif which == 'face': rows[0]['face_index'] = 1
            elif which == 'glyph': rows[0]['glyph_id'] = 3
            elif which == 'run': rows[0]['vertical_layout']['physical_run_face_verified'] = False
            elif which == 'duplicate': rows.insert(0, copy.deepcopy(row))
            else: rows.insert(0, {'type':'error','error':'actual_failure'})
            with self.subTest(which=which), self.assertRaises(ValueError):
                validate_rows(rows, 'a', [12])

    def test_outline_failure_is_retained_and_topology_changes_are_rejected(self):
        a = [['moveTo',0.,0.], ['lineTo',100.,0.], ['closePath']]
        b = [['moveTo',0.,0.], ['lineTo',100.0625,0.], ['closePath']]
        self.assertEqual(outline_error(a,b), 1/16)
        self.assertGreater(outline_error(a,b), 1/32)
        with self.assertRaisesRegex(ValueError, 'topology_changed'):
            outline_error(a, [['moveTo',0.,0.], ['closePath']])

    def test_pair_grid_relation_and_axis_order_are_checked_before_native_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for case in ('grid', 'axes'):
                font = authored_control_face(0, authored_axes()[0], normalized=True)
                if case == 'axes':
                    font['head'].unitsPerEm = 16000
                source = root/f'{case}.ttf'
                font.save(source)
                with self.subTest(case=case), patch('probe_precision_coretext.subprocess.run') as native:
                    with self.assertRaisesRegex(ValueError, 'source_UPEM_times_grid' if case == 'grid' else 'axis_order_differs'):
                        run_pair(source, source, root/f'output-{case}', grid_multiplier=16)
                    native.assert_not_called()
                    self.assertFalse((root/f'output-{case}').exists())


if __name__ == '__main__':
    unittest.main()
