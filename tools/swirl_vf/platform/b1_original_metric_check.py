#!/usr/bin/env python3
"""Bounded, strict original-PingFang metric check; no font reconstruction.

The unchanged Swift binary is wrapped by the existing exact-replay adapter.
All source faces are identified, but only a predeclared endpoint/default subset
is sampled. SourceMetrics is explicitly a table reference, never a replacement
for native values. Original paths travel only through the private in-memory
oracle protocol and are not serialized into this report.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
from pathlib import Path
import platform
import struct
import sys
import tempfile

import numpy as np
from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import rebuild
from audit_font import raw_avar
from source_metrics import SourceMetrics, SourceMetricError
from verified_axis_oracle import BACKEND, make_launcher


EXPECTED_SOURCE = "39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890"
FACES = (0, 15, 31)
GLYPHS = (0, 1, 5, 19177)
TAGS = ("WDTH", "wght", "HGHT")
METRIC_LIMIT = 1 / 32
REPRESENTATION_LIMIT = 1e-5
SCALARS = ("advance_width", "advance_height", "lsb", "horizontal_origin_x",
           "horizontal_origin_y", "vertical_origin_x", "vertical_origin_y",
           "horizontal_advance_sum", "vertical_advance_sum")
VECTORS = ("horizontal_advance_vector", "vertical_advance_vector", "vertical_origin_translation")
REFERENCE_FIELDS = ("advance_width", "advance_height", "horizontal_origin_x",
                    "horizontal_origin_y", "vertical_origin_x", "vertical_origin_y")


def require(value, reason):
    if not value:
        raise ValueError(reason)


def finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def metric_whitelist(record):
    """Validate finite numeric metrics for private in-memory analysis only."""
    require(type(record) is dict and record.get("error") is None, "invalid_native_metric_record")
    result = {}
    for name in SCALARS:
        require(name in record and finite(record[name]), "missing_or_nonfinite_native_metric")
        result[name] = record[name]
    for name in VECTORS:
        value = record.get(name)
        require(type(value) is list and len(value) == 2 and all(finite(v) for v in value),
                "missing_or_nonfinite_native_vector")
        result[name] = list(value)
    return result


def fixed_cases(font):
    """Use actual fvar values; never assume that the original default is 400."""
    axes = {a.axisTag: a for a in font["fvar"].axes}
    require(tuple(axes) == TAGS, "unexpected_source_axes")
    require(all(finite(v) and float(v).is_integer() for a in axes.values()
                for v in (a.minValue, a.defaultValue, a.maxValue)), "noninteger_endpoint_plan")
    require(all(a.minValue < a.defaultValue < a.maxValue for a in axes.values()),
            "noninterior_axis_default")
    defaults = {tag: float(a.defaultValue) for tag, a in axes.items()}
    zero = {tag: 0.0 for tag in axes}
    cases = [("default", defaults, zero)]
    for tag in ("WDTH", "HGHT"):
        for label, node, value in (("min", -1.0, axes[tag].minValue),
                                   ("max", 1.0, axes[tag].maxValue)):
            location, normalized = dict(defaults), dict(zero)
            location[tag], normalized[tag] = float(value), node
            cases.append((tag + "_" + label, location, normalized))
    return cases


def endpoint_reference_basis(font, normalized):
    """Admit only explicit identity anchors; do not solve the A3 mapping.

    Parse raw ordered records, avoiding fontTools' dictionary collapse. A missing,
    duplicate, or nonidentity requested anchor makes this table reference
    unavailable. In particular, a nonzero avar mapping at user default must not
    silently become design zero. Other avar records are neither repaired nor
    interpreted. This is a standard-table reference, not a CoreText mapping claim.
    """
    require(set(normalized) == set(TAGS) and all(v in (-1.0, 0.0, 1.0)
            and finite(v) for v in normalized.values()), "nonendpoint_reference_request")
    if "avar" not in font:
        return {"available": True, "basis": "no_avar_endpoint_or_default",
                "normalized_design_location": dict(normalized), "anchor_checks": []}
    parsed = raw_avar(font.reader["avar"], list(TAGS))
    if (parsed["major"], parsed["minor"], parsed["reserved"], parsed["axis_count"],
            parsed["trailing_bytes"]) != (1, 0, 0, len(TAGS), 0):
        return {"available": False, "reason": "unsupported_raw_avar_header", "anchor_checks": []}
    checks = []
    for tag, axis in zip(TAGS, parsed["axes"]):
        target = int(normalized[tag] * 16384)
        records = [r for r in axis["records"] if r["from_f2dot14"] == target]
        checks.append({"axis": tag, "normalized_requested": normalized[tag],
                       "matching_raw_record_count": len(records),
                       "raw_target_f2dot14": [r["to_f2dot14"] for r in records],
                       "unique_identity_anchor": len(records) == 1
                       and records[0]["to_f2dot14"] == target})
    available = all(c["unique_identity_anchor"] for c in checks)
    result = {"available": available, "basis": "explicit_unique_raw_avar_identity_anchors_only",
              "anchor_checks": checks, "CoreText_mapping_equivalence_claimed": False}
    if available:
        result["normalized_design_location"] = dict(normalized)
    else:
        result["reason"] = "ambiguous_missing_or_nonidentity_avar_anchor"
    return result


def stored_metrics(font, gid):
    name = font.getGlyphOrder()[gid]
    width, lsb = font["hmtx"].metrics[name]
    height, tsb = font["vmtx"].metrics[name]
    require(all(type(v) is int for v in (width, lsb, height, tsb)), "noninteger_source_storage")
    vorg = {"present": "VORG" in font}
    if vorg["present"]:
        table = font["VORG"]
        vorg.update(default_y=int(table.defaultVertOriginY), glyph_y=int(table[name]),
                    explicit_glyph_override=name in table.VOriginRecords)
    return {"units": "serialized_font_design_units", "hmtx": {"advance_width": width, "lsb": lsb},
            "vmtx": {"advance_height": height, "top_side_bearing": tsb}, "VORG": vorg}


def representation_check(record, horizontal, vertical):
    """Exercise the unchanged production gate with zero outline coordinates."""
    try:
        rebuild.with_phantoms(np.empty((0, 2)), record, horizontal, vertical)
    except rebuild.ReconstructionError as error:
        context = error.context.get("metric_representation", {})
        if context.get("field") == "vertical_origin_x":
            return {"passed": False, "reason": "production_vertical_x_not_representable",
                    "absolute_error_font_units": context["absolute_error_font_units"],
                    "tolerance_font_units": context["representation_tolerance_font_units"]}
        return {"passed": False, "reason": "production_metric_representation_rejected",
                "tolerance_font_units": REPRESENTATION_LIMIT}
    return {"passed": True, "tolerance_font_units": REPRESENTATION_LIMIT}


def strict_comparison(native, reference):
    require(all(finite(native.get(k)) and finite(reference.get(k)) for k in REFERENCE_FIELDS),
            "invalid_strict_metric_inputs")
    errors = {key: native[key] - reference[key] for key in REFERENCE_FIELDS}
    return {"tolerance_font_units": METRIC_LIMIT, "signed_errors_font_units": errors,
            "passed": all(abs(e) <= METRIC_LIMIT for e in errors.values()),
            "failing_fields": [key for key, error in errors.items() if abs(error) > METRIC_LIMIT],
            "reference_is_native_observation": False,
            "vertical_x_reference_is_standard_convention_not_stored_value": True}


def observation(record, stored, default_native, reference, basis):
    native = metric_whitelist(record)
    predictions = {
        "half_current_native_advance": native["horizontal_origin_x"] + native["advance_width"] / 2,
        "half_stored_hmtx_advance": native["horizontal_origin_x"] + stored["hmtx"]["advance_width"] / 2,
        "default_native_vertical_origin_x": default_native["vertical_origin_x"],
    }
    result = {"native_metrics": native,
              "native_scalar_binary64_hex": {k: struct.pack(">d", float(native[k])).hex() for k in SCALARS},
              "stored_metrics": stored,
              "source_table_reference_basis": basis,
              "vertical_x_candidates": {name: {"prediction_font_units": value,
                  "native_minus_prediction_font_units": native["vertical_origin_x"] - value}
                  for name, value in predictions.items()},
              "production_representation": representation_check(record,
                  (stored["hmtx"]["advance_width"], stored["hmtx"]["lsb"]),
                  (stored["vmtx"]["advance_height"], stored["vmtx"]["top_side_bearing"]))}
    if reference is not None:
        result["source_table_reference"] = {key: reference[key] for key in REFERENCE_FIELDS}
        result["source_table_reference"]["metric_source"] = "unhinted_standard_source_tables_not_CoreText_API"
        result["strict_source_table_comparison"] = strict_comparison(native, reference)
    else:
        result["strict_source_table_comparison"] = {"passed": False,
            "status": "REFERENCE_UNAVAILABLE_NOT_ACCEPTED", "tolerance_font_units": METRIC_LIMIT}
    return result


def finish_observations(report, oracle, expected_requests, expected_records):
    """No diagnostic completion is granted until summary, EOF and exit pass."""
    summary = oracle.finish()  # NativeOracle checks actual EOF and subprocess exit.
    rebuild.verify_session_summary(summary, report["source_sha256"], expected_requests, expected_records)
    require(summary.get("axis_verification_backend") == BACKEND
            and type(summary.get("verified_batch_count")) is int
            and summary.get("verified_batch_count") == expected_requests
            and summary.get("source_unchanged") is True, "unverified_native_finalization")
    require(len(report["observations"]) == expected_records, "incomplete_observation_report")
    report["native_finalization"] = {key: summary[key] for key in ("request_count",
        "successful_glyph_count", "error_count", "verified_batch_count", "source_unchanged")}
    for key in ("internal_native_request_count", "internal_native_glyph_count"):
        if type(summary.get(key)) is int:
            report["native_finalization"][key] = summary[key]
    report["diagnostics_complete"] = True
    report["reference_unavailable_count"] = sum(
        row["strict_source_table_comparison"].get("status") == "REFERENCE_UNAVAILABLE_NOT_ACCEPTED"
        for row in report["observations"])
    report["strict_metric_failures"] = sum(not row["strict_source_table_comparison"]["passed"]
        and row["strict_source_table_comparison"].get("status") != "REFERENCE_UNAVAILABLE_NOT_ACCEPTED"
        for row in report["observations"])
    report["representation_failures"] = sum(not row["production_representation"]["passed"]
                                            for row in report["observations"])
    passed = not (report["strict_metric_failures"] or report["representation_failures"]
                  or report["reference_unavailable_count"])
    report["status"] = "FINITE_SAMPLE_CHECKS_PASS_NOT_ORIGINAL_ACCEPTANCE" if passed else "STRICT_ORIGINAL_METRIC_CHECK_FAILED"
    return 0 if passed else 1


# Public reports are a separate aggregate schema, not a filtered native record.
# Do not add free-form strings, face/GID keys, locations, hashes, table details,
# observations, metric values, differences, or binary64 payloads here.
PUBLIC_STATUSES = frozenset((
    "NOT_RUN", "FINITE_SAMPLE_CHECKS_PASS_NOT_ORIGINAL_ACCEPTANCE",
    "STRICT_ORIGINAL_METRIC_CHECK_FAILED", "ORIGINAL_METRIC_CHECK_EXECUTION_ERROR",
    "SOURCE_IDENTITY_FAILED", "VORG_ABLATION_REJECTION_OR_REPEAT_FAILURE",
    "DIAGNOSTICS_COMPLETE_ORIGINAL_PRODUCTION_REPRESENTATION_FAILED",
    "BOUNDED_VORG_ABLATION_COMPLETE_NOT_FIX", "VORG_ABLATION_EXECUTION_ERROR",
    "ORIGINAL_SOURCE_IDENTITY_FAILED"))
PUBLIC_BOOLEAN_FIELDS = (
    "diagnostics_complete", "experiment_complete", "source_unchanged",
    "original_font_accepted", "font_output_generated", "original_outlines_published",
    "original_font_published", "variant_font_published", "continuous_space_acceptance",
    "production_extract_or_rebuild_modified", "production_entrypoints_modified",
    "production_fix_established", "source_table_metrics_replace_native",
    "private_temporary_protocol_files_removed", "private_temporary_font_and_protocol_files_removed",
    "diagnostics_complete_and_original_repeat_stable", "strict_original_representation_pass")
PUBLIC_COUNT_FIELDS = (
    "strict_metric_failures", "reference_unavailable_count", "representation_failures",
    "physical_faces_verified", "original_faces_reconstructed", "original_glyph_models_completed",
    "strict_original_representation_failed_count")
PUBLIC_FINALIZATION_COUNTS = (
    "request_count", "successful_glyph_count", "error_count", "verified_batch_count",
    "internal_native_request_count", "internal_native_glyph_count")
PUBLIC_COMPARISON_BOOLEANS = (
    "original_repeat_numeric_exact", "original_repeat_binary64_exact",
    "all_native_fields_unchanged", "measured_differences_invented")
PUBLIC_GATE_BOOLEANS = (
    "strict_original_representation_pass", "strict_original_representation_complete",
    "source_table_equivalence_rechecked")
PUBLIC_GATE_COUNTS = (
    "strict_original_representation_failed_count", "strict_original_representation_checked_count",
    "additional_native_requests")


def _public_fields(values, booleans=(), counts=()):
    """Copy only exact primitive types; malformed/missing fields stay unknown."""
    values = values if type(values) is dict else {}
    result = {key: values.get(key) if type(values.get(key)) is bool else None
              for key in booleans}
    for key in counts:
        value = values.get(key)
        result[key] = value if type(value) is int and 0 <= value <= 2**53 - 1 else None
    return result


def public_log_summary(report):
    """Aggregate-only allowlist shared by stdout and the public JSON artifact.

    Full observations remain in process memory for strict checks only. Unknown
    fields and arbitrary failure messages are never serialized. Counts are null
    before finalization, rather than a misleading zero. Gate semantics and exit
    codes are unchanged; diagnostic completion is not original-font acceptance.
    """
    report = report if type(report) is dict else {}
    status = report.get("status")
    result = {"schema_version": 2, "public_output_scope": "aggregate_only",
              "status": status if type(status) is str and status in PUBLIC_STATUSES
              else "UNRECOGNIZED_STATUS_NOT_ACCEPTED"}
    result.update(_public_fields(report, PUBLIC_BOOLEAN_FIELDS, PUBLIC_COUNT_FIELDS))
    result["native_finalization"] = _public_fields(
        report.get("native_finalization"), ("source_unchanged",), PUBLIC_FINALIZATION_COUNTS)
    result["comparison"] = _public_fields(report.get("comparison"),
        PUBLIC_COMPARISON_BOOLEANS, ("samples", "original_repeat_samples"))
    result["original_representation_gate"] = _public_fields(
        report.get("original_representation_gate"), PUBLIC_GATE_BOOLEANS, PUBLIC_GATE_COUNTS)
    return result


def run(source, binary, output):
    source, binary, output = Path(source).resolve(), Path(binary).resolve(), Path(output)
    require(not output.exists() and not output.is_symlink(), "new_report_path_required")
    require(output.resolve() not in (source, binary), "unsafe_report_alias")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "status": "NOT_RUN", "diagnostics_complete": False,
              "source_sha256": EXPECTED_SOURCE, "source_commit": os.environ.get("GITHUB_SHA", "UNKNOWN"),
              "platform": platform.platform(), "sampled_faces": list(FACES), "sampled_glyphs": list(GLYPHS),
              "plan": "default_WDTH_min_max_HGHT_min_max_at_actual_fvar_integer_nodes",
              "original_font_accepted": False, "original_faces_reconstructed": 0,
              "original_glyph_models_completed": 0, "font_output_generated": False,
              "original_outlines_published": False, "original_font_published": False,
              "continuous_space_acceptance": False, "windows_acceptance": "NOT_RUN",
              "production_extract_or_rebuild_modified": False,
              "source_table_metrics_replace_native": False,
              "strict_metric_tolerance_font_units": METRIC_LIMIT,
              "production_representation_tolerance_font_units": REPRESENTATION_LIMIT,
              "observations": [], "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    code, stage = 1, "source_identity"
    try:
        report["observed_source_sha256"] = rebuild.sha256(source) if source.is_file() else None
        require(report["observed_source_sha256"] == EXPECTED_SOURCE, "source_hash_mismatch")
        require(sys.platform == "darwin", "native_CoreText_runtime_required")
        require(binary.is_file() and os.access(binary, os.X_OK), "native_binary_required")
        report["native_binary_sha256"] = rebuild.sha256(binary)
        with TTCollection(source, lazy=True) as collection:
            require(len(collection.fonts) == 32, "all_32_original_faces_required")
            identities = rebuild.checkpoint_source_faces(collection.fonts)
            stage = "native_identity_and_sampling"
            with tempfile.TemporaryDirectory(prefix="swirl-b1-original-private-") as directory:
                private = Path(directory)
                launcher = make_launcher(private / "verified-axis-oracle", binary)
                report["verified_axis_launcher_sha256"] = rebuild.sha256(launcher)
                oracle = rebuild.NativeOracle(launcher, source, private / "native-stderr.log")
                try:
                    rebuild.verify_checkpoint_session_metadata(oracle.metadata, EXPECTED_SOURCE,
                                                                source.stat().st_size, identities)
                    require(oracle.metadata.get("axis_verification_backend") == BACKEND
                            and oracle.metadata.get("diagnostic_readback_observation_only", False) is False,
                            "exact_replay_adapter_required")
                    report["physical_faces_verified"] = len(identities)
                    report["physical_face_identities"] = identities
                    requests = 0
                    for face in FACES:
                        font = collection.fonts[face]
                        require(max(GLYPHS) < font["maxp"].numGlyphs, "original_gid_missing")
                        provider = SourceMetrics(font)
                        baseline = {}
                        for label, location, normalized in fixed_cases(font):
                            basis = endpoint_reference_basis(font, normalized)
                            records = oracle.samples(face, list(GLYPHS), location)
                            requests += 1
                            for gid in GLYPHS:
                                native = metric_whitelist(records[gid])
                                if label == "default":
                                    baseline[gid] = native
                                reference = None
                                local_basis = dict(basis)
                                if basis["available"]:
                                    try:
                                        reference = provider.at(gid, normalized)
                                    except SourceMetricError:
                                        local_basis.update(available=False, reason="unsupported_source_metric_reference")
                                row = observation(records[gid], stored_metrics(font, gid), baseline[gid],
                                                  reference, local_basis)
                                row.update(face_index=face, glyph_id=gid, case=label, user_location=location)
                                report["observations"].append(row)
                    stage = "native_finalization"
                    require(requests == len(FACES) * 5, "incomplete_request_plan")
                    code = finish_observations(report, oracle, len(FACES) * 5, len(FACES) * 5 * len(GLYPHS))
                finally:
                    oracle.close()
            report["private_temporary_protocol_files_removed"] = True
    except Exception as error:
        known_reasons = ("source_hash_mismatch", "native_CoreText_runtime_required", "native_binary_required",
            "all_32_original_faces_required", "exact_replay_adapter_required", "original_gid_missing",
            "unexpected_source_axes", "noninteger_endpoint_plan", "noninterior_axis_default",
            "incomplete_request_plan", "unverified_native_finalization", "incomplete_observation_report",
            "missing_or_nonfinite_native_metric", "missing_or_nonfinite_native_vector",
            "native oracle source SHA mismatch", "native oracle could not verify every requested physical face",
            "native final summary is incomplete", "native oracle emitted data after its final summary",
            "native oracle failed after its final glyph", "native_readback_replay_not_exactly_stable",
            "native_replay_payload_not_exact", "native_nondefault_axis_not_reported")
        reason = next((value for value in known_reasons if value in str(error)),
                      "PRIVATE_PROTOCOL_OR_SOURCE_FAILURE_DETAILS_NOT_PUBLISHED")
        report.update(status="ORIGINAL_METRIC_CHECK_EXECUTION_ERROR", diagnostics_complete=False,
                      failure={"stage": stage, "type": type(error).__name__, "reason": reason})
        code = 1
    finally:
        try:
            report["source_unchanged"] = source.is_file() and rebuild.sha256(source) == EXPECTED_SOURCE
        except OSError:
            report["source_unchanged"] = False
        if not report["source_unchanged"]:
            report.update(status="SOURCE_IDENTITY_FAILED", diagnostics_complete=False)
            code = 1
        report["ended_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with output.open("x", encoding="utf-8") as stream:
            json.dump(public_log_summary(report), stream, indent=2, allow_nan=False)
            stream.write("\n")
    print("B1_ORIGINAL_SUMMARY_JSON=" + json.dumps(public_log_summary(report),
          separators=(",", ":"), allow_nan=False), flush=True)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New aggregate-only public JSON report file")
    args = parser.parse_args()
    return run(args.source, args.binary, args.output)


if __name__ == "__main__":
    raise SystemExit(main())

