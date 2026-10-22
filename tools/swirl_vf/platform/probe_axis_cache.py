#!/usr/bin/env python3
"""Observe request order, numeric bridges, and readback-created native instances.

Each order begins in a fresh native process. All original requests are observed
before any readback-coordinate reconstruction, so those reconstructions cannot
prime the first phase's instance cache. Paths and metric vectors stay in native
memory; reports contain axis numbers, counts and maximum discrepancies only.
This experiment does not change or replace the production axis acceptance gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile

import compare_axis_construction as construction

ORDERS = ("forward_first", "reverse_first")
FACES = (20, 31)
GIDS = (0, 3, 5, 56, 498, 600)


def request_specs(order: str) -> list[dict]:
    if order not in ORDERS:
        raise ValueError("unknown independent process order")
    weights = [300., 300.01, 400., 400.01]
    if order == "reverse_first":
        weights.reverse()
    requests = []
    for face in FACES:
        for phase, sequence in (("initial", weights), ("reverse", weights[::-1]),
                                ("repeat_initial", weights)):
            for weight in sequence:
                requests.append({"index": len(requests), "face_index": face,
                                 "phase": phase, "location": {"wght": weight}})
        fractional = [{"WDTH": 600.5859375},
                      {"WDTH": 600.5859375, "wght": 300.01},
                      {"WDTH": 600.5859375, "wght": 400.01}]
        if order == "reverse_first":
            fractional.reverse()
        for phase, sequence in (("fractional_width", fractional),
                                ("fractional_width_reverse", fractional[::-1])):
            for location in sequence:
                requests.append({"index": len(requests), "face_index": face,
                                 "phase": phase, "location": dict(location)})
    return requests


SWIFT = r'''
struct CacheRequest: Decodable {
    let index: Int
    let face_index: Int
    let phase: String
    let location: [String: Double]
}
func axisBits(_ location: [String: Double]) -> [String: String] {
    return location.mapValues { String($0.bitPattern, radix:16) }
}
func cacheComparison(_ a: CTFont, _ b: CTFont, _ gids: [Int]) throws -> [String: Any] {
    var geometry = 0.0, metrics = 0.0
    var metricComponents = Array(repeating: 0.0, count: 6)
    var changedGeometry = 0, changedMetrics = 0
    var mismatches: [Int] = []
    for gid in gids {
        let (difference, compatible) = try geometryDifference(a, b, gid)
        if compatible { geometry = max(geometry, difference) }
        else { mismatches.append(gid) }
        changedGeometry += compatible && difference == 0 ? 0 : 1
        let left = try metricVector(a, gid), right = try metricVector(b, gid)
        var glyphMetric = 0.0
        for index in left.indices {
            let delta = abs(left[index] - right[index])
            metricComponents[index] = max(metricComponents[index], delta)
            glyphMetric = max(glyphMetric, delta)
        }
        metrics = max(metrics, glyphMetric)
        changedMetrics += glyphMetric == 0 ? 0 : 1
    }
    return ["glyph_observations": gids.count,
        "max_geometry_difference": geometry, "max_metric_difference": metrics,
        "geometry_changed_glyphs": changedGeometry, "metrics_changed_glyphs": changedMetrics,
        "path_topology_mismatch_gids": mismatches,
        "max_metric_difference_by_component": metricComponents,
        "metric_component_order": ["horizontal_x", "horizontal_y", "vertical_x", "vertical_y",
                                   "vertical_translation_x", "vertical_translation_y"]]
}
func cacheProbeMain() throws {
    guard CommandLine.arguments.count == 4 else { throw OracleError.invalid("cache_probe_arguments") }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let data = try Data(contentsOf: url, options: [.mappedIfSafe])
    guard sha256(data) == "SOURCE_HASH" else { throw OracleError.invalid("wrong_original_source") }
    let order = CommandLine.arguments[2]
    guard order == "forward_first" || order == "reverse_first" else {
        throw OracleError.invalid("unknown_cache_probe_order")
    }
    let requestData = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[3]))
    let requests = try JSONDecoder().decode([CacheRequest].self, from: requestData)
    let states = try locateDescriptors(parseFaces(Bytes(data: data)), url: url)
    guard states.count == 32, states.allSatisfy({ $0.baseFont != nil && $0.raw.glyphCount == 47102 }) else {
        throw OracleError.invalid("all_physical_faces_required")
    }
    let gids = [0, 3, 5, 56, 498, 600]
    var rows: [[String: Any]] = []
    var first: [String: (font: CTFont, index: Int)] = [:]
    var previous: [Int: (font: CTFont, index: Int)] = [:]
    var pending: [(font: CTFont, state: FaceState, reported: [String: Double], row: Int)] = []
    for request in requests {
        guard request.index == rows.count, request.face_index == 20 || request.face_index == 31 else {
            throw OracleError.invalid("unexpected_cache_probe_request")
        }
        let state = states[request.face_index]
        guard state.raw.index == request.face_index else {
            throw OracleError.invalid("cache_probe_physical_face_order_changed")
        }
        var row: [String: Any] = ["request_index": request.index, "face_index": request.face_index,
            "phase": request.phase, "requested_override": request.location, "status": "NOT_OBSERVED"]
        do {
            let (font, location, reported) = try observationInstance(state, request.location)
            row["requested"] = location
            row["requested_binary64_hex"] = axisBits(location)
            row["reported"] = reported
            row["reported_binary64_hex"] = axisBits(reported)
            row["number_metadata_before_glyph_access"] = inspectNumbers(font)
            row["requested_number_metadata"] = state.raw.axes.map { axis -> [String: Any] in
                var number = inspectNumber(NSNumber(value: location[axis.tag]!))
                number["axis"] = axis.tag
                return number
            }
            let key = String(state.raw.index) + ":" + state.raw.axes.map {
                String(location[$0.tag]!.bitPattern, radix:16)
            }.joined(separator: ",")
            if let initial = first[key] {
                var comparison = try cacheComparison(initial.font, font, gids)
                comparison["against_request_index"] = initial.index
                comparison["ctfont_cf_equal"] = CFEqual(initial.font, font)
                row["first_identical_request_comparison"] = comparison
            }
            if let preceding = previous[state.raw.index] {
                var comparison = try cacheComparison(preceding.font, font, gids)
                comparison["against_request_index"] = preceding.index
                row["previous_request_comparison"] = comparison
            } else {
                // Force glyph access even at the first request, before any later
                // instance is created. The comparison is only a finite API check.
                row["first_request_self_comparison"] = try cacheComparison(font, font, gids)
            }
            row["number_metadata_after_glyph_access"] = inspectNumbers(font)
            row["reported_after_glyph_access_binary64_hex"] = axisBits(axisNumbers(font))
            row["status"] = "OBSERVED"
            if first[key] == nil { first[key] = (font, request.index) }
            previous[state.raw.index] = (font, request.index)
            pending.append((font, state, reported, rows.count))
        } catch {
            row["status"] = "OBSERVATION_ERROR"
            row["error"] = String(describing: error)
        }
        rows.append(row)
    }
    // Do not interleave reconstructed readback instances with the request-order
    // experiment: all native requested instances above are retained until here.
    for item in pending {
        do {
            var request = Dictionary(uniqueKeysWithValues: item.state.raw.axes.map {
                ($0.tag, $0.defaultValue)
            })
            request.merge(item.reported) { _, observed in observed }
            let (readbackFont, location, reported) = try observationInstance(item.state, request)
            rows[item.row]["readback_reconstruction_requested"] = location
            rows[item.row]["readback_reconstruction_requested_binary64_hex"] = axisBits(location)
            rows[item.row]["readback_reconstruction_reported_binary64_hex"] = axisBits(reported)
            rows[item.row]["readback_reconstruction_number_metadata"] = inspectNumbers(readbackFont)
            rows[item.row]["request_vs_readback_instance"] = try cacheComparison(item.font, readbackFont, gids)
        } catch {
            rows[item.row]["status"] = "READBACK_RECONSTRUCTION_ERROR"
            rows[item.row]["error"] = String(describing: error)
        }
    }
    try emit(["status": "NATIVE_AXIS_CACHE_OBSERVATION_NOT_FONT_ACCEPTANCE",
        "source_sha256": sha256(data), "physical_faces_verified": states.count,
        "process_order": order, "probed_faces": [20, 31], "glyph_ids": gids,
        "requested_instances_retained_until_readback_phase": true,
        "readback_reconstructions_after_all_original_requests": true,
        "production_axis_guard_unchanged": true, "outlines_published": false,
        "font_generated": false, "reports": rows])
}
try cacheProbeMain()
'''


def make_harness(source: str) -> str:
    combined = construction.make_harness(source)
    separator = "\nfunc compareConstructionMain() throws {"
    if combined.count(separator) != 1:
        raise ValueError("native construction helpers changed; review before reuse")
    return combined.split(separator)[0] + SWIFT.replace("SOURCE_HASH", construction.EXPECTED)


def summarize(native: dict, requests: list[dict]) -> dict:
    rows = native.get("reports", [])
    if (len(rows) != len(requests) or native.get("physical_faces_verified") != 32
            or native.get("source_sha256") != construction.EXPECTED):
        raise ValueError("incomplete native cache experiment or changed source identity")
    result = {"requests": len(rows), "observation_errors": 0, "readback_pairs": 0,
              "identical_request_pairs": 0, "max_readback_geometry_difference": 0.,
              "max_readback_metric_difference": 0., "max_repeat_geometry_difference": 0.,
              "max_repeat_metric_difference": 0., "topology_mismatch_comparisons": 0,
              "font_acceptance": "NOT_ESTABLISHED"}
    for row, expected in zip(rows, requests):
        if any(row.get(key) != expected[other] for key, other in (
                ("request_index", "index"), ("face_index", "face_index"), ("phase", "phase"))):
            raise ValueError("native cache request identity changed")
        if row.get("status") != "OBSERVED":
            result["observation_errors"] += 1
            continue
        for field, count, prefix in (("request_vs_readback_instance", "readback_pairs", "readback"),
                                     ("first_identical_request_comparison", "identical_request_pairs", "repeat")):
            comparison = row.get(field)
            if comparison is None:
                if prefix == "readback":
                    raise ValueError("missing readback comparison")
                continue
            if comparison.get("glyph_observations") != len(GIDS):
                raise ValueError("incomplete native glyph comparison")
            result[count] += 1
            for kind in ("geometry", "metric"):
                value = comparison.get(f"max_{kind}_difference")
                if not isinstance(value, (int, float)) or not 0 <= value < float("inf"):
                    raise ValueError("invalid native discrepancy")
                key = f"max_{prefix}_{kind}_difference"
                result[key] = max(result[key], value)
            mismatches = comparison.get("path_topology_mismatch_gids")
            if not isinstance(mismatches, list) or any(gid not in GIDS for gid in mismatches):
                raise ValueError("invalid native topology discrepancy")
            result["topology_mismatch_comparisons"] += bool(mismatches)
    return result


def run(source: Path, output: Path) -> dict:
    if output.exists() or output.resolve() == source.resolve():
        raise ValueError("report must be a new file distinct from source")
    if hashlib.sha256(source.read_bytes()).hexdigest() != construction.EXPECTED:
        raise ValueError("exact source SHA required")
    code = Path(__file__).with_name("coretext_extract.swift").read_text(encoding="utf-8")
    harness = make_harness(code)
    report = {"status": "NOT_RUN", "platform": platform.platform(),
              "source_sha256": construction.EXPECTED, "source_commit": os.environ.get("GITHUB_SHA"),
              "source_code_sha256": hashlib.sha256(code.encode()).hexdigest(),
              "generated_harness_sha256": hashlib.sha256(harness.encode()).hexdigest(),
              "probe_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "independent_native_processes": True, "production_axis_guard_unchanged": True,
              "outlines_published": False, "font_generated": False, "processes": []}
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    save()
    try:
        with tempfile.TemporaryDirectory(prefix="swirl-axis-cache-") as directory:
            root = Path(directory)
            swift, binary = root / "probe.swift", root / "probe"
            swift.write_text(harness, encoding="utf-8")
            compiled = subprocess.run(["xcrun", "swiftc", "-O", str(swift), "-o", str(binary)],
                                      capture_output=True, text=True, timeout=180)
            if compiled.returncode:
                raise RuntimeError("Swift compilation failed: " + compiled.stderr[-8000:])
            for order in ORDERS:
                requests = request_specs(order)
                input_file = root / f"{order}.json"
                input_file.write_text(json.dumps(requests, allow_nan=False), encoding="utf-8")
                native = subprocess.run([str(binary), str(source), order, str(input_file)],
                                        capture_output=True, text=True, timeout=240)
                if native.returncode:
                    raise RuntimeError("Native cache probe failed: " + native.stderr[-4000:])
                result = json.loads(native.stdout)
                if result.get("process_order") != order:
                    raise ValueError("native process order identity changed")
                result["summary"] = summarize(result, requests)
                report["processes"].append(result)
                save()
                print(json.dumps({"process_order": order, **result["summary"]}, allow_nan=False), flush=True)
        if hashlib.sha256(source.read_bytes()).hexdigest() != construction.EXPECTED:
            raise RuntimeError("source changed during native cache probe")
        report["source_unchanged"] = True
        report["status"] = ("OBSERVED_WITH_ERRORS_NOT_FONT_ACCEPTANCE" if any(
            p["summary"]["observation_errors"] for p in report["processes"])
            else "NATIVE_AXIS_CACHE_OBSERVATION_NOT_FONT_ACCEPTANCE")
    except Exception as error:
        report["status"] = "FAILED"
        report["error"] = str(error)
        save()
        raise
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source, args.output)
    raise SystemExit(2 if result["status"] == "OBSERVED_WITH_ERRORS_NOT_FONT_ACCEPTANCE" else 0)
