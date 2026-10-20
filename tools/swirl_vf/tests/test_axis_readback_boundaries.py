"""Independent numeric and private-payload fixtures; no Apple asset is used."""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import probe_axis_readback_boundaries as boundary


class BoundaryProbeTests(unittest.TestCase):
    axes = {"WDTH": (1., 500., 1000.), "wght": (100., 400., 900.), "HGHT": (1., 500., 1000.)}

    def variants(self):
        return boundary.declared_variants(boundary.SYNTHETIC44)

    def record(self, variant="requested", offset=0.):
        location = next(v["location"] for v in self.variants() if v["name"] == variant)
        return {"type": "glyph", "writer_variant": variant, "request_id": "independent-numeric-fixture",
                "face_index": 0, "glyph_id": 2, "location": deepcopy(location), "reported_location": deepcopy(location),
                "commands": [["moveTo", 12. + offset, 20.], ["lineTo", 30. + offset, 20.],
                             ["lineTo", 30. + offset, 50.], ["closePath"]],
                "advance_width": 80., "advance_height": 100., "lsb": 12. + offset,
                "horizontal_origin_x": 0., "horizontal_origin_y": 0.,
                "vertical_origin_x": 40., "vertical_origin_y": 90.,
                "horizontal_advance_vector": [80., 0.], "vertical_advance_vector": [100., 0.],
                "vertical_origin_translation": [-40., -90.],
                "horizontal_advance_sum": 80., "vertical_advance_sum": 100.,
                "bounds": [12. + offset, 20., 18., 30.], "path_status": "path",
                "lsb_derivation": "original-private-test-fixture", "vertical_origin_derivation": "original-private-test-fixture",
                "error": None}

    def matrix(self):
        return {order: {name: {2: self.record(name)} for name in boundary.VARIANTS} for order in boundary.ORDERS}

    def test_failed_weights_distinguish_multiplication_from_division_by_one_binary64_step(self):
        cases = ((323.3597412109375, "407435c154c985f0", "407435c154c985f1", 323.3596),
                 (267.10205078125, "4070b1a1cac08312", "4070b1a1cac08313", 267.1019))
        for original, divided, multiplied, second in cases:
            values = boundary.candidate_values(original)
            self.assertEqual(tuple(values), boundary.VARIANTS)
            self.assertEqual(boundary.bits(values["divide1"]), divided)
            self.assertEqual(boundary.bits(values["multiply1"]), multiplied)
            self.assertEqual(math.nextafter(values["divide1"], math.inf), values["multiply1"])
            self.assertEqual(values["divide2"], second)
            self.assertEqual(values["multiply2"], values["multiply1"])

    def test_equal_control_candidates_are_retained_as_separate_constructions(self):
        values = boundary.candidate_values(600.5859375)
        self.assertEqual(len(values), 5)
        self.assertEqual(len({boundary.bits(values[name]) for name in boundary.VARIANTS[1:]}), 1)
        self.assertEqual(values["divide1"], 600.5859)
        self.assertNotEqual(values["requested"], values["divide1"])

    def test_candidate_domain_is_explicit_and_never_clamps(self):
        for value in (0, -1, math.inf, math.nan, 1e308, True):
            with self.assertRaises(boundary.BoundaryError):
                boundary.candidate_values(value)
        with self.assertRaisesRegex(boundary.BoundaryError, "all_original_axis_tags"):
            boundary.declared_variants({"WDTH": 600.5859375})

    def test_both_actual_failures_and_binary64_decimal_neighbors_are_predeclared(self):
        for kind, original in (("original", boundary.SAMPLE44), ("synthetic", boundary.SYNTHETIC44)):
            cases = {row["case"]: row for row in boundary.positions(self.axes, kind)}
            self.assertEqual(len(cases), 10)
            self.assertEqual(cases["sample44_exact"]["variants"][0]["location"], original)
            for tag in boundary.TAGS:
                self.assertEqual(cases["sample44_binary64_below"]["variants"][0]["location"][tag],
                                 math.nextafter(original[tag], -math.inf))
                self.assertEqual(cases["sample44_binary64_above"]["variants"][0]["location"][tag],
                                 math.nextafter(original[tag], math.inf))
                integer = math.trunc(original[tag] * 10000)
                self.assertEqual(cases["sample44_decimal_below"]["variants"][0]["location"][tag], (integer - 1) / 10000)
                self.assertEqual(cases["sample44_decimal_above"]["variants"][0]["location"][tag], (integer + 1) / 10000)
            self.assertTrue(all([v["name"] for v in row["variants"]] == list(boundary.VARIANTS) for row in cases.values()))
            self.assertEqual(cases["control_exact"]["variants"][0]["location"]["WDTH"], 600.5859375)

    def test_echo_reports_bit_difference_without_reclassifying_it_as_equal(self):
        variants = self.variants()
        divided = variants[1]
        multiplied = variants[2]["location"]
        tracker = boundary.EchoTracker(self.axes, variants, divided)
        tracker.add(multiplied); tracker.add(multiplied)
        result = tracker.result()["axes"]["wght"]
        self.assertTrue(result["echo_constant_during_glyph_reads"])
        self.assertFalse(result["every_effective_echo_matches_input_bits"])
        self.assertEqual(result["initial_echo"]["declared_candidate_bit_matches"], ["multiply1", "multiply2"])
        self.assertEqual(len(result["distinct_echoes"]), 1)
        self.assertLess(abs(result["input_value"] - result["initial_echo"]["effective_value"]), 1e-6)

    def test_second_layer_and_changes_during_glyph_reads_are_preserved(self):
        variants = self.variants(); before = deepcopy(variants)
        tracker = boundary.EchoTracker(self.axes, variants, variants[1])
        tracker.add(variants[1]["location"])
        tracker.add(variants[3]["location"])
        result = tracker.result()["axes"]["wght"]
        self.assertFalse(result["echo_constant_during_glyph_reads"])
        self.assertFalse(result["every_effective_echo_matches_input_bits"])
        self.assertEqual(len(result["distinct_echoes"]), 2)
        self.assertEqual(result["final_echo"]["effective_value"], 267.1019)
        self.assertEqual(variants, before)

    def test_missing_nondefault_axis_is_reported_and_not_hidden_by_the_default(self):
        variants = self.variants()
        tracker = boundary.EchoTracker(self.axes, variants, variants[0])
        reported = dict(variants[0]["location"]); del reported["wght"]
        tracker.add(reported)
        result = tracker.result()["axes"]["wght"]
        self.assertTrue(result["nondefault_axis_omitted"])
        self.assertFalse(result["initial_echo"]["reported_present"])
        self.assertEqual(result["initial_echo"]["effective_value"], 400.)
        self.assertFalse(result["every_effective_echo_matches_input_bits"])

    def test_native_request_bits_identity_and_GID_cannot_change(self):
        variants = self.variants(); row = self.record()
        request = {"request_id": row["request_id"], "face_index": 0}
        boundary.validate_event(row, request, variants[0], "glyph", 2)
        changed = deepcopy(row); changed["location"]["WDTH"] = math.nextafter(changed["location"]["WDTH"], math.inf)
        with self.assertRaisesRegex(boundary.BoundaryError, "input_location_bits"):
            boundary.validate_event(changed, request, variants[0], "glyph", 2)
        with self.assertRaisesRegex(boundary.BoundaryError, "native_GID_changed"):
            boundary.validate_event(row, request, variants[0], "glyph", 1)
        changed = deepcopy(row); changed["face_index"] = False
        with self.assertRaisesRegex(boundary.BoundaryError, "identity_mismatch"):
            boundary.validate_event(changed, request, variants[0], "glyph", 2)

    def test_every_candidate_is_compared_and_original_reference_is_never_self_compared(self):
        private = self.matrix(); before = deepcopy(private)
        result = boundary.compare_case(private, [2])
        self.assertEqual(result["requested_self_comparisons"], 0)
        self.assertTrue(all(set(row) == set(boundary.VARIANTS[1:]) for row in result["within_process_against_requested"].values()))
        self.assertTrue(all(row["glyph_comparisons"] == row["exact_equal_glyphs"] == 1
                            for row in result["across_process_same_candidate"].values()))
        self.assertEqual(private, before)
        published = json.dumps(result)
        for raw in ("moveTo", "original-private-test-fixture", "horizontal_advance_vector"):
            self.assertNotIn(raw, published)

    def test_cross_process_difference_cannot_hide_behind_local_exact_equality(self):
        private = self.matrix()
        private["reverse"] = {name: {2: self.record(name, .25)} for name in boundary.VARIANTS}
        result = boundary.compare_case(private, [2])
        self.assertTrue(all(row["exact_equal_glyphs"] == 1 for process in result["within_process_against_requested"].values()
                            for row in process.values()))
        self.assertTrue(all(row["exact_equal_glyphs"] == 0 and row["max_command_coordinate_difference"] == .25
                            for row in result["across_process_same_candidate"].values()))

    def test_complete_raw_metric_vectors_and_typed_commands_stay_strict(self):
        private = self.matrix()
        private["forward"]["divide1"][2]["vertical_advance_vector"][1] = .125
        private["forward"]["multiply1"][2]["commands"][1] = ["qCurveTo", 20., 20., 30., 20.]
        result = boundary.compare_case(private, [2])["within_process_against_requested"]["forward"]
        self.assertEqual(result["divide1"]["exact_equal_glyphs"], 0)
        self.assertEqual(result["divide1"]["max_raw_or_derived_metric_difference"], .125)
        self.assertEqual(result["multiply1"]["topology_mismatches"], 1)
        self.assertEqual(result["divide2"]["exact_equal_glyphs"], 1)
        self.assertEqual(result["multiply2"]["exact_equal_glyphs"], 1)

    def test_missing_candidate_GID_or_raw_metric_fails_without_private_data_in_error(self):
        for kind in ("candidate", "gid", "metric", "extra"):
            private = self.matrix()
            if kind == "candidate": del private["forward"]["divide2"]
            elif kind == "gid": private["forward"]["divide2"] = {}
            elif kind == "metric": del private["forward"]["divide2"][2]["horizontal_advance_sum"]
            else: private["forward"]["divide2"][2]["new_field"] = "/private/licensed/source.ttc"
            with self.assertRaises(ValueError) as caught:
                boundary.compare_case(private, [2])
            self.assertNotIn("/private/", str(caught.exception))
        with self.assertRaisesRegex(boundary.BoundaryError, "nonempty_unique_GIDs"):
            boundary.compare_case({}, [])

    def test_self_authored_fixture_is_private_and_original_mode_requires_the_exact_source(self):
        with tempfile.TemporaryDirectory(prefix="original-boundary-fixture-") as tmp:
            source = Path(tmp) / "original-test-fixture.ttc"
            boundary.make_fixture(source)
            digest, identity, axes, faces, gids, planned = boundary.inspect_source(source, "synthetic")
            self.assertEqual(len(digest), 64)
            self.assertEqual(len(identity), 2)
            self.assertEqual(faces, (0, 1)); self.assertEqual(gids, (0, 1, 2))
            self.assertEqual(len(planned), 20)
            self.assertTrue(all(row["variants"] == boundary.declared_variants(row["variants"][0]["location"]) for row in planned))
            with self.assertRaisesRegex(boundary.BoundaryError, "exact_original_source"):
                boundary.inspect_source(source, "original")

    def test_diagnostic_calls_raw_constructor_and_preserves_the_strict_guard(self):
        source = "func constructInstance() {}\n" + boundary.GUARD + "\nfunc run() throws {}"
        harness = boundary.make_harness(source)
        self.assertEqual(harness.count(boundary.GUARD), 1)
        self.assertIn("try constructInstance(state, variant.location)", harness)
        self.assertIn("withExtendedLifetime(retained)", harness)
        self.assertNotIn("try run()", harness)
        with self.assertRaisesRegex(boundary.BoundaryError, "review_changed_production_helpers"):
            boundary.make_harness(source + boundary.GUARD)


if __name__ == "__main__":
    unittest.main()
