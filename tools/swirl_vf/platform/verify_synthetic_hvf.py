#!/usr/bin/env python3
"""Run the real Apple HVF oracle on a wholly original geometric test fixture.

The expected rectangles come from a simple affine formula, independently of
the oracle's binary parser or callback implementation. This is a plumbing/API
test, never a preservation result for PingFang.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys


def verify(rows: list[dict], coords: tuple[float, ...]) -> dict:
    headers = [r for r in rows if r.get("record") == "header"]
    outlines = [r for r in rows if r.get("record") == "outline"]
    summaries = [r for r in rows if r.get("record") == "summary"]
    if len(headers) != 1 or len(outlines) != 1 or len(summaries) != 1:
        raise ValueError("Missing/duplicate oracle record")
    if headers[0]["fvar_axis_tags"] != ["WDTH", "wght", "HGHT"]:
        raise ValueError("Unexpected axis identity/order")
    if outlines[0]["status"] != "OK" or summaries[0]["status"] != "EXTRACTED":
        raise ValueError("Native extraction failed")
    if outlines[0]["applied_axis_count"] != 3:
        raise ValueError("Not all three requested axes were applied")
    points = []
    for command in outlines[0]["events"]:
        if command[0] in {"move", "line", "quad", "cubic"}:
            raw = command[1:]
            if len(raw) % 2 or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in raw):
                raise ValueError("Non-finite or malformed output coordinate")
            points += list(zip(raw[0::2], raw[1::2]))
    if not points:
        raise ValueError("The synthetic square produced no geometry")
    actual = [min(x for x, _ in points), min(y for _, y in points),
              max(x for x, _ in points), max(y for _, y in points)]
    width, shift, height = coords
    expected = [0.0, shift * 20.0, 400.0 * (1.0 + width * .25),
                400.0 * (1.0 + height * .25) + shift * 20.0]
    error = max(abs(x - y) for x, y in zip(actual, expected))
    if error > 1e-8:
        raise ValueError(f"Geometric bounds differ: expected {expected}, got {actual}")
    return {"coords": coords, "control_bounds": actual, "expected_bounds": expected,
            "max_error_font_units": error, "status": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    positions = list(itertools.product((-1.0, 0.0, 1.0), repeat=3))
    positions += [(.4, -.7, .6), (-.314159, .271828, -.161803)]
    results = []
    for index, coords in enumerate(positions):
        command = [str(args.binary.resolve()), str(args.fixture.resolve()), "0",
                   ",".join(map(str, coords)), "0", "1"]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        (args.out / f"case-{index:02d}.jsonl").write_text(result.stdout, encoding="utf-8")
        (args.out / f"case-{index:02d}.stderr.log").write_text(result.stderr, encoding="utf-8")
        try:
            if result.returncode:
                raise ValueError(f"Native return code {result.returncode}: {result.stderr[:500]}")
            verdict = verify([json.loads(line) for line in result.stdout.splitlines()], coords)
        except (ValueError, KeyError, TypeError) as error:
            verdict = {"coords": coords, "status": "NOT_RUN" if result.returncode == 77 else "FAILED",
                       "error": str(error), "native_exit_code": result.returncode}
        results.append(verdict)
        if result.returncode == 77:
            break
    passed = sum(r["status"] == "PASS" for r in results)
    report = {"schema": 1, "status": "PASS" if passed == len(positions) else "FAILED",
              "scope": "Synthetic geometry/API test; no Apple original font was tested",
              "fixture_sha256": hashlib.sha256(args.fixture.read_bytes()).hexdigest(),
              "positions_planned": len(positions), "positions_passed": passed, "results": results}
    if results and results[0]["status"] == "NOT_RUN":
        report["status"] = "NOT_RUN"
    (args.out / "synthetic-hvf-verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "passed": passed, "planned": len(positions)}))
    return 0 if report["status"] == "PASS" else 77 if report["status"] == "NOT_RUN" else 1


if __name__ == "__main__":
    sys.exit(main())
