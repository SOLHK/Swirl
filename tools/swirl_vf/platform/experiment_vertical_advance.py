#!/usr/bin/env python3
"""Measure fractional vertical layout separately from integer raw metrics.

The eight independently authored symbols keep their outlines, GSUB, cmap and
horizontal/vertical metric tables byte-identical. Only GPOS/GDEF add a variable
YAdvance. This is an alternative-layout experiment, never original-font or
production acceptance. Unsupported feature routing and precision failures are
retained. Existing raw-metric gates are not changed.

https://learn.microsoft.com/en-us/typography/opentype/spec/gpos#value-record
https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from fontTools.otlLib.builder import buildSinglePosSubtable, buildValue
from fontTools.ttLib import TTFont
from fontTools.varLib.builder import buildVarDevTable, buildVarData, buildVarRegionList, buildVarStore

import experiment_vertical_gpos as fixture

POINTS = fixture.POINTS


def candidate(original, symbols, route):
    data, failures = fixture.add_adjustment(original, symbols, route)
    fixture.require(not failures, 'authored_advance_requires_exact_integer_coefficients')
    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
    supports, rows = fixture.supports_and_deltas(symbols)
    # GPOS defines positive YAdvance as an increase in advance height for
    # top-to-bottom text, unlike upward-positive YPlacement. Keep that sign;
    # the shaping engine converts it into its pen-position coordinate system.
    font['GDEF'].table.VarStore = buildVarStore(
        buildVarRegionList(supports, [a[0] for a in fixture.AXES]),
        [buildVarData(list(range(len(supports))), rows, optimize=False)])
    values = {s.name: buildValue({'YAdvance': 0, 'YAdvDevice': buildVarDevTable(gid)})
              for gid, s in enumerate(symbols)}
    lookup = font['GPOS'].table.LookupList.Lookup[0]
    lookup.SubTable = [buildSinglePosSubtable(values, font.getReverseGlyphMap())]
    lookup.SubTableCount = 1
    data = fixture.serialize(font)
    with TTFont(io.BytesIO(original)) as before, TTFont(io.BytesIO(data)) as after:
        fixture.require(before.getGlyphOrder() == after.getGlyphOrder() and
            all(before.getTableData(tag) == after.getTableData(tag) for tag in fixture.PROTECTED),
            'vertical_advance_experiment_changed_source_tables')
    return data


def desired(symbol, normalized):
    return fixture.analytic_width(symbol, normalized) - symbol.width


def statistic(stats, field, error, context):
    fixture.add_stat(stats, field, error, context)


def compare_rows(before, after, normalized, symbols, stats, context, fields):
    fixture.require(len(before) == len(after), 'vertical_advance_changed_glyph_count')
    for b, a in zip(before, after):
        fixture.require(b['gid'] == a['gid'], 'vertical_advance_changed_substitution')
        gid = a['gid']; expected = desired(symbols[gid], normalized)
        c = {**context, 'gid': gid, 'normalized': list(normalized), 'expected_delta': expected}
        for field in fields:
            fixture.require(a[field] == b[field], 'vertical_advance_changed_raw_metric_API')
        statistic(stats, 'raw_metrics_change', 0., c)
        delta = a['layout_advance'] - b['layout_advance']
        statistic(stats, 'advance_change', delta, c)
        statistic(stats, 'advance_change_minus_requested_model', delta - expected, c)


def harfbuzz(original, variants, symbols):
    import uharfbuzz as hb
    result = {'engine_version': hb.version_string(), 'groups': {}, 'calls': 0}
    for route, data in variants.items():
        for q in POINTS:
            for policy in ('default', 'enabled', 'disabled'):
                for direction in ('ltr', 'ttb'):
                    features = fixture.feature_settings(route, policy)
                    a = fixture.shape(data, q, direction, 'zh-cn', features)
                    b = fixture.shape(original, q, direction, 'zh-cn', features)
                    fixture.require(a['observed_normalized'] == b['observed_normalized'], 'HB_instance_changed')
                    for record in (a, b):
                        for g in record['glyphs']: g['layout_advance'] = -g['y_advance']
                    group = result['groups'].setdefault('/'.join((route, policy, direction)), {})
                    compare_rows(b['glyphs'], a['glyphs'], q, symbols, group,
                        {'point': list(q)}, ('metric_width', 'metric_height', 'metric_vertical_origin'))
                    for bg, ag in zip(b['glyphs'], a['glyphs']):
                        fixture.require(all(ag[k] == bg[k] for k in ('x_advance','x_offset','y_offset')),
                                        'YAdvance_changed_another_HB_position_field')
                        correction = desired(symbols[ag['gid']], a['observed_normalized'])
                        statistic(group, 'advance_change_minus_observed_axis_model',
                            ag['layout_advance']-bg['layout_advance']-correction,
                            {'point': list(q), 'gid': ag['gid'], 'observed': a['observed_normalized']})
                    result['calls'] += 2
    return result


def coretext(original, variants, symbols, folder):
    import probe_coretext_vertical_gpos as ct
    swift, binary = folder/'advance.swift', folder/'advance-native'
    swift.write_text(ct.make_harness())
    compiled = subprocess.run(['xcrun','swiftc','-O',str(swift),'-o',str(binary)],
                              capture_output=True, text=True, timeout=180)
    fixture.require(compiled.returncode == 0, 'CoreText_compile_failed:' + compiled.stderr[-3000:])
    result = {'harness_sha256': hashlib.sha256(swift.read_bytes()).hexdigest(),
              'groups': {}, 'calls': 0, 'processes': [], 'observations': {}}
    for route, data in variants.items():
        requests = [r for r in ct.requests(route, POINTS) if r['text']=='mixed' and r['language']=='zh-CN']
        measured = []
        for variant, font_data in (('original',original),('candidate',data)):
            path = folder/f'{route}-{variant}.ttf'; path.write_bytes(font_data)
            with TTFont(io.BytesIO(font_data)) as font:
                tags = (*fixture.PROTECTED,'name','GPOS','GDEF')
                hashes = {tag: hashlib.sha256(font.getTableData(tag)).hexdigest() for tag in tags if tag in font}
                absent = [tag for tag in ('GPOS','GDEF') if tag not in font]
            config = {'scope':'independent_original_GPOS_fixture_only', 'font_path':str(path),
                      'font_sha256':hashlib.sha256(font_data).hexdigest(),
                      'table_hashes':hashes,'absent_tables':absent,'requests':requests}
            manifest = folder/'request.json'; manifest.write_text(json.dumps(config))
            run = subprocess.run([str(binary),str(manifest)], capture_output=True,text=True,timeout=600)
            rows = [json.loads(line) for line in run.stdout.splitlines() if line]
            errors = [r for r in rows if r.get('type') in ('request_error','fatal')]
            obs = [r for r in rows if r.get('type')=='observation']
            meta = [r for r in rows if r.get('type')=='metadata']
            summaries = [r for r in rows if r.get('type')=='summary']
            result['processes'].append({'route':route,'variant':variant,'exit_code':run.returncode,
                'metadata':meta,'summaries':summaries,'errors':errors,'stderr':run.stderr[-3000:]})
            result['observations'][route+'/'+variant] = obs
            # Persist completed processes even if a later native request fails.
            (folder/'coretext-checkpoint.json').write_text(json.dumps(result))
            fixture.require(run.returncode==0 and not errors and len(obs)==len(requests)
                and len(meta)==len(summaries)==1 and meta[0]['font_sha256']==config['font_sha256']
                and summaries[0]['errors']==0 and summaries[0]['observations']==len(requests),
                'CoreText_advance_observation_incomplete')
            ct.require_registration_cleanup([r for r in rows if r.get('type')=='fixture_registration_cleanup'],
                                             config['font_sha256'])
            fixture.require(path.read_bytes()==font_data, 'CoreText_input_changed')
            measured.append(obs); result['calls']+=len(obs)
        for request, b, a in zip(requests,*measured):
            fixture.require(b['request']==a['request']==request and b['reported_axes']==a['reported_axes'],
                            'CoreText_advance_request_mismatch')
            for r in (b,a):
                for g in r['glyphs']:
                    fixture.require(g['actual_source_table_identity_verified'], 'CoreText_fallback')
                    # CTRun stores baseline advance in width for both directions.
                    g['layout_advance'] = g['advance'][0]
            group=result['groups'].setdefault('/'.join((route,request['policy'],request['direction'])),{})
            compare_rows(b['glyphs'],a['glyphs'],request['normalized'],symbols,group,
                         {'request':request},('metric_width','metric_height','metric_vertical_origin'))
    return result


def directwrite(original, variants, symbols, binary, folder):
    import probe_directwrite_vertical_layout as dw
    result={'groups':{},'calls':0,'processes':{},'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    for route,data in variants.items():
        requests=[r for r in dw.requests(POINTS) if r['route']==route and r['locale']=='zh-CN' and r['text_kind']=='mixed']
        fixture.require(requests, 'no_DirectWrite_advance_requests')
        observed=[]
        for variant,font_data in (('original',original),('candidate',data)):
            path=folder/f'{route}-{variant}.ttf';path.write_bytes(font_data)
            run=subprocess.run([str(binary),str(path)], input=''.join(dw.request_line(r) for r in requests),
                               capture_output=True,text=True,encoding='utf-8',timeout=600)
            (folder/f'{route}-{variant}.stdout.log').write_text(run.stdout)
            (folder/f'{route}-{variant}.stderr.log').write_text(run.stderr)
            fixture.require(path.read_bytes()==font_data, 'DirectWrite_input_changed')
            parsed=dw.parse_transcript(run.stdout,requests,font_data,run.returncode)
            result['processes'][route+'/'+variant]=parsed;observed.append(parsed['records'])
            result['calls']+=len(parsed['records'])
            (folder/'directwrite-checkpoint.json').write_text(json.dumps(result))
        for request,b,a in zip(requests,*observed):
            before=[g for _,g in dw.flatten(b)];after=[g for _,g in dw.flatten(a)]
            for r in (before,after):
                for g in r:g['layout_advance']=g['advance']
            group=result['groups'].setdefault('/'.join((route,request['policy'],request['direction'])),{})
            compare_rows(before,after,request['requested_normalized_model'],symbols,group,
                         {'request':request},('design_metrics',))
    return result


def run(output, native, binary=None):
    output=Path(output).resolve();fixture.require(not output.exists(),'new_output_directory_required')
    output.mkdir(parents=True)
    report={'status':'IN_PROGRESS','platform':platform.platform(),'production_accepted':False,
            'scope':'authored_symbols_variable_YAdvance_only','original_font_acceptance':'NOT_RUN',
            'windows_11_x64_acceptance':'NOT_RUN','raw_metric_gates_unchanged':True,'limit':fixture.LIMIT,
            'CoreText':'NOT_RUN','DirectWrite':'NOT_RUN'}
    try:
        original,symbols=fixture.original_fixture()
        variants={route:candidate(original,symbols,route) for route in fixture.ROUTES}
        report['font_sha256']={'original':hashlib.sha256(original).hexdigest(),
                              **{k:hashlib.sha256(v).hexdigest() for k,v in variants.items()}}
        report['HarfBuzz']=harfbuzz(original,variants,symbols)
        if native=='coretext':
            fixture.require(sys.platform=='darwin','CoreText_NOT_RUN_requires_macOS')
            report['CoreText']=coretext(original,variants,symbols,output)
        elif native=='directwrite':
            fixture.require(sys.platform=='win32' and binary is not None,'DirectWrite_NOT_RUN_requires_Windows_and_binary')
            report['DirectWrite']=directwrite(original,variants,symbols,Path(binary).resolve(strict=True),output)
        report['status']='DIAGNOSIS_COMPLETE_NOT_ACCEPTANCE'
    except Exception as error:
        report['status']='DIAGNOSIS_FAILED';report['error']=str(error);raise
    finally:
        (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--native',choices=('none','coretext','directwrite'),default='none')
    parser.add_argument('--binary',type=Path)
    args=parser.parse_args();report=run(args.output,args.native,args.binary)
    print(json.dumps({'status':report['status'],'native':args.native}))
