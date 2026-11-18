"""Export local Apple references; never uploads data or generates a target font.

Full default coverage reuses a verified hvf_coverage checkpoint. Independent
variation requests use the same Apple C oracle with one renderer per face.
All coordinates and raw avar records are restricted local research data.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import itertools
import json
from pathlib import Path
import platform
import random
import shutil
import struct
import subprocess
import sys
import time

import numpy as np
from fontTools.ttLib import TTCollection
from fontTools.ttLib.sfnt import calcChecksum

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from batch_geometry import BatchGeometry
from handoff_bundle import digest, read_rows, write_json, write_rows, require
from hvf import HVGL
from source_metrics import SourceMetrics
from target_axis_mapping import axes_from_font, source_axis_plan, CANDIDATE, FLAGS
from windows_font_inventory import inspect
from hvf_coverage import checked_chunk
from hvf_transcript import validate_events
from diagnose_path_types import raw_portable_paths, raw_native_paths, compare_preserved_quadratics

FACE_PLAN = ((0, 'SC Text'), (5, 'SC Display'), (1, 'TC Text'), (6, 'TC Display'))
SAMPLE_TEXT = '中文简体繁體漢字龍鬱龜测试測試字体字體永國国你好世界，。！？：；、（）「」—… ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
SOURCE_SHA = '39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'


def compare(paths, events):
    """Compare all original quadratic controls; preserve ordered contours/winding.

    Cyclic starting-point changes are allowed, reversal is not. The legacy
    tested comparator handles any line/quad correspondence. No curve fitting,
    quantization, point deletion or relaxed tolerance occurs in this export.
    """
    native = raw_native_paths(events)
    if len(native) != len(paths):
        return {'status': 'FAILED', 'reason': 'contour_count_differs'}
    maximum = 0.
    for original, path in zip(paths, native):
        if len(original) != 2*len(path) or any(s.kind != 'Q' for s in path):
            result = compare_preserved_quadratics(raw_portable_paths(paths), native)
            return {'status': 'PASS' if result['status'] == 'within_budget' else 'FAILED',
                    'maximum_control_coordinate_error': result['maximum_point_error'],
                    'method': 'existing_preserved_comparator', 'detail': result}
        points = np.asarray([p for segment in path for p in segment.points[:2]], dtype=float)
        # Retain native end points too; a non-closing end point is not discarded.
        for i, segment in enumerate(path):
            require(tuple(segment.points[2]) == tuple(path[(i+1) % len(path)].points[0]),
                    'native_quadratic_endpoint_discontinuity')
        error = min((float(np.abs(np.roll(points, 2*i, axis=0)-original).max())
                     for i in range(len(path))), default=0.)
        maximum = max(maximum, error)
    return {'status': 'PASS' if maximum <= 1/32 else 'FAILED',
            'maximum_control_coordinate_error': maximum, 'method': 'all_quadratic_controls_cyclic_forward',
            'euclidean_curve_bound': float(np.sqrt(2)*maximum)}


def font_integrity(source):
    """Inspect physical directories, bounds, exact sharing and both head sums.

    TTCs in this source store the literal head checksum including adjustment.
    Record both conventions; do not call a fontTools zero-adjustment warning
    source corruption, or silently rewrite the original file.
    """
    size = source.stat().st_size
    with source.open('rb') as stream:
        header = stream.read(12)
        require(header[:4] == b'ttcf', 'TTC_required')
        version, count = struct.unpack('>II', header[4:])
        require(version in (0x10000, 0x20000) and 0 < count <= 4096, 'unsupported_TTC_header')
        offsets = struct.unpack('>'+str(count)+'I', stream.read(4*count))
        spans, checked, failures, conventions = {}, {}, [], Counter()
        directories = [(0, 12+4*count+(12 if version == 0x20000 else 0))]
        for face, offset in enumerate(offsets):
            stream.seek(offset); directory = stream.read(12)
            require(len(directory) == 12, 'truncated_face')
            n = struct.unpack_from('>H', directory, 4)[0]
            require(n > 0 and offset+12+16*n <= size, 'truncated_table_directory')
            directories.append((offset, offset+12+16*n))
            tags = set()
            for _ in range(n):
                tag, checksum, start, length = struct.unpack('>4sIII', stream.read(16))
                require(tag not in tags and start % 4 == 0 and start+length <= size, 'invalid_table_directory')
                tags.add(tag); key = (start, length)
                spans[key] = True
                if key in checked:
                    require(checked[key]['stored'] == checksum, 'shared_table_checksum_disagrees')
                    continue
                where = stream.tell(); stream.seek(start); data = stream.read(length); stream.seek(where)
                literal = calcChecksum(data)
                zero = calcChecksum(data[:8]+bytes(4)+data[12:]) if tag == b'head' else literal
                mode = 'literal' if literal == checksum else 'head_zero_adjustment' if tag == b'head' and zero == checksum else 'FAILED'
                conventions[mode] += 1
                checked[key] = {'stored': checksum, 'literal': literal, 'head_zero_adjustment': zero}
                if mode == 'FAILED': failures.append({'face': face, 'table': tag.decode('ascii')})
        intervals = sorted([(a, a+b) for a, b in spans] + directories)
        require(all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])), 'partial_table_or_directory_overlap')
    return {'status': 'PASS' if not failures else 'FAILED', 'face_count': count,
            'unique_table_ranges': len(checked), 'checksum_conventions': dict(conventions),
            'checksum_failures': failures, 'bounds_and_sharing': 'PASS',
            'head_zero_adjustment_mismatches': sum(v['stored'] != v['head_zero_adjustment'] for v in checked.values()),
            'sha256': digest(source), 'bytes': size}


def catalog(source, output):
    inventory = inspect(source)
    write_json(output/'source-inventory.json', inventory)
    integrity = font_integrity(source)
    write_json(output/'source-integrity.json', integrity)
    require(integrity['status'] == 'PASS', 'source_integrity_failed')
    with TTCollection(source, lazy=True) as collection:
        first = collection.fonts[0]
        hvgl = HVGL(first.reader['hvgl'])
        structure = hvgl.validate()
        write_json(output/'hvf-structure.json', structure)
        result = {'schema': 1, 'glyph_count': first['maxp'].numGlyphs, 'faces': [],
                  'geometry_units': 'original font units; divide by each face UPM for em geometry',
                  'design_axis_order': ['WDTH', 'wght', 'HGHT'],
                  'user_mapping_candidate': CANDIDATE, **FLAGS}
        for index, label in FACE_PLAN:
            font = collection.fonts[index]
            require(font.reader['hvgl'] == first.reader['hvgl'] and 'hvpm' not in font,
                    'geometry_sharing_not_proven')
            require(font['maxp'].numGlyphs == result['glyph_count'], 'face_glyph_count_differs')
            axes = axes_from_font(font)
            metrics = SourceMetrics(font)
            codes = {}
            for cp, name in font.getBestCmap().items():
                codes.setdefault(name, []).append(cp)
            index_name = f'indices/face-{index}.jsonl.gz'
            rows = ({'gid': gid, 'name': name, 'unicode': codes.get(name, []),
                     'default_metrics': metrics.at(gid, dict.fromkeys(result['design_axis_order'], 0.))}
                    for gid, name in enumerate(font.getGlyphOrder()))
            write_rows(output/index_name, rows)
            uvs = [{'selector': selector, 'entries': entries} for table in font['cmap'].tables
                   if table.format == 14 for selector, entries in table.uvsDict.items()]
            write_json(output/f'indices/face-{index}-uvs.json', uvs)
            row = {'source_index': index, 'target_label': 'SwirlVF '+label,
                   'source_postscript': font['name'].getDebugName(6), 'version': font['name'].getDebugName(5),
                   'upm': font['head'].unitsPerEm, 'glyph_index': index_name,
                   'unicode_count': len(font.getBestCmap()), 'uvs': f'indices/face-{index}-uvs.json',
                   'raw_axes': [asdict(axis) for axis in axes], 'inventory_face': index,
                   'geometry_reference_source_face': 0, 'sharing_basis': 'byte-identical hvgl; no hvpm; same maxp and design axis order',
                   'named_weights': {name: {'source_user_wght': value,
                       'candidate_design_q': source_axis_plan(next(a for a in axes if a.tag == 'wght'), value)['source_q'],
                       'mapping_accepted': False} for name, value in
                       [('Light', 300), ('Regular', 400), ('Medium', 500), ('Semibold', 600), ('Bold', 700)]}}
            result['faces'].append(row)
        write_json(output/'catalog.json', result)
    return result


def default_export(source, checkpoint_dir, output):
    checkpoint = json.loads((checkpoint_dir/'checkpoint.json').read_text())
    recipe = checkpoint['recipe']
    require(recipe['source_sha256'] == digest(source) and recipe['positions'] == [[0., 0., 0.]]
            and recipe['face_index'] == 0 and checkpoint['summary']['status'] == 'EXTRACTED_FINITE_DESIGN_GRID',
            'complete_default_native_checkpoint_required')
    receipt = {'scope': 'all_source_GIDs_at_design_zero', 'passed': 0, 'failed': 0,
               'maximum_control_coordinate_error': 0., 'failures': [], 'empty_gids': [],
               'native_recipe': recipe, 'continuous_space_acceptance': False}
    chunks = []
    with TTCollection(source, lazy=True) as collection:
        renderer = BatchGeometry(HVGL(collection.fonts[0].reader['hvgl']), isolated_tangents=True)
        for key, evidence in checkpoint['rows'].items():
            start = int(key.split('-g')[1]); count = min(recipe['batch_size'], recipe['glyph_count']-start)
            actual = checked_chunk(checkpoint_dir/key, recipe, [0., 0., 0.], start, count)
            require(actual == evidence and actual['status'] == 'EXTRACTED', 'native_checkpoint_changed')
            def rows():
                with (checkpoint_dir/key/'hvf-outlines.jsonl').open() as stream:
                    for line in stream:
                        native = json.loads(line)
                        if native.get('record') != 'outline': continue
                        gid = native['part_index']; root = renderer.table.part(gid)
                        batch = renderer.render(gid, [np.zeros(root.axis_count)])
                        paths = [p[0] for p in batch.paths]
                        result = compare(paths, native['events'])
                        receipt['passed' if result['status'] == 'PASS' else 'failed'] += 1
                        if result['status'] != 'PASS': receipt['failures'].append({'gid': gid, **result})
                        error = result.get('maximum_control_coordinate_error')
                        if error is not None: receipt['maximum_control_coordinate_error'] = max(receipt['maximum_control_coordinate_error'], error)
                        if not paths: receipt['empty_gids'].append(gid)
                        yield {'gid': gid, 'design': [0., 0., 0.], 'paths': [p.tolist() for p in paths],
                               'topology': [len(p) for p in paths], 'contour_sources': [asdict(s) for s in batch.sources],
                               'apple_native': native, 'comparison': result}
            path = f'defaults/g{start:05d}.jsonl.gz'
            entry = write_rows(output/path, rows())
            require(entry['rows'] == count, 'export_default_count_differs')
            chunks.append({'path': path, 'start': start, 'count': count})
            print(json.dumps({'default_completed': receipt['passed']+receipt['failed'], 'failed': receipt['failed']}), flush=True)
    write_json(output/'default-validation.json', receipt)
    return chunks


def sample_plan(source):
    with TTCollection(source, lazy=True) as collection:
        gids = {0, 1166, 19177, 35045, 14813, 40149, 27986, 13858, 16171}
        for face, _ in FACE_PLAN:
            font = collection.fonts[face]; cmap = font.getBestCmap()
            gids.update(font.getGlyphID(cmap[ord(c)]) for c in SAMPLE_TEXT if ord(c) in cmap)
        glyph_seed, validation_seed = 2026110331, 2026110337
        gids.update(random.Random(glyph_seed).sample(range(collection.fonts[0]['maxp'].numGlyphs), 48))
    training = [list(p) for p in itertools.product((-1., 0., 1.), repeat=3)]
    rng = random.Random(validation_seed)
    validation = [[rng.uniform(-1, 1) for _ in range(3)] for _ in range(20)]
    # Independent noninteger single/pair axes and both sides of root branch zero.
    for axes in itertools.chain(itertools.combinations(range(3), 1), itertools.combinations(range(3), 2)):
        p = [0., 0., 0.]
        for axis in axes: p[axis] = (axis+1)*0.1732050807568877
        validation.append(p)
    for sign in (-1, 1):
        validation += [[sign*2**-30, -.2718281828459, .3141592653589],
                       [sign*(1-2**-30), .123456789, -.6180339887499]]
    require(not set(map(tuple, training)) & set(map(tuple, validation)), 'training_validation_overlap')
    return {'glyph_seed': glyph_seed, 'validation_seed': validation_seed, 'gids': sorted(gids),
            'training': training, 'validation': validation, 'continuous_space_acceptance': False,
            'branch_scope': 'root-zero neighborhoods and fixed noninteger combinations; not exhaustive nested clamp boundaries'}


def variations(source, binary, output, plan):
    require(platform.system() == 'Darwin', 'native_export_requires_macOS')
    receipt = {'scope': 'finite_independent_design_samples', 'passed': 0, 'failed': 0,
               'maximum_control_coordinate_error': 0., 'failures': [], 'faces': {},
               'source_sha256': digest(source), 'oracle_sha256': digest(binary),
               'oracle_code_sha256': digest(Path(__file__).with_name('hvf_oracle.c')),
               'continuous_space_acceptance': False, 'coretext_user_mapping_acceptance': False}
    with TTCollection(source, lazy=True) as collection:
        for face, _ in FACE_PLAN:
            font = collection.fonts[face]; renderer = BatchGeometry(HVGL(font.reader['hvgl']), isolated_tangents=True)
            metrics = SourceMetrics(font); face_count = 0
            for cohort in plan.get('cohorts', ('training', 'validation')):
                requests = (plan[cohort+'_requests'] if cohort+'_requests' in plan else
                            [(gid, q) for q in plan[cohort] for gid in plan['gids']])
                request_file = output/f'variations/face-{face}-{cohort}.requests.txt'
                request_file.parent.mkdir(exist_ok=True)
                with request_file.open('x') as stream:
                    for gid, q in requests: stream.write(str(gid)+' '+','.join(map(repr, q))+'\n')
                with request_file.open() as inp, (request_file.with_suffix('.stderr.log')).open('x') as err:
                    process = subprocess.Popen([str(binary), str(source), str(face), 'requests'],
                                               stdin=inp, stdout=subprocess.PIPE, stderr=err, text=True)
                    def rows():
                        header = json.loads(process.stdout.readline())
                        require(header.get('request_stream') is True and header.get('face_index') == face
                                and header.get('engine') == 'Apple HVF' and header.get('input_bytes') == source.stat().st_size
                                and header.get('fvar_axis_tags') == ['WDTH', 'wght', 'HGHT'], 'native_stream_header_differs')
                        write_json(output/f'variations/face-{face}-{cohort}.native-header.json', header)
                        for index, (gid, q) in enumerate(requests):
                            row = json.loads(process.stdout.readline())
                            require(row.get('request_index') == index and row.get('part_index') == gid
                                    and row.get('normalized_coords') == q and row.get('status') == 'OK'
                                    and row.get('native_code') == 0 and row.get('applied_axis_count') == row.get('part_axis_count'),
                                    'native_request_response_mismatch')
                            validate_events(row['events'], row['counters'], header['hvf_total_parts'])
                            root = renderer.table.part(gid)
                            batch = renderer.render(gid, [q[:root.axis_count]])
                            paths = [p[0] for p in batch.paths]
                            result = compare(paths, row['events'])
                            receipt['passed' if result['status'] == 'PASS' else 'failed'] += 1
                            if result['status'] != 'PASS': receipt['failures'].append({'face': face, 'gid': gid, 'design': q, **result})
                            error = result.get('maximum_control_coordinate_error')
                            if error is not None: receipt['maximum_control_coordinate_error'] = max(receipt['maximum_control_coordinate_error'], error)
                            yield {'gid': gid, 'face': face, 'design': q, 'cohort': cohort,
                                   'paths': [p.tolist() for p in paths], 'topology': [len(p) for p in paths],
                                   'metrics': metrics.at(gid, dict(zip(('WDTH', 'wght', 'HGHT'), q))),
                                   'apple_native': row, 'comparison': result}
                        final = json.loads(process.stdout.readline())
                        require(final.get('record') == 'summary' and final.get('rendered') == len(requests)
                                and final.get('failed') == 0 and final.get('status') == 'EXTRACTED'
                                and process.stdout.read() == '' and process.wait(timeout=30) == 0, 'native_stream_incomplete')
                    try:
                        write_rows(output/f'variations/face-{face}-{cohort}.jsonl.gz', rows())
                    finally:
                        process.stdout.close()
                        if process.poll() is None: process.kill(); process.wait()
                face_count += len(requests)
                print(json.dumps({'face': face, 'cohort': cohort, 'native_samples': len(requests), 'failed_total': receipt['failed']}), flush=True)
            receipt['faces'][str(face)] = face_count
    write_json(output/'variation-validation.json', receipt)


def run(args):
    require(platform.system() == 'Darwin', 'export_requires_macOS')
    source = args.source.resolve(strict=True); output = args.output.absolute()
    require(digest(source) == SOURCE_SHA, 'source_identity_differs')
    require(not output.exists() and not output.is_symlink()
            and not any((p/'.git').exists() for p in (output, *output.parents)), 'fresh_output_outside_git_required')
    output.mkdir(parents=True, mode=0o700)
    tick = time.monotonic()
    (output/'source').mkdir(); shutil.copyfile(source, output/'source/PingFangUI.ttc')
    require(digest(output/'source/PingFangUI.ttc') == SOURCE_SHA, 'source_copy_changed')
    catalog(source, output)
    write_json(output/'reference-inventory.json', inspect(args.reference, census=True))
    chunks = default_export(source, args.defaults, output)
    plan = sample_plan(source); write_json(output/'sampling-plan.json', plan)
    variations(source, args.oracle, output, plan)
    require(digest(source) == SOURCE_SHA, 'source_changed_during_export')
    write_json(output/'package.json', {'schema': 1, 'version': 'mac-handoff-0.1',
               'source': {'path': 'source/PingFangUI.ttc', 'sha256': SOURCE_SHA}, 'catalog': 'catalog.json',
               'defaults': sorted(chunks, key=lambda c: c['start']), 'export_seconds': time.monotonic()-tick,
               'host': platform.platform(), 'native_metrics': 'NOT_VERIFIED_BY_CORETEXT',
               'user_axis_mapping': 'CANDIDATE_ONLY', 'continuous_space_acceptance': False,
               'default_geometry_sharing': 'four byte-identical hvgl tables, source design zero only; em scale differs',
               'private_research_only': True})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'reference', 'defaults', 'oracle', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    run(p.parse_args())
