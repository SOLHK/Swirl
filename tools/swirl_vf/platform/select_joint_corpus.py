#!/usr/bin/env python3
"""Deterministic structural/extreme-strata selection, before any fit is run.

Full inventories and source-derived nonlinear scores remain private. Empty or
non-three-axis roots are counted explicitly. High-complexity extremes are
retained regardless of eventual compilation success.
"""
from collections import Counter
from functools import lru_cache
from itertools import product
import argparse,hashlib,json,time
from pathlib import Path
import sys
import numpy as np
from fontTools.ttLib import TTCollection
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from hvf import HVGL,Shape
from projection_factorization import ProjectionSource
from projection_research import fresh_private
from cff2_geometry import require


def select(rows,score,reverse=False,excluded=()):
    available=[r for r in rows if r['gid'] not in excluded]
    return sorted(available,key=lambda r:((-r[score] if reverse else r[score]),r['gid']))[0]


def run(args):
    start=time.monotonic();out=fresh_private(args.private_output)
    with args.source.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    require(digest==args.source_sha256,'source_hash_mismatch')
    rng=np.random.default_rng(args.seed);report=dict(source_sha256=digest,seed=args.seed,faces=[],selection=[])
    with TTCollection(args.source,lazy=True) as collection:
        for index,font in enumerate(collection.fonts):
            if not all(t in font for t in ('hvgl','fvar','avar')):
                report['faces'].append(dict(face=index,eligible=False));continue
            shape_hash=hashlib.sha256(font.reader['hvgl']+(font.reader['hvpm'] if 'hvpm' in font else b'')).hexdigest()
            report['faces'].append(dict(face=index,eligible=True,glyphs=len(font.getGlyphOrder()),
                source_shape_hash=shape_hash,axes=[dict(tag=a.axisTag,min=a.minValue,default=a.defaultValue,max=a.maxValue) for a in font['fvar'].axes]))
        font=collection.fonts[0];table=HVGL(font.reader['hvgl'],font.reader['hvpm'] if 'hvpm' in font else None)
        @lru_cache(None)
        def complexity(gid):
            part=table.part(gid)
            if isinstance(part,Shape):
                c=Counter(part.blends)
                return (sum(part.path_sizes),len(part.path_sizes),c[0],c[2],1)
            values=[complexity(child) for child,_,_ in part.subparts]
            return tuple(sum(x[i] for x in values) for i in range(4))+(1+max((x[4] for x in values),default=0),)
        rows=[];ineligible=Counter()
        order=font.getGlyphOrder()
        for gid in range(table.glyph_count):
            curves,contours,type0,type2,depth=complexity(gid)
            if curves==0:ineligible['empty_outline']+=1;continue
            if table.part(gid).axis_count!=3:ineligible['root_axis_count']+=1;continue
            rows.append(dict(gid=gid,curves=curves,contours=contours,type0=type0,type2=type2,depth=depth,
                             advance=font['hmtx'].metrics[order[gid]][0]))
        selected={1166:['retained_anchor'],19177:['retained_anchor']}
        for key,reverse in (('curves',False),('curves',True),('contours',True),('type2',True),('type0',True),('depth',True),('advance',False),('advance',True)):
            row=select(rows,key,reverse,selected);selected[row['gid']]=[('maximum_' if reverse else 'minimum_')+key]
        ranked=sorted(rows,key=lambda r:(r['curves'],r['gid']))
        middle=ranked[len(ranked)//2];selected.setdefault(middle['gid'],[]).append('median_curve_count')
        pool=set(selected)|set(int(g) for g in rng.choice([r['gid'] for r in rows],64,replace=False))
        corners=np.asarray(list(product((-1.,1.),repeat=3)))
        signs=np.prod(corners,axis=1)
        positions=np.r_[corners,np.zeros((1,3)),rng.uniform(-1,1,(31,3))]
        scores=[]
        for gid in sorted(pool):
            try:
                source=ProjectionSource(table,gid);fields,parameters=source.components(positions)
                values=fields[:,0]+np.einsum('nf,nfp->np',np.clip(parameters,0,1),fields[:,1:])
                controls=np.cumsum(values.reshape(len(positions),-1,2),axis=1)
                mixed=np.einsum('n,npk->pk',signs,controls[:8])/8
                widths=np.ptp(controls[8],axis=0)
                scores.append(dict(gid=gid,strong_coupling=float(np.linalg.norm(mixed,axis=1).max()),
                    clamp_contacts=int(sum(np.count_nonzero((parameters.min(axis=0)<t)&(parameters.max(axis=0)>t)) for t in (0,1))) if parameters.shape[1] else 0,
                    width=float(widths[0]),height=float(widths[1]),projection_factors=source.factors))
            except Exception as error:
                scores.append(dict(gid=gid,error=str(error)))
        valid=[r for r in scores if 'error' not in r]
        for key in ('strong_coupling','clamp_contacts','height'):
            row=select(valid,key,True);selected.setdefault(row['gid'],[]).append('maximum_'+key+'_in_structural_plus_seeded_pool')
        by_gid={r['gid']:r for r in rows};score_by_gid={r['gid']:r for r in scores}
        for gid,reasons in selected.items():
            report['selection'].append(dict(face=0,gid=gid,reasons=reasons,structure=by_gid[gid],probe=score_by_gid[gid]))
        # A second face from the opposite end of the TTC is selected without
        # looking at acceptance. Its independent metrics/maps are retained.
        other=next((r['face'] for r in reversed(report['faces']) if r['eligible'] and r['face']!=0),None)
        if other is not None:
            for gid in (select(rows,'curves',False)['gid'],select(valid,'clamp_contacts',True)['gid']):
                report['selection'].append(dict(face=other,gid=gid,reasons=['cross_face_extreme_pair']))
        report.update(eligible_root_glyphs=len(rows),ineligible=dict(ineligible),nonlinear_probe_pool=len(pool),
                      structural_distribution={key:dict(min=min(r[key] for r in rows),max=max(r[key] for r in rows),
                          p50=float(np.median([r[key] for r in rows])),p95=float(np.percentile([r[key] for r in rows],95)))
                          for key in ('curves','contours','type0','type2','depth')})
        (out/'inventory.json').write_text(json.dumps(dict(rows=rows,nonlinear_scores=scores)))
    report['seconds']=time.monotonic()-start
    (out/'selection.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--source-sha256',required=True)
    p.add_argument('--private-output',type=Path,required=True);p.add_argument('--seed',type=int,default=2026110607)
    run(p.parse_args())
