"""Actual decoded lattice selection; legacy failures remain unchanged."""
from fractions import Fraction as F
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bounded_rebase import (LIMIT, RebasePrecisionError, bounded_rebase,
                            endpoint_lattice_error, nearest_integer)
from metric_variations import add_metric_variations, verify_metric_variations
from target_axis_mapping import SourceAxis
from test_rebase_design_font import q_font, source_axes, serialize
from rebase_design_font import rebase_design_font_precision8
from font_model_certificate import certify_font_models
from bounded_rebase import source_endpoint_transform


THREE_SIXTEENTHS = ((-16384, -16384), (-16384, -3072), (0, 0),
                   (16384, 3072), (16384, 16384))


def clipped_axes():
    return tuple(SourceAxis(a.tag, a.minimum, a.default, a.maximum,
                    THREE_SIXTEENTHS if a.tag == 'wght' else a.records) for a in source_axes())


class BoundedRebaseTests(unittest.TestCase):
    def test_exact_endpoint_lower_bound_proves_8x_cannot_be_fixed_by_extra_regions(self):
        self.assertEqual(endpoint_lattice_error(F(3, 16), 8), F(1, 16))
        self.assertEqual(endpoint_lattice_error(F(3, 16), 12), F(1, 48))
        self.assertEqual(endpoint_lattice_error(F(1, 8), 12), F(1, 24))
        self.assertEqual(endpoint_lattice_error(F(3, 16), 5), F(1, 80))
        self.assertEqual(nearest_integer(F(-3, 2)), -1)
        self.assertEqual(nearest_integer(F(3, 2)), 2)

    def test_actual_legacy_failure_and_new_serialized_font_continuous_fix(self):
        source = q_font(weight_delta=1)
        source.recalcTimestamp = False
        before = serialize(source)
        axes = clipped_axes()
        legacy, _ = rebase_design_font_precision8(source, axes)
        failure = certify_font_models(source, legacy, source_endpoint_transform(axes), target_upem_multiplier=8)
        self.assertEqual(failure['max_metric_error'], F(1, 16))
        self.assertFalse(failure['within_1_32'])
        candidate, report = bounded_rebase(source, axes)
        self.assertEqual(serialize(source), before)
        self.assertEqual(report['selected_multiplier'], 5)
        self.assertEqual(candidate['head'].unitsPerEm, source['head'].unitsPerEm * 5)
        proof = report['continuous_model_certificate']
        self.assertEqual(proof['max_metric_error'], F(1, 80))
        self.assertEqual(proof['max_point_squared_error'], F(1, 6400))
        self.assertTrue(proof['within_1_32'])
        self.assertEqual([row['status'] for row in report['attempts'][:4]],
                         ['REFUSED_ENDPOINT_LATTICE'] * 4)
        self.assertEqual(report['tolerance_source_font_units'], LIMIT)
        self.assertTrue(report['HVAR_VVAR_regenerated_from_serialized_gvar'])
        self.assertEqual(verify_metric_variations(candidate)['status'], 'PASS_EXACT_STANDARD_METRIC_COEFFICIENTS')
        self.assertFalse(report['production_accepted'])
        self.assertFalse(report['font_only_equivalence_accepted'])

    def test_half_coefficient_chooses_a_different_grid_from_the_actual_model(self):
        candidate, report = bounded_rebase(q_font(weight_delta=1), source_axes())
        self.assertEqual(report['selected_multiplier'], 2)
        self.assertEqual(report['continuous_model_certificate']['max_metric_error'], 0)
        self.assertLessEqual(report['continuous_model_certificate']['max_point_squared_error'], LIMIT**2)

    def test_native_rounding_can_amplify_the_fixed_one_eightieth_model_error(self):
        import uharfbuzz as hb
        from continuous_model import evaluate_model
        from font_model_certificate import advance_models
        from precision_metrics import scale_with_precision_metrics
        source = q_font(weight_delta=1)
        candidate, report = bounded_rebase(source, clipped_axes())
        reference = scale_with_precision_metrics(source, 5000)
        q, r = (F(63, 16384), F(3, 16), F(0)), (F(63, 16384), F(1), F(0))
        expected = [evaluate_model(advance_models(font)['HVAR', 'A'], location)[0]/5
                    for font, location in ((reference, q), (candidate, r))]
        self.assertEqual(expected, [F(299515, 1024), F(1497639, 5120)])
        self.assertEqual(abs(expected[0]-expected[1]), F(1, 80))
        actual = []
        for font, location in (
            (reference, {'XWDT': float(q[0]), 'XWGT': float(q[1]), 'XHGT': 0.}),
            (candidate, {'WDTH': 500+500*float(r[0]), 'wght': 900., 'HGHT': 500.})):
            native = hb.Font(hb.Face(serialize(font)))
            hb.ot_font_set_funcs(native)
            native.scale = (64000, 64000)  # identical physical output scale
            native.set_variations(location)
            actual.append(native.get_glyph_h_advance(2))
        self.assertEqual(actual, [18714, 18726])
        self.assertEqual(F(abs(actual[0]-actual[1]), 64), F(3, 16))
        self.assertGreater(F(abs(actual[0]-actual[1]), 64), LIMIT)
        self.assertTrue(report['continuous_model_certificate']['within_1_32'])
        self.assertFalse(report['font_only_equivalence_accepted'])

    def test_all_six_UPM_families_fix_the_same_witness_with_legal_data(self):
        for upem in (1000, 1028, 1064, 1100, 1128, 1144):
            source = q_font(weight_delta=1)
            source['head'].unitsPerEm = upem
            with self.subTest(upem=upem):
                candidate, report = bounded_rebase(source, clipped_axes())
                self.assertEqual(candidate['head'].unitsPerEm, upem * 5)
                self.assertLessEqual(candidate['head'].unitsPerEm, 16384)
                self.assertEqual(report['continuous_model_certificate']['max_metric_error'], F(1, 80))

    def test_no_legal_integer_multiplier_is_not_relabelled_as_global_success(self):
        source = q_font(weight_delta=1)
        source['head'].unitsPerEm = 1144
        for gid, name in enumerate(source.getGlyphOrder()):
            for variation in source['gvar'].variations[name]:
                if 'XWGT' in variation.axes:
                    variation.coordinates = [(gid + 1 if x else 0, y) for x, y in variation.coordinates]
        del source['HVAR']; del source['VVAR']
        add_metric_variations(source)
        source.recalcTimestamp = False
        before = serialize(source)
        # There are 14 legal integer multipliers. Actual decoded HVAR corner
        # values already exclude them all, without building doomed candidates.
        with mock.patch('bounded_rebase.scale_with_precision_metrics', side_effect=AssertionError('preflight must reject')):
            with self.assertRaisesRegex(RebasePrecisionError, 'no_legal_integer_grid') as error:
                bounded_rebase(source, clipped_axes())
        self.assertEqual(len(error.exception.attempts), 14)
        self.assertTrue(all(row['endpoint_metric_lower_bound'] > LIMIT for row in error.exception.attempts))
        self.assertEqual(serialize(source), before)

    def test_changed_hint_unsupported_tables_and_proof_budget_are_rejected(self):
        from fontTools.ttLib import newTable
        source = q_font(weight_delta=1)
        source['morx'] = newTable('morx')
        with self.assertRaisesRegex(RebasePrecisionError, 'unsupported_table'):
            bounded_rebase(source, clipped_axes())
        source = q_font(weight_delta=1)
        with self.assertRaisesRegex(RebasePrecisionError, 'point_budget'):
            bounded_rebase(source, clipped_axes(), max_points=1)
        with self.assertRaises(RebasePrecisionError):
            bounded_rebase(source, clipped_axes(), max_vertices=1)


if __name__ == '__main__':
    unittest.main()
