#!/usr/bin/env python3
"""Private local acceptance wrapper around the existing DirectWrite probe.

This is a protocol/identity gate, not a conversion engine or an equivalence
verdict. Apple-derived input, native logs and rasters must stay private.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from datetime import datetime, timezone

from fontTools.ttLib import TTCollection, TTFont

PLATFORM = Path(__file__).resolve().parent
REPO = PLATFORM.parents[2]
PROBES = (0x41, 0x61, 0x67, 0x30, 0x38, 0x25, 0x4E2D, 0x6587, 0x53E3,
          0x56FD, 0x570B, 0x9AD4, 0x9AA8, 0x6E2F, 0x6FB3, 0x65E5, 0x8A00)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_JSON_key')
        result[key] = value
    return result


def decode(text):
    def invalid_constant(_):
        raise ValueError('nonfinite_JSON_number')
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def f32(value):
    require(type(value) in (int, float) and math.isfinite(value), 'invalid_axis_number')
    return struct.pack('<f', value)


def static_contract(font_path, expected_sha256, expected_glyphs=47102, expected_faces=1):
    """Read exact local input without modifying it; returned cmap data is private."""
    require(re.fullmatch('[0-9a-f]{64}', expected_sha256) is not None, 'invalid_expected_SHA256')
    require(type(expected_glyphs) is int and 0 < expected_glyphs <= 65535, 'invalid_glyph_count')
    require(type(expected_faces) is int and expected_faces > 0, 'invalid_face_count')
    path = Path(font_path)
    require(digest(path) == expected_sha256, 'input_SHA256_mismatch')
    with path.open('rb') as stream:
        collection = stream.read(4) == b'ttcf'
    owner = TTCollection(path, lazy=True) if collection else TTFont(path, lazy=True)
    fonts = owner.fonts if collection else [owner]
    try:
        require(len(fonts) == expected_faces, 'physical_face_count_mismatch')
        faces = []
        for font in fonts:
            order = font.getGlyphOrder()
            require(len(order) == expected_glyphs, 'physical_glyph_count_mismatch')
            require(all(tag in font for tag in ('fvar', 'glyf', 'gvar', 'cmap', 'hmtx', 'vmtx')),
                    'required_candidate_table_missing')
            axes = [{'tag': a.axisTag, 'min': a.minValue, 'default': a.defaultValue, 'max': a.maxValue}
                    for a in font['fvar'].axes]
            require({a['tag'] for a in axes} == {'WDTH', 'wght', 'HGHT'}, 'nominal_axis_contract_required')
            cmap = font.getBestCmap() or {}
            index = {name: gid for gid, name in enumerate(order)}
            faces.append({'glyph_count': len(order), 'axes': axes,
                          'unicode_probes': [{'codepoint': cp, 'glyph_id': index.get(cmap.get(cp), 0)}
                                             for cp in PROBES]})
        require(digest(path) == expected_sha256, 'input_changed_during_preflight')
        return {'sha256': expected_sha256, 'physical_face_count': len(faces),
                'container': 'TTC' if collection else 'SFNT', 'faces': faces}
    finally:
        owner.close()


def windows_scope(observed, caption):
    """Keep Server distinct even when it shares a client kernel build number."""
    if observed.get('product_type') in (2, 3):
        return 'WINDOWS_SERVER'
    if (observed.get('product_type') == 1 and observed.get('major') == 10
            and observed.get('minor') == 0 and observed.get('build', 0) >= 22000
            and 'windows 11' in caption.lower()):
        return 'WINDOWS_11_CLIENT'
    return 'WINDOWS_CLIENT_OR_VERSION_UNRESOLVED'


def native_windows_version():
    # Query product type as well as build. No registry credentials or machine
    # configuration are read. The existing wrapper separately records CIM caption.
    from ctypes import wintypes
    class Version(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('major', wintypes.DWORD),
                    ('minor', wintypes.DWORD), ('build', wintypes.DWORD),
                    ('platform', wintypes.DWORD), ('service_pack', wintypes.WCHAR * 128),
                    ('sp_major', wintypes.WORD), ('sp_minor', wintypes.WORD),
                    ('suite', wintypes.WORD), ('product_type', wintypes.BYTE),
                    ('reserved', wintypes.BYTE)]
    value = Version()
    value.size = ctypes.sizeof(value)
    function = ctypes.WinDLL('ntdll').RtlGetVersion
    function.argtypes = [ctypes.POINTER(Version)]
    function.restype = ctypes.c_long
    require(function(ctypes.byref(value)) == 0, 'Windows_version_observation_failed')
    return {key: int(getattr(value, key)) for key in ('major', 'minor', 'build', 'product_type')}


def validate_transcript(contract, rows, native_report, native_exit, directory):
    """Fail closed on truncated, mismatched or relaxed native evidence.

    Exact axis equality here means identical binary32 input/readback values,
    because DirectWrite's public axis API accepts FLOAT, not binary64.
    """
    require(native_exit == 0 and native_report.get('status') == 'PASS_NATIVE_PROBE', 'native_probe_failed')
    require(native_report.get('input_sha256') == contract['sha256']
            and native_report.get('input_sha256_after') == contract['sha256']
            and native_report.get('input_unchanged') is True, 'wrapper_input_identity_failed')
    require(native_report.get('source_sha256') == digest(PLATFORM / 'directwrite_probe.cpp'),
            'unexpected_native_probe_source')
    require(bool(rows) and rows[0].get('record') == 'header' and rows[-1].get('record') == 'summary',
            'native_transcript_incomplete')
    require(sum(r.get('record') == 'header' for r in rows) == 1
            and sum(r.get('record') == 'summary' for r in rows) == 1, 'duplicate_native_terminal_record')
    header, terminal = rows[0], rows[-1]
    count = contract['physical_face_count']
    require(header.get('input_sha256') == contract['sha256']
            and type(header.get('physical_face_count')) is int
            and header['physical_face_count'] == count and header.get('directwrite_supported') is True,
            'native_input_identity_failed')
    require(terminal.get('status') == 'PASS_NATIVE_PROBE'
            and type(terminal.get('faces_passed')) is int and terminal['faces_passed'] == count
            and type(terminal.get('faces_failed')) is int and terminal['faces_failed'] == 0,
            'native_final_summary_failed')
    require(all(r.get('record') in {'header', 'face', 'instance', 'face_result', 'raster', 'summary'}
                for r in rows), 'unknown_native_record')
    comparisons = instances = sampled = 0
    for face_index, expected in enumerate(contract['faces']):
        grouped = [r for r in rows if r.get('face_index') == face_index]
        faces = [r for r in grouped if r.get('record') == 'face']
        results = [r for r in grouped if r.get('record') == 'face_result']
        require(len(faces) == len(results) == 1, 'face_record_missing_or_duplicate')
        face, result = faces[0], results[0]
        observed_axes = face.get('axes', [])
        observed_cmap = face.get('unicode_probes', [])
        require(face.get('glyph_count') == expected['glyph_count']
                and isinstance(observed_axes, list) and len(observed_axes) == len(expected['axes'])
                and observed_cmap == expected['unicode_probes']
                and all(type(pair.get('codepoint')) is int and type(pair.get('glyph_id')) is int
                        for pair in observed_cmap), 'native_face_cmap_or_axes_mismatch')
        for axis, observed in zip(expected['axes'], observed_axes):
            require(observed.get('tag') == axis['tag']
                    and all(f32(observed.get(field)) == f32(axis[field])
                            for field in ('min', 'default', 'max')), 'native_fvar_axes_mismatch')
        require(type(face.get('probed_glyph_count')) is int and face['probed_glyph_count'] > 0,
                'no_sampled_glyphs')
        jobs = [r for r in grouped if r.get('record') == 'instance']
        n = len(expected['axes'])
        expected_jobs = 1 + 6 * n + (3 ** n if n <= 4 else 0) + 16
        require(result.get('status') == 'PASS_NATIVE_PROBE' and result.get('positions') == expected_jobs
                and len(jobs) == expected_jobs and len({r.get('case') for r in jobs}) == expected_jobs,
                'axis_position_matrix_incomplete')
        suffixes = ('0.000000', '0.173205', '0.381966', '0.618034', '0.826795', '1.000000')
        expected_cases = {'default'} | {f"sweep_{axis['tag']}_{suffix}"
                                        for axis in expected['axes'] for suffix in suffixes}
        expected_cases |= {f'internal_{index}' for index in range(1, 17)}
        if n <= 4:
            expected_cases |= {f'grid_{index}' for index in range(3 ** n)}
        require({row['case'] for row in jobs} == expected_cases, 'axis_position_cases_incomplete')
        sweeps = {a['tag']: set() for a in expected['axes']}
        for row in jobs:
            require(row.get('status') == 'PASS' and type(row.get('geometry_points')) is int
                    and type(row.get('nonempty_glyphs')) is int
                    and row['geometry_points'] >= row['nonempty_glyphs'] > 0,
                    'native_outline_observation_invalid')
            require(type(row.get('total_horizontal_advance_design_units')) in (int, float)
                    and math.isfinite(row['total_horizontal_advance_design_units']), 'invalid_native_metric')
            fingerprint = row.get('outline_metrics_fnv1a64', '')
            require(isinstance(fingerprint, str) and fingerprint.isdecimal()
                    and int(fingerprint) < 2 ** 64, 'invalid_native_outline_metric_hash')
            for axis in expected['axes']:
                tag = axis['tag']
                requested = row.get('requested', {}).get(tag)
                applied = row.get('applied', {}).get(tag)
                require(f32(requested) == f32(applied), 'strict_binary32_axis_readback_failed')
                require(axis['min'] <= requested <= axis['max'], 'requested_axis_out_of_range')
                comparisons += 1
                if row['case'].startswith('sweep_' + tag + '_'):
                    sweeps[tag].add(fingerprint)
            instances += 1
        require(all(len(hashes) >= 2 for hashes in sweeps.values()), 'axis_has_no_observed_movement')
        sampled += face['probed_glyph_count']
    require(all(type(r.get('face_index')) is int and 0 <= r['face_index'] < count
                for r in rows if r.get('record') not in {'header', 'summary'}), 'unexpected_physical_face')
    rasters = [r for r in rows if r.get('record') == 'raster']
    require(len(rasters) == 10
            and {(r.get('dpi'), r.get('theme')) for r in rasters}
            == {(dpi, theme) for dpi in (96, 120, 144, 168, 192) for theme in ('light', 'dark')},
            'five_DPI_raster_matrix_incomplete')
    root = Path(directory).resolve()
    for row in rasters:
        name = row.get('file', '')
        require(row.get('face_index') == 0 and row.get('sizes_dip') == [12, 16, 24, 36]
                and row.get('antialiasing') == 'grayscale', 'native_raster_scope_mismatch')
        require(isinstance(name, str) and Path(name).name == name and '\\' not in name,
                'unsafe_raster_path')
        require(name == f"face-0-default-dpi-{row['dpi']}-{row['theme']}.png", 'native_raster_filename_mismatch')
        path = root / name
        require(path.resolve().parent == root and path.is_file(), 'raster_file_missing_or_redirected')
        with path.open('rb') as stream:
            require(stream.read(8) == b'\x89PNG\r\n\x1a\n', 'native_raster_not_PNG')
    return {'status': 'PASS_LOCAL_DIRECTWRITE_PROTOCOL_ONLY', 'physical_faces': count,
            'sampled_glyphs_across_faces': sampled, 'native_instances': instances,
            'strict_binary32_axis_comparisons': comparisons, 'raster_captures': len(rasters),
            'cmap_probe_pairs': len(PROBES) * count, 'font_only_equivalence_accepted': False,
            'original_HVF_parity': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN',
            'system_installation': 'NOT_RUN', 'shaping': 'NOT_RUN_GLYPH_RUN_RASTERS_ONLY'}


def require_windows_private_path(path):
    resolved = Path(path).resolve()
    root = Path(r'D:\Codex').resolve()
    require(resolved != root and root in resolved.parents, 'Windows_files_must_remain_under_D_Codex')
    return resolved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', required=True, type=Path)
    parser.add_argument('--expected-sha256', required=True)
    parser.add_argument('--font-scope', required=True, choices=('authored_control', 'original_derived_candidate'))
    parser.add_argument('--expected-glyphs', type=int, default=47102)
    parser.add_argument('--expected-faces', type=int, default=1)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    output = args.output or Path(r'D:\Codex\Swirl-VF-private\P8') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    if os.name == 'nt':
        output = require_windows_private_path(output)
        require_windows_private_path(args.font)
        require_windows_private_path(REPO)
    else:
        require(args.output is not None, 'explicit_private_output_required_on_non_Windows')
    contract = static_contract(args.font, args.expected_sha256, args.expected_glyphs, args.expected_faces)
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 1, 'status': 'NOT_RUN', 'font_scope': args.font_scope,
              'input_sha256': contract['sha256'], 'static_contract': contract,
              'Windows11': 'NOT_RUN', 'Windows_Server': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN',
              'font_only_equivalence_accepted': False, 'private_outputs_only': True}
    code = 77
    try:
        if os.name != 'nt':
            report['reason'] = 'Windows_DirectWrite_runtime_unavailable_on_this_host'
        else:
            powershell = shutil.which('pwsh')
            require(powershell is not None, 'PowerShell_7_required_by_existing_native_wrapper')
            report['native_Windows_version'] = native_windows_version()
            temporary = output / '_tmp'
            temporary.mkdir()
            environment = dict(os.environ, TEMP=str(temporary), TMP=str(temporary), PYTHONDONTWRITEBYTECODE='1')
            command = [powershell, '-NoProfile', '-File', str(PLATFORM / 'run_directwrite_probe.ps1'),
                       '-Font', str(args.font.resolve()), '-OutputDirectory', str(output / 'native'), '-Render']
            report['command'] = command
            with (output / 'wrapper.stdout').open('xb') as stdout, (output / 'wrapper.stderr').open('xb') as stderr:
                process = subprocess.run(command, stdout=stdout, stderr=stderr, env=environment, cwd=REPO)
            code = process.returncode
            native = decode((output / 'native/directwrite-run.json').read_text(encoding='utf-8-sig'))
            rows = [decode(line) for line in (output / 'native/directwrite.jsonl').read_text(encoding='utf-8-sig').splitlines()]
            scope = windows_scope(report['native_Windows_version'], native.get('windows_product', ''))
            report['Windows_scope'] = scope
            report['Windows_caption'] = native.get('windows_product', 'UNRESOLVED')
            report['observations'] = validate_transcript(contract, rows, native, code, output / 'native')
            report['status'] = report['observations']['status']
            if scope == 'WINDOWS_11_CLIENT':
                report['Windows11'] = 'NATIVE_LOCAL_PROBE_PASSED_NOT_FINAL_FONT_ACCEPTANCE'
            elif scope == 'WINDOWS_SERVER':
                report['Windows_Server'] = 'NATIVE_LOCAL_PROBE_PASSED_NOT_WINDOWS11'
            code = 0
    except Exception as error:
        report['status'] = 'FAILED'
        report['error'] = str(error)
        code = 1
    finally:
        report['input_unchanged'] = digest(args.font) == contract['sha256']
        if not report['input_unchanged']:
            report['status'] = 'FAILED_INPUT_CHANGED'
            code = 1
        with (output / 'p8-local-report.json').open('x', encoding='utf-8') as stream:
            json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n')
    print(json.dumps({key: report[key] for key in ('status', 'font_scope', 'input_sha256', 'input_unchanged',
                                                   'Windows11', 'Windows_Server', 'font_only_equivalence_accepted')}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
