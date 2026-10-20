#!/usr/bin/env python3
"""Fresh exact-source axis thresholds: native paths, HVAR and libhvf.

This is an observation-only experiment, never a production mapper. All raw
outlines/advances remain private in memory. Each face is observed in two new
CoreText processes with opposite request orders and a checked final transcript.
The existing geometric comparator and 1/32 budget are reused unchanged.
HVAR-conditioned design references are explicitly separate from global mapping
hypotheses: choosing an inferred coordinate per observation is not a formula.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import tempfile

import numpy as np
from fontTools.ttLib import TTCollection

from analyze_axis_quantization import Axis, Candidate, predict
from axis_threshold_cases import threshold_cases
from calibrate_avar_metrics import infer_source_weight_locations, normalize
from calibrate_hvf_geometry import EXPECTED, LIMIT, discrepancy, native_paths, portable_paths, select_glyphs
from probe_user_axis_geometry import (MODELS, axis_records, coretext_paths, make_harness,
                                     map_location, new_stats, record_check, require)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from batch_geometry import BatchGeometry
from hvf import HVGL
from rebuild import NativeOracle
from source_metrics import SourceMetrics
from verified_axis_oracle import (ENVELOPE, declare_readback, finite_number, same_json,
                                  source_identities, validate_native_record)

TAGS = ("WDTH", "wght", "HGHT")
METRIC_GIDS = (5, 12, 56, 169)
EXTRA_MODELS = ("request_normalized16_truncate", "canonical_normalized16_truncate")
ALL_MODELS = MODELS + EXTRA_MODELS
INFERRED_REFERENCES = ("hvar_grid_minus_one", "hvar_grid", "hvar_grid_plus_one")


def bits(location):
    return {tag: struct.pack(">d", float(value)).hex() for tag, value in location.items()}


def mapping_candidates(font, records, location):
    """Predeclared global hypotheses; no observed value enters this function."""
    result = {name: map_location(font, records, location, name) for name in MODELS}
    canonical = {tag: plan["canonical"] for tag, plan in declare_readback(location).items()}
    for name, applied in zip(EXTRA_MODELS, (location, canonical)):
        mapped = {}
        for a in font["fvar"].axes:
            raw = tuple((int(x * 16384), int(y * 16384)) for x, y in records[a.axisTag])
            axis = Axis(a.axisTag, a.minValue, a.defaultValue, a.maxValue, raw)
            mapped[a.axisTag] = predict(applied[a.axisTag], axis,
                Candidate(name, normalization="normalized16_truncate"))["final_normalized"]
        result[name] = mapped
    return result


def check_metadata(native, identities, byte_size):
    require(native.get("diagnostic_readback_observation_only") is True
            and native.get("axis_observations_only") is False
            and native.get("backend") == "CoreText"
            and native.get("source_sha256") == EXPECTED
            and native.get("source_byte_size") == byte_size, "wrong_native_diagnostic_identity")
    faces = native.get("faces")
    require(isinstance(faces, list) and len(faces) == len(identities) == 32,
            "all_original_physical_faces_required")
    for expected, actual in zip(identities, faces):
        require(actual.get("status") == "identity_verified" and all(
            same_json(actual.get(key), value) for key, value in expected.items()),
            "original_face_table_identity_mismatch")


def checked_batch(oracle, face, gids, location):
    records = oracle.samples(face, gids, location)
    request = {"request_id": str(oracle.sequence), "face_index": face,
               "glyph_ids": gids, "location": location}
    seen = set()
    for record in records.values():
        validate_native_record(record, request, seen)
        reported = record.get("reported_location")
        require(isinstance(reported, dict) and set(reported) <= set(TAGS)
                and all(finite_number(v) for v in reported.values()), "invalid_native_readback")
    require(seen == set(gids), "incomplete_native_glyph_batch")
    first = records[gids[0]]["reported_location"]
    require(all(same_json(r["reported_location"], first) for r in records.values()),
            "inconsistent_native_instance_readback")
    return records


def same_private_payload(left, right):
    """Ignore only the transport envelope, retaining every raw payload field."""
    require(left["face_index"] == right["face_index"] and left["glyph_id"] == right["glyph_id"]
            and same_json(left["location"], right["location"]), "cross_process_identity_mismatch")
    return same_json({k: v for k, v in left.items() if k not in ENVELOPE},
                     {k: v for k, v in right.items() if k not in ENVELOPE})


def metric_stats():
    return {"checks": 0, "exact_matches": 0, "outside_1_32": 0, "maximum_error": 0.}


def add_metric(stats, error):
    require(math.isfinite(error) and error >= 0, "nonfinite_metric_difference")
    stats["checks"] += 1
    stats["exact_matches"] += error == 0
    stats["outside_1_32"] += error > LIMIT
    stats["maximum_error"] = max(stats["maximum_error"], error)


def conditioned_grid(inference):
    """A supported best-fit grid reference, never a unique tolerance solution."""
    best = inference["best_fit"]
    value, residual = best["normalized_weight"], best["max_metric_residual"]
    if not (inference["within_unchanged_metric_budget"] is True and finite_number(value)
            and -1 <= value <= 1 and finite_number(residual) and 0 <= residual <= LIMIT):
        return None
    q = math.floor(value * 16384 + .5)
    return q if abs(value * 16384 - q) <= 1e-8 else None


def infer_at_axis_nodes(font, records, cases, observations):
    """Only infer weight when the other two coordinates are independently exact.

    Width/height must be original min/default/max and have raw identity avar.
    HVAR's height regions must be neutral. Random mixed positions still undergo
    the six global outline/metric tests, but do not receive a guessed inverse.
    """
    axes = {a.axisTag: a for a in font["fvar"].axes}
    identity = [(-1., -1.), (0., 0.), (1., 1.)]
    require(records["WDTH"] == identity and records["HGHT"] == identity,
            "inference_requires_identity_width_height_avar")
    height_index = list(axes).index("HGHT")
    for region in font["HVAR"].table.VarStore.VarRegionList.Region:
        a = region.VarRegionAxis[height_index]
        require((a.StartCoord, a.PeakCoord, a.EndCoord) == (0., 0., 0.),
                "inference_requires_neutral_HVAR_height")
    selected, indices = [], []
    for index, (case, samples) in enumerate(zip(cases, observations)):
        location = case["location"]
        if not all(location[tag] in (axes[tag].minValue, axes[tag].defaultValue, axes[tag].maxValue)
                   for tag in ("WDTH", "HGHT")):
            continue
        selected.append(({"location": location, "glyph_ids": list(METRIC_GIDS)},
                         {"advances": [samples[gid]["advance_width"] for gid in METRIC_GIDS]}))
        indices.append(index)
    return dict(zip(indices, infer_source_weight_locations(font, selected)))


def compare_face(font, face, cases, observations, renderer, gids, report, mappings):
    records = axis_records(font)
    metrics = SourceMetrics(font)
    inferred = infer_at_axis_nodes(font, records, cases, observations)
    safe_rows, specifications = [], []
    native_geometry = [{gid: coretext_paths(samples[gid]["commands"]) for gid in gids}
                       for samples in observations]
    for index, (case, samples, mapped) in enumerate(zip(cases, observations, mappings)):
        location = case["location"]
        row = {**case, "requested_binary64_hex": bits(location),
               "reported_location": samples[gids[0]]["reported_location"],
               "reported_binary64_hex": bits(samples[gids[0]]["reported_location"]),
               "global_model_design_coordinates": mapped, "geometry": {}, "horizontal_metric_errors": {}}
        for name, design in mapped.items():
            specifications.append((index, name, design))
            error = max(abs(samples[gid]["advance_width"] - metrics.at(gid, design)["advance_width"])
                        for gid in METRIC_GIDS)
            add_metric(report["global_models"][name]["horizontal_metrics"], error)
            row["horizontal_metric_errors"][name] = error
        if index in inferred:
            inference = inferred[index]
            row["HVAR_inference"] = inference
            value = inference["best_fit"]["normalized_weight"]
            q = conditioned_grid(inference)
            if q is not None:
                grid_error = abs(value * 16384 - q)
                row["HVAR_inference_grid_error"] = grid_error
                row["best_fit_grid_is_not_a_unique_tolerance_solution"] = True
                if grid_error <= 1e-8:
                    row["HVAR_inferred_f2dot14"] = q
                    axes = {a.axisTag: a for a in font["fvar"].axes}
                    design = {tag: normalize(location[tag], axes[tag].minValue,
                        axes[tag].defaultValue, axes[tag].maxValue) for tag in TAGS}
                    row["neighbor_grid_metric_residuals"] = []
                    for delta in (-2, -1, 0, 1, 2):
                        if not -16384 <= q + delta <= 16384:
                            continue
                        point = {**design, "wght": (q + delta) / 16384}
                        error = max(abs(samples[gid]["advance_width"] - metrics.at(gid, point)["advance_width"])
                                    for gid in METRIC_GIDS)
                        row["neighbor_grid_metric_residuals"].append({"f2dot14": q + delta,
                                                                   "max_metric_residual": error})
                        if delta in (-1, 0, 1):
                            name = INFERRED_REFERENCES[delta + 1]
                            specifications.append((index, name, point))
                            if delta == 0:
                                row["HVAR_conditioned_design_coordinate"] = point
        safe_rows.append(row)
    # Batch the established renderer only; every CoreText observation is actual.
    for start in range(0, len(specifications), 1024):
        chunk = specifications[start:start + 1024]
        matrix = np.asarray([[design[tag] for tag in TAGS] for _, _, design in chunk])
        for gid in gids:
            batch = renderer.render(gid, matrix[:, :renderer.table.part(gid).axis_count])
            for offset, (index, name, _) in enumerate(chunk):
                row = safe_rows[index]
                group = report["global_models"][name]["geometry"] if name in ALL_MODELS else report["HVAR_conditioned_references"][name]
                local = row["geometry"].setdefault(name, {"checks": 0, "failures": 0, "maximum_error": 0., "failure_types": {}})
                observed = {}
                def compare():
                    try:
                        observed["error"] = discrepancy(portable_paths([p[offset] for p in batch.paths]), native_geometry[index][gid])[0]
                        return observed["error"]
                    except ValueError as failure:
                        observed["reason"] = str(failure)
                        raise
                record_check(group, face, gid, row["location"], compare)
                local["checks"] += 1
                error = observed.get("error")
                if error is not None and math.isfinite(error):
                    local["maximum_error"] = max(local["maximum_error"], error)
                reason = observed.get("reason")
                if reason is None and (error is None or not math.isfinite(error) or error > LIMIT):
                    reason = "nonfinite_comparison" if error is None or not math.isfinite(error) else "outline_budget_exceeded"
                if reason is not None:
                    local["failures"] += 1
                    local["failure_types"][reason] = local["failure_types"].get(reason, 0) + 1
    return safe_rows, native_geometry


def hvf_paths(binary, source, face, gid, design):
    values = [design[tag] for tag in TAGS]
    native = subprocess.run([str(binary), str(source), str(face), ",".join(map(str, values)), str(gid), "1"],
                            capture_output=True, text=True, timeout=30)
    require(native.returncode == 0, "native_HVF_process_failed")
    rows = [json.loads(line) for line in native.stdout.splitlines()]
    require(len(rows) == 3, "incomplete_native_HVF_transcript")
    header, outline, summary = rows
    require(header.get("record") == "header" and header.get("schema") == 1
            and header.get("engine") == "Apple HVF"
            and header.get("coordinate_space") == "normalized_design_after_avar"
            and header.get("face_index") == face and header.get("face_count") == 32
            and header.get("maxp_glyphs") == 47102 and header.get("input_bytes") == 61473880
            and header.get("fvar_axis_tags") == list(TAGS) and header.get("normalized_coords") == values
            and header.get("start") == gid and header.get("count") == 1, "native_HVF_identity_mismatch")
    require(outline.get("record") == "outline" and outline.get("part_index") == gid
            and outline.get("status") == "OK" and outline.get("native_code") == 0
            and type(outline.get("part_axis_count")) is int and 0 <= outline["part_axis_count"] <= 3
            and type(outline.get("applied_axis_count")) is int
            and outline.get("part_axis_count") == outline.get("applied_axis_count"), "native_HVF_render_failed")
    require(summary.get("record") == "summary" and summary.get("status") == "EXTRACTED"
            and summary.get("rendered") == 1 and summary.get("failed") == 0, "native_HVF_summary_failed")
    events, counters = outline.get("events"), outline.get("counters")
    arities = {"begin_part": 1, "end_part": 1, "begin_path": 0, "end_path": 0,
               "close": 0, "stop": 0, "move": 2, "line": 2, "quad": 4, "cubic": 6}
    count_fields = {"begin_part": "parts_begun", "end_part": "parts_ended", "begin_path": "paths_begun",
                    "end_path": "paths_ended", "move": "moves", "line": "lines", "quad": "quads",
                    "cubic": "cubics", "close": "closes"}
    require(isinstance(events, list) and isinstance(counters, dict), "missing_native_HVF_events_or_counters")
    counted = dict.fromkeys(("events", *count_fields.values()), 0)
    stack = []
    for event in events:
        require(isinstance(event, list) and bool(event) and isinstance(event[0], str)
                and event[0] in arities and len(event) == arities[event[0]] + 1
                and all(finite_number(value) for value in event[1:]), "invalid_native_HVF_event")
        kind = event[0]
        counted["events"] += 1
        if kind in count_fields:
            counted[count_fields[kind]] += 1
        if kind == "begin_part":
            require(type(event[1]) is int and event[1] >= 0, "invalid_native_HVF_part_ID")
            stack.append(event[1])
        elif kind == "end_part":
            require(bool(stack) and stack.pop() == event[1], "unbalanced_native_HVF_parts")
    require(not stack and all(type(counters.get(key)) is int and counters[key] == value
                             for key, value in counted.items()), "native_HVF_counter_mismatch")
    return native_paths(events)


def direct_hvf_checks(binary, source, face, rows, native_geometry, renderer, report):
    if face not in (15, 20, 24, 31):
        return
    for index, row in enumerate(rows):
        if not set(row["cohorts"]) & {"historical_controls", "targeted_thresholds", "default_thresholds"}:
            continue
        design = row.get("HVAR_conditioned_design_coordinate")
        if design is None:
            continue
        for gid in (5, 56, 19177):
            report["active_context"] = {"stage": "native_HVF_comparison", "face_index": face,
                "glyph_id": gid, "user_location": row["location"], "design_location": design}
            actual = hvf_paths(binary, source, face, gid, design)
            record_check(report["native_HVF_vs_CoreText"], face, gid, row["location"],
                         lambda: discrepancy(actual, native_geometry[index][gid])[0])
            matrix = np.asarray([[design[tag] for tag in TAGS]])
            batch = renderer.render(gid, matrix[:, :renderer.table.part(gid).axis_count])
            record_check(report["portable_vs_native_HVF"], face, gid, row["location"],
                         lambda: discrepancy(portable_paths([p[0] for p in batch.paths]), actual)[0])


def run(source, output):
    require(not output.exists() and output.resolve() != source.resolve(), "new_report_path_required")
    require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED and source.stat().st_size == 61473880,
            "exact_original_source_required")
    report = {"status": "NOT_RUN", "source_sha256": EXPECTED, "source_commit": os.environ.get("GITHUB_SHA"),
        "platform": platform.platform(), "outline_limit_font_units": LIMIT, "metric_limit_font_units": LIMIT,
        "production_mapping_changed": False, "raw_avar_records_modified": False,
        "source_outlines_or_raw_metrics_published": False, "font_generated": False,
        "mapping_accepted": False, "continuous_space_accepted": False,
        "HVAR_conditioned_reference_is_not_a_global_mapping": True,
        "HVAR_conditioning": "accepted_best_fit_only_with_residual_and_branch_intervals_retained_no_uniqueness_claim",
        "independent_processes_do_not_claim_system_service_cache_reset": True,
        "faces_completed": 0, "user_positions": 0, "native_processes": [], "faces": [],
        "global_models": {name: {"geometry": new_stats(), "horizontal_metrics": metric_stats()} for name in ALL_MODELS},
        "HVAR_conditioned_references": {name: new_stats() for name in INFERRED_REFERENCES},
        "opposite_order": {"glyph_pairs": 0, "exact_payload_pairs": 0, "readback_mismatches": 0},
        "native_HVF_vs_CoreText": new_stats(), "portable_vs_native_HVF": new_stats()}
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    save()
    try:
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix="swirl-axis-threshold-") as directory:
            fonts = collection.fonts
            require(len(fonts) == 32 and all(f["maxp"].numGlyphs == 47102 for f in fonts), "all_source_faces_gids_required")
            identities = source_identities(fonts)
            table = HVGL(fonts[0].reader["hvgl"])
            selected, coverage = select_glyphs(table)
            gids = sorted(set(selected) | set(METRIC_GIDS) | {19177})
            report.update(selected_glyphs=gids, structural_coverage=coverage)
            renderer = BatchGeometry(table, isolated_tangents=True)
            hvgl_hash = hashlib.sha256(fonts[0].reader["hvgl"]).hexdigest()
            root = Path(directory)
            swift, binary, hvf_binary = root / "diagnostic.swift", root / "diagnostic", root / "hvf_oracle"
            code = Path(__file__).with_name("coretext_extract.swift").read_text()
            harness = make_harness(code)
            swift.write_text(harness)
            report.update(extractor_source_sha256=hashlib.sha256(code.encode()).hexdigest(),
                          generated_harness_sha256=hashlib.sha256(harness.encode()).hexdigest())
            compiled = subprocess.run(["xcrun", "swiftc", "-O", str(swift), "-o", str(binary)], capture_output=True, timeout=180)
            require(compiled.returncode == 0, "CoreText_diagnostic_compile_failed")
            compiled = subprocess.run(["xcrun", "clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-mmacosx-version-min=15.4", str(Path(__file__).with_name("hvf_oracle.c")), "-lhvf", "-o", str(hvf_binary)],
                capture_output=True, timeout=180)
            require(compiled.returncode == 0, "HVF_oracle_compile_failed")
            for face, font in enumerate(fonts):
                report["active_context"] = {"stage": "face_setup", "face_index": face}
                require(hashlib.sha256(font.reader["hvgl"]).hexdigest() == hvgl_hash, "unshared_original_HVGL")
                ranges = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
                cases = threshold_cases(ranges, face)
                records = axis_records(font)
                mappings = [mapping_candidates(font, records, case["location"]) for case in cases]
                original = [None] * len(cases)
                for order in ("forward", "reverse"):
                    oracle = NativeOracle(binary, source, root / f"face-{face}-{order}.log")
                    try:
                        check_metadata(oracle.metadata, identities, source.stat().st_size)
                        indices = range(len(cases)) if order == "forward" else reversed(range(len(cases)))
                        for index in indices:
                            report["active_context"] = {"stage": "CoreText_observation", "face_index": face,
                                "process_order": order, "case_number": index, "label": cases[index]["label"],
                                "user_location": cases[index]["location"]}
                            records = checked_batch(oracle, face, gids, cases[index]["location"])
                            if order == "forward":
                                original[index] = records
                            else:
                                cases[index]["opposite_order_payload_mismatch_gids"] = []
                                cases[index]["opposite_order_readback_mismatch_gids"] = []
                                for gid in gids:
                                    payload_equal = same_private_payload(original[index][gid], records[gid])
                                    echo_equal = same_json(original[index][gid]["reported_location"], records[gid]["reported_location"])
                                    report["opposite_order"]["glyph_pairs"] += 1
                                    report["opposite_order"]["exact_payload_pairs"] += payload_equal
                                    report["opposite_order"]["readback_mismatches"] += not echo_equal
                                    if not payload_equal:
                                        cases[index]["opposite_order_payload_mismatch_gids"].append(gid)
                                    if not echo_equal:
                                        cases[index]["opposite_order_readback_mismatch_gids"].append(gid)
                        report["active_context"] = {"stage": "CoreText_finalization", "face_index": face,
                                                    "process_order": order}
                        summary = oracle.finish()
                        report["native_processes"].append({"face_index": face, "order": order,
                            "os_version": oracle.metadata.get("os_version"), "all_32_physical_faces_verified": True,
                            "summary": summary, "exit_status": 0})
                    finally:
                        oracle.close()
                    save()
                report["active_context"] = {"stage": "portable_and_HVAR_comparison", "face_index": face}
                rows, native_geometry = compare_face(font, face, cases, original, renderer, gids, report, mappings)
                direct_hvf_checks(hvf_binary, source, face, rows, native_geometry, renderer, report)
                report["faces"].append({"face_index": face, "user_positions": len(cases), "observations": rows})
                report["faces_completed"] += 1
                report["user_positions"] += len(cases)
                report["status"] = "IN_PROGRESS_DIAGNOSIS_NOT_ACCEPTANCE"
                save()
                print(json.dumps({"face_index": face, "faces_completed": report["faces_completed"],
                                  "user_positions": report["user_positions"]}), flush=True)
                del original, native_geometry
            require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "original_source_changed")
            report.update(source_unchanged=True, status="COMPLETED_NATIVE_THRESHOLD_DIAGNOSIS_NOT_FONT_ACCEPTANCE")
            report.pop("active_context", None)
    except Exception as error:
        # Exception text may contain an untrusted native payload; publish only
        # its type. Request context already appears in the safe checkpoint.
        report.update(status="FAILED_DIAGNOSIS_NOT_ACCEPTANCE", failure_type=type(error).__name__)
        if re.fullmatch(r"[A-Za-z0-9_]{1,160}", str(error)):
            report["failure_code"] = str(error)
        save()
        raise RuntimeError("axis threshold diagnosis failed; safe checkpoint retained") from None
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
