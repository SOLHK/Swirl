#!/usr/bin/env python3
"""Independent zero-glyph CoreText startup experiment with a private-copy control.

The production extractor, replay adapter and rebuilder remain unchanged. Every
probe runs in a fresh process. The two private variants use the same temporary
pathname in sequence, and every raw source table is independently hashed before
checking the native report. Diagnostic completion is never metric acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import struct
import subprocess
import tempfile

from b1_original_metric_check import EXPECTED_SOURCE
from b1_original_vorg_ablation import read_directories, remove_vorg_directories
from b1_metric_discriminator import load_native_json


SCHEMA = "swirl-vf-b1-original-startup-v1"
LABELS = ("system_original", "private_identical", "private_without_vorg", "system_original_repeat")


class StartupEvidenceError(ValueError):
    pass


def require(value, reason):
    if not value:
        raise StartupEvidenceError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def expected_faces(data):
    """Source identities from raw bytes, without fontTools reserialization."""
    cache, result = {}, []
    for face in read_directories(data)["faces"]:
        records = {r["tag"].decode("ascii"): r for r in face["records"]}
        tables = []
        for tag, record in sorted(records.items()):
            key = (record["offset"], record["length"])
            if key not in cache:
                cache[key] = sha(data[key[0]:key[0] + key[1]])
            tables.append({"tag": tag, "length": key[1], "sha256": cache[key]})
        head, maxp = records["head"], records["maxp"]
        require(head["length"] >= 54 and maxp["length"] >= 6, "source_head_maxp_truncated")
        result.append({"face_index": face["face_index"], "expected_tables": tables,
                       "expected_upem": struct.unpack_from(">H", data, head["offset"] + 18)[0],
                       "expected_glyph_count": struct.unpack_from(">H", data, maxp["offset"] + 4)[0],
                       "source_directory_has_vorg": "VORG" in records})
    return result


def unique_index(rows, field, reason):
    require(type(rows) is list and all(type(r) is dict and type(r.get(field)) is int for r in rows), reason)
    result = {r[field]: r for r in rows}
    require(len(result) == len(rows), reason)
    return result


def check_float_bits(value, bits, reason):
    require(type(value) in (int, float) and math.isfinite(value)
            and struct.pack(">d", float(value)).hex() == bits, reason)


def validate_report(report, digest, size, identities):
    """Recompute identity and counters; do not trust native summary booleans."""
    require(type(report) is dict and report.get("schema") == SCHEMA, "invalid_native_schema")
    source = report.get("source", {})
    require(source.get("sha256") == digest and source.get("sha256_after") == digest
            and source.get("size") == size and source.get("size_after") == size
            and source.get("unchanged") is True, "native_source_binding_mismatch")
    require(report.get("status") == "DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE", "native_diagnostic_incomplete")
    require(report.get("raw_face_count") == len(identities), "native_raw_face_count_mismatch")
    faces = unique_index(report.get("faces"), "face_index", "invalid_native_face_set")
    require(set(faces) == {f["face_index"] for f in identities}, "invalid_native_face_set")
    expected = {f["face_index"]: f for f in identities}
    for index, identity in expected.items():
        face = faces[index]
        require(face.get("parse_status") == "PARSED", "native_source_face_parse_failed")
        require(face.get("expected_source_sha256") == digest and face.get("expected_source_size") == size,
                "native_per_face_source_binding_mismatch")
        for key in ("expected_tables", "expected_upem", "expected_glyph_count", "source_directory_has_vorg"):
            require(face.get(key) == identity[key], "native_source_table_identity_mismatch")
    descriptors = unique_index(report.get("descriptors"), "descriptor_index", "invalid_descriptor_set")
    api = report.get("descriptor_api", {})
    require(type(api.get("count")) is int and api["count"] >= 0, "invalid_descriptor_api_count")
    require(api.get("status") in ("NON_NIL", "NIL", "EMPTY", "TYPE_MISMATCH"), "invalid_descriptor_api_status")
    if api["status"] == "NON_NIL":
        require(api["count"] == len(descriptors) and len(descriptors) > 0, "descriptor_count_mismatch")
    else:
        require(not descriptors and (api["status"] == "TYPE_MISMATCH" or api["count"] == 0),
                "descriptor_rejection_invented_instances")
    matched, unambiguous = {i: [] for i in faces}, {i: [] for i in faces}
    bit_count, retained_checks = 0, 0
    for index, descriptor in descriptors.items():
        require(all(type(descriptor.get(key)) is bool for key in (
            "descriptor_url_present", "descriptor_url_matches_source", "font_url_present", "font_url_matches_source")),
            "invalid_source_url_boolean")
        require((not descriptor["descriptor_url_matches_source"] or descriptor["descriptor_url_present"])
                and (not descriptor["font_url_matches_source"] or descriptor["font_url_present"]),
                "missing_source_url_cannot_match")
        check_float_bits(descriptor.get("font_size"), descriptor.get("font_size_binary64_hex"),
                         "native_size_bits_mismatch")
        bit_count += 1
        matrix = descriptor.get("font_matrix", {})
        matrix_bits = descriptor.get("font_matrix_binary64_hex", {})
        require(set(matrix) == set(matrix_bits) == {"xx", "xy", "yx", "yy", "tx", "ty"},
                "invalid_native_matrix")
        for key in matrix:
            check_float_bits(matrix[key], matrix_bits[key], "native_matrix_bits_mismatch")
            bit_count += 1
        vorg = descriptor.get("direct_vorg", {})
        require(type(vorg.get("present")) is bool, "missing_direct_vorg_observation")
        if vorg["present"]:
            require(type(vorg.get("length")) is int and vorg["length"] >= 0
                    and type(vorg.get("sha256")) is str and len(vorg["sha256"]) == 64,
                    "invalid_direct_vorg_observation")
        else:
            require(vorg.get("length") is None and vorg.get("sha256") is None,
                    "nil_vorg_has_invented_data")
        comparisons = unique_index(descriptor.get("face_comparisons"), "face_index", "invalid_face_comparison_set")
        require(set(comparisons) == set(faces), "incomplete_face_comparison_set")
        exact_faces = []
        for face_index, comparison in comparisons.items():
            identity = expected[face_index]
            tables = comparison.get("tables")
            require(type(tables) is list and len(tables) == len(identity["expected_tables"]),
                    "incomplete_retained_table_comparison")
            all_exact = True
            for table, wanted in zip(tables, identity["expected_tables"]):
                require(table.get("tag") == wanted["tag"] and table.get("expected_length") == wanted["length"]
                        and table.get("expected_sha256") == wanted["sha256"], "comparison_source_table_mismatch")
                require(type(table.get("actual_present")) is bool, "missing_table_presence")
                present = table["actual_present"]
                if not present:
                    require(table.get("actual_length") is None and table.get("actual_sha256") is None,
                            "nil_retained_table_has_invented_data")
                length_equal = present and table.get("actual_length") == wanted["length"]
                hash_equal = present and table.get("actual_sha256") == wanted["sha256"]
                exact = length_equal and hash_equal
                require(table.get("length_equal") is length_equal and table.get("sha256_equal") is hash_equal
                        and table.get("exact") is exact, "retained_table_result_mismatch")
                if wanted["tag"] == "VORG":
                    require([present, table.get("actual_length"), table.get("actual_sha256")]
                            == [vorg["present"], vorg.get("length"), vorg.get("sha256")],
                            "direct_vorg_disagrees_with_table_observation")
                all_exact = all_exact and exact
                retained_checks += 1
            upem_equal = descriptor.get("font_upem") == identity["expected_upem"]
            count_equal = descriptor.get("font_glyph_count") == identity["expected_glyph_count"]
            require(comparison.get("all_retained_tables_exact") is all_exact
                    and comparison.get("upem_equal") is upem_equal
                    and comparison.get("glyph_count_equal") is count_equal, "face_comparison_result_mismatch")
            if all_exact and upem_equal and count_equal:
                exact_faces.append(face_index)
                matched[face_index].append(index)
        require(descriptor.get("exact_matching_face_indices") == sorted(exact_faces), "descriptor_binding_result_mismatch")
        if len(exact_faces) == 1:
            unambiguous[exact_faces[0]].append(index)
    verified = ambiguous = unbound = 0
    for index, face in faces.items():
        require(face.get("exact_descriptor_indices") == sorted(matched[index])
                and face.get("unambiguous_descriptor_indices") == sorted(unambiguous[index]),
                "face_binding_result_mismatch")
        if unambiguous[index]:
            verified += 1
        elif matched[index]:
            ambiguous += 1
        else:
            unbound += 1
    summary = report.get("summary", {})
    counters = {"parsed_face_count": len(faces), "identity_verified_face_count": verified,
                "unbound_face_count": unbound, "ambiguous_face_count": ambiguous,
                "descriptor_count": len(descriptors), "metrics_observed": 0}
    require(all(type(summary.get(k)) is int and summary[k] == v for k, v in counters.items()),
            "native_summary_count_mismatch")
    require(summary.get("all_faces_identity_verified") is (verified == len(faces)), "native_acceptance_boolean_mismatch")
    semantics = report.get("startup_semantics", {})
    require(semantics.get("font_registration_called") is False and semantics.get("requested_font_size") == 0
            and semantics.get("requested_identity_matrix") is True
            and semantics.get("table_options_raw_value") == 0, "native_startup_semantics_changed")
    return {"validated": True, "binary64_values_verified": bit_count,
            "retained_table_comparisons_recomputed": retained_checks,
            "source_table_expectations_verified": sum(len(i["expected_tables"]) for i in identities),
            "all_faces_identity_verified": verified == len(faces)}


def summarize_variant(label, raw, validation):
    exact = [d for d in raw["descriptors"] if len(d["exact_matching_face_indices"]) == 1]
    return {"variant": label, "status": "STARTUP_DIAGNOSTIC_VALIDATED_NOT_ACCEPTANCE",
            "source_sha256": raw["source"]["sha256"], "source_byte_size": raw["source"]["size"],
            "descriptor_api": raw["descriptor_api"], "summary": raw["summary"], "validation": validation,
            "error_codes": raw["error_codes"], "exact_bound_descriptor_count": len(exact),
            "bound_descriptor_source_urls_match": all(d["descriptor_url_matches_source"] for d in exact) if exact else None,
            "bound_font_source_urls_match": all(d["font_url_matches_source"] for d in exact) if exact else None,
            "bound_vorg_present_count": sum(d["direct_vorg"]["present"] for d in exact),
            "bound_vorg_nil_count": sum(not d["direct_vorg"]["present"] for d in exact),
            "direct_vorg_by_bound_descriptor": [{"descriptor_index": d["descriptor_index"],
                "face_index": d["exact_matching_face_indices"][0], **d["direct_vorg"]} for d in exact],
            "metric_record_count": 0, "font_acceptance": False}


def classify(variants, repeat_exact):
    """Refusals have no invented metric or VORG-absence conclusion."""
    rows = {v["variant"]: v for v in variants}
    if len(variants) != len(LABELS) or set(rows) != set(LABELS) or any(v.get("status") != "STARTUP_DIAGNOSTIC_VALIDATED_NOT_ACCEPTANCE" for v in variants):
        return "INCOMPLETE_STARTUP_DIAGNOSTICS"
    if not repeat_exact:
        return "ORIGINAL_STARTUP_REPEAT_NOT_EXACT"
    if not all(rows[k]["summary"]["all_faces_identity_verified"] for k in (LABELS[0], LABELS[3])):
        return "SYSTEM_ORIGINAL_STARTUP_NOT_BOUND"
    if not rows["private_identical"]["summary"]["all_faces_identity_verified"]:
        return "PRIVATE_LOCATION_LOAD_OR_BINDING_BLOCKED_VORG_CAUSALITY_UNKNOWN"
    copied = rows["private_identical"]
    if copied["bound_font_source_urls_match"] is not True or copied["bound_descriptor_source_urls_match"] is not True:
        return "PRIVATE_IDENTICAL_TABLES_MATCH_BUT_SOURCE_URL_NOT_EXACT_VORG_CAUSALITY_UNKNOWN"
    ablated = rows["private_without_vorg"]
    if not ablated["summary"]["all_faces_identity_verified"]:
        return "VORG_REMOVAL_ASSOCIATED_WITH_STARTUP_BINDING_FAILURE"
    if ablated["bound_vorg_present_count"]:
        return "REMOVED_DIRECTORY_VORG_STILL_NATIVE_VISIBLE"
    if ablated["bound_font_source_urls_match"] is not True or ablated["bound_descriptor_source_urls_match"] is not True:
        return "RETAINED_TABLES_BOUND_BUT_SOURCE_URL_NOT_EXACT"
    return "PRIVATE_NO_VORG_BOUND_AND_VORG_API_NIL_STARTUP_ONLY"


def execute(source, binary, output, run_process=subprocess.run):
    source, binary, output = Path(source).resolve(), Path(binary).resolve(), Path(output).resolve()
    require(not output.exists(), "output_must_be_new")
    original = source.read_bytes()
    require(sha(original) == EXPECTED_SOURCE, "original_source_hash_mismatch")
    require(binary.is_file(), "startup_probe_binary_required")
    modified, patch = remove_vorg_directories(original)
    identities = {sha(original): expected_faces(original), sha(modified): expected_faces(modified)}
    require(all(len(rows) == 32 for rows in identities.values()), "all_32_physical_faces_required")
    output.mkdir(parents=True)
    report = {"schema_version": 1, "source_commit": os.environ.get("GITHUB_SHA"),
              "platform": platform.platform(), "native_binary_sha256": sha(binary.read_bytes()),
              "production_entrypoints_modified": False, "source_sha256": sha(original),
              "directory_patch_verification": patch, "variants": [], "native_process_count": 0,
              "metric_record_count": 0, "glyph_request_count": 0, "original_font_accepted": False,
              "production_fix_established": False, "original_faces_reconstructed": 0,
              "font_or_outline_payload_published": False,
              "private_path_control": "identical_and_ablated_bytes_written_sequentially_to_one_path_fresh_processes"}
    raws = {}
    with tempfile.TemporaryDirectory(prefix="swirl-b1-startup-") as tmp:
        private = Path(tmp) / "private-source.ttc"
        for label in LABELS:
            data = modified if label == "private_without_vorg" else original
            candidate = source
            if label.startswith("private_"):
                private.write_bytes(data)
                candidate = private
            require(candidate.read_bytes() == data, "source_bytes_before_probe_mismatch")
            try:
                process = run_process([str(binary), str(candidate)], input=b"", capture_output=True, timeout=180)
                report["native_process_count"] += 1
                require(process.returncode == 0, "startup_probe_nonzero_exit")
                raw = load_native_json(process.stdout)
                validation = validate_report(raw, sha(data), len(data), identities[sha(data)])
                require(candidate.read_bytes() == data, "source_bytes_after_probe_mismatch")
                raw_path = output / (label + "-raw.json")
                raw_path.write_bytes(process.stdout)
                variant = summarize_variant(label, raw, validation)
                variant.update(raw_file=raw_path.name, raw_file_sha256=sha(process.stdout),
                               native_stdout_sha256=sha(process.stdout), native_stdout_byte_size=len(process.stdout),
                               native_stderr_sha256=sha(process.stderr), native_stderr_byte_size=len(process.stderr),
                               native_exit_zero=True, native_stdout_saved_byte_exact=True)
                report["variants"].append(variant)
                raws[label] = raw
            except Exception as error:
                report["variants"].append({"variant": label, "status": "STARTUP_DIAGNOSTIC_INVALID_OR_FAILED",
                    "reason": str(error) if isinstance(error, StartupEvidenceError) else type(error).__name__,
                    "metric_record_count": 0, "font_acceptance": False})
        report["private_temporary_files_removed"] = False
    report["private_temporary_files_removed"] = not Path(tmp).exists()
    report["source_unchanged"] = source.read_bytes() == original
    report["original_repeat_exact"] = (LABELS[0] in raws and LABELS[3] in raws and raws[LABELS[0]] == raws[LABELS[3]])
    report["classification"] = classify(report["variants"], report["original_repeat_exact"])
    complete = (report["classification"] not in ("INCOMPLETE_STARTUP_DIAGNOSTICS", "ORIGINAL_STARTUP_REPEAT_NOT_EXACT",
                                                 "SYSTEM_ORIGINAL_STARTUP_NOT_BOUND")
                and report["source_unchanged"] and report["private_temporary_files_removed"])
    report["status"] = "STARTUP_DIAGNOSTICS_COMPLETE_NOT_ACCEPTANCE" if complete else "STARTUP_DIAGNOSTICS_INCOMPLETE_NOT_ACCEPTANCE"
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if platform.system() != "Darwin":
        print("B1_STARTUP_SUMMARY_JSON=" + json.dumps({"status": "NOT_RUN", "reason": "native_CoreText_runtime_required",
                                                        "original_font_accepted": False, "original_faces_reconstructed": 0}))
        return 2
    try:
        report = execute(args.source, args.binary, args.output)
    except Exception as error:
        print("B1_STARTUP_SUMMARY_JSON=" + json.dumps({"status": "NOT_RUN_OR_FAILED",
            "reason": str(error) if isinstance(error, StartupEvidenceError) else type(error).__name__,
            "original_font_accepted": False, "original_faces_reconstructed": 0}))
        return 1
    print("B1_STARTUP_SUMMARY_JSON=" + json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "STARTUP_DIAGNOSTICS_COMPLETE_NOT_ACCEPTANCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
