#!/usr/bin/env python3
"""Public, independently authored four-face joint-gvar/Medium control.

Generate with --output; verify actual DirectWrite exported outlines with
--native. The expected continuous polynomial never reads the encoded deltas.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.otlLib.builder import buildStatTable
from fontTools.ttLib import TTCollection, newTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from windows_gvar import TensorModel, compile_glyph, TAGS, LIMIT
from metric_variations import add_metric_variations

AXES = [('wdth', 80, 100, 120, 'Width'), ('wght', 100, 500, 900, 'Weight'), ('HGHT', 1, 500, 1000, 'Height')]
LABELS = ('SC Text', 'SC Display', 'TC Text', 'TC Display')
SCALE = 15


def formula(location, face):
    x, y, z = location
    optical = 20 if face % 2 else 0
    dx = 20*x+10*y+7*z+13*x*y+11*x*z+17*y*z+19*x*y*z
    dy = 3*x+15*y+30*z+23*x*y-7*x*z+5*y*z-11*x*y*z
    w = 300+50*x+30*y+7*x*y+13*x*y*z
    h = 650+70*z+40*y+10*x*z+17*x*y*z+optical
    return np.asarray([(60+dx, 40+dy), (60+w+dx, 40+dy), (60+w+dx, 40+h+dy), (60+dx, 40+h+dy)])


def make(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('fresh_authored_output_required')
    collection = TTCollection()
    model = TensorModel([-1., 0., 1.])
    for fi, label in enumerate(LABELS):
        values = np.asarray([np.vstack((formula(p, fi), [(0, 0), (600+50*p[0]+20*p[0]*p[1]*p[2], 0),
                                                        (0, 880), (0, -120)]))*SCALE for p in model.locations])
        glyph, variations, hm, vm, _, _ = compile_glyph(model, values, [1]*4, [3])
        b = FontBuilder((1064 if fi % 2 else 1028)*SCALE, isTTF=True)
        b.setupGlyphOrder(['.notdef', 'A'])
        b.setupCharacterMap({65: 'A', 0x4e2d: 'A', 0x9ad4: 'A', 48: 'A', 0x3002: 'A'})
        b.setupGlyf({n: glyph for n in ('.notdef', 'A')})
        b.setupHorizontalMetrics({n: hm for n in ('.notdef', 'A')})
        b.setupVerticalMetrics({n: vm for n in ('.notdef', 'A')})
        b.setupHorizontalHeader(ascent=884*SCALE, descent=-144*SCALE)
        b.setupVerticalHeader(ascent=500*SCALE, descent=-500*SCALE)
        family = 'SwirlVF Control '+label
        b.setupNameTable(dict(familyName=family, styleName='Regular', typographicFamily=family,
                             typographicSubfamily='Regular', fullName=family, uniqueFontIdentifier=family+'-1',
                             psName=family.replace(' ', ''), version='Version 0.1.0 Authored control'))
        b.setupOS2(sTypoAscender=884*SCALE, sTypoDescender=-144*SCALE, usWinAscent=1060*SCALE, usWinDescent=340*SCALE)
        b.setupPost()
        b.setupMaxp()
        b.setupFvar(AXES, [dict(stylename=n, location={'wdth': 100, 'wght': w, 'HGHT': 500})
                          for n, w in [('Light', 300), ('Regular', 400), ('Medium', 500), ('Semibold', 600), ('Bold', 700)]])
        buildStatTable(b.font, [dict(tag=t, name=title, values=(
            [dict(value=w, name=n, flags=2 if n == 'Regular' else 0) for n, w in
             [('Light', 300), ('Regular', 400), ('Medium', 500), ('Semibold', 600), ('Bold', 700)]]
            if t == 'wght' else [dict(value=d, name='Normal', flags=2)])) for t, lo, d, hi, title in AXES])
        b.font['gvar'] = newTable('gvar')
        b.font['gvar'].variations = {n: variations for n in ('.notdef', 'A')}
        b.font['avar'] = newTable('avar')
        b.font['avar'].majorVersion, b.font['avar'].minorVersion = 1, 0
        b.font['avar'].segments = {t: {-1.: -1., 0.: 0., 1.: 1.} for t in TAGS}
        add_metric_variations(b.font)
        collection.fonts.append(b.font)
    collection.save(output)
    return dict(scope='AUTHORED_NO_PRIVATE_DATA', faces=4, glyphs_per_face=2, bytes=output.stat().st_size)


def verify(native, output):
    native = Path(native)
    rows = [json.loads(line) for line in (native/'outline-coordinates.jsonl').read_text().splitlines()]
    maximum, failures, faces, count = 0., [], set(), 0
    for row in rows:
        if row.get('record') != 'outline':
            continue
        p = [(row['axes'][t]-d)/(d-lo if row['axes'][t] < d else hi-d) for t, lo, d, hi, _ in AXES]
        expected = formula(p, row['face_index'])
        commands = row['commands']
        points = np.asarray([[c[1], -c[2]] for c in commands if c[0] in ('moveTo', 'lineTo')])/SCALE
        # Closing point may be explicitly emitted by the TrueType engine.
        if len(points) == 5 and np.array_equal(points[0], points[-1]):
            points = points[:-1]
        error = float(np.linalg.norm(points-expected, axis=-1).max()) if points.shape == expected.shape else None
        if error is None or error > LIMIT:
            failures.append(dict(face=row['face_index'], case=row['case'], error=error))
        maximum = max(maximum, error or 0.)
        faces.add(row['face_index']); count += 1
    report = dict(scope='AUTHORED_NO_PRIVATE_DATA', engine='DirectWrite', observations=count,
                  faces=sorted(faces), maximum_error_source_units=maximum, threshold=LIMIT,
                  failures=failures, original_font_acceptance=False, desktop_installation='NOT_RUN')
    if faces != set(range(4)) or count < 400:
        report['transcript_failure'] = 'missing_faces_or_positions'
    Path(output).write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    return not failures and 'transcript_failure' not in report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--native', type=Path)
    args = p.parse_args()
    if args.native:
        raise SystemExit(0 if verify(args.native, args.output) else 1)
    print(json.dumps(make(args.output)))
