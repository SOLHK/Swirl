"""Original fixtures; diagnosis must retain metric errors and source identity."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import diagnose_coretext_precision as precision
from compare_axis_construction import GUARD


class CoreTextPrecisionTests(unittest.TestCase):
    def original_observations(self):
        requests = [{"request_id": "minimum", "face_index": 0,
                     "location": {"WDTH": 1., "wght": 100., "HGHT": 1.}, "glyph_ids": [0, 1, 2]},
                    {"request_id": "maximum", "face_index": 1,
                     "location": {"WDTH": 1000., "wght": 900., "HGHT": 1000.}, "glyph_ids": [0, 1, 2]}]
        # These endpoint values follow the fixture's original design, independent
        # of the analysis function and of any native measurement correction.
        metrics = [[(550, 1000, 275, 820), (400, 1000, 200, 820), (570, 850, 285, 760)],
                   [(550, 1000, 275, 820), (400, 1000, 200, 820), (840, 1150, 420, 880)]]
        rows = []
        for request in requests:
            face = request["face_index"]
            for gid in request["glyph_ids"]:
                for scale in precision.SCALES:
                    metric = metrics[face][gid]
                    row = {"request_id": request["request_id"], "face_index": face, "glyph_id": gid,
                           "scale": scale, "point_size": (1000, 1128)[face] * scale,
                           "upm": (1000, 1128)[face], "location": request["location"],
                           "direct": dict(zip(precision.FIELDS, (v * scale for v in metric)))}
                    for name, value in (("run_horizontal", metric[0]), ("run_vertical", metric[1])):
                        row[name] = ({"status": "NO_NOMINAL_FIXTURE_CHARACTER"} if gid == 0 else {
                            "status": "MEASURED", "glyph_id": gid, "advance_magnitude": value * scale,
                            "exact_source_face_axes_and_point_size_verified": True})
                    rows.append(row)
        return requests, rows

    def test_measurement_size_is_not_a_font_coordinate_change(self):
        requests, rows = self.original_observations()
        before = copy.deepcopy(rows)
        result = precision.analyze_rows(rows, requests)
        self.assertEqual(rows, before)
        self.assertEqual(len(result["observations"]), 24)
        for summary in result["by_point_size_scale"].values():
            self.assertEqual(summary["direct_glyphs_outside_original_budget"], 0)
            self.assertEqual(summary["glyph_observations"], 6)
            self.assertEqual(summary["run_measurements"], 8)

    def test_one_unit_vertical_failure_is_retained_at_every_size(self):
        requests, rows = self.original_observations()
        for row in rows:
            if row["glyph_id"] == 2:
                row["direct"]["advance_height"] -= row["scale"]
        result = precision.analyze_rows(rows, requests)
        for summary in result["by_point_size_scale"].values():
            self.assertEqual(summary["direct_glyphs_outside_original_budget"], 2)
            self.assertEqual(summary["max_direct_error_by_field"]["advance_height"], 1)

    def test_empty_glyph_origins_are_not_silently_ignored(self):
        requests, rows = self.original_observations()
        for row in rows:
            if row["glyph_id"] == 1:
                row["direct"]["vertical_origin_x"] = row["direct"]["vertical_origin_y"] = 0
        result = precision.analyze_rows(rows, requests)
        for summary in result["by_point_size_scale"].values():
            self.assertEqual(summary["direct_glyphs_outside_original_budget"], 2)
            self.assertEqual(summary["max_direct_error_by_field"]["vertical_origin_x"], 200)
            self.assertEqual(summary["max_direct_error_by_field"]["vertical_origin_y"], 820)

    def test_missing_duplicate_nonfinite_and_changed_identity_are_rejected(self):
        requests, rows = self.original_observations()
        bad = [rows[:-1], rows[:-1] + [rows[0]]]
        for field, value in (("face_index", 1), ("point_size", 999), ("upm", 999)):
            changed = copy.deepcopy(rows); changed[0][field] = value; bad.append(changed)
        missing = copy.deepcopy(rows); del missing[0]["direct"]["advance_height"]; bad.append(missing)
        nonfinite = copy.deepcopy(rows); nonfinite[0]["direct"]["advance_width"] = float("nan"); bad.append(nonfinite)
        for changed in bad:
            with self.assertRaises(ValueError):
                precision.analyze_rows(changed, requests)

    def test_run_fallback_is_not_a_comparable_metric(self):
        requests, rows = self.original_observations()
        row = next(r for r in rows if r["glyph_id"] == 2)
        row["run_vertical"]["glyph_id"] = 1
        with self.assertRaisesRegex(ValueError, "substituted glyph"):
            precision.analyze_rows(rows, requests)

    def test_unavailable_run_api_is_reported_without_losing_direct_measurements(self):
        requests, rows = self.original_observations()
        row = next(r for r in rows if r["glyph_id"] == 2)
        row["run_vertical"] = {"status": "API_ERROR", "error": "fixture_run_font_missing"}
        result = precision.analyze_rows(rows, requests)
        self.assertEqual(len(result["observations"]), 24)
        self.assertEqual(result["by_point_size_scale"][str(row["scale"])]["run_api_errors"], 1)

    def test_harness_preserves_production_axis_guard_and_pins_generated_sources(self):
        source = "// helpers\n" + GUARD + "\nfunc run() throws { // original main }"
        hashes = [c * 64 for c in "abc"]
        output = precision.make_harness(source, hashes)
        self.assertEqual(output.count(GUARD), 1)
        self.assertIn("generated_synthetic_fonts_only", output)
        self.assertNotIn("// original main", output)
        self.assertIn(json.dumps(hashes), output)
        for invalid in ([], hashes[:2], ["x"*64, *hashes[:2]], [hashes[0]]*3):
            with self.assertRaises(ValueError):
                precision.make_harness(source, invalid)
        with self.assertRaisesRegex(ValueError, "helper structure changed"):
            precision.make_harness(source + GUARD, hashes)

    @unittest.skipIf(sys.platform == "darwin", "native experiment is a separate explicit CI step")
    def test_no_native_runtime_cannot_be_reported_as_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertEqual(precision.run(output, require_native=True), 2)
            report = json.loads((output / "coretext_precision_diagnosis.json").read_text())
            self.assertEqual(report["status"], "NOT_RUN")
            self.assertEqual(report["variants"], {})
            self.assertTrue(report["temporary_synthetic_fonts_removed"])
            self.assertEqual(report["analytical_tolerance_font_units"], 1 / 32)
            self.assertFalse(report["original_strict_gate_replaced"])
            self.assertEqual(report["native_font_acceptance"], "NOT_ESTABLISHED")


if __name__ == "__main__":
    unittest.main()
