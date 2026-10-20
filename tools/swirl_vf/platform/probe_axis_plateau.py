#!/usr/bin/env python3
"""Observe axis plateaus across native constructors and seeded base instances.

The original production constructor, descriptor/graphics alternatives, and two
seeded bases are separate experiments. None is promoted to the source oracle.
Raw outlines/metrics stay private; only identity, coordinates, differences and
HVAR-conditioned references enter the report. Original avar order is retained.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import tempfile

from fontTools.ttLib import TTCollection

from plateau_construction_harness import MODES, make_harness
from probe_axis_thresholds import (EXPECTED, LIMIT, METRIC_GIDS, TAGS, NativeOracle,
    axis_records, bits, check_metadata, checked_batch, conditioned_grid, hvf_paths,
    infer_at_axis_nodes, new_stats, record_check, require, same_json,
    same_private_payload, source_identities)
from probe_user_axis_geometry import coretext_paths, discrepancy
from calibrate_avar_metrics import normalize


def plateau_cases(ranges_by_face):
    require(set(ranges_by_face) == set(range(32)), "all_original_faces_required")
    cases = {}
    for face in (0, 5, 10, 15, 20, 24, 31):
        ranges = ranges_by_face[face]
        require(set(ranges) == set(TAGS), "all_original_axis_tags_required")
        for values in ranges.values():
            require(len(values) == 3 and all(type(v) in (float, int) and math.isfinite(v) for v in values)
                    and values[0] <= values[1] <= values[2] and values[0] < values[2], "invalid_source_axis_range")
        defaults = {tag: float(ranges[tag][1]) for tag in TAGS}
        seen, rows = set(), []

        def add(label, updates):
            location = {**defaults, **updates}
            require(all(ranges[tag][0] <= location[tag] <= ranges[tag][2] for tag in TAGS),
                    "plateau_case_outside_original_range")
            key = tuple(location[tag] for tag in TAGS)
            if key not in seen:
                seen.add(key)
                rows.append({"label": label, "location": location})

        add("original_fvar_default", {})
        for delta in (-.1, -.06, -.05, -.045, -.044, -.042, -.041, -.0401, -.04,
                      -.0399, -.039, -.038, -.037, -.0367, -.03, 0., .03, .0399,
                      .04, .0401, .041, .042, .044, .045, .05, .06, .1):
            add(f"400_boundary_{delta:g}", {"wght": 400. + delta})
        for weight in (299.96, 299.9817, 299.99, 300., 300.0062, 300.01, 300.03, 300.04, 300.06):
            add(f"300_constructor_control_{weight:g}", {"wght": weight})
        for weight in (399.96, 400.01, 400.04, 400.041):
            add(f"mixed_axes_{weight:g}", {"WDTH": 600.5859375, "wght": weight, "HGHT": 250.})
        cases[face] = rows
    return cases


@contextmanager
def constructor_mode(mode):
    """Only the child launch sees this diagnostic selector; always restore it."""
    require(mode in MODES, "unknown_plateau_constructor_mode")
    key = "SWIRL_VF_PLATEAU_MODE"
    previous = os.environ.get(key)
    os.environ[key] = mode
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def safe_failure(error):
    result = {"failure_type": type(error).__name__}
    if re.fullmatch(r"[A-Za-z0-9_]{1,160}", str(error)):
        result["failure_code"] = str(error)
    return result


def compare_payloads(left, right):
    """Keep whole-payload equality separate from scalar metric differences."""
    metric_fields = ("advance_width", "advance_height", "lsb", "horizontal_origin_x",
        "horizontal_origin_y", "vertical_origin_x", "vertical_origin_y", "horizontal_advance_sum", "vertical_advance_sum")
    metric_errors = {key: abs(left[key] - right[key]) for key in metric_fields}
    metric_errors.update({key: max(abs(a - b) for a, b in zip(left[key], right[key]))
        for key in ("horizontal_advance_vector", "vertical_advance_vector", "vertical_origin_translation")})
    require(all(math.isfinite(v) for v in metric_errors.values()), "nonfinite_metric_difference")
    result = {"complete_payload_equal": same_private_payload(left, right),
        "raw_commands_equal": same_json(left["commands"], right["commands"]),
        "readback_equal": same_json(left["reported_location"], right["reported_location"]),
        "maximum_metric_difference": max(metric_errors.values()), "metric_differences": metric_errors}
    try:
        error, segments = discrepancy(coretext_paths(left["commands"]), coretext_paths(right["commands"]))
        require(math.isfinite(error), "nonfinite_geometry_difference")
        result["canonical_geometry"] = {"maximum_point_error": error, "segments": segments,
            "status": "within_budget" if error <= LIMIT else "outside_budget"}
    except ValueError as error:
        result["canonical_geometry"] = {"status": "rejected", **safe_failure(error)}
    return result


def run(source, output):
    require(not output.exists() and source.resolve() != output.resolve(), "new_report_path_required")
    require(source.stat().st_size == 61473880 and hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED,
            "exact_original_source_required")
    report = {"status": "NOT_RUN", "source_sha256": EXPECTED, "source_commit": os.environ.get("GITHUB_SHA"),
        "platform": platform.platform(), "production_constructor_changed": False,
        "production_mapping_changed": False, "raw_avar_records_modified": False,
        "source_outlines_or_raw_metrics_published": False, "mapping_accepted": False, "font_generated": False,
        "outline_limit_font_units": LIMIT, "HVAR_conditioned_reference_is_not_a_global_mapping": True,
        "independent_processes_do_not_claim_system_service_cache_reset": True,
        "modes": [], "native_processes": [], "direct_HVF_reference_comparisons": new_stats()}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    save()
    try:
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix="swirl-axis-plateau-") as directory:
            fonts = collection.fonts
            require(len(fonts) == 32 and all(f["maxp"].numGlyphs == 47102 for f in fonts), "all_source_faces_gids_required")
            identities = source_identities(fonts)
            ranges = {face: {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in f["fvar"].axes}
                      for face, f in enumerate(fonts)}
            cases = plateau_cases(ranges)
            requests = [(face, index) for face, rows in cases.items() for index in range(len(rows))]
            gids = sorted(set(METRIC_GIDS) | {19177})
            report.update(selected_faces=list(cases), selected_glyphs=gids, user_positions=len(requests),
                          planned_constructor_modes=list(MODES), planned_glyph_records=2 * len(MODES) * len(requests) * len(gids))
            root = Path(directory)
            swift, binary, hvf_binary = root / "diagnostic.swift", root / "diagnostic", root / "hvf_oracle"
            code = Path(__file__).with_name("coretext_extract.swift").read_text()
            harness = make_harness(code)
            swift.write_text(harness)
            report.update(extractor_source_sha256=hashlib.sha256(code.encode()).hexdigest(),
                          generated_harness_sha256=hashlib.sha256(harness.encode()).hexdigest())
            compiled = subprocess.run(["xcrun", "swiftc", "-O", str(swift), "-o", str(binary)], capture_output=True, text=True, timeout=180)
            if compiled.returncode:
                # The compiler reads only our public harness source; no font is
                # opened by that process. Preserve actionable compile failures.
                report["compiler_failure_excerpt"] = compiled.stderr[-6000:]
            require(compiled.returncode == 0, "CoreText_plateau_diagnostic_compile_failed")
            compiled = subprocess.run(["xcrun", "clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                "-mmacosx-version-min=15.4", str(Path(__file__).with_name("hvf_oracle.c")), "-lhvf", "-o", str(hvf_binary)],
                capture_output=True, text=True, timeout=180)
            if compiled.returncode:
                report["compiler_failure_excerpt"] = compiled.stderr[-6000:]
            require(compiled.returncode == 0, "HVF_oracle_compile_failed")
            baseline = None
            for mode in MODES:
                observations = {face: [None] * len(rows) for face, rows in cases.items()}
                mode_report = {"mode": mode, "status": "IN_PROGRESS", "opposite_order_pairs": 0,
                    "opposite_order_exact_pairs": 0, "opposite_order_mismatches": [], "faces": []}
                report["modes"].append(mode_report)
                for order in ("forward", "reverse"):
                    report["active_context"] = {"stage": "native_process_start", "mode": mode, "order": order}
                    with constructor_mode(mode):
                        oracle = NativeOracle(binary, source, root / f"{mode}-{order}.log")
                    try:
                        check_metadata(oracle.metadata, identities, source.stat().st_size)
                        require(oracle.metadata.get("plateau_mode") == mode, "wrong_native_constructor_mode")
                        report["native_processes"].append({"mode": mode, "order": order,
                            "os_version": oracle.metadata.get("os_version"), "all_32_physical_faces_verified": True,
                            "base_instances": [{"face_index": f["face_index"], **{key: value for key, value in f.items()
                                if key.startswith("plateau_")}} for f in oracle.metadata["faces"]]})
                        process_report = report["native_processes"][-1]
                        for face, index in (requests if order == "forward" else reversed(requests)):
                            location = cases[face][index]["location"]
                            report["active_context"] = {"stage": "native_observation", "mode": mode,
                                "order": order, "face_index": face, "case_number": index, "user_location": location}
                            records = checked_batch(oracle, face, gids, location)
                            if order == "forward":
                                observations[face][index] = records
                            else:
                                for gid in gids:
                                    left, right = observations[face][index][gid], records[gid]
                                    equal = same_private_payload(left, right) and same_json(left["reported_location"], right["reported_location"])
                                    mode_report["opposite_order_pairs"] += 1
                                    mode_report["opposite_order_exact_pairs"] += equal
                                    if not equal:
                                        mode_report["opposite_order_mismatches"].append({"face_index": face,
                                            "glyph_id": gid, "user_location": location})
                        process_report.update(summary=oracle.finish(), exit_status=0)
                    finally:
                        oracle.close()
                    save()
                if mode == "production":
                    baseline = observations
                require(baseline is not None, "production_baseline_must_be_first")
                for face, rows in cases.items():
                    inference = infer_at_axis_nodes(fonts[face], axis_records(fonts[face]), rows, observations[face])
                    safe_rows = []
                    for index, row in enumerate(rows):
                        location, records = row["location"], observations[face][index]
                        result = {**row, "requested_binary64_hex": bits(location),
                            "reported_location": records[gids[0]]["reported_location"],
                            "reported_binary64_hex": bits(records[gids[0]]["reported_location"]),
                            "against_production": [{"glyph_id": gid, **compare_payloads(baseline[face][index][gid], records[gid])}
                                                   for gid in gids]}
                        if index in inference:
                            result["HVAR_inference"] = inference[index]
                            q = conditioned_grid(inference[index])
                            result["HVAR_inferred_f2dot14"] = q
                            # A native HVF reference independently checks selected
                            # base-sensitive/boundary observations for each mode.
                            if q is not None and face == 20 and location["wght"] in (299.9817, 300.01, 399.96, 400., 400.04, 400.041, 400.05):
                                design = {tag: normalize(location[tag], *ranges[face][tag]) for tag in TAGS}
                                design["wght"] = q / 16384
                                result["native_HVF_conditioned_checks"] = []
                                for gid in (5, 19177):
                                    report["active_context"] = {"stage": "native_HVF_reference", "mode": mode,
                                        "face_index": face, "glyph_id": gid, "user_location": location}
                                    actual = hvf_paths(hvf_binary, source, face, gid, design)
                                    observed = coretext_paths(records[gid]["commands"])
                                    stats = new_stats()
                                    record_check(stats, face, gid, location, lambda: discrepancy(actual, observed)[0])
                                    record_check(report["direct_HVF_reference_comparisons"], face, gid, location,
                                                 lambda: discrepancy(actual, observed)[0])
                                    result["native_HVF_conditioned_checks"].append({"glyph_id": gid,
                                        "design_location": design, **stats})
                        safe_rows.append(result)
                    mode_report["faces"].append({"face_index": face, "observations": safe_rows})
                mode_report["status"] = "COMPLETED_DIAGNOSIS_NOT_CONSTRUCTOR_ACCEPTANCE"
                save()
                print(json.dumps({"mode": mode, "positions": len(requests), "status": mode_report["status"]}), flush=True)
            require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "original_source_changed")
            report.update(source_unchanged=True, status="COMPLETED_NATIVE_PLATEAU_CONSTRUCTION_DIAGNOSIS")
            report.pop("active_context", None)
    except Exception as error:
        report.update(status="FAILED_DIAGNOSIS_NOT_ACCEPTANCE", **safe_failure(error))
        save()
        raise RuntimeError("axis plateau diagnosis failed; safe checkpoint retained") from None
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
