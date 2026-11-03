#!/usr/bin/env python3
"""Compare both adjacent CFF2 patches at one exact normalized interface.

This supplements physical-coordinate shaping acceptance. It deliberately draws
each local glyph directly with a common post-avar2 coordinate vector, using
HarfBuzz and fontTools, to measure the jump that first-match GSUB selection
would otherwise conceal. It does not replace original-source acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTFont
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import cff2_geometry as g
from joint_polynomial import TAGS
from joint_hoi import GROUPS
from verify_joint_candidate import requested_location
from probe_joint_representations import implicit_closures
from p7_validate_candidate import commands


def run(args):
    output = args.private_output.resolve()
    g.require(type(args.count) is int and 1 <= args.count <= 65536, 'invalid_seam_sample_count')
    g.require(not output.exists() and not output.is_relative_to(Path(__file__).resolve().parents[3]),
              'fresh_private_seam_output_required')
    output.mkdir(parents=True, mode=0o700)
    with np.load(args.regions, allow_pickle=False) as archive:
        bounds = archive['bounds']
    g.require(bounds.ndim == 3 and bounds.shape[1:] == (3, 2) and len(bounds) > 1
              and np.isfinite(bounds).all() and np.all(bounds[:, :, 0] < bounds[:, :, 1])
              and np.all(np.abs(bounds) <= 1) and np.all(bounds*16384 == np.round(bounds*16384)),
              'invalid_seam_partition')
    rng = np.random.default_rng(args.seed); pairs = []
    for i in rng.permutation(len(bounds)):
        cell = bounds[i]
        for axis in rng.permutation(3):
            for side in (0, 1):
                p = np.floor(rng.uniform(cell[:, 0], cell[:, 1])*16384+.5)/16384
                p[axis] = cell[axis, side]
                neighbours = np.flatnonzero(np.all((p >= bounds[:, :, 0]) & (p <= bounds[:, :, 1]), axis=1))
                others = neighbours[neighbours != i]
                if len(others):
                    pairs.append((int(i), int(others[0]), p))
                    break
            if len(pairs) >= args.count:
                break
        if len(pairs) >= args.count:
            break
    g.require(len(pairs) == args.count, 'insufficient_shared_interfaces')
    blob = args.candidate.read_bytes()
    report = dict(scope='native_shared_normalized_coordinate_patch_continuity', limit=g.LIMIT,
                  seed=args.seed, pairs=len(pairs), candidate_sha256=hashlib.sha256(blob).hexdigest(), engines={})
    records = []
    with TTFont(args.candidate) as font:
        tags = [a.axisTag for a in font['fvar'].axes]
        g.require(tuple(tags[:3]) == TAGS and 'CFF2' in font, 'joint_CFF2_axes_required')
        engine = hb.Font(hb.Face(blob)); hb.ot_font_set_funcs(engine)
        engine.scale = (font['head'].unitsPerEm*64,)*2
        for index, (left, right, p) in enumerate(pairs):
            user = {a.axisTag: a.defaultValue for a in font['fvar'].axes}
            user.update(requested_location(font, p))
            normalized = font.normalizeLocation(user)
            # These two patches must see exactly the same face coordinate.
            # Keep computed projection ramps from the nearby physical request;
            # identity copies follow the exact chosen physical interface.
            for group, value in zip(GROUPS, p):
                normalized.update({tag: float(value) for tag in group if tag in tags})
            vector = [normalized.get(tag, 0.) for tag in tags]
            engine.set_var_coords_normalized(vector)
            g.require(engine.get_var_coords_normalized() == vector, 'seam_normalized_readback_mismatch')
            glyphs = font.getGlyphSet(location=normalized, normalized=True)
            gids = [font.getGlyphID(f'joint{i}') for i in (left, right)]
            for name, outlines in (
                ('HarfBuzz', [commands(engine, gid) for gid in gids]),
                ('fontTools', [g.source_commands(glyphs[f'joint{i}']) for i in (left, right)])):
                a, b = [g.operands(implicit_closures(value)) for value in outlines]
                topology = a[0] == b[0]
                error = float(np.linalg.norm(g.control_points(*a)-g.control_points(*b), axis=1).max()) if topology else None
                stats = report['engines'].setdefault(name, dict(observations=0, failures=0, max_jump=0.))
                stats['observations'] += 1
                stats['failures'] += error is None or error > g.LIMIT
                stats['max_jump'] = max(stats['max_jump'], error or 0.)
                records.append(dict(index=index, left=left, right=right, coordinates=normalized,
                                    engine=name, error=error, topology=topology))
    report['passed'] = all(v['failures'] == 0 for v in report['engines'].values())
    (output/'observations.json').write_text(json.dumps(records))
    report['observations_sha256'] = hashlib.sha256((output/'observations.json').read_bytes()).hexdigest()
    (output/'report.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report)); return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'regions', 'private-output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--seed', type=int, default=2026110447)
    parser.add_argument('--count', type=int, default=256)
    sys.exit(0 if run(parser.parse_args())['passed'] else 1)
