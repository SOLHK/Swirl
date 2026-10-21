#!/usr/bin/env python3
"""Independent private P8 q-face checks against SHA-bound native caches.

No Apple process is started. Seven frozen cases per encoded GID are read from
the existing complete native transcript caches; actual serialized candidate
outlines/advances come from HarfBuzz. Original TABLE metrics, original HarfBuzz
integer advances and Apple HVF outlines remain separate references. Existing
comparators and their fixed 1/32 threshold are unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from diagnose_path_types import raw_native_paths, raw_coretext_paths, compare_preserved_quadratics
from metric_variations import verify_metric_variations
from p7_original_glyf import PRIVATE, EXPECTED, CUSTOM, HOLDOUT, digest_value, private_directory
from p7_validate_candidate import commands
from probe_axis_thresholds import TAGS
from rebuild import sha256
from source_metrics import SourceMetrics
from source_request_oracle import exact_json
from table_metric_oracle import identity_design_coordinates
from ttc_staging_binary import validate_ttc_binary

LIMIT = 1/32


def require(value, reason):
    if not value:
        raise ValueError(reason)


def _hash(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None,
            'explicit_bound_SHA256_required')
    return value


def _json(path, expected=None):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'regular_cache_file_required')
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    require(expected is None or digest == expected, 'cached_bytes_changed')
    return json.loads(data), digest


def case_indices(recipe):
    """Default, unchanged four P7 holdouts, and two weight extrema only."""
    training, holdout = recipe.get('training'), recipe.get('holdout')
    require(type(training) is list and 1 <= len(training) <= 1024
            and exact_json(holdout, [dict(zip(CUSTOM, p)) for p in HOLDOUT]),
            'frozen_P7_holdouts_required')
    locations = training+holdout
    require(all(type(p) is dict and set(p) == set(CUSTOM)
                and all(type(v) in (int, float) and math.isfinite(v) and -1 <= v <= 1 for v in p.values())
                for p in locations), 'explicit_finite_q_locations_required')
    require(len({tuple(p[tag] for tag in CUSTOM) for p in locations}) == len(locations),
            'duplicate_training_or_holdout_location')
    targets = [('default', (0., 0., 0.)), ('weight_min', (0., -1., 0.)), ('weight_max', (0., 1., 0.))]
    found = []
    for name, position in targets:
        matches = [i for i, p in enumerate(training) if exact_json(p, dict(zip(CUSTOM, position)))]
        require(len(matches) == 1, 'cached_default_and_weight_extrema_required')
        found.append((name, matches[0]))
    return [found[0], *[(f'holdout_{i}', len(training)+i) for i in range(4)], *found[1:]]


def checked_batch(batch):
    receipt, digest = _json(Path(batch)/'batch-receipt.json')
    recipe = receipt.get('recipe')
    require(type(recipe) is dict and receipt.get('recipe_sha256') == digest_value(recipe)
            and recipe.get('source_sha256') == EXPECTED and type(recipe.get('face_index')) is int
            and recipe['face_index'] == 0 and type(recipe.get('multiplier')) is int and recipe['multiplier'] >= 1,
            'source_bound_batch_recipe_required')
    gids, rows = recipe.get('gids'), receipt.get('rows')
    require(type(gids) is list and gids and len(gids) <= 47102 and len(set(gids)) == len(gids)
            and all(type(gid) is int and 0 <= gid < 47102 for gid in gids)
            and type(rows) is dict and set(rows) == set(map(str, gids)), 'complete_batch_rows_required')
    require(all(type(row) is dict and row.get('status') in ('ENCODED_EXPERIMENTAL', 'FAILED')
                for row in rows.values()), 'finished_batch_snapshot_required')
    require(any(row['status'] == 'ENCODED_EXPERIMENTAL' for row in rows.values()), 'encoded_GIDs_required')
    return receipt, digest


def checked_native_cases(batch, gid, row, batch_recipe):
    """Check every source-bound cache SHA; retain only seven event payloads."""
    directory = Path(batch)/f'gid-{gid:05d}'
    require(directory.is_dir() and not directory.is_symlink(), 'regular_GID_cache_directory_required')
    receipt, receipt_digest = _json(directory/'receipt.json', _hash(row.get('sample_receipt_sha256')))
    recipe = receipt.get('recipe')
    require(type(recipe) is dict and receipt.get('recipe_sha256') == digest_value(recipe)
            and recipe.get('source_sha256') == EXPECTED and type(recipe.get('face_index')) is int
            and recipe['face_index'] == 0 and type(recipe.get('gids')) is list
            and len(recipe['gids']) == 1 and type(recipe['gids'][0]) is int and recipe['gids'] == [gid]
            and type(recipe.get('multiplier')) is int and recipe['multiplier'] == batch_recipe['multiplier']
            and _hash(recipe.get('binary_sha256')) == _hash(batch_recipe.get('oracle_sha256')),
            'source_bound_GID_recipe_required')
    require(batch_recipe.get('training') is None or exact_json(recipe.get('training'), batch_recipe['training']),
            'batch_training_plan_changed')
    require(batch_recipe.get('frozen_holdout') is None
            or exact_json(recipe.get('holdout'), [dict(zip(CUSTOM, p)) for p in batch_recipe['frozen_holdout']]),
            'batch_holdout_plan_changed')
    indices = case_indices(recipe)
    records = receipt.get('models')
    require(type(records) is dict and set(records) == {str(gid)}, 'one_bound_model_per_GID_required')
    model, model_digest = _json(directory/f'gid-{gid:05d}.json', _hash(records[str(gid)]['sha256']))
    require(type(model.get('glyph_id')) is int and model['glyph_id'] == gid
            and model.get('recipe_sha256') == receipt['recipe_sha256'], 'cached_model_identity_changed')
    glyf_path = directory/f'gid-{gid:05d}.glyf'
    require(glyf_path.is_file() and not glyf_path.is_symlink()
            and sha256(glyf_path) == _hash(records[str(gid)]['glyf_sha256']), 'cached_glyf_bytes_changed')
    locations, hashes = recipe['training']+recipe['holdout'], receipt.get('native_samples')
    require(type(hashes) is dict and set(hashes) == {f'{gid}:{i}' for i in range(len(locations))},
            'complete_source_native_cache_required')
    wanted = {index: name for name, index in indices}
    cases = []
    for i, location in enumerate(locations):
        value, _ = _json(directory/f'gid-{gid:05d}-native-{i:02d}.json', _hash(hashes[f'{gid}:{i}']))
        q = dict(zip(TAGS, (location[tag] for tag in CUSTOM)))
        require(type(value.get('glyph_id')) is int and value['glyph_id'] == gid
                and value.get('recipe_sha256') == receipt['recipe_sha256']
                and exact_json(value.get('source_q'), q) and type(value.get('events')) is list,
                'cached_native_source_binding_changed')
        if i in wanted:
            # Validate all chosen event structure without changing its geometry.
            raw_native_paths(value['events'])
            cases.append({'name': wanted[i], 'q': q, 'events': value['events']})
    cases.sort(key=lambda item: [name for name, _ in indices].index(item['name']))
    report = model.get('report')
    require(type(report) is dict and type(report.get('source_units_per_em')) is int
            and type(report.get('target_units_per_em')) is int
            and report.get('physical_grid_multiplier') == batch_recipe['multiplier'], 'model_UPM_binding_required')
    return cases, {'sample_receipt_sha256': receipt_digest, 'model_sha256': model_digest,
        'native_cache_files_verified': len(locations), 'source_units_per_em': report['source_units_per_em'],
        'target_units_per_em': report['target_units_per_em']}


def checked_assembly(candidate, batch_digest, encoded, candidate_digest):
    """Bind this precise candidate to the verified source-batch assembly receipt.

    This checks the existing assembler's receipt, not an independently recovered
    equality of every candidate coefficient to every cached model coefficient.
    Actual decoded candidate geometry and metrics are measured below.
    """
    path = Path(candidate).parent/'face-report.json'
    report, digest = _json(path)
    selected = report.get('selected_variable_GIDs')
    require(report.get('source_sha256') == EXPECTED
            and _hash(report.get('model_receipt_sha256')) == batch_digest
            and type(report.get('glyph_count')) is int and report['glyph_count'] == 47102
            and type(selected) is list and all(type(gid) is int for gid in selected)
            and len(selected) == len(encoded) and set(selected) == set(encoded)
            and type(report.get('serialization')) is dict and report['serialization'].get('status') == 'PASS',
            'candidate_assembly_source_batch_binding_required')
    with Path(candidate).open('rb') as stream:
        is_ttc = stream.read(4) == b'ttcf'
    recorded = (report.get('packing', {}).get('sha256') if is_ttc else report.get('candidate_sha256'))
    require(_hash(recorded) == candidate_digest, 'candidate_assembly_bytes_changed')
    return path, digest


def validate(source, batch, candidate, output, expected_sha256=EXPECTED):
    source, batch, candidate = (Path(p).resolve(strict=True) for p in (source, batch, candidate))
    require(expected_sha256 == EXPECTED and sha256(source) == EXPECTED, 'exact_original_source_required')
    require(batch.is_relative_to(PRIVATE) and candidate.is_relative_to(PRIVATE), 'private_batch_and_candidate_required')
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(), 'fresh_validation_output_required')
    output = private_directory(output)
    saved, batch_digest = checked_batch(batch)
    before = sha256(candidate)
    rows = saved['rows']
    encoded = sorted(int(key) for key, row in rows.items() if row['status'] == 'ENCODED_EXPERIMENTAL')
    assembly_path, assembly_digest = checked_assembly(candidate, batch_digest, encoded, before)
    summary = {'status': 'RUNNING_PRIVATE_CACHED_MODEL_VALIDATION', 'source_sha256': EXPECTED,
        'candidate_sha256': before, 'batch_receipt_sha256': batch_digest, 'validator_sha256': sha256(Path(__file__)),
        'assembly_receipt_sha256': assembly_digest,
        'candidate_model_binding': 'ASSEMBLER_RECEIPT_BOUND_NOT_INDEPENDENT_COEFFICIENT_EQUALITY_PROOF',
        'requested_GIDs': len(saved['recipe']['gids']), 'source_batch_encoded_GIDs': len(encoded),
        'failed_build_GIDs': len(rows)-len(encoded), 'GIDs_checked': 0, 'cases_checked': 0,
        'native_cache_files_verified': 0, 'native_calls': 0, 'limit_source_font_units': LIMIT,
        'HarfBuzz': hb.version_string(), 'source_user_mapping_accepted': False, 'production_accepted': False,
        'strict_font_acceptance': False, 'Apple_native_metrics': 'NOT_EXTRACTED',
        'DirectWrite': 'NOT_RUN', 'Windows11': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN',
        'coordinate_scope': 'EXPLICIT_CACHED_DESIGN_Q_NOT_ORIGINAL_USER_MAPPING',
        'measurement_scope': 'SEVEN_CACHED_POSITIONS_PER_GID_NOT_ALL_TRAINING_OR_FULL_DOMAIN',
        'native_equivalence_accepted_GIDs': 0}
    details = []
    try:
        with candidate.open('rb') as stream:
            is_ttc = stream.read(4) == b'ttcf'
        summary['TTC_binary'] = validate_ttc_binary(candidate) if is_ttc else {'status': 'NOT_RUN_TTF_INPUT'}
        if is_ttc:
            require(summary['TTC_binary']['faces'] == 1, 'one_experimental_face_required')
        with TTFont(source, fontNumber=0, lazy=True) as original, TTFont(candidate, fontNumber=0, lazy=True) as target:
            require(original.getGlyphOrder() == target.getGlyphOrder()
                    and original['maxp'].numGlyphs == target['maxp'].numGlyphs == 47102
                    and original['cmap'].compile(original) == target['cmap'].compile(target), 'original_GID_or_cmap_changed')
            require({'glyf', 'loca', 'gvar', 'HVAR', 'VVAR', 'fvar', 'avar'} <= set(target.keys())
                    and not {'hvgl', 'hvpm'} & set(target.keys()), 'standard_experimental_outline_tables_required')
            require(tuple(a.axisTag for a in target['fvar'].axes) == CUSTOM
                    and all((a.minValue, a.defaultValue, a.maxValue) == (-1, 0, 1) for a in target['fvar'].axes),
                    'normalized_custom_q_axes_required')
            identity_design_coordinates(target, dict.fromkeys(CUSTOM, 0.))
            require(target['head'].unitsPerEm == original['head'].unitsPerEm*saved['recipe']['multiplier']
                    and target['head'].unitsPerEm <= 16384, 'candidate_UPM_ratio_changed')
            require(struct.unpack_from('>H', target.reader['gvar'], 12)[0] == 47102
                    and len(target['loca'].locations) == 47103, 'serialized_gvar_loca_GID_count_changed')
            summary['metric_encoding'] = verify_metric_variations(target)
            summary['structure'] = {'glyphs': 47102, 'cmap_GID_order_equal_original': True,
                'source_UPM': original['head'].unitsPerEm, 'target_UPM': target['head'].unitsPerEm}
            provider = SourceMetrics(original)
            reference = hb.Font(hb.Face(source.read_bytes(), 0))
            native = hb.Font(hb.Face(candidate.read_bytes(), 0))
            for font in (reference, native):
                hb.ot_font_set_funcs(font)
                font.scale = (original['head'].unitsPerEm*64,)*2
            for gid in encoded:
                cases, binding = checked_native_cases(batch, gid, rows[str(gid)], saved['recipe'])
                require(binding['source_units_per_em'] == original['head'].unitsPerEm
                        and binding['target_units_per_em'] == target['head'].unitsPerEm, 'model_candidate_UPM_differs')
                summary['native_cache_files_verified'] += binding['native_cache_files_verified']
                row = {'gid': gid, 'binding': binding, 'cases': [], 'outline_failures': 0,
                    'TABLE_metric_field_failures': 0, 'HB_reference_metric_field_failures': 0,
                    'max_outline_control_error': 0., 'max_TABLE_metric_error': 0., 'max_HB_reference_metric_error': 0.,
                    'requested_q_quantization_observations': 0, 'outline_failure_reasons': {}}
                row['source_batch_reported_strict_outline_pass'] = rows[str(gid)].get('strict_outline_pass')
                row['source_batch_reported_strict_TABLE_metric_pass'] = rows[str(gid)].get('strict_table_metric_pass')
                default_commands = None
                row['HB_outline_changes_from_default_cases'] = 0
                for case in cases:
                    q = [case['q'][tag] for tag in TAGS]
                    for font in (reference, native):
                        font.set_var_coords_normalized(q)
                    row['requested_q_quantization_observations'] += sum(a != b for a, b in
                        zip(q, native.get_var_coords_normalized()))
                    observed = commands(native, gid)
                    if default_commands is None:
                        default_commands = observed
                    else:
                        row['HB_outline_changes_from_default_cases'] += observed != default_commands
                    compared = compare_preserved_quadratics(raw_native_paths(case['events']), raw_coretext_paths(observed))
                    good = compared['status'] == 'within_budget'
                    row['outline_failures'] += not good
                    if compared['maximum_point_error'] is not None:
                        row['max_outline_control_error'] = max(row['max_outline_control_error'], compared['maximum_point_error'])
                    if not good:
                        reason = compared.get('reason', compared['status'])
                        row['outline_failure_reasons'][reason] = row['outline_failure_reasons'].get(reason, 0)+1
                    current = {'name': case['name'], 'source_q': case['q'], 'outline_status': compared['status'],
                        'outline_reason': compared.get('reason'), 'outline_control_error': compared['maximum_point_error'],
                        'legacy_status': compared['legacy']['status'], 'legacy_reason': compared['legacy'].get('reason'),
                        'TABLE_metric_errors': [], 'HB_reference_metric_errors': []}
                    table = provider.at(gid, case['q'])
                    for method, field, sign in (('get_glyph_h_advance', 'advance_width', 1),
                                                 ('get_glyph_v_advance', 'advance_height', -1)):
                        a, b = getattr(reference, method)(gid)/64, getattr(native, method)(gid)/64
                        te, he = abs(sign*b-table[field]), abs(a-b)
                        row['TABLE_metric_field_failures'] += te > LIMIT
                        row['HB_reference_metric_field_failures'] += he > LIMIT
                        row['max_TABLE_metric_error'], row['max_HB_reference_metric_error'] = (
                            max(row['max_TABLE_metric_error'], te), max(row['max_HB_reference_metric_error'], he))
                        current['TABLE_metric_errors'].append(te)
                        current['HB_reference_metric_errors'].append(he)
                    row['cases'].append(current)
                row['strict_outline_status'] = 'FAIL' if row['outline_failures'] else 'PASS_FINITE_CACHE_CASES'
                row['strict_TABLE_metric_status'] = 'FAIL' if row['TABLE_metric_field_failures'] else 'PASS_FINITE_CACHE_CASES'
                row['strict_HB_reference_metric_status'] = 'FAIL' if row['HB_reference_metric_field_failures'] else 'PASS_FINITE_CACHE_CASES'
                details.append(row)
                summary['GIDs_checked'] += 1
                summary['cases_checked'] += len(cases)
        require(sha256(source) == EXPECTED and sha256(candidate) == before
                and sha256(batch/'batch-receipt.json') == batch_digest
                and sha256(assembly_path) == assembly_digest, 'source_candidate_batch_or_assembly_changed')
        reasons = Counter()
        for row in details:
            reasons.update(row['outline_failure_reasons'])
        summary.update(status='COMPLETED_PRIVATE_CACHED_MODEL_VALIDATION_NOT_ACCEPTANCE',
            outline_cases_failed=sum(r['outline_failures'] for r in details), outline_failure_reasons=dict(reasons),
            strict_outline_pass_GIDs=sum(not r['outline_failures'] for r in details),
            strict_TABLE_metric_pass_GIDs=sum(not r['TABLE_metric_field_failures'] for r in details),
            strict_HB_reference_metric_pass_GIDs=sum(not r['HB_reference_metric_field_failures'] for r in details),
            TABLE_metric_fields_failed=sum(r['TABLE_metric_field_failures'] for r in details),
            HB_reference_metric_fields_failed=sum(r['HB_reference_metric_field_failures'] for r in details),
            metric_fields_checked=2*summary['cases_checked'],
            maximum_comparable_outline_control_error=max((r['max_outline_control_error'] for r in details), default=0.),
            maximum_TABLE_metric_error=max((r['max_TABLE_metric_error'] for r in details), default=0.),
            maximum_HB_reference_metric_error=max((r['max_HB_reference_metric_error'] for r in details), default=0.),
            actual_HB_outline_varies_GIDs=sum(bool(r['HB_outline_changes_from_default_cases']) for r in details),
            requested_q_quantization_observations=sum(r['requested_q_quantization_observations'] for r in details),
            source_unchanged=True, candidate_unchanged=True, batch_snapshot_unchanged=True, assembly_receipt_unchanged=True,
            outline_comparator='UNCHANGED_PRESERVED_QUADRATICS_NO_SEGMENTS_REMOVED',
            source_metric_reference='ORIGINAL_TABLES_NOT_APPLE_METRIC_API',
            HB_reference='ORIGINAL_STANDARD_HVAR_AND_VMTX_NOT_APPLE_METRIC_API')
    except Exception as error:
        summary.update(status='BLOCKED_PRIVATE_CACHED_MODEL_VALIDATION', error_type=type(error).__name__)
        raise
    finally:
        with (output/'per-gid.json').open('x') as stream:
            json.dump(details, stream, indent=2)
            stream.write('\n')
        summary['private_details_sha256'] = sha256(output/'per-gid.json')
        with (output/'summary.json').open('x') as stream:
            json.dump(summary, stream, indent=2)
            stream.write('\n')
    print(json.dumps(summary))  # Whitelisted aggregates only, never per-GID data.
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'batch', 'candidate', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    validate(args.source, args.batch, args.candidate, args.output, args.expected_sha256)
