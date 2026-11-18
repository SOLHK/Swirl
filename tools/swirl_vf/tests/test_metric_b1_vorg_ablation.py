"""Raw TTC and private-protocol boundaries; no Apple data or native-run claim."""
import contextlib
import copy
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import b1_original_vorg_ablation as b1


def raw_collection(face_count=32, version=0x10000, extra_table=False):
    """Original test bytes, including intentionally noncanonical avar order."""
    avar = struct.pack(">5H", 1, 0, 0, 1, 4) + b"".join(
        struct.pack(">hh", a, b) for a, b in ((0, 100), (-16384, -16384), (0, 0), (16384, 16384)))
    tables = {b"VORG": struct.pack(">HHhH", 1, 0, 911, 0), b"avar": avar,
              b"head": bytes(range(54)), b"hmtx": struct.pack(">Hh", 1000, 70)}
    if extra_table:
        tables[b"zzzz"] = b"separate payload"
    number = len(tables)
    header_end = 12 + face_count * 4 + (12 if version == 0x20000 else 0)
    directory_length = 12 + number * 16
    offsets = [header_end + index * directory_length for index in range(face_count)]
    result = bytearray(offsets[-1] + directory_length)
    struct.pack_into(">4sII", result, 0, b"ttcf", version, face_count)
    struct.pack_into(">" + "I" * face_count, result, 12, *offsets)
    records = []
    for tag, payload in tables.items():
        result.extend(bytes((-len(result)) % 4))
        position = len(result)
        result.extend(payload)
        # The checksum is deliberately distinctive; ablation must copy it,
        # regardless of whether a future loader chooses to enforce it.
        records.append(struct.pack(">4sIII", tag, 0x12345678 + len(records), position, len(payload)))
    for position in offsets:
        struct.pack_into(">4s4H", result, position, b"\0\1\0\0", number, 64, 2, number * 16 - 64)
        result[position + 12:position + directory_length] = b"".join(records)
    return bytes(result)


def metrics(x=500, width=800, height=850):
    return {"advance_width": float(width), "advance_height": float(height), "lsb": 70.0,
            "horizontal_origin_x": 0.0, "horizontal_origin_y": 0.0,
            "vertical_origin_x": float(x), "vertical_origin_y": 911.0,
            "horizontal_advance_sum": float(width), "vertical_advance_sum": float(height),
            "horizontal_advance_vector": [float(width), 0.0],
            "vertical_advance_vector": [float(height), 0.0],
            "vertical_origin_translation": [-float(x), -911.0]}


def variants():
    result = []
    for label, x in zip(b1.VARIANTS, (500, 400, 500)):
        result.append({"variant": label, "status": "TEST_DOUBLE", "diagnostics_complete": True,
                       "source_sha256": ("b" if label == "private_without_vorg" else "a") * 64,
                       "observations": [{"face_index": 15, "case": "WDTH_min", "glyph_id": 5,
                            "user_location": {"WDTH": 1, "wght": 501, "HGHT": 500},
                            "native_metrics": metrics(x)}]})
    return result


def stored_reference():
    return {"units": "serialized_font_design_units", "hmtx": {"advance_width": 1000, "lsb": 70},
            "vmtx": {"advance_height": 1000, "top_side_bearing": 200},
            "VORG": {"present": True, "default_y": 911, "glyph_y": 911, "explicit_glyph_override": False}}


def complete_variants():
    result = variants()
    for variant in result:
        variant["observations"] = []
        for face in b1.FACES:
            for case, width in (("default", 1000), ("WDTH_min", 800), ("WDTH_max", 1200),
                                ("HGHT_min", 1000), ("HGHT_max", 1000)):
                for gid in b1.GLYPHS:
                    x = width / 2 if variant["variant"] == "private_without_vorg" else 500
                    variant["observations"].append({"face_index": face, "glyph_id": gid, "case": case,
                        "user_location": {"WDTH": width, "wght": 501, "HGHT": 500}, "native_metrics": metrics(x, width)})
    return result


class RawVorgDirectoryTests(unittest.TestCase):
    def test_all_32_shared_table_faces_keep_original_payloads_and_raw_avar_order(self):
        original = raw_collection()
        snapshot = bytes(original)
        modified, evidence = b1.remove_vorg_directories(original)
        self.assertEqual(original, snapshot)
        self.assertEqual(len(modified), len(original))
        self.assertNotEqual(modified, original)
        self.assertEqual(evidence["physical_faces"], 32)
        self.assertEqual(evidence["retained_table_byte_comparisons"], 32 * 3)
        self.assertTrue(evidence["all_non_directory_bytes_identical"])
        self.assertTrue(evidence["raw_avar_bytes_and_record_order_preserved"])
        self.assertFalse(evidence["fonttools_reserialization_used"])
        before = b1.read_directories(original)
        after = b1.read_directories(modified)
        for old, new in zip(before["faces"], after["faces"]):
            self.assertEqual(new["num_tables"], 3)
            self.assertEqual(new["search_fields"], [32, 1, 16])
            self.assertEqual([r["tag"] for r in new["records"]], [b"avar", b"head", b"hmtx"])
            self.assertEqual(modified[new["end"]:old["end"]], bytes(16))
            for table in old["records"]:
                begin, length = table["offset"], table["length"]
                self.assertEqual(modified[begin:begin + length], original[begin:begin + length])
        self.assertEqual(len({r["offset"] for f in after["faces"] for r in f["records"] if r["tag"] == b"avar"}), 1)

    def test_power_of_two_search_fields_and_v2_header_are_preserved(self):
        original = raw_collection(2, version=0x20000, extra_table=True)
        modified, _ = b1.remove_vorg_directories(original)
        parsed = b1.read_directories(modified)
        self.assertEqual(original[:32], modified[:32])
        self.assertEqual(parsed["faces"][0]["num_tables"], 4)
        self.assertEqual(parsed["faces"][0]["search_fields"], [64, 2, 0])

    def test_verifier_rejects_retained_payload_changes_including_head_adjustment(self):
        original = raw_collection(2)
        modified, _ = b1.remove_vorg_directories(original)
        for tag, adjustment in ((b"avar", 10), (b"head", 8), (b"hmtx", 0)):
            table = next(r for r in b1.read_directories(original)["faces"][0]["records"] if r["tag"] == tag)
            corrupted = bytearray(modified)
            corrupted[table["offset"] + adjustment] ^= 1
            with self.subTest(table=tag), self.assertRaisesRegex(b1.AblationError, "retained_table_payload_changed"):
                b1.verify_removed_vorg(original, bytes(corrupted))

    def test_unreachable_vorg_bytes_cannot_be_rewritten_or_discarded(self):
        original = raw_collection(2)
        modified, _ = b1.remove_vorg_directories(original)
        table = b1.read_directories(original)["faces"][0]["records"][0]
        corrupted = bytearray(modified)
        corrupted[table["offset"] + 4] ^= 1
        with self.assertRaisesRegex(b1.AblationError, "bytes_outside_directory_changed"):
            b1.verify_removed_vorg(original, bytes(corrupted))

    def test_retained_checksum_offset_and_search_metadata_are_verified(self):
        original = raw_collection(2)
        modified, _ = b1.remove_vorg_directories(original)
        first = b1.read_directories(modified)["faces"][0]
        for relative, reason in ((6, "incorrect_search_fields"), (16, "retained_directory_record_changed")):
            corrupted = bytearray(modified)
            corrupted[first["offset"] + relative] ^= 1
            with self.subTest(offset=relative), self.assertRaisesRegex(b1.AblationError, reason):
                b1.verify_removed_vorg(original, bytes(corrupted))

    def test_duplicate_tables_face_offsets_and_header_overlap_are_rejected(self):
        original = raw_collection(2)
        first = b1.read_directories(original)["faces"][0]
        duplicate_tag = bytearray(original)
        duplicate_tag[first["offset"] + 28:first["offset"] + 32] = b"VORG"
        duplicate_face = bytearray(original)
        duplicate_face[16:20] = duplicate_face[12:16]
        overlapping_payload = bytearray(original)
        struct.pack_into(">I", overlapping_payload, first["offset"] + 20, first["offset"])
        for data, reason in ((duplicate_tag, "duplicate_table_tag"),
                             (duplicate_face, "duplicate_physical_directory_offset"),
                             (overlapping_payload, "table_payload_overlaps_directory")):
            with self.subTest(reason=reason), self.assertRaisesRegex(b1.AblationError, reason):
                b1.remove_vorg_directories(bytes(data))

    def test_out_of_bounds_input_and_repeat_ablation_fail_closed(self):
        original = raw_collection(2)
        for data in (original[:8], original[:19], original[:-1]):
            with self.subTest(length=len(data)), self.assertRaises(b1.AblationError):
                b1.remove_vorg_directories(data)
        modified, _ = b1.remove_vorg_directories(original)
        with self.assertRaisesRegex(b1.AblationError, "each_original_face_requires_one_vorg"):
            b1.remove_vorg_directories(modified)


class VorgEvidenceTests(unittest.TestCase):
    def test_complete_stable_diagnostic_does_not_clear_24_original_representation_failures(self):
        values = complete_variants()
        references = {(face, gid): stored_reference() for face in b1.FACES for gid in b1.GLYPHS}
        self.assertTrue(b1.compare_variants(values)["original_repeat_binary64_exact"])
        gate = b1.check_original_representations(values, references)
        self.assertTrue(gate["strict_original_representation_complete"])
        self.assertFalse(gate["strict_original_representation_pass"])
        self.assertEqual(gate["strict_original_representation_failed_count"], 48)
        self.assertEqual(gate["strict_original_representation_checked_count"], 120)
        self.assertEqual([item["failed_count"] for item in gate["sessions"]], [24, 24])
        self.assertEqual(gate["additional_native_requests"], 0)
        self.assertNotIn("strict_original_representation_pass", values[1])
        rejected = [row for row in values[0]["observations"] if not row["production_representation"]["passed"]]
        self.assertTrue(all(row["production_representation"]["absolute_error_font_units"] == 100 for row in rejected))
        self.assertTrue(all(row["production_representation"]["tolerance_font_units"] == 1e-5 for row in rejected))

    def test_zero_observed_failures_on_incomplete_original_is_not_strict_pass(self):
        values = variants()
        for variant in values:
            variant["observations"][0]["native_metrics"] = metrics(400)
        gate = b1.check_original_representations(values, {(15, 5): stored_reference()})
        self.assertEqual(gate["strict_original_representation_failed_count"], 0)
        self.assertFalse(gate["strict_original_representation_complete"])
        self.assertFalse(gate["strict_original_representation_pass"])

    def test_only_measured_100_unit_x_change_is_reported_and_849_remains_849(self):
        values = variants()
        for variant in values:
            variant["observations"][0]["native_metrics"].update(advance_height=849, vertical_advance_sum=849,
                                                              vertical_advance_vector=[849, 0])
        result = b1.compare_variants(values)
        self.assertTrue(result["original_repeat_numeric_exact"])
        self.assertTrue(result["original_repeat_binary64_exact"])
        delta = result["differences"][0]
        self.assertEqual(delta["without_vorg_minus_original_font_units"]["vertical_origin_x"], -100)
        self.assertEqual(delta["without_vorg_minus_original_font_units"]["advance_height"], 0)
        self.assertEqual(delta["original_x_minus_current_half_width"], 100)
        self.assertEqual(delta["without_vorg_x_minus_current_half_width"], 0)
        self.assertEqual(values[1]["observations"][0]["native_metrics"]["advance_height"], 849)
        self.assertIn("NOT_PRODUCTION_FIX", result["status"])

    def test_rejected_ablation_has_no_differences_but_original_repeat_is_audited(self):
        values = variants()
        values[1].update(diagnostics_complete=False, observations=[], status="NATIVE_REJECTED")
        result = b1.compare_variants(values)
        self.assertIn("INCOMPLETE", result["status"])
        self.assertNotIn("differences", result)
        self.assertTrue(result["original_repeat_numeric_exact"])
        self.assertTrue(result["original_repeat_binary64_exact"])
        self.assertFalse(result["measured_differences_invented"])

    def test_repeat_instability_and_signed_zero_are_distinguished(self):
        values = variants()
        values[2]["observations"][0]["native_metrics"]["horizontal_origin_y"] = -0.0
        result = b1.compare_variants(values)
        self.assertTrue(result["original_repeat_numeric_exact"])
        self.assertFalse(result["original_repeat_binary64_exact"])
        values[2]["observations"][0]["native_metrics"]["advance_height"] = 849
        self.assertFalse(b1.compare_variants(values)["original_repeat_numeric_exact"])

    def test_duplicate_missing_sample_and_nonidentical_locations_are_rejected(self):
        for change, reason in (("duplicate", "duplicate_observation_identity"),
                               ("missing", "variant_sample_identity_mismatch"),
                               ("location", "variant_location_mismatch")):
            values = variants()
            if change == "duplicate":
                values[1]["observations"].append(copy.deepcopy(values[1]["observations"][0]))
            elif change == "missing":
                values[1]["observations"] = []
            else:
                values[1]["observations"][0]["user_location"]["WDTH"] = 2
            with self.subTest(change=change), self.assertRaisesRegex(b1.AblationError, reason):
                b1.compare_variants(values)

    def test_wrong_original_or_unchanged_ablation_source_cannot_be_compared(self):
        values = variants()
        values[2]["source_sha256"] = "c" * 64
        with self.assertRaisesRegex(b1.AblationError, "original_repeat_source_mismatch"):
            b1.compare_variants(values)
        values = variants()
        values[1]["source_sha256"] = values[0]["source_sha256"]
        with self.assertRaisesRegex(b1.AblationError, "ablation_source_not_changed"):
            b1.compare_variants(values)

    def test_public_log_excludes_original_and_variant_metric_records(self):
        values = variants()
        row = values[0]["observations"][0]
        row.update(commands=["PRIVATE_OUTLINE"], bounds=[0, 1, 2, 3], native_binary64_bits={"x": "PRIVATE_BITS"})
        row["native_metrics"]["commands"] = ["PRIVATE_NESTED_OUTLINE"]
        report = {"status": "TEST_DOUBLE", "variants": values, "original_font_accepted": False,
                  "production_fix_established": False, "original_faces_reconstructed": 0,
                  "source_path": "/PRIVATE_PATH", "native_metadata": {"PRIVATE": "PRIVATE"}}
        result = b1.public_log_summary(report)
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("variants", result)
        self.assertNotIn("observations", result)
        self.assertEqual(result["public_output_scope"], "aggregate_only")
        self.assertFalse(result["production_fix_established"])

    def test_arbitrary_error_payload_is_never_public(self):
        self.assertEqual(b1.safe_reason(RuntimeError("PRIVATE_PATH PRIVATE_OUTLINE PRIVATE_CREDENTIAL")),
                         "NATIVE_OR_SOURCE_REJECTION_DETAILS_NOT_PUBLISHED")


class PrivateNativeSessionTests(unittest.TestCase):
    def test_whole_protocol_is_required_and_cleanup_rejection_is_contained(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.ttc"
            source.write_bytes(b"ORIGINAL_TEST_BYTES_NOT_A_FONT")
            binary = directory / "binary"
            binary.write_bytes(b"TEST_DOUBLE_NOT_EXECUTED")
            launcher = directory / "launcher"
            launcher.write_bytes(b"TEST_DOUBLE_LAUNCHER_NOT_EXECUTED")
            source_hash = b1.rebuild.sha256(source)
            identities = [{"face_index": i, "upm": 1000, "glyph_count": 47102,
                           "verified_table_sha256": {"head": "a" * 64}} for i in range(32)]
            metadata = {"source_sha256": source_hash, "source_byte_size": source.stat().st_size,
                        "faces": identities, "axis_verification_backend": b1.BACKEND}
            oracle = Mock(metadata=metadata)
            oracle.samples.return_value = {gid: metrics() | {"commands": ["PRIVATE_OUTLINE"], "bounds": [1, 2, 3, 4]}
                                           for gid in b1.GLYPHS}
            summary = {"type": "summary", "source_sha256": source_hash, "request_count": 1,
                       "successful_glyph_count": 4, "error_count": 0, "verified_batch_count": 1,
                       "source_unchanged": True, "axis_verification_backend": b1.BACKEND,
                       "internal_native_request_count": 2, "internal_native_glyph_count": 8}
            oracle.finish.return_value = summary
            collection = Mock()
            collection.__enter__ = Mock(return_value=SimpleNamespace(fonts=[object()] * 32))
            collection.__exit__ = Mock(return_value=False)
            with patch.object(b1, "TTCollection", return_value=collection), \
                 patch.object(b1.rebuild, "checkpoint_source_faces", return_value=identities), \
                 patch.object(b1, "make_launcher", return_value=launcher), \
                 patch.object(b1.rebuild, "NativeOracle", return_value=oracle):
                plan = [(0, "default", {"WDTH": 501, "wght": 501, "HGHT": 500})]
                result = b1.measure_variant(source, binary, directory, b1.VARIANTS[0], plan)
                self.assertTrue(result["diagnostics_complete"])
                self.assertEqual(result["physical_faces_verified"], 32)
                self.assertTrue(result["native_finalization"]["actual_eof_verified"])
                self.assertNotIn("PRIVATE", json.dumps(result))
                oracle.finish.side_effect = b1.rebuild.ReconstructionError("native oracle failed after its final glyph")
                result = b1.measure_variant(source, binary, directory, b1.VARIANTS[0], plan)
                self.assertFalse(result["diagnostics_complete"])
                self.assertEqual(result["observed_record_count"], 4)
                oracle.finish.side_effect = None
                oracle.close.side_effect = OSError("PRIVATE_PATH")
                result = b1.measure_variant(source, binary, directory, b1.VARIANTS[0], plan)
                self.assertFalse(result["diagnostics_complete"])
                self.assertEqual(result["status"], "NATIVE_VARIANT_CLEANUP_FAILED")
                self.assertNotIn("PRIVATE_PATH", json.dumps(result))

    def test_rejected_variant_does_not_skip_original_repeat_and_private_font_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, binary, output = (directory / name for name in ("original.ttc", "binary", "report.json"))
            original = raw_collection()
            source.write_bytes(original)
            binary.write_bytes(b"TEST_DOUBLE_NOT_EXECUTED")
            binary.chmod(0o700)
            source_hash = b1.digest(original)
            seen = []
            def measure(path, executable, private, label, plan):
                seen.append((path, label, len(plan)))
                result = variants()[b1.VARIANTS.index(label)]
                result["source_sha256"] = b1.rebuild.sha256(path)
                if label == "private_without_vorg":
                    self.assertNotEqual(path, source)
                    self.assertTrue(path.exists())
                    result.update(diagnostics_complete=False, observations=[])
                return result
            collection = Mock()
            collection.__enter__ = Mock(return_value=SimpleNamespace(fonts=[object()] * 32))
            collection.__exit__ = Mock(return_value=False)
            plan = [(name, {"WDTH": 501, "wght": 501, "HGHT": 500}, {})
                    for name in ("default", "WDTH_min", "WDTH_max", "HGHT_min", "HGHT_max")]
            stdout = io.StringIO()
            with patch.object(b1, "EXPECTED_SOURCE", source_hash), patch.object(b1.sys, "platform", "darwin"), \
                 patch.object(b1, "TTCollection", return_value=collection), patch.object(b1, "fixed_cases", return_value=plan), \
                 patch.object(b1, "stored_metrics", return_value=stored_reference()), \
                 patch.object(b1, "measure_variant", side_effect=measure), contextlib.redirect_stdout(stdout):
                code = b1.run(source, binary, output)
            self.assertEqual(code, 1)
            self.assertEqual([label for _, label, _ in seen], list(b1.VARIANTS))
            self.assertTrue(all(size == 15 for _, _, size in seen))
            self.assertEqual(seen[0][0], seen[2][0])
            self.assertFalse(seen[1][0].exists())
            self.assertEqual(source.read_bytes(), original)
            report = json.loads(output.read_text())
            self.assertTrue(report["experiment_complete"])
            self.assertTrue(report["source_unchanged"])
            self.assertFalse(report["original_font_accepted"])
            self.assertFalse(report["production_fix_established"])
            self.assertEqual(report["original_faces_reconstructed"], 0)
            line = stdout.getvalue().strip()
            self.assertTrue(line.startswith("B1_VORG_ABLATION_SUMMARY_JSON="))
            compact = json.loads(line.split("=", 1)[1])
            self.assertEqual(compact, report)
            self.assertNotIn("variants", report)
            self.assertNotIn("directory_patch_verification", report)
            self.assertTrue(compact["comparison"]["original_repeat_binary64_exact"])
            self.assertNotIn("differences", compact["comparison"])
            self.assertNotIn(str(directory), json.dumps(compact))

    def test_cli_stable_complete_ablations_remain_red_for_original_production_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source, binary, output = (directory / name for name in ("original.ttc", "binary", "report.json"))
            source.write_bytes(raw_collection())
            binary.write_bytes(b"TEST_DOUBLE_NOT_EXECUTED")
            binary.chmod(0o700)
            source_hash = b1.rebuild.sha256(source)
            def measure(path, executable, private, label, plan):
                result = complete_variants()[b1.VARIANTS.index(label)]
                result["source_sha256"] = b1.rebuild.sha256(path)
                return result
            collection = Mock()
            collection.__enter__ = Mock(return_value=SimpleNamespace(fonts=[object()] * 32))
            collection.__exit__ = Mock(return_value=False)
            plan = [(name, {"WDTH": 501, "wght": 501, "HGHT": 500}, {})
                    for name in ("default", "WDTH_min", "WDTH_max", "HGHT_min", "HGHT_max")]
            with patch.object(b1, "EXPECTED_SOURCE", source_hash), patch.object(b1.sys, "platform", "darwin"), \
                 patch.object(b1, "TTCollection", return_value=collection), patch.object(b1, "fixed_cases", return_value=plan), \
                 patch.object(b1, "stored_metrics", return_value=stored_reference()), \
                 patch.object(b1, "measure_variant", side_effect=measure), contextlib.redirect_stdout(io.StringIO()):
                code = b1.run(source, binary, output)
            report = json.loads(output.read_text())
            self.assertEqual(code, 1)
            self.assertTrue(report["diagnostics_complete_and_original_repeat_stable"])
            self.assertEqual(report["status"], "DIAGNOSTICS_COMPLETE_ORIGINAL_PRODUCTION_REPRESENTATION_FAILED")
            self.assertEqual(report["strict_original_representation_failed_count"], 48)
            self.assertFalse(report["strict_original_representation_pass"])
            self.assertFalse(report["original_font_accepted"])
            self.assertFalse(report["production_fix_established"])


if __name__ == "__main__":
    unittest.main()

