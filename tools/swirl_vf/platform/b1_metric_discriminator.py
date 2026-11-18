#!/usr/bin/env python3
"""B1 native four-channel experiment, with exact raw-number provenance.

The fixture manifest freezes every case and prediction before the first native
process. Strict metric failures remain failures in the report; completion of a
diagnostic is not native equivalence or permission to build an original font.
"""
from __future__ import annotations

import argparse
import datetime
from fractions import Fraction
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

from b1_metric_fixture import build_suite, rational

LIMIT = Fraction(1, 32)
RAW_STATUS = "NATIVE_DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value):
    if isinstance(value, Fraction):
        return value
    require(type(value) in (int, float) and math.isfinite(value), "finite_native_number_required")
    return Fraction(value)


def at_json_path(root, path):
    require(path.startswith("$"), "invalid_binary64_json_path")
    tail = path[1:]
    cursor = root
    while tail:
        match = re.match(r"(?:\.([^.[\]]+)|\[(\d+)\])", tail)
        require(match is not None, "invalid_binary64_json_path")
        cursor = cursor[match.group(1)] if match.group(1) is not None else cursor[int(match.group(2))]
        tail = tail[match.end():]
    return cursor


def verify_bits(report):
    bits = report.get("binary64_hex_by_json_path")
    require(type(bits) is dict and bool(bits), "native_binary64_map_missing")
    for path, expected in bits.items():
        value = at_json_path(report, path)
        number(value)
        require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{16}", expected), "bad_native_binary64_bits")
        require(struct.pack(">d", float(value)).hex() == expected, "native_decimal_did_not_roundtrip_to_binary64")
    for index, row in enumerate(report.get("observations", [])):
        for suffix in (".point_size", ".direct_advances.vertical_vector[0]",
                       ".direct_advances.vertical_vector[1]", ".direct_advances.vertical_sum",
                       ".direct_advances.horizontal_vector[0]", ".vertical_translation.raw_vector[0]",
                       ".vertical_translation.raw_vector[1]", ".witness_path.geometric_bounds_xywh[3]"):
            require(f"$.observations[{index}]{suffix}" in bits, "required_raw_scalar_bits_missing")
        # JSON spells integral Doubles without a decimal point. Require bit
        # provenance for every numeric observation, not only values Python
        # happened to parse as float. Only declared integer metadata is exempt.
        integer_fields = {"upem", "glyph_count", "nominal_glyph_id", "count", "numerator_upem",
                          "graphics_upem", "advance_int32", "kern_attribute", "index", "line",
                          "run", "glyph_id", "string_index", "status_flags"}
        def complete(value, path):
            if type(value) is dict:
                for key, child in value.items():
                    if key in integer_fields and type(child) is int:
                        continue
                    if key in ("codepoints", "visible_utf16_range"):
                        require(type(child) is list and all(type(n) is int for n in child), "invalid_integer_layout_metadata")
                        continue
                    complete(child, path + "." + key)
            elif type(value) is list:
                for child_index, child in enumerate(value):
                    complete(child, f"{path}[{child_index}]")
            elif type(value) in (int, float):
                number(value)
                require(path in bits, "required_raw_scalar_bits_missing:" + path)
        complete(row, f"$.observations[{index}]")
    return len(bits)


def load_native_json(text):
    # JSONEncoder may spell Double(-0.0) as -0. Retain that sign instead of
    # letting Python's integer parser erase it before checking native bits.
    return json.loads(text, parse_int=lambda token: -0.0 if token == "-0" else int(token))


def validate_raw(report, entry, requests):
    require(report.get("status") == RAW_STATUS, "native_diagnostic_incomplete")
    require(report.get("backend") == "CoreText_B1_independent_diagnostic_only", "native_backend_mismatch")
    require(report.get("source_unchanged_after_measurement") is True, "native_source_not_reverified")
    source = report.get("source", {})
    require(source.get("sha256") == entry["sha256"] and source.get("upem") == entry["upem"]
            and source.get("glyph_count") == 3 and source.get("table_sha256") == entry["table_sha256"],
            "native_source_identity_mismatch")
    expected = {r["id"]: r for r in requests}
    rows = report.get("observations", [])
    require(len(expected) == len(requests) == len(rows) == report.get("completed_request_count")
            == report.get("expected_request_count"), "native_record_count_mismatch")
    seen = set()
    for row in rows:
        key = row.get("id")
        require(key in expected and key not in seen and row.get("status") == "COMPLETE", "native_duplicate_or_missing_request")
        seen.add(key)
        request = expected[key]
        require(row["requested_axes"] == request["axes"] and row["point_size"] == request["point_size"]
                and row["upem"] == entry["upem"] and row["nominal_glyph_id"] == 2, "native_request_identity_mismatch")
        identity = row["font_identity"]
        require(identity.get("all_source_tables_verified") is True and identity.get("axes_size_and_matrix_verified") is True
                and identity.get("verified_table_sha256") == entry["table_sha256"], "native_instance_identity_mismatch")
        layout = row["vertical_layout"]
        require(layout.get("both_nominal_glyphs_and_all_source_tables_verified") is True
                and len(layout["glyphs"]) == 2 and len(layout["runs"]) == 1
                and sorted(g["string_index"] for g in layout["glyphs"]) == [0, 1]
                and all(g["glyph_id"] == 2 for g in layout["glyphs"]), "native_layout_identity_mismatch")
        for run in layout["runs"]:
            require(run["font_identity"]["verified_table_sha256"] == entry["table_sha256"], "native_layout_font_fallback")
    return {"records": len(rows), "binary64_values_verified": verify_bits(report)}


def replay_signature(report):
    signatures = {}
    for index, row in enumerate(report["observations"]):
        prefix = f"$.observations[{index}]"
        bits = {path[len(prefix):]: value for path, value in report["binary64_hex_by_json_path"].items()
                if path.startswith(prefix + ".")}
        signatures[row["id"]] = {"row": row, "bits": bits}
    return signatures


def verify_replay(forward, reverse):
    a, b = replay_signature(forward), replay_signature(reverse)
    require(len(a) == len(forward["observations"]) and len(b) == len(reverse["observations"]), "native_replay_duplicate_id")
    require(set(a) == set(b), "native_replay_id_set_mismatch")
    differences = [key for key in a if a[key] != b[key]]
    require(not differences, "native_reverse_process_replay_changed:" + ",".join(differences[:3]))
    return len(a)


def measured(value, upem, point_size):
    raw = number(value)
    denominator = number(point_size)
    require(denominator > 0 and type(upem) is int and upem > 0, "invalid_unit_basis")
    design = raw * upem / denominator
    return {"raw_points": value, "raw_binary64_hex": struct.pack(">d", float(value)).hex(),
            "raw_exact": rational(raw), "conversion": {"numerator_upem": upem,
                "denominator_point_size_exact": rational(denominator), "expression": "raw_exact * UPEM / point_size_exact"},
            "design_units_exact": rational(design), "design_units": float(design),
            "rounding_applied": False}


def compare(value, expected):
    error = number(value) - number(expected)
    return {"expected_design_units": float(expected), "signed_error_exact": rational(error),
            "signed_error_design_units": float(error), "within_unchanged_1_over_32": abs(error) <= LIMIT}


def design_fraction(quantity):
    exact = quantity["design_units_exact"]
    return Fraction(exact["numerator"], exact["denominator"])


def observe(entry, request, row):
    upem, point_size = row["upem"], row["point_size"]
    raw = row["direct_advances"]
    translation = row["vertical_translation"]["raw_vector"]
    fields = {"advance_width": raw["horizontal_vector"][0], "advance_height": raw["vertical_vector"][0],
              "vertical_translation_x": translation[0], "vertical_translation_y": translation[1],
              "vertical_advance_sum": raw["vertical_sum"]}
    quantities = {key: measured(value, upem, point_size) for key, value in fields.items()}
    exact_values = {key: design_fraction(record) for key, record in quantities.items()}
    exact_values.update(vertical_origin_x=-exact_values["vertical_translation_x"], vertical_origin_y=-exact_values["vertical_translation_y"])
    values = {key: float(value) for key, value in exact_values.items()}
    expected = request["expected"]
    errors = {key: compare(exact_values[key], expected[key]) for key in ("advance_width", "advance_height", "vertical_origin_y")}
    errors["vertical_origin_x_current_half_width"] = compare(exact_values["vertical_origin_x"], expected["vertical_origin_x_current_half_width"])
    witness = [measured(v, upem, point_size) for v in row["witness_path"]["geometric_bounds_xywh"]]
    witness_errors = [compare(design_fraction(v), ideal) for v, ideal in zip(witness, expected["witness_bounds"])]
    glyphs = sorted(row["vertical_layout"]["glyphs"], key=lambda g: g["string_index"])
    require(glyphs[0]["line"] == glyphs[1]["line"] and glyphs[0]["run"] == glyphs[1]["run"], "layout_gap_crosses_run")
    scale = Fraction(upem) / number(point_size)
    gap = [(number(glyphs[1]["position"][i]) - number(glyphs[0]["position"][i])) * scale for i in (0, 1)]
    require(gap[0] == 0 or gap[1] == 0, "layout_gap_not_axis_aligned_keep_raw_for_review")
    gap_length = abs(gap[0]) + abs(gap[1])
    hypotheses = request["hypotheses"]
    predicted = {"ideal_continuous_height": expected["advance_height"],
                 "round_height_once": hypotheses["round_height_once"],
                 "round_each_phantom": hypotheses["round_each_phantom"],
                 "difference_first_em16_then_trunc": hypotheses["difference_first"]["prediction"],
                 "coordinate_first_em16_then_trunc": hypotheses["coordinate_first"]["prediction"]}
    formula = {name: {"prediction": prediction, "exact_match": exact_values["advance_height"] == number(prediction),
                       "error": float(exact_values["advance_height"] - number(prediction))} for name, prediction in predicted.items()}
    return {"fixture_id": entry["fixture_id"], "variant": entry["variant"], "upem": entry["upem"],
            "request_id": request["id"], "partition": request["partition"], "axes": request["axes"],
            "phantom_shift": entry["phantom_shift"], "quantities": quantities, "measured_design_units": values,
            "strict_metric_comparisons": errors,
            "strict_metrics_pass": all(c["within_unchanged_1_over_32"] for c in errors.values()),
            "witness_bounds": witness, "witness_comparisons": witness_errors,
            "witness_pass": all(c["within_unchanged_1_over_32"] for c in witness_errors),
            "layout_position_delta_design_units_exact": [rational(v) for v in gap],
            "layout_step_design_units": float(gap_length), "layout_step_vs_continuous_height": compare(gap_length, expected["advance_height"]),
            "layout_step_equals_direct_height": gap_length == exact_values["advance_height"],
            "global_font_metrics_points": row["global_font_metrics"],
            "cgfont_horizontal_auxiliary": row["cgfont_horizontal_auxiliary"],
            "predeclared_height_hypotheses": formula,
            "origin_x_vs_current_half_width": float(exact_values["vertical_origin_x"] - exact_values["advance_width"] / 2),
            "origin_x_vs_default_half_width": float(exact_values["vertical_origin_x"] - number(expected["vertical_origin_x_default_half_width"]))}


def summarize(observations):
    grouped = {}
    for row in observations:
        key = row["fixture_id"]
        group = grouped.setdefault(key, {"records": 0, "strict_metric_failures": 0, "witness_failures": 0,
                "layout_vs_direct_disagreements": 0, "max_metric_error": {}, "partitions": {}, "hypotheses": {}})
        group["records"] += 1
        group["strict_metric_failures"] += not row["strict_metrics_pass"]
        group["witness_failures"] += not row["witness_pass"]
        group["layout_vs_direct_disagreements"] += not row["layout_step_equals_direct_height"]
        partition = group["partitions"].setdefault(row["partition"], {"records": 0, "strict_metric_failures": 0})
        partition["records"] += 1
        partition["strict_metric_failures"] += not row["strict_metrics_pass"]
        for field, c in row["strict_metric_comparisons"].items():
            group["max_metric_error"][field] = max(group["max_metric_error"].get(field, 0), abs(c["signed_error_design_units"]))
        for name, prediction in row["predeclared_height_hypotheses"].items():
            counts = group["hypotheses"].setdefault(name, {"training_matches": 0, "holdout_matches": 0})
            counts[row["partition"] + "_matches"] += prediction["exact_match"]
    return grouped


def table_effects(observations):
    lookup = {(r["upem"], r["variant"], r["request_id"]): r for r in observations}
    effects = {}
    for row in observations:
        if row["variant"] == "gvar":
            continue
        base_variant = "os2_typo_ascent" if row["variant"] == "os2_typo_ascent_use_typo" else "gvar"
        base = lookup[(row["upem"], base_variant, row["request_id"])]
        stats = effects.setdefault(row["fixture_id"], {"compared_with": f"upem{row['upem']}-{base_variant}", "records": 0,
                    "changed_fields": {}, "max_absolute_difference": {}})
        stats["records"] += 1
        fields = {**row["measured_design_units"], "layout_step": row["layout_step_design_units"]}
        base_fields = {**base["measured_design_units"], "layout_step": base["layout_step_design_units"]}
        for name in ("ascent", "descent", "leading"):
            fields["global_" + name] = row["global_font_metrics_points"][name]
            base_fields["global_" + name] = base["global_font_metrics_points"][name]
        for name, value in fields.items():
            delta = value - base_fields[name]
            stats["changed_fields"][name] = stats["changed_fields"].get(name, 0) + (delta != 0)
            stats["max_absolute_difference"][name] = max(stats["max_absolute_difference"].get(name, 0), abs(delta))
    return effects


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve()
    require(not out.exists(), "new_output_directory_required")
    out.mkdir(parents=True)
    report = {"schema_version": 1, "status": "NOT_RUN", "source_commit": os.environ.get("GITHUB_SHA"),
              "platform": platform.platform(), "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "synthetic_only": True, "original_font_acceptance": "NOT_ESTABLISHED", "diagnosis_is_not_acceptance": True,
              "measurement_correction_applied": False, "strict_budget_font_units": float(LIMIT),
              "production_oracle_modified": False, "production_rebuilder_modified": False,
              "native_executions": [], "observations": []}
    code = 1
    try:
        manifest = build_suite(out / "fixtures")
        report["manifest_sha256_before_native"] = digest(out / "fixtures" / "manifest.json")
        report["fixture_count"] = len(manifest["entries"])
        report["planned_unique_observations"] = sum(len(e["requests"]) for e in manifest["entries"])
        if sys.platform != "darwin":
            report["reason"] = "CoreText unavailable; fixture creation alone is not native execution."
            code = 2 if args.require_native else 0
        else:
            source = Path(__file__).with_name("b1_metric_probe.swift")
            binary = args.binary.resolve() if args.binary else out / "b1_metric_probe"
            if args.binary is None:
                result = subprocess.run(["xcrun", "swiftc", "-O", str(source), "-o", str(binary)], capture_output=True, text=True, timeout=180)
                (out / "swift-compile.log").write_text(result.stdout + result.stderr, encoding="utf-8")
                require(result.returncode == 0, "native_compile_failed:" + result.stderr[-4000:])
            report["binary_sha256"] = digest(binary)
            report["probe_source_sha256"] = digest(source)
            raw_dir = out / "raw"; raw_dir.mkdir()
            replay_total = 0
            for entry in manifest["entries"]:
                raw_reports = []
                font = out / "fixtures" / entry["path"]
                for direction in ("forward", "reverse"):
                    ordered = entry["requests"] if direction == "forward" else list(reversed(entry["requests"]))
                    requests = [{k: r[k] for k in ("id", "axes", "point_size")} for r in ordered]
                    label = entry["fixture_id"] + "-" + direction
                    request_path, raw_path = raw_dir / (label + ".requests.json"), raw_dir / (label + ".json")
                    request_path.write_text(json.dumps(requests, indent=2, allow_nan=False) + "\n", encoding="utf-8")
                    native = subprocess.run([str(binary), "--font", str(font), "--requests", str(request_path), "--output", str(raw_path)],
                                            capture_output=True, text=True, timeout=120)
                    (raw_dir / (label + ".log")).write_text(native.stdout + native.stderr, encoding="utf-8")
                    execution = {"label": label, "exit_code": native.returncode, "raw_file": str(raw_path.relative_to(out))}
                    report["native_executions"].append(execution)
                    if raw_path.exists():
                        execution["raw_sha256"] = digest(raw_path)
                    require(native.returncode == 0, "native_process_failed:" + label + ":" + native.stderr[-2000:])
                    raw_report = load_native_json(raw_path.read_text())
                    execution.update(validate_raw(raw_report, entry, requests))
                    raw_reports.append(raw_report)
                replay_total += verify_replay(*raw_reports)
                by_id = {r["id"]: r for r in raw_reports[0]["observations"]}
                for request in entry["requests"]:
                    report["observations"].append(observe(entry, request, by_id[request["id"]]))
                print(json.dumps({"fixture": entry["fixture_id"], "reverse_replay_pairs": len(by_id),
                                  "measurements_complete_not_acceptance": True}), flush=True)
            require(digest(out / "fixtures" / "manifest.json") == report["manifest_sha256_before_native"], "preregistered_manifest_changed")
            report.update(status=RAW_STATUS, reverse_replay_pairs=replay_total,
                          native_record_count=sum(e["records"] for e in report["native_executions"]),
                          summary=summarize(report["observations"]), table_effects=table_effects(report["observations"]))
            report["strict_metric_failures"] = sum(not row["strict_metrics_pass"] for row in report["observations"])
            report["strict_synthetic_metric_acceptance"] = "FAIL" if report["strict_metric_failures"] else "PASS_FINITE_SYNTHETIC_CASES_ONLY"
            code = 0
    except Exception as error:
        report.update(status="B1_DISCRIMINATOR_FAILED", error={"type": type(error).__name__, "message": str(error)})
    finally:
        (out / "b1-report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        # Synthetic coordinates are public originals. The compact report allows
        # independent audit even if an artifact download is unavailable.
        compact = {k: v for k, v in report.items() if k not in ("observations", "native_executions")}
        compact["anchor_observations"] = [{"fixture": r["fixture_id"], "axes": r["axes"],
            "partition": r["partition"], "raw_height": r["quantities"]["advance_height"]["raw_points"],
            "raw_bits": r["quantities"]["advance_height"]["raw_binary64_hex"],
            "witness_height": r["witness_bounds"][3]["design_units"], "layout_step": r["layout_step_design_units"],
            "vertical_origin_x": r["measured_design_units"]["vertical_origin_x"],
            "vertical_origin_y": r["measured_design_units"]["vertical_origin_y"]}
            for r in report["observations"] if r["axes"]["WDTH"] == 0]
        (out / "b1-summary.json").write_text(json.dumps(compact, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print("B1_SUMMARY_JSON=" + json.dumps(compact, separators=(",", ":"), allow_nan=False), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
