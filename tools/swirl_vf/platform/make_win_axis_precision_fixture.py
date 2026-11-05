#!/usr/bin/env python3
"""Build original, deterministic three-axis fonts for the D1 Windows experiment.

Usage: python make_win_axis_precision_fixture.py OUTPUT_DIRECTORY

The ordinary font is a small rendering/control fixture.  The gain font has
deliberately extreme but valid monotone avar segments and large integral deltas
so that candidate normalization paths can produce observably different outlines
and advances.  Predictions in the manifest are hypotheses, not Windows results.
No glyph, table or metric is taken from an Apple font.

Primary references consulted before this independent implementation:
https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/fontBuilder.py
https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/varLib/builder.py
https://learn.microsoft.com/en-us/typography/opentype/spec/avar
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview
"""
from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_FLOOR
import hashlib
import json
import math
from pathlib import Path
import struct

from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.builder import buildVarData, buildVarRegionList, buildVarStore


SCHEMA = 1
GLYPHS = (".notdef", "space", "A", "B", "uni4E2D", "uni6587")
AXES = (
    ("wght", 100.0, 400.0, 900.0, "Weight"),
    ("WDTH", 50.0, 100.0, 200.0, "Fixture Width"),
    ("HGHT", 50.0, 100.0, 200.0, "Fixture Height"),
)
CMAP = {32: "space", 65: "A", 66: "B", 0x4E2D: "uni4E2D", 0x6587: "uni6587"}
PAIR = ("499.006199", "499.006201")
FIXED_TIME = 3_800_000_000
IDENTITY_MAP = {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0}
GAIN_MAP = {
    -1.0: -1.0,
    -16383 / 16384: 0.0,
    0.0: 0.0,
    3244 / 16384: 0.0,
    3245 / 16384: 1.0,
    1.0: 1.0,
}


def float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def float32_bits(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def float32_from_bits(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


def nearest_fixed16(value: str | float) -> int:
    """Explicit ties-to-positive-infinity; all planned user values are positive."""
    precise = Decimal(value) if isinstance(value, str) else Decimal.from_float(value)
    return int((precise * 65536 + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR))


def exact_decimal(value: float) -> str:
    return format(Decimal.from_float(value), "f")


def normalize(value: float, axis: tuple) -> float:
    _, minimum, default, maximum, _ = axis
    value = min(maximum, max(minimum, value))
    if value == default:
        return 0.0
    return (value - default) / ((default - minimum) if value < default else (maximum - default))


def segment_map(value: float, mapping: dict[float, float]) -> float:
    points = sorted(mapping.items())
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if value <= x1:
            return y0 + (value - x0) * (y1 - y0) / (x1 - x0)
    return points[-1][1]


def requests() -> list[dict]:
    """Predeclared tests; IDs and original decimal spellings survive native input."""
    result = []

    def add(case_id: str, wght: str = "400", WDTH: str = "100", HGHT: str = "100") -> None:
        result.append({"id": case_id, "decimal": {"wght": wght, "WDTH": WDTH, "HGHT": HGHT}})

    add("default")
    add("pair_lo", PAIR[0])
    add("pair_hi", PAIR[1])
    center_bits = float32_bits(float(PAIR[0]))
    for offset in (-2, -1, 0, 1, 2):
        add("f32_" + ("m" + str(-offset) if offset < 0 else "p" + str(offset)),
            exact_decimal(float32_from_bits(center_bits + offset)))
    add("wght_min", "100")
    add("wght_max", "900")
    add("WDTH_min", WDTH="50")
    add("WDTH_max", WDTH="200")
    add("HGHT_min", HGHT="50")
    add("HGHT_max", HGHT="200")
    add("mixed_min", "100", "50", "50")
    add("mixed_max", "900", "200", "200")
    # Below 128, float32 spacing is 1/131072.  These controls can distinguish
    # a user-coordinate 16.16 rounding step; at 499, binary32 is already coarser.
    for offset in range(5):
        add("low_f32_" + str(offset), exact_decimal(100 + offset / 131072))
    lo = 400 + 500 * 3244 / 16384
    hi = 400 + 500 * 3245 / 16384
    for label, fraction in (("lo", 0), ("quarter", 0.25), ("mid", 0.5),
                            ("three_quarter", 0.75), ("hi", 1)):
        add("ramp_" + label, exact_decimal(lo + fraction * (hi - lo)))
    midpoint = float32_bits((lo + hi) / 2)
    add("ramp_mid_f32_below", exact_decimal(float32_from_bits(midpoint - 1)))
    add("ramp_mid_f32_above", exact_decimal(float32_from_bits(midpoint + 1)))
    for case in result:
        numeric = {tag: float(value) for tag, value in case["decimal"].items()}
        case["requested_binary64"] = numeric
        case["binary64_hex"] = {tag: value.hex() for tag, value in numeric.items()}
        case["float32"] = {tag: float32(value) for tag, value in numeric.items()}
        case["float32_bits_hex"] = {tag: f"0x{float32_bits(value):08x}" for tag, value in numeric.items()}
        case["nearest_16_16"] = {tag: nearest_fixed16(value) for tag, value in case["decimal"].items()}
    return result


def _glyph(name: str, width: int):
    # Abstract fixture marks. CJK cmap coverage is for layout identity tests,
    # and must never be described as a Chinese typeface or regional glyph set.
    polygons = {
        ".notdef": [[(0, 0), (0, 1), (1, 1), (1, 0)],
                    [(0.25, 0.5), (0.75, 0.5), (0.75, 0.75), (0.25, 0.75)]],
        "space": [],
        "A": [[(0, 0), (0.5, 1), (1, 0)]],
        "B": [[(0, 0), (0, 1), (0.75, 1), (1, 0.5), (0.75, 0)]],
        "uni4E2D": [[(0, 0), (0, 1), (1, 1), (1, 0)],
                    [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]],
        "uni6587": [[(0, 0), (0.5, 0.5), (0, 1), (1, 1), (0.5, 0.5), (1, 0)]],
    }
    pen = TTGlyphPen(None)
    for polygon in polygons[name]:
        points = [(60 + int(x * width), int(y * 700)) for x, y in polygon]
        pen.moveTo(points[0])
        for point in points[1:]:
            pen.lineTo(point)
        pen.closePath()
    return pen.glyph()


def make_font(path: Path, gain: bool = False) -> dict:
    family = "Swirl D1 Precision" + (" Gain" if gain else "")
    advance = 16000 if gain else 600
    outline_width = 15000 if gain else 440
    weight_delta = 12000 if gain else 180
    width_delta = 600 if gain else 180
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(list(GLYPHS))
    fb.setupCharacterMap(CMAP)
    glyphs = {name: _glyph(name, outline_width) for name in GLYPHS}
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (advance, 0 if name == "space" else 60) for name in GLYPHS})
    fb.setupHorizontalHeader(ascent=850, descent=-150, lineGap=0)
    fb.setupNameTable({
        "familyName": family, "styleName": "Regular",
        "typographicFamily": family, "typographicSubfamily": "Regular",
        "uniqueFontIdentifier": family + ";D1;1.000;original-synthetic",
        "fullName": family + " Regular", "psName": family.replace(" ", "") + "-Regular",
        "version": "Version 1.000 D1 original synthetic",
        "copyright": "Original synthetic diagnostic geometry for Swirl D1; no Apple font data.",
    })
    fb.setupOS2(version=4, sTypoAscender=850, sTypoDescender=-150, sTypoLineGap=0,
                usWinAscent=1000, usWinDescent=250, usWeightClass=400,
                usWidthClass=5, fsType=0, fsSelection=0xC0, sxHeight=350, sCapHeight=700)
    fb.setupPost()
    fb.setupMaxp()
    fb.setupFvar(list(AXES), [
        {"location": {"wght": 100, "WDTH": 100, "HGHT": 100}, "stylename": "Thin"},
        {"location": {"wght": 400, "WDTH": 100, "HGHT": 100}, "stylename": "Regular"},
        {"location": {"wght": 900, "WDTH": 100, "HGHT": 100}, "stylename": "Black"},
    ])
    avar = fb.font["avar"] = newTable("avar")
    avar.majorVersion, avar.minorVersion = 1, 0
    avar.segments = {tag: dict(GAIN_MAP if gain and tag == "wght" else IDENTITY_MAP)
                     for tag, *_ in AXES}
    supports = []
    deltas = []
    for tag, delta in (("wght", weight_delta), ("WDTH", width_delta), ("HGHT", 120)):
        supports.extend(({tag: (-1.0, -1.0, 0.0)}, {tag: (0.0, 1.0, 1.0)}))
        deltas.extend(((tag, -delta), (tag, delta)))
    variations = {}
    for name, glyph in glyphs.items():
        coordinates, _, _ = glyph.getCoordinates(fb.font["glyf"])
        tuples = []
        for support, (tag, delta) in zip(supports, deltas):
            outline = []
            for x, y in coordinates:
                dx = round((x - 60) * delta / outline_width) if tag != "HGHT" else 0
                dy = round(y * delta / 700) if tag == "HGHT" else 0
                outline.append((dx, dy))
            metric_delta = delta if tag != "HGHT" else 0
            tuples.append(TupleVariation(support, outline + [(0, 0), (metric_delta, 0), (0, 0), (0, 0)]))
        variations[name] = tuples
    fb.setupGvar(variations)
    hvar = fb.font["HVAR"] = newTable("HVAR")
    hvar.table = otTables.HVAR()
    hvar.table.Version = 0x10000
    region_list = buildVarRegionList(supports, [axis[0] for axis in AXES])
    rows = [[delta if tag != "HGHT" else 0 for tag, delta in deltas] for _ in GLYPHS]
    hvar.table.VarStore = buildVarStore(region_list, [buildVarData(list(range(6)), rows, optimize=False)])
    hvar.table.AdvWidthMap = None  # glyph ID indexes the one VarData's rows.
    hvar.table.LsbMap = hvar.table.RsbMap = None
    buildStatTable(fb.font, [
        {"tag": "wght", "name": "Weight", "ordering": 0,
         "values": [{"value": 100, "name": "Thin"},
                    {"value": 400, "name": "Regular", "flags": 2},
                    {"value": 900, "name": "Black"}]},
        {"tag": "WDTH", "name": "Fixture Width", "ordering": 1,
         "values": [{"value": 100, "name": "Normal Width", "flags": 2}]},
        {"tag": "HGHT", "name": "Fixture Height", "ordering": 2,
         "values": [{"value": 100, "name": "Normal Height", "flags": 2}]},
    ], elidedFallbackName="Regular")
    fb.font["head"].created = fb.font["head"].modified = FIXED_TIME
    fb.font.recalcTimestamp = False
    path.parent.mkdir(parents=True, exist_ok=True)
    fb.save(path)
    contents = path.read_bytes()
    # Reopen the actual serialized bytes, not the builder's in-memory objects.
    with TTFont(path, recalcTimestamp=False) as reopened:
        tables = {tag: hashlib.sha256(reopened.getTableData(tag)).hexdigest()
                  for tag in ("head", "name", "fvar", "avar", "glyf", "gvar", "HVAR", "STAT")}
        samples = {}
        for tag, minimum, default, maximum, _ in AXES:
            for label, value in (("min", minimum), ("default", default), ("max", maximum)):
                location = {axis[0]: axis[2] for axis in AXES}
                location[tag] = value
                glyph_set = reopened.getGlyphSet(location=location)
                pen = BoundsPen(glyph_set)
                glyph_set["A"].draw(pen)
                samples[tag + "_" + label] = {"A_advance": glyph_set["A"].width, "A_bounds": pen.bounds}
    return {"kind": "gain" if gain else "ordinary", "file": path.name, "family": family,
            "sha256": hashlib.sha256(contents).hexdigest(), "bytes": len(contents),
            "units_per_em": 1000, "glyph_order": list(GLYPHS),
            "tables_sha256": tables, "serialized_control_samples": samples,
            "base_A_advance": advance, "base_A_rightmost": 60 + outline_width,
            "weight_delta": weight_delta, "width_delta": width_delta,
            "height_delta": 120,
            "wght_avar": [list(pair) for pair in sorted((GAIN_MAP if gain else IDENTITY_MAP).items())]}


def model_predictions(case: dict, font: dict) -> dict:
    """Numerical discriminators, explicitly not a claim about DirectWrite code."""
    predictions = {}
    for model in ("binary32_continuous", "binary32_user16_continuous",
                  "binary32_normalize16_before_avar", "binary32_normalize14_before_avar"):
        normalized = {}
        mapped = {}
        for axis in AXES:
            tag = axis[0]
            value = case["float32"][tag]
            if model == "binary32_user16_continuous":
                value = nearest_fixed16(value) / 65536
            q = normalize(value, axis)
            if model == "binary32_normalize16_before_avar":
                q = math.floor(q * 65536 + 0.5) / 65536
            elif model == "binary32_normalize14_before_avar":
                q = math.floor(q * 16384 + 0.5) / 16384
            normalized[tag] = q
            mapped[tag] = segment_map(q, GAIN_MAP if font["kind"] == "gain" and tag == "wght" else IDENTITY_MAP)
        dx = mapped["wght"] * font["weight_delta"] + mapped["WDTH"] * font["width_delta"]
        predictions[model] = {"normalized_before_avar": normalized,
                              "normalized_after_avar": mapped,
                              "A_advance_unrounded": font["base_A_advance"] + dx,
                              "A_rightmost_unrounded": font["base_A_rightmost"] + dx,
                              "A_top_unrounded": 700 + mapped["HGHT"] * font["height_delta"]}
    return predictions


def write_fixture(directory: Path) -> dict:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    cases = requests()
    fonts = [make_font(directory / "ordinary.ttf"), make_font(directory / "gain.ttf", gain=True)]
    tsv = "id\twght\tWDTH\tHGHT\n" + "".join(
        "\t".join([case["id"]] + [case["decimal"][axis[0]] for axis in AXES]) + "\n" for case in cases)
    (directory / "requests.tsv").write_text(tsv, encoding="ascii", newline="\n")
    manifest = {
        "schema": SCHEMA, "original_synthetic": True,
        "original_apple_acceptance": "NOT_RUN", "windows_native_results": "NOT_RUN",
        "axes": [{"tag": tag, "minimum": minimum, "default": default, "maximum": maximum}
                 for tag, minimum, default, maximum, _ in AXES],
        "fonts": fonts, "cases": cases, "requests_file": "requests.tsv",
        "requests_sha256": hashlib.sha256(tsv.encode("ascii")).hexdigest(),
        "pair_float32_ulp": float32_from_bits(float32_bits(float(PAIR[0])) + 1) - float32(float(PAIR[0])),
        "numeric_model_scope": "Predeclared analytic discriminators, not native outputs; no Windows internal quantizer is asserted.",
        "predictions": {font["kind"]: {case["id"]: model_predictions(case, font) for case in cases} for font in fonts},
        "limits": [
            "CJK codepoints map to original abstract fixture marks; regional Chinese shaping is not tested.",
            "The gain font intentionally uses unusually large metrics; it is not a UI typography candidate.",
            "API readback equality does not alone establish outline, advance or raster equality.",
            "System installation, DirectWrite execution and Qt rendering require native Windows evidence.",
        ],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    manifest = write_fixture(args.output_directory)
    print(json.dumps({"schema": SCHEMA, "status": "GENERATED_ORIGINAL_SYNTHETIC",
                      "files": [font["file"] for font in manifest["fonts"]],
                      "cases": len(manifest["cases"]), "windows_native_results": "NOT_RUN"}))


if __name__ == "__main__":
    main()
