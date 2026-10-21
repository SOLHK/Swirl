#!/usr/bin/env python3
"""P5 authored coefficient controls; never accept external or Apple glyphs."""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import random
import sys

from fontTools.ttLib import TTCollection
import uharfbuzz as hb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from bounded_rebase import bounded_rebase, source_endpoint_transform
from continuous_model import evaluate_model
from font_model_certificate import advance_models
from metric_variations import add_metric_variations
from precision_metrics import scale_with_precision_metrics
from target_axis_mapping import SourceAxis, source_axis_plan
from make_target_axis_controls import authored_axes, authored_control_face, ORDER, IDENTITY
from rebuild import sha256, verify_collection_tables
from ttc_staging_pack import pack_collection


UPEMS = (1000, 1028, 1064, 1100, 1128, 1144)
THREE_SIXTEENTHS = ((-16384, -16384), (-16384, -3072), (0, 0),
                   (16384, 3072), (16384, 16384))
LIMIT = Fraction(1, 32)


def generate(output):
    output = Path(output)
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    profiles = authored_axes()
    paths = {'normalized-scaled': [], 'precision': []}
    plans, metric_max, point_squared_max = [], Fraction(0), Fraction(0)
    for face in range(32):
        source = authored_control_face(face, profiles[face], normalized=True)
        source['head'].unitsPerEm = UPEMS[face % len(UPEMS)]
        for variations in source['gvar'].variations.values():
            for variation in variations:
                if 'XWGT' in variation.axes:
                    variation.coordinates = [(round(x / 20), y) for x, y in variation.coordinates]
        del source['HVAR']; del source['VVAR']
        add_metric_variations(source)
        axes = tuple(SourceAxis(tag, *profiles[face][tag],
                     THREE_SIXTEENTHS if tag == 'wght' else IDENTITY) for tag in ORDER)
        target, report = bounded_rebase(source, axes)
        if report['selected_multiplier'] != 5:
            raise ValueError('authored_control_expected_fivefold_grid_changed')
        proof = report['continuous_model_certificate']
        metric_max = max(metric_max, proof['max_metric_error'])
        point_squared_max = max(point_squared_max, proof['max_point_squared_error'])
        if not proof['within_1_32']:
            raise ValueError('authored_continuous_model_budget_failed')
        reference = scale_with_precision_metrics(source, source['head'].unitsPerEm * 5)
        plans.append(axes)
        for kind, font in [('normalized-scaled', reference), ('precision', target)]:
            path = output / f'{kind}-{face:02d}.ttf'
            with path.open('xb') as stream:
                font.save(stream)
            font.close()
            paths[kind].append(path)
        source.close()
    packed = {}
    for kind, faces in paths.items():
        def verify(candidate):
            with TTCollection(candidate, lazy=True) as collection:
                if verify_collection_tables(faces, collection)['faces_checked'] != 32:
                    raise ValueError('all_faces_must_pass_table_byte_gate')
        packed[kind] = pack_collection(faces, output / f'{kind}.ttc',
            expected_sha256=[sha256(path) for path in faces], validate=verify)
    rng = random.Random(0x5035434F454646)
    rows = []
    for face, axes in enumerate(plans):
        vectors = [(0, 0, 0), (-16384, -16384, -16384), (16384, 16384, 16384),
                   (0, 8192, 0), (4096, -8192, -4096), (-12288, 4096, 12288),
                   (256, 256, -256), (-256, -256, 256)]
        vectors += [tuple(256*rng.randint(-64, 64) for _ in ORDER) for _ in range(4)]
        for vector in vectors:
            user = [axis.default + n * (axis.default-axis.minimum if n < 0 else axis.maximum-axis.default)/16384
                    for axis, n in zip(axes, vector)]
            q = [source_axis_plan(axis, value)['source_q'] for axis, value in zip(axes, user)]
            rows.append((face, *q, *user))
    with (output / 'requests.tsv').open('x') as stream:
        for row in rows + list(reversed(rows)):
            stream.write('\t'.join(map(str, row))+'\n')
    blobs = {kind: (output / f'{kind}.ttc').read_bytes() for kind in paths}
    metrics, extents, layout = [], [], []
    # Independent decoded models isolate mapping, coefficient and native
    # rounding errors. These components must not be merged into one "pass".
    models, orders = {}, {}
    for kind in paths:
        with TTCollection(output / f'{kind}.ttc', lazy=True) as collection:
            models[kind] = [advance_models(font) for font in collection.fonts]
            orders[kind] = [font.getGlyphOrder() for font in collection.fonts]
    components = {key: Fraction(0) for key in
                  ('coordinate_composition', 'coefficient_model', 'reference_native_rounding', 'target_native_rounding')}
    shaping_runs = 0
    for face, *values in rows:
        q, user = values[:3], values[3:]
        reference = hb.Font(hb.Face(blobs['normalized-scaled'], face))
        target = hb.Font(hb.Face(blobs['precision'], face))
        for font in (reference, target):
            hb.ot_font_set_funcs(font)
            # SAME physical output scale in unscaled source units.
            font.scale = (UPEMS[face % len(UPEMS)]*64,)*2
        reference.set_var_coords_normalized([v/16384 for v in q])
        target.set_variations(dict(zip(ORDER, user)))
        actual_r = tuple(Fraction(round(v*16384), 16384) for v in target.get_var_coords_normalized())
        requested_q = tuple(Fraction(v, 16384) for v in q)
        composed_q = source_endpoint_transform(plans[face]).source_coordinates(actual_r)
        for gid in range(7):
            for method, kind in (('get_glyph_h_advance', 'HVAR'), ('get_glyph_v_advance', 'VVAR')):
                a_native, b_native = getattr(reference, method)(gid), getattr(target, method)(gid)
                metrics.append(abs(a_native-b_native)/64)
                a_model = models['normalized-scaled'][face][kind, orders['normalized-scaled'][face][gid]]
                b_model = models['precision'][face][kind, orders['precision'][face][gid]]
                requested = evaluate_model(a_model, requested_q)[0] / 5
                composed = evaluate_model(a_model, composed_q)[0] / 5
                encoded = evaluate_model(b_model, actual_r)[0] / 5
                # HarfBuzz reports downward advance as negative; VVAR stores
                # its positive magnitude. Compare the same quantity/units.
                sign = -1 if kind == 'VVAR' else 1
                for key, error in (
                    ('coordinate_composition', abs(requested-composed)),
                    ('coefficient_model', abs(composed-encoded)),
                    ('reference_native_rounding', abs(Fraction(sign*a_native, 64)-requested)),
                    ('target_native_rounding', abs(Fraction(sign*b_native, 64)-encoded))):
                    components[key] = max(components[key], error)
            a, b = reference.get_glyph_extents(gid), target.get_glyph_extents(gid)
            if (a is None) != (b is None):
                raise ValueError('authored_native_empty_glyph_coverage_changed')
            if a is not None:
                extents.extend(abs(x-y)/64 for x, y in zip(a, b))
        for direction in ('ltr', 'ttb'):
            results = []
            for font in (reference, target):
                buffer = hb.Buffer()
                buffer.add_codepoints([65, 0xE000+face, 32, 0x20000+face])
                buffer.direction, buffer.script, buffer.language = direction, 'hani', 'zh-cn'
                hb.shape(font, buffer, {}, shapers=['ot'])
                results.append(([(i.codepoint, i.cluster) for i in buffer.glyph_infos],
                    [tuple(getattr(p, key) for key in ('x_advance', 'y_advance', 'x_offset', 'y_offset'))
                     for p in buffer.glyph_positions]))
            if results[0][0] != results[1][0]:
                raise ValueError('authored_native_shaping_GID_or_cluster_changed')
            layout.extend(abs(x-y)/64 for a, b in zip(results[0][1], results[1][1]) for x, y in zip(a, b))
            shaping_runs += 1
    def parity(values):
        return {'observations': len(values), 'above_1_32': sum(v > LIMIT for v in values),
                'maximum_error_source_font_units': max(values, default=0.),
                'within_1_32': all(v <= LIMIT for v in values)}
    summary = {'status': 'COMPLETED_AUTHORED_PRECISION_CONTROL_NOT_ACCEPTANCE',
        'font_kind': 'self_authored_32_faces_7_GIDs_only', 'faces': 32,
        'selected_multiplier': 5, 'requests': len(rows), 'HarfBuzz': hb.version_string(),
        'continuous_decoded_model': {'all_32_within_1_32': True,
            'maximum_metric_error_exact': [metric_max.numerator, metric_max.denominator],
            'maximum_point_squared_error_exact': [point_squared_max.numerator, point_squared_max.denominator],
            'scope': 'entire_design_cube_only_excludes_user_mapping_and_native_rounding'},
        'actual_HarfBuzz_native': {'metrics': parity(metrics), 'extent_fields': parity(extents),
            'layout_fields': parity(layout), 'shaping_runs': shaping_runs,
            'GIDs_and_clusters_preserved': True, 'reference_already_upscaled': True},
        'finite_metric_error_components_exact': {key: [value.numerator, value.denominator]
                                                 for key, value in components.items()},
        'target_user_inputs': 'unchanged_nominal', 'application_compensation': False,
        'packing': {kind: {k: v[k] for k in ('faces', 'sha256', 'byte_size')} for kind, v in packed.items()},
        'original_font': 'NOT_RUN', 'Windows11': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN',
        'production_accepted': False}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    generate(parser.parse_args().output)
