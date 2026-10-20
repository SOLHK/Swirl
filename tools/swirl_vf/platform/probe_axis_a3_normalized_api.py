#!/usr/bin/env python3
"""Real installed Linux APIs, synthetic VF only: normalized-coordinate channel.

This proves a representation channel after an application retained its original
binary64 coordinate and supplied a distinct normalized q. It does NOT prove
the Apple source mapping, original-font metrics, Windows behavior, or a font
conversion. The temporary font contains only an independently authored square.

API references:
https://harfbuzz.github.io/harfbuzz-hb-font.html#hb-font-set-var-coords-normalized
https://harfbuzz.github.io/harfbuzz-hb-font.html#hb-font-set-var-coords-design
https://freetype.org/freetype2/docs/reference/ft2-multiple_masters.html
"""
from __future__ import annotations

import argparse
import ctypes as C
import ctypes.util
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import struct
import sys

import fontTools
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import buildVarData, buildVarRegionList, buildVarStore


AXES = (("WDTH", 1., 500., 1000.), ("wght", 100., 499., 900.),
        ("HGHT", 1., 500., 1000.))
INPUTS = (("499.006199", 0), ("499.006201", 65))
UPEM = 2048
BASE_ADVANCE = 500
HVAR_DELTA = 16384
STATUS = "SYNTHETIC_LINUX_API_PROOF_NOT_APPLE_OR_WINDOWS_ACCEPTANCE"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def synthetic_font():
    """Build an original two-glyph VF in memory; never read an Apple font."""
    fb = FontBuilder(UPEM, isTTF=True)
    names = [".notdef", "square"]
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({0x41: "square"})
    empty = TTGlyphPen(None)
    square = TTGlyphPen(None)
    square.moveTo((0, 0)); square.lineTo((100, 0)); square.lineTo((100, 100))
    square.lineTo((0, 100)); square.closePath()
    fb.setupGlyf({".notdef": empty.glyph(), "square": square.glyph()})
    fb.setupHorizontalMetrics({name: (BASE_ADVANCE, 0) for name in names})
    fb.setupHorizontalHeader(ascent=1000, descent=-200)
    fb.setupNameTable({"familyName": "Swirl A3 Synthetic API Proof", "styleName": "Regular",
        "uniqueFontIdentifier": "Swirl-A3-independent-synthetic-normalized-api-v1",
        "fullName": "Swirl A3 Synthetic API Proof Regular", "psName": "SwirlA3SyntheticAPIProof-Regular",
        "version": "Version 1.000"})
    fb.setupOS2(sTypoAscender=1000, sTypoDescender=-200, usWinAscent=1000, usWinDescent=200)
    fb.setupPost()
    fb.setupFvar([(*axis, axis[0]) for axis in AXES], [])
    avar = newTable("avar")
    avar.segments = {axis[0]: {-1.: -1., 0.: 0., 1.: 1.} for axis in AXES}
    fb.font["avar"] = avar
    gvar = newTable("gvar")
    gvar.variations = {name: [] for name in names}
    fb.font["gvar"] = gvar
    regions = buildVarRegionList([{"wght": (0., 1., 1.)}], [a[0] for a in AXES])
    hvar = newTable("HVAR")
    hvar.table = otTables.HVAR()
    hvar.table.Version = 0x00010000
    hvar.table.VarStore = buildVarStore(regions, [buildVarData([0], [[0], [HVAR_DELTA]], optimize=False)])
    hvar.table.AdvWidthMap = None
    hvar.table.LsbMap = None
    hvar.table.RsbMap = None
    fb.font["HVAR"] = hvar
    fb.font["head"].created = fb.font["head"].modified = 3750000000
    fb.font.recalcTimestamp = False
    buffer = io.BytesIO()
    fb.font.save(buffer)
    return buffer.getvalue()


def library_identity(name, soname):
    """Identify only this loaded library, not the rest of the process mappings."""
    paths = set()
    maps = Path("/proc/self/maps")
    if maps.exists():
        for line in maps.read_text().splitlines():
            path = line.split()[-1]
            if path.startswith("/") and Path(path).name.startswith(f"lib{name}.so"):
                paths.add(str(Path(path).resolve()))
    return {"requested_soname": soname, "loaded_files": [{"path": path,
        "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()} for path in sorted(paths)]}


def bind(lib, name, restype, *argtypes):
    function = getattr(lib, name)
    function.restype = restype
    function.argtypes = list(argtypes)
    return function


class HarfBuzz:
    def __init__(self, soname, data):
        self.lib = C.CDLL(soname)
        lib = self.lib
        bind(lib, "hb_version_string", C.c_char_p)
        bind(lib, "hb_blob_create", C.c_void_p, C.c_void_p, C.c_uint, C.c_int, C.c_void_p, C.c_void_p)
        bind(lib, "hb_blob_destroy", None, C.c_void_p)
        bind(lib, "hb_face_create", C.c_void_p, C.c_void_p, C.c_uint)
        bind(lib, "hb_face_destroy", None, C.c_void_p)
        bind(lib, "hb_face_get_upem", C.c_uint, C.c_void_p)
        bind(lib, "hb_face_get_glyph_count", C.c_uint, C.c_void_p)
        bind(lib, "hb_font_create", C.c_void_p, C.c_void_p)
        bind(lib, "hb_font_destroy", None, C.c_void_p)
        bind(lib, "hb_ot_font_set_funcs", None, C.c_void_p)
        bind(lib, "hb_font_set_scale", None, C.c_void_p, C.c_int, C.c_int)
        bind(lib, "hb_font_set_var_coords_design", None, C.c_void_p, C.POINTER(C.c_float), C.c_uint)
        bind(lib, "hb_font_get_var_coords_design", C.POINTER(C.c_float), C.c_void_p, C.POINTER(C.c_uint))
        bind(lib, "hb_font_set_var_coords_normalized", None, C.c_void_p, C.POINTER(C.c_int), C.c_uint)
        bind(lib, "hb_font_get_var_coords_normalized", C.POINTER(C.c_int), C.c_void_p, C.POINTER(C.c_uint))
        bind(lib, "hb_font_get_glyph_h_advance", C.c_int, C.c_void_p, C.c_uint)
        raw = C.create_string_buffer(data)
        blob = lib.hb_blob_create(raw, len(data), 0, None, None)  # DUPLICATE
        require(blob, "hb_blob_create_failed")
        self.face = lib.hb_face_create(blob, 0)
        lib.hb_blob_destroy(blob)
        require(self.face and lib.hb_face_get_upem(self.face) == UPEM
                and lib.hb_face_get_glyph_count(self.face) == 2, "hb_synthetic_face_identity_failed")
        self.identity = {**library_identity("harfbuzz", soname), "version": lib.hb_version_string().decode()}

    def close(self):
        if self.face:
            self.lib.hb_face_destroy(self.face)
            self.face = None

    def sample(self, original_decimal, q, normalized):
        require(type(q) is int and -16384 <= q <= 16384, "normalized_q_outside_range")
        original = float(original_decimal)
        lib = self.lib
        font = lib.hb_font_create(self.face)
        require(font, "hb_font_create_failed")
        try:
            lib.hb_ot_font_set_funcs(font)
            lib.hb_font_set_scale(font, UPEM, UPEM)
            supplied_float = C.c_float(original).value
            if normalized:
                values = (C.c_int * 3)(0, q, 0)
                lib.hb_font_set_var_coords_normalized(font, values, 3)
                submitted = {"normalized_f2dot14": list(values)}
            else:
                values = (C.c_float * 3)(500., original, 500.)
                lib.hb_font_set_var_coords_design(font, values, 3)
                submitted = {"design_float32": list(values),
                    "weight_float32_bits": struct.pack(">f", supplied_float).hex()}
            count = C.c_uint()
            coords = lib.hb_font_get_var_coords_normalized(font, C.byref(count))
            require(count.value == 3 and bool(coords), "hb_normalized_getter_axis_count_failed")
            actual = [coords[index] for index in range(count.value)]
            if not normalized:
                design = lib.hb_font_get_var_coords_design(font, C.byref(count))
                require(count.value == 3 and bool(design), "hb_design_getter_axis_count_failed")
                submitted["readback_design_float32"] = [design[index] for index in range(count.value)]
            return {"retained_original_decimal": original_decimal,
                "retained_original_binary64_bits": struct.pack(">d", original).hex(),
                "externally_supplied_q_not_inferred_by_this_probe": q, **submitted,
                "readback_normalized_f2dot14": actual,
                "synthetic_gid1_native_advance_font_units": lib.hb_font_get_glyph_h_advance(font, 1)}
        finally:
            lib.hb_font_destroy(font)


def freetype_probe(soname, data):
    lib = C.CDLL(soname)
    bind(lib, "FT_Init_FreeType", C.c_int, C.POINTER(C.c_void_p))
    bind(lib, "FT_Done_FreeType", C.c_int, C.c_void_p)
    bind(lib, "FT_Library_Version", None, C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int), C.POINTER(C.c_int))
    bind(lib, "FT_New_Memory_Face", C.c_int, C.c_void_p, C.POINTER(C.c_ubyte), C.c_long, C.c_long, C.POINTER(C.c_void_p))
    bind(lib, "FT_Done_Face", C.c_int, C.c_void_p)
    bind(lib, "FT_Set_Var_Blend_Coordinates", C.c_int, C.c_void_p, C.c_uint, C.POINTER(C.c_long))
    bind(lib, "FT_Get_Var_Blend_Coordinates", C.c_int, C.c_void_p, C.c_uint, C.POINTER(C.c_long))
    library, face = C.c_void_p(), C.c_void_p()
    require(lib.FT_Init_FreeType(C.byref(library)) == 0, "freetype_init_failed")
    try:
        major, minor, patch = C.c_int(), C.c_int(), C.c_int()
        lib.FT_Library_Version(library, C.byref(major), C.byref(minor), C.byref(patch))
        raw = (C.c_ubyte * len(data)).from_buffer_copy(data)
        require(lib.FT_New_Memory_Face(library, raw, len(data), 0, C.byref(face)) == 0,
                "freetype_synthetic_memory_face_failed")
        rows = []
        for text, q in INPUTS:
            values = (C.c_long * 3)(0, q * 4, 0)
            actual = (C.c_long * 3)()
            require(lib.FT_Set_Var_Blend_Coordinates(face, 3, values) == 0,
                    "freetype_set_normalized_failed")
            require(lib.FT_Get_Var_Blend_Coordinates(face, 3, actual) == 0,
                    "freetype_get_normalized_failed")
            rows.append({"retained_original_decimal": text,
                "retained_original_binary64_bits": struct.pack(">d", float(text)).hex(),
                "externally_supplied_q_not_inferred_by_this_probe": q,
                "submitted_normalized_16_16": list(values),
                "readback_normalized_16_16": list(actual)})
        return {"status": "SYNTHETIC_NATIVE_NORMALIZED_GETTER_ONLY",
            "library": {**library_identity("freetype", soname),
                "version": f"{major.value}.{minor.value}.{patch.value}"},
            "samples": rows, "q0_and_q65_preserved": all(
                row["submitted_normalized_16_16"] == row["readback_normalized_16_16"] for row in rows),
            "glyph_metric_tested": False}
    finally:
        if face:
            lib.FT_Done_Face(face)
        lib.FT_Done_FreeType(library)


def run():
    report = {"status": "NOT_RUN", "source_commit": os.environ.get("GITHUB_SHA"),
        "runtime": {"platform": platform.platform(), "machine": platform.machine(),
            "python": platform.python_version(), "fonttools": fontTools.__version__,
            "byteorder": sys.byteorder, "c_float_bytes": C.sizeof(C.c_float),
            "c_double_bytes": C.sizeof(C.c_double), "c_long_bytes": C.sizeof(C.c_long)},
        "synthetic_only": True, "apple_source_font_read": False,
        "source_outlines_used": False, "source_font_or_synthetic_font_written": False,
        "general_source_mapper_proven": False, "production_mapping_accepted": False,
        "windows_tested": False, "apple_tested": False,
        "original_user_axes_preserved": [list(axis) for axis in AXES],
        "conditional_scope": "The app must retain the original binary64 input and separately determine q; this probe supplies q externally and proves only that real normalized APIs can transport it."}
    if sys.platform != "linux":
        report["status"] = "NOT_RUN_LINUX_PROOF_ONLY"
        return report
    hb_path = ctypes.util.find_library("harfbuzz")
    ft_path = ctypes.util.find_library("freetype")
    if not hb_path:
        report["status"] = "NOT_RUN_NATIVE_HARFBUZZ_UNAVAILABLE_NO_INSTALL_ATTEMPTED"
        return report
    data = synthetic_font()
    report["synthetic_fixture"] = {"sha256": hashlib.sha256(data).hexdigest(),
        "byte_size": len(data), "glyph_count": 2, "units_per_em": UPEM,
        "authored_gid1_base_advance": BASE_ADVANCE, "authored_gid1_weight_delta": HVAR_DELTA,
        "expected_advance_rule_positive_weight_q": "500 + 16384 * q / 16384",
        "avar": "independently authored identity map on all three axes"}
    hb = HarfBuzz(hb_path, data)
    try:
        design = [hb.sample(text, q, False) for text, q in INPUTS]
        normalized = [hb.sample(text, q, True) for text, q in INPUTS]
        report["harfbuzz"] = {"library": hb.identity, "design_float32_samples": design,
            "normalized_f2dot14_samples": normalized,
            "design_float32_collision": design[0]["weight_float32_bits"] == design[1]["weight_float32_bits"],
            "native_design_output_collision": design[0]["readback_normalized_f2dot14"] == design[1]["readback_normalized_f2dot14"]
                and design[0]["synthetic_gid1_native_advance_font_units"] == design[1]["synthetic_gid1_native_advance_font_units"],
            "q0_and_q65_preserved": all(row["readback_normalized_f2dot14"] == [0, q, 0]
                for row, (_, q) in zip(normalized, INPUTS)),
            "designed_metric_distinction_observed": [row["synthetic_gid1_native_advance_font_units"]
                for row in normalized] == [500, 565]}
    finally:
        hb.close()
    if ft_path:
        report["freetype"] = freetype_probe(ft_path, data)
    else:
        report["freetype"] = {"status": "NOT_RUN_UNAVAILABLE_NO_INSTALL_ATTEMPTED"}
    report["status"] = STATUS
    report["conditional_native_channel_proven_on_this_runtime"] = all(report["harfbuzz"][key]
        for key in ("design_float32_collision", "native_design_output_collision",
                    "q0_and_q65_preserved", "designed_metric_distinction_observed"))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "new_report_path_required")
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "conditional_native_channel_proven_on_this_runtime":
        result.get("conditional_native_channel_proven_on_this_runtime", False)}))
