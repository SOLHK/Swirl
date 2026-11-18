#!/usr/bin/env python3
"""Original B1 UPEM discriminator; no Apple font data or corrected observations.

Only ``head.unitsPerEm`` differs between each 1000/1024 pair. Design coordinates
and metric integers stay identical. A visible rectangle witnesses the same
height as the hidden phantom points, but never purports to expose those points.
Every native invocation must isolate one font in a fresh process.

The candidate arithmetic is preregistered, exact-rational prediction, not an
implementation of CoreText and not a replacement for an observed API result.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.builder import buildVarIdxMap
from fontTools.varLib.varStore import OnlineVarStoreBuilder


UPMS = (1000, 1024)
ORDER = (".notdef", "control", "witness")
TAGS = ("WDTH", "HGHT")
TRAINING_Y = (-1.0, 0.0, 0.25, 0.375, 1.0)
HOLDOUT_Y = (-0.625, 0.125, 0.625)
WIDTH_X = (-1.0, 0.0, 1.0)
VARIANTS = (
    "gvar", "hvar", "vvar", "hvar_vvar", "hhea_ascent", "vhea_ascent",
    "os2_typo_ascent", "os2_use_typo", "os2_typo_ascent_use_typo", "vorg_y", "phantom_shift_1",
    "phantom_shift_91", "phantom_only",
)
REFERENCES = [
    "https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/fontBuilder.py",
    "https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/ttLib/tables/_g_l_y_f.py",
    "https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/varLib/varStore.py",
    "https://learn.microsoft.com/en-us/typography/opentype/spec/gvar",
    "https://learn.microsoft.com/en-us/typography/opentype/spec/vvar",
    "https://learn.microsoft.com/en-us/typography/opentype/spec/vorg",
]
EFFECTS = {
    "gvar": "Original gvar-only reference; no metric-variation tables.",
    "hvar": "Add equivalent HVAR only; gvar phantom data remains identical.",
    "vvar": "Add equivalent VVAR only; no VOrgMap in TrueType.",
    "hvar_vvar": "Add independently equivalent HVAR and VVAR.",
    "hhea_ascent": "Change only hhea.ascent from 800 to 891.",
    "vhea_ascent": "Change only vhea.ascent from 500 to 591.",
    "os2_typo_ascent": "Change only OS/2.sTypoAscender from 800 to 891.",
    "os2_use_typo": "Set only OS/2.fsSelection USE_TYPO_METRICS (bit 7).",
    "os2_typo_ascent_use_typo": "Against os2_typo_ascent (891), set only USE_TYPO_METRICS bit 7; hhea stays 800.",
    "vorg_y": "Add VORG Y=911; diagnostic use with glyf is outside VORG's CFF/CFF2 contract.",
    "phantom_shift_1": "Translate witness top/bottom phantoms by +1 via vmtx bearing only; height unchanged.",
    "phantom_shift_91": "Translate witness top/bottom phantoms by +91 via vmtx bearing only; height unchanged.",
    "phantom_only": "Keep identical variable phantoms; freeze visible HGHT outline coordinates. Path is a counterfactual control, not a same-height witness.",
}


def exact(value) -> Fraction:
    """Reject nonfinite inputs and preserve the actual binary input exactly."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("coordinate must be a finite number")
    if not math.isfinite(value):
        raise ValueError("coordinate must be finite")
    return Fraction(value)


def rational(value) -> dict:
    value = exact(value)
    return {"numerator": value.numerator, "denominator": value.denominator,
            "value": float(value)}


def phantom_shift(variant: str) -> int:
    return {"phantom_shift_1": 1, "phantom_shift_91": 91}.get(variant, 0)


def rational_predictions(y, upem: int, phantom_shift: int = 0) -> dict:
    """Competing predictions retain each intermediate and the rounding rule.

    +91 is chosen *before* native results: at y=-1/UPEM1000 the
    per-coordinate-toward-zero candidate predicts 850, while difference-first
    predicts 849. The unshifted pair does not separate these final integers.
    """
    y = exact(y)
    if upem not in UPMS or not -1 <= y <= 1:
        raise ValueError("unsupported UPEM or coordinate outside [-1, 1]")
    top, bottom = 820 + phantom_shift + 60*y, -180 + phantom_shift - 90*y
    rounded_top, rounded_bottom = math.floor(top + Fraction(1, 2)), math.floor(bottom + Fraction(1, 2))
    height = top - bottom
    rounded_difference = rounded_top - rounded_bottom
    difference_em_code = int(Fraction(rounded_difference * 65536, upem))
    difference_em_funits = Fraction(difference_em_code * upem, 65536)
    top_em_code = int(Fraction(rounded_top * 65536, upem))
    bottom_em_code = int(Fraction(rounded_bottom * 65536, upem))
    coordinate_em_funits = Fraction((top_em_code - bottom_em_code) * upem, 65536)
    return {
        "status": "PREREGISTERED_PREDICTIONS_NOT_NATIVE_OBSERVATIONS",
        "top": rational(top), "bottom": rational(bottom), "height": rational(height),
        "rounded_top": rounded_top, "rounded_bottom": rounded_bottom,
        "round_each_phantom": rounded_difference,
        "round_height_once": math.floor(height + Fraction(1, 2)),
        "difference_first": {
            "rule": "trunc(trunc((round_half_up(top)-round_half_up(bottom))*65536/UPEM)*UPEM/65536)",
            "em16_16_integer": difference_em_code,
            "before_final_truncation": rational(difference_em_funits),
            "prediction": int(difference_em_funits),
        },
        "coordinate_first": {
            "rule": "trunc((trunc(round_half_up(top)*65536/UPEM)-trunc(round_half_up(bottom)*65536/UPEM))*UPEM/65536)",
            "top_em16_16_integer": top_em_code,
            "bottom_em16_16_integer": bottom_em_code,
            "before_final_truncation": rational(coordinate_em_funits),
            "prediction": int(coordinate_em_funits),
        },
    }


def expected_metrics(x, y, shift: int = 0, *, phantom_only: bool = False) -> dict:
    x, y = exact(x), exact(y)
    if not (-1 <= x <= 1 and -1 <= y <= 1):
        raise ValueError("coordinate outside [-1, 1]")
    width, height = 1000 + 200*x, 1000 + 150*y
    top, bottom = 820 + 60*y, -180 - 90*y
    visible_top, visible_bottom = (Fraction(820), Fraction(-180)) if phantom_only else (top, bottom)
    return {
        "advance_width": float(width), "advance_height": float(height),
        "vertical_origin_y": float(top + shift),
        "vertical_origin_x_current_half_width": float(width / 2),
        "vertical_origin_x_default_half_width": 500.0,
        "witness_bounds": [100.0, float(visible_bottom), float(600 + 200*x), float(visible_top - visible_bottom)],
        "basis": {"width": rational(width), "height": rational(height),
                  "phantom_top": rational(top + shift), "phantom_bottom": rational(bottom + shift),
                  "visible_top": rational(visible_top), "visible_bottom": rational(visible_bottom)},
        "outline_role": "fixed_height_counterfactual" if phantom_only else "same_height_visible_witness",
        "basis_note": "Design-space model, not a CoreText result; VORG is separately probed, never silently substituted.",
    }


def _rectangle(left, bottom, right, top):
    pen = TTGlyphPen(None)
    pen.moveTo((left, bottom)); pen.lineTo((right, bottom))
    pen.lineTo((right, top)); pen.lineTo((left, top)); pen.closePath()
    return pen.glyph()


def _add_equivalent_metric_table(font, tag: str) -> None:
    supports = [{"WDTH": (0.0, 1.0, 1.0)}, {"WDTH": (-1.0, -1.0, 0.0)},
                {"HGHT": (0.0, 1.0, 1.0)}, {"HGHT": (-1.0, -1.0, 0.0)}]
    builder = OnlineVarStoreBuilder(list(TAGS))
    builder.setSupports(supports)
    zero = builder.storeDeltas([0, 0, 0, 0])
    table = getattr(otTables, tag)()
    table.Version = 0x00010000
    if tag == "HVAR":
        field, deltas, bearings = "AdvWidthMap", [200, -200, 0, 0], ("LsbMap", "RsbMap")
    else:
        field, deltas, bearings = "AdvHeightMap", [0, 0, 150, -150], ("TsbMap", "BsbMap")
        table.VOrgMap = None
    variable = builder.storeDeltas(deltas)
    setattr(table, field, buildVarIdxMap([zero, zero, variable], list(ORDER)))
    for bearing in bearings:
        setattr(table, bearing, buildVarIdxMap([zero, zero, zero], list(ORDER)))
    table.VarStore = builder.finish()
    font[tag] = newTable(tag)
    font[tag].table = table


def build_fixture(upem: int, variant: str = "gvar") -> TTFont:
    if upem not in UPMS or variant not in VARIANTS:
        raise ValueError("unsupported B1 fixture")
    builder = FontBuilder(upem, isTTF=True)
    builder.setupGlyphOrder(list(ORDER))
    builder.setupCharacterMap({32: "control", 0x4E00: "witness"})
    glyphs = {".notdef": _rectangle(50, 0, 500, 700),
              "control": TTGlyphPen(None).glyph(),
              "witness": _rectangle(100, -180, 700, 820)}
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({".notdef": (550, 50), "control": (400, 0), "witness": (1000, 100)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupVerticalMetrics({".notdef": (1000, 120), "control": (1000, 820),
                                  "witness": (1000, phantom_shift(variant))})
    builder.setupVerticalHeader(ascent=500, descent=-500)
    builder.setupNameTable({"familyName": "Swirl B1 Metric Fixture", "styleName": "Regular",
                           "uniqueFontIdentifier": "SwirlB1MetricFixture-1",
                           "fullName": "Swirl B1 Metric Fixture Regular",
                           "psName": "SwirlB1MetricFixture-Regular", "version": "Version 1.0"})
    builder.setupOS2(version=4, sTypoAscender=800, sTypoDescender=-200, sTypoLineGap=0,
                     usWinAscent=1000, usWinDescent=300, fsSelection=0x40)
    builder.setupPost()
    builder.setupFvar([("WDTH", -1, 0, 1, "Width"), ("HGHT", -1, 0, 1, "Height")], [])
    # Every visible witness coordinate is explicit; no IUP/instruction ambiguity.
    coordinates, _, _ = glyphs["witness"].getCoordinates(builder.font["glyf"])
    width = [(200 if x == 700 else 0, 0) for x, y in coordinates] + [(0, 0), (200, 0), (0, 0), (0, 0)]
    height = [(0, 0 if variant == "phantom_only" else (60 if y == 820 else -90))
              for x, y in coordinates] + [(0, 0), (0, 0), (0, 60), (0, -90)]
    variations = []
    for tag, deltas in (("WDTH", width), ("HGHT", height)):
        variations.append(TupleVariation({tag: (0, 1, 1)}, deltas))
        variations.append(TupleVariation({tag: (-1, -1, 0)}, [(-x, -y) for x, y in deltas]))
    builder.setupGvar({".notdef": [], "control": [], "witness": variations})
    font = builder.font
    if variant in ("hvar", "hvar_vvar"):
        _add_equivalent_metric_table(font, "HVAR")
    if variant in ("vvar", "hvar_vvar"):
        _add_equivalent_metric_table(font, "VVAR")
    if variant == "hhea_ascent": font["hhea"].ascent += 91
    if variant == "vhea_ascent": font["vhea"].ascent += 91
    if variant in ("os2_typo_ascent", "os2_typo_ascent_use_typo"): font["OS/2"].sTypoAscender += 91
    if variant in ("os2_use_typo", "os2_typo_ascent_use_typo"): font["OS/2"].fsSelection |= 1 << 7
    if variant == "vorg_y":
        table = newTable("VORG")
        table.majorVersion, table.minorVersion = 1, 0
        table.defaultVertOriginY, table.VOriginRecords = 911, {}
        font["VORG"] = table
    builder.setupMaxp()
    font["head"].created = font["head"].modified = 3_800_000_000
    font.recalcTimestamp = False
    return font


def comparison_table_bytes(font: TTFont) -> dict[str, bytes]:
    """Only neutralize the mandatory whole-font checksum, not field changes."""
    result = {str(tag): font.reader[tag] for tag in font.reader.keys()}
    head = result["head"]
    result["head"] = head[:8] + bytes(4) + head[12:]
    return result


def storage_snapshot(font: TTFont) -> dict:
    witness = font["glyf"]["witness"]
    coordinates, _, _ = witness.getCoordinates(font["glyf"])
    return {
        "units_per_em": font["head"].unitsPerEm,
        "glyph_order": font.getGlyphOrder(),
        "hmtx": {name: list(font["hmtx"].metrics[name]) for name in ORDER},
        "vmtx": {name: list(font["vmtx"].metrics[name]) for name in ORDER},
        "witness_coordinates": [list(p) for p in coordinates],
        "gvar": [{"support": v.axes, "deltas": [list(p) if p is not None else None for p in v.coordinates]}
                 for v in font["gvar"].variations["witness"]],
        "hhea": {k: getattr(font["hhea"], k) for k in ("ascent", "descent", "lineGap")},
        "vhea": {k: getattr(font["vhea"], k) for k in ("ascent", "descent", "lineGap", "minTopSideBearing", "minBottomSideBearing")},
        "OS2": {k: getattr(font["OS/2"], k) for k in ("sTypoAscender", "sTypoDescender", "sTypoLineGap", "usWinAscent", "usWinDescent", "fsSelection")},
        "VORG": {"defaultVertOriginY": font["VORG"].defaultVertOriginY} if "VORG" in font else None,
        "HVAR_present": "HVAR" in font, "VVAR_present": "VVAR" in font,
        "VVAR_VOrgMap": None,
    }


def fixture_requests(upem: int, variant: str) -> list[dict]:
    shift = phantom_shift(variant)
    result = []
    for partition, ys in (("training", TRAINING_Y), ("holdout", HOLDOUT_Y)):
        for x, y in itertools.product(WIDTH_X, ys):
            result.append({"id": f"{partition}-x{x:g}-y{y:g}", "axes": {"WDTH": x, "HGHT": y},
                           "point_size": upem, "partition": partition,
                           "expected": expected_metrics(x, y, shift, phantom_only=(variant == "phantom_only")),
                           "hypotheses": rational_predictions(y, upem, shift)})
    return result


def changed_fields(before, after, prefix="") -> list[dict]:
    """Show observed storage-field differences, including dependent headers."""
    if type(before) is dict and type(after) is dict and before.keys() == after.keys():
        return [change for key in sorted(before)
                for change in changed_fields(before[key], after[key], f"{prefix}.{key}".lstrip("."))]
    if type(before) is list and type(after) is list and len(before) == len(after):
        return [change for index, (left, right) in enumerate(zip(before, after))
                for change in changed_fields(left, right, f"{prefix}[{index}]")]
    return [] if before == after else [{"field": prefix, "before": before, "after": after}]


def build_suite(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for upem in UPMS:
        tables_by_variant, storage_by_variant = {}, {}
        for variant in VARIANTS:
            fixture_id = f"upem{upem}-{variant}"
            path = out_dir / f"{fixture_id}.ttf"
            font = build_fixture(upem, variant)
            font.save(path)
            font.close()
            with TTFont(path, recalcTimestamp=False) as reopened:
                normalized = comparison_table_bytes(reopened)
                tables_by_variant[variant] = normalized
                snapshot = storage_snapshot(reopened)
                storage_by_variant[variant] = snapshot
                base_tables = tables_by_variant["gvar"]
                changed = sorted(tag for tag in normalized.keys() | base_tables.keys()
                                 if normalized.get(tag) != base_tables.get(tag))
                comparison_variant = "os2_typo_ascent" if variant == "os2_typo_ascent_use_typo" else "gvar"
                comparison_tables = tables_by_variant[comparison_variant]
                entries.append({
                    "fixture_id": fixture_id, "path": path.name, "upem": upem,
                    "variant": variant, "phantom_shift": phantom_shift(variant),
                    "expected_effect": EFFECTS[variant],
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "table_sha256": {str(tag): hashlib.sha256(reopened.reader[tag]).hexdigest()
                                     for tag in reopened.reader.keys()},
                    "changed_tables_vs_gvar": changed,
                    "comparison_variant": comparison_variant,
                    "changed_tables_vs_comparison": sorted(tag for tag in normalized.keys() | comparison_tables.keys()
                                                           if normalized.get(tag) != comparison_tables.get(tag)),
                    "changed_fields": changed_fields(storage_by_variant[comparison_variant], snapshot),
                    "table_comparison_rule": "Only head.checkSumAdjustment bytes 8:12 are zeroed; other changes remain visible.",
                    "storage": snapshot,
                    "requests": fixture_requests(upem, variant),
                })
    manifest = {"schema_version": 1, "source": "self_authored_geometry_no_Apple_data",
                "experiment": "B1 UPEM1000/1024 independent metric-source discriminator",
                "native_acceptance": "NOT_RUN", "original_font_acceptance": "NOT_ESTABLISHED",
                "strict_budget_font_units": 1/32,
                "scalar_model": "Exact rational design units; native raw binary64 observations must be saved separately.",
                "sampling": {"training_y": list(TRAINING_Y), "holdout_y": list(HOLDOUT_Y), "width_x": list(WIDTH_X)},
                "entries": entries, "references": REFERENCES}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_suite(args.out_dir)
    print(json.dumps({"fixture_count": len(manifest["entries"]),
                      "request_count": sum(len(e["requests"]) for e in manifest["entries"]),
                      "manifest": str(args.out_dir / "manifest.json"),
                      "native_acceptance": "NOT_RUN"}))


if __name__ == "__main__":
    main()
