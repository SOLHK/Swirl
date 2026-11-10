#!/usr/bin/env python3
"""Screen a seeded zero-factor stratum; never claim native font acceptance.

A candidate needs both the existing 1/32 field checks and the stricter 1/1024
representation-change bound. No fonts are built by this screening tool. The
selected denominator and all failures are kept; population-wide eligibility
is not inferred from this small diagnostic sample.
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTCollection
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from hvf import HVGL
from projection_research import fresh_private,source_identity
from projection_factorization import ProjectionSource
from adaptive_projection_atlas import fit,validate
from flat_joint_font import collapse
from cff2_geometry import require,LIMIT


def run(a):
    inventory=json.loads(a.inventory.read_text());selection=json.loads(a.selection.read_text())
    require(selection['source_sha256']==a.source_sha256,'flat_screen_source_mismatch')
    exclude={r['gid']for r in selection['selection']}
    pool=sorted(r['gid']for r in inventory['rows']if r['type2']==0 and r['gid']not in exclude)
    require(0<a.count<=len(pool),'invalid_flat_screen_count')
    chosen=np.random.default_rng(a.seed).choice(pool,a.count,replace=False).tolist()
    out=fresh_private(a.private_output);report=dict(seed=a.seed,population=len(pool),count=a.count,selected_gids=chosen,
        selection_precedes_fitting=True,rows=[],native_verification='NOT_RUN',production_accepted=False,
        population_eligibility_estimated=False,scope='uniform seeded zero-Type2 stratum excluding retained corpus')
    with TTCollection(a.source,lazy=True)as fs:
        f=fs.fonts[0];table=HVGL(f.reader['hvgl'],f.reader['hvpm']if 'hvpm'in f else None)
        for gid in chosen:
            source_identity(a.source,a.source_sha256,0,gid);start=time.perf_counter();source=ProjectionSource(table,gid)
            atlas=fit(source,max_boxes=8,use_source_branches=False)
            require(source.factors==0,'flat_screen_factor_mismatch')
            held=np.random.default_rng(a.seed+gid+1).uniform(-1,1,(4096,3));holdout=validate(atlas,source,held)
            row=dict(gid=gid,max_refinement_error=atlas.evidence['max_refinement_error'],holdout=holdout,
                representation_bound_passed=False,field_checks_passed=atlas.evidence['max_refinement_error']<=LIMIT and holdout['max_envelope_error']<=LIMIT)
            try:
                model=collapse(atlas);row['representation_bound_passed']=True;row['representation_change_control_bound']=model.evidence['representation_change_control_bound']
            except ValueError as error:
                message=str(error)
                if not message.startswith('flat_representation_bound_exceeded:'):raise
                row['representation_change_control_bound']=float(message.split(':')[-1])
            row['seconds']=time.perf_counter()-start;report['rows'].append(row)
            (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(row),flush=True)
    report['passed_screen']=sum(r['field_checks_passed']and r['representation_bound_passed']for r in report['rows'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed_screen':report['passed_screen'],'count':a.count}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','inventory','selection','private-output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source-sha256',required=True);p.add_argument('--count',type=int,default=16);p.add_argument('--seed',type=int,default=2026110867)
    run(p.parse_args())
