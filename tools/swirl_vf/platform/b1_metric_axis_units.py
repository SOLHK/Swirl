#!/usr/bin/env python3
"""Separate HGHT user-unit control; preserve normalized design and all deltas.

Patch only the three HGHT Fixed16.16 fvar fields in the original SFNT bytes.
Do not reserialize the font. Other table payloads are byte-identical, with only
head.checkSumAdjustment allowed to change when recomputing the whole-font sum.
Original files and the supplied frozen manifest are retained unmodified.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import hashlib
from pathlib import Path
import struct

from b1_metric_fixture import exact, rational


CHECKSUM_MAGIC = 0xB1B0AFBA


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checksum(data: bytes) -> int:
    padded = data + bytes((-len(data)) % 4)
    return sum(item[0] for item in struct.iter_unpack(">I", padded)) & 0xFFFFFFFF


def table_directory(data: bytes) -> dict:
    require(len(data) >= 12 and data[:4] == b"\x00\x01\x00\x00", "single_face_true_type_sfnt_required")
    count = struct.unpack_from(">H", data, 4)[0]
    end = 12 + 16*count
    require(count > 0 and end <= len(data), "invalid_sfnt_directory")
    tables = {}
    for index in range(count):
        start = 12 + 16*index
        tag = data[start:start+4].decode("ascii")
        stored_sum, offset, length = struct.unpack_from(">III", data, start+4)
        require(tag not in tables and offset >= end and offset + length <= len(data), "invalid_sfnt_table_range")
        tables[tag] = {"directory_offset": start, "offset": offset, "length": length, "checksum": stored_sum}
    require("head" in tables and "fvar" in tables, "head_and_fvar_required")
    require(tables["head"]["length"] >= 54, "truncated_head")
    return tables


def table_payloads(data: bytes) -> dict[str, bytes]:
    return {tag: data[item["offset"]:item["offset"]+item["length"]]
            for tag, item in table_directory(data).items()}


def table_hashes(data: bytes) -> dict[str, str]:
    return {tag: hashlib.sha256(payload).hexdigest() for tag, payload in table_payloads(data).items()}


def _height_axis_offsets(data: bytes, directory: dict) -> tuple[int, tuple[int, int, int]]:
    fvar = directory["fvar"]
    start, length = fvar["offset"], fvar["length"]
    require(length >= 16, "truncated_fvar_header")
    axis_start, _, axis_count, axis_size = struct.unpack_from(">HHHH", data, start+4)
    require(axis_start >= 16 and axis_size >= 20 and axis_count > 0
            and axis_start + axis_count*axis_size <= length, "invalid_fvar_axis_range")
    matches = [start+axis_start+i*axis_size for i in range(axis_count)
               if data[start+axis_start+i*axis_size:start+axis_start+i*axis_size+4] == b"HGHT"]
    require(len(matches) == 1, "exactly_one_HGHT_axis_required")
    offset = matches[0]
    values = struct.unpack_from(">iii", data, offset+4)
    require(values[0] < values[1] < values[2], "nondegenerate_HGHT_axis_required")
    return offset, values


def patch_height_axis(data: bytes, scale: int = 16384) -> tuple[bytes, dict]:
    require(type(scale) is int and scale > 0, "positive_integer_axis_scale_required")
    directory = table_directory(data)
    require(checksum(data) == CHECKSUM_MAGIC, "source_sfnt_checksum_invalid")
    axis_offset, original_fixed = _height_axis_offsets(data, directory)
    scaled_fixed = tuple(value*scale for value in original_fixed)
    require(all(-(1 << 31) <= value < (1 << 31) for value in scaled_fixed), "scaled_HGHT_outside_signed_16_16")
    result = bytearray(data)
    struct.pack_into(">iii", result, axis_offset+4, *scaled_fixed)
    head = directory["head"]
    result[head["offset"]+8:head["offset"]+12] = bytes(4)
    # The head directory checksum is defined with checkSumAdjustment zero.
    for tag in ("fvar", "head"):
        item = directory[tag]
        payload = bytes(result[item["offset"]:item["offset"]+item["length"]])
        struct.pack_into(">I", result, item["directory_offset"]+4, checksum(payload))
    adjustment = (CHECKSUM_MAGIC - checksum(bytes(result))) & 0xFFFFFFFF
    struct.pack_into(">I", result, head["offset"]+8, adjustment)
    result = bytes(result)
    require(checksum(result) == CHECKSUM_MAGIC, "patched_sfnt_checksum_invalid")
    before, after = table_payloads(data), table_payloads(result)
    require(before.keys() == after.keys(), "reparameterization_changed_table_set")
    for tag in before:
        left, right = before[tag], after[tag]
        if tag == "fvar":
            local_offset = axis_offset-directory["fvar"]["offset"]+4
            left = left[:local_offset] + bytes(12) + left[local_offset+12:]
            right = right[:local_offset] + bytes(12) + right[local_offset+12:]
        elif tag == "head":
            left, right = left[:8]+bytes(4)+left[12:], right[:8]+bytes(4)+right[12:]
        require(left == right, "reparameterization_changed_unrelated_table_payload:"+tag)
    metadata = {
        "axis": "HGHT", "scale_integer": scale,
        "before_fixed16_16_integers": list(original_fixed),
        "after_fixed16_16_integers": list(scaled_fixed),
        "before_user_min_default_max": [rational(Fraction(value, 65536)) for value in original_fixed],
        "after_user_min_default_max": [rational(Fraction(value, 65536)) for value in scaled_fixed],
        "changed_table_payloads": sorted(tag for tag in before if before[tag] != after[tag]),
        "unchanged_non_fvar_payload_rule": "All identical; only head.checkSumAdjustment bytes 8:12 may differ.",
        "sfnt_checksum_before": checksum(data), "sfnt_checksum_after": checksum(result),
        "native_scale_basis": {"HGHT": rational(Fraction(1, scale))},
        "mapping_rule": "normalized_HGHT = native_HGHT / scale; no measured value or prediction is replaced.",
        "raw_patch_without_font_reserialization": True,
    }
    return result, metadata


def reparameterize_height_axis(manifest: dict, fixtures_dir: Path, scale: int = 16384) -> dict:
    """Return a new manifest and write new siblings; do not change the inputs."""
    require(type(scale) is int and scale > 0, "positive_integer_axis_scale_required")
    require("axis_user_unit_control" not in manifest, "manifest_already_reparameterized")
    fixtures_dir = Path(fixtures_dir).resolve()
    result = deepcopy(manifest)
    pending = []
    seen_outputs = set()
    for entry in result["entries"]:
        source_path = (fixtures_dir / entry["path"]).resolve()
        require(source_path.is_relative_to(fixtures_dir), "fixture_path_outside_directory")
        output_path = source_path.with_name(source_path.stem + f"-hght-user{scale}" + source_path.suffix)
        require(output_path not in seen_outputs and not output_path.exists(), "new_axis_unit_fixture_path_required")
        seen_outputs.add(output_path)
        original = source_path.read_bytes()
        original_hash = hashlib.sha256(original).hexdigest()
        require(original_hash == entry["sha256"] and table_hashes(original) == entry["table_sha256"],
                "frozen_source_fixture_identity_mismatch")
        patched, basis = patch_height_axis(original, scale)
        basis.update({"before_path": entry["path"], "after_path": str(output_path.relative_to(fixtures_dir)),
                      "before_sha256": original_hash, "after_sha256": hashlib.sha256(patched).hexdigest(),
                      "before_table_sha256": deepcopy(entry["table_sha256"]), "after_table_sha256": table_hashes(patched)})
        entry["path"], entry["sha256"] = basis["after_path"], basis["after_sha256"]
        entry["table_sha256"] = deepcopy(basis["after_table_sha256"])
        entry["native_axis_unit_reparameterization"] = basis
        for request in entry["requests"]:
            normalized = deepcopy(request["axes"])
            require("HGHT" in normalized, "normalized_HGHT_request_required")
            native = deepcopy(normalized)
            native_exact = exact(normalized["HGHT"]) * scale
            native["HGHT"] = float(native_exact)
            require(Fraction(native["HGHT"]) == native_exact, "native_user_axis_conversion_lost_precision")
            request["normalized_design_axes"] = normalized
            request["native_user_axes"] = native
            request["native_scale_basis"] = deepcopy(basis["native_scale_basis"])
        pending.append((output_path, patched))
    # Preflight every fixture and request before making any new font available.
    for path, data in pending:
        path.write_bytes(data)
    result["axis_user_unit_control"] = {
        "axis": "HGHT", "scale_integer": scale,
        "normalized_units_per_native_unit": rational(Fraction(1, scale)),
        "status": "STRICT_NATIVE_READBACK_REQUIRED_NO_COORDINATE_ACCEPTANCE_CHANGE",
        "original_manifest_and_font_files_unchanged": True,
        "normalized_design_axes_and_all_frozen_predictions_unchanged": True,
        "native_acceptance": "NOT_RUN",
    }
    return result


def wire_requests(entry: dict) -> list[dict]:
    """Only native user coordinates go to Swift; normalized design stays saved."""
    return [{"id": request["id"], "axes": deepcopy(request.get("native_user_axes", request["axes"])),
             "point_size": request["point_size"]} for request in entry["requests"]]
