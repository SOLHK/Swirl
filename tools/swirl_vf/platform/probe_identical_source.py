#!/usr/bin/env python3
"""Private in-runner source probe; publish counts/errors, never outlines/fonts.

This diagnostic requires an exact source digest. It does not replace either
native synthetic acceptance or full all-glyph reconstruction. Raw native
records live in process memory; temporary native stderr is deleted on exit.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import platform
import sys
import tempfile
import time

from fontTools.ttLib import TTCollection
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rebuild import (NativeOracle, sha256, normalized_grid, heldout_locations,
                     user_location, reconstruct_glyph, compatible_coordinates, with_phantoms)

EXPECTED = '39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'


def run(source, binary, output):
    if sha256(source) != EXPECTED:
        raise ValueError('No exact source match: do not substitute a different system font')
    if output.exists() or output.resolve() in (source.resolve(), binary.resolve()):
        raise ValueError('Report must be new and separate from input/executable')
    report = {'status':'DIAGNOSTIC_RUNNING_NOT_ACCEPTANCE', 'source_sha256':EXPECTED,
              'platform':platform.platform(), 'source_font_transferred':False,
              'original_outlines_published':False, 'candidate_font_generated':False,
              'original_full_glyph_acceptance':'NOT_RUN', 'windows_acceptance':'NOT_RUN',
              'outline_limit_font_units':1.0, 'metric_limit_font_units':1.0,
              'faces':[], 'errors':[]}
    started = time.monotonic()
    output.parent.mkdir(parents=True, exist_ok=True)
    code = 1
    try:
        with tempfile.TemporaryDirectory(prefix='swirl-private-source-probe-') as tmp:
            oracle = NativeOracle(binary, source, Path(tmp) / 'native.log')
            try:
                report['verified_faces'] = len(oracle.metadata['faces'])
                with TTCollection(source, lazy=True) as fonts:
                    for index, font in enumerate(fonts.fonts):
                        axes = {a.axisTag:(a.minValue,a.defaultValue,a.maxValue) for a in font['fvar'].axes}
                        training = normalized_grid(list(axes))
                        heldout = heldout_locations(list(axes), seed=20261019+index)
                        cmap = font.getBestCmap()
                        gids = sorted({0,1,2} | {font.getGlyphID(cmap[ord(c)]) for c in ' A0g中国國港高' if ord(c) in cmap})
                        record = {'face_index':index, 'glyph_ids':gids,
                                  'training_locations':len(training), 'independent_holdouts':len(heldout),
                                  'native_glyph_records':0, 'metric_rejections':{},
                                  'path_status_counts':{}, 'max_vertical_x_halfwidth_deviation':0.,
                                  'largest_origin_deviation':None, 'metric_rejection_examples':[],
                                  'reconstruction_pass_glyphs':0, 'reconstruction_failures':[],
                                  'complete_font_acceptance':False}
                        report['faces'].append(record)
                        samples = []
                        metric_errors, statuses = Counter(), Counter()
                        for point in training + heldout:
                            values = oracle.samples(index,gids,user_location(point,axes))
                            samples.append(values)
                            for gid, row in values.items():
                                record['native_glyph_records'] += 1
                                statuses[row['path_status']] += 1
                                deviation = abs(row['vertical_origin_x']-row['horizontal_origin_x']-row['advance_width']/2)
                                if deviation > record['max_vertical_x_halfwidth_deviation']:
                                    record['max_vertical_x_halfwidth_deviation'] = deviation
                                    record['largest_origin_deviation'] = {
                                        'glyph_id':gid, 'location':row['location'],
                                        'path_status':row['path_status'],
                                        'advance_width':row['advance_width'],
                                        'vertical_origin_x':row['vertical_origin_x'],
                                        'horizontal_origin_x':row['horizontal_origin_x']}
                                record['path_status_counts'] = dict(statuses)
                                try:
                                    coords,_,_,_ = compatible_coordinates([row])
                                    with_phantoms(coords[0],row,None,None)
                                except Exception as error:
                                    metric_errors[str(error)] += 1
                                    record['metric_rejections'] = dict(metric_errors)
                                    if len(record['metric_rejection_examples']) < 8:
                                        record['metric_rejection_examples'].append({
                                            'glyph_id':gid, 'location':row['location'],
                                            'path_status':row['path_status'],
                                            'advance_width':row['advance_width'],
                                            'advance_height':row['advance_height'],
                                            'vertical_origin_x':row['vertical_origin_x'],
                                            'vertical_origin_y':row['vertical_origin_y'],
                                            'reason':str(error)})
                        record['metric_rejections'] = dict(metric_errors)
                        record['path_status_counts'] = dict(statuses)
                        for gid in gids:
                            rows = [values[gid] for values in samples]
                            try:
                                _,_,_,_,evidence = reconstruct_glyph(rows[:len(training)],rows[len(training):],
                                    training,heldout,axes,None,None)
                                if not evidence['failures']:
                                    record['reconstruction_pass_glyphs'] += 1
                                else:
                                    record['reconstruction_failures'].append({'glyph_id':gid,
                                        'reason':'INITIAL_GRID_ERROR_EXCEEDS_UNCHANGED_BUDGET',
                                        'max_outline_error_bound':evidence['max_outline_error_bound_units'],
                                        'max_metric_error':evidence['max_metric_error_units'],
                                        'failing_samples':len(evidence['failures'])})
                            except Exception as error:
                                record['reconstruction_failures'].append({'glyph_id':gid,
                                    'reason':str(error), 'type':type(error).__name__})
                        # This progress line deliberately includes no glyph coordinates.
                        print(f'face={index} native_records={record["native_glyph_records"]} initial_model_passes={record["reconstruction_pass_glyphs"]}', flush=True)
                report['status'] = 'DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE'
                code = 0
            finally:
                oracle.close()
    except Exception as error:
        report['status'] = 'DIAGNOSTIC_ERROR'
        report['errors'].append({'type':type(error).__name__,'message':str(error)})
    finally:
        report['source_unchanged'] = sha256(source) == EXPECTED
        report['elapsed_seconds'] = time.monotonic()-started
        with output.open('x',encoding='utf-8') as stream:
            json.dump(report,stream,indent=2,allow_nan=False)
        print(json.dumps(report,allow_nan=False),flush=True)
    return code


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--binary',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args = parser.parse_args()
    raise SystemExit(run(args.source,args.binary,args.output))
