"""Original geometry and actual corruptions for the strict C1 structure gate."""
import copy
import io
from pathlib import Path
import sys
import struct
import tempfile
import unittest
from unittest import mock
import weakref

from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.otlLib.builder import buildStatTable
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.instancer import instantiateVariableFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from metric_variations import add_metric_variations
from ttc_staging_contract import StagingError
from ttc_staging_validate import face_contract, validate_face, validate_collection
import ttc_staging_validate as validation


def make_font(index=0):
    """Five hand-authored GIDs; no Apple or other font's outline data."""
    order = [".notdef", "space", "A", "B", "uni4E2D"]
    glyphs = {}
    for gid, name in enumerate(order):
        pen = TTGlyphPen(None)
        if gid > 1:
            pen.moveTo((20, 0))
            pen.lineTo((240 + gid * 10, 0))
            pen.qCurveTo((300, 200), (240, 500))
            pen.lineTo((20, 500))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({0x20: "space", 65: "A", 66: "B", 0x4E2D: "uni4E2D"})
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (300 + gid * 20, 0 if gid <= 1 else 20)
                                    for gid, name in enumerate(order)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupVerticalMetrics({name: (1000, 800 if gid <= 1 else 300) for gid, name in enumerate(order)})
    builder.setupVerticalHeader(ascent=500, descent=-500)
    family = f"C1 Original Shape {index}"
    builder.setupNameTable({"familyName": family, "styleName": "Regular",
                            "uniqueFontIdentifier": family, "fullName": family,
                            "psName": family.replace(" ", "")})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200,
                     usWeightClass=500, usWidthClass=5)
    builder.setupPost()
    builder.setupMaxp()
    builder.setupFvar([("WDTH", 1, 500, 1000, "Width"), ("wght", 100, 500, 900, "Weight"),
                       ("HGHT", 1, 500, 1000, "Height")],
                      [{"location": {"WDTH": 500, "wght": 700, "HGHT": 500},
                        "stylename": "Strong", "postscriptfontname": family.replace(" ", "") + "-Strong"}])
    font = builder.font
    buildStatTable(font, [{"tag": tag, "name": label, "values": [{"value": 500, "name": "Default", "flags": 2}]}
                         for tag, label in (("WDTH", "Width"), ("wght", "Weight"), ("HGHT", "Height"))])
    font["gvar"] = newTable("gvar")
    font["gvar"].version = 1
    font["gvar"].reserved = 0
    font["gvar"].variations = {}
    for gid, name in enumerate(order):
        points, _, _ = glyphs[name].getCoordinates(font["glyf"])
        deltas = [(0 if p[0] == 20 else 20, 0) for p in points]
        deltas += [(0, 0), (40, 0), (0, 0), (0, 0)]
        vertical = [(0, 0 if p[1] == 0 else 40) for p in points]
        vertical += [(0, 0), (0, 0), (0, 50), (0, -50)]
        font["gvar"].variations[name] = [TupleVariation({"WDTH": (0, 1, 1)}, deltas),
                                        TupleVariation({"HGHT": (0, 1, 1)}, vertical)]
    avar = font["avar"] = newTable("avar")
    avar.majorVersion, avar.minorVersion = 1, 0
    avar.segments = {tag: {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0} for tag in ("WDTH", "wght", "HGHT")}
    add_metric_variations(font)
    addOpenTypeFeaturesFromString(font, """
        languagesystem DFLT dflt;
        languagesystem hani ZHT;
        feature locl { script hani; language ZHT; sub A by B; } locl;
        feature kern { pos A B -30; } kern;
        table GDEF { GlyphClassDef [A B uni4E2D], [], [], [space]; } GDEF;
    """)
    uvs = CmapSubtable.newSubtable(14)
    uvs.platformID, uvs.platEncID, uvs.language = 0, 5, 0xFF
    uvs.cmap = {}
    uvs.uvsDict = {0xFE00: [(65, None), (0x4E2D, "B")]}
    font["cmap"].tables.append(uvs)
    font["name"].setName(f"原创 C1 {index}", 1, 3, 1, 0x804)
    font.recalcTimestamp = False
    font["head"].created = font["head"].modified = 3800000000
    stream = io.BytesIO()
    font.save(stream)
    stream.seek(0)
    return TTFont(stream, recalcTimestamp=False)


class TtcStagingValidateTests(unittest.TestCase):
    def setUp(self):
        self.font = make_font()

    def tearDown(self):
        self.font.close()

    def rejects(self, category, code, change):
        change(self.font)
        with self.assertRaises(StagingError) as caught:
            validate_face(self.font)
        self.assertEqual(caught.exception.category, category)
        self.assertEqual(caught.exception.code, code)

    def test_complete_original_face_including_empty_gids_and_uvs(self):
        report = validate_face(self.font)
        self.assertEqual(report["glyphs_checked"], 5)
        self.assertEqual(report["gvar_tuples_checked"], 10)
        self.assertEqual(report["metric_models_checked"], 10)
        self.assertGreater(report["layout_glyph_references_checked"], 0)
        self.assertFalse(report["production_accepted"])

    def test_reopen_contract_and_mixed_axis_interpolation(self):
        contract = face_contract(self.font)
        data = io.BytesIO()
        self.font.save(data)
        data.seek(0)
        with TTFont(data, recalcTimestamp=False) as actual:
            validate_face(actual, contract)
            static = instantiateVariableFont(actual, {"WDTH": 750, "wght": 700, "HGHT": 750}, inplace=False)
            self.assertEqual(static.getGlyphID("A"), 2)
            self.assertEqual(static["hmtx"].metrics["A"][0], 360)
            self.assertEqual(static["vmtx"].metrics["A"][0], 1050)

    def test_contract_has_only_safe_digests_not_names_or_character_maps(self):
        contract = face_contract(self.font)
        self.assertNotIn("glyph_order", contract)
        self.assertNotIn("cmap", contract)
        self.assertNotIn("C1 Original", str(contract))
        self.assertEqual(set(contract["table_sha256"]), set(self.font.keys()) - {"GlyphOrder"})

    def test_contract_read_does_not_recalculate_timestamp(self):
        expected = face_contract(self.font)
        modified = self.font["head"].modified
        self.font.recalcTimestamp = True
        self.assertEqual(face_contract(self.font), expected)
        self.assertEqual(self.font["head"].modified, modified)
        self.assertTrue(self.font.recalcTimestamp)

    def test_original_axis_order_rejected(self):
        self.rejects("input_axis", "original_axis_tags_or_order_changed",
                     lambda f: f["fvar"].axes.reverse())

    def test_original_axis_tag_rejected(self):
        self.rejects("input_axis", "original_axis_tags_or_order_changed",
                     lambda f: setattr(f["fvar"].axes[0], "axisTag", "wdth"))

    def test_nonfinite_axis_range_rejected(self):
        self.rejects("input_axis", "axis_range_invalid",
                     lambda f: setattr(f["fvar"].axes[0], "maxValue", float("nan")))

    def test_out_of_range_named_instance_rejected(self):
        self.rejects("input_axis", "instance_coordinate_invalid",
                     lambda f: f["fvar"].instances[0].coordinates.update(wght=901))

    def test_nonmonotone_avar_rejected(self):
        self.rejects("input_axis", "avar_not_monotone",
                     lambda f: f["avar"].segments["WDTH"].update({0.5: 0.75, 0.75: 0.5}))

    def test_avar_missing_default_rejected(self):
        self.rejects("input_axis", "avar_required_anchors",
                     lambda f: f["avar"].segments["WDTH"].pop(0.0))

    def test_name_all_localizations_bound_by_contract(self):
        contract = face_contract(self.font)
        self.font["name"].setName("Different Localized", 1, 3, 1, 0x804)
        with self.assertRaises(StagingError) as caught:
            validate_face(self.font, contract)
        self.assertEqual(caught.exception.code, "face_contract_mismatch")

    def test_invalid_postscript_name_rejected(self):
        self.rejects("font_tables", "postscript_name_invalid",
                     lambda f: f["name"].setName("Bad Name", 6, 3, 1, 0x409))

    def test_weight_and_width_class_range(self):
        self.rejects("font_tables", "weight_or_width_class",
                     lambda f: setattr(f["OS/2"], "usWidthClass", 10))

    def test_maxp_glyph_count_rejected(self):
        self.rejects("font_tables", "maxp_glyph_count", lambda f: setattr(f["maxp"], "numGlyphs", 4))

    def test_missing_glyf_gid_rejected(self):
        self.rejects("outline", "glyf_gid_coverage", lambda f: f["glyf"].glyphs.pop("B"))

    def test_cmap_references_nonexistent_gid(self):
        self.rejects("font_tables", "cmap_glyph_reference",
                     lambda f: f["cmap"].tables[0].cmap.update({65: "missing"}))

    def test_unicode_cmap_conflict(self):
        def change(font):
            table = [t for t in font["cmap"].tables if t.isUnicode() and t.format != 14][-1]
            table.cmap = dict(table.cmap)
            table.cmap[65] = "B"
        self.rejects("font_tables", "unicode_cmap_conflict", change)

    def test_loca_corruption_cannot_be_hidden_by_recompilation(self):
        self.rejects("font_tables", "loca_offsets",
                     lambda f: f["loca"].locations.__setitem__(2, 0xFFFFFFF0))

    def test_stat_axis_mapping_rejected(self):
        self.rejects("input_axis", "stat_axis_mapping",
                     lambda f: setattr(f["STAT"].table.DesignAxisRecord.Axis[0], "AxisTag", "wdth"))

    def test_stat_value_axis_index_rejected(self):
        self.rejects("input_axis", "stat_axis_index",
                     lambda f: setattr(f["STAT"].table.AxisValueArray.AxisValue[0], "AxisIndex", 9))

    def test_uvs_bad_glyph_reference(self):
        self.rejects("font_tables", "cmap_uvs_glyph_reference",
                     lambda f: next(t for t in f["cmap"].tables if t.format == 14).uvsDict.update({0xFE00: [(65, "missing")]}))

    def test_uvs_duplicate_codepoint(self):
        self.rejects("font_tables", "cmap_uvs_duplicate",
                     lambda f: next(t for t in f["cmap"].tables if t.format == 14).uvsDict.update({0xFE00: [(65, None), (65, "B")]}))

    def test_uvs_default_without_base(self):
        self.rejects("font_tables", "default_uvs_base_missing",
                     lambda f: next(t for t in f["cmap"].tables if t.format == 14).uvsDict.update({0xFE00: [(0x1234, None)]}))

    def test_gvar_point_count_includes_all_four_phantoms(self):
        self.rejects("outline", "gvar_point_count_including_phantoms",
                     lambda f: f["gvar"].variations["A"][0].coordinates.pop())

    def test_gvar_unknown_axis(self):
        self.rejects("input_axis", "gvar_unknown_axis",
                     lambda f: f["gvar"].variations["A"][0].axes.update(XXXX=(0, 1, 1)))

    def test_gvar_nonrepresentable_support(self):
        self.rejects("input_axis", "variation_support_invalid",
                     lambda f: f["gvar"].variations["A"][0].axes.update(WDTH=(0, 0.1, 1)))

    def test_gvar_noninteger_delta(self):
        self.rejects("outline", "gvar_delta_invalid",
                     lambda f: f["gvar"].variations["A"][0].coordinates.__setitem__(0, (0.5, 0)))

    def test_gvar_tuple_count_cannot_overflow_twelve_bit_field(self):
        self.rejects("outline", "gvar_tuple_count",
                     lambda f: f["gvar"].variations.update(A=[f["gvar"].variations["A"][0]] * 4096))

    def test_serialized_gvar_glyph_count_corruption(self):
        stream = io.BytesIO()
        self.font.save(stream)
        stream.seek(0)
        with TTFont(stream, lazy=True) as font:
            offset = font.reader.tables["gvar"].offset
            data = bytearray(stream.getvalue())
        struct.pack_into(">H", data, offset + 12, 4)
        with TTFont(io.BytesIO(data), lazy=True) as corrupted:
            with self.assertRaises(StagingError) as caught:
                validate_face(corrupted)
        self.assertEqual(caught.exception.code, "gvar_header_axis_or_glyph_count")

    def test_serialized_gvar_offset_corruption(self):
        stream = io.BytesIO()
        self.font.save(stream)
        stream.seek(0)
        with TTFont(stream, lazy=True) as font:
            offset = font.reader.tables["gvar"].offset
            data = bytearray(stream.getvalue())
        flags = struct.unpack_from(">H", data, offset + 14)[0]
        width = 4 if flags & 1 else 2
        struct.pack_into(">I" if width == 4 else ">H", data, offset + 20 + 5 * width,
                         0xFFFFFFFF if width == 4 else 65535)
        with TTFont(io.BytesIO(data), lazy=True) as corrupted:
            with self.assertRaises(StagingError) as caught:
                validate_face(corrupted)
        self.assertEqual(caught.exception.code, "gvar_offsets")

    def test_layout_feature_variations_require_remapping(self):
        self.rejects("font_tables", "layout_feature_variations_not_admitted",
                     lambda f: setattr(f["GSUB"].table, "FeatureVariations", otTables.FeatureVariations()))

    def test_incomplete_horizontal_metrics(self):
        self.rejects("metrics", "metric_gid_coverage", lambda f: f["hmtx"].metrics.pop("space"))

    def test_negative_advance(self):
        self.rejects("metrics", "metric_value_invalid", lambda f: f["vmtx"].metrics.update(A=(-1, 300)))

    def test_hvar_corrupt_region_index(self):
        self.rejects("metrics", "variation_region_index",
                     lambda f: f["HVAR"].table.VarStore.VarData[0].VarRegionIndex.__setitem__(0, 99))

    def test_vvar_corrupt_map_index(self):
        self.rejects("metrics", "variation_index_out_of_range",
                     lambda f: f["VVAR"].table.AdvHeightMap.mapping.update(A=0x12340000))

    def test_metric_coefficients_must_equal_gvar(self):
        self.rejects("metrics", "gvar_metric_coefficients_differ",
                     lambda f: f["HVAR"].table.VarStore.VarData[0].Item[0].__setitem__(0, 41))

    def test_metric_region_axis_count(self):
        self.rejects("metrics", "variation_region_count",
                     lambda f: setattr(f["HVAR"].table.VarStore.VarRegionList, "RegionAxisCount", 2))

    def test_gsub_bad_glyph_reference(self):
        self.rejects("font_tables", "layout_glyph_reference",
                     lambda f: f["GSUB"].table.LookupList.Lookup[0].SubTable[0].mapping.update(A="missing"))

    def test_gpos_bad_pair_glyph_reference(self):
        self.rejects("font_tables", "layout_glyph_reference",
                     lambda f: setattr(f["GPOS"].table.LookupList.Lookup[0].SubTable[0].PairSet[0].PairValueRecord[0], "SecondGlyph", "missing"))

    def test_layout_bad_feature_lookup(self):
        self.rejects("font_tables", "feature_lookup_index",
                     lambda f: f["GSUB"].table.FeatureList.FeatureRecord[0].Feature.LookupListIndex.__setitem__(0, 99))

    def test_serialized_lazy_layout_cannot_hide_out_of_range_glyphs(self):
        # fontTools accepts the synthetic glyph65534 spelling as a numeric
        # ushort when compiling. It is still outside this five-GID font. This
        # therefore corrupts actual serialized layout bytes without relying on
        # a mock or an ordinary unknown string that the compiler would reject.
        for tag in ("GSUB", "GPOS", "GDEF"):
            with self.subTest(table=tag):
                font = make_font()
                if tag == "GSUB":
                    font[tag].table.LookupList.Lookup[0].SubTable[0].mapping["A"] = "glyph65534"
                elif tag == "GPOS":
                    font[tag].table.LookupList.Lookup[0].SubTable[0].PairSet[0].PairValueRecord[0].SecondGlyph = "glyph65534"
                else:
                    font[tag].table.GlyphClassDef.classDefs["glyph65534"] = 1
                data = io.BytesIO()
                font.save(data)
                font.close()
                data.seek(0)
                with TTFont(data, lazy=True, recalcTimestamp=False) as corrupted:
                    self.assertEqual(len(corrupted.getGlyphOrder()), 5)
                    with self.assertRaises(StagingError) as caught:
                        validate_face(corrupted)
                    self.assertEqual(caught.exception.category, "font_tables")
                    self.assertEqual(caught.exception.code, "layout_glyph_reference")

    def test_layout_reference_coverage_is_equal_for_lazy_and_eager_reads(self):
        data = io.BytesIO()
        self.font.save(data)
        original = data.getvalue()
        reports = []
        for lazy in (False, True):
            with TTFont(io.BytesIO(original), lazy=lazy, recalcTimestamp=False) as actual:
                reports.append(validate_face(actual))
        self.assertEqual(reports[0]["layout_glyph_references_checked"],
                         reports[1]["layout_glyph_references_checked"])
        self.assertGreater(reports[1]["layout_glyph_references_checked"], 2)

    def test_unmapped_gdef_variation_store_is_rejected(self):
        self.rejects("font_tables", "unmapped_layout_variation_store",
                     lambda f: setattr(f["GDEF"].table, "VarStore", copy.deepcopy(f["HVAR"].table.VarStore)))

    def test_vorg_is_not_a_glyf_origin_fix(self):
        def add_vorg(font):
            table = font["VORG"] = newTable("VORG")
            table.majorVersion, table.minorVersion, table.defaultVertOriginY = 1, 0, 800
            table.VOriginRecords = {"A": 800}
        self.rejects("metrics", "vorg_not_admitted_for_glyf", add_vorg)

    def test_missing_required_table_is_not_silently_skipped(self):
        self.rejects("font_tables", "required_tables_missing", lambda f: f.__delitem__("STAT"))

    def test_collection_32_faces_preserves_independent_regional_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "original-only.ttc"
            collection = TTCollection()
            for index in range(32):
                font = make_font(index)
                for table in font["cmap"].tables:
                    if table.format != 14 and index % 2:
                        table.cmap[65] = "B"
                # Freeze each complete standalone face after the regional map
                # edit; contracts bind those bytes, not a dirty reader's old
                # backing bytes paired with a newly edited in-memory cmap.
                standalone = Path(tmp) / f"face-{index}.ttf"
                font.save(standalone)
                font.close()
                collection.fonts.append(TTFont(standalone, recalcTimestamp=False))
            contracts = [face_contract(font) for font in collection.fonts]
            collection.save(path, shareTables=True)
            report = validate_collection(path, contracts)
            self.assertEqual((report["faces_checked"], report["glyphs_checked"]), (32, 160))
            collection.close()

    def test_collection_face_swap_and_duplicate_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "original-only.ttc"
            first, second = make_font(0), make_font(1)
            expected = [face_contract(first), face_contract(second)]
            collection = TTCollection()
            collection.fonts = [second, first]
            collection.save(path)
            with self.assertRaises(StagingError) as caught:
                validate_collection(path, expected)
            self.assertEqual(caught.exception.code, "face_contract_mismatch")
            with self.assertRaises(StagingError) as caught:
                validate_collection(path, [expected[0], expected[0]])
            self.assertEqual(caught.exception.code, "duplicate_face_identity")
            collection.close()

    def test_collection_releases_decoded_face_before_opening_next_face(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "original-only.ttc"
            collection = TTCollection()
            collection.fonts = [make_font(index) for index in range(3)]
            expected = [face_contract(font) for font in collection.fonts]
            collection.save(path)
            collection.close()
            opened, previous_alive = [], []
            original = validation.TTFont

            def observe(*args, **kwargs):
                # No collection here: bounded face lifetime is the checker's
                # responsibility, including cycles in lazy variation readers.
                previous_alive.append(sum(reference() is not None for reference in opened))
                font = original(*args, **kwargs)
                opened.append(weakref.ref(font))
                return font

            with mock.patch.object(validation, "TTFont", side_effect=observe):
                report = validate_collection(path, expected)
            self.assertEqual(report["faces_checked"], 3)
            self.assertEqual(previous_alive, [0, 0, 0])
            self.assertTrue(all(reference() is None for reference in opened))


if __name__ == "__main__":
    unittest.main()
