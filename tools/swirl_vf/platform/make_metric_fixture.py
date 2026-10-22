#!/usr/bin/env python3
"""Build original two-face, three-axis geometry using the production metric writer.

Contains a blank glyph, a curve, different UPEM values, a mixed width/height
region, and varied vertical advances. No Apple font data is read or emitted.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from metric_variations import add_metric_variations, verify_metric_variations
from test_coretext_extract import make_fixture


def create(output):
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / 'original-synthetic.ttc'
        make_fixture(source)
        with TTCollection(source) as collection:
            for font in collection.fonts:
                add_metric_variations(font)
                font.recalcTimestamp = False
            collection.save(output, shareTables=True)
    with TTCollection(output) as collection:
        return [verify_metric_variations(font) for font in collection.fonts]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps({'fixture_origin': 'self_authored_geometry_only', 'faces': create(args.output)}))
