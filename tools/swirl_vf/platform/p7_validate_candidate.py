#!/usr/bin/env python3
"""Bounded PRIVATE original-candidate validation, never production acceptance.

Source outlines come from actual Apple HVF calls; source advances and shaping
come from the original font's standard tables through HarfBuzz. These references
are different APIs. The existing comparator and fixed 1/32 threshold are used
unchanged. Every raw mismatch remains a mismatch, including extra zero-length
closing segments in a target callback. No font or raw glyph data is exported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from fontTools.ttLib import TTFont
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from calibrate_hvf_geometry import EXPECTED, LIMIT
from diagnose_path_types import raw_native_paths, raw_coretext_paths, compare_preserved_quadratics
from metric_variations import verify_metric_variations
from probe_axis_thresholds import hvf_events, TAGS
from p7_original_glyf import private_directory
from rebuild import sha256, user_location
from source_metrics import SourceMetrics
from target_axis_mapping import source_plan
from ttc_staging_binary import validate_ttc_binary

PRIVATE = ROOT.parents[1]/'build/vf-takeover-private'
CUSTOM = ('XWDT', 'XWGT', 'XHGT')
SELECTED = (0, 2, 12, 1166, 19177)
DEFAULT_ONLY = (5, 56, 2335)
POSITIONS = ((0., 0., 0.), (0., -1., 0.), (0., 1., 0.), (.125, -.375, .625))


def require(value, reason):
    if not value:
        raise ValueError(reason)


def counters():
    return {'glyph_requests': 0, 'native_outline_passed': 0, 'native_outline_failed': 0,
        'native_outline_failure_reasons': {}, 'maximum_comparable_native_outline_control_error': 0.,
        'HB_source_target_advance_fields': 0, 'HB_source_target_fields_above_1_32': 0,
        'maximum_HB_source_target_error': 0., 'target_vs_original_table_advance_fields': 0,
        'target_vs_original_table_fields_above_1_32': 0, 'maximum_target_vs_original_table_error': 0.,
        'contour_pairs': 0, 'target_exact_terminal_zero_lines': 0}


def commands(font, gid):
    result, draw = [], hb.DrawFuncs()
    for method, kind, size in (('move_to', 'moveTo', 2), ('line_to', 'lineTo', 2),
                               ('quadratic_to', 'qCurveTo', 4), ('cubic_to', 'curveTo', 6)):
        def save(*args, kind=kind, size=size):
            result.append([kind, *(float(value)/64 for value in args[:size])])
        getattr(draw, 'set_'+method+'_func')(save)
    draw.set_close_path_func(lambda *args: result.append(['closePath']))
    font.draw_glyph(gid, draw)
    return result


def shape(font, text, direction):
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.direction, buffer.script, buffer.language = direction, 'hani', 'zh-cn'
    hb.shape(font, buffer, {}, shapers=['ot'])
    return ([(info.codepoint, info.cluster) for info in buffer.glyph_infos],
        [tuple(getattr(p, key) for key in ('x_advance', 'y_advance', 'x_offset', 'y_offset'))
         for p in buffer.glyph_positions])


def validate(source, candidate, binary, output, mode, expected_sha256):
    source, candidate, binary = (Path(path).resolve(strict=True) for path in (source, candidate, binary))
    output = Path(output).absolute()
    require(expected_sha256 == EXPECTED and sha256(source) == EXPECTED, 'exact_original_source_required')
    require(mode in ('q', 'nominal'), 'explicit_coordinate_mode_required')
    require(candidate.is_relative_to(PRIVATE), 'private_candidate_required')
    require(not output.exists() and not output.is_symlink(), 'fresh_validation_output_required')
    output = private_directory(output)
    before = sha256(candidate)
    report = {'status': 'RUNNING_PRIVATE_ORIGINAL_CANDIDATE_VALIDATION', 'source_sha256': EXPECTED,
        'candidate_sha256': before, 'validator_sha256': sha256(Path(__file__)), 'oracle_sha256': sha256(binary),
        'mode': mode, 'HarfBuzz': hb.version_string(), 'limit_source_font_units': LIMIT,
        'production_accepted': False, 'strict_font_acceptance': False, 'source_user_mapping_accepted': False,
        'Apple_native_metric_comparison': 'NOT_RUN', 'DirectWrite': 'NOT_RUN', 'Windows11': 'NOT_RUN',
        'Qt_Swirl': 'NOT_RUN', 'device_raster': 'NOT_RUN'}
    try:
        with candidate.open('rb') as stream:
            is_ttc = stream.read(4) == b'ttcf'
        report['TTC_binary'] = (validate_ttc_binary(candidate) if is_ttc else {'status': 'NOT_RUN_TTF_INPUT'})
        if is_ttc:
            require(report['TTC_binary']['faces'] == 1, 'single_experimental_face_required')
        with TTFont(source, fontNumber=0, lazy=True) as original, TTFont(candidate, fontNumber=0, lazy=True) as target:
            require(original.getGlyphOrder() == target.getGlyphOrder()
                    and original['maxp'].numGlyphs == target['maxp'].numGlyphs == 47102,
                    'original_GID_order_or_count_changed')
            require(original['cmap'].compile(original) == target['cmap'].compile(target), 'original_cmap_changed')
            require({'glyf', 'loca', 'gvar', 'HVAR', 'VVAR', 'fvar', 'avar', 'hmtx', 'vmtx'} <= set(target.keys())
                    and not {'hvgl', 'hvpm'} & set(target.keys()), 'standard_outline_metric_tables_required')
            expected_tags = CUSTOM if mode == 'q' else TAGS
            require(tuple(a.axisTag for a in target['fvar'].axes) == expected_tags, 'candidate_coordinate_mode_differs')
            gvar_count = struct.unpack_from('>H', target.reader['gvar'], 12)[0]
            locations = target['loca'].locations
            require(gvar_count == 47102 and len(locations) == 47103 and locations[0] == 0
                    and all(a <= b for a, b in zip(locations, locations[1:]))
                    and locations[-1] <= len(target.reader['glyf']), 'gvar_or_loca_GID_index_invalid')
            report['structure'] = {'glyphs': 47102, 'loca_entries': len(locations), 'gvar_GIDs': gvar_count,
                'cmap_and_GID_order_equal_original': True, 'proprietary_outline_tables_absent': True,
                'source_UPM': original['head'].unitsPerEm, 'target_UPM': target['head'].unitsPerEm}
            report['metric_encoding'] = verify_metric_variations(target)
            provider = SourceMetrics(original)
            reference_font = hb.Font(hb.Face(source.read_bytes(), 0))
            target_font = hb.Font(hb.Face(candidate.read_bytes(), 0))
            for font in (reference_font, target_font):
                hb.ot_font_set_funcs(font)
                font.scale = (original['head'].unitsPerEm*64,)*2
            ranges = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in original['fvar'].axes}
            groups = {name: counters() for name in ('selected_default', 'selected_nondefault',
                                                   'default_only_default', 'default_only_nondefault')}
            shaping = {'runs': 0, 'GID_cluster_equal_runs': 0, 'GID_cluster_failed_runs': 0,
                       'position_fields': 0, 'position_fields_above_1_32': 0, 'maximum_position_error_source_units': 0.}
            text = 'Swirl 中文中國 Aé，. 0123'
            shaping['input_codepoints'], shaping['input_codepoints_in_original_cmap'] = len(text), sum(
                ord(character) in original.getBestCmap() for character in text)
            for number, position in enumerate(POSITIONS):
                if mode == 'nominal':
                    location = user_location(dict(zip(TAGS, position)), ranges)
                    plan = source_plan(original, location)
                    q = [plan['source_q'][tag]/16384 for tag in TAGS]
                    target_font.set_variations(location)
                else:
                    q = list(position)
                    target_font.set_var_coords_normalized(q)
                reference_font.set_var_coords_normalized(q)
                for gid in (*SELECTED, *DEFAULT_ONLY):
                    name = ('selected_' if gid in SELECTED else 'default_only_')+('default' if number == 0 else 'nondefault')
                    group = groups[name]
                    group['glyph_requests'] += 1
                    metric_values = provider.at(gid, dict(zip(TAGS, q)))
                    for method, metric, sign in (('get_glyph_h_advance', 'advance_width', 1),
                                                 ('get_glyph_v_advance', 'advance_height', -1)):
                        a, b = getattr(reference_font, method)(gid)/64, getattr(target_font, method)(gid)/64
                        error = abs(a-b)
                        group['HB_source_target_advance_fields'] += 1
                        group['HB_source_target_fields_above_1_32'] += error > LIMIT
                        group['maximum_HB_source_target_error'] = max(group['maximum_HB_source_target_error'], error)
                        error = abs(sign*b-metric_values[metric])
                        group['target_vs_original_table_advance_fields'] += 1
                        group['target_vs_original_table_fields_above_1_32'] += error > LIMIT
                        group['maximum_target_vs_original_table_error'] = max(group['maximum_target_vs_original_table_error'], error)
                    events = hvf_events(binary, source, 0, gid, dict(zip(TAGS, q)))
                    left, right = raw_native_paths(events), raw_coretext_paths(commands(target_font, gid))
                    result = compare_preserved_quadratics(left, right)
                    good = result['status'] == 'within_budget'
                    group['native_outline_passed' if good else 'native_outline_failed'] += 1
                    if result['maximum_point_error'] is not None:
                        group['maximum_comparable_native_outline_control_error'] = max(
                            group['maximum_comparable_native_outline_control_error'], result['maximum_point_error'])
                    if not good:
                        reason = result.get('reason', result['status'])
                        group['native_outline_failure_reasons'][reason] = group['native_outline_failure_reasons'].get(reason, 0)+1
                    group['contour_pairs'] += min(len(left), len(right))
                    group['target_exact_terminal_zero_lines'] += sum(bool(path) and path[-1].kind == 'L'
                        and path[-1].points[0] == path[-1].points[1] for path in right)
                for direction in ('ltr', 'ttb'):
                    a, b = shape(reference_font, text, direction), shape(target_font, text, direction)
                    same = a[0] == b[0]
                    shaping['runs'] += 1
                    shaping['GID_cluster_equal_runs' if same else 'GID_cluster_failed_runs'] += 1
                    if same:
                        for x, y in zip(a[1], b[1]):
                            for v, w in zip(x, y):
                                error = abs(v-w)/64
                                shaping['position_fields'] += 1
                                shaping['position_fields_above_1_32'] += error > LIMIT
                                shaping['maximum_position_error_source_units'] = max(shaping['maximum_position_error_source_units'], error)
            report['finite_glyph_comparison'] = {'locations': len(POSITIONS), 'selected_variable_GIDs': len(SELECTED),
                'default_only_GIDs': len(DEFAULT_ONLY), 'groups': groups,
                'source_advance_reference': 'ORIGINAL_STANDARD_HVAR_VMTX_HARFBUZZ_NOT_APPLE_METRIC_API',
                'outline_reference': 'ACTUAL_APPLE_HVF_NATIVE_CALLBACKS',
                'outline_comparator': 'UNCHANGED_PRESERVED_QUADRATICS_1_32_NO_SEGMENTS_REMOVED'}
            report['mixed_CJK_Latin_shaping'] = shaping
            report['coordinate_scope'] = ('UNCHANGED_NOMINAL_INPUTS_WITH_UNACCEPTED_P4_SOURCE_Q_HYPOTHESIS'
                                           if mode == 'nominal' else 'EXPLICIT_DESIGN_Q_NOT_USER_MAPPING')
        require(sha256(source) == EXPECTED and sha256(candidate) == before, 'source_or_candidate_changed')
        report.update(status='COMPLETED_PRIVATE_FINITE_ORIGINAL_PARTIAL_CANDIDATE_NOT_ACCEPTANCE',
                      source_unchanged=True, candidate_unchanged=True)
    except Exception as error:
        report.update(status='BLOCKED_PRIVATE_VALIDATION', error_type=type(error).__name__)
        raise
    finally:
        with (output/'summary.json').open('x') as stream:
            json.dump(report, stream, indent=2)
            stream.write('\n')
    print(json.dumps(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--mode', choices=('q', 'nominal'), required=True)
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    validate(args.source, args.candidate, args.binary, args.output, args.mode, args.expected_sha256)
