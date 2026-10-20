"""Independent transport/diagnostic tests, not a DirectWrite runtime verdict."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PLATFORM = Path(__file__).resolve().parents[1] / "platform"
sys.path.insert(0, str(PLATFORM))
import probe_directwrite_vertical_layout as probe
from experiment_vertical_gpos import original_fixture, add_adjustment


SOURCE = b"independent protocol sentinel; this is not a font or native result"
SHA = hashlib.sha256(SOURCE).hexdigest()


def literal_request():
    return {"request_id": 1, "route": "vert", "policy": "default", "direction": "V", "locale": "zh-CN",
            "text_kind": "single_han", "point_index": 0, "requested_normalized_model": [0., 0., 0.],
            "requested_user_axes": {"WDTH": 500., "wght": 400., "HGHT": 500.}}


def literal_layout():
    # Literal native-schema example authored independently of the parser. It is
    # deliberately labelled a protocol fixture and never sent to an acceptance
    # workflow as evidence that Windows ran.
    return {"type": "layout", "request_id": 1, "route": "vert", "policy": "default", "direction": "V",
        "locale": "zh-CN", "text_kind": "single_han", "requested_user_axes": {"WDTH": 500., "wght": 400., "HGHT": 500.},
        "float32_input_axes": {"WDTH": 500., "wght": 400., "HGHT": 500.},
        "layout_reported_axes": {"WDTH": 500., "wght": 400., "HGHT": 500., "wdth": 100.},
        "glyph_count": 1, "layout_metrics": {"left": 0., "top": 0., "width": 1000., "width_including_trailing_whitespace": 1000.,
            "height": 1000., "line_count": 1},
        "runs": [{"text_position": 0, "string_length": 1, "locale": "zh-CN", "baseline": [31., 47.],
            "orientation_angle": 0, "is_sideways": False, "bidi_level": 0, "measuring_mode": 0, "font_em_size": 1000.,
            "source_identity_verified": True, "physical_face_index": 0, "simulations": 0,
            "actual_face_axes": {"WDTH": 500., "wght": 400., "HGHT": 500., "wdth": 100.},
            "orientation_transform": [1., 0., 0., 1., 0., 0.],
            "local_ink_bounds": [-302., -530., -60., 50.], "layout_ink_bounds": [-271., -483., -29., 97.],
            "baseline_relative_ink_bounds": [-302., -530., -60., 50.], "cluster_map": [0],
            "glyphs": [{"gid": 4, "advance": 1000., "advance_offset": 0., "ascender_offset": 0.,
                "design_metrics": {"advance_width": 840, "advance_height": 1000, "left_side_bearing": 118,
                    "right_side_bearing": 480, "top_side_bearing": 230, "bottom_side_bearing": 230, "vertical_origin_y": 860}}]}]}


def literal_metadata():
    return {"type": "metadata", "backend": "DirectWrite_TextLayout4_TextRenderer1", "source_sha256": SHA,
        "source_bytes": len(SOURCE), "physical_face_count": 1, "glyph_count": 8, "units_per_em": 1000,
        "font_em_size_DIP": 1000, "font_family": "Swirl Original GPOS Laboratory", "custom_collection_only": True,
        "empty_fallback": True, "pixel_snapping_disabled": True,
        "Windows_version": {"major": 10, "minor": 0, "build": 26100, "product_type": 3}}


def literal_summary():
    return {"type": "summary", "status": "ALL_REQUESTED_LAYOUT_OBSERVATIONS_COMPLETE", "source_sha256": SHA,
        "request_count": 1, "glyph_count": 1, "error_count": 0, "font_file_locked_through_summary": True}


def transcript(records=None, metadata=None, summary=None):
    return "\n".join(json.dumps(row) for row in [metadata or literal_metadata(), *(records or [literal_layout()]),
                                               summary or literal_summary()]) + "\n"


class DirectWriteLayoutProtocolTests(unittest.TestCase):
    def test_request_matrix_retains_all_axes_routes_positions_and_directions(self):
        rows = probe.requests()
        self.assertEqual(len(rows), 2304)
        self.assertEqual(len({r["request_id"] for r in rows}), 2304)
        self.assertEqual(2 * sum(4 if r["text_kind"] == "mixed" else 1 for r in rows), 11520)
        self.assertEqual({r["route"] for r in rows}, {"vert", "vrt2", "vkrn"})
        self.assertEqual({r["policy"] for r in rows}, {"default", "enabled", "disabled"})
        self.assertEqual({r["direction"] for r in rows}, {"H", "V"})
        self.assertEqual({r["locale"] for r in rows}, {"zh-CN", "zh-HK"})
        self.assertEqual(len({tuple(r["requested_normalized_model"]) for r in rows}), 32)
        self.assertTrue(all(set(r["requested_user_axes"]) == {"WDTH", "wght", "HGHT"} for r in rows))

    def test_request_line_keeps_original_double_and_axis_case(self):
        request = literal_request()
        request["requested_user_axes"]["WDTH"] = 561.7283945
        self.assertEqual(probe.request_line(request).split(),
                         ["1", "V", "zh-CN", "vert", "default", "561.72839450000004", "400", "500", "single_han"])
        self.assertNotEqual(probe.float32(561.7283945), 561.7283945)
        self.assertEqual(probe.normalized_from_user({"WDTH": 500., "wght": 400., "HGHT": 500.}), (0., 0., 0.))

    def test_literal_protocol_accepts_extra_static_axis_but_checks_source_axis_case(self):
        result = probe.parse_transcript(transcript(), [literal_request()], SOURCE, 0)
        self.assertEqual(result["summary"]["request_count"], 1)
        record = literal_layout()
        del record["runs"][0]["actual_face_axes"]["WDTH"]
        with self.assertRaisesRegex(probe.ObservationError, "axis_missing"):
            probe.parse_transcript(transcript([record]), [literal_request()], SOURCE, 0)

    def test_each_actual_face_must_preserve_physical_identity_and_axes(self):
        for field, value in (("source_identity_verified", False), ("physical_face_index", 1), ("simulations", 1)):
            record = literal_layout(); record["runs"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(probe.ObservationError, "fallback_font"):
                probe.parse_transcript(transcript([record]), [literal_request()], SOURCE, 0)
        record = literal_layout(); record["runs"][0]["actual_face_axes"]["WDTH"] = 500.0000305175781
        with self.assertRaisesRegex(probe.ObservationError, "axis_missing"):
            probe.parse_transcript(transcript([record]), [literal_request()], SOURCE, 0)

    def test_metadata_requires_own_source_and_isolated_collection(self):
        for field, value in (("source_sha256", "0" * 64), ("source_bytes", 1), ("physical_face_count", 2),
                             ("glyph_count", 7), ("font_em_size_DIP", 999), ("custom_collection_only", False),
                             ("empty_fallback", False)):
            metadata = literal_metadata(); metadata[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(probe.ObservationError, "metadata_or_fixture_identity"):
                probe.parse_transcript(transcript(metadata=metadata), [literal_request()], SOURCE, 0)

    def test_summary_exit_and_unique_terminal_record_are_required(self):
        for field, value in (("request_count", 2), ("glyph_count", 2), ("source_sha256", "0" * 64),
                             ("error_count", 1), ("font_file_locked_through_summary", False)):
            summary = literal_summary(); summary[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(probe.ObservationError, "terminal_summary"):
                probe.parse_transcript(transcript(summary=summary), [literal_request()], SOURCE, 0)
        with self.assertRaisesRegex(probe.ObservationError, "nonzero_exit"):
            probe.parse_transcript(transcript(), [literal_request()], SOURCE, 8)
        with self.assertRaisesRegex(probe.ObservationError, "extra_after_summary"):
            probe.parse_transcript(transcript() + json.dumps(literal_layout()), [literal_request()], SOURCE, 0)

    def test_explicit_native_error_and_nonfinite_json_do_not_become_results(self):
        with self.assertRaisesRegex(probe.ObservationError, "native_request_error.*request_id.*1"):
            probe.parse_transcript('{"type":"request_error","request_id":1,"error":"layout_fallback"}\n',
                                   [literal_request()], SOURCE, 1)
        record = literal_layout(); record["runs"][0]["glyphs"][0]["advance"] = float("nan")
        with self.assertRaisesRegex(probe.ObservationError, "nonfinite_native_JSON"):
            probe.parse_transcript(transcript([record]), [literal_request()], SOURCE, 0)

    def test_late_record_metric_failure_rejects_whole_transcript(self):
        first, second = literal_layout(), literal_layout()
        second["request_id"] = 2
        del second["runs"][0]["glyphs"][0]["design_metrics"]["vertical_origin_y"]
        request2 = literal_request(); request2["request_id"] = 2
        summary = literal_summary(); summary.update(request_count=2, glyph_count=2)
        with self.assertRaisesRegex(probe.ObservationError, "request_2:incomplete_native_design_metrics"):
            probe.parse_transcript(transcript([first, second], summary=summary), [literal_request(), request2], SOURCE, 0)

    def test_duplicate_ranges_cannot_hide_missing_mixed_characters(self):
        record = literal_layout(); request = literal_request()
        record.update(text_kind="mixed", glyph_count=4); request["text_kind"] = "mixed"
        run = record["runs"][0]
        run["string_length"] = 2; run["cluster_map"] = [0, 1]
        run["glyphs"] = [run["glyphs"][0], copy.deepcopy(run["glyphs"][0])]
        record["runs"].append(copy.deepcopy(run))
        summary = literal_summary(); summary["glyph_count"] = 4
        with self.assertRaisesRegex(probe.ObservationError, "duplicate_text_range"):
            probe.parse_transcript(transcript([record], summary=summary), [request], SOURCE, 0)

    def test_cluster_and_layout_metric_fields_are_not_optional(self):
        record = literal_layout(); record["runs"][0]["cluster_map"] = [1]
        with self.assertRaisesRegex(probe.ObservationError, "clusters_missing"):
            probe.parse_transcript(transcript([record]), [literal_request()], SOURCE, 0)
        record = literal_layout(); del record["layout_metrics"]["height"]
        with self.assertRaisesRegex(probe.ObservationError, "incomplete_layout_metrics"):
            probe.parse_transcript(transcript([record]), [literal_request()], SOURCE, 0)


class DirectWriteLayoutDiagnosticTests(unittest.TestCase):
    def paired_examples(self):
        # Analytic protocol counterexample only: at WDTH max the authored han.vert
        # has AW 960 rather than 840, hence a 60-unit GPOS compensation. Give the
        # observed placement a +0.25 residual to prove budgets remain separate.
        rows, originals, candidates = [], [], []
        for direction in ("H", "V"):
            for point_index, width_axis in enumerate((500., 1000.)):
                request = literal_request(); request.update(request_id=len(rows)+1, direction=direction,
                    point_index=point_index, requested_normalized_model=[float(point_index), 0., 0.])
                request["requested_user_axes"]["WDTH"] = width_axis
                source = literal_layout()
                for key in ("request_id", "direction", "requested_user_axes"):
                    source[key] = copy.deepcopy(request[key])
                for key in ("float32_input_axes", "layout_reported_axes"):
                    source[key]["WDTH"] = width_axis
                source["runs"][0]["actual_face_axes"]["WDTH"] = width_axis
                glyph = source["runs"][0]["glyphs"][0]
                glyph["gid"] = 4 if direction == "V" else 2
                glyph["design_metrics"]["advance_width"] = (840+120*point_index if direction == "V" else 1000+200*point_index)
                if direction == "H":
                    glyph["advance"] = glyph["design_metrics"]["advance_width"]
                box = source["runs"][0]["baseline_relative_ink_bounds"]
                if direction == "V":
                    box[0] -= 60*point_index; box[2] -= 60*point_index
                candidate = copy.deepcopy(source)
                if direction == "V" and point_index:
                    candidate["runs"][0]["baseline_relative_ink_bounds"][0] += 60.25
                    candidate["runs"][0]["baseline_relative_ink_bounds"][2] += 60.25
                    candidate["runs"][0]["glyphs"][0]["ascender_offset"] = 60.25
                rows.append(request); originals.append(source); candidates.append(candidate)
        return rows, originals, candidates

    def test_encoded_gpos_and_real_layout_residual_have_distinct_budgets(self):
        rows, original_records, candidate_records = self.paired_examples()
        original, symbols = original_fixture("even")
        candidate, failures = add_adjustment(original, symbols, "vert")
        self.assertEqual(failures, [])
        result = probe.compare_route({"records": original_records}, {"records": candidate_records}, candidate, symbols, rows, "vert")
        self.assertFalse(result["default_single_han_compensation_within_1_over_32"])
        self.assertTrue(result["default_single_han_compensation_within_reconstruction_1_FUnit"])
        stat = result["policies"]["default"]["V"]["single_han_fixed_origin_X_error_from_source_default"]
        self.assertEqual(stat["max_abs_error"], .25)
        self.assertEqual(stat["above_1_over_32"], 1)
        self.assertEqual(stat["above_reconstruction_1_FUnit"], 0)
        self.assertEqual(result["default_mixed_text_fixed_origin_acceptance"], "NOT_ESTABLISHED_BY_SINGLE_GLYPH_BOUNDS")
        self.assertEqual(result["contracts"]["default_horizontal_layout_unchanged"]["failures"], 0)

    def test_ignored_gpos_remains_a_large_failed_compensation_observation(self):
        rows, original_records, _ = self.paired_examples()
        original, symbols = original_fixture("even")
        candidate, _ = add_adjustment(original, symbols, "vert")
        result = probe.compare_route({"records": original_records}, {"records": copy.deepcopy(original_records)},
                                     candidate, symbols, rows, "vert")
        stat = result["policies"]["default"]["V"]["single_han_fixed_origin_X_error_from_source_default"]
        self.assertEqual(stat["max_abs_error"], 60.)
        self.assertFalse(result["default_single_han_compensation_within_reconstruction_1_FUnit"])
        self.assertFalse(result["internal_normalized_coordinates_observed"])

    def test_ignored_axis_with_constant_bounds_cannot_look_like_compensation(self):
        rows, original_records, _ = self.paired_examples()
        for first, varied in ((original_records[0], original_records[1]), (original_records[2], original_records[3])):
            varied["runs"][0]["glyphs"] = copy.deepcopy(first["runs"][0]["glyphs"])
            varied["runs"][0]["baseline_relative_ink_bounds"] = first["runs"][0]["baseline_relative_ink_bounds"].copy()
        original, symbols = original_fixture("even")
        candidate, _ = add_adjustment(original, symbols, "vert")
        result = probe.compare_route({"records": original_records}, {"records": copy.deepcopy(original_records)},
                                     candidate, symbols, rows, "vert")
        self.assertEqual(result["policies"]["default"]["V"]["single_han_fixed_origin_X_error_from_source_default"]["max_abs_error"], 0.)
        self.assertFalse(result["native_default_layout_advance_model_within_reconstruction_1_FUnit"])
        self.assertFalse(result["default_single_han_compensation_within_reconstruction_1_FUnit"])

    @unittest.skipIf(os.name == "nt", "native Windows observations are exercised by the native CI job")
    def test_non_windows_driver_never_claims_native_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "not_run.json"
            with mock.patch.object(probe.subprocess, "run") as native, \
                    mock.patch.object(probe.platform, "platform", return_value="unit_test_host"):
                result = probe.run(Path(tmp) / "missing.exe", path)
                native.assert_not_called()
            self.assertEqual(result["status"], "NOT_RUN")
            self.assertEqual(result["completed_layout_calls"], 0)
            self.assertFalse(result["all_declared_observations_complete"])
            self.assertEqual(json.loads(path.read_text())["windows_11_acceptance"], "NOT_RUN")
            with self.assertRaisesRegex(probe.ObservationError, "runtime_unavailable"):
                probe.run(Path(tmp) / "missing.exe", Path(tmp) / "required.json", True)

    @unittest.skipIf(os.name == "nt" or shutil.which("g++") is None, "non-Windows compiler scope check only")
    def test_non_windows_native_stub_compiles_and_returns_not_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "native-layout-stub"
            result = subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                     str(PLATFORM / "directwrite_vertical_layout.cpp"), "-o", str(binary)],
                                    capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(result.returncode, 77)
            self.assertEqual(json.loads(result.stdout)["status"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
