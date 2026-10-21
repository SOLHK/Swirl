#!/usr/bin/env python3
"""Private original-HVF conversion experiment, NEVER a production admission.

Real source GIDs become standard glyf/gvar models. Existing source mapping,
native metric and 1/32 gates are not changed. Original data, model JSON, glyph
entries and experimental fonts must stay in the ignored private build root.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import io
import json
import os
from pathlib import Path
import sys

import numpy as np
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.TupleVariation import TupleVariation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from hvf import HVGL
from batch_geometry import BatchGeometry
from hvf_glyph_model import build_glyph_model
from source_metrics import SourceMetrics
from rebuild import normalized_grid, sha256, verify_serialized_face
from d2_hvf_faces import compare
from probe_axis_thresholds import hvf_events, TAGS
from calibrate_hvf_geometry import EXPECTED
from ttc_staging_pack import pack_collection

PRIVATE = ROOT.parents[1]/'build/vf-takeover-private'
CUSTOM = ('XWDT', 'XWGT', 'XHGT')
HOLDOUT = ((.125, -.375, .625), (-.6875, .8125, -.9375),
           (.123456789, -.7654321, .3456789), (.5, .25, -.5))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest_value(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def save_new(path, value):
    with Path(path).open('xb') as stream:
        stream.write(canonical(value)+b'\n')


def private_directory(path):
    path = Path(path).absolute()
    require(path.is_relative_to(PRIVATE) and path != PRIVATE, 'private_build_output_required')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink_output_refused')
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    return path


def replace_receipt(path, value):
    # Only our own recipe-bound receipt is replaced; font/model files use xb.
    temporary = path.with_name(path.name+f'.{os.getpid()}.tmp')
    save_new(temporary, value)
    os.replace(temporary, path)


def events_to_commands(events):
    """Retain native quadratics; no comparator canonicalization or tracing."""
    result, active = [], False
    names = {'move': ('moveTo', 3), 'line': ('lineTo', 3),
             'quad': ('qCurveTo', 5), 'cubic': ('curveTo', 7)}
    for event in events:
        kind = event[0]
        if kind == 'begin_path':
            require(not active, 'nested_native_contour')
            active = True
        elif kind in names:
            name, arity = names[kind]
            require(active and len(event) == arity, 'native_point_outside_contour_or_bad_arity')
            result.append([name, *event[1:]])
        elif kind == 'end_path':
            require(active, 'native_contour_end_without_begin')
            result.append(['closePath'])
            active = False
        elif kind not in ('begin_part', 'end_part', 'close', 'stop'):
            raise ValueError('unknown_native_event')
    require(not active, 'unclosed_native_contour')
    return result


def encode_model(model, recipe_hash):
    glyph, tuples, hm, vm, report = model
    return {'recipe_sha256': recipe_hash, 'glyph_id': report['glyph_id'],
        'points': list(map(list, glyph.coordinates)), 'flags': list(glyph.flags),
        'ends': list(glyph.endPtsOfContours),
        'tuples': [{'axes': item.axes, 'deltas': item.coordinates} for item in tuples],
        'hmtx': hm, 'vmtx': vm, 'report': report}


def decode_model(value):
    glyph = Glyph()
    glyph.numberOfContours = len(value['ends'])
    glyph.coordinates = GlyphCoordinates(value['points'])
    glyph.flags = array.array('B', value['flags'])
    glyph.endPtsOfContours = value['ends']
    from fontTools.ttLib.tables.ttProgram import Program
    glyph.program = Program(); glyph.program.fromBytecode([])
    glyph.recalcBounds(None)
    tuples = [TupleVariation({tag: tuple(v) for tag, v in item['axes'].items()},
                             [tuple(v) for v in item['deltas']]) for item in value['tuples']]
    return glyph, tuples, tuple(value['hmtx']), tuple(value['vmtx']), value['report']


def sample(source, binary, output, gids, multiplier):
    require(sys.platform == 'darwin', 'Apple_HVF_native_runtime_required')
    source, binary = Path(source).resolve(strict=True), Path(binary).resolve(strict=True)
    require(sha256(source) == EXPECTED, 'exact_original_source_required')
    require(gids and len(gids) <= 64 and len(set(gids)) == len(gids)
            and all(type(g) is int and 0 <= g < 47102 for g in gids), 'bounded_unique_original_GIDs_required')
    output = private_directory(output)
    dependencies = ('hvf', 'batch_geometry', 'tangent_geometry', 'transform_geometry',
                    'hvf_glyph_model', 'source_metrics', 'rebuild')
    recipe = {'source_sha256': EXPECTED, 'face_index': 0, 'gids': gids, 'multiplier': multiplier,
        'binary_sha256': sha256(binary), 'oracle_source_sha256': sha256(ROOT/'platform/hvf_oracle.c'),
        'driver_sha256': sha256(Path(__file__)),
        'code': {name: sha256(ROOT/'tools'/f'{name}.py') for name in dependencies},
        'training': normalized_grid(CUSTOM), 'holdout': [dict(zip(CUSTOM, p)) for p in HOLDOUT]}
    recipe_hash = digest_value(recipe)
    receipt_path = output/'receipt.json'
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        require(receipt['recipe'] == recipe and receipt['recipe_sha256'] == recipe_hash,
                'checkpoint_recipe_changed_use_new_output')
    else:
        receipt = {'recipe': recipe, 'recipe_sha256': recipe_hash, 'models': {}, 'native_samples': {},
                   'production_accepted': False, 'source_user_mapping_accepted': False}
        save_new(receipt_path, receipt)
    with TTCollection(source, lazy=True) as collection:
        require(len(collection.fonts) == 32, 'original_TTC_face_count_changed')
        font = collection.fonts[0]
        require(font['maxp'].numGlyphs == 47102 and tuple(a.axisTag for a in font['fvar'].axes)==TAGS,
                'original_face_identity_changed')
        table = HVGL(font.reader['hvgl'])
        metrics = SourceMetrics(font)
        locations = recipe['training']+recipe['holdout']
        for gid in gids:
            path = output/f'gid-{gid:05d}.json'
            if str(gid) in receipt['models']:
                require(sha256(path) == receipt['models'][str(gid)]['sha256'], 'saved_model_bytes_changed')
                continue
            require(not path.exists(), 'unconfirmed_model_exists_use_new_output')
            metric_records = []
            for loc in locations:
                m = metrics.at(gid, dict(zip(TAGS, (loc[tag] for tag in CUSTOM))))
                m['lsb'] = font['hmtx'].metrics[font.getGlyphOrder()[gid]][1]
                metric_records.append(m)
            model = build_glyph_model(table, gid, CUSTOM, recipe['training'], recipe['holdout'],
                metric_records, source_upem=font['head'].unitsPerEm,
                multiplier=multiplier, isolated_tangents=True)
            root = table.part(gid)
            batch = BatchGeometry(table, isolated_tangents=True).render(gid,
                np.asarray([[loc[tag] for tag in CUSTOM[:root.axis_count]] for loc in locations]))
            native_results = []
            for n, loc in enumerate(locations):
                design = dict(zip(TAGS, (loc[tag] for tag in CUSTOM)))
                native_path = output/f'gid-{gid:05d}-native-{n:02d}.json'
                key = f'{gid}:{n}'
                expected = receipt.setdefault('native_samples', {}).get(key)
                if expected is not None:
                    require(sha256(native_path)==expected, 'saved_native_sample_changed')
                    cached = json.loads(native_path.read_text())
                    require(cached['recipe_sha256']==recipe_hash and cached['source_q']==design
                            and cached['glyph_id']==gid, 'wrong_native_sample_checkpoint')
                    events = cached['events']
                else:
                    require(not native_path.exists(), 'unconfirmed_native_sample_exists')
                    events = hvf_events(binary, source, 0, gid, design)
                native_results.append(compare([p[n] for p in batch.paths], events))
                # Preserve source part hierarchy and actual events privately.
                if expected is None:
                    save_new(native_path, {'recipe_sha256': recipe_hash, 'source_q': design,
                        'glyph_id': gid, 'events': events, 'comparison': native_results[-1]})
                    receipt['native_samples'][key] = sha256(native_path)
                    replace_receipt(receipt_path, receipt)
            report = model[-1]
            report.update(native_geometry_validation='PASS_FINITE_APPLE_HVF' if all(
                r['combined_passed'] for r in native_results) else 'FAIL_FINITE_APPLE_HVF',
                native_samples=len(native_results), native_metric_values='NOT_EXTRACTED',
                model_method='C1_sample_reconstruction_not_direct_HVF_coefficient_translation',
                native_comparison=native_results)
            encoded = encode_model(model, recipe_hash)
            save_new(path, encoded)
            # Actual standard binary glyf entry, independently decoded again.
            glyf = newTable('glyf'); glyf.glyphs = {}; glyf.glyphOrder = []
            raw = model[0].compile(glyf)
            restored = Glyph(raw); restored.expand(glyf)
            if raw:
                require(restored.coordinates == model[0].coordinates
                        and restored.endPtsOfContours == model[0].endPtsOfContours,
                        'standard_glyf_roundtrip_changed_points')
            binary_path = output/f'gid-{gid:05d}.glyf'
            with binary_path.open('xb') as stream: stream.write(raw)
            receipt['models'][str(gid)] = {'sha256': sha256(path), 'glyf_sha256': sha256(binary_path),
                'point_count': report['target_design_unit_evidence']['point_count'],
                'contour_count': report['target_design_unit_evidence']['contour_count'],
                'tuple_count': len(model[1]), 'strict_sample_check_passed': report['strict_sample_check_passed'],
                'max_outline_error_source_units': report['max_outline_error_bound_source_units'],
                'native_geometry_validation': report['native_geometry_validation']}
            require(sha256(source) == EXPECTED, 'source_changed_during_native_sampling')
            replace_receipt(receipt_path, receipt)
            print(json.dumps({'stage': 'REAL_ORIGINAL_GID_STANDARD_GLYF_WRITTEN', 'gid': gid,
                **receipt['models'][str(gid)]}), flush=True)
    return receipt


def full_face(source, models_directory, cache_receipt, output):
    """Reuse prior real native defaults; never refill missing glyphs with blanks."""
    from hvf_experiment_face import assemble_experiment_face
    source = Path(source).resolve(strict=True)
    models_directory = Path(models_directory).resolve(strict=True)
    require(sha256(source)==EXPECTED, 'exact_original_source_required')
    saved = json.loads((models_directory/'receipt.json').read_text())
    require(saved['recipe']['source_sha256']==EXPECTED and saved['recipe']['face_index']==0,
            'wrong_model_source_identity')
    require(digest_value(saved['recipe'])==saved['recipe_sha256']
            and saved['recipe']['driver_sha256']==sha256(Path(__file__))
            and all(sha256(ROOT/'tools'/f'{name}.py')==digest
                    for name,digest in saved['recipe']['code'].items()),
            'model_code_or_recipe_changed')
    selected = {}
    for key, row in saved['models'].items():
        path = models_directory/f'gid-{int(key):05d}.json'
        require(sha256(path)==row['sha256'], 'model_changed_after_sampling')
        value = json.loads(path.read_text())
        require(value['recipe_sha256']==saved['recipe_sha256'] and value['glyph_id']==int(key),
                'wrong_model_recipe_or_GID')
        selected[int(key)] = decode_model(value)
    receipt_path = Path(cache_receipt).resolve(strict=True)
    cache = json.loads(receipt_path.read_text())
    native_path = receipt_path.with_name('hvf-outlines.jsonl')
    require(cache['status']=='EXTRACTED' and cache['input']['sha256']==EXPECTED
            and cache['input_unchanged'] is True and sha256(native_path)==cache['outline_sha256'],
            'original_native_default_cache_identity_failed')
    header = cache['native_header']
    require(header['face_index']==0 and header['normalized_coords']==[0,0,0]
            and header['start']==0 and header['count']==47102 and cache['counts']['outlines']==47102,
            'complete_face_zero_default_cache_required')
    output = private_directory(output)
    require(not any(output.iterdir()), 'fresh_face_output_required')
    def records():
        with native_path.open() as stream:
            for line in stream:
                value = json.loads(line)
                if value['record']=='outline':
                    require(value['status']=='OK' and value['native_code']==0, 'failed_cached_native_GID')
                    yield {'glyph_id': value['part_index'], 'commands': events_to_commands(value['events'])}
    with TTCollection(source, lazy=True) as collection:
        font, report = assemble_experiment_face(collection.fonts[0], records(), selected,
                                                multiplier=saved['recipe']['multiplier'])
        target = output/'P7-Original-face0-EXPERIMENTAL.ttf'
        font.save(target)
        verified_digest = sha256(target)
        with TTFont(target) as reopened:
            report['serialization'] = verify_serialized_face(font, reopened)
            require(reopened['cmap'].compile(reopened)==collection.fonts[0]['cmap'].compile(collection.fonts[0]),
                    'original_cmap_changed')
        require(sha256(target)==verified_digest and sha256(source)==EXPECTED,
                'source_or_verified_candidate_changed')
        def verify(candidate):
            with TTCollection(candidate) as packed:
                require(len(packed.fonts)==1, 'experimental_face_count_changed')
                verify_serialized_face(font, packed.fonts[0])
        report['packing'] = pack_collection([target], output/'P7-Original-face0-EXPERIMENTAL.ttc',
            expected_sha256=[verified_digest], validate=verify)
        report.update(source_sha256=EXPECTED, model_receipt_sha256=sha256(models_directory/'receipt.json'),
                      native_default_cache_sha256=cache['outline_sha256'], candidate_sha256=verified_digest)
        save_new(output/'face-report.json', report)
        font.close()
    print(json.dumps({'stage':'REAL_ORIGINAL_EXPERIMENTAL_FACE_WRITTEN',
                      'candidate_sha256': verified_digest, 'production_accepted':False}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    p = sub.add_parser('sample')
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--gids', default='0,2,12,1166,19177')
    p.add_argument('--multiplier', type=int, default=15)
    p = sub.add_parser('face')
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--models', type=Path, required=True)
    p.add_argument('--native-cache', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode=='sample':
        sample(args.source, args.binary, args.output, [int(v) for v in args.gids.split(',')], args.multiplier)
    else:
        full_face(args.source, args.models, args.native_cache, args.output)
