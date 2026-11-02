#!/usr/bin/env python3
"""Private source / serialized CFF2 / native checks for declared local boxes.

The manifest contains source_sha256, face_index and cases with glyph_id, box
([low, high] per axis), knots (three counts), seed and holdouts. All coefficients,
outlines and research fonts stay outside the checkout. These three-glyph fonts
use an authored template, not the source cmap or source metrics, and are never
complete source-font candidates. A local-box pass cannot accept the full cube.
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
from hvf_cubic_batch import cubic_batch
from local_cff2_geometry import encode, validate_knots
from piecewise_geometry import point_errors
import cff2_geometry as geometry
from cff2_metrics import prepare_from_truetype
from rebuild import NativeOracle
from verified_axis_oracle import make_launcher
from test_coretext_extract import make_fixture
from probe_hvf_cff2_geometry import native_commands
from hvf_transcript import validate_transcript


def native_plan(box, profiles, seed):
    """Choose exact 1/16 user coordinates whose normalized values stay local.

    This is a separate, declared native plan, not rounded replacements for the
    mathematical holdouts. Include all eight representable corner positions.
    """
    bounds = []
    for (a,b),(lo,default,hi) in zip(box,profiles):
        user = [default+x*(default-lo if x<0 else hi-default) for x in (a,b)]
        bounds.append((int(np.ceil(user[0]*16)),int(np.floor(user[1]*16))))
    require(len(bounds)==3 and all(lo<=hi for lo,hi in bounds), 'no_representable_native_box')
    rng = np.random.default_rng(seed)
    random = np.array([rng.integers(lo,hi+1,64) for lo,hi in bounds]).T
    ticks = list(dict.fromkeys([*itertools.product(*bounds),*map(tuple,random)]))
    return [tuple(float(v)/16 for v in point) for point in ticks]


def run(source, manifest, output, *, native_binary=None, hvf_binary=None):
    source = Path(source).resolve(strict=True); output = Path(output).resolve()
    require(not output.exists() and not output.is_relative_to(Path(__file__).resolve().parents[3]),
            'new_private_basis_directory_required')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    spec = json.loads(Path(manifest).read_text())
    require(digest == spec['source_sha256'], 'source_hash_mismatch')
    require(bool(native_binary) == bool(hvf_binary), 'both_native_oracles_required')
    if native_binary:
        require(platform.system() == 'Darwin', 'native_Apple_platform_required')
        native_binary = Path(native_binary).resolve(strict=True)
        hvf_binary = Path(hvf_binary).resolve(strict=True)
    face = spec.get('face_index', 0)
    with TTCollection(source, lazy=True) as collection:
        require(type(face) is int and 0 <= face < len(collection.fonts), 'invalid_basis_face')
        font = collection.fonts[face]
        tags = tuple(a.axisTag for a in font['fvar'].axes)
        require(tags == ('WDTH','wght','HGHT'), 'source_axis_order_must_match_probe_template')
        upm = font['head'].unitsPerEm
        table = HVGL(font.reader['hvgl'], font.reader['hvpm'] if 'hvpm' in font else None)
    renderer = BatchGeometry(table, isolated_tangents=True)
    cases = spec['cases']
    require(type(cases) is list and 0 < len(cases) <= 32, 'invalid_basis_cases')
    output.mkdir(parents=True, mode=0o700)
    report = dict(source_sha256=digest, face_index=face, axis_order=tags,
        scope='declared_domains_only_authored_template_no_source_metrics_or_cmap',
        source_font_acceptance=False, cases=[], os=platform.platform(),
        manifest_sha256=hashlib.sha256(Path(manifest).read_bytes()).hexdigest())
    launcher = output/'verified-axis-oracle'
    if native_binary:
        make_launcher(launcher, native_binary)
        report['native_binary_sha256'] = hashlib.sha256(native_binary.read_bytes()).hexdigest()
        report['hvf_binary_sha256'] = hashlib.sha256(hvf_binary.read_bytes()).hexdigest()
    for case_index, case in enumerate(cases):
        gid = case['glyph_id']; box = np.asarray(case['box'], dtype=float)
        counts = case['knots']; held_count = case.get('holdouts',128); seed = case['seed']
        require(type(gid) is int and 0 <= gid < table.glyph_count and box.shape == (3,2)
                and np.isfinite(box).all(), 'invalid_source_box')
        require(type(counts) is list and len(counts) == 3 and all(type(n) is int and 2 <= n <= 65 for n in counts)
                and np.prod(counts) <= 40000, 'invalid_basis_node_budget')
        require(type(held_count) is int and 1 <= held_count <= 4096 and type(seed) is int,
                'invalid_independent_basis_plan')
        knots = validate_knots([np.round(np.linspace(*b,n)*16384)/16384 for b,n in zip(box,counts)])
        require(np.array_equal(np.array([[k[0],k[-1]] for k in knots]),box), 'box_boundaries_not_F2DOT14')
        nodes = np.asarray(list(itertools.product(*knots)))
        held = np.random.default_rng(seed).uniform(box[:,0],box[:,1],(held_count,3))
        require(all(not all(p[a] in knots[a] for a in range(3)) for p in held), 'basis_holdout_overlaps_nodes')
        root_axes = table.part(gid).axis_count
        def sample(points):
            operators, rows = None, []
            for first in range(0,len(points),512):
                ops, relative, _ = cubic_batch(renderer.render(gid,points[first:first+512,:root_axes]))
                require(operators is None or ops == operators, 'source_basis_topology_changed')
                operators = ops; rows.append(relative)
            return operators, np.concatenate(rows)
        ops, values = sample(nodes)
        model = encode(knots,values.reshape(*counts,-1),ops,tags,basis='ramp')
        _, exact = sample(held)
        predicted = np.asarray([model.evaluate(dict(zip(tags,p))) for p in held])
        expected = np.cumsum(exact.reshape(len(held),-1,2),axis=1)
        errors = np.linalg.norm(predicted-expected,axis=2).max(axis=1,initial=0)
        row = dict(glyph_id=gid, box=box.tolist(), knots=counts, training_count=len(nodes),
            holdout_count=len(held), full_cube=bool(np.array_equal(box,np.tile([-1.,1.],(3,1)))),
            max_holdout_error=float(errors.max()), holdout_failures=int((errors>geometry.LIMIT).sum()),
            regions=len(model.supports)-1, serialized='NOT_RUN', native='NOT_RUN', passed=False)
        report['cases'].append(row)
        prefix = f'case-{case_index}-gid-{gid}'
        np.savez_compressed(output/f'{prefix}-model.npz',deltas=model.deltas,holdouts=held)
        (output/f'{prefix}-model.json').write_text(json.dumps(dict(axis_tags=tags,operators=ops,
            supports=model.supports,evidence=model.evidence),indent=2))
        try:
            model.charstring(0).compile(isCFF2=True); row['flat_encodable'] = True
        except ValueError as error:
            row['flat_encodable'] = False; row['encoding_error'] = str(error)
        if not row['holdout_failures'] and row['flat_encodable']:
            model.evidence.update(sampled_geometry_passed=True, failures=[],
                scope='private_declared_box_research_only',max_holdout_error=row['max_holdout_error'])
            template = output/f'{prefix}-template.ttc'; make_fixture(template)
            with TTCollection(template) as collection:
                original = collection.fonts[0]; original['head'].unitsPerEm = upm
                font = geometry.install(prepare_from_truetype(original),
                    dict.fromkeys(original.getGlyphOrder(),model),experimental_local=True)
                candidate = TTCollection(); candidate.fonts = [font]
                path = output/f'{prefix}-research.ttc'; candidate.save(path)
            row['font_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            row['font_bytes'] = path.stat().st_size
            row['serialized'] = dict(observations=0,failures=0,max_error=0.)
            with TTCollection(path) as reopened:
                saved = reopened.fonts[0]
                for p, actual in zip(held,exact):
                    out_ops, out = geometry.operands(geometry.source_commands(saved.getGlyphSet(
                        location=dict(zip(tags,map(float,p))),normalized=True)[saved.getGlyphOrder()[2]]))
                    require(out_ops == ops, 'saved_basis_topology_changed')
                    error = float(point_errors(out[None],actual[None])[0])
                    row['serialized']['observations'] += 1
                    row['serialized']['failures'] += error > geometry.LIMIT
                    row['serialized']['max_error'] = max(row['serialized']['max_error'],error)
                profiles = [(a.minValue,a.defaultValue,a.maxValue) for a in saved['fvar'].axes]
            if native_binary:
                native = NativeOracle(launcher,path,output/f'{prefix}-coretext-stderr.log')
                counts_native = dict(observations=0,failures=0,topology_failures=0,
                    max_cff2_libhvf_error=0.,max_portable_libhvf_error=0.)
                row['native'] = counts_native
                try:
                    with (output/f'{prefix}-coretext.jsonl').open('x') as transcript:
                        for i,user in enumerate(native_plan(box,profiles,seed+1)):
                            normalized = np.asarray([(v-d)/(d-l if v<d else h-d)
                                                     for v,(l,d,h) in zip(user,profiles)])
                            require(((normalized>=box[:,0])&(normalized<=box[:,1])).all(),
                                    'native_roundtrip_left_declared_box')
                            record = native.samples(0,[2],dict(zip(tags,user)))[2]
                            transcript.write(json.dumps(record)+'\n')
                            raw_path = output/f'{prefix}-hvf-{i}.jsonl'
                            process = subprocess.run([str(hvf_binary),str(source),str(face),
                                ','.join(format(float(x),'.17g') for x in normalized),str(gid),'1'],
                                capture_output=True,text=True,timeout=30)
                            raw_path.write_text(process.stdout)
                            (output/f'{prefix}-hvf-{i}.stderr.log').write_text(process.stderr)
                            proof = validate_transcript(raw_path,face=face,coords=normalized.tolist(),
                                start=gid,count=1,parts=False,input_bytes=source.stat().st_size)
                            require(process.returncode==0 and not proof['counts']['failed_outlines'],
                                    'native_source_basis_extraction_failed')
                            raw = next(r for r in map(json.loads,process.stdout.splitlines()) if r.get('record')=='outline')
                            source_ops, wanted = geometry.operands(native_commands(raw))
                            out_ops, actual = geometry.operands(record['commands'])
                            portable_ops, portable = sample(normalized[None])
                            require(source_ops==portable_ops, 'portable_native_basis_topology_changed')
                            portable_error = float(point_errors(portable,wanted[None])[0])
                            counts_native['max_portable_libhvf_error'] = max(counts_native['max_portable_libhvf_error'],portable_error)
                            counts_native['observations'] += 1
                            if out_ops != source_ops:
                                counts_native['topology_failures'] += 1; counts_native['failures'] += 1
                            else:
                                error = float(point_errors(actual[None],wanted[None])[0])
                                counts_native['max_cff2_libhvf_error'] = max(counts_native['max_cff2_libhvf_error'],error)
                                counts_native['failures'] += error > geometry.LIMIT or portable_error > geometry.LIMIT
                    counts_native['receipt'] = native.finish()
                except (ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    counts_native['failures'] += 1
                    counts_native['execution_error'] = str(error)
                finally:
                    native.close()
            row['passed'] = not row['serialized']['failures'] and (
                not native_binary or not row['native']['failures'])
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(row),flush=True)
    require(hashlib.sha256(source.read_bytes()).hexdigest()==digest, 'basis_source_changed')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--private-output',required=True,type=Path)
    parser.add_argument('--coretext-binary',type=Path)
    parser.add_argument('--hvf-binary',type=Path)
    args = parser.parse_args()
    report = run(args.source,args.manifest,args.private_output,
        native_binary=args.coretext_binary,hvf_binary=args.hvf_binary)
    sys.exit(0 if all(c['passed'] for c in report['cases']) else 1)
