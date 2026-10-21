#!/usr/bin/env python3
"""Small P6 authored controls. No external font input or production permission."""
from __future__ import annotations

import argparse
from fractions import Fraction as F
import io
import json
from pathlib import Path
import sys

from fontTools.ttLib import TTCollection
import uharfbuzz as hb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bounded_rebase import bounded_rebase, exact_rebase
from continuous_model import evaluate_model
from font_model_certificate import advance_models
from metric_variations import add_metric_variations
from precision_metrics import scale_with_precision_metrics
from make_target_axis_controls import authored_control_face, ORDER, IDENTITY
from target_axis_mapping import SourceAxis
from rebuild import sha256, verify_collection_tables
from ttc_staging_pack import pack_collection

LIMIT = F(1, 32)
CLIP = ((-16384, -16384), (-16384, -3072), (0, 0),
        (16384, 3072), (16384, 16384))
PROFILES = {'WDTH': (1, 500, 1000), 'wght': (100, 500, 900), 'HGHT': (1, 500, 1000)}
Q = (F(63, 16384), F(3, 16), F(0))
R = (F(63, 16384), F(1), F(0))
USER = {'WDTH': 501.922607421875, 'wght': 900., 'HGHT': 500.}
F2_Q = (F(1141, 16384), F(1453, 16384), F(10955, 16384))
F2_R = (F(1141, 16384), F(7749, 16384), F(10955, 16384))
F2_USER = {'WDTH': 534.820556640625, 'wght': 689.1845703125, 'HGHT': 834.320068359375}


def authored_source():
    source = authored_control_face(0, PROFILES, normalized=True)
    for variations in source['gvar'].variations.values():
        for variation in variations:
            if 'XWGT' in variation.axes:
                variation.coordinates = [(round(x / 20), y) for x, y in variation.coordinates]
    del source['HVAR']; del source['VVAR']
    add_metric_variations(source)
    source.recalcTimestamp = False
    return source


def _blob(font):
    stream = io.BytesIO()
    font.save(stream)
    return stream.getvalue()


def _path(font):
    commands = []
    draw = hb.DrawFuncs()
    for name, count in (('move_to', 2), ('line_to', 2), ('quadratic_to', 4), ('cubic_to', 6)):
        def save(*args, kind=name, size=count):
            commands.append((kind, tuple(args[:size])))
        getattr(draw, f'set_{name}_func')(save)
    draw.set_close_path_func(lambda *args: commands.append(('close', ())))
    font.draw_glyph(2, draw)
    return commands


def trace(reference, target, multiplier, q=Q, r=R, user=USER):
    """Actual HB callbacks at several explicit scales; none is a pixel raster."""
    models = [advance_models(f) for f in (reference, target)]
    native = [hb.Font(hb.Face(_blob(f))) for f in (reference, target)]
    native[0].set_variations(dict(zip(('XWDT', 'XWGT', 'XHGT'), map(float, q))))
    native[1].set_variations(user)
    for font in native:
        hb.ot_font_set_funcs(font)
    actual = [tuple(F(round(v*16384), 16384) for v in f.get_var_coords_normalized())
              for f in native]
    values = [evaluate_model(m['HVAR', 'A'], c)[0] for m, c in zip(models, actual)]
    ideal_q = (actual[1][0], actual[1][1]*F(3, 16), actual[1][2])
    composed = evaluate_model(models[0]['HVAR', 'A'], ideal_q)[0]
    rows = []
    for scale in (1000, 64000, 128000, reference['head'].unitsPerEm):
        for font in native:
            font.scale = (scale, scale)
        paths = [_path(font) for font in native]
        if [x[0] for x in paths[0]] != [x[0] for x in paths[1]]:
            raise ValueError('authored_outline_topology_changed')
        path_error = max((abs(a-b)*1000/scale
                          for (_, aa), (_, bb) in zip(*paths)
                          for a, b in zip(aa, bb)), default=0.)
        advance = [font.get_glyph_h_advance(2) for font in native]
        rows.append({'font_scale': scale, 'scale_is_26_6_source_units': scale == 64000,
            'h_advance_raw': advance,
            'h_advance_source_units': [str(F(v*1000, scale)) for v in advance],
            'h_advance_error_source_units': str(F(abs(advance[0]-advance[1])*1000, scale)),
            'outline_component_max_source_units': path_error,
            'extents_raw': [list(font.get_glyph_extents(2)) for font in native]})
    return {'GID': 2, 'requested_q': list(map(str, q)), 'requested_pre_avar_r': list(map(str, r)),
        'ideal_unquantized_q': list(map(str, ideal_q)),
        'target_user': user, 'source_UPM': 1000, 'native_font_UPM': reference['head'].unitsPerEm,
        'multiplier': multiplier, 'decoded_HVAR_ideal_native_units': list(map(str, values)),
        'decoded_HVAR_ideal_source_units': [str(v/multiplier) for v in values],
        'coefficient_error_source_units': str(abs(composed-values[1])/multiplier),
        'coordinate_quantization_error_source_units': str(abs(composed-values[0])/multiplier),
        'HVAR_integer_base': [f['hmtx'].metrics['A'][0] for f in (reference, target)],
        'decoded_HVAR_delta_native_units': [str(v-f['hmtx'].metrics['A'][0])
                                            for v, f in zip(values, (reference, target))],
        'actual_normalized_F2DOT14': [[round(v*16384) for v in f.get_var_coords_normalized()]
                                     for f in native], 'scales': rows,
        'device_pixel_raster': 'NOT_RUN', 'whole_domain_native_parity': 'NOT_PROVEN'}


def generate(output):
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    source = authored_source()
    axes = tuple(SourceAxis(tag, *PROFILES[tag], CLIP if tag == 'wght' else IDENTITY) for tag in ORDER)
    records = {}
    for name, rebase in (('bounded5', bounded_rebase), ('exact16', exact_rebase)):
        target, report = rebase(source, axes)
        n = report['selected_multiplier']
        reference = scale_with_precision_metrics(source, 1000*n)
        paths = {}
        for kind, font in (('reference', reference), ('target', target)):
            path = output/f'{name}-{kind}.ttf'
            with path.open('xb') as stream:
                font.save(stream)
            paths[kind] = path
            def verify(candidate):
                with TTCollection(candidate, lazy=True) as collection:
                    if verify_collection_tables([path], collection)['faces_checked'] != 1:
                        raise ValueError('authored_face_byte_gate_failed')
            pack_collection([path], output/f'{name}-{kind}.ttc',
                            expected_sha256=[sha256(path)], validate=verify)
        records[name] = {'continuous_certificate': report['continuous_model_certificate'],
                         'coefficient_witness': trace(reference, target, n),
                         'F2_input_witness': trace(reference, target, n, F2_Q, F2_R, F2_USER),
                         'font_SHA256': {kind: sha256(path) for kind, path in paths.items()}}
        reference.close(); target.close()
    source.close()
    summary = {'status': 'AUTHORED_ROUNDING_DIAGNOSTIC_NOT_ACCEPTANCE',
        'HarfBuzz': hb.version_string(), 'controls': records,
        'strict_limit_source_units': LIMIT, 'original_font': 'NOT_RUN', 'Windows11': 'NOT_RUN',
        'production_accepted': False, 'font_only_equivalence_accepted': False}
    with (output/'summary.json').open('x') as stream:
        json.dump(summary, stream, indent=2, default=str)
        stream.write('\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.output), default=str))
