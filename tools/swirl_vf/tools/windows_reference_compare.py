"""Private structural/coupling comparison; never infer cross-version fidelity.

The two versions have no verified physical-axis correspondence. Coupling is
measured WITHIN each font using compatible points and its own normalized space.
These numbers are not a geometric error between different versions/locations.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from fontTools.pens.recordingPen import RecordingPointPen
from fontTools.ttLib import TTCollection

from batch_geometry import BatchGeometry
from hvf import HVGL
from source_metrics import SourceMetrics
from windows_font_builder import SOURCE_SHA, source_vectors
from windows_font_inventory import sha256
from windows_gvar import TensorModel, TAGS, require

REFERENCE_SHA = '124bab748149ea99cd26727384c80f53c92b8abbb3299c66770668ca55ae438b'
TEXT = '中文简體繁漢龍鬱龜永國国测試AaWg0129，。！？（）'


def coupling(values, model):
    coefficients = model.coefficients(values)
    return {str(d): float(max((np.linalg.norm(c, axis=-1).max(initial=0)
                              for c, support in zip(coefficients, model.supports) if len(support) == d), default=0))
            for d in (1, 2, 3)}


def compare(args):
    require(sha256(args.source) == SOURCE_SHA and sha256(args.reference) == REFERENCE_SHA, 'input_version_mismatch')
    require(not args.output.exists() and not args.output.resolve().is_relative_to(Path(__file__).resolve().parents[3]),
            'fresh_private_report_required')
    model = TensorModel([-1., 0., 1.])
    locations = model.locations*.5
    report = dict(source_sha256=SOURCE_SHA, reference_sha256=REFERENCE_SHA,
                  source_version='22.0d5e2', reference_version='21.4d1e1',
                  physical_axis_alignment='NOT_ESTABLISHED_ACROSS_VERSIONS',
                  cross_version_conversion_error='NOT_IDENTIFIABLE',
                  measurement='within-font mixed control-point differences at normalized -0.5/0/+0.5', faces=[])
    with TTCollection(args.source, lazy=True) as original, TTCollection(args.reference, lazy=True) as reference:
        renderer = BatchGeometry(HVGL(original.fonts[0].reader['hvgl']), isolated_tangents=True)
        for index, label in enumerate(('SC Text', 'TC Text')):
            source, target = original.fonts[index], reference.fonts[index]
            metrics = SourceMetrics(source)
            sc, rc = source.getBestCmap(), target.getBestCmap()
            rows = []
            for char in dict.fromkeys(TEXT):
                cp = ord(char)
                if cp not in sc or cp not in rc:
                    rows.append(dict(codepoint=cp, status='missing_in_one_version'))
                    continue
                gid = source.getGlyphID(sc[cp])
                actual, _, _ = source_vectors(renderer, metrics, gid, locations, 1)
                points = []
                for p in locations:
                    pen = RecordingPointPen()
                    target.getGlyphSet(location=dict(zip(TAGS, p)), normalized=True)[rc[cp]].drawPoints(pen)
                    points.append([args_[0] for op, args_, kwargs in pen.value if op == 'addPoint'])
                values = np.asarray(points, dtype=float).reshape(len(locations), -1, 2)
                rows.append(dict(codepoint=cp, source_gid=gid, reference_gid=target.getGlyphID(rc[cp]),
                                 source_mixed_coefficients=coupling(actual[:, :-4], model),
                                 reference_mixed_coefficients=coupling(values, model),
                                 source_upem=source['head'].unitsPerEm, reference_upem=target['head'].unitsPerEm))
            report['faces'].append(dict(face=label, source_unicode_count=len(sc), reference_unicode_count=len(rc),
                shared_unicode_count=len(sc.keys() & rc.keys()), source_only_unicode_count=len(sc.keys()-rc.keys()),
                reference_only_unicode_count=len(rc.keys()-sc.keys()), samples=rows))
    args.output.write_text(json.dumps(report, indent=2))
    for face in report['faces']:
        print(json.dumps(dict(face=face['face'], samples=len(face['samples']), maxima={
            origin: {d: max(r[origin][d] for r in face['samples'] if origin in r) for d in ('2', '3')}
            for origin in ('source_mixed_coefficients', 'reference_mixed_coefficients')})))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    compare(p.parse_args())
