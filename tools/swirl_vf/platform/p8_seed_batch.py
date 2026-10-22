#!/usr/bin/env python3
"""Copy verified private P8 checkpoints into a larger existing batch plan.

No extraction, model change, font publication, deletion or overwrite occurs.
Only a target batch receipt is updated after an exclusive per-GID copy passes
the existing checked_model gate. Interrupted copies remain uncounted and must
be reviewed; a subsequent invocation refuses an orphaned destination directory.

PRECONDITION: the target batch runner and every other seeder must be stopped
for the entire operation. This command requires exclusive target ownership.
Receipt SHA checks detect changes but are not an atomic shared-writer lock;
the frozen P8 runner does not participate in a seeder-only lock protocol.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re

from p7_original_glyf import (ROOT, PRIVATE, EXPECTED, CUSTOM, HOLDOUT, canonical,
    digest_value, private_directory, replace_receipt, sha256)
from p8_batch_original import checked_model, dependencies, summarize, training
from rebuild import normalized_grid


def require(value, reason):
    if not value:
        raise ValueError(reason)


def _hash(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value), 'bound_SHA256_required')
    return value


def _private_existing(path):
    path = Path(path).absolute()
    require(path.is_dir() and not path.is_symlink() and '..' not in path.parts
            and not any(p.is_symlink() for p in path.parents), 'existing_private_batch_required')
    require(path.resolve().is_relative_to(PRIVATE.resolve()) and path.resolve() != PRIVATE.resolve(),
            'existing_private_batch_required')
    return private_directory(path)


def _json(path):
    require(path.is_file() and not path.is_symlink(), 'regular_checkpoint_file_required')
    data = path.read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def _receipt(directory, *, completed):
    receipt, digest = _json(directory/'batch-receipt.json')
    recipe, rows = receipt.get('recipe'), receipt.get('rows')
    require(type(recipe) is dict and receipt.get('recipe_sha256') == digest_value(recipe)
            and recipe.get('source_sha256') == EXPECTED and type(recipe.get('face_index')) is int
            and recipe['face_index'] == 0 and type(recipe.get('multiplier')) is int
            and recipe['multiplier'] >= 1, 'source_bound_batch_recipe_required')
    gids = recipe.get('gids')
    require(type(gids) is list and gids and len(gids) <= 47102
            and all(type(gid) is int and 0 <= gid < 47102 for gid in gids)
            and len(set(gids)) == len(gids), 'unique_original_GIDs_required')
    _hash(recipe.get('plan_sha256')); _hash(recipe.get('oracle_sha256'))
    require(recipe.get('driver_sha256') == sha256(ROOT/'platform/p8_batch_original.py')
            and recipe.get('p7_driver_sha256') == sha256(ROOT/'platform/p7_original_glyf.py')
            and canonical(recipe.get('dependencies')) == canonical(dependencies())
            and recipe.get('profile') in ('p7', 'tensor5')
            and canonical(recipe.get('training')) == canonical(training(recipe['profile']))
            and canonical(recipe.get('frozen_holdout')) == canonical(HOLDOUT),
            'batch_code_or_training_contract_changed')
    require(type(rows) is dict and set(rows) <= set(map(str, gids))
            and all(type(row) is dict and row.get('status') in ('ENCODED_EXPERIMENTAL', 'FAILED')
                    for row in rows.values())
            and (not completed or set(rows) == set(map(str, gids))), 'finished_batch_rows_required')
    require(receipt.get('production_accepted') is False, 'experimental_batch_without_acceptance_required')
    require(type(receipt.get('seed_provenance', [])) is list, 'invalid_seed_provenance')
    return receipt, digest


def _checkpoint(directory, gid, batch_recipe, row):
    require(directory.is_dir() and not directory.is_symlink(), 'regular_GID_directory_required')
    receipt, digest = _json(directory/'receipt.json')
    require(digest == _hash(row.get('sample_receipt_sha256')), 'GID_receipt_bytes_changed')
    recipe = receipt.get('recipe')
    locations = training(batch_recipe['profile'])
    locations = normalized_grid(CUSTOM) if locations is None else locations
    code_names = ('hvf', 'batch_geometry', 'tangent_geometry', 'transform_geometry',
                  'hvf_glyph_model', 'source_metrics', 'rebuild')
    require(type(recipe) is dict and receipt.get('recipe_sha256') == digest_value(recipe)
            and recipe.get('source_sha256') == EXPECTED and type(recipe.get('face_index')) is int
            and recipe['face_index'] == 0 and type(recipe.get('gids')) is list
            and len(recipe['gids']) == 1 and type(recipe['gids'][0]) is int and recipe['gids'] == [gid]
            and type(recipe.get('multiplier')) is int and recipe['multiplier'] == batch_recipe['multiplier']
            and recipe.get('binary_sha256') == batch_recipe['oracle_sha256']
            and recipe.get('driver_sha256') == batch_recipe['p7_driver_sha256']
            and recipe.get('oracle_source_sha256') == sha256(ROOT/'platform/hvf_oracle.c')
            and canonical(recipe.get('code')) == canonical({name: sha256(ROOT/'tools'/f'{name}.py') for name in code_names})
            and canonical(recipe.get('training')) == canonical(locations)
            and canonical(recipe.get('holdout')) == canonical([dict(zip(CUSTOM, p)) for p in HOLDOUT]),
            'per_GID_batch_contract_changed')
    models, native = receipt.get('models'), receipt.get('native_samples')
    require(type(models) is dict and set(models) == {str(gid)}
            and type(native) is dict and set(native) == {f'{gid}:{i}' for i in range(len(locations)+len(HOLDOUT))},
            'complete_single_GID_checkpoint_required')
    manifest = {'receipt.json': digest, f'gid-{gid:05d}.json': _hash(models[str(gid)]['sha256']),
                f'gid-{gid:05d}.glyf': _hash(models[str(gid)]['glyf_sha256'])}
    manifest.update({f'gid-{gid:05d}-native-{i:02d}.json': _hash(native[f'{gid}:{i}'])
                     for i in range(len(locations)+len(HOLDOUT))})
    require(set(path.name for path in directory.iterdir()) == set(manifest)
            and all((directory/name).is_file() and not (directory/name).is_symlink() for name in manifest),
            'exact_regular_checkpoint_file_set_required')
    actual_gid, model, actual_digest = checked_model(directory)
    require(actual_gid == gid and actual_digest == digest, 'verified_GID_identity_changed')
    glyph, tuples, _, _, report = model
    count = len(glyph.coordinates)
    require(all(type(report.get(field)) in (int, float) and math.isfinite(report[field]) and report[field] >= 0
                for field in ('max_outline_error_bound_source_units', 'max_metric_error_source_units')),
            'finite_model_error_required')
    expected = dict(status='ENCODED_EXPERIMENTAL', sample_receipt_sha256=digest,
        tuple_count=len(tuples), point_count=count,
        outline_varies=any(any(x or y for x, y in item.coordinates[:count]) for item in tuples),
        metric_varies=any(any(x or y for x, y in item.coordinates[-4:]) for item in tuples),
        strict_outline_pass=report['max_outline_error_bound_source_units'] <= 1/32,
        strict_table_metric_pass=report['max_metric_error_source_units'] <= 1/32,
        max_outline_error=report['max_outline_error_bound_source_units'],
        max_table_metric_error=report['max_metric_error_source_units'],
        source_native_geometry_pass=report['native_geometry_validation'] == 'PASS_FINITE_APPLE_HVF',
        native_target_equivalence='NOT_RUN', continuous_proof=False, production_accepted=False)
    require(canonical(row) == canonical(expected), 'batch_row_disagrees_with_verified_model')
    return manifest


def seed_batch(source_batch, target_batch):
    source, target = map(_private_existing, (source_batch, target_batch))
    require(source != target and not source.is_relative_to(target) and not target.is_relative_to(source),
            'separate_non_nested_batches_required')
    old, source_digest = _receipt(source, completed=True)
    saved, target_digest = _receipt(target, completed=False)
    strip = lambda recipe: {key: value for key, value in recipe.items() if key not in ('gids', 'plan_sha256')}
    require(canonical(strip(old['recipe'])) == canonical(strip(saved['recipe']))
            and set(old['recipe']['gids']) <= set(saved['recipe']['gids']), 'matching_subset_batch_contract_required')
    # Check every existing target model before creating any copied directory.
    for key, row in saved['rows'].items():
        if row['status'] == 'ENCODED_EXPERIMENTAL':
            _checkpoint(target/f'gid-{int(key):05d}', int(key), saved['recipe'], row)
    selected = [(int(key), row) for key, row in old['rows'].items() if row['status'] == 'ENCODED_EXPERIMENTAL']
    for gid, _ in selected:
        row = saved['rows'].get(str(gid))
        require(row is None or row['status'] == 'ENCODED_EXPERIMENTAL', 'existing_target_row_conflicts_with_seed')
        destination = target/f'gid-{gid:05d}'
        require(row is not None or not destination.exists() and not destination.is_symlink(),
                'orphan_or_interrupted_target_GID_copy')
    provenance = dict(source_batch_receipt_sha256=source_digest,
        source_recipe_sha256=old['recipe_sha256'], target_initial_receipt_sha256=target_digest,
        copied_GIDs=[], native_calls=0, production_accepted=False)
    for gid, row in sorted(selected):
        manifest = _checkpoint(source/f'gid-{gid:05d}', gid, old['recipe'], row)
        if str(gid) in saved['rows']:
            continue
        destination = target/f'gid-{gid:05d}'
        destination.mkdir(mode=0o700, exist_ok=False)
        for name, digest in manifest.items():
            data = (source/f'gid-{gid:05d}'/name).read_bytes()
            require(hashlib.sha256(data).hexdigest() == digest, 'source_checkpoint_changed_during_copy')
            with (destination/name).open('xb') as stream:
                stream.write(data)
        _checkpoint(destination, gid, saved['recipe'], row)
        require(sha256(source/'batch-receipt.json') == source_digest
                and sha256(target/'batch-receipt.json') == target_digest, 'batch_receipt_changed_during_seed')
        saved['rows'][str(gid)] = copy.deepcopy(row)
        if not provenance['copied_GIDs']:
            saved.setdefault('seed_provenance', []).append(provenance)
        provenance['copied_GIDs'].append(gid)
        saved['summary'] = summarize(saved['rows'], len(saved['recipe']['gids']))
        replace_receipt(target/'batch-receipt.json', saved)
        target_digest = sha256(target/'batch-receipt.json')
    require(sha256(source/'batch-receipt.json') == source_digest
            and sha256(target/'batch-receipt.json') == target_digest, 'batch_receipt_changed_during_seed')
    return saved


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-batch', required=True, type=Path)
    parser.add_argument('--target-batch', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(seed_batch(args.source_batch, args.target_batch)['summary']))
