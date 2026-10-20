#!/usr/bin/env python3
"""Compare legitimate native font construction paths without relaxing acceptance.

The baseline observation helper is NOT the production oracle and is never fed
to rebuild.py. Only its axis-readback verdict is suppressed so that alternate
public CoreText/CoreGraphics APIs can be measured against it. Physical source
identity, geometry and metrics remain untouched. Original paths stay in memory;
only aggregate discrepancies and axis numbers leave the native process.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile

EXPECTED = '39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890'
GUARD = r'''        guard let expected = location[axis.tag], abs(effective - expected) <= 1e-6 else {
            throw OracleError.invalid("coretext_did_not_report_requested_axis_value:\(axis.tag)")
        }'''

SWIFT = r'''
func axisNumbers(_ font: CTFont) -> [String: Double] {
    var result: [String: Double] = [:]
    if let values = CTFontCopyVariation(font) as? [NSNumber: NSNumber] {
        for (key, value) in values { result[tagString(key.uint32Value)] = value.doubleValue }
    }
    return result
}
func namedAxes(_ base: CTFont, _ location: [String: Double]) throws -> [String: NSNumber] {
    guard let axes = CTFontCopyVariationAxes(base) as? [[String: Any]] else {
        throw OracleError.invalid("missing_named_axes")
    }
    var named: [String: NSNumber] = [:]
    for axis in axes {
        guard let key = axis[kCTFontVariationAxisIdentifierKey as String] as? NSNumber,
              let name = axis[kCTFontVariationAxisNameKey as String] as? String,
              let value = location[tagString(key.uint32Value)] else {
            throw OracleError.invalid("axis_name_identity_missing")
        }
        guard named[name] == nil else { throw OracleError.invalid("duplicate_axis_name") }
        named[name] = NSNumber(value: value)
    }
    guard named.count == location.count else { throw OracleError.invalid("axis_name_count_mismatch") }
    return named
}
func alternativeFont(_ state: FaceState, _ location: [String: Double], _ method: String) throws -> CTFont {
    guard let base = state.baseFont else { throw OracleError.invalid("unverified_face") }
    var matrix = CGAffineTransform.identity
    let font: CTFont
    if method == "descriptor_copy" {
        let variation = Dictionary(uniqueKeysWithValues: state.raw.axes.map {
            (NSNumber(value: $0.identifier), NSNumber(value: location[$0.tag]!))
        })
        let optical = CTFontCopyAttribute(base, kCTFontOpticalSizeAttribute) ?? NSNumber(value: Double(CTFontGetSize(base)))
        let attributes: [String: Any] = [kCTFontVariationAttribute as String: variation,
            "NSCTFontUnscaledTrackingAttribute": NSNumber(value: 0),
            kCTFontOpticalSizeAttribute as String: optical]
        let descriptor = CTFontDescriptorCreateCopyWithAttributes(CTFontCopyFontDescriptor(base), attributes as CFDictionary)
        font = CTFontCreateWithFontDescriptor(descriptor, CGFloat(state.raw.upm), &matrix)
    } else {
        let graphics = CTFontCopyGraphicsFont(base, nil)
        guard let varied = graphics.copy(withVariations: try namedAxes(base, location) as CFDictionary) else {
            throw OracleError.invalid("CGFont_copy_withVariations_failed")
        }
        let initial = CTFontCreateWithGraphicsFont(varied, CGFloat(state.raw.upm), &matrix, nil)
        if method == "graphics_copy_tracking" {
            let attributes: [String: Any] = ["NSCTFontUnscaledTrackingAttribute": NSNumber(value: 0)]
            let descriptor = CTFontDescriptorCreateWithAttributes(attributes as CFDictionary)
            font = CTFontCreateCopyWithAttributes(initial, CGFloat(state.raw.upm), &matrix, descriptor)
        } else {
            font = initial
        }
    }
    _ = try verifyIdentity(font, state.raw, allTables: false)
    guard CTFontGetMatrix(font).isIdentity, Double(CTFontGetSize(font)) == Double(state.raw.upm) else {
        throw OracleError.invalid("alternative_size_or_transform_changed")
    }
    return font
}
func metricVector(_ font: CTFont, _ glyphID: Int) throws -> [Double] {
    var glyph = CGGlyph(glyphID)
    var horizontal = CGSize.zero, vertical = CGSize.zero, origin = CGSize.zero
    _ = CTFontGetAdvancesForGlyphs(font, .horizontal, &glyph, &horizontal, 1)
    _ = CTFontGetAdvancesForGlyphs(font, .vertical, &glyph, &vertical, 1)
    CTFontGetVerticalTranslationsForGlyphs(font, &glyph, &origin, 1)
    let result = [Double(horizontal.width), Double(horizontal.height), Double(vertical.width),
                  Double(vertical.height), Double(origin.width), Double(origin.height)]
    guard result.allSatisfy(\.isFinite) else { throw OracleError.invalid("nonfinite_metrics") }
    return result
}
func geometryDifference(_ a: CTFont, _ b: CTFont, _ gid: Int) throws -> (Double, Bool) {
    let pa = CTFontCreatePathForGlyph(a, CGGlyph(gid), nil)
    let pb = CTFontCreatePathForGlyph(b, CGGlyph(gid), nil)
    if pa == nil || pb == nil { return (0, pa == nil && pb == nil) }
    let ca = try pathCommands(pa!), cb = try pathCommands(pb!)
    guard ca.count == cb.count else { return (0, false) }
    var maximum = 0.0
    for (x, y) in zip(ca, cb) {
        guard x.count == y.count, x[0] as? String == y[0] as? String else { return (0, false) }
        for index in 1..<x.count {
            guard let p = x[index] as? Double, let q = y[index] as? Double else {
                throw OracleError.invalid("unexpected_path_coordinate_type")
            }
            maximum = max(maximum, abs(p-q))
        }
    }
    return (maximum, true)
}
func inspectNumber(_ value: NSNumber) -> [String: Any] {
    let scalar = value.doubleValue
    var result: [String: Any] = ["value": scalar,
        "binary64_hex": String(scalar.bitPattern, radix:16),
        "objc_type": String(cString: value.objCType)]
    // NSNumber and CFNumber are toll-free bridged. Read the same object through
    // the C API without passing its Double value back into a new CFNumber.
    // The conversion Boolean concerns this stored number, not axis acceptance.
    let isNumber = CFGetTypeID(value) == CFNumberGetTypeID()
    result["is_cf_number"] = isNumber
    if isNumber {
        let number = unsafeBitCast(value, to: CFNumber.self)
        var direct = Double.nan
        let exact = CFNumberGetValue(number, .float64Type, &direct)
        result["cf_number_type"] = CFNumberGetType(number).rawValue
        result["cf_number_byte_size"] = CFNumberGetByteSize(number)
        result["cf_number_is_float"] = CFNumberIsFloatType(number)
        result["cf_number_float64_conversion_exact"] = exact
        result["cf_number_float64_is_finite"] = direct.isFinite
        result["cf_number_float64_binary64_hex"] = String(direct.bitPattern, radix:16)
        result["cf_number_and_nsnumber_bits_equal"] = direct.bitPattern == scalar.bitPattern
        if direct.isFinite { result["cf_number_float64_value"] = direct }
    }
    return result
}
func inspectNumbers(_ font: CTFont) -> [[String: Any]] {
    var values: [[String: Any]] = []
    let descriptor = CTFontCopyFontDescriptor(font)
    let dictionaries: [(String, Any?)] = [
        ("CTFontCopyVariation", CTFontCopyVariation(font)),
        ("CTFontCopyAttribute(kCTFontVariationAttribute)",
            CTFontCopyAttribute(font, kCTFontVariationAttribute)),
        ("CTFontDescriptorCopyAttribute(kCTFontVariationAttribute)",
            CTFontDescriptorCopyAttribute(descriptor, kCTFontVariationAttribute))]
    for (api, dictionary) in dictionaries {
        if let axes = dictionary as? [NSNumber: NSNumber] {
            for (key, value) in axes {
                var row = inspectNumber(value)
                row["api"] = api
                row["axis"] = tagString(key.uint32Value)
                values.append(row)
            }
        }
    }
    let graphics = CTFontCopyGraphicsFont(font, nil)
    if let axes = graphics.variations as? [String: NSNumber] {
        for (key, value) in axes {
            var row = inspectNumber(value)
            row["api"] = "CGFont.variations"
            row["axis_name"] = key
            values.append(row)
        }
    }
    return values
}
func compareConstructionMain() throws {
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let data = try Data(contentsOf:url, options:[.mappedIfSafe])
    guard sha256(data) == "SOURCE_HASH" else { throw OracleError.invalid("wrong_original_source") }
    let states = try locateDescriptors(parseFaces(Bytes(data:data)), url:url)
    guard states.count == 32, states.allSatisfy({ $0.baseFont != nil }) else {
        throw OracleError.invalid("all_physical_faces_required")
    }
    let methods = ["legacy_observation", "descriptor_copy", "graphics_copy", "graphics_copy_tracking"]
    let factors: [Double] = [0, -1, 1, 0.5, -0.5, 0.201171875, -0.265625, 0.951416015625, 0.123456789]
    let gids = [0, 3, 5, 56, 498, 600]
    var reports: [[String: Any]] = []
    for state in states {
        for method in methods {
            var count = 0, strictPass = 0, failures = 0, topologyMismatch = 0
            var maxAxis = 0.0, maxGeometry = 0.0, maxMetric = 0.0
            var examples: [[String: Any]] = [], errors: [String] = []
            for axis in state.raw.axes {
                for factor in factors {
                    try autoreleasepool {
                        var request = Dictionary(uniqueKeysWithValues: state.raw.axes.map { ($0.tag, $0.defaultValue) })
                        request[axis.tag] = axis.defaultValue + factor * (factor < 0 ? axis.defaultValue-axis.minimum : axis.maximum-axis.defaultValue)
                        do {
                            let (baseline, location, _) = try observationInstance(state, request)
                            let font = method == "legacy_observation" ? baseline : try alternativeFont(state, location, method)
                            let reported = axisNumbers(font)
                            let error = state.raw.axes.map { abs((reported[$0.tag] ?? $0.defaultValue) - location[$0.tag]!) }.max() ?? 0
                            guard error.isFinite else { throw OracleError.invalid("nonfinite_axis") }
                            maxAxis = max(maxAxis, error); count += 1
                            strictPass += error <= 1e-6 ? 1 : 0
                            if error > 1e-6 && examples.count < 2 {
                                examples.append(["requested": location, "reported": reported,
                                    "maximum_absolute_error": error, "raw_number_metadata": inspectNumbers(font)])
                            }
                            for gid in gids {
                                let (difference, topology) = try geometryDifference(baseline, font, gid)
                                maxGeometry = max(maxGeometry, difference)
                                topologyMismatch += topology ? 0 : 1
                                let a = try metricVector(baseline, gid), b = try metricVector(font, gid)
                                for (p,q) in zip(a,b) { maxMetric = max(maxMetric, abs(p-q)) }
                            }
                        } catch {
                            failures += 1
                            if errors.count < 2 { errors.append(String(describing:error)) }
                        }
                    }
                }
            }
            reports.append(["face_index": state.raw.index, "method": method,
                "observed_positions": count, "axis_positions_within_original_tolerance": strictPass,
                "construction_failures": failures, "error_examples": errors,
                "max_axis_error": maxAxis, "axis_examples": examples,
                "max_geometry_difference_against_original_api": maxGeometry,
                "path_topology_mismatches": topologyMismatch,
                "max_metric_difference_against_original_api": maxMetric])
        }
    }
    try emit(["status": "NATIVE_CONSTRUCTION_COMPARISON_NOT_FONT_ACCEPTANCE",
        "source_sha256": sha256(data), "physical_faces_verified": states.count,
        "production_oracle_changed": false, "axis_tolerance": 1e-6,
        "number_metadata_schema": 2,
        "cf_number_conversion_exact_is_not_axis_acceptance": true,
        "outlines_published": false, "font_generated": false, "reports": reports])
}
try compareConstructionMain()
'''


def make_harness(source: str) -> str:
    separator = '\nfunc run() throws {'
    if source.count(separator) != 1 or source.count(GUARD) != 1:
        raise ValueError('native production helpers changed; review before reuse')
    prefix = source.split(separator)[0]
    prefix = prefix.replace(GUARD, '        _ = effective // Baseline observation only, never builder input.')
    prefix = prefix.replace('func makeInstance(', 'func observationInstance(', 1)
    return prefix + SWIFT.replace('SOURCE_HASH', EXPECTED)


def run(source: Path, output: Path) -> dict:
    if output.exists() or output.resolve() == source.resolve():
        raise ValueError('report must be a new file distinct from source')
    if hashlib.sha256(source.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError('exact source SHA required')
    code = Path(__file__).with_name('coretext_extract.swift')
    text = code.read_text(encoding='utf-8')
    report = {'status': 'NOT_RUN', 'platform': platform.platform(),
              'source_code_sha256': hashlib.sha256(text.encode()).hexdigest()}
    with tempfile.TemporaryDirectory(prefix='swirl-native-construction-') as directory:
        root = Path(directory); swift = root/'compare.swift'; binary = root/'compare'
        swift.write_text(make_harness(text), encoding='utf-8')
        compiled = subprocess.run(['xcrun', 'swiftc', '-O', str(swift), '-o', str(binary)],
                                  capture_output=True, text=True, timeout=180)
        if compiled.returncode:
            raise RuntimeError('Swift compilation failed: '+compiled.stderr[-8000:])
        native = subprocess.run([str(binary),str(source)],capture_output=True,text=True,timeout=600)
        if native.returncode:
            raise RuntimeError('Native comparison failed: '+native.stderr[-4000:])
        report.update(json.loads(native.stdout))
    if hashlib.sha256(source.read_bytes()).hexdigest() != EXPECTED:
        raise RuntimeError('source changed during native comparison')
    report['source_unchanged'] = True
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    # A bounded aggregate is useful in job logs; full numeric evidence is JSON.
    for method in sorted({r['method'] for r in report['reports']}):
        rows = [r for r in report['reports'] if r['method']==method]
        print(json.dumps({'method':method,'faces':len(rows),
            'observed_positions':sum(r['observed_positions'] for r in rows),
            'axis_positions_within_original_tolerance':sum(r['axis_positions_within_original_tolerance'] for r in rows),
            'construction_failures':sum(r['construction_failures'] for r in rows),
            'max_axis_error':max(r['max_axis_error'] for r in rows),
            'max_geometry_difference':max(r['max_geometry_difference_against_original_api'] for r in rows),
            'max_metric_difference':max(r['max_metric_difference_against_original_api'] for r in rows),
            'path_topology_mismatches':sum(r['path_topology_mismatches'] for r in rows),
            'first_face_example':rows[0]},allow_nan=False),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    run(args.source,args.output)
