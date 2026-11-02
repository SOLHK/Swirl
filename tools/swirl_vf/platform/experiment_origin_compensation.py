#!/usr/bin/env python3
"""Native experiment for a 100-FUnit independent vertical-origin offset.

The exact production helper adds GPOS placement. It preserves every raw metric,
outline and GSUB table. Native callbacks and actual drawing are measured
separately. Success for these authored controls is not original-font acceptance.
"""
from __future__ import annotations
import argparse,hashlib,io,json,platform,subprocess,sys
from pathlib import Path
from fontTools.ttLib import TTFont
import experiment_vertical_gpos as fixture
import probe_coretext_vertical_gpos as ct
import probe_directwrite_vertical_layout as dw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from origin_gpos import append_origin_compensation
from vertical_metrics import Metrics,placement_correction,raw_origin_feasibility,coretext_placement_in_outline_frame

POINTS=((0.,0.,0.),(-1.,-1.,-1.),(1.,1.,1.),(-1.,1.,-1.),(1.,-1.,1.),
        (.201171875,.2475,.42225),(-.37,.62,-.18))

def build():
    raw,symbols=fixture.original_fixture()
    font=TTFont(io.BytesIO(raw))
    source=Metrics(800,1000,(0,0),(500,820));target=Metrics(800,1000,(0,0),(400,820))
    correction=placement_correction(source,target)
    font=append_origin_compensation(font,{s.name:(tuple(int(x) for x in correction),[],[]) for s in symbols})
    data=fixture.serialize(font)
    original=TTFont(io.BytesIO(raw));candidate=TTFont(io.BytesIO(data))
    fixture.require(all(original.getTableData(t)==candidate.getTableData(t) for t in fixture.PROTECTED),
                    'origin_experiment_changed_source_tables')
    return raw,data,raw_origin_feasibility(source)


def run(output,native,binary=None):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    raw,data,feasibility=build()
    result={'scope':'authored_100_FUnit_origin_gap','os':platform.platform(),'source_acceptance':'NOT_RUN',
        'raw_API_equivalence':'FAIL_BY_CONSTRUCTION','raw_origin_feasibility':feasibility,
        'layout':{},'visual':{},'native':native,'limit':1/32,'processes':[]}
    # HarfBuzz comparison includes default horizontal identity and independent
    # raw vertical origins. It is not a substitute for the native comparisons.
    hb_max=0.;hb_count=0
    for p in POINTS:
        for direction in ('ltr','ttb'):
            a=fixture.shape(raw,p,direction,'zh-cn');b=fixture.shape(data,p,direction,'zh-cn')
            for x,y in zip(a['glyphs'],b['glyphs']):
                fixture.require(all(x[k]==y[k] for k in ('gid','x_advance','y_advance','metric_width','metric_height','metric_vertical_origin')),
                                'origin_compensation_changed_HB_raw_metrics_or_advances')
                hb_max=max(hb_max,abs(y['x_offset']-x['x_offset']-(-100 if direction=='ttb' else 0)))
                hb_count+=1
    result['HarfBuzz']={'observations':hb_count,'maximum_placement_error':hb_max}
    observed=[]
    if native=='coretext':
        swift=output/'origin.swift';exe=output/'origin-native';swift.write_text(ct.make_harness())
        run=subprocess.run(['xcrun','swiftc','-O',str(swift),'-o',str(exe)],capture_output=True,text=True,timeout=180)
        fixture.require(run.returncode==0,'origin_harness_compile_failed:'+run.stderr[-2000:])
        requests=[r for r in ct.requests('vert',POINTS) if r['text']=='single_han' and r['language']=='zh-CN']
    elif native=='directwrite':
        exe=Path(binary).resolve(strict=True)
        requests=[r for r in dw.requests(POINTS) if r['route']=='vert' and r['text_kind']=='single_han' and r['locale']=='zh-CN']
    else:requests=[]
    for label,blob in [('source',raw),('compensated',data)] if native!='none' else []:
        path=output/f'{label}.ttf';path.write_bytes(blob)
        if native=='coretext':
            font=TTFont(io.BytesIO(blob));config={'scope':'independent_original_GPOS_fixture_only','font_path':str(path),
                'font_sha256':hashlib.sha256(blob).hexdigest(),
                'table_hashes':{t:hashlib.sha256(font.getTableData(t)).hexdigest() for t in (*fixture.PROTECTED,'name','GPOS','GDEF') if t in font},
                'absent_tables':[t for t in ('GPOS','GDEF') if t not in font],'requests':requests}
            manifest=output/f'{label}.json';manifest.write_text(json.dumps(config))
            process=subprocess.run([str(exe),str(manifest)],capture_output=True,text=True,timeout=300)
            transcript=[json.loads(line) for line in process.stdout.splitlines()]
            records=[r for r in transcript if r.get('type')=='observation']
            fixture.require(process.returncode==0 and len(records)==len(requests),'origin_CoreText_incomplete')
            ct.require_registration_cleanup([r for r in transcript if r.get('type')=='fixture_registration_cleanup'],config['font_sha256'])
        else:
            process=subprocess.run([str(exe),str(path)],input=''.join(dw.request_line(r) for r in requests),
                                   capture_output=True,text=True,timeout=300)
            parsed=dw.parse_transcript(process.stdout,requests,blob,process.returncode);records=parsed['records']
        (output/f'{label}.jsonl').write_text(process.stdout);(output/f'{label}.stderr.log').write_text(process.stderr)
        result['processes'].append({'variant':label,'sha256':hashlib.sha256(blob).hexdigest(),'exit_code':process.returncode,'observations':len(records)})
        observed.append(records)
    for request,a,b in zip(requests,*observed) if observed else []:
        if native=='coretext':
            fixture.require(a['request']==b['request']==request and a['reported_axes']==b['reported_axes'],'origin_CoreText_request_mismatch')
            ag,bg=a['glyphs'][0],b['glyphs'][0]
            for field in ('gid','metric_width','metric_height','metric_vertical_origin','base_advance'):
                fixture.require(ag[field]==bg[field],'origin_CoreText_raw_metric_or_advance_changed')
            # Inspect the actual text matrix; do not infer X placement from the
            # baseline-oriented CTRun position vector in a vertical run.
            direction=request['direction'];policy=request['policy']
            av=coretext_placement_in_outline_frame(ag['base_origin'],ag['text_matrix'])
            bv=coretext_placement_in_outline_frame(bg['base_origin'],bg['text_matrix'])
            shift=[bv[i]-av[i] for i in range(2)]
            expected=-100 if direction=='ttb' and policy!='disabled' else 0
            group=result['layout'].setdefault('/'.join((policy,direction)),{'checks':0,
                'max_X_error':0.,'max_Y_change':0.,'raw_metrics_unchanged':True,
                'base_advances_unchanged':True,'positioned_advance_vectors_changed':0})
            group['checks']+=1;group['max_X_error']=max(group['max_X_error'],abs(shift[0]-expected))
            group['max_Y_change']=max(group['max_Y_change'],abs(shift[1]))
            group['positioned_advance_vectors_changed']+=ag['advance']!=bg['advance']
            result['visual'].setdefault('/'.join((policy,direction)),[]).append(
                {'source_frame_ink':a.get('frame_ink'),'candidate_frame_ink':b.get('frame_ink'),
                 'source_run_ink':a.get('run_ink'),'candidate_run_ink':b.get('run_ink'),
                 'font_units_per_pixel':1/ct.RASTER_SCALE,'strict_visual_acceptance':'NOT_ESTABLISHED'})
        else:
            ar,ag=dw.flatten(a)[0];br,bg=dw.flatten(b)[0]
            fixture.require(ag['gid']==bg['gid'] and ag['design_metrics']==bg['design_metrics']
                            and ag['advance']==bg['advance'],'origin_DirectWrite_raw_metric_or_advance_changed')
            direction=request['direction'];policy=request['policy'];expected=-100 if direction=='V' and policy!='disabled' else 0
            before=ar['baseline_relative_ink_bounds'];after=br['baseline_relative_ink_bounds']
            group=result['layout'].setdefault('/'.join((policy,direction)),{'checks':0,'max_X_error':0.,'max_Y_change':0.,'raw_metrics_unchanged':True})
            group['checks']+=1;group['max_X_error']=max(group['max_X_error'],abs(after[0]-before[0]-expected))
            group['max_Y_change']=max(group['max_Y_change'],abs(after[1]-before[1]))
            # The unchanged full path is actually positioned by DirectWrite and
            # Direct2D. This establishes ink geometry, not pixel raster identity.
            result['visual']['placed_ink_geometry_measured']=True
            result['visual']['raster_acceptance']='NOT_RUN'
    keys=(('default/ltr','default/ttb','enabled/ttb','disabled/ltr','disabled/ttb')
          if native=='coretext' else ('default/H','default/V','enabled/V','disabled/H','disabled/V'))
    result['required_layout_groups']=list(keys) if native!='none' else []
    result['layout_passed']=(native!='none' and hb_max<=1/32 and all(
        key in result['layout'] and result['layout'][key]['checks']==len(POINTS)
        and result['layout'][key]['max_X_error']<=1/32 and result['layout'][key]['max_Y_change']<=1/32
        for key in keys))
    result['status']='PASS_AUTHORED_LAYOUT_ONLY' if result['layout_passed'] else 'LAYOUT_NOT_ACCEPTED'
    (output/'report.json').write_text(json.dumps(result,indent=2))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native',choices=('none','coretext','directwrite'),default='none');parser.add_argument('--binary',type=Path)
    a=parser.parse_args();r=run(a.output,a.native,a.binary);print(json.dumps({'status':r['status'],'layout':r['layout']}))
    if a.native!='none' and not r['layout_passed']:raise SystemExit(1)
