#!/usr/bin/env python3
"""Locate native metric quantization without changing the original strict gate.

This experiment uses only the self-authored two-face fixture. It compares its
gvar-only encoding, the production HVAR/VVAR writer, and the already verified
diagnostic side-bearing maps. The same original glyphs are measured at several
point sizes and through direct CoreText and single-glyph CTRun APIs. Changing a
measurement point size does not change or scale any stored font coordinates.
All raw values and source-unit comparisons are retained. None is corrected,
rounded back, substituted into rebuild.py, or called native font acceptance.

Primary references consulted before implementation:
https://developer.apple.com/documentation/coretext/ctfontgetadvancesforglyphs(_:_:_:_:_:)
https://developer.apple.com/documentation/coretext/ctrungetadvances(_:_:_:)
https://learn.microsoft.com/en-us/typography/opentype/spec/vvar
https://github.com/google/skia/blob/main/src/ports/SkScalerContext_mac_ct.h
https://github.com/harfbuzz/harfbuzz/blob/main/src/hb-coretext-font.cc
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from fontTools.ttLib import TTCollection

from compare_axis_construction import GUARD
from diagnose_coretext_metrics import (
    ideal_metrics, make_metric_fixture, verify_metric_fixture,
)
from test_coretext_extract import make_fixture, native_requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from metric_variations import add_metric_variations, verify_metric_variations

LIMIT = 1 / 32
SCALES = (0.25, 1., 16., 64.)
FIELDS = ("advance_width", "advance_height", "vertical_origin_x", "vertical_origin_y")

SWIFT = r'''
func precisionAxes(_ font: CTFont) -> [String: Double] {
    var values: [String: Double] = [:]
    if let axes = CTFontCopyVariation(font) as? [NSNumber: NSNumber] {
        for (key, value) in axes { values[tagString(key.uint32Value)] = value.doubleValue }
    }
    return values
}

func precisionIdentity(_ font: CTFont, _ state: FaceState,
                       _ location: [String: Double], _ size: Double) throws {
    _ = try verifyIdentity(font, state.raw, allTables: true)
    guard CTFontGetMatrix(font).isIdentity, Double(CTFontGetSize(font)) == size else {
        throw OracleError.invalid("measurement_font_size_or_matrix_changed")
    }
    let values = precisionAxes(font)
    for axis in state.raw.axes {
        guard abs((values[axis.tag] ?? axis.defaultValue) - location[axis.tag]!) <= 1e-6 else {
            throw OracleError.invalid("measurement_font_axis_changed")
        }
    }
}

func precisionDirect(_ font: CTFont, _ gid: Int) throws -> [String: Any] {
    var glyph = CGGlyph(gid)
    var horizontal = CGSize.zero, vertical = CGSize.zero, origin = CGSize.zero
    let hsum = CTFontGetAdvancesForGlyphs(font, .horizontal, &glyph, &horizontal, 1)
    let vsum = CTFontGetAdvancesForGlyphs(font, .vertical, &glyph, &vertical, 1)
    CTFontGetVerticalTranslationsForGlyphs(font, &glyph, &origin, 1)
    let raw = [Double(horizontal.width), Double(horizontal.height),
               Double(vertical.width), Double(vertical.height),
               Double(origin.width), Double(origin.height), hsum, vsum]
    guard raw.allSatisfy(\.isFinite) else { throw OracleError.invalid("nonfinite_direct_metric") }
    return ["advance_width": Double(horizontal.width), "advance_height": Double(vertical.width),
            "vertical_origin_x": -Double(origin.width), "vertical_origin_y": -Double(origin.height),
            "horizontal_vector": [Double(horizontal.width), Double(horizontal.height)],
            "vertical_vector": [Double(vertical.width), Double(vertical.height)],
            "translation_vector": [Double(origin.width), Double(origin.height)],
            "horizontal_sum": hsum, "vertical_sum": vsum]
}

func precisionRun(_ font: CTFont, _ state: FaceState, _ location: [String: Double],
                  _ gid: Int, _ vertical: Bool) throws -> [String: Any] {
    // Only these two glyphs have nominal characters in the original fixture.
    // .notdef is still measured by precisionDirect; never force fallback text.
    guard gid == 1 || gid == 2 else { return ["status": "NO_NOMINAL_FIXTURE_CHARACTER"] }
    let attributes: [String: Any] = [kCTFontAttributeName as String: font,
        kCTVerticalFormsAttributeName as String: vertical, kCTKernAttributeName as String: 0]
    guard let text = CFAttributedStringCreate(nil, (gid == 1 ? " " : "A") as CFString,
                                             attributes as CFDictionary) else {
        throw OracleError.invalid("fixture_attributed_string_failed")
    }
    let line = CTLineCreateWithAttributedString(text)
    guard let runs = CTLineGetGlyphRuns(line) as? [CTRun], runs.count == 1,
          CTRunGetGlyphCount(runs[0]) == 1 else { throw OracleError.invalid("fixture_run_count_changed") }
    let run = runs[0]
    var glyph = CGGlyph(0), advance = CGSize.zero, position = CGPoint.zero
    CTRunGetGlyphs(run, CFRange(location: 0, length: 1), &glyph)
    guard Int(glyph) == gid else { throw OracleError.invalid("fixture_run_substitution_or_fallback") }
    let runAttributes = CTRunGetAttributes(run) as NSDictionary
    guard let runFontValue = runAttributes[kCTFontAttributeName] else {
        throw OracleError.invalid("fixture_run_font_missing")
    }
    let runFont = runFontValue as! CTFont
    try precisionIdentity(runFont, state, location, Double(CTFontGetSize(font)))
    CTRunGetAdvances(run, CFRange(location: 0, length: 1), &advance)
    CTRunGetPositions(run, CFRange(location: 0, length: 1), &position)
    let width = CTRunGetTypographicBounds(run, CFRange(location: 0, length: 1), nil, nil, nil)
    let matrix = CTRunGetTextMatrix(run)
    let values = [Double(advance.width), Double(advance.height), Double(position.x),
                  Double(position.y), width, Double(matrix.a), Double(matrix.b),
                  Double(matrix.c), Double(matrix.d), Double(matrix.tx), Double(matrix.ty)]
    guard values.allSatisfy(\.isFinite) else { throw OracleError.invalid("nonfinite_run_metric") }
    return ["status": "MEASURED", "advance_vector": [Double(advance.width), Double(advance.height)],
            "advance_magnitude": hypot(Double(advance.width), Double(advance.height)),
            "position": [Double(position.x), Double(position.y)], "typographic_width": width,
            "text_matrix": [Double(matrix.a), Double(matrix.b), Double(matrix.c), Double(matrix.d),
                            Double(matrix.tx), Double(matrix.ty)], "glyph_id": Int(glyph),
            "exact_source_face_axes_and_point_size_verified": true]
}

func precisionMain() throws {
    guard CommandLine.arguments.count == 2 else { throw OracleError.invalid("font_argument_required") }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let data = try Data(contentsOf: url, options: [.mappedIfSafe])
    let allowed: Set<String> = ALLOWED_SYNTHETIC_HASHES
    guard allowed.contains(sha256(data)) else { throw OracleError.invalid("generated_synthetic_fonts_only") }
    let states = try locateDescriptors(parseFaces(Bytes(data: data)), url: url)
    guard states.count == 2, states.allSatisfy({ $0.baseFont != nil && $0.raw.glyphCount == 3 }) else {
        throw OracleError.invalid("both_synthetic_physical_faces_required")
    }
    let input = FileHandle.standardInput.readDataToEndOfFile()
    let requests = try JSONDecoder().decode([Request].self, from: input)
    guard requests.count == 58 else { throw OracleError.invalid("unchanged_fixture_request_count_required") }
    try emit(["type": "metadata", "backend": "CoreText", "source_sha256": sha256(data),
              "physical_faces": states.count, "synthetic_only": true,
              "point_size_scales": PRECISION_SCALES])
    for request in requests {
        try autoreleasepool {
            guard request.face_index >= 0, request.face_index < states.count,
                  request.glyph_ids == [0, 1, 2] else { throw OracleError.invalid("bad_synthetic_request") }
            let state = states[request.face_index]
            let (base, location, _) = try makeInstance(state, request.location)
            let scales: [Double] = PRECISION_SCALES
            for scale in scales {
                let size = Double(state.raw.upm) * scale
                var matrix = CGAffineTransform.identity
                let font = scale == 1 ? base : CTFontCreateCopyWithAttributes(base, CGFloat(size), &matrix, nil)
                try precisionIdentity(font, state, location, size)
                for gid in request.glyph_ids {
                    var row: [String: Any] = ["request_id": request.request_id, "face_index": request.face_index,
                        "location": location, "glyph_id": gid, "scale": scale, "upm": state.raw.upm,
                        "point_size": size, "direct": try precisionDirect(font, gid)]
                    for (name, vertical) in [("run_horizontal", false), ("run_vertical", true)] {
                        do { row[name] = try precisionRun(font, state, location, gid, vertical) }
                        catch { row[name] = ["status": "API_ERROR", "error": String(describing: error)] }
                    }
                    try emit(row)
                }
            }
        }
    }
}
do { try precisionMain() }
catch { stderr("Synthetic metric precision diagnosis: \(error)"); exit(2) }
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def make_harness(source, hashes):
    separator = "\nfunc run() throws {"
    require(source.count(separator) == 1 and source.count(GUARD) == 1,
            "production helper structure changed; review before reuse")
    require(len(hashes) == 3 and len(set(hashes)) == 3 and all(
        len(value) == 64 and all(c in "0123456789abcdef" for c in value) for value in hashes),
        "three exact generated fixture hashes required")
    # Unlike the malformed-avar diagnostic, this fixture experiment keeps the
    # production axis guard verbatim. It cannot admit a substituted axis value.
    return source.split(separator)[0] + SWIFT.replace(
        "ALLOWED_SYNTHETIC_HASHES", json.dumps(hashes)).replace("PRECISION_SCALES", json.dumps(SCALES))


def make_production_fixture(source, output):
    with TTCollection(source) as collection:
        for font in collection.fonts:
            add_metric_variations(font)
            font.recalcTimestamp = False
        collection.save(output, shareTables=True)
    with TTCollection(output) as saved:
        return [verify_metric_variations(font) for font in saved.fonts]


def analyze_rows(rows, requests):
    """Require every original fixture glyph at every scale; never omit a field."""
    expected = {(q["request_id"], gid, scale): q for q in requests
                for gid in q["glyph_ids"] for scale in SCALES}
    require(len(rows) == len(expected), "native measurement count differs")
    seen, observations, summaries = set(), [], {}
    for row in rows:
        key = (row.get("request_id"), row.get("glyph_id"), row.get("scale"))
        require(key in expected and key not in seen, "duplicate or unrelated native measurement")
        seen.add(key)
        request = expected[key]
        face, scale, gid = row["face_index"], row["scale"], row["glyph_id"]
        require(face == request["face_index"] and row["location"] == request["location"],
                "native response identity changed")
        require(row["upm"] == (1000, 1128)[face] and row["point_size"] == row["upm"] * scale,
                "native source UPEM or measurement point size changed")
        wanted = ideal_metrics(request["location"], gid)
        direct = row["direct"]
        require(all(field in direct and isinstance(direct[field], (int, float))
                    and math.isfinite(direct[field]) for field in FIELDS), "missing/nonfinite native metric")
        actual = {field: direct[field] / scale for field in FIELDS}
        errors = {field: actual[field] - wanted[field] for field in FIELDS}
        summary = summaries.setdefault(str(scale), {"glyph_observations": 0,
            "direct_glyphs_outside_original_budget": 0, "max_direct_error_by_field": {},
            "run_api_errors": 0, "run_measurements": 0, "max_run_advance_error": {}})
        summary["glyph_observations"] += 1
        summary["direct_glyphs_outside_original_budget"] += any(abs(x) > LIMIT for x in errors.values())
        for field, error in errors.items():
            summary["max_direct_error_by_field"][field] = max(
                summary["max_direct_error_by_field"].get(field, 0.), abs(error))
        item = {**row, "direct_source_font_units": actual, "signed_direct_error_font_units": errors}
        for name, field in (("run_horizontal", "advance_width"), ("run_vertical", "advance_height")):
            run = row[name]
            if gid == 0:
                require(run.get("status") == "NO_NOMINAL_FIXTURE_CHARACTER", "unexpected notdef run")
            elif run.get("status") == "API_ERROR":
                require(bool(run.get("error")), "missing native run failure detail")
                summary["run_api_errors"] += 1
            else:
                require(run.get("status") == "MEASURED" and run.get("glyph_id") == gid
                        and run.get("exact_source_face_axes_and_point_size_verified") is True,
                        "unverified run font or substituted glyph")
                value = run["advance_magnitude"]
                require(isinstance(value, (int, float)) and math.isfinite(value), "nonfinite run advance")
                error = value / scale - wanted[field]
                item[name + "_source_advance_error"] = error
                summary["run_measurements"] += 1
                summary["max_run_advance_error"][name] = max(
                    summary["max_run_advance_error"].get(name, 0.), abs(error))
        observations.append(item)
    require(seen == set(expected), "missing native metric measurement")
    return {"observations": observations, "by_point_size_scale": summaries}


def run(output, require_native=False):
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "coretext_precision_diagnosis.json"
    require(not report_path.exists(), "choose a new diagnostic output directory")
    report = {"status": "NOT_RUN", "platform": platform.platform(),
        "data_origin": "self_authored_synthetic_fonts_only_no_Apple_data",
        "analytical_tolerance_font_units": LIMIT, "production_oracle_modified": False,
        "original_strict_gate_replaced": False, "font_coordinate_scaling": False,
        "native_font_acceptance": "NOT_ESTABLISHED", "point_size_scales": SCALES,
        "variants": {}}
    result_code = 1
    try:
        with tempfile.TemporaryDirectory(prefix="coretext-precision-", dir=output) as temporary:
            root = Path(temporary)
            fixtures = {name: root / (name + ".ttc") for name in (
                "gvar_only", "production_hvar_vvar", "diagnostic_bearing_maps")}
            make_fixture(fixtures["gvar_only"])
            report["production_metric_equivalence"] = make_production_fixture(
                fixtures["gvar_only"], fixtures["production_hvar_vvar"])
            make_metric_fixture(fixtures["gvar_only"], fixtures["diagnostic_bearing_maps"])
            report["diagnostic_metric_equivalence"] = verify_metric_fixture(
                fixtures["gvar_only"], fixtures["diagnostic_bearing_maps"])
            hashes = {name: digest(path) for name, path in fixtures.items()}
            report["fixture_sha256"] = hashes
            source = Path(__file__).with_name("coretext_extract.swift").read_text(encoding="utf-8")
            code = make_harness(source, list(hashes.values()))
            report["production_helper_sha256"] = hashlib.sha256(source.encode()).hexdigest()
            if sys.platform != "darwin":
                report["reason"] = "CoreText unavailable; only standard fixture equivalence checked."
                result_code = 2 if require_native else 0
            else:
                swift, binary = root / "precision.swift", root / "precision"
                swift.write_text(code, encoding="utf-8")
                compiled = subprocess.run(["xcrun", "swiftc", "-O", str(swift), "-o", str(binary)],
                                          capture_output=True, text=True, timeout=180)
                (output / "precision_compile.log").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
                require(compiled.returncode == 0, "native precision harness compilation failed")
                requests = native_requests()
                for name, path in fixtures.items():
                    native = subprocess.run([str(binary), str(path)], input=json.dumps(requests),
                                            capture_output=True, text=True, timeout=180)
                    (output / (name + ".jsonl")).write_text(native.stdout, encoding="utf-8")
                    (output / (name + ".stderr.log")).write_text(native.stderr, encoding="utf-8")
                    require(native.returncode == 0, f"{name}: native precision measurement failed")
                    records = [json.loads(line) for line in native.stdout.splitlines()]
                    require(records and records[0].get("type") == "metadata"
                            and records[0].get("backend") == "CoreText"
                            and records[0].get("source_sha256") == hashes[name]
                            and records[0].get("synthetic_only") is True
                            and records[0].get("physical_faces") == 2
                            and records[0].get("point_size_scales") == list(SCALES),
                            "native metadata identity differs")
                    report["variants"][name] = analyze_rows(records[1:], requests)
                    require(digest(path) == hashes[name], "generated source changed during native run")
                report["status"] = "DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE"
                result_code = 0
        report["temporary_synthetic_fonts_removed"] = True
    except Exception as error:
        report["status"] = "DIAGNOSTIC_ERROR"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        with report_path.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps({"status": report["status"], "report": str(report_path),
        "variants": {name: data["by_point_size_scale"] for name, data in report["variants"].items()}}))
    return result_code


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-native", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(run(arguments.output.resolve(), arguments.require_native))
