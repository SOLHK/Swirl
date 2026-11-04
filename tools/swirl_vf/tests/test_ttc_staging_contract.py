"""C1 safe failures, production closure, and original shared-entry reproducers.

The two SharedEntryReproducerTests document present limitations of unchanged
rebuild.py.  Their passing result means the limitation was reproduced, NOT
that it was fixed or accepted.  All font bytes are original analytic fixtures
created in TemporaryDirectory.  No Apple font/native platform is involved.
"""
import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTCollection, newTable
from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.models import normalizeLocation, piecewiseLinearMap
from fontTools.varLib.varStore import OnlineVarStoreBuilder, VarStoreInstancer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "platform"))
import rebuild
import rebuild_c1_preflight as preflight
from ttc_staging_contract import CATEGORIES, StagingError, require, safe_context
from test_rebuild import AXES, write_fixture
from test_rebuild_pipeline import OriginalAnalyticOracle


class ErrorContractTests(unittest.TestCase):
    def test_all_six_categories_remain_distinct(self):
        self.assertEqual(CATEGORIES, {"input_axis", "metrics", "outline", "serialization",
                                      "platform_read", "font_tables"})
        for category in CATEGORIES:
            error = StagingError(category, "original_test_failure", face_index=2)
            self.assertEqual(error.category, category)
            self.assertEqual(error.to_dict(), {"category": category,
                "code": "original_test_failure", "context": {"face_index": 2}})

    def test_invalid_category_or_free_text_code_never_becomes_report(self):
        for category in ("other", None, [], 7):
            with self.subTest(category=category), self.assertRaises(ValueError):
                StagingError(category, "test")
        for code in ("/private/font.ttf", "ValueError: private", "A", "a\n", "x" * 97, None):
            with self.subTest(code=code), self.assertRaises(ValueError):
                StagingError("serialization", code)

    def test_private_payloads_paths_names_and_unknown_fields_are_removed(self):
        error = StagingError("outline", "test_failure", face_index=2, glyph_id=10,
                             source_path="PRIVATE_SOURCE", message="PRIVATE_ERROR",
                             glyph_name="PRIVATE_NAME", commands=[["moveTo", 12, 13]],
                             payload={"private": "PRIVATE_PAYLOAD"})
        self.assertEqual(error.context, {"face_index": 2, "glyph_id": 10})
        self.assertNotIn("PRIVATE", json.dumps(error.to_dict()))
        self.assertNotIn("PRIVATE", str(error))

    def test_nonfinite_bool_and_huge_numeric_context_is_removed(self):
        for value in (math.nan, math.inf, -math.inf, True, False, 2 ** 10000):
            with self.subTest(value=type(value).__name__):
                self.assertEqual(safe_context({"actual_count": value}), {})

    def test_valid_identifiers_tags_hashes_and_stages_survive(self):
        fields = {"face_index": 31, "gid_first": 47072, "gid_last": 47101,
                  "batch_start": 47072, "batch_stop": 47102,
                  "expected_count": 30, "actual_count": 30,
                  "limit_bytes": 4096, "observed_bytes": 2048, "attempt": 1,
                  "source_sha256": "a" * 64, "stage": "checkpoint", "table": "GPOS"}
        self.assertEqual(safe_context(fields), fields)

    def test_malformed_hash_tag_or_unrecognized_stage_removed(self):
        self.assertEqual(safe_context({"source_sha256": "A" * 64,
                         "table": "/tmp/secret", "axis": "\n\n\n\n",
                         "stage": "PRIVATE_STAGE"}), {})

    def test_to_dict_returns_independent_context(self):
        error = StagingError("metrics", "test", face_index=1)
        error.to_dict()["context"]["face_index"] = 8
        self.assertEqual(error.context["face_index"], 1)
        self.assertEqual(error.as_dict(), error.to_dict())

    def test_require_produces_typed_failure_only_on_false(self):
        self.assertIsNone(require(True, "metrics", "test"))
        with self.assertRaises(StagingError) as caught:
            require(False, "input_axis", "test", face_index=2)
        self.assertEqual(caught.exception.category, "input_axis")


class PreflightTests(unittest.TestCase):
    def assert_blocked(self, report):
        self.assertEqual(report["status"], "BLOCKED")
        for field in ("production_rebuild_permitted", "production_acceptance", "font_generated"):
            self.assertIs(report[field], False)
        self.assertEqual(report["reconstructed_faces"], 0)
        self.assertEqual(report["windows_acceptance"], "NOT_RUN")
        self.assertEqual(report["required_interfaces"], {"A3": "NOT_INTEGRATED", "B1": "NOT_INTEGRATED"})
        self.assertIn("a3_production_input_unavailable", [e["code"] for e in report["failures"]])
        self.assertIn("b1_production_metrics_unavailable", [e["code"] for e in report["failures"]])

    def test_no_source_is_blocked_without_side_effects(self):
        report = preflight.production_preflight()
        self.assert_blocked(report)
        self.assertFalse(report["source_identity_verified"])

    def test_original_source_identity_is_fixed_in_code(self):
        self.assertEqual(preflight.SOURCE_SHA256,
            "39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890")
        self.assertEqual((preflight.SOURCE_BYTES, preflight.SOURCE_FACES, preflight.SOURCE_GLYPHS),
                         (61_473_880, 32, 47_102))
        self.assertEqual(preflight.SOURCE_AXES, ("WDTH", "wght", "HGHT"))

    def test_different_original_fixture_is_not_accepted_as_apple_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "PRIVATE_NAME.ttc"
            write_fixture(source)
            before = source.read_bytes()
            with mock.patch.object(preflight, "_inventory") as inventory:
                report = preflight.production_preflight(source)
            self.assert_blocked(report)
            self.assertFalse(report["source_identity_verified"])
            inventory.assert_not_called()
            self.assertEqual(source.read_bytes(), before)
            self.assertNotIn("PRIVATE_NAME", json.dumps(report))

    def test_exact_identity_and_structure_still_cannot_grant_production(self):
        inventory = [{"face_index": i, "glyph_count": 47_102} for i in range(32)]
        with mock.patch.object(preflight, "_identity", return_value=(preflight.SOURCE_SHA256, preflight.SOURCE_BYTES)), \
             mock.patch.object(preflight, "_inventory", return_value=inventory):
            report = preflight.production_preflight("private-test-double")
        self.assert_blocked(report)
        self.assertTrue(report["source_identity_verified"])
        self.assertTrue(report["source_structure_verified"])
        self.assertEqual(report["physical_faces_checked"], 32)
        self.assertTrue(report["source_unchanged"])

    def test_source_changed_after_inventory_cannot_pass_preparation(self):
        values = [(preflight.SOURCE_SHA256, preflight.SOURCE_BYTES), ("0" * 64, preflight.SOURCE_BYTES)]
        with mock.patch.object(preflight, "_identity", side_effect=values), \
             mock.patch.object(preflight, "_inventory", return_value=[]):
            report = preflight.production_preflight("private-test-double")
        self.assert_blocked(report)
        self.assertFalse(report["source_structure_verified"])
        self.assertIn("source_changed", [e["code"] for e in report["failures"]])

    def test_parser_exception_text_never_leaks(self):
        with mock.patch.object(preflight, "_identity", side_effect=OSError("PRIVATE_PATH PRIVATE_NAME")):
            report = preflight.production_preflight("private-test-double")
        self.assert_blocked(report)
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_inventory_rejects_unbounded_or_wrong_face_count_before_fonttools(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "count.ttc"
            path.write_bytes(b"ttcf\0\1\0\0\xff\xff\xff\xff")
            with mock.patch.object(preflight, "TTCollection") as collection:
                with self.assertRaises(StagingError):
                    preflight._inventory(path)
            collection.assert_not_called()

    def test_no_forged_accepted_interface_argument_exists(self):
        with self.assertRaises(TypeError):
            preflight.production_preflight(accepted_interfaces={"A3": True, "B1": True})

    def test_cli_emits_blocked_json_and_failure_exit_status(self):
        completed = subprocess.run([sys.executable, str(ROOT / "platform" / "rebuild_c1_preflight.py")],
                                   capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 2)
        self.assert_blocked(json.loads(completed.stdout))
        self.assertEqual(completed.stderr, "")


class SharedEntryReproducerTests(unittest.TestCase):
    def test_reproducer_shared_checkpoint_stale_writer_drops_prior_index(self):
        """The old mutable manifest has no writer lease or CAS; C1 must not reuse it."""
        with tempfile.TemporaryDirectory(prefix="c1-original-writers-") as tmp:
            root = Path(tmp)
            source = root / "original-checkpoint-fixture.ttc"
            write_fixture(source, faces=2)
            executable = root / "synthetic-oracle-identity"
            executable.write_bytes(b"original analytic test double only")
            with TTCollection(source) as collection:
                identities = rebuild.checkpoint_source_faces(collection.fonts)
                face_paths = []
                for index, font in enumerate(collection.fonts):
                    path = root / f"original-face-{index}.ttf"
                    font.save(path)
                    face_paths.append(path)
            args = (root / "old-checkpoint", source, executable, (), {}, identities)
            first = rebuild.FaceCheckpoints(*args)
            second = rebuild.FaceCheckpoints(*args)  # Both writers observed the empty manifest.
            for index, writer in enumerate((first, second)):
                recipe = writer.state["recipe"]
                summary = {"type": "summary", "source_sha256": recipe["source_sha256"],
                           "error_count": 0, "request_count": 1,
                           "successful_glyph_count": 3, "synthetic_test_double_only": True}
                transcript = {"status": "PASS", "session_index": index + 1,
                    "face_index": index, "source_sha256": recipe["source_sha256"],
                    "source_identity_sha256": recipe["source_identity_sha256"],
                    "source_face_identity_sha256": recipe["source_face_identity_sha256"][index],
                    "oracle_sha256": recipe["oracle_sha256"], "source_unchanged": True,
                    "native_metadata_verified_against_all_source_tables": True,
                    "native_summary_eof_exit_accepted": True,
                    "request_count": 1, "successful_glyph_count": 3, "summary": summary}
                report = {"face_index": index, "glyph_count": 3, "glyphs_completed": 3,
                          "serialized_model_verification": {"status": "PASS", "glyphs_checked": 3},
                          "native_face_transcript": transcript}
                writer.save(index, face_paths[index], report)
                state = json.loads(writer.manifest.read_text(encoding="utf-8"))
                # This captures today's defect; no attempt is made to accept
                # the loss or repair the shared entry without owner approval.
                self.assertEqual(set(state["faces"]), {str(index)})
            self.assertEqual(len(list(first.directory.glob("face-*.ttf"))), 2)
            self.assertNotIn("0", json.loads(first.manifest.read_text())["faces"])

    def test_reproducer_unremapped_gdef_changes_layout_after_shared_rebuild(self):
        """Known open defect: a PASS here means the current omission is reproduced."""
        with tempfile.TemporaryDirectory(prefix="c1-original-gdef-") as tmp:
            root = Path(tmp)
            source = root / "original-gdef-fixture.ttc"
            write_fixture(source)
            with TTCollection(source) as collection:
                font = collection.fonts[0]
                font["avar"] = newTable("avar")
                font["avar"].majorVersion, font["avar"].minorVersion = 1, 0
                font["avar"].segments = {tag: {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0} for tag in AXES}
                font["avar"].segments["wght"][0.5] = 0.25
                addOpenTypeFeaturesFromString(font,
                    "languagesystem DFLT dflt; feature kern { pos A <0 0 -20 0>; } kern;")
                builder = OnlineVarStoreBuilder(list(AXES))
                builder.setSupports([{"wght": (0, 1, 1)}])
                index = builder.storeDeltas([100])
                gdef = newTable("GDEF")
                gdef.table = otTables.GDEF()
                gdef.table.Version = 0x00010003
                for field in ("GlyphClassDef", "AttachList", "LigCaretList",
                              "MarkAttachClassDef", "MarkGlyphSetsDef"):
                    setattr(gdef.table, field, None)
                gdef.table.VarStore = builder.finish()
                font["GDEF"] = gdef
                subtable = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
                subtable.Value.XAdvDevice = buildVarDevTable(index)
                subtable.ValueFormat |= 0x40
                collection.save(source)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            output = root / "Swirl-VF.ttc"
            with mock.patch.object(rebuild, "NativeOracle", return_value=OriginalAnalyticOracle(source)), \
                 contextlib.redirect_stderr(io.StringIO()):
                result = rebuild.run(source, root / "synthetic-oracle", output,
                                     root / "report.json", batch_size=2)
            self.assertEqual(result["status"], "RECONSTRUCTION_SAMPLED_PASS_PLATFORM_UNVERIFIED")
            deltas = []
            for path in (source, output):
                with TTCollection(path) as collection:
                    font = collection.fonts[0]
                    location = normalizeLocation({"WDTH": 500, "wght": 700, "HGHT": 500}, AXES)
                    normalized = {tag: piecewiseLinearMap(v, font["avar"].segments[tag])
                                  for tag, v in location.items()}
                    device = font["GPOS"].table.LookupList.Lookup[0].SubTable[0].Value.XAdvDevice
                    index = (device.StartSize << 16) | device.EndSize
                    deltas.append(VarStoreInstancer(font["GDEF"].table.VarStore,
                                  font["fvar"].axes, normalized)[index])
            self.assertEqual(deltas, [25.0, 50.0])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)


if __name__ == "__main__":
    unittest.main()
