#!/usr/bin/env python3
"""Recheck native HVAR-inferred coordinates without changing the font oracle.

This consumes calibrate_avar_metrics.py's existing *safe summary*, not glyph
outlines. A matching hypothesis is evidence about those metric observations;
it is not independent CoreText execution or acceptance of HVF geometry.

The candidates are independently implemented from these primary references:
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview
https://github.com/freetype/freetype/blob/master/src/truetype/ttgxvar.c
https://skia.googlesource.com/skia/+/709209322f9597b6712079a4386f4d1c7e9b5d44/tests/TypefaceMacTest.cpp
Raw avar records deliberately retain their order and duplicates. In particular
fontTools' dictionary representation must not be used to round-trip this data.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from audit_font import raw_avar

EXPECTED_SOURCE = '39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'
METRIC_LIMIT = 1 / 32
# Error in an already inferred normalized coordinate, expressed in grid units.
# This is only a binary64 reconstruction check, not a glyph/metric tolerance.
INFERENCE_GRID_EPSILON = 1e-8


@dataclass(frozen=True)
class Axis:
    tag: str
    minimum: float
    default: float
    maximum: float
    records: tuple[tuple[int, int], ...]

    def __post_init__(self):
        if (not all(math.isfinite(v) for v in (self.minimum, self.default, self.maximum))
                or not self.minimum <= self.default <= self.maximum
                or self.minimum == self.maximum):
            raise ValueError('invalid_axis_range')
        if not self.records or any(
                len(pair) != 2 or any(type(x) is not int or not -16384 <= x <= 16384 for x in pair)
                for pair in self.records):
            raise ValueError('invalid_raw_avar_records')


@dataclass(frozen=True)
class Candidate:
    name: str
    input: str = 'double'
    normalization: str = 'double'
    mapping: str = 'double'


# Each candidate applies one global rule to every row. There is no per-face or
# per-coordinate choice of whichever hypothesis happens to match an observation.
CANDIDATES = (
    Candidate('double_then_f2dot14'),
    Candidate('float32_user_then_double', input='float32'),
    Candidate('float32_each_operation', input='float32', normalization='float32', mapping='float32'),
    Candidate('readback_4dp_then_double', input='decimal4'),
    Candidate('readback_7sig_then_double', input='decimal7'),
    Candidate('fixed16_nearest_div_mul', input='fixed16', normalization='fixed16_nearest', mapping='fixed16_nearest'),
    Candidate('fixed16_truncate_div_mul', input='fixed16', normalization='fixed16_truncate', mapping='fixed16_truncate'),
    Candidate('float32_user_then_fixed16', input='float32_fixed16', normalization='fixed16_nearest', mapping='fixed16_nearest'),
    Candidate('readback_4dp_then_fixed16', input='decimal4_fixed16', normalization='fixed16_nearest', mapping='fixed16_nearest'),
    Candidate('readback_7sig_then_fixed16', input='decimal7_fixed16', normalization='fixed16_nearest', mapping='fixed16_nearest'),
    Candidate('normalized16_truncate_then_double_map', normalization='normalized16_truncate'),
    Candidate('normalized16_nearest_then_double_map', normalization='normalized16_nearest'),
    Candidate('float32_normalized16_truncate', input='float32', normalization='float32_normalized16_truncate'),
    Candidate('mapped16_truncate_then_f2dot14', mapping='mapped16_truncate'),
)


def float32(value: float) -> float:
    return struct.unpack('!f', struct.pack('!f', value))[0]


def fixed16(value: float) -> int:
    """Float-to-16.16 conversion with ties toward positive infinity."""
    if not math.isfinite(value):
        raise ValueError('nonfinite_fixed_input')
    return math.floor(value * 65536 + 0.5)


def divide_integer(numerator: int, denominator: int, nearest: bool) -> int:
    """Signed integer division: truncate or nearest with ties away from zero."""
    if denominator == 0:
        raise ValueError('zero_fixed_denominator')
    negative = (numerator < 0) != (denominator < 0)
    dividend, divisor = abs(numerator), abs(denominator)
    quotient, remainder = divmod(dividend, divisor)
    if nearest and remainder * 2 >= divisor:
        quotient += 1
    return -quotient if negative else quotient


def normalize(value: float, axis: Axis) -> float:
    if value == axis.default:
        return 0.0
    span = axis.default - axis.minimum if value < axis.default else axis.maximum - axis.default
    return (value - axis.default) / span


def ordered_map(value: float, records: tuple[tuple[int, int], ...], mode: str = 'double') -> float:
    """Evaluate raw adjacent intervals, preserving the explicit zero fast path.

    This is the existing metric-matching record-order hypothesis, not a claim
    that malformed avar has one portable standardized interpretation.
    """
    if value == 0:
        return 0.0
    pairs = tuple((x / 16384, y / 16384) for x, y in records)
    if value < pairs[0][0]:
        return pairs[0][1]
    for (start, low), (end, high) in zip(pairs, pairs[1:]):
        if value <= end:
            if start == end:
                return high
            if mode in ('fixed16_nearest', 'fixed16_truncate'):
                # All endpoint numbers are exact 16.16 values. Interpolation
                # uses one signed integer multiply/divide, independently of
                # Python's floating point division and banker's rounding.
                position = fixed16(value)
                delta = divide_integer(
                    (position - fixed16(start)) * (fixed16(high) - fixed16(low)),
                    fixed16(end) - fixed16(start), mode == 'fixed16_nearest')
                return (fixed16(low) + delta) / 65536
            if mode == 'float32':
                delta = float32(float32(high - low) * float32(value - start))
                return float32(low + float32(delta / float32(end - start)))
            result = low + (value - start) * (high - low) / (end - start)
            if mode == 'mapped16_truncate':
                result = math.trunc(result * 65536) / 65536
            return result
    return pairs[-1][1]


def predict(value: float, axis: Axis, candidate: Candidate) -> dict:
    """Return each stage as numbers so a native geometry probe can audit it."""
    if not math.isfinite(value) or not axis.minimum <= value <= axis.maximum:
        raise ValueError('axis_value_outside_source_range')
    applied = value
    if candidate.input.startswith('float32'):
        applied = float32(applied)
    elif candidate.input.startswith('decimal4'):
        applied = float(format(applied, '.4f'))
    elif candidate.input.startswith('decimal7'):
        applied = float(format(applied, '.7g'))
    if candidate.input.endswith('fixed16'):
        applied = fixed16(applied) / 65536
    applied = min(axis.maximum, max(axis.minimum, applied))
    mode = candidate.normalization
    if mode in ('fixed16_nearest', 'fixed16_truncate'):
        position, default = fixed16(applied), fixed16(axis.default)
        span = default - fixed16(axis.minimum) if position < default else fixed16(axis.maximum) - default
        n16 = 0 if position == default else divide_integer(
            (position - default) * 65536, span, mode == 'fixed16_nearest')
        normalized = n16 / 65536
    elif mode in ('float32', 'float32_normalized16_truncate'):
        difference = float32(applied - float32(axis.default))
        span = float32(axis.default - axis.minimum if applied < axis.default else axis.maximum - axis.default)
        normalized = 0.0 if difference == 0 else float32(difference / span)
        if mode == 'float32_normalized16_truncate':
            normalized = math.trunc(normalized * 65536) / 65536
    else:
        normalized = normalize(applied, axis)
        if mode == 'normalized16_truncate':
            normalized = math.trunc(normalized * 65536) / 65536
        elif mode == 'normalized16_nearest':
            normalized = fixed16(normalized) / 65536
    normalized = min(1.0, max(-1.0, normalized))
    mapped = ordered_map(normalized, axis.records, candidate.mapping)
    mapped = min(1.0, max(-1.0, mapped))
    # A value already expressed in 16.16 follows the specified signed +2 >> 2.
    if candidate.mapping in ('fixed16_nearest', 'fixed16_truncate', 'mapped16_truncate'):
        quantized = (fixed16(mapped) + 2) >> 2
    else:
        quantized = math.floor(mapped * 16384 + 0.5)
    return {'effective_user_value': applied, 'normalized_before_avar': normalized,
            'mapped_before_final_quantization': mapped, 'f2dot14': quantized,
            'final_normalized': quantized / 16384}


def analyze(summary: dict, axes_by_face: dict[int, dict[str, Axis]]) -> dict:
    """Compare every existing observation and retain every model disagreement."""
    if (summary.get('status') != 'NATIVE_HVAR_MAPPING_DIAGNOSIS_NOT_FONT_ACCEPTANCE'
            or summary.get('source_unchanged') is not True
            or summary.get('original_records_modified') is not False
            or summary.get('production_axis_guard_changed') is not False
            or summary.get('font_generated') is not False
            or summary.get('metric_tolerance') != METRIC_LIMIT):
        raise ValueError('unexpected_native_summary_contract')
    reports = summary.get('reports', [])
    if summary.get('physical_faces') != len(axes_by_face) or len(reports) != len(axes_by_face):
        raise ValueError('physical_face_count_mismatch')
    observations = []
    seen_faces = set()
    for face_report in reports:
        index = face_report['face_index']
        if type(index) is not int or index not in axes_by_face or index in seen_faces:
            raise ValueError('duplicate_or_unknown_face')
        seen_faces.add(index)
        axes = axes_by_face[index]
        rows = face_report['metric_inferred_locations']
        if len(rows) != face_report['native_positions']:
            raise ValueError('face_position_count_mismatch')
        for ordinal, row in enumerate(rows):
            location = row['user_location']
            if set(location) != set(axes) or any(
                    isinstance(location[tag], bool) or not isinstance(location[tag], (int, float))
                    or not math.isfinite(location[tag])
                    or not axis.minimum <= location[tag] <= axis.maximum
                    for tag, axis in axes.items()):
                raise ValueError('invalid_observed_user_location')
            if row.get('geometry_mapping_accepted') is not False:
                raise ValueError('summary_must_not_claim_geometry_acceptance')
            best = row['best_fit']
            residual = best['max_metric_residual']
            if not math.isfinite(residual) or residual < 0:
                raise ValueError('invalid_metric_residual')
            observed = best['normalized_weight']
            problem = None
            grid = None
            if row.get('within_unchanged_metric_budget') is not True or residual > METRIC_LIMIT:
                problem = 'native_metric_inference_outside_budget'
            elif observed is None:
                problem = 'unidentifiable_metric_coordinate'
            elif not math.isfinite(observed) or not -1 <= observed <= 1:
                raise ValueError('invalid_inferred_normalized_coordinate')
            else:
                grid = math.floor(observed * 16384 + 0.5)
                if abs(observed * 16384 - grid) > INFERENCE_GRID_EPSILON:
                    problem = 'inferred_coordinate_not_on_f2dot14_grid'
            observations.append({'face_index': index, 'position_index': ordinal,
                                 'user_location': dict(location), 'observed_normalized': observed,
                                 'observed_f2dot14': grid, 'inference_problem': problem,
                                 'maximum_metric_inference_residual': residual})
    if len(observations) != summary.get('native_requests'):
        raise ValueError('total_native_position_count_mismatch')
    if not observations:
        raise ValueError('empty_native_observations')
    results = []
    baseline_failed = set()
    for candidate in CANDIDATES:
        failures = []
        failed_indices = set()
        by_face = {index: {'observations': 0, 'matches': 0, 'failures': 0} for index in axes_by_face}
        maximum = 0
        for index, observation in enumerate(observations):
            face = observation['face_index']
            axis = axes_by_face[face]['wght']
            stages = predict(observation['user_location']['wght'], axis, candidate)
            delta = None if observation['observed_f2dot14'] is None else stages['f2dot14'] - observation['observed_f2dot14']
            by_face[face]['observations'] += 1
            if observation['inference_problem'] is not None or delta != 0:
                failed_indices.add(index)
                by_face[face]['failures'] += 1
                failures.append({**observation, 'prediction': stages, 'signed_grid_difference': delta})
            else:
                by_face[face]['matches'] += 1
            if delta is not None:
                maximum = max(maximum, abs(delta))
        if not results:
            baseline_failed = failed_indices
        results.append({'candidate': candidate.name, 'input_policy': candidate.input,
                        'normalization_policy': candidate.normalization, 'mapping_policy': candidate.mapping,
                        'observations': len(observations), 'matches': len(observations) - len(failures),
                        'failures': len(failures), 'maximum_error_f2dot14_units': maximum,
                        'explains_baseline_disagreements': len(baseline_failed - failed_indices),
                        'new_disagreements_against_baseline': len(failed_indices - baseline_failed),
                        'faces': [{'face_index': face, **data} for face, data in by_face.items()],
                        'all_disagreements': failures})
    ranked = sorted(results, key=lambda result: (result['failures'], result['maximum_error_f2dot14_units'], result['candidate']))
    return {'status': 'QUANTIZATION_HYPOTHESES_NOT_GEOMETRY_ACCEPTANCE',
            'source_sha256': summary.get('source_sha256'), 'physical_faces': len(axes_by_face),
            'observations_reanalyzed': len(observations), 'new_native_requests': 0,
            'metric_tolerance_unchanged': METRIC_LIMIT, 'inference_grid_epsilon': INFERENCE_GRID_EPSILON,
            'production_oracle_changed': False, 'raw_avar_records_modified': False,
            'geometry_mapping_accepted': False, 'font_generated': False,
            'candidate_selection_is_global': True,
            'baseline_candidate': CANDIDATES[0].name, 'baseline_disagreements': results[0]['all_disagreements'],
            'best_candidate': ranked[0]['candidate'], 'best_candidate_disagreements': ranked[0]['failures'],
            'complete_metric_matches': [result['candidate'] for result in results if result['failures'] == 0],
            'unresolved_samples': ranked[0]['all_disagreements'], 'candidates': results}


def load_source_axes(source: Path) -> dict[int, dict[str, Axis]]:
    if hashlib.sha256(source.read_bytes()).hexdigest() != EXPECTED_SOURCE:
        raise ValueError('exact_original_source_required')
    result = {}
    with TTCollection(source, lazy=True) as collection:
        if len(collection.fonts) != 32:
            raise ValueError('all_32_physical_faces_required')
        for index, font in enumerate(collection.fonts):
            axes = font['fvar'].axes
            tags = [axis.axisTag for axis in axes]
            if tags != ['WDTH', 'wght', 'HGHT'] or font['maxp'].numGlyphs != 47102:
                raise ValueError('source_axes_or_glyph_count_changed')
            raw = raw_avar(font.reader['avar'], tags)
            result[index] = {
                axis.axisTag: Axis(axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue,
                                   tuple((record['from_f2dot14'], record['to_f2dot14'])
                                         for record in raw_axis['records']))
                for axis, raw_axis in zip(axes, raw['axes'])}
    return result


def run(source: Path, summary_path: Path, output: Path) -> dict:
    if output.exists() or output.resolve() in (source.resolve(), summary_path.resolve()):
        raise ValueError('fresh_report_path_required')
    data = summary_path.read_bytes()
    summary = json.loads(data)
    if summary.get('source_sha256') != EXPECTED_SOURCE:
        raise ValueError('native_summary_source_sha256_mismatch')
    result = analyze(summary, load_source_axes(source))
    result['input_summary_sha256'] = hashlib.sha256(data).hexdigest()
    result['analysis_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if hashlib.sha256(source.read_bytes()).hexdigest() != EXPECTED_SOURCE:
        raise ValueError('original_source_changed_during_analysis')
    result['source_unchanged'] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({key: result[key] for key in (
        'status', 'physical_faces', 'observations_reanalyzed', 'new_native_requests',
        'best_candidate', 'best_candidate_disagreements', 'complete_metric_matches')}, allow_nan=False))
    for candidate in result['candidates']:
        print(json.dumps({key: candidate[key] for key in (
            'candidate', 'matches', 'failures', 'maximum_error_f2dot14_units',
            'explains_baseline_disagreements', 'new_disagreements_against_baseline')}))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--native-summary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.native_summary, args.output)
