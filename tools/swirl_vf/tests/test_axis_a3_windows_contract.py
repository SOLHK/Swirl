"""Frozen Apple/Linux evidence and handoff integrity; no Windows invocation."""
from fractions import Fraction
import json
from pathlib import Path
import struct
import sys
import unittest

PLATFORM = Path(__file__).resolve().parents[1] / "platform"
sys.path.insert(0, str(PLATFORM))
from axis_a3_input_cases import TAGS, conditional_lower_bound, input_cases, representations

CONTRACT = PLATFORM / "axis_a3_windows_contract.json"


class WindowsInputContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = CONTRACT.read_bytes()
        cls.contract = json.loads(cls.raw)

    def test_contract_is_compact_and_does_not_claim_windows_execution(self):
        r = self.contract
        self.assertLessEqual(len(self.raw), 12288)
        self.assertEqual(r["schema_version"], 1)
        self.assertEqual(r["status"], "unmeasured")
        self.assertIsNone(r["windows_observations"])
        for key in ("windows_native_tested", "production_mapping_accepted",
                    "continuous_space_accepted", "font_generated"):
            self.assertIs(r[key], False)
        self.assertTrue(r["provenance"]["numeric_values_are_representation_calculations_not_windows_observations"])
        for pair in r["pairs"]:
            self.assertEqual(pair["windows_outcome"], "unmeasured")
            self.assertIsInstance(pair["new_coretext_construction_outcome"], dict)

    def test_provenance_binds_measured_apple_evidence_to_full_commits_and_hashes(self):
        p = self.contract["provenance"]
        self.assertEqual(p["original_evidence_commit"], "53ca5ff74e17bfc65e338b460fa2fc4df3801c1d")
        self.assertEqual(p["new_a3_construction_commit"], "924734943b1da5550c5093a2ae7c50957778fc4d")
        self.assertEqual(p["new_a3_construction_status"], "measured_diagnosis_not_acceptance")
        self.assertEqual(p["new_a3_construction_run"], "https://github.com/SOLHK/Swirl/actions/runs/39399731052")
        self.assertEqual(p["new_a3_construction_artifact_id"], 12254397206)
        self.assertEqual(p["new_a3_construction_report_sha256"],
                         "8975437638198b3a8e851e82ca17c23666c17d05ddfd7f9b9c5e837b7a4a4a71")
        self.assertEqual(p["new_a3_construction_zip_sha256"],
                         "0828f7208319b95c4c693b8ba86a6444332fb1b3c85667b9e78b6456b4226b36")
        self.assertEqual(p["original_source_face_index"], 15)
        self.assertEqual(p["original_source_sha256"], "39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890")
        self.assertEqual(self.contract["axis_order"], list(TAGS))

    def test_face15_ranges_are_verified_in_its_own_native_metadata(self):
        r = self.contract
        self.assertEqual(r["confirmed_source_defaults"], {"WDTH": 500., "wght": 499., "HGHT": 500.})
        verified = r["source_axis_range_verification"]
        self.assertTrue(verified["preserve_original_ranges_tags_and_avar_order"])
        self.assertEqual(verified["status"], "verified_native_metadata")
        self.assertEqual(verified["observed_face15_ranges"],
                         {"WDTH": [1., 500., 1000.], "wght": [100., 499., 900.], "HGHT": [1., 500., 1000.]})
        self.assertEqual(verified["observed_face15_ranges"], r["generation_axis_ranges_fixture"])
        self.assertEqual(verified["artifact_sha256"], r["provenance"]["new_a3_construction_report_sha256"])

    def test_all_three_pairs_match_frozen_case_generator_and_full_axis_bits(self):
        r = self.contract
        generated = {row["label"]: row for row in input_cases({15: r["generation_axis_ranges_fixture"]})}
        self.assertEqual([pair["id"] for pair in r["pairs"]],
                         ["existing_collision", "fixed_only_collision", "float32_only_collision"])
        for pair in r["pairs"]:
            self.assertEqual(len(pair["members"]), 2)
            for member in pair["members"]:
                self.assertEqual(member["user_location"], generated[member["label"]]["location"])
                self.assertEqual(set(member["representations"]), set(TAGS))
                self.assertEqual(set(member["user_location"]), set(TAGS))
                for tag in TAGS:
                    actual = representations(member["user_location"][tag])
                    for key, value in member["representations"][tag].items():
                        self.assertEqual(value, actual[key])

    def test_partition_promises_follow_actual_bit_patterns_not_decimal_labels(self):
        required = {
            "existing_collision": (False, True, True),
            "fixed_only_collision": (False, True, False),
            "float32_only_collision": (False, False, True),
        }
        keys = ("binary64_bits", "fixed16_integer", "float32_bits")
        partition_keys = ("binary64_equal", "fixed16_equal", "float32_equal")
        for pair in self.contract["pairs"]:
            left, right = [member["representations"] for member in pair["members"]]
            measured_partition = tuple(all(left[tag][key] == right[tag][key] for tag in TAGS) for key in keys)
            self.assertEqual(measured_partition, required[pair["id"]])
            self.assertEqual(tuple(pair["expected_full_location_partition"][key] for key in partition_keys), measured_partition)
        first = self.contract["pairs"][0]["members"]
        self.assertEqual([x["representations"]["wght"]["binary64_bits"] for x in first],
                         ["407f3019641f6449", "407f30196638433d"])
        self.assertEqual([x["representations"]["wght"]["float32_bits"] for x in first], ["43f980cb"] * 2)
        self.assertEqual([x["representations"]["wght"]["fixed16_integer"] for x in first], [32702870] * 2)
        for pair in self.contract["pairs"]:
            for member in pair["members"]:
                for tag in TAGS:
                    bits = member["representations"][tag]["binary64_bits"]
                    self.assertEqual(struct.unpack(">d", bytes.fromhex(bits))[0], member["user_location"][tag])

    def test_bound_is_exact_and_preserves_the_strict_threshold(self):
        r = self.contract
        source = r["historical_coretext_counterpart"]
        delta = source["glyph5_absolute_advance_difference_font_units"]
        self.assertEqual(delta, 0.5474853515625)
        self.assertEqual(r["conditional_bound"], conditional_lower_bound(delta))
        bound = Fraction(delta) / 2
        self.assertEqual(bound, Fraction(0.27374267578125))
        self.assertEqual(bound / Fraction(1 / 32), Fraction(8.759765625))
        self.assertIs(r["conditional_bound"]["native_measurement_performed"], False)
        self.assertEqual(r["tolerance"], {"advance_font_units": 1 / 32, "outline_font_units": 1 / 32, "may_be_relaxed": False})

    def test_source_echo_is_separate_from_user_input_and_inferred_design_q(self):
        source = self.contract["historical_coretext_counterpart"]
        requests = [m["user_location"]["wght"] for m in self.contract["pairs"][0]["members"]]
        self.assertEqual(source["source_request_wght"], requests)
        self.assertEqual(source["reported_user_wght"], [499.0061, 499.0062])
        self.assertEqual(source["HVAR_inferred_design_wght_f2dot14"], [0, 65])
        self.assertNotEqual(source["source_request_wght"], source["reported_user_wght"])
        self.assertTrue(source["design_q_is_not_CTFontCopyVariation_user_readback"])
        checks = {row["id"]: row for row in self.contract["required_windows_checks"]}
        self.assertEqual(checks["actual_FLOAT_submitted_bits"]["api"], "DWRITE_FONT_AXIS_VALUE.value (FLOAT)")
        self.assertIn("bit_cast/memcpy", checks["actual_FLOAT_submitted_bits"]["requirement"])
        self.assertIn("actual API input bits", checks["source_vs_target_coordinate_stages"]["requirement"])
        self.assertIn("real_glyph_output", checks)
        self.assertIn("repetition_and_order", checks)
        self.assertIn("failure_and_scope", checks)

    def test_measured_apple_matrix_retains_original_split_and_float32_created_split(self):
        native = self.contract["coretext_construction"]
        self.assertEqual(native["selected_glyphs"], [5, 12, 56, 169, 19177])
        self.assertEqual(native["mode_groups"], {
            "binary64": ["copy_binary64", "anchor_binary64", "descriptor_bulk_binary64",
                         "descriptor_forward_binary64", "descriptor_reverse_binary64"],
            "float32": ["anchor_binary32", "copy_cfnumber_float32"],
            "fixed16": ["anchor_fixed16"], "graphics": ["graphics_binary64"],
        })
        self.assertEqual(native["pair_result_columns"], [
            "HVAR_inferred_wght_q", "reported_user_wght", "gid5_absolute_advance_delta",
            "payload_different_glyphs", "submitted_inputs_identical",
        ])
        measured = {p["id"]: p["new_coretext_construction_outcome"] for p in self.contract["pairs"]}
        # Frozen observations from the cited report, not predictions from input bits.
        self.assertEqual(measured["existing_collision"], {
            "binary64": [[0, 65], [499.0061, 499.0062], 0.5474853515625, 5, False],
            "float32": [[0, 0], [499.0061, 499.0061], 0, 0, True],
            "fixed16": [[0, 0], [499.0061, 499.0061], 0, 0, True],
            "graphics": [[0, 0], [None, None], 0, 0, False],
        })
        self.assertEqual(measured["fixed_only_collision"], {
            "binary64": [[65, 65], [499.0062, 499.0062], 0, 0, False],
            "float32": [[0, 65], [499.0061, 499.0062], 0.5474853515625, 5, False],
            "fixed16": [[65, 65], [499.0062, 499.0062], 0, 0, True],
            "graphics": [[0, 0], [None, None], 0, 0, False],
        })
        self.assertEqual(measured["float32_only_collision"], {
            "binary64": [[0, 0], [499.0061, 499.0061], 0, 0, False],
            "float32": [[0, 0], [499.0061, 499.0061], 0, 0, True],
            "fixed16": [[0, 0], [499.0061, 499.0061], 0, 0, False],
            "graphics": [[0, 0], [None, None], 0, 0, False],
        })
        self.assertIn("q inferred", native["scope"])
        self.assertIn("do not prove float32 coercion", native["graphics_warning"])

    def test_native_completion_retains_readback_failures_and_cache_scope(self):
        native = self.contract["coretext_construction"]
        self.assertEqual(native["native_scalar_checked_values"], 306)
        self.assertIs(native["native_scalar_bits_match"], True)
        self.assertEqual(native["native_records"], 18000)
        modes = [mode for group in native["mode_groups"].values() for mode in group]
        self.assertEqual(len(modes), 9)
        self.assertEqual(len(set(modes)), 9)
        self.assertEqual(native["replay_checks_per_mode"], 200)
        self.assertEqual(native["replay_failures_by_group"],
                         {"binary64": 56, "float32": 154, "fixed16": 120, "graphics": 166})
        self.assertIn("native_nondefault_axis_not_reported only", native["binary64_replay_failure_detail"])
        self.assertIn("payload unchanged", native["binary64_replay_failure_detail"])
        self.assertIn("Failures retained", native["binary64_replay_failure_detail"])
        self.assertEqual(native["opposite_order_exact_pairs_per_mode"], 1000)
        self.assertIs(native["system_cache_reset_claimed"], False)

    def test_normalized_alternatives_remain_unmeasured_on_windows(self):
        routes = {row["id"]: row for row in self.contract["alternative_normalized_routes"]}
        ft, hb = routes["freetype_normalized"], routes["harfbuzz_normalized"]
        self.assertEqual(ft["api"], "FT_Set_Var_Blend_Coordinates")
        self.assertEqual(hb["api"], "hb_font_set_var_coords_normalized")
        self.assertEqual(hb["known_pair_axis_vectors"], [[0, 0, 0], [0, 65, 0]])
        self.assertEqual(ft["known_pair_axis_vectors"], [[4 * q for q in vector] for vector in hb["known_pair_axis_vectors"]])
        for route in routes.values():
            self.assertEqual(route["status"], "unmeasured_on_windows")
            self.assertTrue(route["official_reference"].startswith("https://"))
        self.assertEqual(ft["linux_evidence_reference"], "#/linux_normalized_channel_evidence/freetype")
        self.assertEqual(hb["linux_evidence_reference"], "#/linux_normalized_channel_evidence/harfbuzz")

    def test_linux_native_evidence_proves_external_q_transport_only(self):
        linux = self.contract["linux_normalized_channel_evidence"]
        self.assertEqual(linux["status"], "measured_synthetic_linux_transport_only")
        self.assertEqual(linux["source_commit"], "d22be86b56cd20a257505be569a21fcea3ef2bbf")
        self.assertEqual(linux["ci_run"], "https://github.com/SOLHK/Swirl/actions/runs/39400961369")
        self.assertEqual(linux["report_sha256"],
                         "35c10f6327b9ec5aace54e2a628ee61d22c29a4cb5f6e40fb8932cde14613a32")
        self.assertEqual(linux["platform"], "Linux x86_64")
        self.assertIs(linux["synthetic_only"], True)
        self.assertEqual(linux["externally_supplied_q"], [0, 65])
        self.assertIn("does not derive q", linux["scope"])
        for key in ("general_source_mapper_proven", "apple_tested", "windows_tested",
                    "directwrite_tested", "production_mapping_accepted"):
            self.assertIs(linux[key], False)
        hb, ft = linux["harfbuzz"], linux["freetype"]
        self.assertEqual(hb["version"], "8.3.0")
        self.assertEqual(hb["normalized_f2dot14_readback"], [[0, 0, 0], [0, 65, 0]])
        self.assertEqual(hb["synthetic_gid1_native_advance_font_units"], [500, 565])
        self.assertIs(hb["design_float32_output_collision"], True)
        self.assertEqual(ft["version"], "2.13.2")
        self.assertEqual(ft["normalized_16_16_readback"], [[0, 0, 0], [0, 260, 0]])
        self.assertIs(ft["glyph_metric_tested"], False)


if __name__ == "__main__":
    unittest.main()
