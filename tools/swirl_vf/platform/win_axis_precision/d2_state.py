#!/usr/bin/env python3
"""D2-1 source-bound private-ABI experiment; never a production acceptance gate."""
from __future__ import annotations
import argparse
import difflib
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import subprocess

QT_COMMIT = "7ddbc87d8e14ce51d2957ea72d0a6077593d5ff4"
SOURCE_BLOBS = {
    "src/gui/text/freetype/qfontengine_ft.cpp": "e331a4cc8158ed4d0e66c2f24ab4247d9752be02",
    "src/3rdparty/freetype/src/base/ftobjs.c": "f9f64c40fec3118263cf409af8efc3c407c90863",
}
OFFSETS = [[0,0], [.25,0], [.5,0], [.75,0], [0,0], [.75,0], [.5,0], [.25,0], [0,0], [0,.25], [.25,.25], [0,.25]]


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def extract_function(text, name):
    """Extract only one pinned, self-contained FT API function, retaining its body."""
    matches = list(re.finditer(r"FT_EXPORT_DEF\s*\(\s*void\s*\)\s*" + re.escape(name) + r"\s*\(", text))
    check(len(matches) == 1, "Missing/ambiguous function: " + name)
    start = matches[0].start()
    brace = text.index("{", matches[0].end())
    # The three pinned bodies have no braces inside comments or string literals.
    depth = 1
    end = brace + 1
    while end < len(text) and depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    check(depth == 0, "Unterminated function: " + name)
    result = text[start:end]
    calls = set(re.findall(r"\b(FT_\w+)\s*\(", result))
    check(calls <= {"FT_EXPORT_DEF", name}, "Function is not a self-contained state accessor")
    return result


def patch_source(text):
    begin = text.index("void QFontEngineFT::addGlyphsToPath(")
    end = text.index("\nglyph_t QFontEngineFT::glyphIndex(", begin)
    function = text[begin:end]
    old = "    FT_Face face = lockFace(Unscaled);\n"
    check(function.count(old) == 1 and function.count("    unlockFace();") == 1, "Unexpected outline implementation")
    new = old + '''    const auto unlock = qScopeGuard([this] { unlockFace(); });
    FT_Matrix outlineMatrix;
    FT_Vector savedDelta;
    FT_Get_Transform(face, &outlineMatrix, &savedDelta);
    const auto restore = qScopeGuard([&] {
        FT_Set_Transform(face, &outlineMatrix, &savedDelta);
    });
    FT_Set_Transform(face, &outlineMatrix, nullptr);
'''
    patched = function.replace(old, new).replace("    unlockFace();\n", "")
    return text[:begin] + patched + text[end:]


def prepare(qt, out):
    check(subprocess.check_output(["git", "-C", str(qt), "rev-parse", "HEAD"], text=True).strip() == QT_COMMIT,
          "Qt checkout is not pinned")
    out.mkdir(parents=True, exist_ok=False)
    sources = {}
    for relative, expected in SOURCE_BLOBS.items():
        data = subprocess.check_output(["git", "-C", str(qt), "show", "HEAD:" + relative])
        check((qt / relative).read_bytes().replace(b"\r\n", b"\n") == data, "Modified Qt working tree")
        check(blob(data) == expected, "Upstream source identity mismatch: " + relative)
        sources[relative] = {"git_blob": expected, "sha256": digest(data)}
    ft = (qt / "src/3rdparty/freetype/src/base/ftobjs.c").read_text(encoding="utf-8")
    names = ("FT_Get_Transform", "FT_Set_Transform", "FT_Library_Version")
    definitions = [extract_function(ft, name) for name in names]
    macros = "\n".join("#define " + name + " d2_" + name for name in names)
    header = '''/* Test-only accessors extracted from pinned FreeType, not another rasterizer. */
#include <ft2build.h>
#include FT_FREETYPE_H
#ifdef __cplusplus
extern "C" {
#endif
void d2_FT_Get_Transform(FT_Face, FT_Matrix *, FT_Vector *);
void d2_FT_Set_Transform(FT_Face, FT_Matrix *, FT_Vector *);
void d2_FT_Library_Version(FT_Library, FT_Int *, FT_Int *, FT_Int *);
#ifdef __cplusplus
}
#endif
'''
    (out / "d2_ft_access.h").write_text(header, encoding="utf-8")
    # Preserve upstream's copyright header; the complete license travels with evidence.
    notice = ft[:ft.index("#include")]
    access = notice + "\n#include <ft2build.h>\n#include <freetype/internal/ftobjs.h>\n" + macros + "\n\n" + "\n\n".join(definitions) + "\n"
    (out / "d2_ft_access.c").write_text(access, encoding="utf-8")
    for filename in ("LICENSE.txt", "FTL.TXT"):
        candidates = list((qt / "src/3rdparty/freetype").rglob(filename))
        if candidates:
            (out / filename).write_bytes(candidates[0].read_bytes())
    text = (qt / "src/gui/text/freetype/qfontengine_ft.cpp").read_text(encoding="utf-8")
    changed = patch_source(text)
    patch = "".join(difflib.unified_diff(text.splitlines(keepends=True), changed.splitlines(keepends=True),
                                      fromfile="a/src/gui/text/freetype/qfontengine_ft.cpp",
                                      tofile="b/src/gui/text/freetype/qfontengine_ft.cpp"))
    (out / "qt-6.10.3-outline-delta.patch").write_text(patch, encoding="utf-8")
    report = {"qt_commit": QT_COMMIT, "source_files": sources, "accessors_sha256": digest(access.encode()),
              "patch_sha256": digest(patch.encode()), "upstream_patch_applied": False,
              "method": "Compile only the exact FT transform accessors and version reader; Qt keeps its own bundled rasterizer"}
    (out / "source-binding.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


def valid_path(path):
    check(isinstance(path, list) and len(path) >= 3, "Missing original outline")
    for element in path:
        check(isinstance(element, list) and len(element) == 3 and element[0] in (0,1,2,3), "Malformed path")
        check(all(isinstance(x, (int,float)) and math.isfinite(x) for x in element[1:]), "Nonfinite path")


def valid_state(state):
    for key, size in (("matrix_16_16", 4), ("delta_26_6", 2), ("qt_cached_matrix_16_16", 4)):
        values = state[key]
        check(isinstance(values, list) and len(values) == size
              and all(isinstance(x, (int, float)) and math.isfinite(x) and x == int(x) for x in values),
              "Invalid transform state")


def validate(rows, source_sha, font_sha):
    check(len(rows) == len(OFFSETS) + 2, "Incomplete native log")
    head, tail = rows[0], rows[-1]
    check(head["record"] == "header" and tail["record"] == "summary", "Bad log framing")
    check(head["source_commit"] == source_sha and head["input_sha256"] == font_sha, "Wrong source or font")
    check(head["actual_backend"] == "QFontEngineFT" and head["qt_version"] == "6.10.3", "Wrong runtime")
    check(head["table_identity_exact"] is True and head["freetype_version"] == "2.14.3", "Unverified physical runtime")
    check(head["mode"] in ("control", "guard"), "Unknown isolation mode")
    check(tail["status"] == "DIAGNOSTIC_PASS_NOT_D1_ACCEPTANCE" and tail["production_fix"] is False, "Invalid acceptance claim")
    check(head["fixed_axes"] == {"wght": 499.006195068359375, "WDTH": 100, "HGHT": 100}, "Axis request changed")
    check(head["scope"] == "PRIVATE_ABI_DIAGNOSTIC_NOT_PRODUCTION_FIX", "Wrong experiment scope")
    valid_path(head["baseline_path"])
    valid_state(head["baseline_state"])
    changed = isolated = 0
    for index, row in enumerate(rows[1:-1]):
        check(row["record"] == "observation" and row["index"] == index and row["offset"] == OFFSETS[index], "Missing/reordered offset")
        for name in ("before_draw", "after_draw", "before_guard", "after_guard"):
            valid_state(row[name])
        for name in ("original_path", "isolated_path", "original_replay"):
            valid_path(row[name])
        check(row["original_path"] == row["original_replay"], "Failure erased by intervention")
        check(row["before_guard"] == row["after_guard"], "Transform not restored")
        check(row["cache_after"] == row["cache_after_guard"], "Cache changed by isolation")
        check(row["advance"] == head["baseline_advance"], "Advance changed")
        changed += row["original_path"] != head["baseline_path"]
        isolated += row["isolated_path"] != head["baseline_path"]
        if head["mode"] == "guard":
            check(row["isolated_path"] == head["baseline_path"], "Isolated outline differs exactly")
        else:
            check(row["isolated_path"] == row["original_path"], "Control secretly isolated")
    check(tail["observations"] == len(OFFSETS) and tail["original_path_mismatches"] == changed
          and tail["isolated_path_mismatches"] == isolated, "Dishonest native counts")
    return {"original_mismatches": changed, "isolated_mismatches": isolated}


def run(exe, font, out, expected):
    check(os.name == "nt", "Native Windows required")
    check(os.environ.get("GITHUB_SHA") == expected, "Wrong workflow source SHA")
    out.mkdir(parents=True, exist_ok=False)
    font_sha = digest(font.read_bytes())
    report = {"source_commit": expected, "font_sha256": font_sha, "status": "FAILED", "full_d1_acceptance": False,
              "production_fix": False, "executable_sha256": digest(exe.read_bytes()), "processes": [], "errors": []}
    completed = {}
    for dpi, dpr, hint, disabled, mode in itertools.product((96,144,192), (1,1.25,1.5,2), ("no","full"), (False,True), ("control","guard")):
        label = f"dpi{dpi}-dpr{dpr}-{hint}-cache{int(not disabled)}-{mode}"
        directory = out / label
        directory.mkdir()
        env = dict(os.environ, QT_QPA_PLATFORM="windows:fontengine=freetype", QT_NO_FT_CACHE=str(int(disabled)))
        entry = {"label": label, "status": "FAILED"}
        report["processes"].append(entry)
        try:
            process = subprocess.run([str(exe), str(font), str(directory), str(dpi), str(dpr), hint, mode],
                                     env=env, capture_output=True, timeout=90)
            (directory / "stdout.log").write_bytes(process.stdout)
            (directory / "stderr.log").write_bytes(process.stderr)
            entry["exit_code"] = process.returncode
            check(process.returncode == 0, f"Native exit {process.returncode}: {process.stderr.decode(errors='replace')}")
            log_bytes = (directory / "d2.jsonl").read_bytes()
            rows = [json.loads(line) for line in log_bytes.splitlines() if line.strip()]
            entry.update(validate(rows, expected, font_sha))
            check((rows[0]["logical_dpi"], rows[0]["dpr"], rows[0]["hint"], rows[0]["cache_disabled"], rows[0]["mode"])
                  == (dpi,dpr,hint,disabled,mode), "CLI mode does not match native header")
            pixels = []
            seen = {}
            for row in rows[1:-1]:
                image = (directory / (row["png"] + ".bin")).read_bytes()
                check(len(image) == row["width"] * row["height"] * 4 and digest(image) == row["pixel_sha256"], "Pixel evidence mismatch")
                check(image != b"\xff" * len(image), "Empty raster")
                key = tuple(row["offset"])
                check(key not in seen or seen[key] == image, "Raster replay mismatch")
                seen[key] = image
                pixels.append(image)
            completed[(dpi,dpr,hint,disabled,mode)] = (rows, pixels)
            entry.update(status="PASS_DIAGNOSTIC", log_sha256=digest(log_bytes))
        except Exception as exc:
            entry["error"] = str(exc)
            report["errors"].append(label + ": " + str(exc))
        (out / "d2-analysis.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    comparisons = 0
    for dpi,dpr,hint,disabled in itertools.product((96,144,192), (1,1.25,1.5,2), ("no","full"), (False,True)):
        try:
            a, ap = completed[(dpi,dpr,hint,disabled,"control")]
            b, bp = completed[(dpi,dpr,hint,disabled,"guard")]
            check(ap == bp, "Guard changed complete raster bytes")
            for x,y in zip(a[1:-1], b[1:-1]):
                for field in ("original_path", "advance", "before_draw", "after_draw", "cache_before", "cache_after"):
                    check(x[field] == y[field], "Guard changed independent replay: " + field)
            comparisons += 1
        except Exception as exc:
            report["errors"].append(f"comparison {dpi}/{dpr}/{hint}/{disabled}: {exc}")
    try:
        cold = completed[(96,1,"no",False,"control")][0]
        guarded = completed[(96,1,"no",False,"guard")][0]
        uncached = completed[(96,1,"no",True,"control")][0]
        check(cold[0]["baseline_state"]["delta_26_6"] == [0,0], "Not a cold baseline")
        check(cold[2]["after_draw"]["delta_26_6"] == [16,0], "Quarter-pixel delta not observed")
        check(cold[4]["after_draw"]["delta_26_6"] == [48,0], "Three-quarter delta not observed")
        check(cold[5]["after_draw"]["delta_26_6"] == [48,0], "Cached zero-offset draw did not retain prior delta")
        check(uncached[5]["after_draw"]["delta_26_6"] == [0,0], "Uncached draw did not reset delta")
        check(cold[2]["original_path"] != cold[0]["baseline_path"], "Original failure missing")
        check(guarded[2]["isolated_path"] == guarded[0]["baseline_path"], "Causal intervention failed")
        report["mechanism_confirmed"] = True
    except Exception as exc:
        report["mechanism_confirmed"] = False
        report["errors"].append("mechanism: " + str(exc))
    report["independent_control_guard_comparisons"] = comparisons
    report["observations"] = len(completed) * len(OFFSETS)
    report["status"] = "PASS_D2_DIAGNOSTIC_ONLY" if not report["errors"] else "FAILED"
    (out / "d2-analysis.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare"); p.add_argument("qt", type=Path); p.add_argument("out", type=Path)
    p = sub.add_parser("run"); p.add_argument("exe", type=Path); p.add_argument("font", type=Path); p.add_argument("out", type=Path); p.add_argument("sha")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.qt.resolve(), args.out.resolve())
    else:
        raise SystemExit(run(args.exe.resolve(), args.font.resolve(), args.out.resolve(), args.sha))
