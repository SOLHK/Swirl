#!/usr/bin/env python3
"""Observe native axis readback without accepting it or extracting any glyph.

This standalone diagnosis keeps the production oracle unchanged. A temporary
copy of its instance helper records mismatching coordinates instead of raising
at that specific assertion. All physical face checks remain active. It is never
used by the font builder, and no outline API is called by the diagnostic main.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from compare_axis_construction import GUARD

EXPECTED = '39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'

MAIN = r'''
func diagnosticMain() throws {
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let data = try Data(contentsOf:url, options:[.mappedIfSafe])
    guard sha256(data) == "SOURCE_HASH" else { throw OracleError.invalid("wrong_source") }
    let states = try locateDescriptors(parseFaces(Bytes(data:data)), url:url)
    let unavailable = states.filter { $0.baseFont == nil }.map { $0.raw.index }
    // An unreadable source is an actual diagnostic result, not a Swift trap or
    // permission to substitute an installed font. Do not request any instances.
    if !unavailable.isEmpty {
        let urlDescriptors = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor]
        let dataDescriptors = CTFontManagerCreateFontDescriptorsFromData(data as CFData) as? [CTFontDescriptor]
        let provider = CGDataProvider(data:data as CFData)
        let graphicsFont = provider.flatMap { CGFont($0) }
        try emit(["status":"BLOCKED_SOURCE_IDENTITY", "source_sha256":sha256(data),
            "source_face_count":states.count,
            "physical_faces_verified":states.count - unavailable.count,
            "unavailable_face_indices":unavailable,
            "url_descriptors_returned":urlDescriptors != nil,
            "url_descriptor_count":urlDescriptors?.count ?? 0,
            "data_descriptors_returned":dataDescriptors != nil,
            "data_descriptor_count":dataDescriptors?.count ?? 0,
            "cgfont_created":graphicsFont != nil,
            "os_version":ProcessInfo.processInfo.operatingSystemVersionString,
            "font_data_published":false, "production_assertion_unchanged":true,
            "glyph_extraction_performed":false, "observations":[]])
        return
    }
    var observations: [[String:Any]] = []
    let factors: [Double] = [0, -1, 1, 0.5, -0.5, 0.201171875,
                             -0.265625, 0.951416015625, 0.123456789]
    for state in states {
        for axis in state.raw.axes {
            for factor in factors {
                var requested = Dictionary(uniqueKeysWithValues: state.raw.axes.map { ($0.tag, $0.defaultValue) })
                requested[axis.tag] = axis.defaultValue + factor * (factor < 0 ? axis.defaultValue-axis.minimum : axis.maximum-axis.defaultValue)
                let (_, location, reported) = try diagnosticInstance(state, requested)
                var differences: [String:Double] = [:]
                for item in state.raw.axes {
                    differences[item.tag] = (reported[item.tag] ?? item.defaultValue) - location[item.tag]!
                }
                observations.append(["face_index":state.raw.index, "changed_axis":axis.tag,
                    "factor":factor, "requested":location, "reported":reported,
                    "signed_errors":differences])
            }
        }
    }
    try emit(["status":"AXIS_READBACK_DIAGNOSIS_NOT_ACCEPTANCE", "source_sha256":sha256(data),
              "source_face_count":states.count,
              "physical_faces_verified":states.count, "font_data_published":false,
              "os_version":ProcessInfo.processInfo.operatingSystemVersionString,
              "production_assertion_unchanged":true, "glyph_extraction_performed":false,
              "observations":observations])
}
do { try diagnosticMain() }
catch { stderr("Axis readback diagnosis: \(error)"); exit(2) }
'''


def harness(source):
    text = source.read_text()
    prefix = text[:text.index('\nfunc run() throws {')]
    if prefix.count(GUARD) != 1:
        raise ValueError('production guard changed: review diagnosis instead of blind patching')
    prefix = prefix.replace(GUARD, '        _ = effective // Observation only; no acceptance verdict.')
    prefix = prefix.replace('func makeInstance(', 'func diagnosticInstance(', 1)
    return prefix + MAIN.replace('SOURCE_HASH', EXPECTED)


def diagnose(source, output):
    source = Path(source); output = Path(output)
    if hashlib.sha256(source.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError('exact original source required')
    if output.exists() or output.resolve() == source.resolve():
        raise ValueError('choose a fresh diagnostic report path')
    original = Path(__file__).with_name('coretext_extract.swift')
    with tempfile.TemporaryDirectory(prefix='swirl-axis-readback-') as temporary:
        swift = Path(temporary)/'diagnostic.swift'; binary = Path(temporary)/'diagnostic'
        swift.write_text(harness(original))
        build = subprocess.run(['xcrun','swiftc','-O',str(swift),'-o',str(binary)],
                               capture_output=True,text=True,timeout=180)
        if build.returncode:
            raise RuntimeError(build.stderr)
        run = subprocess.run([str(binary),str(source)],capture_output=True,text=True,timeout=180)
        if run.returncode:
            raise RuntimeError(f'axis diagnostic exit {run.returncode}: {run.stderr[-4000:]}')
        report = json.loads(run.stdout)
    report = summarize(report)
    report['source_code_sha256'] = hashlib.sha256(original.read_bytes()).hexdigest()
    report['diagnostic_harness_sha256'] = hashlib.sha256(harness(original).encode()).hexdigest()
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report,allow_nan=False),flush=True)
    return report


def summarize(native):
    """Keep unavailable physical faces explicit; they have no axis observations."""
    report = dict(native)
    rows = report.pop('observations')
    count = report['source_face_count']
    verified = report['physical_faces_verified']
    if report['status'] == 'BLOCKED_SOURCE_IDENTITY':
        unavailable = report['unavailable_face_indices']
        if (rows or type(count) is not int or type(verified) is not int
                or not 0 <= verified < count
                or len(unavailable) != count - verified
                or len(set(unavailable)) != len(unavailable)
                or any(type(i) is not int or not 0 <= i < count for i in unavailable)):
            raise ValueError('inconsistent blocked source identity evidence')
        report.update(faces=[], position_count=0)
        return report
    if report['status'] != 'AXIS_READBACK_DIAGNOSIS_NOT_ACCEPTANCE' or verified != count:
        raise ValueError('axis observations require every physical source face')
    faces = []
    for index in range(report['physical_faces_verified']):
        relevant = [r for r in rows if r['face_index'] == index]
        failures = [r for r in relevant if any(abs(v)>1e-6 for v in r['signed_errors'].values())]
        faces.append({'face_index':index, 'positions_observed':len(relevant),
                      'positions_outside_unchanged_axis_tolerance':len(failures),
                      'examples':failures[:6],
                      'maximum_absolute_errors':{tag:max(abs(r['signed_errors'][tag]) for r in relevant)
                          for tag in relevant[0]['signed_errors']}})
    report['faces'] = faces
    report['position_count'] = len(rows)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    report = diagnose(args.source,args.output)
    raise SystemExit(2 if report['status'] == 'BLOCKED_SOURCE_IDENTITY' else 0)
