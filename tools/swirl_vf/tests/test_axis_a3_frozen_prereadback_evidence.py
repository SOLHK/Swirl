"""Check archived Apple observations without promoting diagnostics to acceptance.

The new design-stage candidates are compared with the original raw requests.
Their finite HVAR/HVF matches cannot erase actual original/replay differences.
The second archive checks that the existing 201-case native protocol did not
change when the optional experiment hooks were added. No Apple font is needed.
"""
from collections import Counter
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
import zipfile

PLATFORM = Path(__file__).resolve().parents[1] / "platform"
sys.path.insert(0, str(PLATFORM))
from axis_a3_input_cases import representations
from axis_a3_prereadback_cases import (
    ENDPOINT, ONCE_ALL, ONCE_IDENTITY, prereadback_cases,
    prereadback_design_inputs, prereadback_mappings,
)
from probe_axis_anchor import declare_readback

SOURCE = "6d6a7b5eec6e2c7a630dfd4f692e29a7ecc52115"
FONT_SHA = "39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890"
REFERENCE_SOURCE = "9c2fd0092284edc7d346b0c9e1d1208095429b39"
REFERENCE_SHA = "d5ea884cdd1c7ffdf0efdf2dd264c3ee05d69550b55d2319565c6d5ebe9201c6"
TAGS = ("WDTH", "wght", "HGHT")
GIDS = [5, 12, 56, 169, 19177]
MODELS = (ENDPOINT, ONCE_ALL, ONCE_IDENTITY)
MODES = ("anchor_endpoint_original", "anchor_quarter_original")
ORDERS = ("forward", "reverse")
NEW_FAILURE = "prereadback_integer_0_wght_-14039_at"
FACE22 = "prereadback_history_22_arithmetic_fresh_22_0"
FACE30 = "prereadback_history_30_arithmetic_fresh_30_0"
METRIC_DIFFERENCES = {
    "advance_width", "advance_height", "lsb", "horizontal_origin_x",
    "horizontal_origin_y", "vertical_origin_x", "vertical_origin_y",
    "horizontal_advance_sum", "vertical_advance_sum", "bounds",
    "horizontal_advance_vector", "vertical_advance_vector", "vertical_origin_translation",
}
ARCHIVES = {
    "prereadback_6d6a7b5": (
        "axis_a3_prereadback_native_6d6a7b5.zip", "prereadback.json", 210310,
        "f14dc7d77ca586d3cd3b4774f1332ec66ac885f5fe273779b2d770ebf136ac7c", 9080199,
        "b5631489f8c95445264af848956d7e5bbc4748d209895d90b0786d21d58d8d08",
        39407084146, 12257063377, 118575682081,
        "COMPLETED_NATIVE_A3_PREREADBACK_DIAGNOSIS_NOT_ACCEPTANCE"),
    "arithmetic_protocol_6d6a7b5": (
        "axis_a3_prereadback_protocol_6d6a7b5.zip", "arithmetic.json", 253358,
        "c7a6767a15e91073c959c6c836556c5a8c9f1db2930e82bb2788abb31af3d1f7", 12202758,
        "5809374e5f10fcf5220f4c3d8245dba39294863791994dd01f6b99d1a4ab9e2a",
        39407084001, 12257293380, 118575647238,
        "COMPLETED_NATIVE_A3_ARITHMETIC_DIAGNOSIS_NOT_ACCEPTANCE"),
}


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def read_archive(name, member):
    path = PLATFORM / name
    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        raw = archive.read(member)
    return path.read_bytes(), members, raw, json.loads(raw)


def horizontal_summary(checks):
    return {"checks": len(checks), "exact_matches": sum(c["exact"] for c in checks),
            "outside_1_32": sum(not c["within_1_32"] for c in checks),
            "maximum_error": max(c["maximum_error"] for c in checks)}


class FrozenPrereadbackEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((PLATFORM / "axis_a3_prereadback_evidence_20261020.json").read_bytes())
        cls.entries = {e["id"]: e for e in cls.manifest["archives"]}
        cls.archives = {key: read_archive(values[0], values[1]) for key, values in ARCHIVES.items()}
        cls.report = cls.archives["prereadback_6d6a7b5"][3]
        cls.protocol = cls.archives["arithmetic_protocol_6d6a7b5"][3]
        cls.reference_archive = read_archive("axis_a3_arithmetic_native_9c2fd00.zip", "arithmetic.json")
        cls.reference = cls.reference_archive[3]
        cls.cases = {c["label"]: c for c in cls.report["cases"]}

    def assert_geometry_summary(self, rows, summary):
        """Recount both legacy topology failures and preserved-control errors."""
        self.assertEqual(summary["glyphs_with_restored_Q"],
                         sum(r["restored_segment_count"] > 0 for r in rows))
        for name in ("legacy", "preserved_controls"):
            results = [r["legacy"] if name == "legacy" else r for r in rows]
            failed = [r for r in results if r["status"] != "within_budget"]
            stats = summary[name]
            self.assertEqual(stats["checks"], len(results))
            self.assertEqual(stats["failures"], len(failed))
            self.assertEqual(stats["failure_types"], Counter(r["reason"] for r in failed))
            self.assertEqual(stats["maximum_point_error"],
                             max((r["maximum_point_error"] or 0 for r in results), default=0))
            self.assertEqual(len(stats["examples"]), len(failed))
        for row in rows:
            self.assertEqual(row["legacy"]["limit"], 1/32)
            self.assertEqual(row["status"], "within_budget")
            self.assertIsNone(row["reason"])
            self.assertGreaterEqual(row["maximum_point_error"], 0)
            self.assertLessEqual(row["maximum_point_error"], 1/32)

    def test_immutable_archives_reports_source_and_actual_ci_are_bound(self):
        self.assertEqual(set(self.entries), set(ARCHIVES))
        self.assertEqual(self.manifest["original_source_sha256"], FONT_SHA)
        for key, expected in ARCHIVES.items():
            name, member, size, sha, report_size, report_sha, run, artifact, job, status = expected
            entry = self.entries[key]
            data, members, raw, report = self.archives[key]
            with self.subTest(archive=key):
                self.assertEqual((entry["archive"], entry["report_member"]), (name, member))
                self.assertEqual(members, [member])
                self.assertEqual((len(data), entry["archive_bytes"]), (size, size))
                self.assertEqual((hashlib.sha256(data).hexdigest(), entry["archive_sha256"]), (sha, sha))
                self.assertEqual((len(raw), entry["report_bytes"]), (report_size, report_size))
                self.assertEqual((hashlib.sha256(raw).hexdigest(), entry["report_sha256"]),
                                 (report_sha, report_sha))
                self.assertEqual((report["source_commit"], entry["source_commit"]), (SOURCE, SOURCE))
                self.assertEqual((entry["ci_run_id"], entry["artifact_id"], entry["native_job_id"]),
                                 (run, artifact, job))
                self.assertEqual(entry["ci_url"], f"https://github.com/SOLHK/Swirl/actions/runs/{run}")
                self.assertEqual((entry["ci_status"], entry["ci_conclusion"]), ("completed", "success"))
                self.assertEqual((report["status"], entry["reported_status"]), (status, status))
                self.assertEqual(report["source_sha256"], FONT_SHA)

    def test_complete_native_process_entry_and_replay_counts_are_independent(self):
        r, e = self.report, self.entries["prereadback_6d6a7b5"]
        self.assertEqual(r["planned_constructor_modes"], list(MODES))
        self.assertEqual(r["selected_glyphs"], GIDS)
        self.assertEqual(len(r["native_processes"]), 4)
        self.assertEqual({(p["mode"], p["order"]) for p in r["native_processes"]},
                         {(mode, order) for mode in MODES for order in ORDERS})
        for process in r["native_processes"]:
            self.assertIs(process["all_32_physical_faces_verified"], True)
            self.assertIs(process["constructor_entry_bits_verified"], True)
            self.assertEqual(process["exit_status"], 0)
            self.assertEqual(process["os_version"], "Version 27.0.1 (Build 26A434)")
            self.assertEqual(process["constructor_entry_records"], 280)
            self.assertEqual(process["summary"], {
                "type": "summary", "error_count": 0, "request_count": 280,
                "source_sha256": FONT_SHA, "successful_glyph_count": 1400})
        counts = {
            "native_records": sum(p["summary"]["successful_glyph_count"] for p in r["native_processes"]),
            "constructor_entry_records": sum(p["constructor_entry_records"] for p in r["native_processes"]),
            "opposite_order_pairs": sum(m["opposite_order_pairs"] for m in r["modes"]),
            "replay_batches": sum(m["replay_batch_checks"] for m in r["modes"]),
        }
        self.assertEqual(counts, {"native_records": 5600, "constructor_entry_records": 1120,
                                  "opposite_order_pairs": 2800, "replay_batches": 560})
        for key, value in counts.items():
            self.assertEqual((r["actual_" + key], e[key]), (value, value))
        self.assertEqual(r["planned_native_records"], 140 * 2 * 2 * 5 * 2)
        first, second = r["modes"]
        self.assertEqual([first["mode"], second["mode"]], list(MODES))
        # Independent constructors and opposite orders repeat the finite result;
        # these observations do not establish that a system cache was reset.
        self.assertEqual({k: v for k, v in first.items() if k != "mode"},
                         {k: v for k, v in second.items() if k != "mode"})
        for mode in r["modes"]:
            self.assertEqual((mode["opposite_order_pairs"], mode["opposite_order_exact_pairs"]), (1400, 1400))
            self.assertEqual(mode["opposite_order_mismatches"], [])
            # Rendering groups cases by physical face while preserving each
            # face's predeclared order; the raw request plan remains unchanged.
            self.assertEqual([o["label"] for o in mode["observations"]],
                             [c["label"] for c in sorted(r["cases"], key=lambda c: c["face_index"])])
        direct = [c for c in r["cases"] if c["direct_native_HVF"]]
        cached_keys = {(c["face_index"], gid, tuple(vector[tag] for tag in TAGS))
                       for c in direct for vector in c["declared_models"].values() for gid in (5, 19177)}
        self.assertEqual((len(direct), r["planned_direct_HVF_positions"]), (68, 68))
        self.assertEqual((len(cached_keys), r["native_HVF_unique_calls"], e["native_HVF_unique_calls"]),
                         (128, 128, 128))
        self.assertIs(r["HVF_geometry_references_cached_by_face_gid_and_design"], True)

    def test_original_tables_and_predeclared_raw_requests_are_not_refitted_to_observations(self):
        r = self.report
        self.assertEqual(r["original_faces"], self.reference["original_faces"])
        self.assertEqual(canonical_sha(r["original_faces"]),
                         "c02af3963cc2e2ee93917149f090842da26ee7f7c5b120dd7e12fab36369d8fe")
        self.assertEqual([f["face_index"] for f in r["original_faces"]], list(range(32)))
        count, duplicate_patterns = 0, Counter()
        for face in r["original_faces"]:
            self.assertEqual(tuple(face["original_axes"]), TAGS)
            self.assertEqual(tuple(face["original_avar_records_in_table_order"]), TAGS)
            for tag, records in face["original_avar_records_in_table_order"].items():
                count += len(records)
                self.assertTrue(all(len(pair) == 2 and all(v * 16384 == int(v * 16384) for v in pair)
                                    for pair in records))
                if tag == "wght":
                    duplicates = Counter(pair[0] for pair in records)
                    duplicate_patterns[tuple((v, n) for v, n in duplicates.items() if n > 1)] += 1
                else:
                    self.assertEqual(records, [[-1., -1.], [0., 0.], [1., 1.]])
        self.assertEqual(count, 560)
        self.assertEqual(duplicate_patterns, {((-1., 2), (0., 2), (1., 2)): 20, ((1., 2),): 12})
        self.assertEqual(r["original_faces"][15]["original_axes"], {
            "WDTH": [1., 500., 1000.], "wght": [100., 499., 900.], "HGHT": [1., 500., 1000.]})
        self.assertEqual(canonical_sha(r["cases"]),
                         "4e75e381df204771992ffb6ad09582efd3094c91cab2ad6c0050210d737f8e29")
        axes = {f["face_index"]: f["original_axes"] for f in r["original_faces"]}
        generated = prereadback_cases(axes)
        self.assertEqual(len(generated), 140)
        self.assertEqual(len({(c["face_index"], *(c["location"][tag] for tag in TAGS)) for c in generated}), 140)
        self.assertEqual(Counter(c["group"] for c in generated), {
            "fresh_random_holdout": 64, "decimal_stage_instability_holdout": 24,
            "normalized16_decimal_bracket_holdout": 36, "historical_control": 16})
        self.assertEqual(sum(c["is_holdout"] for c in generated), 124)
        self.assertEqual(r["fresh_holdout_seed"], 2746490918)
        self.assertIs(r["all_cases_and_mappings_declared_before_native_launch"], True)
        for case, saved in zip(generated, r["cases"]):
            self.assertEqual(case, {k: v for k, v in saved.items() if k not in {
                "binary64_bits", "declared_models", "predeclared_replay", "declared_design_inputs"}})
            self.assertEqual(tuple(case["location"]), TAGS)
            self.assertEqual(saved["binary64_bits"],
                             {tag: struct.pack(">d", value).hex() for tag, value in case["location"].items()})
            self.assertEqual(saved["predeclared_replay"],
                             {tag: plan["canonical"] for tag, plan in declare_readback(case["location"]).items()})
            face = r["original_faces"][case["face_index"]]
            font = {"fvar": SimpleNamespace(axes=[
                SimpleNamespace(axisTag=tag, minValue=v[0], defaultValue=v[1], maxValue=v[2])
                for tag, v in face["original_axes"].items()])}
            records = face["original_avar_records_in_table_order"]
            # Neither function receives a native observation or a fitted q.
            self.assertEqual(prereadback_design_inputs(font, records, case["location"]), saved["declared_design_inputs"])
            self.assertEqual(prereadback_mappings(font, records, case["location"]), saved["declared_models"])
            self.assertEqual(saved["declared_design_inputs"][ENDPOINT], saved["predeclared_replay"])
            if case["group"] == "historical_control":
                self.assertIs(case["is_holdout"], False)
                self.assertIs(case["participated_in_model_selection"], True)
        context = r["experiment_context"]
        self.assertIs(context["design_stage_values_frozen_before_native"], True)
        self.assertIs(context["observed_readback_used_to_fit_design"], False)
        self.assertEqual(context["prior_native_source_commit"], "eda37d1c733cb1ced283583434e4123824a2147c")
        self.assertEqual(context["prior_report_sha256"],
                         "64483c46413e2ed0fe33731ef75dd22132a59a0da112bf791c0bff950da86f4d")

    def test_all_model_metrics_and_geometry_recount_exactness_without_rounding_away_errors(self):
        golden = {
            ENDPOINT: (135, .01220703125, 119, 56, 112, .012252664064817509, 695, .012252664064703822),
            ONCE_ALL: (140, 0., 124, 68, 136, 0., 694, 6.821210263296962e-13),
            ONCE_IDENTITY: (139, .0032958984375, 123, 67, 134, .005370084551486798, 694, .005554199218863687),
        }
        for mode in self.report["modes"]:
            self.assertEqual(tuple(mode["models"]), MODELS)
            for name, expected in golden.items():
                exact, error, held_exact, hvf_positions, hvf_glyphs, hvf_error, portable_nonzero, portable_error = expected
                observations = mode["observations"]
                checks = [o["model_checks"][name] for o in observations]
                for observed, check in zip(observations, checks):
                    self.assertEqual([d["glyph_id"] for d in check["four_metric_residuals"]], GIDS[:4])
                    for delta in check["four_metric_residuals"]:
                        self.assertEqual(delta["absolute_error"], abs(delta["signed_error"]))
                    self.assertEqual(check["maximum_error"], max(d["absolute_error"] for d in check["four_metric_residuals"]))
                    self.assertIs(check["exact"], check["maximum_error"] == 0)
                    self.assertIs(check["within_1_32"], check["maximum_error"] <= 1/32)
                    self.assertEqual([g["glyph_id"] for g in check["portable_geometry"]], GIDS)
                    self.assertEqual([g["glyph_id"] for g in check["native_HVF_geometry"]],
                                     [5, 19177] if observed["direct_native_HVF"] else [])
                summary = horizontal_summary(checks)
                self.assertEqual(summary, {"checks": 140, "exact_matches": exact,
                                           "outside_1_32": 0, "maximum_error": error})
                self.assertEqual(summary, mode["models"][name]["horizontal_metrics"])
                cohorts = mode["metric_exactness_by_cohort"][name]
                for cohort, is_holdout, wanted in (("holdouts", True, held_exact), ("historical_controls", False, 16)):
                    selected = [o["model_checks"][name] for o in observations if o["is_holdout"] is is_holdout]
                    self.assertEqual(cohorts[cohort], horizontal_summary(selected))
                    self.assertEqual(cohorts[cohort]["exact_matches"], wanted)
                self.assertEqual([o["label"] for o in cohorts["nonexact_observations"]],
                                 [o["label"] for o in observations if not o["model_checks"][name]["exact"]])
                portable = [g for c in checks for g in c["portable_geometry"]]
                hvf = [g for c in checks for g in c["native_HVF_geometry"]]
                for key, rows in (("portable_geometry", portable), ("native_HVF_geometry", hvf)):
                    self.assert_geometry_summary(rows, mode["models"][name][key])
                self.assertEqual((len(portable), sum(g["maximum_point_error"] > 0 for g in portable),
                                  max(g["maximum_point_error"] for g in portable)), (700, portable_nonzero, portable_error))
                self.assertEqual((len(hvf), sum(g["maximum_point_error"] == 0 for g in hvf),
                                  max(g["maximum_point_error"] for g in hvf)), (136, hvf_glyphs, hvf_error))
                exact_positions = sum(bool(c["native_HVF_geometry"]) and
                                      all(g["maximum_point_error"] == 0 for g in c["native_HVF_geometry"]) for c in checks)
                self.assertEqual(exact_positions, hvf_positions)
                frozen = self.manifest["model_results_per_constructor"][name]
                self.assertEqual(frozen["HVAR"], summary)
                self.assertEqual(frozen["HVAR_by_cohort"], {k: cohorts[k] for k in ("holdouts", "historical_controls")})
                self.assertEqual((frozen["direct_HVF_positions"], frozen["direct_HVF_exact_positions"],
                                  frozen["direct_HVF_glyph_comparisons"], frozen["direct_HVF_exact_glyphs"],
                                  frozen["direct_HVF_maximum_point_error"]),
                                 (68, hvf_positions, 136, hvf_glyphs, hvf_error))
                self.assertEqual((frozen["portable_glyph_comparisons"], frozen["portable_nonzero_glyphs"],
                                  frozen["portable_maximum_point_error"]), (700, portable_nonzero, portable_error))
                # The one portable legacy topology rejection survives all three
                # models even where preserving the missing Q control succeeds.
                rejected = [(o["label"], g["glyph_id"]) for o in observations
                            for g in o["model_checks"][name]["portable_geometry"] if g["legacy"]["status"] == "rejected"]
                self.assertEqual(rejected, [("prereadback_integer_0_WDTH_-40815_below", 19177)])

    def test_new_nonidentity_weight_holdout_refutes_once_identity_but_not_once_all(self):
        case = self.cases[NEW_FAILURE]
        self.assertIs(case["is_holdout"], True)
        self.assertEqual(case["location"], {"WDTH": 500., "wght": 415.09865, "HGHT": 500.})
        self.assertEqual(case["predeclared_replay"]["wght"], 415.0985)
        self.assertEqual([case["declared_design_inputs"][name]["wght"] for name in MODELS],
                         [415.0985, 415.0986, 415.0985])
        self.assertEqual([case["declared_models"][name]["wght"] * 16384 for name in MODELS], [-3894, -3893, -3894])
        for mode in self.report["modes"]:
            row = next(o for o in mode["observations"] if o["label"] == NEW_FAILURE)
            self.assertEqual(row["reported_location"], {"wght": 415.0985})
            for name in (ENDPOINT, ONCE_IDENTITY):
                check = row["model_checks"][name]
                self.assertIs(check["exact"], False)
                self.assertIs(check["within_1_32"], True)
                self.assertEqual([d["signed_error"] for d in check["four_metric_residuals"]],
                                 [.0025634765625, .0032958984375, .00164794921875, 0.])
                self.assertEqual([g["maximum_point_error"] for g in check["native_HVF_geometry"]],
                                 [.005370084551486798, .004658718965970365])
            self.assertEqual(row["model_checks"][ONCE_ALL]["maximum_error"], 0)
            self.assertTrue(all(g["maximum_point_error"] == 0 for g in row["model_checks"][ONCE_ALL]["native_HVF_geometry"]))

    def test_actual_original_replay_errors_and_all_52_strict_failures_remain(self):
        totals, rejected = Counter(), Counter()
        all_comparisons = []
        expected_payload_labels = {
            "prereadback_integer_0_WDTH_-40815_at", NEW_FAILURE,
            "prereadback_integer_0_HGHT_-55523_at", "prereadback_integer_5_WDTH_34250_at",
            "prereadback_integer_5_HGHT_20510_at", "prereadback_integer_20_WDTH_-39127_at",
            "prereadback_integer_20_HGHT_-18127_at", "prereadback_integer_24_WDTH_36862_at",
            "prereadback_integer_24_HGHT_13342_at", FACE30,
            "prereadback_derived_30_twice_WDTH_wght_HGHT_raw", "prereadback_derived_30_HGHT_only_raw",
        }
        for mode in self.report["modes"]:
            comparisons = {(c["case_label"], c["order"]): c for c in mode["original_replay_comparisons"]}
            classifiers = {(c["case_label"], c["order"]): c for c in mode["default_omission_checks"]}
            failed = {(f["case_label"], f["order"]): f for f in mode["replay_failures"]}
            keys = {(label, order) for label in self.cases for order in ORDERS}
            self.assertEqual(set(comparisons), keys)
            self.assertEqual(set(classifiers), keys)
            self.assertEqual((len(mode["original_replay_comparisons"]), len(mode["default_omission_checks"])), (280, 280))
            self.assertEqual((len(failed), mode["replay_failed_batches"], mode["replay_batch_checks"]), (26, 26, 280))
            self.assertEqual(set(failed), {(label, order) for label in expected_payload_labels | {FACE22} for order in ORDERS})
            for key, comparison in comparisons.items():
                case, classification = self.cases[key[0]], classifiers[key]
                glyphs = comparison["glyphs"]
                self.assertEqual((comparison["face_index"], comparison["glyph_count"]), (case["face_index"], 5))
                self.assertEqual([g["glyph_id"] for g in glyphs], GIDS)
                self.assertEqual(comparison["payload_different_glyphs"], sum(not g["payload_identical"] for g in glyphs))
                self.assertEqual(comparison["readback_different_glyphs"], sum(not g["readback_identical"] for g in glyphs))
                self.assertEqual(comparison["maximum_advance_difference"], max(g["metric_differences"]["advance_width"] for g in glyphs))
                self.assert_geometry_summary([g["numeric_geometry"] for g in glyphs], comparison["geometry_summary"])
                self.assertEqual(classification["requested_location"], case["location"])
                self.assertEqual(classification["requested_binary64_bits"], case["binary64_bits"])
                self.assertEqual(classification["predeclared_replay_location"], case["predeclared_replay"])
                self.assertEqual(classification["submission_evidence_site"], "constructor_entry")
                self.assertEqual(classification["scope"], "one_complete_observed_batch_only")
                self.assertIs(classification["constructor_entry_binary64_unchanged"], True)
                self.assertIs(classification["default_omission_equivalent"], False)
                self.assertEqual(classification["explained_omitted_axes"], [])
                totals[classification["classification"]] += 1
                legacy = classification["legacy_strict_replay"]
                self.assertEqual(legacy["requested_GID_count"], 5)
                if key in failed:
                    self.assertEqual((failed[key]["status"], legacy["status"]), ("FAILED_FINITE_REPLAY", "FAILED_FINITE_REPLAY"))
                    self.assertEqual(classification["classification"], "REJECTED")
                    self.assertIs(classification["diagnostic_passed"], False)
                    self.assertIs(classification["strict_replay_passed"], False)
                    self.assertEqual(len(classification["failures"]), 5)
                    rejected[classification["reason"]] += 1
                    payload = key[0] in expected_payload_labels
                    self.assertEqual((comparison["payload_different_glyphs"], comparison["readback_different_glyphs"]),
                                     (5, 0) if payload else (0, 5))
                    self.assertIs(legacy["all_payloads_exactly_equal"], not payload)
                    self.assertEqual(classification["reason"], "native_replay_payload_not_exact" if payload
                                     else "native_readback_replay_not_exactly_stable")
                    self.assertEqual(len(failed[key]["payload_differences"]), 5 if payload else 0)
                    self.assertEqual(len(failed[key]["readback_failures"]), 0 if payload else 5)
                else:
                    self.assertEqual(classification["classification"], "STRICT_REPLAY_ALREADY_PASSED")
                    self.assertIs(classification["diagnostic_passed"], True)
                    self.assertIs(classification["strict_replay_passed"], True)
                    self.assertEqual(legacy["status"], "PASS_FINITE_REPLAY")
                    self.assertEqual(classification["failures"], [])
                    self.assertEqual((comparison["payload_different_glyphs"], comparison["readback_different_glyphs"]), (0, 0))
                for glyph in glyphs:
                    if glyph["payload_identical"]:
                        self.assertIs(glyph["raw_commands_identical"], True)
                        self.assertTrue(all(v == 0 for v in glyph["metric_differences"].values()))
                        self.assertEqual(glyph["numeric_geometry"]["maximum_point_error"], 0)
            for label in self.cases:
                self.assertEqual({k: v for k, v in comparisons[label, "forward"].items() if k != "order"},
                                 {k: v for k, v in comparisons[label, "reverse"].items() if k != "order"})
            all_comparisons.extend(comparisons.values())
        self.assertEqual(totals, {"STRICT_REPLAY_ALREADY_PASSED": 508, "REJECTED": 52})
        self.assertEqual(rejected, {"native_replay_payload_not_exact": 48, "native_readback_replay_not_exactly_stable": 4})
        entry = self.entries["prereadback_6d6a7b5"]
        self.assertEqual(entry["classifier_counts"], totals)
        self.assertEqual(entry["rejection_counts"], rejected)
        self.assertEqual(entry["strict_replay_failed_batches"], 52)
        actual = {
            "batches": len(all_comparisons),
            "payload_different_batches": sum(c["payload_different_glyphs"] > 0 for c in all_comparisons),
            "readback_different_batches": sum(c["readback_different_glyphs"] > 0 for c in all_comparisons),
            "payload_different_glyph_pairs": sum(c["payload_different_glyphs"] for c in all_comparisons),
            "readback_different_glyph_pairs": sum(c["readback_different_glyphs"] for c in all_comparisons),
            "maximum_advance_difference": max(c["maximum_advance_difference"] for c in all_comparisons),
            "maximum_numeric_geometry_difference": max(g["numeric_geometry"]["maximum_point_error"]
                                                        for c in all_comparisons for g in c["glyphs"]),
        }
        self.assertEqual(actual, {"batches": 560, "payload_different_batches": 48, "readback_different_batches": 4,
                                  "payload_different_glyph_pairs": 240, "readback_different_glyph_pairs": 20,
                                  "maximum_advance_difference": .01220703125,
                                  "maximum_numeric_geometry_difference": .012252664064817509})
        self.assertEqual(actual, {k: v for k, v in self.manifest["original_replay_numeric_comparison"].items()
                                  if k != "source_of_distances"})

    def test_old_face22_and_face30_failures_survive_zero_hvar_and_once_all_hvf(self):
        for mode in self.report["modes"]:
            observed = {o["label"]: o for o in mode["observations"]}
            for order in ORDERS:
                classifiers = {c["case_label"]: c for c in mode["default_omission_checks"] if c["order"] == order}
                comparisons = {c["case_label"]: c for c in mode["original_replay_comparisons"] if c["order"] == order}
                face22 = classifiers[FACE22]
                self.assertEqual((face22["original_reported_location"]["HGHT"],
                                  face22["predeclared_replay_location"]["HGHT"],
                                  face22["replay_reported_location"]["HGHT"]), (1.1279, 1.1279, 1.1278))
                self.assertIs(face22["legacy_strict_replay"]["all_payloads_exactly_equal"], True)
                self.assertEqual(comparisons[FACE22]["geometry_summary"]["preserved_controls"]["maximum_point_error"], 0)
                face30 = classifiers[FACE30]
                self.assertEqual(face30["original_reported_location"], face30["replay_reported_location"])
                self.assertEqual(face30["replay_reported_location"], self.cases[FACE30]["predeclared_replay"])
                self.assertEqual(comparisons[FACE30]["maximum_advance_difference"], 0)
                self.assertEqual([g["numeric_geometry"]["maximum_point_error"] for g in comparisons[FACE30]["glyphs"]],
                                 [.008711728120943008, .00871582084982947, .006867139997268623,
                                  .008858400986582637, .009678105302214135])
                self.assertTrue(all(not g["payload_identical"] and g["readback_identical"]
                                    and not g["raw_commands_identical"] for g in comparisons[FACE30]["glyphs"]))
            for label in (FACE22, FACE30):
                self.assertTrue(all(c["maximum_error"] == 0 for c in observed[label]["model_checks"].values()))
                self.assertTrue(all(g["maximum_point_error"] == 0
                                    for g in observed[label]["model_checks"][ONCE_ALL]["native_HVF_geometry"]))
            self.assertEqual([g["maximum_point_error"] for g in observed[FACE30]["model_checks"][ENDPOINT]["native_HVF_geometry"]],
                             [.008711728120943008, .009678105302214135])

    def test_original_fixed_collision_and_prior_divsub_counterexample_are_retained(self):
        pair = [self.cases["prereadback_history_15_same_fixed16_collision_" + side] for side in ("low", "high")]
        values = [representations(c["location"]["wght"]) for c in pair]
        self.assertEqual([c["location"] for c in pair], [
            {"WDTH": 500., "wght": 499.006199, "HGHT": 500.},
            {"WDTH": 500., "wght": 499.006201, "HGHT": 500.}])
        self.assertEqual([v["fixed16_integer"] for v in values], [32702870, 32702870])
        self.assertEqual([v["float32_bits"] for v in values], ["43f980cb", "43f980cb"])
        self.assertNotEqual(values[0]["binary64_bits"], values[1]["binary64_bits"])
        for name in MODELS:
            self.assertEqual([c["declared_models"][name]["wght"] * 16384 for c in pair], [0, 65])
        for mode in self.report["modes"]:
            rows = {o["label"]: o for o in mode["observations"]}
            self.assertEqual([rows[c["label"]]["reported_location"] for c in pair], [{"wght": 499.0061}, {"wght": 499.0062}])
            for c in pair:
                for check in rows[c["label"]]["model_checks"].values():
                    self.assertIs(check["exact"], True)
                    self.assertTrue(all(g["maximum_point_error"] == 0 for g in check["native_HVF_geometry"]))
        # The earlier collapse experiment remains actual, immutable evidence.
        # This report does not rerun a float32-collapse mode or the old 141 cases.
        old = {o["label"]: o for o in self.reference["modes"][0]["observations"]}
        collapse = old["arithmetic_original_collision_low"]["model_checks"]["canonical_all_axes_float32_offset_normalized16_truncate"]
        self.assertEqual(collapse["maximum_error"], .5474853515625)
        self.assertIs(collapse["within_1_32"], False)
        self.assertEqual(Fraction(collapse["maximum_error"]) / 2, Fraction(4485, 16384))
        self.assertGreater(Fraction(collapse["maximum_error"]) / 2, Fraction(1, 32))
        divsub_label = "arithmetic_integer_0_WDTH_-42539_above"
        self.assertEqual(self.cases["prereadback_history_0_" + divsub_label]["location"], old[divsub_label]["location"])
        failed = old[divsub_label]["model_checks"]["canonical_identity_negative_divsub32_positive64_normalized16_truncate"]
        self.assertEqual(failed["maximum_error"], .01220703125)
        self.assertIs(failed["exact"], False)
        self.assertIs(failed["within_1_32"], True)

    def test_default_201_case_native_protocol_changes_only_source_identity(self):
        data, members, raw, reference = self.reference_archive
        self.assertEqual(members, ["arithmetic.json"])
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         "3a4239c867d1e745550c189d7624f1d79b6beb4f8b3d36b405eec5a8aca96e56")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), REFERENCE_SHA)
        self.assertEqual(reference["source_commit"], REFERENCE_SOURCE)
        repeat = self.protocol
        self.assertEqual(set(repeat), set(reference))
        self.assertEqual({k for k in repeat if repeat[k] != reference[k]}, {"source_commit"})
        for key in set(repeat) - {"source_commit"}:
            with self.subTest(unchanged_default_protocol_field=key):
                self.assertEqual(repeat[key], reference[key])
        self.assertEqual((len(repeat["cases"]), repeat["unique_face_locations"], repeat["new_holdout_positions"]), (201, 193, 160))
        self.assertEqual((repeat["actual_native_records"], repeat["actual_constructor_entry_records"],
                          repeat["actual_opposite_order_pairs"], repeat["actual_replay_batches"]), (8040, 1608, 4020, 804))
        self.assertEqual(sum(len(m["replay_failures"]) for m in repeat["modes"]), 56)
        classifiers = [c for m in repeat["modes"] for c in m["default_omission_checks"]]
        counts = Counter(c["classification"] for c in classifiers)
        self.assertEqual(counts, {"STRICT_REPLAY_ALREADY_PASSED": 748,
                                  "DEFAULT_OMISSION_EQUIVALENT_FOR_THIS_BATCH": 48, "REJECTED": 8})
        self.assertEqual(self.entries["arithmetic_protocol_6d6a7b5"]["classifier_counts"], counts)
        relation = self.manifest["protocol_repeat_relation"]
        self.assertEqual((relation["reference_source_commit"], relation["reference_report_sha256"]),
                         (REFERENCE_SOURCE, REFERENCE_SHA))
        self.assertEqual(relation["only_changed_paths"], ["source_commit"])
        self.assertIs(relation["all_other_report_values_exactly_equal"], True)
        self.assertIs(relation["strict_replay_failures_unchanged"], True)

    def test_published_residuals_have_narrow_paths_and_every_acceptance_flag_is_false(self):
        forbidden = METRIC_DIFFERENCES | {"commands", "raw_commands", "outline", "raw_native_payload",
                                           "font_bytes", "path_px", "base64", "rsb"}
        flags = {"mapping_accepted", "production_mapping_accepted", "production_accepted", "font_accepted",
                 "continuous_space_accepted", "final_font_accepted", "native_values_modified",
                 "source_user_mapping_inferred", "native_execution_performed_by_classifier"}
        residual_blocks = 0

        def inspect(value, path=()):
            nonlocal residual_blocks
            if isinstance(value, dict):
                is_residual = (len(path) == 7 and path[0] == "modes" and type(path[1]) is int
                               and path[2] == "original_replay_comparisons" and type(path[3]) is int
                               and path[4] == "glyphs" and type(path[5]) is int and path[6] == "metric_differences")
                if is_residual:
                    residual_blocks += 1
                    self.assertEqual(set(value), METRIC_DIFFERENCES)
                    for delta in value.values():
                        self.assertIn(type(delta), (int, float))
                        self.assertTrue(math.isfinite(delta))
                        self.assertGreaterEqual(delta, 0)
                else:
                    self.assertFalse(forbidden.intersection(value), path)
                for key, child in value.items():
                    if key in flags:
                        self.assertIs(child, False, path + (key,))
                    inspect(child, path + (key,))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    inspect(child, path + (index,))
            elif isinstance(value, float):
                self.assertTrue(math.isfinite(value), path)

        for r in (self.report, self.protocol):
            inspect(r)
            for flag in ("font_generated", "production_constructor_changed", "production_mapping_changed",
                         "raw_avar_records_modified", "original_141_subset_rerun", "source_outlines_or_raw_metrics_published"):
                self.assertIs(r[flag], False)
            self.assertEqual((r["metric_limit_font_units"], r["outline_limit_font_units"]), (1/32, 1/32))
            self.assertIs(r["source_unchanged"], True)
            self.assertIs(r["constructor_entry_is_not_CoreText_internal_state"], True)
            self.assertIs(r["independent_processes_do_not_claim_system_cache_reset"], True)
        self.assertEqual(residual_blocks, 2800)
        inspect(self.manifest)
        self.assertEqual(self.manifest["strict_limit_font_units"], 1/32)
        for flag in ("original_141_subset_rerun", "production_mapping_changed", "production_constructor_changed"):
            self.assertIs(self.manifest[flag], False)
        context = self.report["experiment_context"]
        self.assertIs(context["original_replay_numeric_differences_measured"], True)
        self.assertIs(context["candidate_is_not_observed_CoreText_internal_state"], True)
        self.assertIs(self.manifest["experiment_interpretation"]["private_CoreText_operation_order_uniquely_proven"], False)


if __name__ == "__main__":
    unittest.main()
