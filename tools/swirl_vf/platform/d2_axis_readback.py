#!/usr/bin/env python3
"""Diagnose the D1 96 rejected axis requests without accepting any mapping.

No glyph API is called. The production constructor and strict validator remain
verbatim. Original/replay requests are frozen before observing CoreText.
Only aggregate errors/counts are public; private native rows stay in --output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess

from macos_source_baseline import digest, inspect_source

FRACTIONS = (0., .123456789, .5, 1.)
MAIN = r'''
func d2Main() throws {
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let data = try Data(contentsOf:url, options:[.mappedIfSafe])
    guard sha256(data) == CommandLine.arguments[2] else { throw OracleError.invalid("wrong_source") }
    let states = try locateDescriptors(parseFaces(Bytes(data:data)),url:url)
    let requests = try JSONDecoder().decode([Request].self, from:FileHandle.standardInput.readDataToEndOfFile())
    var rows: [[String:Any]] = []
    let verified = states.filter { $0.baseFont != nil }.count
    if verified == states.count {
        for request in requests {
            guard request.face_index >= 0, request.face_index < states.count,
                  request.glyph_ids.isEmpty else { throw OracleError.invalid("invalid_axis_only_request") }
            let state = states[request.face_index]
            let (_, location, reported) = try constructInstance(state,request.location)
            var strict = true, failure = ""
            do { try validateReportedAxes(state.raw.axes,location,reported) }
            catch { strict = false; failure = String(describing:error) }
            rows.append(["request_id":request.request_id,"face_index":request.face_index,
                "location":location,"reported":reported,"strict_passed":strict,"failure":failure])
        }
    }
    try emit(["source_sha256":sha256(data),"faces":states.map { $0.metadata },
        "physical_faces_verified":verified,"rows":rows,
        "os_version":ProcessInfo.processInfo.operatingSystemVersionString])
}
do { try d2Main() }
catch { stderr("D2 axis diagnosis: \(error)"); exit(2) }
'''


def canonical(value):
    # Existing A3 preregistered T(T(x)); diagnostic replay only, not a new mapper.
    def step(x):
        return math.trunc(x * 10000) / 10000
    return step(step(value))


def requests_for(faces):
    requests = []
    for face in faces:
        axes = face['axes']
        defaults = {a['tag']: a['default'] for a in axes}
        for axis in axes:
            for index, fraction in enumerate(FRACTIONS):
                location = {**defaults, axis['tag']: axis['minimum'] + fraction * (axis['maximum'] - axis['minimum'])}
                row = {'request_id': f"f{face['face_index']}-{axis['tag']}-{index}",
                       'face_index': face['face_index'], 'location': location, 'glyph_ids': [],
                       'axis': axis['tag'], 'phase': 'original', 'fraction_index': index}
                requests.append(row)
                if index == 1:
                    requests.append({**row, 'request_id': row['request_id'] + '-replay', 'phase': 'replay',
                                     'location': {tag: canonical(v) for tag, v in location.items()}})
    return requests


def harness(extractor):
    text = Path(extractor).read_text()
    marker = '\nfunc run() throws {'
    if text.count(marker) != 1:
        raise ValueError('review_changed_production_entry_point')
    return text.split(marker)[0] + MAIN


def analyze(native, faces, requests, expected_hash):
    if native.get('source_sha256') != expected_hash or len(native.get('faces', [])) != len(faces):
        raise ValueError('native_source_identity_mismatch')
    verified = 0
    for source, observed in zip(faces, native['faces']):
        if type(observed.get('face_index')) is not int or observed['face_index'] != source['face_index']:
            raise ValueError('native_face_order_mismatch')
        if observed.get('status') == 'identity_verified':
            wanted = {tag: table['sha256'] for tag, table in source['tables'].items()}
            if observed.get('verified_table_sha256') != wanted:
                raise ValueError('native_original_table_identity_mismatch')
            verified += 1
    if type(native.get('physical_faces_verified')) is not int or native['physical_faces_verified'] != verified:
        raise ValueError('native_verified_face_count_mismatch')
    report = {'status': 'AXIS_READBACK_DIAGNOSIS_NOT_MAPPING_ACCEPTANCE',
              'source_sha256': expected_hash, 'faces': len(faces), 'physical_faces_verified': verified,
              'original_requests': 0, 'original_strict_passed': 0, 'original_strict_failed': 0,
              'predeclared_replay_requests': 0, 'replay_strict_passed': 0, 'replay_echo_exact': 0,
              'original_errors_match_predeclared_TT': 0, 'failure_fraction_counts': {}, 'by_axis': {},
              'mapping_accepted': False, 'glyph_equivalence_tested': False, 'font_generated': False}
    if verified != len(faces):
        if native.get('rows'):
            raise ValueError('unverified_faces_must_not_have_observations')
        report['status'] = 'BLOCKED_SOURCE_IDENTITY'
        return report
    if len(native.get('rows', [])) != len(requests):
        raise ValueError('native_axis_count_mismatch')
    seen = set()
    expected = {q['request_id']: q for q in requests}
    for row in native['rows']:
        key = row.get('request_id')
        if key not in expected or key in seen:
            raise ValueError('duplicate_or_unrelated_axis_row')
        seen.add(key); request = expected[key]
        if row.get('face_index') != request['face_index'] or row.get('location') != request['location']:
            raise ValueError('native_axis_request_changed')
        reported = row.get('reported')
        if (not isinstance(reported, dict) or any(type(v) not in (int, float) or not math.isfinite(v)
                                                for v in reported.values())
                or type(row.get('strict_passed')) is not bool):
            raise ValueError('invalid_native_axis_evidence')
        defaults = {a['tag']: a['default'] for a in faces[request['face_index']]['axes']}
        if set(reported) - set(defaults):
            raise ValueError('unknown_reported_axis')
        effective = {tag: reported.get(tag, default) for tag, default in defaults.items()}
        strict_expected = all((tag in reported or value == defaults[tag]) and abs(effective[tag] - value) <= 1e-6
                              for tag, value in request['location'].items())
        if row['strict_passed'] != strict_expected:
            raise ValueError('native_strict_verdict_contradicts_unchanged_guard')
        allowed = {f'coretext_did_not_report_requested_axis_value:{tag}' for tag in defaults}
        if (row['strict_passed'] and row.get('failure') != '') or (not row['strict_passed'] and row.get('failure') not in allowed):
            raise ValueError('invalid_strict_failure_code')
        if request['phase'] == 'replay':
            report['predeclared_replay_requests'] += 1
            report['replay_strict_passed'] += int(row['strict_passed'])
            report['replay_echo_exact'] += int(effective == request['location'])
        else:
            report['original_requests'] += 1
            report['original_strict_passed' if row['strict_passed'] else 'original_strict_failed'] += 1
            if not row['strict_passed']:
                fraction = str(request['fraction_index'])
                report['failure_fraction_counts'][fraction] = report['failure_fraction_counts'].get(fraction, 0) + 1
            axis = request['axis']
            group = report['by_axis'].setdefault(axis, {'requests': 0, 'strict_failed': 0, 'maximum_absolute_readback_error': 0.})
            group['requests'] += 1
            group['strict_failed'] += int(not row['strict_passed'])
            error = max(abs(effective[t] - v) for t, v in request['location'].items())
            group['maximum_absolute_readback_error'] = max(group['maximum_absolute_readback_error'], error)
            if not row['strict_passed'] and effective == {t: canonical(v) for t, v in request['location'].items()}:
                report['original_errors_match_predeclared_TT'] += 1
    return report


def run(source, output, expected_hash):
    source, output = Path(source).resolve(strict=True), Path(output).absolute()
    if digest(source) != expected_hash:
        raise ValueError('exact_requested_source_required')
    if output.exists() or output.is_symlink():
        raise ValueError('fresh_private_output_required')
    output.mkdir(parents=True, mode=0o700)
    faces = inspect_source(source)
    requests = requests_for(faces)
    (output / 'requests.json').write_text(json.dumps(requests, indent=2, allow_nan=False))
    if platform.system() != 'Darwin':
        raise RuntimeError('CoreText unavailable; NOT_RUN')
    extractor = Path(__file__).with_name('coretext_extract.swift')
    text = harness(extractor)
    swift, binary = output / 'axis.swift', output / 'axis'
    swift.write_text(text)
    built = subprocess.run(['xcrun', 'swiftc', '-O', str(swift), '-o', str(binary)], capture_output=True, timeout=180)
    (output / 'compile.log').write_bytes(built.stdout + built.stderr)
    if built.returncode:
        raise RuntimeError('axis_compile_failed_see_private_log')
    actual = subprocess.run([str(binary), str(source), expected_hash], input=json.dumps(requests).encode(),
                            capture_output=True, timeout=180)
    (output / 'native.stderr.log').write_bytes(actual.stderr)
    if actual.returncode:
        raise RuntimeError('axis_native_failed_see_private_log')
    native = json.loads(actual.stdout)
    (output / 'private-native.json').write_bytes(actual.stdout)
    report = analyze(native, faces, requests, expected_hash)
    report.update(os_version=native['os_version'], diagnostic_sha256=digest(Path(__file__)), extractor_sha256=digest(extractor),
                  harness_sha256=hashlib.sha256(text.encode()).hexdigest(), source_unchanged=digest(source) == expected_hash)
    if not report['source_unchanged']:
        raise ValueError('source_changed_during_axis_diagnosis')
    (output / 'summary.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps(report, allow_nan=False), flush=True)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--expected-sha256', required=True)
    args = p.parse_args()
    result = run(args.source, args.output, args.expected_sha256)
    raise SystemExit(2 if result['status'] == 'BLOCKED_SOURCE_IDENTITY' else 0)
