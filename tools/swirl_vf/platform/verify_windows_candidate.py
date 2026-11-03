#!/usr/bin/env python3
"""Private saved-font verification: actual HarfBuzz + Apple HVF observations.

All source point data stays in memory or in the explicitly private directory.
DirectWrite remains a separately required Windows run, never inferred here.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTCollection
from fontTools.pens.recordingPen import RecordingPointPen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from windows_font_builder import SOURCE_SHA, source_locations, source_vectors, FACE_PLAN
from windows_font_inventory import sha256
from hvf import HVGL
from batch_geometry import BatchGeometry
from source_metrics import SourceMetrics
from probe_axis_thresholds import hvf_events
from calibrate_hvf_geometry import discrepancy, portable_paths, native_paths
from p7_validate_candidate import commands
from diagnose_path_types import raw_coretext_paths, raw_native_paths, raw_portable_paths, compare_preserved_quadratics


def verify(args):
    folder = args.candidate.resolve().parent
    build = json.loads((folder/'report.json').read_text())
    if sha256(args.source) != SOURCE_SHA or sha256(args.candidate) != build['sha256']:
        raise ValueError('source_or_candidate_hash_mismatch')
    blob = args.candidate.read_bytes()
    report = dict(candidate_sha256=build['sha256'], source_sha256=SOURCE_SHA, faces=[],
                  DirectWrite='NOT_RUN', Windows_installation='NOT_RUN', production_accepted=False)
    samples = np.r_[np.zeros((1, 3)), np.asarray(list(__import__('itertools').product((-1., 0., 1.), repeat=3))),
                    np.floor(np.random.default_rng(2026110329).uniform(-1, 1, (args.samples, 3))*16384+.5)/16384]
    with TTCollection(args.source, lazy=True) as sc, TTCollection(args.candidate, lazy=True) as tc:
        table = HVGL(sc.fonts[0].reader['hvgl'])
        renderer = BatchGeometry(table, isolated_tangents=True)
        for index, (source_index, label) in enumerate(FACE_PLAN):
            source, target = sc.fonts[source_index], tc.fonts[index]
            metrics = SourceMetrics(source)
            engine = hb.Font(hb.Face(blob, index)); hb.ot_font_set_funcs(engine)
            source_upem, target_upem = source['head'].unitsPerEm, target['head'].unitsPerEm
            engine.scale = (source_upem*64, source_upem*64)
            selected = build['source_gids'] if not args.subset else [g for g in (0, 12, 1166, 19177) if g in build['source_gids']]
            if args.random_glyphs:
                random = np.random.default_rng(2026110307).choice(build['source_gids'], min(args.random_glyphs, len(build['source_gids'])), replace=False)
                selected = sorted(set(map(int, random)) | {0, 1166, 19177})
            positions = {g: build['source_gids'].index(g) for g in selected}
            stats = dict(face=label, glyphs=len(selected), observations=0, empty_mismatches=0,
                         max_source_control_error=0., max_HB_control_error=0.,
                         max_HB_advance_width_error=0., max_HB_advance_height_error=0.,
                         HB_topology_failures=0, HB_numeric_failures=0, native_source_observations=0,
                         max_native_source_error=0., native_source_failures=0, legacy_source_type_failures=0,
                         native_source_cases=[], axes_changed={}, quality=Counter())
            q = source_locations(source, samples)
            for gid in selected:
                values, flags, ends = source_vectors(renderer, metrics, gid, q, 1)
                target_gid = positions[gid]
                name = target.getGlyphOrder()[target_gid]
                saved_vectors = []
                for n, p in enumerate(samples):
                    location = dict(zip(('wdth', 'wght', 'HGHT'), map(float, p)))
                    pen = RecordingPointPen()
                    target.getGlyphSet(location=location, normalized=True)[name].drawPoints(pen)
                    points = np.asarray([v[1][0] for v in pen.value if v[0] == 'addPoint']).reshape(-1, 2)*source_upem/target_upem
                    if len(points) != len(flags):
                        raise ValueError('saved_point_topology_changed')
                    err = float(np.linalg.norm(points-values[n, :-4], axis=-1).max(initial=0))
                    stats['max_source_control_error'] = max(stats['max_source_control_error'], err)
                    saved_vectors.append(points)
                    engine.set_var_coords_normalized(list(map(float, p)))
                    expected_width = values[n, -3, 0]-values[n, -4, 0]
                    expected_height = values[n, -2, 1]-values[n, -1, 1]
                    stats['max_HB_advance_width_error'] = max(stats['max_HB_advance_width_error'], abs(engine.get_glyph_h_advance(target_gid)/64-expected_width))
                    stats['max_HB_advance_height_error'] = max(stats['max_HB_advance_height_error'], abs(-engine.get_glyph_v_advance(target_gid)/64-expected_height))
                    observed = commands(engine, target_gid)
                    if bool(observed) != bool(flags):
                        stats['empty_mismatches'] += 1
                    if flags:
                        # Independent native source is deliberately bounded and
                        # uses fresh processes, never the fitted training arrays.
                        if args.oracle and (args.oracle_all or gid in (0, 1166, 19177)) and n in (0, len(samples)-1):
                            events = hvf_events(args.oracle, args.source, source_index, gid,
                                                dict(zip(('WDTH', 'wght', 'HGHT'), map(float, q[n]))))
                            paths = renderer.render(gid, q[n:n+1, :table.part(gid).axis_count]).paths
                            try:
                                native_error = discrepancy(portable_paths([p_[0] for p_ in paths]), native_paths(events))[0]
                            except ValueError as error:
                                native_error = None
                                stats['legacy_source_type_failures'] += 1
                            raw_check = compare_preserved_quadratics(raw_portable_paths([p_[0] for p_ in paths]), raw_native_paths(events))
                            native_error = raw_check['maximum_point_error']
                            stats['native_source_cases'].append(dict(gid=gid, sample=n,
                                status=raw_check['status'], error=native_error))
                            stats['native_source_observations'] += 1
                            stats['native_source_failures'] += native_error is None or native_error > 1/32
                            stats['max_native_source_error'] = max(stats['max_native_source_error'], native_error or 0.)
                            comparison = compare_preserved_quadratics(raw_native_paths(events), raw_coretext_paths(observed))
                            e = comparison['maximum_point_error']
                            stats['HB_topology_failures'] += e is None
                            stats['HB_numeric_failures'] += e is not None and e > 1/32
                            stats['max_HB_control_error'] = max(stats['max_HB_control_error'], e or 0.)
                    stats['observations'] += 1
                maximum = max((float(np.linalg.norm(p-v[:-4], axis=-1).max(initial=0)) for p, v in zip(saved_vectors, values)), default=0)
                stats['quality']['sampled_high_precision' if maximum <= 1/32 else 'basic_geometry_samples' if maximum <= 2 else 'geometry_difference'] += 1
            # Native draw signatures at default and each positive axis extreme.
            for axis in range(3):
                digests = []
                for amount in (0., 1.):
                    loc = [0.]*3; loc[axis] = amount
                    engine.set_var_coords_normalized(loc)
                    payload = [commands(engine, positions[g]) for g in selected]
                    digests.append(__import__('hashlib').sha256(json.dumps(payload).encode()).hexdigest())
                stats['axes_changed'][('wdth', 'wght', 'HGHT')[axis]] = digests[0] != digests[1]
            report['faces'].append(stats)
    report['status'] = 'FAIL' if any(f['empty_mismatches'] or f['native_source_failures'] or f['HB_topology_failures'] or not all(f['axes_changed'].values()) for f in report['faces']) else 'PASS_STRUCTURAL_NATIVE_SAMPLES_WITH_REPORTED_GEOMETRY_DIFFERENCES'
    args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    return report['status'] != 'FAIL'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--candidate', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--oracle', type=Path)
    p.add_argument('--samples', type=int, default=16)
    p.add_argument('--subset', action='store_true')
    p.add_argument('--random-glyphs', type=int, default=0)
    p.add_argument('--oracle-all', action='store_true')
    raise SystemExit(0 if verify(p.parse_args()) else 1)
