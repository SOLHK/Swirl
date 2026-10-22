"""Real native API integration tests; absence skips, no mocks imitate evidence."""
import ctypes.util
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from probe_axis_a3_normalized_api import (AXES, BASE_ADVANCE, HVAR_DELTA, INPUTS,
    STATUS, HarfBuzz, run, synthetic_font)


class SyntheticFixtureTests(unittest.TestCase):
    def test_fixture_is_deterministic_independently_authored_and_keeps_three_axes(self):
        data = synthetic_font()
        self.assertEqual(hashlib.sha256(data).hexdigest(), hashlib.sha256(synthetic_font()).hexdigest())
        with TTFont(io.BytesIO(data)) as font:
            self.assertEqual(font["maxp"].numGlyphs, 2)
            self.assertEqual([(a.axisTag, a.minValue, a.defaultValue, a.maxValue)
                             for a in font["fvar"].axes], list(AXES))
            self.assertEqual(font["hmtx"].metrics["square"][0], BASE_ADVANCE)
            self.assertEqual(font["HVAR"].table.VarStore.VarData[0].Item, [[0], [HVAR_DELTA]])
            self.assertEqual(font["glyf"]["square"].numberOfContours, 1)
            self.assertEqual(list(font["glyf"]["square"].coordinates), [(0, 0), (100, 0), (100, 100), (0, 100)])
            self.assertNotIn("hvgl", font)


@unittest.skipUnless(sys.platform == "linux" and ctypes.util.find_library("harfbuzz"),
                     "real installed Linux HarfBuzz required; no mock substitute")
class NativeNormalizedApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run()

    def test_actual_design_float_api_collapses_the_two_original_binary64_inputs(self):
        report = self.report["harfbuzz"]
        first, second = report["design_float32_samples"]
        self.assertNotEqual(first["retained_original_binary64_bits"], second["retained_original_binary64_bits"])
        self.assertEqual(first["weight_float32_bits"], "43f980cb")
        self.assertEqual(second["weight_float32_bits"], "43f980cb")
        self.assertEqual(first["readback_design_float32"], second["readback_design_float32"])
        self.assertTrue(report["native_design_output_collision"])

    def test_actual_normalized_api_preserves_distinct_q_and_produces_authored_metric_difference(self):
        samples = self.report["harfbuzz"]["normalized_f2dot14_samples"]
        self.assertEqual([r["readback_normalized_f2dot14"] for r in samples], [[0, 0, 0], [0, 65, 0]])
        self.assertEqual([r["synthetic_gid1_native_advance_font_units"] for r in samples], [500, 565])
        self.assertEqual([r["retained_original_decimal"] for r in samples], [text for text, _ in INPUTS])

    def test_independent_fresh_font_objects_retain_order_independent_results(self):
        hb = HarfBuzz(ctypes.util.find_library("harfbuzz"), synthetic_font())
        try:
            forward = [hb.sample(text, q, True) for text, q in INPUTS]
            reverse = [hb.sample(text, q, True) for text, q in reversed(INPUTS)]
            self.assertEqual(forward, list(reversed(reverse)))
        finally:
            hb.close()

    def test_real_freetype_normalized_setter_and_getter_when_installed(self):
        if not ctypes.util.find_library("freetype"):
            self.skipTest("real installed FreeType absent")
        ft = self.report["freetype"]
        self.assertTrue(ft["q0_and_q65_preserved"])
        self.assertEqual([r["readback_normalized_16_16"] for r in ft["samples"]], [[0, 0, 0], [0, 260, 0]])
        self.assertFalse(ft["glyph_metric_tested"])

    def test_report_preserves_scope_versions_and_safe_output(self):
        report = self.report
        self.assertEqual(report["status"], STATUS)
        self.assertTrue(report["conditional_native_channel_proven_on_this_runtime"])
        self.assertTrue(report["synthetic_only"])
        for flag in ("apple_source_font_read", "source_outlines_used", "source_font_or_synthetic_font_written",
                     "general_source_mapper_proven", "production_mapping_accepted", "windows_tested", "apple_tested"):
            self.assertFalse(report[flag])
        self.assertTrue(report["harfbuzz"]["library"]["version"])
        self.assertTrue(report["harfbuzz"]["library"]["loaded_files"])
        self.assertTrue(all(len(row["sha256"]) == 64 for row in report["harfbuzz"]["library"]["loaded_files"]))
        json.dumps(report, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
