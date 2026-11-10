"""Independent synthetic/negative controls; local success is not Windows evidence."""
import copy
import ctypes.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import probe_axis_a3_normalized_runtime as probe


class FixtureControls(unittest.TestCase):
    def test_authored_three_axis_fixture_is_deterministic(self):
        data = probe.fixture()
        self.assertEqual(data, probe.fixture())
        with TTFont(io.BytesIO(data)) as font:
            self.assertEqual([(a.axisTag, a.minValue, a.defaultValue, a.maxValue)
                              for a in font['fvar'].axes], list(probe.AXES))
            self.assertEqual(font['maxp'].numGlyphs, 2)
            self.assertEqual(font.getGlyphOrder(), ['.notdef', 'square'])
            self.assertEqual(len(font['gvar'].variations['square']), 1)
            for records in font['avar'].segments.values():
                self.assertEqual(list(records.items()), [(-1., -1.), (0., 0.), (1., 1.)])

    def test_plan_retains_pair_and_two_orders_without_claiming_a_mapper(self):
        rows = probe.plan()
        self.assertEqual(len(rows), 18)
        self.assertEqual(len({r['id'] for r in rows}), 18)
        self.assertEqual([r['q'] for r in rows[:8]], list(probe.QS))
        self.assertEqual([r['q'] for r in rows[8:16]], list(reversed(probe.QS)))
        self.assertEqual([r['decimal'] for r in rows[-2:]], list(probe.PAIR))
        self.assertTrue(all(value is False for value in probe.FLAGS.values()))
        rows[0]['q'] = 123
        self.assertEqual(probe.plan()[0]['q'], -16384)

    def test_fixed_exact_rounding_and_collision(self):
        self.assertEqual([probe.fixed16(float(x)) for x in probe.PAIR], [32702870] * 2)
        self.assertEqual(probe.fixed16(-.5 / 65536), 0)
        self.assertEqual(probe.fixed16(.5 / 65536), 1)
        for value in (True, float('nan'), float('inf'), '499'):
            with self.assertRaises(ValueError): probe.fixed16(value)

    def test_missing_libraries_fail_instead_of_skipping_native_work(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'native_dll_missing'):
                probe.library_paths(directory)
        with patch.object(probe.sys, 'platform', 'win32'):
            with self.assertRaisesRegex(ValueError, 'windows_explicit'):
                probe.library_paths()


@unittest.skipUnless(sys.platform != 'win32' and ctypes.util.find_library('harfbuzz')
                     and ctypes.util.find_library('freetype'), 'native Linux libraries required')
class NativeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.report = probe.run(Path(cls.temp.name) / 'report.json')
        cls.processes = cls.report['processes']

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_native_counts_exact_metrics_and_complete_outline(self):
        self.assertEqual(self.report['checks'], {'native_observations': 72,
            'opposite_order_pairs': 36, 'normalized_glyph_checks': 64, 'all_exact': True})
        self.assertTrue(self.report['conditional_channel_verified'])
        self.assertFalse(self.report['windows_tested'])
        for key in probe.FLAGS: self.assertIs(self.report[key], False)
        for process in self.processes:
            index = {r['case']['id']: r for r in process['rows']}
            self.assertEqual(index['q_0_0']['ft']['advance'], 500)
            self.assertEqual(index['q_65_0']['ft']['advance'], 565)
            self.assertNotEqual(index['q_0_0']['ft']['points'], index['q_65_0']['ft']['points'])
            self.assertEqual(index['collision_0']['hb'], index['collision_1']['hb'])
            self.assertEqual(index['collision_0']['ft'], index['collision_1']['ft'])

    def test_equal_readback_cannot_mask_changed_metrics_or_outline(self):
        for engine, field in (('hb', 'advance'), ('ft', 'advance'), ('hb', 'extents'), ('ft', 'points')):
            processes = copy.deepcopy(self.processes)
            value = processes[0]['rows'][5][engine][field]
            if isinstance(value, int): processes[0]['rows'][5][engine][field] += 1
            elif field == 'points': value[1][0] += 1
            else: value[2] += 1
            with self.subTest(engine=engine, field=field), self.assertRaises(ValueError):
                probe.validate(processes)

    def test_missing_extra_reordered_or_bool_cases_are_rejected(self):
        for mutation in ('missing', 'extra', 'reordered', 'bool', 'native_bool', 'nan'):
            rows = copy.deepcopy(self.processes)
            if mutation == 'missing': rows[0]['rows'].pop()
            if mutation == 'extra': rows[0]['rows'].append(rows[0]['rows'][0])
            if mutation == 'reordered': rows[0]['rows'].reverse()
            if mutation == 'bool': rows[0]['rows'][4]['case']['q'] = True
            if mutation == 'native_bool': rows[0]['rows'][4]['hb']['readback'][1] = True
            if mutation == 'nan': rows[0]['rows'][4]['ft']['advance'] = float('nan')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): probe.validate(rows)

    def test_input_bits_and_opposite_order_outputs_cannot_be_silently_rewritten(self):
        for mutate in ('input', 'pair', 'versions', 'pid', 'fixture'):
            rows = copy.deepcopy(self.processes)
            if mutate == 'input': rows[0]['rows'][-1]['hb']['submitted_float32_bits'][1] = '43f980cc'
            if mutate == 'pair': rows[0]['rows'][-1]['ft']['advance'] += 1
            if mutate == 'versions': rows[1]['versions']['freetype'] = 'wrong'
            if mutate == 'pid': rows[1]['process_id'] = rows[0]['process_id']
            if mutate == 'fixture': rows[1]['fixture_sha256'] = '0' * 64
            with self.subTest(mutation=mutate), self.assertRaises(ValueError): probe.validate(rows)

    def test_failure_report_survives_and_acceptance_stays_false(self):
        target = Path(self.temp.name) / 'failed.json'
        with patch.object(probe, 'validate', side_effect=ValueError('authored_failed_guard')):
            with self.assertRaisesRegex(ValueError, 'authored_failed_guard'): probe.run(target)
        report = json.loads(target.read_text())
        self.assertEqual(report['status'], 'FAILED_SYNTHETIC_NORMALIZED_CHANNEL')
        self.assertEqual(report['error_code'], 'authored_failed_guard')
        self.assertFalse(report['conditional_channel_verified'])
        for key in probe.FLAGS: self.assertIs(report[key], False)
        with self.assertRaisesRegex(ValueError, 'new_report_path_required'): probe.run(target)


if __name__ == '__main__': unittest.main()
