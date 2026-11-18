#!/usr/bin/env python3
"""Compare full projection fields with an explicit retained Git implementation.

All source samples and the extracted reference module stay in a fresh private
output directory. Only hashes, time and peak RSS appear in the report. Each
method runs in a separate process; equality covers all fields and parameters.
"""
import argparse,hashlib,importlib.util,json,resource,subprocess,sys,time
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTCollection
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from projection_research import source_identity,fresh_private
from projection_factorization import ProjectionSource
from hvf import HVGL
from cff2_geometry import require


def run(a):
    identity=source_identity(a.source,a.source_sha256,a.face,a.gid)
    if a.method:
        cls=ProjectionSource
        if a.method=='reference':
            spec=importlib.util.spec_from_file_location('retained_projection_direction',a.reference_module)
            module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
            if a.reference_batch_module:
                bspec=importlib.util.spec_from_file_location('retained_batch_geometry',a.reference_batch_module)
                batch=importlib.util.module_from_spec(bspec);sys.modules[bspec.name]=batch;bspec.loader.exec_module(batch)
                module.BatchGeometry=batch.BatchGeometry
            cls=module.ProjectionSource
        with TTCollection(a.source,lazy=True) as fonts:
            f=fonts.fonts[a.face];provider=cls(HVGL(f.reader['hvgl'],f.reader['hvpm'] if 'hvpm' in f else None),a.gid)
            points=np.random.default_rng(a.seed).uniform(-1,1,(a.samples,3));provider.components(points[:1])
            fields,parameters=hashlib.sha256(),hashlib.sha256();start=time.perf_counter()
            for i in range(0,len(points),256):
                values,t=provider.components(points[i:i+256]);fields.update(values.tobytes());parameters.update(t.tobytes())
            row=dict(identity=identity,method=a.method,seed=a.seed,positions=len(points),factors=provider.factors,
                seconds=time.perf_counter()-start,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                *(1 if sys.platform=='darwin' else 1024),field_sha256=fields.hexdigest(),parameter_sha256=parameters.hexdigest())
        print(json.dumps(row));return
    out=fresh_private(a.private_output);repo=Path(__file__).resolve().parents[3]
    revision=subprocess.check_output(['git','rev-parse','--verify',a.reference_revision+'^{commit}'],cwd=repo,text=True).strip()
    reference=out/'reference.py';reference.write_bytes(subprocess.check_output(
        ['git','show',revision+':tools/swirl_vf/tools/projection_factorization.py'],cwd=repo))
    if a.reference_batch:
        batch_reference=out/'reference_batch.py';batch_reference.write_bytes(subprocess.check_output(
            ['git','show',revision+':tools/swirl_vf/tools/batch_geometry.py'],cwd=repo))
    rows=[]
    for method in ('reference','current'):
        command=[sys.executable,__file__,'--source',str(a.source),'--source-sha256',a.source_sha256,
            '--face',str(a.face),'--gid',str(a.gid),'--samples',str(a.samples),'--seed',str(a.seed),
            '--method',method,'--reference-module',str(reference)]
        if a.reference_batch:command+=['--reference-batch-module',str(batch_reference)]
        result=subprocess.run(command,capture_output=True,text=True);(out/(method+'.stderr.log')).write_text(result.stderr)
        result.check_returncode();rows.append(json.loads(result.stdout))
    exact=all(rows[0][key]==rows[1][key] for key in ('field_sha256','parameter_sha256'))
    report=dict(identity=identity,reference_revision=revision,rows=rows,exact_field_and_parameter_bytes_equal=exact,
                reference_batch_geometry=a.reference_batch,
                accuracy_acceptance=False,concurrent_host_activity_uncontrolled=True)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    require(exact,'projection_direction_bytes_changed')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--source-sha256',required=True)
    p.add_argument('--face',type=int,default=0);p.add_argument('--gid',type=int,required=True)
    p.add_argument('--private-output',type=Path);p.add_argument('--reference-revision')
    p.add_argument('--samples',type=int,default=16384);p.add_argument('--seed',type=int,default=2026110841)
    p.add_argument('--method',choices=('reference','current'));p.add_argument('--reference-module',type=Path)
    p.add_argument('--reference-batch',action='store_true',help='Also compare the retained BatchGeometry implementation')
    p.add_argument('--reference-batch-module',type=Path)
    a=p.parse_args()
    if a.samples<=0 or (not a.method and (not a.private_output or not a.reference_revision)):
        p.error('positive samples, private output and explicit reference revision required')
    run(a)
