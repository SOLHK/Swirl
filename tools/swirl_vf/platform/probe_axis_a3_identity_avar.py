#!/usr/bin/env python3
"""Frozen A3 identity-avar arithmetic hypothesis; native evidence, not acceptance.

The preceding native HVAR study disproved global nearest-normalized16 rounding.
This independent cohort tests whether an unmodified, strictly ordered identity
avar map bypasses the intermediate normalized16 truncation. Nonidentity maps
retain the previous float32/truncate rule. No face, GID or observed-error branch
is permitted in the candidate. Raw avar order and duplicates remain untouched.

Primary references: OpenType normalization and FreeType's separation of user
and normalized inputs; neither reference establishes Apple's implementation.
https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview
https://github.com/freetype/freetype/blob/master/src/truetype/ttgxvar.c
"""
from __future__ import annotations

import argparse
import hashlib
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

from probe_axis_anchor import (EXPECTED, LIMIT, METRIC_GIDS, MODEL_NAMES, TAGS,
    BatchGeometry, HVGL, NativeOracle, SourceMetrics, add_control, add_metric,
    axis_records, bits, check_metadata, checked_batch, control_stats,
    declare_readback, declared_mappings, diagnostic_failure, float32, hvf_events,
    make_harness, metric_stats, normalize, raw_coretext_paths, raw_native_paths,
    raw_portable_paths, replay_audit, require, same_json, same_private_payload,
    selected_mode, source_identities)
from probe_axis_a3_hvar import FOCUS, metric_residuals, validate_axes
from verified_axis_oracle import finite_number


FRESH_SEED = 0xA31D2026
BOUNDARY_FACES = (15, 18, 20)
BOUNDARY_Q = (-7311, 5277)
BOUNDARY_EPSILON = 2. ** -20
ANCHOR_MODES = ("anchor_endpoint_original", "anchor_quarter_original")
CANDIDATE = "canonical_identity_avar_float32_direct_f2dot14"
DOUBLE_CONTROL = "canonical_identity_avar_binary64_direct_f2dot14"
ALL_MODELS = MODEL_NAMES + (CANDIDATE, DOUBLE_CONTROL)
PRIOR_COMMIT = "22a89a154217c5a4ea65788d2994e99e816ffabf"
PRIOR_REPORT_SHA256 = "cfcab697ff93d6756e1fb2840d4836428f2bf8a37f85752a4d70f4be1a0ae84a"
PRIOR_NEAREST_FAILURES = (
    {"label": "previous_nearest_holdout_1", "location": {
        "WDTH": 506.0136563804356, "wght": 271.5572090688256,
        "HGHT": 647.3836060029549}, "previous_nearest_metric_error": .003303971141576767},
    {"label": "previous_nearest_holdout_5", "location": {
        "WDTH": 733.8074261111074, "wght": 520.4531783300665,
        "HGHT": 72.83509247991965}, "previous_nearest_metric_error": .01220703125},
)


def identity_records(records):
    """Recognize an ordered identity map without sorting or deduplicating it."""
    if not isinstance(records, (tuple, list)) or len(records) < 3:
        return False
    if not all(isinstance(row, (tuple, list)) and len(row) == 2
               and all(finite_number(value) for value in row) for row in records):
        return False
    return (tuple(records[0]) == (-1., -1.) and tuple(records[-1]) == (1., 1.)
            and any(tuple(row) == (0., 0.) for row in records)
            and all(x == y and -1 <= x <= 1 and x * 16384 == int(x * 16384)
                    for x, y in records)
            and all(left[0] < right[0] for left, right in zip(records, records[1:])))


def identity_mappings(font, records, location):
    """Four frozen hypotheses, with no native data or selected face as input."""
    result = declared_mappings(font, records, location)
    canonical = {tag: plan["canonical"] for tag, plan in declare_readback(location).items()}
    for name in (CANDIDATE, DOUBLE_CONTROL):
        mapped = dict(result[MODEL_NAMES[1]])
        for axis in font["fvar"].axes:
            tag = axis.axisTag
            if identity_records(records[tag]):
                value = normalize(canonical[tag], axis.minValue, axis.defaultValue, axis.maxValue)
                if name == CANDIDATE:
                    value = float32(value)
                mapped[tag] = math.floor(value * 16384 + .5) / 16384
        require(set(mapped) == set(TAGS) and all(finite_number(v) and -1 <= v <= 1
                for v in mapped.values()), "a3_identity_mapping_outside_design_space")
        result[name] = mapped
    return result


def identity_cases(face_axes):
    """103 predeclared positions: 100 new holdouts and 3 historical controls."""
    require(set(face_axes) == set(range(32)), "a3_identity_all_32_faces_required")
    for axes in face_axes.values():
        validate_axes(axes)
    cases = []

    def add(face, label, group, location, **metadata):
        axes = face_axes[face]
        require(set(location) == set(TAGS) and all(finite_number(location[tag])
                and axes[tag][0] <= location[tag] <= axes[tag][2] for tag in TAGS),
                "a3_identity_case_outside_original_axes")
        cases.append({"face_index": face, "label": label, "group": group,
                      "is_holdout": group != "historical_control", "location": dict(location), **metadata})

    rng = random.Random(FRESH_SEED)
    for face in range(32):
        axes = face_axes[face]
        for index in range(2):
            add(face, f"identity_fresh_{face}_{index}", "fresh_random_holdout",
                {tag: rng.uniform(axes[tag][0], axes[tag][2]) for tag in TAGS},
                direct_native_HVF=index == 0)
    for face in BOUNDARY_FACES:
        axes = face_axes[face]
        defaults = {tag: axes[tag][1] for tag in TAGS}
        for tag in ("WDTH", "HGHT"):
            for q in BOUNDARY_Q:
                midpoint = (q + .5) / 16384
                minimum, default, maximum = axes[tag]
                span = default - minimum if midpoint < 0 else maximum - default
                require(span > 0, "a3_identity_boundary_requires_two_sided_axis")
                user_midpoint = default + midpoint * span
                for side, offset in (("below", -BOUNDARY_EPSILON), ("at", 0.),
                                     ("above", BOUNDARY_EPSILON)):
                    add(face, f"identity_boundary_{face}_{tag}_{q}_{side}", "rounding_boundary_holdout",
                        {**defaults, tag: default + (midpoint + offset) * span},
                        normalized_midpoint=midpoint, user_midpoint=user_midpoint,
                        normalized_offset=offset, boundary_axis=tag, direct_native_HVF=False)
    add(18, "original_nonexact_focus", "historical_control", FOCUS,
        previous_truncate_metric_error=.01220703125, direct_native_HVF=True)
    for row in PRIOR_NEAREST_FAILURES:
        add(18, row["label"], "historical_control", row["location"],
            previous_nearest_metric_error=row["previous_nearest_metric_error"], direct_native_HVF=True)
    require(len(cases) == 103 and len({(row["face_index"], *(row["location"][tag]
            for tag in TAGS)) for row in cases}) == 103, "a3_identity_cohort_count_changed")
    return cases


def mode_case_indices(cases, mode):
    require(mode in ANCHOR_MODES + ("production",), "a3_identity_unknown_mode")
    return [index for index, case in enumerate(cases)
            if mode != "production" or not case["is_holdout"]]


def metric_summary(observations, model):
    """Exactness and threshold counts remain separate; preserve every residual."""
    result = {"holdouts": metric_stats(), "historical_controls": metric_stats(),
              "nonexact_observations": []}
    for row in observations:
        check = row["model_checks"][model]
        add_metric(result["holdouts" if row["is_holdout"] else "historical_controls"],
                   check["maximum_error"])
        if not check["exact"]:
            result["nonexact_observations"].append({"face_index": row["face_index"],
                "label": row["label"], "is_holdout": row["is_holdout"],
                "maximum_error": check["maximum_error"], "within_1_32": check["within_1_32"],
                "four_metric_residuals": check["four_metric_residuals"]})
    return result


def run(source, output):
    require(not output.exists() and source.resolve() != output.resolve(), "new_report_path_required")
    require(source.stat().st_size == 61473880 and hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED,
            "exact_original_source_required")
    report = {"status": "NOT_RUN", "source_sha256": EXPECTED,
        "source_commit": os.environ.get("GITHUB_SHA"), "platform": platform.platform(),
        "prior_hvar_commit": PRIOR_COMMIT, "prior_report_sha256": PRIOR_REPORT_SHA256,
        "prior_run_url": "https://github.com/SOLHK/Swirl/actions/runs/39398883017",
        "candidate": CANDIDATE, "models": list(ALL_MODELS),
        "candidate_frozen_before_new_observations": True, "mapping_accepted": False,
        "font_generated": False, "continuous_space_accepted": False,
        "production_constructor_changed": False, "production_mapping_changed": False,
        "raw_avar_records_modified": False, "source_outlines_or_raw_metrics_published": False,
        "independent_processes_do_not_claim_system_cache_reset": True,
        "HVF_geometry_references_cached_by_face_gid_and_design": True,
        "metric_limit_font_units": LIMIT, "outline_limit_font_units": LIMIT,
        "fresh_holdout_seed": FRESH_SEED, "native_processes": [], "native_HVF_unique_calls": 0,
        "modes": [], "model_rule": {
            CANDIDATE: "C=T(T(x)); identity raw avar only: normalize in binary64, cast result to binary32, nearest F2DOT14 directly; every nonidentity map retains old float32-normalized16 truncate.",
            DOUBLE_CONTROL: "Same table-structural rule, but identity axes retain binary64 normalization before direct nearest F2DOT14; nonidentity axes retain the old float32/truncate rule."}}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    save()
    try:
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix="swirl-a3-identity-") as directory:
            fonts = collection.fonts
            require(len(fonts) == 32 and all(f["maxp"].numGlyphs == 47102 for f in fonts),
                    "all_source_faces_gids_required")
            identities = source_identities(fonts)
            axes = {face: {a.axisTag: (a.minValue, a.defaultValue, a.maxValue)
                          for a in font["fvar"].axes} for face, font in enumerate(fonts)}
            records = {face: axis_records(font) for face, font in enumerate(fonts)}
            cases = identity_cases(axes)
            plans = [declare_readback(case["location"]) for case in cases]
            models = [identity_mappings(fonts[case["face_index"]], records[case["face_index"]], case["location"])
                      for case in cases]
            modes = ANCHOR_MODES + ("production",)
            gids = sorted(set(METRIC_GIDS) | {19177})
            report.update(user_positions=len(cases), new_holdout_positions=sum(c["is_holdout"] for c in cases),
                historical_control_positions=sum(not c["is_holdout"] for c in cases), selected_glyphs=gids,
                planned_constructor_modes=list(modes),
                production_mode_historical_controls_only=True,
                planned_native_records=4 * len(gids) * sum(len(mode_case_indices(cases, mode)) for mode in modes),
                all_cases_and_mappings_declared_before_native_launch=True,
                original_faces=[{"face_index": face, "original_axes": axes[face],
                    "original_avar_records_in_table_order": records[face],
                    "raw_avar_sha256": hashlib.sha256(font.reader["avar"]).hexdigest(),
                    "identity_axes": [tag for tag in TAGS if identity_records(records[face][tag])]}
                    for face, font in enumerate(fonts)],
                cases=[{**case, "binary64_bits": bits(case["location"]), "declared_models": mapping,
                    "predeclared_replay": {tag: plan["canonical"] for tag, plan in declaration.items()}}
                    for case, mapping, declaration in zip(cases, models, plans)])
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
                require(result.returncode == 0, "a3_identity_native_compile_failed")
            cache, reference = {}, {}

            def hvf_get(face, gid, design):
                key = (face, gid, *(design[tag] for tag in TAGS))
                if key not in cache:
                    cache[key] = raw_native_paths(hvf_events(hvf_binary, source, face, gid, design))
                    report["native_HVF_unique_calls"] += 1
                return cache[key]

            for mode in modes:
                indices = mode_case_indices(cases, mode)
                original, replayed = {}, {}
                mr = {"mode": mode, "status": "IN_PROGRESS", "user_positions": len(indices),
                    "opposite_order_pairs": 0, "opposite_order_exact_pairs": 0,
                    "opposite_order_mismatches": [], "replay_batch_checks": 0,
                    "replay_failed_batches": 0, "replay_failures": [],
                    "models": {name: {"horizontal_metrics": metric_stats(), "portable_geometry": control_stats(),
                                      "native_HVF_geometry": control_stats()} for name in ALL_MODELS},
                    "observations": []}
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
                        for index in (indices if order == "forward" else reversed(indices)):
                            case = cases[index]; face = case["face_index"]
                            point = case["location"]
                            report["active_context"] = {"mode": mode, "order": order,
                                "stage": "native_observation", "face_index": face, "case_label": case["label"]}
                            canonical = {tag: plan["canonical"] for tag, plan in plans[index].items()}
                            observed = checked_batch(oracle, face, gids, point)
                            replay = checked_batch(oracle, face, gids, canonical)
                            audit = replay_audit(identities[face], point, observed, replay, plans[index])
                            mr["replay_batch_checks"] += 1
                            if audit["status"] != "PASS_FINITE_REPLAY":
                                mr["replay_failed_batches"] += 1
                                mr["replay_failures"].append({"case_label": case["label"], "order": order, **audit})
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
                    finally:
                        oracle.close()
                    save()
                for face in sorted({cases[index]["face_index"] for index in indices}):
                    local = [index for index in indices if cases[index]["face_index"] == face]
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
                                        hvf_get(face, gid, design), raw_coretext_paths(observed[gid]["commands"]),
                                        face, gid, case["location"])
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
                mr["metric_exactness_by_cohort"] = {name: metric_summary(mr["observations"], name) for name in ALL_MODELS}
                mr["status"] = "COMPLETED_A3_IDENTITY_AVAR_DIAGNOSIS_NOT_ACCEPTANCE"
                save()
                print(json.dumps({"mode": mode, "status": mr["status"], "user_positions": len(indices),
                    "candidate_horizontal_metrics": mr["models"][CANDIDATE]["horizontal_metrics"],
                    "replay_failed_batches": mr["replay_failed_batches"]}), flush=True)
            require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "original_source_changed")
            actual = sum(p["summary"]["successful_glyph_count"] for p in report["native_processes"])
            require(actual == report["planned_native_records"], "a3_identity_native_record_total_mismatch")
            report.update(source_unchanged=True, actual_native_records=actual,
                actual_opposite_order_pairs=sum(m["opposite_order_pairs"] for m in report["modes"]),
                actual_replay_batches=sum(m["replay_batch_checks"] for m in report["modes"]),
                candidate_has_nonexact_holdout_metrics=any(
                    m["metric_exactness_by_cohort"][CANDIDATE]["holdouts"]["exact_matches"] !=
                    m["metric_exactness_by_cohort"][CANDIDATE]["holdouts"]["checks"] for m in report["modes"]),
                status="COMPLETED_NATIVE_A3_IDENTITY_AVAR_DIAGNOSIS_NOT_ACCEPTANCE")
            report.pop("active_context", None)
    except Exception as error:
        report.update(status="FAILED_A3_IDENTITY_AVAR_DIAGNOSIS_NOT_ACCEPTANCE", **diagnostic_failure(error))
        save()
        raise RuntimeError("A3 identity-avar diagnosis failed; safe checkpoint retained") from None
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
