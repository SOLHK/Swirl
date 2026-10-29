#!/usr/bin/env python3
"""Test one predeclared binary64/Fixed input boundary with actual native paths.

The two source-coordinate predictions are deliberately not accepted in advance.
This reuses the reviewed constructors, fixed mapping hypotheses, structural GID
selector, raw-Q comparison and exact replay. No source payload is published.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import tempfile

from fontTools.ttLib import TTCollection

from probe_axis_anchor import (CLOSURE_MODES, EXPECTED, LIMIT, METRIC_GIDS,
    MODEL_NAMES, TAGS, BatchGeometry, HVGL, NativeOracle, add_control, axis_records,
    check_metadata, checked_batch, control_stats, declare_readback, declared_mappings,
    diagnostic_failure, evaluate_face, hvf_events, make_harness, metric_stats,
    raw_coretext_paths, raw_native_paths, replay_audit, require, same_json,
    same_private_payload, selected_mode, source_identities)
from calibrate_hvf_geometry import select_glyphs
from verified_axis_oracle import ENVELOPE, SCALARS, VECTORS, finite_number


FACE_INDEX = 15


def fixed16_input(value):
    """Spec input conversion: nearest, ties to the higher integer, exactly."""
    require(finite_number(value), "finite_numeric_fixed_input_required")
    return math.floor(Fraction(value) * 65536 + Fraction(1, 2))


def resolution_cases(axes):
    require(type(axes) is dict and set(axes) == set(TAGS), "all_original_axis_tags_required")
    for tag, values in axes.items():
        require(isinstance(values, (tuple, list)) and len(values) == 3
                and all(finite_number(value) for value in values)
                and values[0] <= values[1] <= values[2] and values[0] < values[2],
                "invalid_source_axis_range")
    defaults = {tag: float(axes[tag][1]) for tag in TAGS}
    require(defaults == {"WDTH": 500., "wght": 499., "HGHT": 500.},
            "review_changed_resolution_face_defaults")
    weights = (("collision_low", 499.006199), ("collision_high", 499.006201),
               ("default", 499.), ("canonical_low", 499.0061),
               ("canonical_high", 499.0062), ("shared_fixed_input", 32702870 / 65536))
    rows = [{"label": label, "location": {**defaults, "wght": weight}} for label, weight in weights]
    require(all(axes[tag][0] <= row["location"][tag] <= axes[tag][2]
                for row in rows for tag in TAGS), "resolution_case_outside_source_range")
    require(rows[0]["location"] != rows[1]["location"]
            and {tag: fixed16_input(rows[0]["location"][tag]) for tag in TAGS}
            == {tag: fixed16_input(rows[1]["location"][tag]) for tag in TAGS},
            "predeclared_input_pair_not_a_fixed16_collision")
    return rows


def summarize_pair(left, right):
    """Compare distinct original requests without rewriting either location."""
    require(set(left) == set(right) and bool(left), "input_pair_glyph_sets_differ")
    stats = control_stats()
    rows = []
    for gid in sorted(left):
        a, b = left[gid], right[gid]
        require(a["face_index"] == b["face_index"] == FACE_INDEX
                and a["glyph_id"] == b["glyph_id"] == gid, "input_pair_identity_mismatch")
        payload_a = {k: v for k, v in a.items() if k not in ENVELOPE}
        payload_b = {k: v for k, v in b.items() if k not in ENVELOPE}
        errors = {key: abs(a[key] - b[key]) for key in SCALARS}
        errors.update({key: max(abs(x - y) for x, y in zip(a[key], b[key]))
                       for key in VECTORS if key != "bounds"})
        require(all(math.isfinite(v) for v in errors.values()), "nonfinite_input_pair_difference")
        geometry = add_control(stats, raw_coretext_paths(a["commands"]),
                               raw_coretext_paths(b["commands"]), FACE_INDEX, gid, a["location"])
        rows.append({"glyph_id": gid, "payload_identical": same_json(payload_a, payload_b),
                     "raw_commands_identical": same_json(a["commands"], b["commands"]),
                     "readback_identical": same_json(a["reported_location"], b["reported_location"]),
                     "metric_max_error": max(errors.values()), "metric_differences": errors,
                     "numeric_geometry": geometry})
    return rows


def run(source, output):
    require(not output.exists() and source.resolve() != output.resolve(), "new_report_path_required")
    require(source.stat().st_size == 61473880 and hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED,
            "exact_original_source_required")
    report = {"status": "NOT_RUN", "source_sha256": EXPECTED,
        "source_commit": os.environ.get("GITHUB_SHA"), "platform": platform.platform(),
        "mapping_accepted": False, "font_generated": False, "continuous_space_accepted": False,
        "production_constructor_changed": False, "production_mapping_changed": False,
        "standard_format_impossibility_proved": False, "outline_limit_font_units": LIMIT,
        "source_outlines_or_raw_metrics_published": False, "native_processes": [], "modes": [],
        "native_HVF_unique_calls": 0,
        "fixed_input_policy": "binary64_to_16_16_nearest_ties_to_higher_integer_before_normalization",
        "fixed_input_policy_reference": "https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview#coordinate-scales-and-normalization"}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    save()
    try:
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix="swirl-input-resolution-") as directory:
            fonts = collection.fonts
            require(len(fonts) == 32 and all(font["maxp"].numGlyphs == 47102 for font in fonts),
                    "all_source_faces_gids_required")
            identities = source_identities(fonts)
            font = fonts[FACE_INDEX]
            axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
            cases = resolution_cases(axes)
            declarations = [declare_readback(case["location"]) for case in cases]
            mappings = [declared_mappings(font, axis_records(font), case["location"]) for case in cases]
            table = HVGL(font.reader["hvgl"])
            selected, coverage = select_glyphs(table)
            gids = sorted(set(selected) | set(METRIC_GIDS) | {19177})
            renderer = BatchGeometry(table, isolated_tangents=True)
            report.update(selected_face=FACE_INDEX, selected_glyphs=gids, structural_coverage=coverage,
                user_positions=len(cases), planned_native_records=4 * len(CLOSURE_MODES) * len(cases) * len(gids),
                all_cases_models_and_replay_declared_before_native_launch=True,
                planned_constructor_modes=list(CLOSURE_MODES), cases=[{**case,
                    "binary64_hex": {tag: float(value).hex() for tag, value in case["location"].items()},
                    "standard_fixed16_input_integers": {tag: fixed16_input(value) for tag, value in case["location"].items()},
                    "predeclared_replay": {tag: plan["canonical"] for tag, plan in declaration.items()},
                    "declared_models": mapping} for case, declaration, mapping in zip(cases, declarations, mappings)])
            root = Path(directory)
            swift, binary, hvf_binary = root / "diagnostic.swift", root / "diagnostic", root / "hvf_oracle"
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
                require(result.returncode == 0, "input_resolution_native_compile_failed")
            cache = {}

            def hvf_get(face, gid, design):
                key = (face, gid, *(design[tag] for tag in TAGS))
                if key not in cache:
                    cache[key] = raw_native_paths(hvf_events(hvf_binary, source, face, gid, design))
                    report["native_HVF_unique_calls"] += 1
                return cache[key]

            for mode in CLOSURE_MODES:
                original, replayed = [None] * len(cases), [None] * len(cases)
                mode_report = {"mode": mode, "status": "IN_PROGRESS", "opposite_order_pairs": 0,
                    "opposite_order_exact_pairs": 0, "opposite_order_mismatches": [],
                    "replay_batch_checks": 0, "replay_failed_batches": 0, "replay_failures": [],
                    "conditional_native_HVF": control_stats(), "models": {name: {
                        "horizontal_metrics": metric_stats(), "portable_geometry": control_stats(),
                        "native_HVF_geometry": control_stats()} for name in MODEL_NAMES}}
                report["modes"].append(mode_report)
                for order in ("forward", "reverse"):
                    report["active_context"] = {"mode": mode, "order": order, "stage": "native_start"}
                    with selected_mode(mode):
                        oracle = NativeOracle(binary, source, root / f"{mode}-{order}.log")
                    try:
                        check_metadata(oracle.metadata, identities, source.stat().st_size)
                        require(oracle.metadata.get("anchor_mode") == mode, "wrong_native_anchor_mode")
                        process = {"mode": mode, "order": order, "all_32_physical_faces_verified": True,
                                   "os_version": oracle.metadata.get("os_version")}
                        report["native_processes"].append(process)
                        for index in (range(len(cases)) if order == "forward" else reversed(range(len(cases)))):
                            point = cases[index]["location"]
                            report["active_context"] = {"mode": mode, "order": order,
                                "stage": "native_observation", "case_label": cases[index]["label"]}
                            canonical = {tag: plan["canonical"] for tag, plan in declarations[index].items()}
                            observed = checked_batch(oracle, FACE_INDEX, gids, point)
                            replay = checked_batch(oracle, FACE_INDEX, gids, canonical)
                            audit = replay_audit(identities[FACE_INDEX], point, observed, replay, declarations[index])
                            mode_report["replay_batch_checks"] += 1
                            if audit["status"] != "PASS_FINITE_REPLAY":
                                mode_report["replay_failed_batches"] += 1
                                mode_report["replay_failures"].append({"case_label": cases[index]["label"], "order": order, **audit})
                            if order == "forward":
                                original[index], replayed[index] = observed, replay
                            else:
                                for phase, lhs, rhs in (("original", original[index], observed), ("replay", replayed[index], replay)):
                                    for gid in gids:
                                        equal = (same_private_payload(lhs[gid], rhs[gid]) and
                                                 same_json(lhs[gid]["reported_location"], rhs[gid]["reported_location"]))
                                        mode_report["opposite_order_pairs"] += 1
                                        mode_report["opposite_order_exact_pairs"] += equal
                                        if not equal:
                                            mode_report["opposite_order_mismatches"].append({"case_label": cases[index]["label"],
                                                "glyph_id": gid, "phase": phase})
                        process.update(summary=oracle.finish(), exit_status=0)
                    finally:
                        oracle.close()
                    save()
                rows = evaluate_face(font, FACE_INDEX, cases, original, renderer, gids,
                                     mode_report, mappings, hvf_get, False)
                for index, row in enumerate(rows):
                    for name, design in mappings[index].items():
                        row["model_checks"][name]["native_HVF_geometry"] = [{"glyph_id": gid,
                            **add_control(mode_report["models"][name]["native_HVF_geometry"],
                                hvf_get(FACE_INDEX, gid, design), raw_coretext_paths(original[index][gid]["commands"]),
                                FACE_INDEX, gid, cases[index]["location"])} for gid in (5, 19177)]
                    q = row.get("HVAR_inferred_f2dot14")
                    if q is not None:
                        design = {"WDTH": 0., "wght": q / 16384, "HGHT": 0.}
                        row["HVAR_conditioned_HVF_checks"] = [{"glyph_id": gid, "design_location": design,
                            **add_control(mode_report["conditional_native_HVF"], hvf_get(FACE_INDEX, gid, design),
                                raw_coretext_paths(original[index][gid]["commands"]), FACE_INDEX, gid,
                                cases[index]["location"])} for gid in (5, 19177)]
                mode_report.update(observations=rows, collision_pair=summarize_pair(original[0], original[1]),
                                   status="COMPLETED_INPUT_RESOLUTION_DIAGNOSIS_NOT_ACCEPTANCE")
                save()
            require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "original_source_changed")
            report.update(source_unchanged=True, status="COMPLETED_NATIVE_INPUT_RESOLUTION_DIAGNOSIS_NOT_ACCEPTANCE")
            report.pop("active_context", None)
    except Exception as error:
        report.update(status="FAILED_INPUT_RESOLUTION_DIAGNOSIS_NOT_ACCEPTANCE", **diagnostic_failure(error))
        save()
        raise RuntimeError("input resolution diagnosis failed; safe checkpoint retained") from None
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
