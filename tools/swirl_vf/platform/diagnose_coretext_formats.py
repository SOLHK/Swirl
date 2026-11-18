#!/usr/bin/env python3
"""Minimal authored outline-format controls; no source-font data or gate waiver.

The same one-face, two-glyph, three-axis font is serialized with standard
glyf/loca/gvar, with both outline formats, and with HVGL only. No axes, names,
character mappings or metrics change. The raw SFNT directory is checked before
each file is passed to the actual CoreText URL/data/CGFont/registration APIs.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import platform
import struct
import subprocess

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.sfnt import calcChecksum
from fontTools.ttLib.tables.TupleVariation import TupleVariation

from diagnose_font_sources import harness, inspect, validate_native, require
from macos_source_baseline import digest
from make_synthetic_hvf import create


def fixtures(directory):
    seed = directory / 'authored-hvf-seed.ttf'
    create(seed)
    with TTFont(seed) as original:
        raw = original.getTableData('hvgl')
    # Reuse the existing authored square part twice; account for HVGL's
    # little-endian relative index and double alignment. No Apple bytes enter.
    start, end = struct.unpack_from('<II', raw, 24)
    shape = raw[24+start:24+end]
    hvgl = struct.pack('<HHIIIII', 3, 1, 0, 2, 24, 2, 0)
    hvgl += struct.pack('<III', 16, 16+len(shape), 16+2*len(shape)) + bytes(4) + shape*2
    builder = FontBuilder(1000, isTTF=True)
    order = ['.notdef', 'probe']
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({65: 'probe'})
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0)); pen.lineTo((400, 0)); pen.lineTo((400, 400)); pen.lineTo((0, 400)); pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (500, 0) for name in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupVerticalMetrics({name: (1000, 400) for name in order})
    builder.setupVerticalHeader(ascent=800, descent=-200)
    builder.setupNameTable({'familyName': 'Swirl Authored Format Control', 'styleName': 'Regular',
        'uniqueFontIdentifier': 'SwirlAuthoredFormatControl-1', 'fullName': 'Swirl Authored Format Control Regular',
        'psName': 'SwirlAuthoredFormatControl-Regular', 'version': 'Version 1.0'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupFvar([(tag, -1, 0, 1, tag) for tag in ('WDTH', 'wght', 'HGHT')], [])
    avar = newTable('avar')
    avar.segments = {tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in ('WDTH', 'wght', 'HGHT')}
    builder.font['avar'] = avar
    variations = []
    points = [(0, 0), (400, 0), (400, 400), (0, 400)]
    for tag in ('WDTH', 'wght', 'HGHT'):
        for sign in (-1, 1):
            deltas = [(sign*x//4, 0) if tag == 'WDTH' else (0, sign*y//4) if tag == 'HGHT'
                      else (0, sign*20) for x, y in points] + [(0, 0)]*4
            variations.append(TupleVariation({tag: (min(0, sign), sign, max(0, sign))}, deltas))
    builder.setupGvar({name: copy.deepcopy(variations) for name in order})
    builder.setupMaxp()
    builder.font['head'].created = builder.font['head'].modified = 3_800_000_000
    builder.font.recalcTimestamp = False
    canonical = directory / 'canonical-standard.ttf'
    builder.font.save(canonical)
    outputs = {}
    for mode in ('standard', 'both', 'hvgl-only'):
        font = TTFont(canonical, recalcTimestamp=False)
        if mode != 'standard':
            table = newTable('hvgl'); table.data = hvgl; font['hvgl'] = table
        if mode == 'hvgl-only':
            for tag in ('glyf', 'loca', 'gvar'):
                del font[tag]
            font.recalcBBoxes = False
        path = directory / (mode+'.ttf')
        font.save(path)
        font.close()
        outputs[mode] = path
    return outputs


def directory_check(path):
    data = path.read_bytes()
    require(data[:4] == b'\0\1\0\0', 'authored single TrueType SFNT expected')
    count = struct.unpack_from('>H', data, 4)[0]
    require(12+16*count <= len(data), 'truncated SFNT directory')
    tables, spans = {}, []
    for index in range(count):
        tag, checksum, offset, length = struct.unpack_from('>4sIII', data, 12+16*index)
        tag = tag.decode('ascii')
        require(tag not in tables and offset % 4 == 0 and offset >= 12+16*count
                and offset+length <= len(data), 'invalid SFNT table bounds/alignment')
        raw = data[offset:offset+length]
        checked = raw[:8]+bytes(4)+raw[12:] if tag == 'head' else raw
        require(calcChecksum(checked) == checksum, 'authored table checksum differs')
        spans.append((offset, offset+length))
        tables[tag] = {'offset': offset, 'length': length}
    require(all(left[1] <= right[0] for left, right in zip(sorted(spans), sorted(spans)[1:])),
            'authored tables overlap')
    require(calcChecksum(data) == 0xB1B0AFBA, 'authored global checksum differs')
    return {'status': 'PASS', 'tables': tables, 'bytes': len(data), 'sha256': digest(path)}


def run(output):
    require(platform.system() == 'Darwin', 'native format comparison NOT_RUN: macOS required')
    output = Path(output).absolute()
    require(not output.exists() and not output.is_symlink(), 'fresh private output required')
    output.mkdir(parents=True, mode=0o700)
    swift, binary = output / 'probe.swift', output / 'probe'
    swift.write_text(harness())
    build = subprocess.run(['xcrun', 'swiftc', '-O', str(swift), '-o', str(binary)], capture_output=True, timeout=180)
    (output / 'compile.log').write_bytes(build.stdout+build.stderr)
    require(build.returncode == 0, 'native probe build failed')
    report = {'scope': 'SELF_AUTHORED_ONLY', 'host': platform.platform(), 'production_fix_accepted': False,
              'probe_sha256': digest(binary), 'harness_sha256': digest(swift), 'cases': {}}
    for mode, path in fixtures(output).items():
        directory = directory_check(path)
        parsed = inspect(path)
        process = subprocess.run([str(binary), str(path)], capture_output=True, timeout=180)
        (output / (mode+'.stdout')).write_bytes(process.stdout)
        (output / (mode+'.stderr')).write_bytes(process.stderr)
        require(process.returncode == 0, 'native format diagnosis failed')
        native = json.loads(process.stdout)
        validate_native(native, parsed)
        report['cases'][mode] = {'sfnt': directory, 'parsed': parsed, 'native': native, 'exit': process.returncode}
        (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({mode: {'physical_faces': row['native']['physical_faces'],
        'verified_faces': row['native']['native_identity_faces'], 'register_error': row['native'].get('register_error_code')}
        for mode, row in report['cases'].items()}))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    run(p.parse_args().output)
