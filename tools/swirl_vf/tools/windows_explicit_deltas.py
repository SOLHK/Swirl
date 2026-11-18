"""Expand IUP in an existing private candidate without refitting any geometry.

The decoded coefficient map is exactly preserved. This isolates the measured
DirectWrite IUP execution difference; it makes no private-font native claim.
fontTools' IUP decoder/writer remain external MIT-licensed dependencies.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import time
from itertools import product
import multiprocessing
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables._g_v_a_r import compileGlyph_
from fontTools.varLib.iup import iup_delta

from windows_font_builder import raw_table, FACE_PLAN, peak_rss, bounded_map
from windows_font_inventory import sha256
from windows_gvar import TAGS, require
from ttc_staging_pack import pack_collection


def shared_peaks():
    """All possible 3/5-node compiler peaks; unused entries are harmless.

    A different producer's peaks are embedded by fontTools automatically.
    This avoids a second whole-font scan and changes no region or delta.
    """
    records = [struct.pack('>hhh', *p) for p in product((-16384, -8192, 0, 8192, 16384), repeat=3) if any(p)]
    return b''.join(records), {p: i for i, p in enumerate(records)}


def expand_glyph(font, name, shared=None):
    base, control = font['glyf']._getCoordinatesAndControls(name, font['hmtx'].metrics, font['vmtx'].metrics)
    require(control.numberOfContours >= 0, 'expanded_simple_glyph_required')
    variations = font['gvar'].variations[name]
    inferred = 0
    for var in variations:
        inferred += sum(p is None for p in var.coordinates)
        points = np.asarray(iup_delta(var.coordinates, list(base), list(control.endPts)))
        require(points.shape == (len(base), 2) and np.isfinite(points).all()
                and np.array_equal(points, np.floor(points))
                and np.all(points >= -32768) and np.all(points <= 32767), 'IUP_did_not_reconstruct_integer_deltas')
        var.coordinates = [(int(x), int(y)) for x, y in points]
    data = compileGlyph_(2, variations, len(base), TAGS, shared or {}, optimizeSize=True)
    return data, len(variations), inferred


def face_key(font):
    digest = hashlib.sha256()
    for tag in ('glyf', 'gvar', 'hmtx', 'vmtx', 'fvar'):
        data = font.reader[tag]
        digest.update(tag.encode()+struct.pack('>I', len(data))+data)
    return digest.hexdigest()


def initialize_expander(path, face_index):
    global EXPAND_FONT, EXPAND_PEAKS
    EXPAND_FONT = TTFont(path, fontNumber=face_index, lazy=True)
    EXPAND_PEAKS = shared_peaks()[1]


def expand_worker(name):
    result = expand_glyph(EXPAND_FONT, name, EXPAND_PEAKS)
    del EXPAND_FONT['gvar'].variations[name]
    del EXPAND_FONT['glyf'].glyphs[name]
    return result


def encode_face(font, path, label, source=None, face_index=0, workers=1):
    started = time.monotonic()
    peaks, indices = shared_peaks()
    offsets, glyphs, tuples, inferred = [0], 0, 0, 0
    pool = None
    if workers > 1:
        require(source is not None, 'parallel_expansion_needs_source_path')
        pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn'),
                                   initializer=initialize_expander, initargs=(str(source), face_index))
        results = bounded_map(pool, expand_worker, font.getGlyphOrder(), workers*2)
    else:
        def sequential():
            for name in font.getGlyphOrder():
                yield expand_glyph(font, name, indices)
                del font['gvar'].variations[name]
                del font['glyf'].glyphs[name]
        results = sequential()
    try:
        with path.open('xb') as stream:
            for data, n, omitted in results:
                stream.write(data); offsets.append(stream.tell())
                glyphs += 1; tuples += n; inferred += omitted
                if glyphs % 1000 == 0:
                    print(json.dumps(dict(style=label, glyphs=glyphs, seconds=time.monotonic()-started)), flush=True)
    finally:
        if pool:
            pool.shutdown(wait=True, cancel_futures=True)
    start = 20+4*len(offsets)
    data = struct.pack('>HHHHIHHI', 1, 0, 3, len(indices), start, glyphs, 1, start+len(peaks))
    data += struct.pack('>'+str(len(offsets))+'I', *offsets)+peaks+path.read_bytes()
    return data, dict(glyphs=glyphs, tuples=tuples, expanded_points=inferred)


def cache_face(source, directory, workers=1):
    directory = directory.resolve()
    require(not any((p/'.git').exists() for p in (directory, *directory.parents)), 'private_cache_required')
    before = sha256(source)
    with TTFont(source, lazy=True) as font:
        key = face_key(font)
        output = directory/key
        output.mkdir(parents=True, exist_ok=False, mode=0o700)
        data, counts = encode_face(font, output/'body.private', source.name, source=source, workers=workers)
        (output/'gvar.private').write_bytes(data)
        require(sha256(source) == before, 'source_changed_during_cache')
        manifest = dict(schema=1, key=key, input_sha256=before, gvar_sha256=hashlib.sha256(data).hexdigest(), counts=counts)
        (output/'cache.json').write_text(json.dumps(manifest, indent=2))
    return manifest


def expand(args):
    started = time.monotonic()
    source, output = args.candidate.resolve(), args.output.resolve()
    require(not output.exists() and not any((p/'.git').exists() for p in (output, *output.parents)), 'fresh_private_output_required')
    report = json.loads((source.parent/'report.json').read_text())
    before = sha256(source)
    require(report['sha256'] == before, 'input_hash_mismatch')
    output.mkdir(parents=True, mode=0o700)
    encoded, paths, counts = {}, [], {}
    with TTCollection(source, lazy=True) as collection:
        require(len(collection.fonts) == 4, 'four_faces_required')
        for index, (_, label) in enumerate(FACE_PLAN):
            font = collection.fonts[index]
            font.recalcBBoxes, font.recalcTimestamp = False, False
            style = label.split()[1]
            if style not in encoded:
                key = face_key(font)
                cache = getattr(args, 'cache', None)
                cached = cache/key if cache else None
                if cached and (cached/'cache.json').exists():
                    manifest = json.loads((cached/'cache.json').read_text())
                    require(manifest['schema'] == 1 and manifest['key'] == key, 'cache_identity_mismatch')
                    require(sha256(cached/'gvar.private') == manifest['gvar_sha256'], 'cache_payload_mismatch')
                    encoded[style] = (cached/'gvar.private').read_bytes()
                    counts[style] = manifest['counts']
                else:
                    encoded[style], counts[style] = encode_face(font, output/(style+'.explicit-gvar.private'), style,
                        source=source, face_index=index, workers=getattr(args, 'workers', 1))
            # Preserve every table byte except the deliberate gvar expansion
            # and project fontRevision. Original proprietary tables were already
            # excluded by the source builder; this does not copy a reference.
            require('hvgl' not in font and 'CFF2' not in font, 'standard_candidate_required')
            for tag in list(font.reader.keys()):
                if tag not in ('gvar', 'head'):
                    font[tag] = raw_table(tag, font.reader[tag])
            font['gvar'] = raw_table('gvar', encoded[style])
            font['head'].fontRevision = .1
            destination = output/(label.replace(' ', '-')+'.ttf')
            font.save(destination)
            paths.append(destination)
    staging = output/'SwirlVF-test.ttc'
    packed = pack_collection(paths, staging)
    final = output/'SwirlVF.ttc'
    with staging.open('rb') as src, final.open('xb') as dst:
        shutil.copyfileobj(src, dst, 1024*1024)
    require(sha256(final) == sha256(staging) and sha256(source) == before, 'expanded_pack_changed')
    for style in ('Text', 'Display'):
        shutil.copyfile(source.parent/(style+'-glyph-report.json'), output/(style+'-glyph-report.json'))
    report.update(parent_candidate_sha256=before, sha256=sha256(final), bytes=final.stat().st_size,
                  status='BUILT_LOCAL_TEST_CANDIDATE', delta_encoding='EXPLICIT_NO_IUP', iup='DISABLED', coefficient_maps_preserved_exactly=True,
                  expansion=counts, expansion_seconds=time.monotonic()-started,
                  expansion_peak_rss_bytes=peak_rss(), packaging=packed,
                  Windows_DirectWrite='NOT_RUN', production_accepted=False)
    for row, path in zip(report['faces'], paths):
        row.update(bytes=path.stat().st_size, sha256=sha256(path))
    (output/'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ('bytes', 'sha256', 'expansion_seconds', 'expansion')}))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    inputs = p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--candidate', type=Path)
    inputs.add_argument('--cache-face', type=Path)
    p.add_argument('--cache', type=Path)
    p.add_argument('--workers', type=int, default=1)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    require(1 <= args.workers <= 6, 'invalid_worker_count')
    if args.cache_face:
        print(json.dumps(cache_face(args.cache_face, args.output, args.workers)))
    else:
        expand(args)
