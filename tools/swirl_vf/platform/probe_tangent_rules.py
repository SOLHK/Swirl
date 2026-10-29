#!/usr/bin/env python3
"""Observe Apple HVF tangent construction on self-authored geometric fixtures.

No Apple font, glyph or private outline is read. Input records and native paths
may be logged because every fixture is constructed here from simple numbers.
This is a diagnostic, not source-font acceptance and not a replacement for the
unchanged strict regression tests. Each native call runs in a fresh process.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

import numpy as np
from fontTools.ttLib import TTFont, newTable
from make_synthetic_hvf import create


def cases():
    # On-curve XY (or type-0 parallel factor) followed by outgoing control XY.
    base = np.array([[0,0,50,0], [100,0,150,0], [.5,0,180,80],
                     [180,160,180,230], [180,300,60,300], [0,300,0,150]], float)
    types = [1,1,0,2,1,1]
    result = []
    changes = [('baseline', []), ('incoming_x', [(2,2,40)]),
               ('incoming_y', [(2,3,40)]), ('tangent_x', [(3,0,40)]),
               ('tangent_y', [(3,1,40)]), ('outgoing_x', [(3,2,40)]),
               ('outgoing_y', [(3,3,40)]), ('next_on_x', [(4,0,40)]),
               ('next_on_y', [(4,1,40)]), ('mixed', [(2,2,31),(3,0,-17),(4,0,23)])]
    for name, adjustments in changes:
        data = base.copy()
        for row,column,delta in adjustments: data[row,column] += delta
        result.append((name, types, data))
        result.append((name+'_corner_control', [1,1,0,1,1,1], data.copy()))
    # Test the opposite tangent orientation, with the curve after the tangent.
    opposite = np.array([[0,0,90,0],[180,0,180,70],[180,140,180,220],
                         [.5,0,100,300],[0,300,0,150]],float)
    for dx in (0,40):
        data=opposite.copy();data[2,2]+=dx
        result.append((f'opposite_outgoing_{dx}',[1,1,2,0,1],data))
    return result


def encode_shape(types, data):
    if len(types)!=len(data) or data.shape!=(len(types),4): raise ValueError('bad shape dimensions')
    if not np.isfinite(data).all() or any(t not in range(5) for t in types): raise ValueError('bad shape data')
    shape=struct.pack('<5H',0,3,1,len(types),len(types))+bytes(types)
    shape+=bytes((-len(shape))%8)
    shape+=np.asarray(data,dtype='<f8').tobytes()
    shape+=bytes(2*3*len(types)*4*8) # independent axes, zero deltas for this diagnosis
    return struct.pack('<HHIIIII',3,1,0,1,24,1,0)+struct.pack('<II',8,8+len(shape))+shape


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists(): raise ValueError('output already exists')
    observations=[]
    with tempfile.TemporaryDirectory(prefix='swirl-tangent-original-') as d:
        fixture=Path(d)/'synthetic.ttf';create(fixture)
        for name,types,data in cases():
            with TTFont(fixture,recalcBBoxes=False,recalcTimestamp=False) as f:
                table=newTable('hvgl');table.data=encode_shape(types,data);f['hvgl']=table
                pending=Path(d)/'pending.ttf';f.save(pending)
            pending.replace(fixture)
            r=subprocess.run([str(args.binary.resolve()),str(fixture),'0','0,0,0','0','1'],
                             capture_output=True,text=True,timeout=30)
            if r.returncode: raise RuntimeError('synthetic oracle failure: '+r.stderr[:400])
            rows=[json.loads(line) for line in r.stdout.splitlines() if line]
            outlines=[row for row in rows if row.get('record')=='outline']
            if len(outlines)!=1 or outlines[0]['status']!='OK': raise RuntimeError('native outline missing')
            observation={'case':name,'blends':types,'master':data.tolist(),
                         'native_events':outlines[0]['events']}
            observations.append(observation)
            print('SYNTHETIC_TANGENT '+json.dumps(observation,allow_nan=False),flush=True)
    report={'status':'DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE',
            'data_origin':'self_authored_geometry_no_Apple_font_data',
            'original_font_acceptance':'NOT_RUN','observations':observations}
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')

if __name__=='__main__': main()
