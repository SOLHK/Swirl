"""Authored endpoint clipping and exact arithmetic, never source glyph data."""
import bisect
from fractions import Fraction
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from design_axis_basis import (DesignAxisBasis, basis_from_axis, build_rebased_avar,
    compile_rebased_axis, coordinate_error_bound, decode_target_r, encode_source_q)
from font_axis_mapping import ANCHORS, GRID, compile_axis
from target_axis_mapping import SourceAxis, source_axis_plan
from test_font_axis_mapping import AvarFont


IDENTITY = ((-16384, -16384), (0, 0), (16384, 16384))
# Authored raw format example: zero jump and a clipped used positive endpoint.
CLIPPED = ((-16384, -16384), (0, 0), (0, 65),
           (16384, 13107), (16384, 16384))


class DesignAxisBasisTests(unittest.TestCase):
    def axis(self, records=CLIPPED, tag='wght'):
        return SourceAxis(tag, 100., 500., 900., records)

    def test_real_endpoint_candidate_is_frozen_and_rebased_without_changing_raw_source(self):
        axis = self.axis()
        basis = basis_from_axis(axis)
        self.assertEqual(basis, DesignAxisBasis('wght', -16384, 0, 13107))
        with self.assertRaisesRegex(ValueError, 'required_anchor_not_preserved'):
            compile_axis(axis)
        compiled_basis, records = compile_rebased_axis(axis)
        self.assertEqual(compiled_basis, basis)
        self.assertTrue(all(anchor in records for anchor in ANCHORS))
        self.assertEqual(axis.records, CLIPPED)
        for q, expected in ((-16384, -16384), (0, 0), (13107, 16384)):
            r = encode_source_q(basis, q)
            self.assertIs(type(r), int)
            self.assertEqual(r, expected)
            self.assertEqual(decode_target_r(basis, r), q)

    def test_all_integer_q_values_embed_injectively_with_exact_rational_error_bound(self):
        for lo, hi in ((-16384, 13107), (-12000, 3276), (-16384, 16384)):
            basis = DesignAxisBasis('TEST', lo, 0, hi)
            previous = None
            for q in range(lo, hi + 1):
                r = encode_source_q(basis, q)
                self.assertTrue(previous is None or previous < r)
                previous = r
                decoded = decode_target_r(basis, r)
                self.assertIsInstance(decoded, Fraction)
                self.assertLessEqual(abs(decoded - q), coordinate_error_bound(basis, q))
                # Integer recovery is distinct from fractional coordinate
                # replay, which is generally inexact during interpolation.
                nearest = (decoded + Fraction(1, 2)).__floor__()
                self.assertEqual(nearest, q)

    def test_fractional_inverse_is_explicitly_not_numeric_identity(self):
        basis = DesignAxisBasis('TEST', -16384, 0, 13107)
        r = encode_source_q(basis, 1)
        self.assertEqual(r, 1)
        self.assertEqual(decode_target_r(basis, r), Fraction(13107, 16384))
        self.assertNotEqual(decode_target_r(basis, r), 1)
        self.assertLessEqual(abs(decode_target_r(basis, r) - 1), Fraction(13107, 32768))
        # Positive and negative half ties go toward the higher integer.
        symmetric = DesignAxisBasis('TEST', -8192, 0, 8192)
        self.assertEqual(encode_source_q(symmetric, -1), -2)
        self.assertEqual(encode_source_q(symmetric, 1), 2)

    def test_serialized_new_avar_is_legal_and_ordered_on_all_three_axes(self):
        axes = (self.axis(IDENTITY, 'WDTH'), self.axis(), self.axis(IDENTITY, 'HGHT'))
        table, certificate = build_rebased_avar(axes)
        data = table.compile(AvarFont([axis.tag for axis in axes]))
        self.assertEqual(struct.unpack_from('>4H', data), (1, 0, 0, 3))
        offset = 8
        for axis in axes:
            count = struct.unpack_from('>H', data, offset)[0]
            offset += 2
            records = tuple(struct.unpack_from('>hh', data, offset + 4*i) for i in range(count))
            offset += 4*count
            self.assertEqual(records, compile_rebased_axis(axis)[1])
            self.assertTrue(all(anchor in records for anchor in ANCHORS))
            self.assertTrue(all(a[0] < b[0] and a[1] <= b[1] for a, b in zip(records, records[1:])))
        self.assertEqual(offset, len(data))
        self.assertEqual(certificate['bases'][1]['q_max'], 13107)

    def test_dense_grid_preserved_by_shared_exact_collinear_compression(self):
        axis = self.axis()
        basis, records = compile_rebased_axis(axis)
        xs = [x for x, _ in records]
        for n in range(-GRID, GRID + 1):
            i = min(bisect.bisect_right(xs, n), len(records) - 1)
            a, b = records[i - 1], records[i]
            numerator = (n - a[0]) * (b[1] - a[1])
            denominator = b[0] - a[0]
            self.assertEqual(numerator % denominator, 0)
            actual = a[1] + numerator // denominator
            span = axis.default - axis.minimum if n < 0 else axis.maximum - axis.default
            q = source_axis_plan(axis, axis.default + n * span / GRID)['source_q']
            self.assertEqual(actual, encode_source_q(basis, q))

    def test_quarter_cell_and_original_input_collisions_are_still_unresolved(self):
        axis = self.axis()
        basis, records = compile_rebased_axis(axis)
        position = records.index((0, 0))
        first_positive = records[position + 1]
        self.assertEqual(first_positive[0], 1)
        user = 500 + 400 / 65536
        self.assertEqual(source_axis_plan(axis, user)['source_q'], 0)
        # A quarter-cell normalized16 input interpolates inside the first
        # legal segment. Rebasing endpoints does not remove this disagreement.
        mapped16 = first_positive[1]
        target_r = (mapped16 + 2) >> 2
        self.assertNotEqual(decode_target_r(basis, target_r), 0)
        low, high = 500.006199, 500.006201
        self.assertEqual(struct.pack('>f', low), struct.pack('>f', high))
        self.assertEqual(int(low * 65536 + .5), int(high * 65536 + .5))
        qa, qb = (source_axis_plan(axis, x)['source_q'] for x in (low, high))
        self.assertEqual((qa, qb), (0, 65))
        self.assertNotEqual(encode_source_q(basis, qa), encode_source_q(basis, qb))

    def test_coordinate_basis_cannot_just_relabel_a_region_outside_used_source_range(self):
        basis = DesignAxisBasis('TEST', -16384, 0, 8192)
        r = encode_source_q(basis, 8192)
        self.assertEqual(r, 16384)
        # Source region (0,16384,16384) with integer delta1 has scalar1/2
        # at the source-used endpoint. Clipping its peak to target+1 and
        # retaining delta1 would incorrectly produce1 instead of1/2.
        self.assertEqual(decode_target_r(basis, r) / 16384, Fraction(1, 2))
        self.assertNotEqual(Fraction(r, 16384), Fraction(1, 2))

    def test_certificate_disclaims_every_unimplemented_glyph_or_store_transform(self):
        table, report = build_rebased_avar((self.axis(),))
        for field in ('glyph_model_reparameterization', 'HVAR_reparameterization',
                      'VVAR_reparameterization', 'GDEF_layout_region_reparameterization'):
            self.assertEqual(report[field], 'NOT_IMPLEMENTED')
        self.assertEqual(report['glyph_model_status'], 'NOT_REBUILT')
        self.assertFalse(report['fractional_decode_is_numerically_lossless'])
        self.assertEqual(report['original_binary64_input_collisions'], 'NOT_RESOLVED')
        self.assertEqual(report['target_normalized16_between_grid_knots'], 'NOT_EVALUATED')
        for field in ('source_user_mapping_accepted', 'target_mapping_accepted',
                      'continuous_space_acceptance', 'font_conversion_accepted',
                      'font_only_equivalence_accepted'):
            self.assertIs(report[field], False)
        table.segments['wght'][0] = 1
        again, _ = build_rebased_avar((self.axis(),))
        self.assertEqual(again.segments['wght'][0], 0)

    def test_nonmonotonic_and_outside_endpoint_models_are_rejected(self):
        backward = ((-16384, -16384), (-8192, 8192), (0, 0), (16384, 16384))
        with self.assertRaisesRegex(ValueError, 'not_monotonic'):
            compile_rebased_axis(self.axis(backward))
        outside = ((-16384, -16384), (0, 0), (8192, 16000),
                   (16384, 12000), (16384, 16384))
        with self.assertRaisesRegex(ValueError, 'outside_endpoint_basis'):
            compile_rebased_axis(self.axis(outside))

    def test_invalid_basis_coordinates_and_axis_lists_are_refused(self):
        for values in ((0, 0, 1), (-1, 1, 1), (-16385, 0, 1), (-1, 0, 16385),
                       (-1., 0, 1), (-1, False, 1)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                DesignAxisBasis('TEST', *values)
        basis = DesignAxisBasis('TEST', -12000, 0, 13107)
        for q in (-12001, 13108, True, 1., None):
            with self.subTest(q=q), self.assertRaises(ValueError): encode_source_q(basis, q)
        for r in (-16385, 16385, False, 1., None):
            with self.subTest(r=r), self.assertRaises(ValueError): decode_target_r(basis, r)
        for axes in (None, (), [], {}, [None]):
            with self.subTest(axes=axes), self.assertRaises(ValueError): build_rebased_avar(axes)
        with self.assertRaisesRegex(ValueError, 'duplicate_source_axis_tags'):
            build_rebased_avar((self.axis(), self.axis()))


if __name__ == '__main__':
    unittest.main()
