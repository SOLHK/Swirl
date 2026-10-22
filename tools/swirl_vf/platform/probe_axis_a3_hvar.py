#!/usr/bin/env python3
"""A3: isolate the previously nonexact face-18 three-axis HVAR observation.

The archived failure is evidence, not a fitted exception. All cases, arithmetic
hypotheses and the 27-cell conditional design lattice are frozen before native
launch. CoreText supplies the observations; Apple libhvf and the existing raw-Q
comparator supply independent geometry checks. Only coordinates, counts, and
errors leave process memory. No production mapper or source table is changed.

Primary implementation references (design guidance, not copied code):
https://github.com/freetype/freetype/blob/master/src/truetype/ttgxvar.c
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import tempfile

import numpy as np
from fontTools.ttLib import TTCollection

from probe_axis_anchor import (CLOSURE_MODES, EXPECTED, LIMIT, METRIC_GIDS,
    MODEL_NAMES, TAGS, BatchGeometry, HVGL, NativeOracle, SourceMetrics, add_control,
    add_metric, axis_records, bits, check_metadata, checked_batch, control_stats,
    declare_readback, declared_mappings, diagnostic_failure, float32, hvf_events,
    make_harness, metric_stats, normalize, ordered_map, raw_coretext_paths,
    raw_native_paths, raw_portable_paths, replay_audit, require, same_json,
    same_private_payload, selected_mode, source_identities)
from verified_axis_oracle import finite_number


FACE = 18
FOCUS = {"WDTH": 395.1762070327519, "wght": 493.5928547043863,
         "HGHT": 579.3731774437933}
FRESH_SEED = 0xA3182026
EXTRA_MODELS = (
    "canonical_float32_user_sub_div_normalized16_truncate",
    "canonical_float32_delta_div_normalized16_truncate",
    "canonical_float32_reciprocal_mul_normalized16_truncate",
    "request_float32_result_normalized16_truncate",
    "canonical_float32_result_normalized16_nearest",
)
ALL_MODELS = MODEL_NAMES + EXTRA_MODELS
MODEL_DESCRIPTIONS = {
    MODEL_NAMES[0]: "Existing C=T(T(x)); binary64 normalize; truncate normalized16; ordered avar; nearest F2DOT14.",
    MODEL_NAMES[1]: "Existing C=T(T(x)); binary64 normalize then binary32 result; truncate normalized16; ordered avar; nearest F2DOT14.",
    EXTRA_MODELS[0]: "C; binary32 user and default; binary32 subtraction and span; binary32 division result; truncate normalized16.",
    EXTRA_MODELS[1]: "C; binary64 subtraction cast to binary32; binary32 span; binary32 division result; truncate normalized16.",
    EXTRA_MODELS[2]: "C; binary64 subtraction cast to binary32; binary32 reciprocal of span; binary32 product; truncate normalized16.",
    EXTRA_MODELS[3]: "Original request (no C); binary64 normalize then binary32 result; truncate normalized16.",
    EXTRA_MODELS[4]: "C; binary64 normalize then binary32 result; nearest normalized16, ties positive. Retained falsifiable alternative, not a repair.",
}


def validate_axes(axes):
    require(type(axes) is dict and set(axes) == set(TAGS), "a3_all_three_original_axes_required")
    for tag in TAGS:
        values = axes[tag]
        require(isinstance(values, (tuple, list)) and len(values) == 3
                and all(finite_number(x) for x in values)
                and values[0] <= values[1] <= values[2] and values[0] < values[2],
                "a3_invalid_original_axis_range")


def hvar_cases(axes):
    """34 fixed cases, independent of native results; all three axes are kept."""
    validate_axes(axes)
    defaults = {tag: float(axes[tag][1]) for tag in TAGS}
    require(all(axes[tag][0] < FOCUS[tag] < axes[tag][2] for tag in TAGS),
            "a3_focus_outside_original_axes")
    cases = []

    def add(label, group, location):
        require(set(location) == set(TAGS) and all(finite_number(location[tag])
                and axes[tag][0] <= location[tag] <= axes[tag][2] for tag in TAGS),
                "a3_case_outside_original_axes")
        cases.append({"label": label, "group": group, "location": dict(location)})

    add("archived_face18_fresh_triple_7", "archived_nonexact", FOCUS)
    add("default_control", "defaults", defaults)
    for tag in TAGS:
        add(f"{tag}_only", "single_axis_isolation", {**defaults, tag: FOCUS[tag]})
        add(f"{tag}_reset_to_default", "single_axis_reset", {**FOCUS, tag: defaults[tag]})
        span = axes[tag][1] - axes[tag][0] if FOCUS[tag] < axes[tag][1] else axes[tag][2] - axes[tag][1]
        for side, sign in (("below", -1), ("above", 1)):
            add(f"{tag}_binary64_{side}", "binary64_neighbors",
                {**FOCUS, tag: math.nextafter(FOCUS[tag], math.inf * sign)})
            add(f"{tag}_user_fixed16_{side}", "user_fixed16_neighbors",
                {**FOCUS, tag: FOCUS[tag] + sign / 65536})
            add(f"{tag}_normalized16_{side}", "normalized16_neighbors",
                {**FOCUS, tag: FOCUS[tag] + sign * span / 65536})
    rng = random.Random(FRESH_SEED)
    for index in range(8):
        add(f"a3_fresh_holdout_{index}", "fresh_holdout",
            {tag: rng.uniform(axes[tag][0], axes[tag][2]) for tag in TAGS})
    require(len(cases) == 34 and len({tuple(row["location"][tag] for tag in TAGS) for row in cases}) == 34,
            "a3_case_count_or_distinctness_changed")
    return cases


def a3_mappings(font, records, location):
    """Return global arithmetic hypotheses only; no measured value is an input."""
    result = declared_mappings(font, records, location)
    canonical = {tag: plan["canonical"] for tag, plan in declare_readback(location).items()}
    for name in EXTRA_MODELS:
        mapped = {}
        for axis in font["fvar"].axes:
            tag = axis.axisTag
            value = location[tag] if name == EXTRA_MODELS[3] else canonical[tag]
            default = axis.defaultValue
            span = default - axis.minValue if value < default else axis.maxValue - default
            if value == default:
                normalized = 0.
            elif name == EXTRA_MODELS[0]:
                applied, center = float32(value), float32(default)
                span = default - axis.minValue if applied < center else axis.maxValue - default
                normalized = float32(float32(applied - center) / float32(span))
            elif name == EXTRA_MODELS[1]:
                normalized = float32(float32(value - default) / float32(span))
            elif name == EXTRA_MODELS[2]:
                normalized = float32(float32(value - default) * float32(1. / span))
            else:
                normalized = float32(normalize(value, axis.minValue, default, axis.maxValue))
            n16 = (math.floor(normalized * 65536 + .5) if name == EXTRA_MODELS[4]
                   else math.trunc(normalized * 65536))
            raw = tuple((int(x * 16384), int(y * 16384)) for x, y in records[tag])
            final = math.floor(ordered_map(n16 / 65536, raw) * 16384 + .5) / 16384
            require(math.isfinite(final) and -1 <= final <= 1, "a3_model_outside_design_space")
            mapped[tag] = final
        result[name] = mapped
    return result


def conditional_grid(design):
    """A fixed 27-cell local diagnostic, never a per-point production formula."""
    require(type(design) is dict and set(design) == set(TAGS) and all(
        finite_number(v) and -1 <= v <= 1 and v * 16384 == int(v * 16384)
        for v in design.values()), "a3_grid_requires_three_f2dot14_coordinates")
    result = []
    for offsets in itertools.product((-1, 0, 1), repeat=3):
        point = {tag: design[tag] + delta / 16384 for tag, delta in zip(TAGS, offsets)}
        if all(-1 <= value <= 1 for value in point.values()):
            result.append({"offset_f2dot14": dict(zip(TAGS, offsets)), "design_location": point})
    return result


def metric_residuals(metrics, observed, design):
    """Expose signed differences, never absolute source advances or outlines."""
    rows = []
    for gid in METRIC_GIDS:
        difference = observed[gid]["advance_width"] - metrics.at(gid, design)["advance_width"]
        require(math.isfinite(difference), "a3_nonfinite_HVAR_residual")
        rows.append({"glyph_id": gid, "signed_error": difference, "absolute_error": abs(difference)})
    maximum = max(row["absolute_error"] for row in rows)
    return {"four_metric_residuals": rows, "maximum_error": maximum,
            "exact": maximum == 0., "within_1_32": maximum <= LIMIT}


def run(source, output):
    require(not output.exists() and source.resolve() != output.resolve(), "new_report_path_required")
    require(source.stat().st_size == 61473880 and hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED,
            "exact_original_source_required")
    report = {"status": "NOT_RUN", "source_sha256": EXPECTED,
        "source_commit": os.environ.get("GITHUB_SHA"), "platform": platform.platform(),
        "mapping_accepted": False, "font_generated": False, "continuous_space_accepted": False,
        "production_constructor_changed": False, "production_mapping_changed": False,
        "raw_avar_records_modified": False, "source_outlines_or_raw_metrics_published": False,
        "independent_processes_do_not_claim_system_cache_reset": True,
        "HVF_geometry_references_cached_by_gid_and_design": True,
        "outline_limit_font_units": LIMIT, "metric_limit_font_units": LIMIT,
        "conditional_grid_is_not_global_mapping": True, "archived_metric_error": .01220703125,
        "archived_portable_geometry_error": .011959285366742733,
        "native_processes": [], "native_HVF_unique_calls": 0, "modes": [],
        "model_descriptions": MODEL_DESCRIPTIONS, "fresh_holdout_seed": FRESH_SEED}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    save()
    try:
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix="swirl-a3-hvar-") as directory:
            fonts = collection.fonts
            require(len(fonts) == 32 and all(f["maxp"].numGlyphs == 47102 for f in fonts),
                    "all_source_faces_gids_required")
            identities = source_identities(fonts)
            font = fonts[FACE]
            axes = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
            records = axis_records(font)
            cases = hvar_cases(axes)
            plans = [declare_readback(case["location"]) for case in cases]
            models = [a3_mappings(font, records, case["location"]) for case in cases]
            grid = conditional_grid(models[0][MODEL_NAMES[1]])
            gids = sorted(set(METRIC_GIDS) | {19177})
            metrics = SourceMetrics(font)
            renderer = BatchGeometry(HVGL(font.reader["hvgl"]), isolated_tangents=True)
            report.update(selected_face=FACE, selected_glyphs=gids, user_positions=len(cases),
                original_axes=axes, original_avar_records_in_table_order=records,
                raw_avar_sha256=hashlib.sha256(font.reader["avar"]).hexdigest(),
                planned_constructor_modes=list(CLOSURE_MODES),
                planned_native_records=4 * len(CLOSURE_MODES) * len(cases) * len(gids),
                all_cases_models_and_grid_declared_before_native_launch=True,
                cases=[{**case, "binary64_bits": bits(case["location"]), "declared_models": model,
                        "predeclared_replay": {tag: plan["canonical"] for tag, plan in declaration.items()}}
                       for case, model, declaration in zip(cases, models, plans)],
                predeclared_conditional_grid=grid)
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
                require(result.returncode == 0, "a3_hvar_native_compile_failed")
            cache = {}

            def hvf_get(gid, design):
                key = (gid, *(design[tag] for tag in TAGS))
                if key not in cache:
                    cache[key] = raw_native_paths(hvf_events(hvf_binary, source, FACE, gid, design))
                    report["native_HVF_unique_calls"] += 1
                return cache[key]

            reference = None
            for mode in CLOSURE_MODES:
                original, replayed = [None] * len(cases), [None] * len(cases)
                mr = {"mode": mode, "status": "IN_PROGRESS", "opposite_order_pairs": 0,
                    "opposite_order_exact_pairs": 0, "opposite_order_mismatches": [],
                    "replay_batch_checks": 0, "replay_failed_batches": 0, "replay_failures": [],
                    "models": {name: {"horizontal_metrics": metric_stats(), "portable_geometry": control_stats(),
                                      "native_HVF_geometry": control_stats()} for name in ALL_MODELS},
                    "conditional_grid_geometry": control_stats(), "observations": []}
                report["modes"].append(mr)
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
                            canonical = {tag: plan["canonical"] for tag, plan in plans[index].items()}
                            observed = checked_batch(oracle, FACE, gids, point)
                            replay = checked_batch(oracle, FACE, gids, canonical)
                            audit = replay_audit(identities[FACE], point, observed, replay, plans[index])
                            mr["replay_batch_checks"] += 1
                            if audit["status"] != "PASS_FINITE_REPLAY":
                                mr["replay_failed_batches"] += 1
                                mr["replay_failures"].append({"case_label": cases[index]["label"], "order": order, **audit})
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
                                            mr["opposite_order_mismatches"].append({"case_label": cases[index]["label"],
                                                "glyph_id": gid, "phase": phase})
                        process.update(summary=oracle.finish(), exit_status=0)
                    finally:
                        oracle.close()
                    save()
                if reference is None:
                    reference = original
                specs = [(index, name, design) for index, names in enumerate(models) for name, design in names.items()]
                matrix = np.asarray([[design[tag] for tag in TAGS] for _, _, design in specs])
                for index, (case, observed) in enumerate(zip(cases, original)):
                    row = {**case, "reported_location": observed[gids[0]]["reported_location"],
                        "reported_binary64_bits": bits(observed[gids[0]]["reported_location"]), "model_checks": {},
                        "against_production_payload_equal": all(same_private_payload(reference[index][gid], observed[gid])
                                                                 for gid in gids)}
                    for name, design in models[index].items():
                        residual = metric_residuals(metrics, observed, design)
                        add_metric(mr["models"][name]["horizontal_metrics"], residual["maximum_error"])
                        row["model_checks"][name] = {**residual, "portable_geometry": [], "native_HVF_geometry": []}
                        if index == 0 or case["label"] in ("a3_fresh_holdout_0", "a3_fresh_holdout_1"):
                            for gid in (5, 19177):
                                comparison = add_control(mr["models"][name]["native_HVF_geometry"], hvf_get(gid, design),
                                    raw_coretext_paths(observed[gid]["commands"]), FACE, gid, case["location"])
                                row["model_checks"][name]["native_HVF_geometry"].append({"glyph_id": gid, **comparison})
                    mr["observations"].append(row)
                for gid in gids:
                    batch = renderer.render(gid, matrix[:, :renderer.table.part(gid).axis_count])
                    for offset, (index, name, _) in enumerate(specs):
                        comparison = add_control(mr["models"][name]["portable_geometry"],
                            raw_portable_paths([path[offset] for path in batch.paths]),
                            raw_coretext_paths(original[index][gid]["commands"]), FACE, gid, cases[index]["location"])
                        mr["observations"][index]["model_checks"][name]["portable_geometry"].append({"glyph_id": gid, **comparison})
                mr["conditional_grid_references"] = []
                for cell in grid:
                    design = cell["design_location"]
                    row = {**cell, **metric_residuals(metrics, original[0], design), "native_HVF_geometry": []}
                    for gid in (5, 19177):
                        comparison = add_control(mr["conditional_grid_geometry"], hvf_get(gid, design),
                            raw_coretext_paths(original[0][gid]["commands"]), FACE, gid, FOCUS)
                        row["native_HVF_geometry"].append({"glyph_id": gid, **comparison})
                    mr["conditional_grid_references"].append(row)
                mr["status"] = "COMPLETED_A3_HVAR_DIAGNOSIS_NOT_ACCEPTANCE"
                save()
                print(json.dumps({"mode": mode, "status": mr["status"], "user_positions": len(cases),
                    "replay_failed_batches": mr["replay_failed_batches"],
                    "baseline_focus_metric_error": mr["observations"][0]["model_checks"][MODEL_NAMES[1]]["maximum_error"]}), flush=True)
            require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "original_source_changed")
            actual_records = sum(p["summary"]["successful_glyph_count"] for p in report["native_processes"])
            require(actual_records == report["planned_native_records"], "a3_native_record_total_mismatch")
            report.update(actual_native_records=actual_records,
                actual_opposite_order_pairs=sum(m["opposite_order_pairs"] for m in report["modes"]),
                actual_replay_batches=sum(m["replay_batch_checks"] for m in report["modes"]))
            report.update(source_unchanged=True, status="COMPLETED_NATIVE_A3_HVAR_DIAGNOSIS_NOT_ACCEPTANCE")
            report.pop("active_context", None)
    except Exception as error:
        report.update(status="FAILED_A3_HVAR_DIAGNOSIS_NOT_ACCEPTANCE", **diagnostic_failure(error))
        save()
        raise RuntimeError("A3 HVAR diagnosis failed; safe checkpoint retained") from None
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
