#!/usr/bin/env python3
"""Independent serialized CFF2/avar2 observations against Apple's HVF oracle.

Source-derived coordinates, contours, failures and native transcripts stay in
a fresh external directory. No fitting occurs here. Repeated and training
positions remain tested, but are never counted as independent observations.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys
import numpy as np
from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib.models import normalizeValue, piecewiseLinearMap
import uharfbuzz as hb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import cff2_geometry as geometry
from joint_polynomial import TAGS
from projection_research import fresh_private, source_identity
from adaptive_projection_atlas import fingerprints
from hvf import HVGL
from source_metrics import SourceMetrics
from hvf_transcript import validate_transcript
from probe_joint_boundaries import independent_plan
from probe_hvf_cff2_geometry import native_commands
from probe_joint_representations import compare, implicit_closures
from p7_validate_candidate import commands as hb_commands
from verified_axis_oracle import declare_readback


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''): h.update(block)
    return h.hexdigest()


def contour_measure(commands):
    normalized = implicit_closures(commands)
    ops, values = geometry.operands(normalized)
    at, begin, areas, area, gap, offset = np.zeros(2), None, [], 0., 0., 0
    def cross(a, b): return a[0]*b[1]-a[1]*b[0]
    for operator, count in ops:
        points = [at.copy()]
        for j in range(0, count, 2):
            at = at+values[offset+j:offset+j+2]; points.append(at.copy())
        if operator == 'rmoveto':
            if begin is not None:
                areas.append(area+cross(points[0], begin)/2)
                gap = max(gap, float(np.linalg.norm(points[0]-begin)))
            begin, area = at.copy(), 0.
        elif operator == 'rlineto':
            area += cross(points[0], points[1])/2
        else:
            a, b, c, d = points
            coefficients = [a, 3*(b-a), 3*(a-2*b+c), d-a+3*(b-c)]
            area += sum(cross(coefficients[i], coefficients[j])*j/(i+j)/2
                        for i in range(4) for j in range(1, 4))
        offset += count
    if begin is not None:
        areas.append(area+cross(at, begin)/2)
        gap = max(gap, float(np.linalg.norm(at-begin)))
    closed = sum(c[0] == 'closePath' for c in normalized) == len(areas)
    return np.asarray(areas), gap, closed


def make_plan(table, gid, bounds, seed, random_count, seams):
    rng = np.random.default_rng(seed)
    result = [dict(kind='boundary_grid', point=list(p))
              for p in itertools.product((-1., -.5, 0., .5, 1.), repeat=3)]
    for axes in ((0,), (1,), (2,), (0, 1), (0, 2), (1, 2)):
        for _ in range(64):
            p = np.zeros(3); p[list(axes)] = rng.uniform(-1, 1, len(axes))
            result.append(dict(kind='single' if len(axes) == 1 else 'dual', point=p.tolist()))
    result.extend(dict(kind='triple_random', point=p.tolist())
                  for p in rng.uniform(-1, 1, (random_count, 3)))
    branch, partitions = independent_plan(table, gid, seed=seed+1)
    result.extend(row for row in branch if row['kind'].startswith('branch'))
    # A wider, still local pair survives documented decimal user-axis readback.
    for part in partitions:
        a, b = np.asarray(part['start_coordinates']), np.asarray(part['end_coordinates'])
        for event in part['events']:
            for shift in (-1e-5, 1e-5):
                t = float(np.clip(event['parameter']+shift, 0, 1))
                result.append(dict(kind='branch_wide_'+event['kind'], point=((1-t)*a+t*b).tolist()))
    for index in rng.choice(len(bounds), min(seams, len(bounds)), replace=False):
        box = bounds[index]
        p = rng.uniform(box[:, 0], box[:, 1])
        axis = int(rng.integers(0, 3)); p[axis] = box[axis, int(rng.integers(0, 2))]
        for shift in (-2/16384, -1e-7, 0., 1e-7, 2/16384):
            q = p.copy(); q[axis] = np.clip(q[axis]+shift, -1, 1)
            result.append(dict(kind='patch_seam', point=q.tolist()))
    return result


def requests_for_plan(source, candidate, plan):
    axes = {a.axisTag: a for a in source['fvar'].axes}
    maps = source['avar'].segments
    requests, roots = [], []
    for i, item in enumerate(plan):
        location = {}
        for tag, q in zip(TAGS, item['point']):
            mapping = maps[tag]
            inverse = {v: k for k, v in mapping.items()}; inverse[0.] = 0.
            x = piecewiseLinearMap(float(np.clip(q, min(mapping.values()), max(mapping.values()))), inverse)
            axis = axes[tag]
            value = axis.defaultValue+x*(axis.defaultValue-axis.minValue if x < 0 else axis.maxValue-axis.defaultValue)
            location[tag] = round(value*8192)/8192
        location = declared_user_location(location)
        root = [piecewiseLinearMap(normalizeValue(location[tag],
                (axes[tag].minValue, axes[tag].defaultValue, axes[tag].maxValue)), maps[tag]) for tag in TAGS]
        location.update({a.axisTag: a.defaultValue for a in candidate['fvar'].axes[3:]})
        requests.append(dict(id=str(i), text='A', coordinates=location)); roots.append(root)
    return requests, np.asarray(roots)


def declared_user_location(location):
    # Four predeclared decimal truncations, all before any native call.
    # The first creates a decimal-grid value. Exhaustive float64 analysis
    # of the 1..1000 user range found at most two further downward steps.
    # Keep the final exact-readback guard; never retry a native observation.
    for _ in range(2):
        location = {tag: row['canonical'] for tag, row in declare_readback(location).items()}
    geometry.require(all(row['canonical'] == location[tag] for tag, row in declare_readback(location).items()),
                     'axis_request_not_stable_before_native_observation')
    return location


def replay_requests(source, candidate, paths, offset):
    """Replay exact physical inputs, never previous outlines or verdicts."""
    requests, roots = [], []
    defaults = {a.axisTag: a.defaultValue for a in candidate['fvar'].axes[3:]}
    axes = {a.axisTag: a for a in source['fvar'].axes}
    for path in paths:
        for row in json.loads(path.read_text())['requests']:
            values = row['coordinates']
            geometry.require(set(TAGS) <= set(values) and row['text']=='A'
                and all(value == 0 for tag,value in values.items() if tag not in TAGS),
                'replay_requires_physical_inputs_and_default_computational_axes')
            physical = {tag: values[tag] for tag in TAGS}
            geometry.require(all(type(v) in (int,float) and np.isfinite(v)
                and axes[tag].minValue <= v <= axes[tag].maxValue for tag,v in physical.items()),
                'invalid_replay_physical_coordinate')
            roots.append([piecewiseLinearMap(normalizeValue(physical[tag],
                (axes[tag].minValue,axes[tag].defaultValue,axes[tag].maxValue)),source['avar'].segments[tag])
                for tag in TAGS])
            requests.append(dict(id=str(offset+len(requests)),text='A',coordinates={**physical,**defaults}))
    return requests,np.asarray(roots).reshape(-1,3)


def independence(points, atlas_path, parameter_path, *, legacy_grid=False):
    held = fingerprints(points)
    with np.load(atlas_path, allow_pickle=False) as atlas:
        recorded = 'fitting_fingerprints' in atlas
        fitted = atlas['fitting_fingerprints'] if recorded else np.empty(0, dtype='V16')
    with np.load(parameter_path, allow_pickle=False) as parameters:
        parameter_fit = (parameters['fitting_fingerprints'] if 'fitting_fingerprints' in parameters
                         else fingerprints(parameters['supports'][:, :, 1]))
    overlap = np.isin(held, np.r_[fitted, parameter_fit])
    # Always exclude the conservative dyadic-node superset, including tiny
    # forward/inverse-axis roundoff. Explicit fingerprints additionally cover
    # non-grid refinement and source-branch samples. Without those receipts,
    # the grid exclusion proves separation only for the legacy grid-only fit.
    overlap |= np.all(np.isclose(points*131072, np.rint(points*131072), rtol=0, atol=1e-7), axis=1)
    unique, first = np.unique(held, return_index=True)
    independent = np.zeros(len(points), dtype=bool)
    independent[first] = ~overlap[first]
    proven = recorded or legacy_grid
    return dict(proven=proven, observations=len(points), unique_positions=len(unique),
                overlapping_observations=int(overlap.sum()),
                unique_independent_positions=int(independent.sum()) if proven else None,
                duplicate_observations=len(points)-len(unique),
                conservative_F2_grid_exclusion=True,
                legacy_conservative_grid_exclusion=legacy_grid), independent if proven else np.zeros(len(points), dtype=bool)


def run(args):
    geometry.require(platform.system() == 'Darwin', 'CoreText_native_probe_requires_macOS')
    identity = source_identity(args.source, args.source_sha256, args.face, args.gid)
    out = fresh_private(args.private_output)
    with np.load(args.atlas, allow_pickle=False) as data:
        bounds = data['bounds']
        if not args.legacy_grid_atlas:
            geometry.require(json.loads(str(data['metadata']))['identity'] == identity,
                             'atlas_source_identity_mismatch')
    with np.load(args.parameters, allow_pickle=False) as data:
        geometry.require(json.loads(str(data['metadata']))['identity'] == identity,
                         'parameter_source_identity_mismatch')
    with TTCollection(args.source, lazy=True) as collection, TTFont(args.candidate) as font, ExitStack() as cleanup:
        source = collection.fonts[args.face]
        geometry.require(font['head'].unitsPerEm == source['head'].unitsPerEm,
                         'source_font_unit_scale_changed')
        geometry.require(tuple(a.axisTag for a in font['fvar'].axes[:3]) == TAGS, 'physical_axes_changed')
        for a, b in zip(source['fvar'].axes, font['fvar'].axes):
            geometry.require((a.minValue, a.defaultValue, a.maxValue, a.flags) ==
                             (b.minValue, b.defaultValue, b.maxValue, b.flags), 'source_axis_profile_changed')
            geometry.require(source['avar'].segments[a.axisTag] == font['avar'].segments[b.axisTag],
                             'source_axis_segment_map_changed')
        table = HVGL(source.reader['hvgl'], source.reader['hvpm'] if 'hvpm' in source else None)
        plan = make_plan(table, args.gid, bounds, args.seed, args.random, args.seams)
        if args.regression_plan:
            plan.extend(dict(row, kind='retained_failure_regression')
                        for row in json.loads(args.regression_plan.read_text()))
        requests, roots = requests_for_plan(source, font, plan)
        extra_requests,extra_roots = replay_requests(source,font,getattr(args,'replay_manifest',()),len(requests))
        if extra_requests:
            requests.extend(extra_requests);roots=np.r_[roots,extra_roots]
            plan.extend(dict(kind='exact_physical_regression',point=p.tolist()) for p in extra_roots)
        separation, independent = independence(roots, args.atlas, args.parameters, legacy_grid=args.legacy_grid_atlas)
        (out/'plan.json').write_text(json.dumps(dict(plan=plan, roots=roots.tolist(), separation=separation)))
        blob = args.candidate.read_bytes()
        manifest = dict(font_path=str(args.candidate.resolve()), font_sha256=hashlib.sha256(blob).hexdigest(),
            axis_defaults={a.axisTag: a.defaultValue for a in font['fvar'].axes},
            table_hashes={tag: hashlib.sha256(font.reader[tag]).hexdigest()
                          for tag in ('CFF2', 'fvar', 'avar', 'GSUB', 'cmap', 'HVAR') if tag in font}, requests=requests)
        (out/'manifest.json').write_text(json.dumps(manifest))
        binary = args.coretext_binary or out/'layout-oracle'
        if not args.coretext_binary:
            built = subprocess.run(['swiftc', '-O', str(Path(__file__).with_name('coretext_joint_layout.swift')),
                                    '-o', str(binary)], capture_output=True, text=True, timeout=120)
            (out/'compile.log').write_text(built.stdout+built.stderr); built.check_returncode()
        print(json.dumps(dict(stage='CoreText', observations=len(requests))), flush=True)
        raw = cleanup.enter_context((out/'native.jsonl').open('w'))
        stderr = cleanup.enter_context((out/'native-stderr.log').open('w'))
        native = cleanup.enter_context(subprocess.Popen([str(binary), str(out/'manifest.json')],
            stdout=subprocess.PIPE, stderr=stderr, text=True))
        cleanup.callback(lambda: native.terminate() if native.poll() is None else None)
        def stream_native():
            for line in native.stdout:
                raw.write(line); raw.flush()
                yield json.loads(line)
        native_rows = stream_native()
        target = hb.Font(hb.Face(blob)); original = hb.Font(hb.Face(args.source.read_bytes(), args.face))
        upm = source['head'].unitsPerEm
        for hfont in (target, original):
            hb.ot_font_set_funcs(hfont); hfont.scale = (upm*64, upm*64)
        metrics = SourceMetrics(source)
        ft_indices = set(np.linspace(0, len(requests)-1, min(args.fonttools, len(requests)), dtype=int))
        from audit_joint_axis_contract import compare_fonts
        report = dict(identity=identity, limit=geometry.LIMIT, independence=separation,
            acceptance_scope='joint_post_avar_q_geometry_and_reported_metrics',
            axis_mapping_contract=compare_fonts(source,font),
            observations=len(requests), categories=dict(Counter(p['kind'] for p in plan)),
            engines={}, source_HarfBuzz_advance_max_error=0., production_accepted=False,
            full_font_coverage=False, os=platform.platform(), harfbuzz=hb.version_string(),
            source_oracle_sha256=digest(args.hvf_oracle), candidate_sha256=digest(args.candidate),
            coretext_oracle_sha256=digest(binary), font_bytes=len(blob), seed=args.seed,
            atlas_sha256=digest(args.atlas), parameter_archive_sha256=digest(args.parameters),
            verifier_sha256=digest(__file__))
        failures = []
        with (out/'hvf-native.jsonl').open('w') as hvf_raw, (out/'observations.jsonl').open('w') as observations:
            for i, (request, q, item) in enumerate(zip(requests, roots, plan)):
                ct = next(native_rows)
                geometry.require(ct['type'] == 'sample' and ct['id'] == request['id'] and
                    ct['coordinates'] == request['coordinates'] and len(ct['glyphs']) == 1, 'native_request_mismatch')
                hvf = subprocess.run([str(args.hvf_oracle), str(args.source), str(args.face),
                    ','.join(format(x, '.17g') for x in q), str(args.gid), '1'], capture_output=True, text=True, timeout=30)
                hvf_raw.write(hvf.stdout)
                current = out/'current-hvf.jsonl'; current.write_text(hvf.stdout)
                proof = validate_transcript(current, face=args.face, coords=q, start=args.gid, count=1,
                                            parts=False, input_bytes=args.source.stat().st_size)
                geometry.require(hvf.returncode == 0 and not proof['counts']['failed_outlines'], 'native_HVF_source_failed')
                commands = native_commands(next(r for r in map(json.loads, hvf.stdout.splitlines()) if r.get('record') == 'outline'))
                expected = geometry.operands(commands); areas, _, _ = contour_measure(commands)
                loc = request['coordinates']; target.set_variations(loc)
                original.set_variations({tag: loc[tag] for tag in TAGS})
                buffer = hb.Buffer(); buffer.add_str('A'); buffer.guess_segment_properties(); hb.shape(target, buffer)
                geometry.require(len(buffer.glyph_infos) == 1, 'candidate_HarfBuzz_shaping_count')
                selected = buffer.glyph_infos[0].codepoint
                actuals = {'CoreText': (ct['glyphs'][0]['gid'], ct['glyphs'][0]['commands'], ct['glyphs'][0]['advance_width']),
                           'HarfBuzz': (selected, hb_commands(target, selected), buffer.glyph_positions[0].x_advance/64)}
                if i in ft_indices:
                    glyph = font.getGlyphSet(location=loc)[font.getGlyphOrder()[selected]]
                    actuals['fontTools'] = (selected, geometry.source_commands(glyph), glyph.width)
                exact_width = metrics.at(args.gid, dict(zip(TAGS, q)))['advance_width']
                same_engine_width = original.get_glyph_h_advance(args.gid)/64
                report['source_HarfBuzz_advance_max_error'] = max(report['source_HarfBuzz_advance_max_error'],
                    abs(actuals['HarfBuzz'][2]-same_engine_width))
                measured = dict(index=i, kind=item['kind'], independent=bool(independent[i]), engines={})
                for engine, (gid, cmds, advance) in actuals.items():
                    verdict = compare(expected, cmds); signs, gap, closed = contour_measure(cmds)
                    direction = len(signs) == len(areas) and np.array_equal(np.sign(signs), np.sign(areas))
                    width_error = abs(advance-(same_engine_width if engine == 'HarfBuzz' else exact_width))
                    stats = report['engines'].setdefault(engine, dict(observations=0, independent_observations=0,
                        max_error=0., independent_max_error=0., failures=0, topology_failures=0,
                        direction_failures=0, closure_failures=0, selection_failures=0,
                        max_explicit_closure_gap=0., max_advance_error=0., advance_failures=0))
                    stats['observations'] += 1; stats['independent_observations'] += bool(independent[i])
                    stats['max_error'] = max(stats['max_error'], verdict['error'] or 0.)
                    if independent[i]: stats['independent_max_error'] = max(stats['independent_max_error'], verdict['error'] or 0.)
                    stats['failures'] += not verdict['passed']; stats['topology_failures'] += verdict['error'] is None
                    stats['direction_failures'] += not direction; stats['closure_failures'] += not closed or gap > geometry.LIMIT
                    selected_valid = 3 <= gid < len(bounds)+3
                    stats['selection_failures'] += not selected_valid
                    stats['max_explicit_closure_gap'] = max(stats['max_explicit_closure_gap'], gap)
                    stats['max_advance_error'] = max(stats['max_advance_error'], width_error)
                    stats['advance_failures'] += width_error > geometry.LIMIT
                    measured['engines'][engine] = dict(**verdict, selected_gid=gid, direction=bool(direction),
                        selected_valid=bool(selected_valid), closed=bool(closed), closure_gap=gap,
                        advance_error=width_error)
                    if not verdict['passed'] or not direction or not closed or not selected_valid or gap > geometry.LIMIT or width_error > geometry.LIMIT:
                        failures.append(dict(index=i, kind=item['kind'], engine=engine, **measured['engines'][engine]))
                observations.write(json.dumps(measured)+'\n')
                if i % 256 == 0: print(json.dumps(dict(stage='compare', index=i, engines=report['engines'])), flush=True)
        summary = next(native_rows)
        geometry.require(summary['type'] == 'summary' and summary['request_count'] == len(requests)
            and summary['font_sha256'] == manifest['font_sha256'] and summary['exact_axis_readback']
            and summary['run_tables_verified'] and next(native_rows, None) is None, 'native_summary_mismatch')
        geometry.require(native.wait() == 0, 'native_CoreText_process_failed')
        report['sampled_geometry_passed'] = all(not any(stats[key] for key in
            ('failures', 'topology_failures', 'direction_failures', 'closure_failures', 'selection_failures', 'advance_failures'))
            for stats in report['engines'].values())
        report['strict_independent_native_passed'] = (report['sampled_geometry_passed']
            and separation['proven'] and all(stats['independent_observations'] > 0
                                            for stats in report['engines'].values()))
        report['artifact_hashes'] = {name: digest(out/name) for name in
            ('plan.json', 'manifest.json', 'native.jsonl', 'hvf-native.jsonl', 'observations.jsonl')}
        (out/'failures.json').write_text(json.dumps(failures, indent=2))
        (out/'report.json').write_text(json.dumps(report, indent=2))
        source_identity(args.source, args.source_sha256, args.face, args.gid)
        print(json.dumps(report), flush=True)
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'candidate', 'atlas', 'parameters', 'hvf-oracle', 'private-output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--gid', type=int, required=True)
    parser.add_argument('--face', type=int, default=0)
    parser.add_argument('--seed', type=int, default=2026110451)
    parser.add_argument('--random', type=int, default=4096)
    parser.add_argument('--seams', type=int, default=128)
    parser.add_argument('--fonttools', type=int, default=256)
    parser.add_argument('--coretext-binary', type=Path)
    parser.add_argument('--regression-plan', type=Path)
    parser.add_argument('--replay-manifest', type=Path, action='append', default=[],
                        help='Freshly execute exact physical inputs from a retained private manifest')
    parser.add_argument('--legacy-grid-atlas', action='store_true')
    args = parser.parse_args()
    geometry.require(args.random > 0 and args.seams > 0 and args.fonttools > 0, 'positive_validation_coverage_required')
    result = run(args)
    raise SystemExit(0 if result['strict_independent_native_passed'] else 1)
