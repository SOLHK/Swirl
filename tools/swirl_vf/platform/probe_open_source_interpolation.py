#!/usr/bin/env python3
"""Measure locally rebuilt HOI-test and how2avar2 fonts in native engines.

Upstream files are inputs only and stay outside the repository. The HOI
reference is the Bernstein polynomial of four actual corner outlines; the
avar2 reference is the unmapped font with both auxiliary axes set explicitly.
This tests upstream interpolation semantics, not acceptance of an HVF glyph.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTFont
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import cff2_geometry as g
from probe_joint_representations import compare, implicit_closures
from p7_validate_candidate import commands


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def outline(font, glyph, location):
    return g.operands(implicit_closures(g.source_commands(font.getGlyphSet(location=location)[glyph])))


def run_case(path, text, requests, expected, output, binary, quantized_reference=None):
    output.mkdir()
    with TTFont(path) as font:
        blob = path.read_bytes()
        manifest = dict(font_path=str(path), font_sha256=digest(path),
            axis_defaults={a.axisTag: a.defaultValue for a in font['fvar'].axes},
            table_hashes={tag: hashlib.sha256(font.reader[tag]).hexdigest()
                          for tag in ('glyf', 'gvar', 'fvar', 'cmap', 'avar') if tag in font},
            requests=[dict(id=str(i), text=text, coordinates=location) for i, location in enumerate(requests)])
        (output/'manifest.json').write_text(json.dumps(manifest))
        native = subprocess.run([str(binary), str(output/'manifest.json')], capture_output=True, text=True)
        (output/'native.jsonl').write_text(native.stdout); (output/'stderr.log').write_text(native.stderr)
        native.check_returncode()
        observed = [json.loads(line) for line in native.stdout.splitlines()]
        g.require(observed[-1].get('request_count') == len(requests), 'upstream_native_batch_incomplete')
        target = hb.Font(hb.Face(blob)); hb.ot_font_set_funcs(target)
        target.scale = (font['head'].unitsPerEm*64,)*2
        stats = {engine: dict(observations=0, max_error=0., failures=0) for engine in ('CoreText', 'HarfBuzz', 'fontTools')}
        for index, (row, location, reference) in enumerate(zip(observed, requests, expected)):
            target.set_variations(location)
            buffer = hb.Buffer(); buffer.add_str(text); buffer.guess_segment_properties(); hb.shape(target, buffer)
            gid = buffer.glyph_infos[0].codepoint
            actual = dict(CoreText=row['glyphs'][0]['commands'], HarfBuzz=commands(target, gid),
                fontTools=g.source_commands(font.getGlyphSet(location=location)[font.getGlyphOrder()[gid]]))
            for engine, value in actual.items():
                verdict = compare(reference, value); item = stats[engine]
                item['observations'] += 1; item['failures'] += not verdict['passed']
                item['max_error'] = max(item['max_error'], verdict['error'] or 0.)
                if quantized_reference is not None:
                    diagnostic = compare(quantized_reference[index], value)
                    item['max_error_vs_quantized_reference'] = max(
                        item.get('max_error_vs_quantized_reference', 0.), diagnostic['error'] or 0.)
                    item['failures_vs_quantized_reference'] = item.get('failures_vs_quantized_reference', 0)+int(not diagnostic['passed'])
        return dict(font_sha256=digest(path), bytes=len(blob), engines=stats, native_summary=observed[-1])


def run(args):
    output = args.private_output.resolve()
    g.require(not output.exists() and not output.is_relative_to(Path(__file__).resolve().parents[3]),
              'fresh_private_reference_output_required')
    output.mkdir(parents=True, mode=0o700)
    binary = output/'observer'
    subprocess.run(['swiftc', '-O', str(Path(__file__).with_name('coretext_joint_layout.swift')),
                    '-o', str(binary)], check=True)
    t = np.arange(65)/64
    with TTFont(args.hoi_font) as font:
        axes = [a.axisTag for a in font['fvar'].axes]
        g.require(axes == ['XXXX', 'YYYY', 'ZZZZ'], 'unexpected_HOI_cubic_axes')
        corners = [outline(font, 'B', dict(zip(axes, p))) for p in ((0, 0, 0), (100, 0, 0),
                   (100, 100, 0), (100, 100, 100))]
        g.require(all(c[0] == corners[0][0] for c in corners), 'upstream_corner_topology_changed')
        weights = np.array([(1-t)**3, 3*t*(1-t)**2, 3*t*t*(1-t), t**3]).T
        expected = [(corners[0][0], values) for values in weights @ np.array([c[1] for c in corners])]
        requests = [dict.fromkeys(axes, float(100*u)) for u in t]
        # This is a distinct control: a single changing axis does not implement
        # the one-parameter cubic. Record its residual rather than hiding it.
        uncoupled = [outline(font, 'B', dict(zip(axes, (100*u, 0, 0)))) for u in t]
        difference = max(float(np.linalg.norm(g.control_points(a[0], a[1])-
                          g.control_points(b[0], b[1]), axis=1).max()) for a, b in zip(uncoupled, expected))
    report = dict(scope='upstream_controls_only', limit=g.LIMIT,
        HOI_test=run_case(args.hoi_font, 'B', requests, expected, output/'hoi', binary))
    report['HOI_test']['uncoupled_axis_max_residual'] = difference
    with TTFont(args.how2_original) as source, TTFont(args.how2_mapped) as target:
        axes = [a.axisTag for a in target['fvar'].axes]
        # Integer degrees have exact native user-coordinate transport. Keep
        # any F2DOT14 interpolation error visible in the resulting measurements.
        degrees = np.arange(91, dtype=float)
        requests = [{tag: float(u) if tag == 'ZROT' else 0. for tag in axes} for u in degrees]
        expected = [outline(source, 'H', {tag: float(u) for tag in axes}) for u in degrees]
        quantized = [g.operands(implicit_closures(g.source_commands(source.getGlyphSet(
                     location={tag: float(np.floor(u/90*16384+.5)/16384) for tag in axes}, normalized=True)['H'])))
                     for u in degrees]
    report['how2avar2'] = run_case(args.how2_mapped, 'H', requests, expected, output/'avar2', binary, quantized)
    report['passed'] = all(not s['failures'] for case in ('HOI_test', 'how2avar2')
                           for s in report[case]['engines'].values())
    (output/'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report)); return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('hoi-font', 'how2-original', 'how2-mapped', 'private-output'):
        parser.add_argument('--'+arg, type=Path, required=True)
    sys.exit(0 if run(parser.parse_args())['passed'] else 1)
