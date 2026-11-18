#!/usr/bin/env python3
"""A/B isolated sampling cost and exact parameter equality on a private glyph."""
import argparse,hashlib,json,resource,subprocess,sys,time
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTCollection
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from projection_research import source_identity,fresh_private
from projection_factorization import ProjectionSource
from hvf import HVGL


def run(a):
    identity=source_identity(a.source,a.source_sha256,a.face,a.gid)
    if a.method:
        with TTCollection(a.source,lazy=True) as fonts:
            font=fonts.fonts[a.face];table=HVGL(font.reader['hvgl'],font.reader['hvpm'] if 'hvpm' in font else None)
            provider=ProjectionSource(table,a.gid);provider(np.zeros((1,3)))
            positions=np.random.default_rng(a.seed).uniform(-1,1,(a.samples,3));values=[];start=time.perf_counter()
            for offset in range(0,len(positions),256):
                p=positions[offset:offset+256]
                values.append(provider.components(p)[1] if a.method=='component_fields' else provider.parameter_values(p))
            seconds=time.perf_counter()-start;parameters=np.concatenate(values)
        print(json.dumps(dict(identity=identity,method=a.method,seconds=seconds,positions=a.samples,
            factors=parameters.shape[1],parameter_sha256=hashlib.sha256(parameters.tobytes()).hexdigest(),
            peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024))))
        return
    out=fresh_private(a.private_output);rows=[]
    for method in ('component_fields','parameters_only'):
        command=[sys.executable,__file__,'--source',str(a.source),'--source-sha256',a.source_sha256,'--gid',str(a.gid),
                 '--face',str(a.face),'--samples',str(a.samples),'--seed',str(a.seed),'--method',method]
        result=subprocess.run(command,capture_output=True,text=True);(out/(method+'.stderr.log')).write_text(result.stderr)
        result.check_returncode();rows.append(json.loads(result.stdout))
    assert rows[0]['parameter_sha256']==rows[1]['parameter_sha256'],'parameter_sampling_changed'
    report=dict(identity=identity,seed=a.seed,rows=rows,exact_parameter_bytes_equal=True,accuracy_acceptance=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--source-sha256',required=True)
    p.add_argument('--face',type=int,default=0);p.add_argument('--gid',type=int,required=True);p.add_argument('--private-output',type=Path)
    p.add_argument('--samples',type=int,default=16384);p.add_argument('--seed',type=int,default=2026110731)
    p.add_argument('--method',choices=('component_fields','parameters_only'));a=p.parse_args()
    if a.samples<=0 or (not a.method and not a.private_output):p.error('positive sample count and output required')
    run(a)
