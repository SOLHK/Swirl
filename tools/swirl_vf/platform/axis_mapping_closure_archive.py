"""Bind a new native diagnosis to the historical 3,048 safe axis observations.

The compact archive contains only user-coordinate hashes, HVAR-inferred design
grid integers and the historical baseline's failing indices. No measured
advance or glyph path is stored. Inferred q remains a conditional reference;
geometry, exact HVAR, replay and direct-native coverage are reported separately.
Nothing in this module grants production-oracle or continuous-space acceptance.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


TAGS = ("WDTH", "wght", "HGHT")
SOURCE = "39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890"
MODEL = "canonical_float32_normalized16_truncate"
MODES = ("production", "anchor_endpoint_original", "anchor_quarter_original")
LIMIT = 1 / 32
ARCHIVE_PATH = Path(__file__).resolve().parents[1] / "tests/data/axis_mapping_archive_20261020.json"
ARCHIVE_SHA256 = "3eca463b6eb42df74565b6f25047a93f4dc9e6219d872a4ac070815f1c9b2bc1"


def require(condition, code):
    if not condition:
        raise ValueError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def coordinate_row(global_id, location):
    require(type(global_id) is str and global_id.isascii() and global_id.isdigit()
            and global_id == str(int(global_id)), "invalid_archive_global_id")
    require(isinstance(location, dict) and set(location) == set(TAGS)
            and all(finite(location[tag]) for tag in TAGS), "invalid_archive_user_location")
    return [global_id, *(float(location[tag]).hex() for tag in TAGS)]


def load_archive():
    raw = ARCHIVE_PATH.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ARCHIVE_SHA256, "historical_archive_digest_changed")
    archive = json.loads(raw)
    require(archive["schema"] == 1 and archive["source_sha256"] == SOURCE
            and archive["physical_faces"] == 32 and archive["positions"] == 3048
            and archive["historical_baseline_disagreements"] == 141,
            "historical_archive_identity_changed")
    return archive


def _archived_rows(rows):
    for row in rows:
        keys = set(row) & {"archive_global_request_id", "archive_position_index", "archive_id"}
        require(not keys or {"archive_global_request_id", "archive_position_index"} <= keys,
                "archive_partial_request_identity")
    return [row for row in rows if "archive_global_request_id" in row]


def _prepare(cases, archive):
    """Pure preparation also exercised using an independently authored archive."""
    require(set(cases) == set(range(32)) and all(type(f) is int for f in cases),
            "archive_all_32_faces_required")
    require(archive["source_sha256"] == SOURCE and archive["physical_faces"] == 32
            and [f["face_index"] for f in archive["faces"]] == list(range(32)),
            "archive_face_identity_changed")
    expected, global_ordinal, historical = [], 0, 0
    for reference in archive["faces"]:
        face = reference["face_index"]
        rows = _archived_rows(cases[face])
        count = reference["positions"]
        require(type(count) is int and count > 0 and len(rows) == count
                and len(reference["weight_f2dot14"]) == count,
                "archive_position_count_changed")
        require(reference["first_global_request_id"] == str(global_ordinal), "archive_global_order_changed")
        indices = reference["baseline_disagreement_indices"]
        require(all(type(i) is int and 0 <= i < count for i in indices)
                and indices == sorted(set(indices)), "archive_baseline_indices_invalid")
        require(all(type(q) is int and -16384 <= q <= 16384 for q in reference["weight_f2dot14"]),
                "archive_inferred_grid_invalid")
        coordinates, observations, prepared = [], [], []
        for index, (case, q) in enumerate(zip(rows, reference["weight_f2dot14"])):
            require(type(case.get("archive_position_index")) is int
                    and case["archive_position_index"] == index
                    and case["archive_global_request_id"] == str(global_ordinal),
                    "archive_request_order_changed")
            if "archive_id" in case:
                require(case["archive_id"] == str(global_ordinal), "archive_request_alias_changed")
            coordinate = coordinate_row(str(global_ordinal), case["location"])
            coordinates.append(coordinate)
            observations.append(coordinate + [q])
            prepared.append({"archive_global_request_id": str(global_ordinal),
                "archive_position_index": index, "location": dict(case["location"]),
                "archived_inferred_f2dot14": q, "historical_baseline_disagreement": index in indices})
            global_ordinal += 1
        require(digest(coordinates) == reference["locations_sha256"], "archive_user_coordinates_changed")
        require(digest(observations) == reference["observations_sha256"], "archive_axis_observations_changed")
        expected.append({"face_index": face, "observations": prepared})
        historical += len(indices)
    require(global_ordinal == archive["positions"]
            and historical == archive["historical_baseline_disagreements"], "archive_totals_changed")
    return {"source_sha256": SOURCE, "reference_verified": False,
        "archive_positions": global_ordinal, "historical_baseline_disagreements": historical,
        "baseline_disagreement_global_request_ids": [row["archive_global_request_id"]
            for face in expected for row in face["observations"] if row["historical_baseline_disagreement"]],
        "archive_provenance": {k: archive[k] for k in ("native_source_commit", "run_id", "artifact_id",
                                "artifact_zip_sha256", "archive_json_sha256")},
        "faces": expected}


def prepare_archive(cases):
    """Call before launching any native process; reject altered old requests."""
    prepared = _prepare(cases, load_archive())
    prepared.update(reference_verified=True, archive_fixture_sha256=ARCHIVE_SHA256)
    return prepared


def _counts():
    return {"positions": 0, "candidate_matches_archived_inferred_q": 0,
        "current_inference_matches_archived_q": 0, "candidate_matches_current_inferred_q": 0,
        "unavailable_current_inference": 0, "exact_HVAR_positions": 0,
        "HVAR_positions_outside_1_32": 0, "maximum_HVAR_error": 0.0,
        "portable_checks": 0, "portable_failures": 0, "portable_legacy_failures": 0,
        "maximum_portable_point_error": 0.0, "direct_native_positions": 0,
        "direct_native_checks": 0, "direct_native_exact_checks": 0,
        "direct_native_failures": 0, "direct_native_legacy_failures": 0,
        "maximum_direct_native_point_error": 0.0}


def _check_geometry(entries, expected_gids, stats, prefix):
    require(isinstance(entries, list) and len(entries) == len(expected_gids)
            and {e.get("glyph_id") for e in entries} == set(expected_gids),
            "archive_geometry_coverage_changed")
    for entry in entries:
        status, error = entry.get("status"), entry.get("maximum_point_error")
        require(status in ("within_budget", "outside_budget", "rejected")
                and (error is None or finite(error) and error >= 0), "archive_geometry_verdict_invalid")
        failed = status != "within_budget" or error is None or error > LIMIT
        stats[prefix + "_checks"] += 1
        stats[prefix + "_failures"] += failed
        if error is not None:
            key = "maximum_" + prefix + "_point_error"
            stats[key] = max(stats[key], error)
        legacy = entry.get("legacy", {})
        require(legacy.get("status") in ("within_budget", "outside_budget", "rejected"),
                "archive_legacy_verdict_missing")
        stats[prefix + "_legacy_failures"] += legacy["status"] != "within_budget"
        if prefix == "direct_native":
            stats["direct_native_exact_checks"] += not failed and error == 0


def _accumulate(stats, row, reference, glyphs):
    design = row["declared_model_design_coordinates"][MODEL]
    require(set(design) == set(TAGS) and all(finite(design[t]) and -1 <= design[t] <= 1 for t in TAGS),
            "archive_declared_design_invalid")
    qfloat = design["wght"] * 16384
    require(qfloat == int(qfloat), "archive_candidate_not_f2dot14")
    candidate, observed, old = int(qfloat), row.get("HVAR_inferred_f2dot14"), reference["archived_inferred_f2dot14"]
    if observed is not None:
        require(type(observed) is int and -16384 <= observed <= 16384, "archive_observed_grid_invalid")
        inference = row.get("HVAR_inference", {})
        best = inference.get("best_fit", {})
        value, residual = best.get("normalized_weight"), best.get("max_metric_residual")
        require(inference.get("geometry_mapping_accepted") is False
                and inference.get("within_unchanged_metric_budget") is True
                and finite(value) and abs(value * 16384 - observed) <= 1e-8
                and finite(residual) and 0 <= residual <= LIMIT, "archive_observed_inference_invalid")
    checks = row["model_checks"][MODEL]
    metric_error = checks.get("maximum_horizontal_metric_error")
    require(finite(metric_error) and metric_error >= 0, "archive_HVAR_error_invalid")
    stats["positions"] += 1
    stats["candidate_matches_archived_inferred_q"] += candidate == old
    stats["current_inference_matches_archived_q"] += observed == old
    stats["candidate_matches_current_inferred_q"] += observed is not None and candidate == observed
    stats["unavailable_current_inference"] += observed is None
    stats["exact_HVAR_positions"] += metric_error == 0
    stats["HVAR_positions_outside_1_32"] += metric_error > LIMIT
    stats["maximum_HVAR_error"] = max(stats["maximum_HVAR_error"], metric_error)
    _check_geometry(checks["geometry"], glyphs, stats, "portable")
    native = checks.get("native_HVF_geometry", [])
    if native:
        stats["direct_native_positions"] += 1
        _check_geometry(native, (5, 19177), stats, "direct_native")
    return candidate, observed, metric_error


def audit_archive_modes(report, prepared):
    """Report separate finite comparisons, never a blanket mapping PASS.

    A malformed identity or incomplete report is rejected. Valid observed
    disagreements, missing inferences and geometric failures remain explicit.
    Direct-native counts describe only actually tested rows, including zero.
    """
    require(report.get("status") == "COMPLETED_NATIVE_ANCHOR_DIAGNOSIS_NOT_ACCEPTANCE"
            and report.get("source_unchanged") is True
            and report.get("source_sha256") == prepared["source_sha256"] == SOURCE
            and report.get("outline_limit_font_units") == LIMIT
            and report.get("mapping_accepted") is False
            and report.get("replay_plan_declared_before_native_launch") is True,
            "archive_current_report_incomplete_or_unbound")
    require([m["mode"] for m in report["modes"]] == list(MODES), "archive_constructor_modes_changed")
    glyphs = report["selected_glyphs"]
    require(glyphs == [5, 12, 56, 169, 19177], "archive_selected_glyphs_changed")
    result = {"status": "HISTORICAL_AXIS_COMPARISON_NOT_PRODUCTION_ACCEPTANCE",
        "archive_reference_verified": prepared["reference_verified"],
        "archive_positions": prepared["archive_positions"],
        "historical_baseline_disagreements": prepared["historical_baseline_disagreements"],
        "archive_provenance": prepared["archive_provenance"], "candidate": MODEL,
        "HVAR_inferred_q_is_conditional_not_direct_internal_axis_API": True,
        "mapping_accepted": False, "continuous_space_accepted": False, "modes": []}
    for mode in report["modes"]:
        require(mode["status"] == "COMPLETED_ANCHOR_DIAGNOSIS_NOT_ACCEPTANCE"
                and [f["face_index"] for f in mode["faces"]] == list(range(32)),
                "archive_current_mode_incomplete")
        summary = {"mode": mode["mode"], "all_archived": _counts(), "historical_141": _counts(),
            "inferred_q_changes": [], "current_model_disagreements": [], "historical_unresolved_rows": [],
            "all_profile_replay_batch_checks": mode["replay_batch_checks"],
            "all_profile_replay_failed_batches": mode["replay_failed_batches"],
            "all_profile_opposite_order_pairs": mode["opposite_order_pairs"],
            "all_profile_opposite_order_exact_pairs": mode["opposite_order_exact_pairs"]}
        for face, reference_face in zip(mode["faces"], prepared["faces"]):
            rows = _archived_rows(face["observations"])
            references = reference_face["observations"]
            require(face["face_index"] == reference_face["face_index"] and len(rows) == len(references),
                    "archive_current_row_count_changed")
            for row, reference in zip(rows, references):
                require(row["archive_global_request_id"] == reference["archive_global_request_id"]
                        and type(row.get("archive_position_index")) is int
                        and row["archive_position_index"] == reference["archive_position_index"]
                        and coordinate_row(row["archive_global_request_id"], row["location"])
                            == coordinate_row(reference["archive_global_request_id"], reference["location"]),
                        "archive_current_request_identity_changed")
                before_all = dict(summary["all_archived"])
                candidate, observed, error = _accumulate(summary["all_archived"], row, reference, glyphs)
                current_all = summary["all_archived"]
                detail = {"face_index": face["face_index"], "archive_position_index": reference["archive_position_index"],
                    "archive_global_request_id": reference["archive_global_request_id"],
                    "location": reference["location"], "archived_inferred_f2dot14": reference["archived_inferred_f2dot14"],
                    "current_inferred_f2dot14": observed, "candidate_f2dot14": candidate,
                    "maximum_HVAR_error": error,
                    "portable_failure_count": current_all["portable_failures"] - before_all["portable_failures"],
                    "direct_native_failure_count": current_all["direct_native_failures"] - before_all["direct_native_failures"]}
                if observed != reference["archived_inferred_f2dot14"]:
                    summary["inferred_q_changes"].append(detail)
                if (observed != candidate or error != 0 or detail["portable_failure_count"]
                        or detail["direct_native_failure_count"]):
                    summary["current_model_disagreements"].append(detail)
                if reference["historical_baseline_disagreement"]:
                    before = dict(summary["historical_141"])
                    _accumulate(summary["historical_141"], row, reference, glyphs)
                    current = summary["historical_141"]
                    direct_missing = (mode["mode"] != "production"
                                      and not row["model_checks"][MODEL].get("native_HVF_geometry"))
                    if (candidate != reference["archived_inferred_f2dot14"] or observed != candidate or error != 0
                            or current["portable_failures"] > before["portable_failures"]
                            or current["direct_native_failures"] > before["direct_native_failures"] or direct_missing):
                        summary["historical_unresolved_rows"].append({**detail,
                            "direct_native_coverage_missing": direct_missing})
        require(summary["all_archived"]["positions"] == prepared["archive_positions"]
                and summary["historical_141"]["positions"] == prepared["historical_baseline_disagreements"],
                "archive_current_totals_changed")
        summary["changed_inferred_q_count"] = len(summary["inferred_q_changes"])
        summary["original_production_archive_reproduced"] = (mode["mode"] == "production"
            and not summary["inferred_q_changes"])
        result["modes"].append(summary)
    return result
