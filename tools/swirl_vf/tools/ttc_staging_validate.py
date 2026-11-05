"""Strict, bounded C1 output checks; no Apple inputs or equivalence claims.

This profile validates expanded quadratic reconstruction output. It does not
repair a font, replace an axis, renumber a GID or certify source/native parity.
Contracts contain hashes and public structural metadata, never outline bytes,
character maps or glyph names. The full serialized tables remain private.

Primary references (independently implemented checks):
https://github.com/fonttools/fonttools/tree/main/Lib/fontTools/ttLib
https://learn.microsoft.com/en-us/typography/opentype/spec/otff
https://learn.microsoft.com/en-us/typography/opentype/spec/gvar
https://learn.microsoft.com/en-us/typography/opentype/spec/hvar
https://learn.microsoft.com/en-us/typography/opentype/spec/vvar
https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats
"""
from __future__ import annotations

import gc
import hashlib
import json
import math
from pathlib import Path
import struct

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.otBase import BaseTable
from fontTools.ttLib.tables.otConverters import GlyphID

from metric_variations import MetricVariationError, verify_metric_variations
from ttc_staging_contract import StagingError


AXIS_TAGS = ("WDTH", "wght", "HGHT")
REQUIRED = frozenset(("head", "hhea", "hmtx", "maxp", "name", "OS/2", "post",
                      "cmap", "glyf", "loca", "fvar", "gvar", "STAT", "HVAR",
                      "vhea", "vmtx", "VVAR"))
CONTRACT_VERSION = 1


def _need(condition, category, code, **context):
    if not condition:
        raise StagingError(category, code, **context)


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _fixed(value, scale, low, high):
    return _number(value) and low <= value <= high and value * scale == int(value * scale)


def _glyph_ref(value, names, code="layout_glyph_reference"):
    _need(type(value) is str and value in names, "font_tables", code)


def _table_data(font, tag):
    recalc_timestamp = font.recalcTimestamp
    try:
        # A validation read must not rewrite head.modified merely because the
        # caller opened TTFont with its default recalcTimestamp=True option.
        font.recalcTimestamp = False
        value = font.getTableData(tag)
    except Exception as error:
        raise StagingError("serialization", "table_compile_failed", table=tag) from error
    finally:
        font.recalcTimestamp = recalc_timestamp
    if tag == "head":
        _need(len(value) >= 54, "font_tables", "head_length")
        # The TTC checksum adjustment is intentionally unused by the spec.
        value = value[:8] + b"\0" * 4 + value[12:]
    return value


def _cmap(font, order):
    names = set(order)
    maps, unicode_map = [], {}
    for table in font["cmap"].tables:
        _need(table.format in (0, 2, 4, 6, 8, 10, 12, 13, 14),
              "font_tables", "unsupported_cmap_format")
        key = (table.platformID, table.platEncID, table.format, getattr(table, "language", 0))
        if table.format == 14:
            rows = []
            for selector, entries in sorted(table.uvsDict.items()):
                _need(_integer(selector, 0xFE00, 0xFE0F)
                      or _integer(selector, 0xE0100, 0xE01EF), "font_tables", "cmap_uvs_selector")
                seen = set()
                for codepoint, name in entries:
                    _need(_integer(codepoint, 0, 0x10FFFF) and not 0xD800 <= codepoint <= 0xDFFF,
                          "font_tables", "cmap_uvs_codepoint")
                    _need(codepoint not in seen, "font_tables", "cmap_uvs_duplicate")
                    seen.add(codepoint)
                    if name is not None:
                        _glyph_ref(name, names, "cmap_uvs_glyph_reference")
                rows.append((selector, sorted((cp, None if name is None else font.getGlyphID(name))
                                              for cp, name in entries)))
            maps.append((key, rows))
            continue
        rows = []
        for codepoint, name in sorted(table.cmap.items()):
            _need(_integer(codepoint, 0, 0x10FFFF), "font_tables", "cmap_codepoint")
            _glyph_ref(name, names, "cmap_glyph_reference")
            gid = font.getGlyphID(name)
            rows.append((codepoint, gid))
            if table.isUnicode():
                _need(codepoint not in unicode_map or unicode_map[codepoint] == gid,
                      "font_tables", "unicode_cmap_conflict")
                unicode_map[codepoint] = gid
        maps.append((key, rows))
    _need(bool(unicode_map), "font_tables", "unicode_cmap_missing")
    for table in font["cmap"].tables:
        if table.format == 14:
            _need(all(name is not None or cp in unicode_map for entries in table.uvsDict.values()
                      for cp, name in entries), "font_tables", "default_uvs_base_missing")
    return sorted(maps), len(unicode_map)


def _axes(font):
    axes = font["fvar"].axes
    tags = tuple(a.axisTag for a in axes)
    _need(tags == AXIS_TAGS, "input_axis", "original_axis_tags_or_order_changed")
    names = {r.nameID for r in font["name"].names}
    values = []
    for axis in axes:
        low, default, high = axis.minValue, axis.defaultValue, axis.maxValue
        _need(all(_fixed(v, 65536, -32768, 32767 + 65535/65536) for v in (low, default, high))
              and low <= default <= high and low < high,
              "input_axis", "axis_range_invalid")
        _need(axis.axisNameID in names, "font_tables", "axis_name_missing")
        values.append((axis.axisTag, low, default, high, axis.flags, axis.axisNameID))
    instances = []
    for instance in font["fvar"].instances:
        _need(set(instance.coordinates) == set(tags), "input_axis", "instance_axes_incomplete")
        _need(instance.subfamilyNameID in names, "font_tables", "instance_name_missing")
        ps = getattr(instance, "postscriptNameID", 0xFFFF)
        _need(ps == 0xFFFF or ps in names, "font_tables", "instance_postscript_name_missing")
        for axis in axes:
            value = instance.coordinates[axis.axisTag]
            _need(_fixed(value, 65536, axis.minValue, axis.maxValue),
                  "input_axis", "instance_coordinate_invalid")
        instances.append((instance.subfamilyNameID, ps, instance.flags,
                          [(tag, instance.coordinates[tag]) for tag in tags]))
    if "avar" in font:
        avar = font["avar"]
        _need(avar.majorVersion == 1 and avar.minorVersion == 0,
              "input_axis", "unsupported_avar_version")
        _need(set(avar.segments) == set(tags), "input_axis", "avar_axes_incomplete")
        for segment in avar.segments.values():
            _need(all(segment.get(v) == v for v in (-1.0, 0.0, 1.0)),
                  "input_axis", "avar_required_anchors")
            pairs = sorted(segment.items())
            _need(all(_fixed(x, 16384, -1, 1) and _fixed(y, 16384, -1, 1) for x, y in pairs),
                  "input_axis", "avar_coordinate_invalid")
            _need(all(a[1] <= b[1] for a, b in zip(pairs, pairs[1:])),
                  "input_axis", "avar_not_monotone")
    return values, instances


def _names(font):
    records, ids = [], set()
    for record in font["name"].names:
        try:
            value = record.toUnicode(errors="strict")
        except Exception as error:
            raise StagingError("font_tables", "name_decode_failed") from error
        ids.add(record.nameID)
        records.append((record.nameID, record.platformID, record.platEncID, record.langID, value))
        if record.nameID == 6:
            _need(0 < len(value) <= 63 and all(33 <= ord(c) <= 126 and c not in "[]()/<>%" for c in value),
                  "font_tables", "postscript_name_invalid")
    _need({1, 2, 4, 6} <= ids, "font_tables", "required_name_missing")
    return sorted(records)


def _stat(font):
    table = font["STAT"].table
    _need(table.Version in (0x00010000, 0x00010001, 0x00010002),
          "font_tables", "stat_version")
    axes = table.DesignAxisRecord.Axis if table.DesignAxisRecord else []
    _need(table.DesignAxisCount == len(axes) and len(axes) == len(AXIS_TAGS)
          and {axis.AxisTag for axis in axes} == set(AXIS_TAGS),
          "input_axis", "stat_axis_mapping")
    names = {record.nameID for record in font["name"].names}
    _need(all(axis.AxisNameID in names for axis in axes), "font_tables", "stat_axis_name_missing")
    fallback = getattr(table, "ElidedFallbackNameID", None)
    _need(fallback is None or fallback in names, "font_tables", "stat_fallback_name_missing")
    values = table.AxisValueArray.AxisValue if table.AxisValueArray else []
    _need(table.AxisValueCount == len(values), "font_tables", "stat_value_count")
    for value in values:
        _need(value.Format in (1, 2, 3, 4) and value.ValueNameID in names,
              "font_tables", "stat_value_format_or_name")
        records = value.AxisValueRecord if value.Format == 4 else [value]
        if value.Format == 4:
            _need(value.AxisCount == len(records)
                  and len({r.AxisIndex for r in records}) == len(records),
                  "input_axis", "stat_multi_axis_count")
        for record in records:
            _need(_integer(record.AxisIndex, 0, len(axes)-1), "input_axis", "stat_axis_index")
            fields = ("NominalValue", "RangeMinValue", "RangeMaxValue") if value.Format == 2 else ("Value",)
            if value.Format == 3:
                fields += ("LinkedValue",)
            for field in fields:
                _need(_fixed(getattr(record, field), 65536, -32768, 32767 + 65535/65536),
                      "input_axis", "stat_coordinate_invalid")
            if value.Format == 2:
                _need(record.RangeMinValue <= record.NominalValue <= record.RangeMaxValue,
                      "input_axis", "stat_range_invalid")


def _support(triples, axis_count):
    _need(len(triples) == axis_count, "input_axis", "variation_region_axis_count")
    for low, peak, high in triples:
        _need(all(_fixed(v, 16384, -1, 1) for v in (low, peak, high))
              and low <= peak <= high, "input_axis", "variation_support_invalid")
        _need((low, peak, high) == (0, 0, 0)
              or (peak != 0 and not low < 0 < high),
              "input_axis", "variation_support_noncontributing")


def _store(store, axis_count, category="metrics"):
    _need(store is not None and store.Format == 1, category, "variation_store_format")
    regions = store.VarRegionList
    _need(regions.RegionAxisCount == axis_count and regions.RegionCount == len(regions.Region),
          category, "variation_region_count")
    for region in regions.Region:
        _support([(a.StartCoord, a.PeakCoord, a.EndCoord) for a in region.VarRegionAxis], axis_count)
    _need(store.VarDataCount == len(store.VarData), category, "variation_data_count")
    for data in store.VarData:
        _need(data.VarRegionCount == len(data.VarRegionIndex), category, "variation_data_region_count")
        _need(len(set(data.VarRegionIndex)) == len(data.VarRegionIndex), category, "variation_region_duplicate")
        _need(all(_integer(index, 0, len(regions.Region)-1) for index in data.VarRegionIndex),
              category, "variation_region_index")
        _need(data.ItemCount == len(data.Item), category, "variation_item_count")
        _need(all(len(row) == len(data.VarRegionIndex)
                  and all(_integer(v, -2147483648, 2147483647) for v in row) for row in data.Item),
              category, "variation_item_row")
    return store


def _var_index(index, store, category="metrics"):
    _need(_integer(index, 0, 0xFFFFFFFF), category, "variation_index_invalid")
    if index == 0xFFFFFFFF:
        return
    outer, inner = index >> 16, index & 0xFFFF
    _need(outer < len(store.VarData) and inner < len(store.VarData[outer].Item),
          category, "variation_index_out_of_range")


def _metrics(font, order):
    names = set(order)
    for tag, header, count_attr in (("hmtx", "hhea", "numberOfHMetrics"),
                                     ("vmtx", "vhea", "numberOfVMetrics")):
        table = font[tag]
        _need(set(table.metrics) == names, "metrics", "metric_gid_coverage", table=tag)
        _need(all(len(pair) == 2 and _integer(pair[0], 0, 65535)
                  and _integer(pair[1], -32768, 32767) for pair in table.metrics.values()),
              "metrics", "metric_value_invalid", table=tag)
        # In-memory FontBuilder headers get their counts during compilation.
        font.getTableData(tag)
        _need(_integer(getattr(font[header], count_attr), 1, len(order)),
              "metrics", "metric_header_count", table=tag)
    if "VORG" in font:
        vorg = font["VORG"]
        _need(set(vorg.VOriginRecords) <= names, "metrics", "vorg_glyph_reference")
        raise StagingError("metrics", "vorg_not_admitted_for_glyf")
    for tag, advance in (("HVAR", "AdvWidthMap"), ("VVAR", "AdvHeightMap")):
        table = font[tag].table
        _need(table.Version == 0x00010000, "metrics", "metric_variation_version", table=tag)
        store = _store(table.VarStore, len(AXIS_TAGS))
        fields = (advance, "LsbMap", "RsbMap") if tag == "HVAR" else (advance, "TsbMap", "BsbMap", "VOrgMap")
        for field in fields:
            mapping = getattr(table, field, None)
            if mapping is None:
                if field == advance:
                    for gid in range(len(order)):
                        _var_index(gid, store)
                continue
            _need(set(mapping.mapping) == names, "metrics", "metric_map_gid_coverage", table=tag)
            for index in mapping.mapping.values():
                _var_index(index, store)
        # Reuse the exact coefficient comparator; this is standard-model parity,
        # never a claim about the Apple source or the B1 origin problem.
    try:
        return verify_metric_variations(font)
    except (MetricVariationError, KeyError, IndexError, TypeError, ValueError) as error:
        raise StagingError("metrics", "gvar_metric_coefficients_differ") from error


def _outlines(font, order):
    glyf = font["glyf"]
    _need(set(glyf.glyphs) == set(order), "outline", "glyf_gid_coverage")
    _need(font["gvar"].version == 1 and font["gvar"].reserved == 0,
          "font_tables", "gvar_version")
    _need(set(font["gvar"].variations) <= set(order), "outline", "gvar_unknown_gid")
    points = tuples = 0
    for gid, name in enumerate(order):
        glyph = glyf[name]
        _need(not glyph.isComposite(), "outline", "expanded_glyph_required", gid=gid)
        coordinates, end_points, flags = glyph.getCoordinates(glyf)
        _need(0 <= glyph.numberOfContours <= 32767 and glyph.numberOfContours == len(end_points)
              and len(coordinates) <= 65535,
              "outline", "contour_count", gid=gid)
        _need(len(flags) == len(coordinates), "outline", "point_flag_count", gid=gid)
        _need((not coordinates and not end_points) or
              (bool(end_points) and end_points[-1] == len(coordinates)-1
               and all(a < b for a, b in zip((-1, *end_points), end_points))),
              "outline", "contour_end_points", gid=gid)
        _need(all(len(pair) == 2 and all(_number(v) and v == int(v) and -32768 <= v <= 32767 for v in pair)
                  for pair in coordinates), "outline", "glyf_coordinate_invalid", gid=gid)
        variations = font["gvar"].variations.get(name, [])
        _need(len(variations) <= 4095, "outline", "gvar_tuple_count", gid=gid)
        for variation in variations:
            _need(set(variation.axes) <= set(AXIS_TAGS), "input_axis", "gvar_unknown_axis", gid=gid)
            _support([variation.axes.get(tag, (0, 0, 0)) for tag in AXIS_TAGS], len(AXIS_TAGS))
            _need(any(variation.axes.get(tag, (0, 0, 0)) != (0, 0, 0) for tag in AXIS_TAGS),
                  "input_axis", "gvar_constant_tuple", gid=gid)
            _need(len(variation.coordinates) == len(coordinates) + 4,
                  "outline", "gvar_point_count_including_phantoms", gid=gid)
            _need(all(pair is None or (len(pair) == 2 and
                      all(_number(v) and v == int(v) and -32768 <= v <= 32767 for v in pair))
                      for pair in variation.coordinates), "outline", "gvar_delta_invalid", gid=gid)
            tuples += 1
        points += len(coordinates)
    # Compiling glyf populates loca for an in-memory model without rewriting it.
    data = font.getTableData("glyf")
    locations = list(font["loca"].locations)
    _need(len(locations) == len(order) + 1 and locations[0] == 0,
          "font_tables", "loca_count_or_origin")
    _need(all(_integer(v, 0, len(data)) for v in locations)
          and all(a <= b for a, b in zip(locations, locations[1:])),
          "font_tables", "loca_offsets")
    _need(font["head"].indexToLocFormat in (0, 1), "font_tables", "loca_format")
    if font["head"].indexToLocFormat == 0:
        _need(all(v % 2 == 0 and v <= 131070 for v in locations), "font_tables", "short_loca_range")
    return points, tuples


def _existing_loca(font):
    """Check before compilation can regenerate offsets and hide corruption."""
    locations = getattr(font["loca"], "locations", None)
    if locations is None:
        return
    _need(len(locations) == font["maxp"].numGlyphs + 1,
          "font_tables", "maxp_glyph_count")
    if getattr(font, "reader", None) is not None and "glyf" in font.reader.tables:
        size = font.reader.tables["glyf"].length
        _need(locations[0] == 0 and all(_integer(v, 0, size) for v in locations)
              and all(a <= b for a, b in zip(locations, locations[1:])),
              "font_tables", "loca_offsets")


def _existing_gvar(font, glyph_count):
    """Check stored indexing before fontTools can hide surplus/missing records."""
    if getattr(font, "reader", None) is None or "gvar" not in font.reader:
        return
    data = font.reader["gvar"]
    _need(len(data) >= 20, "font_tables", "gvar_header_length")
    major, minor, axis_count, shared_count, shared_offset, count, flags, array_offset = struct.unpack(
        ">HHHHIHHI", data[:20])
    _need((major, minor) == (1, 0) and flags in (0, 1), "font_tables", "gvar_header_version")
    _need(axis_count == len(AXIS_TAGS) and count == glyph_count,
          "font_tables", "gvar_header_axis_or_glyph_count")
    width = 4 if flags & 1 else 2
    offsets_end = 20 + (count + 1) * width
    _need(offsets_end <= len(data) and offsets_end <= array_offset <= len(data),
          "font_tables", "gvar_offset_array_bounds")
    if shared_count:
        _need(shared_count <= 4096 and offsets_end <= shared_offset
              and shared_offset + shared_count * axis_count * 2 <= len(data),
              "font_tables", "gvar_shared_tuple_bounds")
    offsets = struct.unpack(">" + ("I" if width == 4 else "H") * (count + 1), data[20:offsets_end])
    scale = 1 if width == 4 else 2
    _need(all(offset * scale <= len(data) - array_offset for offset in offsets)
          and all(a <= b for a, b in zip(offsets, offsets[1:])),
          "font_tables", "gvar_offsets")


def _layout(font, order):
    names, count, visited = set(order), 0, set()
    gdef_store = None
    if "GDEF" in font:
        gdef = font["GDEF"].table
        if getattr(gdef, "VarStore", None) is not None:
            # A valid source store still lives in the source normalized space.
            # C1 has no independently validated avar/layout remapping adapter.
            raise StagingError("font_tables", "unmapped_layout_variation_store")

    def refs(value):
        nonlocal count
        if isinstance(value, (list, tuple)):
            for item in value:
                refs(item)
        else:
            _glyph_ref(value, names)
            count += 1

    def walk(value, depth=0):
        _need(depth <= 80, "font_tables", "layout_depth_limit")
        if value is None or isinstance(value, (str, bytes, int, float)):
            return
        if id(value) in visited:
            return
        visited.add(id(value))
        _need(len(visited) <= 2000000, "font_tables", "layout_node_limit")
        if isinstance(value, dict):
            for item in value.values():
                walk(item, depth + 1)
            return
        if isinstance(value, (tuple, list)):
            for item in value:
                walk(item, depth + 1)
            return
        if isinstance(value, BaseTable):
            # With TTFont(lazy=True), custom GSUB mappings and GDEF classDefs
            # are absent from __dict__ until this explicit decode. Walking a
            # deferred reader before compilation otherwise misses real GID
            # references that fontTools can round-trip as glyph65534 names.
            value.ensureDecompiled()
        attributes = vars(value)
        for field in ("glyphs", "Component"):
            if field in attributes:
                refs(attributes[field])
        for field in ("LigGlyph", "SecondGlyph"):
            if field in attributes:
                refs(attributes[field])
        if "classDefs" in attributes:
            refs(list(attributes["classDefs"]))
            _need(all(_integer(v, 0, 65535) for v in attributes["classDefs"].values()),
                  "font_tables", "layout_class_invalid")
        for field in ("mapping", "alternates"):
            if field in attributes:
                for source, target in attributes[field].items():
                    refs(source)
                    refs(target)
        if "ligatures" in attributes:
            refs(list(attributes["ligatures"]))
        if getattr(value, "DeltaFormat", None) == 0x8000:
            _need(gdef_store is not None, "font_tables", "layout_variation_store_missing")
            _var_index((value.StartSize << 16) | value.EndSize, gdef_store, "font_tables")
        if hasattr(value, "getConverters"):
            for converter in value.getConverters():
                if isinstance(converter, GlyphID) and hasattr(value, converter.name):
                    refs(getattr(value, converter.name))
        for field, item in attributes.items():
            if field != "VarStore":
                walk(item, depth + 1)

    for tag in ("GSUB", "GPOS", "GDEF", "BASE"):
        if tag not in font:
            continue
        root = font[tag].table
        if tag == "BASE":
            _need(getattr(root, "VarStore", None) is None,
                  "font_tables", "unmapped_layout_variation_store", table=tag)
        if tag in ("GSUB", "GPOS"):
            _need(root.Version in (0x00010000, 0x00010001), "font_tables", "layout_version", table=tag)
            features = root.FeatureList.FeatureRecord if root.FeatureList else []
            lookups = root.LookupList.Lookup if root.LookupList else []
            for lookup in lookups:
                _need(_integer(lookup.LookupType, 1, 8 if tag == "GPOS" else 9)
                      and lookup.SubTableCount == len(lookup.SubTable),
                      "font_tables", "lookup_type_or_count", table=tag)
            for feature in features:
                _need(all(_integer(i, 0, len(lookups)-1) for i in feature.Feature.LookupListIndex),
                      "font_tables", "feature_lookup_index", table=tag)
            if root.ScriptList:
                for script in root.ScriptList.ScriptRecord:
                    languages = [r.LangSys for r in script.Script.LangSysRecord]
                    if script.Script.DefaultLangSys is not None:
                        languages.append(script.Script.DefaultLangSys)
                    for language in languages:
                        _need(all(_integer(i, 0, len(features)-1) for i in language.FeatureIndex)
                              and (language.ReqFeatureIndex == 0xFFFF or
                                   _integer(language.ReqFeatureIndex, 0, len(features)-1)),
                              "font_tables", "language_feature_index", table=tag)
            # The existing converter does not map variable layout conditions.
            _need(getattr(root, "FeatureVariations", None) is None,
                  "font_tables", "layout_feature_variations_not_admitted", table=tag)
        walk(root)
        _table_data(font, tag)  # Reject nonrepresentable references/fields.
    return count


def _contract(font, order, cmap, name_records, axes, instances):
    table_tags = sorted(tag for tag in font.keys() if tag != "GlyphOrder")
    tables = {tag: hashlib.sha256(_table_data(font, tag)).hexdigest() for tag in table_tags}
    serialized = {}
    for tag in table_tags:
        if getattr(font, "reader", None) is not None and tag in font.reader:
            data = font.reader[tag]
            if tag == "head":
                data = data[:8] + b"\0" * 4 + data[12:]
            serialized[tag] = hashlib.sha256(data).hexdigest()
        else:
            serialized[tag] = tables[tag]
    return {"schema": CONTRACT_VERSION, "glyph_count": len(order),
            "upm": font["head"].unitsPerEm, "glyph_order_sha256": _digest(order),
            "cmap_sha256": _digest(cmap), "names_sha256": _digest(name_records),
            "postscript_name_sha256": _digest(font["name"].getDebugName(6)),
            "axes": [list(axis) for axis in axes], "instances_sha256": _digest(instances),
            "weight_class": font["OS/2"].usWeightClass,
            "width_class": font["OS/2"].usWidthClass, "table_sha256": tables,
            "serialized_table_sha256": serialized}


def _checked(font):
    _need(REQUIRED <= set(font.keys()), "font_tables", "required_tables_missing")
    _need(not ({"hvgl", "hvpm", "CFF ", "CFF2", "MVAR", "cvar", "DSIG"} & set(font.keys())),
          "font_tables", "unmapped_or_incompatible_tables")
    _existing_loca(font)
    order = font.getGlyphOrder()
    _need(bool(order) and len(order) <= 65535 and order[0] == ".notdef"
          and len(set(order)) == len(order), "font_tables", "glyph_order_invalid")
    _need(font["maxp"].numGlyphs == len(order), "font_tables", "maxp_glyph_count")
    _existing_gvar(font, len(order))
    _need(_integer(font["head"].unitsPerEm, 16, 16384), "font_tables", "units_per_em_invalid")
    _need(_integer(font["OS/2"].usWeightClass, 1, 1000)
          and _integer(font["OS/2"].usWidthClass, 1, 9), "font_tables", "weight_or_width_class")
    name_records = _names(font)
    axes, instances = _axes(font)
    _stat(font)
    cmap, cmap_count = _cmap(font, order)
    points, tuples = _outlines(font, order)
    metric_report = _metrics(font, order)
    references = _layout(font, order)
    contract = _contract(font, order, cmap, name_records, axes, instances)
    return contract, {"status": "PASS_C1_OUTPUT_STRUCTURE", "glyphs_checked": len(order),
                      "outline_points_checked": points, "gvar_tuples_checked": tuples,
                      "unicode_mappings_checked": cmap_count, "layout_glyph_references_checked": references,
                      "table_count": len(contract["table_sha256"]),
                      "metric_models_checked": metric_report["glyph_metric_models_checked"],
                      "native_source_equivalence": False, "production_accepted": False}


def face_contract(font):
    """Validate one standard face and return its safe immutable comparison key.

    Freeze edits to a standalone TTF and reopen before taking a packaging
    contract. Both decoded coefficients and original serialized table bytes
    are bound; a dirty TTFont reader does not describe the newly saved bytes.
    """
    try:
        return _checked(font)[0]
    except StagingError:
        raise
    except Exception as error:
        raise StagingError("font_tables", "malformed_face") from error


def validate_face(font, expected=None):
    """Validate all GIDs and table links; compare a frozen standalone contract."""
    try:
        contract, report = _checked(font)
        if expected is not None:
            _need(type(expected) is dict and expected.get("schema") == CONTRACT_VERSION,
                  "serialization", "face_contract_schema")
            _need(contract == expected, "serialization", "face_contract_mismatch")
        return report
    except StagingError:
        raise
    except Exception as error:
        raise StagingError("font_tables", "malformed_face") from error


def validate_collection(path, expected_contracts):
    """Stream physical TTC faces in order; no cross-face glyph renumbering.

    Only one TTFont is decoded at a time. Expected contracts must originate in
    the independently checked standalone faces, not in the untrusted TTC.
    """
    _need(type(expected_contracts) in (list, tuple) and bool(expected_contracts),
          "serialization", "collection_contracts_missing")
    path = Path(path)
    try:
        with path.open("rb") as stream:
            header = stream.read(12)
            _need(len(header) == 12 and header[:4] == b"ttcf",
                  "serialization", "ttc_header")
            version, count = struct.unpack(">II", header[4:])
            _need(version in (0x00010000, 0x00020000) and count == len(expected_contracts),
                  "serialization", "ttc_face_count_or_version")
        identities = [contract.get("postscript_name_sha256") for contract in expected_contracts]
        _need(len(set(identities)) == len(identities), "font_tables", "duplicate_face_identity")
        reports = []
        for index, expected in enumerate(expected_contracts):
            with TTFont(path, fontNumber=index, lazy=True, recalcTimestamp=False) as font:
                report = validate_face(font, expected)
                reports.append({"face_index": index, **report})
            # close() releases the file, not decoded tables or lazy-reader
            # cycles. Release this physical face before opening the next one.
            del font
            gc.collect()
        return {"status": "PASS_C1_TTC_STRUCTURE", "faces_checked": count,
                "glyphs_checked": sum(r["glyphs_checked"] for r in reports),
                "faces": reports, "native_source_equivalence": False,
                "production_accepted": False}
    except StagingError:
        raise
    except Exception as error:
        raise StagingError("platform_read", "collection_reopen_failed") from error
