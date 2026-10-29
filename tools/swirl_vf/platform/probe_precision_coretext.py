#!/usr/bin/env python3
"""Bounded real CoreText measurement of the saved self-authored P5 witness.

No Apple input, coordinate correction, application compensation or acceptance
override. Point-size output is converted back to the original source design
units, and raw axis echoes and metric failures remain in the report.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

from fontTools.ttLib import TTCollection, TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from continuous_model import evaluate_model
from font_model_certificate import advance_models, _point_models

SIZES = (12, 48, 1000, 5000)
Q = (Fraction(63, 16384), Fraction(3, 16), Fraction(0))
R = (Fraction(63, 16384), Fraction(1), Fraction(0))
AXES = {
    'reference': {'XWDT': float(Q[0]), 'XWGT': float(Q[1]), 'XHGT': 0.},
    'target': {'WDTH': 501.922607421875, 'wght': 900., 'HGHT': 500.},
}
FILENAMES = {'reference': 'normalized-scaled', 'target': 'precision'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_rows(rows, source_sha, sizes):
    require(not any(r.get('type') == 'error' for r in rows), 'native_diagnostic_rejected_request')
    measurements = [r for r in rows if r.get('type') == 'measurement']
    cleanup = [r for r in rows if r.get('type') == 'cleanup']
    require(len(rows) == len(sizes)+1 and len(measurements) == len(sizes)
            and len(cleanup) == 1 and cleanup[0].get('process_unregistered') is True
            and all(r.get('source_sha256') == source_sha for r in rows), 'native_transcript_or_cleanup_incomplete')
    require([r['point_size'] for r in measurements] == list(sizes), 'native_point_size_order_changed')
    require(all(r['face_index'] == 0 and r['glyph_id'] == 2 and r['physical_face_verified'] is True
                and r['horizontal_layout']['physical_run_face_verified'] is True
                and r['vertical_layout']['physical_run_face_verified'] is True for r in measurements),
            'native_face_or_actual_run_identity_failed')
    return measurements


def source_units(record, grid_multiplier=5):
    source_upem = record['font_upem']/grid_multiplier
    multiplier = source_upem/record['point_size']
    commands = [[row[0], *(float(v)*multiplier for v in row[1:])] for row in record['commands']]
    return {'horizontal_advance': record['horizontal_vector'][0]*multiplier,
            'vertical_advance': record['vertical_vector'][0]*multiplier,
            'vertical_origin': [-v*multiplier for v in record['vertical_translation']],
            'font_baseline_metrics': [record[k]*multiplier for k in ('font_ascent', 'font_descent', 'font_leading')],
            'commands': commands,
            'horizontal_line_position': [v*multiplier for v in record['horizontal_layout']['position']],
            'vertical_line_position': [v*multiplier for v in record['vertical_layout']['position']],
            'source_upem': source_upem}


def outline_error(a, b):
    require([(r[0], len(r)) for r in a] == [(r[0], len(r)) for r in b], 'native_path_topology_changed')
    return max((math.hypot(x[i]-y[i], x[i+1]-y[i+1])
                for x, y in zip(a, b) for i in range(1, len(x), 2)), default=0.)


def model_values(font, coordinates, grid_multiplier=5):
    name = font.getGlyphOrder()[2]
    metrics = advance_models(font)
    _, points = _point_models(font, name)
    count = len(font['glyf'][name].getCoordinates(font['glyf'])[0])
    values = {kind: evaluate_model(metrics[kind, name], coordinates)[0]/grid_multiplier for kind in ('HVAR', 'VVAR')}
    return {'advance_source_units_exact': {k: [v.numerator, v.denominator] for k, v in values.items()},
            'advance_source_units': {k: float(v) for k, v in values.items()},
            'outline_points_source_units': [[float(v/grid_multiplier) for v in evaluate_model(p, coordinates)] for p in points[:count]]}


def run(controls, output):
    controls, output = Path(controls).resolve(), Path(output).resolve()
    require(not output.exists() and not output.is_symlink(), 'fresh_native_output_required')
    saved = json.loads((controls/'summary.json').read_text())
    require(saved['font_kind'] == 'self_authored_32_faces_7_GIDs_only'
            and saved['selected_multiplier'] == 5 and saved['production_accepted'] is False,
            'only_saved_authored_P5_controls_allowed')
    paths = {k: controls/f'{name}.ttc' for k, name in FILENAMES.items()}
    models = {}
    for kind, path in paths.items():
        require(digest(path) == saved['packing'][FILENAMES[kind]]['sha256'], 'authored_control_hash_changed')
        with TTCollection(path, lazy=True) as collection:
            require(len(collection.fonts) == 32 and len(collection.fonts[0].getGlyphOrder()) == 7,
                    'authored_control_shape_changed')
            models[kind] = model_values(collection.fonts[0], Q if kind == 'reference' else R)
    return _measure_pair(paths, output, models, 5, AXES, Q, R, 'saved_P5_bounded_fivefold')


def run_pair(reference, target, output, *, grid_multiplier=16, axes=AXES, q=Q, r=R, case_name='exact16_original_witness'):
    """Measure explicitly supplied authored seven-GID TTFs or one-face TTCs."""
    require(type(grid_multiplier) is int and grid_multiplier > 0, 'positive_grid_multiplier_required')
    output = Path(output).resolve()
    require(not output.exists() and not output.is_symlink(), 'fresh_native_output_required')
    paths = {'reference': Path(reference).resolve(), 'target': Path(target).resolve()}
    models = {}
    for kind, path in paths.items():
        with TTFont(path, fontNumber=0) as font:
            require(font.getGlyphOrder() == ['.notdef','space','A','regional','regional.alt','unencoded','curve'],
                    'authored_seven_GID_fixture_required')
            require(font['head'].unitsPerEm == 1000*grid_multiplier,
                    'authored_pair_requires_1000_source_UPEM_times_grid')
            require(tuple(a.axisTag for a in font['fvar'].axes) ==
                    (('XWDT','XWGT','XHGT') if kind == 'reference' else ('WDTH','wght','HGHT')),
                    'authored_pair_axis_order_differs')
            models[kind] = model_values(font, q if kind == 'reference' else r, grid_multiplier)
    return _measure_pair(paths, output, models, grid_multiplier, axes, q, r, case_name)


def _measure_pair(paths, output, models, grid_multiplier, axis_values, q, r, case_name):
    initial_hashes = {kind: digest(path) for kind, path in paths.items()}
    output.mkdir(parents=True, mode=0o700)
    binary = output/'precision_coretext'
    command = ['xcrun', 'swiftc', '-O', str(ROOT/'platform/precision_coretext.swift'), '-o', str(binary)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=180)
    (output/'compile.log').write_text(compiled.stdout+compiled.stderr)
    require(compiled.returncode == 0, 'native_probe_compilation_failed')
    measurements = {}
    for order, sizes in (('forward', SIZES), ('reverse', tuple(reversed(SIZES)))):
        for kind, path in paths.items():
            command = [str(binary), str(path), '0', ','.join(map(str, sizes)),
                       *(f'{tag}={value!r}' for tag, value in axis_values[kind].items())]
            native = subprocess.run(command, capture_output=True, text=True, timeout=120)
            (output/f'{kind}-{order}.jsonl').write_text(native.stdout)
            (output/f'{kind}-{order}.stderr').write_text(native.stderr)
            rows = [json.loads(line) for line in native.stdout.splitlines() if line]
            require(native.returncode == 0, 'native_probe_failed_see_preserved_synthetic_transcript')
            measurements[kind, order] = validate_rows(rows, digest(path), sizes)
    # Retain exact process-order replay as an independent channel, not a retry.
    for kind in paths:
        require(measurements[kind, 'forward'] == list(reversed(measurements[kind, 'reverse'])),
                'native_reverse_order_replay_differed')
    comparisons = []
    for reference, target in zip(measurements['reference', 'forward'], measurements['target', 'forward']):
        a, b = source_units(reference, grid_multiplier), source_units(target, grid_multiplier)
        require(reference['point_size'] == target['point_size'], 'native_pair_point_size_differs')
        comparisons.append({'point_size': reference['point_size'], 'reference': a, 'target': b,
            'horizontal_advance_difference': b['horizontal_advance']-a['horizontal_advance'],
            'vertical_advance_difference': b['vertical_advance']-a['vertical_advance'],
            'maximum_outline_point_distance': outline_error(a['commands'], b['commands']),
            'baseline_metric_differences': [y-x for x, y in zip(a['font_baseline_metrics'], b['font_baseline_metrics'])],
            'axis_echo_errors': {kind: {tag: record['reported_axes'].get(tag, record['default_axes'][tag])-value
                for tag, value in axis_values[kind].items()} for kind, record in [('reference',reference),('target',target)]},
            'actual_line_GIDs': {kind: {key: record[key]['gid'] for key in ('horizontal_layout','vertical_layout')}
                                 for kind, record in [('reference',reference),('target',target)]}})
    summary = {'status': 'COMPLETED_AUTHORED_CORETEXT_WITNESS_NOT_ACCEPTANCE',
        'data_origin': 'self_authored_P5_P6_controls_no_Apple_data', 'case_name': case_name,
        'face_index': 0, 'direct_gid': 2, 'grid_multiplier': grid_multiplier,
        'supplied_design_reference_q': [float(v) for v in q],
        'supplied_design_reference_r': [float(v) for v in r],
        'models_scope': 'supplied_coordinates_not_observed_native_post_avar',
        'actual_native_post_avar_coordinates': 'NOT_OBSERVED',
        'requested_user_axes': axis_values, 'point_sizes': list(SIZES), 'native_records': 16,
        'exact_reverse_pairs': 8, 'raw_native_font_and_run_identity_verified': True,
        'os_version': measurements['reference','forward'][0]['os_version'],
        'models_at_supplied_coordinates': models, 'comparisons_source_font_units': comparisons,
        'maximum_native_advance_error': max(abs(r['horizontal_advance_difference']) for r in comparisons),
        'maximum_native_outline_error': max(r['maximum_outline_point_distance'] for r in comparisons),
        'strict_limit_source_font_units': 1/32,
        'original_font': 'NOT_RUN', 'Windows11': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN',
        'application_compensation': False, 'production_accepted': False,
        'source_hashes_unchanged': {k: digest(p) == initial_hashes[k] for k,p in paths.items()},
        'source_hashes': initial_hashes,
        'native_binary_sha256': digest(binary), 'native_source_sha256': digest(ROOT/'platform/precision_coretext.swift')}
    (output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--controls', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.controls, args.output)
    print(json.dumps({k: summary[k] for k in ('status','native_records','maximum_native_advance_error','maximum_native_outline_error')}))
