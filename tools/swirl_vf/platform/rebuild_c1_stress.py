#!/usr/bin/env python3
"""Reproducible C1 original-font stress; default one complete 47,102-GID face.

No font input is accepted. Only the project's original geometric fixture is
generated. All font/TTC bytes live in TemporaryDirectory and are removed even
on failure. Stdout contains one safe JSON summary; no font bytes, paths, glyph
coordinates or character mappings are emitted.

Use --glyph-count 7 or 127 for a quick CI smoke run. The full default measures
whole-face validation separately from the streaming packer's Python allocation
peak. The latter must not be presented as the whole pipeline's memory usage.
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import platform
import sys
import tempfile
import time
import tracemalloc

import fontTools
from fontTools.ttLib import TTCollection, TTFont
import numpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from rebuild_c1_fixture import write_faces
from ttc_staging_contract import StagingError
from ttc_staging_pack import pack_collection
from ttc_staging_validate import validate_face


def _environment():
    return {"python_version": platform.python_version(),
            "fonttools_version": fontTools.__version__,
            "numpy_version": numpy.__version__,
            "platform_system": platform.system(),
            "platform_release": platform.release(),
            "machine": platform.machine()}


def _peak_rss():
    try:
        import resource
    except ImportError:
        return {"process_peak_rss_bytes": None,
                "process_peak_rss_measurement": "resource_unavailable"}
    try:
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (OSError, ValueError):
        return {"process_peak_rss_bytes": None,
                "process_peak_rss_measurement": "resource_query_failed"}
    # ru_maxrss is KiB on Linux and bytes on macOS. Do not guess other hosts'
    # units or substitute zero on Windows where resource is unavailable.
    if sys.platform.startswith("linux"):
        value = int(raw * 1024)
    elif sys.platform == "darwin":
        value = int(raw)
    else:
        return {"process_peak_rss_bytes": None,
                "process_peak_rss_measurement": "unsupported_platform_units"}
    return {"process_peak_rss_bytes": value,
            "process_peak_rss_measurement": "whole_process_resource_peak_including_generation_and_validation"}


def run(glyph_count=47102):
    if type(glyph_count) is not int or not 7 <= glyph_count <= 65535:
        raise StagingError("font_tables", "invalid_stress_glyph_count")
    if tracemalloc.is_tracing():
        raise StagingError("serialization", "stress_requires_separate_tracemalloc_session")
    began = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="c1-original-stress-") as temporary:
        root = Path(temporary)
        start = time.perf_counter()
        paths = write_faces(root / "faces", count=1, glyph_count=glyph_count)
        generated_seconds = time.perf_counter() - start
        source_size = paths[0].stat().st_size
        start = time.perf_counter()
        with TTFont(paths[0], lazy=True, recalcTimestamp=False) as font:
            validation = validate_face(font)
        validation_seconds = time.perf_counter() - start
        # A closed TTFont still owns its decoded objects until its last Python
        # reference goes away. Release it before the independent packing phase.
        del font
        gc.collect()
        output = root / "original-stress.staging.ttc"
        start = time.perf_counter()
        tracemalloc.start()
        try:
            packing = pack_collection(paths, output, chunk_size=65536)
            _current, pack_peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        packing_seconds = time.perf_counter() - start
        start = time.perf_counter()
        with TTCollection(output, lazy=True) as collection:
            if len(collection.fonts) != 1:
                raise StagingError("serialization", "stress_collection_face_count")
            reopened = collection.fonts[0]
            order = reopened.getGlyphOrder()
            expected_last = "curve" if glyph_count == 7 else f"unused{glyph_count-1:05d}"
            if (reopened["maxp"].numGlyphs != glyph_count or len(order) != glyph_count
                    or order[0] != ".notdef" or order[-1] != expected_last):
                raise StagingError("serialization", "stress_reopened_gid_coverage")
        reopening_seconds = time.perf_counter() - start
        result = {"schema": 1, "status": "PASS_C1_ORIGINAL_STRESS",
                  "environment": _environment(),
                  "original_synthetic_fixture_only": True,
                  "actual_original_font_executed": False,
                  "production_accepted": False,
                  "glyph_count": glyph_count, "physical_faces": 1,
                  "source_byte_size": source_size,
                  "fixture_generation_seconds": generated_seconds,
                  "source_validation_seconds": validation_seconds,
                  "packing_seconds": packing_seconds,
                  "reopening_seconds": reopening_seconds,
                  "validation": validation, "packing": packing,
                  "pack_tracemalloc_peak_bytes": pack_peak,
                  "pack_tracemalloc_scope": "new_python_allocations_during_pack_only_excludes_prior_validation",
                  "memory_limitation": "whole_face_fonttools_validation_materializes_outline_and_variation_objects",
                  **_peak_rss()}
    result["elapsed_seconds_including_cleanup"] = time.perf_counter() - began
    result["temporary_font_files_cleaned"] = True
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glyph-count", type=int, default=47102)
    args = parser.parse_args()
    try:
        result = run(args.glyph_count)
        exit_code = 0
    except StagingError as error:
        result = {"schema": 1, "status": "FAILED_C1_ORIGINAL_STRESS",
                  "environment": _environment(), "production_accepted": False,
                  "actual_original_font_executed": False, "failure": error.to_dict()}
        exit_code = 2
    except Exception as error:
        # Do not forward exception messages that can embed paths or font data.
        result = {"schema": 1, "status": "FAILED_C1_ORIGINAL_STRESS",
                  "environment": _environment(), "production_accepted": False,
                  "actual_original_font_executed": False,
                  "failure": {"category": "serialization", "code": "stress_execution_failed",
                              "exception_type": type(error).__name__}}
        exit_code = 2
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
