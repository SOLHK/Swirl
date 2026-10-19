#!/usr/bin/env python3
"""Read all HVF structures; report exactly why a production conversion is gated."""
from __future__ import annotations
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

from fontTools.ttLib import TTCollection
from hvf import HVGL, Shape
from audit_font import raw_avar


def inspect(source: Path, output: Path):
    with source.open("rb") as stream:
        original_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    fonts = TTCollection(source, lazy=True).fonts
    started = time.monotonic()
    report = {"source_name": source.name, "source_sha256": original_hash,
              "source_size_bytes": source.stat().st_size, "face_count": len(fonts),
              "platform": platform.platform(), "python": platform.python_version(),
              "fonttools": __import__('fontTools').__version__, "faces": [], "hvgl_tables": [],
              "final_font_generated": False, "windows_runtime": "NOT_RUN",
              "apple_oracle": "NOT_RUN", "conversion_status": "BLOCKED_PENDING_NATIVE_ORACLE"}
    shared = {}
    for index, font in enumerate(fonts):
        entry = font.reader.tables.get("hvgl")
        if entry is None:
            report["faces"].append({"index": index, "error": "missing hvgl"})
            continue
        raw = font.getTableData("hvgl")
        mapping = font.getTableData("hvpm") if "hvpm" in font else None
        key = (hashlib.sha256(raw).hexdigest(), hashlib.sha256(mapping or b"").hexdigest())
        if key not in shared:
            table = HVGL(raw, mapping)
            record = table.validate()
            @lru_cache(maxsize=None)
            def requirements(part_id):
                part = table.part(part_id)
                if isinstance(part, Shape):
                    return frozenset(["tangent_blend"] if any(x > 1 for x in part.blends) else [])
                value = set()
                if any(part.rotations.extreme_values.flatten()):
                    value.add("nonlinear_rotation")
                for child, _, _ in part.subparts:
                    value.update(requirements(child))
                return frozenset(value)
            affected = {label: [gid for gid in range(table.glyph_count) if label in requirements(gid)]
                        for label in ("tangent_blend", "nonlinear_rotation")}
            record["affected_visible_glyphs"] = {label: len(ids) for label, ids in affected.items()}
            record["affected_visible_glyph_ids"] = affected
            record["sha256"] = key[0]
            record["hvpm_present"] = bool(mapping)
            shared[key] = len(report["hvgl_tables"])
            report["hvgl_tables"].append(record)
        tags = [axis.axisTag for axis in font["fvar"].axes]
        avar = raw_avar(font.reader["avar"], tags) if "avar" in font else None
        report["faces"].append({"index": index, "postscript_name": font["name"].getDebugName(6),
                                "hvgl_record": shared[key], "axis_tags": tags,
                                "raw_avar_standard_record_conformance": avar["standard_record_conformance_pass"] if avar else True})
    report["elapsed_seconds"] = time.monotonic() - started
    with source.open("rb") as stream:
        report["source_unchanged"] = original_hash == hashlib.file_digest(stream, "sha256").hexdigest()
    report["blockers"] = [
        "Native Apple outline/metric oracle has not been run against this exact source hash.",
        "Portable experimental rendering explicitly refuses undocumented tangent blend reconstruction.",
        "Raw Apple avar duplicates/order must be evaluated by CoreText; dictionary collapse is not equivalent proof.",
        "Nonlinear hierarchy/rotation and float-to-integer conversion require independent unsampled-point error bounds.",
        "Actual private-source Windows DirectWrite, Qt and physical DPI tests have not run."]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.source, args.output)
    print(json.dumps({k: result[k] for k in ("source_sha256", "face_count", "source_unchanged", "conversion_status")}, indent=2))
    for table in result["hvgl_tables"]:
        print(json.dumps({k: table[k] for k in ("part_count", "glyph_count", "binary_and_structure_validation", "affected_visible_glyphs")}, indent=2))

