#!/usr/bin/env python3
"""Falsifiable raw-avar hypotheses measured against exact-source CoreText HVAR.

This does NOT repair avar or replace the production oracle's strict axis guard.
It compares alternative interpretations with native horizontal advances while
keeping all original records intact. Raw native metrics stay in memory; public
output contains aggregate errors, axis coordinates and candidate names only.
A matching HVAR interpretation alone does not certify HVF geometry or a font.
"""
from __future__ import annotations
import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile

import numpy as np

from fontTools.ttLib import TTCollection
from fontTools.varLib.varStore import VarStoreInstancer
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from audit_font import raw_avar
from compare_axis_construction import EXPECTED, GUARD

LIMIT=1/32

SWIFT=r'''
func metricCalibrationMain() throws {
    let url=URL(fileURLWithPath:CommandLine.arguments[1])
    let data=try Data(contentsOf:url,options:[.mappedIfSafe])
    guard sha256(data)=="SOURCE_HASH" else { throw OracleError.invalid("wrong_exact_source") }
    let states=try locateDescriptors(parseFaces(Bytes(data:data)),url:url)
    guard states.count==32,states.allSatisfy({$0.baseFont != nil}) else {
        throw OracleError.invalid("all_physical_faces_must_match_source")
    }
    let input=FileHandle.standardInput.readDataToEndOfFile()
    let requests=try JSONDecoder().decode([Request].self,from:input)
    guard requests.count<=20000 else { throw OracleError.invalid("excessive_request_count") }
    try emit(["type":"metadata","source_sha256":sha256(data),"physical_faces":states.count,
              "backend":"CoreText","purpose":"diagnostic_not_production_oracle"])
    for request in requests {
        try autoreleasepool {
            guard request.face_index>=0,request.face_index<states.count else {
                throw OracleError.invalid("invalid_face_index")
            }
            let state=states[request.face_index]
            let (font,location,reported)=try metricObservationInstance(state,request.location)
            var advances:[Double]=[]
            for gid in request.glyph_ids {
                guard gid>=0,gid<Int(state.raw.glyphCount) else { throw OracleError.invalid("invalid_gid") }
                var glyph=CGGlyph(gid),value=CGSize.zero
                _=CTFontGetAdvancesForGlyphs(font,.horizontal,&glyph,&value,1)
                guard value.width.isFinite else { throw OracleError.invalid("nonfinite_native_advance") }
                advances.append(Double(value.width))
            }
            try emit(["request_id":request.request_id,"face_index":request.face_index,
                      "location":location,"reported":reported,"advances":advances])
        }
    }
}
try metricCalibrationMain()
'''


def harness(text):
    if text.count('\nfunc run() throws {')!=1 or text.count(GUARD)!=1:
        raise ValueError('review changed source helper before reuse')
    prefix=text.split('\nfunc run() throws {')[0]
    prefix=prefix.replace(GUARD,'        _ = effective // Diagnostic observation only, not production acceptance.')
    prefix=prefix.replace('func makeInstance(','func metricObservationInstance(',1)
    return prefix+SWIFT.replace('SOURCE_HASH',EXPECTED)


def normalize(value, minimum, default, maximum):
    if value==default: return 0.
    return (value-default)/(default-minimum if value<default else maximum-default)


def ordered_intervals(records, value):
    # Deliberate hypothesis about native iteration, not a sanitization policy.
    if value<records[0][0]: return records[0][1]
    for (a,b),(c,d) in zip(records,records[1:]):
        if value<=c:
            return d if a==c else b+(value-a)*(d-b)/(c-a)
    return records[-1][1]


def candidate_map(records, value, policy, special_zero):
    if special_zero and value==0: return 0.
    if policy=='identity': return value
    if policy=='ordered_intervals': return ordered_intervals(records,value)
    pairs={}
    for x,y in records:
        if policy=='first_sorted': pairs.setdefault(x,y)
        elif policy=='last_sorted': pairs[x]=y
        elif policy=='nonidentity_anchor_sorted':
            if x==y and any(p==x and q!=y for p,q in records): continue
            pairs[x]=y
        else: raise ValueError('unknown_mapping_hypothesis')
    ordered=sorted(pairs.items())
    if value<=ordered[0][0]: return ordered[0][1]
    return ordered_intervals(ordered,value)


def infer_weight_from_metrics(measured, negative, neutral, positive):
    """Invert two affine metric branches, independently of any avar hypothesis.

    Values are four-dimensional advance vectors at a fixed width location.
    A returned coordinate is diagnostic, not geometry or continuous-space proof.
    Flat/uninformative branches remain intervals instead of invented coordinates.
    """
    arrays = [np.asarray(v, dtype=np.float64) for v in (measured, negative, neutral, positive)]
    if any(a.shape != (4,) or not np.isfinite(a).all() for a in arrays):
        raise ValueError('four_finite_metric_observations_required')
    actual, low, base, high = arrays
    candidates = []
    for sign, endpoint in ((-1, low), (1, high)):
        slope = endpoint - base
        norm = float(np.dot(slope, slope))
        if norm == 0:
            value = None; interval = [-1., 0.] if sign < 0 else [0., 1.]
            predicted = base
        else:
            factor = float(np.clip(np.dot(actual - base, slope) / norm, 0., 1.))
            value = sign * factor; interval = [value, value]
            predicted = base + factor * slope
        error = float(np.max(np.abs(actual - predicted)))
        candidates.append({'normalized_weight': value, 'possible_interval': interval,
                           'max_metric_residual': error})
    candidates.sort(key=lambda c: c['max_metric_residual'])
    accepted = [c for c in candidates if c['max_metric_residual'] <= LIMIT]
    return {'best_fit': candidates[0], 'consistent_branches': accepted,
            'within_unchanged_metric_budget': bool(accepted),
            'geometry_mapping_accepted': False}


def infer_source_weight_locations(font, selected):
    """No outline/advance data is published, only inferred axis coordinates."""
    axes = {a.axisTag: a for a in font['fvar'].axes}
    order = font.getGlyphOrder(); table = font['HVAR'].table
    weight_index = list(axes).index('wght')
    for region in table.VarStore.VarRegionList.Region:
        a = region.VarRegionAxis[weight_index]
        triple = (a.StartCoord, a.PeakCoord, a.EndCoord)
        if triple not in ((-1., -1., 0.), (0., 0., 0.), (0., 1., 1.)):
            raise ValueError('HVAR_weight_is_not_two_affine_branches')
    cache = {}; result = []
    for request, observed in selected:
        loc = request['location']; width = axes['WDTH']
        x = normalize(loc['WDTH'], width.minValue, width.defaultValue, width.maxValue)
        key = (x, tuple(request['glyph_ids']))
        if key not in cache:
            vectors = []
            for w in (-1., 0., 1.):
                inst = VarStoreInstancer(table.VarStore, font['fvar'].axes,
                                        {'WDTH': x, 'wght': w, 'HGHT': 0.})
                vector = []
                for gid in request['glyph_ids']:
                    name = order[gid]
                    index = table.AdvWidthMap.mapping[name] if table.AdvWidthMap else gid
                    vector.append(font['hmtx'].metrics[name][0] + inst[index])
                vectors.append(vector)
            cache[key] = vectors
        inference = infer_weight_from_metrics(observed['advances'], *cache[key])
        result.append({'user_location': loc, **inference})
    return result


def requests_for(fonts):
    requests=[]
    for face,font in enumerate(fonts):
        axes={a.axisTag:a for a in font['fvar'].axes}
        tags=list(axes)
        record=raw_avar(font.reader['avar'],tags)
        weight=axes['wght']
        points={weight.minValue,weight.defaultValue,weight.maxValue,500.,499.,501.}
        for axis in record['axes']:
            if axis['tag']!='wght': continue
            for item in axis['records']:
                x=item['from_f2dot14']/16384
                value=weight.defaultValue+x*(weight.defaultValue-weight.minValue if x<0 else weight.maxValue-weight.defaultValue)
                points.update(value+eps for eps in (-.01,0.,.01))
        values=sorted(v for v in points if weight.minValue<=v<=weight.maxValue)
        values += [random.Random(715+face+n).uniform(weight.minValue,weight.maxValue) for n in range(4)]
        width=axes['WDTH']
        for w in values:
            for x in (width.minValue,width.defaultValue,width.maxValue):
                location={a.axisTag:a.defaultValue for a in axes.values()}
                location.update(wght=w,WDTH=x)
                requests.append({'request_id':str(len(requests)),'face_index':face,
                                 'location':location,'glyph_ids':[5,12,56,169]})
    return requests


def run(source, output):
    if output.exists() or output.resolve()==source.resolve(): raise ValueError('new_report_path_required')
    if hashlib.sha256(source.read_bytes()).hexdigest()!=EXPECTED: raise ValueError('exact_source_required')
    code=Path(__file__).with_name('coretext_extract.swift').read_text(encoding='utf-8')
    with TTCollection(source,lazy=True) as fonts:
        requests=requests_for(fonts.fonts)
        with tempfile.TemporaryDirectory(prefix='swirl-avar-metrics-') as directory:
            root=Path(directory); swift=root/'metrics.swift'; binary=root/'metrics'
            swift.write_text(harness(code),encoding='utf-8')
            compiled=subprocess.run(['xcrun','swiftc','-O',str(swift),'-o',str(binary)],capture_output=True,text=True,timeout=180)
            if compiled.returncode: raise RuntimeError(compiled.stderr[-5000:])
            native=subprocess.run([str(binary),str(source)],input=json.dumps(requests),capture_output=True,text=True,timeout=600)
            if native.returncode: raise RuntimeError(native.stderr[-3000:])
            lines=native.stdout.splitlines(); metadata=json.loads(lines[0]); rows=[json.loads(x) for x in lines[1:]]
            if metadata['source_sha256']!=EXPECTED or metadata['backend']!='CoreText' or metadata['physical_faces']!=32:
                raise ValueError('native_source_identity_changed')
            if len(rows)!=len(requests): raise ValueError('native_response_count_mismatch')
            for request,row in zip(requests,rows):
                if any(request[k]!=row[k] for k in ('request_id','face_index','location')) or len(row['advances'])!=4:
                    raise ValueError('native_response_identity_changed')
        reports=[]
        policies=('identity','ordered_intervals','first_sorted','last_sorted','nonidentity_anchor_sorted')
        for face,font in enumerate(fonts.fonts):
            axes={a.axisTag:a for a in font['fvar'].axes}; tags=list(axes)
            raw=raw_avar(font.reader['avar'],tags)
            weights=next(a for a in raw['axes'] if a['tag']=='wght')
            records=[(p['from_f2dot14']/16384,p['to_f2dot14']/16384) for p in weights['records']]
            order=font.getGlyphOrder(); table=font['HVAR'].table
            selected=[(q,r) for q,r in zip(requests,rows) if q['face_index']==face]
            alternatives=[]
            for center_policy in ('fvar_default','numeric_500'):
                for policy in policies:
                    for special_zero in (False,True):
                        for default_fastpath in (False,True):
                            stats={'normalization':center_policy,'record_policy':policy,
                                'zero_normalized_maps_to_zero':special_zero,'all_default_uses_base_metrics':default_fastpath,
                                'checks':0,'failures':0,'max_error_font_units':0.,'failure_examples':[]}
                            for request,row in selected:
                                location=request['location']; normalized={}
                                all_default=all(location[tag]==axis.defaultValue for tag,axis in axes.items())
                                for tag,axis in axes.items():
                                    center=500. if tag=='wght' and center_policy=='numeric_500' else axis.defaultValue
                                    normalized[tag]=normalize(location[tag],axis.minValue,center,axis.maxValue)
                                normalized['wght']=candidate_map(records,normalized['wght'],policy,special_zero)
                                if not all(math.isfinite(x) and -1<=x<=1 for x in normalized.values()):
                                    raise ValueError('mapping_hypothesis_left_design_space')
                                variations=VarStoreInstancer(table.VarStore,font['fvar'].axes,normalized)
                                for gid,actual in zip(request['glyph_ids'],row['advances']):
                                    name=order[gid]; idx=table.AdvWidthMap.mapping[name] if table.AdvWidthMap else gid
                                    value=font['hmtx'].metrics[name][0]
                                    if not(default_fastpath and all_default): value+=variations[idx]
                                    error=abs(float(actual)-value)
                                    stats['checks']+=1; stats['max_error_font_units']=max(stats['max_error_font_units'],error)
                                    if error>LIMIT:
                                        stats['failures']+=1
                                        if len(stats['failure_examples'])<2:
                                            stats['failure_examples'].append({'location':location,'glyph_id':gid,'absolute_error':error})
                            alternatives.append(stats)
            alternatives.sort(key=lambda x:(x['failures'],x['max_error_font_units']))
            reports.append({'face_index':face,'native_positions':len(selected),
                            'matching_interpretations':[x for x in alternatives if x['failures']==0],
                            'best_failing_interpretations':[x for x in alternatives if x['failures']][:3],
                            'total_hypotheses':len(alternatives),
                            'metric_inferred_locations':infer_source_weight_locations(font, selected)})
            print(json.dumps({'face_index':face,'best':alternatives[0],'matching_hypotheses':sum(x['failures']==0 for x in alternatives)}),flush=True)
        report={'status':'NATIVE_HVAR_MAPPING_DIAGNOSIS_NOT_FONT_ACCEPTANCE',
                'source_sha256':EXPECTED,'source_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==EXPECTED,
                'original_records_modified':False,'production_axis_guard_changed':False,
                'native_requests':len(requests),'physical_faces':32,'metric_tolerance':LIMIT,
                'font_generated':False,'reports':reports}
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open('x',encoding='utf-8') as stream: json.dump(report,stream,indent=2,allow_nan=False)
        return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.source,args.output)
