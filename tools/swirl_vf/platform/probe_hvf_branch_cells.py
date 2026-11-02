#!/usr/bin/env python3
"""Private analytic branch-surface / portable / Apple libhvf comparison.

The manifest supplies source_sha256 and cases[{glyph_id, anchor}]. Anchors
are post-avar design coordinates, not user axis values. Actual source outlines
and analytic coefficients are written only to a new private directory outside
the checkout. This probe does not fit or accept a CFF2 model.
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
from fontTools.ttLib import TTCollection
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from hvf import HVGL, require
from batch_geometry import BatchGeometry
from hvf_branch_cells import branch_cell
from hvf_cubic_batch import cubic_batch
from cff2_geometry import operands, control_points, LIMIT
from hvf_transcript import validate_transcript
from probe_hvf_cff2_geometry import native_commands


def boundary_positions(cell, maximum=8):
    """Intersect each analytic surface along its anchor gradient.

    Both quadratic roots are retained as candidates. Each actual native input
    is recorded separately; the existence of an algebraic contact is not a
    claim that every other ancestor condition holds along the entire line.
    """
    require(type(maximum) is int and 1 <= maximum <= 64, 'invalid_boundary_pair_limit')
    anchor = cell.anchor
    h = np.r_[1., anchor]
    candidates = []
    for surface in cell.surfaces:
        q = surface.coefficients
        gradient = 2*(q @ h)[1:]
        length = np.linalg.norm(gradient)
        if not length:
            continue
        direction = gradient/length
        d = np.r_[0., direction]
        polynomial = [h @ q @ h, 2*d @ q @ h, d @ q @ d]
        for root in np.polynomial.polynomial.polyroots(polynomial):
            if not np.isreal(root):
                continue
            distance = float(np.real(root))
            contact = anchor+distance*direction
            if (np.abs(contact) > 1).any():
                continue
            pair = [contact-sign*direction/16384 for sign in (1,-1)]
            if any((np.abs(p) > 1).any() for p in pair):
                continue
            candidates.append((abs(distance), surface.identity, pair))
    selected, seen = [], set()
    for distance, identity, pair in sorted(candidates, key=lambda v: (v[0], str(v[1]))):
        key = tuple(float(v) for point in pair for v in point)
        if key in seen:
            continue
        seen.add(key)
        selected.append(dict(identity=identity, distance=distance,
                             positions=[p.tolist() for p in pair]))
        if len(selected) == maximum:
            break
    return selected


def run(source, manifest, binary, output):
    source = Path(source).resolve(strict=True); binary = Path(binary).resolve(strict=True)
    output = Path(output).resolve(); repo = Path(__file__).resolve().parents[3]
    require(platform.system() == 'Darwin', 'actual_Apple_libhvf_required')
    require(not output.exists() and not output.is_relative_to(repo), 'new_private_directory_required')
    spec = json.loads(Path(manifest).read_text())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    require(digest == spec['source_sha256'], 'source_hash_mismatch')
    face = spec.get('face_index', 0)
    with TTCollection(source, lazy=True) as collection:
        require(type(face) is int and 0 <= face < len(collection.fonts), 'invalid_source_face')
        font = collection.fonts[face]
        tags = tuple(a.axisTag for a in font['fvar'].axes)
        require(len(tags) == 3, 'three_source_axes_required')
        table = HVGL(font.reader['hvgl'], font.reader['hvpm'] if 'hvpm' in font else None)
    renderer = BatchGeometry(table, isolated_tangents=True)
    output.mkdir(parents=True, mode=0o700)
    report = dict(scope='analytic_source_branch_geometry_only', source_sha256=digest,
        binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), axis_order=tags,
        platform=platform.platform(), face_index=face, cases=[], CFF2_acceptance=False)
    cases = spec['cases']
    require(type(cases) is list and cases and len(cases) <= 256, 'invalid_branch_cases')
    gids = [case['glyph_id'] for case in cases]
    require(all(type(gid) is int and 0 <= gid < table.glyph_count for gid in gids)
            and len(set(gids)) == len(gids), 'invalid_or_duplicate_branch_glyphs')
    for case in cases:
        gid = case['glyph_id']; anchor = np.asarray(case['anchor'], dtype=float)
        require(anchor.shape == (3,) and np.isfinite(anchor).all()
                and (np.abs(anchor) <= 1).all(), 'invalid_font_branch_anchor')
        axes = table.part(gid).axis_count
        cell = branch_cell(table, gid, anchor[:axes])
        boundaries = boundary_positions(cell)
        for boundary in boundaries:
            boundary['positions'] = [list(p)+anchor[axes:].tolist() for p in boundary['positions']]
        points = list(itertools.product((-1.,0.,1.),repeat=3))+[tuple(anchor)]
        points += [tuple(p) for b in boundaries for p in b['positions']]
        points = np.asarray(list(dict.fromkeys(points)))
        batch = renderer.render(gid, points[:, :axes])
        expected_ops, _, expected = cubic_batch(batch)
        row = dict(glyph_id=gid, anchor=case['anchor'], boundary_pairs=boundaries,
                   observations=0, failures=[], max_control_error=0.)
        for i, point in enumerate(points):
            path = output/f'gid-{gid}-position-{i}.jsonl'
            command = [str(binary),str(source),str(face),
                ','.join(format(float(x),'.17g') for x in point),str(gid),'1']
            result = subprocess.run(command,capture_output=True,text=True,timeout=30)
            path.write_text(result.stdout)
            (output/f'gid-{gid}-position-{i}.stderr.log').write_text(result.stderr)
            proof = validate_transcript(path,face=face,coords=point.tolist(),start=gid,
                count=1,parts=False,input_bytes=source.stat().st_size)
            require(result.returncode == 0 and not proof['counts']['failed_outlines'], 'native_branch_extraction_failed')
            outline = next(row for row in map(json.loads, result.stdout.splitlines())
                           if row.get('record') == 'outline')
            ops, values = operands(native_commands(outline))
            row['observations'] += 1
            if ops != expected_ops:
                row['failures'].append(dict(position=point.tolist(),reason='topology_mismatch'))
                continue
            error = float(np.linalg.norm(control_points(ops,values)-expected[i],axis=1).max(initial=0))
            row['max_control_error'] = max(row['max_control_error'], error)
            if error > LIMIT:
                row['failures'].append(dict(position=point.tolist(),error=error))
        row['contours'] = len(batch.paths)
        row['cubic_controls'] = expected.shape[1]
        report['cases'].append(row)
        (output/f'cell-{gid}.json').write_text(json.dumps(dict(anchor=cell.anchor.tolist(),
            surfaces=[dict(identity=s.identity,coefficients=s.coefficients.tolist(),state=s.state)
                      for s in cell.surfaces]),indent=2))
        require(hashlib.sha256(source.read_bytes()).hexdigest() == digest, 'source_changed')
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:row[k] for k in ('glyph_id','observations','failures','max_control_error','contours','cubic_controls')}),flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source,args.manifest,args.binary,args.private_output)
    raise SystemExit(1 if any(c['failures'] for c in report['cases']) else 0)
