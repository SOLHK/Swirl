"""Report Qt XML incidents without counting skipped/private cases as passes.

Only reads reports produced by this build. No font files, settings or secrets
are collected. Lifecycle callbacks are retained but excluded from case totals.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET


def read_cases(path: Path) -> list[dict]:
    root = ET.parse(path).getroot()
    if root.tag != "TestCase":
        raise ValueError(f"{path.name}: expected a Qt XML TestCase")
    cases = []
    for function in root.findall("TestFunction"):
        name = function.get("name", "")
        incidents = function.findall("Incident")
        if not incidents:
            raise ValueError(f"{path.name}: no result for {name}")
        for incident in incidents:
            cases.append({
                "report": path.name,
                "function": name,
                "data": incident.findtext("DataTag", ""),
                "status": incident.get("type", "unknown"),
                "description": incident.findtext("Description", ""),
                "lifecycle": name in {"initTestCase", "cleanupTestCase"},
            })
    if not cases:
        raise ValueError(f"{path.name}: no test results")
    return cases


def summarize(build: Path, require_windows: bool) -> dict:
    reports = ["font-selection.xml", "font-axis-policy.xml"]
    required = [("font-selection.xml", name) for name in (
        "defaultSelectionAndPersistence", "importKeepsOriginalFile",
        "malformedImportPreservesState", "optionalMetadataReplacement",
        "optionalCffImport", "automaticAxesRespectDesignAndDpi",
        "manualProfilesAndAutomaticRestore", "automaticProfilesRestartAcrossProcess",
        "legacyAxisSettingsArePreserved", "automaticAxesProduceRealGlyphsAndFallback",
        "fontCachesAreBoundedAndStable", "displayContextHasBoundedLifecycle",
        "qmlLiveAutomaticFonts", "fontDisplayContextLifetime",
        "previewFontResourcesInvalidateRaster", "previewWindowMetricsAndIdleStability",
        "previewRepeatedAxesReuseResources",
        "automaticWidthUsesRealAdvances",
    )]
    if require_windows:
        reports.append("font-native-raster.xml")
        required.extend(("font-native-raster.xml", name) for name in (
            "nativeGlyphsHaveNoColourFringes", "previewRepeatedAxesReuseResources",
            "automaticWidthUsesRealAdvances",
        ))
    cases, errors = [], []
    for report in reports:
        try:
            cases.extend(read_cases(build / report))
        except (OSError, ET.ParseError, ValueError) as exc:
            errors.append(str(exc))
    for report, name in required:
        matching = [case for case in cases if (case["report"], case["function"]) == (report, name)]
        if not matching or any(case["status"] != "pass" for case in matching):
            errors.append(f"Required case did not pass: {report}/{name}")
    policy_cases = [case for case in cases if case["report"] == "font-axis-policy.xml" and not case["lifecycle"]]
    if not policy_cases or any(case["status"] != "pass" for case in policy_cases):
        errors.append("All independent policy cases must execute and pass")
    # These existing cases need a private local TTC/evidence path or a child
    # process. The Windows native case is separately mandatory in its own run.
    local_only = {"importOptionalPingFangUiCollection", "optionalVariableAxesAndLivePreview",
                  "optionalRestartRead", "optionalRenderMatrix", "optionalNativePointSizes",
                  "optionalPaintedPreviewAxes", "optionalRasterQualityMatrix",
                  "optionalPhysicalFontIdentity",
                  "nativeGlyphsHaveNoColourFringes"}
    for case in cases:
        if case["status"] not in {"pass", "skip"}:
            errors.append(f"{case['report']}/{case['function']}: {case['status']}")
        if case["status"] == "skip" and case["report"] == "font-selection.xml" and case["function"] not in local_only:
            errors.append(f"Unexpected public font case skip: {case['function']}")
    counts = {status: sum(case["status"] == status and not case["lifecycle"] for case in cases)
              for status in ("pass", "skip")}
    return {"schema": 1, "countsExcludingLifecycle": counts, "errors": errors,
            "cases": cases, "physicalDpiVerified": False, "refresh240HzVerified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-windows", action="store_true")
    args = parser.parse_args()
    result = summarize(args.build, args.require_windows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = result["countsExcludingLifecycle"]
    lines = ["## Font test cases", "",
             f"Passed: {counts['pass']}; skipped: {counts['skip']}; report/gate errors: {len(result['errors'])}.",
             "Lifecycle callbacks are excluded. Skipped cases are not passes.", "",
             "### Skipped cases", ""]
    skipped = [case for case in result["cases"] if case["status"] == "skip"]
    lines += [f"- {case['report']}/{case['function']}: {case['description']}" for case in skipped] or ["None."]
    if result["errors"]:
        lines += ["", "### Errors", ""] + [f"- {error}" for error in result["errors"]]
    lines += ["", "Hosted Qt/D3D11 checks do not verify a physical Windows 11 display, cross-monitor DPI transitions, or 240 Hz performance.", ""]
    summary = "\n".join(lines)
    print(summary)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(path).open("a", encoding="utf-8") as stream:
            stream.write(summary)
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
