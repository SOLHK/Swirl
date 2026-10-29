#!/usr/bin/env python3
"""Create a tiny, original geometric HVF fixture without any Apple font data.

This is a renderer test container, not a replacement font. Only one square glyph
exists. Its three orthogonal axes move independent points by known amounts.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import struct

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import newTable


def create(path: Path) -> None:
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef"])
    builder.setupCharacterMap({})
    pen = TTGlyphPen(None)
    pen.moveTo((0, 0)); pen.lineTo((400, 0)); pen.lineTo((400, 400)); pen.lineTo((0, 400)); pen.closePath()
    builder.setupGlyf({".notdef": pen.glyph()})
    builder.setupHorizontalMetrics({".notdef": (500, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Swirl Synthetic HVF Fixture", "styleName": "Regular",
                           "uniqueFontIdentifier": "Swirl-Synthetic-HVF-1",
                           "fullName": "Swirl Synthetic HVF Fixture Regular", "psName": "SwirlSyntheticHVF"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    builder.setupFvar([("WDTH", -1, 0, 1, "Width"), ("wght", -1, 0, 1, "Weight"),
                      ("HGHT", -1, 0, 1, "Height")], [])
    # 4 segment records: explicit on-curve point followed by off-curve point.
    base = [0, 0, 200, 0, 400, 0, 400, 200, 400, 400, 200, 400, 0, 400, 0, 200]
    columns = []
    for axis in range(3):
        for sign in (-1, 1):
            delta = [0.0] * 16
            if axis == 0:  # Width affects every x, with a known linear slope.
                delta = [sign * value * 0.25 if i % 2 == 0 else 0 for i, value in enumerate(base)]
            elif axis == 1:  # A vertical translation; deliberately not a real typeface.
                delta = [sign * 20.0 if i % 2 else 0 for i in range(16)]
            else:  # Height affects every y.
                delta = [sign * value * 0.25 if i % 2 else 0 for i, value in enumerate(base)]
            columns.extend(delta)
    shape = struct.pack("<HHHHH", 0, 3, 1, 4, 4) + bytes([1] * 4) + b"\0\0"
    shape += struct.pack("<16d", *base) + struct.pack("<96d", *columns)
    hvgl = struct.pack("<HHIIIII", 3, 1, 0, 1, 24, 1, 0)
    hvgl += struct.pack("<II", 8, 8 + len(shape)) + shape
    table = newTable("hvgl")
    table.data = hvgl
    builder.font["hvgl"] = table
    # Keeping conventional outlines here would let a broken test silently use
    # the standard glyf table; the oracle must use the synthetic HVF table.
    del builder.font["glyf"]
    del builder.font["loca"]
    builder.font.recalcBBoxes = False
    builder.font.recalcTimestamp = False
    path.parent.mkdir(parents=True, exist_ok=True)
    builder.save(str(path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    create(parser.parse_args().output)
