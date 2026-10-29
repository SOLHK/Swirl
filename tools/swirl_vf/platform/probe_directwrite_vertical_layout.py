#!/usr/bin/env python3
"""Measure DirectWrite's actual layout of independent variable GPOS fixtures.

Only the authored geometric-symbol font from experiment_vertical_gpos is used.
Each of the four fonts is loaded in a separate native process/custom collection.
This is a diagnostic of feature routing and placement, not font acceptance.
The native executable must be compiled from directwrite_vertical_layout.cpp.
No user-font input, outline serialization, font installation or GUI is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import math
import os
from pathlib import Path
import platform
import struct
import subprocess
import tempfile
import time

import fontTools
from fontTools.ttLib import TTFont

from experiment_vertical_gpos import (
    AXES, POINTS, PROTECTED, ROUTES, add_adjustment, analytic_width,
    original_fixture, requested_location, table_adjustments,
)

SCHEMA = "swirl_directwrite_vertical_layout_v1"
POLICIES = ("default", "enabled", "disabled")
DIRECTIONS = ("H", "V")
LOCALES = ("zh-CN", "zh-HK")
TEXT_KINDS = ("mixed", "single_han")
METRIC_FIELDS = {"advance_width", "advance_height", "left_side_bearing", "right_side_bearing",
                 "top_side_bearing", "bottom_side_bearing", "vertical_origin_y"}


class ObservationError(ValueError):
    """A protocol, identity or completeness failure, with safe context only."""


def require(condition, message):
    if not condition:
        raise ObservationError(message)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def float32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def normalized_from_user(values):
    """Independent linear model, not an observed DWrite internal coordinate."""
    return tuple((values[tag] - default) / (default - minimum if values[tag] < default else maximum - default)
                 for tag, minimum, default, maximum in AXES)


def requests(points=POINTS):
    rows = []
    for route, policy, direction, locale, text_kind, (point_index, point) in itertools.product(
            ROUTES, POLICIES, DIRECTIONS, LOCALES, TEXT_KINDS, enumerate(points)):
        rows.append({"request_id": len(rows) + 1, "route": route, "policy": policy, "direction": direction,
                     "locale": locale, "text_kind": text_kind, "point_index": point_index,
                     "requested_normalized_model": list(point), "requested_user_axes": requested_location(point)})
    return rows


def request_line(row):
    return " ".join((str(row["request_id"]), row["direction"], row["locale"], row["route"], row["policy"],
                     *(format(row["requested_user_axes"][a[0]], ".17g") for a in AXES), row["text_kind"])) + "\n"


def exact_axes(actual, wanted, context):
    require(type(actual) is dict and all(type(k) is str and len(k) == 4 and number(v) for k, v in actual.items()),
            f"{context}:invalid_axis_record")
    require(all(tag in actual and actual[tag] == value for tag, value in wanted.items()),
            f"{context}:requested_axis_missing_ignored_or_clamped")


def validate_layout(record, request):
    context = f"request_{request['request_id']}"
    require(record.get("type") == "layout", f"{context}:not_a_layout_record")
    for field in ("request_id", "route", "policy", "direction", "locale", "text_kind", "requested_user_axes"):
        require(record.get(field) == request[field], f"{context}:request_echo_mismatch_{field}")
    desired = {tag: float32(value) for tag, value in request["requested_user_axes"].items()}
    require(record.get("float32_input_axes") == desired, f"{context}:wrong_float32_input")
    exact_axes(record.get("layout_reported_axes"), desired, context)
    expected_glyphs = 4 if request["text_kind"] == "mixed" else 1
    require(record.get("glyph_count") == expected_glyphs, f"{context}:incomplete_glyph_count")
    runs = record.get("runs")
    require(type(runs) is list and 0 < len(runs) <= expected_glyphs, f"{context}:missing_actual_layout_runs")
    covered = set()
    glyphs_seen = 0
    for run in runs:
        require(run.get("source_identity_verified") is True and run.get("physical_face_index") == 0
                and run.get("simulations") == 0, f"{context}:unverified_or_fallback_font")
        exact_axes(run.get("actual_face_axes"), desired, context + ":actual_face")
        require(run.get("bidi_level") == 0 and type(run.get("is_sideways")) is bool
                and run.get("orientation_angle") in (0, 1, 2, 3) and run.get("font_em_size") == 1000,
                f"{context}:unexpected_fixture_run_properties")
        for field, length in (("baseline", 2), ("orientation_transform", 6)):
            require(type(run.get(field)) is list and len(run[field]) == length and all(number(x) for x in run[field]),
                    f"{context}:invalid_{field}")
        for field in ("local_ink_bounds", "layout_ink_bounds", "baseline_relative_ink_bounds"):
            box = run.get(field)
            require(field in run and (box is None or type(box) is list and len(box) == 4
                    and all(number(x) for x in box) and box[0] <= box[2] and box[1] <= box[3]),
                    f"{context}:invalid_{field}")
        require(type(run.get("text_position")) is int and type(run.get("string_length")) is int
                and run["text_position"] >= 0 and run["string_length"] > 0
                and run["text_position"] + run["string_length"] <= expected_glyphs,
                f"{context}:invalid_text_range")
        indices = set(range(run["text_position"], run["text_position"] + run["string_length"]))
        require(not (covered & indices), f"{context}:duplicate_text_range")
        covered.update(indices)
        glyphs = run.get("glyphs")
        require(type(glyphs) is list and len(glyphs) == run["string_length"], f"{context}:fixture_glyph_count_changed")
        require(type(run.get("cluster_map")) is list and len(run["cluster_map"]) == run["string_length"]
                and set(run["cluster_map"]) == set(range(len(glyphs)))
                and all(type(i) is int for i in run["cluster_map"]), f"{context}:fixture_clusters_missing_or_duplicated")
        for glyph in glyphs:
            require(type(glyph.get("gid")) is int and 0 < glyph["gid"] < 8, f"{context}:missing_or_invalid_glyph")
            require(all(number(glyph.get(field)) for field in ("advance", "advance_offset", "ascender_offset")),
                    f"{context}:nonfinite_or_missing_placement")
            metrics = glyph.get("design_metrics")
            require(type(metrics) is dict and set(metrics) == METRIC_FIELDS and all(number(v) for v in metrics.values()),
                    f"{context}:incomplete_native_design_metrics")
        glyphs_seen += len(glyphs)
    require(covered == set(range(expected_glyphs)) and glyphs_seen == expected_glyphs, f"{context}:incomplete_actual_layout")
    metrics = record.get("layout_metrics")
    require(type(metrics) is dict and metrics.get("line_count") == 1
            and all(number(metrics.get(k)) for k in ("left", "top", "width", "width_including_trailing_whitespace", "height")),
            f"{context}:incomplete_layout_metrics")


def parse_transcript(stdout, expected_requests, source, returncode):
    def invalid_number(value):
        raise ObservationError("nonfinite_native_JSON:" + value)

    try:
        rows = [json.loads(line, parse_constant=invalid_number) for line in stdout.splitlines() if line.strip()]
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ObservationError("invalid_native_JSON") from exc
    require(all(type(row) is dict for row in rows), "native_nonobject_record")
    errors = [row for row in rows if row.get("type") == "request_error"]
    require(not errors, "native_request_error:" + json.dumps(errors, sort_keys=True))
    require(returncode == 0, f"native_nonzero_exit:{returncode}")
    require(len(rows) == len(expected_requests) + 2, "native_record_count_mismatch_or_extra_after_summary")
    metadata, summary = rows[0], rows[-1]
    sha = hashlib.sha256(source).hexdigest()
    require(metadata.get("type") == "metadata" and metadata.get("backend") == "DirectWrite_TextLayout4_TextRenderer1"
            and metadata.get("source_sha256") == sha and metadata.get("source_bytes") == len(source)
            and metadata.get("physical_face_count") == 1 and metadata.get("glyph_count") == 8
            and metadata.get("units_per_em") == metadata.get("font_em_size_DIP") == 1000
            and metadata.get("font_family") == "Swirl Original GPOS Laboratory"
            and all(metadata.get(k) is True for k in ("custom_collection_only", "empty_fallback", "pixel_snapping_disabled")),
            "native_metadata_or_fixture_identity_mismatch")
    require(type(metadata.get("Windows_version")) is dict
            and all(type(metadata["Windows_version"].get(k)) is int for k in ("major", "minor", "build", "product_type")),
            "native_Windows_version_not_observed")
    glyph_count = sum(4 if r["text_kind"] == "mixed" else 1 for r in expected_requests)
    require(summary.get("type") == "summary" and summary.get("status") == "ALL_REQUESTED_LAYOUT_OBSERVATIONS_COMPLETE"
            and summary.get("source_sha256") == sha and summary.get("request_count") == len(expected_requests)
            and summary.get("glyph_count") == glyph_count and summary.get("error_count") == 0
            and summary.get("font_file_locked_through_summary") is True, "native_terminal_summary_mismatch")
    for row, expected in zip(rows[1:-1], expected_requests):
        validate_layout(row, expected)
    return {"metadata": metadata, "summary": summary, "records": rows[1:-1]}


def flatten(record):
    """Order observed callback glyphs by source character, without reshaping."""
    result = {}
    for run in record["runs"]:
        for i, glyph_index in enumerate(run["cluster_map"]):
            result[run["text_position"] + i] = (run, run["glyphs"][glyph_index])
    return [result[i] for i in sorted(result)]


def stat(group, name, error, context):
    require(number(error), "nonfinite_derived_diagnostic")
    entry = group.setdefault(name, {"checks": 0, "max_abs_error": 0., "above_1_over_32": 0,
                                    "above_reconstruction_1_FUnit": 0, "worst": None})
    entry["checks"] += 1
    entry["above_1_over_32"] += abs(error) > 1 / 32
    entry["above_reconstruction_1_FUnit"] += abs(error) > 1.
    if entry["worst"] is None or abs(error) > entry["max_abs_error"]:
        entry["max_abs_error"] = abs(error)
        entry["worst"] = {**context, "signed_error": error}


def diagnostic(group, name, passed, context):
    entry = group.setdefault(name, {"checks": 0, "failures": 0, "first_failure": None})
    entry["checks"] += 1
    if not passed:
        entry["failures"] += 1
        if entry["first_failure"] is None:
            entry["first_failure"] = context


def compare_route(original, candidate, candidate_bytes, symbols, expected_requests, route):
    before = {r["request_id"]: r for r in original["records"]}
    after = {r["request_id"]: r for r in candidate["records"]}
    requested = {r["request_id"]: r for r in expected_requests if r["route"] == route}
    require(set(after) == set(requested) <= set(before), "comparison_requests_incomplete")
    default = {}
    for r in requested.values():
        if all(value == 0 for value in r["requested_normalized_model"]):
            default[(r["policy"], r["direction"], r["locale"], r["text_kind"])] = before[r["request_id"]]
    result = {"policies": {}, "contracts": {}, "paired_layout_calls": len(after) * 2,
              "paired_glyph_observations": 0, "float32_input_differs_from_requested_cases": 0,
              "internal_normalized_coordinates_observed": False,
              "coordinate_models": ["linear_normalization_of_actual_float32_face_axes",
                                    "nearest_F2DOT14_hypothesis_not_native_readback"]}
    encoded_cache = {}
    for request_id, a in after.items():
        b = before[request_id]; request = requested[request_id]
        context = {k: request[k] for k in ("request_id", "route", "policy", "direction", "locale", "text_kind", "point_index")}
        context["requested_user_axes"] = request["requested_user_axes"]
        context["float32_input_axes"] = a["float32_input_axes"]
        result["float32_input_differs_from_requested_cases"] += a["float32_input_axes"] != request["requested_user_axes"]
        normalized = normalized_from_user(a["float32_input_axes"])
        quantized = tuple(math.floor(v * 16384 + .5) / 16384 for v in normalized)
        if normalized not in encoded_cache:
            encoded_cache[normalized] = table_adjustments(candidate_bytes, symbols, normalized)
        if quantized not in encoded_cache:
            encoded_cache[quantized] = table_adjustments(candidate_bytes, symbols, quantized)
        encoded, encoded_quantized = encoded_cache[normalized], encoded_cache[quantized]
        group = result["policies"].setdefault(request["policy"], {}).setdefault(request["direction"], {})
        b_glyphs, a_glyphs = flatten(b), flatten(a)
        require(len(b_glyphs) == len(a_glyphs), f"request_{request_id}:GPOS_changed_glyph_count")
        diagnostic(result["contracts"], "GPOS_preserves_GSUB_and_clusters",
                   [g[1]["gid"] for g in b_glyphs] == [g[1]["gid"] for g in a_glyphs], context)
        actual_gids = [g[1]["gid"] for g in a_glyphs]
        regional = (3, 5) if request["locale"] == "zh-HK" else (2, 4)
        diagnostic(result["contracts"], "regional_GSUB_and_remaining_characters",
                   actual_gids[0] in regional and actual_gids[1:] == ([1, 6, 7] if request["text_kind"] == "mixed" else []),
                   {**context, "actual_gids": actual_gids})
        if request["policy"] == "default":
            expected_han = regional[request["direction"] == "V"]
            diagnostic(result["contracts"], "default_regional_and_vertical_GSUB",
                       actual_gids[0] == expected_han, {**context, "actual_gids": actual_gids})
        if request["policy"] == "default" and request["direction"] == "H":
            diagnostic(result["contracts"], "default_horizontal_layout_unchanged", a == b, context)
        if request["policy"] == "disabled":
            diagnostic(result["contracts"], "disabled_GPOS_layout_unchanged", a == b, context)
        for (br, bg), (ar, ag) in zip(b_glyphs, a_glyphs):
            gid = ag["gid"]; symbol = symbols[gid]
            glyph_context = {**context, "gid": gid, "glyph": symbol.name,
                "source_continuous_AW_at_requested": analytic_width(symbol, request["requested_normalized_model"]),
                "source_continuous_AW_at_float32_axis_model": analytic_width(symbol, normalized),
                "native_design_AW": ag["design_metrics"]["advance_width"], "native_layout_advance": ag["advance"],
                "encoded_GPOS_XPlacement_at_float32_axis_model": encoded[symbol.name],
                "encoded_GPOS_XPlacement_at_F2DOT14_hypothesis": encoded_quantized[symbol.name],
                "orientation_angle": ar["orientation_angle"], "is_sideways": ar["is_sideways"]}
            require(ar["actual_face_axes"] == br["actual_face_axes"], f"request_{request_id}:GPOS_changed_actual_axis_instance")
            diagnostic(result["contracts"], "GPOS_preserves_native_design_metrics",
                       ag["design_metrics"] == bg["design_metrics"], glyph_context)
            stat(group, "native_design_AW_minus_continuous_float32_model",
                 ag["design_metrics"]["advance_width"] - analytic_width(symbol, normalized), glyph_context)
            for field in ("advance", "advance_offset", "ascender_offset"):
                stat(group, "observed_" + field + "_change_from_source", ag[field] - bg[field], glyph_context)
            diagnostic(result["contracts"], "GPOS_preserves_layout_advances", ag["advance"] == bg["advance"], glyph_context)
            result["paired_glyph_observations"] += 2
        if request["text_kind"] == "single_han":
            require(len(a["runs"]) == len(b["runs"]) == 1, "single_han_fragmented_into_multiple_runs")
            a_box, b_box = a["runs"][0]["baseline_relative_ink_bounds"], b["runs"][0]["baseline_relative_ink_bounds"]
            require(a_box is not None and b_box is not None, "single_han_has_no_ink")
            gid = a_glyphs[0][1]["gid"]; encoded_x = encoded[symbols[gid].name]
            shift_context = {**context, "gid": gid, "before_baseline_relative_ink_bounds": b_box,
                             "after_baseline_relative_ink_bounds": a_box,
                             "encoded_GPOS_XPlacement_at_float32_axis_model": encoded_x}
            shift = a_box[0] - b_box[0]
            stat(group, "single_han_actual_layout_X_shift", shift, shift_context)
            stat(group, "single_han_actual_layout_X_shift_minus_encoded_GPOS", shift - encoded_x, shift_context)
            stat(group, "single_han_actual_layout_Y_shift", a_box[1] - b_box[1], shift_context)
            stat(group, "single_han_ink_width_change", (a_box[2] - a_box[0]) - (b_box[2] - b_box[0]), shift_context)
            stat(group, "single_han_ink_height_change", (a_box[3] - a_box[1]) - (b_box[3] - b_box[1]), shift_context)
            key = (request["policy"], request["direction"], request["locale"], request["text_kind"])
            require(key in default, "missing_independent_default_layout_reference")
            default_record = default[key]
            require(flatten(default_record)[0][1]["gid"] == gid, "source_default_and_variation_changed_fixture_GSUB")
            default_box = default_record["runs"][0]["baseline_relative_ink_bounds"]
            if request["direction"] == "V":
                stat(group, "single_han_source_variable_X_drift_from_source_default", b_box[0] - default_box[0], shift_context)
                stat(group, "single_han_fixed_origin_X_error_from_source_default", a_box[0] - default_box[0], shift_context)
    # Report the default behavior of every route, including ignored routes. The
    # original reconstruction budget and the stricter algorithm budget remain
    # separate; choosing an explicit feature cannot certify default application.
    vertical = result["policies"]["default"]["V"]["single_han_fixed_origin_X_error_from_source_default"]
    horizontal = result["contracts"]["default_horizontal_layout_unchanged"]
    native_advances_match = all(group["native_design_AW_minus_continuous_float32_model"]["above_reconstruction_1_FUnit"] == 0
                               for group in result["policies"]["default"].values())
    contracts_match = all(contract["failures"] == 0 for contract in result["contracts"].values())
    result["native_default_layout_advance_model_within_reconstruction_1_FUnit"] = native_advances_match
    # A constant, ignored axis can also produce constant bounds. Such a result
    # cannot pass this scoped conclusion merely because a face reports the tag.
    eligible = native_advances_match and contracts_match and horizontal["failures"] == 0
    result["default_single_han_compensation_within_1_over_32"] = eligible and vertical["above_1_over_32"] == 0
    result["default_single_han_compensation_within_reconstruction_1_FUnit"] = eligible and vertical["above_reconstruction_1_FUnit"] == 0
    result["default_mixed_text_fixed_origin_acceptance"] = "NOT_ESTABLISHED_BY_SINGLE_GLYPH_BOUNDS"
    return result


def run(binary, output, require_native=False):
    output = Path(output).resolve()
    require(not output.exists(), "new_report_path_required")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"schema": SCHEMA, "status": "NOT_RUN", "source_commit": os.environ.get("GITHUB_SHA"),
        "data_origin": "independent_geometric_symbols_no_Apple_font_input", "font_binary_published": False,
        "fonttools_version": fontTools.__version__, "host_platform": platform.platform(),
        "windows_11_acceptance": "NOT_RUN", "Qt_acceptance": "NOT_RUN", "original_font_acceptance": "NOT_RUN",
        "rasterization_and_DPI_acceptance": "NOT_RUN", "font_installation": "NOT_RUN",
        "exact_algorithm_limit_FUnit": 1 / 32, "existing_reconstruction_limit_FUnit": 1.,
        "measurement": "actual_IDWriteTextLayout4_Draw_and_TextRenderer1_callbacks",
        "bounds": "D2D_PathGeometry_curve_bounds_of_complete_actual_callback_run_with_official_orientation_transform",
        "units": "DIP_at_fontEmSize_1000_and_UPM_1000_no_pixel_snapping",
        "coordinate_caveat": "requested_Double_and_actual_Float32_axis_readback_are_recorded; internal_normalization_is_not_observed",
        "feature_routes": {}, "native_observations": {}}
    succeeded = False
    try:
        if os.name != "nt":
            report["reason"] = "Windows_DirectWrite_runtime_unavailable"
            require(not require_native, report["reason"])
            return report
        binary = Path(binary).resolve()
        require(binary.is_file(), "native_layout_binary_missing")
        report["native_binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
        report["driver_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        all_requests = requests()
        original, symbols = original_fixture("even")
        variants = {"original": original}
        protected = TTFont(io.BytesIO(original))
        for route in ROUTES:
            candidate, errors = add_adjustment(original, symbols, route)
            require(not errors, "unexpected_fractional_even_fixture_encoding")
            font = TTFont(io.BytesIO(candidate))
            require(all(font.getTableData(t) == protected.getTableData(t) for t in PROTECTED),
                    "GPOS_changed_source_outline_mapping_or_metric_table")
            variants[route] = candidate
        report["locations"] = len(POINTS)
        report["axes"] = [a[0] for a in AXES]
        report["expected_layout_calls"] = len(all_requests) * 2
        report["expected_glyph_observations"] = sum(4 if r["text_kind"] == "mixed" else 1 for r in all_requests) * 2
        with tempfile.TemporaryDirectory(prefix="swirl-original-dwrite-layout-") as temporary:
            for variant, data in variants.items():
                selected = all_requests if variant == "original" else [r for r in all_requests if r["route"] == variant]
                font_path = Path(temporary) / (variant + ".ttf")
                font_path.write_bytes(data)
                started = time.monotonic()
                completed = subprocess.run([str(binary), str(font_path)], input="".join(request_line(r) for r in selected),
                    text=True, encoding="utf-8", capture_output=True, timeout=600, check=False)
                # communicate() has consumed EOF and waited for exit; a terminal
                # summary is accepted only after the process and source checks.
                require(font_path.read_bytes() == data, "fixture_changed_during_native_layout")
                require(not completed.stderr.strip(), "unexpected_native_stderr")
                observed = parse_transcript(completed.stdout, selected, data, completed.returncode)
                observed["elapsed_seconds"] = time.monotonic() - started
                report["native_observations"][variant] = observed
        for route in ROUTES:
            report["feature_routes"][route] = compare_route(report["native_observations"]["original"],
                report["native_observations"][route], variants[route], symbols, all_requests, route)
        report["actual_layout_calls"] = sum(v["summary"]["request_count"] for v in report["native_observations"].values())
        report["actual_glyph_observations"] = sum(v["summary"]["glyph_count"] for v in report["native_observations"].values())
        require(report["actual_layout_calls"] == report["expected_layout_calls"]
                and report["actual_glyph_observations"] == report["expected_glyph_observations"], "experiment_count_mismatch")
        report["status"] = "ALL_DECLARED_LAYOUT_OBSERVATIONS_COMPLETE_NOT_FONT_ACCEPTANCE"
        succeeded = True
        return report
    except Exception as exc:
        report["status"] = "FAIL_PROTOCOL_OR_LAYOUT_IDENTITY"
        report["error_type"] = type(exc).__name__
        # Known ObservationErrors contain only declared IDs, fields and native
        # safe errors. Other exceptions can contain temporary host paths.
        report["error"] = str(exc) if isinstance(exc, ObservationError) else "native_layout_experiment_interrupted"
        raise
    finally:
        report["completed_layout_calls"] = sum(v["summary"]["request_count"] for v in report["native_observations"].values())
        report["all_declared_observations_complete"] = succeeded
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args.binary, args.output, args.require_native)
    except Exception:
        print(json.dumps({"status": "FAIL", "safe_report_written": args.output.is_file()}))
        return 1
    print(json.dumps({"status": result["status"], "actual_layout_calls": result.get("actual_layout_calls", 0),
                      "actual_glyph_observations": result.get("actual_glyph_observations", 0),
                      "windows_11_acceptance": "NOT_RUN", "Qt_acceptance": "NOT_RUN"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
