#!/usr/bin/env python3
"""Run a preselected real-glyph corpus in isolated, measured private processes.

Selection precedes fitting. Failures remain in the receipt and never remove a
case from its denominator. No candidate or raw transcript is a public artifact.
"""
import argparse,hashlib,json,platform,re,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from projection_research import fresh_private
from cff2_geometry import require

BASE=Path(__file__).resolve().parents[1]


def stage(command,directory,label):
    log=directory/(label+'.log');start=time.perf_counter()
    if sys.platform=='darwin':prefix=['/usr/bin/time','-l']
    elif sys.platform.startswith('linux'):prefix=['/usr/bin/time','-v']
    else:prefix=[]
    with log.open('w') as stream:
        result=subprocess.run(prefix+list(map(str,command)),stdout=stream,stderr=subprocess.STDOUT)
    text=log.read_text();pattern=(r'(\d+)\s+maximum resident set size' if sys.platform=='darwin'
        else r'Maximum resident set size \(kbytes\):\s*(\d+)')
    match=re.search(pattern,text)
    receipt=dict(stage=label,exit_code=result.returncode,elapsed_seconds=time.perf_counter()-start,
        peak_rss_bytes=int(match[1])*(1 if sys.platform=='darwin' else 1024) if match else None)
    report=directory/label/'report.json'
    if report.exists():receipt['result']=json.loads(report.read_text())
    return receipt


def run(args):
    selection=json.loads(args.selection.read_text())
    require(selection['source_sha256']==args.source_sha256,'selection_source_mismatch')
    chosen={(int(x.split(':')[0]),int(x.split(':')[1])) for x in args.case}
    available={(r['face'],r['gid']) for r in selection['selection']}
    require(not chosen-available,'requested_case_not_in_preselected_corpus')
    require(not (args.fields_directory or args.parameters_directory) or len(chosen)==1,
            'reused_models_require_one_selected_case')
    out=fresh_private(args.private_output)
    report=dict(selection_seed=selection['seed'],source_sha256=args.source_sha256,
        platform=platform.platform(),max_boxes=args.max_boxes,parameter_level=args.level,
        random_native_positions=args.random,seed=args.seed,selection_count=len(available),
        requested_cases=sorted(chosen or available),cases=[],production_accepted=False,
        full_font_coverage=False,DirectWrite='NOT_RUN')
    common=['--source',args.source,'--source-sha256',args.source_sha256]
    for row in selection['selection']:
        face,gid=row['face'],row['gid']
        if chosen and (face,gid) not in chosen:continue
        directory=out/f'face{face}-gid{gid}';directory.mkdir()
        case=dict(face=face,gid=gid,reasons=row['reasons'],stages=[],passed=False)
        report['cases'].append(case)
        fit=BASE/'tools/projection_research.py'
        identity=common+['--face',face,'--gid',gid]
        commands=[('fields',[sys.executable,fit,'fit-fields',*identity,'--max-boxes',args.max_boxes,
            '--seed',args.seed+gid+face*100000,'--private-output',directory/'fields']),
            ('parameters',[sys.executable,fit,'fit-parameters',*identity,'--level',args.level,
            '--max-nodes',args.max_nodes,'--seed',args.seed+gid+face*100000+1,'--private-output',directory/'parameters']),
            ('build',[sys.executable,fit,'build',*identity,'--atlas',directory/'fields/atlas.npz',
            '--parameters',directory/'parameters/parameters.npz','--private-output',directory/'build']),
            ('compressed',[sys.executable,BASE/'platform/compress_joint_font.py',directory/'build/candidate.otf',
            '--private-output',directory/'compressed']),
            ('native',[sys.executable,BASE/'platform/probe_projection_candidate.py',*identity,
            '--candidate',directory/'compressed/candidate.otf','--atlas',directory/'fields/atlas.npz',
            '--parameters',directory/'parameters/parameters.npz','--hvf-oracle',args.hvf_oracle,
            '--seed',args.seed+gid+face*100000+2,'--random',args.random,'--seams',128,
            '--fonttools',256,'--private-output',directory/'native'])]
        # Resume after a measured fitting stage without overwriting any earlier
        # result. Reused models retain their original fitting receipts; native
        # acceptance is always fresh. Identity is checked again by build/probe.
        for label,previous,filename in (('fields',args.fields_directory,'atlas.npz'),
                                        ('parameters',args.parameters_directory,'parameters.npz')):
            if previous is None:continue
            saved=json.loads((previous/'report.json').read_text())
            require(saved.get('stage_passed') and saved['identity']==dict(
                source_sha256=args.source_sha256,face_index=face,glyph_id=gid),'invalid_reused_corpus_stage')
            path=previous/filename
            case['stages'].append(dict(stage=label,reused=True,exit_code=0,result=saved,
                input_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            commands=[(name,[previous/filename if x==directory/label/filename else x for x in command])
                      for name,command in commands if name!=label]
        for label,command in commands:
            print(json.dumps(dict(face=face,gid=gid,starting=label)),flush=True)
            case['running_stage']=label
            (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            measured=stage(command,directory,label);case['stages'].append(measured)
            case.pop('running_stage')
            (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(dict(face=face,gid=gid,stage=label,exit_code=measured['exit_code'],
                                 seconds=measured['elapsed_seconds'],peak_rss_bytes=measured['peak_rss_bytes'])),flush=True)
            if measured['exit_code']!=0:
                case['failed_stage']=label;break
        else:
            case['passed']=bool(case['stages'][-1]['result']['strict_independent_native_passed'])
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    report['passed_cases']=sum(c['passed'] for c in report['cases'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(cases=len(report['cases']),passed=report['passed_cases'])),flush=True)
    return all(c['passed'] for c in report['cases'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','selection','hvf-oracle','private-output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source-sha256',required=True);p.add_argument('--case',action='append',default=[],help='face:GID; must already be selected')
    p.add_argument('--max-boxes',type=int,default=2048);p.add_argument('--level',type=int,default=14)
    p.add_argument('--max-nodes',type=int,default=1000000);p.add_argument('--random',type=int,default=4096)
    p.add_argument('--seed',type=int,default=2026110701)
    p.add_argument('--fields-directory',type=Path,help='Reuse a successful private field-stage archive for one case')
    p.add_argument('--parameters-directory',type=Path,help='Reuse a successful private parameter-stage archive for one case')
    raise SystemExit(0 if run(p.parse_args()) else 1)
