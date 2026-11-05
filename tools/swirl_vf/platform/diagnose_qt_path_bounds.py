#!/usr/bin/env python3
"""Private exact curve-bound diagnostic; retain the original Qt gate failures."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from bezier_path_certificate import certify_qt_paths


def diagnose(report):
    if report.get('schema')!=1 or report.get('scope')!='private_source_local_box_only' or \
            report.get('limit_source_units')!=1/32 or report.get('source_font_acceptance') is not False:
        raise ValueError('private_Qt_report_required')
    rows=report['rows']
    if not isinstance(rows,list) or not 1<=len(rows)<=4096 or report['observations']!=len(rows) or \
            any(type(r.get('passed')) is not bool for r in rows) or \
            report['failures']!=sum(not r['passed'] for r in rows):
        raise ValueError('inconsistent_Qt_report_counts')
    results=[];bounded=0;maximum=0.
    for i,row in enumerate(rows):
        if row['passed']:continue
        if row.get('identity') is not True:
            proof=dict(status='NO_CERTIFICATE',reason='native_identity_not_verified')
        else:
            proof=certify_qt_paths(row['actual_path'],row['reference_path'])
        if proof['status']=='BOUND_WITHIN_LIMIT':
            bounded+=1;maximum=max(maximum,proof['max_curve_distance_bound'])
        results.append(dict(observation=i,proof=proof))
    return dict(status='DIAGNOSTIC_ONLY',source_glyph_id=report['source_glyph_id'],
                source_sha256=report['source_sha256'],font_sha256=report['font_sha256'],
                original_strict_status=report['status'],original_strict_failures=report['failures'],
                observations=len(rows),bounded_failed_observations=bounded,
                unbounded_failed_observations=len(results)-bounded,
                max_curve_distance_bound=maximum if bounded else None,
                limit_source_units=1/32,strict_path_gate_overridden=False,
                source_font_acceptance=False,production_accepted=False,results=results)


def run(inputs,output):
    root=Path(__file__).resolve().parents[3];output=Path(output).resolve()
    if output.exists() or output.is_relative_to(root):
        raise ValueError('new_private_output_required')
    receipts=[]
    for path in inputs:
        path=Path(path).resolve(strict=True)
        if path.is_relative_to(root):raise ValueError('private_input_required')
        data=path.read_bytes();receipt=diagnose(json.loads(data))
        receipt['input_sha256']=hashlib.sha256(data).hexdigest();receipts.append(receipt)
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with output.open('x') as stream:stream.write(json.dumps(receipts,indent=2)+'\n')
    for receipt in receipts:print(json.dumps({k:v for k,v in receipt.items() if k!='results'}))
    return receipts


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',required=True,type=Path,nargs='+')
    parser.add_argument('--private-output',required=True,type=Path)
    args=parser.parse_args();run(args.inputs,args.private_output)
