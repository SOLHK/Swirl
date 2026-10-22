#!/usr/bin/env python3
"""Observe finite decimal candidates; never grant font or axis acceptance.

The requested value, two once-truncated representations, and one further
application of each representation are declared before native processes start.
Two fresh processes construct them in opposite orders. Original typed paths and
all raw/derived metrics remain in anonymous pipes/private memory. Only axis
numbers, their binary64 encodings, and aggregate payload differences are saved.
"""
from __future__ import annotations

import argparse
import copy
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

import probe_axis_first_writer as payload
from compare_axis_construction import EXPECTED, GUARD
from test_coretext_extract import make_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from incremental_pipe import TimedLineReader
from rebuild import checkpoint_source_faces, sha256, verify_checkpoint_session_metadata

TAGS = ("WDTH", "wght", "HGHT")
VARIANTS = ("requested", "divide1", "multiply1", "divide2", "multiply2")
ORDERS = ("forward", "reverse")
ORIGINAL_FACES = (0, 15, 20, 31)
SAMPLE44 = {"WDTH": 304.712646484375, "wght": 323.3597412109375, "HGHT": 728.240966796875}
SYNTHETIC44 = {**SAMPLE44, "wght": 267.10205078125}


class BoundaryError(ValueError):
    """Fixed diagnostic codes, never unreviewed native payloads or paths."""


def require(condition, code):
    if not condition:
        raise BoundaryError(code)


def bits(value):
    require(payload.finite_number(value), "nonfinite_axis_number")
    return struct.pack("!d", value).hex()


def candidate_values(value):
    require(payload.finite_number(value) and value > 0 and math.isfinite(value * 10000),
            "positive_finite_candidate_domain_required")
    integer = math.trunc(value * 10000)
    divide1, multiply1 = integer / 10000, integer * 0.0001
    return {"requested": value, "divide1": divide1, "multiply1": multiply1,
            "divide2": math.trunc(divide1 * 10000) / 10000,
            "multiply2": math.trunc(multiply1 * 10000) * 0.0001}


def declared_variants(location):
    require(set(location) == set(TAGS), "all_original_axis_tags_required")
    values = {tag: candidate_values(location[tag]) for tag in TAGS}
    # Equal values deliberately remain separate declared constructions.
    return [{"name": name, "location": {tag: values[tag][name] for tag in TAGS}}
            for name in VARIANTS]


def positions(axes, source_kind):
    require(tuple(axes) == TAGS, "source_axis_tags_or_order_changed")
    require(source_kind in ("original", "synthetic"), "unknown_source_kind")
    defaults = {tag: axes[tag][1] for tag in TAGS}
    target = SAMPLE44 if source_kind == "original" else SYNTHETIC44
    control = {**defaults, "WDTH": 600.5859375}
    result = []
    for family, base, active in (("sample44", target, TAGS), ("control", control, ("WDTH",))):
        changes = [("exact", dict(base))]
        for label, direction in (("binary64_below", -math.inf), ("binary64_above", math.inf)):
            changes.append((label, {**base, **{tag: math.nextafter(base[tag], direction) for tag in active}}))
        for label, offset in (("decimal_below", -1), ("decimal_above", 1)):
            changes.append((label, {**base, **{tag: (math.trunc(base[tag] * 10000) + offset) / 10000
                                               for tag in active}}))
        for suffix, location in changes:
            variants = declared_variants(location)
            require(all(axes[tag][0] <= variant["location"][tag] <= axes[tag][2]
                        for variant in variants for tag in TAGS), "declared_candidate_outside_source_axis_range")
            result.append({"case": family + "_" + suffix, "variants": variants})
    return result


SWIFT = r'''
struct BoundaryVariant: Decodable {
    let name: String
    let location: [String: Double]
}
struct BoundaryRequest: Decodable {
    let request_id: String
    let face_index: Int
    let variants: [BoundaryVariant]
    let glyph_ids: [Int]
}
func boundaryAxes(_ font: CTFont) -> [String: Double] {
    var result: [String: Double] = [:]
    if let values = CTFontCopyVariation(font) as? [NSNumber: NSNumber] {
        for (key, value) in values { result[tagString(key.uint32Value)] = value.doubleValue }
    }
    return result
}
func boundaryMain() throws {
    guard CommandLine.arguments.count == 4 else { throw OracleError.invalid("boundary_arguments") }
    let url = URL(fileURLWithPath: CommandLine.arguments[1])
    let data = try Data(contentsOf: url, options: [.mappedIfSafe])
    guard sha256(data) == CommandLine.arguments[2] else { throw OracleError.invalid("boundary_source_hash_mismatch") }
    let order = CommandLine.arguments[3]
    guard order == "forward" || order == "reverse" else { throw OracleError.invalid("boundary_order") }
    let bytes = Bytes(data: data)
    let states = try locateDescriptors(parseFaces(bytes), url: url)
    guard !states.isEmpty, states.allSatisfy({ $0.baseFont != nil }) else {
        throw OracleError.invalid("boundary_all_physical_faces_must_be_verified")
    }
    try emit(["type": "metadata", "backend": "CoreText", "axis_observations_only": true,
              "source_sha256": sha256(data), "source_byte_size": data.count, "order": order,
              "faces": states.map(\.metadata)])
    let input = JSONLines()
    var requests = 0, glyphs = 0
    while let line = try input.next() {
        let request = try JSONDecoder().decode(BoundaryRequest.self, from: line)
        guard request.face_index >= 0, request.face_index < states.count,
              request.variants.count == 5,
              Set(request.variants.map(\.name)) == Set(["requested", "divide1", "multiply1", "divide2", "multiply2"]),
              !request.glyph_ids.isEmpty, request.glyph_ids.count <= 256,
              Set(request.glyph_ids).count == request.glyph_ids.count else {
            throw OracleError.invalid("boundary_request_invalid")
        }
        let state = states[request.face_index]
        let ordered = order == "forward" ? request.variants : Array(request.variants.reversed())
        var retained: [CTFont] = []
        for variant in ordered {
            // Keep the strict makeInstance wrapper unchanged and unused here.
            let (font, location, reported) = try constructInstance(state, variant.location)
            retained.append(font)
            try emit(["type": "stage_start", "request_id": request.request_id, "face_index": request.face_index,
                      "writer_variant": variant.name, "location": location, "reported_location": reported])
            // Every selected GID is read before the next instance is constructed.
            for gid in request.glyph_ids {
                let native = Request(request_id: request.request_id, face_index: request.face_index,
                                     location: location, glyph_ids: [gid])
                var record = try autoreleasepool { try extractGlyph(native, gid, state, font, location, reported, bytes) }
                record["type"] = "glyph"
                record["writer_variant"] = variant.name
                record["reported_location"] = boundaryAxes(font)
                try emit(record)
                glyphs += 1
            }
            try emit(["type": "stage_end", "request_id": request.request_id, "face_index": request.face_index,
                      "writer_variant": variant.name, "location": location, "reported_location": boundaryAxes(font),
                      "glyph_records": request.glyph_ids.count])
        }
        withExtendedLifetime(retained) { }
        requests += 1
    }
    try emit(["type": "finished", "request_count": requests, "glyph_records": glyphs, "source_sha256": sha256(data)])
}
do { try boundaryMain() }
catch {
    let code = (error as? OracleError)?.description ?? "unclassified_boundary_native_error"
    try? emit(["type": "error", "code": code])
    exit(2)
}
'''


def make_harness(source):
    separator = "\nfunc run() throws {"
    require(source.count(GUARD) == 1 and source.count(separator) == 1
            and source.count("func constructInstance(") == 1, "review_changed_production_helpers")
    # The original strict guard remains literally present in the diagnostic.
    return source.split(separator)[0] + SWIFT


def validate_event(row, request, variant, event_type, glyph=None):
    require(type(row) is dict and row.get("type") == event_type
            and row.get("request_id") == request["request_id"]
            and type(row.get("face_index")) is int and row["face_index"] == request["face_index"]
            and row.get("writer_variant") == variant["name"], "native_event_identity_mismatch")
    location, reported = row.get("location"), row.get("reported_location")
    require(type(location) is dict and set(location) == set(TAGS)
            and all(bits(location[tag]) == bits(variant["location"][tag]) for tag in TAGS),
            "native_input_location_bits_changed")
    require(type(reported) is dict and set(reported) <= set(TAGS)
            and all(payload.finite_number(v) for v in reported.values()), "invalid_native_reported_axes")
    if glyph is not None:
        require(type(row.get("glyph_id")) is int and row["glyph_id"] == glyph, "native_GID_changed")
    return reported


class EchoTracker:
    def __init__(self, axes, variants, current):
        self.axes, self.variants, self.current = axes, variants, current
        self.first = self.last = None
        self.seen = {tag: {} for tag in TAGS}
        self.observations = 0

    def add(self, reported):
        require(type(reported) is dict and set(reported) <= set(TAGS), "invalid_native_echo_dictionary")
        state = {}
        for tag in TAGS:
            value = reported.get(tag, self.axes[tag][1])
            encoded = bits(value)
            state[tag] = {"reported_present": tag in reported, "effective_value": value,
                          "binary64_hex": encoded,
                          "declared_candidate_bit_matches": [v["name"] for v in self.variants
                                                              if bits(v["location"][tag]) == encoded]}
            self.seen[tag][(tag in reported, encoded)] = state[tag]
        if self.first is None:
            self.first = state
        self.last = state
        self.observations += 1

    def result(self):
        require(self.first is not None, "no_axis_observations")
        return {"axis_observation_rounds": self.observations, "axes": {
            tag: {"input_value": self.current["location"][tag],
                  "input_binary64_hex": bits(self.current["location"][tag]),
                  "initial_echo": self.first[tag], "final_echo": self.last[tag],
                  "distinct_echoes": list(self.seen[tag].values()),
                  "echo_constant_during_glyph_reads": len(self.seen[tag]) == 1,
                  "every_effective_echo_matches_input_bits": all(
                      row["binary64_hex"] == bits(self.current["location"][tag]) for row in self.seen[tag].values()),
                  "nondefault_axis_omitted": self.current["location"][tag] != self.axes[tag][1]
                      and any(not row["reported_present"] for row in self.seen[tag].values())}
            for tag in TAGS}}


def compare_case(private, gids):
    """Compare all predeclared candidates; never select the best result."""
    require(bool(gids) and len(set(gids)) == len(gids)
            and all(type(gid) is int and gid >= 0 for gid in gids), "nonempty_unique_GIDs_required")
    require(set(private) == set(ORDERS) and all(set(private[o]) == set(VARIANTS) for o in ORDERS),
            "incomplete_candidate_comparison_matrix")
    require(all(set(private[o][v]) == set(gids) for o in ORDERS for v in VARIANTS),
            "incomplete_candidate_GID_matrix")
    within = {order: {name: payload.empty_stats() for name in VARIANTS[1:]} for order in ORDERS}
    across = {name: payload.empty_stats() for name in VARIANTS}
    for gid in gids:
        for order in ORDERS:
            for name in VARIANTS[1:]:
                payload.accumulate(within[order][name], payload.compare_private_glyphs(
                    private[order]["requested"][gid], private[order][name][gid]))
        for name in VARIANTS:
            payload.accumulate(across[name], payload.compare_private_glyphs(
                private["forward"][name][gid], private["reverse"][name][gid]))
    return {"within_process_against_requested": within, "across_process_same_candidate": across,
            "requested_self_comparisons": 0}


class BoundaryNative(payload.NativeProcess):
    def __init__(self, binary, source, digest, order):
        self.process = subprocess.Popen([str(binary), str(source), digest, order], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.reader = TimedLineReader(self.process.stdout.fileno())
        self.order = order


def inspect_source(source, kind):
    require(kind in ("original", "synthetic"), "unknown_source_kind")
    digest = sha256(source)
    if kind == "original":
        require(digest == EXPECTED and source.stat().st_size == 61_473_880, "exact_original_source_required")
    with TTCollection(source, lazy=True) as collection:
        count, glyphs = (32, 47102) if kind == "original" else (2, 3)
        require(len(collection.fonts) == count and all(f["maxp"].numGlyphs == glyphs for f in collection.fonts),
                "source_face_or_GID_count_mismatch")
        identity = checkpoint_source_faces(collection.fonts)
        axes = {i: {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in f["fvar"].axes}
                for i, f in enumerate(collection.fonts)}
    faces = ORIGINAL_FACES if kind == "original" else (0, 1)
    gids = payload.DEFAULT_GIDS if kind == "original" else (0, 1, 2)
    planned = [{**case, "request_id": f"{kind}-{face}-{case['case']}", "face_index": face, "glyph_ids": list(gids)}
               for face in faces for case in positions(axes[face], kind)]
    return digest, identity, axes, faces, gids, planned


def observe_source(source, kind, binary, report, save):
    digest, identity, axes, faces, gids, planned = inspect_source(source, kind)
    section = {"status": "RUNNING", "source_sha256": digest, "source_kind": kind,
               "physical_faces_verified": len(identity), "selected_faces": list(faces),
               "selected_glyph_count": len(gids), "requested_positions": len(planned),
               "all_source_GIDs_compared": kind == "synthetic", "native_glyph_records_read": 0,
               "completed_positions": 0, "cases": []}
    report["sources"][kind] = section
    save()
    processes = []
    try:
        for order in ORDERS:
            processes.append(BoundaryNative(binary, source, digest, order))
        for native in processes:
            metadata = native.read(timeout=120)
            require(metadata.get("type") == "metadata" and metadata.get("order") == native.order
                    and metadata.get("backend") == "CoreText" and metadata.get("axis_observations_only") is True,
                    "native_observation_metadata_required")
            verify_checkpoint_session_metadata(metadata, digest, source.stat().st_size, identity)
            require(all(f.get("status") == "identity_verified" for f in metadata["faces"]),
                    "native_physical_face_identity_not_verified")
        for request in planned:
            section["active_case"] = {key: request[key] for key in ("request_id", "face_index", "case")}
            private = {order: {} for order in ORDERS}
            observed = {order: {} for order in ORDERS}
            for native in processes:
                native.send(request)
            for phase in range(len(VARIANTS)):
                for native in processes:
                    variant = request["variants"][phase if native.order == "forward" else len(VARIANTS) - 1 - phase]
                    tracker = EchoTracker(axes[request["face_index"]], request["variants"], variant)
                    tracker.add(validate_event(native.read(), request, variant, "stage_start"))
                    rows = {}
                    for gid in gids:
                        section["active_GID"] = gid
                        row = native.read()
                        tracker.add(validate_event(row, request, variant, "glyph", gid))
                        payload._private_payload(row)
                        rows[gid] = row
                        section["native_glyph_records_read"] += 1
                    end = native.read()
                    tracker.add(validate_event(end, request, variant, "stage_end"))
                    require(type(end.get("glyph_records")) is int and end["glyph_records"] == len(gids),
                            "native_candidate_stage_incomplete")
                    private[native.order][variant["name"]] = rows
                    observed[native.order][variant["name"]] = tracker.result()
            section["cases"].append({**section["active_case"], "declared_variants": copy.deepcopy(request["variants"]),
                                     "observed_axes": observed, "payload_comparisons": compare_case(private, gids)})
            section["completed_positions"] += 1
            section.pop("active_case", None); section.pop("active_GID", None)
            save()
        for native in processes:
            native.process.stdin.close()
        for native in processes:
            finished = native.read()
            require(finished.get("type") == "finished" and finished.get("source_sha256") == digest
                    and type(finished.get("request_count")) is int and finished["request_count"] == len(planned)
                    and type(finished.get("glyph_records")) is int
                    and finished["glyph_records"] == len(planned) * len(gids) * len(VARIANTS),
                    "native_final_counts_mismatch")
            require(native.reader.readline(timeout=30) == "", "unexpected_native_output_after_summary")
            require(native.process.wait(timeout=10) == 0, "native_process_exit_failed")
        require(sha256(source) == digest, "source_changed_during_boundary_probe")
        section.update(status="ALL_DECLARED_OBSERVATIONS_COMPLETE_NOT_FONT_ACCEPTANCE", source_unchanged=True)
    finally:
        for native in processes:
            native.close()
    save()


def run(source, output, mode="both"):
    output = Path(output)
    require(mode in ("both", "original", "synthetic"), "unknown_probe_mode")
    require(mode == "synthetic" or source is not None, "original_source_path_required")
    require(not output.exists() and not output.is_symlink(), "new_output_path_required")
    code_path = Path(__file__).with_name("coretext_extract.swift")
    code = code_path.read_text(encoding="utf-8")
    harness = make_harness(code)
    report = {"status": "NOT_RUN", "source_commit": os.environ.get("GITHUB_SHA"), "platform": platform.platform(),
              "source_code_sha256": sha256(code_path), "probe_code_sha256": sha256(Path(__file__)),
              "comparison_code_sha256": sha256(Path(payload.__file__)), "mode": mode,
              "declared_candidate_order": list(VARIANTS), "process_orders": list(ORDERS),
              "candidate_definitions": {"divide1": "trunc(x*10000)/10000", "multiply1": "trunc(x*10000)*0.0001",
                                        "divide2": "trunc(divide1*10000)/10000", "multiply2": "trunc(multiply1*10000)*0.0001"},
              "all_candidates_predeclared_before_native_processes": True, "recursive_search": False,
              "candidate_selection_or_acceptance": False, "production_guard_changed": False,
              "original_strict_axis_tolerance": 1e-6, "payload_comparison_tolerance": 0.,
              "raw_commands_or_metrics_published": False, "native_stdout_written_to_disk": False,
              "converted_font_generated": False, "whole_font_acceptance": "NOT_ESTABLISHED",
              "process_scope_does_not_claim_system_font_service_cache_reset": True, "sources": {}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, allow_nan=False)
    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory(prefix="swirl-axis-boundary-") as directory:
            temporary = Path(directory)
            swift, binary = temporary / "probe.swift", temporary / "probe"
            swift.write_text(harness, encoding="utf-8")
            compilation = subprocess.run(["xcrun", "swiftc", "-O", str(swift), "-o", str(binary)],
                                         capture_output=True, text=True, timeout=180)
            if compilation.returncode:
                report["swift_compilation_diagnostic"] = compilation.stderr[-8000:]
                raise BoundaryError("boundary_swift_compile_failed")
            if mode in ("original", "both"):
                observe_source(Path(source), "original", binary, report, save)
            if mode in ("synthetic", "both"):
                fixture = temporary / "self-authored-fixture.ttc"
                make_fixture(fixture)
                observe_source(fixture, "synthetic", binary, report, save)
        report["status"] = "ALL_DECLARED_OBSERVATIONS_COMPLETE_NOT_FONT_ACCEPTANCE"
    except Exception as error:
        report["status"] = "BOUNDARY_PROBE_FAILED"
        report["error"] = str(error) if isinstance(error, (BoundaryError, payload.ProbeError)) else type(error).__name__
        save()
        raise
    save()
    print(json.dumps({"status": report["status"], "sources": {key: {field: row[field] for field in
        ("status", "source_sha256", "selected_faces", "selected_glyph_count", "completed_positions", "native_glyph_records_read")}
        for key, row in report["sources"].items()}}, allow_nan=False), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?")
    parser.add_argument("--mode", choices=("both", "original", "synthetic"), default="both")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.source, args.output, args.mode)
    except Exception:
        print("boundary_probe_failed; inspect safe summary", file=sys.stderr)
        raise SystemExit(2)
