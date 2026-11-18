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
import cff2_geometry as geometry
from fontTools.ttLib import newTable
from required_variation_feature import require_feature
from fontTools.misc.psCharStrings import T2CharString


class MicroBlendControl:
    """One region, no calls; blend stack four, drawing stack six."""
    def __init__(self,tags,base,variant):
        self.axis_tags,self.base,self.variant=tags,base,variant
        self.supports=[{},{tags[0]:(0,1,1)}]
        self.operators=ops;self.evidence={'sampled_geometry_passed':True}
    def charstring(self,vsindex):
        program=[vsindex,'vsindex'];column=0
        for operator,count in self.operators:
            for _ in range(count):
                value=geometry.fixed(float(self.base[column]))
                if column==0:
                    if self.variant=='micro_nested_delta':program.extend([value,0,20,1,'blend',1,'blend'])
                    elif self.variant=='micro_nested_base':program.extend([value,20,1,'blend',0,1,'blend'])
                    else:program.extend([value,20,1,'blend'])
                else:program.append(value)
                column+=1
            program.append(operator)
        return T2CharString(program=program)


def control_variant(font,variant):
    """Isolate format, polynomial execution, avar2 and sharing independently."""
    tags=tuple(a.axisTag for a in font['fvar'].axes)
    zero=np.zeros((1,3));base=source(zero)[0];direction=delta(zero)[0]
    slope=np.zeros_like(base);slope[0]=20
    if variant in ('static_cff2','flat_cff2','flat_avar2'):
        supports=[{}]+[{tag:triple} for tag in tags for triple in ((-1,-1,0),(0,1,1))]
        coefficients=np.zeros((len(supports),len(base)));coefficients[0]=base
        if variant!='static_cff2':coefficients[1:3]=[-slope,slope]
        if variant=='flat_avar2':
            coefficients[0]+=direction/2
            for k in range(4):coefficients[7+2*k:9+2*k]=[-direction/8,direction/8]
        model=geometry.OutlineModel(tags,ops,supports,coefficients,dict(sampled_geometry_passed=True))
        font=geometry.install(font,dict.fromkeys(font.getGlyphOrder(),model))
    if variant.startswith('micro_'):
        model=MicroBlendControl(tags,base,variant)
        font=geometry.install(font,dict.fromkeys(font.getGlyphOrder(),model))
    if variant in ('static_cff2','flat_cff2','horner_avar1') or variant.startswith('micro_'):
        avar=newTable('avar');avar.majorVersion=1;avar.minorVersion=0
        avar.segments={t:{-1.:-1.,0.:0.,1.:1.} for t in tags};font['avar']=avar
    def expected(p):
        if variant=='static_cff2':values=base
        elif variant.startswith('micro_'):values=base+max(0,p[0])**(2 if variant=='micro_nested_delta' else 1)*slope
        elif variant=='flat_cff2':values=base+p[0]*slope
        elif variant=='flat_avar2':values=base+p[0]*slope+np.clip(.25+.6*p[0]+.4*p[1]-.3*p[2],0,1)*direction
        else:values=source(p[None])[0]+(.5 if variant=='horner_avar1' else np.clip(.25+.6*p[0]+.4*p[1]-.3*p[2],0,1))*delta(p[None])[0]
        return ops,values
    return font,expected


def run(output,binary=None,variant='full'):
    out=output.resolve()
    if out.exists():raise ValueError('fresh_control_output_required')
    out.mkdir(parents=True)
    make_fixture(out/'authored.ttc')
    base_variant=variant.removesuffix('_rlig').removesuffix('_requested')
    with TTCollection(out/'authored.ttc') as collection:
        font,boxes=build_control(collection.fonts[0],share_expressions=base_variant!='unshared')
    font,expected_function=control_variant(font,base_variant)
    if variant.endswith('_rlig'):
        for record in font['GSUB'].table.FeatureList.FeatureRecord:
            if record.FeatureTag=='rvrn':record.FeatureTag='rlig'
    require_feature(font,'rlig' if variant.endswith('_rlig') else 'rvrn')
    names={1:'Swirl Joint DirectWrite Control',2:'Regular',3:'SwirlJointDirectWriteControl-1',
           4:'Swirl Joint DirectWrite Control',6:'SwirlJointDirectWriteControl',
           16:'Swirl Joint DirectWrite Control',17:'Regular'}
    font['name'].names=[n for n in font['name'].names if n.nameID not in names]
    for index,value in names.items():
        font['name'].setName(value,index,3,1,0x409);font['name'].setName(value,index,1,0,0)
    compression=compress(font) if base_variant=='full' else None
    font.save(out/'control.otf')
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
    report=dict(scope='authored_control_only',variant=variant,os=platform.platform(),font_sha256=hashlib.sha256(blob).hexdigest(),
        font_bytes=len(blob),requests=len(requests),compression=compression,production_accepted=False,
        original_font_acceptance=False,Windows_11_acceptance='NOT_RUN',DirectWrite='NOT_RUN',
        HarfBuzz=dict(observations=0,failures=0,max_error=0.))
    if base_variant.startswith('micro_'):
        report['micro_isolation']=dict(variation_regions=1,subroutine_calls=0,avar_version=1,
            maximum_blend_stack=4,maximum_drawing_stack=max(n for _,n in ops),
            nested_operand='delta' if base_variant=='micro_nested_delta' else
                           'base' if base_variant=='micro_nested_base' else None)
    expected=[]
    for r in requests:
        p=r['p'];wanted=expected_function(p);expected.append(wanted)
        location=dict(r['location'])
        if r['mode']=='explicit':location.update({a.axisTag:a.defaultValue for a in axes[3:]})
        target.set_variations(location);b=hb.Buffer();b.add_str('A');b.guess_segment_properties();hb.shape(target,b)
        verdict=compare(wanted,commands(target,b.glyph_infos[0].codepoint));stats=report['HarfBuzz']
        stats['observations']+=1;stats['failures']+=not verdict['passed'];stats['max_error']=max(stats['max_error'],verdict['error'] or 0.)
    if binary:
        lines=[' '.join([str(r['id']),r['mode']]+[format(r['location'][t],'.17g') for t in TAGS]) for r in requests]
        command=[str(binary.resolve()),str(out/'control.otf')]+(['rvrn'] if variant.endswith('_requested') else [])
        native=subprocess.run(command,input='\n'.join(lines)+'\n',capture_output=True,text=True)
        (out/'native.jsonl').write_text(native.stdout);(out/'native.stderr.log').write_text(native.stderr)
        report['native_exit_code']=native.returncode
        report['native_error']=native.stderr.strip()
        if native.returncode==77:report['DirectWrite']='NOT_RUN'
        elif native.returncode:
            report['DirectWrite']='EXECUTION_FAILED'
        else:
            rows=list(map(json.loads,native.stdout.splitlines()))
            if rows[0]['type']!='metadata' or rows[-1].get('requests')!=len(requests) or not rows[-1].get('actual_tables_verified'):
                raise ValueError('incomplete_native_transcript')
            report['native_metadata']=rows[0];stats=dict(observations=0,failures=0,max_error=0.,selection_failures=0,advance_failures=0,empty_outlines=0,axis_readback_failures=0,max_axis_readback_error=0.)
            observed=rows[1:-1]
            if len(observed)!=len(requests):raise ValueError('native_request_count_mismatch')
            for r,wanted,row in zip(requests,expected,observed):
                if row['id']!=r['id'] or row['type']!='sample':raise ValueError('native_request_identity_mismatch')
                verdict=compare(wanted,row['commands']);gid=row['gid'];p=r['p']
                selected=3<=gid<11 and np.all((p>=boxes[gid-3].bounds[:,0])&(p<=boxes[gid-3].bounds[:,1]))
                stats['observations']+=1;stats['failures']+=not verdict['passed'];stats['max_error']=max(stats['max_error'],verdict['error'] or 0.)
                stats['selection_failures']+=not selected;stats['advance_failures']+=abs(row['advance']-700)>1/32
                stats['empty_outlines']+=not row['commands']
                stats['axis_readback_failures']+=row['axis_readback_failures']
                stats['max_axis_readback_error']=max(stats['max_axis_readback_error'],row['max_axis_readback_error'])
            report['DirectWrite']=stats
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path)
    p.add_argument('--matrix',action='store_true');a=p.parse_args()
    variants=('static_cff2','flat_cff2','horner_avar1','flat_avar2','unshared','full',
              'flat_cff2_rlig','flat_cff2_requested','full_rlig','full_requested',
              'micro_linear_requested','micro_nested_base_requested','micro_nested_delta_requested') if a.matrix else ('full',)
    reports=[run(a.output/v,a.binary,v) if a.matrix else run(a.output,a.binary) for v in variants]
    def failed(r):
        dw=r['DirectWrite']
        return r['HarfBuzz']['failures'] or (isinstance(dw,dict) and any(dw[k] for k in ('failures','selection_failures','advance_failures','axis_readback_failures'))) or dw=='EXECUTION_FAILED'
    raise SystemExit(1 if any(map(failed,reports)) else 0)
