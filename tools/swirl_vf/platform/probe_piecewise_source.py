#!/usr/bin/env python3
"""Private HVF branch-aware slice reconstruction with independent holdouts.

Manifest: source_sha256, face_index, cases[{glyph_id, anchor_design_coordinates}].
Coordinates are already AFTER avar, in source fvar axis order. No user-axis
mapping is inferred. Model coefficients and branch records remain in the
explicit private output directory; stdout contains only bounded error totals.
This is not a full-design-space or complete-font builder.
"""
from __future__ import annotations
import argparse,hashlib,itertools,json,os,platform,sys,time
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTCollection
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from hvf import HVGL,require
from batch_geometry import BatchGeometry
from hvf_glyph_model import _commands
from hvf_piecewise_axes import line_partition
from piecewise_geometry import fit_slice,point_errors
import cff2_geometry as geometry


def run(source,manifest,output):
    source=Path(source).resolve(strict=True);output=Path(output).resolve()
    require(not output.exists() and not output.is_relative_to(Path(__file__).resolve().parents[3]),
            'new_private_directory_outside_repository_required')
    spec=json.loads(Path(manifest).read_text());digest=hashlib.sha256(source.read_bytes()).hexdigest()
    require(digest==spec['source_sha256'],'source_hash_mismatch')
    output.mkdir(parents=True,mode=0o700)
    with TTCollection(source,lazy=True) as collection:
        face=collection.fonts[spec['face_index']];tags=tuple(a.axisTag for a in face['fvar'].axes)
        table=HVGL(face.reader['hvgl'])
    renderer=BatchGeometry(table,isolated_tangents=True)
    reports=[]
    for case in spec['cases']:
        gid=case['glyph_id'];anchor=np.asarray(case['anchor_design_coordinates'],dtype=float)
        require(anchor.shape==(len(tags),) and table.part(gid).axis_count==len(tags),'explicit_root_axis_vector_required')
        for axis,tag in enumerate(tags):
            started=time.monotonic();partition=line_partition(table,gid,axis,anchor)
            operators=None;cache={}
            def evaluate(xs):
                nonlocal operators
                missing=list(dict.fromkeys(float(x) for x in xs if float(x) not in cache))
                for begin in range(0,len(missing),256):
                    part=missing[begin:begin+256];p=np.tile(anchor,(len(part),1));p[:,axis]=part
                    b=renderer.render(gid,p)
                    for i,x in enumerate(part):
                        ops,v=geometry.operands(_commands(b.paths,i,1))
                        if operators is None:operators=ops
                        require(ops==operators,'source_slice_topology_changed')
                        cache[x]=v
                return np.asarray([cache[float(x)] for x in xs])
            evaluate([0.])
            held=np.random.default_rng(20261102).uniform(-1,1,512)
            model=fit_slice(evaluate,operators,tags,tag,{t:float(anchor[i]) for i,t in enumerate(tags) if i!=axis},
                            held,transitions=partition['knots'])
            nodes=np.linspace(-1,1,9);baseline=evaluate(nodes)
            linear=np.stack([np.interp(held,nodes,baseline[:,i]) for i in range(baseline.shape[1])],axis=1)
            old_error=float(point_errors(linear,evaluate(held)).max(initial=0))
            record={'glyph_id':gid,'axis':tag,'source_sha256':digest,'face_index':spec['face_index'],
                    'partition':partition,'operators':operators,'supports':model.supports,'evidence':model.evidence,
                    'baseline_uniform_nine_knots_max_holdout_error':old_error,'seconds':time.monotonic()-started}
            prefix=f'slice-{gid}-{tag}'
            np.savez_compressed(output/f'{prefix}.npz',deltas=model.deltas)
            (output/f'{prefix}.json').write_text(json.dumps(record,indent=2))
            reports.append({k:v for k,v in record.items() if k not in ('partition','operators','supports')})
            receipt={'source_sha256':digest,'manifest_sha256':hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
                     'os':platform.platform(),'python':sys.version,'cases':reports,'full_three_axis_acceptance':False,
                     'native_validation':'NOT_RUN','production_accepted':False}
            (output/'checkpoint.json').write_text(json.dumps(receipt,indent=2))
            print(json.dumps({'gid':gid,'axis':tag,'knots':len(model.supports),'old_max':old_error,
                 'new_max':model.evidence['max_holdout_error'],'slice_passed':model.evidence['sampled_geometry_passed']}),flush=True)
    return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--private-output',type=Path,required=True)
    a=parser.parse_args();run(a.source,a.manifest,a.private_output)
