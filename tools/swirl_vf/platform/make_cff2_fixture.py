#!/usr/bin/env python3
"""Generate original CFF2 controls; accepts no private source font.

The quadratic control comes from the existing authored CoreText fixture. A
quarter-unit X translation deliberately exercises fractional default points.
Its two TTC faces, GIDs and three axes are retained. This is not SwirlVF.ttc.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
import tempfile

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import cff2_geometry as geometry
from cff2_metrics import prepare_from_truetype
from test_coretext_extract import make_fixture

TAGS = ('WDTH', 'wght', 'HGHT')
GRID = [dict(zip(TAGS, p)) for p in itertools.product((-1., 0., 1.), repeat=3)]
HOLDOUTS = [dict(zip(TAGS, p)) for p in ((.25, -.5, .75), (.125, .375, -.625))]


def records(font, name, locations, translation=0., *, repeat_contours=1):
    result = []
    for location in locations:
        glyph = font.getGlyphSet(location=location, normalized=True, recalcBounds=False)[name]
        commands = geometry.source_commands(glyph)
        for command in commands:
            for index in range(1, len(command), 2):
                command[index] += translation
        result.append(commands * repeat_contours)
    return result


def convert(font, translation=0., *, factored=False, compact=False, repeat_contours=1):
    if type(repeat_contours) is not int or not 1 <= repeat_contours <= 1024:
        raise ValueError('invalid_authored_contour_repeat')
    if factored and compact:
        raise ValueError('choose_one_cff2_encoding')
    grid, held = GRID, HOLDOUTS
    if factored or compact:
        # More Cartesian regions than the CFF2 operand stack can hold in a
        # flat blend. Algebraic factoring must preserve the same function.
        grid = [dict(zip(TAGS, p)) for p in itertools.product(
            tuple(i / 4 for i in range(-4, 5)), repeat=3)]
        held = [dict(zip(TAGS, p)) for p in ((.17, -.31, .79), (-.77, .42, .57))]
    models = {}
    for name in font.getGlyphOrder():
        model = geometry.fit(records(font, name, grid, translation, repeat_contours=repeat_contours), grid,
                             records(font, name, held, translation, repeat_contours=repeat_contours), held, TAGS)
        models[name] = (geometry.factor(model) if factored else
                        geometry.compact(model) if compact else model)
    return geometry.install(prepare_from_truetype(font), models), models


def write_fixture(path, *, factored=False, compact=False, repeat_contours=1):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError('fresh_authored_cff2_output_required')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=path.parent) as tmp:
        source = Path(tmp) / 'authored-source.ttc'; make_fixture(source)
        with TTCollection(source) as original:
            conversions = [convert(font, .25, factored=factored, compact=compact,
                                   repeat_contours=repeat_contours)
                           for font in original.fonts]
            result = TTCollection(); result.fonts = [font for font, _ in conversions]
            output = Path(tmp) / 'authored-cff2.ttc'; result.save(output)
            # A serialized read is required before exposing even an authored control.
            with TTCollection(output) as saved:
                if len(saved.fonts) != 2 or not all('CFF2' in font and
                        font['maxp'].numGlyphs == 3 for font in saved.fonts):
                    raise ValueError('authored_cff2_serialized_coverage_changed')
            output.replace(path)
    return {'scope': 'authored CFF2 control, not original-font conversion',
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'bytes': path.stat().st_size, 'faces': 2, 'glyphs_per_face': 3,
            'axes': list(TAGS), 'factored_blends': factored, 'compact_blends': compact,
            'repeat_contours': repeat_contours, 'production_accepted': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    encoding = parser.add_mutually_exclusive_group()
    encoding.add_argument('--factored', action='store_true')
    encoding.add_argument('--compact', action='store_true')
    args = parser.parse_args()
    print(json.dumps(write_fixture(args.output, factored=args.factored, compact=args.compact), indent=2))
