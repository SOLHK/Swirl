"""Compare actual DirectWrite controls with the independent authored source.

Native coordinates are exported only by an explicit probe flag. This validator
accepts the authored three-GID fixture, never a private original-font substitute.
The raw metric gate, native loader gate and original-font acceptance are separate.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path
import tempfile

import numpy as np
from fontTools.ttLib import TTCollection

from make_cff2_fixture import records, geometry
from test_coretext_extract import make_fixture

LIMIT = 1/32


def float32(value):
    """Recover the exact FLOAT transported by the native API's 9-digit JSON."""
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('invalid_native_axis_number')
    try:
        result = struct.unpack('>f', struct.pack('>f', value))[0]
    except (OverflowError, struct.error) as error:
        raise ValueError('invalid_native_axis_number') from error
    if not math.isfinite(result):
        raise ValueError('invalid_native_axis_number')
    return result


def expected_positions(source):
    """Independent, complete declaration of the native 3-axis sampling contract.

    Case names and submitted FLOATs are derived from the authored source, never
    from observed rows. Sixty-two records at the default location are not a
    three-axis test. fvar axis order also determines grid and Halton dimensions.
    """
    axes = source['fvar'].axes
    if len(axes) != 3:
        raise ValueError('authored_three_axis_contract_changed')
    defaults = {a.axisTag: float32(a.defaultValue) for a in axes}
    result = {'default': defaults}
    for axis in axes:
        for fraction in (0., .1732050807569, .3819660112501,
                         .6180339887499, .8267949192431, 1.):
            result[f'sweep_{axis.axisTag}_{fraction:.6f}'] = dict(defaults, **{
                axis.axisTag: float32(axis.minValue + fraction*(axis.maxValue-axis.minValue))})
    for index in range(27):
        result[f'grid_{index}'] = {a.axisTag: float32(
            (a.minValue, a.defaultValue, a.maxValue)[index//(3**dimension) % 3])
            for dimension, a in enumerate(axes)}
    def halton(index, base):
        value, factor = 0., 1.
        while index:
            factor /= base
            value += factor*(index % base)
            index //= base
        return value
    for index in range(1, 17):
        result[f'internal_{index}'] = {a.axisTag: float32(
            a.minValue + halton(index+31, base)*(a.maxValue-a.minValue))
            for a, base in zip(axes, (2, 3, 5))}
    return result


def validate_instances(transcript, native, sources):
    """Reject incomplete, relabelled or rounded-away native axis evidence."""
    headers = [r for r in transcript if r.get('record') == 'header']
    if len(headers) != 1 or any(headers[0].get(k) is not True for k in
            ('directwrite_supported', 'all_glyphs', 'outline_coordinates_exported')):
        raise ValueError('native_complete_outline_export_not_declared')
    if headers[0].get('input_sha256') != native.get('input_sha256') or not native.get('input_sha256'):
        raise ValueError('native_font_identity_mismatch')
    count = len(sources)
    if headers[0].get('physical_face_count') != count:
        raise ValueError('authored_native_face_coverage_changed')
    faces = [r for r in transcript if r.get('record') == 'face']
    if len(faces) != count or {r.get('face_index') for r in faces} != set(range(count)):
        raise ValueError('duplicate_or_missing_native_face')
    for row in faces:
        source = sources[row['face_index']]
        axes = [dict(tag=a.axisTag, min=a.minValue, default=a.defaultValue, max=a.maxValue)
                for a in source['fvar'].axes]
        if row.get('glyph_count') != len(source.getGlyphOrder()) or row.get('probed_glyph_count') != len(source.getGlyphOrder()) or row.get('axes') != axes:
            raise ValueError('authored_native_GID_or_axis_coverage_changed')
    plan = {(face, case): point for face, source in enumerate(sources)
            for case, point in expected_positions(source).items()}
    instances = {}
    for row in (r for r in transcript if r.get('record') == 'instance'):
        key = (row.get('face_index'), row.get('case'))
        if key not in plan or key in instances:
            raise ValueError('duplicate_or_unrequested_native_instance')
        expected = plan[key]
        requested, applied = row.get('requested', {}), row.get('applied', {})
        if set(requested) != set(expected) or any(float32(requested[t]) != v for t, v in expected.items()):
            raise ValueError('native_instance_coordinate_plan_changed')
        # DirectWrite adds synthetic standard-axis defaults; only the physical
        # fvar axes are part of this exact readback contract.
        if not set(expected) <= set(applied) or any(float32(applied[t]) != v for t, v in expected.items()):
            raise ValueError('native_instance_axis_readback_changed')
        if row.get('status') != 'PASS':
            raise ValueError('native_instance_failed')
        instances[key] = row
    if set(instances) != set(plan):
        raise ValueError('incomplete_native_instance_plan')
    summaries = [r for r in transcript if r.get('record') == 'summary']
    results = [r for r in transcript if r.get('record') == 'face_result']
    if (len(summaries) != 1 or transcript[-1] is not summaries[0]
            or len(results) != count or {r.get('face_index') for r in results} != set(range(count))
            or native.get('input_unchanged') is not True):
        raise ValueError('native_completion_not_proven')
    completed = (summaries[0].get('status') == 'PASS_NATIVE_PROBE'
        and summaries[0].get('faces_passed') == count and summaries[0].get('faces_failed') == 0
        and all(r.get('status') == 'PASS_NATIVE_PROBE' and r.get('positions') == 62 for r in results)
        and native.get('native_exit_code') == 0)
    # Failed native controls remain comparable so one rejected variant does not
    # prevent later independent controls from running. They can never pass.
    return instances, completed



def compare(row, source, *, repeats=1, nonlinear=False):
    if row.get('record') != 'outline' or row.get('coordinate_frame') != 'x_right_y_down_font_units':
        raise ValueError('native_outline_frame_not_proven')
    gid = row['glyph_id']; order = source.getGlyphOrder()
    if type(gid) is not int or not 0 <= gid < len(order) or row.get('upm') != source['head'].unitsPerEm:
        raise ValueError('native_outline_GID_or_UPM_changed')
    tags = {a.axisTag for a in source['fvar'].axes}
    if set(row['axes']) != tags:
        raise ValueError('native_outline_axis_set_changed')
    location = {}
    for axis in source['fvar'].axes:
        v = row['axes'][axis.axisTag]
        if type(v) not in (int,float) or not math.isfinite(v) or not axis.minValue <= v <= axis.maxValue:
            raise ValueError('invalid_native_outline_axis_value')
        v = float32(v)
        default = axis.defaultValue
        location[axis.axisTag] = ((v-default)/(axis.maxValue-default) if v >= default
                                  else (v-default)/(default-axis.minValue))
    # Source fixture avar is identity. Fail if that premise ever changes.
    if 'avar' in source and any(x != y for mapping in source['avar'].segments.values() for x,y in mapping.items()):
        raise ValueError('authored_geometry_requires_identity_avar')
    expected = geometry.operands(records(source,order[gid],[location],.25,
        repeat_contours=repeats, nonlinear=nonlinear)[0])
    commands = []
    for command in row['commands']:
        values = list(command)
        for i in range(2,len(values),2): values[i] = -values[i]
        commands.append(values)
    actual = geometry.operands(commands)
    if actual[0] != expected[0]:
        return {'passed':False,'reason':'cubic_topology_mismatch','expected_controls':len(expected[1])//2,
                'actual_controls':len(actual[1])//2}
    errors = np.linalg.norm(geometry.control_points(*actual)-geometry.control_points(*expected),axis=1)
    maximum = float(errors.max(initial=0))
    return {'passed':maximum <= LIMIT,'max_control_error':maximum,'controls':len(errors)}


def verify(path, transcript, native, *, variant):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != native.get('outline_coordinates_sha256'):
        raise ValueError('native_outline_transcript_hash_mismatch')
    count = 1 if variant=='flat_standalone' else 2
    report = {'scope':'authored independent source geometry only','limit_source_units':LIMIT,
              'observations':0,'controls':0,'max_control_error':0.,'failed_observations':0,
              'failures':[],'production_accepted':False,'transcript_sha256':native['outline_coordinates_sha256']}
    seen=set()
    with tempfile.TemporaryDirectory() as folder:
        source=Path(folder)/'authored.ttc';make_fixture(source)
        with TTCollection(source) as original, path.open(encoding='utf-8') as lines:
            instances, completed = validate_instances(transcript, native, original.fonts[:count])
            report['native_completed_successfully'] = completed
            expected = {(face, case, gid) for face, case in instances for gid in range(3)}
            for line in lines:
                row=json.loads(line);key=(row['face_index'],row['case'],row['glyph_id'])
                if key not in expected or key in seen or row['axes']!=instances[key[:2]]['requested']:
                    raise ValueError('duplicate_unrequested_or_mismatched_native_outline')
                seen.add(key)
                result=compare(row,original.fonts[key[0]],repeats=512 if variant=='flat_long' else 1,
                               nonlinear=variant=='adaptive')
                report['observations']+=1;report['controls']+=result.get('controls',0)
                report['max_control_error']=max(report['max_control_error'],result.get('max_control_error',0))
                if not result['passed']:
                    report['failed_observations']+=1
                    report['failures'].append({'face':key[0],'case':key[1],'gid':key[2],**result})
    report['complete_coverage']=seen==expected
    report['exact_axis_plan_verified']=True
    report['status']='PASS_AUTHORED_GEOMETRY' if report['complete_coverage'] and completed and not report['failed_observations'] else 'FAIL_AUTHORED_GEOMETRY'
    return report
