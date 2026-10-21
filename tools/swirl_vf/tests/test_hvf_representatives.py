"""Deterministic authored structural sampling; contains no original font data."""
import copy
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from hvf import HVGL
from hvf_representatives import hvf_metadata, select_representatives
from test_hvf import table, shape, composite


def authored_rows(count=160):
    rows = [{'gid': gid, 'point_count': 0 if gid == 2 else 6+(gid % 19)*10,
             'contour_count': 0 if gid == 2 else 1+gid % 12, 'depth': 1+gid % 4,
             'leaf_occurrences': 1+gid % 5, 'is_composite': bool(gid % 2),
             'root_axis_count': gid % 4, 'tangent_types': [gid % 3],
             'has_rotation': gid % 17 == 0} for gid in range(count)]
    rows[-1].update(point_count=2048, contour_count=40, depth=12, is_composite=True)
    return rows


def authored_cmap():
    return {65: 3, 97: 4, 33: 5, 49: 6, 0x4E2D: 37, 0x3400: 38, 0x20000: 39,
            0x30A2: 40, 0x3042: 41, 0xFF0C: 42, 0x3002: 43, 0x391: 44,
            0x410: 45, 0xE000: 46, 0xF900: 47, 0xAC00: 48}


class HVFRepresentativesTests(unittest.TestCase):
    def test_metadata_counts_expanded_hierarchy_without_rendering(self):
        source = HVGL(table([composite(rotation=.25), shape(blends=(2, 1, 0))], visible=1))
        rows = hvf_metadata(source)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['point_count'], rows[0]['contour_count'], rows[0]['depth']), (6, 1, 2))
        self.assertEqual(rows[0]['leaf_occurrences'], 1)
        self.assertEqual(rows[0]['tangent_types'], [0, 1, 2])
        self.assertTrue(rows[0]['has_rotation'])
        self.assertTrue(rows[0]['is_composite'])

    def test_empty_metadata_and_remapped_descendant_are_explicit(self):
        empty = HVGL(table([struct.pack('<4H', 0, 0, 0, 0)]))
        self.assertEqual(hvf_metadata(empty)[0]['point_count'], 0)
        mapping = struct.pack('<HHIIIII', 1, 0, 8, 1, 1, 1, 2)
        source = HVGL(table([composite(), shape(), shape(blends=(2, 1, 1))], visible=1), mapping)
        self.assertEqual(hvf_metadata(source)[0]['tangent_types'], [1, 2])

    def test_cycles_and_invalid_metadata_count_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            hvf_metadata(HVGL(table([composite(child=0)])))
        source = HVGL(table([shape()]))
        for count in (True, 0, 2):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'glyph_count'):
                hvf_metadata(source, count)

    def test_exact_hundred_is_stable_across_metadata_and_cmap_order(self):
        rows, cmap = authored_rows(), authored_cmap()
        required = (0, 2, 12, 116, 153)
        first = select_representatives(rows, cmap, count=100, required_gids=required)
        second = select_representatives(list(reversed(rows)), dict(reversed(list(cmap.items()))),
                                        count=100, required_gids=required)
        self.assertEqual(first, second)
        self.assertEqual(len(first['gids']), 100)
        self.assertEqual(first['gids'], sorted(set(first['gids'])))
        self.assertTrue(set(required) <= set(first['gids']))
        self.assertFalse(first['geometry_evaluated'])
        self.assertFalse(first['sample_error_measured'])
        self.assertFalse(first['production_accepted'])
        self.assertEqual(first['native_calls'], 0)

    def test_real_coverage_categories_and_extremes_are_reported(self):
        plan = select_representatives(authored_rows(), authored_cmap(), count=100, required_gids=(0, 2, 12))
        selected = plan['coverage']['selected']
        self.assertEqual(selected['maximum_point_count'], 2048)
        self.assertEqual(selected['maximum_contour_count'], 40)
        self.assertEqual(selected['maximum_depth'], 12)
        self.assertGreater(selected['empty_glyphs'], 0)
        self.assertGreater(selected['composites'], 0)
        self.assertGreater(selected['direct_shapes'], 0)
        self.assertGreater(selected['rotation_glyphs'], 0)
        self.assertEqual(selected['tangent_types'], [0, 1, 2])
        for region in ('Latin_basic', 'CJK_basic', 'CJK_extension_A', 'CJK_extension_B',
                       'Punctuation', 'Digits', 'Katakana', 'Hiragana', 'Greek', 'Cyrillic', 'Hangul'):
            self.assertGreater(selected['unicode_region_GID_counts'][region], 0)
        self.assertIn('largest_point_count', plan['reasons']['159'])

    def test_scalable_full_selection_preserves_every_input_GID(self):
        rows = authored_rows()
        plan = select_representatives(rows, authored_cmap(), count=len(rows), required_gids=())
        self.assertEqual(plan['gids'], list(range(len(rows))))
        plan['selected_metadata'][0]['tangent_types'].append(4)
        self.assertEqual(rows[0]['tangent_types'], [0])

    def test_required_cases_cannot_be_silently_dropped(self):
        rows = authored_rows()
        for required in ((0, 0), (999,), (False,), (0, 1, 2)):
            with self.subTest(required=required), self.assertRaisesRegex(ValueError, 'required_GIDs'):
                select_representatives(rows, {}, count=2, required_gids=required)
        for count in (True, 0, 161):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, 'count_invalid'):
                select_representatives(rows, {}, count=count, required_gids=())

    def test_invalid_metadata_and_cmap_fail_closed(self):
        rows = authored_rows()
        cases = [rows+[copy.deepcopy(rows[0])]]
        for field, value in (('point_count', -1), ('is_composite', 1), ('tangent_types', [2, 1]),
                             ('root_axis_count', True)):
            changed = copy.deepcopy(rows)
            changed[0][field] = value
            cases.append(changed)
        for values in cases:
            with self.subTest(rows=len(values)), self.assertRaises(ValueError):
                select_representatives(values, {}, count=10, required_gids=())
        for cmap in ({65: 999}, {True: 1}, {0x110000: 1}, {65: True}):
            with self.subTest(cmap=cmap), self.assertRaisesRegex(ValueError, 'cmap_invalid'):
                select_representatives(rows, cmap, count=10, required_gids=())


if __name__ == '__main__':
    unittest.main()
