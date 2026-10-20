"""Startup evidence boundaries using self-authored TTC bytes and native test doubles.

These are protocol/orchestration tests. No test invokes or claims CoreText.
The execute tests explicitly substitute 32 small identities for the native
source's physical-face requirement; separate tests retain that production gate.
"""
import copy
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import b1_original_startup as b1
from b1_metric_fixture import build_fixture


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bits(value):
    return struct.pack(">d", float(value)).hex()


@lru_cache(maxsize=1)
def small_collection():
    """Two independently authored, three-glyph fixture faces; no Apple data."""
    collection = TTCollection()
    collection.fonts = [build_fixture(upem, "vorg_y") for upem in (1000, 1024)]
    stream = io.BytesIO()
    try:
        collection.save(stream)
        return stream.getvalue()
    finally:
        collection.close()


def source_identities(count=2, vorg=True):
    """Small, distinct source identities for adversarial report validation."""
    result = []
    for index in range(count):
        payloads = {"head": b"head-" + str(index).encode(), "maxp": b"maxp",
                    "name": b"name-" + str(index).encode()}
        if vorg:
            payloads["VORG"] = struct.pack(">HHhH", 1, 0, 911, 0)
        result.append({"face_index": index,
                       "expected_tables": [{"tag": tag, "length": len(data), "sha256": digest(data)}
                                           for tag, data in sorted(payloads.items())],
                       "expected_upem": 1000, "expected_glyph_count": 3,
                       "source_directory_has_vorg": vorg})
    return result


def native_report(identities, source_digest="a" * 64, size=4096, api_status="NON_NIL", direct_vorg=None):
    """Construct self-consistent test evidence; validators must rederive it."""
    faces = [{**copy.deepcopy(identity), "parse_status": "PARSED",
              "expected_source_sha256": source_digest, "expected_source_size": size,
              "exact_descriptor_indices": [], "unambiguous_descriptor_indices": []}
             for identity in identities]
    face_by_index = {face["face_index"]: face for face in faces}
    descriptors = []
    for index, actual_identity in enumerate(identities if api_status == "NON_NIL" else []):
        actual = {table["tag"]: table for table in actual_identity["expected_tables"]}
        vorg_table = actual.get("VORG")
        vorg = ({"present": True, "length": vorg_table["length"], "sha256": vorg_table["sha256"]}
                if vorg_table else {"present": False, "length": None, "sha256": None})
        if direct_vorg is not None:
            vorg = copy.deepcopy(direct_vorg)
        comparisons, matches = [], []
        for wanted in identities:
            table_rows = []
            for table in wanted["expected_tables"]:
                observed = actual.get(table["tag"])
                present = observed is not None
                length_equal = present and observed["length"] == table["length"]
                hash_equal = present and observed["sha256"] == table["sha256"]
                table_rows.append({"tag": table["tag"], "expected_length": table["length"],
                                   "expected_sha256": table["sha256"], "actual_present": present,
                                   "actual_length": observed["length"] if present else None,
                                   "actual_sha256": observed["sha256"] if present else None,
                                   "length_equal": length_equal, "sha256_equal": hash_equal,
                                   "exact": length_equal and hash_equal})
            all_exact = all(row["exact"] for row in table_rows)
            upem_equal = actual_identity["expected_upem"] == wanted["expected_upem"]
            glyph_equal = actual_identity["expected_glyph_count"] == wanted["expected_glyph_count"]
            comparisons.append({"face_index": wanted["face_index"], "tables": table_rows,
                                "all_retained_tables_exact": all_exact, "upem_equal": upem_equal,
                                "glyph_count_equal": glyph_equal})
            if all_exact and upem_equal and glyph_equal:
                matches.append(wanted["face_index"])
                face_by_index[wanted["face_index"]]["exact_descriptor_indices"].append(index)
        if len(matches) == 1:
            face_by_index[matches[0]]["unambiguous_descriptor_indices"].append(index)
        matrix = {"xx": 1.0, "xy": 0.0, "yx": 0.0, "yy": 1.0, "tx": 0.0, "ty": 0.0}
        descriptors.append({"descriptor_index": index, "font_upem": actual_identity["expected_upem"],
                            "font_glyph_count": actual_identity["expected_glyph_count"],
                            "font_size": 12.0, "font_size_binary64_hex": bits(12),
                            "font_matrix": matrix, "font_matrix_binary64_hex": {k: bits(v) for k, v in matrix.items()},
                            "descriptor_url_present": True, "descriptor_url_matches_source": True,
                            "font_url_present": True, "font_url_matches_source": True,
                            "direct_vorg": vorg, "face_comparisons": comparisons,
                            "exact_matching_face_indices": sorted(matches)})
    verified = sum(bool(face["unambiguous_descriptor_indices"]) for face in faces)
    ambiguous = sum(bool(face["exact_descriptor_indices"]) and not face["unambiguous_descriptor_indices"]
                    for face in faces)
    return {"schema": b1.SCHEMA, "status": "DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE",
            "source": {"sha256": source_digest, "size": size, "sha256_after": source_digest,
                       "size_after": size, "unchanged": True}, "raw_face_count": len(identities),
            "descriptor_api": {"status": api_status, "count": len(descriptors)},
            "faces": faces, "descriptors": descriptors,
            "summary": {"parsed_face_count": len(faces), "identity_verified_face_count": verified,
                        "unbound_face_count": len(faces) - verified - ambiguous, "ambiguous_face_count": ambiguous,
                        "descriptor_count": len(descriptors), "metrics_observed": 0,
                        "all_faces_identity_verified": verified == len(faces)},
            "startup_semantics": {"font_registration_called": False, "requested_font_size": 0,
                                  "requested_identity_matrix": True, "table_options_raw_value": 0},
            "error_codes": []}


def summarized(label, api_status="NON_NIL", direct_vorg=None, mutate=None):
    identities = source_identities(vorg=label != "private_without_vorg")
    raw = native_report(identities, api_status=api_status, direct_vorg=direct_vorg)
    if mutate:
        mutate(raw)
    validation = b1.validate_report(raw, "a" * 64, 4096, identities)
    return b1.summarize_variant(label, raw, validation)


class SourceStartupIdentityTests(unittest.TestCase):
    def test_raw_identities_match_every_serialized_table_and_physical_face(self):
        data = small_collection()
        identities = b1.expected_faces(data)
        self.assertEqual([row["expected_upem"] for row in identities], [1000, 1024])
        self.assertEqual([row["expected_glyph_count"] for row in identities], [3, 3])
        collection = TTCollection(io.BytesIO(data), lazy=True)
        try:
            for index, (font, identity) in enumerate(zip(collection.fonts, identities)):
                expected = [{"tag": tag, "length": len(font.reader[tag]), "sha256": digest(font.reader[tag])}
                            for tag in sorted(font.reader.keys())]
                self.assertEqual(identity["face_index"], index)
                self.assertEqual(identity["expected_tables"], expected)
                self.assertTrue(identity["source_directory_has_vorg"])
        finally:
            collection.close()

    def test_directory_ablation_changes_source_identity_without_reserializing_retained_tables(self):
        original = small_collection()
        modified, evidence = b1.remove_vorg_directories(original)
        self.assertNotEqual(digest(modified), digest(original))
        self.assertEqual(len(modified), len(original))
        self.assertTrue(evidence["all_non_directory_bytes_identical"])
        for before, after in zip(b1.expected_faces(original), b1.expected_faces(modified)):
            self.assertFalse(after["source_directory_has_vorg"])
            self.assertEqual(after["expected_tables"], [table for table in before["expected_tables"] if table["tag"] != "VORG"])
            self.assertEqual(after["expected_upem"], before["expected_upem"])
            self.assertEqual(after["expected_glyph_count"], before["expected_glyph_count"])


class StartupReportValidationTests(unittest.TestCase):
    def setUp(self):
        self.identities = source_identities()
        self.raw = native_report(self.identities)

    def validate(self, raw):
        return b1.validate_report(raw, "a" * 64, 4096, self.identities)

    def test_valid_report_recomputes_identity_and_bits_without_metric_acceptance(self):
        counts = self.validate(self.raw)
        self.assertEqual(counts["binary64_values_verified"], 14)
        self.assertEqual(counts["retained_table_comparisons_recomputed"], 16)
        self.assertEqual(counts["source_table_expectations_verified"], 8)
        self.assertTrue(counts["all_faces_identity_verified"])
        row = b1.summarize_variant("system_original", self.raw, counts)
        self.assertEqual(row["metric_record_count"], 0)
        self.assertFalse(row["font_acceptance"])

    def test_forged_source_table_hash_binding_and_summary_are_rejected(self):
        changes = [
            (lambda r: r["source"].update(sha256="b" * 64), "native_source_binding_mismatch"),
            (lambda r: r["faces"][0]["expected_tables"][0].update(sha256="b" * 64), "native_source_table_identity_mismatch"),
            (lambda r: r["descriptors"][0]["face_comparisons"][0]["tables"][0].update(expected_sha256="b" * 64), "comparison_source_table_mismatch"),
            (lambda r: r["descriptors"][0]["face_comparisons"][0]["tables"][0].update(actual_sha256="b" * 64), "retained_table_result_mismatch"),
            (lambda r: r["descriptors"][0].update(exact_matching_face_indices=[1]), "descriptor_binding_result_mismatch"),
            (lambda r: r["summary"].update(identity_verified_face_count=1), "native_summary_count_mismatch"),
            (lambda r: r["summary"].update(metrics_observed=1), "native_summary_count_mismatch"),
            (lambda r: r["summary"].update(all_faces_identity_verified=False), "native_acceptance_boolean_mismatch"),
        ]
        for mutate, reason in changes:
            raw = copy.deepcopy(self.raw)
            mutate(raw)
            with self.subTest(reason=reason), self.assertRaisesRegex(b1.StartupEvidenceError, reason):
                self.validate(raw)

    def test_duplicate_faces_descriptors_and_comparisons_cannot_inflate_identity(self):
        for field, reason in (("faces", "invalid_native_face_set"), ("descriptors", "invalid_descriptor_set"),
                              ("face_comparisons", "invalid_face_comparison_set")):
            raw = copy.deepcopy(self.raw)
            rows = raw["descriptors"][0][field] if field == "face_comparisons" else raw[field]
            rows.append(copy.deepcopy(rows[0]))
            with self.subTest(field=field), self.assertRaisesRegex(b1.StartupEvidenceError, reason):
                self.validate(raw)

    def test_ambiguous_identical_faces_are_not_counted_as_verified(self):
        identities = source_identities()
        identities[1] = {**copy.deepcopy(identities[0]), "face_index": 1}
        raw = native_report(identities)
        result = b1.validate_report(raw, "a" * 64, 4096, identities)
        self.assertFalse(result["all_faces_identity_verified"])
        self.assertEqual(raw["summary"]["ambiguous_face_count"], 2)
        self.assertEqual(raw["summary"]["identity_verified_face_count"], 0)
        self.assertEqual(b1.summarize_variant("system_original", raw, result)["exact_bound_descriptor_count"], 0)

    def test_binary64_and_strict_source_url_booleans_are_required(self):
        for field in ("descriptor_url_present", "descriptor_url_matches_source", "font_url_present", "font_url_matches_source"):
            raw = copy.deepcopy(self.raw)
            raw["descriptors"][0][field] = "false"
            with self.subTest(field=field), self.assertRaisesRegex(b1.StartupEvidenceError, "invalid_source_url_boolean"):
                self.validate(raw)
        for mutate, reason in (
            (lambda d: d.update(font_size_binary64_hex=bits(13)), "native_size_bits_mismatch"),
            (lambda d: d["font_matrix_binary64_hex"].update(tx=bits(-0.0)), "native_matrix_bits_mismatch"),
            (lambda d: d.update(descriptor_url_present=False), "missing_source_url_cannot_match"),
            (lambda d: d.update(font_url_present=False), "missing_source_url_cannot_match"),
        ):
            raw = copy.deepcopy(self.raw)
            mutate(raw["descriptors"][0])
            with self.subTest(reason=reason), self.assertRaisesRegex(b1.StartupEvidenceError, reason):
                self.validate(raw)

    def test_nil_vorg_cannot_carry_bytes_or_disagree_with_table_observation(self):
        for observation, reason in (
            ({"present": False, "length": 0, "sha256": digest(b"")}, "nil_vorg_has_invented_data"),
            ({"present": False, "length": None, "sha256": None}, "direct_vorg_disagrees_with_table_observation"),
            ({"present": True, "length": 0, "sha256": digest(b"")}, "direct_vorg_disagrees_with_table_observation"),
        ):
            raw = copy.deepcopy(self.raw)
            raw["descriptors"][0]["direct_vorg"] = observation
            with self.subTest(reason=reason), self.assertRaisesRegex(b1.StartupEvidenceError, reason):
                self.validate(raw)

    def test_missing_descriptors_provide_no_bound_vorg_absence_observations(self):
        for status in ("NIL", "EMPTY", "TYPE_MISMATCH"):
            raw = native_report(self.identities, api_status=status)
            result = self.validate(raw)
            summary = b1.summarize_variant("private_identical", raw, result)
            with self.subTest(status=status):
                self.assertFalse(result["all_faces_identity_verified"])
                self.assertEqual(result["binary64_values_verified"], 0)
                self.assertEqual(summary["bound_vorg_nil_count"], 0)
                self.assertEqual(summary["direct_vorg_by_bound_descriptor"], [])
                self.assertIsNone(summary["bound_font_source_urls_match"])


class StartupCausalityTests(unittest.TestCase):
    def variants(self, replacement=None):
        return [replacement if replacement and replacement["variant"] == label else summarized(label)
                for label in b1.LABELS]

    def test_private_original_load_failure_prevents_vorg_causal_attribution(self):
        rows = self.variants(summarized("private_identical", api_status="NIL"))
        self.assertEqual(b1.classify(rows, True), "PRIVATE_LOCATION_LOAD_OR_BINDING_BLOCKED_VORG_CAUSALITY_UNKNOWN")

    def test_system_best_match_for_private_identical_cannot_establish_private_loading(self):
        for field in ("descriptor_url_matches_source", "font_url_matches_source"):
            def mutate(raw):
                raw["descriptors"][0][field] = False
            rows = self.variants(summarized("private_identical", mutate=mutate))
            rows[2] = summarized("private_without_vorg", api_status="NIL")
            with self.subTest(field=field):
                self.assertEqual(b1.classify(rows, True),
                                 "PRIVATE_IDENTICAL_TABLES_MATCH_BUT_SOURCE_URL_NOT_EXACT_VORG_CAUSALITY_UNKNOWN")

    def test_ablated_load_failure_after_verified_private_control_is_only_an_association(self):
        row = summarized("private_without_vorg", api_status="NIL")
        self.assertEqual(b1.classify(self.variants(row), True), "VORG_REMOVAL_ASSOCIATED_WITH_STARTUP_BINDING_FAILURE")
        self.assertEqual(row["bound_vorg_nil_count"], 0)
        self.assertFalse(row["font_acceptance"])

    def test_present_empty_vorg_and_native_nil_have_different_conclusions(self):
        empty = summarized("private_without_vorg", direct_vorg={"present": True, "length": 0, "sha256": digest(b"")})
        self.assertEqual(empty["bound_vorg_present_count"], 2)
        self.assertEqual(empty["bound_vorg_nil_count"], 0)
        self.assertEqual(b1.classify(self.variants(empty), True), "REMOVED_DIRECTORY_VORG_STILL_NATIVE_VISIBLE")
        rows = self.variants()
        self.assertEqual(rows[2]["bound_vorg_nil_count"], 2)
        self.assertEqual(b1.classify(rows, True), "PRIVATE_NO_VORG_BOUND_AND_VORG_API_NIL_STARTUP_ONLY")
        self.assertTrue(all(not row["font_acceptance"] and row["metric_record_count"] == 0 for row in rows))

    def test_source_url_mismatch_and_original_instability_do_not_become_success(self):
        def mutate(raw):
            raw["descriptors"][0]["font_url_matches_source"] = False
        rows = self.variants(summarized("private_without_vorg", mutate=mutate))
        self.assertEqual(b1.classify(rows, True), "RETAINED_TABLES_BOUND_BUT_SOURCE_URL_NOT_EXACT")
        self.assertEqual(b1.classify(rows, False), "ORIGINAL_STARTUP_REPEAT_NOT_EXACT")


class StartupExecutionIsolationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source, self.binary, self.output = (self.root / name for name in ("original.ttc", "probe", "output"))
        self.original = small_collection()
        self.modified, _ = b1.remove_vorg_directories(self.original)
        self.source.write_bytes(self.original)
        self.binary.write_bytes(b"native probe test double; never executed")
        self.identities = {digest(self.original): source_identities(32),
                           digest(self.modified): source_identities(32, vorg=False)}
        self.calls = []

    def execute(self, mutate=None, signed_zero_literal=False, after_probe=None):
        def process(argv, **kwargs):
            label = b1.LABELS[len(self.calls)]
            candidate = Path(argv[1])
            data = candidate.read_bytes()
            raw = native_report(self.identities[digest(data)], digest(data), len(data))
            if mutate:
                replacement = mutate(label, raw)
                if replacement is not None:
                    raw = replacement
            if signed_zero_literal:
                for descriptor in raw["descriptors"]:
                    descriptor["font_matrix"]["tx"] = -0.0
                    descriptor["font_matrix_binary64_hex"]["tx"] = bits(-0.0)
            encoded = json.dumps(raw, separators=(",", ":")).encode()
            if signed_zero_literal:
                encoded = encoded.replace(b'"tx":-0.0', b'"tx":-0')
            stdout = b" \n" + encoded + b"\n\t"
            stderr = b"private diagnostic stderr sentinel"
            self.calls.append({"label": label, "path": candidate, "bytes": data, "kwargs": kwargs,
                               "stdout": stdout, "stderr": stderr, "argv": argv})
            if after_probe:
                after_probe(label, candidate)
            return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

        def expected(data):
            return copy.deepcopy(self.identities[digest(data)])

        with patch.object(b1, "EXPECTED_SOURCE", digest(self.original)), patch.object(b1, "expected_faces", side_effect=expected):
            return b1.execute(self.source, self.binary, self.output, run_process=process)

    def test_same_private_path_source_isolation_cleanup_and_byte_exact_stdout(self):
        report = self.execute()
        self.assertEqual(report["classification"], "PRIVATE_NO_VORG_BOUND_AND_VORG_API_NIL_STARTUP_ONLY")
        self.assertEqual(report["status"], "STARTUP_DIAGNOSTICS_COMPLETE_NOT_ACCEPTANCE")
        self.assertEqual(report["native_process_count"], 4)
        self.assertEqual([call["bytes"] for call in self.calls], [self.original, self.original, self.modified, self.original])
        self.assertEqual(self.calls[0]["path"], self.source)
        self.assertEqual(self.calls[3]["path"], self.source)
        self.assertEqual(self.calls[1]["path"], self.calls[2]["path"])
        self.assertNotEqual(self.calls[1]["path"], self.source)
        self.assertFalse(self.calls[1]["path"].parent.exists())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertTrue(report["private_temporary_files_removed"] and report["source_unchanged"] and report["original_repeat_exact"])
        for call, row in zip(self.calls, report["variants"]):
            self.assertEqual(call["argv"][0], str(self.binary))
            self.assertEqual(call["kwargs"], {"input": b"", "capture_output": True, "timeout": 180})
            self.assertEqual((self.output / row["raw_file"]).read_bytes(), call["stdout"])
            self.assertEqual(row["raw_file_sha256"], digest(call["stdout"]))
            self.assertEqual(row["native_stdout_sha256"], digest(call["stdout"]))
            self.assertEqual(row["native_stderr_sha256"], digest(call["stderr"]))
        for key in ("metric_record_count", "glyph_request_count", "original_faces_reconstructed"):
            self.assertEqual(report[key], 0)
        for key in ("original_font_accepted", "production_fix_established", "production_entrypoints_modified"):
            self.assertFalse(report[key])
        self.assertNotIn("private diagnostic stderr sentinel", (self.output / "summary.json").read_text())

    def test_native_json_negative_zero_is_preserved_before_bit_validation(self):
        report = self.execute(signed_zero_literal=True)
        self.assertTrue(report["original_repeat_exact"])
        self.assertEqual(report["status"], "STARTUP_DIAGNOSTICS_COMPLETE_NOT_ACCEPTANCE")
        for call, row in zip(self.calls, report["variants"]):
            self.assertIn(b'"tx":-0,', call["stdout"])
            self.assertEqual(row["validation"]["binary64_values_verified"], 32 * 7)
            self.assertEqual((self.output / row["raw_file"]).read_bytes(), call["stdout"])

    def test_private_original_descriptor_rejection_preserves_original_rerun_and_unknown_causality(self):
        def mutate(label, raw):
            if label == "private_identical":
                return native_report(self.identities[digest(self.original)], digest(self.original), len(self.original), api_status="NIL")
        report = self.execute(mutate=mutate)
        self.assertEqual(report["classification"], "PRIVATE_LOCATION_LOAD_OR_BINDING_BLOCKED_VORG_CAUSALITY_UNKNOWN")
        self.assertEqual(report["native_process_count"], 4)
        self.assertTrue(report["original_repeat_exact"])
        self.assertEqual(report["variants"][1]["bound_vorg_nil_count"], 0)
        self.assertEqual(report["metric_record_count"], 0)

    def test_truthful_but_different_original_repeat_cannot_complete_diagnostics(self):
        def mutate(label, raw):
            if label == "system_original_repeat":
                raw["descriptors"][0].update(font_size=13.0, font_size_binary64_hex=bits(13))
        report = self.execute(mutate=mutate)
        self.assertFalse(report["original_repeat_exact"])
        self.assertEqual(report["classification"], "ORIGINAL_STARTUP_REPEAT_NOT_EXACT")
        self.assertEqual(report["status"], "STARTUP_DIAGNOSTICS_INCOMPLETE_NOT_ACCEPTANCE")
        self.assertTrue(all(row["validation"]["validated"] for row in report["variants"]))
        self.assertFalse(report["original_font_accepted"])

    def test_private_source_mutation_is_detected_without_touching_original_or_skipping_repeat(self):
        def after_probe(label, candidate):
            if label == "private_identical":
                candidate.write_bytes(candidate.read_bytes() + b"unexpected bytes")
        report = self.execute(after_probe=after_probe)
        self.assertEqual(report["variants"][1]["reason"], "source_bytes_after_probe_mismatch")
        self.assertEqual(report["classification"], "INCOMPLETE_STARTUP_DIAGNOSTICS")
        self.assertEqual(report["native_process_count"], 4)
        self.assertTrue(report["original_repeat_exact"] and report["source_unchanged"] and report["private_temporary_files_removed"])
        self.assertFalse((self.output / "private_identical-raw.json").exists())
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_wrong_original_hash_or_missing_physical_faces_stops_before_processes(self):
        process = Mock()
        with patch.object(b1, "EXPECTED_SOURCE", "0" * 64):
            with self.assertRaisesRegex(b1.StartupEvidenceError, "original_source_hash_mismatch"):
                b1.execute(self.source, self.binary, self.output, run_process=process)
        process.assert_not_called()
        self.assertFalse(self.output.exists())
        with patch.object(b1, "EXPECTED_SOURCE", digest(self.original)):
            with self.assertRaisesRegex(b1.StartupEvidenceError, "all_32_physical_faces_required"):
                b1.execute(self.source, self.binary, self.output, run_process=process)
        process.assert_not_called()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
