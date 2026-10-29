"""A3 public CoreText construction/representation experiment, never an oracle.

Reuse the pinned identity/transport/extraction prefix byte-for-byte. The new
dispatcher only selects an observation path; no constructor is promoted to
production. Float32/Fixed transforms are explicit lossy diagnostic controls.
Public API contracts: CTFontDescriptorCreateCopyWithVariation (CGFloat),
CTFontCreateCopyWithAttributes and CGFont.copy(withVariations:).
"""
from __future__ import annotations

import hashlib
import json

import anchor_construction_harness as anchor


MODES = ("copy_binary64", "anchor_binary64", "anchor_binary32", "anchor_fixed16",
         "descriptor_bulk_binary64", "descriptor_forward_binary64",
         "descriptor_reverse_binary64", "graphics_binary64", "copy_cfnumber_float32")
MODE_ENV = "SWIRL_VF_A3_CONSTRUCTOR_MODE"
_RUN = "\nfunc run() throws {"
_MARKER = "// SWIRL_VF_A3_INPUT_CONSTRUCTION_DIAGNOSTIC"

SCALAR_SWIFT = r'''
func a3FixedInteger(_ value: Double) throws -> Int64 {
    guard value.isFinite, value >= -32768.0, value <= 32767.99998474121 else {
        throw OracleError.invalid("a3_value_outside_fixed16_range")
    }
    let scaled = value * 65536.0
    let integral = floor(scaled)
    // Do not add 0.5 before flooring: a large near-half value can round twice.
    return Int64(integral + (scaled - integral >= 0.5 ? 1.0 : 0.0))
}

func a3Coordinate(_ value: Double, _ mode: String) throws -> Double {
    guard value.isFinite else { throw OracleError.invalid("a3_nonfinite_input") }
    if mode == "anchor_binary32" || mode == "copy_cfnumber_float32" {
        let result = Double(Float(value))
        guard result.isFinite else { throw OracleError.invalid("a3_nonfinite_float32_input") }
        return result
    }
    if mode == "anchor_fixed16" {
        return Double(try a3FixedInteger(value)) / 65536.0
    }
    return value
}
'''

_HELPERS = r'''
// SWIRL_VF_A3_INPUT_CONSTRUCTION_DIAGNOSTIC
func a3Mode() throws -> String {
    let allowed = Set(A3_MODES_JSON)
    guard let mode = ProcessInfo.processInfo.environment["A3_MODE_ENV"], allowed.contains(mode) else {
        throw OracleError.invalid("a3_constructor_mode_missing_or_unknown")
    }
    return mode
}

func a3Alternative(_ state: FaceState, _ location: [String: Double], _ mode: String) throws -> CTFont {
    guard let base = state.baseFont else { throw OracleError.invalid("a3_unverified_base") }
    let optical = try anchorExpectedOptical(base, location)
    let attributes: [String: Any] = ["NSCTFontUnscaledTrackingAttribute": NSNumber(value: 0),
                                   kCTFontOpticalSizeAttribute as String: NSNumber(value: optical)]
    var matrix = CGAffineTransform.identity
    let font: CTFont
    if mode == "copy_cfnumber_float32" {
        var values: [NSNumber: NSNumber] = [:]
        for axis in state.raw.axes {
            guard let value = location[axis.tag] else { throw OracleError.invalid("a3_axis_missing") }
            values[NSNumber(value: axis.identifier)] = NSNumber(value: Float(value))
        }
        var all = attributes
        all[kCTFontVariationAttribute as String] = values
        let descriptor = CTFontDescriptorCreateWithAttributes(all as CFDictionary)
        font = CTFontCreateCopyWithAttributes(base, CGFloat(state.raw.upm), &matrix, descriptor)
    } else {
        var descriptor = CTFontDescriptorCreateCopyWithAttributes(CTFontCopyFontDescriptor(base), attributes as CFDictionary)
        let axes = mode == "descriptor_reverse_binary64" ? Array(state.raw.axes.reversed()) : state.raw.axes
        for axis in axes {
            guard let value = location[axis.tag] else { throw OracleError.invalid("a3_axis_missing") }
            let identifier = unsafeBitCast(NSNumber(value: axis.identifier), to: CFNumber.self)
            descriptor = CTFontDescriptorCreateCopyWithVariation(descriptor, identifier, CGFloat(value))
        }
        font = CTFontCreateWithFontDescriptor(descriptor, CGFloat(state.raw.upm), &matrix)
    }
    _ = try verifyIdentity(font, state.raw, allTables: false)
    guard CTFontGetMatrix(font).isIdentity, Double(CTFontGetSize(font)) == Double(state.raw.upm) else {
        throw OracleError.invalid("a3_size_or_matrix_changed")
    }
    return font
}

func a3Instance(_ state: FaceState, _ requested: [String: Double], _ mode: String) throws -> (CTFont, [String: Double], [String: Double]) {
    let location = try anchorLocation(state, requested)
    switch mode {
    case "copy_binary64":
        return try constructInstance(state, location)
    case "anchor_binary64", "anchor_binary32", "anchor_fixed16":
        let transformed = try location.mapValues { try a3Coordinate($0, mode) }
        let (font, _, reported) = try anchorInstance(state, transformed, "anchor_endpoint_original")
        // Keep the original request as envelope; the exact transformed input is
        // predeclared and checked by the independent native scalar experiment.
        return (font, location, reported)
    case "descriptor_bulk_binary64":
        let font = try alternativeFont(state, location, "descriptor_copy")
        return (font, location, axisNumbers(font))
    case "graphics_binary64":
        let font = try alternativeFont(state, location, "graphics_copy_tracking")
        return (font, location, axisNumbers(font))
    case "descriptor_forward_binary64", "descriptor_reverse_binary64", "copy_cfnumber_float32":
        let font = try a3Alternative(state, location, mode)
        return (font, location, axisNumbers(font))
    default:
        throw OracleError.invalid("a3_constructor_mode_missing_or_unknown")
    }
}

func a3ScalarMain() throws {
    let values = try JSONDecoder().decode([Double].self, from: FileHandle.standardInput.readDataToEndOfFile())
    guard !values.isEmpty, values.count <= 10000 else { throw OracleError.invalid("a3_scalar_count_invalid") }
    var records: [[String: Any]] = []
    for value in values {
        let fixed = try a3FixedInteger(value)
        records.append(["binary64_bits": String(value.bitPattern, radix: 16),
                        "float32_bits": String(Float(value).bitPattern, radix: 16),
                        "float32_value": try a3Coordinate(value, "anchor_binary32"),
                        "fixed16_integer": fixed,
                        "fixed16_value": try a3Coordinate(value, "anchor_fixed16"),
                        "NSNumber_double": inspectNumber(NSNumber(value: value)),
                        "NSNumber_float": inspectNumber(NSNumber(value: Float(value)))])
    }
    try emit(["status": "NATIVE_SCALAR_REPRESENTATIONS_NOT_FONT_ACCEPTANCE",
              "records": records, "CGFloat_bytes": MemoryLayout<CGFloat>.size,
              "Double_bytes": MemoryLayout<Double>.size, "Float_bytes": MemoryLayout<Float>.size,
              "os_version": ProcessInfo.processInfo.operatingSystemVersionString])
}
'''


def make_harness(source: str) -> str:
    if _MARKER in source:
        raise ValueError("a3_refuses_already_generated_harness")
    generated = anchor.make_harness(source)
    prefix, run = generated.split(_RUN)
    original_prefix = source.split(_RUN)[0]
    if not prefix.startswith(original_prefix):
        raise ValueError("a3_production_prefix_not_preserved")
    replacements = (
        ("    let mode = try anchorMode()", "    if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == \"--a3-scalars\" {\n"
         "        try a3ScalarMain(); return\n    }\n    let mode = try a3Mode()"),
        ("    let states = try anchorPrepareStates(locateDescriptors(rawFaces, url: url), mode)",
         "    let states = try anchorPrepareStates(locateDescriptors(rawFaces, url: url), \"production\")"),
        ('"anchor_mode": mode, "diagnostic_readback_observation_only": true,',
         '"a3_mode": mode, "diagnostic_readback_observation_only": true,'),
        ('"NOT_ACCEPTED_diagnostic_anchor_construction_only"', '"NOT_ACCEPTED_A3_input_construction_only"'),
        ("            let (font, location, reported) = try anchorInstance(state, request.location, mode)",
         "            let (font, location, reported) = try a3Instance(state, request.location, mode)"),
    )
    for old, _ in replacements:
        if run.count(old) != 1:
            raise ValueError("a3_review_changed_native_dispatch")
    for old, new in replacements:
        run = run.replace(old, new, 1)
    helpers = _HELPERS.replace("A3_MODES_JSON", json.dumps(MODES)).replace("A3_MODE_ENV", MODE_ENV)
    result = prefix + SCALAR_SWIFT + helpers + _RUN + run
    if not result.startswith(original_prefix) or hashlib.sha256(original_prefix.encode()).hexdigest() != anchor.REVIEWED_PRODUCTION_PREFIX_SHA256:
        raise ValueError("a3_production_prefix_changed")
    return result
