#!/usr/bin/env python3
"""Authored oblique-axis avar2 / hierarchical VARC representation controls.

Reuses the existing three-axis CFF2 and native protocol fixtures. No source
font is accepted as input. A passing control does not accept an HVF glyph.
VARC/avar2 proposal semantics:
https://github.com/harfbuzz/boring-expansion-spec/blob/main/avar2.md
https://github.com/harfbuzz/boring-expansion-spec/blob/main/VARC.md
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTCollection,newTable
from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import buildVarRegionList,buildVarData,buildVarStore,buildDeltaSetIndexMap
from fontTools.varLib.multiVarStore import OnlineMultiVarStoreBuilder

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import cff2_geometry as geometry
from rebuild import NativeOracle
from verified_axis_oracle import make_launcher
from make_cff2_fixture import convert,records,TAGS
from test_coretext_extract import make_fixture
from p7_validate_candidate import commands as hb_commands

PROFILES=((1,500,1000),(100,400,900),(1,500,1000))


def controls(source):
    geometry.require(source['name'].getDebugName(1)=='Swirl Native Oracle Fixture 0'
        and source['maxp'].numGlyphs==3 and source['head'].unitsPerEm==1000
        and tuple(a.axisTag for a in source['fvar'].axes)==TAGS,
        'authored_three_glyph_control_required')
    base,_=convert(source,.25)
    warp=copy.deepcopy(base)
    avar=newTable('avar');avar.majorVersion=2;avar.minorVersion=0
    avar.segments={t:{-1.:-1.,0.:0.,1.:1.} for t in TAGS}
    avar.table=otTables.avar();avar.table.Reserved=0
    supports=[{'WDTH':(-1,-1,0)},{'WDTH':(0,1,1)},
              {'HGHT':(-1,-1,0)},{'HGHT':(0,1,1)}]
    avar.table.VarStore=buildVarStore(buildVarRegionList(supports,TAGS),
        [buildVarData(list(range(4)),[[0]*4,[-8192,8192,4096,-4096],[0]*4],optimize=False)])
    avar.table.VarIdxMap=buildDeltaSetIndexMap([0,1,2]);warp['avar']=avar

    hierarchy=copy.deepcopy(base)
    varc=newTable('VARC');v=varc.table=otTables.VARC();v.Version=0x10000
    v.Coverage=otTables.Coverage();v.Coverage.glyphs=[hierarchy.getGlyphOrder()[0]]
    v.ConditionList=None
    v.AxisIndicesList=otTables.AxisIndicesList();v.AxisIndicesList.Item=[(0,1,2)]
    builder=OnlineMultiVarStoreBuilder(TAGS)
    builder.setSupports([{t:triple} for t in TAGS for triple in ((-1,-1,0),(0,1,1))])
    comp=otTables.VarComponent();comp.glyphName=hierarchy.getGlyphOrder()[2]
    comp.axisIndicesIndex=0;comp.axisValues=(0.,0.,0.)
    # Copy every inherited coordinate explicitly. This also avoids the known
    # fontTools CFF2 pushLocation omission when only one axis is overridden.
    comp.axisValuesVarIndex=builder.storeDeltas([
        [-16384,-4096,0],[16384,4096,0],[0,-8192,0],[0,8192,0],
        [0,4096,-16384],[0,-4096,16384]],round=lambda value:value)
    comp.flags=int(otTables.VarComponentFlags.HAVE_TRANSLATE_X)
    comp.transform.translateX=100.
    v.MultiVarStore=builder.finish();v.VarCompositeGlyphs=otTables.VarCompositeGlyphs()
    v.VarCompositeGlyphs.VarCompositeGlyph=[otTables.VarCompositeGlyph([comp])]
    hierarchy['VARC']=varc
    return {'avar2':warp,'VARC':hierarchy}


def request_plan(seed=2026110309):
    points=np.r_[np.asarray([[0,0,0],[.5,0,0],[0,.5,0],[0,0,.5],
                            [.5,-.25,.5],[1,1,1],[-1,-1,-1]]),
                 np.random.default_rng(seed).uniform(-1,1,(64,3))]
    result=[]
    for p in points:
        # Fractional user positions exactly survive CoreText readback. These
        # normalized coordinates remain non-grid values (e.g. denominator 499).
        location={tag:round((default+x*(default-lo if x<0 else hi-default))*16)/16
                  for tag,x,(lo,default,hi) in zip(TAGS,p,PROFILES)}
        result.append(location)
    return result


def expected(source,kind,location):
    p=np.asarray([(location[tag]-d)/(d-lo if location[tag]<d else hi-d)
                  for tag,(lo,d,hi) in zip(TAGS,PROFILES)])
    if kind=='avar2':p[1]=np.clip(p[1]+.5*p[0]-.25*p[2],-1,1)
    elif kind=='VARC':p[1]=.25*p[0]+.5*p[1]-.25*p[2]
    else:raise ValueError('unknown_joint_representation_control')
    commands=records(source,source.getGlyphOrder()[2],[dict(zip(TAGS,p))],.25)[0]
    if kind=='VARC':
        for command in commands:
            for i in range(1,len(command),2):command[i]+=100
    return geometry.operands(implicit_closures(commands))


def implicit_closures(commands):
    """Canonicalize only an exact line to the start immediately before close.

    HarfBuzz emits this edge explicitly; CoreText and the source pen use the
    implicit close. No point is moved and no non-closing segment is discarded.
    """
    result=[];start=None
    for command in commands:
        command=[command[0],*map(float,command[1:])]
        if command[0]=='moveTo':start=command[1:]
        if command[0]=='closePath' and result and result[-1]==['lineTo',*(start or [])]:
            result.pop()
        result.append(command)
        if command[0]=='closePath':start=None
    return result


def compare(expected_outline,commands):
    ops,values=geometry.operands(implicit_closures(commands))
    if ops!=expected_outline[0]:return dict(passed=False,error=None,reason='topology_mismatch')
    error=float(np.linalg.norm(geometry.control_points(ops,values)-
                               geometry.control_points(*expected_outline),axis=1).max(initial=0))
    return dict(passed=error<=geometry.LIMIT,error=error)


def run(output):
    output=Path(output).resolve()
    geometry.require(not output.exists() and not output.is_relative_to(Path(__file__).resolve().parents[3]),
                     'fresh_external_diagnostic_output_required')
    geometry.require(platform.system()=='Darwin','joint_controls_require_CoreText')
    output.mkdir(parents=True,mode=0o700)
    binary=output/'coretext_extract'
    build=subprocess.run(['swiftc','-O',str(Path(__file__).with_name('coretext_extract.swift')),
                          '-o',str(binary)],capture_output=True,text=True,timeout=120)
    (output/'compile.log').write_text(build.stdout+build.stderr);build.check_returncode()
    launcher=output/'verified-axis-oracle';make_launcher(launcher,binary)
    template=output/'template.ttc';make_fixture(template)
    report=dict(scope='authored_joint_axis_representation_controls_only',
                production_accepted=False,source_glyphs_accepted=0,
                limit_source_font_units=geometry.LIMIT,os=platform.platform(),
                harfbuzz=hb.version_string(),cases={},
                binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    with TTCollection(template) as collection:
        source=collection.fonts[0]
        for kind,font in controls(source).items():
            path=output/f'{kind}.ttc';target=TTCollection();target.fonts=[font];target.save(path)
            blob=path.read_bytes();digest=hashlib.sha256(blob).hexdigest()
            native=NativeOracle(launcher,path,output/f'{kind}-stderr.log')
            hfont=hb.Font(hb.Face(blob));hb.ot_font_set_funcs(hfont);hfont.scale=(64000,64000)
            result=dict(font_sha256=digest,observations=0,engines={},font_bytes=len(blob))
            report['cases'][kind]=result
            gid=2 if kind=='avar2' else 0
            try:
                with TTCollection(path) as reopened, (output/f'{kind}-native.jsonl').open('x') as transcript:
                    for location in request_plan():
                        row=native.samples(0,[gid],location)[gid]
                        transcript.write(json.dumps(row)+'\n');result['observations']+=1
                        wanted=expected(source,kind,location);hfont.set_variations(location)
                        saved=reopened.fonts[0]
                        samples={'CoreText':row['commands'],'HarfBuzz':hb_commands(hfont,gid),
                            'fontTools':geometry.source_commands(saved.getGlyphSet(location=location)[saved.getGlyphOrder()[gid]])}
                        for engine,commands in samples.items():
                            verdict=compare(wanted,commands)
                            counts=result['engines'].setdefault(engine,dict(observations=0,failures=0,
                                                    topology_failures=0,max_comparable_error=None))
                            counts['observations']+=1;counts['failures']+=not verdict['passed']
                            if verdict['error'] is None:counts['topology_failures']+=1
                            else:counts['max_comparable_error']=max(counts['max_comparable_error'] or 0,verdict['error'])
                    result['terminal_receipt']=native.finish()
                    result['exact_axis_protocol']=native.metadata.get('axis_verification_backend')
            finally:native.close()
            (output/'report.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(dict(kind=kind,**result)),flush=True)
    report['passed']=all(e['failures']==0 for c in report['cases'].values() for e in c['engines'].values())
    (output/'report.json').write_text(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--private-output',required=True,type=Path)
    args=parser.parse_args();sys.exit(0 if run(args.private_output)['passed'] else 1)
