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

EXPECTED = '39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'

MAIN = r'''
func diagnosticMain() throws {
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let data = try Data(contentsOf:url, options:[.mappedIfSafe])
    guard sha256(data) == "SOURCE_HASH" else { throw OracleError.invalid("wrong_source") }
    let states = try locateDescriptors(parseFaces(Bytes(data:data)), url:url)
    var observations: [[String:Any]] = []
    let factors: [Double] = [0, -1, 1, 0.5, -0.5, 0.201171875,
                             -0.265625, 0.951416015625, 0.123456789]
    for state in states {
        guard state.baseFont != nil else { throw OracleError.invalid("missing_physical_face") }
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
              "physical_faces_verified":states.count, "font_data_published":false,
              "production_assertion_unchanged":true, "glyph_extraction_performed":false,
              "observations":observations])
}
try diagnosticMain()
'''


def harness(source):
    text = source.read_text()
    prefix = text[:text.index('\nfunc run() throws {')]
    guard = r'''        guard let expected = location[axis.tag], abs(effective - expected) <= 1e-6 else {
            throw OracleError.invalid("coretext_did_not_report_requested_axis_value:\(axis.tag)")
        }'''
    if prefix.count(guard) != 1:
        raise ValueError('production guard changed: review diagnosis instead of blind patching')
    prefix = prefix.replace(guard, '        _ = effective // Observation only; no acceptance verdict.')
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
    rows = report.pop('observations')
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
    report['source_code_sha256'] = hashlib.sha256(original.read_bytes()).hexdigest()
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps(report,allow_nan=False),flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    diagnose(args.source,args.output)
