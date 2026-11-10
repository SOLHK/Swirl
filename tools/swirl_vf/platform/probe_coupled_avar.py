#!/usr/bin/env python3
"""Measure avar v2 coupling using authored, measurably variable CFF2 outlines.

Experimental capability only, not a source converter or a production dependency.
The current Microsoft avar page describes v1. This separately probes the avar2
extension already present in fontTools; it does not infer Windows support from
HarfBuzz/CoreText. An unchanged font is a native positive control and ignoring
the mapping must produce a large counterfactual error.
"""
from __future__ import annotations
import argparse,hashlib,io,itertools,json,platform,subprocess
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import buildVarStore,buildVarRegionList,buildVarData,buildDeltaSetIndexMap
import experiment_vertical_gpos as fixture
import probe_coretext_vertical_gpos as ct
import probe_directwrite_vertical_layout as dw
from make_cff2_fixture import convert,geometry
from metric_variations import add_metric_variations

TAGS=('WDTH','wght','HGHT')
POINTS=tuple(itertools.product((-1.,0.,1.),repeat=3))+tuple(tuple(p) for p in np.random.default_rng(18022).uniform(-1,1,(32,3)))


def build():
    raw,_=fixture.original_fixture();f=TTFont(io.BytesIO(raw));del f['HVAR'];add_metric_variations(f)
    font,models=convert(f,0)
    for name in ('han','han.hk'):
        m=models[name];zero=m.deltas[0].copy();delta=np.zeros_like(zero);delta[::2]=zero[::2]/4
        models[name]=geometry.OutlineModel(m.axis_tags,m.operators,
            [{},{'WDTH':(0.,1.,1.)},{'WDTH':(-1.,-1.,0.)}],np.asarray([zero,delta,-delta]),dict(m.evidence))
    font=geometry.install(font,models);base=fixture.serialize(font)
    # Preserve the already serialized outline/metric bytes. Recompiling an
    # in-memory CFF2 twice can introduce explicit default vsindex operators.
    font=TTFont(io.BytesIO(base),recalcBBoxes=False)
    avar=newTable('avar');avar.majorVersion=2;avar.minorVersion=0
    avar.segments={tag:{-1.:-1.,0.:0.,1.:1.} for tag in TAGS};avar.table=otTables.avar();avar.table.Reserved=0
    regions=[{'WDTH':(0.,1.,1.)},{'WDTH':(-1.,-1.,0.)},{'HGHT':(0.,1.,1.)},{'HGHT':(-1.,-1.,0.)}]
    avar.table.VarStore=buildVarStore(buildVarRegionList(regions,list(TAGS)),
        [buildVarData([0,1,2,3],[[-8192,8192,8192,-8192],[0,0,0,0],[0,0,0,0]],optimize=False)])
    avar.table.VarIdxMap=buildDeltaSetIndexMap([0,1,2]);font['avar']=avar
    return base,fixture.serialize(font)


def run(output,native,binary=None):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    report={'scope':'authored_experimental_avar2_coordinate_capability','os':platform.platform(),
        'native':native,'limit':1/32,'mapping':'WDTH_out=(WDTH_in+HGHT_in)/2; other axes unchanged',
        'source_font_acceptance':'NOT_RUN','production_accepted':False,'cases':{}}
    if native=='coretext':
        code=output/'probe.swift';code.write_text(ct.make_harness());binary=output/'probe-native'
        p=subprocess.run(['xcrun','swiftc','-O',str(code),'-o',str(binary)],capture_output=True,text=True,timeout=180)
        (output/'compile.log').write_text(p.stdout+p.stderr);fixture.require(p.returncode==0,'coupled_avar_compile_failed')
        requests=[r for r in ct.requests('vert',POINTS) if r['text']=='single_han' and r['policy']=='default' and r['direction']=='ltr']
        for r in requests:r['observe_axis_echo_mismatch']=True
    else:
        binary=Path(binary).resolve(strict=True)
        requests=[r for r in dw.requests(POINTS) if r['route']=='vert' and r['text_kind']=='single_han' and r['policy']=='default' and r['direction']=='H']
    base,coupled=build()
    for label,blob in (('baseline',base),('coupled',coupled)):
        path=output/f'{label}.otf';path.write_bytes(blob)
        if native=='coretext':
            f=TTFont(io.BytesIO(blob));cfg={'scope':'independent_original_GPOS_fixture_only','font_path':str(path),
                'font_sha256':hashlib.sha256(blob).hexdigest(),'table_hashes':{t:hashlib.sha256(f.getTableData(t)).hexdigest() for t in f.keys() if t!='GlyphOrder'},
                'absent_tables':['glyf','gvar','loca','GPOS','GDEF'],'requests':requests}
            manifest=output/f'{label}.json';manifest.write_text(json.dumps(cfg))
            p=subprocess.run([str(binary),str(manifest)],capture_output=True,text=True,timeout=180)
            rows=list(map(json.loads,p.stdout.splitlines()))
            records=[r for r in rows if r.get('type')=='observation']
            ct.require_registration_cleanup([r for r in rows if r.get('type')=='fixture_registration_cleanup'],cfg['font_sha256'])
        else:
            p=subprocess.run([str(binary),str(path),'--authored-cff2','--observe-axis-echo'],
                input=''.join(dw.request_line(r) for r in requests),capture_output=True,text=True,timeout=180)
            (output/f'{label}.jsonl').write_text(p.stdout);(output/f'{label}.log').write_text(p.stderr)
            records=dw.parse_transcript(p.stdout,requests,blob,p.returncode,observe_axis_echo=True)['records']
        (output/f'{label}.jsonl').write_text(p.stdout);(output/f'{label}.log').write_text(p.stderr)
        fixture.require(p.returncode==0 and len(records)==len(requests),'coupled_avar_native_incomplete')
        errors=[];counter=[];echo=0
        for req,row in zip(requests,records):
            if native=='coretext':
                q=req['normalized'];glyph=row['glyphs'][0];actual=glyph['path_bounds'][2:];gid=glyph['gid']
                echo+=not glyph['raw_axis_echo_matches']
            else:
                q=req['requested_normalized_model'];run,glyph=dw.flatten(row)[0];b=run['baseline_relative_ink_bounds']
                actual=(b[2]-b[0],b[3]-b[1]);gid=glyph['gid'];echo+=not run['raw_axis_echo_matches']
            fixture.require(gid in (2,3),'coupled_avar_wrong_GSUB_route')
            # The existing authored quadrilateral has xMin=90+7*gid,
            # xMax=350+5*gid, yMin=100, yMax=650-5*gid for GIDs 2/3.
            # Analytic X scaling is independent of variation-store decoding.
            x=(q[0]+q[2])/2 if label=='coupled' else q[0]
            width=260-2*gid;expected=(width*(1+x/4),550-5*gid)
            errors.append(float(np.max(np.abs(np.asarray(actual)-expected))))
            counter.append(abs(width*(1+q[0]/4)-expected[0]))
        report['cases'][label]={'checks':len(errors),'maximum_geometry_error':max(errors),
            'failures':sum(e>1/32 for e in errors),'raw_axis_echo_failures':int(echo),
            'ignored_mapping_counterfactual_max_error':max(counter),'font_sha256':hashlib.sha256(blob).hexdigest()}
    fixture.require(report['cases']['coupled']['ignored_mapping_counterfactual_max_error']>=64,
                    'coupled_mapping_test_not_discriminating')
    report['status']='PASS_AUTHORED_CAPABILITY' if all(r['failures']==0 for r in report['cases'].values()) else 'COUPLED_MAPPING_NOT_ACCEPTED'
    (output/'report.json').write_text(json.dumps(report,indent=2));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--native',choices=('coretext','directwrite'),required=True);p.add_argument('--binary',type=Path)
    a=p.parse_args();r=run(a.output,a.native,a.binary);print(json.dumps(r))
    if r['status']!='PASS_AUTHORED_CAPABILITY':raise SystemExit(1)
