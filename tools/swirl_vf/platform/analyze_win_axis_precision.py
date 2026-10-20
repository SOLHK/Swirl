#!/usr/bin/env python3
"""Independently validate D1 native evidence; never certify an original TTC."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(text):
    def finite_float(token):
        value = float(token)
        require(math.isfinite(value), "Overflow/nonfinite JSON number")
        return value
    return json.loads(text, object_pairs_hook=no_duplicate_keys,
                      parse_float=finite_float,
                      parse_constant=lambda value: (_ for _ in ()).throw(EvidenceError("Nonfinite JSON: " + value)))


def load_json(path):
    return read_json(Path(path).read_text(encoding="utf-8-sig"))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def float_bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def valid_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def validate_process_header(label, header, entry=None):
    """Bind an observed process to the requested load path/backend/order.

    The Qt field is the recorded QPA backend request, not a private-engine-class
    inspection. This distinction remains explicit in the final experiment scope.
    """
    pieces = label.split("-")
    require(len(pieces) in (4, 5), "Malformed process label")
    kind, api = pieces[:2]
    require(kind in ("ordinary", "gain"), "Unknown process fixture")
    mode, order = pieces[-2:]
    require(mode in ("private", "installed") and order in ("forward", "reverse"), "Unknown process load/order")
    if api == "dwrite":
        require(len(pieces) == 4, "Malformed DirectWrite label")
        expected_mode = "system_collection" if mode == "installed" else "direct_file"
        require(header.get("load_mode") == expected_mode, "DirectWrite header load mode differs from process label")
        require(header.get("first_order") == order, "DirectWrite header order differs from process label")
    elif api == "qt":
        require(kind == "ordinary" and len(pieces) == 5 and pieces[2] in ("native", "freetype"), "Unknown Qt backend label")
        expected_mode = "system_installed" if mode == "installed" else "application_private"
        require(header.get("load_mode") == expected_mode, "Qt header load mode differs from process label")
        require(header.get("reverse") is (order == "reverse"), "Qt header order differs from process label")
        expected_qpa = "windows:fontengine=" + pieces[2]
        require(header.get("requested_qpa") == expected_qpa, "Qt header backend request differs from process label")
        if entry is not None:
            require(entry.get("platform_requested") == expected_qpa, "Harness Qt backend request differs from process label")
    else:
        raise EvidenceError("Unknown process API")
    if entry is not None:
        require(entry.get("header") == header, "Harness header snapshot differs from native JSONL")


def outline_points(operations):
    """Decode the declared D1 path grammar and reject truncated/nonfinite paths."""
    require(isinstance(operations, list) and operations, "Empty outline operation stream")
    for word in operations:
        require(type(word) is int and 0 <= word <= 0xFFFFFFFF, "Invalid path word")
    points = []
    cursor = 0
    begun = False
    while cursor < len(operations):
        require(cursor + 2 <= len(operations), "Truncated operation header")
        opcode, argument = operations[cursor:cursor + 2]
        cursor += 2
        if opcode in (1, 2):
            require(argument in (0, 1) if opcode == 1 else argument & ~3 == 0, "Invalid outline state enum")
            count = 0
        elif opcode == 3:
            require(argument in (0, 1), "Invalid BeginFigure enum")
            require(not begun, "Nested outline figure")
            begun = True
            count = 1
        elif opcode in (4, 5):
            require(begun, "Path segment outside figure")
            count = argument * (3 if opcode == 5 else 1)
        elif opcode == 6:
            require(argument in (0, 1), "Invalid EndFigure enum")
            require(begun, "EndFigure without BeginFigure")
            begun = False
            count = 0
        else:
            raise EvidenceError("Unknown outline opcode")
        require(cursor + 2 * count <= len(operations), "Truncated path coordinates")
        for _ in range(count):
            x, y = (struct.unpack("<f", struct.pack("<I", n))[0]
                    for n in operations[cursor:cursor + 2])
            require(math.isfinite(x) and math.isfinite(y), "Nonfinite native outline")
            points.append((x, y))
            cursor += 2
    require(points and not begun, "Empty or unterminated outline")
    return points


def read_log(path, expected_hash, expected_status):
    raw = Path(path).read_text(encoding="utf-8-sig")
    require(raw.endswith("\n"), "Truncated JSONL terminator")
    rows = [read_json(line) for line in raw.splitlines() if line.strip()]
    require(len(rows) >= 3, "Empty native evidence")
    require(all(isinstance(row, dict) for row in rows), "Native JSONL row is not an object")
    headers = [r for r in rows if r.get("record") == "header"]
    summaries = [r for r in rows if r.get("record") == "summary"]
    require(len(headers) == len(summaries) == 1, "Missing/duplicate native header/footer")
    require(rows[0] is headers[0] and rows[-1] is summaries[0], "Misplaced native header/footer")
    require(not any(r.get("record") == "error" for r in rows), "Native error row")
    require(headers[0].get("input_sha256") == expected_hash, "Wrong native font identity")
    require(summaries[0].get("status") == expected_status, "Native execution incomplete or failed")
    return headers[0], summaries[0], rows[1:-1]


NATIVE_FIELDS = ("api_readback", "outline", "design_metrics", "natural_placement", "raster")
NATIVE_OBSERVABLE_FIELDS = tuple(key for key in NATIVE_FIELDS if key != "api_readback")


def native_payload(row):
    return {key: row[key] for key in NATIVE_FIELDS}


def native_observables(payload):
    return {key: payload[key] for key in NATIVE_OBSERVABLE_FIELDS}


def validate_native_rasters(rasters):
    expected = {(em, dpr) for em in (16, 32) for dpr in (1, 1.25, 1.5, 2)}
    require(isinstance(rasters, list) and len(rasters) == len(expected), "Incomplete native raster matrix")
    seen = set()
    for raster in rasters:
        require(isinstance(raster, dict), "Native raster is not an object")
        key = (raster.get("em"), raster.get("dpr"))
        require(all(finite_number(v) for v in key) and key in expected and key not in seen, "Unexpected/duplicate native raster em/DPR")
        seen.add(key)
        bounds = raster.get("bounds")
        require(isinstance(bounds, list) and len(bounds) == 4 and all(type(v) is int for v in bounds), "Invalid native raster bounds")
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        require(width > 0 and height > 0 and type(raster.get("bytes")) is int
                and raster["bytes"] == width * height * 3, "Native raster bounds/byte count mismatch")
        require(valid_sha256(raster.get("sha256")), "Invalid native raster SHA256")
    require(seen == expected, "Incomplete native raster em/DPR matrix")


def validate_native_glyphs(row):
    expected_gids = [2, 3, 4, 5]
    for field in ("outline", "design_metrics", "natural_placement"):
        glyphs = row.get(field)
        require(isinstance(glyphs, list) and len(glyphs) == 4
                and all(isinstance(g, dict) and type(g.get("gid")) is int for g in glyphs)
                and [g["gid"] for g in glyphs] == expected_gids,
                "Wrong native glyph identities: " + field)
    for glyph in row["outline"]:
        outline_points(glyph["operations_u32"])
    for glyph in row["design_metrics"]:
        for name in ("advanceWidth", "leftSideBearing", "rightSideBearing", "advanceHeight",
                     "topSideBearing", "bottomSideBearing", "verticalOriginY"):
            value = glyph.get(name)
            lower, upper = (0, 0xFFFFFFFF) if name in ("advanceWidth", "advanceHeight") else (-0x80000000, 0x7FFFFFFF)
            require(type(value) is int and lower <= value <= upper, "Invalid native design metric: " + name)
    for glyph in row["natural_placement"]:
        require(glyph.get("em") == 1000 and finite_number(glyph.get("advance")) and glyph["advance"] > 0, "Invalid natural placement")
        offsets = glyph.get("offset")
        require(isinstance(offsets, list) and len(offsets) == 2 and all(finite_number(v) for v in offsets), "Invalid natural placement offset")


def validate_native_readback(values):
    require(isinstance(values, list), "Native axis readback is not an array")
    seen = set()
    for axis in values:
        require(isinstance(axis, dict), "Native axis readback entry is not an object")
        tag, value, bits = axis.get("tag"), axis.get("value"), axis.get("bits")
        require(isinstance(tag, str) and len(tag) == 4 and tag not in seen, "Duplicate/invalid native readback tag")
        require(finite_number(value) and type(bits) is int and 0 <= bits <= 0xFFFFFFFF, "Invalid native readback value")
        require(struct.unpack("<f", struct.pack("<I", bits))[0] == value, "Native readback float/bit mismatch")
        seen.add(tag)
    require({"wght", "WDTH", "HGHT"}.issubset(seen), "Missing physical axis in native readback")


def validate_native(path, font, manifest):
    header, summary, rows = read_log(path, font["sha256"], "PASS_DWRITE_SYNTHETIC")
    require(header.get("family") == font["family"] and header.get("input_bytes") == font["bytes"]
            and header.get("units_per_em") == 1000 and header.get("glyph_count") == 6, "Wrong native fixture metadata")
    require(header.get("api_axis_type") == "IEEE754_binary32", "Wrong declared native axis type")
    actual_tables = header.get("physical_table_sha256", {})
    require(all(actual_tables.get(tag) == digest for tag, digest in font["tables_sha256"].items()), "Native physical table hash differs from serialized fixture")
    cases = {c["id"]: c for c in manifest["cases"]}
    require(len(cases) == len(manifest["cases"]) and cases, "Empty/duplicate manifest case IDs")
    expected = {(case, p) for case in cases for p in range(2)}
    observed = {}
    for row in rows:
        require(row.get("record") == "observation", "Unexpected DirectWrite record")
        key = (row["case_id"], row["pass"])
        require(key in expected and key not in observed, "Unexpected/duplicate DirectWrite position")
        c = cases[key[0]]
        require(row["requested_decimal"] == c["decimal"], "Request decimal changed")
        require(row["requested"] == c["requested_binary64"], "Requested binary64 changed")
        require(row["input_float"] == c["float32"], "API float conversion changed")
        require(row["input_float_bits"] == {tag: int(bits, 16) for tag, bits in c["float32_bits_hex"].items()}, "API float bits mismatch")
        validate_native_glyphs(row)
        validate_native_readback(row["api_readback"])
        validate_native_rasters(row["raster"])
        observed[key] = row
    require(set(observed) == expected, "Incomplete native case/pass matrix")
    require(header["case_count"] == len(cases) and summary["observation_count"] == len(expected), "Native count mismatch")
    result = {case: native_payload(observed[case, 0]) for case in cases}
    require(all(result[c] == native_payload(observed[c, 1]) for c in cases), "Native reverse replay mismatch")
    require(result["pair_lo"] == result["pair_hi"], "Actual DirectWrite precision pair differs")
    for tag in ("wght", "WDTH", "HGHT"):
        require(result[tag + "_min"]["outline"] != result[tag + "_max"]["outline"], "Native axis positive control missing")
    models = manifest["predictions"][font["kind"]]
    residuals = {}
    for model in models["default"]:
        advance_errors, outline_errors = [], []
        for case, payload in result.items():
            predicted = models[case][model]
            advance_errors.append(abs(payload["natural_placement"][0]["advance"] - predicted["A_advance_unrounded"]))
            rightmost = max(x for x, _ in outline_points(payload["outline"][0]["operations_u32"]))
            outline_errors.append(abs(rightmost - predicted["A_rightmost_unrounded"]))
        residuals[model] = {"maximum_advance_error": max(advance_errors), "maximum_outline_right_error": max(outline_errors),
                            "both_within_1_32_on_frozen_cases": max(advance_errors + outline_errors) <= 1 / 32}
    selected = {}
    for case in ("pair_lo", "pair_hi", "f32_m1", "f32_p1", "low_f32_0", "low_f32_1", "low_f32_2",
                 "low_f32_3", "low_f32_4", "ramp_lo", "ramp_mid", "ramp_hi"):
        payload = result[case]
        weight_readback = next(axis for axis in payload["api_readback"] if axis["tag"] == "wght")
        selected[case] = {"requested": cases[case]["decimal"]["wght"],
                          "api_float32": cases[case]["float32"]["wght"],
                          "api_float32_bits": cases[case]["float32_bits_hex"]["wght"],
                          "api_readback_wght": weight_readback["value"],
                          "api_readback_wght_bits": f"0x{weight_readback['bits']:08x}",
                          "A_design_advance": payload["design_metrics"][0]["advanceWidth"],
                          "A_natural_advance": payload["natural_placement"][0]["advance"],
                          "A_outline_right": max(x for x, _ in outline_points(payload["outline"][0]["operations_u32"]))}
    return {"header": header, "summary": summary, "payloads": result,
            "selected": selected, "model_residuals": residuals,
            "model_scope": "Four predeclared finite hypotheses; a normalized16-before-avar match does not exclude user16 rounding followed by normalized16 rounding, and does not identify proprietary Windows internals.",
            "low_float_pair_observables_equal": native_observables(result["low_f32_1"]) == native_observables(result["low_f32_2"]),
            "low_float_pair_api_readback_equal": result["low_f32_1"]["api_readback"] == result["low_f32_2"]["api_readback"]}


QT_CASES = {"default", "pair_lo", "pair_hi", "float_prev", "float_next", "wght_min", "wght_max",
            "WDTH_min", "WDTH_max", "HGHT_min", "HGHT_max", "mixed", "automatic_600"}


def qt_case_requests():
    center = float_bits(499.006199)
    previous = struct.unpack("<f", struct.pack("<I", center - 1))[0]
    following = struct.unpack("<f", struct.pack("<I", center + 1))[0]
    values = {"default": (400, 100, 100), "automatic_600": (600, 100, 100),
              "pair_lo": (499.006199, 100, 100), "pair_hi": (499.006201, 100, 100),
              "float_prev": (previous, 100, 100), "float_next": (following, 100, 100),
              "wght_min": (100, 100, 100), "wght_max": (900, 100, 100),
              "WDTH_min": (400, 50, 100), "WDTH_max": (400, 200, 100),
              "HGHT_min": (400, 100, 50), "HGHT_max": (400, 100, 200),
              "mixed": (623.25, 137.5, 172.5)}
    return {case: dict(zip(("wght", "WDTH", "HGHT"), coordinates)) for case, coordinates in values.items()}


def validate_qt_policy(rows, header, summary):
    policies = [row for row in rows if row.get("record") == "policy_observation"]
    expected = {("automatic", dpi, dpr, weight) for dpi in (96, 144, 192)
                for dpr in (1, 1.25, 1.5, 2) for weight in (400, 600)}
    expected |= {("manual", dpi, dpr, None) for dpi in (96, 144, 192) for dpr in (1, 1.25, 1.5, 2)}
    require(len(policies) == 36 and header.get("expected_policy_checks") == 36
            and summary.get("production_policy_checks") == 36, "Incomplete Qt production-policy matrix")
    seen = set()
    for row in policies:
        mode = row.get("mode")
        key = (mode, row.get("logical_dpi"), row.get("dpr"), row.get("weight"))
        require(key in expected and key not in seen, "Unexpected/duplicate Qt production-policy position")
        require(row.get("implementation") == "existing_FontAxisPolicy_resolve", "Qt policy did not identify production resolver")
        if mode == "automatic":
            axes = {"wght": row["weight"], "WDTH": 100, "HGHT": 100}
        else:
            axes = {"wght": 623.25, "WDTH": 137.5, "HGHT": 172.5}
            require(row.get("wrong_case_wdth_rejected") is True, "Qt manual policy did not reject lowercase alias")
        require(row.get("resolved_axes") == axes, "Qt production policy changed weight/custom defaults or axis units")
        seen.add(key)
    require(seen == expected, "Incomplete Qt production-policy positions")


def validate_qt_path(path, empty_allowed=False):
    require(isinstance(path, list) and (empty_allowed or path), "Empty or invalid Qt outline")
    begun = False
    cursor = 0
    while cursor < len(path):
        element = path[cursor]
        require(isinstance(element, list) and len(element) == 3 and type(element[0]) is int
                and element[0] in (0, 1, 2, 3) and all(finite_number(v) for v in element[1:]), "Invalid Qt outline element")
        if element[0] == 0:
            begun = True
        else:
            require(begun, "Qt outline segment precedes MoveTo")
            if element[0] == 2:
                require(cursor + 2 < len(path), "Truncated Qt cubic curve")
                for extra in path[cursor + 1:cursor + 3]:
                    require(isinstance(extra, list) and len(extra) == 3 and extra[0] == 3
                            and type(extra[0]) is int and all(finite_number(v) for v in extra[1:]), "Invalid Qt cubic data")
                cursor += 2
            else:
                require(element[0] != 3, "Orphan Qt cubic data")
        cursor += 1


def validate_qt_glyphs(payload):
    glyphs = payload.get("glyphs")
    require(isinstance(glyphs, list) and len(glyphs) == 5, "Missing Qt fixture glyphs")
    for glyph, (scalar, gid) in zip(glyphs, ((65, 2), (32, 1), (66, 3), (0x4E2D, 4), (0x6587, 5))):
        require(glyph.get("codepoint") == scalar and glyph.get("gid") == gid
                and type(glyph.get("gid")) is int, "Wrong Qt codepoint/glyph identity")
        advance = glyph.get("advance_px")
        require(isinstance(advance, list) and len(advance) == 2 and all(finite_number(v) for v in advance), "Invalid Qt glyph advance")
        validate_qt_path(glyph.get("path_px"), empty_allowed=gid == 1)
        if gid == 1:
            require(glyph["path_px"] == [], "Qt space unexpectedly contains an outline")
    raster = payload.get("raster")
    require(isinstance(raster, dict) and type(raster.get("width")) is int and type(raster.get("height")) is int
            and raster["width"] > 0 and raster["height"] > 0, "Invalid Qt raster dimensions")
    ink = raster.get("ink_pixels")
    require(finite_number(ink) and int(ink) == ink and 0 < ink <= raster["width"] * raster["height"], "Blank or invalid Qt raster ink count")
    require(valid_sha256(raster.get("pixel_sha256")), "Invalid Qt raster digest")


def validate_qt(path, font, installed):
    header, summary, rows = read_log(path, font["sha256"], "PASS_QT_SYNTHETIC")
    require(header["qt_version"] == "6.10.3" and header["qpa_platform"] == "windows", "Wrong Qt platform/version")
    observations = [r for r in rows if r.get("record") == "observation"]
    cases = {r["case_id"] for r in observations}
    require(cases == QT_CASES, "Incomplete/unrecognized Qt cases")
    require(all(r.get("record") in ("observation", "pair_comparison", "policy_observation", "reload", "load_failure_control") for r in rows), "Unexpected Qt record")
    require(header.get("family") == font["family"] and header.get("input_bytes") == font["bytes"]
            and header.get("units_per_em") == 1000, "Wrong Qt fixture metadata")
    actual_tables = header.get("source_table_sha256", {})
    require(all(actual_tables.get(tag) == digest for tag, digest in font["tables_sha256"].items()), "Qt source table hash differs from serialized fixture")
    validate_qt_policy(rows, header, summary)
    passes = 2 if installed else 3
    require(header.get("pass_count") == passes and header.get("case_ids") is not None
            and set(header["case_ids"]) == cases and len(header["case_ids"]) == len(cases), "Wrong Qt declared cases/pass count")
    scenarios = {(point, dpi, dpr) for point in (9, 12, 18) for dpi in (96, 144) for dpr in (1, 1.25, 1.5, 2)}
    scenario_names = {(point, dpi, dpr): f"pt{point:g}-dpi{dpi}-dpr{dpr:g}" for point, dpi, dpr in scenarios}
    expected = {(point, dpi, dpr, case, p) for point, dpi, dpr in scenarios for case in cases for p in range(passes)}
    require(header.get("expected_observations") == len(expected), "Qt declared observation count mismatch")
    requests = qt_case_requests()
    observed = {}
    for row in observations:
        key = (row["point_size"], row["logical_dpi"], row["dpr"], row["case_id"], row["pass"])
        require(key in expected and key not in observed, "Unexpected/duplicate Qt position")
        require(row.get("scenario") == scenario_names[key[:3]], "Qt scenario name/coordinates differ")
        require(row.get("requested_decimal") == requests[row["case_id"]], "Qt frozen binary64 request changed")
        p = row["payload"]
        require(p["table_identity_exact"] is True and p["family"] == font["family"], "Qt fallback or identity failure")
        validate_qt_glyphs(p)
        for tag in ("wght", "WDTH", "HGHT"):
            actual = row["api_float32"][tag]
            require(actual["bits"] == f"0x{float_bits(row['requested_decimal'][tag]):08x}", "Qt binary32 request mismatch")
            expected_float = struct.unpack("<f", struct.pack("<f", row["requested_decimal"][tag]))[0]
            require(actual.get("value") == expected_float, "Qt float32 value/bit mismatch")
            require(p["qfont_requested_axis_storage"][tag] == actual, "Qt request storage mismatch")
        observed[key] = p
    require(set(observed) == expected, "Incomplete Qt scenario/pass matrix")
    require(summary["observations"] == len(expected), "Qt observation count mismatch")
    payloads = {k[:-1]: p for k, p in observed.items() if k[-1] == 0}
    for key, payload in observed.items():
        require(payloads[key[:-1]] == payload, "Qt exact replay mismatch")
    pair_count = len(scenarios) * passes
    comparisons = [r for r in rows if r.get("record") == "pair_comparison"]
    require(len(comparisons) == pair_count == summary["pair_comparisons"], "Qt pair comparison count mismatch")
    expected_comparisons = {(scenario, p) for scenario in scenario_names.values() for p in range(passes)}
    compared = set()
    for row in comparisons:
        key = (row.get("scenario"), row.get("pass"))
        require(key in expected_comparisons and key not in compared, "Unexpected/duplicate Qt pair comparison")
        require(all(row.get(field) is True for field in ("api_float32_equal", "raw_outline_equal", "raw_advance_equal",
                    "qfontmetrics_equal", "textlayout_equal", "raster_equal")), "Qt pair comparison reports an actual failure")
        compared.add(key)
    require(compared == expected_comparisons, "Incomplete Qt pair comparison matrix")
    for point, dpi, dpr in scenarios:
        require(payloads[point, dpi, dpr, "pair_lo"] == payloads[point, dpi, dpr, "pair_hi"], "Qt actual pair differs")
        for tag in ("wght", "WDTH", "HGHT"):
            a, b = (payloads[point, dpi, dpr, tag + suffix] for suffix in ("_min", "_max"))
            require([g["path_px"] for g in a["glyphs"]] != [g["path_px"] for g in b["glyphs"]], "Qt positive outline control missing")
            require(a["raster"] != b["raster"], "Qt positive raster control missing")
    if not installed:
        require(sum(r.get("record") == "reload" for r in rows) == 1 and summary["application_reload"] == "PASS", "Qt private reload not executed")
        controls = [r for r in rows if r.get("record") == "load_failure_control"]
        require(len(controls) == 1 and controls[0]["missing_file_rejected"] is True and controls[0]["default_family_unchanged"] is True, "Qt missing-load control absent")
    else:
        require(not any(r.get("record") in ("reload", "load_failure_control") for r in rows)
                and summary.get("application_reload") == "NOT_APPLICABLE", "Installed Qt run used private load/reload controls")
    require(summary["exact_replays"] == len(payloads) * (passes - 1), "Qt replay count mismatch")
    return {"header": header, "summary": summary, "payloads": payloads}


def analyze(directory, expected_source_sha=None):
    directory = Path(directory)
    run = load_json(directory / "windows-axis-precision-run.json")
    require(run["status"] == "PASS_SYNTHETIC_WINDOWS_EXPERIMENT", "Windows execution has not passed")
    require(run["system_installation_requested"] is True, "Full D1 analysis requires actual installation observations")
    if expected_source_sha:
        require(run["source_commit"] == expected_source_sha, "Evidence belongs to another source commit")
    manifest = load_json(directory / "fixture-manifest.json")
    require(manifest["original_synthetic"] is True, "Not the authored D1 fixture")
    require(sha256(directory / "requests.tsv") == manifest["requests_sha256"], "Case stream hash changed")
    fonts = {f["kind"]: f for f in manifest["fonts"]}
    require(set(fonts) == {"ordinary", "gain"} and len(manifest["fonts"]) == 2, "Missing/duplicate original fixture")
    expected = {f"{font}-dwrite-{mode}-{order}" for font in fonts for mode in ("private", "installed") for order in ("forward", "reverse")}
    expected |= {f"ordinary-qt-{backend}-{mode}-{order}" for backend in ("native", "freetype") for mode in ("private", "installed") for order in ("forward", "reverse")}
    entries = {r["label"]: r for r in run["runs"]}
    require(len(entries) == len(run["runs"]) == 16 and set(entries) == expected, "Incomplete/duplicate Windows process matrix")
    measurements, results = {}, {}
    for label, entry in entries.items():
        require(entry["status"] == "PASS" and entry["exit_code"] == 0 and entry["timeout"] is False, "Failed native subprocess")
        font = fonts[label.split("-", 1)[0]]
        native = "-dwrite-" in label
        file = directory / label / ("directwrite-axis-precision.jsonl" if native else "qt-axis-precision.jsonl")
        require(sha256(file) == entry["native_log"]["sha256"], "Native evidence hash changed")
        result = validate_native(file, font, manifest) if native else validate_qt(file, font, "-installed-" in label)
        validate_process_header(label, result["header"], entry)
        measurements[label] = result.pop("payloads")
        result.pop("header")
        results[label] = result
    cross_process, cross_load = {}, {}
    for label in sorted(entries):
        if not label.endswith("-forward"):
            continue
        other = label.removesuffix("forward") + "reverse"
        equal = measurements[label] == measurements[other]
        cross_process[label] = equal
        require(equal, "Independent opposite-order process mismatch: " + label)
        if "-private-" in label:
            installed = label.replace("-private-", "-installed-")
            a, b = measurements[label], measurements[installed]
            differences = [str(k) for k in a if a[k] != b.get(k)]
            cross_load[label] = {"equal": not differences and set(a) == set(b), "differing_positions": len(differences), "first_differences": differences[:5]}
    require(len(run["installations"]) == 2 and all(x["status"] == "REGISTERED" and x["cleanup"] == "PASS" for x in run["installations"]), "Installation cleanup incomplete")
    return {"schema": 1, "status": "PASS_D1_EVIDENCE_ANALYSIS", "source_commit": run["source_commit"],
            "windows_product": run["windows_product"], "windows_build": run["windows_build"],
            "dwrite_version": run["dwrite_version"], "qt_version": run["qt_sdk"], "processes": len(entries),
            "pair_decimal": ["499.006199", "499.006201"], "pair_float32": 499.006195068359375,
            "pair_float32_bits": "0x43f980cb", "actual_pair_collapsed_all_experiments": True,
            "opposite_process_replays": cross_process, "private_vs_installed": cross_load,
            "experiments": results, "original_ttc_acceptance": "NOT_RUN_NO_QUALIFIED_CANDIDATE",
            "windows11_desktop_acceptance": "NOT_RUN", "real_swirl_ui_acceptance": "NOT_RUN",
            "scope": "Frozen authored fixtures on these runtime versions; model matches do not reveal proprietary Windows internal implementation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_directory", type=Path)
    parser.add_argument("--expected-source-sha")
    args = parser.parse_args()
    output = args.evidence_directory / "d1-analysis.json"
    try:
        result = analyze(args.evidence_directory, args.expected_source_sha)
    except (EvidenceError, KeyError, TypeError, ValueError, OSError) as error:
        result = {"schema": 1, "status": "FAILED_EVIDENCE_ANALYSIS", "error": str(error),
                  "original_ttc_acceptance": "NOT_RUN"}
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
        raise SystemExit(1)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("D1_ANALYSIS " + json.dumps(result, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
