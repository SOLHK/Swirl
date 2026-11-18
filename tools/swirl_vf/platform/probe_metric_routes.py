#!/usr/bin/env python3
"""Isolate the 849/850 native metric path with authored, byte-checked controls.

Only head.unitsPerEm and the presence of exact HVAR/VVAR encodings vary. Raw
outline/phantom bytes do not. Fonts are measured at their own UPEM, so reported
numbers remain design units. This deliberately changes physical em size and is
NOT a production rescaling fix. Existing strict acceptance is never changed.
"""
from __future__ import annotations
import argparse,hashlib,json,platform,subprocess,sys
from pathlib import Path
from fontTools.ttLib import TTCollection
from test_coretext_extract import make_fixture
from diagnose_coretext_metrics import normalized_location,ideal_metrics
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from metric_variations import add_metric_variations
from verified_axis_oracle import make_launcher
from source_metrics import SourceMetrics

LOCATIONS=[{'WDTH':1.,'wght':100.,'HGHT':1.},
           {'WDTH':500.,'wght':400.,'HGHT':500.},
           {'WDTH':631.25,'wght':523.75,'HGHT':711.125}]


def run(output,binary):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    source=output/'authored-source.ttc';make_fixture(source)
    launcher=make_launcher(output/'exact-axis-oracle',binary)
    report={'scope':'authored_metric_routes_not_original_font','os':platform.platform(),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'native_binary_sha256':hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
            'limit':1/32,'strict_acceptance_changed':False,'variants':[]}
    for upm in (1000,1024,1128,16384):
        for route in ('gvar','HVAR','VVAR','HVAR_VVAR'):
            with TTCollection(source) as collection:
                font=collection.fonts[0]
                protected={t:font.getTableData(t) for t in ('glyf','loca','gvar','hmtx','vmtx','fvar','avar','cmap')}
                if route!='gvar':
                    add_metric_variations(font)
                    if route=='HVAR':del font['VVAR']
                    if route=='VVAR':del font['HVAR']
                font['head'].unitsPerEm=upm
                collection.fonts=[font];path=output/f'{upm}-{route}.ttc';collection.save(path)
            with TTCollection(path) as reopened:
                font=reopened.fonts[0]
                assert all(font.getTableData(t)==b for t,b in protected.items())
                table=[SourceMetrics(font).at(2,normalized_location(p)) for p in LOCATIONS]
            requests=[dict(request_id=str(i),face_index=0,glyph_ids=[2],location=p) for i,p in enumerate(LOCATIONS)]
            run=subprocess.run([str(launcher),str(path)],input=''.join(json.dumps(r)+'\n' for r in requests),
                               capture_output=True,text=True,timeout=120)
            (output/f'{upm}-{route}.jsonl').write_text(run.stdout)
            (output/f'{upm}-{route}.stderr').write_text(run.stderr)
            rows=[json.loads(line) for line in run.stdout.splitlines()]
            observed=[r for r in rows if r.get('glyph_id')==2]
            if run.returncode or len(observed)!=len(requests):raise RuntimeError(f'metric_route_native_failure:{upm}:{route}')
            record={'upm':upm,'route':route,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'exit_code':run.returncode,'protected_tables_identical':list(protected),'observations':[]}
            for i,(r,t) in enumerate(zip(observed,table)):
                fields=('advance_width','advance_height','vertical_origin_x','vertical_origin_y')
                record['observations'].append(dict(location=LOCATIONS[i],table={k:t[k] for k in fields},
                    native={k:r[k] for k in fields},error={k:r[k]-t[k] for k in fields},
                    phantom_top=t['vertical_origin_y'],phantom_bottom=t['vertical_origin_y']-t['advance_height']))
            report['variants'].append(record)
            (output/'report.json').write_text(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--binary',type=Path,required=True);a=parser.parse_args()
    r=run(a.output,a.binary);print(json.dumps({'variants':len(r['variants']),'acceptance':'DIAGNOSTIC_ONLY'}))
