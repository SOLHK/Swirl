#!/usr/bin/env python3
"""Complete synthetic reconstruction with native paths and explicit table metrics.

The old strict CoreText API gate is executed and reported separately, unchanged.
Its failures are retained. This gate checks the converter's correctly sourced
metrics, all native outlines, the complete two-face/three-GID reconstruction,
serialized model/TTC integrity and an independent native reread. It never reads
Apple fonts and never treats table-derived values as raw native measurements.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import tempfile

from fontTools.ttLib import TTCollection

from diagnose_coretext_metrics import ideal_metrics, make_static_fixture, static_table_metrics
from test_coretext_extract import make_fixture, native_requests, normalized, validate_results
from test_native_reconstruction import (check_collection, check_rebuild_report,
    canonical_commands, compare_native, native_records, recorded_run)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from source_metrics import SourceMetrics
from table_metric_oracle import (FIELDS, RAW_FIELDS, adapt_record, adapted_metadata,
                                 identity_design_coordinates, source_hash)
from verified_axis_oracle import make_launcher as make_verified_axis_launcher


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def analytic_commands(location, gid):
    """The original fixture geometry, independently of either metric reader."""
    if gid == 1:
        return []
    if gid == 0:
        return [['moveTo', 50, 0], ['lineTo', 500, 0], ['lineTo', 500, 700],
                ['lineTo', 50, 700], ['closePath']]
    require(gid == 2, 'unknown original synthetic glyph')
    x = normalized(location['WDTH'], 1, 500, 1000)
    w = normalized(location['wght'], 100, 400, 900)
    y = normalized(location['HGHT'], 1, 500, 1000)
    cross = max(0, x) * max(0, y)
    left, right, control = 100+20*x, 400+80*x+60*w+20*cross, 500+100*x+60*w+20*cross
    return [['moveTo', left, 0], ['lineTo', right, 0],
            ['qCurveTo', control, 300+90*y, right, 600+180*y],
            ['lineTo', left, 600+180*y], ['closePath']]


def adapt_records(source, rows):
    digest = source_hash(source)
    result = []
    with TTCollection(source, lazy=True) as collection:
        providers = [SourceMetrics(font) for font in collection.fonts]
        require(rows and rows[0].get('type') == 'metadata', 'native metadata missing')
        result.append(adapted_metadata(rows[0], digest, collection.fonts))
        for row in rows[1:]:
            if 'glyph_id' not in row:
                result.append(dict(row))
                continue
            face = row['face_index']
            coordinates = identity_design_coordinates(collection.fonts[face], row['location'])
            result.append(adapt_record(providers[face], row, coordinates, {
                'policy': 'standard_verified_identity_avar_unrounded_design_coordinates',
                'source_sha256': digest, 'face_index': face}))
    return result


def check_adapted_records(raw_rows, converted_rows, requests, *, analytical=True, limit=1/32):
    raw_glyph_rows = [row for row in raw_rows if 'glyph_id' in row]
    raw = {(row['request_id'], row['glyph_id']): row for row in raw_glyph_rows}
    expected = {(r['request_id'], gid): r for r in requests for gid in r['glyph_ids']}
    rows = [row for row in converted_rows if 'glyph_id' in row]
    require(set(raw) == set(expected) and len(raw_glyph_rows) == len(rows) == len(expected),
            'raw/adapted glyph count differs')
    maximum = {}
    raw_maximum = {}
    seen = set()
    for row in rows:
        key = (row['request_id'], row['glyph_id'])
        require(key in expected and key not in seen, 'duplicate or unrelated adapted glyph')
        seen.add(key)
        original, request = raw[key], expected[key]
        require(row['face_index'] == request['face_index'] and row['location'] == request['location'],
                'adapted source identity or requested axes changed')
        for field in ('commands', 'bounds', 'lsb', 'location', 'reported_location'):
            require(row[field] == original[field], f'adapter changed native {field}')
        for field in RAW_FIELDS:
            if field in original:
                require(row['raw_coretext_metrics'][field] == original[field], f'raw {field} was altered')
        require(row.get('metric_backend') == 'SourceTables'
                and row.get('source_metric_provenance', {}).get('native_API_values_replaced_in_evidence') is False,
                'table/native metric provenance missing')
        for field in FIELDS:
            difference = original[field] - row[field]
            require(row['raw_coretext_metric_error_font_units'][field] == difference,
                    f'raw {field} discrepancy concealed')
            raw_maximum[field] = max(raw_maximum.get(field, 0.), abs(difference))
        if analytical:
            wanted = ideal_metrics(request['location'], row['glyph_id'])
            bounds = row['bounds']
            actual = {**row, 'x_min': bounds[0], 'y_min': bounds[1],
                      'x_max': bounds[0]+bounds[2], 'y_max': bounds[1]+bounds[3]}
            for field, value in wanted.items():
                error = abs(actual[field] - value)
                require(math.isfinite(error) and error <= limit,
                        f'{key} analytic {field} error {error} exceeds unchanged {limit}')
                maximum[field] = max(maximum.get(field, 0.), error)
            commands = canonical_commands(row['commands'])
            wanted_commands = analytic_commands(request['location'], row['glyph_id'])
            require([(c[0], len(c)) for c in commands] == [(c[0], len(c)) for c in wanted_commands],
                    f'{key} native analytic contour topology differs')
            for actual, wanted in zip(commands, wanted_commands):
                for i in range(1, len(actual), 2):
                    error = math.hypot(actual[i]-wanted[i], actual[i+1]-wanted[i+1])
                    require(math.isfinite(error) and error <= limit,
                            f'{key} native analytic control-point error {error} exceeds {limit}')
                    maximum['native_control_point'] = max(maximum.get('native_control_point', 0.), error)
    return {'status': 'PASS_TABLE_METRICS_AND_UNCHANGED_NATIVE_PATHS',
            'glyph_records': len(rows), 'metric_reference': 'original_source_tables',
            'maximum_analytic_error_by_field': maximum,
            'maximum_retained_raw_API_error_by_field': raw_maximum,
            'analytic_limit_font_units': limit if analytical else None,
            'raw_CoreText_API_gate_passed_by_this_check': False}


def make_launcher(path, binary):
    """Bind all adapter dependencies so a face-checkpoint cannot reuse old code."""
    files = [ROOT / 'tools' / name for name in
             ('table_metric_oracle.py', 'source_metrics.py', 'audit_font.py', 'incremental_pipe.py')]
    files.append(Path(binary).resolve())
    bindings = {str(p): source_hash(p) for p in files}
    command = [sys.executable, str(files[0]), '--native', str(binary), '--standard-identity']
    code = ('#!/usr/bin/env python3\nimport hashlib, os, pathlib, sys\n'
            f'bindings = {bindings!r}\n'
            'for filename, wanted in bindings.items():\n'
            '    if hashlib.sha256(pathlib.Path(filename).read_bytes()).hexdigest() != wanted:\n'
            '        raise SystemExit("bound_table_metric_adapter_code_changed")\n'
            f'os.execv({sys.executable!r}, {command!r} + sys.argv[1:])\n')
    path.write_text(code, encoding='utf-8')
    path.chmod(0o700)
    return bindings


def run(output, binary=None, require_native=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / 'native_table_metric_reconstruction.json'
    require(not report_path.exists(), 'choose a new evidence output directory')
    report = {'status': 'NOT_RUN', 'platform': platform.platform(), 'schema_version': 1,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'data_origin': 'self_authored_two_face_three_GID_fixture_no_Apple_data',
              'original_strict_native_API_gate_modified': False,
              'native_original_font_acceptance': 'NOT_RUN', 'windows_acceptance': 'NOT_RUN',
              'font_artifact_retained': False, 'commands': []}
    code = 1
    try:
        if sys.platform != 'darwin':
            report['reason'] = 'CoreText is unavailable; no native reconstruction was executed.'
            code = 2 if require_native else 0
        else:
            binary = Path(binary).resolve() if binary else output / 'coretext_extract'
            if not binary.exists():
                built = recorded_run(['xcrun', 'swiftc', '-O', str(ROOT / 'platform/coretext_extract.swift'),
                                      '-o', str(binary)], output, 'compile-coretext', report['commands'], timeout=180)
                require(built.returncode == 0, 'production CoreText extractor failed to compile')
            report['native_binary_sha256'] = source_hash(binary)
            with tempfile.TemporaryDirectory(prefix='native-table-metrics-', dir=output) as temporary:
                temp = Path(temporary)
                source, candidate = temp / 'original-fixture.ttc', temp / 'Swirl-VF.ttc'
                make_fixture(source)
                source_digest = source_hash(source)
                report['source_sha256'] = source_digest
                requests = native_requests()
                raw = native_records(binary, source, requests, output, 'original-raw', report['commands'])
                try:
                    old_result = validate_results(raw, requests, source_digest)
                    report['old_strict_native_API_gate'] = {'status': 'PASS', 'result': old_result}
                except Exception as error:
                    report['old_strict_native_API_gate'] = {'status': 'FAIL', 'error': str(error),
                        'failure_context': getattr(error, 'details', None), 'original_tolerance_font_units': 1/32}
                converted = adapt_records(source, raw)
                report['original_table_metric_and_native_outline_gate'] = check_adapted_records(raw, converted, requests)
                (output / 'original-adapted.jsonl').write_text(
                    ''.join(json.dumps(r, allow_nan=False) + '\n' for r in converted), encoding='utf-8')

                report['static_instances'] = []
                for label, location in [('default', {'WDTH': 500., 'wght': 400., 'HGHT': 500.}),
                                        ('fractional', {'WDTH': 631.25, 'wght': 523.75, 'HGHT': 711.125})]:
                    static = temp / f'static-{label}.ttc'
                    make_static_fixture(source, static, location)
                    static_requests = [{'request_id': f'{label}-{face}', 'face_index': face,
                                        'location': {}, 'glyph_ids': [0, 1, 2]} for face in range(2)]
                    static_raw = native_records(binary, static, static_requests, output, 'static-'+label, report['commands'])
                    static_adapted = adapt_records(static, static_raw)
                    checked = check_adapted_records(static_raw, static_adapted, static_requests, analytical=False)
                    with TTCollection(static) as collection:
                        for row in static_adapted:
                            if 'glyph_id' not in row:
                                continue
                            expected = static_table_metrics(collection.fonts[row['face_index']], row['glyph_id'])
                            for field in FIELDS:
                                require(row[field] == expected[field], f'static serialized {field} changed')
                    report['static_instances'].append({'case': label, 'source_sha256': source_hash(static), **checked})

                launcher = temp / 'table-metric-oracle'
                axis_launcher = make_verified_axis_launcher(temp / 'verified-axis-oracle', binary)
                report['verified_axis_launcher_sha256'] = source_hash(axis_launcher)
                report['axis_acceptance'] = 'every_requested_GID_exact_native_replay_before_batch_release'
                report['adapter_dependency_sha256'] = make_launcher(launcher, axis_launcher)
                build_report = output / 'table-reconstruction-report.json'
                result = recorded_run([sys.executable, str(ROOT / 'tools/rebuild.py'), str(source),
                                       '--oracle', str(launcher), '--output', str(candidate),
                                       '--report', str(build_report), '--batch-size', '2'],
                                      output, 'table-reconstruction', report['commands'], timeout=600)
                if build_report.exists():
                    report['reconstruction_report'] = json.loads(build_report.read_text(encoding='utf-8'))
                require(result.returncode == 0 and candidate.is_file(), 'complete native/table reconstruction failed; retained its exact report')
                candidate_digest = source_hash(candidate)
                check_rebuild_report(report['reconstruction_report'], source_digest, candidate_digest)
                report['collection_structure'] = check_collection(source, candidate)
                target_raw = native_records(binary, candidate, requests, output, 'candidate-raw', report['commands'])
                target = adapt_records(candidate, target_raw)
                report['candidate_provenance_gate'] = check_adapted_records(target_raw, target, requests,
                                                                         analytical=True, limit=1.)
                report['independent_native_outline_and_table_metric_comparison'] = compare_native(converted, target, requests)
                report['candidate_sha256'] = candidate_digest
                report['candidate_bytes'] = candidate.stat().st_size
                require(source_hash(source) == source_digest, 'original source bytes changed')
                report['source_unchanged'] = True
                report['status'] = 'PASS_SYNTHETIC_NATIVE_OUTLINE_TABLE_METRIC_RECONSTRUCTION_ONLY'
            report['temporary_fonts_removed'] = True
            code = 0
    except Exception as error:
        report['status'] = 'FAILED'
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        report['ended_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(report_path)}))
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--require-native', action='store_true')
    args = parser.parse_args()
    raise SystemExit(run(args.output, args.binary, args.require_native))
