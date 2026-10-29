"""Offline integrity and non-acceptance guards for real A3 CI evidence.

These tests read the original artifact bytes; they do not rerun CoreText or
replace native observations with Python predictions. ZIP member/size checks use
the standard-library interface documented in the primary upstream reference:
https://github.com/python/cpython/blob/main/Doc/library/zipfile.rst
"""

import hashlib
import json
import math
from pathlib import Path
import unittest
import zipfile


PLATFORM = Path(__file__).resolve().parents[1] / "platform"
MANIFEST = PLATFORM / "axis_a3_evidence_manifest_20261020.json"
LIMIT = 1 / 32
OLD_DOUBLE = "canonical_normalized16_truncate"
OLD_FLOAT = "canonical_float32_normalized16_truncate"
NEAREST = "canonical_float32_result_normalized16_nearest"
EXPECTED_IDS = {
    "resolution_53ca5ff", "hvar_22a89a1", "construction_9247349",
    "identity_0c603aa", "construction_9dd2676", "normalized_d22be86",
}
FORBIDDEN_RAW_KEYS = {
    "commands", "raw_commands", "points", "control_points", "contours",
    "outline", "outlines", "outline_commands", "raw_outline", "raw_outlines",
    "raw_metrics", "font_bytes", "font_data", "font_base64", "source_font_bytes",
}
ORIGINAL_METRIC_KEYS = {
    "advance_width", "advance_height", "bounds", "lsb", "rsb", "tsb", "bsb",
    "horizontal_origin_x", "horizontal_origin_y", "vertical_origin_x",
    "vertical_origin_y", "horizontal_advance_sum", "vertical_advance_sum",
    "horizontal_advance_vector", "vertical_advance_vector",
    "vertical_origin_translation",
}
FALSE_FLAGS = {
    "font_generated", "production_mapping_changed", "production_constructor_changed",
    "source_outlines_or_raw_metrics_published", "original_avar_records_modified",
    "raw_avar_records_modified", "original_141_subset_rerun", "windows_native_tested",
    "standard_format_impossibility_proved", "general_source_mapper_proven",
    "apple_source_font_read", "source_outlines_used", "source_font_or_synthetic_font_written",
    "windows_tested", "apple_tested", "Apple_or_Windows_acceptance",
}


def fields(value, path=()):
    """Yield dictionary fields, including fields inside arbitrarily nested lists."""
    if isinstance(value, dict):
        for key, child in value.items():
            yield path, key, child
            yield from fields(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from fields(child, path + (str(index),))


def unsafe_fields(value):
    violations = []
    for path, key, child in fields(value):
        if key.casefold() in FORBIDDEN_RAW_KEYS:
            violations.append(path + (key,))
        if key.casefold() in ORIGINAL_METRIC_KEYS:
            # Only a scalar difference is public, never a source metric or vector.
            if (not path or path[-1] != "metric_differences"
                    or type(child) not in (int, float) or not math.isfinite(child)):
                violations.append(path + (key,))
    return violations


def labelled(rows, label):
    return next(row for row in rows if row["label"] == label)


def glyph(rows, gid):
    return next(row for row in rows if row["glyph_id"] == gid)


class AxisA3EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_bytes())
        cls.entries = {entry["id"]: entry for entry in cls.manifest["archives"]}
        cls.report_bytes, cls.reports = {}, {}
        for identifier, entry in cls.entries.items():
            with zipfile.ZipFile(PLATFORM / entry["archive"]) as archive:
                data = archive.read(entry["report_member"])
            cls.report_bytes[identifier] = data
            cls.reports[identifier] = json.loads(data)

    def test_exact_artifact_bytes_sizes_and_single_json_members(self):
        self.assertEqual(set(self.entries), EXPECTED_IDS)
        self.assertEqual(len(self.entries), len(self.manifest["archives"]))
        self.assertEqual(
            {p.name for p in PLATFORM.glob("axis_a3_native_*.zip")},
            {entry["archive"] for entry in self.entries.values()},
        )
        for identifier, entry in self.entries.items():
            with self.subTest(archive=identifier):
                self.assertEqual(entry["archive"], f"axis_a3_native_{identifier}.zip")
                member = entry["report_member"]
                self.assertEqual(Path(member).name, member)
                self.assertEqual(Path(member).suffix, ".json")
                data = (PLATFORM / entry["archive"]).read_bytes()
                self.assertEqual(len(data), entry["archive_bytes"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry["archive_sha256"])
                with zipfile.ZipFile(PLATFORM / entry["archive"]) as archive:
                    self.assertEqual(archive.namelist(), [member])
                    info = archive.getinfo(member)
                    self.assertFalse(info.is_dir())
                    self.assertFalse(info.flag_bits & 1, "Encrypted evidence is not reviewable")
                    self.assertEqual(info.file_size, entry["report_bytes"])
                report_bytes = self.report_bytes[identifier]
                self.assertEqual(len(report_bytes), entry["report_bytes"])
                self.assertEqual(hashlib.sha256(report_bytes).hexdigest(), entry["report_sha256"])

    def test_ci_commit_binding_complete_transport_and_diagnostic_only_flags(self):
        self.assertEqual(self.manifest["strict_limit_font_units"], LIMIT)
        for identifier, entry in self.entries.items():
            report = self.reports[identifier]
            with self.subTest(archive=identifier):
                self.assertRegex(entry["source_commit"], r"^[0-9a-f]{40}$")
                self.assertTrue(entry["source_commit"].startswith(identifier.rsplit("_", 1)[1]))
                self.assertEqual(report["source_commit"], entry["source_commit"])
                self.assertEqual(entry["ci_url"],
                                 f"https://github.com/SOLHK/Swirl/actions/runs/{entry['ci_run_id']}")
                self.assertGreater(entry["ci_run_id"], 0)
                self.assertGreater(entry["artifact_id"], 0)
                self.assertEqual(entry["ci_conclusion"], "success")
                self.assertEqual(report["status"], entry["reported_status"])
                self.assertIn("NOT_ACCEPTANCE" if "native_processes" in report
                              else "NOT_APPLE_OR_WINDOWS_ACCEPTANCE", report["status"])
                if "native_processes" not in report:
                    continue  # Synthetic Linux API calls have their own evidence below.
                self.assertEqual(report["source_sha256"], self.manifest["original_source_sha256"])
                self.assertIs(report["source_unchanged"], True)
                processes = report["native_processes"]
                self.assertEqual(len(processes), entry["native_processes"])
                records = sum(p["summary"]["successful_glyph_count"] for p in processes)
                self.assertEqual(records, entry["native_records"])
                self.assertEqual(records, report["planned_native_records"])
                if "actual_native_records" in report:
                    self.assertEqual(records, report["actual_native_records"])
                self.assertEqual(len(report["cases"]), entry["labelled_cases"])
                for process in processes:
                    self.assertEqual(process["exit_status"], 0)
                    self.assertEqual(process["summary"]["error_count"], 0)
                    self.assertIs(process["all_32_physical_faces_verified"], True)
                    self.assertEqual(process["summary"]["source_sha256"], report["source_sha256"])
                    self.assertEqual(process["summary"]["successful_glyph_count"],
                                     process["summary"]["request_count"] * len(report["selected_glyphs"]))
                for case in report["cases"]:
                    self.assertEqual(set(case["location"]), {"WDTH", "wght", "HGHT"})
        for identifier, document in [("manifest", self.manifest), *self.reports.items()]:
            for path, key, value in fields(document):
                if key in FALSE_FLAGS or key.endswith("_accepted"):
                    self.assertIs(value, False, (identifier, path, key))
                if key in {"outline_limit_font_units", "metric_limit_font_units", "limit_font_units", "limit"}:
                    self.assertEqual(value, LIMIT, (identifier, path, key))

    def test_recursive_privacy_guard_permits_only_scalar_metric_differences(self):
        for identifier, report in self.reports.items():
            self.assertEqual(unsafe_fields(report), [], identifier)
        # Authored negative controls ensure the scanner reaches nested lists and
        # does not trust a safe-looking enclosing key or a publication flag.
        for key in ("commands", "raw_commands", "points", "contours", "font_bytes"):
            self.assertTrue(unsafe_fields({"nested": [{key: []}]}), key)
        self.assertTrue(unsafe_fields({"nested": [{"advance_width": 500}]}))
        self.assertTrue(unsafe_fields({"nested": [{"bounds": [1, 2, 3, 4]}]}))
        self.assertTrue(unsafe_fields({"metric_differences": {"advance_width": [500, 501]}}))
        self.assertEqual(unsafe_fields({"nested": [{"metric_differences": {"advance_width": .5}}]}), [])

    def test_constructor_repeat_changes_only_commit_and_retains_replay_failures(self):
        relation = self.manifest["construction_repeat_relation"]
        first = self.reports[relation["first"]]
        repeat = self.reports[relation["repeat"]]
        self.assertEqual(relation["only_different_top_level_field"], "source_commit")
        self.assertNotEqual(first["source_commit"], repeat["source_commit"])
        self.assertEqual({k: v for k, v in first.items() if k != "source_commit"},
                         {k: v for k, v in repeat.items() if k != "source_commit"})
        self.assertTrue(any(mode["replay_failed_batches"] > 0 for mode in repeat["modes"]))
        for mode in repeat["modes"]:
            self.assertEqual(mode["opposite_order_pairs"], mode["opposite_order_exact_pairs"])
            self.assertEqual(mode["replay_failed_batches"], len(mode["replay_failures"]))
        # A successful rerun means complete diagnostics, including these failures.
        self.assertIs(repeat["mapping_accepted"], False)

    def test_archived_collision_still_exceeds_the_strict_simultaneous_error_bound(self):
        report = self.reports["resolution_53ca5ff"]
        low, high = (labelled(report["cases"], label) for label in ("collision_low", "collision_high"))
        self.assertEqual((low["location"]["wght"], high["location"]["wght"]),
                         (499.006199, 499.006201))
        self.assertNotEqual(low["binary64_hex"]["wght"], high["binary64_hex"]["wght"])
        for case in (low, high):
            self.assertEqual(case["standard_fixed16_input_integers"]["wght"], 32702870)
            self.assertEqual(math.floor(case["location"]["wght"] * 65536 + .5), 32702870)
        for mode in report["modes"]:
            with self.subTest(mode=mode["mode"]):
                self.assertEqual([labelled(mode["observations"], label)["HVAR_inferred_f2dot14"]
                                  for label in ("collision_low", "collision_high")], [0, 65])
                self.assertEqual(len(mode["collision_pair"]), 35)
                self.assertEqual(sum(not row["payload_identical"] for row in mode["collision_pair"]), 31)
                delta = glyph(mode["collision_pair"], 5)["metric_differences"]["advance_width"]
                self.assertEqual(delta, 0.5474853515625)
                self.assertGreater(abs(delta) / 2, LIMIT)
        self.assertIs(report["standard_format_impossibility_proved"], False)

    def test_original_hvar_focus_and_nearest_holdout_failures_are_not_erased(self):
        report = self.reports["hvar_22a89a1"]
        self.assertIs(report["conditional_grid_is_not_global_mapping"], True)
        for mode in report["modes"]:
            focus = labelled(mode["observations"], "archived_face18_fresh_triple_7")
            self.assertEqual(focus["location"], {"WDTH": 395.1762070327519,
                             "wght": 493.5928547043863, "HGHT": 579.3731774437933})
            for model in (OLD_DOUBLE, OLD_FLOAT):
                check = focus["model_checks"][model]
                self.assertIs(check["exact"], False)
                self.assertIs(check["within_1_32"], True)
                self.assertEqual(check["maximum_error"], 0.01220703125)
                self.assertEqual(glyph(check["native_HVF_geometry"], 19177)["maximum_point_error"],
                                 0.011959285366742733)
            self.assertIs(focus["model_checks"][NEAREST]["exact"], True)
            self.assertTrue(any(not row["model_checks"][NEAREST]["exact"]
                                for row in mode["observations"] if row is not focus))

    def test_new_identity_counterexamples_and_hght_metric_blindspot_remain_visible(self):
        report = self.reports["identity_0c603aa"]
        prior = self.entries["hvar_22a89a1"]
        self.assertEqual(report["prior_hvar_commit"], prior["source_commit"])
        self.assertEqual(report["prior_report_sha256"], prior["report_sha256"])
        self.assertEqual(report["prior_run_url"], prior["ci_url"])
        self.assertIs(report["candidate_frozen_before_new_observations"], True)
        candidate = report["candidate"]
        anchors = [mode for mode in report["modes"] if mode["mode"].startswith("anchor_")]
        self.assertEqual(len(anchors), 2)
        self.assertEqual(anchors[0]["observations"], anchors[1]["observations"])
        for mode in anchors:
            holdouts = [row for row in mode["observations"] if row["is_holdout"]]
            checks = [row["model_checks"][candidate] for row in holdouts]
            failures = [check for check in checks if check["maximum_error"] != 0]
            self.assertTrue(failures, "The rejected candidate must not become all-exact")
            self.assertTrue(all(check["within_1_32"] and not check["exact"] for check in failures))
            aggregate = mode["metric_exactness_by_cohort"][candidate]["holdouts"]
            self.assertEqual(aggregate["checks"], len(checks))
            self.assertEqual(aggregate["exact_matches"], len(checks) - len(failures))
            native_counter = labelled(holdouts, "identity_fresh_23_0")["model_checks"][candidate]
            self.assertGreater(native_counter["maximum_error"], 0)
            self.assertGreater(glyph(native_counter["native_HVF_geometry"], 19177)["maximum_point_error"], 0)

            blindspot = labelled(holdouts, "identity_fresh_2_0")
            check = blindspot["model_checks"][candidate]
            self.assertIs(check["exact"], True)
            self.assertEqual(check["maximum_error"], 0)
            native = glyph(check["native_HVF_geometry"], 19177)
            self.assertGreater(native["maximum_point_error"], 0)
            self.assertLess(native["maximum_point_error"], LIMIT)
            self.assertEqual(native["legacy"]["reason"], "segment_types_differ")
            self.assertGreater(native["restored_segment_count"], 0)
            declared = labelled(report["cases"], blindspot["label"])["declared_models"]
            self.assertEqual([tag for tag in ("WDTH", "wght", "HGHT")
                              if declared[candidate][tag] != declared[OLD_DOUBLE][tag]], ["HGHT"])
            self.assertEqual(glyph(blindspot["model_checks"][OLD_DOUBLE]["native_HVF_geometry"],
                                   19177)["maximum_point_error"], 0)

            fresh = labelled(holdouts, "identity_fresh_12_1")
            self.assertIs(fresh["model_checks"][OLD_FLOAT]["exact"], False)
            self.assertIs(fresh["model_checks"][OLD_DOUBLE]["exact"], True)
            self.assertFalse(fresh["direct_native_HVF"])
            self.assertEqual(fresh["model_checks"][OLD_FLOAT]["native_HVF_geometry"], [])

    def test_synthetic_normalized_channel_proof_stays_separate_from_font_acceptance(self):
        report = self.reports["normalized_d22be86"]
        entry = self.entries["normalized_d22be86"]
        self.assertIs(report["synthetic_only"], True)
        self.assertIs(report["conditional_native_channel_proven_on_this_runtime"], True)
        self.assertIn("Linux", report["runtime"]["platform"])
        for engine in ("harfbuzz", "freetype"):
            self.assertEqual(report[engine]["library"]["version"], entry[f"{engine}_version"])
        design = report["harfbuzz"]["design_float32_samples"]
        normalized = report["harfbuzz"]["normalized_f2dot14_samples"]
        self.assertEqual(design[0]["weight_float32_bits"], design[1]["weight_float32_bits"])
        self.assertNotEqual(design[0]["retained_original_binary64_bits"],
                            design[1]["retained_original_binary64_bits"])
        self.assertEqual([row["readback_normalized_f2dot14"] for row in normalized],
                         [[0, 0, 0], [0, 65, 0]])
        self.assertEqual([row["synthetic_gid1_native_advance_font_units"] for row in normalized], [500, 565])
        self.assertEqual([row["readback_normalized_16_16"] for row in report["freetype"]["samples"]],
                         [[0, 0, 0], [0, 260, 0]])
        self.assertIs(report["freetype"]["glyph_metric_tested"], False)
        for key in ("general_source_mapper_proven", "production_mapping_accepted", "apple_tested", "windows_tested"):
            self.assertIs(report[key], False)


if __name__ == "__main__":
    unittest.main()
