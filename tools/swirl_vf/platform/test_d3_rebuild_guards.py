#!/usr/bin/env python3
"""Native admission and actual shaping on C1's self-authored GDEF witness only."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import platform
import sys

from fontTools.ttLib import TTCollection
import uharfbuzz as hb

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'tests')]
import rebuild
from test_d3_layout_admission import layout_fixture


def run(output, binary):
    output.mkdir(parents=True, exist_ok=False)
    if sys.platform != 'darwin':
        summary = {'status': 'NOT_RUN', 'reason': 'CoreText requires macOS'}
        (output/'summary.json').write_text(json.dumps(summary)+'\n')
        return summary, 2
    source, control = output/'source.ttc', output/'identity-avar-control.ttc'
    layout_fixture(source, variable=True)
    before = rebuild.sha256(source)
    with TTCollection(source) as collection:
        collection.fonts[0]['avar'].segments['wght'].pop(.5)
        collection.save(control)
    rows = []
    for path in (source, control):
        font = hb.Font(hb.Face(path.read_bytes(), 0))
        font.scale = (1000, 1000)
        font.set_variations({'WDTH': 500, 'wght': 700, 'HGHT': 500})
        advances = []
        for kern in (False, True):
            buffer = hb.Buffer()
            buffer.add_str('A')
            buffer.guess_segment_properties()
            hb.shape(font, buffer, {'kern': kern})
            assert [glyph.codepoint for glyph in buffer.glyph_infos] == [1]
            advances.append(buffer.glyph_positions[0].x_advance)
        rows.append({'fixture': path.stem, 'unpositioned_advance': advances[0],
                     'positioned_advance': advances[1], 'GPOS_adjustment': advances[1]-advances[0]})
    assert [row['GPOS_adjustment'] for row in rows] == [5, 30]
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            rebuild.run(source, binary.resolve(strict=True), output/'Swirl-VF.ttc', output/'private-report.json')
        except rebuild.ReconstructionError as error:
            assert str(error).startswith('GDEF variable layout'), str(error)
        else:
            raise AssertionError('production must refuse unremapped GDEF')
    report = json.loads((output/'private-report.json').read_text())
    assert report['native_observation_progress']['attempted_batches_this_run'] == 0
    assert report['output_generated'] is False and not (output/'Swirl-VF.ttc').exists()
    assert rebuild.sha256(source) == before
    assert len(report['oracle']['faces']) == 1
    assert report['oracle']['faces'][0]['status'] == 'identity_verified'
    summary = {'status': 'PASS_SYNTHETIC_NATIVE_ADMISSION_ONLY', 'host': platform.platform(),
        'scope': 'self_authored_analytic_no_Apple_data', 'harfbuzz_version': hb.version_string(),
        'shaping': rows, 'native_backend': report['oracle']['backend'], 'physical_faces_verified': 1,
        'native_glyph_batches': 0, 'source_unchanged': True, 'font_generated': False,
        'original_conversion_faces': 0, 'Windows11': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN'}
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary, 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--binary', required=True, type=Path)
    args = parser.parse_args()
    summary, status = run(args.output, args.binary)
    print(json.dumps(summary))
    raise SystemExit(status)
