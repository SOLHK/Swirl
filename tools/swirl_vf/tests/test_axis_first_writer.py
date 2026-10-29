"""Independent analytic records expose first-writer false positives privately."""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import probe_axis_first_writer as writer


class FirstWriterTests(unittest.TestCase):
    defaults = {"WDTH": 500., "wght": 500., "HGHT": 500.}

    def request(self):
        location = {"WDTH": 600.5859375, "wght": 400.01, "HGHT": 500.}
        return {"request_id": "original-fixture", "face_index": 20,
                "requested": location, "canonical": writer.canonical_location(location), "glyph_ids": [7]}

    def record(self, offset=0.):
        request = self.request()
        return {"type": "glyph", "writer_variant": "requested", "request_id": request["request_id"],
                "face_index": 20, "glyph_id": 7, "location": request["requested"],
                "reported_location": request["canonical"],
                "commands": [["moveTo", 12. + offset, 21.], ["lineTo", 42. + offset, 21.],
                             ["lineTo", 42. + offset, 61.], ["closePath"]],
                "advance_width": 80., "advance_height": 100., "lsb": 12. + offset,
                "horizontal_origin_x": 0., "horizontal_origin_y": 0.,
                "vertical_origin_x": 40., "vertical_origin_y": 90.,
                "horizontal_advance_vector": [80., 0.], "vertical_advance_vector": [100., 0.],
                "vertical_origin_translation": [-40., -90.],
                "horizontal_advance_sum": 80., "vertical_advance_sum": 100.,
                "bounds": [12. + offset, 21., 30., 40.], "path_status": "path",
                "lsb_derivation": "independent-original-fixture",
                "vertical_origin_derivation": "independent-original-fixture", "error": None}

    def test_local_equality_cannot_hide_opposite_first_writer_cache_effect(self):
        a, b = self.record(), self.record(.25)
        result = writer.compare_four_variants(a, deepcopy(a), b, deepcopy(b))
        self.assertEqual(result["within_requested_first_process"]["exact_equal_glyphs"], 1)
        self.assertEqual(result["within_canonical_first_process"]["exact_equal_glyphs"], 1)
        for label in ("requested_across_processes", "canonical_across_processes"):
            self.assertEqual(result[label]["exact_equal_glyphs"], 0)
            self.assertEqual(result[label]["max_command_coordinate_difference"], .25)

    def test_all_four_exact_comparisons_preserve_raw_records_and_publish_only_counts(self):
        a = self.record(); before = deepcopy(a)
        result = writer.compare_four_variants(a, deepcopy(a), deepcopy(a), deepcopy(a))
        self.assertTrue(all(row["exact_equal_glyphs"] == 1 for row in result.values()))
        self.assertEqual(a, before)
        text = json.dumps(result)
        self.assertNotIn("moveTo", text)
        self.assertNotIn("21.0", text)
        self.assertNotIn("independent-original-fixture", text)

    def test_ignored_vector_components_and_advance_sums_must_be_equal(self):
        for field, index in (("horizontal_advance_vector", 1), ("vertical_advance_vector", 1),
                             ("vertical_origin_translation", 0), ("horizontal_advance_sum", None),
                             ("vertical_advance_sum", None)):
            left, right = self.record(), self.record()
            if index is None:
                right[field] += .125
            else:
                right[field][index] += .125
            result = writer.compare_private_glyphs(left, right)
            self.assertEqual(result["exact_equal_glyphs"], 0)
            self.assertEqual(result["max_raw_or_derived_metric_difference"], .125)

    def test_single_binary64_step_is_not_hidden_under_the_original_axis_tolerance(self):
        left, right = self.record(), self.record()
        right["commands"][0][1] = math.nextafter(right["commands"][0][1], math.inf)
        result = writer.compare_private_glyphs(left, right)
        self.assertEqual(result["exact_equal_glyphs"], 0)
        self.assertGreater(result["max_command_coordinate_difference"], 0.)
        self.assertLess(result["max_command_coordinate_difference"], 1e-6)

    def test_typed_commands_and_path_status_cannot_be_discarded(self):
        left, right = self.record(), self.record()
        right["commands"][1] = ["qCurveTo", 22., 21., 42., 21.]
        result = writer.compare_private_glyphs(left, right)
        self.assertEqual(result["exact_equal_glyphs"], 0)
        self.assertEqual(result["topology_mismatches"], 1)
        right = self.record(); right["path_status"] = "empty_path"
        result = writer.compare_private_glyphs(left, right)
        self.assertEqual(result["exact_equal_glyphs"], 0)

    def test_missing_nonfinite_unknown_fields_and_different_gids_are_rejected(self):
        variants = []
        missing = self.record(); del missing["vertical_advance_vector"]; variants.append(missing)
        invalid = self.record(); invalid["bounds"][0] = math.nan; variants.append(invalid)
        extra = self.record(); extra["new_native_metric"] = [1234567.89]; variants.append(extra)
        identity = self.record(); identity["glyph_id"] = 8; variants.append(identity)
        command = self.record(); command["commands"][0][1] = True; variants.append(command)
        for changed in variants:
            with self.assertRaises(writer.ProbeError) as caught:
                writer.compare_private_glyphs(self.record(), changed)
            self.assertNotIn("1234567.89", str(caught.exception))

    def test_requested_echo_is_validated_against_precomputed_decimal_rule(self):
        request = self.request(); row = self.record()
        self.assertEqual(request["canonical"]["WDTH"], 600.5859)
        self.assertNotEqual(request["canonical"]["WDTH"], request["requested"]["WDTH"])
        self.assertEqual(writer.validate_echo(row, request, "requested", self.defaults, "glyph"),
                         request["canonical"])
        row["reported_location"]["WDTH"] += 1e-7
        with self.assertRaisesRegex(writer.ProbeError, "decimal4_rule_not_observed"):
            writer.validate_echo(row, request, "requested", self.defaults, "glyph")

    def test_precomputed_candidate_truncates_instead_of_rounding_distinguishing_positions(self):
        original = {"WDTH": 561.7283945, "wght": 400.01, "HGHT": 581.267578125}
        expected = {"WDTH": 561.7283, "wght": 400.01, "HGHT": 581.2675}
        self.assertEqual(writer.canonical_location(original), expected)
        for tag in ("WDTH", "HGHT"):
            self.assertNotEqual(expected[tag], float(format(original[tag], ".4f")))
        self.assertEqual(original["WDTH"], 561.7283945)

    def test_nonidempotent_arithmetic_does_not_replace_the_required_stable_native_echo(self):
        request = self.request()
        request["requested"]["WDTH"] = 100.001125
        request["canonical"] = writer.canonical_location(request["requested"])
        self.assertEqual(request["canonical"]["WDTH"], 100.0011)
        recursive = writer.canonical_location(request["canonical"])
        self.assertEqual(recursive["WDTH"], 100.001)
        self.assertNotEqual(request["canonical"], recursive)
        row = self.record()
        row["writer_variant"] = "canonical"
        row["location"] = deepcopy(request["canonical"])
        row["reported_location"] = deepcopy(request["canonical"])
        writer.validate_echo(row, request, "canonical", self.defaults, "glyph")
        row["reported_location"] = recursive
        with self.assertRaisesRegex(writer.ProbeError, "decimal4_rule_not_observed"):
            writer.validate_echo(row, request, "canonical", self.defaults, "glyph")

    def test_positive_truncation_candidate_rejects_values_outside_its_stated_domain(self):
        for value in (0., -1., math.inf, math.nan, 1e308, True):
            location = {**self.defaults, "WDTH": value}
            with self.assertRaisesRegex(writer.ProbeError, "invalid_requested_axis_location"):
                writer.canonical_location(location)

    def test_missing_nondefault_axis_fails_even_when_other_fields_are_correct(self):
        request = self.request(); row = self.record()
        del row["reported_location"]["WDTH"]
        with self.assertRaisesRegex(writer.ProbeError, "missing_nondefault_axis"):
            writer.validate_echo(row, request, "requested", self.defaults, "glyph")
        row = self.record(); del row["reported_location"]["HGHT"]
        writer.validate_echo(row, request, "requested", self.defaults, "glyph")

    def test_canonical_value_cannot_be_selected_from_a_convenient_observation(self):
        request = self.request(); row = self.record()
        request["canonical"]["WDTH"] = 600.586
        row["reported_location"]["WDTH"] = 600.586
        with self.assertRaisesRegex(writer.ProbeError, "canonical_rule_changed"):
            writer.validate_echo(row, request, "requested", self.defaults, "glyph")

    def test_small_probe_covers_three_axis_endpoints_and_both_mixed_weight_targets(self):
        axes = {face: {"WDTH": (1., 500., 1000.), "wght": (100., 500., 600. if face == 20 else 900.),
                       "HGHT": (1., 500., 1000.)} for face in (20, 31)}
        requests = writer.requests_for_axes(axes)
        self.assertEqual(len(requests), 22)
        self.assertTrue(all(len(row["glyph_ids"]) == 32 for row in requests))
        for face in (20, 31):
            rows = [row for row in requests if row["face_index"] == face]
            for tag in writer.TAGS:
                self.assertIn(axes[face][tag][0], [row["requested"][tag] for row in rows])
                self.assertIn(axes[face][tag][2], [row["requested"][tag] for row in rows])
            self.assertEqual({row["requested"]["wght"] for row in rows
                              if row["requested"]["WDTH"] == 600.5859375}, {300.01, 400.01})
            for requested, canonical in ((561.7283945, 561.7283), (581.267578125, 581.2675)):
                samples = [row for row in rows if row["requested"]["WDTH"] == requested]
                self.assertEqual(len(samples), 1)
                self.assertEqual(samples[0]["canonical"]["WDTH"], canonical)
                self.assertTrue(all(samples[0]["requested"][tag] != self.defaults[tag]
                                    for tag in writer.TAGS))

    def test_changed_production_guard_cannot_be_silently_reused(self):
        source = "func makeInstance() {}\n" + writer.construction.GUARD + "\nfunc run() throws {}"
        harness = writer.make_harness(source)
        self.assertIn(writer.construction.GUARD, source)
        self.assertNotIn("try compareConstructionMain()", harness)
        self.assertIn("withExtendedLifetime(retained)", harness)
        with self.assertRaises(ValueError):
            writer.make_harness(source + writer.construction.GUARD)


if __name__ == "__main__":
    unittest.main()
