#!/usr/bin/env python3
"""Calibrate portable hierarchy/Type-2 interpretation against native libhvf.

This deliberately operates in normalized DESIGN coordinates, not source user
coordinates. No avar inference or original-font acceptance is claimed. Native
outlines remain process-private and are discarded; only maximum discrepancies,
counts and offending GIDs are written. Type-2-as-explicit is a falsifiable
hypothesis, not an implementation marked production-ready in advance.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
from functools import lru_cache
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile

import numpy as np
from fontTools.ttLib import TTCollection
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from hvf import HVGL, Shape, ExperimentalRenderer

EXPECTED='39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'
LIMIT=1/32

class ExplicitTangentHypothesis:
    def __init__(self, table): self.table=table
    @lru_cache(maxsize=None)
    def part(self, index):
        part=self.table.part(index)
        if isinstance(part,Shape) and 2 in part.blends:
            return replace(part,blends=tuple(1 if kind==2 else kind for kind in part.blends))
        return part


def linear(p,q,r):
    direction=r-p; length=float(np.dot(direction,direction))
    if length<1e-20: return bool(np.linalg.norm(q-p)<1e-10)
    t=float(np.dot(q-p,direction)/length)
    return -1e-10<=t<=1+1e-10 and np.linalg.norm(q-(p+t*direction))<1e-8


def segment(p,q,r):
    p,q,r=(np.asarray(x,dtype=float) for x in (p,q,r))
    if not all(np.isfinite(v).all() for v in (p,q,r)): raise ValueError('nonfinite_geometry')
    if linear(p,q,r): return ('L', np.concatenate((p,r)))
    return ('Q',np.concatenate((p,q,r)))


def portable_paths(paths):
    result=[]
    for points in paths:
        if len(points)%2: raise ValueError('odd_portable_point_count')
        pairs=np.asarray(points).reshape(-1,2,2)
        result.append([segment(pair[0],pair[1],pairs[(i+1)%len(pairs),0]) for i,pair in enumerate(pairs)])
    return result


def native_paths(events):
    paths=[]; current=None; start=None; parts=[]
    for item in events:
        kind=item[0]
        if kind=='begin_path':
            if current is not None: raise ValueError('nested_native_path')
            current=[]; start=None; previous=None
        elif kind=='move':
            if current is None: raise ValueError('native_move_outside_path')
            if start is not None: raise ValueError('multiple_moves_per_native_path')
            start=np.asarray(item[1:],float); previous=start
        elif kind in ('line','quad'):
            if current is None or start is None: raise ValueError('native_segment_without_move')
            point=np.asarray(item[-2:],float)
            control=(previous+point)/2 if kind=='line' else np.asarray(item[1:3],float)
            current.append(segment(previous,control,point)); previous=point
        elif kind=='cubic': raise ValueError('native_cubic_needs_separate_correspondence')
        elif kind=='close':
            if start is not None and np.linalg.norm(previous-start)>1e-10:
                current.append(segment(previous,(previous+start)/2,start)); previous=start
        elif kind=='end_path':
            if current is None: raise ValueError('native_path_end_without_begin')
            if current and np.linalg.norm(previous-start)>1e-8: raise ValueError('native_path_not_closed')
            if current: paths.append(current)
            current=None; start=None
    if current is not None: raise ValueError('native_unclosed_event_stream')
    return paths


def _scalar_cycle_minimum(left, right):
    """Retain legacy behavior outside the canonical float64 fast path."""
    candidates=[]
    for shift in range(len(left)):
        errors=[]
        for i,(kind,values) in enumerate(left):
            other,points=right[(i+shift)%len(right)]
            if kind!=other: break
            errors.append(float(np.abs(values-points).max()))
        else: candidates.append(max(errors,default=0.))
    if not candidates: raise ValueError('segment_types_differ')
    return min(candidates)


def _small_cycle_minimum(left, right):
    """Avoid array setup for short contours, with the same proven bound."""
    best=math.inf; matched=False
    for shift in range(len(left)):
        error=0.
        for i,(kind,values) in enumerate(left):
            other,points=right[(i+shift)%len(right)]
            if kind!=other: break
            point_error=float(np.abs(values-points).max())
            if not math.isfinite(point_error):
                return _scalar_cycle_minimum(left,right)
            error=max(error,point_error)
            if matched and error>=best: break
        else:
            best=min(best,error); matched=True
            if best==0.: return best
    if not matched: raise ValueError('segment_types_differ')
    return best


def discrepancy(wanted, actual):
    if len(wanted)!=len(actual): raise ValueError('path_count_differs')
    max_error=0.; tested=0
    for left,right in zip(wanted,actual):
        if len(left)!=len(right): raise ValueError('segment_count_differs')
        if not left: continue
        count=len(left)
        if not all(kind in ('L','Q') and isinstance(values,np.ndarray)
                   and values.dtype==np.dtype('float64')
                   and values.shape==(4 if kind=='L' else 6,)
                   for kind,values in left+right):
            max_error=max(max_error,_scalar_cycle_minimum(left,right)); tested+=count
            continue
        if count<=16:
            max_error=max(max_error,_small_cycle_minimum(left,right)); tested+=count
            continue
        left_kinds=np.asarray([kind for kind,_ in left])
        right_kinds=np.asarray([kind for kind,_ in right])
        # Canonical segments are lines (four values) or quadratics (six).
        # Zero padding has no effect on a same-kind absolute-error maximum.
        # Reject mismatched kinds exactly as before; no resampling, segment
        # merging or change to the control-point error metric is introduced.
        lhs=np.zeros((count,6)); rhs=np.zeros((count,6))
        for i,((kind,values),(other,points)) in enumerate(zip(left,right)):
            lhs[i,:len(values)]=values; rhs[i,:len(points)]=points
        if not np.isfinite(lhs).all() or not np.isfinite(rhs).all():
            max_error=max(max_error,_scalar_cycle_minimum(left,right)); tested+=count
            continue
        shifts=np.flatnonzero(right_kinds==left_kinds[0])
        lower_bounds=np.max(np.abs(rhs[shifts]-lhs[0]),axis=1)
        # The first segment's error is a lower bound on that shift's full
        # maximum. Visit the most promising shifts first, then discard only
        # candidates that mathematically cannot improve the current minimum.
        indices=np.arange(count); best=math.inf; matched=False
        for candidate in np.argsort(lower_bounds,kind='stable'):
            lower=float(lower_bounds[candidate])
            if matched and lower>=best: continue
            shifted=(indices+int(shifts[candidate]))%count
            if not np.array_equal(left_kinds,right_kinds[shifted]): continue
            error=float(np.abs(lhs-rhs[shifted]).max())
            best=min(best,error); matched=True
            if best==0.: break
        if not matched: raise ValueError('segment_types_differ')
        max_error=max(max_error,best);tested+=count
    return max_error,tested


def select_glyphs(table):
    @lru_cache(maxsize=None)
    def leaves(index):
        part=table.part(index)
        if isinstance(part,Shape): return frozenset([index] if 2 in part.blends else [])
        return frozenset().union(*(leaves(child) for child,_,_ in part.subparts))
    all_type2={i for i in range(table.part_count) if isinstance(table.part(i),Shape) and 2 in table.part(i).blends}
    covered=set(); selected=set(range(8))
    for gid in range(table.glyph_count):
        fresh=set(leaves(gid))-covered
        if fresh: selected.add(gid); covered.update(fresh)
        if covered==all_type2: break
    if covered!=all_type2: raise ValueError('unreachable_type2_shape_not_covered')
    # Separately cover deep hierarchy and rotation-bearing roots.
    @lru_cache(maxsize=None)
    def structure(index):
        part=table.part(index)
        if isinstance(part,Shape): return 1,False
        children=[structure(child) for child,_,_ in part.subparts]
        rotated=bool(np.any(part.rotations.extreme_values)) or any(x[1] for x in children)
        return 1+max((x[0] for x in children),default=0),rotated
    depths=[structure(i)[0] for i in range(table.glyph_count)]
    selected.add(max(range(table.glyph_count),key=lambda i:depths[i]))
    rotated=[i for i in range(table.glyph_count) if structure(i)[1]]
    selected.update(rotated[:2])
    selected.update(random.Random(20261019).sample(range(table.glyph_count),8))
    return sorted(selected),{'type2_shapes_covered':len(covered),'type2_shapes_present':len(all_type2),
                            'maximum_tree_depth_tested':max(depths[i] for i in selected),
                            'selected_rotation_roots':sum(structure(i)[1] for i in selected)}


def run(source, output):
    if output.exists() or output.resolve()==source.resolve(): raise ValueError('report_path_not_new')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=EXPECTED: raise ValueError('exact_source_required')
    with TTCollection(source,lazy=True) as fonts:
        table=HVGL(fonts.fonts[0].reader['hvgl'])
        selected,coverage=select_glyphs(table)
        renderer=ExperimentalRenderer(ExplicitTangentHypothesis(table))
        positions=list(itertools.product((-1.,0.,1.),repeat=3))
        rng=random.Random(74321)
        positions += [tuple(rng.uniform(-.98,.98) for _ in range(3)) for _ in range(7)]
        report={'status':'NOT_RUN','source_sha256':EXPECTED,'scope':'design_space_only_no_avar_or_metric_acceptance',
                'type2_interpretation':'explicit_on_curve_hypothesis','outline_limit_font_units':LIMIT,
                'selected_glyphs':selected,'coverage':coverage,'positions':len(positions),
                'glyph_instances':0,'passed':0,'failures':0,'max_point_error':0.,
                'native_error_counts':{},'failure_examples':[],'source_outlines_published':False,
                'final_font_generated':False}
        with tempfile.TemporaryDirectory(prefix='swirl-hvf-calibration-') as directory:
            binary=Path(directory)/'hvf_oracle'
            compiled=subprocess.run(['xcrun','clang','-std=c11','-O2','-Wall','-Wextra','-Werror',
                '-mmacosx-version-min=15.4',str(Path(__file__).with_name('hvf_oracle.c')),'-lhvf','-o',str(binary)],
                capture_output=True,text=True,timeout=180)
            if compiled.returncode: raise RuntimeError(compiled.stderr[-4000:])
            for position in positions:
                for gid in selected:
                    report['glyph_instances']+=1
                    try:
                        native=subprocess.run([str(binary),str(source),'0',','.join(map(str,position)),str(gid),'1'],
                                              capture_output=True,text=True,timeout=30)
                        if native.returncode: raise ValueError('native_process_failed')
                        rows=[json.loads(x) for x in native.stdout.splitlines()]
                        records=[x for x in rows if x.get('record')=='outline']
                        if len(records)!=1 or records[0]['part_index']!=gid or records[0]['status']!='OK':
                            raise ValueError('native_identity_or_render_failure')
                        expected=portable_paths(renderer.render(gid,position[:table.part(gid).axis_count]))
                        actual=native_paths(records[0]['events'])
                        error,segments=discrepancy(expected,actual)
                        report['max_point_error']=max(report['max_point_error'],error)
                        if error>LIMIT:
                            raise ValueError('control_point_error_budget_exceeded')
                        report['passed']+=1
                    except (ValueError,RuntimeError) as failure:
                        code=str(failure)
                        report['failures']+=1
                        counts=report['native_error_counts'];counts[code]=counts.get(code,0)+1
                        if len(report['failure_examples'])<8:
                            report['failure_examples'].append({'glyph_id':gid,'design_location':position,'reason':code})
                print(json.dumps({'completed_design_locations':positions.index(position)+1,
                      'passed':report['passed'],'failures':report['failures']}),flush=True)
        report['source_unchanged']=hashlib.sha256(source.read_bytes()).hexdigest()==EXPECTED
        report['status']='SAMPLED_DESIGN_GEOMETRY_PASS_NOT_FONT_ACCEPTANCE' if not report['failures'] else 'GEOMETRY_CALIBRATION_FAILED'
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x',encoding='utf-8') as stream: json.dump(report,stream,indent=2,allow_nan=False)
        print(json.dumps(report,allow_nan=False),flush=True)
        return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.source,args.output)
