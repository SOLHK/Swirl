#!/usr/bin/env python3
"""Use dedicated CFF2 vertical alternates for fractional origin placement.

This authored experiment preserves the horizontal models, GSUB, HVAR/VVAR and
VORG. It changes only the two existing vertical alternate outlines. Raw glyph
geometry and side bearings therefore are NOT equivalent; actual shaped ink
placement is tested separately. The original GPOS strict failures stay intact.
"""
from __future__ import annotations
import argparse,hashlib,io,json,platform,subprocess,sys
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTFont
import experiment_vertical_gpos as fixture
import experiment_origin_compensation as origin
import probe_coretext_vertical_gpos as ct
import probe_directwrite_vertical_layout as dw
from make_cff2_fixture import convert
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from metric_variations import add_metric_variations
from layout_translation import translate_vertical_model
from cff2_side_bearings import install_top_bearings
import cff2_geometry as geometry

VERTICAL_NAMES=('han.vert','han.hk.vert')
POINTS=origin.POINTS+tuple(tuple(map(float,p)) for p in np.random.default_rng(82931).uniform(-1,1,(32,3)))


def desired(p,components):
    x,y=origin.desired(p,True)
    return (x,y if components=='xy' else 0.)


def build(components='xy',repair_y_bearing=False):
    fixture.require(components in ('x','xy'),'unknown_origin_components')
    fixture.require(not repair_y_bearing or components=='xy','Y_bearing_requires_Y_translation')
    raw,_=fixture.original_fixture(); font=TTFont(io.BytesIO(raw));font.ensureDecompiled()
    # Re-encode the unchanged authored phantom model, making explicit CFF2
    # VVAR/VORG as well as HVAR. The comparison starts from this CFF2 baseline.
    del font['HVAR'];add_metric_variations(font)
    baseline,models=convert(font,0)
    supports=[];deltas=[]
    for tag,delta in zip(('WDTH','wght','HGHT'),((-40,6),(-8,-12),(-16,10))):
        supports.extend([{tag:(0.,1.,1.)},{tag:(-1.,-1.,0.)}])
        deltas.extend([delta,tuple(-v for v in delta)])
    supports.append({'WDTH':(0.,1.,1.),'HGHT':(0.,1.,1.)});deltas.append((-10,0))
    base=(-100,24 if components=='xy' else 0)
    if components=='x':deltas=[(x,0) for x,y in deltas]
    for name in VERTICAL_NAMES:
        models[name]=translate_vertical_model(models[name],base,supports,deltas)
    candidate=geometry.install(baseline,models,experimental_layout=True)
    if repair_y_bearing:
        candidate=install_top_bearings(candidate,{name:(baseline['vmtx'].metrics[name][1]-base[1],
            supports,[-v[1] for v in deltas]) for name in VERTICAL_NAMES})
    a,b=fixture.serialize(baseline),fixture.serialize(candidate)
    old,new=TTFont(io.BytesIO(a)),TTFont(io.BytesIO(b))
    protected=sorted(set(old.keys())-{'GlyphOrder','head','CFF2'})
    # vhea extrema are recalculated from the modified vmtx by fontTools.
    if repair_y_bearing:protected=[t for t in protected if t not in ('VVAR','vmtx','vhea')]
    fixture.require(all(old.getTableData(t)==new.getTableData(t) for t in protected),
                    'outline_origin_changed_non_geometry_tables')
    # Independent full-domain geometry checks, including every unmodified GID.
    maximum=0.;checks=0
    for p in POINTS:
        loc=dict(zip(('WDTH','wght','HGHT'),p))
        before,after=old.getGlyphSet(location=loc,normalized=True),new.getGlyphSet(location=loc,normalized=True)
        for name in old.getGlyphOrder():
            ao,av=geometry.operands(geometry.source_commands(before[name]))
            bo,bv=geometry.operands(geometry.source_commands(after[name]))
            fixture.require(ao==bo,'outline_origin_topology_changed')
            shift=desired(p,components) if name in VERTICAL_NAMES else (0,0)
            if len(av):
                error=np.linalg.norm(geometry.control_points(bo,bv)-geometry.control_points(ao,av)-shift,axis=1).max()
                maximum=max(maximum,float(error))
            checks+=1
    fixture.require(maximum<=1/32,'outline_origin_serialization_failed')
    return a,b,{'checks':checks,'maximum_control_translation_error':maximum,'unchanged_tables':protected}


def run(output,native,binary=None,*,components='xy',repair_y_bearing=False):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    a,b,serial=build(components,repair_y_bearing)
    result={'scope':'authored_CFF2_vertical_alternate_layout_only','os':platform.platform(),
        'native':native,'limit':1/32,'source_font_acceptance':'NOT_RUN',
        'raw_geometry_and_side_bearing_equivalence':'FAIL_BY_CONSTRUCTION',
        'raw_axis_echo_failures':0,'raw_axis_echo_samples':[],
        'components':components,'repair_y_bearing':repair_y_bearing,'raw_metric_changes':[],
        'unchanged_horizontal_outlines':True,'serialized':serial,'layout':{},'visual_raster':'NOT_ESTABLISHED',
        'processes':[]}
    hb_checks=0
    for p in POINTS:
        for direction in ('ltr','ttb'):
            for language in ('zh-cn','zh-hk'):
                left=fixture.shape(a,p,direction,language);right=fixture.shape(b,p,direction,language)
                fixture.require(left==right,'outline_origin_changed_HarfBuzz_raw_metrics_or_positions')
                expected=(4 if language=='zh-cn' else 5) if direction=='ttb' else (2 if language=='zh-cn' else 3)
                fixture.require(right['glyphs'][0]['gid']==expected,'outline_origin_HarfBuzz_wrong_GSUB_route')
                hb_checks+=1
    result['HarfBuzz_unchanged_positions_and_routes']=hb_checks
    if native=='coretext':
        code=output/'origin-outline.swift';code.write_text(ct.make_harness());binary=output/'origin-outline-native'
        process=subprocess.run(['xcrun','swiftc','-O',str(code),'-o',str(binary)],capture_output=True,text=True,timeout=180)
        fixture.require(process.returncode==0,'outline_origin_compile_failed:'+process.stderr[-2000:])
        requests=[r for r in ct.requests('vert',POINTS) if r['text']=='single_han' and r['policy']=='default']
        # Preserve the strict raw-axis result while collecting downstream
        # placement. This is not an axis-acceptance override: the result exposes
        # every failure and is labelled separately from native font acceptance.
        for r in requests:r['observe_axis_echo_mismatch']=True
    elif native=='directwrite':
        binary=Path(binary).resolve(strict=True)
        requests=[r for r in dw.requests(POINTS) if r['route']=='vert' and r['policy']=='default' and r['text_kind']=='single_han']
    else:requests=[]
    observations=[]
    for name,blob in [('source',a),('compensated',b)] if requests else []:
        path=output/f'{name}.otf';path.write_bytes(blob)
        if native=='coretext':
            font=TTFont(io.BytesIO(blob));config={'scope':'independent_original_GPOS_fixture_only',
                'font_path':str(path),'font_sha256':hashlib.sha256(blob).hexdigest(),
                'table_hashes':{t:hashlib.sha256(font.getTableData(t)).hexdigest() for t in font.keys() if t!='GlyphOrder'},
                'absent_tables':['glyf','gvar','loca','GPOS','GDEF'],'requests':requests}
            manifest=output/f'{name}.json';manifest.write_text(json.dumps(config))
            process=subprocess.run([str(binary),str(manifest)],capture_output=True,text=True,timeout=300)
            (output/f'{name}.jsonl').write_text(process.stdout);(output/f'{name}.stderr.log').write_text(process.stderr)
            rows=[json.loads(line) for line in process.stdout.splitlines()]
            records=[r for r in rows if r.get('type')=='observation']
            ct.require_registration_cleanup([r for r in rows if r.get('type')=='fixture_registration_cleanup'],config['font_sha256'])
        else:
            process=subprocess.run([str(binary),str(path),'--authored-cff2','--observe-axis-echo'],input=''.join(dw.request_line(r) for r in requests),
                capture_output=True,text=True,timeout=300)
            (output/f'{name}.jsonl').write_text(process.stdout);(output/f'{name}.stderr.log').write_text(process.stderr)
            try:
                parsed=dw.parse_transcript(process.stdout,requests,blob,process.returncode,observe_axis_echo=True)
                fixture.require(parsed['metadata'].get('authored_outline_kind')=='CFF2',
                                'outline_origin_native_CFF2_type_not_verified')
                records=parsed['records']
            except ValueError as error:
                result.update(status='FAIL_NATIVE_EXECUTION',native_failure=str(error))
                result['processes'].append({'variant':name,'sha256':hashlib.sha256(blob).hexdigest(),
                    'exit_code':process.returncode,'stdout_sha256':hashlib.sha256(process.stdout.encode()).hexdigest()})
                (output/'report.json').write_text(json.dumps(result,indent=2))
                raise
        fixture.require(process.returncode==0 and len(records)==len(requests),'outline_origin_native_incomplete')
        result['processes'].append({'variant':name,'sha256':hashlib.sha256(blob).hexdigest(),
                                    'exit_code':process.returncode,'observations':len(records)})
        observations.append(records)
    for req,left,right in zip(requests,*observations) if observations else []:
        if native=='coretext':
            x,y=left['glyphs'][0],right['glyphs'][0];vertical=req['direction']=='ttb';locale=req['language']
            for key in ('gid','metric_width','metric_height','metric_vertical_origin','position','advance','base_origin','base_advance','text_matrix'):
                fixture.require(x[key]==y[key],'outline_origin_CoreText_changed_layout_or_raw_advance:'+key)
            fixture.require(x['actual_run_axes']==y['actual_run_axes'],
                            'outline_origin_CoreText_comparison_instances_differ')
            result['raw_axis_echo_failures']+=int(not x['raw_axis_echo_matches'])+int(not y['raw_axis_echo_matches'])
            shift=[y['path_bounds'][i]-x['path_bounds'][i] for i in range(2)]
            p=req['normalized'];gid=y['gid']
        else:
            xr,x=dw.flatten(left)[0];yr,y=dw.flatten(right)[0];vertical=req['direction']=='V';locale=req['locale']
            fixture.require(xr['actual_face_axes']==yr['actual_face_axes'],
                            'outline_origin_DirectWrite_comparison_instances_differ')
            for variant,run in (('source',xr),('compensated',yr)):
                if not run['raw_axis_echo_matches']:
                    result['raw_axis_echo_failures']+=1
                    result['raw_axis_echo_samples'].append({'variant':variant,'request_id':req['request_id'],
                        'requested_user_axes':req['requested_user_axes'],'float32_input_axes':left['float32_input_axes'],
                        'actual_face_axes':run['actual_face_axes']})
            fixture.require(x['gid']==y['gid'] and x['advance']==y['advance'],'outline_origin_DirectWrite_changed_advance')
            for key in ('advance_width','advance_height','vertical_origin_y'):
                if x['design_metrics'][key]!=y['design_metrics'][key]:
                    result['raw_metric_changes'].append({'request_id':req['request_id'],'field':key,
                        'source':x['design_metrics'][key],'candidate':y['design_metrics'][key]})
            before,after=xr['baseline_relative_ink_bounds'],yr['baseline_relative_ink_bounds']
            shift=[after[0]-before[0],before[1]-after[1]]
            p=req['requested_normalized_model'];gid=y['gid']
        wanted=(4 if locale=='zh-CN' else 5) if vertical else (2 if locale=='zh-CN' else 3)
        fixture.require(gid==wanted,'outline_origin_actual_native_GSUB_route_incorrect')
        expected=desired(p,components) if vertical else (0,0)
        group=result['layout'].setdefault(('vertical' if vertical else 'horizontal')+'/'+locale,
            {'checks':0,'maximum_X_error':0.,'maximum_Y_error':0.})
        group['checks']+=1
        group['maximum_X_error']=max(group['maximum_X_error'],abs(shift[0]-expected[0]))
        group['maximum_Y_error']=max(group['maximum_Y_error'],abs(shift[1]-expected[1]))
    passed=(native!='none' and len(result['layout'])==4 and all(g['checks']==len(POINTS)
        and g['maximum_X_error']<=1/32 and g['maximum_Y_error']<=1/32 for g in result['layout'].values()))
    result['status']='PASS_AUTHORED_VERTICAL_INK_PLACEMENT_ONLY' if passed else 'LAYOUT_NOT_ACCEPTED'
    result['raw_axis_echo_status']='FAIL_RETAINED' if result['raw_axis_echo_failures'] else 'NO_RAW_ECHO_MISMATCH_OBSERVED'
    result['raw_advance_origin_status']='FAIL_RETAINED' if result['raw_metric_changes'] else 'NO_DIFFERENCE_OBSERVED'
    (output/'report.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--native',choices=('none','coretext','directwrite'),default='none');p.add_argument('--binary',type=Path)
    p.add_argument('--components',choices=('x','xy'),default='xy');p.add_argument('--repair-y-bearing',action='store_true')
    args=p.parse_args();r=run(args.output,args.native,args.binary,components=args.components,repair_y_bearing=args.repair_y_bearing);print(json.dumps(r))
    if args.native!='none' and r['status']!='PASS_AUTHORED_VERTICAL_INK_PLACEMENT_ONLY':raise SystemExit(1)
