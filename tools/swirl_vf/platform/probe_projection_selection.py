#!/usr/bin/env python3
"""Audit native patch selection, measuring CoreText's effective coordinates.

Physical user-coordinate readback does not expose an engine's normalized
coordinates. An authored linear outline with byte-identical fvar/avar tables
measures them without extracting any source outline or changing the request.
All requests and observations remain in a fresh private directory.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTCollection, TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import cff2_geometry as geometry
from projection_research import fresh_private
from probe_projection_candidate import digest
from test_coretext_extract import make_fixture


def coordinate_font(source, template):
    for tag in ('name', 'fvar', 'avar'):
        template[tag] = copy.deepcopy(source[tag])
    template['head'].unitsPerEm = source['head'].unitsPerEm
    for tag in ('trak', 'GSUB', 'GPOS'):
        if tag in template:
            del template[tag]
    tags = tuple(a.axisTag for a in template['fvar'].axes)
    supports = [{}]+[{tag: triple} for tag in tags[:3]
                    for triple in ((-1, -1, 0), (0, 1, 1))]
    values = np.zeros((7, 8)); values[0] = [0, 0, 1, 0, -1, 1, 0, -1]
    values[1, [0, 4, 6]] = [-10000, 10000, -10000]; values[2] = -values[1]
    values[3, 1] = -10000; values[4, 1] = 10000
    values[5, [4, 6]] = [-10000, 10000]; values[6] = -values[5]
    ops = (('rmoveto', 2), ('rlineto', 2), ('rlineto', 2), ('rlineto', 2))
    model = geometry.OutlineModel(tags, ops, supports, values, {'sampled_geometry_passed': True})
    empty = geometry.OutlineModel(tags, (), [{}], np.zeros((1, 0)), {'sampled_geometry_passed': True})
    return geometry.install(template, {'.notdef': empty, 'space': empty, 'probe': model})


def run(args):
    out = fresh_private(args.private_output)
    original = json.loads((args.acceptance/'manifest.json').read_text())
    plan = json.loads((args.acceptance/'plan.json').read_text())
    rows = [json.loads(s) for s in (args.acceptance/'observations.jsonl').read_text().splitlines()]
    candidate = Path(original['font_path'])
    geometry.require(digest(candidate) == original['font_sha256'], 'candidate_hash_changed')
    geometry.require(len(rows) == len(original['requests']), 'incomplete_selection_observations')
    with np.load(args.atlas, allow_pickle=False) as data:
        bounds = data['bounds']
    engine = hb.Font(hb.Face(candidate.read_bytes())); hb.ot_font_set_funcs(engine)
    report = dict(observations=len(rows), HarfBuzz_condition_mismatches=0,
        CoreText_selection_differs_from_HarfBuzz=0,
        CoreText_condition_mismatches_after_measuring_effective_coordinates=0,
        max_effective_physical_coordinate_change=0., production_accepted=False,
        candidate_sha256=original['font_sha256'])
    def first(q):
        eligible = np.flatnonzero(np.all((q >= bounds[:, :, 0]) & (q <= bounds[:, :, 1]), axis=1))
        return int(eligible[0])+3 if len(eligible) else -1
    indices = []
    for i, (request, row) in enumerate(zip(original['requests'], rows)):
        geometry.require(row['index'] == i, 'selection_observation_order_changed')
        engine.set_variations(request['coordinates'])
        actual = row['engines']['HarfBuzz']['selected_gid']
        report['HarfBuzz_condition_mismatches'] += actual != first(np.asarray(engine.get_var_coords_normalized()[:3]))
        if row['engines']['CoreText']['selected_gid'] != actual:
            indices.append(i)
    report['CoreText_selection_differs_from_HarfBuzz'] = len(indices)
    make_fixture(out/'template.ttc')
    with TTFont(candidate) as source, TTCollection(out/'template.ttc') as collection:
        font = coordinate_font(source, collection.fonts[0]); font.save(out/'coordinate.otf')
        with TTFont(out/'coordinate.otf') as saved:
            geometry.require(all(source.getTableData(t) == saved.getTableData(t) for t in ('fvar', 'avar')),
                             'coordinate_probe_axis_tables_changed')
            manifest = dict(font_path=str(out/'coordinate.otf'), font_sha256=digest(out/'coordinate.otf'),
                axis_defaults=original['axis_defaults'],
                table_hashes={t: digest_table(saved.reader[t]) for t in ('CFF2', 'fvar', 'avar', 'cmap')},
                requests=[original['requests'][i] for i in indices])
    (out/'manifest.json').write_text(json.dumps(manifest))
    native = subprocess.run([str(args.coretext_binary), str(out/'manifest.json')], capture_output=True, text=True)
    (out/'native.jsonl').write_text(native.stdout); (out/'stderr.log').write_text(native.stderr)
    native.check_returncode()
    observed = [json.loads(s) for s in native.stdout.splitlines()]
    geometry.require(len(observed) == len(indices)+1 and observed[-1]['type'] == 'summary'
        and observed[-1]['request_count'] == len(indices) and observed[-1]['run_tables_verified']
        and observed[-1]['font_sha256'] == manifest['font_sha256']
        and observed[-1]['exact_axis_readback'], 'coordinate_probe_transcript_incomplete')
    for i, row in zip(indices, observed):
        request = original['requests'][i]
        geometry.require(row['id'] == request['id'] and row['coordinates'] == request['coordinates']
                         and len(row['glyphs']) == 1, 'coordinate_probe_request_changed')
        commands = row['glyphs'][0]['commands']
        geometry.require(commands[0][0] == 'moveTo' and commands[2][0] == 'lineTo',
                         'coordinate_probe_topology_changed')
        q = np.asarray([commands[0][1], commands[0][2], commands[2][1]])/10000
        report['CoreText_condition_mismatches_after_measuring_effective_coordinates'] += (
            first(q) != rows[i]['engines']['CoreText']['selected_gid'])
        report['max_effective_physical_coordinate_change'] = max(
            report['max_effective_physical_coordinate_change'], float(abs(q-np.asarray(plan['roots'][i])).max()))
    report.update(fvar_and_avar_byte_identical=True, native_transcript_sha256=digest(out/'native.jsonl'))
    report['passed'] = (report['HarfBuzz_condition_mismatches'] == 0
        and report['CoreText_condition_mismatches_after_measuring_effective_coordinates'] == 0)
    (out/'report.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report)); return report


def digest_table(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('acceptance', 'atlas', 'private-output', 'coretext-binary'):
        parser.add_argument('--'+name, type=Path, required=True)
    raise SystemExit(0 if run(parser.parse_args())['passed'] else 1)
