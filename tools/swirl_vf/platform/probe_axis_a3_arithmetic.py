#!/usr/bin/env python3
"""Native falsification of A3 arithmetic order and default-omission evidence.

Reuse frozen identity, transport, geometry and source-metric implementations.
Every hypothesis and fresh point is declared before launching CoreText. All
legacy replay failures remain visible, including when a narrower diagnostic
classification explains a default-axis omission. Nothing here is a production
oracle, an accepted mapping, or permission to build an original font.
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

import numpy as np
from fontTools.ttLib import TTCollection

from axis_a3_arithmetic_cases import (ALL_MODELS, FRESH_SEED, MODEL_DESCRIPTIONS,
                                     NEW_MODELS, arithmetic_cases, arithmetic_mappings)
from axis_a3_arithmetic_harness import MODES, check_entry_audit, diagnostic_failure, make_harness
from axis_a3_default_omission import classify_default_omission
from probe_axis_a3_construction import compare_records
from probe_axis_a3_hvar import metric_residuals
from probe_axis_a3_identity_avar import metric_summary
from probe_axis_anchor import (EXPECTED, LIMIT, METRIC_GIDS, TAGS, BatchGeometry,
    HVGL, NativeOracle, SourceMetrics, add_control, add_metric, axis_records, bits,
    check_metadata, checked_batch, control_stats, declare_readback,
    hvf_events, metric_stats, raw_coretext_paths,
    raw_native_paths, raw_portable_paths, replay_audit, require, same_json,
    same_private_payload, selected_mode, source_identities)


STATUS = "COMPLETED_NATIVE_A3_ARITHMETIC_DIAGNOSIS_NOT_ACCEPTANCE"


def run(source, output, *, case_factory=arithmetic_cases, mapping_factory=arithmetic_mappings,
        model_names=ALL_MODELS, new_model_names=NEW_MODELS,
        model_descriptions=MODEL_DESCRIPTIONS, fresh_seed=FRESH_SEED,
        status=STATUS, report_context=None, compare_replay_geometry=False,
        design_input_factory=None):
    """Run a predeclared A3 experiment with the same frozen native protocol.

    Defaults reproduce the original arithmetic experiment. A separate A3 driver
    can supply independently frozen cases/models; it cannot alter the native
    constructor, source identity checks, readback guard or acceptance flags.
    """
    require(not output.exists() and source.resolve() != output.resolve(), "new_report_path_required")
    require(source.stat().st_size == 61473880 and hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED,
            "exact_original_source_required")
    report = {"status": "NOT_RUN", "source_sha256": EXPECTED,
        "source_commit": os.environ.get("GITHUB_SHA"), "platform": platform.platform(),
        "mapping_accepted": False, "font_generated": False, "continuous_space_accepted": False,
        "production_constructor_changed": False, "production_mapping_changed": False,
        "raw_avar_records_modified": False, "original_141_subset_rerun": False,
        "source_outlines_or_raw_metrics_published": False,
        "constructor_entry_is_not_CoreText_internal_state": True,
        "independent_processes_do_not_claim_system_cache_reset": True,
        "HVF_geometry_references_cached_by_face_gid_and_design": True,
        "metric_limit_font_units": LIMIT, "outline_limit_font_units": LIMIT,
        "fresh_holdout_seed": fresh_seed, "model_descriptions": model_descriptions,
        "native_processes": [], "native_HVF_unique_calls": 0, "modes": []}
    if report_context is not None:
        report["experiment_context"] = report_context
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    save()
    try:
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix="swirl-a3-arithmetic-") as directory:
            fonts = collection.fonts
            require(len(fonts) == 32 and all(f["maxp"].numGlyphs == 47102 for f in fonts),
                    "all_source_faces_gids_required")
            identities = source_identities(fonts)
            axes = {face: {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
                    for face, font in enumerate(fonts)}
            records = {face: axis_records(font) for face, font in enumerate(fonts)}
            cases = case_factory(axes)
            plans = [declare_readback(case["location"]) for case in cases]
            models = [mapping_factory(fonts[case["face_index"]], records[case["face_index"]], case["location"])
                      for case in cases]
            gids = sorted(set(METRIC_GIDS) | {19177})
            report.update(user_positions=len(cases), unique_face_locations=len({
                    (c["face_index"], *(c["location"][tag] for tag in TAGS)) for c in cases}),
                new_holdout_positions=sum(c["is_holdout"] for c in cases),
                historical_control_positions=sum(not c["is_holdout"] for c in cases),
                selected_glyphs=gids, planned_constructor_modes=list(MODES),
                planned_native_records=4 * len(gids) * len(cases) * len(MODES),
                planned_direct_HVF_positions=sum(c["direct_native_HVF"] for c in cases),
                all_cases_and_mappings_declared_before_native_launch=True,
                original_faces=[{"face_index": face, "original_axes": axes[face],
                    "original_avar_records_in_table_order": records[face],
                    "raw_avar_sha256": hashlib.sha256(font.reader["avar"]).hexdigest()}
                    for face, font in enumerate(fonts)],
                cases=[{**case, "binary64_bits": bits(case["location"]), "declared_models": mapping,
                    "predeclared_replay": {tag: plan["canonical"] for tag, plan in declaration.items()}}
                    for case, mapping, declaration in zip(cases, models, plans)])
            if design_input_factory is not None:
                for frozen, case in zip(report["cases"], cases):
                    face = case["face_index"]
                    frozen["declared_design_inputs"] = design_input_factory(
                        fonts[face], records[face], case["location"])
            root = Path(directory)
            swift, binary, hvf_binary = root / "arithmetic.swift", root / "arithmetic", root / "hvf_oracle"
            code = Path(__file__).with_name("coretext_extract.swift").read_text()
            harness = make_harness(code)
            swift.write_text(harness)
            report.update(extractor_source_sha256=hashlib.sha256(code.encode()).hexdigest(),
                          generated_harness_sha256=hashlib.sha256(harness.encode()).hexdigest())
            save()
            for command in (["xcrun", "swiftc", "-O", str(swift), "-o", str(binary)],
                    ["xcrun", "clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                     "-mmacosx-version-min=15.4", str(Path(__file__).with_name("hvf_oracle.c")), "-lhvf", "-o", str(hvf_binary)]):
                result = subprocess.run(command, capture_output=True, text=True, timeout=180)
                if result.returncode:
                    report["compiler_failure_excerpt"] = result.stderr[-6000:]
                require(result.returncode == 0, "a3_arithmetic_native_compile_failed")
            cache, reference = {}, {}

            def hvf_get(face, gid, design):
                key = (face, gid, *(design[tag] for tag in TAGS))
                if key not in cache:
                    cache[key] = raw_native_paths(hvf_events(hvf_binary, source, face, gid, design))
                    report["native_HVF_unique_calls"] += 1
                return cache[key]

            for mode in MODES:
                original, replayed = {}, {}
                mr = {"mode": mode, "status": "IN_PROGRESS", "user_positions": len(cases),
                    "opposite_order_pairs": 0, "opposite_order_exact_pairs": 0,
                    "opposite_order_mismatches": [], "replay_batch_checks": 0,
                    "replay_failed_batches": 0, "replay_failures": [], "default_omission_checks": [],
                    "models": {name: {"horizontal_metrics": metric_stats(), "portable_geometry": control_stats(),
                                      "native_HVF_geometry": control_stats()} for name in model_names},
                    "observations": []}
                if compare_replay_geometry:
                    mr["original_replay_comparisons"] = []
                report["modes"].append(mr)
                for order in ("forward", "reverse"):
                    log = root / f"{mode}-{order}.log"
                    report["active_context"] = {"mode": mode, "order": order, "stage": "native_start"}
                    with selected_mode(mode):
                        oracle = NativeOracle(binary, source, log)
                    request_plan, pending = [], []
                    try:
                        check_metadata(oracle.metadata, identities, source.stat().st_size)
                        require(oracle.metadata.get("anchor_mode") == mode, "wrong_native_anchor_mode")
                        process = {"mode": mode, "order": order, "all_32_physical_faces_verified": True,
                                   "os_version": oracle.metadata.get("os_version")}
                        report["native_processes"].append(process)
                        for index in (range(len(cases)) if order == "forward" else reversed(range(len(cases)))):
                            case = cases[index]; face = case["face_index"]; point = case["location"]
                            report["active_context"] = {"mode": mode, "order": order,
                                "stage": "native_observation", "face_index": face, "case_label": case["label"]}
                            canonical = {tag: plan["canonical"] for tag, plan in plans[index].items()}
                            observed = checked_batch(oracle, face, gids, point)
                            original_id = str(oracle.sequence)
                            request_plan.append({"request_id": original_id, "face_index": face, "location": point})
                            replay = checked_batch(oracle, face, gids, canonical)
                            replay_id = str(oracle.sequence)
                            request_plan.append({"request_id": replay_id, "face_index": face, "location": canonical})
                            audit = replay_audit(identities[face], point, observed, replay, plans[index])
                            if compare_replay_geometry:
                                mr["original_replay_comparisons"].append({"case_label": case["label"],
                                    "face_index": face, "order": order, **compare_records(observed, replay)})
                            mr["replay_batch_checks"] += 1
                            if audit["status"] != "PASS_FINITE_REPLAY":
                                mr["replay_failed_batches"] += 1
                                mr["replay_failures"].append({"case_label": case["label"], "order": order, **audit})
                            pending.append((index, original_id, replay_id, observed, replay))
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
                                            mr["opposite_order_mismatches"].append({"case_label": case["label"],
                                                "face_index": face, "glyph_id": gid, "phase": phase})
                        process.update(summary=oracle.finish(), exit_status=0)
                        native_faces = oracle.metadata["faces"]
                    finally:
                        oracle.close()
                    entry_bits = check_entry_audit(log.read_text(), request_plan, mode)
                    process.update(constructor_entry_records=len(entry_bits), constructor_entry_bits_verified=True)
                    for index, original_id, replay_id, observed, replay in pending:
                        case = cases[index]; face = case["face_index"]
                        classification = classify_default_omission(identities[face], case["location"], observed, replay,
                            requested_gids=gids, native_identity=native_faces[face],
                            submitted_original_bits=entry_bits[original_id], submitted_replay_bits=entry_bits[replay_id],
                            declaration=plans[index])
                        mr["default_omission_checks"].append({"case_label": case["label"], "order": order, **classification})
                    save()
                for face in range(32):
                    local = [index for index, case in enumerate(cases) if case["face_index"] == face]
                    if not local:
                        continue
                    metrics = SourceMetrics(fonts[face])
                    renderer = BatchGeometry(HVGL(fonts[face].reader["hvgl"]), isolated_tangents=True)
                    rows = {}
                    specs = [(index, name, design) for index in local for name, design in models[index].items()]
                    matrix = np.asarray([[design[tag] for tag in TAGS] for _, _, design in specs])
                    for index in local:
                        case = cases[index]; observed = original[index]
                        reference.setdefault(index, observed)
                        row = {**case, "reported_location": observed[gids[0]]["reported_location"],
                            "reported_binary64_bits": bits(observed[gids[0]]["reported_location"]),
                            "against_endpoint_payload_equal": all(same_private_payload(reference[index][gid], observed[gid]) for gid in gids),
                            "model_checks": {}}
                        for name, design in models[index].items():
                            residual = metric_residuals(metrics, observed, design)
                            add_metric(mr["models"][name]["horizontal_metrics"], residual["maximum_error"])
                            row["model_checks"][name] = {**residual, "portable_geometry": [], "native_HVF_geometry": []}
                            if case["direct_native_HVF"]:
                                for gid in (5, 19177):
                                    comparison = add_control(mr["models"][name]["native_HVF_geometry"],
                                        hvf_get(face, gid, design), raw_coretext_paths(observed[gid]["commands"]), face, gid, case["location"])
                                    row["model_checks"][name]["native_HVF_geometry"].append({"glyph_id": gid, **comparison})
                        rows[index] = row
                        mr["observations"].append(row)
                    for gid in gids:
                        batch = renderer.render(gid, matrix[:, :renderer.table.part(gid).axis_count])
                        for offset, (index, name, _) in enumerate(specs):
                            comparison = add_control(mr["models"][name]["portable_geometry"],
                                raw_portable_paths([path[offset] for path in batch.paths]),
                                raw_coretext_paths(original[index][gid]["commands"]), face, gid, cases[index]["location"])
                            rows[index]["model_checks"][name]["portable_geometry"].append({"glyph_id": gid, **comparison})
                    report["active_context"] = {"mode": mode, "stage": "references", "face_index": face}
                    save()
                mr["metric_exactness_by_cohort"] = {name: metric_summary(mr["observations"], name) for name in model_names}
                mr["status"] = status
                save()
                print(json.dumps({"mode": mode, "status": status, "user_positions": len(cases),
                    "new_models": {name: mr["models"][name]["horizontal_metrics"] for name in new_model_names},
                    "replay_failed_batches": mr["replay_failed_batches"]}), flush=True)
            require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "original_source_changed")
            actual = sum(p["summary"]["successful_glyph_count"] for p in report["native_processes"])
            require(actual == report["planned_native_records"], "a3_arithmetic_native_record_total_mismatch")
            report.update(source_unchanged=True, actual_native_records=actual,
                actual_constructor_entry_records=sum(p["constructor_entry_records"] for p in report["native_processes"]),
                actual_opposite_order_pairs=sum(m["opposite_order_pairs"] for m in report["modes"]),
                actual_replay_batches=sum(m["replay_batch_checks"] for m in report["modes"]), status=status)
            report.pop("active_context", None)
    except Exception as error:
        report.update(status=status.replace("COMPLETED_NATIVE_", "FAILED_"), **diagnostic_failure(error))
        save()
        raise RuntimeError("A3 arithmetic diagnosis failed; safe checkpoint retained") from None
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
