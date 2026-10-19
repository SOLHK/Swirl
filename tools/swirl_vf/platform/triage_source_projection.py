#!/usr/bin/env python3
"""Summarize exact-source HVF control-point failures without exporting contours."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

LIMIT = 1 / 32
EXPECTED_GIDS = {6, 7, 104, 170, 3262, 19177}

def summarize(report: dict) -> dict:
    groups = report.get("by_glyph")
    if not isinstance(groups, dict):
        raise ValueError("missing per-GID verification records")
    cases = 0
    failures = 0
    failing = []
    for raw_gid, data in groups.items():
        gid = int(raw_gid)
        passed, failed = int(data["passed"]), int(data["failed"])
        if min(passed, failed) < 0:
            raise ValueError("negative counts")
        cases += passed + failed
        failures += failed
        if failed:
            failing.append({"gid": gid, "passed": passed, "failed": failed,
                            "max_error_funits": float(data["max_error"]) if "max_error" in data
                            else float(data.get("max_control_point_error", 0))})
    failing.sort(key=lambda x: (-x["failed"], x["gid"]))
    return {"sample_count": cases, "failed_samples": failures,
            "passing_samples": cases - failures, "failed_gids": failing,
            "error_budget_funits": LIMIT,
            "status": "ORIGINAL_GEOMETRY_NOT_ACCEPTED" if failures else "SAMPLED_GEOMETRY_PASS"}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve() or args.output.exists():
        parser.error("output must be a fresh file distinct from source")
    report = summarize(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))

if __name__ == "__main__":
    main()
