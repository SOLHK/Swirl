"""Portable tests of authored fixtures and numeric discriminators, never Windows.

Native observations are produced by the separate D1 Windows workflow.  These
tests cannot certify DirectWrite, Qt, system installation or the Apple font.
"""
from __future__ import annotations

from decimal import Decimal
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import make_win_axis_precision_fixture as fixture
import analyze_win_axis_precision as evidence


class WindowsAxisPrecisionFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temporary.name)
        cls.manifest = fixture.write_fixture(cls.directory / "first")
        cls.cases = {case["id"]: case for case in cls.manifest["cases"]}

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_requested_pair_is_distinct_binary64_but_collides_binary32(self):
        lo, hi = self.cases["pair_lo"], self.cases["pair_hi"]
        self.assertNotEqual(lo["requested_binary64"]["wght"], hi["requested_binary64"]["wght"])
        self.assertNotEqual(lo["binary64_hex"]["wght"], hi["binary64_hex"]["wght"])
        for case in (lo, hi):
            self.assertEqual(case["float32_bits_hex"]["wght"], "0x43f980cb")
            self.assertEqual(case["float32"]["wght"], 499.006195068359375)
            self.assertEqual(case["nearest_16_16"]["wght"], 32702870)
        self.assertEqual(self.manifest["pair_float32_ulp"], 1 / 32768)

    def test_low_controls_distinguish_float32_from_user_fixed16(self):
        lo, hi = self.cases["low_f32_1"], self.cases["low_f32_2"]
        self.assertNotEqual(lo["float32"]["wght"], hi["float32"]["wght"])
        self.assertEqual(lo["nearest_16_16"]["wght"], 6553601)
        self.assertEqual(hi["nearest_16_16"]["wght"], 6553601)
        for case in (lo, hi):
            self.assertEqual(Decimal(case["decimal"]["wght"]), Decimal.from_float(case["float32"]["wght"]))
        models = self.manifest["predictions"]["gain"]
        self.assertGreater(abs(models[lo["id"]]["binary32_continuous"]["A_advance_unrounded"]
                               - models[hi["id"]]["binary32_continuous"]["A_advance_unrounded"]), 4.99)
        self.assertEqual(models[lo["id"]]["binary32_user16_continuous"],
                         models[hi["id"]]["binary32_user16_continuous"])

    def test_tsv_preserves_cases_order_original_decimal_and_uppercase_tags(self):
        path = self.directory / "first" / "requests.tsv"
        content = path.read_text(encoding="ascii")
        rows = content.splitlines()
        self.assertEqual(rows[0], "id\twght\tWDTH\tHGHT")
        self.assertEqual(len(rows), len(self.manifest["cases"]) + 1)
        self.assertEqual(len(self.cases), len(self.manifest["cases"]))
        for line, case in zip(rows[1:], self.manifest["cases"]):
            fields = line.split("\t")
            self.assertEqual(fields[0], case["id"])
            self.assertEqual(fields[1:], [case["decimal"][tag] for tag, *_ in fixture.AXES])
            self.assertTrue(all(math.isfinite(float(value)) for value in fields[1:]))
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), self.manifest["requests_sha256"])

    def test_all_outputs_are_deterministic(self):
        fixture.write_fixture(self.directory / "second")
        for filename in ("ordinary.ttf", "gain.ttf", "manifest.json", "requests.tsv"):
            self.assertEqual((self.directory / "first" / filename).read_bytes(),
                             (self.directory / "second" / filename).read_bytes(), filename)

    def test_sfnt_checksum_and_manifest_font_hashes(self):
        for info in self.manifest["fonts"]:
            content = (self.directory / "first" / info["file"]).read_bytes()
            self.assertEqual(len(content), info["bytes"])
            self.assertEqual(hashlib.sha256(content).hexdigest(), info["sha256"])
            padded = content + b"\0" * (-len(content) % 4)
            self.assertEqual(sum(struct.unpack(">" + "I" * (len(padded) // 4), padded)) & 0xFFFFFFFF,
                             0xB1B0AFBA)

    def test_serialized_font_identity_cmap_axes_and_stat(self):
        for info in self.manifest["fonts"]:
            with TTFont(self.directory / "first" / info["file"], checkChecksums=2) as font:
                self.assertEqual(font.getGlyphOrder(), list(fixture.GLYPHS))
                self.assertEqual(font.getBestCmap(), fixture.CMAP)
                self.assertEqual(font["name"].getDebugName(16), info["family"])
                self.assertEqual(font["name"].getDebugName(17), "Regular")
                self.assertEqual([axis.axisTag for axis in font["fvar"].axes], ["wght", "WDTH", "HGHT"])
                self.assertEqual([(axis.minValue, axis.defaultValue, axis.maxValue)
                                  for axis in font["fvar"].axes],
                                 [(axis[1], axis[2], axis[3]) for axis in fixture.AXES])
                self.assertEqual(font["STAT"].table.DesignAxisCount, 3)
                self.assertEqual(font["STAT"].table.AxisValueCount, 5)
                self.assertEqual(font["OS/2"].version, 4)
                self.assertEqual(font["head"].unitsPerEm, 1000)
                self.assertTrue({"fvar", "avar", "gvar", "HVAR", "STAT"}.issubset(font.keys()))

    def test_avar_maps_are_legal_monotone_exact_f2dot14(self):
        for info in self.manifest["fonts"]:
            with TTFont(self.directory / "first" / info["file"]) as font:
                for mapping in font["avar"].segments.values():
                    points = sorted(mapping.items())
                    self.assertEqual(mapping[-1], -1)
                    self.assertEqual(mapping[0], 0)
                    self.assertEqual(mapping[1], 1)
                    self.assertTrue(all(x0 < x1 and y0 <= y1 for (x0, y0), (x1, y1) in zip(points, points[1:])))
                    self.assertTrue(all(value * 16384 == int(value * 16384) for point in points for value in point))
                if info["kind"] == "gain":
                    self.assertEqual(font["avar"].segments["wght"], fixture.GAIN_MAP)

    def test_gvar_phantom_advance_and_hvar_encode_same_deltas(self):
        for info in self.manifest["fonts"]:
            with TTFont(self.directory / "first" / info["file"]) as font:
                hvar = font["HVAR"].table
                self.assertIsNone(hvar.AdvWidthMap)
                self.assertEqual(hvar.VarStore.VarDataCount, 1)
                data = hvar.VarStore.VarData[0]
                self.assertEqual(len(data.Item), len(fixture.GLYPHS))
                self.assertEqual(data.VarRegionIndex, list(range(6)))
                for glyph_id, name in enumerate(fixture.GLYPHS):
                    coordinates, _, _ = font["glyf"][name].getCoordinates(font["glyf"])
                    variations = font["gvar"].variations[name]
                    self.assertEqual(len(variations), 6)
                    for region_id, variation in enumerate(variations):
                        self.assertEqual(len(variation.coordinates), len(coordinates) + 4)
                        self.assertEqual(variation.coordinates[-4], (0, 0))
                        self.assertEqual(variation.coordinates[-3], (data.Item[glyph_id][region_id], 0))
                        self.assertEqual(variation.coordinates[-2:], [(0, 0), (0, 0)])

    def test_all_three_axes_change_real_serialized_geometry(self):
        for info in self.manifest["fonts"]:
            samples = info["serialized_control_samples"]
            default = samples["wght_default"]
            self.assertEqual(default["A_advance"], info["base_A_advance"])
            self.assertEqual(default["A_bounds"], (60, 0, info["base_A_rightmost"], 700))
            for tag in ("wght", "WDTH", "HGHT"):
                self.assertNotEqual(samples[tag + "_min"]["A_bounds"], default["A_bounds"])
                self.assertNotEqual(samples[tag + "_max"]["A_bounds"], default["A_bounds"])
            self.assertEqual(samples["HGHT_min"]["A_advance"], default["A_advance"])
            self.assertEqual(samples["HGHT_max"]["A_advance"], default["A_advance"])

    def test_saved_static_instances_have_expected_control_metrics_and_bounds(self):
        for info in self.manifest["fonts"]:
            for case_id in ("default", "wght_min", "wght_max", "WDTH_min", "WDTH_max", "HGHT_min", "HGHT_max", "mixed_min", "mixed_max"):
                with self.subTest(font=info["kind"], case=case_id):
                    with TTFont(self.directory / "first" / info["file"], recalcTimestamp=False) as font:
                        instance = instantiateVariableFont(font, self.cases[case_id]["float32"], inplace=False)
                        path = self.directory / "static.ttf"
                        instance.save(path)
                        instance.close()
                    with TTFont(path) as static:
                        expected = self.manifest["predictions"][info["kind"]][case_id]["binary32_continuous"]
                        self.assertEqual(static["hmtx"].metrics["A"][0], expected["A_advance_unrounded"])
                        glyph_set = static.getGlyphSet()
                        pen = BoundsPen(glyph_set)
                        glyph_set["A"].draw(pen)
                        self.assertEqual(pen.bounds[2], expected["A_rightmost_unrounded"])
                        self.assertEqual(pen.bounds[3], expected["A_top_unrounded"])
                        self.assertTrue(all(advance >= 0 for advance, _ in static["hmtx"].metrics.values()))

    def test_gain_predeclared_models_are_observably_distinct(self):
        prediction = self.manifest["predictions"]["gain"]["pair_lo"]
        self.assertAlmostEqual(prediction["binary32_continuous"]["A_advance_unrounded"], 18820, places=6)
        self.assertEqual(prediction["binary32_normalize16_before_avar"]["A_advance_unrounded"], 19000)
        self.assertEqual(prediction["binary32_normalize14_before_avar"]["A_advance_unrounded"], 16000)
        neighbor = self.manifest["predictions"]["gain"]["f32_p1"]
        self.assertAlmostEqual(neighbor["binary32_continuous"]["A_advance_unrounded"]
                               - prediction["binary32_continuous"]["A_advance_unrounded"], 12, places=6)

    def test_generated_manifest_does_not_claim_native_or_original_acceptance(self):
        saved = json.loads((self.directory / "first" / "manifest.json").read_text())
        self.assertTrue(saved["original_synthetic"])
        self.assertEqual(saved["windows_native_results"], "NOT_RUN")
        self.assertEqual(saved["original_apple_acceptance"], "NOT_RUN")
        self.assertIn("not native outputs", saved["numeric_model_scope"])
        self.assertTrue(any("abstract fixture marks" in item for item in saved["limits"]))


class WindowsAxisPrecisionEvidenceTests(unittest.TestCase):
    """Reject broken evidence before any native-result claim is constructed.

    Small parser envelopes exercise rejection paths. They are intentionally
    incomplete observations and are never advertised as fake passing native
    reports or used to establish a Windows numerical result.
    """

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def _write_log(self, rows, terminated=True):
        path = self.directory / "native.jsonl"
        path.write_text("\n".join(json.dumps(row, allow_nan=False) for row in rows)
                        + ("\n" if terminated else ""), encoding="utf-8")
        return path

    def _envelope(self):
        return [{"record": "header", "input_sha256": "a" * 64},
                {"record": "observation"},
                {"record": "summary", "status": "TEST_ENVELOPE_ONLY"}]

    def test_json_rejects_duplicate_keys_at_any_depth(self):
        for text in ('{"record":"header","record":"summary"}',
                     '{"a":{"sha256":"x","sha256":"y"}}'):
            with self.subTest(text=text), self.assertRaises(evidence.EvidenceError):
                evidence.read_json(text)

    def test_json_rejects_nonfinite_literals_and_numeric_overflow(self):
        for token in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999"):
            with self.subTest(token=token), self.assertRaises(evidence.EvidenceError):
                evidence.read_json('{"nested":[{"advance":' + token + '}]}')

    def test_json_keeps_distinct_original_pair_and_case_sensitive_axes(self):
        parsed = evidence.read_json('{"lo":499.006199,"hi":499.006201,"WDTH":100,"wdth":88}')
        self.assertNotEqual(parsed["lo"], parsed["hi"])
        self.assertEqual(parsed["WDTH"], 100)
        self.assertEqual(parsed["wdth"], 88)

    def test_read_log_rejects_truncated_eof_even_with_complete_last_json(self):
        path = self._write_log(self._envelope(), terminated=False)
        with self.assertRaisesRegex(evidence.EvidenceError, "terminator"):
            evidence.read_log(path, "a" * 64, "TEST_ENVELOPE_ONLY")

    def test_read_log_rejects_missing_duplicated_or_misplaced_boundaries(self):
        header, observation, summary = self._envelope()
        for label, rows in (
                ("missing_footer", [header, observation, observation]),
                ("duplicate_header", [header, header, observation, summary]),
                ("duplicate_footer", [header, observation, summary, summary]),
                ("misplaced_header", [observation, header, summary]),
                ("misplaced_footer", [header, summary, observation])):
            with self.subTest(label=label), self.assertRaises(evidence.EvidenceError):
                evidence.read_log(self._write_log(rows), "a" * 64, "TEST_ENVELOPE_ONLY")

    def test_read_log_rejects_wrong_identity_failed_footer_and_error_rows(self):
        header, observation, summary = self._envelope()
        for label, rows, expected_hash in (
                ("wrong_font", [header, observation, summary], "b" * 64),
                ("failure", [header, observation, {"record": "summary", "status": "FAILED"}], "a" * 64),
                ("native_error", [header, {"record": "error", "error": "probe failed"}, summary], "a" * 64)):
            with self.subTest(label=label), self.assertRaises(evidence.EvidenceError):
                evidence.read_log(self._write_log(rows), expected_hash, "TEST_ENVELOPE_ONLY")

    def test_read_log_rejects_non_object_records_without_uncaught_attribute_error(self):
        header, _, summary = self._envelope()
        for row in ([], None, "observation", 0, True):
            with self.subTest(row=row), self.assertRaises(evidence.EvidenceError):
                evidence.read_log(self._write_log([header, row, summary]), "a" * 64, "TEST_ENVELOPE_ONLY")

    @staticmethod
    def _triangle_stream():
        z = fixture.float32_bits(0)
        o = fixture.float32_bits(1)
        return [1, 1, 2, 0, 3, 0, z, z, 4, 2, o, z, z, o, 6, 1]

    def test_outline_decoder_reads_exact_float_coordinates(self):
        self.assertEqual(evidence.outline_points(self._triangle_stream()), [(0, 0), (1, 0), (0, 1)])

    def test_outline_decoder_rejects_incomplete_or_nonfinite_native_operations(self):
        z = fixture.float32_bits(0)
        cases = [[], [3], [7, 0], [6, 1], [4, 1, z, z],
                 [3, 0, z, z], [3, 0, z, z, 3, 0, z, z, 6, 1],
                 [3, 0, z, z, 5, 1, z, z, 6, 1],
                 [3, 0, 0x7FC00000, z, 6, 1], [3, 0, z, 0x7F800000, 6, 1],
                 [3, 0, True, z, 6, 1], [3, 0, -1, z, 6, 1],
                 [3, 0, 2**32, z, 6, 1], [3, 0, 0.0, z, 6, 1]]
        for operations in cases:
            with self.subTest(operations=operations), self.assertRaises(evidence.EvidenceError):
                evidence.outline_points(operations)

    def test_outline_decoder_rejects_invalid_directwrite_enum_values(self):
        for index in (1, 3, 5, 15):
            operations = self._triangle_stream()
            operations[index] = 99
            with self.subTest(argument_index=index), self.assertRaises(evidence.EvidenceError):
                evidence.outline_points(operations)

    def test_empty_native_observation_set_and_qt_matrix_are_rejected(self):
        font = {"sha256": "a" * 64}
        empty = [{"record": "header", "input_sha256": font["sha256"]},
                 {"record": "summary", "status": "PASS_DWRITE_SYNTHETIC"}]
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_native(self._write_log(empty), font, {"cases": []})
        partial = [{"record": "header", "input_sha256": font["sha256"],
                    "qt_version": "6.10.3", "qpa_platform": "windows"},
                   {"record": "observation", "case_id": "default"},
                   {"record": "summary", "status": "PASS_QT_SYNTHETIC"}]
        with self.assertRaises(evidence.EvidenceError):
            evidence.validate_qt(self._write_log(partial), font, installed=True)

    def test_analyzer_rejects_empty_missing_and_duplicate_process_matrix(self):
        manifest = fixture.write_fixture(self.directory / "fixtures")
        (self.directory / "fixture-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (self.directory / "requests.tsv").write_bytes((self.directory / "fixtures" / "requests.tsv").read_bytes())
        # Labels alone are sufficient for this rejection gate; no fabricated
        # font measurement or PASS payload is constructed.
        labels = [f"{font}-dwrite-{mode}-{order}"
                  for font in ("ordinary", "gain")
                  for mode in ("private", "installed") for order in ("forward", "reverse")]
        labels += [f"ordinary-qt-{backend}-{mode}-{order}"
                   for backend in ("native", "freetype")
                   for mode in ("private", "installed") for order in ("forward", "reverse")]
        for label, chosen in (("empty", []), ("missing", labels[:-1]),
                              ("duplicate", labels[:-1] + [labels[0]])):
            report = {"status": "PASS_SYNTHETIC_WINDOWS_EXPERIMENT", "system_installation_requested": True,
                      "source_commit": "a" * 40, "runs": [{"label": name} for name in chosen]}
            (self.directory / "windows-axis-precision-run.json").write_text(json.dumps(report), encoding="utf-8")
            with self.subTest(label=label), self.assertRaisesRegex(evidence.EvidenceError, "process matrix"):
                evidence.analyze(self.directory, "a" * 40)

    def test_process_header_cannot_substitute_load_order_or_qt_backend(self):
        native = {"load_mode": "direct_file", "first_order": "forward"}
        evidence.validate_process_header("ordinary-dwrite-private-forward", native)
        for label in ("ordinary-dwrite-installed-forward", "ordinary-dwrite-private-reverse"):
            with self.subTest(label=label), self.assertRaises(evidence.EvidenceError):
                evidence.validate_process_header(label, native)
        qt = {"load_mode": "application_private", "reverse": False, "requested_qpa": "windows:fontengine=native"}
        evidence.validate_process_header("ordinary-qt-native-private-forward", qt)
        for label in ("ordinary-qt-native-installed-forward", "ordinary-qt-native-private-reverse",
                      "ordinary-qt-freetype-private-forward"):
            with self.subTest(label=label), self.assertRaises(evidence.EvidenceError):
                evidence.validate_process_header(label, qt)
        with self.assertRaisesRegex(evidence.EvidenceError, "Harness header snapshot"):
            evidence.validate_process_header("ordinary-dwrite-private-forward", native, {"header": {}})
        with self.assertRaisesRegex(evidence.EvidenceError, "Harness Qt backend"):
            evidence.validate_process_header("ordinary-qt-native-private-forward", qt,
                                             {"header": qt, "platform_requested": "windows:fontengine=freetype"})

    def test_native_metric_and_placement_gids_cannot_be_reordered(self):
        for field in ("outline", "design_metrics", "natural_placement"):
            row = {key: [{"gid": gid} for gid in (2, 3, 4, 5)]
                   for key in ("outline", "design_metrics", "natural_placement")}
            row[field][0]["gid"] = 5
            with self.subTest(field=field), self.assertRaisesRegex(evidence.EvidenceError, "glyph identities: " + field):
                evidence.validate_native_glyphs(row)

    def test_native_raster_matrix_rejects_duplicate_dpr_wrong_size_or_digest(self):
        rasters = [{"em": em, "dpr": dpr, "bounds": [0, 0, 1, 1], "bytes": 3, "sha256": "a" * 64}
                   for em in (16, 32) for dpr in (1, 1.25, 1.5, 2)]
        evidence.validate_native_rasters(rasters)
        variants = []
        duplicate = copy.deepcopy(rasters); duplicate[-1] = duplicate[0]; variants.append(duplicate)
        wrong_bytes = copy.deepcopy(rasters); wrong_bytes[0]["bytes"] = 4; variants.append(wrong_bytes)
        bad_hash = copy.deepcopy(rasters); bad_hash[0]["sha256"] = "z" * 64; variants.append(bad_hash)
        empty_bounds = copy.deepcopy(rasters); empty_bounds[0]["bounds"] = [0, 0, 0, 1]; variants.append(empty_bounds)
        variants.append(rasters[:-1])
        for index, value in enumerate(variants):
            with self.subTest(variant=index), self.assertRaises(evidence.EvidenceError):
                evidence.validate_native_rasters(value)

    def test_native_readback_cannot_hide_duplicate_tags_or_inconsistent_bits(self):
        values = [{"tag": tag, "value": value, "bits": fixture.float32_bits(value)}
                  for tag, value in (("wght", 400), ("WDTH", 100), ("HGHT", 100))]
        evidence.validate_native_readback(values)
        duplicate = copy.deepcopy(values); duplicate[-1] = duplicate[0]
        inconsistent = copy.deepcopy(values); inconsistent[0]["bits"] += 1
        for variant in ([], values[:-1], duplicate, inconsistent, [None]):
            with self.subTest(variant=variant), self.assertRaises(evidence.EvidenceError):
                evidence.validate_native_readback(variant)

    def test_low_pair_rendering_comparison_does_not_include_api_readback(self):
        first = {key: [] for key in evidence.NATIVE_FIELDS}
        second = copy.deepcopy(first)
        first["api_readback"] = [{"tag": "wght", "value": 100}]
        second["api_readback"] = [{"tag": "wght", "value": 100.0000152587890625}]
        self.assertNotEqual(first, second)
        self.assertEqual(evidence.native_observables(first), evidence.native_observables(second))
        second["natural_placement"] = [{"advance": 1}]
        self.assertNotEqual(evidence.native_observables(first), evidence.native_observables(second))

    def test_qt_policy_rejects_missing_duplicate_alias_and_changed_values(self):
        rows = []
        for dpi in (96, 144, 192):
            for dpr in (1, 1.25, 1.5, 2):
                for weight in (400, 600):
                    rows.append({"record": "policy_observation", "mode": "automatic", "weight": weight,
                                 "logical_dpi": dpi, "dpr": dpr, "resolved_axes": {"wght": weight, "WDTH": 100, "HGHT": 100},
                                 "implementation": "existing_FontAxisPolicy_resolve"})
                rows.append({"record": "policy_observation", "mode": "manual", "logical_dpi": dpi, "dpr": dpr,
                             "resolved_axes": {"wght": 623.25, "WDTH": 137.5, "HGHT": 172.5},
                             "wrong_case_wdth_rejected": True, "implementation": "existing_FontAxisPolicy_resolve"})
        header, summary = {"expected_policy_checks": 36}, {"production_policy_checks": 36}
        evidence.validate_qt_policy(rows, header, summary)
        duplicate = copy.deepcopy(rows); duplicate[-1] = duplicate[0]
        alias = copy.deepcopy(rows); alias[2]["resolved_axes"]["wdth"] = 88
        wrong_weight = copy.deepcopy(rows); wrong_weight[1]["resolved_axes"]["wght"] = 400
        for variant in ([], rows[:-1], duplicate, alias, wrong_weight):
            with self.subTest(length=len(variant)), self.assertRaises(evidence.EvidenceError):
                evidence.validate_qt_policy(variant, header, summary)

    def test_qt_path_rejects_orphan_curve_data_and_nonfinite_coordinates(self):
        evidence.validate_qt_path([[0, 0, 0], [1, 1, 0], [1, 0, 1], [1, 0, 0]])
        evidence.validate_qt_path([], empty_allowed=True)
        for path in ([], [[1, 0, 0]], [[0, 0, 0], [3, 1, 1]],
                     [[0, 0, 0], [2, 1, 1], [3, 2, 2]],
                     [[0, 0, 0], [1, float("nan"), 1]], [[0, 0, 0], [9, 1, 1]]):
            with self.subTest(path=path), self.assertRaises(evidence.EvidenceError):
                evidence.validate_qt_path(path)


if __name__ == "__main__":
    unittest.main()
