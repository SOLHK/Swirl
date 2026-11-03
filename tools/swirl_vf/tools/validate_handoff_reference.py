"""Offline portable replay of a sealed private handoff, including stored Apple evidence.

HarfBuzz verifies standard advances only. Its integer FUnit rounding and F2DOT14
readback are recorded separately; neither is labelled a CoreText observation.
This tool does not call a native Apple API and is intended to run on Windows.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time

import numpy as np
import uharfbuzz as hb

from handoff_bundle import Reference, verify, relative_file, read_rows, write_json, require

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
from export_mac_handoff import compare
from hvf_transcript import validate_events


def replay(root):
    started = time.monotonic()
    report = {'integrity': verify(root), 'geometry_replayed': 0, 'geometry_failed': 0,
              'max_replay_control_coordinate_error': 0., 'stored_native_compared': 0,
              'stored_native_failed': 0, 'max_stored_native_control_coordinate_error': 0.,
              'default_metric_fields': 0, 'default_metric_mismatches': 0,
              'variation_metric_fields': 0, 'variation_raw_fields_above_1_32': 0,
              'max_variation_raw_advance_difference': 0., 'variation_integer_rounded_mismatches': 0,
              'max_HB_design_readback_difference': 0., 'failures': [],
              'HB_constructor_locations': {}, 'default_metric_design_location': [0., 0., 0.],
              'CoreText': 'NOT_RUN', 'Apple_library_called': False, 'DirectWrite': 'NOT_RUN',
              'continuous_space_acceptance': False, 'private_font_Windows_execution': 'NOT_ESTABLISHED_BY_THIS_REPORT'}
    reference = Reference(root)
    try:
        blob = hb.Blob.from_file_path(relative_file(root, reference.package['source']['path']))
        engines = {}
        for face in reference.catalog['faces']:
            index = face['source_index']; font = reference.collection.fonts[index]
            engine = hb.Font(hb.Face(blob, index)); hb.ot_font_set_funcs(engine)
            engine.scale = (font['head'].unitsPerEm*64,)*2; engines[index] = engine
            # Font construction normalizes user defaults through avar. The
            # source's noncanonical Display map yields nonzero design wght in
            # HarfBuzz. A design-zero baseline must explicitly request zero;
            # otherwise two different physical locations are compared.
            report['HB_constructor_locations'][str(index)] = engine.get_var_coords_normalized()
            engine.set_var_coords_normalized([0., 0., 0.])
            require(engine.get_var_coords_normalized() == [0., 0., 0.], 'HB_design_zero_not_applied')
            for row in read_rows(relative_file(root, face['glyph_index'])):
                if 'default_metrics' not in row: continue  # authored format-only fixture
                gid = row['gid']; expected = row['default_metrics']
                for key, value in (('advance_width', engine.get_glyph_h_advance(gid)/64),
                                   ('advance_height', -engine.get_glyph_v_advance(gid)/64)):
                    report['default_metric_fields'] += 1
                    report['default_metric_mismatches'] += expected[key] != value
        inputs = [(entry['path'], 0) for entry in reference.package['defaults']]
        manifest = json.loads((Path(root)/'manifest.json').read_text())
        inputs += [(name, None) for name in manifest['files']
                   if '/variations/' in '/'+name and name.endswith('.jsonl.gz')]
        for name, default_face in inputs:
            for row in read_rows(relative_file(root, name)):
                face = default_face if default_face is not None else row['face']
                actual = reference.evaluate(face, row['gid'], row['design'])
                expected, got = row['paths'], actual['paths']
                topology = [len(p) for p in expected] == [len(p) for p in got]
                error = (max((float(np.max(np.abs(np.asarray(p)-q))) for p, q in zip(expected, got)), default=0.)
                         if topology else None)
                report['geometry_replayed'] += 1
                if error is not None: report['max_replay_control_coordinate_error'] = max(report['max_replay_control_coordinate_error'], error)
                if error is None or error > 1/32:
                    report['geometry_failed'] += 1
                    report['failures'].append({'kind': 'replay', 'file': name, 'gid': row['gid'], 'error': error})
                if 'apple_native' in row:
                    native = row['apple_native']
                    require(native['part_index'] == row['gid'] and native['status'] == 'OK' and native['native_code'] == 0,
                            'stored_native_identity_or_status_differs')
                    if 'normalized_coords' in native:
                        require(native['normalized_coords'] == row['design'], 'stored_native_location_differs')
                    table = reference.states[face][0].table
                    validate_events(native['events'], native['counters'], table.part_count)
                    result = compare([np.asarray(p) for p in got], native['events'])
                    report['stored_native_compared'] += 1
                    report['stored_native_failed'] += result['status'] != 'PASS'
                    error = result.get('maximum_control_coordinate_error')
                    if error is not None:
                        report['max_stored_native_control_coordinate_error'] = max(report['max_stored_native_control_coordinate_error'], error)
                    if result['status'] != 'PASS': report['failures'].append({'kind': 'stored_native', 'file': name, 'gid': row['gid'], **result})
                if default_face is None:
                    engine = engines[face]; engine.set_var_coords_normalized(row['design'])
                    normalized = engine.get_var_coords_normalized()
                    report['max_HB_design_readback_difference'] = max(report['max_HB_design_readback_difference'],
                        max(abs(a-b) for a, b in zip(normalized, row['design'])))
                    metrics = reference.states[face][1].at(row['gid'], dict(zip(('WDTH', 'wght', 'HGHT'), normalized)))
                    for key, value in (('advance_width', engine.get_glyph_h_advance(row['gid'])/64),
                                       ('advance_height', -engine.get_glyph_v_advance(row['gid'])/64)):
                        error = abs(metrics[key]-value)
                        report['variation_metric_fields'] += 1
                        report['variation_raw_fields_above_1_32'] += error > 1/32
                        report['max_variation_raw_advance_difference'] = max(report['max_variation_raw_advance_difference'], error)
                        report['variation_integer_rounded_mismatches'] += value != math.floor(metrics[key]+.5)
            print(json.dumps({'replayed': report['geometry_replayed'], 'geometry_failed': report['geometry_failed'],
                              'stored_native_failed': report['stored_native_failed']}), flush=True)
    finally:
        reference.close()
    failed = sum(report[key] for key in ('geometry_failed', 'stored_native_failed',
                                        'default_metric_mismatches', 'variation_integer_rounded_mismatches'))
    report.update(status='PASS_FINITE_REFERENCE_REPLAY' if failed == 0 else 'FAILED', seconds=time.monotonic()-started)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('bundle', type=Path); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    require(not args.output.absolute().is_relative_to(args.bundle.resolve()), 'report_must_be_outside_sealed_bundle')
    result = replay(args.bundle)
    write_json(args.output, result)
    raise SystemExit(result['status'] != 'PASS_FINITE_REFERENCE_REPLAY')
