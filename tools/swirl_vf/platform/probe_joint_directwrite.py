#!/usr/bin/env python3
"""Authored polynomial/Clamp control; no source-font argument or private data.

Windows execution is through actual TextLayout, including required GSUB and
omitted/explicit hidden defaults. Linux/macOS can generate and validate the
control with HarfBuzz, but must report DirectWrite NOT_RUN.
"""
import argparse,hashlib,itertools,json,platform,subprocess,sys
from pathlib import Path
import numpy as np
from fontTools.ttLib import TTCollection,TTFont
import uharfbuzz as hb
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from probe_polynomial_clamp import build_control,source,delta,ops,TAGS
from test_coretext_extract import make_fixture
from cff2_structural_pool import compress
from probe_joint_representations import compare
from p7_validate_candidate import commands


def run(output,binary=None):
    out=output.resolve()
    if out.exists():raise ValueError('fresh_control_output_required')
    out.mkdir(parents=True)
    make_fixture(out/'authored.ttc')
    with TTCollection(out/'authored.ttc') as collection:
        font,boxes=build_control(collection.fonts[0],share_expressions=True)
    names={1:'Swirl Joint DirectWrite Control',2:'Regular',3:'SwirlJointDirectWriteControl-1',
           4:'Swirl Joint DirectWrite Control',6:'SwirlJointDirectWriteControl',
           16:'Swirl Joint DirectWrite Control',17:'Regular'}
    font['name'].names=[n for n in font['name'].names if n.nameID not in names]
    for index,value in names.items():
        font['name'].setName(value,index,3,1,0x409);font['name'].setName(value,index,1,0,0)
    compression=compress(font);font.save(out/'control.otf')
    points=np.r_[np.asarray(list(itertools.product((-1.,-.5,0.,.5,1.),repeat=3))),
                 np.random.default_rng(2026110719).uniform(-1,1,(256,3))]
    axes=font['fvar'].axes;requests=[]
    for point in points:
        location={a.axisTag:float(np.float32(a.defaultValue+x*(a.defaultValue-a.minValue if x<0 else a.maxValue-a.defaultValue)))
                  for a,x in zip(axes,point)}
        p=np.asarray([(location[a.axisTag]-a.defaultValue)/(a.defaultValue-a.minValue if location[a.axisTag]<a.defaultValue else a.maxValue-a.defaultValue) for a in axes[:3]])
        for mode in ('omitted','explicit'):
            requests.append(dict(id=len(requests),mode=mode,location=location,p=p))
    blob=(out/'control.otf').read_bytes();target=hb.Font(hb.Face(blob));hb.ot_font_set_funcs(target);target.scale=(64000,64000)
    report=dict(scope='authored_control_only',os=platform.platform(),font_sha256=hashlib.sha256(blob).hexdigest(),
        font_bytes=len(blob),requests=len(requests),compression=compression,production_accepted=False,
        original_font_acceptance=False,Windows_11_acceptance='NOT_RUN',DirectWrite='NOT_RUN',
        HarfBuzz=dict(observations=0,failures=0,max_error=0.))
    expected=[]
    for r in requests:
        p=r['p'];wanted=(ops,source(p[None])[0]+np.clip(.25+.6*p[0]+.4*p[1]-.3*p[2],0,1)*delta(p[None])[0]);expected.append(wanted)
        location=dict(r['location'])
        if r['mode']=='explicit':location.update({a.axisTag:a.defaultValue for a in axes[3:]})
        target.set_variations(location);b=hb.Buffer();b.add_str('A');b.guess_segment_properties();hb.shape(target,b)
        verdict=compare(wanted,commands(target,b.glyph_infos[0].codepoint));stats=report['HarfBuzz']
        stats['observations']+=1;stats['failures']+=not verdict['passed'];stats['max_error']=max(stats['max_error'],verdict['error'] or 0.)
    if binary:
        lines=[' '.join([str(r['id']),r['mode']]+[format(r['location'][t],'.17g') for t in TAGS]) for r in requests]
        native=subprocess.run([str(binary.resolve()),str(out/'control.otf')],input='\n'.join(lines)+'\n',capture_output=True,text=True)
        (out/'native.jsonl').write_text(native.stdout);(out/'native.stderr.log').write_text(native.stderr)
        report['native_exit_code']=native.returncode
        if native.returncode==77:report['DirectWrite']='NOT_RUN'
        elif native.returncode:
            report['DirectWrite']='EXECUTION_FAILED'
        else:
            rows=list(map(json.loads,native.stdout.splitlines()))
            if rows[0]['type']!='metadata' or rows[-1].get('requests')!=len(requests) or not rows[-1].get('actual_tables_and_axes_verified'):
                raise ValueError('incomplete_native_transcript')
            report['native_metadata']=rows[0];stats=dict(observations=0,failures=0,max_error=0.,selection_failures=0,advance_failures=0)
            observed=rows[1:-1]
            if len(observed)!=len(requests):raise ValueError('native_request_count_mismatch')
            for r,wanted,row in zip(requests,expected,observed):
                if row['id']!=r['id'] or row['type']!='sample':raise ValueError('native_request_identity_mismatch')
                verdict=compare(wanted,row['commands']);gid=row['gid'];p=r['p']
                selected=3<=gid<11 and np.all((p>=boxes[gid-3].bounds[:,0])&(p<=boxes[gid-3].bounds[:,1]))
                stats['observations']+=1;stats['failures']+=not verdict['passed'];stats['max_error']=max(stats['max_error'],verdict['error'] or 0.)
                stats['selection_failures']+=not selected;stats['advance_failures']+=abs(row['advance']-700)>1/32
            report['DirectWrite']=stats
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path)
    a=p.parse_args();r=run(a.output,a.binary)
    dw=r['DirectWrite'];failed=r['HarfBuzz']['failures'] or (isinstance(dw,dict) and any(dw[k] for k in ('failures','selection_failures','advance_failures'))) or dw=='EXECUTION_FAILED'
    raise SystemExit(1 if failed else 0)
