"""Authored protocol regressions, not CoreText execution or font acceptance.

These small invented raw records exercise the diagnostic gate. No Apple source
font, extracted contour or measured source metric is included in this fixture.
"""
import copy
import json
import math
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from axis_a3_default_omission import classify_default_omission
from verified_axis_oracle import declare_readback


def bits(location):
    return {tag: struct.pack(">d", float(value)).hex() for tag, value in location.items()}


def authored_identity():
    axes = [{"tag": tag, "identifier": int.from_bytes(tag.encode("ascii"), "big"),
             "minimum": 1., "default": default, "maximum": 1000.,
             "flags": hidden, "hidden": bool(hidden)}
            for tag, default, hidden in (("WDTH", 500., 1), ("wght", 499., 0), ("HGHT", 500., 1))]
    return {"face_index": 15, "upm": 1000, "glyph_count": 20000, "axes": axes,
            "verified_table_sha256": {tag: str(index) * 64 for index, tag in
                                      enumerate(("head", "name", "maxp", "cmap", "fvar", "avar", "test"))}}


def authored_record(identity, location, reported, gid, request_id):
    return {"request_id": request_id, "face_index": identity["face_index"], "glyph_id": gid,
            "location": copy.deepcopy(location), "reported_location": copy.deepcopy(reported),
            "commands": [["moveTo", 1., 2.], ["lineTo", 3., 4.], ["closePath"]],
            "bounds": [1., 2., 2., 2.], "path_status": "path",
            "advance_width": 400. + gid, "advance_height": 900., "lsb": 1.,
            "horizontal_origin_x": 0., "horizontal_origin_y": 0.,
            "vertical_origin_x": 201., "vertical_origin_y": 800.,
            "horizontal_advance_sum": 400. + gid, "vertical_advance_sum": 900.,
            "horizontal_advance_vector": [400. + gid, 0.], "vertical_advance_vector": [900., 0.],
            "vertical_origin_translation": [-201., -800.], "lsb_derivation": "authored_fixture",
            "vertical_origin_derivation": "authored_fixture", "error": None,
            "authored_private_extension": {"marker": [True, None, "invented", 1.25]}}


def evidence(location=None):
    identity = authored_identity()
    location = {"WDTH": 500.00005, "wght": 499.25, "HGHT": 500.} if location is None else location
    declaration = declare_readback(location)
    canonical = {tag: plan["canonical"] for tag, plan in declaration.items()}
    defaults = {axis["tag"]: axis["default"] for axis in identity["axes"]}
    reported = {tag: value for tag, value in canonical.items() if value != defaults[tag]}
    gids = [0, 5, 19177]
    return {"identity": identity, "location": copy.deepcopy(location), "requested_gids": gids,
            "native_identity": {**copy.deepcopy(identity), "status": "identity_verified",
                                "anchor_metadata": {"authored_extra": True}},
            "original": {gid: authored_record(identity, location, reported, gid, "original-1") for gid in gids},
            "replay": {gid: authored_record(identity, canonical, reported, gid, "replay-2") for gid in gids},
            "declaration": declaration, "submitted_original_bits": bits(location),
            "submitted_replay_bits": bits(canonical)}


class DefaultOmissionTests(unittest.TestCase):
    def classify(self, item):
        result = classify_default_omission(**item)
        # Every outcome must remain safe JSON with no accidental promotion.
        json.dumps(result, allow_nan=False)
        for flag in ("mapping_accepted", "production_mapping_accepted", "production_accepted",
                     "font_accepted", "continuous_space_accepted", "source_user_mapping_inferred",
                     "native_values_modified", "native_execution_performed_by_classifier"):
            self.assertIs(result[flag], False, flag)
        return result

    def reject(self, item, reason=None):
        result = self.classify(item)
        self.assertEqual(result["classification"], "REJECTED")
        self.assertIs(result["diagnostic_passed"], False)
        self.assertIs(result["default_omission_equivalent"], False)
        self.assertTrue(result["failures"])
        if reason is not None:
            self.assertEqual(result["reason"], reason)
        return result

    def test_predeclared_default_omission_is_only_diagnostic_and_original_failure_survives(self):
        for value in (math.nextafter(500., math.inf), 500.00005, 500.0000999999999):
            with self.subTest(value=value):
                item = evidence({"WDTH": value, "wght": 499.25, "HGHT": 500.})
                before = copy.deepcopy(item)
                result = self.classify(item)
                self.assertEqual(item, before)
                self.assertEqual(result["classification"], "DEFAULT_OMISSION_EQUIVALENT_FOR_THIS_BATCH")
                self.assertTrue(result["default_omission_equivalent"])
                self.assertTrue(result["constructor_entry_binary64_unchanged"])
                self.assertEqual(result["submission_evidence_site"], "constructor_entry")
                self.assertEqual(result["explained_omitted_axes"], ["WDTH"])
                self.assertEqual(result["predeclared_replay_location"]["WDTH"], 500.)
                self.assertEqual(result["requested_binary64_bits"], bits(item["location"]))
                legacy = result["legacy_strict_replay"]
                self.assertEqual(legacy["status"], "FAILED_FINITE_REPLAY")
                self.assertEqual(len(legacy["readback_failures"]), len(item["requested_gids"]))
                self.assertTrue(all(error["reason"] == "native_nondefault_axis_not_reported"
                                    and error["axis"] == "WDTH" for error in legacy["readback_failures"]))
                self.assertTrue(legacy["all_payloads_exactly_equal"])

    def test_all_three_omissions_and_an_already_strict_pass_remain_distinct(self):
        item = evidence({"WDTH": 500.00005, "wght": 499.00005, "HGHT": 500.00005})
        result = self.classify(item)
        self.assertTrue(result["default_omission_equivalent"])
        self.assertEqual(result["explained_omitted_axes"], ["WDTH", "wght", "HGHT"])
        for location in ({"WDTH": 500., "wght": 499., "HGHT": 500.},
                         {"WDTH": 501., "wght": 499.25, "HGHT": 600.125}):
            item = evidence(location)
            result = self.classify(item)
            self.assertEqual(result["classification"], "STRICT_REPLAY_ALREADY_PASSED")
            self.assertTrue(result["strict_replay_passed"])
            self.assertFalse(result["default_omission_equivalent"])
        item = evidence()
        for record in item["original"].values():
            record["reported_location"]["WDTH"] = 500.
        self.assertEqual(self.classify(item)["classification"], "STRICT_REPLAY_ALREADY_PASSED")

    def test_missing_real_nondefault_and_existing_collision_cannot_be_hidden_by_same_payload(self):
        for value in (499.006199, 499.006201, 550., math.nextafter(499., -math.inf)):
            item = evidence({"WDTH": 500., "wght": value, "HGHT": 500.})
            for phase in ("original", "replay"):
                for record in item[phase].values():
                    record["reported_location"] = {}
            result = self.reject(item, "omitted_nondefault_axis_has_nondefault_predeclared_replay")
            self.assertTrue(result["legacy_strict_replay"]["all_payloads_exactly_equal"])
            self.assertEqual(result["legacy_strict_replay"]["status"], "FAILED_FINITE_REPLAY")

    def test_explained_first_omission_cannot_mask_wrong_present_axis(self):
        item = evidence()
        for record in item["original"].values():
            record["reported_location"]["wght"] = 499.5
        result = self.reject(item, "native_readback_not_named_decimal4_candidate")
        self.assertEqual({failure["axis"] for failure in result["legacy_strict_replay"]["readback_failures"]},
                         {"WDTH"})
        self.assertEqual({failure["axis"] for failure in result["failures"]}, {"wght"})

    def test_actual_constructor_entry_bits_reject_loss_and_incomplete_audit(self):
        item = evidence({"WDTH": math.nextafter(500., math.inf), "wght": 499.25, "HGHT": 500.})
        rounded = struct.unpack(">f", struct.pack(">f", item["location"]["WDTH"]))[0]
        self.assertEqual(rounded, 500.)
        item["submitted_original_bits"]["WDTH"] = bits({"WDTH": rounded})["WDTH"]
        result = self.reject(item, "constructor_entry_original_binary64_changed")
        self.assertEqual(result["legacy_strict_replay"]["status"], "FAILED_FINITE_REPLAY")
        for phase in ("original", "replay"):
            key = "submitted_" + phase + "_bits"
            item = evidence(); del item[key]["HGHT"]
            self.reject(item, "constructor_entry_" + phase + "_audit_incomplete")
            for invalid in (True, 1, "nan", "0" * 17):
                item = evidence(); item[key]["HGHT"] = invalid
                self.reject(item, "constructor_entry_" + phase + "_bits_invalid")
            item = evidence(); item[key]["HGHT"] = bits({"HGHT": math.nextafter(500., math.inf)})["HGHT"]
            self.reject(item, "constructor_entry_" + phase + "_binary64_changed")

    def test_complete_face_tables_and_ordered_axes_are_required_but_native_extras_are_allowed(self):
        self.assertTrue(self.classify(evidence())["diagnostic_passed"])
        for field, value in (("face_index", 18), ("upm", 2048), ("glyph_count", 19999),
                             ("status", "unverified")):
            item = evidence(); item["native_identity"][field] = value
            self.reject(item, "native_face_or_original_table_identity_mismatch")
        for mutation in ("default", "order", "flags", "table", "missing_table", "extra_table"):
            item = evidence(); native = item["native_identity"]
            if mutation == "default": native["axes"][0]["default"] += 1
            if mutation == "order": native["axes"].reverse()
            if mutation == "flags": native["axes"][0]["hidden"] = False
            if mutation == "table": native["verified_table_sha256"]["test"] = "f" * 64
            if mutation == "missing_table": del native["verified_table_sha256"]["avar"]
            if mutation == "extra_table": native["verified_table_sha256"]["new!"] = "f" * 64
            self.reject(item, "native_face_or_original_table_identity_mismatch")

    def test_complete_gid_set_request_identity_and_raw_location_are_mandatory(self):
        item = evidence()
        for phase in ("original", "replay"):
            del item[phase][19177]
        self.reject(item, "native_original_batch_incomplete")
        for invalid in ([], [0, 0], [0, True], [0, 20000]):
            item = evidence(); item["requested_gids"] = invalid
            self.reject(item, "invalid_or_duplicate_request_GIDs")
        for phase in ("original", "replay"):
            for key, value in (("face_index", 20), ("face_index", True), ("request_id", "wrong-request"),
                               ("glyph_id", 5), ("location", {"WDTH": 500., "wght": 499., "HGHT": 500.})):
                item = evidence(); item[phase][19177][key] = value
                self.reject(item)
            item = evidence(); item[phase][19177]["reported_location"]["wght"] = 499.5
            self.reject(item, "native_inconsistent_" + phase + "_readback")
        item = evidence()
        for record in item["replay"].values(): record["request_id"] = "original-1"
        self.reject(item, "original_and_replay_request_identity_reused")

    def test_canonical_replay_must_be_exact_and_report_every_nondefault(self):
        item = evidence()
        for record in item["replay"].values():
            record["reported_location"]["HGHT"] = math.nextafter(500., math.inf)
        self.reject(item, "native_readback_replay_not_exactly_stable")
        item = evidence()
        for record in item["replay"].values(): del record["reported_location"]["wght"]
        self.reject(item, "native_nondefault_axis_not_reported")

    def test_every_glyph_and_unknown_payload_must_match_with_no_metric_tolerance(self):
        for mutation in ("unknown_changed", "unknown_added", "unknown_removed", "tiny_metric", "command"):
            item = evidence(); record = item["replay"][19177]
            if mutation == "unknown_changed": record["authored_private_extension"]["marker"][0] = False
            if mutation == "unknown_added": record["DO_NOT_PUBLISH_UNKNOWN_FIELD"] = {"secret": "sentinel"}
            if mutation == "unknown_removed": del record["authored_private_extension"]
            if mutation == "tiny_metric": record["advance_width"] += 2 ** -30
            if mutation == "command": record["commands"][0][1] = math.nextafter(1., math.inf)
            result = self.reject(item, "native_replay_payload_not_exact")
            self.assertEqual([failure["glyph_id"] for failure in result["failures"]], [19177])
            public = json.dumps(result)
            for private in ("DO_NOT_PUBLISH_UNKNOWN_FIELD", "authored_private_extension", "commands", "advance_width"):
                self.assertNotIn(private, public)

    def test_nan_bool_and_malformed_unknown_payload_fail_without_private_error_text(self):
        for value in (float("nan"), float("inf"), True, "500"):
            item = evidence(); item["location"]["WDTH"] = value
            self.reject(item, "original_location_invalid")
            item = evidence(); item["original"][0]["advance_width"] = value
            self.reject(item, "native_scalar_missing_or_nonfinite")
            item = evidence(); item["original"][0]["reported_location"]["wght"] = value
            self.reject(item, "native_reported_axis_set_or_number_invalid")
        item = evidence(); item["replay"][0]["PRIVATE_NAN_KEY"] = {"nested": [float("nan")]}
        result = self.reject(item, "native_payload_is_not_finite_JSON")
        self.assertNotIn("PRIVATE_NAN_KEY", json.dumps(result))
        item = evidence(); item["original"][0]["error"] = "PRIVATE_NATIVE_ERROR_AND_OUTLINE_SENTINEL"
        result = self.reject(item, "upstream_native_request_failed")
        self.assertNotIn("PRIVATE_NATIVE_ERROR_AND_OUTLINE_SENTINEL", json.dumps(result))
        item = evidence(); item["replay"][0]["commands"] = [["lineTo", True, 4.]]
        self.reject(item, "native_command_type_arity_or_number_invalid")

    def test_declared_plan_cannot_be_changed_to_fit_observations(self):
        item = evidence({"WDTH": 500., "wght": 499.006201, "HGHT": 500.})
        item["declaration"]["wght"]["canonical"] = 499.
        self.reject(item, "predeclared_replay_plan_changed")
        item = evidence(); item["declaration"]["WDTH"]["once"] += 1
        self.reject(item, "predeclared_replay_plan_changed")
        item = evidence(); item["declaration"] = None
        self.assertTrue(self.classify(item)["default_omission_equivalent"])

    def test_signed_zero_input_change_is_rejected_even_when_old_numeric_equality_would_pass(self):
        item = evidence({"WDTH": -0., "wght": 499.25, "HGHT": 500.})
        for identity in (item["identity"], item["native_identity"]):
            identity["axes"][0].update(minimum=0., default=0.)
        for phase in ("original", "replay"):
            for record in item[phase].values(): record["reported_location"].pop("WDTH", None)
        self.assertTrue(self.classify(item)["strict_replay_passed"])
        item["original"][0]["location"]["WDTH"] = 0.
        self.reject(item, "native_raw_location_binary64_changed")


if __name__ == "__main__":
    unittest.main()
