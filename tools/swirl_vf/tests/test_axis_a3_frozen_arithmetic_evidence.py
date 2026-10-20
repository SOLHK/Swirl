"""Regression checks on real Apple A3 evidence, never a simulated native pass.

The immutable first archive intentionally retains all 804 early classifier
rejections. Native completion, exact horizontal metrics, geometry budgets and
strict replay have separate assertions so none can certify the other. The
native repeat may change only source identity and diagnostic classifications.
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
from axis_a3_arithmetic_cases import arithmetic_cases, arithmetic_mappings
from axis_a3_input_cases import representations

MANIFEST = PLATFORM / "axis_a3_arithmetic_evidence_20261020.json"
SOURCE_SHA = "eda37d1c733cb1ced283583434e4123824a2147c"
FONT_SHA = "39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890"
STATUS = "COMPLETED_NATIVE_A3_ARITHMETIC_DIAGNOSIS_NOT_ACCEPTANCE"
ENDPOINT = "canonical_identity_negative_endpoint32_positive64_normalized16_truncate"
OFFSET = "canonical_identity_negative_offset32_positive64_normalized16_truncate"
DIVSUB = "canonical_identity_negative_divsub32_positive64_normalized16_truncate"
ALL_AXES = "canonical_all_axes_float32_offset_normalized16_truncate"
TAGS = ("WDTH", "wght", "HGHT")


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


class FrozenArithmeticEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_bytes())
        cls.entry = next(a for a in cls.manifest["archives"] if a["id"] == "arithmetic_eda37d1")
        cls.archive_path = PLATFORM / cls.entry["archive"]
        cls.archive_bytes = cls.archive_path.read_bytes()
        with zipfile.ZipFile(cls.archive_path) as archive:
            cls.members = archive.namelist()
            cls.raw = archive.read(cls.entry["report_member"])
        cls.report = json.loads(cls.raw)
        cls.repeat_entry = next(a for a in cls.manifest["archives"] if a["id"] == "arithmetic_9c2fd00")
        repeat_path = PLATFORM / cls.repeat_entry["archive"]
        cls.repeat_archive_bytes = repeat_path.read_bytes()
        with zipfile.ZipFile(repeat_path) as archive:
            cls.repeat_members = archive.namelist()
            cls.repeat_raw = archive.read(cls.repeat_entry["report_member"])
        cls.repeat_report = json.loads(cls.repeat_raw)

    def test_actual_archive_member_source_and_ci_identity(self):
        e, r = self.entry, self.report
        self.assertEqual(e["archive"], "axis_a3_arithmetic_native_eda37d1.zip")
        self.assertEqual(len(self.archive_bytes), e["archive_bytes"])
        self.assertEqual(e["archive_bytes"], 202162)
        self.assertEqual(hashlib.sha256(self.archive_bytes).hexdigest(), e["archive_sha256"])
        self.assertEqual(e["archive_sha256"],
                         "951092a6f3116dcf26b4a799a3d0d260a3b5ca59a3c4f44389ca277e7f5c64c1")
        self.assertEqual(self.members, ["arithmetic.json"])
        self.assertEqual(e["report_member"], self.members[0])
        self.assertEqual(len(self.raw), e["report_bytes"])
        self.assertEqual(e["report_bytes"], 11530594)
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), e["report_sha256"])
        self.assertEqual(e["report_sha256"],
                         "64483c46413e2ed0fe33731ef75dd22132a59a0da112bf791c0bff950da86f4d")
        self.assertEqual((e["source_commit"], r["source_commit"]), (SOURCE_SHA, SOURCE_SHA))
        self.assertEqual((e["ci_run_id"], e["artifact_id"], e["native_job_id"]),
                         (39404600942, 12255423793, 118567521503))
        self.assertEqual(e["ci_url"], "https://github.com/SOLHK/Swirl/actions/runs/39404600942")
        self.assertEqual((e["ci_status"], e["ci_conclusion"]), ("completed", "success"))
        self.assertEqual(r["status"], e["reported_status"])
        self.assertEqual(r["status"], STATUS)
        self.assertEqual(r["source_sha256"], self.manifest["original_source_sha256"])
        self.assertEqual(r["source_sha256"], FONT_SHA)

    def test_complete_native_counts_do_not_hide_the_early_classifier_rejection(self):
        r, e = self.report, self.entry
        self.assertEqual(len(r["native_processes"]), e["native_processes"])
        self.assertEqual({(p["mode"], p["order"]) for p in r["native_processes"]}, {
            (mode, order) for mode in ("anchor_endpoint_original", "anchor_quarter_original")
            for order in ("forward", "reverse")})
        for process in r["native_processes"]:
            self.assertIs(process["all_32_physical_faces_verified"], True)
            self.assertIs(process["constructor_entry_bits_verified"], True)
            self.assertEqual(process["exit_status"], 0)
            self.assertEqual(process["summary"]["error_count"], 0)
            self.assertEqual(process["summary"]["source_sha256"], FONT_SHA)
            self.assertEqual(process["summary"]["request_count"], 402)
            self.assertEqual(process["constructor_entry_records"], 402)
            self.assertEqual(process["summary"]["successful_glyph_count"], 2010)
        counts = {
            "native_records": sum(p["summary"]["successful_glyph_count"] for p in r["native_processes"]),
            "constructor_entry_records": sum(p["constructor_entry_records"] for p in r["native_processes"]),
            "opposite_order_pairs": sum(m["opposite_order_pairs"] for m in r["modes"]),
            "replay_batches": sum(m["replay_batch_checks"] for m in r["modes"]),
        }
        self.assertEqual(counts, {"native_records": 8040, "constructor_entry_records": 1608,
                                  "opposite_order_pairs": 4020, "replay_batches": 804})
        for key, value in counts.items():
            self.assertEqual(e[key], value)
            self.assertEqual(r["actual_" + key], value)
        self.assertEqual(r["planned_native_records"], 201 * 2 * 2 * 5 * 2)
        self.assertEqual(sum(m["opposite_order_exact_pairs"] for m in r["modes"]), 4020)
        self.assertTrue(all(not m["opposite_order_mismatches"] for m in r["modes"]))
        self.assertEqual((r["planned_direct_HVF_positions"], r["native_HVF_unique_calls"]), (93, 160))
        self.assertIs(r["HVF_geometry_references_cached_by_face_gid_and_design"], True)
        classifiers = [c for m in r["modes"] for c in m["default_omission_checks"]]
        self.assertEqual(len(classifiers), counts["replay_batches"])
        self.assertEqual(Counter((c["classification"], c["reason"]) for c in classifiers),
                         {("REJECTED", "original_table_binding_incomplete"): 804})
        self.assertIs(e["original_classifier_bug_retained"], True)
        for result in classifiers:
            self.assertIs(result["diagnostic_passed"], False)
            # This default follows rejection before the bit check, despite the
            # independent harness above having verified all actual entry bits.
            self.assertIs(result["constructor_entry_binary64_unchanged"], False)
            self.assertEqual(result["legacy_strict_replay"]["status"], "NOT_EVALUATED_INVALID_EVIDENCE")
        self.assertEqual(self.manifest["initial_classifier_failure"]["rejected_batches"], 804)

    def test_original_axes_avar_order_duplicates_and_frozen_plan_survive(self):
        r = self.report
        self.assertEqual(canonical_sha(r["original_faces"]),
                         "c02af3963cc2e2ee93917149f090842da26ee7f7c5b120dd7e12fab36369d8fe")
        self.assertEqual([f["face_index"] for f in r["original_faces"]], list(range(32)))
        total, patterns = 0, Counter()
        axes = {}
        for face in r["original_faces"]:
            axes[face["face_index"]] = face["original_axes"]
            self.assertEqual(tuple(face["original_axes"]), TAGS)
            self.assertEqual(tuple(face["original_avar_records_in_table_order"]), TAGS)
            for tag, records in face["original_avar_records_in_table_order"].items():
                total += len(records)
                for pair in records:
                    self.assertEqual(len(pair), 2)
                    self.assertTrue(all(v * 16384 == int(v * 16384) for v in pair))
                if tag == "wght":
                    counts = Counter(pair[0] for pair in records)
                    patterns[tuple((v, n) for v, n in counts.items() if n > 1)] += 1
                else:
                    self.assertEqual(records, [[-1., -1.], [0., 0.], [1., 1.]])
        self.assertEqual(total, 560)
        self.assertEqual(patterns, {((-1., 2), (0., 2), (1., 2)): 20, ((1., 2),): 12})
        self.assertEqual(axes[15], {"WDTH": [1., 500., 1000.], "wght": [100., 499., 900.],
                                   "HGHT": [1., 500., 1000.]})
        self.assertEqual(canonical_sha(r["cases"]),
                         "f455254225e52ae810eb7b56b7ac52ae11002960fb6d54ae862f4264b9d1cdd5")
        generated = arithmetic_cases(axes)
        self.assertEqual(len(generated), 201)
        self.assertEqual(Counter(c["group"] for c in generated), {
            "fresh_random_holdout": 64, "normalized16_integer_boundary_holdout": 36,
            "default_omission_boundary_holdout": 60, "historical_control": 41})
        self.assertEqual(len({(c["face_index"], *(c["location"][tag] for tag in TAGS)) for c in generated}), 193)
        self.assertEqual(sum(c["is_holdout"] for c in generated), 160)
        self.assertEqual(r["fresh_holdout_seed"], 2745573414)
        self.assertIs(r["all_cases_and_mappings_declared_before_native_launch"], True)
        for case, saved in zip(generated, r["cases"]):
            self.assertEqual(case, {k: v for k, v in saved.items()
                                   if k not in ("binary64_bits", "declared_models", "predeclared_replay")})
            self.assertEqual(saved["binary64_bits"],
                             {tag: struct.pack(">d", value).hex() for tag, value in case["location"].items()})
            face = r["original_faces"][case["face_index"]]
            font = {"fvar": SimpleNamespace(axes=[
                SimpleNamespace(axisTag=tag, minValue=v[0], defaultValue=v[1], maxValue=v[2])
                for tag, v in face["original_axes"].items()])}
            # Only original axis metadata, ordered records and user inputs are
            # supplied; no observed metrics or paths enter the 1206 vectors.
            self.assertEqual(arithmetic_mappings(font, face["original_avar_records_in_table_order"],
                                                case["location"]), saved["declared_models"])

    def test_all_56_strict_replay_failures_remain_visible_separately_from_classifier(self):
        categories = Counter()
        for mode in self.report["modes"]:
            self.assertEqual((mode["replay_batch_checks"], mode["replay_failed_batches"]), (402, 28))
            self.assertEqual(len(mode["replay_failures"]), 28)
            self.assertEqual(len({f["case_label"] for f in mode["replay_failures"]}), 14)
            self.assertEqual(Counter(f["order"] for f in mode["replay_failures"]), {"forward": 14, "reverse": 14})
            for fail in mode["replay_failures"]:
                self.assertEqual(fail["status"], "FAILED_FINITE_REPLAY")
                self.assertEqual(fail["glyph_pairs"], 5)
                codes = Counter(e["failure_code"] for e in fail["readback_failures"])
                if codes == {"native_nondefault_axis_not_reported": 5}:
                    self.assertTrue(fail["case_label"].startswith("arithmetic_default_"))
                    self.assertTrue(fail["case_label"].endswith("_nextafter_above"))
                    self.assertEqual(fail["payload_differences"], [])
                    categories["default_omission"] += 1
                elif codes == {"native_readback_replay_not_exactly_stable": 5}:
                    self.assertEqual(fail["case_label"], "arithmetic_fresh_22_0")
                    self.assertEqual(fail["payload_differences"], [])
                    categories["unstable_readback"] += 1
                else:
                    self.assertEqual(codes, {})
                    self.assertEqual(fail["case_label"], "arithmetic_fresh_30_0")
                    self.assertEqual([d["glyph_id"] for d in fail["payload_differences"]], [5, 12, 56, 169, 19177])
                    categories["payload_changed"] += 1
        self.assertEqual(categories, {"default_omission": 48, "unstable_readback": 4, "payload_changed": 4})
        self.assertEqual(sum(categories.values()), self.entry["strict_replay_failed_batches"])

    def test_fresh22_unstable_replay_and_fresh30_equal_metrics_do_not_certify_payloads(self):
        for mode in self.report["modes"]:
            observed = {o["label"]: o for o in mode["observations"]}
            for fail in mode["replay_failures"]:
                if fail["case_label"] == "arithmetic_fresh_22_0":
                    self.assertEqual(observed[fail["case_label"]]["reported_location"]["HGHT"], 1.1279)
                    self.assertEqual(fail["predeclared_replay_location"]["HGHT"], 1.1279)
                    for error in fail["readback_failures"]:
                        self.assertEqual((error["axis"], error["phase"]), ("HGHT", "replay"))
                        self.assertEqual((error["requested_value"], error["reported_value"]), (1.1279, 1.1278))
                if fail["case_label"] == "arithmetic_fresh_30_0":
                    row = observed[fail["case_label"]]
                    self.assertEqual(row["reported_location"], fail["predeclared_replay_location"])
                    self.assertEqual(row["reported_location"], {"WDTH": 729.2925, "wght": 660.9897, "HGHT": 303.5933})
                    # No strict readback failure, yet every selected glyph's
                    # raw payload changed; only field names were published.
                    self.assertEqual(fail["readback_failures"], [])
                    self.assertEqual({d["glyph_id"]: d["fields"] for d in fail["payload_differences"]}, {
                        5: ["bounds", "commands", "lsb"], 12: ["bounds", "commands"],
                        56: ["bounds", "commands", "lsb"], 169: ["bounds", "commands", "lsb"],
                        19177: ["bounds", "commands", "lsb"],
                    })
                    for name in (ENDPOINT, OFFSET):
                        result = row["model_checks"][name]
                        self.assertIs(result["exact"], True)
                        self.assertEqual(result["maximum_error"], 0)
                        self.assertTrue(all(x["signed_error"] == 0 for x in result["four_metric_residuals"]))
                        self.assertEqual([(c["glyph_id"], c["maximum_point_error"])
                                          for c in result["native_HVF_geometry"]],
                                         [(5, 0.008711728120943008), (19177, 0.009678105302214135)])
                        self.assertTrue(all(c["status"] == "within_budget" and 0 < c["maximum_point_error"] <= 1/32
                                            for c in result["native_HVF_geometry"]))

    def test_new_divsub_counterexample_and_original_fixed_collision_remain_failures(self):
        cases = {c["label"]: c for c in self.report["cases"]}
        pair = [cases["arithmetic_original_collision_" + side] for side in ("low", "high")]
        values = [representations(c["location"]["wght"]) for c in pair]
        self.assertEqual([v["fixed16_integer"] for v in values], [32702870, 32702870])
        self.assertEqual([v["float32_bits"] for v in values], ["43f980cb", "43f980cb"])
        self.assertNotEqual(values[0]["binary64_bits"], values[1]["binary64_bits"])
        for c in pair:
            self.assertEqual((c["face_index"], c["location"]["WDTH"], c["location"]["HGHT"]), (15, 500, 500))
        for name in self.report["model_descriptions"]:
            self.assertEqual([c["declared_models"][name]["wght"] * 16384 for c in pair],
                             [65, 65] if name == ALL_AXES else [0, 65])
        for mode in self.report["modes"]:
            rows = {o["label"]: o for o in mode["observations"]}
            self.assertEqual([rows[c["label"]]["reported_location"] for c in pair],
                             [{"wght": 499.0061}, {"wght": 499.0062}])
            result = rows[pair[0]["label"]]["model_checks"][ALL_AXES]
            self.assertIs(result["exact"], False)
            self.assertIs(result["within_1_32"], False)
            self.assertEqual(result["maximum_error"], 0.5474853515625)
            self.assertEqual(result["four_metric_residuals"][0]["signed_error"], -0.5474853515625)
            self.assertEqual(Fraction(result["maximum_error"]) / 2, Fraction(4485, 16384))
            self.assertEqual(sum(c["status"] == "outside_budget" for c in result["portable_geometry"]), 5)
            self.assertEqual(sum(c["status"] == "outside_budget" for c in result["native_HVF_geometry"]), 2)
            boundary = rows["arithmetic_integer_0_WDTH_-42539_above"]
            self.assertIs(boundary["is_holdout"], True)
            failed = boundary["model_checks"][DIVSUB]
            self.assertEqual(failed["maximum_error"], 0.01220703125)
            self.assertIs(failed["within_1_32"], True)
            self.assertIs(failed["exact"], False)  # Finite tolerance never means exact.
            for name in (ENDPOINT, OFFSET):
                self.assertEqual(boundary["model_checks"][name]["maximum_error"], 0)
                self.assertEqual(mode["models"][name]["horizontal_metrics"],
                                 {"checks": 201, "exact_matches": 201, "outside_1_32": 0, "maximum_error": 0.0})
                hvf = mode["models"][name]["native_HVF_geometry"]["preserved_controls"]
                self.assertEqual((hvf["checks"], hvf["failures"], hvf["maximum_point_error"]),
                                 (186, 0, 0.009678105302214135))

    def test_frozen_native_results_agree_between_independent_constructor_modes(self):
        first, second = self.report["modes"]
        self.assertNotEqual(first["mode"], second["mode"])
        for field in ("observations", "models", "replay_failures", "metric_exactness_by_cohort"):
            self.assertEqual(first[field], second[field])
        self.assertEqual(canonical_sha(first["observations"]),
                         "01ca05f3155da23d6d5a0881e54993a60a6a3e4445b925f6fa7e5c60629e6ed2")
        self.assertEqual(canonical_sha(first["models"]),
                         "581d219fca2c892fbbcf81cc44aa6918ad4d7381a3da931147580cfe49223cd3")
        self.assertEqual(canonical_sha(first["replay_failures"]),
                         "8d810fd382859611d853b2cbba0c962e6bb8eb2c91bc150587c50fbf4a540792")

    def test_repeat_archive_and_ci_are_bound_to_the_diagnostic_fix(self):
        e, r = self.repeat_entry, self.repeat_report
        fix = "9c2fd0092284edc7d346b0c9e1d1208095429b39"
        self.assertEqual(e["archive"], "axis_a3_arithmetic_native_9c2fd00.zip")
        self.assertEqual((len(self.repeat_archive_bytes), e["archive_bytes"]), (253358, 253358))
        self.assertEqual(hashlib.sha256(self.repeat_archive_bytes).hexdigest(), e["archive_sha256"])
        self.assertEqual(e["archive_sha256"],
                         "3a4239c867d1e745550c189d7624f1d79b6beb4f8b3d36b405eec5a8aca96e56")
        self.assertEqual(self.repeat_members, ["arithmetic.json"])
        self.assertEqual(e["report_member"], self.repeat_members[0])
        self.assertEqual((len(self.repeat_raw), e["report_bytes"]), (12202758, 12202758))
        self.assertEqual(hashlib.sha256(self.repeat_raw).hexdigest(), e["report_sha256"])
        self.assertEqual(e["report_sha256"],
                         "d5ea884cdd1c7ffdf0efdf2dd264c3ee05d69550b55d2319565c6d5ebe9201c6")
        self.assertEqual((e["source_commit"], r["source_commit"],
                          self.manifest["diagnostic_fix"]["source_commit"]), (fix, fix, fix))
        self.assertEqual((e["ci_run_id"], e["artifact_id"], e["native_job_id"]),
                         (39405368777, 12256825953, 118570021118))
        self.assertEqual(e["ci_url"], "https://github.com/SOLHK/Swirl/actions/runs/39405368777")
        self.assertEqual((e["ci_status"], e["ci_conclusion"]), ("completed", "success"))
        self.assertEqual((e["reported_status"], r["status"]), (STATUS, STATUS))
        for key in ("native_records", "native_processes", "constructor_entry_records", "opposite_order_pairs",
                    "replay_batches", "native_HVF_unique_calls", "labelled_cases", "unique_face_locations",
                    "new_holdout_labels", "historical_control_labels", "strict_replay_failed_batches"):
            self.assertEqual(e[key], self.entry[key])
        self.assertIs(self.manifest["diagnostic_fix"]["production_changed"], False)
        self.assertIs(self.manifest["diagnostic_fix"]["native_repeat_completed"], True)
        self.assertIs(e["all_flags_remain_diagnostic_only"], True)

    def test_repeat_changes_only_source_commit_and_classifier_results(self):
        first, repeat = self.report, self.repeat_report
        self.assertEqual(set(first), set(repeat))
        changed = {k for k in first if first[k] != repeat[k]}
        self.assertEqual(changed, {"source_commit", "modes"})
        self.assertNotEqual(first["source_commit"], repeat["source_commit"])
        for key in set(first) - changed:
            with self.subTest(top_level_field=key):
                self.assertEqual(first[key], repeat[key])
        self.assertEqual(len(first["modes"]), len(repeat["modes"]))
        for old_mode, new_mode in zip(first["modes"], repeat["modes"]):
            self.assertEqual(set(old_mode), set(new_mode))
            self.assertEqual({k for k in old_mode if old_mode[k] != new_mode[k]},
                             {"default_omission_checks"})
            for key in set(old_mode) - {"default_omission_checks"}:
                with self.subTest(mode=old_mode["mode"], field=key):
                    self.assertEqual(old_mode[key], new_mode[key])
        relation = self.manifest["repeat_relation"]
        self.assertEqual((relation["first"], relation["repeat"]),
                         (self.entry["id"], self.repeat_entry["id"]))
        self.assertEqual(relation["only_changed_paths"], ["source_commit", "modes[*].default_omission_checks"])
        for key in ("all_other_report_values_exactly_equal", "strict_replay_failures_unchanged",
                    "original_table_binding_failure_in_first_report_preserved"):
            self.assertIs(relation[key], True)

    def test_repeat_default_equivalence_is_narrow_and_never_waives_fresh_replay_failures(self):
        r = self.repeat_report
        cases = {c["label"]: c for c in r["cases"]}
        totals, rejected_reasons = Counter(), Counter()
        for mode in r["modes"]:
            rows = mode["default_omission_checks"]
            self.assertEqual(len(rows), 402)
            self.assertEqual(Counter(row["classification"] for row in rows), {
                "STRICT_REPLAY_ALREADY_PASSED": 374,
                "DEFAULT_OMISSION_EQUIVALENT_FOR_THIS_BATCH": 24, "REJECTED": 4})
            self.assertEqual({(row["case_label"], row["order"]) for row in rows},
                             {(label, order) for label in cases for order in ("forward", "reverse")})
            strict_failed = {(f["case_label"], f["order"]) for f in mode["replay_failures"]}
            observed = {o["label"]: o for o in mode["observations"]}
            for row in rows:
                totals[row["classification"]] += 1
                case = cases[row["case_label"]]
                self.assertEqual(row["face_index"], case["face_index"])
                self.assertEqual(row["requested_location"], case["location"])
                self.assertEqual(row["requested_binary64_bits"], case["binary64_bits"])
                self.assertEqual(row["predeclared_replay_location"], case["predeclared_replay"])
                self.assertEqual(row["original_reported_location"], observed[row["case_label"]]["reported_location"])
                self.assertEqual(row["scope"], "one_complete_observed_batch_only")
                self.assertEqual(row["submission_evidence_site"], "constructor_entry")
                self.assertIs(row["constructor_entry_binary64_unchanged"], True)
                self.assertEqual(row["requested_GID_count"], 5)
                legacy = row["legacy_strict_replay"]
                self.assertEqual(legacy["requested_GID_count"], 5)
                key = (row["case_label"], row["order"])
                if row["classification"] == "STRICT_REPLAY_ALREADY_PASSED":
                    self.assertNotIn(key, strict_failed)
                    self.assertEqual(legacy["status"], "PASS_FINITE_REPLAY")
                    self.assertIs(row["strict_replay_passed"], True)
                    self.assertIs(row["diagnostic_passed"], True)
                    self.assertIs(row["default_omission_equivalent"], False)
                    self.assertIs(legacy["all_payloads_exactly_equal"], True)
                    self.assertEqual(row["explained_omitted_axes"], [])
                    self.assertEqual(row["failures"], [])
                elif row["classification"] == "DEFAULT_OMISSION_EQUIVALENT_FOR_THIS_BATCH":
                    self.assertIn(key, strict_failed)  # The legacy rejection is retained.
                    self.assertEqual(legacy["status"], "FAILED_FINITE_REPLAY")
                    self.assertIs(row["strict_replay_passed"], False)
                    self.assertIs(row["diagnostic_passed"], True)
                    self.assertIs(row["default_omission_equivalent"], True)
                    self.assertEqual(case["group"], "default_omission_boundary_holdout")
                    self.assertEqual(case["default_side"], "nextafter_above")
                    self.assertIn(case["face_index"], (0, 5, 20, 24))
                    axis = case["boundary_axis"]
                    defaults = {tag: v[1] for tag, v in r["original_faces"][case["face_index"]]["original_axes"].items()}
                    requested = dict(defaults)
                    requested[axis] = math.nextafter(defaults[axis], math.inf)
                    self.assertEqual(row["requested_location"], requested)
                    self.assertNotEqual(requested, defaults)
                    self.assertEqual(row["predeclared_replay_location"], defaults)
                    self.assertEqual(row["explained_omitted_axes"], [axis])
                    self.assertEqual(row["original_reported_location"], {})
                    self.assertEqual(row["replay_reported_location"], {})
                    self.assertEqual(row["reason"], "predeclared_default_omission_and_exact_complete_replay")
                    self.assertEqual(row["failures"], [])
                    self.assertEqual(legacy["payload_differences"], [])
                    self.assertIs(legacy["all_payloads_exactly_equal"], True)
                    self.assertEqual([f["glyph_id"] for f in legacy["readback_failures"]], r["selected_glyphs"])
                    for failure in legacy["readback_failures"]:
                        self.assertEqual((failure["reason"], failure["phase"], failure["axis"]),
                                         ("native_nondefault_axis_not_reported", "original", axis))
                        self.assertEqual(failure["requested_value"], requested[axis])
                        self.assertIs(failure["reported_axis_present"], False)
                else:
                    self.assertEqual(row["classification"], "REJECTED")
                    self.assertIn(key, strict_failed)
                    self.assertEqual(legacy["status"], "FAILED_FINITE_REPLAY")
                    self.assertIs(row["diagnostic_passed"], False)
                    self.assertIs(row["strict_replay_passed"], False)
                    self.assertIs(row["default_omission_equivalent"], False)
                    self.assertEqual(row["explained_omitted_axes"], [])
                    rejected_reasons[row["reason"]] += 1
                    if row["case_label"] == "arithmetic_fresh_22_0":
                        self.assertEqual(row["reason"], "native_readback_replay_not_exactly_stable")
                        self.assertEqual(row["original_reported_location"]["HGHT"], 1.1279)
                        self.assertEqual(row["predeclared_replay_location"]["HGHT"], 1.1279)
                        self.assertEqual(row["replay_reported_location"]["HGHT"], 1.1278)
                        self.assertIs(legacy["all_payloads_exactly_equal"], True)
                        self.assertEqual(legacy["payload_differences"], [])
                    else:
                        self.assertEqual(row["case_label"], "arithmetic_fresh_30_0")
                        self.assertEqual(row["reason"], "native_replay_payload_not_exact")
                        self.assertEqual(row["original_reported_location"], row["replay_reported_location"])
                        self.assertEqual(row["replay_reported_location"], row["predeclared_replay_location"])
                        self.assertEqual(legacy["readback_failures"], [])
                        self.assertIs(legacy["all_payloads_exactly_equal"], False)
                        self.assertEqual([f["glyph_id"] for f in legacy["payload_differences"]], r["selected_glyphs"])
                    self.assertEqual(len(row["failures"]), 5)
        self.assertEqual(totals, {"STRICT_REPLAY_ALREADY_PASSED": 748,
                                  "DEFAULT_OMISSION_EQUIVALENT_FOR_THIS_BATCH": 48, "REJECTED": 8})
        self.assertEqual(rejected_reasons, {"native_readback_replay_not_exactly_stable": 4,
                                           "native_replay_payload_not_exact": 4})
        evidence = self.manifest["repeat_diagnostic_classification"]
        self.assertEqual((evidence["batches"], evidence["strict_replay_already_passed"],
                          evidence["default_omission_equivalent_for_this_batch"], evidence["rejected"]),
                         (804, 748, 48, 8))
        self.assertEqual(evidence["rejection_counts"], rejected_reasons)
        self.assertIs(evidence["all_constructor_entry_binary64_unchanged"], True)
        for key in ("production_mapping_accepted", "continuous_space_accepted", "final_font_accepted"):
            self.assertIs(evidence[key], False)

    def test_public_archive_contains_residuals_not_raw_apple_payload_or_acceptance(self):
        r = self.report
        for key in ("mapping_accepted", "font_generated", "continuous_space_accepted",
                    "production_constructor_changed", "production_mapping_changed",
                    "raw_avar_records_modified", "original_141_subset_rerun",
                    "source_outlines_or_raw_metrics_published"):
            self.assertIs(r[key], False)
        for key in ("production_mapping_accepted", "continuous_space_accepted", "final_font_accepted",
                    "production_mapping_changed", "production_constructor_changed", "original_141_subset_rerun"):
            self.assertIs(self.manifest[key], False)
        self.assertEqual((r["metric_limit_font_units"], r["outline_limit_font_units"],
                          self.manifest["strict_limit_font_units"]), (1/32, 1/32, 1/32))
        self.assertIs(r["source_unchanged"], True)
        self.assertIs(r["constructor_entry_is_not_CoreText_internal_state"], True)
        self.assertIs(r["independent_processes_do_not_claim_system_cache_reset"], True)
        forbidden = {"commands", "bounds", "advance_width", "advance_height", "lsb", "rsb",
                     "outline", "raw_native_payload", "font_bytes", "path_px", "base64"}

        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
            elif isinstance(value, float):
                self.assertTrue(math.isfinite(value))

        for report in (r, self.repeat_report):
            inspect(report)
            for mode in report["modes"]:
                for row in mode["default_omission_checks"]:
                    for flag in ("mapping_accepted", "production_mapping_accepted", "production_accepted",
                                 "font_accepted", "continuous_space_accepted", "native_values_modified",
                                 "source_user_mapping_inferred", "native_execution_performed_by_classifier"):
                        self.assertIs(row[flag], False)


if __name__ == "__main__":
    unittest.main()
