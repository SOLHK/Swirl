"""Authored archive/report counterexamples, containing no font data."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import axis_mapping_closure_archive as archive


def authored_archive():
    cases, faces = {}, []
    for face in range(32):
        cases[face] = [{"archive_global_request_id": str(face * 2 + index),
            "archive_id": str(face * 2 + index), "archive_position_index": index,
            "location": {"WDTH": 500., "wght": float(200 + face + index * 400), "HGHT": 500.}}
            for index in range(2)]
        q = [-100 + face, 100 + face]
        coords = [archive.coordinate_row(r["archive_global_request_id"], r["location"]) for r in cases[face]]
        faces.append({"face_index": face, "positions": 2, "first_global_request_id": str(face * 2),
            "weight_f2dot14": q, "baseline_disagreement_indices": [1],
            "locations_sha256": archive.digest(coords),
            "observations_sha256": archive.digest([p + [v] for p, v in zip(coords, q)])})
    fixture = {"source_sha256": archive.SOURCE, "physical_faces": 32, "positions": 64,
        "historical_baseline_disagreements": 32, "native_source_commit": "authored_test",
        "run_id": 0, "artifact_id": 0, "artifact_zip_sha256": "authored_test",
        "archive_json_sha256": "authored_test", "faces": faces}
    return cases, fixture


def geometry(gids):
    return [{"glyph_id": gid, "status": "within_budget", "maximum_point_error": 0.,
             "legacy": {"status": "within_budget"}} for gid in gids]


def authored_report(cases, prepared):
    glyphs = [5, 12, 56, 169, 19177]
    modes = []
    for name in archive.MODES:
        faces = []
        for face in range(32):
            rows = []
            for index, case in enumerate(cases[face]):
                q = prepared["faces"][face]["observations"][index]["archived_inferred_f2dot14"]
                # A new construction intentionally changes nonhistorical rows;
                # the reference stays independently authored and unchanged.
                if name != "production" and index == 0:
                    q += 1
                check = {"maximum_horizontal_metric_error": 0., "geometry": geometry(glyphs)}
                if name != "production":
                    check["native_HVF_geometry"] = geometry([5, 19177])
                rows.append({**deepcopy(case), "HVAR_inferred_f2dot14": q,
                    "HVAR_inference": {"geometry_mapping_accepted": False,
                        "within_unchanged_metric_budget": True,
                        "best_fit": {"normalized_weight": q / 16384, "max_metric_residual": 0.}},
                    "declared_model_design_coordinates": {archive.MODEL: {"WDTH": 0., "wght": q / 16384, "HGHT": 0.}},
                    "model_checks": {archive.MODEL: check}})
            faces.append({"face_index": face, "observations": rows})
        modes.append({"mode": name, "status": "COMPLETED_ANCHOR_DIAGNOSIS_NOT_ACCEPTANCE",
            "faces": faces, "replay_batch_checks": 128, "replay_failed_batches": 0,
            "opposite_order_pairs": 640, "opposite_order_exact_pairs": 640})
    return {"status": "COMPLETED_NATIVE_ANCHOR_DIAGNOSIS_NOT_ACCEPTANCE", "source_unchanged": True,
        "source_sha256": archive.SOURCE, "outline_limit_font_units": 1 / 32,
        "mapping_accepted": False, "replay_plan_declared_before_native_launch": True,
        "selected_glyphs": glyphs, "modes": modes}


class MappingClosureArchiveTests(unittest.TestCase):
    def test_real_reference_is_small_hash_bound_and_contains_no_payload(self):
        reference = archive.load_archive()
        self.assertEqual(sum(len(f["weight_f2dot14"]) for f in reference["faces"]), 3048)
        self.assertEqual(sum(len(f["baseline_disagreement_indices"]) for f in reference["faces"]), 141)
        self.assertLess(archive.ARCHIVE_PATH.stat().st_size, 30000)
        text = json.dumps(reference)
        for forbidden in ('"commands"', '"points"', '"advances"', '"advance_width"', '"glyphs"'):
            self.assertNotIn(forbidden, text)
        with patch.object(archive, "ARCHIVE_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "historical_archive_digest_changed"):
                archive.load_archive()

    def test_prepare_preserves_orders_hashes_and_historical_ids_without_mutation(self):
        cases, fixture = authored_archive()
        before = deepcopy((cases, fixture))
        result = archive._prepare(cases, fixture)
        self.assertEqual((cases, fixture), before)
        self.assertEqual(result["archive_positions"], 64)
        self.assertEqual(result["baseline_disagreement_global_request_ids"], [str(i) for i in range(1, 64, 2)])
        self.assertFalse(result["reference_verified"])
        self.assertEqual(result["faces"][0]["observations"][0]["archived_inferred_f2dot14"], -100)

    def test_prepare_rejects_missing_reordered_duplicate_and_changed_user_coordinates(self):
        for mutation, code in (
                (lambda c: c.pop(31), "archive_all_32_faces_required"),
                (lambda c: c[0].pop(), "archive_position_count_changed"),
                (lambda c: c[0].reverse(), "archive_request_order_changed"),
                (lambda c: c[0][1].update(archive_global_request_id="0"), "archive_request_order_changed"),
                (lambda c: c[0][0]["location"].update(WDTH=500.00000000000006), "archive_user_coordinates_changed"),
                (lambda c: c[0][0].pop("archive_global_request_id"), "archive_partial_request_identity")):
            cases, fixture = authored_archive()
            mutation(cases)
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                archive._prepare(cases, fixture)

    def test_actual_reference_q_is_not_substituted_by_a_matching_candidate(self):
        cases, fixture = authored_archive()
        fixture["faces"][0]["weight_f2dot14"][0] += 1
        with self.assertRaisesRegex(ValueError, "archive_axis_observations_changed"):
            archive._prepare(cases, fixture)
        cases, fixture = authored_archive()
        fixture["faces"][0]["baseline_disagreement_indices"] = [1, 1]
        with self.assertRaisesRegex(ValueError, "archive_baseline_indices_invalid"):
            archive._prepare(cases, fixture)

    def test_independent_reproduction_changes_and_actual_native_coverage_are_separate(self):
        cases, fixture = authored_archive()
        prepared = archive._prepare(cases, fixture)
        report = authored_report(cases, prepared)
        before = deepcopy((report, prepared))
        result = archive.audit_archive_modes(report, prepared)
        self.assertEqual((report, prepared), before)
        self.assertFalse(result["mapping_accepted"])
        self.assertFalse(result["continuous_space_accepted"])
        production, endpoint, quarter = result["modes"]
        self.assertTrue(production["original_production_archive_reproduced"])
        self.assertEqual(production["all_archived"]["current_inference_matches_archived_q"], 64)
        self.assertEqual(production["historical_141"]["direct_native_checks"], 0)
        for row in (endpoint, quarter):
            self.assertEqual(row["changed_inferred_q_count"], 32)
            self.assertEqual(row["all_archived"]["candidate_matches_current_inferred_q"], 64)
            self.assertEqual(row["historical_141"]["candidate_matches_archived_inferred_q"], 32)
            self.assertEqual(row["historical_141"]["direct_native_positions"], 32)
            self.assertEqual(row["historical_141"]["direct_native_exact_checks"], 64)
            self.assertEqual(row["historical_unresolved_rows"], [])

    def test_real_numeric_failures_unknown_q_and_replay_failures_stay_visible(self):
        cases, fixture = authored_archive()
        prepared = archive._prepare(cases, fixture)
        report = authored_report(cases, prepared)
        mode = report["modes"][1]
        row = mode["faces"][0]["observations"][1]
        row["HVAR_inferred_f2dot14"] = None
        check = row["model_checks"][archive.MODEL]
        check["maximum_horizontal_metric_error"] = .001  # Within budget, still not exact.
        check["geometry"][0].update(status="outside_budget", maximum_point_error=.25)
        check["native_HVF_geometry"][0].update(status="rejected", maximum_point_error=None)
        mode["replay_failed_batches"] = 2
        mode["opposite_order_exact_pairs"] -= 1
        result = archive.audit_archive_modes(report, prepared)["modes"][1]
        group = result["historical_141"]
        self.assertEqual((group["unavailable_current_inference"], group["portable_failures"], group["direct_native_failures"]), (1, 1, 1))
        self.assertEqual(group["exact_HVAR_positions"], 31)
        self.assertEqual(group["HVAR_positions_outside_1_32"], 0)
        self.assertEqual(len(result["current_model_disagreements"]), 1)
        self.assertEqual(len(result["historical_unresolved_rows"]), 1)
        self.assertEqual(result["all_profile_replay_failed_batches"], 2)
        self.assertEqual(result["all_profile_opposite_order_exact_pairs"], 639)

    def test_missing_direct_native_historical_checks_never_become_full_native_pass(self):
        cases, fixture = authored_archive()
        prepared = archive._prepare(cases, fixture)
        report = authored_report(cases, prepared)
        report["modes"][2]["faces"][0]["observations"][1]["model_checks"][archive.MODEL].pop("native_HVF_geometry")
        row = archive.audit_archive_modes(report, prepared)["modes"][2]
        self.assertEqual(row["historical_141"]["direct_native_positions"], 31)
        self.assertEqual(row["historical_141"]["direct_native_checks"], 62)
        self.assertEqual(len(row["historical_unresolved_rows"]), 1)
        self.assertTrue(row["historical_unresolved_rows"][0]["direct_native_coverage_missing"])

    def test_changed_report_identity_incomplete_reports_and_lost_geometry_are_rejected(self):
        for mutation, code in (
                (lambda r: r.update(status="IN_PROGRESS"), "archive_current_report_incomplete_or_unbound"),
                (lambda r: r.update(source_sha256="0" * 64), "archive_current_report_incomplete_or_unbound"),
                (lambda r: r["modes"][0]["faces"][0]["observations"].pop(), "archive_current_row_count_changed"),
                (lambda r: r["modes"][0]["faces"][0]["observations"].reverse(), "archive_current_request_identity_changed"),
                (lambda r: r["modes"][0]["faces"][0]["observations"][0]["model_checks"][archive.MODEL]["geometry"].pop(), "archive_geometry_coverage_changed"),
                (lambda r: r["modes"][0]["faces"][0]["observations"][0]["HVAR_inference"]["best_fit"].update(normalized_weight=.5), "archive_observed_inference_invalid")):
            cases, fixture = authored_archive()
            prepared = archive._prepare(cases, fixture)
            report = authored_report(cases, prepared)
            mutation(report)
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                archive.audit_archive_modes(report, prepared)


if __name__ == "__main__":
    unittest.main()
