"""Original arithmetic and evidence-contract tests; no Apple font assets."""
from copy import deepcopy
from fractions import Fraction
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from analyze_axis_quantization import (
    Axis, CANDIDATES, METRIC_LIMIT, analyze, divide_integer, fixed16,
    float32, ordered_map, predict,
)


IDENTITY = ((-16384, -16384), (0, 0), (16384, 16384))


def sample(value, observed):
    return {'user_location': {'wght': value},
            'best_fit': {'normalized_weight': observed,
                         'possible_interval': [observed, observed], 'max_metric_residual': 0.0},
            'within_unchanged_metric_budget': True, 'geometry_mapping_accepted': False}


def evidence(rows):
    return {'status': 'NATIVE_HVAR_MAPPING_DIAGNOSIS_NOT_FONT_ACCEPTANCE',
            'source_sha256': 'synthetic-safe-summary', 'source_unchanged': True,
            'original_records_modified': False, 'production_axis_guard_changed': False,
            'font_generated': False, 'metric_tolerance': METRIC_LIMIT,
            'physical_faces': 1, 'native_requests': len(rows),
            'reports': [{'face_index': 0, 'native_positions': len(rows),
                         'metric_inferred_locations': rows}]}


class QuantizationArithmeticTests(unittest.TestCase):
    def test_requested_example_is_exactly_binary32_representable(self):
        value = 600.5859375
        self.assertEqual(float32(value), value)
        self.assertEqual(fixed16(value) / 65536, value)
        self.assertNotEqual(float(format(value, '.7g')), value)
        self.assertNotEqual(float(format(value, '.4f')), value)

    def test_fixed_conversion_ties_have_the_documented_sign(self):
        cases = ((Fraction(1, 131072), 1), (Fraction(-1, 131072), 0),
                 (Fraction(3, 131072), 2), (Fraction(-3, 131072), -1))
        for number, expected in cases:
            self.assertEqual(fixed16(float(number)), expected)

    def test_signed_fixed_division_is_independent_of_python_round(self):
        for numerator, denominator, near, truncated in (
                (7, 2, 4, 3), (-7, 2, -4, -3), (7, -2, -4, -3),
                (-7, -2, 4, 3), (8, 3, 3, 2), (-8, 3, -3, -2)):
            self.assertEqual(divide_integer(numerator, denominator, True), near)
            self.assertEqual(divide_integer(numerator, denominator, False), truncated)
        with self.assertRaises(ValueError):
            divide_integer(1, 0, True)

    def test_two_stage_rounding_has_a_real_distinguishing_counterexample(self):
        # 3/131072 is 1.5 units on the 16.16 grid but only .375 units
        # on the 2.14 grid. Rounding once and rounding twice differ.
        axis = Axis('wght', 0.0, 1.0, 2.0, IDENTITY)
        value = 1.0 + float(Fraction(3, 131072))
        candidates = {candidate.name: candidate for candidate in CANDIDATES}
        direct = predict(value, axis, candidates['double_then_f2dot14'])
        fixed = predict(value, axis, candidates['fixed16_nearest_div_mul'])
        self.assertEqual(direct['f2dot14'], 0)
        self.assertEqual(fixed['f2dot14'], 1)

    def test_original_affine_examples_and_all_default_endpoints(self):
        records = ((-16384, -16384), (-8192, -12288), (0, 0),
                   (8192, 4096), (16384, 16384))
        axis = Axis('wght', 10.0, 50.0, 90.0, records)
        for candidate in CANDIDATES:
            for value, expected in ((10, -16384), (30, -12288), (50, 0),
                                    (60, 2048), (70, 4096), (90, 16384)):
                self.assertEqual(predict(value, axis, candidate)['f2dot14'], expected)

    def test_duplicated_endpoints_and_zero_have_distinct_semantics(self):
        records = ((-16384, -16384), (-16384, -12288),
                   (0, -4096), (0, 0), (16384, 12288), (16384, 16384))
        before = deepcopy(records)
        self.assertEqual(ordered_map(-1, records), -0.75)
        self.assertEqual(ordered_map(1, records), 0.75)
        self.assertEqual(ordered_map(0, records), 0.0)
        epsilon = Fraction(1, 65536)
        self.assertEqual(ordered_map(float(-epsilon), records),
                         float(-Fraction(1, 4) - epsilon * Fraction(1, 2)))
        self.assertEqual(ordered_map(float(epsilon), records), float(epsilon * Fraction(3, 4)))
        self.assertEqual(records, before)

    def test_unordered_near_zero_record_is_not_sorted_or_deduplicated(self):
        records = ((-16384, -16384), (0, -4096), (-128, 0),
                   (0, 0), (16384, 16384))
        self.assertEqual(ordered_map(0, records), 0)
        # The first adjacent interval still contains this negative value.
        # Sorting would instead route through (-128, 0), changing the result.
        self.assertEqual(ordered_map(-1 / 256, records),
                         float(-Fraction(1, 4) - Fraction(1, 256) * Fraction(3, 4)))
        self.assertEqual(ordered_map(1 / 256, records), 1 / 256)

    def test_three_axis_tags_are_preserved_in_predictor(self):
        for tag in ('WDTH', 'wght', 'HGHT'):
            axis = Axis(tag, 10.0, 50.0, 90.0, IDENTITY)
            self.assertEqual(predict(70, axis, CANDIDATES[0])['f2dot14'], 8192)
            self.assertEqual(axis.tag, tag)

    def test_nonfinite_and_outside_source_values_are_not_silently_clamped(self):
        axis = Axis('wght', 10.0, 50.0, 90.0, IDENTITY)
        for value in (float('nan'), float('inf'), -float('inf'), 9.999, 90.001):
            with self.assertRaises(ValueError):
                predict(value, axis, CANDIDATES[0])
        for value in (float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                fixed16(value)


class QuantizationEvidenceTests(unittest.TestCase):
    axes = {0: {'wght': Axis('wght', 10.0, 50.0, 90.0, IDENTITY)}}

    def test_matching_hypotheses_stay_plural_and_do_not_claim_geometry(self):
        data = evidence([sample(10, -1), sample(50, 0), sample(70, 0.5), sample(90, 1)])
        before = deepcopy(data)
        result = analyze(data, self.axes)
        self.assertGreater(len(result['complete_metric_matches']), 1)
        self.assertEqual(result['observations_reanalyzed'], 4)
        self.assertEqual(result['new_native_requests'], 0)
        self.assertFalse(result['geometry_mapping_accepted'])
        self.assertFalse(result['font_generated'])
        self.assertTrue(result['candidate_selection_is_global'])
        self.assertEqual(data, before)

    def test_every_unexplained_row_is_preserved_without_tolerance_growth(self):
        data = evidence([sample(50, 1 / 16384)])
        result = analyze(data, self.axes)
        self.assertEqual(result['complete_metric_matches'], [])
        self.assertEqual(len(result['baseline_disagreements']), 1)
        self.assertEqual(len(result['unresolved_samples']), 1)
        self.assertEqual(result['unresolved_samples'][0]['observed_f2dot14'], 1)
        self.assertEqual(result['metric_tolerance_unchanged'], METRIC_LIMIT)
        for candidate in result['candidates']:
            self.assertEqual(candidate['failures'], 1)
            self.assertEqual(len(candidate['all_disagreements']), 1)

    def test_ambiguous_metric_inference_is_not_invented_as_zero(self):
        result = analyze(evidence([sample(50, None)]), self.axes)
        self.assertEqual(result['complete_metric_matches'], [])
        row = result['unresolved_samples'][0]
        self.assertIsNone(row['observed_f2dot14'])
        self.assertEqual(row['inference_problem'], 'unidentifiable_metric_coordinate')

    def test_off_grid_inference_is_retained_even_if_rounded_grid_matches(self):
        result = analyze(evidence([sample(50, 0.1 / 16384)]), self.axes)
        self.assertEqual(result['complete_metric_matches'], [])
        self.assertEqual(result['unresolved_samples'][0]['inference_problem'],
                         'inferred_coordinate_not_on_f2dot14_grid')

    def test_failed_original_metric_budget_cannot_pass_any_candidate(self):
        row = sample(50, 0)
        row['best_fit']['max_metric_residual'] = METRIC_LIMIT * 2
        row['within_unchanged_metric_budget'] = False
        result = analyze(evidence([row]), self.axes)
        self.assertEqual(result['complete_metric_matches'], [])
        self.assertEqual(result['unresolved_samples'][0]['inference_problem'],
                         'native_metric_inference_outside_budget')

    def test_face_and_observation_counts_must_agree(self):
        for mutate in (
                lambda value: value.update(native_requests=2),
                lambda value: value.update(physical_faces=2),
                lambda value: value['reports'][0].update(native_positions=2),
                lambda value: value['reports'][0].update(face_index=99)):
            data = evidence([sample(50, 0)])
            mutate(data)
            with self.assertRaises(ValueError):
                analyze(data, self.axes)

    def test_tampered_contract_and_nonfinite_data_fail(self):
        for key, value in (('metric_tolerance', 0.1), ('font_generated', True),
                           ('source_unchanged', False), ('production_axis_guard_changed', True)):
            data = evidence([sample(50, 0)])
            data[key] = value
            with self.assertRaises(ValueError):
                analyze(data, self.axes)
        for bad_value in (float('nan'), float('inf'), 91, True):
            with self.assertRaises(ValueError):
                analyze(evidence([sample(bad_value, 0)]), self.axes)


if __name__ == '__main__':
    unittest.main()
