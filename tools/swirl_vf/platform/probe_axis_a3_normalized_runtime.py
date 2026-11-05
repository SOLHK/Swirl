#!/usr/bin/env python3
"""Independent native HB/FT normalized transport, not an Apple source mapper.

Only an authored square/HVAR/gvar fixture is opened. q is supplied externally,
never inferred from Apple results here. A Windows execution is not DirectWrite,
Qt, Windows 11, or Swirl acceptance. Both complete input arrays are captured
immediately before the C calls. Native glyph results, not getters alone, gate
this finite transport experiment. All production flags stay false.
"""
from __future__ import annotations
import argparse
import ctypes as C
import ctypes.util
from fractions import Fraction
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from probe_axis_a3_normalized_api import AXES, UPEM, HarfBuzz, bind, require, synthetic_font

QS = (-16384, -65, -1, 0, 1, 65, 8192, 16384)
PAIR = ('499.006199', '499.006201')
FLAGS = {'mapping_accepted': False, 'continuous_space_accepted': False,
         'apple_source_tested': False, 'directwrite_tested': False,
         'qt_tested': False, 'swirl_tested': False, 'font_conversion_accepted': False}


def fixture():
    """The square's right edge and advance grow by q for positive weight q."""
    font = TTFont(io.BytesIO(synthetic_font()), recalcTimestamp=False)
    font['gvar'].variations['square'] = [TupleVariation({'wght': (0., 1., 1.)},
        [(0, 0), (16384, 0), (16384, 0), (0, 0), (0, 0), (16384, 0), (0, 0), (0, 0)])]
    out = io.BytesIO()
    font.save(out)
    font.close()
    return out.getvalue()


def plan():
    rows = [{'id': f'q_{q}_{repeat}', 'kind': 'normalized', 'q': q}
            for repeat, values in enumerate((QS, tuple(reversed(QS)))) for q in values]
    rows += [{'id': f'collision_{i}', 'kind': 'design', 'decimal': value}
             for i, value in enumerate(PAIR)]
    return rows


def fixed16(value):
    require(type(value) in (int, float) and math.isfinite(value), 'invalid_fixed_input')
    return math.floor(Fraction(value) * 65536 + Fraction(1, 2))


def array_bits(values, code):
    return [struct.pack('>' + code, value).hex() for value in values]


# Public FreeType ABI prefixes. c_long deliberately follows LP64/LLP64; never
# assume FT_Fixed/FT_Pos is an int64 on Windows. Native face invariants are read
# before dereferencing the glyph slot. Definitions follow freetype/freetype.h.
class Vector(C.Structure):
    _fields_ = [('x', C.c_long), ('y', C.c_long)]

class Generic(C.Structure):
    _fields_ = [('data', C.c_void_p), ('finalizer', C.c_void_p)]

class Bitmap(C.Structure):
    _fields_ = [('rows', C.c_uint), ('width', C.c_uint), ('pitch', C.c_int),
                ('buffer', C.c_void_p), ('num_grays', C.c_ushort),
                ('pixel_mode', C.c_ubyte), ('palette_mode', C.c_ubyte), ('palette', C.c_void_p)]

class Outline(C.Structure):
    _fields_ = [('n_contours', C.c_short), ('n_points', C.c_short),
                ('points', C.POINTER(Vector)), ('tags', C.POINTER(C.c_ubyte)),
                ('contours', C.POINTER(C.c_short)), ('flags', C.c_int)]

class Slot(C.Structure):
    _fields_ = [('library', C.c_void_p), ('face', C.c_void_p), ('next', C.c_void_p),
                ('glyph_index', C.c_uint), ('generic', Generic), ('metrics', C.c_long * 8),
                ('linearHoriAdvance', C.c_long), ('linearVertAdvance', C.c_long),
                ('advance', Vector), ('format', C.c_uint), ('bitmap', Bitmap),
                ('bitmap_left', C.c_int), ('bitmap_top', C.c_int), ('outline', Outline)]

class Face(C.Structure):
    _fields_ = [(name, C.c_long) for name in
                ('num_faces', 'face_index', 'face_flags', 'style_flags', 'num_glyphs')] + [
                ('family_name', C.c_char_p), ('style_name', C.c_char_p),
                ('num_fixed_sizes', C.c_int), ('available_sizes', C.c_void_p),
                ('num_charmaps', C.c_int), ('charmaps', C.c_void_p), ('generic', Generic),
                ('bbox', C.c_long * 4), ('units_per_EM', C.c_ushort)] + [
                (name, C.c_short) for name in ('ascender', 'descender', 'height',
                'max_advance_width', 'max_advance_height', 'underline_position', 'underline_thickness')] + [
                ('glyph', C.POINTER(Slot))]


class FreeType:
    def __init__(self, path, data):
        self.lib, self.library, self.face = C.CDLL(path), C.c_void_p(), C.c_void_p()
        lib = self.lib
        bind(lib, 'FT_Init_FreeType', C.c_int, C.POINTER(C.c_void_p))
        bind(lib, 'FT_Done_FreeType', C.c_int, C.c_void_p)
        bind(lib, 'FT_New_Memory_Face', C.c_int, C.c_void_p, C.c_void_p, C.c_long, C.c_long, C.POINTER(C.c_void_p))
        bind(lib, 'FT_Done_Face', C.c_int, C.c_void_p)
        bind(lib, 'FT_Library_Version', None, C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_int))
        bind(lib, 'FT_Load_Glyph', C.c_int, C.c_void_p, C.c_uint, C.c_int32)
        for name in ('FT_Set_Var_Blend_Coordinates', 'FT_Get_Var_Blend_Coordinates',
                     'FT_Set_Var_Design_Coordinates'):
            bind(lib, name, C.c_int, C.c_void_p, C.c_uint, C.POINTER(C.c_long))
        require(lib.FT_Init_FreeType(C.byref(self.library)) == 0, 'ft_init_failed')
        self.raw = C.create_string_buffer(data)  # memory face borrows these bytes
        try:
            require(lib.FT_New_Memory_Face(self.library, self.raw, len(data), 0, C.byref(self.face)) == 0,
                    'ft_memory_face_failed')
            face = C.cast(self.face, C.POINTER(Face)).contents
            require(face.num_faces == 1 and face.face_index == 0 and face.num_glyphs == 2
                    and face.units_per_EM == UPEM and bool(face.glyph), 'ft_abi_or_fixture_identity_failed')
            v = [C.c_int() for _ in range(3)]
            lib.FT_Library_Version(self.library, *(C.byref(x) for x in v))
            self.version = '.'.join(str(x.value) for x in v)
        except Exception:
            self.close()
            raise

    def close(self):
        if self.face:
            self.lib.FT_Done_Face(self.face)
            self.face = C.c_void_p()
        if self.library:
            self.lib.FT_Done_FreeType(self.library)
            self.library = C.c_void_p()

    def sample(self, case):
        normalized = case['kind'] == 'normalized'
        values = (C.c_long * 3)(0, case['q'] * 4, 0) if normalized else (
            C.c_long * 3)(fixed16(500.), fixed16(float(case['decimal'])), fixed16(500.))
        submitted = list(values)  # actual C array, not a repeated Python cast
        setter = self.lib.FT_Set_Var_Blend_Coordinates if normalized else self.lib.FT_Set_Var_Design_Coordinates
        require(setter(self.face, 3, values) == 0, 'ft_set_coordinates_failed')
        actual = (C.c_long * 3)()
        require(self.lib.FT_Get_Var_Blend_Coordinates(self.face, 3, actual) == 0, 'ft_get_coordinates_failed')
        # Unscaled, unhinted, no bitmaps: integer font-unit controls in this fixture.
        require(self.lib.FT_Load_Glyph(self.face, 1, 1 | 2 | 8) == 0, 'ft_load_glyph_failed')
        slot = C.cast(self.face, C.POINTER(Face)).contents.glyph.contents
        outline = slot.outline
        require(slot.format == 0x6f75746c and outline.n_points == 4 and outline.n_contours == 1,
                'ft_unexpected_synthetic_outline')
        points = [[outline.points[i].x, outline.points[i].y] for i in range(4)]
        return {'submitted': submitted, 'readback': list(actual),
                'advance': slot.metrics[4], 'points': points,
                'tags': [outline.tags[i] for i in range(4)], 'contours': [outline.contours[0]]}


class Extents(C.Structure):
    _fields_ = [(x, C.c_int32) for x in ('x_bearing', 'y_bearing', 'width', 'height')]


class HBChannel(HarfBuzz):
    def __init__(self, path, data):
        super().__init__(path, data)
        bind(self.lib, 'hb_font_get_glyph_extents', C.c_int, C.c_void_p, C.c_uint, C.POINTER(Extents))
        self.font = self.lib.hb_font_create(self.face)
        require(self.font, 'hb_font_create_failed')
        self.lib.hb_ot_font_set_funcs(self.font)
        self.lib.hb_font_set_scale(self.font, UPEM, UPEM)

    def sample(self, case):
        normalized = case['kind'] == 'normalized'
        values = (C.c_int * 3)(0, case['q'], 0) if normalized else (
            C.c_float * 3)(500., float(case['decimal']), 500.)
        submitted = list(values)
        entry_bits = None if normalized else array_bits(submitted, 'f')
        setter = self.lib.hb_font_set_var_coords_normalized if normalized else self.lib.hb_font_set_var_coords_design
        setter(self.font, values, 3)
        count = C.c_uint()
        actual = self.lib.hb_font_get_var_coords_normalized(self.font, C.byref(count))
        require(count.value == 3 and actual, 'hb_get_coordinate_count_failed')
        extents = Extents()
        require(self.lib.hb_font_get_glyph_extents(self.font, 1, C.byref(extents)), 'hb_glyph_extents_failed')
        return {'submitted': submitted, 'submitted_float32_bits': entry_bits,
                'readback': [actual[i] for i in range(3)],
                'advance': self.lib.hb_font_get_glyph_h_advance(self.font, 1),
                'extents': [getattr(extents, name) for name, _ in Extents._fields_]}

    def close(self):
        if getattr(self, 'font', None):
            self.lib.hb_font_destroy(self.font)
            self.font = None
        super().close()


def library_paths(directory=None):
    if directory:
        root = Path(directory).resolve()
        require(root.is_dir(), 'native_library_directory_missing')
        names = ('libharfbuzz-0.dll', 'libfreetype-6.dll')
        paths = [str(root / name) for name in names]
        require(all(Path(p).is_file() for p in paths), 'native_dll_missing')
        return paths
    require(sys.platform != 'win32', 'windows_explicit_dll_directory_required')
    paths = [ctypes.util.find_library(name) for name in ('harfbuzz', 'freetype')]
    require(all(paths), 'native_libraries_required_no_skip')
    return paths


def worker(order, directory=None):
    data, cases = fixture(), plan()
    require(order in ('forward', 'reverse'), 'invalid_order')
    paths = library_paths(directory)
    cookie = os.add_dll_directory(str(Path(directory).resolve())) if sys.platform == 'win32' else None
    hb = ft = None
    try:
        hb, ft = HBChannel(paths[0], data), FreeType(paths[1], data)
        rows = [{'case': case, 'hb': hb.sample(case), 'ft': ft.sample(case)}
                for case in (cases if order == 'forward' else reversed(cases))]
        return {'order': order, 'fixture_sha256': hashlib.sha256(data).hexdigest(), 'rows': rows,
                'libraries': [{'requested': p, 'sha256': hashlib.sha256(Path(p).read_bytes()).hexdigest()
                               if Path(p).is_file() else None} for p in paths],
                'versions': {'harfbuzz': hb.identity['version'], 'freetype': ft.version},
                'c_long_bytes': C.sizeof(C.c_long), 'process_id': os.getpid()}
    finally:
        if ft: ft.close()
        if hb: hb.close()
        if cookie: cookie.close()


def validate(processes):
    """Independently authored expectation; no per-point fitting or tolerance."""
    require(len(processes) == 2 and [p['order'] for p in processes] == ['forward', 'reverse'], 'missing_process_order')
    require(processes[0]['process_id'] != processes[1]['process_id'], 'independent_processes_required')
    require(processes[0]['versions'] == processes[1]['versions']
            and processes[0]['libraries'] == processes[1]['libraries'], 'native_libraries_changed')
    expected = plan()
    indexes = []
    for process in processes:
        cases = expected if process['order'] == 'forward' else list(reversed(expected))
        require(json.dumps([row['case'] for row in process['rows']], sort_keys=True, allow_nan=False) ==
                json.dumps(cases, sort_keys=True), 'native_case_identity_or_count_changed')
        def numeric_payload(value):
            if isinstance(value, dict):
                return all(numeric_payload(v) for v in value.values())
            if isinstance(value, list):
                return all(numeric_payload(v) for v in value)
            return value is None or type(value) is str or (type(value) in (int, float) and math.isfinite(value))
        require(all(numeric_payload(row[name]) for row in process['rows'] for name in ('hb', 'ft')),
                'invalid_native_numeric_payload')
        index = {row['case']['id']: row for row in process['rows']}
        for row in process['rows']:
            case = row['case']
            if case['kind'] == 'normalized':
                q, growth = case['q'], max(0, case['q'])
                for name, scale in (('hb', 1), ('ft', 4)):
                    require(row[name]['submitted'] == row[name]['readback'] == [0, q * scale, 0],
                            'normalized_input_or_readback_changed')
                    require(row[name]['advance'] == 500 + growth, 'native_hvar_advance_changed')
                require(row['hb']['extents'] == [0, 100, 100 + growth, -100], 'native_hb_outline_changed')
                require(row['ft']['points'] == [[0, 0], [100 + growth, 0], [100 + growth, 100], [0, 100]]
                        and row['ft']['tags'] == [1, 1, 1, 1] and row['ft']['contours'] == [3],
                        'native_ft_outline_changed')
        a, b = (index[f'collision_{i}'] for i in range(2))
        require(a['hb']['submitted_float32_bits'] == b['hb']['submitted_float32_bits'] ==
                ['43fa0000', '43f980cb', '43fa0000'], 'design_float32_entry_bits_changed')
        require(a['ft']['submitted'] == b['ft']['submitted'] == [32768000, 32702870, 32768000],
                'design_fixed16_entry_changed')
        require(a['hb'] == b['hb'] and a['ft'] == b['ft'], 'collapsed_inputs_changed_native_output')
        indexes.append(index)
    require(json.dumps(indexes[0], sort_keys=True, allow_nan=False) ==
            json.dumps(indexes[1], sort_keys=True, allow_nan=False), 'opposite_process_payload_changed')
    require(processes[0]['fixture_sha256'] == processes[1]['fixture_sha256'], 'fixture_changed_between_processes')
    return {'native_observations': 2 * 2 * len(expected), 'opposite_order_pairs': 2 * len(expected),
            'normalized_glyph_checks': 2 * 2 * (len(expected) - 2), 'all_exact': True}


def run(output, directory=None):
    output = Path(output)
    require(not output.exists(), 'new_report_path_required')
    report = {'status': 'NOT_RUN', 'source_commit': os.environ.get('GITHUB_SHA'), **FLAGS,
              'platform': platform.platform(), 'python': platform.python_version(),
              'synthetic_only': True, 'q_is_externally_supplied_not_derived_from_binary64': True,
              'axes': [list(a) for a in AXES], 'avar': 'authored identity; not original Apple avar',
              'original_pair_binary64_bits': array_bits([float(x) for x in PAIR], 'd'),
              'processes': [], 'windows_tested': False, 'conditional_channel_verified': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for order in ('forward', 'reverse'):
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', order]
            if directory: command += ['--library-dir', str(directory)]
            child = subprocess.run(command, capture_output=True, text=True, timeout=60)
            require(child.returncode == 0, 'native_worker_failed')
            report['processes'].append(json.loads(child.stdout))
        report['checks'] = validate(report['processes'])
        report.update(status='PASS_FINITE_SYNTHETIC_NORMALIZED_CHANNEL_ONLY',
                      windows_tested=sys.platform == 'win32', conditional_channel_verified=True)
    except Exception as error:
        report.update(status='FAILED_SYNTHETIC_NORMALIZED_CHANNEL', error_type=type(error).__name__)
        message = str(error)
        if message and len(message) <= 96 and all(c in 'abcdefghijklmnopqrstuvwxyz0123456789_' for c in message):
            report['error_code'] = message
        raise
    finally:
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--library-dir', type=Path)
    parser.add_argument('--worker', choices=('forward', 'reverse'))
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.worker, args.library_dir), allow_nan=False))
    else:
        parser.error('--output required') if args.output is None else None
        result = run(args.output, args.library_dir)
        print(json.dumps({key: result[key] for key in ('status', 'checks', 'windows_tested', 'mapping_accepted')}))
