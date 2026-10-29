#!/usr/bin/env python3
"""Execute the production Swift axis validator with original synthetic inputs.

This checks acceptance logic, not CoreText's behavior for an actual font. The
production helpers are compiled verbatim; no independent Python implementation
of the validation condition can grant a native pass.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from compare_axis_construction import GUARD


SWIFT = r'''
func testAxisGuard() throws {
    let axes: [Axis] = [
        Axis(tag: "WDTH", identifier: 0x57445448, minimum: 1, defaultValue: 500, maximum: 1000, flags: 1),
        Axis(tag: "wght", identifier: 0x77676874, minimum: 100, defaultValue: 400, maximum: 900, flags: 0),
        Axis(tag: "HGHT", identifier: 0x48474854, minimum: 1, defaultValue: 500, maximum: 1000, flags: 1)]
    let defaults = Dictionary(uniqueKeysWithValues: axes.map { ($0.tag, $0.defaultValue) })
    var cases: [[String: Any]] = []
    func check(_ name: String, _ location: [String: Double], _ reported: [String: Double], _ expectedError: String?) throws {
        var actualError: String?
        do { try validateReportedAxes(axes, location, reported) }
        catch { actualError = String(describing: error) }
        guard actualError == expectedError else {
            throw OracleError.invalid("axis_guard_case_failed:\(name)")
        }
        cases.append(["case": name, "accepted": actualError == nil, "passed": true])
    }
    try check("omitted_exact_defaults", defaults, [:], nil)
    try check("explicit_exact_defaults", defaults, defaults, nil)
    for axis in axes {
        let expectedError = "coretext_did_not_report_requested_axis_value:\(axis.tag)"
        var omitted = defaults
        omitted.removeValue(forKey: axis.tag)
        for (label, value) in [("next_binary64", axis.defaultValue.nextUp),
                               ("within_epsilon_above", axis.defaultValue + 0.0000005),
                               ("within_epsilon_below", axis.defaultValue - 0.0000005)] {
            var location = defaults
            location[axis.tag] = value
            try check("\(axis.tag)_missing_\(label)", location, omitted, expectedError)
        }
        var location = defaults
        location[axis.tag] = axis.defaultValue + 0.0000005
        try check("\(axis.tag)_explicit_within_unchanged_epsilon", location, defaults, nil)
        location[axis.tag] = axis.defaultValue + 0.000002
        try check("\(axis.tag)_explicit_outside_unchanged_epsilon", location, defaults, expectedError)
        try check("\(axis.tag)_explicit_exact_nondefault", location, location, nil)
    }
    var originalRequest = defaults, originalEcho = defaults
    originalRequest["WDTH"] = 600.5859375
    originalEcho["WDTH"] = 600.5859
    try check("known_decimal4_mismatch_still_rejected", originalRequest, originalEcho,
              "coretext_did_not_report_requested_axis_value:WDTH")
    var missingRequest = defaults
    missingRequest.removeValue(forKey: "WDTH")
    try check("missing_requested_axis_rejected", missingRequest, defaults,
              "coretext_did_not_report_requested_axis_value:WDTH")
    try emit(["status": "PASS_PRODUCTION_SWIFT_VALIDATOR", "case_count": cases.count,
              "cases": cases, "numeric_tolerance": 1e-6, "actual_font_test": false])
}
do { try testAxisGuard() }
catch {
    try? emit(["status": "FAIL", "error": String(describing: error)])
    exit(1)
}
'''


def make_harness(source: str) -> str:
    separator = "\nfunc run() throws {"
    if (source.count(separator) != 1 or source.count(GUARD) != 1
            or source.count("func validateReportedAxes(") != 1
            or source.count("try validateReportedAxes(state.raw.axes, location, reported)") != 1):
        raise ValueError("review_changed_production_axis_validator")
    return source.split(separator)[0] + SWIFT


def run_axis_guard_tests(output: Path) -> dict:
    """Fail if compilation or the actual Swift checks fail; never mark a skip PASS."""
    output.mkdir(parents=True, exist_ok=True)
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise RuntimeError("axis_guard_swiftc_unavailable")
    source = Path(__file__).with_name("coretext_extract.swift").read_text(encoding="utf-8")
    harness = output / "coretext_axis_guard.swift"
    binary = output / "coretext_axis_guard"
    harness.write_text(make_harness(source), encoding="utf-8")
    compiled = subprocess.run([swiftc, "-O", str(harness), "-o", str(binary)],
                              capture_output=True, text=True, timeout=120)
    (output / "axis_guard_compile.log").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
    if compiled.returncode:
        raise RuntimeError("axis_guard_swift_compilation_failed")
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
    (output / "axis_guard_stderr.log").write_text(result.stderr, encoding="utf-8")
    (output / "axis_guard_result.json").write_text(result.stdout, encoding="utf-8")
    if result.returncode:
        raise AssertionError("production_swift_axis_guard_regression_failed")
    summary = json.loads(result.stdout)
    if (summary.get("status") != "PASS_PRODUCTION_SWIFT_VALIDATOR"
            or type(summary.get("case_count")) is not int or summary["case_count"] != 22
            or len(summary.get("cases", [])) != 22
            or not all(row.get("passed") is True for row in summary["cases"])
            or summary.get("numeric_tolerance") != 1e-6
            or summary.get("actual_font_test") is not False):
        raise AssertionError("incomplete_production_swift_axis_guard_result")
    return summary
