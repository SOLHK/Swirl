#!/usr/bin/env python3
"""Classify a narrowly explained default-axis omission in private A3 evidence.

This module neither constructs a font nor releases converter input. Its caller
must first verify the native process, source bytes, full table/face metadata,
transport completion and constructor-entry audit. ``submitted_*_bits`` are the
complete binary64 bit patterns observed immediately before the constructor was
called, bound by the caller to the actual request ID and face. They are not a
claim about CoreText's private internal representation.

The only new interpretation is an omitted original axis whose *predeclared*
replay coordinate equals that original axis's default. Existing readback rules
still apply to every present axis, and the replay must echo exactly and match
the entire private payload for every requested GID, including unknown fields.
Original strict failures remain alongside this diagnostic result. Neither a
positive classification nor strict replay is production/font acceptance.
"""
from __future__ import annotations

from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verified_axis_oracle import (  # noqa: E402
    ENVELOPE, VerificationError, declare_readback, effective_readback,
    finite_number, require, same_json, validate_native_record,
)


TAGS = frozenset(("WDTH", "wght", "HGHT"))
IDENTITY_FIELDS = ("face_index", "upm", "glyph_count", "axes", "verified_table_sha256")
SCHEMA = "swirl_vf_a3_default_omission_diagnostic_v1"


def _bits(value):
    return struct.pack(">d", float(value)).hex()


def _finite_json(value, depth=0):
    """Unknown payload is compared, never silently ignored or published."""
    if depth > 128:
        return False
    if value is None or type(value) in (str, bool):
        return True
    if type(value) in (int, float):
        return finite_number(value)
    if type(value) is list:
        return all(_finite_json(item, depth + 1) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _finite_json(item, depth + 1)
                   for key, item in value.items())
    return False


def _failure(error, *, phase=None, gid=None):
    # Native error text, payload field names and request IDs may contain private
    # source information. Only fixed verifier codes and public axis context leave
    # this module. All exceptions reaching this helper come from local checks.
    result = {"reason": str(error)}
    if phase is not None:
        result["phase"] = phase
    if gid is not None:
        result["glyph_id"] = gid
    context = error.context
    if context.get("axis") in TAGS:
        result["axis"] = context["axis"]
    if type(context.get("reported_axis_present")) is bool:
        result["reported_axis_present"] = context["reported_axis_present"]
    for key in ("requested_value", "reported_value", "expected_candidate_value",
                "expected_secondary_candidate_value"):
        value = context.get(key)
        if finite_number(value):
            result[key] = value
            result[key + "_hex"] = float(value).hex()
    return result


def _identity(identity, native_identity):
    require(type(identity) is dict and all(key in identity for key in IDENTITY_FIELDS),
            "source_identity_incomplete")
    require(type(identity["face_index"]) is int and identity["face_index"] >= 0
            and type(identity["upm"]) is int and 0 < identity["upm"] <= 65535
            and type(identity["glyph_count"]) is int and 0 < identity["glyph_count"] <= 65535,
            "source_face_identity_invalid")
    axes = identity["axes"]
    require(type(axes) is list and len(axes) == 3
            and all(type(axis) is dict for axis in axes), "original_three_axes_required")
    require(all(type(axis.get("tag")) is str for axis in axes)
            and {axis["tag"] for axis in axes} == TAGS, "original_three_axes_required")
    for axis in axes:
        tag = axis["tag"]
        require(type(axis.get("identifier")) is int
                and axis["identifier"] == int.from_bytes(tag.encode("ascii"), "big")
                and all(finite_number(axis.get(key)) for key in ("minimum", "default", "maximum"))
                and axis["minimum"] <= axis["default"] <= axis["maximum"]
                and axis["minimum"] < axis["maximum"]
                and type(axis.get("flags")) is int and 0 <= axis["flags"] <= 65535
                and type(axis.get("hidden")) is bool and axis["hidden"] == bool(axis["flags"] & 1),
                "original_axis_identity_invalid", axis=tag)
    tables = identity["verified_table_sha256"]
    require(type(tables) is dict and {"head", "name", "maxp", "cmap", "fvar", "avar"} <= set(tables)
            and all(type(tag) is str and len(tag) == 4 and tag.isascii()
                    and type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest)
                    for tag, digest in tables.items()), "original_table_binding_incomplete")
    # Extra native metadata (including the anchor identity) is deliberately
    # allowed. Every field of the complete expected source identity must match.
    require(type(native_identity) is dict and native_identity.get("status") == "identity_verified"
            and all(same_json(native_identity.get(key), value) for key, value in identity.items()),
            "native_face_or_original_table_identity_mismatch")


def _location(location, identity, reason):
    require(type(location) is dict and set(location) == TAGS, reason)
    require(all(finite_number(location[axis["tag"]])
                and axis["minimum"] <= location[axis["tag"]] <= axis["maximum"]
                for axis in identity["axes"]), reason)


def _batch(records, identity, location, gids, phase):
    require(type(records) is dict and all(type(gid) is int for gid in records)
            and set(records) == set(gids), "native_" + phase + "_batch_incomplete")
    first = records[gids[0]]
    require(type(first) is dict, "native_success_record_not_object")
    request_id = first.get("request_id")
    require(type(request_id) is str and bool(request_id) and len(request_id) <= 1024,
            "native_request_id_invalid")
    request = {"request_id": request_id, "face_index": identity["face_index"],
               "location": location, "glyph_ids": gids}
    seen, first_reported = set(), None
    for gid in gids:
        record = records[gid]
        actual_gid = validate_native_record(record, request, seen)
        require(actual_gid == gid, "native_record_dictionary_GID_mismatch")
        # The old finite numeric comparator regards signed zeros as equal. Raw
        # constructor input is stricter: its original binary64 bits must survive.
        require(all(_bits(record["location"][tag]) == _bits(location[tag]) for tag in TAGS),
                "native_raw_location_binary64_changed")
        reported = record.get("reported_location")
        require(type(reported) is dict and set(reported) <= TAGS
                and all(finite_number(value) for value in reported.values()),
                "native_reported_axis_set_or_number_invalid")
        require(all(axis["minimum"] <= reported[axis["tag"]] <= axis["maximum"]
                    for axis in identity["axes"] if axis["tag"] in reported),
                "native_axis_readback_out_of_range")
        if first_reported is None:
            first_reported = reported
        require(same_json(reported, first_reported), "native_inconsistent_" + phase + "_readback")
        require(_finite_json(record), "native_payload_is_not_finite_JSON")
    require(seen == set(gids), "native_" + phase + "_batch_incomplete")
    return request_id, first_reported


def _strict_audit(identity, location, canonical, declaration, original, replay, gids):
    failures, differences = [], []
    for gid in gids:
        for phase, records, requested in (("original", original, location), ("replay", replay, canonical)):
            try:
                effective_readback(records[gid], identity, requested,
                                   replay=phase == "replay", declaration=declaration)
            except VerificationError as error:
                failures.append(_failure(error, phase=phase, gid=gid))
        left = {key: value for key, value in original[gid].items() if key not in ENVELOPE}
        right = {key: value for key, value in replay[gid].items() if key not in ENVELOPE}
        if not same_json(left, right):
            differences.append({"glyph_id": gid, "reason": "native_replay_payload_not_exact",
                                "payload_field_set_equal": left.keys() == right.keys()})
    return {"status": "FAILED_FINITE_REPLAY" if failures or differences else "PASS_FINITE_REPLAY",
            "readback_failures": failures, "payload_differences": differences,
            "all_payloads_exactly_equal": not differences, "requested_GID_count": len(gids)}


def _submission(bits, expected, phase):
    require(type(bits) is dict and set(bits) == TAGS,
            "constructor_entry_" + phase + "_audit_incomplete")
    for tag in TAGS:
        value = bits[tag]
        require(type(value) is str and re.fullmatch(r"[0-9a-fA-F]{16}", value),
                "constructor_entry_" + phase + "_bits_invalid", axis=tag)
        require(value.lower() == _bits(expected[tag]),
                "constructor_entry_" + phase + "_binary64_changed", axis=tag)


def classify_default_omission(identity, location, original, replay, *, requested_gids,
                              native_identity, submitted_original_bits, submitted_replay_bits,
                              declaration=None):
    """Return a safe finite-batch classification; expected failures never abort.

    ``original`` and ``replay`` are complete GID-to-raw-record dictionaries from
    independently constructed instances. The caller freezes ``declare_readback``
    before native calls. If supplied, that declaration must equal the same fixed
    plan recomputed here; this function never selects a plan from native output.
    Constructor audit IDs/counts/face binding and source/process verification are
    caller preconditions. The only public output is safe diagnostic metadata;
    raw native records are neither modified nor included in the returned value.
    """
    result = {"schema": SCHEMA, "classification": "REJECTED", "reason": None,
              "diagnostic_passed": False, "default_omission_equivalent": False,
              "strict_replay_passed": False, "scope": "one_complete_observed_batch_only",
              "submission_evidence_site": "constructor_entry",
              "constructor_entry_binary64_unchanged": False,
              "native_execution_performed_by_classifier": False,
              "source_user_mapping_inferred": False, "native_values_modified": False,
              "mapping_accepted": False, "production_mapping_accepted": False,
              "production_accepted": False, "font_accepted": False,
              "continuous_space_accepted": False, "explained_omitted_axes": [],
              "failures": [], "legacy_strict_replay": {
                  "status": "NOT_EVALUATED_INVALID_EVIDENCE", "readback_failures": [],
                  "payload_differences": [], "all_payloads_exactly_equal": False}}
    try:
        _identity(identity, native_identity)
        _location(location, identity, "original_location_invalid")
        require(type(requested_gids) in (list, tuple) and 0 < len(requested_gids) <= 4096
                and all(type(gid) is int and 0 <= gid < identity["glyph_count"] for gid in requested_gids)
                and len(set(requested_gids)) == len(requested_gids), "invalid_or_duplicate_request_GIDs")
        gids = list(requested_gids)
        fixed = declare_readback(location)
        require(declaration is None or same_json(declaration, fixed), "predeclared_replay_plan_changed")
        canonical = {tag: fixed[tag]["canonical"] for tag in location}
        _location(canonical, identity, "predeclared_axis_candidate_outside_source_range")
        original_id, original_reported = _batch(original, identity, location, gids, "original")
        replay_id, replay_reported = _batch(replay, identity, canonical, gids, "replay")
        result["legacy_strict_replay"] = _strict_audit(
            identity, location, canonical, fixed, original, replay, gids)
        result["strict_replay_passed"] = result["legacy_strict_replay"]["status"] == "PASS_FINITE_REPLAY"
        result.update(face_index=identity["face_index"], requested_GID_count=len(gids),
                      requested_location=dict(location), predeclared_replay_location=canonical,
                      requested_binary64_bits={tag: _bits(value) for tag, value in location.items()},
                      original_reported_location=dict(original_reported),
                      replay_reported_location=dict(replay_reported))
        require(original_id != replay_id, "original_and_replay_request_identity_reused")
        _submission(submitted_original_bits, location, "original")
        _submission(submitted_replay_bits, canonical, "replay")
        result["constructor_entry_binary64_unchanged"] = True
        omitted = [axis["tag"] for axis in identity["axes"]
                   if axis["tag"] not in original_reported and location[axis["tag"]] != axis["default"]]
        defaults = {axis["tag"]: axis["default"] for axis in identity["axes"]}
        for tag in omitted:
            require(canonical[tag] == defaults[tag],
                    "omitted_nondefault_axis_has_nondefault_predeclared_replay", axis=tag)
        result["explained_omitted_axes"] = omitted
        # Check all axes again after filling only justified omissions in a local
        # dictionary. The old verifier stops at its first failure; checking only
        # that failure would allow a second invalid present axis to escape.
        for gid in gids:
            completed = dict(original[gid]["reported_location"])
            for tag in omitted:
                completed[tag] = defaults[tag]
            try:
                effective_readback({"reported_location": completed}, identity, location, declaration=fixed)
            except VerificationError as error:
                result["failures"].append(_failure(error, phase="original", gid=gid))
            try:
                effective_readback(replay[gid], identity, canonical, replay=True)
            except VerificationError as error:
                result["failures"].append(_failure(error, phase="replay", gid=gid))
        result["failures"].extend(result["legacy_strict_replay"]["payload_differences"])
        if result["failures"]:
            result["reason"] = result["failures"][0]["reason"]
            return result
        if omitted:
            require(not result["strict_replay_passed"], "expected_original_strict_omission_failure_missing")
            result.update(classification="DEFAULT_OMISSION_EQUIVALENT_FOR_THIS_BATCH",
                          default_omission_equivalent=True, diagnostic_passed=True,
                          reason="predeclared_default_omission_and_exact_complete_replay")
        else:
            require(result["strict_replay_passed"], "unexplained_legacy_strict_replay_failure")
            result.update(classification="STRICT_REPLAY_ALREADY_PASSED", diagnostic_passed=True,
                          reason="no_new_default_omission_interpretation_needed")
    except VerificationError as error:
        failure = _failure(error)
        result["failures"].append(failure)
        result["reason"] = failure["reason"]
    return result
