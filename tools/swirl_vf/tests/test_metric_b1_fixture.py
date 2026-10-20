"""Storage/control checks for B1; these never report a native metric pass."""
from fractions import Fraction
import hashlib
import math
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from fontTools.varLib.varStore import VarStoreInstancer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from b1_metric_fixture import (
    HOLDOUT_Y, ORDER, TRAINING_Y, UPMS, VARIANTS, build_fixture, build_suite,
    comparison_table_bytes, expected_metrics, fixture_requests, rational_predictions,
)


class B1MetricFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.path = Path(cls.directory.name)
        cls.manifest = build_suite(cls.path)
        cls.entries = {(e["upem"], e["variant"]): e for e in cls.manifest["entries"]}

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def open_font(self, upem=1000, variant="gvar"):
        return TTFont(self.path / self.entries[upem, variant]["path"], recalcTimestamp=False)

    def test_pairs_change_only_upem_and_required_checksum(self):
        for variant in VARIANTS:
            with self.subTest(variant=variant), self.open_font(1000, variant) as a, self.open_font(1024, variant) as b:
                at, bt = comparison_table_bytes(a), comparison_table_bytes(b)
                self.assertEqual(at.keys(), bt.keys())
                for tag in at:
                    left, right = at[tag], bt[tag]
                    if tag == "head":
                        self.assertEqual(a["head"].unitsPerEm, 1000)
                        self.assertEqual(b["head"].unitsPerEm, 1024)
                        left, right = left[:18] + bytes(2) + left[20:], right[:18] + bytes(2) + right[20:]
                    self.assertEqual(left, right, (variant, tag))

    def test_semantic_sentinels_are_isolated(self):
        expected = {"gvar": [], "hvar": ["HVAR"], "vvar": ["VVAR"],
                    "hvar_vvar": ["HVAR", "VVAR"], "hhea_ascent": ["hhea"],
                    "vhea_ascent": ["vhea"], "os2_typo_ascent": ["OS/2"],
                    "os2_use_typo": ["OS/2"], "os2_typo_ascent_use_typo": ["OS/2"], "vorg_y": ["VORG"],
                    "phantom_shift_1": ["vhea", "vmtx"],
                    "phantom_shift_91": ["vhea", "vmtx"], "phantom_only": ["gvar"]}
        for key, entry in self.entries.items():
            with self.subTest(key=key):
                self.assertEqual(entry["changed_tables_vs_gvar"], expected[key[1]])
        for upem in UPMS:
            self.assertEqual(self.entries[upem, "hhea_ascent"]["storage"]["hhea"]["ascent"], 891)
            self.assertEqual(self.entries[upem, "vhea_ascent"]["storage"]["vhea"]["ascent"], 591)
            self.assertEqual(self.entries[upem, "os2_typo_ascent"]["storage"]["OS2"]["sTypoAscender"], 891)
            self.assertEqual(self.entries[upem, "os2_use_typo"]["storage"]["OS2"]["fsSelection"], 0xC0)

    def test_os2_combined_control_changes_only_selection_bit_from_typo_sentinel(self):
        for upem in UPMS:
            entry = self.entries[upem, "os2_typo_ascent_use_typo"]
            self.assertEqual(entry["comparison_variant"], "os2_typo_ascent")
            self.assertEqual(entry["changed_tables_vs_comparison"], ["OS/2"])
            self.assertEqual(entry["changed_fields"], [{"field": "OS2.fsSelection", "before": 0x40, "after": 0xC0}])
            self.assertEqual(entry["storage"]["OS2"]["sTypoAscender"], 891)
            self.assertEqual(entry["storage"]["hhea"]["ascent"], 800)

    def test_phantom_only_freezes_outline_without_altering_metric_deltas(self):
        for upem in UPMS:
            with self.open_font(upem, "gvar") as base, self.open_font(upem, "phantom_only") as control:
                for a, b in zip(base["gvar"].variations["witness"], control["gvar"].variations["witness"]):
                    self.assertEqual(a.axes, b.axes)
                    self.assertEqual(a.coordinates[-4:], b.coordinates[-4:])
                    if "HGHT" in b.axes:
                        self.assertEqual(b.coordinates[:4], [(0, 0)] * 4)
                    else:
                        self.assertEqual(a.coordinates, b.coordinates)
            for request in self.entries[upem, "phantom_only"]["requests"]:
                self.assertEqual(request["expected"]["witness_bounds"][1::2], [-180, 1000])
                self.assertEqual(request["expected"]["advance_height"], 1000 + 150 * request["axes"]["HGHT"])
                self.assertEqual(request["expected"]["outline_role"], "fixed_height_counterfactual")

    def test_default_phantoms_match_stored_metrics(self):
        for (upem, variant), entry in self.entries.items():
            with self.subTest(upem=upem, variant=variant), self.open_font(upem, variant) as font:
                coordinates, _ = font["glyf"]._getCoordinatesAndControls(
                    "witness", font["hmtx"].metrics, font["vmtx"].metrics)
                shift = entry["phantom_shift"]
                self.assertEqual(list(coordinates[-4:]), [(0, 0), (1000, 0), (0, 820 + shift), (0, -180 + shift)])
                self.assertEqual(list(coordinates[:4]), [(100, -180), (700, -180), (700, 820), (100, 820)])

    def test_visible_witness_and_phantom_deltas_agree(self):
        with self.open_font() as font:
            variations = font["gvar"].variations["witness"]
            for variation in variations:
                self.assertEqual(len(variation.coordinates), 8)
                self.assertFalse(any(p is None for p in variation.coordinates))
                if "HGHT" in variation.axes:
                    points = variation.coordinates
                    self.assertEqual(points[0][1], points[1][1])
                    self.assertEqual(points[2][1], points[3][1])
                    self.assertEqual(points[2][1], points[-2][1])
                    self.assertEqual(points[0][1], points[-1][1])
            self.assertFalse(font["gvar"].variations["control"])
            self.assertFalse(font["gvar"].variations[".notdef"])

    def test_serialized_variable_outline_preserves_fractional_witness_height(self):
        for upem in UPMS:
            for variant in ("gvar", "hvar_vvar", "phantom_shift_91", "phantom_only"):
                with self.open_font(upem, variant) as font:
                    for request in fixture_requests(upem, variant):
                        glyph_set = font.getGlyphSet(location=request["axes"], normalized=True)
                        pen = BoundsPen(glyph_set)
                        glyph_set["witness"].draw(pen)
                        left, bottom, width, height = request["expected"]["witness_bounds"]
                        self.assertEqual(pen.bounds, (left, bottom, left + width, bottom + height))

    def test_equivalent_metric_coefficients_from_serialized_tables(self):
        checks = 0
        for upem in UPMS:
            for variant in ("hvar", "vvar", "hvar_vvar"):
                with self.open_font(upem, variant) as font:
                    for request in fixture_requests(upem, variant):
                        x, y = request["axes"]["WDTH"], request["axes"]["HGHT"]
                        for tag, field, expected in (("HVAR", "AdvWidthMap", 200*x), ("VVAR", "AdvHeightMap", 150*y)):
                            if tag not in font: continue
                            table = font[tag].table
                            instancer = VarStoreInstancer(table.VarStore, font["fvar"].axes, request["axes"])
                            mapping = getattr(table, field).mapping
                            for name in ORDER:
                                self.assertEqual(instancer[mapping[name]], expected if name == "witness" else 0)
                                checks += 1
                            for side_field in (("LsbMap", "RsbMap") if tag == "HVAR" else ("TsbMap", "BsbMap")):
                                for index in getattr(table, side_field).mapping.values():
                                    self.assertEqual(instancer[index], 0)
                                    checks += 1
                            if tag == "VVAR": self.assertIsNone(table.VOrgMap)
        self.assertEqual(checks, 1728)

    def test_dyadic_inputs_are_exact_in_standard_encodings(self):
        for entry in self.manifest["entries"]:
            self.assertEqual(len(entry["requests"]), 24)
            for request in entry["requests"]:
                for value in request["axes"].values():
                    self.assertEqual(Fraction(value * 16384).denominator, 1)
                    self.assertEqual(Fraction(value * 65536).denominator, 1)
                self.assertEqual(request["point_size"], entry["upem"])
        self.assertFalse(set(TRAINING_Y) & set(HOLDOUT_Y))

    def test_preregistered_minimum_separates_upem_candidate(self):
        a, b = rational_predictions(-1, 1000), rational_predictions(-1, 1024)
        self.assertEqual(a["height"]["value"], 850)
        self.assertEqual(b["height"]["value"], 850)
        self.assertEqual(a["difference_first"]["before_final_truncation"]["value"], 849.9908447265625)
        self.assertEqual(a["difference_first"]["prediction"], 849)
        self.assertEqual(b["difference_first"]["prediction"], 850)

    def test_translation_separates_per_point_and_difference_quantization(self):
        baseline = rational_predictions(-1, 1000)
        shifted = rational_predictions(-1, 1000, 91)
        self.assertEqual(baseline["height"], shifted["height"])
        self.assertEqual(baseline["coordinate_first"]["prediction"], 849)
        self.assertEqual(shifted["coordinate_first"]["prediction"], 850)
        self.assertEqual(shifted["difference_first"]["prediction"], 849)
        for shift in (0, 1, 91):
            dyadic = rational_predictions(-1, 1024, shift)
            self.assertEqual(dyadic["coordinate_first"]["prediction"], 850)
            self.assertEqual(dyadic["difference_first"]["prediction"], 850)

    def test_internal_points_separate_phantom_rounding_from_height_rounding(self):
        quarter = rational_predictions(0.25, 1000)
        eighths = rational_predictions(0.375, 1000)
        self.assertEqual((quarter["round_each_phantom"], quarter["round_height_once"]), (1037, 1038))
        self.assertEqual((eighths["round_each_phantom"], eighths["round_height_once"]), (1057, 1056))

    def test_preserves_fractional_expected_values(self):
        value = expected_metrics(0, 0.25)
        self.assertEqual(value["advance_height"], 1037.5)
        self.assertEqual(value["basis"]["height"], {"numerator": 2075, "denominator": 2, "value": 1037.5})
        self.assertEqual(expected_metrics(-1, -1)["vertical_origin_x_current_half_width"], 400)
        self.assertEqual(expected_metrics(-1, -1)["vertical_origin_x_default_half_width"], 500)

    def test_rejects_nonfinite_or_invalid_model_inputs(self):
        for value in (math.nan, math.inf, -math.inf, True, "0.25"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rational_predictions(value, 1000)
        for arguments in ((1001, "gvar"), (1000, "unknown")):
            with self.assertRaises(ValueError): build_fixture(*arguments)
        with self.assertRaises(ValueError): rational_predictions(1.1, 1000)
        with self.assertRaises(ValueError): expected_metrics(1.1, 0)

    def test_manifest_hashes_and_no_native_acceptance_claim(self):
        self.assertEqual(self.manifest["native_acceptance"], "NOT_RUN")
        self.assertEqual(self.manifest["original_font_acceptance"], "NOT_ESTABLISHED")
        self.assertEqual(self.manifest["strict_budget_font_units"], 1/32)
        self.assertEqual(len(self.manifest["entries"]), 26)
        for entry in self.manifest["entries"]:
            path = self.path / entry["path"]
            self.assertEqual(entry["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            with TTFont(path, lazy=True) as font:
                for tag, digest in entry["table_sha256"].items():
                    self.assertEqual(digest, hashlib.sha256(font.reader[tag]).hexdigest())


if __name__ == "__main__":
    unittest.main()
