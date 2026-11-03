#!/usr/bin/env python3
"""Reproducible private fitting and encoding for joint projection research.

All source-derived samples, coefficients and fonts must remain outside the
repository. Fitting and native acceptance are separate commands. A successful
build is not font acceptance; use platform/probe_projection_candidate.py next.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from fontTools.ttLib import TTCollection

from cff2_geometry import LIMIT, require
from hvf import HVGL
from projection_factorization import ProjectionSource
import adaptive_projection_atlas as atlas_module
import sparse_projection
from localized_projection_font import build


def source_identity(path, digest, face, gid):
    require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'source_hash_mismatch')
    return dict(source_sha256=digest, face_index=face, glyph_id=gid)


def fresh_private(path):
    path = Path(path).resolve()
    require(not path.exists() and not path.is_relative_to(Path(__file__).resolve().parents[3]),
            'fresh_external_private_directory_required')
    path.mkdir(parents=True, mode=0o700)
    return path


def progress(row):
    print(json.dumps(row), flush=True)


def run(args):
    identity = source_identity(args.source, args.source_sha256, args.face, args.gid)
    output = fresh_private(args.private_output)
    start = time.monotonic()
    with TTCollection(args.source, lazy=True) as collection:
        require(0 <= args.face < len(collection.fonts), 'invalid_source_face')
        source = collection.fonts[args.face]
        table = HVGL(source.reader['hvgl'], source.reader['hvpm'] if 'hvpm' in source else None)
        provider = ProjectionSource(table, args.gid)
        provider(np.zeros((1, 3)))
        report = dict(identity=identity, command=args.command, production_accepted=False)
        stages=dict(source_initialize_seconds=time.monotonic()-start)
        sampled_before=provider.count; evaluation_before=provider.evaluation_seconds
        stage_start=time.monotonic()
        if args.command == 'fit-fields':
            initial=(atlas_module.ProjectionAtlas.load(args.resume_atlas,identity)
                     if getattr(args,'resume_atlas',None) else None)
            atlas = atlas_module.fit(provider, max_boxes=args.max_boxes,
                source_aligned_cuts=not args.midpoint_cuts, progress=progress,initial_atlas=initial)
            stages['field_fit_seconds']=time.monotonic()-stage_start;stage_start=time.monotonic()
            held = np.random.default_rng(args.seed).uniform(-1, 1, (args.holdouts, 3))
            proof = atlas_module.validate(atlas, provider, held)
            atlas.evidence['component_holdout'] = proof
            stages['field_holdout_seconds']=time.monotonic()-stage_start;stage_start=time.monotonic()
            atlas.save(output/'atlas.npz', identity)
            stages['archive_write_seconds']=time.monotonic()-stage_start
            report.update(atlas.evidence, seed=args.seed)
            passed = proof['max_envelope_error'] <= LIMIT and atlas.evidence['max_refinement_error'] <= LIMIT
        elif args.command == 'fit-parameters':
            model = (sparse_projection.fit(provider.parameter_values, args.level,
                max_nodes=args.max_nodes, progress=progress) if provider.factors else
                sparse_projection.SparseParameters(np.zeros((1,3,3)),np.zeros((1,0)),1))
            stages['parameter_fit_seconds']=time.monotonic()-stage_start;stage_start=time.monotonic()
            encoded = sparse_projection.encode_clamp_ramps(model, args.ramps)
            held = np.random.default_rng(args.seed).uniform(-1, 1, (args.holdouts, 3))
            fitted = atlas_module.fingerprints(model.supports[:, :, 1])
            require(not np.intersect1d(fitted, atlas_module.fingerprints(held)).size,
                    'parameter_holdouts_overlap_training')
            errors=[]
            for offset in range(0,len(held),64):
                p=held[offset:offset+64];fields,parameters=provider.components(p)
                delta=encoded.evaluate_clamped(p)-np.clip(parameters,0,1)
                error=np.einsum('nf,nfp->np',delta,fields[:,1:])
                errors.append(np.linalg.norm(np.cumsum(error.reshape(len(p),-1,2),axis=1),axis=2).max(axis=1))
            error=np.concatenate(errors)
            stages['parameter_holdout_seconds']=time.monotonic()-stage_start;stage_start=time.monotonic()
            proof = dict(holdouts_disjoint=True, holdout_count=len(held), seed=args.seed,
                         max_parameter_induced_error=float(error.max()),
                         failures=int((error > LIMIT/2).sum()), budget=LIMIT/2,
                         native_verification='NOT_RUN')
            np.savez_compressed(output/'parameters.npz', supports=model.supports,
                coefficients=model.coefficients, fitting_fingerprints=fitted,
                metadata=json.dumps(dict(identity=identity, level=args.level, ramps=args.ramps,
                                         training_nodes=model.training_nodes, proof=proof)))
            stages['archive_write_seconds']=time.monotonic()-stage_start
            report.update(proof, raw_regions=len(model.supports), encoded_regions=len(encoded.supports))
            passed = not proof['failures']
        else:
            atlas = atlas_module.ProjectionAtlas.load(args.atlas, identity)
            with np.load(args.parameters, allow_pickle=False) as data:
                metadata = json.loads(str(data['metadata']))
                require(metadata['identity'] == identity, 'parameter_source_identity_mismatch')
                require(metadata['proof']['holdouts_disjoint'] and metadata['proof']['failures'] == 0,
                        'unverified_projection_parameters')
                model = sparse_projection.SparseParameters(data['supports'], data['coefficients'],
                                                           metadata['training_nodes'])
            stages['archive_load_seconds']=time.monotonic()-stage_start;stage_start=time.monotonic()
            candidate = build(source, args.gid, atlas, model, ramps=metadata['ramps'],
                              eager_fields=getattr(args,'eager_fields',False))
            stages['font_encode_seconds']=time.monotonic()-stage_start;stage_start=time.monotonic()
            candidate.save(output/'candidate.otf')
            stages['font_save_seconds']=time.monotonic()-stage_start
            report.update(candidate._swirl_projection_receipt,
                          font_bytes=(output/'candidate.otf').stat().st_size)
            passed = True
    source_identity(args.source, args.source_sha256, args.face, args.gid)
    report.update(seconds=time.monotonic()-start, stage_passed=passed,stages=stages,
                  source_evaluation_seconds=provider.evaluation_seconds-evaluation_before,
                  source_positions_evaluated=provider.count-sampled_before)
    (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    progress(report)
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('fit-fields', 'fit-parameters', 'build'))
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--face', type=int, default=0)
    parser.add_argument('--gid', type=int, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--max-boxes', type=int, default=4096)
    parser.add_argument('--midpoint-cuts', action='store_true',
                        help='reproduce the retained midpoint-partition experiment; branch probes remain enabled')
    parser.add_argument('--eager-fields',action='store_true',help='Controlled memory baseline: materialize all output fields before encoding')
    parser.add_argument('--level', type=int, default=14)
    parser.add_argument('--max-nodes', type=int, default=1_000_000)
    parser.add_argument('--ramps', type=int, default=4)
    parser.add_argument('--holdouts', type=int, default=4096)
    parser.add_argument('--seed', type=int, default=2026110463)
    parser.add_argument('--atlas', type=Path)
    parser.add_argument('--resume-atlas',type=Path,help='Reassess/refine private cells, retaining all previous training receipts')
    parser.add_argument('--parameters', type=Path)
    args = parser.parse_args()
    require(args.holdouts > 0, 'positive_holdout_count_required')
    require(args.command != 'build' or (args.atlas is not None and args.parameters is not None),
            'build_requires_private_atlas_and_parameters')
    raise SystemExit(0 if run(args) else 1)


if __name__ == '__main__':
    main()
