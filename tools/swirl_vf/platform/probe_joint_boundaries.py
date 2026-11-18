#!/usr/bin/env python3
"""Independent joint-axis and analytic-boundary Apple HVF observations.

No observations from this plan fit a model. Native source transcripts stay in
the new private output directory. The optional retained dense models are only
diagnosed; failed models are never installed or admitted as font candidates.
All coordinates are post-avar in physical fvar order, including uppercase WDTH.
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

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from batch_geometry import BatchGeometry
from hvf import HVGL,require
from hvf_glyph_model import _commands
from hvf_piecewise_axes import segment_partition
from interpolation_witness import flat_cell_degree,polynomial_witness
import cff2_geometry as geometry
from hvf_transcript import validate_transcript
from probe_hvf_cff2_geometry import compare_commands,native_commands


def independent_plan(table,gid,seed=2026110307):
    rng=np.random.default_rng(seed)
    plan=[]
    def add(kind,p):plan.append(dict(kind=kind,point=list(map(float,p))))
    for axes in ((0,),(1,),(2,),(0,1),(0,2),(1,2),(0,1,2)):
        for _ in range(128 if len(axes)==3 else 32):
            p=np.zeros(3);p[list(axes)]=rng.uniform(-1,1,len(axes))
            add(('single','dual','triple')[len(axes)-1],p)
    for p in itertools.product((-1.,0.,1.),repeat=3):add('grid_boundary',p)
    events=[];partitions=[]
    for _ in range(8):
        a,b=rng.uniform(-1,1,(2,3))
        part=segment_partition(table,gid,a,b);partitions.append(part)
        knots=np.asarray(part['parameters'])
        for event in part['events']:
            t=event['parameter'];index=int(np.searchsorted(knots,t))
            radius=min(t-knots[index-1],knots[index+1]-t)/8
            if radius<=0:raise ValueError('noninterior_joint_partition_event')
            events.append((event['kind'],a,b,t,min(radius,1e-7)))
    # Stratify by source event kind. Selection uses no observed errors or fit.
    for kind in sorted({e[0] for e in events}):
        group=[e for e in events if e[0]==kind]
        for index in rng.choice(len(group),min(16,len(group)),replace=False):
            _,a,b,t,epsilon=group[index]
            for offset in (-epsilon,0.,epsilon):add('branch_'+kind,(1-t-offset)*a+(t+offset)*b)
    # Identical events at a shared component boundary need only one oracle call.
    unique={}
    for row in plan:unique.setdefault(tuple(row['point']),row)
    return list(unique.values()),partitions


def dense_witnesses(table,renderer,gid,tags,directory,seed=2026110307):
    meta=Path(directory)/f'dense-{gid}.json';data=Path(directory)/f'dense-{gid}.npz'
    spec=json.loads(meta.read_text())
    with np.load(data,allow_pickle=False) as archive:deltas=archive['deltas']
    model=geometry.OutlineModel(tags,tuple(map(tuple,spec['operators'])),spec['supports'],deltas,spec['evidence'])
    held=np.random.default_rng(seed).uniform(-1,1,(128,3))
    # The retained fitter's nodes are F2DOT14 and its refinement midpoints
    # are half-ticks. Reject even a coincidental overlap with that whole grid.
    require(np.any(held*32768!=np.rint(held*32768),axis=1).all(),
            'joint_holdout_overlaps_tensor_training_grid')
    batch=renderer.render(gid,held)
    actual=np.asarray([geometry.control_points(*geometry.operands(_commands(batch.paths,i,1)))
                       for i in range(len(held))])
    errors=np.asarray([np.linalg.norm(model.evaluate(dict(zip(tags,p)))-v,axis=1).max()
                       for p,v in zip(held,actual)])
    worst=held[int(errors.argmax())]
    knots=[np.asarray(sorted({-1.,0.,1.,*[v for s in model.supports if tag in s for v in s[tag]]}))
           for tag in tags]
    intervals=[]
    for x,k in zip(worst,knots):
        i=np.searchsorted(k,x,side='right')-1;intervals.append((k[i],k[i+1]))
    witnesses=[]
    for axis in range(3):
        a=worst.copy();b=worst.copy();a[axis],b[axis]=intervals[axis]
        degree=flat_cell_degree(tags,model.supports,a,b)
        part=segment_partition(table,gid,a,b)
        # The worst structural contact is chosen for diagnosis, never fitting.
        ts=[t for t in part['parameters'] if 0<t<1]
        if not ts:ts=[.5]
        sample=np.asarray([a,*[(1-t)*a+t*b for t in ts],b])
        batch=renderer.render(gid,sample)
        values=[geometry.control_points(*geometry.operands(_commands(batch.paths,i,1)))
                for i in range(len(sample))]
        candidates=[polynomial_witness([0.,t,1.],np.asarray([values[0],values[i+1],values[-1]]),degree)
                    for i,t in enumerate(ts)]
        at=max(range(len(candidates)),key=lambda i:candidates[i]['lower_bound'])
        witnesses.append(dict(axis=tags[axis],**candidates[at],
                              points=[a.tolist(),sample[at+1].tolist(),b.tolist()]))
    # Body diagonals vary all three physical axes simultaneously. Dyadic
    # parameters retain exact collinearity in these F2DOT14 support cells.
    diagonals=[]
    for reverse in itertools.product((False,True),repeat=2):
        bounds=[pair[::-1] if flip else pair for pair,flip in zip(intervals,(False,*reverse))]
        a=np.asarray([v[0] for v in bounds]);b=np.asarray([v[1] for v in bounds])
        degree=flat_cell_degree(tags,model.supports,a,b);ts=np.arange(5)/4
        sample=(1-ts[:,None])*a+ts[:,None]*b
        batch=renderer.render(gid,sample)
        values=np.asarray([geometry.control_points(*geometry.operands(_commands(batch.paths,i,1)))
                           for i in range(len(sample))])
        diagonals.append(dict(axis='joint',**polynomial_witness(ts,values,degree),points=sample.tolist()))
    witnesses.append(max(diagonals,key=lambda w:w['lower_bound']))
    return dict(holdout_count=len(held),max_holdout_error=float(errors.max()),
                failing_holdouts=int(np.count_nonzero(errors>geometry.LIMIT)),
                holdouts_disjoint_from_training_and_midpoint_grid=True,
                metadata_sha256=hashlib.sha256(meta.read_bytes()).hexdigest(),
                coefficient_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
                witnesses=witnesses)


def probe_status(cases):
    if not cases or any(c['native_failures'] for c in cases):return 'FAIL_SOURCE_NATIVE'
    if any(c['dense_model'] and (c['dense_model']['failing_holdouts'] or
            any(w['native_observation_bound']['exceeds_limit'] for w in c['dense_model']['witnesses']))
           for c in cases):return 'FAIL_RETAINED_MODELS'
    return 'PASS_SCOPED_SOURCE_PROBE'


def run(source,source_sha,binary,output,face=0,gids=(1166,19177),dense_models=None):
    source=Path(source).resolve(strict=True);binary=Path(binary).resolve(strict=True)
    output=Path(output).resolve();repo=Path(__file__).resolve().parents[3]
    require(platform.system()=='Darwin','joint_native_probe_requires_macOS')
    require(not output.exists() and not output.is_relative_to(repo),'new_private_directory_required')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    require(digest==source_sha,'source_hash_mismatch')
    with TTCollection(source,lazy=True) as c:
        require(type(face) is int and 0<=face<len(c.fonts),'invalid_source_face')
        f=c.fonts[face];tags=tuple(a.axisTag for a in f['fvar'].axes)
        table=HVGL(f.reader['hvgl'],f.reader['hvpm'] if 'hvpm' in f else None)
    require(tags==('WDTH','wght','HGHT'),'physical_source_axis_order_required')
    require(gids and len(set(gids))==len(gids) and all(type(g) is int and
            0<=g<table.glyph_count and table.part(g).axis_count==3 for g in gids),'invalid_joint_GID_plan')
    output.mkdir(parents=True,mode=0o700)
    renderer=BatchGeometry(table,isolated_tangents=True)
    report=dict(source_sha256=digest,face_index=face,axis_tags=tags,
                oracle_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                os=platform.platform(),limit_source_font_units=geometry.LIMIT,cases=[],
                font_acceptance=False,full_font_coverage=False,
                scope='post_avar_source_geometry_and_retained_model_diagnosis')
    for gid in gids:
        plan,partitions=independent_plan(table,gid)
        dense=dense_witnesses(table,renderer,gid,tags,dense_models) if dense_models else None
        if dense:
            for witness in dense['witnesses']:
                witness['native_plan_indices']=list(range(len(plan),len(plan)+len(witness['points'])))
                plan.extend(dict(kind='polynomial_witness',point=p) for p in witness.pop('points'))
        (output/f'gid-{gid}-plan.json').write_text(json.dumps(plan,indent=2))
        (output/f'gid-{gid}-partitions.json').write_text(json.dumps(partitions,indent=2))
        row=dict(glyph_id=gid,observations=len(plan),categories={},max_portable_native_error=0.,
                 native_failures=[],dense_model=dense)
        native_values={}
        with (output/f'gid-{gid}-native.jsonl').open('x') as raw, \
             (output/f'gid-{gid}-stderr.jsonl').open('x') as errors:
            for start in range(0,len(plan),128):
                chunk=plan[start:start+128]
                batch=renderer.render(gid,[p['point'] for p in chunk])
                for offset,item in enumerate(chunk):
                    i=start+offset;p=item['point'];kind=item['kind']
                    process=subprocess.run([str(binary),str(source),str(face),
                        ','.join(format(v,'.17g') for v in p),str(gid),'1'],
                        capture_output=True,text=True,timeout=30)
                    raw.write(process.stdout)
                    errors.write(json.dumps(dict(index=i,returncode=process.returncode,stderr=process.stderr))+'\n')
                    transcript=output/'current-transcript.jsonl';transcript.write_text(process.stdout)
                    proof=validate_transcript(transcript,face=face,coords=p,start=gid,count=1,
                                              parts=False,input_bytes=source.stat().st_size)
                    require(process.returncode==0 and not proof['counts']['failed_outlines'],
                            'joint_native_extraction_failed')
                    native=next(r for r in map(json.loads,process.stdout.splitlines()) if r.get('record')=='outline')
                    cmds=native_commands(native)
                    verdict=compare_commands(_commands(batch.paths,offset,1),cmds)
                    count=row['categories'].setdefault(kind,dict(observations=0,max_error=0.))
                    count['observations']+=1
                    if verdict['max_control_error'] is not None:
                        error=verdict['max_control_error'];count['max_error']=max(count['max_error'],error)
                        row['max_portable_native_error']=max(row['max_portable_native_error'],error)
                    if not verdict['passed']:row['native_failures'].append(dict(index=i,**verdict))
                    if kind=='polynomial_witness':native_values[i]=geometry.control_points(*geometry.operands(cmds))
        if dense:
            for witness in dense['witnesses']:
                indices=witness.pop('native_plan_indices')
                p=np.asarray([plan[i]['point'] for i in indices])
                axis=0 if witness['axis']=='joint' else tags.index(witness['axis'])
                ts=(p[:,axis]-p[0,axis])/(p[-1,axis]-p[0,axis])
                witness['native_observation_bound']=polynomial_witness(ts,
                    np.asarray([native_values[i] for i in indices]),witness['degree'])
        row['plan_sha256']=hashlib.sha256((output/f'gid-{gid}-plan.json').read_bytes()).hexdigest()
        row['transcript_sha256']=hashlib.sha256((output/f'gid-{gid}-native.jsonl').read_bytes()).hexdigest()
        report['cases'].append(row)
        report['status']=probe_status(report['cases'])
        require(hashlib.sha256(source.read_bytes()).hexdigest()==digest,'source_changed_during_probe')
        (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
        print(json.dumps(row),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--source-sha256',required=True)
    parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--private-output',type=Path,required=True)
    parser.add_argument('--face',type=int,default=0)
    parser.add_argument('--gids',default='1166,19177')
    parser.add_argument('--dense-models',type=Path)
    args=parser.parse_args()
    result=run(args.source,args.source_sha256,args.binary,args.private_output,args.face,
               tuple(map(int,args.gids.split(','))),args.dense_models)
    sys.exit(0 if result['status']=='PASS_SCOPED_SOURCE_PROBE' else 1)
