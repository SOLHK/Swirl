"""Independent fixed-origin counterexamples; no Apple font or native data."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import rebuild
from test_rebuild import AXES, analytic_record, write_fixture
from test_rebuild_pipeline import OriginalAnalyticOracle


class MetricFailureEvidenceTests(unittest.TestCase):
    def test_late_glyph_origin_failure_retains_actual_sample_and_blocks_TTC(self):
        with tempfile.TemporaryDirectory(prefix="original-origin-counterexample-") as tmp:
            root = Path(tmp)
            source, candidate, report = root/"original.ttc", root/"Swirl-VF.ttc", root/"report.json"
            write_fixture(source, faces=3)
            before = source.read_bytes()
            oracle = OriginalAnalyticOracle(source)
            original_samples = oracle.samples
            failed_location = {}

            def samples(face, gids, location):
                records = original_samples(face, gids, location)
                for row in records.values():
                    row["location"] = dict(location)
                if len(oracle.requests) == 2:
                    # A half-unit static-origin discrepancy is still an error
                    # under the existing representation gate, irrespective of
                    # the separate one-unit sampled reconstruction budget.
                    records[1]["vertical_origin_x"] += .5
                    failed_location.update(location)
                return records

            oracle.samples = samples
            with mock.patch.object(rebuild, "NativeOracle", return_value=oracle):
                with self.assertRaisesRegex(rebuild.ReconstructionError, "not representable by standard vmtx"):
                    rebuild.run(source, root/"no-native-process", candidate, report, batch_size=2)
            saved = json.loads(report.read_text())
            self.assertEqual(source.read_bytes(), before)
            self.assertFalse(candidate.exists())
            self.assertEqual(saved["status"], "BLOCKED")
            self.assertFalse(saved["output_generated"])
            self.assertEqual(saved["faces"][0]["glyphs_completed"], 1)
            context = saved["failures"][0]["context"]
            self.assertEqual((context["face_index"], context["glyph_id"]), (0, 1))
            evidence = context["metric_representation"]
            self.assertEqual(evidence, {"field": "vertical_origin_x", "sample_number": 1,
                "sample_kind": "training", "user_location": failed_location,
                "absolute_error_font_units": .5, "representation_tolerance_font_units": 1e-5})
            self.assertEqual(oracle.finish_count, 0)
            self.assertEqual(oracle.close_count, 1)
            progress = saved["native_observation_progress"]
            self.assertEqual(progress["completed_batches_this_run"], len(oracle.requests))
            self.assertEqual(progress["glyph_observations_in_completed_batches_this_run"], 2*len(oracle.requests))

    def test_holdout_origin_error_is_not_lost_or_accepted_as_general_metric_budget(self):
        locations = rebuild.normalized_grid(AXES)
        training = [analytic_record(location) for location in locations]
        point = {"WDTH": .125, "wght": -.375, "HGHT": .625}
        heldout = analytic_record(point)
        heldout["location"] = rebuild.user_location(point, AXES)
        heldout["vertical_origin_x"] += .125
        with self.assertRaises(rebuild.ReconstructionError) as failed:
            rebuild.reconstruct_glyph(training, [heldout], locations, [point], AXES,
                                      (700, 0), (1000, 0), metric_limit=100.)
        evidence = rebuild.metric_failure_details(failed.exception.context["metric_representation"])
        self.assertEqual(evidence["sample_number"], len(training))
        self.assertEqual(evidence["sample_kind"], "holdout")
        self.assertEqual(evidence["user_location"], heldout["location"])
        self.assertEqual(evidence["absolute_error_font_units"], .125)
        self.assertEqual(evidence["representation_tolerance_font_units"], 1e-5)

    def test_public_metric_allowlist_excludes_paths_raw_metrics_and_nonfinite_values(self):
        record = {"field": "vertical_origin_x", "sample_number": True, "sample_kind": "PRIVATE",
            "absolute_error_font_units": float("nan"), "representation_tolerance_font_units": float("inf"),
            "user_location": {"WDTH": 500.125, "wght": True, "HGHT": float("nan"), "secret": "PRIVATE"},
            "advance_width": 733, "native_vertical_origin_x": 300,
            "commands": [["PRIVATE"]], "path": "/private/PRIVATE"}
        self.assertEqual(rebuild.metric_failure_details(record),
                         {"field": "vertical_origin_x", "user_location": {"WDTH": 500.125}})
        self.assertEqual(rebuild.metric_failure_details(None), {})
        record["absolute_error_font_units"] = 10**10000
        self.assertNotIn("absolute_error_font_units", rebuild.metric_failure_details(record))


if __name__ == "__main__":
    unittest.main()
