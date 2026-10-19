#!/usr/bin/env python3
"""Bounded CoreText metric diagnosis using only original synthetic test fonts.

This does not replace or relax test_coretext_extract.py. It records deviations
from its unchanged 1/32 FUnit analytical budget for the gvar-only fixture, an
equivalent HVAR/VVAR fixture, and statically instantiated copies. A completed
diagnosis is not an acceptance pass. No Apple font or original private outline
is read. The unchanged Swift oracle measures every variant in a fresh process.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTCollection, newTable
from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import buildVarIdxMap
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.varLib.varStore import OnlineVarStoreBuilder, VarStoreInstancer

from test_coretext_extract import make_fixture, normalized

LIMIT = 1 / 32
TAGS = ("WDTH", "wght", "HGHT")
CASES = [
    ("all_min", {"WDTH": 1., "wght": 100., "HGHT": 1.}),
    ("default", {"WDTH": 500., "wght": 400., "HGHT": 500.}),
    ("all_max", {"WDTH": 1000., "wght": 900., "HGHT": 1000.}),
    ("height_min", {"WDTH": 500., "wght": 400., "HGHT": 1.}),
    ("height_max", {"WDTH": 500., "wght": 400., "HGHT": 1000.}),
    ("weight_min", {"WDTH": 500., "wght": 100., "HGHT": 500.}),
    ("fractional_a", {"WDTH": 631.25, "wght": 523.75, "HGHT": 711.125}),
    ("fractional_b", {"WDTH": 631.25, "wght": 523.875, "HGHT": 711.125}),
]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_location(location):
    return {"WDTH": normalized(location["WDTH"], 1, 500, 1000),
            "wght": normalized(location["wght"], 100, 400, 900),
            "HGHT": normalized(location["HGHT"], 1, 500, 1000)}


def ideal_metrics(location, gid):
    x, w, y = (normalized_location(location)[tag] for tag in TAGS)
    cross = max(0., x) * max(0., y)
    if gid == 0:
        advance, height, top, bounds = 550., 1000., 820., (50., 0., 500., 700.)
    elif gid == 1:
        advance, height, top, bounds = 400., 1000., 820., (0., 0., 0., 0.)
    else:
        advance, height, top = 700 + 100*x + 30*w + 10*cross, 1000 + 150*y, 820 + 60*y
        bounds = (100 + 20*x, 0., 450 + 90*x + 60*w + 20*cross, 600 + 180*y)
    return {"advance_width": advance, "advance_height": height,
            "vertical_origin_x": advance / 2, "vertical_origin_y": top,
            "horizontal_origin_x": 0., "horizontal_origin_y": 0., "lsb": bounds[0],
            "x_min": bounds[0], "y_min": bounds[1], "x_max": bounds[2], "y_max": bounds[3]}


def add_metric_tables(font):
    """Add standard metrics for exactly the original fixture's gvar model.

    Keep its original gvar phantom data as required for TrueType outlines. The
    added side-bearing deltas use glyf control bounds, not geometric extrema.
    VVAR.VOrgMap remains absent: that mapping is for CFF2 vertical origins.
    """
    supports = []
    for tag in TAGS:
        supports.extend([{tag: (0., 1., 1.)}, {tag: (-1., -1., 0.)}])
    supports.append({"WDTH": (0., 1., 1.), "HGHT": (0., 1., 1.)})
    metrics = {
        "HVAR": {"AdvWidthMap": [100, -100, 30, -30, 0, 0, 10],
                 "LsbMap": [20, -20, 0, 0, 0, 0, 0],
                 "RsbMap": [0, 0, -30, 30, 0, 0, -10]},
        "VVAR": {"AdvHeightMap": [0, 0, 0, 0, 150, -150, 0],
                 "TsbMap": [0, 0, 0, 0, -120, 120, 0],
                 "BsbMap": [0, 0, 0, 0, 90, -90, 0]},
    }
    for tag, mappings in metrics.items():
        store = OnlineVarStoreBuilder(list(TAGS))
        store.setSupports(supports)
        zero = store.storeDeltas([0] * len(supports))
        table = getattr(otTables, tag)()
        table.Version = 0x00010000
        for field, deltas in mappings.items():
            variable = store.storeDeltas(deltas)
            setattr(table, field, buildVarIdxMap([zero, zero, variable], font.getGlyphOrder()))
        if tag == "VVAR":
            table.VOrgMap = None
        table.VarStore = store.finish()
        font[tag] = newTable(tag)
        font[tag].table = table


def make_metric_fixture(source, destination):
    collection = TTCollection(source)
    for font in collection.fonts:
        add_metric_tables(font)
        font.recalcTimestamp = False
    collection.save(destination, shareTables=True)
    collection.close()


def verify_metric_fixture(source, modified):
    """Verify serialized metric variation coefficients independently of CoreText."""
    original, variant = TTCollection(source, lazy=True), TTCollection(modified, lazy=True)
    checked = 0
    max_error = 0.
    try:
        for face, (base, font) in enumerate(zip(original.fonts, variant.fonts)):
            for tag in base.reader.keys():
                a, b = base.reader[tag], font.reader[tag]
                if tag == "head":
                    a, b = a[:8] + b"\0"*4 + a[12:], b[:8] + b"\0"*4 + b[12:]
                require(a == b, f"metric fixture changed original face {face} table {tag}")
            points = [dict(zip(TAGS, p)) for p in itertools.product((-1., 0., 1.), repeat=3)]
            points += [normalized_location(location) for _, location in CASES[-2:]]
            for point in points:
                x, w, y = (point[tag] for tag in TAGS)
                cross = max(0., x) * max(0., y)
                expectations = {
                    "HVAR": {"AdvWidthMap": 100*x + 30*w + 10*cross,
                             "LsbMap": 20*x, "RsbMap": -30*w - 10*cross},
                    "VVAR": {"AdvHeightMap": 150*y, "TsbMap": -120*y, "BsbMap": 90*y},
                }
                for tag, fields in expectations.items():
                    table = font[tag].table
                    instancer = VarStoreInstancer(table.VarStore, font["fvar"].axes, point)
                    for field, expected in fields.items():
                        mapping = getattr(table, field).mapping
                        for gid, name in enumerate(font.getGlyphOrder()):
                            actual = float(instancer[mapping[name]])
                            error = abs(actual - (expected if gid == 2 else 0.))
                            max_error = max(max_error, error)
                            require(error < 1e-9, f"non-equivalent {tag}/{field} face {face} gid {gid} at {point}")
                            checked += 1
        return {"status": "PASS_STANDARD_TABLE_COEFFICIENT_CHECK_ONLY", "checks": checked,
                "max_error_font_units": max_error,
                "original_tables_unchanged_except_head_checksum": True,
                "native_acceptance": "NOT_ESTABLISHED"}
    finally:
        original.close(); variant.close()


def make_static_fixture(source, destination, location):
    collection = TTCollection(source)
    for index, font in enumerate(collection.fonts):
        static = instantiateVariableFont(font, location, inplace=False)
        static.recalcTimestamp = False
        require("fvar" not in static and "gvar" not in static, "static instance retained variation axes")
        collection.fonts[index] = static
    collection.save(destination, shareTables=True)
    collection.close()


def static_table_metrics(font, gid):
    name = font.getGlyphOrder()[gid]
    glyph = font["glyf"][name]
    glyph.recalcBounds(font["glyf"])
    width, left = font["hmtx"].metrics[name]
    height, top_bearing = font["vmtx"].metrics[name]
    glyph_set = font.getGlyphSet()
    pen = BoundsPen(glyph_set)
    glyph_set[name].draw(pen)
    bounds = pen.bounds or (0., 0., 0., 0.)
    require(glyph.xMin - left == 0, "static fixture unexpectedly changed horizontal origin")
    return {"advance_width": width, "advance_height": height,
            "vertical_origin_x": width / 2, "vertical_origin_y": glyph.yMax + top_bearing,
            "horizontal_origin_x": 0., "horizontal_origin_y": 0., "lsb": bounds[0],
            "x_min": bounds[0], "y_min": bounds[1], "x_max": bounds[2], "y_max": bounds[3]}


def measured_fields(result):
    require(result.get("error") is None, f"CoreText glyph failure: {result}")
    bounds = result["bounds"]
    values = {field: result[field] for field in ("advance_width", "advance_height", "vertical_origin_x",
              "vertical_origin_y", "horizontal_origin_x", "horizontal_origin_y", "lsb")}
    values.update(x_min=bounds[0], y_min=bounds[1], x_max=bounds[0]+bounds[2], y_max=bounds[1]+bounds[3])
    require(all(isinstance(v, (int, float)) and math.isfinite(v) for v in values.values()), "nonfinite measurement")
    return values


def comparison(actual, expected):
    differences = {field: actual[field] - value for field, value in expected.items()}
    return {"expected": expected, "signed_error_font_units": differences,
            "within_unchanged_1_over_32_budget": all(abs(e) <= LIMIT for e in differences.values()),
            "failing_fields": [field for field, error in differences.items() if abs(error) > LIMIT]}


def inferred_prediction(location, upm):
    """Post-hoc hypothesis from prior native records, never a measurement fix."""
    ideal = ideal_metrics(location, 2)
    top = math.floor(ideal["vertical_origin_y"] + .5)
    bottom = math.floor(ideal["vertical_origin_y"] - ideal["advance_height"] + .5)
    advance = math.floor(ideal["advance_width"] + .5)
    fixed_em_width = math.floor(advance / upm * 65536) * upm / 65536
    fixed_em_height = math.floor((top - bottom) / upm * 65536) * upm / 65536
    return {"advance_width": fixed_em_width, "advance_height": math.floor(fixed_em_height),
            "vertical_origin_y": top}


def native_measurements(binary, font, requests, output, label):
    request_text = "".join(json.dumps(r) + "\n" for r in requests)
    (output / f"{label}.requests.jsonl").write_text(request_text, encoding="utf-8")
    start = time.monotonic()
    result = subprocess.run([str(binary), str(font)], input=request_text,
                            capture_output=True, text=True, timeout=180)
    (output / f"{label}.responses.jsonl").write_text(result.stdout, encoding="utf-8")
    (output / f"{label}.stderr.log").write_text(result.stderr, encoding="utf-8")
    require(result.returncode == 0, f"{label}: extractor exit {result.returncode}")
    rows = [json.loads(line) for line in result.stdout.splitlines() if line]
    require(rows and rows[0].get("type") == "metadata", f"{label}: missing metadata")
    metadata = rows[0]
    require(metadata.get("source_sha256") == digest(font), f"{label}: source SHA mismatch")
    require(metadata.get("backend") == "CoreText", f"{label}: not a CoreText measurement")
    faces = metadata.get("faces", [])
    require(len(faces) == 2 and all(face.get("status") == "identity_verified" and face.get("face_index") == i
            and face.get("upm") == (1000, 1128)[i] for i, face in enumerate(faces)),
            f"{label}: physical face verification failed")
    expected = {(r["request_id"], gid): r for r in requests for gid in r["glyph_ids"]}
    records = {}
    for row in rows:
        if "glyph_id" not in row:
            continue
        key = (row["request_id"], row["glyph_id"])
        require(key in expected and key not in records, f"{label}: unexpected/duplicate glyph response")
        request = expected[key]
        require(row.get("face_index") == request["face_index"] and row.get("location") == request["location"],
                f"{label}: request/response mismatch")
        measured_fields(row)
        records[key] = row
    require(set(records) == set(expected), f"{label}: missing glyph measurements")
    return records, {"label": label, "metadata": metadata, "duration_seconds": time.monotonic() - start,
                     "native_exit_code": result.returncode, "response_count": len(records),
                     "raw_response_file": f"{label}.responses.jsonl"}


def observe_variant(binary, font, cases, variant, output, report, *, static=False):
    requests, meaning = [], {}
    for case, location in cases:
        for face in range(2):
            request_id = f"{variant}:{case}:face{face}"
            requests.append({"request_id": request_id, "face_index": face,
                             "location": {} if static else location, "glyph_ids": [0, 1, 2]})
            meaning[request_id] = (case, location)
    label = variant if not static else f"static-{cases[0][0]}"
    rows, execution = native_measurements(binary, font, requests, output, label)
    report["executions"].append(execution)
    tables = TTCollection(font) if static else None
    try:
        for (request_id, gid), row in rows.items():
            case, location = meaning[request_id]
            actual = measured_fields(row)
            observation = {"variant": variant, "case": case, "face_index": row["face_index"],
                           "glyph_id": gid, "original_user_location": location,
                           "measured": actual, "source_sha256": execution["metadata"]["source_sha256"],
                           "versus_ideal_analytic_model": comparison(actual, ideal_metrics(location, gid))}
            if tables is not None:
                baseline = static_table_metrics(tables.fonts[row["face_index"]], gid)
                observation["versus_serialized_static_font"] = comparison(actual, baseline)
                observation["static_encoding_quantization"] = comparison(baseline, ideal_metrics(location, gid))
            elif variant == "gvar_only" and gid == 2 and case != "default":
                predicted = inferred_prediction(location, (1000, 1128)[row["face_index"]])
                observation["inferred_prior_quantization_hypothesis"] = {
                    "inference_only_not_correction": True, "prediction": predicted,
                    "signed_error": {key: actual[key] - value for key, value in predicted.items()}}
            report["observations"].append(observation)
    finally:
        if tables is not None:
            tables.close()


def summarize(report):
    output = {}
    for observation in report["observations"]:
        summary = output.setdefault(observation["variant"], {"glyph_observations": 0,
                                    "observations_outside_original_budget": 0, "max_absolute_error_by_field": {}})
        summary["glyph_observations"] += 1
        compare = observation["versus_ideal_analytic_model"]
        summary["observations_outside_original_budget"] += not compare["within_unchanged_1_over_32_budget"]
        for field, error in compare["signed_error_font_units"].items():
            summary["max_absolute_error_by_field"][field] = max(summary["max_absolute_error_by_field"].get(field, 0.), abs(error))
        if "versus_serialized_static_font" in observation:
            summary["static_measurements_outside_serialized_font_budget"] = summary.get("static_measurements_outside_serialized_font_budget", 0) + (
                not observation["versus_serialized_static_font"]["within_unchanged_1_over_32_budget"])
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    report_path = out / "coretext_metric_diagnosis.json"
    require(not report_path.exists(), "choose a new diagnostic output directory")
    report = {"schema_version": 1, "status": "NOT_RUN", "platform": platform.platform(),
              "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "data_origin": "self_authored_synthetic_fonts_only_no_Apple_data",
              "native_original_font_acceptance": "NOT_RUN", "windows_acceptance": "NOT_RUN",
              "production_oracle_modified": False, "production_reconstruction_modified": False,
              "original_strict_test_replaced": False, "analytical_tolerance_font_units": LIMIT,
              "diagnosis_is_not_acceptance": True, "executions": [], "observations": [],
              "inferred_hypothesis": "Nondefault gvar-only CoreText metrics may round design phantoms to integers, then truncate normalized EM metrics to 16.16; vertical advances may undergo another integer truncation. This is a hypothesis inferred from previous records, not a correction.",
              "static_reference_policy": "Compare static instances both with the exact analytical variable model and their own serialized integer geometry/metrics; neither comparison changes the original budget.",
              "source_code_sha256": {p.name: digest(p) for p in (Path(__file__).resolve(),
                  Path(__file__).with_name("test_coretext_extract.py"), Path(__file__).with_name("coretext_extract.swift"))}}
    code = 1
    try:
        with tempfile.TemporaryDirectory(prefix="synthetic-coretext-diagnosis-", dir=out) as temporary:
            temp = Path(temporary)
            source, mapped = temp / "gvar-only.ttc", temp / "equivalent-hvar-vvar.ttc"
            make_fixture(source)
            make_metric_fixture(source, mapped)
            report["variable_fixture_sha256"] = digest(source)
            report["metric_fixture_sha256"] = digest(mapped)
            report["standard_metric_equivalence"] = verify_metric_fixture(source, mapped)
            if sys.platform != "darwin":
                report["reason"] = "CoreText is unavailable on this runtime; only standard table equivalence was checked."
                code = 2 if args.require_native else 0
            else:
                binary = args.binary.resolve() if args.binary else out / "coretext_extract"
                if args.binary is None:
                    swiftc = shutil.which("swiftc")
                    require(bool(swiftc), "swiftc unavailable")
                    compiled = subprocess.run([swiftc, "-O", str(Path(__file__).with_name("coretext_extract.swift")),
                                               "-o", str(binary)], capture_output=True, text=True, timeout=180)
                    (out / "swift_compile.log").write_text(compiled.stdout + compiled.stderr, encoding="utf-8")
                    require(compiled.returncode == 0, "unchanged Swift oracle compilation failed")
                require(binary.is_file(), "CoreText oracle executable is missing")
                report["oracle_binary_sha256"] = digest(binary)
                observe_variant(binary, source, CASES, "gvar_only", out, report)
                observe_variant(binary, mapped, CASES, "equivalent_hvar_vvar", out, report)
                for case, location in CASES:
                    static = temp / f"static-{case}.ttc"
                    make_static_fixture(source, static, location)
                    observe_variant(binary, static, [(case, location)], "static_instance", out, report, static=True)
                report["status"] = "DIAGNOSTIC_COMPLETE_NOT_ACCEPTANCE"
                report["summary"] = summarize(report)
                code = 0
        report["temporary_synthetic_fonts_removed"] = True
    except Exception as error:
        report["status"] = "DIAGNOSTIC_ERROR"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["ended_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(report_path)}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
