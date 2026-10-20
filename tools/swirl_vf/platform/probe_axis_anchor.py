#!/usr/bin/env python3
"""Diagnose far-axis construction without accepting a new production oracle.

All CoreText outputs are actual observations. Initial bases, two independently
declared anchor choices, exact decimal replay, raw avar models, HVAR inversion
and native HVF geometry have separate verdicts. No raw Apple payload is saved.
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

import numpy as np
from fontTools.ttLib import TTCollection

from anchor_construction_harness import MODES, MODE_ENV, make_harness
from axis_anchor_cases import anchor_cases
from analyze_axis_quantization import float32, ordered_map
from diagnose_path_types import (compare_preserved_quadratics, raw_coretext_paths,
                                 raw_native_paths, raw_portable_paths)
from probe_axis_plateau import compare_payloads, safe_failure
from probe_axis_thresholds import (EXPECTED, LIMIT, METRIC_GIDS, TAGS, NativeOracle,
    BatchGeometry, HVGL, SourceMetrics, add_metric, axis_records, bits, check_metadata,
    checked_batch, conditioned_grid, declare_readback, hvf_events, infer_at_axis_nodes,
    mapping_candidates, metric_stats, new_stats, record_check, require, same_json,
    same_private_payload, source_identities)
from calibrate_avar_metrics import normalize
from verified_axis_oracle import ENVELOPE, VerificationError, effective_readback


MODEL_NAMES = ("canonical_normalized16_truncate", "canonical_float32_normalized16_truncate")
NATIVE_ERROR_CODES = frozenset((
    "invalid_anchor_axis_range_or_target", "anchor_not_inside_source_range_or_not_distant",
    "anchor_nonfinite_optical_attribute", "anchor_expected_optical_attribute_invalid",
    "anchor_optical_inheritance_mismatch", "anchor_axis_identity_mismatch",
    "anchor_nondefault_axis_not_reported", "anchor_readback_not_exactly_predeclared",
    "anchor_all_original_faces_required", "anchor_missing_original_base",
    "anchor_mode_missing_or_unknown", "anchor_target_axis_missing",
    "anchor_wrong_original_source", "anchor_requires_source_path_only",
    "coretext_font_size_mismatch", "coretext_non_identity_font_matrix", "unknown_axis_tag",
    "requested_face_has_no_verified_coretext_descriptor"))


def diagnostic_failure(error):
    """Recover only named public error codes from the native transport wrapper."""
    result = safe_failure(error)
    match = re.fullmatch(r"(?:native request [0-9]+ face [0-9]+ failed|native oracle startup failed): ([A-Za-z0-9_]{1,160})",
                         str(error))
    if match and match.group(1) in NATIVE_ERROR_CODES:
        result["native_failure_code"] = match.group(1)
    return result


def declared_mappings(font, records, location):
    """Two fixed hypotheses; the float32 cast follows double normalization only."""
    result = {MODEL_NAMES[0]: mapping_candidates(font, records, location)[MODEL_NAMES[0]]}
    canonical = {tag: plan["canonical"] for tag, plan in declare_readback(location).items()}
    mapped = {}
    for axis in font["fvar"].axes:
        value = normalize(canonical[axis.axisTag], axis.minValue, axis.defaultValue, axis.maxValue)
        value = math.trunc(float32(value) * 65536) / 65536
        raw = tuple((int(x * 16384), int(y * 16384)) for x, y in records[axis.axisTag])
        design = ordered_map(value, raw)
        mapped[axis.axisTag] = math.floor(design * 16384 + .5) / 16384
    result[MODEL_NAMES[1]] = mapped
    return result


@contextmanager
def selected_mode(mode):
    require(mode in MODES, "unknown_anchor_mode")
    previous = os.environ.get(MODE_ENV)
    os.environ[MODE_ENV] = mode
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(MODE_ENV, None)
        else:
            os.environ[MODE_ENV] = previous


def replay_audit(identity, location, original, replay, declaration):
    """Use the production readback checks; keep all payload fields in equality.

    These records have already passed native transport/arity checks. A failed
    diagnostic does not release records to any builder. Both native requests
    are executed even when a readback fails so that all failure evidence stays.
    """
    canonical = {tag: plan["canonical"] for tag, plan in declaration.items()}
    require(set(original) == set(replay) and bool(original), "replay_glyph_sets_differ")
    result = {"status": "PASS_FINITE_REPLAY", "predeclared_replay_location": canonical,
              "readback_failures": [], "payload_differences": [], "glyph_pairs": len(original)}
    for gid in original:
        for phase, record, point in (("original", original[gid], location), ("replay", replay[gid], canonical)):
            require(record["face_index"] == identity["face_index"] and record["glyph_id"] == gid
                    and same_json(record["location"], point), "replay_record_identity_mismatch")
            try:
                effective_readback(record, identity, point, replay=phase == "replay", declaration=declaration)
            except VerificationError as error:
                # effective_readback's context contains axis numbers only. Never
                # pass a native request_error or payload through this channel.
                context = {k: v for k, v in error.context.items() if k in (
                    "axis", "phase", "requested_value", "requested_value_hex", "reported_axis_present",
                    "reported_value", "reported_value_hex", "expected_candidate_value",
                    "expected_candidate_value_hex", "expected_secondary_candidate_value",
                    "expected_secondary_candidate_value_hex")}
                result["readback_failures"].append({"glyph_id": gid, **safe_failure(error), **context})
        left = {k: v for k, v in original[gid].items() if k not in ENVELOPE}
        right = {k: v for k, v in replay[gid].items() if k not in ENVELOPE}
        if not same_json(left, right):
            fields = sorted(k for k in left.keys() | right.keys()
                            if k not in left or k not in right or not same_json(left[k], right[k]))
            result["payload_differences"].append({"glyph_id": gid, "fields": fields})
    if result["readback_failures"] or result["payload_differences"]:
        result["status"] = "FAILED_FINITE_REPLAY"
    return result


def control_stats():
    return {"legacy": new_stats(), "preserved_controls": new_stats(), "glyphs_with_restored_Q": 0}


def add_control(stats, left, right, face, gid, location):
    result = compare_preserved_quadratics(left, right)
    for key, outcome in (("legacy", result["legacy"]), ("preserved_controls", result)):
        def error():
            if outcome["status"] == "rejected":
                raise ValueError(outcome["reason"])
            return outcome["maximum_point_error"]
        record_check(stats[key], face, gid, location, error)
    stats["glyphs_with_restored_Q"] += result["restored_segment_count"] > 0
    return {"status": result["status"], "maximum_point_error": result["maximum_point_error"],
            "reason": result.get("reason"), "legacy": result["legacy"],
            "restored_segment_count": result["restored_segment_count"]}


def direct_case(face, case):
    """Predeclare a small direct-HVF subset, independently of observed errors."""
    point = case["location"]
    if face not in (0, 20, 24, 31):
        return False
    return (point["wght"] in (299.9817, 300.01, 400.04, 400.0401)
            or any("random_triple_0" in label for label in case.get("labels", [case["label"]]))
            or case["label"] == "default")


def evaluate_face(font, face, cases, observations, renderer, gids, mode_report, mappings,
                  hvf_get, is_anchor):
    metrics = SourceMetrics(font)
    inference = infer_at_axis_nodes(font, axis_records(font), cases, observations)
    raw_native = [{gid: raw_coretext_paths(records[gid]["commands"]) for gid in gids}
                  for records in observations]
    rows = []
    specifications = [(index, name, design) for index, designs in enumerate(mappings)
                      for name, design in designs.items()]
    for index, (case, records) in enumerate(zip(cases, observations)):
        row = {**case, "requested_binary64_hex": bits(case["location"]),
               "reported_location": records[gids[0]]["reported_location"],
               "reported_binary64_hex": bits(records[gids[0]]["reported_location"]),
               "declared_model_design_coordinates": mappings[index], "model_checks": {}}
        for name, design in mappings[index].items():
            error = max(abs(records[gid]["advance_width"] - metrics.at(gid, design)["advance_width"])
                        for gid in METRIC_GIDS)
            add_metric(mode_report["models"][name]["horizontal_metrics"], error)
            row["model_checks"][name] = {"maximum_horizontal_metric_error": error, "geometry": []}
        if index in inference:
            row["HVAR_inference"] = inference[index]
            q = conditioned_grid(inference[index])
            row["HVAR_inferred_f2dot14"] = q
            if q is not None and direct_case(face, case):
                axes = {a.axisTag: a for a in font["fvar"].axes}
                design = {tag: normalize(case["location"][tag], axes[tag].minValue,
                    axes[tag].defaultValue, axes[tag].maxValue) for tag in TAGS}
                design["wght"] = q / 16384
                row["HVAR_conditioned_HVF_checks"] = []
                for gid in (5, 19177):
                    comparison = add_control(mode_report["conditional_native_HVF"],
                        hvf_get(face, gid, design), raw_native[index][gid], face, gid, case["location"])
                    row["HVAR_conditioned_HVF_checks"].append({"glyph_id": gid,
                        "design_location": design, **comparison})
        rows.append(row)
    for start in range(0, len(specifications), 512):
        chunk = specifications[start:start + 512]
        matrix = np.asarray([[design[tag] for tag in TAGS] for _, _, design in chunk])
        for gid in gids:
            batch = renderer.render(gid, matrix[:, :renderer.table.part(gid).axis_count])
            for offset, (index, name, design) in enumerate(chunk):
                comparison = add_control(mode_report["models"][name]["portable_geometry"],
                    raw_portable_paths([path[offset] for path in batch.paths]), raw_native[index][gid],
                    face, gid, cases[index]["location"])
                rows[index]["model_checks"][name]["geometry"].append({"glyph_id": gid, **comparison})
                if is_anchor and gid in (5, 19177) and direct_case(face, cases[index]):
                    native = hvf_get(face, gid, design)
                    comparison = add_control(mode_report["models"][name]["native_HVF_geometry"],
                        native, raw_native[index][gid], face, gid, cases[index]["location"])
                    rows[index]["model_checks"][name].setdefault("native_HVF_geometry", []).append(
                        {"glyph_id": gid, **comparison})
    return rows


def run(source, output):
    require(not output.exists() and source.resolve() != output.resolve(), "new_report_path_required")
    require(source.stat().st_size == 61473880 and hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED,
            "exact_original_source_required")
    report = {"status": "NOT_RUN", "source_sha256": EXPECTED, "source_commit": os.environ.get("GITHUB_SHA"),
        "platform": platform.platform(), "production_constructor_changed": False, "production_mapping_changed": False,
        "raw_avar_records_modified": False, "source_outlines_or_raw_metrics_published": False,
        "mapping_accepted": False, "font_generated": False, "outline_limit_font_units": LIMIT,
        "continuous_space_accepted": False, "conditional_HVAR_is_not_global_mapping": True,
        "native_processes": [], "modes": [], "native_HVF_unique_calls": 0}
    output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    save()
    try:
        with TTCollection(source, lazy=True) as collection, tempfile.TemporaryDirectory(prefix="swirl-axis-anchor-") as directory:
            fonts = collection.fonts
            require(len(fonts) == 32 and all(f["maxp"].numGlyphs == 47102 for f in fonts), "all_source_faces_gids_required")
            identities = source_identities(fonts)
            ranges = {face: {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes}
                      for face, font in enumerate(fonts)}
            cases = anchor_cases(ranges)
            requests = [(face, index) for face, rows in cases.items() for index in range(len(rows))]
            mappings = {face: [declared_mappings(fonts[face], axis_records(fonts[face]), case["location"])
                              for case in rows] for face, rows in cases.items()}
            declarations = {face: [declare_readback(case["location"]) for case in rows] for face, rows in cases.items()}
            gids = sorted(set(METRIC_GIDS) | {19177})
            report.update(selected_faces=list(cases), selected_glyphs=gids, user_positions=len(requests),
                planned_constructor_modes=list(MODES), planned_native_records=4 * len(MODES) * len(requests) * len(gids),
                replay_plan_declared_before_native_launch=True, model_names=list(MODEL_NAMES))
            table_bytes = fonts[0].reader["hvgl"]
            digest = hashlib.sha256(table_bytes).hexdigest()
            require(all(hashlib.sha256(fonts[face].reader["hvgl"]).hexdigest() == digest for face in cases),
                    "unshared_original_HVGL")
            renderer = BatchGeometry(HVGL(table_bytes), isolated_tangents=True)
            root = Path(directory)
            swift, binary, hvf_binary = root / "diagnostic.swift", root / "diagnostic", root / "hvf_oracle"
            code = Path(__file__).with_name("coretext_extract.swift").read_text()
            harness = make_harness(code)
            swift.write_text(harness)
            report.update(extractor_source_sha256=hashlib.sha256(code.encode()).hexdigest(),
                          generated_harness_sha256=hashlib.sha256(harness.encode()).hexdigest())
            commands = (["xcrun", "swiftc", "-O", str(swift), "-o", str(binary)],
                        ["xcrun", "clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                         "-mmacosx-version-min=15.4", str(Path(__file__).with_name("hvf_oracle.c")), "-lhvf", "-o", str(hvf_binary)])
            for command in commands:
                result = subprocess.run(command, capture_output=True, text=True, timeout=180)
                if result.returncode:
                    report["compiler_failure_excerpt"] = result.stderr[-6000:]
                require(result.returncode == 0, "anchor_native_diagnostic_compile_failed")
            cache = {}

            def hvf_get(face, gid, design):
                key = (face, gid, *(design[tag] for tag in TAGS))
                if key not in cache:
                    cache[key] = raw_native_paths(hvf_events(hvf_binary, source, face, gid, design))
                    report["native_HVF_unique_calls"] += 1
                return cache[key]

            production = anchor_reference = None
            require(MODES[0] == "production", "production_control_must_be_first")
            for mode in MODES:
                original = {face: [None] * len(rows) for face, rows in cases.items()}
                replayed = {face: [None] * len(rows) for face, rows in cases.items()}
                mode_report = {"mode": mode, "status": "IN_PROGRESS", "opposite_order_pairs": 0,
                    "opposite_order_exact_pairs": 0, "opposite_order_mismatches": [], "replay_batch_checks": 0,
                    "replay_failed_batches": 0, "replay_failures": [], "faces": [],
                    "conditional_native_HVF": control_stats(),
                    "models": {name: {"horizontal_metrics": metric_stats(), "portable_geometry": control_stats(),
                                      "native_HVF_geometry": control_stats()} for name in MODEL_NAMES}}
                report["modes"].append(mode_report)
                for order in ("forward", "reverse"):
                    report["active_context"] = {"stage": "native_start", "mode": mode, "order": order}
                    with selected_mode(mode):
                        oracle = NativeOracle(binary, source, root / f"{mode}-{order}.log")
                    try:
                        check_metadata(oracle.metadata, identities, source.stat().st_size)
                        require(oracle.metadata.get("anchor_mode") == mode, "wrong_native_anchor_mode")
                        process = {"mode": mode, "order": order, "all_32_physical_faces_verified": True,
                            "os_version": oracle.metadata.get("os_version"),
                            "base_instances": [{"face_index": f["face_index"], **{k: v for k, v in f.items()
                                               if k.startswith("anchor_") or k.startswith("plateau_")}}
                                               for f in oracle.metadata["faces"]]}
                        report["native_processes"].append(process)
                        for face, index in (requests if order == "forward" else reversed(requests)):
                            point = cases[face][index]["location"]
                            plan = declarations[face][index]
                            canonical = {tag: item["canonical"] for tag, item in plan.items()}
                            report["active_context"] = {"stage": "native_observation", "mode": mode, "order": order,
                                "face_index": face, "case_number": index, "user_location": point}
                            observed = checked_batch(oracle, face, gids, point)
                            replay = checked_batch(oracle, face, gids, canonical)
                            audit = replay_audit(identities[face], point, observed, replay, plan)
                            mode_report["replay_batch_checks"] += 1
                            if audit["status"] != "PASS_FINITE_REPLAY":
                                mode_report["replay_failed_batches"] += 1
                                mode_report["replay_failures"].append({"face_index": face, "user_location": point,
                                    "order": order, **audit})
                            if order == "forward":
                                original[face][index], replayed[face][index] = observed, replay
                            else:
                                for phase, left, right in (("original", original[face][index], observed),
                                                           ("replay", replayed[face][index], replay)):
                                    for gid in gids:
                                        equal = (same_private_payload(left[gid], right[gid]) and
                                                 same_json(left[gid]["reported_location"], right[gid]["reported_location"]))
                                        mode_report["opposite_order_pairs"] += 1
                                        mode_report["opposite_order_exact_pairs"] += equal
                                        if not equal:
                                            mode_report["opposite_order_mismatches"].append({"face_index": face,
                                                "glyph_id": gid, "user_location": point, "phase": phase})
                        process.update(summary=oracle.finish(), exit_status=0)
                    finally:
                        oracle.close()
                    save()
                if mode == "production":
                    production = original
                elif anchor_reference is None:
                    anchor_reference = original
                require(production is not None, "missing_original_constructor_control")
                for face, rows in cases.items():
                    report["active_context"] = {"stage": "independent_reference_comparison", "mode": mode, "face_index": face}
                    safe_rows = evaluate_face(fonts[face], face, rows, original[face], renderer, gids,
                                              mode_report, mappings[face], hvf_get, mode != "production")
                    for index, row in enumerate(safe_rows):
                        row["against_production"] = [{"glyph_id": gid,
                            **compare_payloads(production[face][index][gid], original[face][index][gid])} for gid in gids]
                        if mode != "production":
                            row["against_first_anchor"] = [{"glyph_id": gid,
                                **compare_payloads(anchor_reference[face][index][gid], original[face][index][gid])} for gid in gids]
                    mode_report["faces"].append({"face_index": face, "observations": safe_rows})
                    save()
                mode_report["status"] = "COMPLETED_ANCHOR_DIAGNOSIS_NOT_ACCEPTANCE"
                save()
                print(json.dumps({"mode": mode, "positions": len(requests), "replay_failed_batches":
                                  mode_report["replay_failed_batches"], "status": mode_report["status"]}), flush=True)
            require(hashlib.sha256(source.read_bytes()).hexdigest() == EXPECTED, "original_source_changed")
            report.update(source_unchanged=True, status="COMPLETED_NATIVE_ANCHOR_DIAGNOSIS_NOT_ACCEPTANCE")
            report.pop("active_context", None)
    except Exception as error:
        report.update(status="FAILED_ANCHOR_DIAGNOSIS_NOT_ACCEPTANCE", **diagnostic_failure(error))
        save()
        raise RuntimeError("axis anchor diagnosis failed; safe checkpoint retained") from None
    save()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
