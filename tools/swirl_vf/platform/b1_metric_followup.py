#!/usr/bin/env python3
"""Fresh native B1 samples for post-stage-1 hypotheses, never metric correction."""
from __future__ import annotations

import argparse
import datetime
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

from b1_metric_discriminator import (
    LIMIT, design_fraction, digest, load_native_json, number, observe,
    require, summarize, validate_raw, verify_replay,
)
from b1_metric_fixture import rational
from b1_metric_followup_fixture import MODEL_STATUS, build_suite, round_delta_away


def fraction_record(value):
    return Fraction(value["numerator"], value["denominator"])


def freeze_origin_predictions(manifest):
    """Freeze competing bbox/bearing interpretations before native execution."""
    manifest["origin_y_model_status"] = MODEL_STATUS
    manifest["origin_y_model_scope"] = (
        "Rectangular witness only. Competing ceil and nearest control-bbox models; "
        "For integer top P, B+P-ceil(B) equals B+floor(P-B), so bbox rounding "
        "and bearing rounding cannot be distinguished by that expression. "
        "Not an assertion of Apple's internal bounding-box implementation."
    )
    for entry in manifest["entries"]:
        require(len({r["id"] for r in entry["requests"]}) == len(entry["requests"]),
                "duplicate_frozen_request_id")
        predictions = {}
        for request in entry["requests"]:
            y = number(request["axes"]["HGHT"])
            bounds = request["expected"]["witness_bounds"]
            visible_max = number(bounds[1]) + number(bounds[3])
            top = 820 + entry["phantom_shift"] + round_delta_away(60*y)
            ceil_bbox, nearest_bbox = math.ceil(visible_max), round_delta_away(visible_max)
            has_vorg = "VORG" in entry["table_sha256"]
            has_vvar = "VVAR" in entry["table_sha256"]
            if has_vorg:
                source, selected = "stored_VORG_y", Fraction(911)
            elif has_vvar:
                source, selected = "VVAR_continuous_top", number(request["expected"]["vertical_origin_y"])
            else:
                source, selected = "rounded_delta_plus_visible_minus_ceil_bbox", visible_max + top - ceil_bbox
            predictions[request["id"]] = {
                "top_after_delta_round": top, "visible_control_ymax_exact": rational(visible_max),
                "ceil_control_ymax": ceil_bbox, "nearest_control_ymax": nearest_bbox,
                "ceil_bbox_candidate": rational(visible_max + top - ceil_bbox),
                "nearest_bbox_candidate": rational(visible_max + top - nearest_bbox),
                "continuous_candidate": rational(number(request["expected"]["vertical_origin_y"])),
                "selected_source_candidate": source, "selected_prediction": rational(selected),
            }
        entry["predictions_origin_y"] = predictions
    return manifest


def exact_prediction(actual, predicted):
    actual, predicted = number(actual), number(predicted)
    return {"prediction_exact": rational(predicted), "observed_exact": rational(actual),
            "error_exact": rational(actual-predicted), "exact_match": actual == predicted}


def observe_followup(entry, request, row):
    result = observe(entry, request, row)
    result["case_group"] = request["case_group"]
    height = design_fraction(result["quantities"]["advance_height"])
    width = design_fraction(result["quantities"]["advance_width"])
    origin_x = -design_fraction(result["quantities"]["vertical_translation_x"])
    origin_y = -design_fraction(result["quantities"]["vertical_translation_y"])
    height_basis = entry["predictions_round_delta"][request["id"]]
    has_vvar = "VVAR" in entry["table_sha256"]
    height_prediction = (height_basis["vvar_truncate_continuous"]["prediction"] if has_vvar
                         else height_basis["prediction"])
    result["fresh_height_candidate"] = {
        "status": MODEL_STATUS, "source_candidate": "VVAR_truncate_continuous" if has_vvar else "gvar_delta_round_then_quantize",
        **exact_prediction(height, height_prediction),
    }
    origins = entry["predictions_origin_y"][request["id"]]
    result["fresh_origin_y_candidates"] = {
        name: exact_prediction(origin_y, fraction_record(origins[name]))
        for name in ("ceil_bbox_candidate", "nearest_bbox_candidate", "continuous_candidate", "selected_prediction")
    }
    result["fresh_origin_y_selected_source"] = origins["selected_source_candidate"]
    storage = entry["origin_x_storage_hypotheses"]
    result["origin_x_relationships"] = {
        "half_current_raw_advance": exact_prediction(origin_x, width/2),
        "half_current_continuous_advance": exact_prediction(origin_x, number(request["expected"]["advance_width"])/2),
        "half_stored_advance_exact": exact_prediction(origin_x, fraction_record(storage["exact_stored_half"])),
        "half_stored_advance_truncated": exact_prediction(origin_x, storage["truncated_stored_half"]),
    }
    return result


def followup_summary(observations):
    result = summarize(observations)
    for row in observations:
        group = result[row["fixture_id"]]
        group["fresh_height_candidate_matches"] = group.get("fresh_height_candidate_matches", 0) + row["fresh_height_candidate"]["exact_match"]
        for field in ("fresh_origin_y_candidates", "origin_x_relationships"):
            counts = group.setdefault(field, {})
            for name, comparison in row[field].items():
                counts[name] = counts.get(name, 0) + comparison["exact_match"]
    return result


def paired_table_effects(manifest, observations):
    planned = {}
    for entry in manifest["entries"]:
        for request in entry["requests"]:
            key = (entry["upem"], entry["variant"], request["id"])
            require(key not in planned, "duplicate_frozen_request_id")
            planned[key] = (entry, request)
    lookup = {}
    for row in observations:
        key = (row["upem"], row["variant"], row["request_id"])
        require(key not in lookup, "duplicate_observation_for_table_comparison")
        require(key in planned, "unplanned_observation_for_table_comparison")
        entry, request = planned[key]
        require(row["axes"] == request["axes"] and row["fixture_id"] == entry["fixture_id"],
                "table_comparison_location_or_identity_mismatch")
        lookup[key] = row
    require(set(lookup) == set(planned), "table_comparison_incomplete_observation_set")
    results = []
    for entry in manifest["entries"]:
        if entry["variant"] == entry["comparison_variant"]:
            continue
        for request in entry["requests"]:
            key = (entry["upem"], entry["variant"], request["id"])
            baseline = lookup[(entry["upem"], entry["comparison_variant"], request["id"])]
            row = lookup[key]
            require(row["axes"] == baseline["axes"], "table_comparison_location_or_identity_mismatch")
            differences = {
                name: rational(design_fraction(value) - design_fraction(baseline["quantities"][name]))
                for name, value in row["quantities"].items()
            }
            results.append({"fixture": entry["fixture_id"], "comparison_variant": entry["comparison_variant"],
                            "request_id": request["id"], "axes": request["axes"],
                            "native_quantity_differences_exact": differences})
    return results


def compact_report(report):
    result = {k: v for k, v in report.items() if k not in ("observations", "native_executions", "paired_table_effects")}
    # All 546 finite measurements are small enough to expose in the job log.
    # This is original synthetic geometry, not any Apple font's contours.
    result["observed_metrics"] = [{
        "fixture": row["fixture_id"], "axes": row["axes"], "case_group": row["case_group"],
        "raw_height": row["quantities"]["advance_height"]["raw_points"],
        "raw_height_bits": row["quantities"]["advance_height"]["raw_binary64_hex"],
        "height_prediction": row["fresh_height_candidate"]["prediction_exact"]["value"],
        "height_candidate_matches": row["fresh_height_candidate"]["exact_match"],
        "origin_y_predictions": {name: candidate["prediction_exact"]["value"]
                                 for name, candidate in row["fresh_origin_y_candidates"].items()},
        "origin_y_selected_matches": row["fresh_origin_y_candidates"]["selected_prediction"]["exact_match"],
        "metrics": row["measured_design_units"], "witness_pass": row["witness_pass"],
        "layout_equals_direct": row["layout_step_equals_direct_height"],
        "strict_metrics_pass": row["strict_metrics_pass"],
    } for row in report["observations"]]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    require(not out.exists(), "new_output_directory_required")
    out.mkdir(parents=True)
    report = {
        "schema_version": 1, "status": "NOT_RUN", "source_commit": os.environ.get("GITHUB_SHA"),
        "platform": platform.platform(), "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model_status": MODEL_STATUS, "first_stage_run": 39399674995,
        "strict_budget_font_units": float(LIMIT), "measurement_correction_applied": False,
        "original_font_acceptance": "NOT_ESTABLISHED", "original_faces_reconstructed": 0,
        "production_oracle_modified": False, "production_rebuilder_modified": False,
        "observations": [], "native_executions": [],
    }
    code = 1
    try:
        manifest = freeze_origin_predictions(build_suite(out/"fixtures"))
        manifest_path = out/"fixtures"/"manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        report["manifest_sha256_before_native"] = digest(manifest_path)
        report["fixture_count"] = len(manifest["entries"])
        report["planned_unique_observations"] = sum(len(e["requests"]) for e in manifest["entries"])
        if sys.platform != "darwin":
            report["reason"] = "CoreText unavailable; no native hypothesis was tested."
            code = 2 if args.require_native else 0
        else:
            source = Path(__file__).with_name("b1_metric_probe.swift")
            binary = args.binary.resolve() if args.binary else out/"b1_metric_probe"
            if args.binary is None:
                compiled = subprocess.run(["xcrun", "swiftc", "-O", str(source), "-o", str(binary)], capture_output=True, text=True, timeout=180)
                (out/"swift-compile.log").write_text(compiled.stdout+compiled.stderr, encoding="utf-8")
                require(compiled.returncode == 0, "native_compile_failed:"+compiled.stderr[-4000:])
            report["binary_sha256"], report["probe_source_sha256"] = digest(binary), digest(source)
            raw_dir = out/"raw"; raw_dir.mkdir()
            replay_total = 0
            for entry in manifest["entries"]:
                raw_reports = []
                for direction in ("forward", "reverse"):
                    ordered = entry["requests"] if direction == "forward" else list(reversed(entry["requests"]))
                    requests = [{k: r[k] for k in ("id", "axes", "point_size")} for r in ordered]
                    label = entry["fixture_id"]+"-"+direction
                    request_path, raw_path = raw_dir/(label+".requests.json"), raw_dir/(label+".json")
                    request_path.write_text(json.dumps(requests, indent=2, allow_nan=False)+"\n", encoding="utf-8")
                    process = subprocess.run([str(binary), "--font", str(out/"fixtures"/entry["path"]), "--requests", str(request_path), "--output", str(raw_path)], capture_output=True, text=True, timeout=120)
                    (raw_dir/(label+".log")).write_text(process.stdout+process.stderr, encoding="utf-8")
                    execution = {"label": label, "exit_code": process.returncode, "raw_file": str(raw_path.relative_to(out))}
                    report["native_executions"].append(execution)
                    if raw_path.exists(): execution["raw_sha256"] = digest(raw_path)
                    require(process.returncode == 0, "native_process_failed:"+label+":"+process.stderr[-2000:])
                    raw = load_native_json(raw_path.read_text())
                    execution.update(validate_raw(raw, entry, requests))
                    raw_reports.append(raw)
                replay_total += verify_replay(*raw_reports)
                by_id = {r["id"]: r for r in raw_reports[0]["observations"]}
                report["observations"].extend(observe_followup(entry, r, by_id[r["id"]]) for r in entry["requests"])
                print(json.dumps({"fixture": entry["fixture_id"], "exact_replay_pairs": len(by_id), "metric_acceptance_claimed": False}), flush=True)
            require(digest(manifest_path) == report["manifest_sha256_before_native"], "frozen_manifest_changed")
            rows = report["observations"]
            report.update(
                status="NATIVE_FOLLOWUP_COMPLETE_NOT_ACCEPTANCE", reverse_replay_pairs=replay_total,
                native_record_count=sum(e["records"] for e in report["native_executions"]),
                summary=followup_summary(rows), paired_table_effects=paired_table_effects(manifest, rows),
                height_candidate_failures=sum(not r["fresh_height_candidate"]["exact_match"] for r in rows),
                selected_origin_y_candidate_failures=sum(not r["fresh_origin_y_candidates"]["selected_prediction"]["exact_match"] for r in rows),
                strict_metric_failures=sum(not r["strict_metrics_pass"] for r in rows),
                witness_failures=sum(not r["witness_pass"] for r in rows),
                layout_vs_direct_disagreements=sum(not r["layout_step_equals_direct_height"] for r in rows),
            )
            # Competing origin candidates can be rejected without invalidating
            # completed measurements. Report their failures; never repair them.
            report["height_candidate_independent_validation"] = "REJECTED" if report["height_candidate_failures"] else "MATCHES_FINITE_FRESH_SAMPLES_ONLY"
            report["strict_synthetic_metric_acceptance"] = "FAIL" if report["strict_metric_failures"] else "PASS_FINITE_SYNTHETIC_CASES_ONLY"
            code = 0 if not (report["witness_failures"] or report["layout_vs_direct_disagreements"]) else 1
    except Exception as error:
        report.update(status="B1_FOLLOWUP_FAILED", error={"type": type(error).__name__, "message": str(error)})
    finally:
        (out/"followup-report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        compact = compact_report(report)
        (out/"followup-summary.json").write_text(json.dumps(compact, indent=2, allow_nan=False)+"\n", encoding="utf-8")
        print("B1_FOLLOWUP_SUMMARY_JSON="+json.dumps(compact, separators=(",", ":"), allow_nan=False), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
