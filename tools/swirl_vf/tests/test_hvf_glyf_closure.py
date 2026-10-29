"""Authored exact closure proof, full gvar remapping and native font checks."""
import array
import copy
import io
from pathlib import Path
import sys
import unittest

import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables.ttProgram import Program

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from hvf_glyf_closure import compact_closing_points
from rebuild_c1_fixture import make_face


def authored():
    glyph = Glyph()
    glyph.numberOfContours = 2
    # The internal duplicate at1/2 must survive.
    glyph.coordinates = GlyphCoordinates([(0, 0), (50, 0), (50, 0), (50, 50), (0, 0),
                                         (100, 100), (150, 100), (150, 150), (100, 100)])
    glyph.flags = array.array('B', [0x41] + [1]*8)
    glyph.endPtsOfContours = [4, 8]
    glyph.program = Program(); glyph.program.fromBytecode([])
    glyph.recalcBounds(None)
    positive = [(3, 4), (9, 2), (9, 2), (8, 7), (3, 4),
                (-2, 3), (5, -2), (6, -3), (-2, 3)]
    negative = [(-x, -y) for x, y in positive]
    phantoms = [(3, 0), (23, 0), (0, 11), (0, -7)]
    tuples = [TupleVariation({'WDTH': support}, points + phantoms)
              for support, points in (((-1., -1., 0.), negative), ((0., 1., 1.), positive))]
    return glyph, tuples


def blob(font):
    stream = io.BytesIO(); font.save(stream)
    return stream.getvalue()


def path(font):
    result = []
    draw = hb.DrawFuncs()
    for kind, size in (('move_to', 2), ('line_to', 2), ('quadratic_to', 4), ('cubic_to', 6)):
        def record(*args, name=kind, arity=size): result.append((name, tuple(args[:arity])))
        getattr(draw, 'set_'+kind+'_func')(record)
    draw.set_close_path_func(lambda *args: result.append(('close', ())))
    font.draw_glyph(2, draw)
    return result


def without_terminal_zero_lines(commands):
    # Test-only exact equality, never the production native comparator.
    result, previous, start = [], None, None
    for index, (kind, values) in enumerate(commands):
        if kind == 'move_to': start = previous = values
        elif kind == 'line_to':
            if (values == previous == start and index+1 < len(commands)
                    and commands[index+1][0] == 'close'):
                continue
            previous = values
        elif kind in ('quadratic_to', 'cubic_to'): previous = values[-2:]
        result.append((kind, values))
    return result


class HVFGlyfClosureTests(unittest.TestCase):
    def test_multicontour_full_tuples_and_four_phantoms_remap_exactly(self):
        glyph, variations = authored()
        before = copy.deepcopy((glyph.coordinates, glyph.flags, glyph.endPtsOfContours, variations))
        compact, tuples, stats = compact_closing_points(glyph, variations)
        kept = [0, 1, 2, 3, 5, 6, 7]
        self.assertEqual(list(compact.coordinates), [glyph.coordinates[index] for index in kept])
        self.assertEqual(compact.endPtsOfContours, [3, 6])
        self.assertEqual(compact.coordinates[1], compact.coordinates[2])
        self.assertEqual(stats['removed_original_indices'], [4, 8])
        self.assertFalse(stats['production_accepted'])
        for old, new in zip(variations, tuples):
            self.assertEqual(new.axes, old.axes)
            self.assertEqual(new.coordinates, [old.coordinates[i] for i in kept] + old.coordinates[-4:])
        self.assertEqual(glyph.coordinates, before[0])
        self.assertEqual(glyph.flags, before[1])
        self.assertEqual(glyph.endPtsOfContours, before[2])
        self.assertEqual([v.coordinates for v in variations], [v.coordinates for v in before[3]])

    def test_different_endpoint_delta_and_sparse_tuple_skip_without_hiding_failure(self):
        glyph, tuples = authored()
        tuples[0].coordinates[4] = (999, 0)
        compact, _, stats = compact_closing_points(glyph, tuples)
        self.assertEqual(stats['removed_original_indices'], [8])
        self.assertEqual(stats['skipped']['different_endpoint_delta'], 1)
        self.assertEqual(compact.coordinates[4], glyph.coordinates[4])
        glyph, tuples = authored(); tuples[0].coordinates[2] = None
        compact, actual, stats = compact_closing_points(glyph, tuples)
        self.assertEqual(stats['removed_terminal_points'], 0)
        self.assertEqual(stats['skipped']['incomplete_tuple'], 2)
        self.assertEqual(list(compact.coordinates), list(glyph.coordinates))
        self.assertIsNone(actual[0].coordinates[2])

    def test_hints_composites_and_inconsistent_point_counts_are_refused(self):
        for failure in ('hints', 'composite', 'flags', 'ends', 'tuple'):
            glyph, tuples = authored()
            if failure == 'hints': glyph.program.fromBytecode([0])
            if failure == 'composite': glyph.numberOfContours = -1
            if failure == 'flags': glyph.flags.pop()
            if failure == 'ends': glyph.endPtsOfContours[-1] -= 1
            if failure == 'tuple': tuples[0].coordinates.pop()
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                compact_closing_points(glyph, tuples)

    def test_serialized_HarfBuzz_geometry_and_gvar_metric_advances_are_unchanged(self):
        glyph, tuples = authored()
        original = make_face(0)
        original['glyf']['A'] = glyph; original['gvar'].variations['A'] = tuples
        original['hmtx'].metrics['A'] = (600, 0); original['vmtx'].metrics['A'] = (1000, 750)
        del original['HVAR']; del original['VVAR']  # native advances exercise gvar phantoms
        target = copy.deepcopy(original)
        target['glyf']['A'], target['gvar'].variations['A'], _ = compact_closing_points(glyph, tuples)
        data = [blob(font) for font in (original, target)]
        with TTFont(io.BytesIO(data[1])) as decoded:
            self.assertEqual(decoded['glyf']['A'].endPtsOfContours, [3, 6])
            for source, actual in zip(target['gvar'].variations['A'], decoded['gvar'].variations['A']):
                self.assertEqual(source.axes, actual.axes)
                self.assertEqual(source.coordinates, actual.coordinates)
        native = [hb.Font(hb.Face(value)) for value in data]
        for font in native: hb.ot_font_set_funcs(font); font.scale = (64000, 64000)
        advances = []
        for q in (-1, -.375, 0, .125, .75, 1):
            for font in native: font.set_var_coords_normalized([q, 0, 0])
            for method in ('get_glyph_h_advance', 'get_glyph_v_advance', 'get_glyph_extents'):
                self.assertEqual(getattr(native[0], method)(2), getattr(native[1], method)(2))
            self.assertEqual(without_terminal_zero_lines(path(native[0])),
                             without_terminal_zero_lines(path(native[1])))
            advances.append(native[1].get_glyph_h_advance(2))
        self.assertGreater(len(set(advances)), 1)


if __name__ == '__main__':
    unittest.main()
