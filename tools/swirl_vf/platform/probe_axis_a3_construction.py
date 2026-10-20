#!/usr/bin/env python3
"""Observe A3 input precision and public Apple constructors on a frozen cohort.

The experiment retains the production prefix and guard, runs complete native
transcripts in opposite orders, and publishes differences only. Neither an API
readback nor a successful diagnostic run admits a production mapping or font.
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
import subprocess
import tempfile

from fontTools.ttLib import TTCollection

from axis_a3_constructor_harness import MODES, MODE_ENV, make_harness
from axis_a3_input_cases import (SELECTED_FACES, conditional_lower_bound,
                                 input_cases, representations)
from probe_axis_anchor import (EXPECTED, LIMIT, METRIC_GIDS, TAGS, NativeOracle,
    add_control, axis_records, check_metadata, checked_batch, conditioned_grid,
    control_stats, declare_readback, declared_mappings, diagnostic_failure,
    infer_at_axis_nodes, raw_coretext_paths, replay_audit, require, same_json,
    same_private_payload, source_identities)
from verified_axis_oracle import ENVELOPE, SCALARS, VECTORS, finite_number


LOSSY_MODES = ("anchor_binary32", "anchor_fixed16", "copy_cfnumber_float32")
PAIR_GROUPS = ("existing_collision", "fixed_only_collision", "float32_only_collision")


def submitted_location(location, mode):
    require(mode in MODES, "a3_unknown_constructor_mode")
    require(type(location) is dict and set(location) == set(TAGS), "a3_complete_three_axes_required")
    field = "float32_value" if mode in ("anchor_binary32", "copy_cfnumber_float32") else "fixed16_value"
    return {tag: (representations(location[tag])[field] if mode in LOSSY_MODES else location[tag]) for tag in TAGS}


@contextmanager
def constructor_mode(mode):
    require(mode in MODES, "a3_unknown_constructor_mode")
    previous = os.environ.get(MODE_ENV)
    os.environ[MODE_ENV] = mode
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(MODE_ENV, None)
        else:
            os.environ[MODE_ENV] = previous


def compare_records(left, right):
    """Different request locations are allowed; face/GID and payload are not.

    Unknown payload fields participate in exact equality without being emitted.
    Only difference magnitudes, verdicts and public glyph identities leave here.
    """
    require(set(left) == set(right) and bool(left), "a3_comparison_glyph_set_mismatch")
    stats = control_stats()
    rows = []
    for gid in sorted(left):
        a, b = left[gid], right[gid]
        require(a["face_index"] == b["face_index"] and a["glyph_id"] == b["glyph_id"] == gid,
                "a3_comparison_face_or_glyph_mismatch")
        differences = {}
        for key in SCALARS:
            require(finite_number(a[key]) and finite_number(b[key]), "a3_nonfinite_metric_comparison")
            differences[key] = abs(a[key] - b[key])
        for key, count in VECTORS.items():
            require(len(a[key]) == len(b[key]) == count and all(finite_number(v) for v in a[key] + b[key]),
                    "a3_invalid_vector_comparison")
            differences[key] = max(abs(x - y) for x, y in zip(a[key], b[key]))
        require(all(math.isfinite(v) for v in differences.values()), "a3_nonfinite_difference")
        geometry = add_control(stats, raw_coretext_paths(a["commands"]), raw_coretext_paths(b["commands"]),
                               a["face_index"], gid, a["location"])
        rows.append({"glyph_id": gid,
            "payload_identical": same_json({k: v for k, v in a.items() if k not in ENVELOPE},
                                            {k: v for k, v in b.items() if k not in ENVELOPE}),
            "readback_identical": same_json(a["reported_location"], b["reported_location"]),
            "raw_commands_identical": same_json(a["commands"], b["commands"]),
            "metric_differences": differences, "numeric_geometry": geometry})
    return {"glyph_count": len(rows), "payload_different_glyphs": sum(not r["payload_identical"] for r in rows),
        "readback_different_glyphs": sum(not r["readback_identical"] for r in rows),
        "maximum_advance_difference": max(r["metric_differences"]["advance_width"] for r in rows),
        "geometry_summary": stats, "glyphs": rows}


def check_scalar_report(values, report):
    """Cross-check the actual compiled Swift conversion using Python rationals.

    NSNumber is permitted to optimize storage; compare bits, not an assumed
    objCType. NSNumber's -0 to +0 storage optimization is a separately reported
    bit loss, never an exact match. It does not abort the positive source-axis
    experiment; any nonzero loss or changed raw Swift conversion still fails.
    All fields here describe input numbers, not Apple font payloads.
    """
    require(report.get("status") == "NATIVE_SCALAR_REPRESENTATIONS_NOT_FONT_ACCEPTANCE"
            and (report.get("CGFloat_bytes"), report.get("Double_bytes"), report.get("Float_bytes")) == (8, 8, 4),
            "a3_native_scalar_platform_contract")
    rows = report.get("records")
    require(type(rows) is list and len(rows) == len(values), "a3_native_scalar_count_mismatch")
    signed_zero_changes = []
    for index, (value, row) in enumerate(zip(values, rows)):
        expected = representations(value)
        require(type(row) is dict
                and type(row.get("binary64_bits")) is str
                and type(row.get("float32_bits")) is str
                and row["binary64_bits"].zfill(16) == expected["binary64_bits"]
                and row["float32_bits"].zfill(8) == expected["float32_bits"]
                and finite_number(row.get("float32_value"))
                and row.get("float32_value") == expected["float32_value"]
                and type(row.get("fixed16_integer")) is int
                and row.get("fixed16_integer") == expected["fixed16_integer"]
                and finite_number(row.get("fixed16_value"))
                and row.get("fixed16_value") == expected["fixed16_value"], "a3_native_scalar_bits_or_values_mismatch")
        for key, number in (("NSNumber_double", value), ("NSNumber_float", expected["float32_value"])):
            observed = row.get(key, {})
            expected_bits = representations(number)["binary64_bits"]
            require(type(observed) is dict
                    and type(observed.get("binary64_hex")) is str
                    and type(observed.get("cf_number_float64_binary64_hex")) is str
                    and observed.get("cf_number_and_nsnumber_bits_equal") is True
                    and observed.get("cf_number_float64_conversion_exact") is True,
                    "a3_native_CFNumber_lost_input_bits")
            ns_bits = observed["binary64_hex"].zfill(16)
            cf_bits = observed["cf_number_float64_binary64_hex"].zfill(16)
            if ns_bits == cf_bits == expected_bits:
                continue
            if expected_bits == "8000000000000000" and ns_bits == cf_bits == "0000000000000000":
                signed_zero_changes.append({"value_index": index, "number_object": key,
                    "expected_binary64_bits": expected_bits, "stored_binary64_bits": ns_bits,
                    "classification": "negative_zero_optimized_to_positive_zero_in_number_storage"})
                continue
            require(False, "a3_native_CFNumber_lost_input_bits")
    return {"status": ("COMPLETED_NATIVE_SCALAR_CONTROLS_WITH_SIGNED_ZERO_STORAGE_CHANGES_NOT_FONT_ACCEPTANCE"
                       if signed_zero_changes else "PASS_NATIVE_SCALAR_CONTROLS_NOT_FONT_ACCEPTANCE"),
            "checked_values": len(values), "signed_zero_storage_changes": signed_zero_changes,
            "all_python_reference_bits_match": not signed_zero_changes,
            "all_nonzero_input_bits_match": True,
            "raw_swift_conversion_bits_match": True}


def run(source, output):
    require(not output.exists() and source.resolve() != output.resolve(), "new_report_path_required")
    require(source.stat().st_size == 61473880 and hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED,
            "exact_original_source_required")
    report = {"status": "NOT_RUN", "source_sha256": EXPECTED,
        "source_commit": os.environ.get("GITHUB_SHA"), "platform": platform.platform(),
        "production_mapping_changed": False, "production_constructor_changed": False,
        "mapping_accepted": False, "font_generated": False, "continuous_space_accepted": False,
        "source_outlines_or_raw_metrics_published": False, "original_avar_records_modified": False,
        "lossy_controls_are_not_production_candidates": True, "outline_limit_font_units": LIMIT,
        "independent_processes_do_not_claim_system_cache_reset": True,
        "replay_contract": "unchanged_original_request_decimal4_plan_in_every_mode_failures_retained",
        "native_processes": [], "modes": []}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")

    save()
    try:
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix="swirl-a3-construct-") as directory:
            fonts = collection.fonts
            require(len(fonts) == 32 and all(f["maxp"].numGlyphs == 47102 for f in fonts), "all_source_faces_gids_required")
            identities = source_identities(fonts)
            axes = {face: {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in fonts[face]["fvar"].axes}
                    for face in SELECTED_FACES}
            raw = {face: axis_records(fonts[face]) for face in SELECTED_FACES}
            integers = {face: {tag: [(int(x * 16384), int(y * 16384)) for x, y in records]
                              for tag, records in raw[face].items()} for face in SELECTED_FACES}
            cases = input_cases(axes, integers)
            plans = [declare_readback(case["location"]) for case in cases]
            gids = sorted(set(METRIC_GIDS) | {19177})
            report.update(original_axes=axes, raw_avar_original_order_and_duplicates=integers,
                raw_avar_sha256={face: hashlib.sha256(fonts[face].reader["avar"]).hexdigest() for face in SELECTED_FACES},
                selected_glyphs=gids, user_positions=len(cases), all_cases_declared_before_native_launch=True,
                planned_modes=list(MODES), planned_native_records=4 * len(MODES) * len(cases) * len(gids),
                cases=[{**case, "representations": {tag: representations(v) for tag, v in case["location"].items()},
                    "submitted_location_by_mode": {mode: submitted_location(case["location"], mode) for mode in MODES},
                    "declared_source_models": declared_mappings(fonts[case["face_index"]], raw[case["face_index"]], case["location"]),
                    "predeclared_replay": {tag: p["canonical"] for tag, p in plan.items()}}
                    for case, plan in zip(cases, plans)])
            root = Path(directory)
            swift, binary = root / "a3.swift", root / "a3"
            code = Path(__file__).with_name("coretext_extract.swift").read_text()
            harness = make_harness(code)
            swift.write_text(harness)
            report.update(extractor_source_sha256=hashlib.sha256(code.encode()).hexdigest(),
                          generated_harness_sha256=hashlib.sha256(harness.encode()).hexdigest())
            save()
            compiled = subprocess.run(["xcrun", "swiftc", "-O", str(swift), "-o", str(binary)],
                                      capture_output=True, text=True, timeout=180)
            if compiled.returncode:
                report["compiler_failure_excerpt"] = compiled.stderr[-6000:]
            require(compiled.returncode == 0, "a3_constructor_native_compile_failed")
            scalar_values = [v for case in cases for v in case["location"].values()]
            scalar_values += [-0., 0., -.5 / 65536, -1.5 / 65536, .5 / 65536,
                              math.nextafter(-30000 + .5 / 65536, -math.inf)]
            scalar = subprocess.run([str(binary), "--a3-scalars"], input=json.dumps(scalar_values),
                                    capture_output=True, text=True, timeout=30)
            require(scalar.returncode == 0, "a3_native_scalar_execution_failed")
            report["native_scalar_result"] = json.loads(scalar.stdout)
            save()
            report["native_scalar_controls"] = check_scalar_report(scalar_values, report["native_scalar_result"])
            save()
            references = {}
            for mode in MODES:
                original, replayed = [None] * len(cases), [None] * len(cases)
                mr = {"mode": mode, "status": "IN_PROGRESS", "opposite_order_pairs": 0,
                      "opposite_order_exact_pairs": 0, "opposite_order_mismatches": [],
                      "replay_batch_checks": 0, "replay_failed_batches": 0, "replay_failures": []}
                report["modes"].append(mr)
                for order in ("forward", "reverse"):
                    report["active_context"] = {"mode": mode, "order": order, "stage": "native_start"}
                    with constructor_mode(mode):
                        oracle = NativeOracle(binary, source, root / f"{mode}-{order}.log")
                    try:
                        check_metadata(oracle.metadata, identities, source.stat().st_size)
                        require(oracle.metadata.get("a3_mode") == mode, "a3_wrong_native_mode")
                        process = {"mode": mode, "order": order, "all_32_physical_faces_verified": True,
                                   "os_version": oracle.metadata.get("os_version")}
                        report["native_processes"].append(process)
                        for index in (range(len(cases)) if order == "forward" else reversed(range(len(cases)))):
                            case = cases[index]
                            face, point = case["face_index"], case["location"]
                            report["active_context"] = {"mode": mode, "order": order,
                                "stage": "native_observation", "face_index": face, "label": case["label"]}
                            canonical = {tag: p["canonical"] for tag, p in plans[index].items()}
                            observed = checked_batch(oracle, face, gids, point)
                            replay = checked_batch(oracle, face, gids, canonical)
                            audit = replay_audit(identities[face], point, observed, replay, plans[index])
                            mr["replay_batch_checks"] += 1
                            if audit["status"] != "PASS_FINITE_REPLAY":
                                mr["replay_failed_batches"] += 1
                                mr["replay_failures"].append({"face_index": face, "label": case["label"], "order": order, **audit})
                            if order == "forward":
                                original[index], replayed[index] = observed, replay
                            else:
                                for phase, left, right in (("original", original[index], observed), ("replay", replayed[index], replay)):
                                    for gid in gids:
                                        equal = same_private_payload(left[gid], right[gid]) and same_json(
                                            left[gid]["reported_location"], right[gid]["reported_location"])
                                        mr["opposite_order_pairs"] += 1
                                        mr["opposite_order_exact_pairs"] += equal
                                        if not equal:
                                            mr["opposite_order_mismatches"].append({"face_index": face, "label": case["label"],
                                                                                  "phase": phase, "glyph_id": gid})
                        process.update(summary=oracle.finish(), exit_status=0)
                    finally:
                        oracle.close()
                    save()
                if mode in ("copy_binary64", "anchor_binary64"):
                    references[mode] = original
                inferred = {}
                for face in SELECTED_FACES:
                    indices = [i for i, case in enumerate(cases) if case["face_index"] == face]
                    values = infer_at_axis_nodes(fonts[face], raw[face], [cases[i] for i in indices], [original[i] for i in indices])
                    inferred.update({indices[i]: value for i, value in values.items()})
                mr["observations"] = [{"face_index": case["face_index"], "label": case["label"],
                    "reported_location": original[i][gids[0]]["reported_location"],
                    "HVAR_inferred_f2dot14": conditioned_grid(inferred[i]) if i in inferred else None,
                    "comparisons": {name: compare_records(ref[i], original[i]) for name, ref in references.items()}}
                    for i, case in enumerate(cases)]
                mr["input_pairs"] = []
                for group in PAIR_GROUPS:
                    indices = [i for i, c in enumerate(cases) if c["group"] == group]
                    require(len(indices) == 2, "a3_pair_plan_not_two_points")
                    a, b = indices
                    comparison = compare_records(original[a], original[b])
                    error = next(r["metric_differences"]["advance_width"] for r in comparison["glyphs"] if r["glyph_id"] == 5)
                    mr["input_pairs"].append({"group": group, "left_label": cases[a]["label"], "right_label": cases[b]["label"],
                        "submitted_inputs_identical": same_json(submitted_location(cases[a]["location"], mode),
                                                                submitted_location(cases[b]["location"], mode)),
                        "comparison": comparison, "gid5_conditional_bound": conditional_lower_bound(error)})
                mr["status"] = "COMPLETED_A3_CONSTRUCTOR_DIAGNOSIS_NOT_ACCEPTANCE"
                save()
                print(json.dumps({"mode": mode, "status": mr["status"], "replay_failed_batches": mr["replay_failed_batches"],
                    "opposite_order_exact_pairs": mr["opposite_order_exact_pairs"],
                    "known_pair_advance_difference": mr["input_pairs"][0]["comparison"]["maximum_advance_difference"]}), flush=True)
            actual = sum(p["summary"]["successful_glyph_count"] for p in report["native_processes"])
            require(actual == report["planned_native_records"], "a3_native_record_count_mismatch")
            require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "original_source_changed")
            report.update(actual_native_records=actual, source_unchanged=True,
                          status="COMPLETED_NATIVE_A3_CONSTRUCTION_DIAGNOSIS_NOT_ACCEPTANCE")
            report.pop("active_context", None)
    except Exception as error:
        report.update(status="FAILED_A3_CONSTRUCTION_DIAGNOSIS_NOT_ACCEPTANCE", **diagnostic_failure(error))
        save()
        raise RuntimeError("A3 construction diagnosis failed; safe checkpoint retained") from None
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
