#!/usr/bin/env python3
"""Compare exact-source CoreText USER instances with independent HVGL geometry.

The diagnostic instance helper observes, but does not accept, differing API
readbacks. Production makeInstance and its original guard remain unchanged.
Every outline stays in a private process/temporary directory. Public reports
contain coordinates, counts, GIDs and discrepancies only. A best candidate at
one point never stands in for one model passing the entire requested sample.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile

import numpy as np
from fontTools.ttLib import TTCollection

from calibrate_hvf_geometry import EXPECTED, LIMIT, discrepancy, native_paths, portable_paths, select_glyphs
from calibrate_avar_metrics import normalize, ordered_intervals
from compare_axis_construction import GUARD
from axis_geometry_candidates import map_signed_zero_raw_order, targeted_user_locations

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from audit_font import raw_avar
from batch_geometry import BatchGeometry
from hvf import HVGL
from rebuild import NativeOracle, user_location
from source_metrics import SourceMetrics

MODELS = ("raw_order_float", "raw_order_final_f2dot14", "raw_order_two_f2dot14",
          "signed_zero_raw_order_two_f2dot14")


def require(value, message):
    if not value:
        raise ValueError(message)


def make_harness(text):
    require(text.count(GUARD) == 1 and text.count("\nfunc run() throws {") == 1,
            "review_changed_production_helper")
    text = text.replace(GUARD, "        _ = effective // Diagnostic only: record the mismatch, never accept it.")
    text = text.replace('"backend": "CoreText",',
                        '"backend": "CoreText", "diagnostic_readback_observation_only": true,', 1)
    require('"diagnostic_readback_observation_only": true' in text,
            "diagnostic_metadata_marker_missing")
    return text


def coretext_paths(commands):
    events, opened = [], False
    for command in commands:
        name, *values = command
        if name == "moveTo":
            require(not opened, "unclosed_coretext_contour")
            require(len(values) == 2, "invalid_move")
            events.extend([["begin_path"], ["move", *values]])
            opened = True
        elif name in ("lineTo", "qCurveTo", "curveTo"):
            require(opened, "coretext_segment_outside_contour")
            kind, count = {"lineTo": ("line", 2), "qCurveTo": ("quad", 4),
                           "curveTo": ("cubic", 6)}[name]
            require(len(values) == count, "invalid_segment")
            events.append([kind, *values])
        elif name == "closePath":
            require(opened and not values, "invalid_close")
            events.extend([["close"], ["end_path"]])
            opened = False
        else:
            raise ValueError("unknown_coretext_command")
    require(not opened, "unclosed_coretext_contour")
    return native_paths(events)


def axis_records(font):
    tags = [a.axisTag for a in font["fvar"].axes]
    raw = raw_avar(font.reader["avar"], tags)
    return {a["tag"]: [(v["from_f2dot14"] / 16384, v["to_f2dot14"] / 16384)
                       for v in a["records"]] for a in raw["axes"]}


def map_location(font, records, location, model):
    require(model in MODELS, "unknown_mapping_model")
    result = {}
    for axis in font["fvar"].axes:
        value = normalize(location[axis.axisTag], axis.minValue, axis.defaultValue, axis.maxValue)
        if model == "signed_zero_raw_order_two_f2dot14":
            result[axis.axisTag] = map_signed_zero_raw_order(value, records[axis.axisTag])
            continue
        if model == "raw_order_two_f2dot14":
            value = math.floor(value * 16384 + .5) / 16384
        mapped = 0. if value == 0. else ordered_intervals(records[axis.axisTag], value)
        if model != "raw_order_float":
            mapped = math.floor(mapped * 16384 + .5) / 16384
        require(math.isfinite(mapped) and -1 <= mapped <= 1, "mapped_coordinate_out_of_range")
        result[axis.axisTag] = mapped
    return result


def requests_for_face(font, face):
    axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
    tags = list(axes)
    require(tags == ["WDTH", "wght", "HGHT"], "original_axis_order_changed")
    normalized = [dict(zip(tags, p)) for p in itertools.product((-1., 0., 1.), repeat=3)]
    for tag in tags:
        for value in (-.265625, .201171875, .951416015625, .123456789):
            p = dict.fromkeys(tags, 0.); p[tag] = value; normalized.append(p)
    rng = random.Random(20371020 + face)
    normalized += [{tag: rng.uniform(-.98, .98) for tag in tags} for _ in range(3)]
    records = axis_records(font)
    for tag in tags:
        for value, _ in records[tag]:
            for offset in (-1 / 65536, 0., 1 / 65536):
                if -1 <= value + offset <= 1:
                    p = dict.fromkeys(tags, 0.); p[tag] = value + offset; normalized.append(p)
    seen, result = set(), []
    for p in normalized:
        location = user_location(p, axes)
        key = tuple(location[tag] for tag in tags)
        if key not in seen:
            result.append(location); seen.add(key)
    for item in targeted_user_locations(axes):
        location = item["location"]
        key = tuple(location[tag] for tag in tags)
        if key not in seen:
            result.append(location); seen.add(key)
    return result


def new_stats():
    return {"checks": 0, "failures": 0, "maximum_point_error": 0., "failure_types": {}, "examples": []}


def record_check(stats, face, gid, location, comparison):
    stats["checks"] += 1
    error = None
    try:
        error = comparison()
        require(math.isfinite(error), "nonfinite_comparison")
        stats["maximum_point_error"] = max(stats["maximum_point_error"], error)
        require(error <= LIMIT, "outline_budget_exceeded")
    except ValueError as failure:
        reason = str(failure)
        stats["failures"] += 1
        stats["failure_types"][reason] = stats["failure_types"].get(reason, 0) + 1
        if len(stats["examples"]) < 2048:
            stats["examples"].append({"face_index": face, "glyph_id": gid,
                                      "user_location": location, "reason": reason,
                                      "maximum_point_error": error})


def render_face_references(renderer, selected, mapped_locations):
    """Batch only deterministic portable calculations; native requests stay separate."""
    designs = np.asarray([list(mapped[model].values())
                          for mapped in mapped_locations for model in MODELS])
    return {gid: renderer.render(gid, designs[:, :renderer.table.part(gid).axis_count])
            for gid in selected}


def run(source, output):
    require(not output.exists() and output.resolve() != source.resolve(), "new_report_path_required")
    require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "exact_original_source_required")
    report = {"status": "NOT_RUN", "source_sha256": EXPECTED, "source_commit": os.environ.get("GITHUB_SHA"),
              "scope": "sampled_user_coordinates_not_complete_font_acceptance",
              "outline_limit_font_units": LIMIT, "faces_completed": 0, "user_positions": 0,
              "source_outlines_published": False, "final_font_generated": False,
              "production_readback_guard_unchanged": True, "models": {m: new_stats() for m in MODELS},
              "request_vs_reported_instance": new_stats(), "readback_differences": 0,
              "raw_metric_differences": {}, "faces": []}
    report["new_candidate_scope"] = "signed_zero_geometry_hypothesis_not_HVAR_mapping_acceptance"
    report["retained_prior_HVAR_quantization_disagreements"] = 141
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix="swirl-user-geometry-") as temp:
        fonts = collection.fonts
        require(len(fonts) == 32 and all(f["maxp"].numGlyphs == 47102 for f in fonts), "all_source_faces_gids_required")
        root = Path(temp); swift = root / "diagnostic.swift"; binary = root / "diagnostic"
        swift.write_text(make_harness(Path(__file__).with_name("coretext_extract.swift").read_text()))
        compiled = subprocess.run(["xcrun", "swiftc", "-O", str(swift), "-o", str(binary)],
                                  capture_output=True, text=True, timeout=180)
        require(compiled.returncode == 0, "native_helper_compile_failed:" + compiled.stderr[-4000:])
        table = HVGL(fonts[0].reader["hvgl"])
        selected, coverage = select_glyphs(table)
        report.update(selected_glyphs=selected, structural_coverage=coverage)
        renderer = BatchGeometry(table, isolated_tangents=True)
        hvgl_hash = hashlib.sha256(fonts[0].reader["hvgl"]).hexdigest()
        oracle = NativeOracle(binary, source, root / "oracle.log")
        try:
            require(oracle.metadata.get("diagnostic_readback_observation_only") is True, "wrong_diagnostic_binary")
            report["physical_faces_verified"] = len(oracle.metadata["faces"])
            report["os_version"] = oracle.metadata.get("os_version")
            for face, font in enumerate(fonts):
                require(hashlib.sha256(font.reader["hvgl"]).hexdigest() == hvgl_hash, "unshared_source_geometry")
                records = axis_records(font); positions = requests_for_face(font, face)
                metrics = SourceMetrics(font)
                mapped_locations = [{m: map_location(font, records, location, m) for m in MODELS}
                                    for location in positions]
                # Evaluation has no cross-sample state. Keep every native face,
                # request and metric observation; batch only this pure reference.
                reference_batches = render_face_references(renderer, selected, mapped_locations)
                start = report["models"][MODELS[0]]["checks"]
                for position_number, location in enumerate(positions):
                    original = oracle.samples(face, selected, location)
                    reported = {a.axisTag: original[selected[0]]["reported_location"].get(a.axisTag, a.defaultValue)
                                for a in font["fvar"].axes}
                    require(all(r["reported_location"] == original[selected[0]]["reported_location"] for r in original.values()),
                            "inconsistent_instance_readback")
                    changed = any(reported[k] != location[k] for k in location)
                    report["readback_differences"] += changed
                    echoed = oracle.samples(face, selected, reported) if changed else original
                    mapped = mapped_locations[position_number]
                    for gid in selected:
                        actual = coretext_paths(original[gid]["commands"])
                        record_check(report["request_vs_reported_instance"], face, gid, location,
                                     lambda: discrepancy(actual, coretext_paths(echoed[gid]["commands"]))[0])
                        batch = reference_batches[gid]
                        for i, model in enumerate(MODELS):
                            sample_index = position_number * len(MODELS) + i
                            record_check(report["models"][model], face, gid, location,
                                lambda i=sample_index: discrepancy(portable_paths([p[i] for p in batch.paths]), actual)[0])
                        ideal = metrics.at(gid, mapped["raw_order_final_f2dot14"])
                        for field in ("advance_width", "advance_height", "vertical_origin_x", "vertical_origin_y"):
                            difference = abs(original[gid][field] - ideal[field])
                            item = report["raw_metric_differences"].setdefault(field, {"checks": 0, "over_budget": 0, "maximum_error": 0.})
                            item["checks"] += 1; item["over_budget"] += difference > LIMIT
                            if difference > item["maximum_error"]:
                                item["maximum_error_context"] = {"face_index": face, "glyph_id": gid,
                                    "user_location": location, "reported_location": reported,
                                    "raw_native_value": original[gid][field], "source_table_value": ideal[field],
                                    "source_design_coordinates": mapped["raw_order_final_f2dot14"]}
                            item["maximum_error"] = max(item["maximum_error"], difference)
                    report["user_positions"] += 1
                    if position_number % 16 == 15:
                        save()
                report["faces_completed"] += 1
                report["faces"].append({"face_index": face, "positions": len(positions),
                    "glyph_instances": report["models"][MODELS[0]]["checks"] - start})
                save()
                print(json.dumps({"face_completed": face, "positions": report["user_positions"],
                    "model_failures": {m: report["models"][m]["failures"] for m in MODELS}}), flush=True)
        except Exception as error:
            report.update(status="USER_GEOMETRY_EXECUTION_FAILED", error_type=type(error).__name__, error=str(error)[:600])
            save(); raise
        finally:
            oracle.close()
    report["source_unchanged"] = hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED
    require(report["source_unchanged"], "source_changed_during_native_comparison")
    report["models_passing_entire_sample"] = [m for m in MODELS if not report["models"][m]["failures"]]
    report["status"] = "SAMPLED_USER_GEOMETRY_PASS" if report["models_passing_entire_sample"] else "USER_GEOMETRY_MODELS_REJECTED"
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source, args.output)
    print(json.dumps({"status": result["status"], "faces_completed": result["faces_completed"]}), flush=True)
