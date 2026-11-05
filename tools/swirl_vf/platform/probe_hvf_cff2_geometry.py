#!/usr/bin/env python3
"""Private mixed-axis source/native/model comparison with complete receipts.

All three design coordinates vary together. The reference is Apple libhvf on
the exact supplied bytes, not the fitted model. Coordinates are after avar;
user-coordinate transport, metrics and a complete font remain separate gates.
No source outlines or model coefficients are included in the summary. Raw
native transcripts must stay in the explicitly private output directory.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
from fontTools.ttLib import TTCollection

from hvf_transcript import validate_transcript

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from batch_geometry import BatchGeometry
from hvf import HVGL
from hvf_glyph_model import _commands
import cff2_geometry as geometry


def positions(seed=20261103, holdouts=32):
    if type(holdouts) is not int or not 1 <= holdouts <= 256:
        raise ValueError('bounded_independent_holdout_count_required')
    grid = np.asarray(list(itertools.product((-1., 0., 1.), repeat=3)))
    # Odd F2DOT14 coordinates exclude the fitting grid and all zero-axis planes.
    held = np.random.default_rng(seed).choice(np.arange(-16383, 16384, 2), (holdouts, 3)) / 16384
    if len({tuple(p) for p in held}) != holdouts:
        raise ValueError('duplicate_independent_holdout')
    return grid, held


def compare_commands(expected, actual):
    left_ops, left = geometry.operands(expected)
    right_ops, right = geometry.operands(actual)
    if left_ops != right_ops:
        return dict(passed=False, reason='cubic_topology_mismatch',
                    max_control_error=None)
    error = float(np.linalg.norm(geometry.control_points(left_ops, left)
        - geometry.control_points(right_ops, right), axis=1).max(initial=0))
    return dict(passed=error <= geometry.LIMIT, max_control_error=error)


def native_commands(row):
    names = {'move': 'moveTo', 'line': 'lineTo', 'quad': 'qCurveTo',
             'cubic': 'curveTo', 'close': 'closePath'}
    return [[names[e[0]], *e[1:]] for e in row['events'] if e[0] in names]


def run(source, expected_sha, binary, output, *, face=0, gids=(0, 2, 12, 1166, 19177), holdouts=32, adaptive=False):
    source = Path(source).resolve(strict=True)
    binary = Path(binary).resolve(strict=True)
    output = Path(output).resolve()
    repo = Path(__file__).resolve().parents[3]
    if platform.system() != 'Darwin':
        raise RuntimeError('native_HVF_requires_macOS')
    if output.exists() or output.is_relative_to(repo):
        raise ValueError('new_private_output_outside_repository_required')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != expected_sha:
        raise ValueError('source_hash_mismatch')
    grid, held = positions(holdouts=holdouts)
    points = np.concatenate((grid, held))
    output.mkdir(parents=True, mode=0o700)
    with TTCollection(source, lazy=True) as collection:
        if type(face) is not int or not 0 <= face < len(collection.fonts):
            raise ValueError('invalid_source_face')
        font = collection.fonts[face]
        tags = tuple(a.axisTag for a in font['fvar'].axes)
        if len(tags) != 3 or not gids or len(set(gids)) != len(gids) or any(
                type(g) is not int or not 0 <= g < font['maxp'].numGlyphs for g in gids):
            raise ValueError('invalid_source_axes_or_GID_plan')
        table = HVGL(font.reader['hvgl'], font.reader['hvpm'] if 'hvpm' in font else None)
        count = font['maxp'].numGlyphs
    renderer = BatchGeometry(table, isolated_tangents=True)
    report = dict(scope='selected_GIDs_post_avar_three_axis_native_and_CFF2_fit',
        source_sha256=digest, native_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        platform=platform.platform(), face_index=face, source_glyph_count=count,
        axis_order=tags, grid_positions=len(grid), independent_positions=len(held),
        position_plan_sha256=hashlib.sha256(points.astype('>f8').tobytes()).hexdigest(),
        limit_source_units=geometry.LIMIT, cases=[], production_accepted=False,
        complete_font_acceptance='NOT_RUN', user_axis_mapping='NOT_TESTED', metrics='NOT_EXTRACTED')
    locations = [dict(zip(tags, map(float, p))) for p in points]
    for gid in gids:
        axes = table.part(gid).axis_count
        batch = renderer.render(gid, points[:, :axes])
        portable = [_commands(batch.paths, i, 1) for i in range(len(points))]
        case = dict(glyph_id=gid, native_comparisons=0, native_failures=[],
                    max_portable_native_control_error=0., native_topology_failures=0)
        try:
            model = geometry.fit(portable[:len(grid)], locations[:len(grid)],
                portable[len(grid):], locations[len(grid):], tags)
            case['fit'] = dict(passed=model.evidence['sampled_geometry_passed'],
                failed_samples=len(model.evidence['failures']),
                max_control_error=model.evidence['max_control_error_source_units'])
        except ValueError as error:
            case['fit'] = dict(passed=False, error=str(error))
        adaptive_model = None
        if adaptive:
            from adaptive_cff2_geometry import fit_tensor
            operators = geometry.operands(portable[0])[0]
            def evaluate(requested):
                actual = renderer.render(gid, requested[:, :axes])
                data = [geometry.operands(_commands(actual.paths, i, 1)) for i in range(len(requested))]
                if any(ops != operators for ops, _ in data):
                    raise ValueError('source_tensor_topology_changed')
                return np.asarray([v for _, v in data])
            adaptive_model = fit_tensor(evaluate, operators, tags, held)
            evidence = adaptive_model.evidence
            case['adaptive_fit'] = {k:evidence[k] for k in ('sampled_geometry_passed',
                'training_count', 'holdout_count', 'nonzero_regions', 'flat_blend_stack_encodable',
                'max_training_error', 'max_refinement_error', 'max_holdout_error')}
            case['adaptive_fit'].update(native_failures=0, max_native_control_error=0.)
        for i, point in enumerate(points):
            transcript = output / f'gid-{gid}-position-{i}.jsonl'
            command = [str(binary), str(source), str(face),
                ','.join(format(float(v), '.17g') for v in point), str(gid), '1']
            process = subprocess.run(command, capture_output=True, text=True, timeout=30)
            transcript.write_text(process.stdout)
            (output / f'gid-{gid}-position-{i}.stderr.log').write_text(process.stderr)
            proof = validate_transcript(transcript, face=face, coords=point.tolist(),
                start=gid, count=1, parts=False, input_bytes=source.stat().st_size)
            if process.returncode != 0 or proof['counts']['failed_outlines']:
                raise RuntimeError('native_geometry_extraction_failed')
            rows = [json.loads(line) for line in process.stdout.splitlines()]
            outline = next(row for row in rows if row.get('record') == 'outline')
            verdict = compare_commands(portable[i], native_commands(outline))
            if adaptive_model is not None:
                native_ops, native_values = geometry.operands(native_commands(outline))
                native_fit = case['adaptive_fit']
                if native_ops != adaptive_model.operators:
                    native_fit['native_failures'] += 1
                else:
                    error = float(np.linalg.norm(adaptive_model.evaluate(locations[i])
                        - geometry.control_points(native_ops, native_values), axis=1).max(initial=0))
                    native_fit['native_failures'] += error > geometry.LIMIT
                    native_fit['max_native_control_error'] = max(native_fit['max_native_control_error'], error)
            case['native_comparisons'] += 1
            if verdict['max_control_error'] is None:
                case['native_topology_failures'] += 1
            else:
                case['max_portable_native_control_error'] = max(
                    case['max_portable_native_control_error'], verdict['max_control_error'])
            if not verdict['passed']:
                case['native_failures'].append(dict(position_index=i, **verdict))
        report['cases'].append(case)
        report['source_unchanged'] = hashlib.sha256(source.read_bytes()).hexdigest() == digest
        if not report['source_unchanged']:
            raise RuntimeError('source_changed_during_native_comparison')
        (output / 'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(case), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--private-output', required=True, type=Path)
    parser.add_argument('--face', type=int, default=0)
    parser.add_argument('--gids', default='0,2,12,1166,19177')
    parser.add_argument('--holdouts', type=int, default=32)
    parser.add_argument('--adaptive', action='store_true')
    args = parser.parse_args()
    result = run(args.source, args.source_sha256, args.binary, args.private_output,
        face=args.face, gids=tuple(int(g) for g in args.gids.split(',')), holdouts=args.holdouts,
        adaptive=args.adaptive)
    sys.exit(0 if all(c['fit']['passed'] and not c['native_failures'] for c in result['cases']) else 1)
