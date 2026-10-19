#!/usr/bin/env python3
"""Run the complete CoreText -> reconstruction -> CoreText path on synthetic data.

The source is test_coretext_extract.make_fixture's original two-face TTC, never
PingFang or an Apple derivative. The temporary file named Swirl-VF.ttc is removed
after the test. Only logs, hashes, geometric observations and a scoped synthetic
verdict remain. A successful test is not original-font or Windows acceptance.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

from fontTools.ttLib import TTCollection

from test_coretext_extract import make_fixture, native_requests, validate_results


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def axes(font):
    return [{"tag": a.axisTag, "min": a.minValue, "default": a.defaultValue,
             "max": a.maxValue, "flags": a.flags, "name_id": a.axisNameID,
             "name": font["name"].getDebugName(a.axisNameID)} for a in font["fvar"].axes]


def cmap_gids(font):
    return [(table.platformID, table.platEncID, table.language, table.format,
             sorted((cp, font.getGlyphID(name)) for cp, name in table.cmap.items()))
            for table in font["cmap"].tables]


def check_collection(source_path, candidate_path):
    """Exact metadata and default-origin storage checks, independently of run()."""
    source = TTCollection(source_path)
    candidate = TTCollection(candidate_path)
    reports = []
    try:
        require(len(source.fonts) == len(candidate.fonts) == 2, "two physical TTC faces required")
        for index, (original, target) in enumerate(zip(source.fonts, candidate.fonts)):
            prefix = f"face {index}"
            names = original.getGlyphOrder()
            require(names == target.getGlyphOrder() and len(names) == 3, f"{prefix}: GID/order changed")
            require(original["head"].unitsPerEm == target["head"].unitsPerEm == (1000, 1128)[index],
                    f"{prefix}: original UPEM changed")
            require(cmap_gids(original) == cmap_gids(target), f"{prefix}: Unicode/GID mapping changed")
            require(axes(original) == axes(target), f"{prefix}: axis tag/range/default/flag/name changed")
            require(original["fvar"].compile(original) == target["fvar"].compile(target),
                    f"{prefix}: fvar metadata or named instances changed")
            require(original["avar"].segments == target["avar"].segments,
                    f"{prefix}: identity fixture avar changed")
            require(original["hmtx"].metrics == target["hmtx"].metrics,
                    f"{prefix}: default horizontal advance/bearing changed")
            require(original["vmtx"].metrics == target["vmtx"].metrics,
                    f"{prefix}: default vertical advance/bearing changed")
            require(original["trak"].compile(original) == target["trak"].compile(target),
                    f"{prefix}: fixture tracking table was silently deleted or changed")
            require(not any(tag in target for tag in ("hvgl", "hvpm")), f"{prefix}: nonstandard outline table")
            require(all(tag in target for tag in ("glyf", "gvar", "loca")), f"{prefix}: missing standard outline data")
            for gid, name in enumerate(names):
                a, b = original["glyf"][name], target["glyf"][name]
                a.recalcBounds(original["glyf"]); b.recalcBounds(target["glyf"])
                horizontal_a = a.xMin - original["hmtx"].metrics[name][1]
                horizontal_b = b.xMin - target["hmtx"].metrics[name][1]
                vertical_a = a.yMax + original["vmtx"].metrics[name][1]
                vertical_b = b.yMax + target["vmtx"].metrics[name][1]
                require(horizontal_a == horizontal_b == 0, f"{prefix}, gid {gid}: horizontal origin shifted")
                require(vertical_a == vertical_b == 820, f"{prefix}, gid {gid}: vertical origin shifted")
            reports.append({"face_index": index, "glyph_count": len(names), "glyph_order": names,
                            "upm": target["head"].unitsPerEm, "axes": axes(target),
                            "default_horizontal_and_vertical_metrics": "EXACT",
                            "default_horizontal_origin_x": 0, "default_vertical_origin_y": 820,
                            "status": "PASS"})
    finally:
        source.close(); candidate.close()
    return reports


def check_rebuild_report(report, source_sha, candidate_sha):
    require(report.get("status") == "RECONSTRUCTION_SAMPLED_PASS_PLATFORM_UNVERIFIED", "rebuild did not pass sampled gates")
    require(report.get("output_generated") is True and not report.get("failures"), "rebuild output/failure state inconsistent")
    require(report.get("source_sha256") == source_sha and report.get("output_sha256") == candidate_sha,
            "rebuild input/output SHA does not match actual files")
    require(report.get("lossless_conversion") is False and report.get("windows_acceptance") == "NOT_RUN",
            "reconstruction must not claim lossless or Windows acceptance")
    require(report.get("outline_limit_font_units") == 1.0 and report.get("metric_limit_font_units") == 1.0,
            "smoke test expects unchanged predeclared 1 FUnit reconstruction limits")
    faces = report.get("faces", [])
    require(len(faces) == 2, "missing per-face reconstruction evidence")
    for index, face in enumerate(faces):
        require(face.get("face_index") == index and face.get("glyph_count") == 3,
                "rebuild did not account for every original face/GID")
        require(face.get("training_points") == 27 and face.get("initial_holdout_points", 0) >= 26,
                "training/independent holdout evidence incomplete")
        for name in ("max_outline_error", "max_metric_error"):
            value = face.get(name)
            require(isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 1.0,
                    f"face {index}: invalid/out-of-budget {name}")
        serialized = face.get("serialized_model_verification", {})
        require(serialized.get("status") == "PASS" and serialized.get("glyphs_checked") == 3
                and serialized.get("native_holdout_error_preserved") is True
                and serialized.get("continuous_native_space_proof") is False,
                f"face {index}: serialized native-checked model evidence missing")
    collection = report.get("collection_verification", {})
    require(collection.get("status") == "PASS" and collection.get("faces_checked") == 2,
            "TTC packing evidence missing")


def native_records(binary, font, requests, out, label, commands):
    request_text = "".join(json.dumps(r, allow_nan=False) + "\n" for r in requests)
    result = recorded_run([str(binary), str(font)], out, label, commands, timeout=180, input=request_text)
    require(result.returncode == 0, f"{label}: CoreText extractor exit {result.returncode}")
    rows = [json.loads(line) for line in result.stdout.splitlines() if line]
    metadata = [r for r in rows if r.get("type") == "metadata"]
    summaries = [r for r in rows if r.get("type") == "summary"]
    require(rows and rows[0].get("type") == "metadata" and len(metadata) == len(summaries) == 1,
            f"{label}: metadata/summary incomplete")
    require(metadata[0].get("source_sha256") == digest(font), f"{label}: source identity mismatch")
    require(metadata[0].get("backend") == "CoreText", f"{label}: native backend missing")
    faces = metadata[0].get("faces", [])
    require(len(faces) == 2 and all(f.get("status") == "identity_verified" for f in faces),
            f"{label}: not every physical face identity verified")
    require(all(f.get("face_index") == i and f.get("glyph_count") == 3
                and f.get("upm") == (1000, 1128)[i] for i, f in enumerate(faces)),
            f"{label}: native physical face/GID/UPEM metadata mismatch")
    summary = summaries[0]
    require(summary.get("request_count") == len(requests) and summary.get("error_count") == 0
            and summary.get("successful_glyph_count") == sum(len(r["glyph_ids"]) for r in requests),
            f"{label}: incomplete/error native requests")
    return rows


def canonical_commands(commands):
    """Ignore only zero-length lines and the redundant straight closing edge."""
    output = []
    origin = current = None
    for command in commands:
        kind = command[0]
        if kind == "moveTo":
            origin = current = tuple(command[1:])
        elif kind == "lineTo":
            endpoint = tuple(command[1:])
            if endpoint == current:
                continue
            current = endpoint
        elif kind in ("qCurveTo", "curveTo"):
            current = tuple(command[-2:])
        elif kind == "closePath":
            if output and output[-1][0] == "lineTo" and tuple(output[-1][1:]) == origin:
                output.pop()
            origin = current = None
        else:
            raise AssertionError(f"unsupported native command {kind}")
        output.append(command)
    return output


def compare_native(source, candidate, requests):
    expected = {(r["request_id"], gid): r for r in requests for gid in r["glyph_ids"]}
    source_rows = {(r["request_id"], r["glyph_id"]): r for r in source if "glyph_id" in r}
    actual_rows = [r for r in candidate if "glyph_id" in r]
    require(set(source_rows) == set(expected) and len(actual_rows) == len(expected), "native GID result count changed")
    seen = set()
    metrics = ("advance_width", "advance_height", "lsb", "horizontal_origin_x", "horizontal_origin_y",
               "vertical_origin_x", "vertical_origin_y")
    max_point = max_metric = max_bounds = 0.0
    for actual in actual_rows:
        key = (actual["request_id"], actual["glyph_id"])
        require(key in expected and key not in seen, "duplicate or unrelated reconstructed native GID")
        seen.add(key); request = expected[key]; original = source_rows[key]
        require(actual.get("error") is None and actual.get("face_index") == request["face_index"]
                and actual.get("location") == request["location"], "native reconstructed response mismatch")
        for field in metrics:
            a, b = original[field], actual[field]
            require(math.isfinite(a) and math.isfinite(b), f"nonfinite {field}")
            error = abs(a - b); max_metric = max(max_metric, error)
            require(error <= 1.0, f"{key}: {field} error {error} exceeds 1 FUnit")
        a_commands = canonical_commands(original["commands"])
        b_commands = canonical_commands(actual["commands"])
        require([(c[0], len(c)) for c in a_commands] == [(c[0], len(c)) for c in b_commands],
                f"{key}: reconstructed contour topology changed")
        for a, b in zip(a_commands, b_commands):
            for index in range(1, len(a), 2):
                error = math.hypot(a[index] - b[index], a[index + 1] - b[index + 1])
                require(math.isfinite(error) and error <= 1.0, f"{key}: native control-point error {error}")
                max_point = max(max_point, error)
        require(len(original["bounds"]) == len(actual["bounds"]) == 4, f"{key}: incomplete bounds")
        for a, b in zip(original["bounds"], actual["bounds"]):
            error = abs(a - b)
            require(math.isfinite(error) and error <= 1.0, f"{key}: native bound error {error}")
            max_bounds = max(max_bounds, error)
    return {"status": "PASS", "requests": len(requests), "glyph_records": len(actual_rows),
            "max_control_point_error_font_units": max_point,
            "max_metric_error_font_units": max_metric, "max_bounds_error_font_units": max_bounds,
            "limit_font_units": 1.0, "continuous_space_proof": False,
            "command_normalization": "only zero-length straight segments and redundant straight closing edges"}


def recorded_run(command, out, label, commands, *, timeout, input=None):
    started = time.monotonic()
    try:
        result = subprocess.run(command, input=input, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        def decoded(value):
            return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")
        (out / (label + ".stdout.log")).write_text(decoded(error.stdout), encoding="utf-8")
        (out / (label + ".stderr.log")).write_text(decoded(error.stderr), encoding="utf-8")
        commands.append({"command": command, "status": "TIMEOUT", "limit_seconds": timeout,
                         "duration_seconds": time.monotonic() - started})
        raise
    (out / (label + ".stdout.log")).write_text(result.stdout, encoding="utf-8")
    (out / (label + ".stderr.log")).write_text(result.stderr, encoding="utf-8")
    commands.append({"command": command, "exit_code": result.returncode,
                     "duration_seconds": time.monotonic() - started})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--binary", type=Path, help="Reuse a built coretext_extract executable")
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=True)
    report_path = out / "native_reconstruction_result.json"
    require(not report_path.exists(), "choose a new evidence output directory")
    root = Path(__file__).resolve().parents[1]
    report = {"schema": 1, "status": "NOT_RUN", "platform": platform.platform(),
              "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "data_origin": "self_authored_two_face_synthetic_fixture_no_Apple_data",
              "original_apple_font_test": "NOT_RUN", "windows_acceptance": "NOT_RUN",
              "swirl_ui_acceptance": "NOT_RUN", "continuous_preservation_proof": False,
              "commands": [], "font_artifact_retained": False,
              "source_code_sha256": {str(p.relative_to(root)): digest(p) for p in (
                  Path(__file__).resolve(), root / "platform/test_coretext_extract.py",
                  root / "platform/coretext_extract.swift", root / "tools/rebuild.py")}}
    code = 1
    try:
        if sys.platform != "darwin":
            report["reason"] = "CoreText runtime is unavailable; no native reconstruction was executed."
            code = 2 if args.require_native else 0
        else:
            binary = args.binary.resolve() if args.binary else out / "coretext_extract"
            if args.binary is None:
                swiftc = shutil.which("swiftc")
                require(bool(swiftc), "swiftc unavailable")
                compiled = recorded_run([swiftc, "-O", str(root / "platform/coretext_extract.swift"), "-o", str(binary)],
                                        out, "swift-compile", report["commands"], timeout=180)
                require(compiled.returncode == 0, "Swift compilation failed")
            require(binary.is_file(), "coretext_extract executable missing")
            report["oracle_binary_sha256"] = digest(binary)
            requests = native_requests()
            (out / "native-comparison-requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in requests), encoding="utf-8")
            with tempfile.TemporaryDirectory(prefix="synthetic-native-rebuild-", dir=out) as temporary:
                temp = Path(temporary)
                source = temp / "self-authored-two-face-fixture.ttc"
                candidate = temp / "Swirl-VF.ttc"
                make_fixture(source)
                report["fixture_sha256"] = source_sha = digest(source)
                original_records = native_records(binary, source, requests, out, "original-native", report["commands"])
                report["source_analytic_validation"] = validate_results(original_records, requests, source_sha)
                build_report = out / "reconstruction-report.json"
                result = recorded_run([sys.executable, str(root / "tools/rebuild.py"), str(source),
                                       "--oracle", str(binary), "--output", str(candidate),
                                       "--report", str(build_report), "--batch-size", "2"],
                                      out, "reconstruction", report["commands"], timeout=600)
                require(result.returncode == 0 and candidate.is_file(), "native reconstruction CLI failed; inspect its report/logs")
                report["candidate_sha256"] = candidate_sha = digest(candidate)
                report["candidate_bytes"] = candidate.stat().st_size
                built = json.loads(build_report.read_text(encoding="utf-8"))
                check_rebuild_report(built, source_sha, candidate_sha)
                report["collection_structure"] = check_collection(source, candidate)
                target_records = native_records(binary, candidate, requests, out, "reconstructed-native", report["commands"])
                report["independent_native_comparison"] = compare_native(original_records, target_records, requests)
                require(digest(source) == source_sha, "synthetic source changed during test")
                report["source_unchanged"] = True
                report["status"] = "PASS_SYNTHETIC_NATIVE_RECONSTRUCTION_ONLY"
            report["temporary_fonts_removed"] = True
            code = 0
    except Exception as error:
        report["status"] = "FAILED"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["ended_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(report_path)}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
