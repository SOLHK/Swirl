"""Authored raw-axis examples for a detached legal avar candidate compiler."""
import bisect
from fractions import Fraction
from pathlib import Path
import struct
import sys
import unittest

from fontTools.ttLib import TTFont, newTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from font_axis_mapping import ANCHORS, GRID, build_standard_avar, compile_axis
from target_axis_mapping import SourceAxis, source_axis_plan


IDENTITY = ((-16384, -16384), (0, 0), (16384, 16384))
JUMP = ((-16384, -16384), (0, 0), (0, 65), (16384, 16384))


class AvarFont(TTFont):
    """Only the fvar order used by fontTools' real avar codec, no font payload."""
    def __init__(self, tags):
        super().__init__()
        class Axis:
            def __init__(self, tag): self.axisTag = tag
        self['fvar'] = newTable('fvar')
        self['fvar'].axes = [Axis(tag) for tag in tags]


class FontAxisMappingTests(unittest.TestCase):
    def axis(self, records=IDENTITY, tag='wght'):
        return SourceAxis(tag, 100., 500., 900., records)

    def test_identity_compiles_to_only_three_exact_required_records(self):
        for bounds in ((1, 500, 1000), (100, 499, 900), (100, 500, 600),
                       (100, 500, 900), (100, 501, 900)):
            axis = SourceAxis('TEST', *bounds, IDENTITY)
            with self.subTest(bounds=bounds):
                self.assertEqual(compile_axis(axis), ANCHORS)

    def test_raw_duplicate_zero_is_not_copied_as_a_malformed_segment_dictionary(self):
        axis = self.axis(JUMP)
        records = compile_axis(axis)
        self.assertEqual(axis.records, JUMP)
        self.assertNotEqual(records, JUMP)
        self.assertTrue(all(a[0] < b[0] and a[1] <= b[1] for a, b in zip(records, records[1:])))
        self.assertEqual(next(y for x, y in records if x == 0), 0)
        self.assertGreater(next(y for x, y in records if x > 0), 0)
        table, certificate = build_standard_avar((axis,))
        self.assertEqual(table.segments['wght'][0], 0)
        self.assertTrue(certificate['axes'][0]['source_raw_records_unchanged'])
        self.assertFalse(certificate['target_mapping_accepted'])

    def test_actual_avar_serialization_is_legal_unique_monotonic_and_exact(self):
        axes = (self.axis(JUMP, 'WDTH'), self.axis(), self.axis(JUMP, 'HGHT'))
        table, certificate = build_standard_avar(axes)
        raw = table.compile(AvarFont([axis.tag for axis in axes]))
        self.assertEqual(struct.unpack_from('>4H', raw), (1, 0, 0, 3))
        offset = 8
        for axis, summary in zip(axes, certificate['axes']):
            count = struct.unpack_from('>H', raw, offset)[0]
            offset += 2
            records = tuple(struct.unpack_from('>hh', raw, offset + 4 * i) for i in range(count))
            offset += 4 * count
            self.assertEqual(records, compile_axis(axis))
            self.assertEqual(count, summary['compiled_records'])
            self.assertTrue(all(anchor in records for anchor in ANCHORS))
            self.assertTrue(all(a[0] < b[0] and a[1] <= b[1] for a, b in zip(records, records[1:])))
        self.assertEqual(offset, len(raw))

    def test_nonmonotonic_candidate_is_rejected_without_reordering_raw_records(self):
        records = ((-16384, -16384), (-8192, 8192), (0, 0), (16384, 16384))
        axis = self.axis(records)
        with self.assertRaisesRegex(ValueError, 'not_monotonic'):
            compile_axis(axis)
        self.assertEqual(axis.records, records)

    def test_duplicate_endpoint_is_rejected_when_ordered_source_plan_misses_anchor(self):
        records = ((-16384, -16384), (0, 0), (16384, 12000), (16384, 16384))
        axis = self.axis(records)
        self.assertEqual(source_axis_plan(axis, axis.maximum)['source_q'], 12000)
        with self.assertRaisesRegex(ValueError, 'required_anchor_not_preserved'):
            compile_axis(axis)
        self.assertEqual(axis.records, records)

    def test_every_dense_grid_value_survives_exact_integer_collinear_compression(self):
        records = ((-16384, -16384), (-8192, -4096), (0, 0), (0, 65),
                   (8192, 12000), (16384, 16384))
        axis = self.axis(records)
        compiled = compile_axis(axis)
        self.assertLess(len(compiled), 32769)
        xs = [x for x, _ in compiled]
        for n in range(-GRID, GRID + 1):
            position = min(bisect.bisect_right(xs, n), len(compiled) - 1)
            left, right = compiled[position - 1], compiled[position]
            numerator = (n - left[0]) * (right[1] - left[1])
            denominator = right[0] - left[0]
            self.assertEqual(numerator % denominator, 0)
            actual = left[1] + numerator // denominator
            span = axis.default - axis.minimum if n < 0 else axis.maximum - axis.default
            expected = source_axis_plan(axis, axis.default + n * span / GRID)['source_q']
            self.assertEqual(actual, expected)

    def test_certificate_never_promotes_mapping_or_existing_nominal_glyph_model(self):
        axis = self.axis(JUMP)
        table, report = build_standard_avar((axis,))
        self.assertTrue(report['font_only'])
        self.assertTrue(report['mapping_candidate_only'])
        self.assertTrue(report['source_glyph_model_unchanged'])
        self.assertEqual(report['glyph_model_status'], 'NOT_REBUILT')
        self.assertEqual(report['target_glyph_model_required_space'], 'independently_verified_source_design_q')
        self.assertEqual(report['native_normalization_test'], 'NOT_RUN')
        self.assertEqual(report['target_normalized16_between_grid_knots'], 'NOT_EVALUATED')
        for field in ('source_user_mapping_accepted', 'target_mapping_accepted',
                      'continuous_space_acceptance', 'font_conversion_accepted',
                      'font_only_equivalence_accepted'):
            self.assertIs(report[field], False)
        # Each build returns a detached mutable table. An edit to one result
        # cannot corrupt the immutable compilation cache or a later build.
        table.segments['wght'][0] = 1
        again, _ = build_standard_avar((axis,))
        self.assertEqual(again.segments['wght'][0], 0)

    def test_finite_f2_grid_certificate_does_not_cover_a_quarter_grid_input(self):
        axis = self.axis(JUMP)
        records = compile_axis(axis)
        zero = records.index((0, 0))
        right = records[zero + 1]
        self.assertEqual(right, (1, 66))
        # Independent exact arithmetic at a nominal input between the compiled
        # grid knots. Every operation below is exactly representable in 16.16:
        # n16=1 is one quarter of the first F2DOT14 input cell; interpolation
        # produces mapped16=66, and specified final conversion gives q=17.
        # This is a numeric counterexample, not a native-normalizer emulator.
        original_user = 500 + 400 / 65536
        self.assertEqual(original_user, 500.006103515625)
        self.assertEqual(source_axis_plan(axis, original_user)['source_q'], 0)
        normalized = Fraction(1, 65536)
        ratio = normalized / Fraction(right[0], GRID)
        mapped = ratio * Fraction(right[1], GRID)
        self.assertEqual(ratio * 65536, 16384)
        self.assertEqual(mapped * 65536, 66)
        self.assertEqual((int(mapped * 65536) + 2) >> 2, 17)

    def test_wrong_input_shapes_and_duplicate_axis_tags_are_refused(self):
        for value in (None, {}, (), [], [None], ['wght']):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_standard_avar(value)
        with self.assertRaisesRegex(ValueError, 'duplicate_source_axis_tags'):
            build_standard_avar((self.axis(), self.axis(JUMP)))
        for value in ('wght', {}, [], None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'raw_source_axis_required'):
                compile_axis(value)


if __name__ == '__main__':
    unittest.main()
