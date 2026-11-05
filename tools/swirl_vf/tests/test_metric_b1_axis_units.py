"""HGHT-unit metamorphic controls; storage equivalence is not native evidence."""
from copy import deepcopy
from fractions import Fraction
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.sfnt import calcChecksum
from fontTools.varLib.varStore import VarStoreInstancer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from b1_metric_followup import freeze_origin_predictions
from b1_metric_followup_fixture import build_suite
from b1_metric_axis_units import (
    CHECKSUM_MAGIC, patch_height_axis, reparameterize_height_axis, wire_requests,
)


class B1MetricAxisUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.path = Path(cls.directory.name)
        cls.original = freeze_origin_predictions(build_suite(cls.path))
        cls.original_snapshot = deepcopy(cls.original)
        cls.font_bytes = {entry["path"]: (cls.path / entry["path"]).read_bytes() for entry in cls.original["entries"]}
        cls.manifest_bytes = (cls.path / "manifest.json").read_bytes()
        cls.control = reparameterize_height_axis(cls.original, cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_supplied_frozen_manifest_and_all_original_files_are_unchanged(self):
        self.assertEqual(self.original, self.original_snapshot)
        self.assertEqual((self.path / "manifest.json").read_bytes(), self.manifest_bytes)
        for path, original in self.font_bytes.items():
            self.assertEqual((self.path / path).read_bytes(), original)
        self.assertIsNot(self.control, self.original)

    def test_all_550_requests_keep_ids_order_normalized_design_and_predictions(self):
        self.assertEqual(len(self.control["entries"]), 16)
        self.assertEqual(sum(len(e["requests"]) for e in self.control["entries"]), 550)
        for before, after in zip(self.original["entries"], self.control["entries"]):
            self.assertEqual(before["fixture_id"], after["fixture_id"])
            self.assertEqual(before["predictions_round_delta"], after["predictions_round_delta"])
            self.assertEqual(before["predictions_origin_y"], after["predictions_origin_y"])
            self.assertEqual(before["origin_x_storage_hypotheses"], after["origin_x_storage_hypotheses"])
            self.assertEqual([r["id"] for r in before["requests"]], [r["id"] for r in after["requests"]])
            for old, new in zip(before["requests"], after["requests"]):
                self.assertEqual({k: new[k] for k in old}, old)
                self.assertEqual(new["normalized_design_axes"], old["axes"])

    def test_fvar_changes_only_hght_min_default_max(self):
        for before, after in zip(self.original["entries"], self.control["entries"]):
            with TTFont(self.path / before["path"]) as original, TTFont(self.path / after["path"]) as converted:
                self.assertEqual(original["fvar"].instances, converted["fvar"].instances)
                for old, new in zip(original["fvar"].axes, converted["fvar"].axes):
                    self.assertEqual(old.axisTag, new.axisTag)
                    self.assertEqual(old.flags, new.flags)
                    self.assertEqual(old.axisNameID, new.axisNameID)
                    scale = 16384 if old.axisTag == "HGHT" else 1
                    self.assertEqual((new.minValue, new.defaultValue, new.maxValue),
                                     (old.minValue*scale, old.defaultValue*scale, old.maxValue*scale))
                hght = next(axis for axis in converted["fvar"].axes if axis.axisTag == "HGHT")
                self.assertEqual((hght.minValue, hght.defaultValue, hght.maxValue), (-16384, 0, 16384))

    def test_every_other_table_payload_is_byte_identical(self):
        for before, after in zip(self.original["entries"], self.control["entries"]):
            with TTFont(self.path / before["path"], lazy=True) as a, TTFont(self.path / after["path"], lazy=True) as b:
                self.assertEqual(set(a.reader.keys()), set(b.reader.keys()))
                for tag in a.reader.keys():
                    left, right = a.reader[tag], b.reader[tag]
                    if tag == "fvar":
                        self.assertNotEqual(left, right)
                        continue
                    if tag == "head":
                        left, right = left[:8]+bytes(4)+left[12:], right[:8]+bytes(4)+right[12:]
                    self.assertEqual(left, right, (after["fixture_id"], tag))

    def test_sfnt_and_directory_checksums_are_valid_after_raw_patch(self):
        for entry in self.control["entries"]:
            data = (self.path / entry["path"]).read_bytes()
            self.assertEqual(calcChecksum(data), CHECKSUM_MAGIC)
            with TTFont(self.path / entry["path"], lazy=True) as font:
                for tag in font.reader.keys():
                    payload = font.reader[tag]
                    if tag == "head": payload = payload[:8]+bytes(4)+payload[12:]
                    self.assertEqual(calcChecksum(payload), font.reader.tables[tag].checkSum)

    def test_native_user_axes_map_exactly_back_using_the_saved_basis(self):
        for entry in self.control["entries"]:
            for request in entry["requests"]:
                basis = request["native_scale_basis"]["HGHT"]
                self.assertEqual(basis, {"numerator": 1, "denominator": 16384, "value": 1/16384})
                self.assertEqual(Fraction(request["native_user_axes"]["HGHT"])*Fraction(basis["numerator"], basis["denominator"]),
                                 Fraction(request["axes"]["HGHT"]))
                self.assertEqual(request["native_user_axes"]["WDTH"], request["axes"]["WDTH"])

    def test_53_over_64_control_reaches_swift_as_13568_without_axis_relabeling(self):
        count = 0
        for entry in self.control["entries"]:
            wired = {r["id"]: r for r in wire_requests(entry)}
            for request in entry["requests"]:
                if request["case_group"] != "exact_normalization_grid_control": continue
                self.assertEqual(request["axes"]["HGHT"], 53/64)
                self.assertEqual(request["native_user_axes"]["HGHT"], 13568)
                self.assertEqual(wired[request["id"]]["axes"], {"WDTH": 0.0, "HGHT": 13568.0})
                self.assertEqual(request["normalized_design_axes"]["HGHT"], 53/64)
                count += 1
        self.assertEqual(count, 4)

    def test_wire_requests_fall_back_to_original_axes_and_are_independent_copies(self):
        for entry in self.original["entries"]:
            wire = wire_requests(entry)
            self.assertEqual(wire, [{"id": r["id"], "axes": r["axes"], "point_size": r["point_size"]} for r in entry["requests"]])
        entry = self.control["entries"][0]
        before = deepcopy(entry["requests"][0])
        wire = wire_requests(entry)
        self.assertEqual(set(wire[0]), {"id", "axes", "point_size"})
        wire[0]["axes"]["HGHT"] = 123
        self.assertEqual(entry["requests"][0], before)

    def test_vvar_coefficients_remain_the_same_normalized_function(self):
        checks = 0
        for entry in self.control["entries"]:
            if "VVAR" not in entry["table_sha256"]: continue
            with TTFont(self.path / entry["path"]) as font:
                table = font["VVAR"].table
                for request in entry["requests"]:
                    instance = VarStoreInstancer(table.VarStore, font["fvar"].axes, request["normalized_design_axes"])
                    self.assertEqual(instance[table.AdvHeightMap.mapping["witness"]], 150*request["axes"]["HGHT"])
                    self.assertIsNone(table.VOrgMap)
                    checks += 1
        self.assertEqual(checks, 242)

    def test_fonttools_user_axis_path_reaches_the_same_unrounded_outline(self):
        checks = 0
        for entry in self.control["entries"]:
            with TTFont(self.path / entry["path"]) as font:
                for request in entry["requests"]:
                    glyph_set = font.getGlyphSet(location=request["native_user_axes"], normalized=False)
                    pen = BoundsPen(glyph_set); glyph_set["witness"].draw(pen)
                    x, y, width, height = request["expected"]["witness_bounds"]
                    self.assertEqual(pen.bounds, (x, y, x+width, y+height))
                    checks += 1
        self.assertEqual(checks, 550)

    def test_before_after_provenance_hashes_match_real_bytes(self):
        for original, converted in zip(self.original["entries"], self.control["entries"]):
            provenance = converted["native_axis_unit_reparameterization"]
            self.assertTrue(provenance["raw_patch_without_font_reserialization"])
            self.assertEqual(provenance["before_sha256"], original["sha256"])
            self.assertEqual(provenance["before_table_sha256"], original["table_sha256"])
            self.assertEqual(provenance["after_sha256"], converted["sha256"])
            self.assertEqual(provenance["after_table_sha256"], converted["table_sha256"])
            self.assertEqual(converted["sha256"], hashlib.sha256((self.path / converted["path"]).read_bytes()).hexdigest())
            self.assertIn("fvar", provenance["changed_table_payloads"])
            self.assertTrue(set(provenance["changed_table_payloads"]) <= {"fvar", "head"})

    def test_invalid_scales_and_repeated_conversion_are_rejected(self):
        original = next(iter(self.font_bytes.values()))
        for scale in (0, -1, True, 16384.0, 32768):
            with self.subTest(scale=scale), self.assertRaises(ValueError): patch_height_axis(original, scale)
        with self.assertRaisesRegex(ValueError, "already_reparameterized"):
            reparameterize_height_axis(self.control, self.path)

    def test_corrupt_frozen_source_is_rejected_before_any_output_is_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = deepcopy(self.original)
            manifest["entries"] = manifest["entries"][:1]
            entry = manifest["entries"][0]
            (directory / entry["path"]).write_bytes(self.font_bytes[entry["path"]])
            entry["sha256"] = "0"*64
            with self.assertRaisesRegex(ValueError, "frozen_source_fixture_identity_mismatch"):
                reparameterize_height_axis(manifest, directory)
            self.assertEqual([p.name for p in directory.iterdir()], [entry["path"]])

    def test_unit_control_never_grants_native_axis_or_metric_acceptance(self):
        metadata = self.control["axis_user_unit_control"]
        self.assertEqual(metadata["native_acceptance"], "NOT_RUN")
        self.assertEqual(metadata["status"], "STRICT_NATIVE_READBACK_REQUIRED_NO_COORDINATE_ACCEPTANCE_CHANGE")
        self.assertEqual(self.control["native_acceptance"], "NOT_RUN")
        self.assertEqual(self.control["original_font_acceptance"], "NOT_ESTABLISHED")
        self.assertFalse(self.control["measurement_correction_applied"])


if __name__ == "__main__":
    unittest.main()
