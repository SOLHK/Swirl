#!/usr/bin/env python3
"""Bounded 32-face Apple HVF comparison; no axis mapping or metric acceptance.

Reuse native transcript checks, representative GID selection, portable rendering,
legacy comparison and preserved-Q companion unchanged. Native events never leave
memory. Reports/checkpoints contain only source/code hashes, counts and errors.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import itertools
import json
from pathlib import Path
import platform
import time

from fontTools.ttLib import TTCollection
from calibrate_hvf_geometry import (HVGL, ExperimentalRenderer, select_glyphs,
    portable_paths, native_paths, discrepancy, LIMIT, EXPECTED)
from diagnose_path_types import raw_portable_paths, raw_native_paths, compare_preserved_quadratics
from macos_source_baseline import digest
from probe_axis_thresholds import hvf_events, TAGS


def design_locations():
    corners = list(itertools.product((-1., 1.), repeat=3))
    axial = [(0., weight, 0.) for weight in (-1., -.5, 0., .5, 1.)]
    return corners + axial + [(.123456789, -.7654321, .3456789), (-.9375, .8125, -.6875)]


def compare(paths, events):
    """Retain the old verdict even if its existing Q companion succeeds."""
    try:
        error, _ = discrepancy(portable_paths(paths), native_paths(events))
        legacy = error <= LIMIT
        reason = None if legacy else 'point_error_exceeds_budget'
    except ValueError as exc:
        reason = str(exc)
        if reason not in ('path_count_differs', 'segment_count_differs', 'segment_types_differ'):
            raise
        error, legacy = None, False
    if legacy:
        return {'legacy_passed': True, 'companion_called': False,
                'combined_passed': True, 'maximum_point_error': error, 'legacy_reason': None}
    companion = compare_preserved_quadratics(raw_portable_paths(paths), raw_native_paths(events))
    return {'legacy_passed': False, 'companion_called': True,
            'combined_passed': companion['status'] == 'within_budget',
            'maximum_point_error': companion['maximum_point_error'], 'legacy_reason': reason}


def validate_face(row, face, planned, recipe_hash):
    if (row.get('face_index') != face or type(row.get('face_index')) is not int
            or row.get('recipe_sha256') != recipe_hash or row.get('completed') != planned
            or row.get('status') != 'COMPLETED_FINITE_DESIGN_COMPARISON'):
        raise ValueError('incomplete_or_unbound_face_checkpoint')
    for field in ('completed', 'legacy_passed', 'legacy_failed', 'companion_calls',
                  'companion_passed', 'combined_passed', 'combined_failed'):
        if type(row.get(field)) is not int or not 0 <= row[field] <= planned:
            raise ValueError('invalid_face_count')
    if (row['legacy_passed'] + row['legacy_failed'] != planned
            or row['companion_calls'] != row['legacy_failed']
            or row['companion_passed'] > row['companion_calls']
            or row['combined_passed'] != row['legacy_passed'] + row['companion_passed']
            or row['combined_passed'] + row['combined_failed'] != planned):
        raise ValueError('inconsistent_face_comparison_counts')
    return row


def recipe_identity(source_hash, binary, gids, coverage, faces):
    root = Path(__file__).resolve().parents[1]
    # Bind all local diagnostic/rendering dependencies, not merely this driver.
    code = {str(p.relative_to(root)): digest(p) for directory in ('tools', 'platform')
            for p in sorted((root / directory).glob('*.py'))}
    return {'source_sha256': source_hash, 'binary_sha256': digest(binary),
            'oracle_c_sha256': digest(Path(__file__).with_name('hvf_oracle.c')),
            'code_sha256': code, 'gids': gids, 'coverage': coverage,
            'design_locations': [list(p) for p in design_locations()], 'faces': faces, 'limit': LIMIT}


def run(source, binary, output):
    source, binary = Path(source).resolve(strict=True), Path(binary).resolve(strict=True)
    output = Path(output).absolute()
    if platform.system() != 'Darwin':
        raise RuntimeError('Apple HVF unavailable; native comparison NOT_RUN')
    before = digest(source)
    if before != EXPECTED:
        raise ValueError('exact_original_source_required')
    if output.is_symlink() or (output / 'summary.json').exists():
        raise ValueError('completed_or_symlink_output_must_not_be_overwritten')
    with TTCollection(source, lazy=True) as collection:
        if len(collection.fonts) != 32:
            raise ValueError('all_32_original_faces_required')
        contexts, faces = {}, []
        for index, font in enumerate(collection.fonts):
            if font['maxp'].numGlyphs != 47102 or [a.axisTag for a in font['fvar'].axes] != list(TAGS) or 'hvpm' in font:
                raise ValueError('original_face_structure_changed')
            key = hashlib.sha256(font.reader['hvgl']).hexdigest()
            if key not in contexts:
                table = HVGL(font.reader['hvgl']); table.validate()
                contexts[key] = (table, ExperimentalRenderer(table, isolated_tangents=True))
            faces.append({'face_index': index, 'hvgl_sha256': key})
        selected, coverage = select_glyphs(next(iter(contexts.values()))[0])
        # Keep two old default type-rejection witnesses in the finite sample.
        gids = sorted(set(selected) | {1166, 2335})
        recipe = recipe_identity(before, binary, gids, coverage, faces)
        recipe_hash = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()
        manifest = output / 'recipe.json'
        if output.exists():
            if not manifest.is_file() or json.loads(manifest.read_text()) != recipe:
                raise ValueError('unrecognized_or_changed_checkpoint_recipe')
        else:
            output.mkdir(parents=True, mode=0o700)
            manifest.write_text(json.dumps(recipe, indent=2, allow_nan=False))
        planned = len(gids) * len(design_locations())
        @lru_cache(maxsize=1024)
        def portable(key, gid, location):
            table, renderer = contexts[key]
            return renderer.render(gid, location[:table.part(gid).axis_count])
        results = []
        started = time.monotonic()
        for face in faces:
            index, key = face['face_index'], face['hvgl_sha256']
            checkpoint = output / f'face-{index:02}.json'
            if checkpoint.exists():
                row = validate_face(json.loads(checkpoint.read_text()), index, planned, recipe_hash)
            else:
                row = {'face_index': index, 'recipe_sha256': recipe_hash,
                       'status': 'COMPLETED_FINITE_DESIGN_COMPARISON', 'completed': 0,
                       'legacy_passed': 0, 'legacy_failed': 0, 'companion_calls': 0,
                       'companion_passed': 0, 'combined_passed': 0, 'combined_failed': 0,
                       'maximum_point_error': 0., 'legacy_failure_counts': {}}
                for location in design_locations():
                    for gid in gids:
                        # Every face/GID/location executes an actual native process.
                        events = hvf_events(binary, source, index, gid, dict(zip(TAGS, location)))
                        observed = compare(portable(key, gid, location), events)
                        row['completed'] += 1
                        row['legacy_passed' if observed['legacy_passed'] else 'legacy_failed'] += 1
                        row['combined_passed' if observed['combined_passed'] else 'combined_failed'] += 1
                        if observed['companion_called']:
                            row['companion_calls'] += 1
                            row['companion_passed'] += int(observed['combined_passed'])
                            reason = observed['legacy_reason']
                            row['legacy_failure_counts'][reason] = row['legacy_failure_counts'].get(reason, 0) + 1
                        if observed['maximum_point_error'] is not None:
                            row['maximum_point_error'] = max(row['maximum_point_error'], observed['maximum_point_error'])
                validate_face(row, index, planned, recipe_hash)
                if digest(source) != before:
                    raise ValueError('source_changed_during_native_comparison')
                with checkpoint.open('x') as stream:
                    json.dump(row, stream, indent=2, allow_nan=False)
            results.append(row)
            print(json.dumps({'completed_faces': len(results), 'combined_failed': row['combined_failed'],
                              'legacy_failed_retained': row['legacy_failed']}), flush=True)
    report = {'status': 'COMPLETED_32_FACE_FINITE_DESIGN_COMPARISON_NOT_FONT_ACCEPTANCE',
              'source_sha256': before, 'recipe_sha256': recipe_hash,
              'native_faces': 32, 'gids_per_face': len(gids), 'locations_per_face': len(design_locations()),
              'unique_portable_hvgl_tables': len(contexts), 'coverage': coverage,
              'limit_font_units': LIMIT, 'elapsed_seconds': time.monotonic() - started,
              'source_unchanged': digest(source) == before,
              'font_generated': False, 'mapping_accepted': False, 'metrics_tested': False,
              'windows11_acceptance': 'NOT_RUN', 'faces': results}
    for field in ('completed', 'legacy_passed', 'legacy_failed', 'companion_calls',
                  'companion_passed', 'combined_passed', 'combined_failed'):
        report[field] = sum(row[field] for row in results)
    report['maximum_point_error'] = max(row['maximum_point_error'] for row in results)
    if not report['source_unchanged']:
        raise ValueError('source_changed_during_native_comparison')
    with (output / 'summary.json').open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='private new or unchanged resumable directory')
    args = parser.parse_args()
    result = run(args.source, args.binary, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != 'faces'}), flush=True)
    raise SystemExit(1 if result['combined_failed'] else 0)
