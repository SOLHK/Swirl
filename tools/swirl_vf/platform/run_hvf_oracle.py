#!/usr/bin/env python3
"""Build/run the Apple HVF oracle, retaining exact input identity and evidence.

No font is uploaded, installed, renamed, or modified. Output contains original
outline coordinates; keep the output private with the source font.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import time


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    font = args.font.expanduser().resolve(strict=True)
    source = Path(__file__).with_name("hvf_oracle.c").resolve(strict=True)
    target = args.out.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    record = target / "hvf-run.json"
    outline = target / "hvf-outlines.jsonl"
    if record.exists() or outline.exists():
        raise ValueError("Choose a new output directory; an earlier run will not be overwritten")
    original = sha256(font)
    report = {
        "schema": 1,
        "status": "NOT_RUN",
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "input": {"path": str(font), "bytes": font.stat().st_size, "sha256": original},
        "source_sha256": sha256(source),
        "request": {"face_index": args.face, "normalized_design_coords": args.coords,
                    "start": args.start, "count": args.count, "parts": args.parts},
        "user_coordinate_mapping": "NOT_TESTED",
        "metrics": "NOT_EXTRACTED",
        "original_outline_equality": "NOT_EVALUATED",
        "output_privacy": "Contains source-font outlines; do not publish in a public repository",
    }
    started = time.monotonic()
    returncode = 77
    try:
        if sys.platform != "darwin":
            report["reason"] = "Apple HVF C runtime is unavailable on this operating system"
            return returncode
        if not shutil.which("xcrun"):
            report["reason"] = "Xcode Command Line Tools are unavailable"
            return returncode
        binary = args.binary.expanduser().resolve(strict=True) if args.binary else target / "hvf_oracle"
        if not args.binary:
            cmd = ["xcrun", "clang", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                   "-mmacosx-version-min=15.4", str(source), "-lhvf", "-o", str(binary)]
            report["build_command"] = cmd
            build = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            (target / "build.stdout.log").write_text(build.stdout, encoding="utf-8")
            (target / "build.stderr.log").write_text(build.stderr, encoding="utf-8")
            report["build_exit_code"] = build.returncode
            if build.returncode:
                report["status"] = "BUILD_FAILED"
                report["reason"] = "Actual Apple SDK compilation failed; see build.stderr.log"
                returncode = build.returncode
                return returncode
        report["binary_sha256"] = sha256(binary)
        cmd = [str(binary), str(font), str(args.face), args.coords, str(args.start), str(args.count)]
        if args.parts:
            cmd.append("parts")
        report["run_command"] = cmd
        with outline.open("xb") as stdout, (target / "runtime.stderr.log").open("xb") as stderr:
            result = subprocess.run(cmd, stdout=stdout, stderr=stderr, timeout=args.timeout)
        returncode = result.returncode
        report["runtime_exit_code"] = returncode
        report["outline_sha256"] = sha256(outline)
        counts = {"headers": 0, "outlines": 0, "failed_outlines": 0, "summaries": 0}
        final = None
        header = None
        with outline.open(encoding="utf-8") as lines:
            for line in lines:
                row = json.loads(line)
                kind = row.get("record")
                if kind == "header":
                    counts["headers"] += 1
                    header = row
                elif kind == "outline":
                    counts["outlines"] += 1
                    if row.get("status") != "OK":
                        counts["failed_outlines"] += 1
                elif kind == "summary":
                    counts["summaries"] += 1
                    final = row
        report["counts"] = counts
        report["native_header"] = header
        report["native_summary"] = final
        if (returncode == 0 and counts["headers"] == 1 and counts["summaries"] == 1
                and counts["failed_outlines"] == 0 and final
                and final.get("status") == "EXTRACTED" and final.get("failed") == 0
                and counts["outlines"] == final.get("rendered")
                and header and header.get("count") == counts["outlines"]):
            report["status"] = "EXTRACTED"
        else:
            report["status"] = "NOT_RUN" if returncode == 77 else "FAILED"
            if not returncode:
                returncode = 1
        return returncode
    except (subprocess.SubprocessError, OSError, ValueError) as error:
        report["status"] = "FAILED"
        report["error"] = f"{type(error).__name__}: {error}"
        returncode = 1
        return returncode
    finally:
        after = sha256(font)
        report["input_sha256_after"] = after
        report["input_unchanged"] = after == original
        if after != original:
            report["status"] = "FAILED_INPUT_CHANGED"
        report["duration_seconds"] = time.monotonic() - started
        report["ended_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save(record, report)
        print(json.dumps({"status": report["status"], "report": str(record)}, ensure_ascii=False))
        if after != original:
            # Override any pending success return: a changing source invalidates evidence.
            raise RuntimeError("The input file changed during the run")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--face", type=int, default=0)
    parser.add_argument("--coords", required=True, help="Use --coords=-1,0,0 for negative coordinates")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--count", type=int, default=0, help="0 extracts all remaining glyphs")
    parser.add_argument("--parts", action="store_true", help="Address HVF part IDs rather than maxp glyph IDs")
    parser.add_argument("--binary", type=Path, help="Use a previously compiled oracle")
    parser.add_argument("--timeout", type=float, default=7200)
    args = parser.parse_args()
    if min(args.face, args.start, args.count) < 0 or args.timeout <= 0:
        parser.error("Indices/count must be nonnegative, timeout must be positive")
    try:
        return run(args)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
