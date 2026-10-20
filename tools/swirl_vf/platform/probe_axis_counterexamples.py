#!/usr/bin/env python3
"""Narrow follow-up to the completed native axis-threshold experiment.

Observe the eight remaining GID-19177 type failures, decimal neighbors of the
300/400 thresholds, and new held-out weights. The strict comparison is retained
alongside a separate raw-segment diagnosis. This never selects a production
mapping, changes a tolerance, or writes any source outline/raw metric.
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
import re
import subprocess
import tempfile

import numpy as np
from fontTools.ttLib import TTCollection

from probe_user_axis_geometry import coretext_paths
from diagnose_path_types import (diagnose_paths, raw_coretext_paths,
                                 raw_native_paths, raw_portable_paths)
from probe_axis_thresholds import (ALL_MODELS, INFERRED_REFERENCES, METRIC_GIDS, TAGS,
    BatchGeometry, EXPECTED, HVGL, LIMIT, NativeOracle, axis_records, check_metadata,
    checked_batch, compare_face, discrepancy, hvf_events, make_harness,
    mapping_candidates, metric_stats, native_paths, new_stats, portable_paths,
    record_check, require, same_json, same_private_payload, source_identities)


TYPE_CASES = (
    (0, 500., 837.5754436931355, 500.),
    (1, 422.3943344488167, 810.2631054512518, 344.1305449918785),
    (8, 500., 831.1462518294346, 500.),
    *((face, 1., 100., 1.) for face in range(15, 20)),
)


def counterexample_cases(ranges_by_face):
    """Predeclare cases from ranges alone; never inspect native observations."""
    require(set(ranges_by_face) == set(range(32)), "all_original_faces_required")
    for ranges in ranges_by_face.values():
        require(set(ranges) == set(TAGS), "all_original_axis_tags_required")
        for values in ranges.values():
            require(len(values) == 3 and all(type(v) in (float, int) and math.isfinite(v)
                for v in values) and values[0] <= values[1] <= values[2]
                and values[0] < values[2], "invalid_source_axis_range")
    result, seen = {}, {}

    def add(face, label, updates, cohort):
        ranges = ranges_by_face[face]
        location = {tag: float(ranges[tag][1]) for tag in TAGS}
        location.update(updates)
        require(all(ranges[tag][0] <= location[tag] <= ranges[tag][2] for tag in TAGS),
                "counterexample_outside_original_range")
        key = (face, *(location[tag] for tag in TAGS))
        if key in seen:
            row = seen[key]
            if label not in row["labels"]:
                row["labels"].append(label)
            if cohort not in row["cohorts"]:
                row["cohorts"].append(cohort)
            return
        row = {"label": label, "labels": [label], "cohort": cohort,
               "cohorts": [cohort], "location": location}
        result.setdefault(face, []).append(row)
        seen[key] = row

    for face, width, weight, height in TYPE_CASES:
        add(face, "remaining_type_failure", dict(zip(TAGS, (width, weight, height))), "type_failures")
    # The neighboring decimal requests bracket six 16.16 steps in both
    # directions. They extend the prior observations without selecting a
    # special rule for the 400 interval or overwriting its raw avar records.
    for face in (20, 24, 31):
        for center in (300., 400.):
            for step in range(-6, 7):
                value = center + step * 400 / 65536
                lower = math.floor(value * 10000)
                for offset in (0, 1):
                    add(face, f"threshold_{center:g}_step_{step}_decimal_{offset}",
                        {"wght": (lower + offset) / 10000}, "narrow_thresholds")
            # The 300-left raw interval has another slope: include its own
            # decimal neighbors of 50/3277 as well as the 50/4915 neighbors.
            for delta in (.0061, .0062, .008, .01, .0101, .0102, .0121, .0122, .0123, .0152, .0153, .04):
                for direction in (-1, 1):
                    add(face, f"threshold_{center:g}_delta_{direction * delta:g}",
                        {"wght": center + direction * delta}, "narrow_thresholds")
        for weight in (300.025, 400.025, 399.968):
            add(face, f"float32_half_grid_control_{weight:g}", {"wght": weight}, "narrow_thresholds")
    for face, weight in ((25, 482.20654224674365), (30, 462.34568323838)):
        add(face, "zero_anchor_rule_falsifier", {"wght": weight}, "rejected_rule_controls")
    for face in (20, 24, 25, 30, 31):
        rng = random.Random(20561020 + face)
        for index in range(8):
            add(face, f"new_weight_holdout_{index}", {"wght": rng.uniform(440., 495.)}, "fresh_holdouts")
    for face in tuple(result):
        add(face, "source_default_control", {}, "defaults")
    return dict(sorted(result.items()))


def direct_checks(binary, source, face, rows, observations, renderer, report):
    """Native three-way checks retain the original strict L/Q result."""
    for index, row in enumerate(rows):
        cohorts = set(row["cohorts"])
        if not (cohorts & {"type_failures", "rejected_rule_controls"}
                or face == 20 and "narrow_thresholds" in cohorts):
            continue
        designs = [("canonical_normalized16_truncate",
                    row["global_model_design_coordinates"]["canonical_normalized16_truncate"])]
        inferred = row.get("HVAR_conditioned_design_coordinate")
        if inferred is not None and not same_json(inferred, designs[0][1]):
            designs.append(("HVAR_conditioned_not_global_mapping", inferred))
        row["direct_native_checks"] = []
        for reference, design in designs:
            for gid in (5, 19177):
                report["active_context"] = {"stage": "direct_native_and_raw_type_comparison",
                    "face_index": face, "glyph_id": gid, "user_location": row["location"],
                    "reference": reference, "design_location": design}
                events = hvf_events(binary, source, face, gid, design)
                native = native_paths(events)
                matrix = np.asarray([[design[tag] for tag in TAGS]])
                rendered = renderer.render(gid, matrix[:, :renderer.table.part(gid).axis_count])
                points = [p[0] for p in rendered.paths]
                coretext = coretext_paths(observations[index][gid]["commands"])
                portable = portable_paths(points)
                checks = {"reference": reference, "glyph_id": gid, "strict": {}}
                for name, left, right in (("native_HVF_vs_CoreText", native, coretext),
                    ("portable_vs_native_HVF", portable, native),
                    ("portable_vs_CoreText", portable, coretext)):
                    stats = new_stats()
                    record_check(stats, face, gid, row["location"], lambda: discrepancy(left, right)[0])
                    checks["strict"][name] = stats
                    global_stats = report["direct_strict"][name]
                    record_check(global_stats, face, gid, row["location"], lambda: discrepancy(left, right)[0])
                if "type_failures" in cohorts and gid == 19177:
                    raw_native = raw_native_paths(events)
                    raw_portable = raw_portable_paths(points)
                    raw_coretext = raw_coretext_paths(observations[index][gid]["commands"])
                    checks["raw_segment_diagnosis_not_acceptance"] = {
                        "native_HVF_vs_CoreText": diagnose_paths(raw_native, raw_coretext),
                        "portable_vs_native_HVF": diagnose_paths(raw_portable, raw_native),
                        "portable_vs_CoreText": diagnose_paths(raw_portable, raw_coretext)}
                row["direct_native_checks"].append(checks)


def run(source, output):
    require(not output.exists() and output.resolve() != source.resolve(), "new_report_path_required")
    require(source.stat().st_size == 61473880
            and hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "exact_original_source_required")
    report = {"status": "NOT_RUN", "source_sha256": EXPECTED,
        "source_commit": os.environ.get("GITHUB_SHA"), "platform": platform.platform(),
        "outline_limit_font_units": LIMIT, "metric_limit_font_units": LIMIT,
        "production_mapping_changed": False, "strict_comparator_changed": False,
        "raw_avar_records_modified": False,
        "source_outlines_or_raw_metrics_published": False, "font_generated": False,
        "mapping_accepted": False, "continuous_space_accepted": False,
        "HVAR_conditioned_reference_is_not_a_global_mapping": True,
        "independent_processes_do_not_claim_system_service_cache_reset": True,
        "native_processes": [], "faces": [], "faces_completed": 0, "user_positions": 0,
        "global_models": {name: {"geometry": new_stats(), "horizontal_metrics": metric_stats()} for name in ALL_MODELS},
        "HVAR_conditioned_references": {name: new_stats() for name in INFERRED_REFERENCES},
        "opposite_order": {"glyph_pairs": 0, "exact_payload_pairs": 0, "readback_mismatches": 0, "mismatches": []},
        "direct_strict": {name: new_stats() for name in
            ("native_HVF_vs_CoreText", "portable_vs_native_HVF", "portable_vs_CoreText")}}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    save()
    try:
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix="swirl-axis-counterexample-") as directory:
            fonts = collection.fonts
            require(len(fonts) == 32 and all(f["maxp"].numGlyphs == 47102 for f in fonts), "all_source_faces_gids_required")
            identities = source_identities(fonts)
            cases_by_face = counterexample_cases({face: {a.axisTag: (a.minValue, a.defaultValue, a.maxValue)
                for a in font["fvar"].axes} for face, font in enumerate(fonts)})
            mappings = {face: [mapping_candidates(fonts[face], axis_records(fonts[face]), case["location"])
                for case in cases] for face, cases in cases_by_face.items()}
            report["planned_positions"] = sum(map(len, cases_by_face.values()))
            report["selected_faces"] = list(cases_by_face)
            gids = sorted(set(METRIC_GIDS) | {19177})
            report["selected_glyphs"] = gids
            hvgl = fonts[0].reader["hvgl"]
            hvgl_hash = hashlib.sha256(hvgl).hexdigest()
            require(all(hashlib.sha256(fonts[face].reader["hvgl"]).hexdigest() == hvgl_hash
                for face in cases_by_face), "unshared_original_HVGL")
            renderer = BatchGeometry(HVGL(hvgl), isolated_tangents=True)
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
            original = {face: [None] * len(cases) for face, cases in cases_by_face.items()}
            requests = [(face, index) for face, cases in cases_by_face.items() for index in range(len(cases))]
            for order in ("forward", "reverse"):
                oracle = NativeOracle(binary, source, root / f"{order}.log")
                try:
                    check_metadata(oracle.metadata, identities, source.stat().st_size)
                    for face, index in (requests if order == "forward" else reversed(requests)):
                        location = cases_by_face[face][index]["location"]
                        report["active_context"] = {"stage": "CoreText_observation", "order": order,
                            "face_index": face, "case_number": index, "user_location": location}
                        records = checked_batch(oracle, face, gids, location)
                        if order == "forward":
                            original[face][index] = records
                        else:
                            for gid in gids:
                                left, right = original[face][index][gid], records[gid]
                                payload_equal = same_private_payload(left, right)
                                echo_equal = same_json(left["reported_location"], right["reported_location"])
                                report["opposite_order"]["glyph_pairs"] += 1
                                report["opposite_order"]["exact_payload_pairs"] += payload_equal
                                report["opposite_order"]["readback_mismatches"] += not echo_equal
                                if not (payload_equal and echo_equal):
                                    report["opposite_order"]["mismatches"].append({"face_index": face,
                                        "case_number": index, "glyph_id": gid, "user_location": location,
                                        "payload_equal": payload_equal, "readback_equal": echo_equal})
                    summary = oracle.finish()
                    report["native_processes"].append({"order": order,
                        "os_version": oracle.metadata.get("os_version"), "all_32_physical_faces_verified": True,
                        "summary": summary, "exit_status": 0})
                finally:
                    oracle.close()
                save()
            for face, cases in cases_by_face.items():
                report["active_context"] = {"stage": "portable_and_HVAR_comparison", "face_index": face}
                rows, _ = compare_face(fonts[face], face, cases, original[face], renderer, gids, report, mappings[face])
                direct_checks(hvf_binary, source, face, rows, original[face], renderer, report)
                report["faces"].append({"face_index": face, "user_positions": len(cases), "observations": rows})
                report["faces_completed"] += 1
                report["user_positions"] += len(cases)
                report["status"] = "IN_PROGRESS_DIAGNOSIS_NOT_ACCEPTANCE"
                save()
                print(json.dumps({"face_index": face, "positions_completed": report["user_positions"]}), flush=True)
            require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "original_source_changed")
            report.update(source_unchanged=True, status="COMPLETED_COUNTEREXAMPLE_DIAGNOSIS_NOT_FONT_ACCEPTANCE")
            report.pop("active_context", None)
    except Exception as error:
        report.update(status="FAILED_DIAGNOSIS_NOT_ACCEPTANCE", failure_type=type(error).__name__)
        if re.fullmatch(r"[A-Za-z0-9_]{1,160}", str(error)):
            report["failure_code"] = str(error)
        save()
        raise RuntimeError("axis counterexample diagnosis failed; safe checkpoint retained") from None
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
