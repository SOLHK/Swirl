#!/usr/bin/env python3
"""Authored q-space controls, never a converted Apple font or delivery file.

The two TTCs differ only in fvar/axis names. Their standard outline and metric
variation bytes are identical. The normalized reference uses custom tags;
registered wght is never assigned an invalid negative user scale.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

from fontTools.ttLib import TTCollection, TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rebuild_c1_fixture import make_face
from rebuild import sha256, verify_collection_tables
from target_axis_mapping import axis_transport, SourceAxis, TAGS
from ttc_staging_pack import pack_collection

ORDER = ('WDTH', 'wght', 'HGHT')
REFERENCE = ('XWDT', 'XWGT', 'XHGT')
IDENTITY = ((-16384, -16384), (0, 0), (16384, 16384))
WEIGHT_RANGES = ((100, 499, 900), (100, 500, 600), (100, 500, 900), (100, 501, 900))


def authored_axes():
    return {face: {'WDTH': (1, 500, 1000), 'wght': WEIGHT_RANGES[face % 4],
                   'HGHT': (1, 500, 1000)} for face in range(32)}


def authored_control_face(face, axes, *, normalized):
    font = make_face(face)
    tags = REFERENCE if normalized else ORDER
    for axis, source_tag, tag in zip(font['fvar'].axes, ORDER, tags):
        axis.axisTag = tag
        axis.minValue, axis.defaultValue, axis.maxValue = (
            (-1, 0, 1) if normalized else axes[source_tag])
    font['fvar'].instances = []
    del font['STAT']
    font['avar'].segments = {tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in tags}
    if normalized:
        rename = dict(zip(ORDER, REFERENCE))
        for tuples in font['gvar'].variations.values():
            for variation in tuples:
                variation.axes = {rename[tag]: value for tag, value in variation.axes.items()}
    return font


def write_controls(output, axes_by_face=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    axes_by_face = authored_axes() if axes_by_face is None else axes_by_face
    if set(axes_by_face) != set(range(32)):
        raise ValueError('all_32_axis_profiles_required')
    paths = {'normalized': [], 'transported': []}
    for face in range(32):
        for kind in paths:
            font = authored_control_face(face, axes_by_face[face], normalized=kind == 'normalized')
            path = output / f'{kind}-{face:02d}.ttf'
            with path.open('xb') as stream:
                font.save(stream)
            font.close()
            paths[kind].append(path)
    summaries = {}
    for kind, faces in paths.items():
        def verify(candidate):
            with TTCollection(candidate, lazy=True) as collection:
                assert verify_collection_tables(faces, collection)['faces_checked'] == 32
        summaries[kind] = pack_collection(faces, output / f'{kind}.ttc',
            expected_sha256=[sha256(path) for path in faces], validate=verify)
    return summaries


def transport_requests(axes_by_face, vectors=None):
    rng = random.Random(0x5044544152474554)
    rows = []
    for face in range(32):
        q_vectors = ([(0, 0, 0), (-16384, -16384, -16384), (16384, 16384, 16384),
                      (1, 65, -1), (-1, -3893, 1), (7513, 5275, -6448)]
                     + [tuple(rng.randint(-16384, 16384) for _ in ORDER) for _ in range(2)])
        if vectors is not None:
            q_vectors = vectors[face]
        for vector in q_vectors:
            y = [axis_transport(SourceAxis(tag, *axes_by_face[face][tag], IDENTITY), q)['target_user']
                 for tag, q in zip(ORDER, vector)]
            rows.append((face, *vector, *y))
    return rows


def check_harfbuzz(output, rows):
    import uharfbuzz as hb
    blobs = {kind: (output / f'{kind}.ttc').read_bytes() for kind in ('normalized', 'transported')}
    checks = 0
    for face, *values in rows:
        q, y = values[:3], values[3:]
        reference = hb.Font(hb.Face(blobs['normalized'], face))
        target = hb.Font(hb.Face(blobs['transported'], face))
        reference.set_var_coords_normalized([v / 16384 for v in q])
        target.set_variations(dict(zip(ORDER, y)))
        if target.get_var_coords_normalized() != reference.get_var_coords_normalized():
            raise ValueError('native_HarfBuzz_target_q_changed')
        for gid in range(7):
            for method in ('get_glyph_h_advance', 'get_glyph_v_advance', 'get_glyph_extents'):
                if getattr(target, method)(gid) != getattr(reference, method)(gid):
                    raise ValueError('native_HarfBuzz_target_glyph_changed')
                checks += 1
    return {'status': 'PASS_AUTHORED_Q_TRANSPORT_ONLY', 'requests': len(rows),
            'glyph_metric_extents_comparisons': checks, 'HarfBuzz': hb.version_string(),
            'font_only_original_equivalence': False, 'original_font_generated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    summaries = write_controls(args.output)
    rows = transport_requests(authored_axes())
    with (args.output / 'requests.tsv').open('x') as stream:
        for row in rows + list(reversed(rows)):
            stream.write('\t'.join(map(str, row)) + '\n')
    result = check_harfbuzz(args.output, rows)
    result['source_kind'] = 'self_authored_32_face_control_only'
    result['packing'] = {kind: {key: summary[key] for key in ('faces', 'sha256', 'byte_size')}
                         for kind, summary in summaries.items()}
    (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
