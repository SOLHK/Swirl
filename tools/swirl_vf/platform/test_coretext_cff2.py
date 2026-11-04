#!/usr/bin/env python3
"""Native CFF2 architecture gate against the unchanged 1/32 source-unit limit.

All fonts are authored controls generated here. Geometry, axes, empty paths
and raw metrics have separate results. Any mismatch fails the gate and remains
in the report. A successful control would still not accept the original font.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import fontTools
from fontTools.ttLib import TTCollection
import uharfbuzz as hb

from make_cff2_fixture import write_fixture, records
from test_coretext_extract import make_fixture, native_requests
from diagnose_coretext_metrics import ideal_metrics, normalized_location
from check_coretext_cff2_empty import run as run_empty_proof

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rebuild import NativeOracle
import cff2_geometry as geometry

LIMIT = 1 / 32
METRICS = ('advance_width', 'advance_height', 'vertical_origin_x', 'vertical_origin_y')


def run(output):
    if platform.system() != 'Darwin':
        raise RuntimeError('CoreText CFF2 NOT_RUN: macOS required')
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'IN_PROGRESS', 'production_accepted': False,
              'scope': 'authored CFF2 controls; no original-font or Windows 11 acceptance',
              'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'os': platform.platform(), 'python': platform.python_version(),
              'fonttools': fontTools.__version__, 'harfbuzz': hb.version_string(),
              'limit_source_font_units': LIMIT, 'variants': {}, 'failures': []}
    try:
        report['empty_path_proof'] = run_empty_proof(output / 'empty-proof')
        binary = output / 'coretext_extract'
        command = ['swiftc', '-O', str(Path(__file__).with_name('coretext_extract.swift')), '-o', str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (output / 'compile.log').write_text(compiled.stdout + compiled.stderr)
        report['compile'] = {'command': command, 'exit_code': compiled.returncode}
        compiled.check_returncode()
        report['binary_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
        source = output / 'authored-source.ttc'; make_fixture(source)
        with TTCollection(source) as original:
            for kind in ('flat', 'factored', 'compact', 'flat_long', 'adaptive', 'ramp', 'hierarchical'):
                path = output / f'authored-cff2-{kind}.ttc'
                repeats = 512 if kind == 'flat_long' else 1
                fixture = write_fixture(path, factored=kind == 'factored', compact=kind == 'compact',
                                        repeat_contours=repeats, adaptive=kind == 'adaptive',ramp=kind == 'ramp',hierarchical=kind == 'hierarchical')
                native = NativeOracle(binary, path, output / f'{kind}-native.log')
                result = {'fixture': fixture, 'native_identity': native.metadata,
                          'max_cubic_control_error': 0., 'max_metric_errors': {},
                          'glyph_observations': 0, 'geometry_failures': 0,
                          'raw_metric_failures': 0}
                report['variants'][kind] = result
                blob = path.read_bytes()
                hb_fonts = []
                for face, font in enumerate(original.fonts):
                    hb_font = hb.Font(hb.Face(blob, face)); hb.ot_font_set_funcs(hb_font)
                    upm = font['head'].unitsPerEm; hb_font.scale = (upm * 64, upm * 64)
                    hb_fonts.append(hb_font)
                try:
                    with (output / f'{kind}-observations.jsonl').open('x') as transcript:
                        for request in native_requests():
                            face, location = request['face_index'], request['location']
                            samples = native.samples(face, request['glyph_ids'], location)
                            hb_font = hb_fonts[face]; hb_font.set_variations(location)
                            for gid, row in samples.items():
                                transcript.write(json.dumps(row, allow_nan=False) + '\n')
                                result['glyph_observations'] += 1
                                context = dict(variant=kind, face=face, gid=gid, location=location)
                                expected = ideal_metrics(location, gid)
                                vorg = hb_font.get_glyph_v_origin(gid)
                                hb_metrics = {'advance_width': hb_font.get_glyph_h_advance(gid) / 64,
                                    'advance_height': -hb_font.get_glyph_v_advance(gid) / 64,
                                    'vertical_origin_x': vorg[0] / 64, 'vertical_origin_y': vorg[1] / 64}
                                for engine, metrics in (('CoreText', row), ('HarfBuzz', hb_metrics)):
                                    for key in METRICS:
                                        error = abs(metrics[key] - expected[key]); label = engine + '.' + key
                                        result['max_metric_errors'][label] = max(error, result['max_metric_errors'].get(label, 0.))
                                        if error > LIMIT:
                                            result['raw_metric_failures'] += 1
                                            report['failures'].append(dict(context, engine=engine, field=key,
                                                actual=metrics[key], expected=expected[key], error=error))
                                name = original.fonts[face].getGlyphOrder()[gid]
                                wanted = records(original.fonts[face], name, [normalized_location(location)], .25,
                                                 repeat_contours=repeats, nonlinear=kind in ('adaptive','ramp','hierarchical'))[0]
                                expected_ops, expected_values = geometry.operands(wanted)
                                actual_ops, actual_values = geometry.operands(row['commands'])
                                if actual_ops != expected_ops:
                                    result['geometry_failures'] += 1
                                    report['failures'].append(dict(context, field='cubic_topology'))
                                else:
                                    error = float(np.linalg.norm(geometry.control_points(actual_ops, actual_values)
                                        - geometry.control_points(expected_ops, expected_values), axis=1).max(initial=0))
                                    result['max_cubic_control_error'] = max(error, result['max_cubic_control_error'])
                                    if error > LIMIT:
                                        result['geometry_failures'] += 1
                                        report['failures'].append(dict(context, field='cubic_geometry', error=error))
                    native.finish(); result['summary'] = native.summary
                finally:
                    native.close()
        report['status'] = 'FAIL_STRICT_METRICS_OR_GEOMETRY' if report['failures'] else 'PASS_AUTHORED_CFF2_CONTROLS'
    except Exception as error:
        report['status'] = 'FAIL_EXECUTION'; report['error'] = str(error)
        raise
    finally:
        (output / 'cff2-result.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = run(args.output)
    print(json.dumps({'status': report['status'], 'failures': len(report['failures']),
                      'report': str(args.output / 'cff2-result.json')}, indent=2))
    sys.exit(0 if report['status'] == 'PASS_AUTHORED_CFF2_CONTROLS' else 1)
