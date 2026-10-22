"""Original diagnostic report fixtures; no Apple paths or native font assets."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import probe_axis_cache as cache


class AxisCacheProbeTests(unittest.TestCase):
    def fixture(self):
        requests = [{"index": 0, "face_index": 20, "phase": "first"},
                    {"index": 1, "face_index": 20, "phase": "repeat"}]
        comparison = {"glyph_observations": 6, "max_geometry_difference": 0.,
                      "max_metric_difference": 0., "path_topology_mismatch_gids": []}
        rows = [{"request_index": r["index"], "face_index": r["face_index"], "phase": r["phase"],
                 "status": "OBSERVED", "request_vs_readback_instance": copy.deepcopy(comparison)}
                for r in requests]
        rows[1]["first_identical_request_comparison"] = copy.deepcopy(comparison)
        return requests, {"reports": rows, "physical_faces_verified": 32,
                          "source_sha256": cache.construction.EXPECTED}

    def test_equal_observations_are_not_font_acceptance(self):
        requests, native = self.fixture()
        before = copy.deepcopy(native)
        result = cache.summarize(native, requests)
        self.assertEqual(result["readback_pairs"], 2)
        self.assertEqual(result["identical_request_pairs"], 1)
        self.assertEqual(result["observation_errors"], 0)
        self.assertEqual(result["font_acceptance"], "NOT_ESTABLISHED")
        self.assertEqual(native, before)

    def test_metric_geometry_and_topology_changes_remain_separate(self):
        requests, native = self.fixture()
        native["reports"][0]["request_vs_readback_instance"]["max_metric_difference"] = .125
        native["reports"][1]["request_vs_readback_instance"]["path_topology_mismatch_gids"] = [5]
        native["reports"][1]["first_identical_request_comparison"]["max_geometry_difference"] = .25
        result = cache.summarize(native, requests)
        self.assertEqual(result["max_readback_metric_difference"], .125)
        self.assertEqual(result["max_repeat_geometry_difference"], .25)
        self.assertEqual(result["topology_mismatch_comparisons"], 1)
        self.assertEqual(result["font_acceptance"], "NOT_ESTABLISHED")

    def test_failed_observations_remain_errors_without_fabricated_comparison(self):
        requests, native = self.fixture()
        native["reports"][0] = {"request_index": 0, "face_index": 20, "phase": "first",
                                 "status": "OBSERVATION_ERROR", "error": "original-fixture-error"}
        result = cache.summarize(native, requests)
        self.assertEqual(result["observation_errors"], 1)
        self.assertEqual(result["readback_pairs"], 1)

    def test_missing_readback_or_glyph_observations_are_rejected(self):
        requests, native = self.fixture()
        del native["reports"][0]["request_vs_readback_instance"]
        with self.assertRaisesRegex(ValueError, "missing readback"):
            cache.summarize(native, requests)
        requests, native = self.fixture()
        native["reports"][0]["request_vs_readback_instance"]["glyph_observations"] = 5
        with self.assertRaisesRegex(ValueError, "incomplete native glyph"):
            cache.summarize(native, requests)

    def test_incomplete_or_reordered_or_different_source_is_rejected(self):
        requests, native = self.fixture()
        variants = []
        missing = copy.deepcopy(native); missing["reports"].pop(); variants.append(missing)
        reordered = copy.deepcopy(native); reordered["reports"].reverse(); variants.append(reordered)
        other = copy.deepcopy(native); other["source_sha256"] = "0" * 64; variants.append(other)
        faces = copy.deepcopy(native); faces["physical_faces_verified"] = 31; variants.append(faces)
        for changed in variants:
            with self.assertRaises(ValueError):
                cache.summarize(changed, requests)

    def test_nonfinite_or_negative_discrepancy_is_rejected(self):
        for value in (float("nan"), float("inf"), -1., None):
            requests, native = self.fixture()
            native["reports"][0]["request_vs_readback_instance"]["max_geometry_difference"] = value
            with self.assertRaisesRegex(ValueError, "invalid native discrepancy"):
                cache.summarize(native, requests)

    def test_opposite_initial_orders_cover_the_same_exact_requests(self):
        forward, reverse = (cache.request_specs(order) for order in cache.ORDERS)
        self.assertEqual(len(forward), 36)
        self.assertEqual(len(reverse), 36)
        for face in (20, 31):
            first = [r["location"]["wght"] for r in forward
                     if r["face_index"] == face and r["phase"] == "initial"]
            second = [r["location"]["wght"] for r in reverse
                      if r["face_index"] == face and r["phase"] == "initial"]
            self.assertEqual(first, [300., 300.01, 400., 400.01])
            self.assertEqual(first, second[::-1])
            widths = [r["location"]["WDTH"] for r in forward
                      if r["face_index"] == face and "WDTH" in r["location"]]
            self.assertEqual(widths, [600.5859375] * 6)
        with self.assertRaises(ValueError):
            cache.request_specs("unsupported")

    def test_changed_native_helpers_are_not_silently_reused(self):
        source = "func makeInstance() {}\n" + cache.construction.GUARD + "\nfunc run() throws {}"
        harness = cache.make_harness(source)
        self.assertIn("func observationInstance()", harness)
        self.assertNotIn("try compareConstructionMain()", harness)
        self.assertEqual(harness.count("try cacheProbeMain()"), 1)
        self.assertIn(cache.construction.GUARD, source)
        with self.assertRaises(ValueError):
            cache.make_harness(source + cache.construction.GUARD)


if __name__ == "__main__":
    unittest.main()
