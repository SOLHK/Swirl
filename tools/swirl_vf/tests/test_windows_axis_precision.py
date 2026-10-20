"""Portable tests of authored fixtures and numeric discriminators, never Windows.

Native observations are produced by the separate D1 Windows workflow.  These
tests cannot certify DirectWrite, Qt, system installation or the Apple font.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import make_win_axis_precision_fixture as fixture


class WindowsAxisPrecisionFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        cls.manifest = fixture.write_fixture(cls.directory / "first")
        cls.cases = {case["id"]: case for case in cls.manifest["cases"]}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_requested_pair_is_distinct_binary64_but_collides_binary32(self):
        lo, hi = self.cases["pair_lo"], self.cases["pair_hi"]
        self.assertNotEqual(lo["requested_binary64"]["wght"], hi["requested_binary64"]["wght"])
        self.assertNotEqual(lo["binary64_hex"]["wght"], hi["binary64_hex"]["wght"])
        for case in (lo, hi):
            self.assertEqual(case["float32_bits_hex"]["wght"], "0x43f980cb")
            self.assertEqual(case["float32"]["wght"], 499.006195068359375)
            self.assertEqual(case["nearest_16_16"]["wght"], 32702870)
        self.assertEqual(self.manifest["pair_float32_ulp"], 1 / 32768)

    def test_low_controls_distinguish_float32_from_user_fixed16(self):
        lo, hi = self.cases["low_f32_1"], self.cases["low_f32_2"]
        self.assertNotEqual(lo["float32"]["wght"], hi["float32"]["wght"])
        self.assertEqual(lo["nearest_16_16"]["wght"], 6553601)
        self.assertEqual(hi["nearest_16_16"]["wght"], 6553601)
        for case in (lo, hi):
            self.assertEqual(Decimal(case["decimal"]["wght"]), Decimal.from_float(case["float32"]["wght"]))
        models = self.manifest["predictions"]["gain"]
        self.assertGreater(abs(models[lo["id"]]["binary32_continuous"]["A_advance_unrounded"]
                               - models[hi["id"]]["binary32_continuous"]["A_advance_unrounded"]), 4.99)
        self.assertEqual(models[lo["id"]]["binary32_user16_continuous"],
                         models[hi["id"]]["binary32_user16_continuous"])

    def test_tsv_preserves_cases_order_original_decimal_and_uppercase_tags(self):
        path = self.directory / "first" / "requests.tsv"
        content = path.read_text(encoding="ascii")
        rows = content.splitlines()
        self.assertEqual(rows[0], "id\twght\tWDTH\tHGHT")
        self.assertEqual(len(rows), len(self.manifest["cases"]) + 1)
        self.assertEqual(len(self.cases), len(self.manifest["cases"]))
        for line, case in zip(rows[1:], self.manifest["cases"]):
            fields = line.split("\t")
            self.assertEqual(fields[0], case["id"])
            self.assertEqual(fields[1:], [case["decimal"][tag] for tag, *_ in fixture.AXES])
            self.assertTrue(all(math.isfinite(float(value)) for value in fields[1:]))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), self.manifest["requests_sha256"])

    def test_all_outputs_are_deterministic(self):
        fixture.write_fixture(self.directory / "second")
        for filename in ("ordinary.ttf", "gain.ttf", "manifest.json", "requests.tsv"):
            self.assertEqual((self.directory / "first" / filename).read_bytes(),
                             (self.directory / "second" / filename).read_bytes(), filename)

    def test_sfnt_checksum_and_manifest_font_hashes(self):
        for info in self.manifest["fonts"]:
            content = (self.directory / "first" / info["file"]).read_bytes()
            self.assertEqual(len(content), info["bytes"])
            self.assertEqual(hashlib.sha256(content).hexdigest(), info["sha256"])
            padded = content + b"\0" * (-len(content) % 4)
            self.assertEqual(sum(struct.unpack(">" + "I" * (len(padded) // 4), padded)) & 0xFFFFFFFF,
                             0xB1B0AFBA)

    def test_serialized_font_identity_cmap_axes_and_stat(self):
        for info in self.manifest["fonts"]:
            with TTFont(self.directory / "first" / info["file"], checkChecksums=2) as font:
                self.assertEqual(font.getGlyphOrder(), list(fixture.GLYPHS))
                self.assertEqual(font.getBestCmap(), fixture.CMAP)
                self.assertEqual(font["name"].getDebugName(16), info["family"])
                self.assertEqual(font["name"].getDebugName(17), "Regular")
                self.assertEqual([axis.axisTag for axis in font["fvar"].axes], ["wght", "WDTH", "HGHT"])
                self.assertEqual([(axis.minValue, axis.defaultValue, axis.maxValue)
                                  for axis in font["fvar"].axes],
                                 [(axis[1], axis[2], axis[3]) for axis in fixture.AXES])
                self.assertEqual(font["STAT"].table.DesignAxisCount, 3)
                self.assertEqual(font["STAT"].table.AxisValueCount, 5)
                self.assertEqual(font["OS/2"].version, 4)
                self.assertEqual(font["head"].unitsPerEm, 1000)
                self.assertTrue({"fvar", "avar", "gvar", "HVAR", "STAT"}.issubset(font.keys()))

    def test_avar_maps_are_legal_monotone_exact_f2dot14(self):
        for info in self.manifest["fonts"]:
            with TTFont(self.directory / "first" / info["file"]) as font:
                for mapping in font["avar"].segments.values():
                    points = sorted(mapping.items())
                    self.assertEqual(mapping[-1], -1)
                    self.assertEqual(mapping[0], 0)
                    self.assertEqual(mapping[1], 1)
                    self.assertTrue(all(x0 < x1 and y0 <= y1 for (x0, y0), (x1, y1) in zip(points, points[1:])))
                    self.assertTrue(all(value * 16384 == int(value * 16384) for point in points for value in point))
                if info["kind"] == "gain":
                    self.assertEqual(font["avar"].segments["wght"], fixture.GAIN_MAP)

    def test_gvar_phantom_advance_and_hvar_encode_same_deltas(self):
        for info in self.manifest["fonts"]:
            with TTFont(self.directory / "first" / info["file"]) as font:
                hvar = font["HVAR"].table
                self.assertIsNone(hvar.AdvWidthMap)
                self.assertEqual(hvar.VarStore.VarDataCount, 1)
                data = hvar.VarStore.VarData[0]
                self.assertEqual(len(data.Item), len(fixture.GLYPHS))
                self.assertEqual(data.VarRegionIndex, list(range(6)))
                for glyph_id, name in enumerate(fixture.GLYPHS):
                    coordinates, _, _ = font["glyf"][name].getCoordinates(font["glyf"])
                    variations = font["gvar"].variations[name]
                    self.assertEqual(len(variations), 6)
                    for region_id, variation in enumerate(variations):
                        self.assertEqual(len(variation.coordinates), len(coordinates) + 4)
                        self.assertEqual(variation.coordinates[-4], (0, 0))
                        self.assertEqual(variation.coordinates[-3], (data.Item[glyph_id][region_id], 0))
                        self.assertEqual(variation.coordinates[-2:], [(0, 0), (0, 0)])

    def test_all_three_axes_change_real_serialized_geometry(self):
        for info in self.manifest["fonts"]:
            samples = info["serialized_control_samples"]
            default = samples["wght_default"]
            self.assertEqual(default["A_advance"], info["base_A_advance"])
            self.assertEqual(default["A_bounds"], (60, 0, info["base_A_rightmost"], 700))
            for tag in ("wght", "WDTH", "HGHT"):
                self.assertNotEqual(samples[tag + "_min"]["A_bounds"], default["A_bounds"])
                self.assertNotEqual(samples[tag + "_max"]["A_bounds"], default["A_bounds"])
            self.assertEqual(samples["HGHT_min"]["A_advance"], default["A_advance"])
            self.assertEqual(samples["HGHT_max"]["A_advance"], default["A_advance"])

    def test_saved_static_instances_have_expected_control_metrics_and_bounds(self):
        for info in self.manifest["fonts"]:
            for case_id in ("default", "wght_min", "wght_max", "WDTH_min", "WDTH_max", "HGHT_min", "HGHT_max", "mixed_min", "mixed_max"):
                with self.subTest(font=info["kind"], case=case_id):
                    with TTFont(self.directory / "first" / info["file"], recalcTimestamp=False) as font:
                        instance = instantiateVariableFont(font, self.cases[case_id]["float32"], inplace=False)
                        path = self.directory / "static.ttf"
                        instance.save(path)
                        instance.close()
                    with TTFont(path) as static:
                        expected = self.manifest["predictions"][info["kind"]][case_id]["binary32_continuous"]
                        self.assertEqual(static["hmtx"].metrics["A"][0], expected["A_advance_unrounded"])
                        glyph_set = static.getGlyphSet()
                        pen = BoundsPen(glyph_set)
                        glyph_set["A"].draw(pen)
                        self.assertEqual(pen.bounds[2], expected["A_rightmost_unrounded"])
                        self.assertEqual(pen.bounds[3], expected["A_top_unrounded"])
                        self.assertTrue(all(advance >= 0 for advance, _ in static["hmtx"].metrics.values()))

    def test_gain_predeclared_models_are_observably_distinct(self):
        prediction = self.manifest["predictions"]["gain"]["pair_lo"]
        self.assertAlmostEqual(prediction["binary32_continuous"]["A_advance_unrounded"], 18820, places=6)
        self.assertEqual(prediction["binary32_normalize16_before_avar"]["A_advance_unrounded"], 19000)
        self.assertEqual(prediction["binary32_normalize14_before_avar"]["A_advance_unrounded"], 16000)
        neighbor = self.manifest["predictions"]["gain"]["f32_p1"]
        self.assertAlmostEqual(neighbor["binary32_continuous"]["A_advance_unrounded"]
                               - prediction["binary32_continuous"]["A_advance_unrounded"], 12, places=6)

    def test_generated_manifest_does_not_claim_native_or_original_acceptance(self):
        saved = json.loads((self.directory / "first" / "manifest.json").read_text())
        self.assertTrue(saved["original_synthetic"])
        self.assertEqual(saved["windows_native_results"], "NOT_RUN")
        self.assertEqual(saved["original_apple_acceptance"], "NOT_RUN")
        self.assertIn("not native outputs", saved["numeric_model_scope"])
        self.assertTrue(any("abstract fixture marks" in item for item in saved["limits"]))


if __name__ == "__main__":
    unittest.main()
