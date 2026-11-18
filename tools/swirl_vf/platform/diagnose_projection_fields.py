#!/usr/bin/env python3
"""Diagnose retained field failures without fitting or serializing a font.

Only aggregate errors and branch counts are reported. A fourth-difference
witness bounds the error of ANY cubic on that particular five-point slice;
it is not a limit on repartitioning, other representations, or physical
outlines after independently varying projection factors. Source evaluation
is float64, so the numerical witness is not an interval proof about Apple HVF.
"""
import argparse,hashlib,json,sys
from collections import Counter
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTCollection
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from projection_research import fresh_private,source_identity
from projection_factorization import ProjectionSource
from adaptive_projection_atlas import ProjectionAtlas,fingerprints,source_events
from hvf import HVGL
from cff2_geometry import require,LIMIT


def cubic_witness(values):
    """Equal-spaced five-point vector data; coefficient absolute sum is 16."""
    values=np.asarray(values);require(values.shape[0]==5,'five_cubic_witness_points_required')
    return np.linalg.norm(np.einsum('n,n...d->...d',np.array([1,-4,6,-4,1])/16,values),axis=-1)


def run(a):
    identity=source_identity(a.source,a.source_sha256,a.face,a.gid);out=fresh_private(a.private_output)
    atlas=ProjectionAtlas.load(a.atlas,identity);points=np.random.default_rng(a.seed).uniform(-1,1,(a.samples,3))
    require(not np.intersect1d(fingerprints(points),atlas.fitting_fingerprints).size,'diagnostic_holdout_overlap')
    maximum=0.;worst=None;physical_maximum=0.;failures=0;physical_failures=0
    with TTCollection(a.source,lazy=True) as fs:
        f=fs.fonts[a.face];provider=ProjectionSource(HVGL(f.reader['hvgl'],f.reader['hvpm'] if 'hvpm' in f else None),a.gid)
        for start in range(0,len(points),64):
            p=points[start:start+64];fields,parameters=provider.components(p);delta=atlas.values(p).reshape(fields.shape)-fields
            absolute=np.cumsum(delta.reshape(len(p),provider.factors+1,-1,2),axis=2)
            per_field=np.linalg.norm(absolute,axis=-1)
            envelope=per_field.sum(axis=1).max(axis=1)
            physical=np.linalg.norm(absolute[:,0]+np.einsum('nf,nfpd->npd',np.clip(parameters,0,1),absolute[:,1:]),axis=-1).max(axis=1)
            failures+=int((envelope>LIMIT).sum());physical_failures+=int((physical>LIMIT).sum());physical_maximum=max(physical_maximum,float(physical.max()))
            if envelope.max()>maximum:
                k=int(envelope.argmax());maximum=float(envelope[k]);worst=p[k].copy();field_maxima=per_field[k].max(axis=1)
        require(worst is not None,'diagnostic_requires_nonzero_error')
        box=next(b for b in atlas.boxes if np.all((worst>=b.bounds[:,0])&(worst<=b.bounds[:,1])))
        events=Counter();witness=0.;witness_field=0;witness_axis=None
        for axis in range(3):
            lo,hi=box.bounds[axis];a0,b0=worst.copy(),worst.copy();a0[axis],b0[axis]=lo,hi
            crossings=source_events(provider,a0,b0);events.update(e['kind'] for e in crossings)
            intervals=[(lo,hi)]
            for event in crossings:
                centre=event['coordinates'][axis];radius=min(centre-lo,hi-centre)
                if radius>0:intervals.append((centre-radius,centre+radius))
            for left,right in intervals:
                p=np.tile(worst,(5,1));p[:,axis]=left+(right-left)*np.arange(5)/4
                fields,_=provider.components(p)
                absolute=np.cumsum(fields.reshape(5,provider.factors+1,-1,2),axis=2)
                bounds=cubic_witness(absolute);value=float(bounds.max())
                if value>witness:
                    witness=value;witness_field=int(np.unravel_index(bounds.argmax(),bounds.shape)[0]);witness_axis=axis
        report=dict(identity=identity,atlas_sha256=hashlib.sha256(a.atlas.read_bytes()).hexdigest(),seed=a.seed,
            samples=len(points),holdouts_disjoint=True,boxes=len(atlas.boxes),factors=provider.factors,
            maximum_component_envelope_error=maximum,component_failures=failures,
            maximum_physical_error=physical_maximum,physical_failures=physical_failures,
            worst_sample_field_maxima=field_maxima.tolist(),worst_cell_chord_event_counts=dict(events),
            measured_cubic_slice_lower_bound=witness,witness_field=witness_field,witness_axis_index=witness_axis,
            witness_scope='retained component-field cubic on one existing cell; floating source evaluation',
            representation_or_format_impossibility_claimed=False,serialization_involved=False,
            native_acceptance=False,limit=LIMIT)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','atlas','private-output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source-sha256',required=True);p.add_argument('--face',type=int,default=0);p.add_argument('--gid',type=int,required=True)
    p.add_argument('--seed',type=int,default=2026110847);p.add_argument('--samples',type=int,default=4096)
    a=p.parse_args();require(a.samples>0,'positive_diagnostic_samples_required');run(a)
