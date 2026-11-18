#!/usr/bin/env python3
"""Authored standard glyf/gvar fractional-component control, three physical axes.

This tests a possible precision representation, not a new HVF fitter. There
are no hidden axes, avar2 maps or GSUB patch glyphs. All source data are authored.
"""
import argparse,hashlib,itertools,json,subprocess,sys
from pathlib import Path
import numpy as np
import uharfbuzz as hb
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont,newTable
from fontTools.ttLib.tables.TupleVariation import TupleVariation
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import cff2_geometry as geometry
from probe_joint_representations import compare
from p7_validate_candidate import commands
TAGS=('WDTH','wght','HGHT');PROFILES=((1,500,1000),(100,400,900),(1,500,1000))
BASE=np.array([[100.15625,.09375],[400.0625,.15625],[500.21875,300.09375],[400.1875,600.03125],[100.0625,600.21875]])
TERMS={}
for axes,vector in (((0,),(20.0625,0)),((1,),(7.125,0)),((2,),(0,16.125)),((0,2),(3.375,0)),((1,2),(0,2.03125)),((0,1,2),(1.0625,1.15625))):
    TERMS[axes]=np.tile(vector,(5,1))
SCALE=32;CENTRE=np.array([320,320])


def path(points):
    points=np.asarray(points).tolist()
    return [['moveTo',*points[0]],['lineTo',*points[1]],['qCurveTo',*points[2],*points[3]],['lineTo',*points[4]],['closePath']]


def build():
    b=FontBuilder(1000,isTTF=True);order=['.notdef','space','detail','probe'];b.setupGlyphOrder(order);b.setupCharacterMap({32:'space',65:'probe'})
    pen=TTGlyphPen(None);pts=(BASE-CENTRE)*SCALE
    assert np.all(pts==np.rint(pts)) and np.max(np.abs(pts))<32768
    q=list(map(tuple,pts));pen.moveTo(q[0]);pen.lineTo(q[1]);pen.qCurveTo(q[2],q[3]);pen.lineTo(q[4]);pen.closePath()
    glyphs={'.notdef':TTGlyphPen(None).glyph(),'space':TTGlyphPen(None).glyph(),'detail':pen.glyph()}
    p=TTGlyphPen(glyphs);p.addComponent('detail',(1/SCALE,0,0,1/SCALE,*CENTRE));glyphs['probe']=p.glyph(componentFlags=0);b.setupGlyf(glyphs)
    b.setupHorizontalMetrics({'.notdef':(700,0),'space':(700,0),'detail':(0,int(pts[:,0].min())),'probe':(700,100)})
    b.setupHorizontalHeader(ascent=800,descent=-200)
    b.setupNameTable({'familyName':'Swirl Joint DirectWrite Control','styleName':'Regular','uniqueFontIdentifier':'SwirlScaledGlyf-1','fullName':'Swirl Joint DirectWrite Control','psName':'SwirlScaledGlyf'})
    b.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=1000,usWinDescent=300);b.setupPost();b.setupMaxp()
    b.setupFvar([(tag,*bounds,tag)for tag,bounds in zip(TAGS,PROFILES)],[])
    avar=newTable('avar');avar.segments={t:{-1.:-1.,0.:0.,1.:1.}for t in TAGS};b.font['avar']=avar
    variations=[]
    for axes,values in TERMS.items():
        for signs in itertools.product((-1,1),repeat=len(axes)):
            supports={TAGS[a]:(-1,-1,0)if sign<0 else(0,1,1)for a,sign in zip(axes,signs)}
            delta=values*(SCALE*np.prod(signs));assert np.all(delta==np.rint(delta))
            variations.append(TupleVariation(supports,[tuple(map(int,v))for v in delta]+[(0,0)]*4))
    b.setupGvar({n:variations if n=='detail'else[]for n in order})
    b.font.recalcTimestamp=False;b.font['head'].created=b.font['head'].modified=3800000000
    return b.font


def run(a):
    out=a.output.resolve()
    if out.exists():raise ValueError('fresh_authored_control_output_required')
    out.mkdir(parents=True);font=build();font.save(out/'control.ttf');font=TTFont(out/'control.ttf');blob=(out/'control.ttf').read_bytes()
    points=np.r_[np.array(list(itertools.product((-1.,0.,1.),repeat=3))),np.random.default_rng(2026110871).uniform(-1,1,(256,3))]
    requests=[];expected=[]
    for i,p in enumerate(points):
        loc={tag:round((default+x*(default-lo if x<0 else hi-default))*16)/16 for tag,x,(lo,default,hi)in zip(TAGS,p,PROFILES)}
        q=np.array([(loc[t]-d)/(d-lo if loc[t]<d else hi-d)for t,(lo,d,hi)in zip(TAGS,PROFILES)])
        values=BASE.copy()
        for axes,coefs in TERMS.items():values+=np.prod(q[list(axes)])*coefs
        expected.append(geometry.operands(path(values)));requests.append(dict(id=str(i),text='A',coordinates=loc))
    report=dict(scope='authored_scaled_glyf_only',limit=1/32,font_bytes=len(blob),font_sha256=hashlib.sha256(blob).hexdigest(),
        physical_axes=list(TAGS),computed_axes=0,glyphs=4,GSUB=False,avar_version=1,component_scale=1/SCALE,gvar_tuples=len(font['gvar'].variations['detail']),
        source_glyphs_accepted=0,production_accepted=False,engines={},DirectWrite='NOT_RUN',Windows_11='NOT_RUN')
    def record(engine,index,gid,cmds,advance):
        v=compare(expected[index],cmds);r=report['engines'].setdefault(engine,dict(observations=0,failures=0,max_error=0.,selection_failures=0,advance_failures=0,empty_outlines=0))
        r['observations']+=1;r['failures']+=not v['passed'];r['max_error']=max(r['max_error'],v['error']or 0);r['selection_failures']+=gid!=3;r['advance_failures']+=abs(advance-700)>1/32;r['empty_outlines']+=not cmds
    h=hb.Font(hb.Face(blob));hb.ot_font_set_funcs(h);h.scale=(64000,64000)
    for i,r in enumerate(requests):
        h.set_variations(r['coordinates']);buf=hb.Buffer();buf.add_str('A');buf.guess_segment_properties();hb.shape(h,buf)
        record('HarfBuzz',i,buf.glyph_infos[0].codepoint,commands(h,buf.glyph_infos[0].codepoint),buf.glyph_positions[0].x_advance/64)
        gs=font.getGlyphSet(location=r['coordinates']);g=gs['probe'];pen=DecomposingRecordingPen(gs);g.draw(pen)
        drawn=[[op,*[float(v)for point in args for v in point]]for op,args in pen.value]
        record('fontTools',i,3,drawn,g.width)
    if a.coretext:
        manifest=dict(font_path=str(out/'control.ttf'),font_sha256=report['font_sha256'],axis_defaults={x.axisTag:x.defaultValue for x in font['fvar'].axes},
            table_hashes={t:hashlib.sha256(font.reader[t]).hexdigest()for t in ('glyf','loca','gvar','fvar','avar','cmap')},requests=requests)
        (out/'manifest.json').write_text(json.dumps(manifest));binary=out/'oracle'
        subprocess.run(['swiftc','-O',str(Path(__file__).with_name('coretext_joint_layout.swift')),'-o',str(binary)],check=True)
        result=subprocess.run([str(binary),str(out/'manifest.json')],capture_output=True,text=True);(out/'native.jsonl').write_text(result.stdout);(out/'native.stderr.log').write_text(result.stderr);result.check_returncode()
        rows=list(map(json.loads,result.stdout.splitlines()));assert rows[-1]['request_count']==len(requests) and rows[-1]['run_tables_verified']
        for i,row in enumerate(rows[:-1]):
            assert row['id']==str(i);g=row['glyphs'][0];record('CoreText',i,g['gid'],g['commands'],g['advance_width'])
    if a.binary:
        lines=[' '.join([str(i),'omitted']+[str(r['coordinates'][t])for t in TAGS])for i,r in enumerate(requests)]
        result=subprocess.run([str(a.binary.resolve()),str(out/'control.ttf')],input='\n'.join(lines)+'\n',capture_output=True,text=True)
        (out/'directwrite.jsonl').write_text(result.stdout);(out/'directwrite.stderr.log').write_text(result.stderr);result.check_returncode()
        rows=list(map(json.loads,result.stdout.splitlines()));assert rows[-1]['requests']==len(requests) and rows[-1]['actual_tables_verified']
        report['DirectWrite']='EXECUTED';report['native_metadata']=rows[0];report['axis_readback_failures']=0
        for i,row in enumerate(rows[1:-1]):
            assert row['id']==i;record('DirectWrite',i,row['gid'],row['commands'],row['advance']);report['axis_readback_failures']+=row['axis_readback_failures']
    report['sampled_control_passed']=all(not any(r[k]for k in ('failures','selection_failures','advance_failures','empty_outlines'))for r in report['engines'].values())and not report.get('axis_readback_failures',0)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--coretext',action='store_true');p.add_argument('--binary',type=Path)
    raise SystemExit(0 if run(p.parse_args())['sampled_control_passed']else 1)
