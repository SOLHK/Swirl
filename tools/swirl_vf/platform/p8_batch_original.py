#!/usr/bin/env python3
"""Private, resumable original-GID batches using P7/C1, never production.

Each GID retains its own source/code/native-bound P7 checkpoint. Failed GIDs
are isolated without default-outline substitution. Encoded, varied, strict
outline, strict TABLE metric and native-target acceptance are separate counts.
"""
from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path
import sys
import time
import traceback

from p7_original_glyf import (ROOT, PRIVATE, EXPECTED, CUSTOM, HOLDOUT, canonical,
    digest_value, private_directory, save_new, replace_receipt, require, sha256,
    sample, decode_model, assemble_verified_private_face)


def checked_gids(plan):
    require(plan.get('source_sha256') == EXPECTED and plan.get('source_face_index') == 0,
            'source_bound_face_zero_plan_required')
    gids = plan.get('gids')
    require(type(gids) is list and 1 <= len(gids) <= 47102
            and len(set(gids)) == len(gids)
            and all(type(gid) is int and 0 <= gid < 47102 for gid in gids),
            'unique_real_original_GIDs_required')
    return gids


def summarize(rows, requested):
    encoded = [row for row in rows.values() if row['status'] == 'ENCODED_EXPERIMENTAL']
    failures = {}
    for row in rows.values():
        if row['status'] == 'FAILED':
            key = row['failure_category']
            failures[key] = failures.get(key, 0)+1
    return dict(requested_GIDs=requested, attempted_GIDs=len(rows), encoded_GIDs=len(encoded),
        failed_GIDs=sum(failures.values()), pending_GIDs=requested-len(rows),
        nonzero_outline_variation_GIDs=sum(row['outline_varies'] for row in encoded),
        nonzero_metric_variation_GIDs=sum(row['metric_varies'] for row in encoded),
        nonzero_gvar_GIDs=sum(row['tuple_count'] > 0 for row in encoded),
        strict_sampled_model_outline_pass_GIDs=sum(row['strict_outline_pass'] for row in encoded),
        strict_sampled_TABLE_metric_pass_GIDs=sum(row['strict_table_metric_pass'] for row in encoded),
        original_HVF_extraction_pass_GIDs=sum(row['source_native_geometry_pass'] for row in encoded),
        serialized_independent_outline_validation='NOT_RUN_UNTIL_FACE_VALIDATOR',
        native_target_metric_equivalence='NOT_RUN', native_equivalence_accepted_GIDs=0,
        failure_categories=failures, continuous_proof=False, production_accepted=False)


def dependencies():
    names = ('hvf', 'batch_geometry', 'tangent_geometry', 'transform_geometry',
             'hvf_glyph_model', 'source_metrics', 'rebuild', 'hvf_glyf_closure', 'hvf_model_nodes')
    return {str(ROOT/'tools'/f'{name}.py'): sha256(ROOT/'tools'/f'{name}.py') for name in names}


def training(profile):
    if profile == 'p7':
        return None
    require(profile == 'tensor5', 'known_bounded_training_profile_required')
    from hvf_model_nodes import tensor_training_grid
    return tensor_training_grid(CUSTOM, forbidden_locations=[dict(zip(CUSTOM, p)) for p in HOLDOUT])


def checked_model(directory):
    receipt = json.loads((directory/'receipt.json').read_text())
    require(receipt['recipe_sha256'] == digest_value(receipt['recipe'])
            and receipt['recipe']['source_sha256'] == EXPECTED
            and receipt['recipe']['driver_sha256'] == sha256(ROOT/'platform/p7_original_glyf.py')
            and all(sha256(ROOT/'tools'/f'{name}.py') == digest
                    for name, digest in receipt['recipe']['code'].items()),
            'per_GID_model_recipe_or_code_changed')
    require(len(receipt['models']) == 1, 'one_GID_checkpoint_required')
    gid, row = next(iter(receipt['models'].items()))
    path, binary = directory/f'gid-{int(gid):05d}.json', directory/f'gid-{int(gid):05d}.glyf'
    require(sha256(path) == row['sha256'] and sha256(binary) == row['glyf_sha256'],
            'per_GID_model_or_glyf_bytes_changed')
    encoded = json.loads(path.read_text())
    require(encoded['glyph_id'] == int(gid) and encoded['recipe_sha256'] == receipt['recipe_sha256'],
            'per_GID_model_identity_changed')
    require(len(receipt['native_samples']) == len(receipt['recipe']['training'])+len(receipt['recipe']['holdout']),
            'per_GID_native_sample_count_changed')
    for key, digest in receipt['native_samples'].items():
        g, n = map(int, key.split(':'))
        require(g == int(gid) and sha256(directory/f'gid-{g:05d}-native-{n:02d}.json') == digest,
                'per_GID_native_sample_bytes_changed')
    return int(gid), decode_model(encoded), sha256(directory/'receipt.json')


def run(source, binary, plan_path, output, *, max_new_gids=None, profile='p7'):
    source, binary, plan_path = (Path(path).resolve(strict=True) for path in (source, binary, plan_path))
    require(sha256(source) == EXPECTED, 'exact_original_source_required')
    require(plan_path.is_relative_to(PRIVATE), 'private_source_bound_plan_required')
    plan = json.loads(plan_path.read_text())
    gids = checked_gids(plan)
    require(max_new_gids is None or type(max_new_gids) is int and max_new_gids > 0,
            'positive_batch_work_limit_required')
    locations = training(profile)
    output = private_directory(output)
    recipe = dict(source_sha256=EXPECTED, face_index=0, gids=gids, multiplier=15,
        plan_sha256=sha256(plan_path), profile=profile, training=locations,
        frozen_holdout=HOLDOUT, oracle_sha256=sha256(binary),
        driver_sha256=sha256(Path(__file__)), p7_driver_sha256=sha256(ROOT/'platform/p7_original_glyf.py'),
        dependencies=dependencies())
    recipe = json.loads(canonical(recipe))
    digest = digest_value(recipe)
    path = output/'batch-receipt.json'
    if path.exists():
        receipt = json.loads(path.read_text())
        require(receipt['recipe_sha256'] == digest and receipt['recipe'] == recipe,
                'batch_recipe_changed_use_fresh_output')
    else:
        require(not any(output.iterdir()), 'fresh_batch_output_required')
        receipt = dict(recipe=recipe, recipe_sha256=digest, rows={}, production_accepted=False)
        save_new(path, receipt)
    count, started = 0, time.monotonic()
    historical = (0, 2, 12, 1166, 2335, 19177)
    order = [gid for gid in historical if gid in gids]+[gid for gid in gids if gid not in historical]
    for gid in order:
        key = str(gid)
        if key in receipt['rows']:
            row = receipt['rows'][key]
            if row['status'] == 'ENCODED_EXPERIMENTAL':
                actual_gid, _, checkpoint = checked_model(output/f'gid-{gid:05d}')
                require(actual_gid == gid and checkpoint == row['sample_receipt_sha256'],
                        'completed_batch_GID_checkpoint_changed')
                continue
            if row['status'] == 'FAILED':
                continue
        if max_new_gids is not None and count >= max_new_gids:
            break
        directory = output/f'gid-{gid:05d}'
        receipt['rows'][key] = dict(status='RUNNING')
        replace_receipt(path, receipt)
        try:
            # Output contains scalar progress plus private failure/model context;
            # the caller keeps this entire directory local, never public CI.
            with (output/f'gid-{gid:05d}-execution.log').open('a') as log, contextlib.redirect_stdout(log):
                sample(source, binary, directory, [gid], 15, training_locations=locations)
            actual_gid, model, checkpoint = checked_model(directory)
            require(actual_gid == gid, 'built_model_GID_changed')
            glyph, tuples, hm, vm, report = model
            point_count = len(glyph.coordinates)
            receipt['rows'][key] = dict(status='ENCODED_EXPERIMENTAL', sample_receipt_sha256=checkpoint,
                tuple_count=len(tuples), point_count=point_count,
                outline_varies=any(any(x or y for x, y in item.coordinates[:point_count]) for item in tuples),
                metric_varies=any(any(x or y for x, y in item.coordinates[-4:]) for item in tuples),
                strict_outline_pass=report['max_outline_error_bound_source_units'] <= 1/32,
                strict_table_metric_pass=report['max_metric_error_source_units'] <= 1/32,
                max_outline_error=report['max_outline_error_bound_source_units'],
                max_table_metric_error=report['max_metric_error_source_units'],
                source_native_geometry_pass=report['native_geometry_validation'] == 'PASS_FINITE_APPLE_HVF',
                native_target_equivalence='NOT_RUN', continuous_proof=False, production_accepted=False)
        except Exception as error:
            receipt['rows'][key] = dict(status='FAILED', failure_category=type(error).__name__,
                                       private_failure_reason=str(error), production_accepted=False)
            with (output/f'gid-{gid:05d}-failure.log').open('a') as log:
                traceback.print_exc(file=log)
        count += 1
        receipt['summary'] = summarize(receipt['rows'], len(gids))
        receipt['last_invocation'] = dict(new_GIDs=count, seconds=time.monotonic()-started)
        replace_receipt(path, receipt)
        print(json.dumps(receipt['summary']), flush=True)
    require(sha256(source) == EXPECTED and sha256(plan_path) == recipe['plan_sha256'],
            'source_or_plan_changed_during_batch')
    return receipt


def face(source, batch, cache_receipt, output):
    batch = Path(batch).resolve(strict=True)
    require(batch.is_relative_to(PRIVATE), 'private_batch_required')
    receipt_path = batch/'batch-receipt.json'
    saved = json.loads(receipt_path.read_text())
    recipe = saved['recipe']
    require(saved['recipe_sha256'] == digest_value(recipe) and recipe['source_sha256'] == EXPECTED
            and recipe['driver_sha256'] == sha256(Path(__file__))
            and recipe['p7_driver_sha256'] == sha256(ROOT/'platform/p7_original_glyf.py')
            and all(sha256(Path(path)) == digest for path, digest in recipe['dependencies'].items()),
            'batch_source_or_code_changed')
    selected = {}
    for key, row in saved['rows'].items():
        if row['status'] != 'ENCODED_EXPERIMENTAL':
            continue
        gid, model, digest = checked_model(batch/f'gid-{int(key):05d}')
        require(gid == int(key) and digest == row['sample_receipt_sha256'], 'batch_model_changed')
        selected[gid] = model
    require(selected, 'no_variable_models_to_assemble')
    return assemble_verified_private_face(source, selected, multiplier=15, cache_receipt=cache_receipt,
                                          output=output, model_receipt=receipt_path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    command = sub.add_parser('run')
    command.add_argument('--source', type=Path, required=True)
    command.add_argument('--binary', type=Path, required=True)
    command.add_argument('--plan', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--max-new-gids', type=int)
    command.add_argument('--profile', choices=('p7', 'tensor5'), default='p7')
    command = sub.add_parser('face')
    command.add_argument('--source', type=Path, required=True)
    command.add_argument('--batch', type=Path, required=True)
    command.add_argument('--native-cache', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'run':
        run(args.source, args.binary, args.plan, args.output, max_new_gids=args.max_new_gids, profile=args.profile)
    else:
        face(args.source, args.batch, args.native_cache, args.output)
