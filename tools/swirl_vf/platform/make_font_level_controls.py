#!/usr/bin/env python3
"""Actual standard-table rebase of authored fonts, with original-user inputs.

No application adapter is applied to the target requests. A normalized custom
axis font supplies the independent authored reference; the target font itself
contains the reparameterized gvar, HVAR/VVAR and legal avar mappings.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

from fontTools.ttLib import TTCollection, TTFont
import uharfbuzz as hb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from target_axis_mapping import SourceAxis, source_axis_plan
from rebase_design_font import rebase_design_font
from design_axis_basis import basis_from_axis, decode_target_r
from make_target_axis_controls import authored_axes, authored_control_face, ORDER, IDENTITY
from rebuild import sha256, verify_collection_tables
from ttc_staging_pack import pack_collection

# Authored half-domain witness, not extracted Apple records. Its duplicated
# endpoint sentinel intentionally distinguishes source-q from target-r.
HALF_DOMAIN = ((-16384, -16384), (-16384, -8192), (0, 0),
               (16384, 8192), (16384, 16384))


def generate(output):
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    profiles = authored_axes()
    paths = {'normalized': [], 'font-level': []}
    source_axes = {}
    for face in range(32):
        axes = tuple(SourceAxis(tag, *profiles[face][tag], HALF_DOMAIN if tag == 'wght' else IDENTITY)
                     for tag in ORDER)
        source_axes[face] = axes
        source = authored_control_face(face, profiles[face], normalized=True)
        target, report = rebase_design_font(source, axes)
        for kind, font in [('normalized', source), ('font-level', target)]:
            path = output / f'{kind}-{face:02d}.ttf'
            with path.open('xb') as stream:
                font.save(stream)
            paths[kind].append(path)
            font.close()
    summaries = {}
    for kind, faces in paths.items():
        def verify(candidate):
            with TTCollection(candidate, lazy=True) as collection:
                assert verify_collection_tables(faces, collection)['faces_checked'] == 32
        summaries[kind] = pack_collection(faces, output / f'{kind}.ttc',
            expected_sha256=[sha256(path) for path in faces], validate=verify)
    rng = random.Random(0x5034464F4E544F4E4C59)
    requests = []
    for face in range(32):
        vectors = [(0, 0, 0), (-16384, -16384, -16384), (16384, 16384, 16384),
                   (2, 66, -2), (-2, -3892, 2), (7512, 5274, -6448)]
        vectors += [tuple(2*rng.randint(-8192, 8192) for _ in ORDER) for _ in range(2)]
        for n in vectors:
            y = {tag: profiles[face][tag][1] + value * (
                    profiles[face][tag][1]-profiles[face][tag][0] if value < 0
                    else profiles[face][tag][2]-profiles[face][tag][1]) / 16384
                 for tag, value in zip(ORDER, n)}
            q = {a.tag: source_axis_plan(a, y[a.tag])['source_q'] for a in source_axes[face]}
            expected = dict(zip(ORDER, (n[0], n[1]//2, n[2])))
            if q != expected:
                raise ValueError('authored_source_reference_not_independently_expected')
            requests.append((face, *(q[tag] for tag in ORDER), *(y[tag] for tag in ORDER)))
    with (output / 'requests.tsv').open('x') as stream:
        for row in requests + list(reversed(requests)):
            stream.write('\t'.join(map(str, row)) + '\n')
    blobs = {kind: (output / f'{kind}.ttc').read_bytes() for kind in paths}
    comparisons = 0
    for face, *values in requests:
        q, user = values[:3], values[3:]
        reference = hb.Font(hb.Face(blobs['normalized'], face))
        target = hb.Font(hb.Face(blobs['font-level'], face))
        reference.set_var_coords_normalized([v/16384 for v in q])
        target.set_variations(dict(zip(ORDER, user)))  # unchanged nominal user input
        actual_r = target.get_var_coords_normalized()
        for axis, source_q, r in zip(source_axes[face], q, actual_r):
            if decode_target_r(basis_from_axis(axis), round(r*16384)) != source_q:
                raise ValueError('authored_font_level_actual_native_mapping_changed')
        for gid in range(7):
            for method in ('get_glyph_h_advance', 'get_glyph_v_advance', 'get_glyph_extents'):
                if getattr(reference, method)(gid) != getattr(target, method)(gid):
                    raise ValueError('authored_font_level_native_glyph_changed')
                comparisons += 1
    result = {'status': 'PASS_AUTHORED_FONT_ONLY_REPARAMETERIZATION',
        'algorithm': report['algorithm'], 'harfbuzz': hb.version_string(),
        'faces': 32, 'requests': len(requests), 'glyph_metric_extents_checks': comparisons,
        'target_inputs': 'unchanged_original_nominal_user_coordinates',
        'application_compensation': False, 'original_conversion_accepted': False,
        'original_font_generated': False, 'Windows11': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN',
        'packing': {kind: {k: s[k] for k in ('faces', 'sha256', 'byte_size')}
                    for kind, s in summaries.items()}}
    (output / 'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.output)
