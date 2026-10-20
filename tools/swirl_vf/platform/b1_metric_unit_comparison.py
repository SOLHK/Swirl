"""Exact axis-unit comparison against a rejected, partial native baseline.

This module never upgrades that baseline to an accepted or replayed report.
Only the four declared channels are compared; no correction or tolerance is used.
"""
from __future__ import annotations

from fractions import Fraction
import re
import struct

from b1_metric_discriminator import at_json_path, number, require, validate_raw
from b1_metric_fixture import rational


CHANNELS = ("direct_advances", "vertical_translation", "witness_path", "vertical_layout")
INTEGER_FIELDS = {"upem", "glyph_count", "nominal_glyph_id", "count", "numerator_upem",
                  "graphics_upem", "advance_int32", "kern_attribute", "index", "line",
                  "run", "glyph_id", "string_index", "status_flags"}


def normalized_axes(request):
    axes = request.get("normalized_design_axes", request["axes"])
    require(axes == request["axes"] and set(axes) == {"WDTH", "HGHT"}, "normalized_manifest_axes_mismatch")
    require(all(-1 <= number(value) <= 1 for value in axes.values()), "normalized_axis_out_of_range")
    return axes


def wire_requests(entry, unit_scale):
    result, seen = [], set()
    for request in entry["requests"]:
        key = request["id"]
        require(type(key) is str and key not in seen, "duplicate_manifest_request_id")
        seen.add(key)
        axes = normalized_axes(request)
        native = request.get("native_user_axes", request["axes"])
        require(set(native) == {"WDTH", "HGHT"}
                and number(native["WDTH"]) == number(axes["WDTH"])
                and number(native["HGHT"]) == number(axes["HGHT"]) * unit_scale,
                "native_user_axis_unit_basis_mismatch")
        result.append(dict(request, axes=native))
    return result


def verify_source(report, entry, scale):
    source = report.get("source", {})
    require(source.get("sha256") == entry["sha256"] and source.get("upem") == entry["upem"]
            and source.get("glyph_count") == 3 and source.get("table_sha256") == entry["table_sha256"],
            "native_source_identity_mismatch")
    axes = source.get("axes")
    require(type(axes) is list and len(axes) == 2, "native_source_axis_domains_missing")
    indexed = {axis["tag"]: axis for axis in axes}
    require(set(indexed) == {"WDTH", "HGHT"}, "native_source_axis_domains_mismatch")
    for tag, extent in (("WDTH", 1), ("HGHT", scale)):
        axis = indexed[tag]
        require(number(axis["minimum"]) == -extent and number(axis["maximum"]) == extent
                and number(axis["default"]) == 0, "native_source_axis_domains_mismatch")


def verify_partial_bits(report):
    """Check the original paths, without deleting FAILED rows or renumbering."""
    bits = report.get("binary64_hex_by_json_path")
    require(type(bits) is dict and bool(bits), "native_binary64_map_missing")
    for path, expected in bits.items():
        require(type(path) is str and type(expected) is str and re.fullmatch(r"[0-9a-f]{16}", expected),
                "bad_native_binary64_bits")
        try:
            value = at_json_path(report, path)
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("binary64_path_without_native_value") from error
        number(value)
        require(struct.pack(">d", float(value)).hex() == expected, "native_decimal_did_not_roundtrip_to_binary64")

    def walk(value, path):
        if type(value) is dict:
            for key, child in value.items():
                if key in INTEGER_FIELDS and type(child) is int:
                    continue
                if key in ("codepoints", "visible_utf16_range"):
                    require(type(child) is list and all(type(item) is int for item in child), "invalid_integer_layout_metadata")
                    continue
                walk(child, path + "." + key)
        elif type(value) is list:
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")
        elif type(value) in (int, float):
            number(value)
            require(path in bits, "required_raw_scalar_bits_missing:" + path)

    for index, row in enumerate(report["observations"]):
        walk(row, f"$.observations[{index}]")
    return len(bits)


def validate_partial_baseline(report, entry):
    require(report.get("status") == "NATIVE_DIAGNOSTIC_FAILED", "baseline_must_remain_failed_partial_report")
    require(report.get("backend") == "CoreText_B1_independent_diagnostic_only", "native_backend_mismatch")
    verify_source(report, entry, 1)
    requests = wire_requests(entry, 1)
    expected = {request["id"]: request for request in requests}
    rows = report.get("observations")
    require(type(rows) is list and len(rows) == len(expected) == report.get("expected_request_count"),
            "partial_baseline_record_count_mismatch")
    seen, complete, failed = set(), 0, 0
    for row in rows:
        key = row.get("id")
        require(key in expected and key not in seen, "baseline_duplicate_or_extra_request")
        seen.add(key)
        require(row.get("status") in ("COMPLETE", "FAILED"), "baseline_unknown_record_status")
        request = expected[key]
        require(row.get("requested_axes") == request["axes"] and row.get("point_size") == request["point_size"]
                and row.get("upem") == entry["upem"], "baseline_request_identity_mismatch")
        if row["status"] == "FAILED":
            failed += 1
            require(type(row.get("error")) is str and bool(row["error"]), "failed_baseline_error_missing")
            require(not any(channel in row for channel in CHANNELS), "failed_baseline_contains_complete_channels")
            continue
        complete += 1
        require(row.get("error") is None and row.get("nominal_glyph_id") == 2
                and all(type(row.get(channel)) is dict for channel in CHANNELS), "complete_baseline_record_incomplete")
        identity = row.get("font_identity", {})
        require(identity.get("all_source_tables_verified") is True
                and identity.get("axes_size_and_matrix_verified") is True
                and identity.get("verified_table_sha256") == entry["table_sha256"], "native_instance_identity_mismatch")
        layout = row["vertical_layout"]
        glyphs, runs = layout.get("glyphs", []), layout.get("runs", [])
        require(layout.get("both_nominal_glyphs_and_all_source_tables_verified") is True
                and len(glyphs) == 2 and len(runs) == 1
                and sorted(g.get("string_index") for g in glyphs) == [0, 1]
                and all(g.get("glyph_id") == 2 for g in glyphs), "native_layout_identity_mismatch")
        require(all(run["font_identity"]["verified_table_sha256"] == entry["table_sha256"] for run in runs),
                "native_layout_font_fallback")
    require(complete == report.get("completed_request_count") and complete > 0 and failed > 0,
            "baseline_complete_failed_counts_mismatch")
    return {"classification": "partial_no_reverse", "complete_records": complete, "failed_records": failed,
            "binary64_values_verified": verify_partial_bits(report), "reverse_replay_verified": False,
            "source_final_reverification_present": report.get("source_unchanged_after_measurement") is True,
            "baseline_promoted_to_accepted_report": False}


def remove_font_identity(value):
    if type(value) is dict:
        return {key: remove_font_identity(child) for key, child in value.items() if key != "font_identity"}
    if type(value) is list:
        return [remove_font_identity(child) for child in value]
    return value


def same_values(left, right):
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(same_values(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(same_values(a, b) for a, b in zip(left, right))
    return left == right


def channel_bits(report, index, channel):
    prefix = f"$.observations[{index}].{channel}"
    return {path[len(prefix):]: bits for path, bits in report["binary64_hex_by_json_path"].items()
            if (path.startswith(prefix + ".") or path.startswith(prefix + "["))
            and not re.search(r"(?:^|\.)font_identity(?:\.|\[|$)", path)}


def compare_unit_channels(baseline_raw, scaled_raw, baseline_entry, scaled_entry):
    baseline = validate_partial_baseline(baseline_raw, baseline_entry)
    require(baseline_entry["upem"] == scaled_entry["upem"]
            and baseline_entry["variant"] == scaled_entry["variant"], "unit_comparison_fixture_semantics_mismatch")
    verify_source(scaled_raw, scaled_entry, 16384)
    scaled_requests = wire_requests(scaled_entry, 16384)
    scaled_validation = validate_raw(scaled_raw, scaled_entry, scaled_requests)
    baseline_requests = {request["id"]: request for request in baseline_entry["requests"]}
    scaled_by_id = {request["id"]: request for request in scaled_entry["requests"]}
    require(set(baseline_requests) == set(scaled_by_id), "unit_comparison_request_set_mismatch")
    for key, request in baseline_requests.items():
        require(normalized_axes(request) == normalized_axes(scaled_by_id[key])
                and request["point_size"] == scaled_by_id[key]["point_size"], "unit_comparison_request_semantics_mismatch")
    left = {row["id"]: (index, row) for index, row in enumerate(baseline_raw["observations"])}
    right = {row["id"]: (index, row) for index, row in enumerate(scaled_raw["observations"])}
    rows = []
    for key in baseline_requests:
        a_index, a = left[key]
        b_index, b = right[key]
        item = {"request_id": key, "baseline_status": a["status"], "scaled_status": b["status"]}
        if a["status"] != "COMPLETE":
            item.update(status="baseline_failed_not_compared", baseline_error=a["error"])
        else:
            channels = {}
            for channel in CHANNELS:
                values = same_values(remove_font_identity(a[channel]), remove_font_identity(b[channel]))
                bits = channel_bits(baseline_raw, a_index, channel) == channel_bits(scaled_raw, b_index, channel)
                channels[channel] = {"status": "same" if values and bits else "mismatch",
                                     "values_exact_match": values, "binary64_exact_match": bits}
            item.update(channels=channels, status="same" if all(value["status"] == "same" for value in channels.values()) else "mismatch")
        rows.append(item)
    return {"status": "BOUNDED_UNIT_COMPARISON_NOT_NATIVE_ACCEPTANCE", "baseline": baseline,
            "baseline_source_sha256": baseline_entry["sha256"], "scaled_source_sha256": scaled_entry["sha256"],
            "height_axis_units": [1, 16384], "scaled_raw_validation": scaled_validation,
            "scaled_reverse_replay_verification": "REQUIRED_BY_CALLING_RUNNER_NOT_RECHECKED_HERE",
            "excluded_comparison_fields": ["font_identity recursively; identities separately checked against each own source"],
            "same_count": sum(row["status"] == "same" for row in rows),
            "mismatch_count": sum(row["status"] == "mismatch" for row in rows),
            "not_compared_count": sum(row["status"] == "baseline_failed_not_compared" for row in rows),
            "measurement_correction_applied": False, "numeric_tolerance_used": False,
            "native_acceptance": False, "observations": rows}


def infer_witness_axes(row, request, variant):
    require(row.get("status") == "COMPLETE", "complete_witness_required")
    axes = normalized_axes(request)
    require(row["requested_axes"] == request.get("native_user_axes", request["axes"])
            and row["point_size"] == request["point_size"], "witness_request_identity_mismatch")
    upem, point_size = row["upem"], number(row["point_size"])
    require(type(upem) is int and upem > 0 and point_size > 0, "invalid_witness_unit_basis")
    raw = row["witness_path"]["geometric_bounds_xywh"]
    require(type(raw) is list and len(raw) == 4, "four_witness_bounds_required")
    converted = [number(value) * upem / point_size for value in raw]
    x_min, bottom, width, height = converted
    top = bottom + height
    x = (width - 600) / 200
    expected_x, expected_y = number(axes["WDTH"]), number(axes["HGHT"])
    result = {"status": "VISIBLE_RECTANGLE_AXIS_INFERENCE_NOT_PHANTOM_ACCESS", "variant": variant,
        "basis": {"raw_bounds_points_exact": [rational(number(value)) for value in raw],
                  "upem": upem, "point_size_exact": rational(point_size),
                  "expression": "design_units_exact = Fraction(raw_points) * UPEM / Fraction(point_size)",
                  "rounding_applied": False,
                  "design_units_exact": {key: rational(value) for key, value in
                     (("x_min", x_min), ("bottom", bottom), ("width", width), ("height", height), ("top", top))}},
        "WDTH": {"available": True, "formula": "(width - 600) / 200", "inferred_exact": rational(x),
                 "requested_normalized_exact": rational(expected_x), "exact_match": x == expected_x}}
    if variant == "phantom_only":
        result["HGHT"] = {"available": False, "reason": "fixed_visible_outline_cannot_identify_HGHT",
                          "fixed_top_and_bottom_exact": top == 820 and bottom == -180,
                          "requested_normalized_exact": rational(expected_y)}
        result["all_axes_exact_match"] = None
    else:
        y_top, y_bottom = (top - 820) / 60, (-180 - bottom) / 90
        result["HGHT"] = {"available": True, "top_formula": "(top - 820) / 60",
            "bottom_formula": "(-180 - bottom) / 90", "from_top_exact": rational(y_top),
            "from_bottom_exact": rational(y_bottom), "top_bottom_exact_agreement": y_top == y_bottom,
            "requested_normalized_exact": rational(expected_y), "exact_match": y_top == y_bottom == expected_y}
        result["all_axes_exact_match"] = x == expected_x and y_top == y_bottom == expected_y
    return result
