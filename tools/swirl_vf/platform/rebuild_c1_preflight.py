#!/usr/bin/env python3
"""Read-only preparation inventory for the exact private 32-face source.

This command NEVER grants permission to run a production rebuild.  A3 and B1
have no accepted production input contract at this checkpoint.  A JSON file
claiming ``accepted: true`` is deliberately not an input option.  Reports
contain only identity hashes, table tags and aggregate counts, never paths,
names, outlines, native payloads, or exception text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from ttc_staging_contract import StagingError, require


SOURCE_SHA256 = "39d42acd292ed5c9de5cf185b54a3c460630d610a718ed84c9e4f148e226f890"
SOURCE_BYTES = 61_473_880
SOURCE_FACES = 32
SOURCE_GLYPHS = 47_102
SOURCE_AXES = ("WDTH", "wght", "HGHT")
PROFILE = "swirl-vf-original-20261020"


def _identity(path):
    require(path.is_file() and not path.is_symlink(), "platform_read",
            "source_not_regular_file", stage="source_identity")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        before = path.stat()
        size = 0
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
        after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            and size == after.st_size, "serialization", "source_changed",
            stage="source_identity")
    return digest.hexdigest(), size


def _inventory(path):
    # Check the count before TTCollection allocates a list of physical faces.
    with path.open("rb") as stream:
        header = stream.read(12)
    require(len(header) == 12 and header[:4] == b"ttcf", "font_tables",
            "source_not_ttc", stage="source_tables")
    version, count = struct.unpack(">II", header[4:])
    require(version in (0x10000, 0x20000) and count == SOURCE_FACES,
            "font_tables", "source_face_count", expected_count=SOURCE_FACES,
            actual_count=count, stage="source_tables")
    inventory = []
    with TTCollection(path, lazy=True) as collection:
        require(len(collection.fonts) == SOURCE_FACES, "font_tables",
                "source_face_count", actual_count=len(collection.fonts))
        for index, font in enumerate(collection.fonts):
            tags = set(font.reader.tables)
            require({"head", "maxp", "fvar", "name", "cmap", "OS/2", "hmtx"} <= tags,
                    "font_tables", "source_required_table_missing", face_index=index)
            require(len(tags) <= 256, "font_tables", "source_table_count",
                    face_index=index, actual_count=len(tags))
            require(font["maxp"].numGlyphs == SOURCE_GLYPHS, "font_tables",
                    "source_glyph_count", face_index=index,
                    expected_count=SOURCE_GLYPHS, actual_count=font["maxp"].numGlyphs)
            axes = font["fvar"].axes
            require(tuple(a.axisTag for a in axes) == SOURCE_AXES, "input_axis",
                    "source_axis_tags_or_order", face_index=index)
            for axis_index, axis in enumerate(axes):
                values = (axis.minValue, axis.defaultValue, axis.maxValue)
                require(all(type(v) in (int, float) and math.isfinite(v) for v in values)
                        and values[0] <= values[1] <= values[2] and values[0] < values[2], "input_axis",
                        "source_axis_range", face_index=index, axis_index=axis_index)
            require(16 <= font["head"].unitsPerEm <= 16384, "metrics",
                    "source_upem", face_index=index)
            require(1 <= font["OS/2"].usWeightClass <= 1000
                    and 1 <= font["OS/2"].usWidthClass <= 9,
                    "font_tables", "source_weight_width", face_index=index)
            inventory.append({"face_index": index,
                              "glyph_count": font["maxp"].numGlyphs,
                              "axis_tags": list(SOURCE_AXES),
                              "table_count": len(tags),
                              "table_tags": sorted(tags)})
    return inventory


def production_preflight(source=None):
    """Return a public-safe BLOCKED report, including available source checks.

    The source profile is a code constant, not a caller-supplied acceptance
    manifest.  An exact identity match binds all raw original fvar/avar/name/
    cmap/layout bytes without interpreting or normalizing their semantics.
    """
    report = {
        "schema_version": 1,
        "profile": PROFILE,
        "status": "BLOCKED",
        "source_identity_verified": False,
        "source_structure_verified": False,
        "source_unchanged": False,
        "physical_faces_checked": 0,
        "reconstructed_faces": 0,
        "production_rebuild_permitted": False,
        "production_acceptance": False,
        "font_generated": False,
        "windows_acceptance": "NOT_RUN",
        "required_interfaces": {"A3": "NOT_INTEGRATED", "B1": "NOT_INTEGRATED"},
        "failures": [
            StagingError("input_axis", "a3_production_input_unavailable").to_dict(),
            StagingError("metrics", "b1_production_metrics_unavailable").to_dict(),
        ],
    }
    try:
        require(source is not None, "platform_read", "source_not_supplied")
        path = Path(source)
        digest, byte_size = _identity(path)
        require(digest == SOURCE_SHA256 and byte_size == SOURCE_BYTES,
                "font_tables", "original_source_identity_mismatch",
                expected_count=SOURCE_BYTES, actual_count=byte_size,
                source_sha256=digest)
        report["source_sha256"] = digest
        report["source_identity_verified"] = True
        inventory = _inventory(path)
        final_digest, final_size = _identity(path)
        require(final_digest == digest and final_size == byte_size,
                "serialization", "source_changed", stage="preflight")
        report["source_unchanged"] = True
        report["source_structure_verified"] = True
        report["physical_faces_checked"] = len(inventory)
        report["source_inventory"] = inventory
    except StagingError as error:
        report["failures"].append(error.to_dict())
    except (OSError, ValueError, KeyError, TypeError, AssertionError, struct.error):
        report["failures"].append(StagingError("platform_read", "source_read_failed").to_dict())
    except Exception:
        # fontTools readers can raise parser-specific errors. Their messages
        # can contain private paths or glyph names and must not escape to CI.
        report["failures"].append(StagingError("font_tables", "source_table_decode_failed").to_dict())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(production_preflight(args.source), sort_keys=True,
                     indent=2, allow_nan=False))
    return 2  # BLOCKED is never a success exit status, including exact input.


if __name__ == "__main__":
    raise SystemExit(main())
