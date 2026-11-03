#!/usr/bin/env python3
"""Independent serialized joint-font acceptance against Apple HVF.

This tool fits nothing. Plans, source outlines, failed observations and fonts
stay in a fresh private directory. It tests standard native shaping (including
FeatureVariations), not a Python-only selector. Geometry uses the unquantized
source design coordinates corresponding to the declared physical user input.
HarfBuzz advances are compared both to original HarfBuzz and to source tables:
the latter exposes the engine's integer-HVAR rounding, rather than attributing
that existing engine behavior to a reconstructed glyph.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTCollection, TTFont
from fontTools.varLib.models import normalizeValue, piecewiseLinearMap

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import cff2_geometry as geometry
from hvf import HVGL
from source_metrics import SourceMetrics
from verified_axis_oracle import declare_readback
from hvf_transcript import validate_transcript
from probe_joint_boundaries import independent_plan
from probe_joint_representations import compare, implicit_closures
from probe_hvf_cff2_geometry import native_commands
from p7_validate_candidate import commands as hb_commands

TAGS = ('WDTH', 'wght', 'HGHT')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def winding(commands):
    """Exact polynomial signed-area integration, retaining contour order."""
    areas, area, current, start = [], 0., None, None
    for command in commands:
        op = command[0]
        p = np.asarray(command[1:], dtype=float).reshape(-1, 2)
        if op == 'moveTo':
            geometry.require(current is None, 'open_contour_before_move')
            current = start = p[0]; area = 0.
            continue
        geometry.require(current is not None, 'contour_command_without_move')
        if op == 'closePath':
            area += (current[0]*start[1]-current[1]*start[0])/2
            areas.append(area); current = start = None
            continue
        if op == 'lineTo':
            power = np.asarray([current, p[0]-current])
        elif op == 'qCurveTo':
            power = np.asarray([current, 2*(p[0]-current), current-2*p[0]+p[1]])
        elif op == 'curveTo':
            power = np.asarray([current, 3*(p[0]-current),
                                3*(current-2*p[0]+p[1]), -current+3*p[0]-3*p[1]+p[2]])
        else:
            raise ValueError('unsupported_contour_command')
        dx = np.polynomial.polynomial.polyder(power[:, 0])
        dy = np.polynomial.polynomial.polyder(power[:, 1])
        cross = np.polynomial.polynomial.polysub(
            np.polynomial.polynomial.polymul(power[:, 0], dy),
            np.polynomial.polynomial.polymul(power[:, 1], dx))
        area += float(np.sum(cross/np.arange(1, len(cross)+1)))/2
        current = p[-1]
    geometry.require(current is None, 'unclosed_contour')
    return np.sign(areas).astype(int).tolist()


def requested_location(source, point):
    """Generate a fine fractional input before native execution; never retry it.

    Select the nearest stable member of a fixed three-point decimal stencil.
    This is a sampling-domain definition, not correction of a native response.
    No observed outline, error, model or native readback enters this selection.
    The observer still requires exact equality to the predeclared input. These
    samples cannot certify all arbitrary binary64 user-coordinate transports.
    """
    location = {}
    for axis, q in zip(source['fvar'].axes, point):
        mapping = source['avar'].segments[axis.axisTag]
        pairs = sorted(mapping.items())
        geometry.require(all(b[1] >= a[1] for a, b in zip(pairs, pairs[1:])),
                         'nonmonotone_source_axis_map')
        target = float(np.clip(q, pairs[0][1], pairs[-1][1]))
        # A plateau is valid avar data. Choose a preimage before native input;
        # the original forward mapping remains the reference for geometry.
        if target == 0 and mapping.get(0) == 0:
            x = 0.
        else:
            x = pairs[-1][0]
            for (a, left), (b, right) in zip(pairs, pairs[1:]):
                if left <= target <= right:
                    x = a if left == right else a+(b-a)*(target-left)/(right-left)
                    break
        value = axis.defaultValue+x*(axis.defaultValue-axis.minValue if x < 0
                                    else axis.maxValue-axis.defaultValue)
        tick = round(value*10000)
        candidates = [(tick+offset)/10000 for offset in (0, -1, 1)]
        candidates = [v for v in candidates if axis.minValue <= v <= axis.maxValue
                      and declare_readback({axis.axisTag: v})[axis.axisTag]['canonical'] == v]
        geometry.require(bool(candidates), 'predeclared_user_coordinate_not_stable')
        location[axis.axisTag] = min(candidates, key=lambda v: (abs(v-value), v))
    return location


def source_location(source, user):
    return [piecewiseLinearMap(normalizeValue(user[a.axisTag],
             (a.minValue, a.defaultValue, a.maxValue)), source['avar'].segments[a.axisTag])
            for a in source['fvar'].axes]


def sample_plan(table, gid, bounds, seed, random_count):
    rng = np.random.default_rng(seed)
    result = [('boundary', np.asarray(p)) for p in itertools.product((-1., -.5, 0., .5, 1.), repeat=3)]
    for axis in range(3):
        for value in rng.uniform(-1, 1, 64):
            point = np.zeros(3); point[axis] = value
            result.append(('single', point))
    for fixed in range(3):
        for point in rng.uniform(-1, 1, (64, 3)):
            point[fixed] = 0.; result.append(('dual', point))
    result.extend(('triple', p) for p in rng.uniform(-1, 1, (random_count, 3)))
    branches, _ = independent_plan(table, gid, seed=seed+1)
    result.extend((row['kind'], np.asarray(row['point'])) for row in branches
                  if row['kind'].startswith('branch'))
    # Replay the entire old dense-model holdout set, including its maxima.
    result.extend(('previous_dense_holdout', p) for p in
                  np.random.default_rng(2026110307).uniform(-1, 1, (128, 3)))
    geometry.require(bounds.ndim == 3 and bounds.shape[1:] == (3, 2)
                     and len(bounds) > 0 and np.isfinite(bounds).all(), 'invalid_region_bounds')
    for index in rng.choice(len(bounds), min(128, len(bounds)), replace=False):
        cell = bounds[index]
        point = rng.uniform(cell[:, 0], cell[:, 1])
        axis = int(rng.integers(0, 3))
        point[axis] = cell[axis, int(rng.integers(0, 2))]
        for shift in (-1/16384, 0., 1/16384):
            other = point.copy(); other[axis] = np.clip(other[axis]+shift, -1, 1)
            result.append(('region_seam', other))
    return result


def run(args):
    source_path = args.source.resolve(strict=True)
    candidate_path = args.candidate.resolve(strict=True)
    output = args.private_output.resolve()
    repository = Path(__file__).resolve().parents[3]
    geometry.require(platform.system() == 'Darwin', 'Apple_HVF_and_CoreText_required')
    geometry.require(not output.exists() and not output.is_relative_to(repository),
                     'fresh_private_output_outside_repository_required')
    geometry.require(digest(source_path) == args.source_sha256, 'source_hash_mismatch')
    output.mkdir(parents=True, mode=0o700)
    binary = output/'coretext_joint_layout'
    build = subprocess.run(['swiftc', '-O', str(Path(__file__).with_name('coretext_joint_layout.swift')),
                            '-o', str(binary)], capture_output=True, text=True, timeout=120)
    (output/'compile.log').write_text(build.stdout+build.stderr); build.check_returncode()
    with TTCollection(source_path, lazy=True) as collection, TTFont(candidate_path) as font:
        source = collection.fonts[args.face]
        geometry.require(tuple(a.axisTag for a in source['fvar'].axes) == TAGS
                         and tuple(a.axisTag for a in font['fvar'].axes[:3]) == TAGS,
                         'three_physical_axes_must_be_preserved')
        for left, right in zip(source['fvar'].axes, font['fvar'].axes):
            geometry.require((left.minValue, left.defaultValue, left.maxValue) ==
                             (right.minValue, right.defaultValue, right.maxValue), 'physical_axis_range_changed')
        geometry.require(font['head'].unitsPerEm == source['head'].unitsPerEm,
                         'source_unit_scale_required')
        table = HVGL(source.reader['hvgl'], source.reader['hvpm'] if 'hvpm' in source else None)
        with np.load(args.regions, allow_pickle=False) as archive:
            bounds = archive['bounds']
        points = sample_plan(table, args.gid, bounds, args.seed, args.random_count)
        hidden = {a.axisTag: a.defaultValue for a in font['fvar'].axes[3:]}
        requests, locations, categories = [], [], []
        for i, (kind, point) in enumerate(points):
            physical = requested_location(source, point)
            q = source_location(source, physical)
            requests.append(dict(id=str(i), text=args.text, coordinates={**physical, **hidden}))
            locations.append(q); categories.append(kind)
        manifest = dict(font_path=str(candidate_path), font_sha256=digest(candidate_path),
            axis_defaults={a.axisTag: a.defaultValue for a in font['fvar'].axes},
            table_hashes={tag: hashlib.sha256(font.reader[tag]).hexdigest()
                          for tag in ('CFF2', 'fvar', 'avar', 'GSUB', 'cmap', 'HVAR')}, requests=requests)
        (output/'manifest.json').write_text(json.dumps(manifest, allow_nan=False))
        (output/'source-plan.json').write_text(json.dumps(dict(categories=categories, coordinates=locations)))
        print(json.dumps(dict(stage='CoreText', observations=len(requests))), flush=True)
        with (output/'coretext.jsonl').open('x') as stdout, (output/'coretext-stderr.log').open('x') as stderr:
            native = subprocess.run([str(binary), str(output/'manifest.json')], stdout=stdout, stderr=stderr,
                                    timeout=args.timeout)
        native.check_returncode()
        observed = [json.loads(line) for line in (output/'coretext.jsonl').read_text().splitlines()]
        geometry.require(len(observed) == len(requests)+1 and
                         observed[-1].get('request_count') == len(requests), 'incomplete_CoreText_transcript')
        original = hb.Font(hb.Face(source_path.read_bytes(), args.face))
        target = hb.Font(hb.Face(candidate_path.read_bytes()))
        upm = font['head'].unitsPerEm
        for engine in (original, target):
            hb.ot_font_set_funcs(engine); engine.scale = (upm*64, upm*64)
        metrics = SourceMetrics(source)
        report = dict(gid=args.gid, source_sha256=args.source_sha256,
            candidate_sha256=manifest['font_sha256'], face=args.face, seed=args.seed,
            limit=geometry.LIMIT, scope='selected_source_glyph_native_shaping',
            training_samples_consumed=0, continuous_space_proof=False,
            engines={}, failures=[], observations=len(requests), categories={},
            input_sampling='nearest stable decimal4 from fixed three-point stencil, before native execution',
            arbitrary_binary64_transport_certified=False,
            harfbuzz_version=hb.version_string(), native_summary=observed[-1])
        # fontTools spans every category, selected independently of errors.
        ft_indices = set(range(0, len(requests), max(1, len(requests)//256)))
        ft_indices.update(next(i for i, k in enumerate(categories) if k == kind) for kind in set(categories))
        with (output/'hvf.jsonl').open('x') as transcript:
            for i, (request, row, q, kind) in enumerate(zip(requests, observed, locations, categories)):
                geometry.require(row.get('id') == request['id'] and len(row.get('glyphs', [])) == 1,
                                 'native_layout_request_or_glyph_count_mismatch')
                native = subprocess.run([str(args.hvf_binary), str(source_path), str(args.face),
                    ','.join(format(v, '.17g') for v in q), str(args.gid), '1'],
                    capture_output=True, text=True, timeout=30)
                transcript.write(native.stdout)
                current = output/'current-hvf.jsonl'; current.write_text(native.stdout)
                proof = validate_transcript(current, face=args.face, coords=q, start=args.gid, count=1,
                                            parts=False, input_bytes=source_path.stat().st_size)
                geometry.require(native.returncode == 0 and not proof['counts']['failed_outlines'],
                                 'Apple_HVF_extraction_failed')
                commands = native_commands(next(r for r in map(json.loads, native.stdout.splitlines())
                                                if r.get('record') == 'outline'))
                expected = geometry.operands(implicit_closures(commands)); directions = winding(commands)
                user = request['coordinates']; target.set_variations(user)
                original.set_variations({tag: user[tag] for tag in TAGS})
                buffer = hb.Buffer(); buffer.add_str(args.text); buffer.guess_segment_properties(); hb.shape(target, buffer)
                geometry.require(len(buffer.glyph_infos) == 1, 'HarfBuzz_glyph_count_mismatch')
                selected = buffer.glyph_infos[0].codepoint
                width = metrics.at(args.gid, dict(zip(TAGS, q)))['advance_width']
                original_width = original.get_glyph_h_advance(args.gid)/64
                ct = row['glyphs'][0]
                actual = {'CoreText': (ct['commands'], ct['advance_width'], width),
                          'HarfBuzz': (hb_commands(target, selected), buffer.glyph_positions[0].x_advance/64,
                                       original_width)}
                if i in ft_indices:
                    glyph = font.getGlyphSet(location=user)[font.getGlyphOrder()[selected]]
                    actual['fontTools'] = (geometry.source_commands(glyph), glyph.width, width)
                report['categories'][kind] = report['categories'].get(kind, 0)+1
                for name, (outline, advance, reference_width) in actual.items():
                    verdict = compare(expected, outline)
                    direction_ok = winding(outline) == directions
                    stats = report['engines'].setdefault(name, dict(observations=0, max_error=0.,
                        failures=0, topology_failures=0, direction_failures=0, advance_failures=0,
                        max_advance_error=0., max_advance_vs_unrounded_tables=0.))
                    stats['observations'] += 1
                    stats['max_error'] = max(stats['max_error'], verdict['error'] or 0.)
                    stats['topology_failures'] += verdict['error'] is None
                    stats['direction_failures'] += not direction_ok
                    ae = abs(advance-reference_width)
                    stats['advance_failures'] += ae > geometry.LIMIT
                    stats['max_advance_error'] = max(stats['max_advance_error'], ae)
                    stats['max_advance_vs_unrounded_tables'] = max(stats['max_advance_vs_unrounded_tables'], abs(advance-width))
                    passed = verdict['passed'] and direction_ok and ae <= geometry.LIMIT
                    stats['failures'] += not passed
                    if not passed:
                        report['failures'].append(dict(index=i, category=kind, engine=name,
                            outline=verdict, direction_ok=direction_ok, advance_error=ae))
                if i % 128 == 0:
                    print(json.dumps(dict(stage='compare', index=i, engines=report['engines'])), flush=True)
        report['passed'] = not report['failures']
        report['source_unchanged'] = digest(source_path) == args.source_sha256
        report['candidate_unchanged'] = digest(candidate_path) == manifest['font_sha256']
        geometry.require(report['source_unchanged'] and report['candidate_unchanged'], 'font_changed_during_validation')
        report['artifacts_sha256'] = {name: digest(output/name) for name in
            ('manifest.json', 'source-plan.json', 'coretext.jsonl', 'hvf.jsonl', 'coretext_joint_layout')}
        (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
        print(json.dumps({k: v for k, v in report.items() if k != 'failures'}), flush=True)
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'candidate', 'regions', 'hvf-binary', 'private-output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--gid', type=int, required=True)
    parser.add_argument('--face', type=int, default=0)
    parser.add_argument('--text', default='A')
    parser.add_argument('--seed', type=int, default=2026110411)
    parser.add_argument('--random-count', type=int, default=2048)
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    sys.exit(0 if run(args)['passed'] else 1)
