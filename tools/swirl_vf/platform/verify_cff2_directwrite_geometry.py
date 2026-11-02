"""Compare actual DirectWrite controls with the independent authored source.

Native coordinates are exported only by an explicit probe flag. This validator
accepts the authored three-GID fixture, never a private original-font substitute.
The raw metric gate, native loader gate and original-font acceptance are separate.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import tempfile

import numpy as np
from fontTools.ttLib import TTCollection

from make_cff2_fixture import records, geometry
from test_coretext_extract import make_fixture

LIMIT = 1/32


def compare(row, source, *, repeats=1):
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
        default = axis.defaultValue
        location[axis.axisTag] = ((v-default)/(axis.maxValue-default) if v >= default
                                  else (v-default)/(default-axis.minValue))
    # Source fixture avar is identity. Fail if that premise ever changes.
    if 'avar' in source and any(x != y for mapping in source['avar'].segments.values() for x,y in mapping.items()):
        raise ValueError('authored_geometry_requires_identity_avar')
    expected = geometry.operands(records(source,order[gid],[location],.25,repeat_contours=repeats)[0])
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
    headers = [r for r in transcript if r.get('record')=='header']
    faces = {r['face_index']:r for r in transcript if r.get('record')=='face'}
    instances = {(r['face_index'],r['case']):r for r in transcript if r.get('record')=='instance'}
    count = 1 if variant=='flat_standalone' else 2
    if len(headers)!=1 or headers[0].get('outline_coordinates_exported') is not True:
        raise ValueError('native_outline_export_not_declared')
    if headers[0]['physical_face_count']!=count or set(faces)!=set(range(count)) or any(
        f['glyph_count']!=3 or f['probed_glyph_count']!=3 for f in faces.values()):
        raise ValueError('authored_native_face_or_GID_coverage_changed')
    if len(faces)!=sum(r.get('record')=='face' for r in transcript) or len(instances)!=sum(
        r.get('record')=='instance' for r in transcript):
        raise ValueError('duplicate_native_face_or_instance')
    expected = {(face,case,gid) for face,case in instances for gid in range(3)}
    report = {'scope':'authored independent source geometry only','limit_source_units':LIMIT,
              'observations':0,'controls':0,'max_control_error':0.,'failed_observations':0,
              'failures':[],'production_accepted':False,'transcript_sha256':native['outline_coordinates_sha256']}
    seen=set()
    with tempfile.TemporaryDirectory() as folder:
        source=Path(folder)/'authored.ttc';make_fixture(source)
        with TTCollection(source) as original:
            for line in path.open(encoding='utf-8'):
                row=json.loads(line);key=(row['face_index'],row['case'],row['glyph_id'])
                if key not in expected or key in seen or row['axes']!=instances[key[:2]]['requested']:
                    raise ValueError('duplicate_unrequested_or_mismatched_native_outline')
                seen.add(key)
                result=compare(row,original.fonts[key[0]],repeats=512 if variant=='flat_long' else 1)
                report['observations']+=1;report['controls']+=result.get('controls',0)
                report['max_control_error']=max(report['max_control_error'],result.get('max_control_error',0))
                if not result['passed']:
                    report['failed_observations']+=1
                    report['failures'].append({'face':key[0],'case':key[1],'gid':key[2],**result})
    report['complete_coverage']=seen==expected and all(sum(f==i for f,_ in instances)==62 for i in range(count))
    report['status']='PASS_AUTHORED_GEOMETRY' if report['complete_coverage'] and not report['failed_observations'] else 'FAIL_AUTHORED_GEOMETRY'
    return report
