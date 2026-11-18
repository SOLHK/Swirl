#!/usr/bin/env python3
"""Reuse q-space models only across byte-identical source geometry tables.

Faces retain their own fvar/avar, metrics and native acceptance. This avoids
refitting identical HVF functions; it does not assert user-coordinate parity.
Every reuse gets new independent component/parameter holdouts and receipts.
"""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTCollection
from hvf import HVGL
from cff2_geometry import LIMIT,require
from projection_research import fresh_private,source_identity
from projection_factorization import ProjectionSource
from adaptive_projection_atlas import ProjectionAtlas,validate,fingerprints
from sparse_projection import SparseParameters,encode_clamp_ramps


def equal_geometry_tables(a,b):
    require([x.axisTag for x in a['fvar'].axes]==[x.axisTag for x in b['fvar'].axes]
            ==['WDTH','wght','HGHT'],'reused_geometry_axis_order_mismatch')
    hashes={}
    for tag in ('hvgl','hvpm'):
        require((tag in a)==(tag in b),'reused_geometry_table_presence_mismatch')
        if tag not in a:
            require(tag!='hvgl','reused_geometry_missing_hvgl');continue
        left,right=a.reader[tag],b.reader[tag]
        require(left==right,'reused_geometry_table_bytes_mismatch')
        hashes[tag]=hashlib.sha256(left).hexdigest()
    return hashes


def run(args):
    start=time.perf_counter();identity=source_identity(args.source,args.source_sha256,args.face,args.gid)
    out=fresh_private(args.private_output)
    with np.load(args.atlas,allow_pickle=False) as data:
        previous=json.loads(str(data['metadata']))['identity']
    require(previous['source_sha256']==identity['source_sha256'] and previous['glyph_id']==args.gid,
            'reused_atlas_source_mismatch')
    with TTCollection(args.source,lazy=True) as collection:
        require(0<=args.face<len(collection.fonts) and 0<=previous['face_index']<len(collection.fonts),
                'invalid_reuse_face')
        source=collection.fonts[args.face]
        hashes=equal_geometry_tables(collection.fonts[previous['face_index']],source)
        atlas=ProjectionAtlas.load(args.atlas,previous)
        with np.load(args.parameters,allow_pickle=False) as data:
            metadata=json.loads(str(data['metadata']))
            require(metadata['identity']==previous and metadata['proof']['holdouts_disjoint']
                    and metadata['proof']['failures']==0,'unverified_reused_parameters')
            supports,coefficients,trained=(data[k].copy() for k in ('supports','coefficients','fitting_fingerprints'))
        provider=ProjectionSource(HVGL(source.reader['hvgl'],source.reader['hvpm'] if 'hvpm' in source else None),args.gid)
        provider(np.zeros((1,3)))
        model=SparseParameters(supports,coefficients,metadata['training_nodes'])
        encoded=encode_clamp_ramps(model,metadata['ramps'])
        held=np.random.default_rng(args.seed).uniform(-1,1,(args.holdouts,3))
        require(not np.intersect1d(fingerprints(held),trained).size,'reuse_parameter_holdout_overlap')
        component=validate(atlas,provider,held)
        maximum=0.;failures=0
        for offset in range(0,len(held),64):
            p=held[offset:offset+64];fields,parameters=provider.components(p)
            error=np.einsum('nf,nfp->np',encoded.evaluate_clamped(p)-np.clip(parameters,0,1),fields[:,1:])
            values=np.linalg.norm(np.cumsum(error.reshape(len(p),-1,2),axis=1),axis=2).max(axis=1)
            maximum=max(maximum,float(values.max()));failures+=int((values>LIMIT/2).sum())
        proof=dict(holdouts_disjoint=True,holdout_count=len(held),seed=args.seed,
            max_parameter_induced_error=maximum,failures=failures,budget=LIMIT/2,native_verification='NOT_RUN')
        atlas.evidence['component_holdout']=component
        atlas.evidence['reused_geometry_identity']=previous
        atlas.evidence['reused_geometry_table_hashes']=hashes
        atlas.save(out/'atlas.npz',identity)
        metadata.update(identity=identity,proof=proof,reused_geometry_identity=previous,reused_geometry_table_hashes=hashes)
        np.savez_compressed(out/'parameters.npz',supports=supports,coefficients=coefficients,
            fitting_fingerprints=trained,metadata=json.dumps(metadata))
        passed=component['max_envelope_error']<=LIMIT and atlas.evidence['max_refinement_error']<=LIMIT and failures==0
    source_identity(args.source,args.source_sha256,args.face,args.gid)
    report=dict(identity=identity,reused_from=previous,geometry_table_hashes=hashes,boxes=len(atlas.boxes),
        component_holdout=component,parameter_holdout=proof,stage_passed=passed,seconds=time.perf_counter()-start,
        seed=args.seed,refit_samples=0,native_verification='NOT_RUN',production_accepted=False,
        user_axis_equivalence_established=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    return passed


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','atlas','parameters','private-output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source-sha256',required=True);p.add_argument('--gid',type=int,required=True)
    p.add_argument('--face',type=int,required=True);p.add_argument('--holdouts',type=int,default=4096)
    p.add_argument('--seed',type=int,default=2026110801)
    a=p.parse_args();require(a.holdouts>0,'positive_holdout_count_required')
    raise SystemExit(0 if run(a) else 1)
