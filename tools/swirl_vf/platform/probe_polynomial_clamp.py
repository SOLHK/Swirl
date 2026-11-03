#!/usr/bin/env python3
"""Authored avar2 clamp ramps, polynomial CFF2, and actual GSUB selection.

No proprietary font input is accepted. Native success of this control is not
acceptance of an original HVF glyph. Three original physical axes remain;
four explicitly hidden axes carry one clamped computational parameter.
"""
import argparse
import copy
import sys,json,hashlib,subprocess,itertools
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from joint_polynomial import *
import cff2_geometry as g
from test_coretext_extract import make_fixture
from fontTools.ttLib import TTCollection,TTFont
from fontTools.varLib.featureVars import addFeatureVariations
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib.builder import buildVarStore,buildVarData,buildVarRegionList,buildDeltaSetIndexMap
from probe_joint_representations import compare
from p7_validate_candidate import commands
import uharfbuzz as hb
HIDDEN=tuple(f'H{i:03d}' for i in range(4));ALLTAGS=TAGS+HIDDEN
ops=(('rmoveto',2),('rrcurveto',6),('rlineto',2))
def source(p):
 x,y,z=p.T
 return np.array([100+20*x*x*y,100+30*y*z*z*z,10+0*x,50+15*x*y*z,20+0*x,50+0*x,60+0*x,20*x*x*y*y*z*z,-85+0*x,-95-20*x*x*y*y*z*z]).T
def delta(p):
 x,y,z=p.T
 return np.array([20+10*x*y,30+5*x*x*z,0*x,0*x,0*x,0*x,0*x,0*x,0*x,0*x]).T
def build_control(template, *, share_expressions=False):
    boxes=[]
    for lo in itertools.product((-1,0),repeat=3):
     m=interpolate(np.c_[lo,np.array(lo)+1],ops,source)
     assert np.abs(m.values(m.from_local(GRID))-source(m.from_local(GRID))).max()<1e-6
     d=interpolate(m.bounds,ops,delta)
     m.coefficients+=d.coefficients/2
     m.factors={tag:d.coefficients/8 for tag in HIDDEN};m.signed_factors=True;m.axis_tags=ALLTAGS
     m.evidence['sampled_geometry_passed']=True;boxes.append(m)
    f=copy.deepcopy(template);order=f.getGlyphOrder()+[f'box{i}' for i in range(8)];f.setGlyphOrder(order)
    for i,tag in enumerate(HIDDEN):
     axis=Axis();axis.axisTag=tag;axis.minValue=-1;axis.defaultValue=0;axis.maxValue=1;axis.flags=1;axis.axisNameID=f['name'].addName('Projection ramp '+str(i));f['fvar'].axes.append(axis)
    avar=newTable('avar');avar.majorVersion=2;avar.minorVersion=0;avar.segments={tag:{-1.:-1.,0.:0.,1.:1.} for tag in ALLTAGS};avar.table=otTables.avar();avar.table.Reserved=0
    supports=[{}]+[{tag:triple} for tag in TAGS for triple in ((-1,-1,0),(0,1,1))]
    rows=[[0]*7 for _ in TAGS]+[[round(v*16384) for v in [8*.25-(2*j+1),-8*.6,8*.6,-8*.4,8*.4,8*.3,-8*.3]] for j in range(4)]
    avar.table.VarStore=buildVarStore(buildVarRegionList(supports,ALLTAGS),[buildVarData(list(range(7)),rows,optimize=False)]);avar.table.VarIdxMap=buildDeltaSetIndexMap(list(range(7)));f['avar']=avar
    f['hmtx'].metrics=dict.fromkeys(order,(700,0));f['vmtx'].metrics=dict.fromkeys(order,(1000,0))
    for tag in ('HVAR','VVAR','GSUB','GPOS'):
     if tag in f:del f[tag]
    empty=g.OutlineModel(ALLTAGS,(),[{}],np.zeros((1,0)),{'sampled_geometry_passed':True})
    models=dict.fromkeys(order,empty);models['probe']=boxes[0]
    models.update({f'box{i}':m for i,m in enumerate(boxes)})
    f=g.install(f,models,share_expressions=share_expressions)
    addFeatureVariations(f,[([{t:tuple(b) for t,b in zip(TAGS,m.bounds)}],{'probe':f'box{i}'}) for i,m in enumerate(boxes)])
    return f,boxes

def run(output, *, share_expressions=False):
    out=Path(output).resolve()
    g.require(not out.exists() and not out.is_relative_to(Path(__file__).resolve().parents[3]), 'fresh_external_control_output_required')
    out.mkdir(parents=True, mode=0o700)
    binary=out/'layout-oracle'
    result=subprocess.run(['swiftc','-O',str(Path(__file__).with_name('coretext_joint_layout.swift')),'-o',str(binary)],capture_output=True,text=True)
    (out/'compile.log').write_text(result.stdout+result.stderr);result.check_returncode()
    make_fixture(out/'template.ttc')
    with TTCollection(out/'template.ttc') as template:
        candidate,boxes=build_control(template.fonts[0],share_expressions=share_expressions);candidate.save(out/'poly.otf')
    q=np.r_[np.asarray(list(itertools.product((-1,0,1),repeat=3))),np.random.default_rng(47).uniform(-1,1,(128,3))]
    profiles=((1,500,1000),(100,400,900),(1,500,1000));requests=[]
    for i,p in enumerate(q):
     loc={t:round((d+x*(d-lo if x<0 else hi-d))*16)/16 for t,x,(lo,d,hi) in zip(TAGS,p,profiles)}
     requests.append(dict(id=str(i),text='A',coordinates=loc))
     loc.update(dict.fromkeys(HIDDEN,0.))
    blob=(out/'poly.otf').read_bytes();font=TTFont(out/'poly.otf')
    config=dict(font_path=str(out/'poly.otf'),font_sha256=hashlib.sha256(blob).hexdigest(),axis_defaults={**{t:d for t,(lo,d,hi) in zip(TAGS,profiles)},**dict.fromkeys(HIDDEN,0.)},table_hashes={t:hashlib.sha256(font.reader[t]).hexdigest() for t in ('CFF2','fvar','avar','GSUB','cmap')},requests=requests)
    (out/'manifest.json').write_text(json.dumps(config))
    r=subprocess.run([str(binary),str(out/'manifest.json')],capture_output=True,text=True);(out/'native.jsonl').write_text(r.stdout);(out/'stderr.log').write_text(r.stderr);r.check_returncode()
    rows=[json.loads(line) for line in r.stdout.splitlines()];assert rows[-1]['request_count']==len(requests)
    h=hb.Font(hb.Face(blob));hb.ot_font_set_funcs(h);h.scale=(64000,64000)
    report={k:dict(failures=0,max_error=0,observations=0,selection_failures=0) for k in ('CoreText','HarfBuzz','fontTools')}
    for request,row in zip(requests,rows):
     loc=request['coordinates'];p=np.asarray([(loc[t]-d)/(d-lo if loc[t]<d else hi-d) for t,(lo,d,hi) in zip(TAGS,profiles)])
     expected=(ops,source(p[None,:])[0]+np.clip(.25+.6*p[0]+.4*p[1]-.3*p[2],0,1)*delta(p[None,:])[0]);h.set_variations(loc)
     b=hb.Buffer();b.add_str('A');b.guess_segment_properties();hb.shape(h,b);gid=b.glyph_infos[0].codepoint
     actuals={'CoreText':(row['glyphs'][0]['gid'],row['glyphs'][0]['commands']),'HarfBuzz':(gid,commands(h,gid)),'fontTools':(gid,g.source_commands(font.getGlyphSet(location=loc)[font.getGlyphOrder()[gid]]))}
     for engine,(selected,cmd) in actuals.items():
      v=compare(expected,cmd);stats=report[engine];stats['observations']+=1;stats['failures']+=not v['passed'];stats['max_error']=max(stats['max_error'],v['error'] or 0);stats['selection_failures']+=selected<3 or not np.all((p>=boxes[selected-3].bounds[:,0])&(p<=boxes[selected-3].bounds[:,1]))
    report={'scope':'authored_clamp_polynomial_control_only','production_accepted':False,
            'share_expressions':share_expressions,'font_bytes':len(blob),
            'expression_pool':getattr(candidate,'_swirl_expression_pool_report',None),
            'engines':report};print(json.dumps(report));(out/'report.json').write_text(json.dumps(report,indent=2));return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-output', required=True, type=Path)
    parser.add_argument('--share-expressions',action='store_true')
    args=parser.parse_args();report=run(args.private_output,share_expressions=args.share_expressions)
    sys.exit(0 if all(v['failures']==v['selection_failures']==0 for v in report['engines'].values()) else 1)
