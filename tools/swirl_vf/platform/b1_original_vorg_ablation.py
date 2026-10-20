#!/usr/bin/env python3
"""Private raw-directory VORG ablation; diagnostic, never a conversion fix.

Only the TTC's per-face table directories are patched. No fontTools save,
avar interpretation, outline transformation or table-payload rewrite occurs.
The original file is read-only; the ablated file lives in a temporary directory.
Three fresh exact-replay CoreText sessions measure original / no VORG / original
repeat. A rejected HVGL-without-VORG font is recorded as a rejection, not supplied
with invented metric values. Neither original nor variant fonts are published.

The earlier glyf/VORG probe is outside the OpenType VORG contract (VORG is for
CFF/CFF2, and must be ignored for TrueType). An observed CoreText response does
not turn that probe, or this HVGL-specific experiment, into a production fix.
https://learn.microsoft.com/en-us/typography/opentype/spec/vorg
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import sys
import tempfile

from fontTools.ttLib import TTCollection

from b1_original_metric_check import (EXPECTED_SOURCE, FACES, GLYPHS, SCALARS, VECTORS,
                                    fixed_cases, metric_whitelist, representation_check, stored_metrics)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import rebuild
from verified_axis_oracle import BACKEND, make_launcher


VARIANTS = ("original_with_vorg", "private_without_vorg", "original_repeat")


class AblationError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise AblationError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def intersects(a, b):
    return a[0] < b[1] and b[0] < a[1]


def read_directories(data):
    """Read raw SFNT/TTC records, rejecting unsafe spans before any edit."""
    require(type(data) is bytes and len(data) >= 12, "truncated_ttc_header")
    tag, version, count = struct.unpack_from(">4sII", data)
    require(tag == b"ttcf" and version in (0x10000, 0x20000), "unsupported_ttc_header")
    require(0 < count <= 4096, "invalid_ttc_face_count")
    header_end = 12 + 4 * count + (12 if version == 0x20000 else 0)
    require(header_end <= len(data), "truncated_ttc_offsets")
    offsets = struct.unpack_from(">" + "I" * count, data, 12)
    require(len(set(offsets)) == count, "duplicate_physical_directory_offset")
    faces, spans = [], [(0, header_end)]
    for index, offset in enumerate(offsets):
        require(offset >= header_end and offset + 12 <= len(data), "sfnt_directory_out_of_bounds")
        scaler, number, search_range, selector, shift = struct.unpack_from(">4s4H", data, offset)
        require(scaler in (b"\0\1\0\0", b"OTTO", b"true", b"typ1"), "unsupported_sfnt_scaler")
        require(0 < number <= 4095, "invalid_sfnt_table_count")
        end = offset + 12 + 16 * number
        require(end <= len(data), "truncated_sfnt_directory")
        span = (offset, end)
        require(not any(intersects(span, other) for other in spans), "overlapping_sfnt_directories")
        spans.append(span)
        records = []
        for entry in range(number):
            position = offset + 12 + 16 * entry
            table_tag, checksum, table_offset, length = struct.unpack_from(">4sIII", data, position)
            require(all(32 <= byte < 127 for byte in table_tag), "invalid_table_tag")
            require(table_offset <= len(data) and length <= len(data) - table_offset,
                    "table_payload_out_of_bounds")
            records.append({"tag": table_tag, "checksum": checksum, "offset": table_offset,
                            "length": length, "record": data[position:position + 16]})
        require(len({r["tag"] for r in records}) == number, "duplicate_table_tag")
        faces.append({"face_index": index, "offset": offset, "end": end, "num_tables": number,
                      "search_fields": [search_range, selector, shift], "records": records})
    for face in faces:
        for record in face["records"]:
            span = (record["offset"], record["offset"] + record["length"])
            if record["length"]:
                require(not any(intersects(span, other) for other in spans), "table_payload_overlaps_directory")
    return {"version": version, "header_end": header_end, "faces": faces}


def search_fields(count):
    require(type(count) is int and 0 < count <= 4095, "invalid_retained_table_count")
    selector = count.bit_length() - 1
    search_range = 16 * (1 << selector)
    return search_range, selector, count * 16 - search_range


def verify_removed_vorg(original, modified):
    """Independently inspect the result and compare every retained raw table."""
    before, after = read_directories(original), read_directories(modified)
    require(len(original) == len(modified), "ablation_file_size_changed")
    require(original[:before["header_end"]] == modified[:before["header_end"]], "ttc_header_changed")
    require(len(before["faces"]) == len(after["faces"]), "ablation_face_count_changed")
    expected_edits, checks, faces = [], 0, []
    for old, new in zip(before["faces"], after["faces"]):
        retained = [record for record in old["records"] if record["tag"] != b"VORG"]
        require(len(retained) == old["num_tables"] - 1, "each_original_face_requires_one_vorg")
        require(new["offset"] == old["offset"] and new["num_tables"] == len(retained),
                "incorrect_ablation_directory")
        require(new["search_fields"] == list(search_fields(len(retained))), "incorrect_search_fields")
        require([r["record"] for r in new["records"]] == [r["record"] for r in retained],
                "retained_directory_record_changed")
        start = old["offset"]
        require(original[start:start + 4] == modified[start:start + 4], "sfnt_scaler_changed")
        require(modified[new["end"]:old["end"]] == bytes(old["end"] - new["end"]),
                "removed_directory_slot_not_zero")
        for table in retained:
            offset, length = table["offset"], table["length"]
            require(original[offset:offset + length] == modified[offset:offset + length],
                    "retained_table_payload_changed")
            checks += 1
        expected_edits.append((start + 4, old["end"]))
        faces.append({"face_index": old["face_index"], "old_table_count": old["num_tables"],
                      "retained_table_count": len(retained), "removed_vorg_entries": 1,
                      "retained_directory_records_exact": True, "retained_table_payloads_exact": True})
    # All bytes outside the edited directory spans, including unreachable VORG
    # payloads and head.checkSumAdjustment, must remain exactly as in the source.
    cursor = 0
    for start, end in sorted(expected_edits):
        require(original[cursor:start] == modified[cursor:start], "bytes_outside_directory_changed")
        cursor = end
    require(original[cursor:] == modified[cursor:], "bytes_outside_directory_changed")
    return {"physical_faces": len(faces), "retained_table_byte_comparisons": checks,
            "all_retained_tables_byte_identical": True, "all_non_directory_bytes_identical": True,
            "raw_avar_bytes_and_record_order_preserved": True, "fonttools_reserialization_used": False,
            "head_checksum_adjustment_and_signatures_not_rewritten": True, "faces": faces}


def remove_vorg_directories(original):
    parsed = read_directories(original)
    result = bytearray(original)
    for face in parsed["faces"]:
        records = [record for record in face["records"] if record["tag"] != b"VORG"]
        require(len(records) == face["num_tables"] - 1, "each_original_face_requires_one_vorg")
        new_count = len(records)
        start = face["offset"]
        struct.pack_into(">4H", result, start + 4, new_count, *search_fields(new_count))
        retained = b"".join(record["record"] for record in records)
        result[start + 12:face["end"]] = retained + bytes(16)
    modified = bytes(result)
    evidence = verify_removed_vorg(original, modified)
    evidence.update(original_sha256=digest(original), private_variant_sha256=digest(modified),
                    original_byte_size=len(original), private_variant_byte_size=len(modified))
    return modified, evidence


def metric_bits(metrics):
    result = {key: struct.pack(">d", float(metrics[key])).hex() for key in SCALARS}
    for key in VECTORS:
        result[key] = [struct.pack(">d", float(v)).hex() for v in metrics[key]]
    return result


def safe_reason(error):
    """Never publish arbitrary native errors, stderr, font paths or payloads."""
    allowed = ("native oracle did not return metadata", "native oracle startup failed",
        "native oracle could not verify every requested physical face", "native oracle source SHA mismatch",
        "native_face_or_original_table_identity_mismatch", "all_32_physical_faces_required",
        "native final summary is incomplete", "native oracle emitted data after its final summary",
        "native oracle failed after its final glyph", "native_readback_replay_not_exactly_stable",
        "native_replay_payload_not_exact", "native_nondefault_axis_not_reported",
        "source_changed_during_axis_verification", "exact_replay_adapter_required",
        "source_hash_mismatch", "native_CoreText_runtime_required", "native_binary_required")
    if isinstance(error, AblationError):
        # Every AblationError reason originates in a constant local guard.
        return str(error)
    return next((reason for reason in allowed if reason in str(error)),
                "NATIVE_OR_SOURCE_REJECTION_DETAILS_NOT_PUBLISHED")


def measure_variant(source, binary, directory, label, plan):
    result = {"variant": label, "status": "NOT_RUN", "diagnostics_complete": False,
              "source_sha256": None, "observations": [], "fresh_oracle_process_requested": True,
              "original_font_accepted": False, "font_or_outline_published": False}
    oracle, stage = None, "source_identity"
    try:
        result["source_sha256"] = rebuild.sha256(source)
        result["source_byte_size"] = source.stat().st_size
        with TTCollection(source, lazy=True) as collection:
            require(len(collection.fonts) == 32, "all_32_physical_faces_required")
            identities = rebuild.checkpoint_source_faces(collection.fonts)
        launcher = make_launcher(directory / (label + "-oracle"), binary)
        stage = "native_startup"
        oracle = rebuild.NativeOracle(launcher, source, directory / (label + "-stderr.log"))
        stage = "native_identity"
        rebuild.verify_checkpoint_session_metadata(oracle.metadata, result["source_sha256"],
                                                    result["source_byte_size"], identities)
        require(oracle.metadata.get("axis_verification_backend") == BACKEND
                and oracle.metadata.get("diagnostic_readback_observation_only", False) is False,
                "exact_replay_adapter_required")
        result["physical_faces_verified"] = len(identities)
        result["physical_face_identity_digest"] = rebuild.identity_digest(identities)
        result["verified_axis_launcher_sha256"] = rebuild.sha256(launcher)
        result["native_metadata_verification"] = {
            "source_sha256_and_byte_size_exact": True, "all_physical_table_hashes_exact": True,
            "all_physical_faces_identity_verified": True, "backend": "CoreText",
            "axis_verification_backend": BACKEND, "axis_observations_only": False,
            "diagnostic_readback_observation_only": False}
        stage = "native_sampling"
        for face, label_, location in plan:
            records = oracle.samples(face, list(GLYPHS), location)
            for gid in GLYPHS:
                metrics = metric_whitelist(records[gid])
                result["observations"].append({"face_index": face, "glyph_id": gid,
                    "case": label_, "user_location": location, "native_metrics": metrics,
                    "native_binary64_bits": metric_bits(metrics)})
        stage = "native_finalization"
        summary = oracle.finish()
        rebuild.verify_session_summary(summary, result["source_sha256"], len(plan), len(plan) * len(GLYPHS))
        require(summary.get("axis_verification_backend") == BACKEND
                and type(summary.get("verified_batch_count")) is int
                and summary["verified_batch_count"] == len(plan)
                and summary.get("source_unchanged") is True, "unverified_native_finalization")
        result["native_finalization"] = {key: summary[key] for key in ("request_count",
            "successful_glyph_count", "error_count", "verified_batch_count", "source_unchanged",
            "internal_native_request_count", "internal_native_glyph_count") if key in summary}
        result["native_finalization"].update(summary_validated=True, actual_eof_verified=True,
                                             native_process_exit_zero=True)
        result.update(status="BOUNDED_NATIVE_OBSERVATIONS_COMPLETE_NOT_ACCEPTANCE", diagnostics_complete=True)
    except Exception as error:
        result.update(status="NATIVE_VARIANT_REJECTED_OR_EXECUTION_FAILED", diagnostics_complete=False,
                      failure={"stage": stage, "type": type(error).__name__, "reason": safe_reason(error)})
    finally:
        if oracle is not None:
            try:
                oracle.close()
            except Exception as error:
                result.update(status="NATIVE_VARIANT_CLEANUP_FAILED", diagnostics_complete=False,
                    cleanup_failure={"type": type(error).__name__, "reason": safe_reason(error)})
        result["observed_record_count"] = len(result["observations"])
        try:
            result["source_unchanged"] = (result["source_sha256"] is not None
                                          and rebuild.sha256(source) == result["source_sha256"])
        except OSError:
            result["source_unchanged"] = False
        if not result["source_unchanged"]:
            result.update(status="VARIANT_SOURCE_CHANGED", diagnostics_complete=False)
    return result


def compare_variants(results):
    indexed = {item["variant"]: item for item in results}
    require(len(indexed) == len(results), "duplicate_variant_identity")
    incomplete = {"status": "NOT_COMPARABLE_NATIVE_VARIANT_INCOMPLETE", "measured_differences_invented": False}
    if set(indexed) != set(VARIANTS):
        return incomplete
    original, ablated, repeated = (indexed[label] for label in VARIANTS)
    require(original["source_sha256"] == repeated["source_sha256"], "original_repeat_source_mismatch")
    key = lambda row: (row["face_index"], row["case"], row["glyph_id"])
    rows = [{key(row): row for row in item["observations"]} for item in (original, ablated, repeated)]
    require(all(len(rowmap) == len(item["observations"]) for rowmap, item in zip(rows, (original, ablated, repeated))),
            "duplicate_observation_identity")
    # The final original session remains independently useful even when removing
    # VORG makes the HVGL font unloadable. Do not compare partial ablation data.
    if original["diagnostics_complete"] and repeated["diagnostics_complete"]:
        require(set(rows[0]) == set(rows[2]), "original_repeat_sample_identity_mismatch")
        repeat_numeric, repeat_bits = True, True
        for identity, original_row in rows[0].items():
            repeated_row = rows[2][identity]
            require(original_row["user_location"] == repeated_row["user_location"], "original_repeat_location_mismatch")
            a, again = (metric_whitelist(row["native_metrics"]) for row in (original_row, repeated_row))
            repeat_numeric = repeat_numeric and a == again
            repeat_bits = repeat_bits and metric_bits(a) == metric_bits(again)
        incomplete.update(original_repeat_samples=len(rows[0]), original_repeat_numeric_exact=repeat_numeric,
                          original_repeat_binary64_exact=repeat_bits)
    if not all(item["diagnostics_complete"] for item in indexed.values()):
        return incomplete
    require(original["source_sha256"] != ablated["source_sha256"], "ablation_source_not_changed")
    require(set(rows[0]) == set(rows[1]) == set(rows[2]), "variant_sample_identity_mismatch")
    differences = []
    for identity, original_row in rows[0].items():
        ablated_row, repeated_row = rows[1][identity], rows[2][identity]
        require(original_row["user_location"] == ablated_row["user_location"] == repeated_row["user_location"],
                "variant_location_mismatch")
        a, b, again = (metric_whitelist(row["native_metrics"]) for row in (original_row, ablated_row, repeated_row))
        delta = {field: b[field] - a[field] for field in SCALARS}
        vector_delta = {field: [new - old for old, new in zip(a[field], b[field])] for field in VECTORS}
        differences.append({"face_index": identity[0], "case": identity[1], "glyph_id": identity[2],
            "without_vorg_minus_original_font_units": delta,
            "without_vorg_minus_original_vectors": vector_delta,
            "original_repeat_numeric_exact": a == again,
            "original_repeat_binary64_exact": metric_bits(a) == metric_bits(again),
            "original_x_minus_current_half_width": a["vertical_origin_x"] - a["horizontal_origin_x"] - a["advance_width"] / 2,
            "without_vorg_x_minus_current_half_width": b["vertical_origin_x"] - b["horizontal_origin_x"] - b["advance_width"] / 2})
    return {"status": "COMPARED_BOUNDED_METRICS_NOT_PRODUCTION_FIX", "samples": len(differences),
            "original_repeat_numeric_exact": repeat_numeric, "original_repeat_binary64_exact": repeat_bits,
            "difference_sign": "private_without_vorg_minus_original_with_vorg", "differences": differences,
            "all_native_fields_unchanged": all(all(v == 0 for v in row["without_vorg_minus_original_font_units"].values())
                and all(all(v == 0 for v in vector) for vector in row["without_vorg_minus_original_vectors"].values())
                for row in differences)}


def check_original_representations(results, stored):
    """Reuse original native samples in the unchanged production strict gate.

    This checks representability only; it does not replace source metric
    equivalence checks, infer a source avar mapping, or accept an original face.
    """
    failed, checked, sessions = 0, 0, []
    for variant in results:
        if variant["variant"] not in ("original_with_vorg", "original_repeat"):
            continue
        failures = 0
        for row in variant["observations"]:
            reference = stored[(row["face_index"], row["glyph_id"])]
            outcome = representation_check(metric_whitelist(row["native_metrics"]),
                (reference["hmtx"]["advance_width"], reference["hmtx"]["lsb"]),
                (reference["vmtx"]["advance_height"], reference["vmtx"]["top_side_bearing"]))
            row["stored_original_metrics"] = reference
            row["production_representation"] = outcome
            failures += not outcome["passed"]
        count = len(variant["observations"])
        failed += failures
        checked += count
        variant["strict_original_representation_failed_count"] = failures
        variant["strict_original_representation_pass"] = (variant["diagnostics_complete"]
                                                          and count == 60 and failures == 0)
        sessions.append({"variant": variant["variant"], "checked_record_count": count,
                         "failed_count": failures, "diagnostics_complete": variant["diagnostics_complete"]})
    complete = (len(sessions) == 2 and checked == 120
                and all(item["diagnostics_complete"] and item["checked_record_count"] == 60 for item in sessions))
    return {"strict_original_representation_pass": complete and failed == 0,
            "strict_original_representation_failed_count": failed,
            "strict_original_representation_checked_count": checked,
            "strict_original_representation_complete": complete,
            "scope": "two_existing_60_record_original_sessions_unchanged_production_gate",
            "tolerance_font_units": 1e-5, "additional_native_requests": 0,
            "source_table_equivalence_rechecked": False, "sessions": sessions}


def public_log_summary(report):
    """Export only the closed report schema; native payloads never cross it."""
    scalar_fields = ("schema_version", "status", "experiment_complete", "source_sha256", "source_commit",
        "native_binary_sha256", "sampled_faces", "sampled_glyphs", "source_unchanged",
        "original_font_accepted", "production_fix_established", "original_faces_reconstructed",
        "original_glyph_models_completed", "variant_font_published", "original_font_published",
        "original_outlines_published", "production_entrypoints_modified", "source_table_metrics_replace_native",
        "continuous_space_acceptance", "windows_acceptance", "private_temporary_font_and_protocol_files_removed",
        "interpretation", "failure", "directory_patch_verification", "comparison",
        "diagnostics_complete_and_original_repeat_stable", "strict_original_representation_pass",
        "strict_original_representation_failed_count", "original_representation_gate")
    result = {key: report[key] for key in scalar_fields if key in report}
    result["variants"] = []
    variant_fields = ("variant", "status", "diagnostics_complete", "source_sha256", "source_byte_size",
        "fresh_oracle_process_requested", "original_font_accepted", "font_or_outline_published",
        "physical_faces_verified", "physical_face_identity_digest", "verified_axis_launcher_sha256",
        "native_metadata_verification", "native_finalization", "failure", "cleanup_failure",
        "observed_record_count", "source_unchanged", "strict_original_representation_pass",
        "strict_original_representation_failed_count")
    for variant in report["variants"]:
        saved = {key: variant[key] for key in variant_fields if key in variant}
        saved["observations"] = []
        for row in variant["observations"]:
            native = metric_whitelist(row["native_metrics"])
            kept = {key: row[key] for key in ("face_index", "glyph_id", "case", "user_location",
                                            "stored_original_metrics", "production_representation") if key in row}
            saved["observations"].append(kept | {"native_metrics": native, "native_binary64_bits": metric_bits(native)})
        result["variants"].append(saved)
    return result


def run(source, binary, output):
    source, binary, output = Path(source).resolve(), Path(binary).resolve(), Path(output)
    require(not output.exists() and not output.is_symlink(), "new_report_path_required")
    require(output.resolve() not in (source, binary), "unsafe_report_alias")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "status": "NOT_RUN", "experiment_complete": False,
        "source_sha256": EXPECTED_SOURCE, "source_commit": os.environ.get("GITHUB_SHA", "UNKNOWN"),
        "platform": platform.platform(), "sampled_faces": list(FACES), "sampled_glyphs": list(GLYPHS),
        "variants": [], "original_font_accepted": False, "production_fix_established": False,
        "original_faces_reconstructed": 0, "original_glyph_models_completed": 0,
        "variant_font_published": False, "original_font_published": False, "original_outlines_published": False,
        "production_entrypoints_modified": False, "source_table_metrics_replace_native": False,
        "continuous_space_acceptance": False, "windows_acceptance": "NOT_RUN",
        "interpretation": "Private HVGL VORG ablation only; successful loading or changed metrics does not establish a standard production conversion.",
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    code = 1
    try:
        original = source.read_bytes()
        require(digest(original) == EXPECTED_SOURCE, "source_hash_mismatch")
        require(sys.platform == "darwin", "native_CoreText_runtime_required")
        require(binary.is_file() and os.access(binary, os.X_OK), "native_binary_required")
        modified, patch_evidence = remove_vorg_directories(original)
        require(patch_evidence["physical_faces"] == 32, "all_32_physical_faces_required")
        report["directory_patch_verification"] = patch_evidence
        report["native_binary_sha256"] = rebuild.sha256(binary)
        with TTCollection(source, lazy=True) as collection:
            plan = [(face, label, location) for face in FACES
                    for label, location, _ in fixed_cases(collection.fonts[face])]
            stored = {(face, gid): stored_metrics(collection.fonts[face], gid) for face in FACES for gid in GLYPHS}
        require(len(plan) == 15, "fixed_request_plan_changed")
        with tempfile.TemporaryDirectory(prefix="swirl-b1-vorg-private-") as temporary:
            directory = Path(temporary)
            variant = directory / "without-vorg.ttc"
            with variant.open("xb") as stream:
                stream.write(modified)
            require(variant.read_bytes() == modified, "private_variant_write_mismatch")
            # Never short-circuit the original repeat if the ablated HVGL font
            # is rejected. Each NativeOracle owns a fresh process and private log.
            for label in VARIANTS:
                path = variant if label == "private_without_vorg" else source
                report["variants"].append(measure_variant(path, binary, directory, label, plan))
            report["original_representation_gate"] = check_original_representations(report["variants"], stored)
            for key in ("strict_original_representation_pass", "strict_original_representation_failed_count"):
                report[key] = report["original_representation_gate"][key]
            report["comparison"] = compare_variants(report["variants"])
        report["private_temporary_font_and_protocol_files_removed"] = True
        report["experiment_complete"] = True
        completed = all(item["diagnostics_complete"] for item in report["variants"])
        repeat = (report["comparison"].get("original_repeat_numeric_exact", False)
                  and report["comparison"].get("original_repeat_binary64_exact", False))
        report["diagnostics_complete_and_original_repeat_stable"] = completed and repeat
        if not completed or not repeat:
            report["status"] = "VORG_ABLATION_REJECTION_OR_REPEAT_FAILURE"
        elif not report["strict_original_representation_pass"]:
            report["status"] = "DIAGNOSTICS_COMPLETE_ORIGINAL_PRODUCTION_REPRESENTATION_FAILED"
        else:
            report["status"] = "BOUNDED_VORG_ABLATION_COMPLETE_NOT_FIX"
        code = 0 if completed and repeat and report["strict_original_representation_pass"] else 1
    except Exception as error:
        report.update(status="VORG_ABLATION_EXECUTION_ERROR", failure={"type": type(error).__name__,
                                                                      "reason": safe_reason(error)})
    finally:
        try:
            report["source_unchanged"] = source.is_file() and rebuild.sha256(source) == EXPECTED_SOURCE
        except OSError:
            report["source_unchanged"] = False
        if not report["source_unchanged"]:
            report.update(status="ORIGINAL_SOURCE_IDENTITY_FAILED", experiment_complete=False)
            code = 1
        report["ended_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
    print("B1_VORG_ABLATION_SUMMARY_JSON=" + json.dumps(public_log_summary(report),
          separators=(",", ":"), allow_nan=False), flush=True)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New safe JSON report file")
    args = parser.parse_args()
    return run(args.source, args.binary, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
