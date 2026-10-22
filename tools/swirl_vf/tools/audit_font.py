#!/usr/bin/env python3
"""Read-only TTC/OTF audit. Does not export outlines or rewrite the input font.

Usage: python tools/audit_font.py /path/PingFangUI.ttc --output audit/original

The raw avar records are deliberately retained: converting them straight to a
dict, as fontTools does, loses duplicate coordinates used in some Apple fonts.
Reports distinguish byte integrity, parser support, and OpenType conformance.
No successful audit result implies CoreText, DirectWrite, or Qt rendering works.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import itertools
import json
import logging
import math
import platform
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import fontTools
from fontTools.ttLib import TTCollection, TTFont, getTableClass
from fontTools.ttLib.sfnt import calcChecksum
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.varLib.varStore import VarStoreInstancer


REQUESTED_TABLES = (
    "hvgl", "hvpm", "glyf", "loca", "gvar", "CFF ", "CFF2", "fvar", "avar",
    "STAT", "name", "cmap", "GSUB", "GPOS", "GDEF", "HVAR", "VVAR", "MVAR",
    "hmtx", "vmtx", "hhea", "vhea", "head", "OS/2", "maxp", "post", "BASE",
    "VORG", "trak", "kern", "morx", "mort", "kerx", "feat", "ankr", "opbd",
    "bsln", "just", "prop", "cidg", "meta", "cvt ", "fpgm", "prep", "gasp",
)
SOURCES = {
    "hvgl": "https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvgl.html",
    "hvpm": "https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6hvpm.html",
    "avar": "https://learn.microsoft.com/en-us/typography/opentype/spec/avar",
    "fonttools": "https://fonttools.readthedocs.io/en/latest/ttLib/index.html",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, headings, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headings)
        writer.writerows(rows)


def object_json(value, depth=0):
    """Serialize small decoded table objects, never binary outline contents."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return {"byte_length": len(value), "sha256": digest(value)}
    if isinstance(value, (tuple, list)):
        return [object_json(v, depth + 1) for v in value]
    if isinstance(value, dict):
        return {str(k): object_json(v, depth + 1) for k, v in value.items()}
    if depth > 20:
        return {"unexpanded_type": type(value).__name__}
    if hasattr(value, "ensureDecompiled"):
        value.ensureDecompiled(recurse=True)
    if hasattr(value, "__dict__"):
        return {
            key: object_json(val, depth + 1)
            for key, val in vars(value).items()
            if not key.startswith("_") and key not in {"reader", "font", "getGlyphName"}
            and not callable(val)
        }
    return {"unexpanded_type": type(value).__name__}


def name_text(font, name_id):
    record = font["name"].getName(name_id, 3, 1, 0x409)
    if record is None:
        record = font["name"].getName(name_id, 1, 0, 0)
    return record.toUnicode() if record is not None else font["name"].getDebugName(name_id)


def raw_avar(data: bytes, axes: list[str]) -> dict:
    """Parse raw records losslessly, report violations without repairing them."""
    if len(data) < 8:
        raise ValueError("avar header truncated")
    major, minor, reserved, count = struct.unpack_from(">4H", data)
    result = {"major": major, "minor": minor, "reserved": reserved,
              "axis_count": count, "axes": [], "violations": []}
    if count != len(axes):
        result["violations"].append("axis_count_does_not_match_fvar")
    if reserved:
        result["violations"].append("reserved_field_nonzero")
    cursor = 8
    for axis_index in range(count):
        if cursor + 2 > len(data):
            raise ValueError("avar map count truncated")
        size = struct.unpack_from(">H", data, cursor)[0]
        cursor += 2
        if cursor + 4 * size > len(data):
            raise ValueError("avar records truncated")
        records = []
        violations = []
        for record_index in range(size):
            source, target = struct.unpack_from(">hh", data, cursor)
            cursor += 4
            records.append({"index": record_index, "from_f2dot14": source,
                            "to_f2dot14": target, "from": source / 16384,
                            "to": target / 16384})
        if records:
            for anchor in [-16384, 0, 16384]:
                if not any(r["from_f2dot14"] == r["to_f2dot14"] == anchor for r in records):
                    violations.append({"kind": "missing_required_anchor", "coordinate": anchor / 16384})
        seen = {}
        for index, record in enumerate(records):
            source, target = record["from_f2dot14"], record["to_f2dot14"]
            if source in seen:
                violations.append({"kind": "duplicate_from_coordinate", "index": index,
                                   "previous_index": seen[source], "coordinate": source / 16384})
            seen[source] = index
            if not (-16384 <= source <= 16384 and -16384 <= target <= 16384):
                violations.append({"kind": "coordinate_out_of_normalized_range", "index": index})
            if index:
                previous = records[index - 1]
                if source < previous["from_f2dot14"]:
                    violations.append({"kind": "from_coordinates_out_of_order", "index": index})
                if target < previous["to_f2dot14"]:
                    violations.append({"kind": "to_coordinate_retrograde", "index": index})
        result["axes"].append({"axis_index": axis_index,
                               "tag": axes[axis_index] if axis_index < len(axes) else None,
                               "raw_record_count": size, "records": records,
                               "violations": violations})
    result["trailing_bytes"] = len(data) - cursor
    result["standard_record_conformance_pass"] = not result["violations"] and not any(
        item["violations"] for item in result["axes"])
    result["semantic_note"] = (
        "Raw record order and duplicates preserved. Dict-collapsed maps are diagnostic only; "
        "the CoreText normalization behavior is not established by this parser."
    )
    return result


def inspect_hvgl(data: bytes, table_offset: int) -> dict:
    """Validate public header/index/part-header fields, without evaluating outlines."""
    if len(data) < 24:
        raise ValueError("hvgl header truncated")
    major, minor, flags, part_count, index_offset, glyph_count, unused = struct.unpack_from("<HH5I", data)
    result = {"version_major": major, "version_minor": minor, "format_flags": flags,
              "part_count": part_count, "part_index_offset": index_offset,
              "externally_visible_glyph_count": glyph_count, "unused": unused,
              "table_float64_aligned_in_file": table_offset % 8 == 0,
              "violations": [], "validation_scope": "header_index_and_part_headers_only"}
    errors = result["violations"]
    if (major, minor) != (3, 1):
        errors.append({"kind": "public_spec_version_not_3_1"})
        return result
    if flags or unused:
        errors.append({"kind": "nonzero_header_flags_or_unused"})
    if glyph_count > part_count:
        errors.append({"kind": "glyph_count_exceeds_part_count"})
    index_end = index_offset + 4 * (part_count + 1)
    if index_offset < 24 or index_end > len(data):
        errors.append({"kind": "part_index_out_of_bounds"})
        return result
    offsets = struct.unpack_from(f"<{part_count + 1}I", data, index_offset)
    if offsets[0] < 4 * (part_count + 1):
        errors.append({"kind": "first_part_overlaps_index"})
    if offsets[-1] + index_offset > len(data):
        errors.append({"kind": "part_sentinel_out_of_bounds"})
    types = collections.Counter()
    axes = collections.Counter()
    visible_types = collections.Counter()
    visible_axes = collections.Counter()
    visible_composites = []
    references = 0
    max_subparts = 0
    max_tree_parts = 0
    max_tree_axes = 0
    rotations = collections.Counter()
    translations = collections.Counter()
    for part in range(part_count):
        begin, end = index_offset + offsets[part], index_offset + offsets[part + 1]
        if end < begin or begin < index_end or end > len(data) or end - begin < 8:
            errors.append({"kind": "invalid_part_bounds", "part_id": part, "begin": begin, "end": end})
            continue
        flags, axis_count = struct.unpack_from("<2H", data, begin)
        shape = flags & 1 == 0
        kind = "shape" if shape else "composite"
        types[kind] += 1
        axes[axis_count] += 1
        if part < glyph_count:
            visible_types[kind] += 1
            visible_axes[axis_count] += 1
        if flags & ~1:
            errors.append({"kind": "unknown_part_flag_bits", "part_id": part, "flags": flags})
        required_alignment = 8 if shape else 4
        if begin % required_alignment:
            errors.append({"kind": "part_alignment", "part_id": part, "required": required_alignment})
        if shape:
            path_count, segment_count = struct.unpack_from("<2H", data, begin + 4)
            path_end = begin + 8 + path_count * 2
            if path_end + segment_count > end:
                errors.append({"kind": "shape_path_metadata_out_of_bounds", "part_id": part})
                continue
            path_sizes = struct.unpack_from(f"<{path_count}H", data, begin + 8)
            if sum(path_sizes) != segment_count:
                errors.append({"kind": "shape_path_segment_count_mismatch", "part_id": part})
            vector_begin = (path_end + segment_count + 7) & ~7
            vector_end = vector_begin + 8 * 4 * segment_count * (1 + 2 * axis_count)
            if vector_end > end:
                errors.append({"kind": "shape_coordinate_arrays_out_of_bounds", "part_id": part})
        else:
            if end - begin < 36:
                errors.append({"kind": "composite_header_truncated", "part_id": part})
                continue
            header = struct.unpack_from("<18H", data, begin)
            subparts, tree_parts, tree_axes = header[2:5]
            max_subparts = max(max_subparts, subparts)
            max_tree_parts = max(max_tree_parts, tree_parts)
            max_tree_axes = max(max_tree_axes, tree_axes)
            translations["master_nonzero_count"] += header[8]
            translations["extremum_nonzero_count"] += header[10]
            rotations["master_nonzero_count"] += header[9]
            rotations["extremum_nonzero_count"] += header[11]
            subpart_begin = begin + 4 * header[12]
            if subpart_begin < begin + 36 or subpart_begin + 8 * subparts > end:
                errors.append({"kind": "composite_subpart_array_out_of_bounds", "part_id": part})
                continue
            for i in range(subparts):
                child_id, tree_part_offset, tree_axis_offset = struct.unpack_from("<IHH", data, subpart_begin + 8 * i)
                references += 1
                if child_id >= part_count:
                    errors.append({"kind": "child_part_id_out_of_range", "part_id": part, "child_id": child_id})
                if tree_part_offset >= tree_parts or tree_axis_offset > tree_axes:
                    errors.append({"kind": "child_tree_offset_out_of_range", "part_id": part, "child_index": i})
            if part < glyph_count:
                visible_composites.append((part, subparts, tree_parts, tree_axes))
    result.update({"part_type_counts": dict(types), "part_axis_count_histogram": dict(axes),
                   "visible_type_counts": dict(visible_types), "visible_axis_count_histogram": dict(visible_axes),
                   "direct_subpart_reference_count": references, "maximum_direct_subparts": max_subparts,
                   "maximum_declared_tree_parts": max_tree_parts, "maximum_declared_tree_axes": max_tree_axes,
                   "rotation_records": dict(rotations), "translation_records": dict(translations),
                   "trailing_bytes_after_sentinel": len(data) - index_offset - offsets[-1]})
    return result


def numeric_metrics(data: bytes, glyph_count: int, long_count: int) -> list[tuple[int, int]]:
    required = 4 * long_count + 2 * (glyph_count - long_count)
    if not 0 < long_count <= glyph_count or required > len(data):
        raise ValueError(f"invalid metrics: glyphs={glyph_count}, long={long_count}, bytes={len(data)}")
    result = list(struct.iter_unpack(">Hh", data[:4 * long_count]))
    last_advance = result[-1][0]
    result.extend((last_advance, bearing) for (bearing,) in
                  struct.iter_unpack(">h", data[4 * long_count:required]))
    return result


def metric_summary(metrics):
    advances = [m[0] for m in metrics]
    bearings = [m[1] for m in metrics]
    return {"glyph_count": len(metrics), "advance_min": min(advances), "advance_max": max(advances),
            "zero_advance_count": advances.count(0), "bearing_min": min(bearings), "bearing_max": max(bearings),
            "negative_bearing_count": sum(v < 0 for v in bearings),
            "advance_histogram": dict(sorted(collections.Counter(advances).items()))}


def summarize_layout(font, tag: str) -> dict:
    table = font[tag].table
    table.ensureDecompiled(recurse=True)
    result = {"version": table.Version, "scripts": [], "features": [], "lookup_type_counts": {}}
    if table.ScriptList:
        for record in table.ScriptList.ScriptRecord:
            script = record.Script
            result["scripts"].append({"tag": record.ScriptTag,
                                      "default_language": object_json(script.DefaultLangSys),
                                      "languages": [{"tag": lr.LangSysTag,
                                                     "feature_indices": lr.LangSys.FeatureIndex,
                                                     "required_feature_index": lr.LangSys.ReqFeatureIndex}
                                                    for lr in script.LangSysRecord]})
    if table.FeatureList:
        for record in table.FeatureList.FeatureRecord:
            result["features"].append({"tag": record.FeatureTag,
                                       "lookup_indices": record.Feature.LookupListIndex})
    if table.LookupList:
        result["lookup_count"] = table.LookupList.LookupCount
        result["lookup_type_counts"] = dict(collections.Counter(l.LookupType for l in table.LookupList.Lookup))
    result["feature_variations_present"] = getattr(table, "FeatureVariations", None) is not None
    return result


def stat_summary(font):
    table = font["STAT"].table
    table.ensureDecompiled(recurse=True)
    result = object_json(table)
    records = getattr(table, "DesignAxisRecord", None)
    if records:
        result["resolved_axes"] = [{"tag": a.AxisTag, "name_id": a.AxisNameID,
                                    "name": name_text(font, a.AxisNameID), "order": a.AxisOrdering}
                                   for a in records.Axis]
    return result


def hvar_summary(font, out: Path, artifact_key: str, glyph_order):
    table = font["HVAR"].table
    table.ensureDecompiled(recurse=True)
    store = table.VarStore
    regions = [[{"start": a.StartCoord, "peak": a.PeakCoord, "end": a.EndCoord}
                for a in region.VarRegionAxis] for region in store.VarRegionList.Region]
    maps = {}
    for name in ["AdvWidthMap", "LsbMap", "RsbMap"]:
        mapping = getattr(table, name, None)
        if mapping is None:
            maps[name] = None
        else:
            values = mapping.mapping
            maps[name] = {"mapping_count": len(values), "distinct_var_indices": len(set(values.values()))}
    path = out / "mappings" / f"hvar_{artifact_key}.csv"
    rows = []
    for gid, glyph_name in enumerate(glyph_order):
        indices = []
        for name in ["AdvWidthMap", "LsbMap", "RsbMap"]:
            mapping = getattr(table, name, None)
            indices.append(mapping.mapping.get(glyph_name, "") if mapping is not None else (gid if name == "AdvWidthMap" else ""))
        rows.append((gid, *indices))
    write_csv(path, ["glyph_id", "advance_var_index", "lsb_var_index", "rsb_var_index"], rows)
    normalized_samples = []
    axis_tags = [axis.axisTag for axis in font["fvar"].axes]
    instancer = VarStoreInstancer(store, font["fvar"].axes)
    cmap = font.getBestCmap() or {}
    # These are direct normalized ItemVariationStore evaluations. They deliberately
    # do not apply ambiguous raw Apple avar records or claim CoreText equivalence.
    sample_locations = itertools.product((-1.0, 0.0, 1.0), repeat=len(axis_tags)) if len(axis_tags) <= 4 else [tuple(0.0 for _ in axis_tags)]
    for values in sample_locations:
        location = dict(zip(axis_tags, values))
        instancer.setLocation(location)
        for character in "A0中国字":
            if ord(character) not in cmap:
                continue
            glyph_name = cmap[ord(character)]
            glyph_id = font.getGlyphID(glyph_name)
            var_index = table.AdvWidthMap.mapping[glyph_name] if table.AdvWidthMap is not None else glyph_id
            default_advance = font["hmtx"].metrics[glyph_name][0]
            delta = instancer[var_index]
            normalized_samples.append({"character": character, "glyph_id": glyph_id,
                                       "design_normalized_location": location,
                                       "stored_default_advance": default_advance,
                                       "hvar_delta": delta, "varied_advance": default_advance + delta})
    return {"version": table.Version, "format": store.Format,
            "region_axis_count": store.VarRegionList.RegionAxisCount,
            "region_count": store.VarRegionList.RegionCount, "regions": regions,
            "var_data": [{"item_count": v.ItemCount, "region_indices": v.VarRegionIndex,
                          "nonzero_delta_count": sum(d != 0 for item in v.Item for d in item)} for v in store.VarData],
            "maps": maps, "mapping_csv": str(path.relative_to(out)),
            "active_axis_indices": [i for i in range(store.VarRegionList.RegionAxisCount)
                                    if any(r[i]["peak"] != 0 for r in regions)],
            "mixed_axis_region_count": sum(sum(a["peak"] != 0 for a in r) > 1 for r in regions),
            "design_normalized_metric_samples": normalized_samples,
            "metric_sample_scope": "ItemVariationStore evaluation in design-normalized coordinates, not CoreText user-axis evaluation; no avar interpretation implied."}


def build_report(source: Path, out: Path) -> dict:
    before_digest = file_digest(source)
    file_size = source.stat().st_size
    with source.open("rb") as stream:
        raw_header = stream.read(12)
    is_collection = raw_header[:4] == b"ttcf"
    collection = TTCollection(str(source), lazy=True) if is_collection else None
    fonts = collection.fonts if collection else [TTFont(str(source), lazy=True)]
    report = {
        "schema_version": 1, "audit_started_utc": datetime.now(timezone.utc).isoformat(),
        "input": {"path": str(source), "basename": source.name, "byte_size": file_size,
                  "decimal_MB": file_size / 1_000_000, "binary_MiB": file_size / (1024 * 1024),
                  "sha256": before_digest, "origin_os_version": "user_reported_not_independently_verified"},
        "runtime": {"python": sys.version, "fonttools": fontTools.__version__, "platform": platform.platform()},
        "collection": {"is_ttc": is_collection, "face_count": len(fonts)},
        "sources": SOURCES, "faces": [], "table_sharing": [], "issues": [],
        "outline_evaluation": {"performed": False, "reason": "This tool audits tables and metadata; decoder and platform rendering are separate gates."},
        "runtime_rendering": {"macos_coretext": "not_run", "windows_directwrite": "not_run", "qt": "not_run"},
    }
    if is_collection:
        version, count = struct.unpack_from(">II", raw_header, 4)
        report["collection"].update({"version_hex": f"0x{version:08x}", "declared_face_count": count})
    unique_tables = {}
    table_rows = []
    face_rows = []
    axis_rows = []
    avar_rows = []
    names_rows = []
    license_records = []
    cmap_cache = {}
    metrics_cache = {}
    hvgl_cache = {}
    hvar_cache = {}
    best_maps = {}
    for face_index, font in enumerate(fonts):
        logging.info("Auditing face %d/%d", face_index + 1, len(fonts))
        face = {"face_index": face_index, "sfnt_version_hex": font.sfntVersion.encode("latin1").hex(),
                "table_tags": sorted(font.reader.keys()), "tables": {}, "parser_errors": [],
                "table_presence": {t: t in font.reader for t in REQUESTED_TABLES}}
        report["faces"].append(face)
        for tag, entry in sorted(font.reader.tables.items()):
            key = (entry.offset, entry.length)
            if key not in unique_tables:
                raw = font.reader[tag]
                checksum_bytes = raw[:8] + b"\0\0\0\0" + raw[12:] if tag == "head" else raw
                unique_tables[key] = {"offset": entry.offset, "byte_length": entry.length,
                                      "sha256": digest(raw), "computed_checksum": calcChecksum(checksum_bytes),
                                      "raw_checksum": calcChecksum(raw),
                                      "face_tables": []}
            info = unique_tables[key]
            info["face_tables"].append({"face_index": face_index, "tag": tag})
            details = {"offset": entry.offset, "byte_length": entry.length, "sha256": info["sha256"],
                       "stored_checksum_hex": f"0x{entry.checkSum:08x}",
                       "computed_checksum_hex": f"0x{info['computed_checksum']:08x}",
                       "checksum_matches": entry.checkSum == info["computed_checksum"],
                       "raw_including_adjustment_checksum_matches": entry.checkSum == info["raw_checksum"],
                       "bounds_valid": 0 <= entry.offset <= entry.offset + entry.length <= file_size,
                       "aligned_4_bytes": entry.offset % 4 == 0}
            face["tables"][tag] = details
            try:
                table_class = getTableClass(tag)
                is_raw = table_class is DefaultTable
                decoded = None if is_raw else font[tag]
                details["parser_status"] = "opaque_bytes_only" if is_raw else "decoded"
                details["parser_type"] = table_class.__module__ + "." + table_class.__name__
                if hasattr(decoded, "table") and hasattr(decoded.table, "ensureDecompiled"):
                    decoded.table.ensureDecompiled(recurse=True)
            except Exception as error:
                details["parser_status"] = "error"
                details["parser_error"] = f"{type(error).__name__}: {error}"
                face["parser_errors"].append({"tag": tag, "error": details["parser_error"]})
                logging.exception("Face %d table %s failed to decode", face_index, tag)
            for failed in ["checksum_matches", "bounds_valid", "aligned_4_bytes"]:
                if not details[failed]:
                    report["issues"].append({"face": face_index, "table": tag, "kind": failed, "value": False})
            table_rows.append((face_index, tag, entry.offset, entry.length, details["sha256"],
                               details["checksum_matches"], details["parser_status"]))
        try:
            face["family"] = name_text(font, 1)
            face["style"] = name_text(font, 2)
            face["postscript_name"] = name_text(font, 6)
            face["font_version_name"] = name_text(font, 5)
            face["names"] = []
            for record in font["name"].names:
                item = {"name_id": record.nameID, "platform_id": record.platformID,
                        "encoding_id": record.platEncID, "language_id": record.langID}
                try:
                    item["text"] = record.toUnicode()
                except Exception as error:
                    item.update({"decode_error": f"{type(error).__name__}: {error}", "raw_hex": record.string.hex()})
                face["names"].append(item)
                names_rows.append((face_index, record.nameID, record.platformID, record.platEncID, record.langID, item.get("text", "")))
                if record.nameID in {0, 7, 8, 9, 13, 14}:
                    license_records.append({"face_index": face_index, **item})
            glyph_count = font["maxp"].numGlyphs
            face["glyph_count"] = glyph_count
            glyph_order = font.getGlyphOrder()
            face["glyph_order_count"] = len(glyph_order)
            face["glyph_names_stored_in_post"] = getattr(font["post"], "formatType", None) != 3.0
            face["glyph_id_note"] = "Numeric GIDs are authoritative; post format 3 supplies no names, so fontTools-generated glyph names can differ with the regional cmap."
            for tag in ["head", "hhea", "vhea", "OS/2", "post", "BASE", "VORG", "MVAR", "VVAR"]:
                if tag in font and face["tables"][tag]["parser_status"] == "decoded":
                    face[tag] = object_json(font[tag])
            face["meta"] = object_json(font["meta"]) if "meta" in font else None
            axes = []
            if "fvar" in font:
                for axis_index, axis in enumerate(font["fvar"].axes):
                    item = {"index": axis_index, "tag": axis.axisTag, "minimum": axis.minValue,
                            "default": axis.defaultValue, "maximum": axis.maxValue,
                            "flags": axis.flags, "hidden": bool(axis.flags & 1),
                            "name_id": axis.axisNameID, "name": name_text(font, axis.axisNameID)}
                    axes.append(item)
                    axis_rows.append((face_index, axis_index, axis.axisTag, axis.minValue, axis.defaultValue,
                                      axis.maxValue, axis.flags, item["hidden"], item["name"]))
                face["axes"] = axes
                face["named_instances"] = [{"subfamily_name_id": inst.subfamilyNameID,
                                             "subfamily": name_text(font, inst.subfamilyNameID),
                                             "postscript_name_id": inst.postscriptNameID,
                                             "postscript_name": name_text(font, inst.postscriptNameID) if inst.postscriptNameID != 65535 else None,
                                             "flags": inst.flags, "coordinates": dict(inst.coordinates)}
                                            for inst in font["fvar"].instances]
            if "avar" in font:
                face["avar_raw"] = raw_avar(font.reader["avar"], [a["tag"] for a in axes])
                face["avar_fonttools_collapsed_diagnostic"] = {tag: [[k, v] for k, v in mapping.items()]
                                                             for tag, mapping in font["avar"].segments.items()}
                for axis in face["avar_raw"]["axes"]:
                    for record in axis["records"]:
                        avar_rows.append((face_index, axis["tag"], record["index"], record["from_f2dot14"],
                                          record["to_f2dot14"], record["from"], record["to"]))
                if not face["avar_raw"]["standard_record_conformance_pass"]:
                    report["issues"].append({"face": face_index, "table": "avar", "kind": "raw_avar_standard_conformance"})
            if "STAT" in font:
                face["STAT"] = stat_summary(font)
            for tag in ["GSUB", "GPOS"]:
                if tag in font:
                    face[tag] = summarize_layout(font, tag)
            if "trak" in font:
                trak = font["trak"]
                face["trak"] = {"version": trak.version, "format": trak.format, "directions": {}}
                for direction in ["horizData", "vertData"]:
                    tracks = getattr(trak, direction, {})
                    face["trak"]["directions"][direction] = [{"track": track, "name_id": entry.nameIndex,
                                                             "name": name_text(font, entry.nameIndex),
                                                             "size_value_pairs": sorted(entry.items())}
                                                            for track, entry in tracks.items()]
            for tag in ["morx", "mort", "kerx", "kern", "feat", "ankr", "opbd", "bsln", "just", "prop"]:
                if tag in font:
                    face[tag] = {"present": True, "parser_status": face["tables"][tag]["parser_status"],
                                 "decoded_summary": object_json(font[tag])}

            cmap_entry = font.reader.tables["cmap"]
            cmap_key = f"{cmap_entry.offset}_{cmap_entry.length}"
            if cmap_key not in cmap_cache:
                best = font.getBestCmap() or {}
                gids = {cp: font.getGlyphID(name) for cp, name in best.items()}
                best_maps[cmap_key] = gids
                path = out / "mappings" / f"cmap_{cmap_key}.csv"
                write_csv(path, ["unicode_hex", "unicode_decimal", "glyph_id", "glyph_name_diagnostic"],
                          ((f"U+{cp:04X}", cp, gids[cp], best[cp]) for cp in sorted(best)))
                subtables, uvs_rows, all_subtable_rows = [], [], []
                unicode_assignments = collections.defaultdict(set)
                for subtable_index, subtable in enumerate(font["cmap"].tables):
                    mapping = getattr(subtable, "cmap", {})
                    subtable_info = {"subtable_index": subtable_index, "format": subtable.format,
                                     "platform_id": subtable.platformID, "encoding_id": subtable.platEncID,
                                     "language": getattr(subtable, "language", None),
                                     "is_unicode": subtable.isUnicode(), "mapping_count": len(mapping)}
                    for code, glyph in sorted(mapping.items()):
                        mapped_gid = font.getGlyphID(glyph)
                        all_subtable_rows.append((subtable_index, subtable.format, subtable.platformID,
                                                  subtable.platEncID, subtable.isUnicode(), code, f"0x{code:X}", mapped_gid))
                        if subtable.isUnicode():
                            unicode_assignments[code].add(mapped_gid)
                    if subtable.format == 14:
                        uvs = subtable.uvsDict
                        subtable_info["variation_selectors"] = [f"U+{v:04X}" for v in sorted(uvs)]
                        subtable_info["uvs_mapping_count"] = sum(len(rows) for rows in uvs.values())
                        for selector, pairs in sorted(uvs.items()):
                            for base, glyph in pairs:
                                uvs_rows.append((subtable_index, f"U+{base:04X}", f"U+{selector:04X}",
                                                 font.getGlyphID(glyph) if glyph is not None else "default", glyph or ""))
                    subtables.append(subtable_info)
                uvs_path = out / "mappings" / f"cmap_uvs_{cmap_key}.csv"
                write_csv(uvs_path, ["subtable_index", "base_unicode", "variation_selector", "glyph_id_or_default", "glyph_name_diagnostic"], uvs_rows)
                all_path = out / "mappings" / f"cmap_all_subtables_{cmap_key}.csv"
                write_csv(all_path, ["subtable_index", "format", "platform_id", "encoding_id", "is_unicode", "character_code_decimal", "character_code_hex", "glyph_id"], all_subtable_rows)
                cmap_cache[cmap_key] = {"best_unicode_mapping_count": len(gids),
                                       "best_unicode_distinct_gids": len(set(gids.values())),
                                       "best_unicode_min": min(gids) if gids else None,
                                       "best_unicode_max": max(gids) if gids else None,
                                       "best_unicode_astral_count": sum(cp > 0xFFFF for cp in gids),
                                       "best_unicode_plane_counts": dict(collections.Counter(cp >> 16 for cp in gids)),
                                       "subtables": subtables, "mapping_csv": str(path.relative_to(out)),
                                       "all_subtables_csv": str(all_path.relative_to(out)),
                                       "all_unicode_subtables_union_count": len(unicode_assignments),
                                       "conflicting_unicode_gid_assignments": {f"U+{cp:04X}": sorted(values) for cp, values in unicode_assignments.items() if len(values) > 1},
                                       "variation_sequence_csv": str(uvs_path.relative_to(out)),
                                       "mapped_gid_out_of_range_count": sum(gid >= glyph_count for gid in gids.values())}
            face["cmap"] = cmap_cache[cmap_key]
            face["cmap_group_key"] = cmap_key

            hm = font.reader.tables.get("hmtx")
            vm = font.reader.tables.get("vmtx")
            metrics_key = f"{hm.offset if hm else 'none'}_{vm.offset if vm else 'none'}_{glyph_count}_{font['hhea'].numberOfHMetrics if hm else 0}_{font['vhea'].numberOfVMetrics if vm else 0}"
            if metrics_key not in metrics_cache:
                hmetrics = numeric_metrics(font.reader["hmtx"], glyph_count, font["hhea"].numberOfHMetrics) if hm else None
                vmetrics = numeric_metrics(font.reader["vmtx"], glyph_count, font["vhea"].numberOfVMetrics) if vm else None
                path = out / "mappings" / f"metrics_{metrics_key}.csv"
                write_csv(path, ["glyph_id", "h_advance", "left_side_bearing", "v_advance", "top_side_bearing"],
                          ((gid, *(hmetrics[gid] if hmetrics else ("", "")), *(vmetrics[gid] if vmetrics else ("", "")))
                           for gid in range(glyph_count)))
                metrics_cache[metrics_key] = {"horizontal": metric_summary(hmetrics) if hmetrics else None,
                                             "vertical": metric_summary(vmetrics) if vmetrics else None,
                                             "mapping_csv": str(path.relative_to(out)),
                                             "note": "Stored default advances and bearings only. Outline bounds and varied side bearings require the HVF decoder."}
            face["metrics"] = metrics_cache[metrics_key]
            if "HVAR" in font:
                entry = font.reader.tables["HVAR"]
                key = f"{entry.offset}_{entry.length}"
                if key not in hvar_cache:
                    hvar_cache[key] = hvar_summary(font, out, key, glyph_order)
                face["HVAR"] = hvar_cache[key]
            if "hvgl" in font:
                entry = font.reader.tables["hvgl"]
                key = f"{entry.offset}_{entry.length}"
                if key not in hvgl_cache:
                    hvgl_cache[key] = inspect_hvgl(font.reader["hvgl"], entry.offset)
                face["hvgl"] = hvgl_cache[key]
            face_rows.append((face_index, face.get("family"), face.get("style"), face.get("postscript_name"),
                              glyph_count, font["head"].unitsPerEm, face["cmap"]["best_unicode_mapping_count"],
                              len(axes), len(face.get("named_instances", [])), font["OS/2"].fsType))
        except Exception as error:
            face["face_audit_error"] = f"{type(error).__name__}: {error}"
            report["issues"].append({"face": face_index, "kind": "face_audit_error", "error": face["face_audit_error"]})
            logging.exception("Face %d audit failed", face_index)

    report["table_sharing"] = sorted(unique_tables.values(), key=lambda entry: (entry["offset"], entry["byte_length"]))
    for left, right in zip(report["table_sharing"], report["table_sharing"][1:]):
        if left["offset"] + left["byte_length"] > right["offset"]:
            report["issues"].append({"kind": "partially_overlapping_distinct_tables",
                                     "first_offset": left["offset"], "second_offset": right["offset"]})
    report["coverage_comparisons"] = []
    for a, b in itertools.combinations(best_maps, 2):
        amap, bmap = best_maps[a], best_maps[b]
        shared = amap.keys() & bmap.keys()
        differences = [(cp, amap[cp], bmap[cp]) for cp in sorted(shared) if amap[cp] != bmap[cp]]
        path = out / "mappings" / f"regional_gid_differences_{a}__{b}.csv"
        write_csv(path, ["unicode_hex", "first_gid", "second_gid"], ((f"U+{cp:04X}", ga, gb) for cp, ga, gb in differences))
        report["coverage_comparisons"].append({"first_cmap_group": a, "second_cmap_group": b,
                                               "shared_unicode_count": len(shared),
                                               "only_first_count": len(amap.keys() - bmap.keys()),
                                               "only_second_count": len(bmap.keys() - amap.keys()),
                                               "different_gid_for_shared_unicode": len(differences),
                                               "difference_csv": str(path.relative_to(out)),
                                               "note": "A GID difference proves a different referenced part, not its precise visual outline difference."})
    union = set().union(*(mapping.keys() for mapping in best_maps.values()))
    report["unicode_union_count"] = len(union)
    report["total_face_glyph_slots"] = sum(f.get("glyph_count", 0) for f in report["faces"])
    report["unique_hvgl_table_count"] = len(hvgl_cache)
    report["unique_hvgl_header_summaries"] = hvgl_cache
    report["unique_table_blob_count"] = len(unique_tables)
    report["unique_cmap_count"] = len(cmap_cache)
    report["after_audit_sha256"] = file_digest(source)
    report["source_unchanged"] = before_digest == report["after_audit_sha256"]
    report["audit_finished_utc"] = datetime.now(timezone.utc).isoformat()
    write_csv(out / "faces.csv", ["face_index", "family", "style", "postscript_name", "glyph_count", "units_per_em", "best_unicode_count", "axis_count", "named_instance_count", "os2_fs_type"], face_rows)
    write_csv(out / "tables.csv", ["face_index", "tag", "offset", "byte_length", "sha256", "checksum_matches", "parser_status"], table_rows)
    write_csv(out / "axes.csv", ["face_index", "axis_index", "tag", "minimum", "default", "maximum", "flags", "hidden", "name"], axis_rows)
    write_csv(out / "avar_raw_records.csv", ["face_index", "axis_tag", "record_index", "from_f2dot14", "to_f2dot14", "from_normalized", "to_normalized"], avar_rows)
    write_csv(out / "name_records.csv", ["face_index", "name_id", "platform_id", "encoding_id", "language_id", "text"], names_rows)
    write_json(out / "original_license_name_records.json", license_records)
    write_json(out / "font_audit.json", report)
    if collection:
        collection.close()
    else:
        fonts[0].close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("font", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.font.resolve(strict=True)
    out = args.output.resolve()
    if source == out or source in out.parents:
        parser.error("output must be a directory separate from the source font")
    out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO,
                        handlers=[logging.FileHandler(out / "audit.log", encoding="utf-8"), logging.StreamHandler()],
                        format="%(asctime)s %(levelname)s %(message)s")
    report = build_report(source, out)
    summary = {"sha256": report["input"]["sha256"], "byte_size": report["input"]["byte_size"],
               "face_count": report["collection"]["face_count"], "unique_table_blob_count": report["unique_table_blob_count"],
               "unicode_union_count": report["unicode_union_count"], "issue_count": len(report["issues"]),
               "source_unchanged": report["source_unchanged"], "report": str(out / "font_audit.json")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    logging.info("Completed read-only audit; %d recorded issues (not silently repaired).", len(report["issues"]))
    return 0 if report["source_unchanged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
