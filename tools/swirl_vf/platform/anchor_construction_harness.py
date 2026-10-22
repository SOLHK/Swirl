"""Generate an observation-only two-hop CoreText axis construction experiment.

The reviewed production prefix, constructor, validator, identity checks and
glyph extraction remain byte-for-byte unchanged. The plateau generator supplies
the already-tested transport adaptation and public-API helpers. This variant
replaces only its diagnostic dispatcher with predeclared, distant full-axis
anchors. No observed coordinate feeds a retry or chooses the target request.

This harness is NOT_ACCEPTED as a production/rebuild oracle. Native compilation
and original-font behavior require separate CI execution; generator tests alone
cannot establish either result.
"""
from __future__ import annotations

import hashlib
import json

import plateau_construction_harness as plateau


MODES = ("production", "anchor_endpoint_original", "anchor_endpoint_300",
         "anchor_endpoint_500", "anchor_quarter_original")
MODE_ENV = "SWIRL_VF_ANCHOR_MODE"

# Bind the exact reviewed production helpers. A later prefix change requires an
# explicit source review and a corresponding update, not silent diagnostic drift.
REVIEWED_PRODUCTION_PREFIX_SHA256 = "3f08090f15e7fb7d69e1c63516d129a4b066e7e4f5f6bfb4c8645b561c31e792"
_RUN = "\nfunc run() throws {"
_MARKER = "// SWIRL_VF_ANCHOR_CONSTRUCTION_DIAGNOSTIC"
_PLATEAU_MARKER = "// SWIRL_VF_PLATEAU_CONSTRUCTION_DIAGNOSTIC"


# Pure scalar logic, kept in its own source fragment so native CI can execute
# the exact helper with original synthetic ranges without opening any font.
COORDINATE_SWIFT = r'''
func anchorCoordinate(_ target: Double, _ minimum: Double, _ maximum: Double, _ quarter: Bool) throws -> Double {
    let span = maximum - minimum
    guard target.isFinite, minimum.isFinite, maximum.isFinite, span.isFinite,
          span > 0, target >= minimum, target <= maximum else {
        throw OracleError.invalid("invalid_anchor_axis_range_or_target")
    }
    let midpoint = minimum + span * 0.5
    let value: Double
    if target <= midpoint {
        value = quarter ? minimum + span * 0.75 : maximum
    } else {
        value = quarter ? minimum + span * 0.25 : minimum
    }
    let separation = span * (quarter ? 0.25 : 0.5)
    guard value.isFinite, value >= minimum, value <= maximum,
          abs(value - target) >= separation else {
        throw OracleError.invalid("anchor_not_inside_source_range_or_not_distant")
    }
    return value
}
'''


_HELPERS = r'''
// Observation only. This executable must never be supplied to rebuild.py.
func anchorMode() throws -> String {
    let allowed = Set(ANCHOR_MODES_JSON)
    guard let mode = ProcessInfo.processInfo.environment["ANCHOR_MODE_ENV"],
          allowed.contains(mode) else {
        throw OracleError.invalid("anchor_mode_missing_or_unknown")
    }
    return mode
}

func anchorOpticalMetadata(_ font: CTFont) throws -> Any {
    guard let value = (CTFontCopyAttribute(font, kCTFontOpticalSizeAttribute) as? NSNumber)?.doubleValue else {
        return NSNull()
    }
    guard value.isFinite else { throw OracleError.invalid("anchor_nonfinite_optical_attribute") }
    return value
}

func anchorExpectedOptical(_ baseFont: CTFont, _ location: [String: Double]) throws -> Double {
    // These two expressions are the unchanged production constructor's rule.
    let baseOpticalSize = (CTFontCopyAttribute(baseFont, kCTFontOpticalSizeAttribute) as? NSNumber)?.doubleValue
    let opticalSize = location["opsz"] ?? ((baseOpticalSize ?? 0) > 0 ? baseOpticalSize! : Double(CTFontGetSize(baseFont)))
    guard opticalSize.isFinite, opticalSize > 0 else {
        throw OracleError.invalid("anchor_expected_optical_attribute_invalid")
    }
    return opticalSize
}

func anchorRequireOptical(_ font: CTFont, _ expected: Double) throws {
    guard expected.isFinite,
          let actual = (CTFontCopyAttribute(font, kCTFontOpticalSizeAttribute) as? NSNumber)?.doubleValue,
          actual.isFinite, actual == expected else {
        throw OracleError.invalid("anchor_optical_inheritance_mismatch")
    }
}

func anchorRequireReadback(_ axes: [Axis], _ planned: [String: Double], _ reported: [String: Double]) throws {
    let tags = Set(axes.map(\.tag))
    guard Set(planned.keys) == tags, reported.keys.allSatisfy({ tags.contains($0) }) else {
        throw OracleError.invalid("anchor_axis_identity_mismatch")
    }
    for axis in axes {
        guard let expected = planned[axis.tag], expected.isFinite,
              expected >= axis.minimum, expected <= axis.maximum,
              (reported[axis.tag] != nil || expected == axis.defaultValue) else {
            throw OracleError.invalid("anchor_nondefault_axis_not_reported")
        }
        let effective = reported[axis.tag] ?? axis.defaultValue
        guard effective.isFinite, effective == expected else {
            throw OracleError.invalid("anchor_readback_not_exactly_predeclared")
        }
    }
}

func anchorPrepareStates(_ originals: [FaceState], _ mode: String) throws -> [FaceState] {
    guard originals.count == 32, originals.allSatisfy({ $0.baseFont != nil }) else {
        throw OracleError.invalid("anchor_all_original_faces_required")
    }
    return try originals.map { original in
        guard let base = original.baseFont else {
            throw OracleError.invalid("anchor_missing_original_base")
        }
        var metadata = original.metadata
        metadata["anchor_mode"] = mode
        metadata["anchor_original_base_axes"] = axisNumbers(base)
        metadata["anchor_original_base_name"] = CTFontCopyPostScriptName(base) as String
        metadata["anchor_original_base_size"] = Double(CTFontGetSize(base))
        metadata["anchor_original_base_optical"] = try anchorOpticalMetadata(base)
        metadata["anchor_seed_requested_location"] = NSNull()
        var seeded = base
        if mode == "anchor_endpoint_300" || mode == "anchor_endpoint_500" {
            var location = Dictionary(uniqueKeysWithValues: original.raw.axes.map { ($0.tag, $0.defaultValue) })
            location["wght"] = mode == "anchor_endpoint_300" ? 300.0 : 500.0
            let expectedOptical = try anchorExpectedOptical(base, location)
            let (font, _, _) = try constructInstance(original, location)
            _ = try verifyIdentity(font, original.raw, allTables: true)
            try anchorRequireOptical(font, expectedOptical)
            seeded = font
            metadata["anchor_seed_requested_location"] = location
        }
        metadata["anchor_seeded_base_axes"] = axisNumbers(seeded)
        metadata["anchor_seeded_base_name"] = CTFontCopyPostScriptName(seeded) as String
        metadata["anchor_seeded_base_size"] = Double(CTFontGetSize(seeded))
        metadata["anchor_seeded_base_optical"] = try anchorOpticalMetadata(seeded)
        return FaceState(raw: original.raw, baseFont: seeded, metadata: metadata)
    }
}

func anchorInstance(_ state: FaceState, _ requested: [String: Double], _ mode: String) throws -> (CTFont, [String: Double], [String: Double]) {
    if mode == "production" {
        return try constructInstance(state, requested)
    }
    guard mode == "anchor_endpoint_original" || mode == "anchor_endpoint_300"
          || mode == "anchor_endpoint_500" || mode == "anchor_quarter_original" else {
        throw OracleError.invalid("anchor_mode_missing_or_unknown")
    }
    // Validate the target before constructing a font. Every anchor coordinate
    // depends only on the original range and target, never on a native echo.
    let location = try anchorLocation(state, requested)
    guard let base = state.baseFont else { throw OracleError.invalid("anchor_missing_original_base") }
    var planned: [String: Double] = [:]
    let quarter = mode == "anchor_quarter_original"
    for axis in state.raw.axes {
        guard let value = location[axis.tag] else { throw OracleError.invalid("anchor_target_axis_missing") }
        planned[axis.tag] = try anchorCoordinate(value, axis.minimum, axis.maximum, quarter)
    }
    let firstOptical = try anchorExpectedOptical(base, planned)
    let (anchor, _, anchorReported) = try constructInstance(state, planned)
    try anchorRequireReadback(state.raw.axes, planned, anchorReported)
    try anchorRequireOptical(anchor, firstOptical)
    // No cached previous request, no readback feedback, no retry or fallback.
    let anchored = FaceState(raw: state.raw, baseFont: anchor, metadata: state.metadata)
    let secondOptical = try anchorExpectedOptical(anchor, location)
    let result = try constructInstance(anchored, location)
    try anchorRequireOptical(result.0, secondOptical)
    return result
}
'''


def make_harness(source: str) -> str:
    """Adapt the reviewed plateau harness with strictly checked unique anchors."""
    if _MARKER in source or _PLATEAU_MARKER in source or source.count(_RUN) != 1:
        raise ValueError("review_changed_anchor_production_prefix")
    production_prefix = source.split(_RUN)[0]
    if hashlib.sha256(production_prefix.encode()).hexdigest() != REVIEWED_PRODUCTION_PREFIX_SHA256:
        raise ValueError("review_changed_anchor_production_prefix")
    generated = plateau.make_harness(source)
    if generated.count(_RUN) != 1 or generated.count(_PLATEAU_MARKER) != 1:
        raise ValueError("review_changed_anchor_plateau_helpers")
    prefix, run = generated.split(_RUN)
    helpers_prefix, helpers = prefix.split(_PLATEAU_MARKER)
    if not helpers_prefix.startswith(production_prefix):
        raise ValueError("review_changed_anchor_production_prefix")
    start, end = "\nfunc plateauLocation(", "\nfunc plateauPrepareStates("
    if (generated.count(start) != 1 or generated.count(end) != 1
            or helpers.count(start) != 1 or helpers.count(end) != 1):
        raise ValueError("review_changed_anchor_location_helper")
    location = start + helpers.split(start)[1].split(end)[0]
    location = location.replace("func plateauLocation(", "func anchorLocation(", 1)
    replacements = (
        ("    let mode = try plateauMode()", "    let mode = try anchorMode()"),
        ('"plateau_requires_source_path_only"', '"anchor_requires_source_path_only"'),
        ('"plateau_wrong_original_source"', '"anchor_wrong_original_source"'),
        ("    let states = try plateauPrepareStates(locateDescriptors(rawFaces, url: url), mode)",
         "    let states = try anchorPrepareStates(locateDescriptors(rawFaces, url: url), mode)"),
        ('"plateau_mode": mode', '"anchor_mode": mode'),
        ('"NOT_ACCEPTED_diagnostic_construction_comparison_only"',
         '"NOT_ACCEPTED_diagnostic_anchor_construction_only"'),
        ("            let (font, location, reported) = try plateauInstance(state, request.location, mode)",
         "            let (font, location, reported) = try anchorInstance(state, request.location, mode)"),
    )
    for old, _ in replacements:
        if run.count(old) != 1:
            raise ValueError("review_changed_anchor_run_anchor")
    for old, new in replacements:
        run = run.replace(old, new, 1)
    diagnostic = _HELPERS.replace("ANCHOR_MODES_JSON", json.dumps(MODES))
    diagnostic = diagnostic.replace("ANCHOR_MODE_ENV", MODE_ENV)
    return helpers_prefix + _MARKER + "\n" + location + COORDINATE_SWIFT + diagnostic + _RUN + run
