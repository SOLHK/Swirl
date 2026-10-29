"""Original numerical/identity fixtures for the observation-only native probe."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from probe_axis_thresholds import (ALL_MODELS, EXPECTED, bits, check_metadata, checked_batch, conditioned_grid,
    hvf_paths, infer_at_axis_nodes, mapping_candidates, same_private_payload)
from test_verified_axis_oracle import native_record
from calibrate_avar_metrics import infer_weight_from_metrics


TAGS = ("WDTH", "wght", "HGHT")
IDENTITY = [(-1., -1.), (0., 0.), (1., 1.)]


class ThresholdProbeTests(unittest.TestCase):
    def test_rejected_clipped_inverse_never_becomes_a_conditioned_grid(self):
        endpoints = ([-4, -2, 1, 0], [0, 0, 0, 0], [4, 2, -1, 0])
        rejected = infer_weight_from_metrics([8, 4, -2, 0], *endpoints)
        self.assertEqual(rejected["best_fit"]["normalized_weight"], 1.)
        self.assertFalse(rejected["within_unchanged_metric_budget"])
        self.assertIsNone(conditioned_grid(rejected))
        accepted = infer_weight_from_metrics([1, .5, -.25, 0], *endpoints)
        self.assertEqual(conditioned_grid(accepted), 4096)
        nongrid = infer_weight_from_metrics([4 / 3, 2 / 3, -1 / 3, 0], *endpoints)
        self.assertIsNone(conditioned_grid(nongrid))

    def test_global_candidates_use_original_ranges_and_keep_duplicate_records(self):
        axes = [SimpleNamespace(axisTag=tag, minValue=100., defaultValue=500., maxValue=900.) for tag in TAGS]
        font = {"fvar": SimpleNamespace(axes=axes)}
        raw = {tag: list(IDENTITY) for tag in TAGS}
        raw["wght"] = [(-1., -1.), (0., 0.), (0., .125), (1., .75), (1., 1.)]
        before = deepcopy(raw)
        location = dict.fromkeys(TAGS, 500.)
        location["wght"] += 400 / 65536
        values = mapping_candidates(font, raw, location)
        self.assertEqual(set(values), set(ALL_MODELS))
        # This authored discontinuity distinguishes request normalization from
        # predeclared decimal truncation before normalization. No native output
        # is used to select a model or to alter the raw ordered records.
        self.assertEqual(values["request_normalized16_truncate"]["wght"], .125)
        self.assertEqual(values["canonical_normalized16_truncate"]["wght"], 0.)
        self.assertEqual(raw, before)
        defaults = mapping_candidates(font, raw, dict.fromkeys(TAGS, 500.))
        self.assertTrue(all(value == dict.fromkeys(TAGS, 0.) for value in defaults.values()))

    def test_metadata_binds_every_face_and_original_table(self):
        identities = [{"face_index": face, "glyph_count": 17, "axes": [],
                       "verified_table_sha256": {"test": str(face)}} for face in range(32)]
        native = {"diagnostic_readback_observation_only": True, "axis_observations_only": False,
                  "backend": "CoreText", "source_sha256": EXPECTED, "source_byte_size": 123,
                  "faces": [{**deepcopy(face), "status": "identity_verified"} for face in identities]}
        check_metadata(native, identities, 123)
        bad = deepcopy(native); bad["faces"][-1]["verified_table_sha256"]["test"] = "changed"
        with self.assertRaisesRegex(ValueError, "original_face_table_identity_mismatch"):
            check_metadata(bad, identities, 123)
        for field, value in (("axis_observations_only", True), ("source_byte_size", 124),
                             ("diagnostic_readback_observation_only", False)):
            bad = {**native, field: value}
            with self.assertRaises(ValueError):
                check_metadata(bad, identities, 123)

    def test_cross_process_comparison_keeps_complete_typed_payload(self):
        request = {"request_id": "1", "face_index": 0, "location": dict.fromkeys(TAGS, 500.)}
        left = native_record(request, 0)
        right = deepcopy(left); right["request_id"] = "other-process-4"
        self.assertTrue(same_private_payload(left, right))
        for change in (lambda r: r.__setitem__("advance_height", 849.876),
                       lambda r: r["bounds"].__setitem__(0, 1.),
                       lambda r: r["commands"][1].__setitem__(0, "moveTo"),
                       lambda r: r.__setitem__("path_status", "empty_path"),
                       lambda r: r.__setitem__("unexpected_metric", 1)):
            altered = deepcopy(right); change(altered)
            self.assertFalse(same_private_payload(left, altered))
        altered = deepcopy(right); altered["location"]["wght"] = 500.1
        with self.assertRaises(ValueError):
            same_private_payload(left, altered)

    def test_checked_batch_rejects_bad_glyph_data_without_an_echo_tolerance(self):
        location = dict.fromkeys(TAGS, 500.)
        request = {"request_id": "1", "face_index": 0, "location": location, "glyph_ids": [0, 1]}
        data = {gid: native_record(request, gid) for gid in request["glyph_ids"]}
        oracle = SimpleNamespace(sequence=1, samples=lambda *args: data)
        self.assertEqual(checked_batch(oracle, 0, [0, 1], location), data)
        data[1]["advance_height"] = float("nan")
        with self.assertRaises(ValueError):
            checked_batch(oracle, 0, [0, 1], location)
        data[1] = native_record(request, 1)
        data[1]["reported_location"]["wght"] = 500.0001
        with self.assertRaisesRegex(ValueError, "inconsistent_native_instance_readback"):
            checked_batch(oracle, 0, [0, 1], location)

    def test_weight_inverse_refuses_fractional_other_axes_and_nonidentity_maps(self):
        axes = [SimpleNamespace(axisTag=tag, minValue=100., defaultValue=500., maxValue=900.) for tag in TAGS]
        neutral = SimpleNamespace(StartCoord=0., PeakCoord=0., EndCoord=0.)
        table = SimpleNamespace(VarStore=SimpleNamespace(VarRegionList=SimpleNamespace(
            Region=[SimpleNamespace(VarRegionAxis=[neutral, neutral, neutral])])))
        font = {"fvar": SimpleNamespace(axes=axes), "HVAR": SimpleNamespace(table=table)}
        records = {tag: list(IDENTITY) for tag in TAGS}
        cases = [{"location": {"WDTH": width, "wght": 350., "HGHT": 500.}} for width in (500., 500.1)]
        observations = [{gid: {"advance_width": 400. + gid} for gid in (5, 12, 56, 169)}] * 2
        with patch("probe_axis_thresholds.infer_source_weight_locations", return_value=[{"authored": True}]) as inverse:
            result = infer_at_axis_nodes(font, records, cases, observations)
        self.assertEqual(result, {0: {"authored": True}})
        self.assertEqual(len(inverse.call_args.args[1]), 1)
        records["WDTH"] = [(-1., -.5), (0., 0.), (1., 1.)]
        with self.assertRaisesRegex(ValueError, "identity_width_height"):
            infer_at_axis_nodes(font, records, cases, observations)

    def test_direct_HVF_requires_matching_identity_and_complete_final_summary(self):
        design = dict.fromkeys(TAGS, 0.)
        rows = [{"record": "header", "engine": "Apple HVF", "schema": 1,
                 "coordinate_space": "normalized_design_after_avar", "face_index": 2, "face_count": 32,
                 "maxp_glyphs": 47102, "input_bytes": 61473880, "fvar_axis_tags": list(TAGS),
                 "normalized_coords": [0., 0., 0.], "start": 7, "count": 1},
                {"record": "outline", "part_index": 7, "status": "OK", "native_code": 0,
                 "part_axis_count": 3, "applied_axis_count": 3, "events": [],
                 "counters": dict.fromkeys(("events", "parts_begun", "parts_ended", "paths_begun", "paths_ended",
                                            "moves", "lines", "quads", "cubics", "closes"), 0)},
                {"record": "summary", "status": "EXTRACTED", "rendered": 1, "failed": 0}]
        def observe(values):
            result = SimpleNamespace(returncode=0, stdout="\n".join(map(json.dumps, values)))
            with patch("probe_axis_thresholds.subprocess.run", return_value=result):
                return hvf_paths(Path("authored-oracle"), Path("authored-source"), 2, 7, design)
        self.assertEqual(observe(rows), [])
        for changed in (rows[:-1], rows + [rows[-1]]):
            with self.assertRaisesRegex(ValueError, "incomplete_native_HVF_transcript"):
                observe(changed)
        for record, key, value in ((0, "face_index", 3), (0, "normalized_coords", [0., .5, 0.]),
                                   (1, "applied_axis_count", 2), (1, "events", [["unknown_event", 1, 2, 3]]),
                                   (2, "failed", 1)):
            changed = deepcopy(rows); changed[record][key] = value
            with self.assertRaises(ValueError):
                observe(changed)
        for record, key in ((0, "schema"), (0, "coordinate_space"), (1, "part_axis_count"),
                            (1, "applied_axis_count"), (1, "counters")):
            changed = deepcopy(rows); changed[record].pop(key)
            with self.assertRaises(ValueError):
                observe(changed)

    def test_binary64_evidence_preserves_signed_zero_and_fractional_value(self):
        self.assertEqual(bits({"a": 0., "b": -0., "c": 600.5859375}),
                         {"a": "0000000000000000", "b": "8000000000000000", "c": "4082c4b000000000"})


if __name__ == "__main__":
    unittest.main()
