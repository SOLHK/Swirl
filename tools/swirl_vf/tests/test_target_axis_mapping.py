"""Authored axis metadata and exact arithmetic; no Apple glyph data."""
from fractions import Fraction
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import target_axis_mapping as mapping
from test_rebuild import write_fixture


IDENTITY = ((-16384, -16384), (0, 0), (16384, 16384))
# Independently authored discontinuity: raw zero is zero, its positive-side
# limit is 65/16384. This deliberately cannot be collapsed into an avar dict.
JUMP = ((-16384, -16384), (0, 0), (0, 65), (16384, 16384))


def raw_table(records):
    return struct.pack('>4H', 1, 0, 0, len(records)) + b''.join(
        struct.pack('>H', len(rows)) + b''.join(struct.pack('>hh', *pair) for pair in rows)
        for rows in records)


class TargetAxisMappingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='authored-axis-map-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.base = self.root / 'authored.ttc'
        write_fixture(self.base)

    def font(self, records=(IDENTITY,) * 3, name='axis.ttf'):
        path = self.root / name
        with TTCollection(self.base) as collection:
            font = collection.fonts[0]
            table = DefaultTable('avar')
            table.data = raw_table(records)
            font['avar'] = table
            font.save(path)
        loaded = TTFont(path, lazy=True)
        self.addCleanup(loaded.close)
        return loaded

    def test_raw_reader_preserves_duplicates_even_after_dictionary_decompilation(self):
        font = self.font((IDENTITY, JUMP, IDENTITY))
        axes = mapping.axes_from_font(font)
        self.assertEqual(axes[1].records, JUMP)
        self.assertFalse(axes[1].identity)
        # fontTools' map cannot represent both records; the serialized reader
        # remains the only source for this candidate after decompilation too.
        self.assertEqual(font['avar'].segments['wght'][0.], 65 / 16384)
        self.assertEqual(mapping.axes_from_font(font)[1].records, JUMP)

    def test_original_zero_and_positive_jump_are_not_smoothed_or_deduplicated(self):
        self.assertEqual(mapping.ordered_map(0., JUMP), 0.)
        self.assertGreater(mapping.ordered_map(1 / 65536, JUMP), 65 / 16384)
        axis = mapping.SourceAxis('wght', 100., 500., 900., JUMP)
        self.assertEqual(mapping.source_axis_plan(axis, 500.)['source_q'], 0)
        self.assertEqual(mapping.source_axis_plan(axis, 500.006199)['source_q'], 0)
        self.assertEqual(mapping.source_axis_plan(axis, 500.006201)['source_q'], 65)

    def test_raw_record_order_and_zero_fast_path_are_observable(self):
        records = ((-16384, -16384), (4096, 8192), (0, 0), (16384, 16384))
        self.assertAlmostEqual(mapping.ordered_map(.125, records), .35)
        self.assertEqual(mapping.ordered_map(.125, tuple(sorted(records))), .25)
        self.assertEqual(mapping.ordered_map(0., records), 0.)

    def test_source_candidate_uses_once_input_not_final_readback(self):
        axis = mapping.SourceAxis('wght', 100., 501., 900., JUMP)
        result = mapping.source_axis_plan(axis, 415.09865)
        self.assertEqual(result['original_user'], 415.09865)
        self.assertEqual(result['once_user'], 415.0986)
        # Authored negative branch is identity: the independent decimal-rational
        # n16 truncation is -14038; nearest F2DOT14 ties toward positive infinity.
        self.assertEqual(math.trunc((Fraction(4150986, 10000) - 501) / 401 * 65536), -14038)
        self.assertEqual(result['normalized16'], -14038 / 65536)
        self.assertEqual(result['source_q'], (-14038 + 2) // 4)
        self.assertNotEqual(result['once_user'], math.trunc(result['once_user'] * 10000) / 10000)

    def test_identity_negative_endpoint_and_positive_arithmetic_are_independent(self):
        axis = mapping.SourceAxis('WDTH', 1., 500., 1000., IDENTITY)
        below = mapping.source_axis_plan(axis, 250.12345)
        once = 250.1234
        endpoint = struct.unpack('>f', struct.pack('>f', (once - 1) / 499))[0] - 1
        self.assertEqual(below['normalized16'], math.trunc(endpoint * 65536) / 65536)
        above = mapping.source_axis_plan(axis, 753.12345)
        self.assertEqual(above['normalized16'], math.trunc(((753.1234 - 500) / 500) * 65536) / 65536)

    def test_full_source_and_target_plans_never_accept_conversion(self):
        source = self.font((IDENTITY, JUMP, IDENTITY))
        location = {'WDTH': 600.123456, 'wght': 500.006201, 'HGHT': 401.234567}
        plan = mapping.source_plan(source, location)
        self.assertEqual(plan['original_user'], location)
        self.assertEqual(plan['source_q']['wght'], 65)
        target = self.font(name='identity-target.ttf')
        encoded = mapping.target_plan(target, plan['source_q'], source_axes=mapping.axes_from_font(source))
        self.assertEqual(encoded['hb_normalized'], [plan['source_q'][tag] for tag in plan['axis_order']])
        self.assertEqual(encoded['ft_normalized'], [q * 4 for q in encoded['hb_normalized']])
        self.assertNotEqual(encoded['target_user']['wght'], location['wght'])
        self.assertTrue(encoded['application_adapter_required'])
        for result in (plan, encoded):
            for flag in mapping.FLAGS:
                self.assertIs(result[flag], False)

    def test_every_q_cell_has_exact_FLOAT_and_fixed16_for_integer_axis_families(self):
        # Authored integer ranges cover asymmetric defaults and narrow spans.
        # Exhaustive q coverage is arithmetic only, not a native acceptance run.
        families = ((1, 500, 1000), (100, 499, 900), (100, 500, 600),
                    (100, 500, 900), (100, 501, 900))
        for low, default, high in families:
            axis = mapping.SourceAxis('test', low, default, high, IDENTITY)
            for q in range(-16384, 16385):
                row = mapping.axis_transport(axis, q)
                rational = Fraction(default) + Fraction(q * (default - low if q < 0 else high - default), 16384)
                self.assertEqual(Fraction(row['target_user']), rational)
                self.assertEqual(Fraction(row['target_float32']), rational)
                self.assertEqual(row['target_fixed16'], rational * 65536)
                self.assertEqual(row['hb_normalized'], q)
                self.assertEqual(row['ft_normalized'], q * 4)

    def test_source_collision_cannot_be_repaired_by_a_font_only_target(self):
        a, b = 500.006199, 500.006201
        self.assertEqual(struct.pack('>f', a), struct.pack('>f', b))
        self.assertEqual(math.floor(a * 65536 + .5), math.floor(b * 65536 + .5))
        axis = mapping.SourceAxis('wght', 100., 500., 900., JUMP)
        qa, qb = (mapping.source_axis_plan(axis, x)['source_q'] for x in (a, b))
        self.assertEqual((qa, qb), (0, 65))
        target = mapping.SourceAxis('wght', 100., 500., 900., IDENTITY)
        # The adapter can carry known q, but must explicitly change user input.
        ya, yb = (mapping.axis_transport(target, q)['target_user'] for q in (qa, qb))
        self.assertNotEqual(ya, yb)
        self.assertNotEqual(ya, a)
        self.assertNotEqual(yb, b)

    def test_nonidentity_target_and_changed_ranges_are_rejected(self):
        source = self.font((IDENTITY, JUMP, IDENTITY))
        with self.assertRaisesRegex(ValueError, 'identity_avar'):
            mapping.target_plan(source, {'WDTH': 0, 'wght': 65, 'HGHT': 0})
        target = self.font(name='changed-ranges.ttf')
        axes = list(mapping.axes_from_font(target))
        axes[1] = mapping.SourceAxis('wght', 100., 400., 900., IDENTITY)
        with self.assertRaisesRegex(ValueError, 'ranges_changed'):
            mapping.target_plan(target, {'WDTH': 0, 'wght': 65, 'HGHT': 0}, source_axes=axes)

    def test_schema_nonfinite_boolean_q_and_inexact_encoding_fail_closed(self):
        for bounds in ((True, 500, 1000), (1, float('nan'), 1000), (1, 1, 1000), (1, 500, 32768)):
            with self.assertRaises(ValueError):
                mapping.SourceAxis('WDTH', *bounds, IDENTITY)
        axis = mapping.SourceAxis('WDTH', 1, 500, 1000, IDENTITY)
        for value in (True, float('nan'), float('inf'), 0, 1001):
            with self.assertRaises(ValueError):
                mapping.source_axis_plan(axis, value)
        for q in (True, 1., -16385, 16385):
            with self.assertRaises(ValueError):
                mapping.axis_transport(axis, q)
        fractional = mapping.SourceAxis('WDTH', 1, 500 + 1 / 65536, 1000, IDENTITY)
        with self.assertRaisesRegex(ValueError, 'not_exactly'):
            mapping.axis_transport(fractional, 1)


if __name__ == '__main__':
    unittest.main()
