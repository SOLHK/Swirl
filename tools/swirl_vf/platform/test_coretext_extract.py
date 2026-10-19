#!/usr/bin/env python3
"""Native oracle regression using an original, generated test font (no Apple data).

On macOS this compiles and executes the Swift extractor and compares its measured
paths and metrics with analytically defined three-axis fixture geometry. On other
systems it records NOT RUN, never a native test pass. --require-native fails if
CoreText cannot execute.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, newTable
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables._t_r_a_k import TrackData, TrackTableEntry


def make_fixture(path: Path) -> None:
    """Two TTC faces, one quadratic glyph, one blank; nonzero trak is intentional."""
    fonts = []
    for index, upm in enumerate((1000, 1128)):
        builder = FontBuilder(upm, isTTF=True)
        order = [".notdef", "space", "probe"]
        builder.setupGlyphOrder(order)
        builder.setupCharacterMap({32: "space", 65: "probe"})
        glyphs = {}
        pen = TTGlyphPen(None)
        pen.moveTo((50, 0)); pen.lineTo((500, 0)); pen.lineTo((500, 700)); pen.lineTo((50, 700)); pen.closePath()
        glyphs[".notdef"] = pen.glyph()
        glyphs["space"] = TTGlyphPen(None).glyph()
        pen = TTGlyphPen(None)
        pen.moveTo((100, 0)); pen.lineTo((400, 0)); pen.qCurveTo((500, 300), (400, 600)); pen.lineTo((100, 600)); pen.closePath()
        glyphs["probe"] = pen.glyph()
        builder.setupGlyf(glyphs)
        builder.setupHorizontalMetrics({".notdef": (550, 50), "space": (400, 0), "probe": (700, 100)})
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupVerticalMetrics({".notdef": (1000, 120), "space": (1000, 820), "probe": (1000, 220)})
        builder.setupVerticalHeader(ascent=500, descent=-500)
        builder.setupNameTable({"familyName": f"Swirl Native Oracle Fixture {index}", "styleName": "Regular",
                                "uniqueFontIdentifier": f"SwirlNativeOracleFixture-{index}-1",
                                "fullName": f"Swirl Native Oracle Fixture {index} Regular",
                                "psName": f"SwirlNativeOracleFixture{index}-Regular", "version": "Version 1.0"})
        builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, sTypoLineGap=0, usWinAscent=1000, usWinDescent=300)
        builder.setupPost()
        axes = [("WDTH", 1, 500, 1000, "Width"), ("wght", 100, 400, 900, "Weight"), ("HGHT", 1, 500, 1000, "Height")]
        builder.setupFvar(axes, [])
        builder.font["fvar"].axes[0].flags = builder.font["fvar"].axes[2].flags = 1
        avar = newTable("avar")
        avar.segments = {tag: {-1.0: -1.0, 0.0: 0.0, 1.0: 1.0} for tag, *_ in axes}
        builder.font["avar"] = avar
        coordinates, _, _ = glyphs["probe"].getCoordinates(builder.font["glyf"])
        width = [(int(x * .2), 0) for x, y in coordinates] + [(0, 0), (100, 0), (0, 0), (0, 0)]
        height = [(0, int(y * .3)) for x, y in coordinates] + [(0, 0), (0, 0), (0, 60), (0, -90)]
        weight = [(0 if x == 100 else 60, 0) for x, y in coordinates] + [(0, 0), (30, 0), (0, 0), (0, 0)]
        mixed = [(0 if x == 100 else 20, 0) for x, y in coordinates] + [(0, 0), (10, 0), (0, 0), (0, 0)]
        variations = []
        for tag, deltas in [("WDTH", width), ("wght", weight), ("HGHT", height)]:
            variations.append(TupleVariation({tag: (0, 1, 1)}, deltas))
            variations.append(TupleVariation({tag: (-1, -1, 0)}, [(-x, -y) for x, y in deltas]))
        variations.append(TupleVariation({"WDTH": (0, 1, 1), "HGHT": (0, 1, 1)}, mixed))
        builder.setupGvar({".notdef": [], "space": [], "probe": variations})
        trak = newTable("trak")
        trak.version = 1.0; trak.format = 0
        name_id = builder.font["name"].addName("Fixture tracking must not leak into raw metrics")
        # CoreText's zero-track policy must be explicitly disabled in the oracle.
        # A constant +37 FUnits at all sizes makes accidental tracking easy to detect.
        trak.horizData = TrackData({0.0: TrackTableEntry({10.0: 37, 1200.0: 37}, nameIndex=name_id)})
        trak.vertData = TrackData()
        builder.font["trak"] = trak
        builder.setupMaxp()
        builder.font["head"].created = builder.font["head"].modified = 3_800_000_000
        builder.font.recalcTimestamp = False
        fonts.append(builder.font)
    collection = TTCollection()
    collection.fonts = fonts
    collection.save(path)


def normalized(value, minimum, default, maximum):
    return (value - default) / ((default - minimum) if value < default else (maximum - default))


def native_requests():
    requests = []
    locations = [dict(zip(["WDTH", "wght", "HGHT"], values)) for values in
                 itertools.product([1., 500., 1000.], [100., 400., 900.], [1., 500., 1000.])]
    locations += [{"WDTH": 631.25, "wght": 523.75, "HGHT": 711.125},
                  {"WDTH": 631.25, "wght": 523.875, "HGHT": 711.125}]
    for face in (0, 1):
        for index, location in enumerate(locations):
            requests.append({"request_id": f"face{face}-point{index}", "face_index": face,
                             "location": location, "glyph_ids": [0, 1, 2]})
    return requests


def assert_close(actual, expected, label, epsilon=1 / 32):
    # Two 26.6 font-unit steps cover native interpolation quantization at the
    # deliberately fractional interior points. Endpoints remain analytically exact.
    if not isinstance(actual, (int, float)) or not math.isfinite(actual) or abs(actual - expected) > epsilon:
        raise AssertionError(f"{label}: actual={actual}, expected={expected}, tolerance={epsilon}")


class NativeResultValidationError(AssertionError):
    """Keep the exact failed synthetic measurement; never adjust its threshold."""
    def __init__(self, error, result, request):
        self.details = {"validation_error": str(error),
                        "request_id": result.get("request_id"),
                        "face_index": result.get("face_index"),
                        "glyph_id": result.get("glyph_id"),
                        "location": result.get("location"),
                        "requested_input": request,
                        "native_result": result}
        super().__init__(f"request={result.get('request_id')} face={result.get('face_index')} "
                         f"gid={result.get('glyph_id')}: {error}")


def validate_results(records, requests, source_sha):
    if not records or records[0].get("type") != "metadata":
        raise AssertionError("metadata must be first")
    metadata = records[0]
    if metadata.get("source_sha256") != source_sha:
        raise AssertionError("source identity mismatch")
    if len(metadata.get("faces", [])) != 2:
        raise AssertionError("both raw TTC faces must be represented")
    for index, face in enumerate(metadata["faces"]):
        if face.get("status") != "identity_verified" or face.get("face_index") != index:
            raise AssertionError(f"face {index} not verified: {face}")
        if face.get("upm") != [1000, 1128][index]:
            raise AssertionError("original per-face UPEM changed")
    expected = {(r["request_id"], gid): r for r in requests for gid in r["glyph_ids"]}
    results = [r for r in records if "glyph_id" in r]
    if len(results) != len(expected):
        raise AssertionError(f"wrong result count: {len(results)} vs {len(expected)}")
    seen = set()
    for result in results:
        try:
            key = (result["request_id"], result["glyph_id"])
            if key in seen or key not in expected:
                raise AssertionError("duplicate or unrelated glyph result")
            seen.add(key)
            request = expected[key]
            if result.get("error") is not None:
                raise AssertionError(f"native glyph failed: {result}")
            if result["face_index"] != request["face_index"]:
                raise AssertionError("wrong source face returned")
            assert_close(result["horizontal_origin_x"], 0, "horizontal origin")
            if result["glyph_id"] == 0:
                assert_close(result["advance_width"], 550, "notdef advance without trak")
                continue
            if result["glyph_id"] == 1:
                if result["commands"]:
                    raise AssertionError("blank glyph must be preserved as empty")
                assert_close(result["advance_width"], 400, "space advance without trak")
                continue
            location = request["location"]
            width = normalized(location["WDTH"], 1, 500, 1000)
            weight = normalized(location["wght"], 100, 400, 900)
            height = normalized(location["HGHT"], 1, 500, 1000)
            cross = max(0, width) * max(0, height)
            advance = 700 + width * 100 + weight * 30 + cross * 10
            assert_close(result["advance_width"], advance, "varied advance without trak")
            assert_close(result["advance_height"], 1000 + height * 150, "vertical advance is raw CGSize.width")
            assert_close(result["vertical_origin_y"], 820 + height * 60, "vertical origin sign")
            assert_close(result["vertical_origin_x"], advance / 2, "vertical origin half advance")
            assert_close(result["lsb"], 100 + width * 20, "effective geometric left bearing")
            assert_close(result["bounds"][0] + result["bounds"][2], 450 + width * 90 + weight * 60 + cross * 20,
                         "true curve extremum differs from control-point bound")
            assert_close(result["bounds"][1] + result["bounds"][3], 600 + height * 180, "height-dependent outline")
            if not any(command[0] in {"qCurveTo", "curveTo"} for command in result["commands"]):
                raise AssertionError("native curve path was flattened or lost")
        except Exception as error:
            request = expected.get((result.get("request_id"), result.get("glyph_id")))
            raise NativeResultValidationError(error, result, request) from error
    return {"passed": True, "source_sha256": source_sha, "face_count": 2,
            "request_count": len(requests), "glyph_result_count": len(results),
            "metric_and_geometric_tolerance_font_units": 1 / 32,
            "coverage": ["explicit TTC face identity", "different per-face UPEM", "three axes including hidden HGHT",
                         "all 27 axis min/default/max combinations", "fractional interior points", "mixed WDTH/HGHT gvar response",
                         "nonzero trak disabled", "blank glyph", "native curves and true extrema", "vertical advance and origin signs"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    fixture = out / "native-oracle-fixture.ttc"
    make_fixture(fixture)
    source_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    requests = native_requests()
    request_text = "".join(json.dumps(r) + "\n" for r in requests)
    (out / "requests.jsonl").write_text(request_text, encoding="utf-8")
    status = {"platform": platform.platform(), "source": "self_authored_synthetic_fixture_no_Apple_data",
              "source_sha256": source_sha, "native_original_font_test": "not_run"}
    if sys.platform != "darwin":
        status.update({"status": "NOT_RUN", "reason": "CoreText requires macOS; current runtime cannot execute it."})
        (out / "coretext_test_result.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(status, indent=2))
        return 2 if args.require_native else 0
    binary = args.binary.resolve() if args.binary else out / "coretext_extract"
    if args.binary is None:
        swiftc = shutil.which("swiftc")
        if not swiftc:
            raise RuntimeError("swiftc unavailable")
        compile_result = subprocess.run([swiftc, "-O", str(Path(__file__).with_name("coretext_extract.swift")), "-o", str(binary)], capture_output=True, text=True)
        (out / "swift_compile.log").write_text(compile_result.stdout + compile_result.stderr, encoding="utf-8")
        if compile_result.returncode:
            raise RuntimeError(f"Swift compilation failed; see {out / 'swift_compile.log'}")
    result = subprocess.run([str(binary), str(fixture)], input=request_text, capture_output=True, text=True, timeout=120)
    (out / "native_oracle_results.jsonl").write_text(result.stdout, encoding="utf-8")
    (out / "native_oracle_stderr.log").write_text(result.stderr, encoding="utf-8")
    status["native_exit_code"] = result.returncode
    try:
        if result.returncode:
            raise AssertionError(f"native extractor exit {result.returncode}")
        records = [json.loads(line) for line in result.stdout.splitlines() if line]
        status.update(validate_results(records, requests, source_sha))
        status["status"] = "PASS_SYNTHETIC_NATIVE_ONLY"
    except Exception as error:
        status.update({"status": "FAIL", "error": str(error)})
        if isinstance(error, NativeResultValidationError):
            status["failure_context"] = error.details
    (out / "coretext_test_result.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2))
    return 0 if status["status"] == "PASS_SYNTHETIC_NATIVE_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
