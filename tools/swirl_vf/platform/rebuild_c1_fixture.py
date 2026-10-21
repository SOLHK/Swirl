"""Original geometric fonts for C1 packaging tests; contains no Apple data.

Every face has its own private-use/BMP/non-BMP/UVS mapping and name. The seven
base GIDs include two empty glyphs, a quadratic curve and an unencoded glyph.
Larger glyph counts are available for local memory/checkpoint stress tests.
The three axis tags deliberately exercise the requested spelling and order;
this synthetic geometry makes no claim about PingFang's axis semantics.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from metric_variations import add_metric_variations


AXES = {"WDTH": (1, 500, 1000), "wght": (100, 500, 900), "HGHT": (1, 500, 1000)}
BASE_ORDER = (".notdef", "space", "A", "regional", "regional.alt", "unencoded", "curve")


def make_face(index, glyph_count=7):
    """Build one independently named original TrueType variable font."""
    if type(index) is not int or not 0 <= index < 32 or type(glyph_count) is not int or not 7 <= glyph_count <= 65535:
        raise ValueError("fixture requires face 0..31 and 7..65535 glyphs")
    order = list(BASE_ORDER) + [f"unused{gid:05d}" for gid in range(7, glyph_count)]
    glyphs, horizontal, vertical, variations = {}, {}, {}, {}
    for gid, name in enumerate(order[:len(BASE_ORDER)]):
        pen = TTGlyphPen(None)
        left, bottom = 10 + gid % 11, -20
        width, height = 240 + index * 2 + gid % 21 * 11, 500 + gid % 17 * 5
        if gid >= 2:
            pen.moveTo((left, bottom))
            pen.lineTo((left + width, bottom))
            if gid == 6:
                pen.qCurveTo((left + width + 20, bottom + height),
                             (left + width // 2, bottom + height + 60))
            else:
                pen.lineTo((left + width, bottom + height))
            pen.lineTo((left, bottom + height))
            pen.closePath()
        glyph = pen.glyph()
        glyph.recalcBounds(None)
        glyphs[name] = glyph
        horizontal[name] = (250 + gid % 21 * 21 + index, glyph.xMin)
        vertical[name] = (1000 + index, 900 - glyph.yMax)
        coords, _, _ = glyph.getCoordinates(None)
        n = len(coords)
        tuples = []
        for tag, amount in (("WDTH", 80), ("wght", 20), ("HGHT", 60)):
            for sign in (-1, 1):
                support = (-1, -1, 0) if sign < 0 else (0, 1, 1)
                delta = []
                for x, y in coords:
                    if tag == "HGHT":
                        delta.append((0, amount * sign if y > bottom else 0))
                    else:
                        delta.append((amount * sign if x > left else 0, 0))
                # The left phantom stays zero. Every metric variation is a
                # second exact encoding of these same four phantom deltas.
                aw = amount * sign if tag != "HGHT" else 0
                top = 30 * sign if tag == "HGHT" else 0
                bottom_delta = -30 * sign if tag == "HGHT" else 0
                delta.extend(((0, 0), (aw, 0), (0, top), (0, bottom_delta)))
                tuples.append(TupleVariation({tag: support}, delta))
        # A mixed-axis coefficient exercises region ordering and interpolation.
        for xsign in (-1, 1):
            for ysign in (-1, 1):
                delta = [(12 * xsign * ysign if x > left else 0, 0) for x, _ in coords]
                delta.extend(((0, 0), (12 * xsign * ysign, 0), (0, 0), (0, 0)))
                supports = {tag: (-1, -1, 0) if sign < 0 else (0, 1, 1)
                            for tag, sign in (("WDTH", xsign), ("HGHT", ysign))}
                tuples.append(TupleVariation(supports, delta))
        assert all(len(t.coordinates) == n + 4 for t in tuples)
        variations[name] = tuples
    # Stress fixtures deliberately repeat only our own geometric templates.
    # Every physical GID still receives serialized outline/variation/metric
    # records; sharing Python objects avoids making the fixture generator the
    # memory bottleneck when testing a full 47,102-GID face.
    for gid, name in enumerate(order[len(BASE_ORDER):], len(BASE_ORDER)):
        template = BASE_ORDER[2 + gid % 5]
        glyphs[name] = glyphs[template]
        horizontal[name] = horizontal[template]
        vertical[name] = vertical[template]
        variations[name] = variations[template]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({32: "space", 65: "A", 0xE000 + index: "regional",
                               0x4E00 + index: "regional.alt", 0x20000 + index: "curve"})
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(horizontal)
    builder.setupHorizontalHeader(ascent=900, descent=-200)
    builder.setupVerticalMetrics(vertical)
    builder.setupVerticalHeader(ascent=500, descent=-500)
    region = ("SC", "TC", "HK", "MO", "JA")[index % 5]
    family = f"C1 Original Geometry {index:02d} {region}"
    builder.setupNameTable({"familyName": family, "styleName": "Medium",
                            "uniqueFontIdentifier": family, "fullName": family + " Medium",
                            "psName": family.replace(" ", "") + "-Medium",
                            "typographicFamily": family, "typographicSubfamily": "Medium"})
    builder.setupOS2(sTypoAscender=900, sTypoDescender=-200, usWinAscent=1000,
                    usWinDescent=200, usWeightClass=500, usWidthClass=1 + index % 9)
    builder.setupPost()
    builder.setupMaxp()
    builder.font["maxp"].numGlyphs = len(order)
    builder.font["hhea"].numberOfHMetrics = len(order)
    builder.font["vhea"].numberOfVMetrics = len(order)
    builder.setupFvar([(tag, *values, tag) for tag, values in AXES.items()],
                      [{"location": {"WDTH": 500, "wght": 500, "HGHT": 500},
                        "stylename": "Medium"},
                       {"location": {"WDTH": 800, "wght": 700, "HGHT": 750},
                        "stylename": "Wide Tall"}])
    font = builder.font
    buildStatTable(font, [{"tag": tag, "name": tag, "ordering": number,
                           "values": [{"value": values[1], "name": "Normal", "flags": 2}]}
                          for number, (tag, values) in enumerate(AXES.items())])
    font["avar"] = newTable("avar")
    font["avar"].majorVersion, font["avar"].minorVersion = 1, 0
    font["avar"].segments = {tag: {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0} for tag in AXES}
    font["gvar"] = newTable("gvar")
    font["gvar"].version, font["gvar"].reserved = 1, 0
    font["gvar"].variations = variations
    add_metric_variations(font)
    uvs = CmapSubtable.newSubtable(14)
    uvs.platformID, uvs.platEncID, uvs.language = 0, 5, 0
    uvs.cmap = {}
    uvs.uvsDict = {0xFE00: [(65, None), (0xE000 + index, "regional.alt")]}
    font["cmap"].tables.append(uvs)
    addOpenTypeFeaturesFromString(font, """
        languagesystem DFLT dflt;
        languagesystem hani ZHS;
        feature locl { sub regional by regional.alt; } locl;
        feature vert { sub A by regional; } vert;
        feature kern { pos A regional -20; } kern;
        table GDEF {
            GlyphClassDef [A regional regional.alt unencoded curve], [], [], [];
        } GDEF;
    """)
    font.recalcTimestamp = False
    font["head"].created = font["head"].modified = 3800000000
    return font


def write_faces(directory, count=32, glyph_count=7):
    """Write deterministic original fixture faces, refusing existing files."""
    if type(count) is not int or not 1 <= count <= 32:
        raise ValueError("fixture face count must be 1..32")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / f"c1-original-{index:02d}.ttf" for index in range(count)]
    if any(path.exists() or path.is_symlink() for path in paths):
        raise FileExistsError("fixture output exists")
    for index, path in enumerate(paths):
        font = make_face(index, glyph_count)
        try:
            with path.open("xb") as output:
                font.save(output)
        finally:
            font.close()
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--faces", type=int, default=32)
    parser.add_argument("--glyphs", type=int, default=7)
    args = parser.parse_args()
    write_faces(args.directory, args.faces, args.glyphs)
