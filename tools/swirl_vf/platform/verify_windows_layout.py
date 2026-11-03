"""Private user-coordinate and OpenType layout observations, not Windows proof.

Uses uharfbuzz's public variation/buffer APIs (Apache-2.0 binding, external
dependency). The source coordinate interpretation retains the A3 hypothesis.
No CoreText mapping, pixel rendering or global precision claim is made here.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import uharfbuzz as hb
from fontTools.pens.recordingPen import RecordingPointPen
from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from windows_font_builder import FACE_PLAN, SOURCE_SHA, source_vectors, source_locations
from windows_font_inventory import sha256
from windows_gvar import TAGS, require
from target_axis_mapping import axes_from_font, source_axis_plan
from batch_geometry import BatchGeometry
from hvf import HVGL
from source_metrics import SourceMetrics


def positions(font):
    default = {a.axisTag: float(a.defaultValue) for a in font['fvar'].axes}
    result = [default]
    for tag, values in [('wght', (100, 300, 400, 500, 600, 700, 900)),
                        ('wdth', (80, 90, 110, 120)), ('HGHT', (1, 250, 750, 1000))]:
        result.extend(default | {tag: float(v)} for v in values)
    return result + [dict(wdth=90., wght=650., HGHT=800.),
                     dict(wdth=112., wght=350., HGHT=300.),
                     dict(wdth=99.5, wght=500.5, HGHT=500.5)]


def shape(font, text, direction, language):
    buffer = hb.Buffer()
    buffer.add_str(text)
    buffer.direction, buffer.language = direction, language
    buffer.guess_segment_properties()
    hb.shape(font, buffer, shapers=['ot'])
    return ([(g.codepoint, g.cluster) for g in buffer.glyph_infos],
            np.asarray([[p.x_advance, p.y_advance, p.x_offset, p.y_offset]
                        for p in buffer.glyph_positions], dtype=float)/64)


def verify(args):
    require(not args.output.exists(), 'fresh_layout_report_required')
    build = json.loads((args.candidate.parent/'report.json').read_text())
    require(build['full_glyph_coverage'] and sha256(args.candidate) == build['sha256']
            and sha256(args.source) == SOURCE_SHA, 'full_candidate_identity_required')
    blobs = [hb.Blob.from_file_path(p) for p in (args.source, args.candidate)]
    report = dict(candidate_sha256=build['sha256'], source_user_mapping='A3_FINITE_HYPOTHESIS',
                  DirectWrite='NOT_RUN', desktop_visual='NOT_RUN', faces=[])
    with TTCollection(args.source, lazy=True) as sc, TTCollection(args.candidate, lazy=True) as tc:
        renderer = BatchGeometry(HVGL(sc.fonts[0].reader['hvgl']), isolated_tangents=True)
        for index, (source_index, label) in enumerate(FACE_PLAN):
            source, target = sc.fonts[source_index], tc.fonts[index]
            engines = [hb.Font(hb.Face(blobs[0], source_index)), hb.Font(hb.Face(blobs[1], index))]
            upem = source['head'].unitsPerEm
            for engine in engines:
                hb.ot_font_set_funcs(engine)
                engine.scale = (upem*64, upem*64)
            axes, metrics = axes_from_font(source), SourceMetrics(source)
            strings = ['中文简体繁體漢字龍鬱龜，。！？（）「」', 'AaWg SwirlVF 0123456789:;!?']
            cmap = target.getBestCmap()
            glyphs = sorted({target.getGlyphID(cmap[ord(c)]) for c in ''.join(strings) if ord(c) in cmap}
                            | {1166, 19177})
            row = dict(face=label, positions=[], glyphs=len(glyphs), layout_observations=0,
                       glyph_cluster_mismatches=0, missing_glyphs=0, max_control_error=0.,
                       max_source_q_mapping_error=0., max_advance_error=0., max_offset_error=0.,
                       max_native_metric_advance_error=0., by_point_size={})
            for position in positions(target):
                engines[1].set_variations(position)
                actual = np.asarray(engines[1].get_var_coords_normalized())
                requested_source = dict(position)
                wdth = position['wdth']
                requested_source['WDTH'] = 500+(wdth-100)/20*(499 if wdth < 100 else 500)
                del requested_source['wdth']
                q = np.asarray([source_axis_plan(a, requested_source[a.tag])['source_q']/16384 for a in axes])
                engines[0].set_var_coords_normalized(q.tolist())
                mapped = source_locations(source, actual[None, :])[0]
                mapping_error = float(np.max(np.abs(mapped-q)))
                row['max_source_q_mapping_error'] = max(row['max_source_q_mapping_error'], mapping_error)
                error = 0.
                glyph_set = target.getGlyphSet(location=dict(zip(TAGS, actual)), normalized=True)
                for gid in glyphs:
                    expected, _, _ = source_vectors(renderer, metrics, gid, q[None, :], 1)
                    pen = RecordingPointPen()
                    glyph_set[target.getGlyphName(gid)].drawPoints(pen)
                    points = np.asarray([a[0] for op, a, kw in pen.value if op == 'addPoint'], dtype=float).reshape(-1, 2)
                    points *= upem/target['head'].unitsPerEm
                    require(points.shape == expected[0, :-4].shape, 'user_position_topology_changed')
                    error = max(error, float(np.linalg.norm(points-expected[0, :-4], axis=1).max(initial=0)))
                row['max_control_error'] = max(row['max_control_error'], error)
                row['positions'].append(dict(user=position, normalized=actual.tolist(), source_q=q.tolist(),
                    source_q_mapping_error=mapping_error, max_control_error=error))
                for point_size in (12, 16, 24, 48):
                    for engine in engines:
                        engine.ptem = point_size
                    size_row = row['by_point_size'].setdefault(str(point_size), dict(max_advance_error=0.,
                        max_source_layout_increment=0., max_target_layout_increment=0.))
                    for text in strings:
                        for direction in ('ltr', 'ttb'):
                            observations = [shape(f, text, direction, 'zh-cn' if label.startswith('SC') else 'zh-tw') for f in engines]
                            a, b = observations
                            row['layout_observations'] += 1
                            row['glyph_cluster_mismatches'] += a[0] != b[0]
                            row['missing_glyphs'] += sum(gid == 0 for gid, cluster in b[0])
                            if a[0] == b[0]:
                                delta = np.abs(a[1]-b[1])
                                error = float(delta[:, :2].max(initial=0))
                                row['max_advance_error'] = max(row['max_advance_error'], error)
                                row['max_offset_error'] = max(row['max_offset_error'], float(delta[:, 2:].max(initial=0)))
                                size_row['max_advance_error'] = max(size_row['max_advance_error'], error)
                                component = 0 if direction == 'ltr' else 1
                                advances = []
                                for engine, observed, which in zip(engines, observations, ('source', 'target')):
                                    getter = engine.get_glyph_h_advance if component == 0 else engine.get_glyph_v_advance
                                    raw = np.asarray([getter(gid)/64 for gid, cluster in observed[0]])
                                    advances.append(raw)
                                    key = 'max_'+which+'_layout_increment'
                                    size_row[key] = max(size_row[key], float(np.abs(observed[1][:, component]-raw).max(initial=0)))
                                row['max_native_metric_advance_error'] = max(row['max_native_metric_advance_error'],
                                    float(np.abs(advances[0]-advances[1]).max(initial=0)))
            row['geometric_bound_in_pixels'] = {str(px): row['max_control_error']*px/upem for px in (12, 16, 24, 48, 96)}
            report['faces'].append(row)
            print(json.dumps({k: v for k, v in row.items() if k != 'positions'}), flush=True)
    report['status'] = 'FAIL_LAYOUT' if any(r['glyph_cluster_mismatches'] or r['missing_glyphs'] for r in report['faces']) else 'PASS_SAMPLED_GLYPH_MAPPING_WITH_REPORTED_POSITION_AND_GEOMETRY_DIFFERENCES'
    args.output.write_text(json.dumps(report, indent=2))
    return report['status'] != 'FAIL_LAYOUT'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    raise SystemExit(0 if verify(p.parse_args()) else 1)
