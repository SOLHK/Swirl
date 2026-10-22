"""Integrity of independently audited native D1 aggregates; invokes no Windows API.

The immutable reports/archives are cited by hash in the safe summary. CI checks
the retained identities, arithmetic and scope without downloading raw payloads.
The original Face15 contract remains separate from synthetic Windows evidence.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

PLATFORM = Path(__file__).resolve().parents[1] / "platform"
sys.path.insert(0, str(PLATFORM))
from axis_a3_input_cases import representations

EVIDENCE = PLATFORM / "axis_a3_windows_evidence_20261020.json"
CONTRACT = PLATFORM / "axis_a3_windows_contract.json"
NATIVE_SHA = "41504fed7ec7ca6d4768389106a03aa9bc5cd36e"
EVIDENCE_SHA = "4c0fcaf4a66fd34d3487754dd2f849a278da3a3e"
RUN_URL = "https://github.com/SOLHK/Swirl/actions/runs/39401509155"


class WindowsSyntheticEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = EVIDENCE.read_bytes()
        cls.evidence = json.loads(cls.raw)
        cls.contract = json.loads(CONTRACT.read_bytes())

    def assert_unaccepted_scope(self, evidence, contract):
        """Reject promotion of partial synthetic results to original acceptance."""
        self.assertEqual(evidence["status"],
                         "measured_synthetic_partial_evidence_ci_failure_retained")
        self.assertIs(evidence["acceptance"]["windows_synthetic_api_executed"], True)
        for name, value in evidence["acceptance"].items():
            if name != "windows_synthetic_api_executed":
                self.assertIs(value, False, name)
        p = evidence["provenance"]
        self.assertEqual(p["ci_conclusion"], "failure")
        self.assertEqual(p["native_run_status"], "FAILED")
        self.assertEqual(p["analysis_status"], "FAILED_EVIDENCE_ANALYSIS")
        self.assertEqual(p["validated_section_status"], "PARTIAL_EVIDENCE_ONLY")
        self.assertIs(p["d1_full_acceptance"], False)
        self.assertEqual(contract["status"], "unmeasured")
        self.assertIsNone(contract["windows_observations"])
        for name in ("windows_native_tested", "production_mapping_accepted",
                     "continuous_space_accepted", "font_generated"):
            self.assertIs(contract[name], False, name)
        self.assertIs(contract["windows_synthetic_evidence"]["original_contract_accepted"], False)
        for pair in contract["pairs"]:
            self.assertEqual(pair["windows_outcome"], "unmeasured")
        for row in evidence["a3_request_coverage"]:
            self.assertEqual(row["windows_outcome"], "unmeasured")
            self.assertIs(row["original_full_locations_tested"], False)
        for route in evidence["normalized_routes"]:
            self.assertEqual(route["status"], "unmeasured_on_windows")
            self.assertIs(route["direct_native_setter_called"], False)
        for route in contract["alternative_normalized_routes"]:
            self.assertEqual(route["status"], "unmeasured_on_windows")
        self.assertIs(evidence["fixed_object_state_diagnostics"]["primary_failure_waived"], False)

    def test_compact_hash_pointer_does_not_replace_the_original_contract(self):
        pointer = self.contract["windows_synthetic_evidence"]
        self.assertEqual(pointer["path"], EVIDENCE.name)
        self.assertEqual(pointer["sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertIn("synthetic", pointer["scope"])
        self.assertIn("unmeasured", pointer["scope"])
        self.assertLessEqual(CONTRACT.stat().st_size, 12288)
        self.assertEqual(self.evidence["schema_version"], 1)
        self.assertEqual(self.evidence["kind"],
                         "swirl_vf_a3_independent_d1_windows_synthetic_evidence")
        self.assert_unaccepted_scope(self.evidence, self.contract)

    def test_immutable_native_source_and_later_evidence_commit_are_distinct(self):
        p = self.evidence["provenance"]
        self.assertEqual(p["repository"], "SOLHK/Swirl")
        self.assertEqual(p["branch_at_audit"], "work/vf-windows-d1")
        self.assertEqual(p["native_source_commit"], NATIVE_SHA)
        self.assertEqual(p["evidence_commit"], EVIDENCE_SHA)
        self.assertNotEqual(NATIVE_SHA, EVIDENCE_SHA)
        self.assertEqual(p["native_source_url"], f"https://github.com/SOLHK/Swirl/tree/{NATIVE_SHA}")
        self.assertEqual(p["evidence_url"], f"https://github.com/SOLHK/Swirl/tree/{EVIDENCE_SHA}")
        self.assertEqual(p["ci_run_id"], 39401509155)
        self.assertEqual(p["ci_run_url"], RUN_URL)
        self.assertEqual(p["ci_status"], "completed")
        self.assertEqual(p["analysis_error"], "Windows execution has not passed")
        self.assertEqual(p["d1_final_summary_path"],
                         "docs/evidence/SWIRL_VF_WINDOWS_D1_FINAL_20261020.json")
        self.assertEqual(p["d1_final_summary_git_blob_sha1"],
                         "b9ac09e04c786e928712ff0f0b7f2e6ac5f68f1c")
        for key in ("artifacts_independently_sha256_verified",
                    "artifact_reports_match_committed_git_blobs",
                    "raw_jsonl_independently_compared"):
            self.assertIs(p[key], True)
        self.assertEqual({x["path"]: x["sha256"] for x in self.evidence["source_files"]}, {
            "tools/swirl_vf/platform/win_axis_precision_directwrite.cpp":
                "65e1656b32322cf11458a008843a24d2f2f27c04b42a1a89fe5ac7c3dbd7e093",
            "tools/swirl_vf/platform/win_axis_precision_qt.cpp":
                "79cad751da027ec95122a6a4581d9bcea993b72518912f973ebe20d761b334fe",
            "tools/swirl_vf/platform/make_win_axis_precision_fixture.py":
                "03e175660fbf538d4a3eb0c4269390c1881e45e9e0ce3af3dc690a482dd30336",
            "tools/swirl_vf/platform/analyze_win_axis_precision.py":
                "f0362ddb6f2833243ebea2f228909b7f4a679d38cd979e8d3549e4b3dccac89d",
        })

    def test_both_artifacts_and_committed_reports_are_bound_to_the_failed_run(self):
        expected = {
            "windows2022": (118557079537, 12254259788, 3275954,
                            "7825518135349628ab0d0f3a83a54ebab8f57225e281d04daef270b2988343bd",
                            "b742af59a7dd8491376faf20e27f5796507e23ed4f76cb53028a7fa647bd1427",
                            "f2ce5d46c8b1d97af8da9d3bca28f99575a51327", "20348"),
            "windows2025": (118557079179, 12255265257, 3275868,
                            "ca1dc2d7720c81228ba28035efcd6ebe75d2c95c3788617b58b2595229e41c6e",
                            "999e7edb535a1de478c11143bc1ed30454898b050f761b1a715f6fef5a4964b8",
                            "746982b28cbfd8e387f67c8227fa38200f2918a0", "26100"),
        }
        self.assertEqual([a["runtime"] for a in self.evidence["artifacts"]], list(expected))
        for artifact in self.evidence["artifacts"]:
            runtime = artifact["runtime"]
            job, aid, size, archive, report, blob, build = expected[runtime]
            for key, value in (("job_id", job), ("artifact_id", aid), ("zip_bytes", size),
                               ("zip_sha256", archive), ("report_sha256", report),
                               ("committed_report_git_blob_sha1", blob)):
                self.assertEqual(artifact[key], value)
            self.assertEqual(artifact["job_conclusion"], "failure")
            self.assertEqual(artifact["artifact_url"], f"{RUN_URL}/artifacts/{aid}")
            self.assertEqual(artifact["report_path_in_zip"], "d1-evidence/d1-analysis.json")
            year = runtime[-4:]
            self.assertEqual(artifact["committed_report_path"],
                             f"docs/evidence/SWIRL_VF_WINDOWS_D1_SERVER{year}_20261020.json")
            self.assertEqual(artifact["environment"], {
                "windows_product": f"Microsoft Windows Server {year} Datacenter",
                "windows_build": build,
                "dwrite_version": f"10.0.{build}.1 (WinBuild.160101.0800)",
                "qt_sdk": "6.10.3",
            })

    def test_synthetic_axes_and_glyph_identity_do_not_masquerade_as_face15(self):
        fixture = self.evidence["synthetic_fixture"]
        self.assertEqual(fixture["axis_order"], ["wght", "WDTH", "HGHT"])
        self.assertEqual(fixture["axes_min_default_max"],
                         {"wght": [100, 400, 900], "WDTH": [50, 100, 200], "HGHT": [50, 100, 200]})
        self.assertNotEqual(fixture["axes_min_default_max"],
                            self.contract["source_axis_range_verification"]["observed_face15_ranges"])
        self.assertEqual((fixture["units_per_em"], fixture["glyph_count"],
                          fixture["compared_glyph_name"], fixture["compared_glyph_id"]), (1000, 6, "A", 2))
        self.assertIs(fixture["original_apple_font"], False)
        self.assertIs(fixture["original_apple_avar"], False)
        self.assertEqual([f["sha256"] for f in fixture["fonts"]], [
            "1011e838786f1516db99d783bb9b85d962de1783e5cfc20c22fa552db22ed211",
            "1d05d64130cd12a14d8de40e25302b6468cfd4168923ec3319c02edf69cabb47",
        ])
        self.assertEqual([f["bytes"] for f in fixture["fonts"]], [3300, 3384])

    def test_old_weight_pair_preserves_full_tuple_bits_and_unmeasured_face15(self):
        p = self.evidence["old_pair"]
        source_pair = self.contract["pairs"][0]
        self.assertEqual(p["a3_pair_id"], source_pair["id"])
        self.assertEqual(p["d1_case_ids"], ["pair_lo", "pair_hi"])
        self.assertEqual(len(p["requested_full_locations"]), 2)
        for i, location in enumerate(p["requested_full_locations"]):
            source = source_pair["members"][i]["user_location"]
            self.assertEqual(location, {"wght": source["wght"], "WDTH": 100, "HGHT": 100})
            self.assertNotEqual(location, source)
            for tag, value in location.items():
                calc = representations(value)
                self.assertEqual(p["original_binary64_bits"][i][tag], calc["binary64_bits"])
                self.assertEqual(p["identical_float32_bits"][tag], calc["float32_bits"])
                self.assertEqual(p["calculated_fixed16_integers"][i][tag], calc["fixed16_integer"])
                decoded = struct.unpack(">f", bytes.fromhex(calc["float32_bits"]))[0]
                self.assertEqual(p["identical_float32_location"][tag], decoded)
        self.assertNotEqual(p["original_binary64_bits"][0], p["original_binary64_bits"][1])
        self.assertEqual(p["identical_float32_bits"],
                         {"wght": "43f980cb", "WDTH": "42c80000", "HGHT": "42c80000"})
        self.assertIs(p["fixed16_values_are_numeric_calculations_not_native_stage_observations"], True)
        self.assertIs(p["original_a3_full_location_tested"], False)
        trace = self.evidence["input_trace"]
        self.assertIs(trace["directwrite_actual_native_field_pair_equality_checked"], True)
        self.assertIs(trace["directwrite_actual_field_bit_array_serialized"], False)
        self.assertEqual(trace["directwrite_serialized_bits_origin"], "native_recast_of_original_binary64")
        self.assertIs(trace["qt_storage_is_native_face_readback"], False)

    def test_complete_process_counts_exclude_failed_processes_and_do_not_double_pairs(self):
        c = self.evidence["coverage_per_os"]
        groups = c["complete_groups"]
        self.assertEqual([g["api"] for g in groups],
                         ["directwrite", "qt_native_private", "qt_native_installed"])
        self.assertEqual([g["observations_total"] for g in groups], [448, 1872, 1248])
        for g in groups:
            self.assertEqual(g["observations_per_process"],
                             g["cases_per_process"] * g["scenarios_per_case"] * g["passes_per_process"])
            self.assertEqual(g["observations_total"], g["processes"] * g["observations_per_process"])
        self.assertEqual(c["complete_validated_processes"], sum(g["processes"] for g in groups))
        self.assertEqual(c["complete_validated_processes"], 12)
        self.assertEqual(c["complete_observations"], sum(g["observations_total"] for g in groups))
        self.assertEqual(c["complete_observations"], 3568)
        self.assertEqual(c["expected_primary_processes"], 16)
        self.assertEqual(c["expected_primary_processes"],
                         c["complete_validated_processes"] + c["failed_qt_freetype_processes"])
        for key in ("missing_processes", "unexpected_processes", "binding_errors",
                    "opposite_process_comparison_differences",
                    "private_vs_installed_summary_comparison_differences"):
            self.assertEqual(c[key], 0)
        self.assertEqual(c["opposite_process_comparisons"], 6)
        self.assertEqual(c["private_vs_installed_summary_comparisons"], 3)
        self.assertIs(c["failed_process_observations_included_in_complete_counts"], False)
        pair = self.evidence["old_pair"]
        # One low/high comparison per scenario and pass; two observations per pair.
        dwrite, private, installed = groups
        expected_dwrite = dwrite["processes"] * dwrite["passes_per_process"]
        expected_qt = sum(g["processes"] * g["scenarios_per_case"] * g["passes_per_process"]
                          for g in (private, installed))
        self.assertEqual(pair["full_payload_pairs_per_os"], {"directwrite": expected_dwrite, "qt_native": expected_qt})
        self.assertEqual((expected_dwrite, expected_qt), (16, 240))
        self.assertEqual(pair["full_payload_pairs_both_os"], 2 * (expected_dwrite + expected_qt))
        self.assertEqual(pair["full_payload_pairs_both_os"], 512)
        self.assertEqual(pair["different_pairs_both_os"], 0)
        self.assertEqual(pair["saved_directwrite_raster_byte_pairs_per_os"], 8)
        self.assertEqual(pair["saved_directwrite_raster_byte_pair_differences"], 0)
        self.assertEqual(pair["synthetic_gid2_directwrite_advance_font_units"],
                         {"ordinary": [636, 636], "gain": [19000, 19000]})
        cross = self.evidence["cross_os"]
        self.assertEqual(cross["complete_process_pairs"], c["complete_validated_processes"])
        self.assertEqual(cross["full_payload_observation_pairs"], c["complete_observations"])
        self.assertEqual(cross["complete_observations_across_both_os"], 2 * c["complete_observations"])
        self.assertEqual(cross["different_observation_pairs"], 0)

    def test_failed_freetype_and_fixed_object_state_results_remain_diagnostic(self):
        f = self.evidence["qt_freetype_failures"]
        self.assertEqual((f["processes_per_os"], f["processes_both_os"]), (4, 8))
        self.assertEqual(f["processes_per_os"], self.evidence["coverage_per_os"]["failed_qt_freetype_processes"])
        self.assertEqual(f["status"], "FAILED")
        self.assertEqual(f["exit_code_each"], 1)
        self.assertIs(f["timeout_each"], False)
        self.assertEqual(f["observations_before_failure_each"], 13)
        self.assertEqual(f["completed_full_replay_checks_each"], 0)
        self.assertEqual(f["completed_pair_comparisons_each"], 0)
        self.assertEqual(f["failed_pair_comparison_records_each"], 1)
        self.assertEqual(f["native_error"], "Identical API inputs produced different actual pair outputs")
        self.assertIs(f["primary_failures_retained"], True)
        self.assertIs(f["windows_normalized_setter_tested"], False)
        d = self.evidence["fixed_object_state_diagnostics"]
        self.assertEqual(d["status"], "DIAGNOSTIC_COMPLETED_NOT_ACCEPTANCE")
        self.assertEqual(d["processes_both_os"], f["processes_both_os"])
        self.assertEqual(d["observations_each"], 9)
        self.assertEqual(d["observations_total"], d["processes_both_os"] * d["observations_each"])
        self.assertEqual(d["requested_full_location"], self.evidence["old_pair"]["requested_full_locations"][0])
        self.assertEqual(d["weight_float32_bits"], "43f980cb")
        for key in ("fixed_raw_object_each", "fixed_axis_request_each", "all_advances_equal_each"):
            self.assertIs(d[key], True)
        self.assertEqual(d["distinct_path_shapes_each"], 3)
        self.assertEqual(d["path_changed_after_raster_count_each"], 2)
        self.assertEqual(d["path_changed_after_advance_count_each"], 0)
        self.assertEqual(d["horizontal_advance_pixels"], 7.625)
        for key in ("primary_failure_waived", "decimal_precision_preservation_proven",
                    "private_backend_state_inspected", "system_cache_reset_claimed"):
            self.assertIs(d[key], False)

    def test_new_a3_pair_requests_and_normalized_routes_are_still_missing(self):
        coverage = self.evidence["a3_request_coverage"]
        self.assertEqual([p["pair_id"] for p in coverage], [p["id"] for p in self.contract["pairs"]])
        self.assertEqual([p["original_wght_members_submitted_to_d1"] for p in coverage],
                         [[True, True], [False, False], [False, True]])
        missing_bits = []
        for row, pair in zip(coverage, self.contract["pairs"]):
            for present, member in zip(row["original_wght_members_submitted_to_d1"], pair["members"]):
                if not present:
                    missing_bits.append(member["representations"]["wght"]["binary64_bits"])
        self.assertEqual(self.evidence["unmeasured_original_wght_binary64_bits"], missing_bits)
        for row, route in zip(self.evidence["normalized_routes"], self.contract["alternative_normalized_routes"]):
            self.assertEqual(row["id"], route["id"])
            self.assertEqual(row["api"], route["api"])
            self.assertEqual(row["status"], route["status"])
        self.assertEqual(len(self.evidence["normalized_routes"]), 2)
        self.assertIs(self.contract["linux_normalized_channel_evidence"]["windows_tested"], False)

    def test_strict_apple_bound_is_retained_without_importing_synthetic_metrics(self):
        strict = self.evidence["strict_source_contract"]
        tolerance = self.contract["tolerance"]
        for key in ("advance_font_units", "outline_font_units", "may_be_relaxed"):
            self.assertEqual(strict[key], tolerance[key])
        self.assertEqual(strict["advance_font_units"], 1 / 32)
        delta = strict["source_gid5_difference_font_units"]
        self.assertEqual(delta, self.contract["historical_coretext_counterpart"]["glyph5_absolute_advance_difference_font_units"])
        bound = Fraction(delta) / 2
        self.assertEqual(bound, Fraction(4485, 16384))
        self.assertEqual(strict["conditional_minimum_worst_case_error_font_units"], float(bound))
        self.assertEqual(bound, Fraction(self.contract["conditional_bound"]["minimum_worst_case_error"]))
        self.assertIs(strict["bound_is_deterministic_identical_state_condition_only"], True)
        self.assertIs(strict["d1_synthetic_metrics_used_as_apple_metrics"], False)

    def test_acceptance_promotions_are_rejected(self):
        # These mutations represent the precise overclaims the handoff must block.
        mutations = [
            ("contract", ("status",), "accepted"),
            ("contract", ("windows_native_tested",), True),
            ("contract", ("windows_observations",), {}),
            ("contract", ("production_mapping_accepted",), True),
            ("contract", ("pairs", 0, "windows_outcome"), "passed"),
            ("contract", ("alternative_normalized_routes", 0, "status"), "passed"),
            ("contract", ("windows_synthetic_evidence", "original_contract_accepted"), True),
            ("evidence", ("acceptance", "original_a3_contract_accepted"), True),
            ("evidence", ("acceptance", "original_apple_face15_tested_on_windows"), True),
            ("evidence", ("acceptance", "windows_normalized_routes_tested"), True),
            ("evidence", ("provenance", "ci_conclusion"), "success"),
            ("evidence", ("provenance", "d1_full_acceptance"), True),
            ("evidence", ("a3_request_coverage", 0, "original_full_locations_tested"), True),
            ("evidence", ("normalized_routes", 0, "direct_native_setter_called"), True),
            ("evidence", ("fixed_object_state_diagnostics", "primary_failure_waived"), True),
        ]
        for target, path, value in mutations:
            with self.subTest(target=target, path=path):
                e, c = deepcopy(self.evidence), deepcopy(self.contract)
                obj = e if target == "evidence" else c
                for key in path[:-1]:
                    obj = obj[key]
                obj[path[-1]] = value
                with self.assertRaises(AssertionError):
                    self.assert_unaccepted_scope(e, c)

    def test_summary_contains_no_native_payload_or_archive(self):
        self.assertEqual(self.evidence["safety"], {
            "aggregate_only": True, "raw_native_payload_embedded": False,
            "apple_font_or_outline_embedded": False, "artifact_archive_embedded": False,
        })
        forbidden = {"payload", "outline", "path_px", "before_path_px", "after_raster_path_px",
                     "after_advance_path_px", "raster", "bitmap", "pixels", "font_bytes", "base64"}

        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
            elif isinstance(value, str):
                self.assertFalse(value.startswith("data:"))
                self.assertLess(len(value), 700)

        inspect(self.evidence)
        self.assertLess(len(self.raw), 20000)


if __name__ == "__main__":
    unittest.main()
