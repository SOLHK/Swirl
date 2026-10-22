#!/usr/bin/env python3
"""Compare opposite first writers in two fresh native processes.

Only the selected glyphs are measured. Complete typed path commands and all
extractGlyph metric fields pass through anonymous pipes into private Python
memory. They are neither written to disk nor included in public summaries.
Canonical values are computed before either native process starts; observations
are never used to choose an accommodating canonical value. This diagnostic
does not replace the production oracle's original 1e-6 readback gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import tempfile

from fontTools.ttLib import TTCollection
import compare_axis_construction as construction

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from incremental_pipe import TimedLineReader

ORDERS = ("requested_first", "canonical_first")
TAGS = ("WDTH", "wght", "HGHT")
DEFAULT_FACES = (20, 31)
DEFAULT_GIDS = (0, 1, 2, 3, 4, 5, 6, 7, 20, 82, 97, 104, 170, 184, 197, 209,
                263, 275, 292, 722, 3262, 4985, 6441, 6442, 7883, 13890,
                17485, 19177, 21150, 30806, 35342, 38593)
SCALARS = ("advance_width", "advance_height", "lsb", "horizontal_origin_x", "horizontal_origin_y",
           "vertical_origin_x", "vertical_origin_y", "horizontal_advance_sum", "vertical_advance_sum")
VECTORS = {"horizontal_advance_vector": 2, "vertical_advance_vector": 2,
           "vertical_origin_translation": 2, "bounds": 4}
STRINGS = ("lsb_derivation", "vertical_origin_derivation", "path_status")
META_FIELDS = {"type", "writer_variant", "request_id", "face_index", "glyph_id",
               "location", "reported_location"}
PAYLOAD_FIELDS = {"commands", "error", *SCALARS, *VECTORS, *STRINGS}
COMPARISONS = ("requested_across_processes", "canonical_across_processes",
               "within_requested_first_process", "within_canonical_first_process")


class ProbeError(ValueError):
    """Messages are fixed codes/field names, never private payload values."""


def require(condition, code):
    if not condition:
        raise ProbeError(code)


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def same_bits(left, right):
    return finite_number(left) and finite_number(right) and struct.pack("!d", left) == struct.pack("!d", right)


def canonical_location(location):
    require(set(location) == set(TAGS)
            and all(finite_number(v) and v > 0 and math.isfinite(v * 10000) for v in location.values()),
            "invalid_requested_axis_location")
    # A single binary64 product/truncate/divide candidate. CoreText must prove
    # that this value is its stable echo; a second arithmetic application can
    # change the value, and is deliberately not used to choose another target.
    return {tag: math.trunc(location[tag] * 10000) / 10000 for tag in TAGS}


def requests_for_axes(axes_by_face, faces=DEFAULT_FACES, glyph_ids=DEFAULT_GIDS):
    require(bool(faces) and len(set(faces)) == len(faces), "invalid_selected_faces")
    require(bool(glyph_ids) and len(glyph_ids) <= 256 and len(set(glyph_ids)) == len(glyph_ids)
            and all(type(gid) is int and 0 <= gid < 47102 for gid in glyph_ids), "invalid_selected_glyphs")
    result = []
    for face in faces:
        require(face in axes_by_face, "missing_source_face_axes")
        axes = axes_by_face[face]
        require(tuple(axes) == TAGS, "original_axis_tags_or_order_changed")
        defaults = {tag: axes[tag][1] for tag in TAGS}
        updates = [("all_defaults", {})]
        updates += [(f"{tag}_{label}", {tag: axes[tag][index]})
                    for tag in TAGS for label, index in (("minimum", 0), ("maximum", 2))]
        updates += [(f"fractional_width_weight_{weight}", {"WDTH": 600.5859375, "wght": weight})
                    for weight in (300.01, 400.01)]
        # Unlike 600.5859375, these positions distinguish the observed
        # truncation candidate from round-to-nearest decimal formatting.
        updates += [("fractional_truncate_distinguishing_561", {
                         "WDTH": 561.7283945, "wght": 300.01, "HGHT": 581.267578125}),
                    ("fractional_truncate_distinguishing_581", {
                         "WDTH": 581.267578125, "wght": 400.01, "HGHT": 561.7283945})]
        for label, update in updates:
            requested = {**defaults, **update}
            canonical = canonical_location(requested)
            require(all(axes[tag][0] <= requested[tag] <= axes[tag][2]
                        and axes[tag][0] <= canonical[tag] <= axes[tag][2] for tag in TAGS),
                    "diagnostic_position_outside_source_range")
            result.append({"request_id": f"writer-{len(result)}", "face_index": face,
                           "case": label, "requested": requested, "canonical": canonical,
                           "glyph_ids": list(glyph_ids)})
    return result


SWIFT = r'''
struct FirstWriterRequest: Decodable {
    let request_id: String
    let face_index: Int
    let requested: [String: Double]
    let canonical: [String: Double]
    let glyph_ids: [Int]
}
func firstWriterEcho(_ font: CTFont, _ state: FaceState, _ request: FirstWriterRequest) throws -> [String: Double] {
    let reported = axisNumbers(font)
    let tags = Set(state.raw.axes.map(\.tag))
    guard Set(request.requested.keys) == tags, Set(request.canonical.keys) == tags,
          reported.keys.allSatisfy({ tags.contains($0) }) else {
        throw OracleError.invalid("first_writer_axis_dictionary_mismatch")
    }
    for axis in state.raw.axes {
        let original = request.requested[axis.tag]!
        let canonical = request.canonical[axis.tag]!
        if original != axis.defaultValue || canonical != axis.defaultValue {
            guard reported[axis.tag] != nil else {
                throw OracleError.invalid("first_writer_missing_nondefault_axis:\(axis.tag)")
            }
        }
        let value = reported[axis.tag] ?? axis.defaultValue
        guard value.isFinite, value.bitPattern == canonical.bitPattern else {
            throw OracleError.invalid("first_writer_decimal4_rule_not_observed:\(axis.tag)")
        }
    }
    return reported
}
func firstWriterMain() throws {
    guard CommandLine.arguments.count == 3 else { throw OracleError.invalid("first_writer_arguments") }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let data = try Data(contentsOf: url, options: [.mappedIfSafe])
    guard sha256(data) == "SOURCE_HASH" else { throw OracleError.invalid("wrong_original_source") }
    let order = CommandLine.arguments[2]
    guard order == "requested_first" || order == "canonical_first" else {
        throw OracleError.invalid("unknown_first_writer_order")
    }
    let bytes = Bytes(data: data)
    let states = try locateDescriptors(parseFaces(bytes), url: url)
    guard states.count == 32, states.allSatisfy({ $0.baseFont != nil && $0.raw.glyphCount == 47102 }) else {
        throw OracleError.invalid("all_physical_faces_required")
    }
    try emit(["type": "metadata", "source_sha256": sha256(data), "physical_faces_verified": states.count,
              "order": order, "production_axis_guard_changed": false])
    let input = JSONLines()
    var requestCount = 0, glyphCount = 0
    while let line = try input.next() {
        let request = try JSONDecoder().decode(FirstWriterRequest.self, from: line)
        guard request.face_index >= 0, request.face_index < states.count,
              !request.glyph_ids.isEmpty, request.glyph_ids.count <= 256,
              Set(request.glyph_ids).count == request.glyph_ids.count else {
            throw OracleError.invalid("invalid_first_writer_request")
        }
        let state = states[request.face_index]
        guard state.raw.index == request.face_index else { throw OracleError.invalid("physical_face_order_changed") }
        let variants = order == "requested_first" ? ["requested", "canonical"] : ["canonical", "requested"]
        var retained: [CTFont] = []
        for variant in variants {
            let desired = variant == "requested" ? request.requested : request.canonical
            let (font, location, _) = try observationInstance(state, desired)
            retained.append(font)
            let before = try firstWriterEcho(font, state, request)
            try emit(["type": "stage_start", "request_id": request.request_id, "face_index": request.face_index,
                      "writer_variant": variant, "location": location, "reported_location": before])
            // Force every requested glyph through the first-created instance
            // before constructing the second instance of this same target.
            for gid in request.glyph_ids {
                try autoreleasepool {
                    let nativeRequest = Request(request_id: request.request_id, face_index: request.face_index,
                                                location: location, glyph_ids: [gid])
                    var record = try extractGlyph(nativeRequest, gid, state, font, location, before, bytes)
                    let after = try firstWriterEcho(font, state, request)
                    guard after == before else { throw OracleError.invalid("first_writer_echo_changed_during_glyph") }
                    record["type"] = "glyph"
                    record["writer_variant"] = variant
                    try emit(record)
                    glyphCount += 1
                }
            }
            let after = try firstWriterEcho(font, state, request)
            guard before == after else { throw OracleError.invalid("first_writer_echo_changed_after_stage") }
            try emit(["type": "stage_end", "request_id": request.request_id, "face_index": request.face_index,
                      "writer_variant": variant, "location": location, "reported_location": after,
                      "glyph_records": request.glyph_ids.count])
        }
        withExtendedLifetime(retained) { }
        requestCount += 1
    }
    try emit(["type": "finished", "request_count": requestCount, "glyph_records": glyphCount])
}
do { try firstWriterMain() }
catch {
    let code: String
    if let known = error as? OracleError { code = known.description }
    else { code = "unclassified_native_first_writer_error" }
    try? emit(["type": "error", "code": code])
    exit(2)
}
'''


def make_harness(source):
    combined = construction.make_harness(source)
    separator = "\nfunc compareConstructionMain() throws {"
    require(combined.count(separator) == 1, "review_changed_construction_helpers")
    return combined.split(separator)[0] + SWIFT.replace("SOURCE_HASH", construction.EXPECTED)


def validate_echo(row, request, variant, defaults, event_type):
    require(row.get("type") == event_type and row.get("request_id") == request["request_id"]
            and row.get("face_index") == request["face_index"] and row.get("writer_variant") == variant,
            "native_event_identity_changed")
    desired = request[variant]
    require(request["canonical"] == canonical_location(request["requested"]), "canonical_rule_changed_before_comparison")
    location, reported = row.get("location"), row.get("reported_location")
    require(isinstance(location, dict) and set(location) == set(TAGS)
            and all(same_bits(location[tag], desired[tag]) for tag in TAGS), "native_requested_location_changed")
    require(isinstance(reported, dict) and set(reported) <= set(TAGS), "native_echo_axis_dictionary_changed")
    for tag in TAGS:
        if request["requested"][tag] != defaults[tag] or request["canonical"][tag] != defaults[tag]:
            require(tag in reported, "missing_nondefault_axis:" + tag)
        require(same_bits(reported.get(tag, defaults[tag]), request["canonical"][tag]),
                "decimal4_rule_not_observed:" + tag)
    return reported


def _private_payload(record):
    require(set(record) == META_FIELDS | PAYLOAD_FIELDS, "missing_or_unreviewed_native_payload_field")
    require(record["error"] is None, "native_glyph_error")
    require(all(isinstance(record[key], str) for key in STRINGS), "invalid_native_string_field")
    require(record["path_status"] in ("path", "empty_path", "nil_path_but_source_proves_empty"),
            "unverified_native_empty_path")
    commands = record["commands"]
    require(isinstance(commands, list), "missing_native_commands")
    arities = {"moveTo": 3, "lineTo": 3, "qCurveTo": 5, "curveTo": 7, "closePath": 1}
    for command in commands:
        require(isinstance(command, list) and bool(command) and isinstance(command[0], str) and command[0] in arities
                and len(command) == arities[command[0]] and all(finite_number(v) for v in command[1:]),
                "invalid_typed_native_command")
    require(bool(commands) or record["path_status"] != "path", "native_path_claim_without_commands")
    metrics = []
    for key in SCALARS:
        require(finite_number(record[key]), "invalid_native_metric:" + key)
        metrics.append(record[key])
    for key, size in VECTORS.items():
        vector = record[key]
        require(isinstance(vector, list) and len(vector) == size and all(finite_number(v) for v in vector),
                "invalid_native_metric_vector:" + key)
        metrics.extend(vector)
    return commands, metrics


def compare_private_glyphs(left, right):
    """Return only irreversible aggregate differences; retain no raw payload."""
    require(all(left.get(key) == right.get(key) for key in ("request_id", "face_index", "glyph_id")),
            "private_comparison_identity_mismatch")
    a, am = _private_payload(left)
    b, bm = _private_payload(right)
    topology = len(a) != len(b) or any(x[0] != y[0] or len(x) != len(y) for x, y in zip(a, b))
    coordinate_error = max((abs(xv - yv) for x, y in zip(a, b)
                            if x[0] == y[0] and len(x) == len(y)
                            for xv, yv in zip(x[1:], y[1:])), default=0.)
    metric_error = max((abs(x - y) for x, y in zip(am, bm)), default=0.)
    descriptor_mismatch = any(left[key] != right[key] for key in STRINGS)
    exact = not topology and coordinate_error == 0 and metric_error == 0 and not descriptor_mismatch
    return {"glyph_comparisons": 1, "exact_equal_glyphs": int(exact),
            "topology_mismatches": int(topology), "metric_or_path_descriptor_mismatches": int(descriptor_mismatch),
            "max_command_coordinate_difference": coordinate_error, "max_raw_or_derived_metric_difference": metric_error}


def compare_four_variants(requested_a, canonical_a, canonical_b, requested_b):
    """Two local equalities alone cannot establish independence of first writer."""
    pairs = ((requested_a, requested_b), (canonical_a, canonical_b),
             (requested_a, canonical_a), (canonical_b, requested_b))
    return {label: compare_private_glyphs(*pair) for label, pair in zip(COMPARISONS, pairs)}


def empty_stats():
    return {"glyph_comparisons": 0, "exact_equal_glyphs": 0, "topology_mismatches": 0,
            "metric_or_path_descriptor_mismatches": 0, "max_command_coordinate_difference": 0.,
            "max_raw_or_derived_metric_difference": 0.}


def accumulate(target, sample):
    for key in target:
        target[key] = max(target[key], sample[key]) if key.startswith("max_") else target[key] + sample[key]


class NativeProcess:
    def __init__(self, binary, source, order):
        self.process = subprocess.Popen([str(binary), str(source), order], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.reader = TimedLineReader(self.process.stdout.fileno())
        self.order = order

    def read(self, timeout=30):
        line = self.reader.readline(timeout=timeout)
        require(bool(line), "unexpected_native_pipe_eof")
        try:
            row = json.loads(line)
        except (ValueError, TypeError):
            raise ProbeError("invalid_private_native_json") from None
        require(isinstance(row, dict), "invalid_private_native_message")
        if row.get("type") == "error":
            # OracleError contains tool-authored codes. Do not echo arbitrary
            # subprocess output, malformed JSON, or any extracted glyph record.
            code = row.get("code", "unknown")
            require(isinstance(code, str) and len(code) <= 200
                    and all(c.isalnum() or c in "_:,-." for c in code), "unreviewed_native_error_code")
            raise ProbeError("native_error:" + code)
        return row

    def send(self, request):
        self.process.stdin.write((json.dumps(request, allow_nan=False) + "\n").encode())
        self.process.stdin.flush()

    def close(self):
        self.reader.close()
        for stream in (self.process.stdin, self.process.stdout):
            if stream and not stream.closed:
                stream.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)


def run(source, output, faces=DEFAULT_FACES, glyph_ids=DEFAULT_GIDS):
    require(not output.exists() and output.resolve() != source.resolve(), "new_report_path_required")
    require(hashlib.sha256(source.read_bytes()).hexdigest() == construction.EXPECTED, "exact_original_source_required")
    with TTCollection(source, lazy=True) as collection:
        require(len(collection.fonts) == 32 and all(f["maxp"].numGlyphs == 47102 for f in collection.fonts),
                "original_physical_faces_or_glyph_counts_changed")
        axes = {i: {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in f["fvar"].axes}
                for i, f in enumerate(collection.fonts)}
    requests = requests_for_axes(axes, faces, glyph_ids)
    code = Path(__file__).with_name("coretext_extract.swift").read_text(encoding="utf-8")
    harness = make_harness(code)
    labels = COMPARISONS
    report = {"status": "NOT_RUN", "source_sha256": construction.EXPECTED,
              "source_commit": os.environ.get("GITHUB_SHA"), "platform": platform.platform(),
              "source_code_sha256": hashlib.sha256(code.encode()).hexdigest(),
              "generated_harness_sha256": hashlib.sha256(harness.encode()).hexdigest(),
              "probe_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "selected_faces": list(faces), "selected_glyph_count": len(glyph_ids),
              "requested_positions": len(requests), "completed_positions": 0,
              "native_process_orders": list(ORDERS), "native_glyph_records_read": 0,
              "canonical_values_precomputed_before_native_process_start": True,
              "first_created_instance_accesses_all_requested_glyphs_before_second_creation": True,
              "canonical_rule": "positive_trunc_double_times_10000_divide_10000",
              "canonical_arithmetic_applications": 1,
              "canonical_echo_stability_requires_native_observation_not_recursive_arithmetic": True,
              "canonical_echo_tolerance": 0., "glyph_equality_tolerance": 0.,
              "production_axis_guard_changed": False, "original_axis_tolerance": 1e-6,
              "all_source_glyphs_compared": False, "whole_font_acceptance": "NOT_ESTABLISHED",
              "process_scope_does_not_claim_system_font_service_cache_reset": True,
              "raw_commands_or_metrics_published": False, "native_stdout_written_to_disk": False,
              "font_generated": False, "comparisons": {label: empty_stats() for label in labels}, "cases": []}
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    save()
    processes = []
    try:
        with tempfile.TemporaryDirectory(prefix="swirl-first-writer-") as directory:
            root = Path(directory)
            swift, binary = root / "probe.swift", root / "probe"
            swift.write_text(harness, encoding="utf-8")
            compilation = subprocess.run(["xcrun", "swiftc", "-O", str(swift), "-o", str(binary)],
                                         capture_output=True, text=True, timeout=180)
            if compilation.returncode:
                # Compilation runs before a font or native glyph is opened;
                # this diagnostic contains tool source, not font data.
                report["swift_compilation_diagnostic"] = compilation.stderr[-8000:]
                raise ProbeError("first_writer_swift_compile_failed")
            for order in ORDERS:
                native = NativeProcess(binary, source, order)
                processes.append(native)
            for native in processes:
                metadata = native.read(timeout=120)
                require(metadata.get("type") == "metadata" and metadata.get("order") == native.order
                        and metadata.get("source_sha256") == construction.EXPECTED
                        and metadata.get("physical_faces_verified") == 32
                        and metadata.get("production_axis_guard_changed") is False,
                        "native_process_identity_not_verified")
            for request in requests:
                context = {"request_id": request["request_id"], "face_index": request["face_index"],
                           "case": request["case"]}
                report["active_case"] = context
                defaults = {tag: axes[request["face_index"]][tag][1] for tag in TAGS}
                first = [{}, {}]
                echoes = [{}, {}]
                case_stats = {label: empty_stats() for label in labels}
                for native in processes:
                    native.send(request)
                for phase in (0, 1):
                    variants = ("requested", "canonical") if phase == 0 else ("canonical", "requested")
                    for index, native in enumerate(processes):
                        start = native.read()
                        echoes[index][variants[index]] = validate_echo(start, request, variants[index], defaults, "stage_start")
                    for gid in request["glyph_ids"]:
                        report["active_glyph_id"] = gid
                        rows = []
                        for index, native in enumerate(processes):
                            row = native.read()
                            echo = validate_echo(row, request, variants[index], defaults, "glyph")
                            require(echo == echoes[index][variants[index]], "native_echo_changed_during_glyph")
                            require(row.get("glyph_id") == gid, "native_glyph_identity_changed")
                            _private_payload(row)
                            rows.append(row)
                            report["native_glyph_records_read"] += 1
                        if phase == 0:
                            first[0][gid], first[1][gid] = rows
                        else:
                            requested_a, canonical_b = first[0].pop(gid), first[1].pop(gid)
                            canonical_a, requested_b = rows
                            results = compare_four_variants(requested_a, canonical_a, canonical_b, requested_b)
                            for label, result in results.items():
                                accumulate(case_stats[label], result)
                                accumulate(report["comparisons"][label], result)
                    for index, native in enumerate(processes):
                        end = native.read()
                        echo = validate_echo(end, request, variants[index], defaults, "stage_end")
                        require(echo == echoes[index][variants[index]], "native_echo_changed_after_stage")
                        require(end.get("glyph_records") == len(glyph_ids), "incomplete_native_stage")
                report["cases"].append({**context, "comparisons": case_stats})
                report["completed_positions"] += 1
                save()
            for native in processes:
                native.process.stdin.close()
            for native in processes:
                finished = native.read()
                require(finished.get("type") == "finished" and finished.get("request_count") == len(requests)
                        and finished.get("glyph_records") == len(requests) * len(glyph_ids) * 2,
                        "incomplete_native_process")
                require(native.process.wait(timeout=10) == 0, "native_process_failed")
            require(hashlib.sha256(source.read_bytes()).hexdigest() == construction.EXPECTED,
                    "original_source_changed_during_probe")
            report["source_unchanged"] = True
            report["status"] = ("EXACT_EQUIVALENCE_FOR_SELECTED_GLYPHS_NOT_FONT_ACCEPTANCE"
                                if all(s["glyph_comparisons"] == s["exact_equal_glyphs"]
                                       for s in report["comparisons"].values())
                                else "FIRST_WRITER_EQUIVALENCE_REJECTED")
            report.pop("active_case", None)
            report.pop("active_glyph_id", None)
    except Exception as error:
        report["status"] = "FAILED"
        report["error"] = str(error) if isinstance(error, ProbeError) else type(error).__name__
        save()
        raise
    finally:
        for native in processes:
            native.close()
    save()
    print(json.dumps({key: report[key] for key in ("status", "selected_faces", "selected_glyph_count",
                      "completed_positions", "native_glyph_records_read", "comparisons")}, allow_nan=False), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.source, args.output)
    except Exception:
        # Never let a private payload enter an exception traceback in CI logs.
        print("first_writer_probe_failed; inspect safe summary", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(0 if result["status"] == "EXACT_EQUIVALENCE_FOR_SELECTED_GLYPHS_NOT_FONT_ACCEPTANCE" else 2)
