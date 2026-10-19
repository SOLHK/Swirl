#!/usr/bin/env python3
"""Verify implemented isolated tangents against native data, never release a font.

Recorded input is restricted to the 22 self-authored experiments from the first
native run. Fresh verification retains the 48 previously independent cases and adds
54 unseen explicit boundary cases; none of the failing inputs is removed.
An optional original-source mode writes AGGREGATES ONLY, never Apple outlines.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile

import numpy as np
from fontTools.ttLib import TTCollection, TTFont, newTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tangent_geometry import resolve_path
from hvf import HVGL, ExperimentalRenderer
from probe_tangent_rules import cases, encode_shape
from probe_hierarchy_rules import native_quadratics, point_error
from make_synthetic_hvf import create

SOURCE_SHA = '39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'
LIMIT = 1 / 32


def extra_cases():
    """Not among the 22 observations used to infer the formula."""
    rng = np.random.default_rng(83492026)
    _, tags, baseline = cases()[0]
    for n in range(48):
        data = baseline.copy()
        data[2, 2:] += rng.uniform(-150, 150, 2)
        data[3, 2:] += rng.uniform(-150, 150, 2)
        data[3, :2] += rng.uniform(-350, 350, 2)
        data[2, 0] = float(rng.uniform(0.1, 0.9))
        # Original coordinates, rotated/scaled before encoding, not a second
        # transform imposed on Apple's result. Type-0 scalar stays a scalar.
        angle = rng.uniform(-np.pi, np.pi)
        c, s = np.cos(angle), np.sin(angle)
        rotation = np.array([[c, -s], [s, c]]) * rng.uniform(0.2, 3)
        offset = rng.uniform(-150, 150, 2)
        for i, tag in enumerate(tags):
            if tag != 0:
                data[i, :2] = data[i, :2] @ rotation.T + offset
        data[:, 2:] = data[:, 2:] @ rotation.T + offset
        yield f'independent_{n}', tags, data


def boundary_cases():
    """New exact boundary/near-boundary points, not used to infer clamping."""
    _, tags, base = cases()[0]
    parameters = (-4., -1e-6, 0., 1e-6, .5, 1.-1e-6, 1., 1.+1e-6, 4.)
    for angle in (0., .371, -1.2):
        c, s = np.cos(angle), np.sin(angle)
        rotation = np.array([[c,-s],[s,c]])
        a, b = np.array([120.,-40.]), np.array([160.,180.])
        direction = b-a
        normal = np.array([-direction[1], direction[0]])
        normal /= np.linalg.norm(normal)
        for t in parameters:
            for displacement in (-173., 229.):
                data = base.copy()
                data[2,2:] = a; data[3,2:] = b
                data[3,:2] = a+t*direction+displacement*normal
                for index, tag in enumerate(tags):
                    if tag != 0: data[index,:2] = data[index,:2] @ rotation.T
                data[:,2:] = data[:,2:] @ rotation.T
                yield f'boundary_{angle}_{t}_{displacement}', tags, data


def native_events(binary, font, coordinate, gid=0):
    result = subprocess.run([str(binary.resolve()), str(font.resolve()), '0',
                             ','.join(map(str, coordinate)), str(gid), '1'],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        # Never include original glyph output or stderr in public reports.
        raise ValueError(f'native process exit {result.returncode}')
    records = [json.loads(line) for line in result.stdout.splitlines() if line]
    outlines = [r for r in records if r.get('record') == 'outline']
    if len(outlines) != 1 or outlines[0].get('part_index') != gid or outlines[0].get('status') != 'OK':
        raise ValueError('native outline identity or status mismatch')
    return outlines[0]['events']


def verify_recorded(path):
    report = json.loads(path.read_text(encoding='utf-8'))
    if report.get('data_origin') != 'self_authored_geometry_no_Apple_font_data':
        raise ValueError('only the original synthetic experiment record is accepted')
    rows = report['observations']
    expected = {name: (tags, data) for name, tags, data in cases()}
    if len(rows) != len(expected) or {r['case'] for r in rows} != set(expected):
        raise ValueError('recorded experiment set changed')
    errors = []
    for row in rows:
        tags, data = expected[row['case']]
        if tags != row['blends'] or not np.array_equal(data, row['master']):
            raise ValueError('recorded synthetic input differs')
        error = point_error([resolve_path(data, tags)], native_quadratics(row['native_events']))
        errors.append({'case': row['case'], 'max_point_error': error, 'passed': error <= LIMIT})
    return {'status': 'RECORDED_SYNTHETIC_PASS' if all(x['passed'] for x in errors) else 'RECORDED_SYNTHETIC_FAILED',
            'record_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'cases': len(errors), 'max_point_error': max(x['max_point_error'] for x in errors),
            'failures': sum(not x['passed'] for x in errors), 'results': errors,
            'new_native_process_executed': False, 'original_font_acceptance': 'NOT_RUN',
            'tolerance_font_units': LIMIT}


def verify_synthetic(binary):
    errors = []
    with tempfile.TemporaryDirectory(prefix='swirl-type2-independent-') as directory:
        font = Path(directory) / 'synthetic.ttf'; create(font)
        for name, tags, data in cases() + list(extra_cases()) + list(boundary_cases()):
            with TTFont(font, recalcBBoxes=False, recalcTimestamp=False) as f:
                table = newTable('hvgl'); table.data = encode_shape(tags, data); f['hvgl'] = table
                pending = Path(directory) / 'next.ttf'; f.save(pending)
            pending.replace(font)
            events = native_events(binary, font, [0, 0, 0])
            error = point_error([resolve_path(data, tags)], native_quadratics(events))
            errors.append({'case': name, 'max_point_error': error, 'passed': error <= LIMIT,
                           'synthetic_input_blends': tags, 'synthetic_input_master': data.tolist(),
                           'synthetic_native_events': events})
    return {'status': 'NATIVE_SYNTHETIC_PASS' if all(x['passed'] for x in errors) else 'NATIVE_SYNTHETIC_FAILED',
            'cases': len(errors), 'prior_independent_cases_retained': 48, 'new_boundary_cases': 54, 'failures': sum(not x['passed'] for x in errors),
            'max_point_error': max(x['max_point_error'] for x in errors), 'results': errors,
            'original_font_acceptance': 'NOT_RUN', 'tolerance_font_units': LIMIT}


def verify_source(binary, source):
    # Reuse the previous EXACT comparison, sample selection and random seed.
    # Do not change its canonicalisation to make the new renderer pass.
    from calibrate_hvf_geometry import select_glyphs, portable_paths, native_paths, discrepancy
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != SOURCE_SHA:
        raise ValueError('exact original source required')
    positions = list(itertools.product((-1., 0., 1.), repeat=3))
    rng = random.Random(74321)
    positions += [tuple(rng.uniform(-.98, .98) for _ in range(3)) for _ in range(7)]
    failures = []; reasons = {}; maximum = 0.; count = 0; by_gid = {}
    with TTCollection(source, lazy=True) as fonts:
        table = HVGL(fonts.fonts[0].reader['hvgl'])
        gids, coverage = select_glyphs(table)
        renderer = ExperimentalRenderer(table, isolated_tangents=True)
        for position in positions:
            for gid in gids:
                count += 1
                stats = by_gid.setdefault(str(gid), {'passed': 0, 'failed': 0, 'max_point_error': 0.})
                try:
                    events = native_events(binary, source, position, gid)
                    paths = renderer.render(gid, position[:table.part(gid).axis_count])
                    error, _ = discrepancy(portable_paths(paths), native_paths(events))
                    maximum = max(maximum, error); stats['max_point_error'] = max(stats['max_point_error'], error)
                    if error > LIMIT:
                        raise ValueError('control_point_error_budget_exceeded')
                    stats['passed'] += 1
                except (ValueError, RuntimeError) as error:
                    stats['failed'] += 1
                    reason = str(error)
                    reasons[reason] = reasons.get(reason, 0) + 1
                    failures.append({'glyph_id': gid, 'design_location': position, 'reason': reason})
            print(json.dumps({'source_locations_completed': positions.index(position)+1,
                              'instances': count, 'failures': len(failures)}), flush=True)
    unchanged = hashlib.sha256(source.read_bytes()).hexdigest() == before
    if not unchanged:
        raise ValueError('source changed')
    return {'status': 'SAMPLED_DESIGN_GEOMETRY_PASS_NOT_FONT_ACCEPTANCE' if not failures else 'GEOMETRY_CALIBRATION_FAILED',
            'source_sha256': before, 'source_unchanged': unchanged, 'selected_glyphs': gids,
            'coverage': coverage, 'positions': len(positions), 'glyph_instances': count,
            'passed': count-len(failures), 'failures': len(failures), 'by_glyph': by_gid,
            'max_point_error': maximum, 'failure_reasons': reasons, 'failure_examples': failures[:16],
            'type2_interpretation': 'implemented_closest_control_segment_projection',
            'tolerance_font_units': LIMIT, 'source_outlines_published': False,
            'scope': 'sampled_design_geometry_only_no_avar_metrics_or_Windows', 'final_font_generated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--recorded', type=Path)
    mode.add_argument('--native-binary', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('choose a new output report')
    if args.source and not args.native_binary:
        raise ValueError('--source requires a native binary')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = verify_recorded(args.recorded) if args.recorded else (
        verify_source(args.native_binary, args.source) if args.source else verify_synthetic(args.native_binary))
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('results', 'by_glyph')}, allow_nan=False))
    return 1 if result['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
