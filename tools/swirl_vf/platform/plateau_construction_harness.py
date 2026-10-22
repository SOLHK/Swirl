"""Build a private, diagnostic CoreText construction-path observation harness.

The generated program retains the production JSON-lines transport, source
identity checks, extraction, and EOF accounting.  Its five construction paths
observe raw readbacks and payloads; none is an accepted rebuild oracle.  Public
reports must be produced by a separate driver that retains no glyph commands.

The alternate public-API helpers are reused verbatim from the existing native
construction comparison.  In particular, an alternate request never constructs
a production baseline first: doing so would confound a cache/state experiment.
"""
from __future__ import annotations

import json

from compare_axis_construction import EXPECTED, GUARD, SWIFT as CONSTRUCTION_SWIFT


MODES = ("production", "descriptor_copy", "graphics_copy_tracking",
         "rebase_300", "rebase_500")
MODE_ENV = "SWIRL_VF_PLATEAU_MODE"

_MARKER = "// SWIRL_VF_PLATEAU_CONSTRUCTION_DIAGNOSTIC"
_RUN = "\nfunc run() throws {"
_COMPARISON_MAIN = "\nfunc compareConstructionMain() throws {"

_HELPERS = r'''
// SWIRL_VF_PLATEAU_CONSTRUCTION_DIAGNOSTIC
// Observation only. This executable must never be supplied to rebuild.py.
func plateauMode() throws -> String {
    let allowed = Set(PLATEAU_MODES_JSON)
    guard let mode = ProcessInfo.processInfo.environment["PLATEAU_MODE_ENV"],
          allowed.contains(mode) else {
        throw OracleError.invalid("plateau_mode_missing_or_unknown")
    }
    return mode
}

func plateauLocation(_ state: FaceState, _ requested: [String: Double]) throws -> [String: Double] {
    let axisTags = Set(state.raw.axes.map(\.tag))
    guard requested.keys.allSatisfy({ axisTags.contains($0) }) else {
        throw OracleError.invalid("unknown_axis_tag")
    }
    var location: [String: Double] = [:]
    for axis in state.raw.axes {
        let value = requested[axis.tag] ?? axis.defaultValue
        guard value.isFinite, value >= axis.minimum, value <= axis.maximum else {
            throw OracleError.invalid("axis_value_out_of_source_range:\(axis.tag)")
        }
        location[axis.tag] = value
    }
    return location
}

func plateauPrepareStates(_ originals: [FaceState], _ mode: String) throws -> [FaceState] {
    guard originals.count == 32, originals.allSatisfy({ $0.baseFont != nil }) else {
        throw OracleError.invalid("plateau_all_original_faces_required")
    }
    return try originals.map { original in
        guard let base = original.baseFont else {
            throw OracleError.invalid("plateau_missing_original_base")
        }
        var metadata = original.metadata
        metadata["plateau_mode"] = mode
        metadata["plateau_original_base_axes"] = axisNumbers(base)
        metadata["plateau_original_base_name"] = CTFontCopyPostScriptName(base) as String
        metadata["plateau_original_base_size"] = Double(CTFontGetSize(base))
        var seeded = base
        if mode == "rebase_300" || mode == "rebase_500" {
            var location = Dictionary(uniqueKeysWithValues: original.raw.axes.map { ($0.tag, $0.defaultValue) })
            location["wght"] = mode == "rebase_300" ? 300.0 : 500.0
            let (font, _, _) = try constructInstance(original, location)
            _ = try verifyIdentity(font, original.raw, allTables: true)
            seeded = font
        }
        metadata["plateau_seeded_base_axes"] = axisNumbers(seeded)
        metadata["plateau_seeded_base_name"] = CTFontCopyPostScriptName(seeded) as String
        metadata["plateau_seeded_base_size"] = Double(CTFontGetSize(seeded))
        return FaceState(raw: original.raw, baseFont: seeded, metadata: metadata)
    }
}

func plateauInstance(_ state: FaceState, _ requested: [String: Double], _ mode: String) throws -> (CTFont, [String: Double], [String: Double]) {
    switch mode {
    case "production", "rebase_300", "rebase_500":
        return try constructInstance(state, requested)
    case "descriptor_copy", "graphics_copy_tracking":
        // Validation does not create a font or measure a production baseline.
        let location = try plateauLocation(state, requested)
        let font = try alternativeFont(state, location, mode)
        return (font, location, axisNumbers(font))
    default:
        throw OracleError.invalid("plateau_mode_missing_or_unknown")
    }
}
'''


def make_harness(source: str) -> str:
    """Return generated Swift, failing closed if any production anchor changed.

    Select exactly one mode through :data:`MODE_ENV` for each native process.
    The only command-line argument is the original font path.  The unchanged
    NativeOracle request and summary protocol is used on stdin/stdout.
    """
    if (_MARKER in source or source.count(_RUN) != 1 or source.count(GUARD) != 1
            or CONSTRUCTION_SWIFT.count(_COMPARISON_MAIN) != 1):
        raise ValueError("review_changed_plateau_production_helpers")
    prefix, run = source.split(_RUN)
    helpers = CONSTRUCTION_SWIFT.split(_COMPARISON_MAIN)[0]
    for signature in ("func constructInstance(", "func makeInstance(",
                      "func locateDescriptors(", "func validateReportedAxes("):
        if prefix.count(signature) != 1 or source.count(signature) != 1:
            raise ValueError("review_changed_plateau_production_helpers")
    for signature in ("func axisNumbers(", "func namedAxes(", "func alternativeFont("):
        if helpers.count(signature) != 1 or signature in source:
            raise ValueError("review_changed_plateau_construction_helpers")

    replacements = (
        ('    let observationsOnly = CommandLine.arguments.count == 3 && CommandLine.arguments[2] == "--axis-observations"\n'
         '    guard CommandLine.arguments.count == 2 || observationsOnly else {\n'
         '        throw OracleError.invalid("usage: coretext_extract /path/font.ttc [--axis-observations] < requests.jsonl > private_oracle.jsonl")\n'
         '    }',
         '    let mode = try plateauMode()\n'
         '    guard CommandLine.arguments.count == 2 else {\n'
         '        throw OracleError.invalid("plateau_requires_source_path_only")\n'
         '    }'),
        ('    let data = try Data(contentsOf: url, options: [.mappedIfSafe])',
         '    let data = try Data(contentsOf: url, options: [.mappedIfSafe])\n'
         f'    guard sha256(data) == "{EXPECTED}" else {{\n'
         '        throw OracleError.invalid("plateau_wrong_original_source")\n'
         '    }'),
        ('    let states = try locateDescriptors(rawFaces, url: url)',
         '    let states = try plateauPrepareStates(locateDescriptors(rawFaces, url: url), mode)'),
        ('              "axis_observations_only": observationsOnly,',
         '              "plateau_mode": mode, "diagnostic_readback_observation_only": true,\n'
         '              "axis_observations_only": false,'),
        ('              "axis_observation_acceptance": observationsOnly ? "NOT_ACCEPTED_requires_independent_per_request_verification" : "strict_reported_coordinate_check",',
         '              "axis_observation_acceptance": "NOT_ACCEPTED_diagnostic_construction_comparison_only",'),
        ('              "axis_policy": "all source fvar user axes set explicitly; effective reported coordinates checked; no manual avar interpretation",',
         '              "axis_policy": "all source fvar user axes set explicitly; readbacks observed without acceptance; no manual avar interpretation",'),
        ('            let (font, location, reported) = try (observationsOnly\n'
         '                ? constructInstance(state, request.location) : makeInstance(state, request.location))',
         '            let (font, location, reported) = try plateauInstance(state, request.location, mode)'),
    )
    # Check every anchor against the original text before changing any of it.
    for old, _ in replacements:
        if source.count(old) != 1 or run.count(old) != 1:
            raise ValueError("review_changed_plateau_run_anchor")
    for old, new in replacements:
        run = run.replace(old, new, 1)
    if "observationsOnly" in run:
        raise ValueError("review_changed_plateau_observation_protocol")
    diagnostic = _HELPERS.replace("PLATEAU_MODES_JSON", json.dumps(MODES))
    diagnostic = diagnostic.replace("PLATEAU_MODE_ENV", MODE_ENV)
    return prefix + helpers + diagnostic + _RUN + run
