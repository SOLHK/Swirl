#!/usr/bin/env python3
"""Preregistered B1 follow-up after the first native discrimination run.

The delta-rounding formula is an inference from run 39399674995, frozen before
the fresh coordinates below are measured. It is a falsifiable observation model,
never a correction of native measurements or a claim about Apple's internals.
The original first-stage fixture and its rejected candidate remain untouched.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path

from fontTools.ttLib import TTFont, newTable

from b1_metric_fixture import (
    UPMS, REFERENCES, build_fixture, changed_fields, comparison_table_bytes,
    exact, expected_metrics, phantom_shift, rational, rational_predictions,
    storage_snapshot,
)


STAGE_ONE_RUN = "https://github.com/SOLHK/Swirl/actions/runs/39399674995"
MODEL_STATUS = "POST_STAGE1_INFERENCE_FROZEN_BEFORE_FOLLOWUP_NATIVE"
FOLLOWUP_Y = (-0.9375, -0.875, -0.8125, -0.6875, -0.5625, -0.4375,
              -0.3125, -0.1875, -0.0625, 0.0625, 0.1875, 0.3125,
              0.4375, 0.5625, 0.6875, 0.8125, 0.9375)
FOLLOWUP_X = (-0.375, 0.0, 0.375)
ORIGIN_Y = (-0.0625, 0.0625)
EXACT_NORMALIZATION_Y = 53 / 64
HEIGHT_VARIANTS = ("gvar", "phantom_only", "phantom_shift_91", "vvar", "hvar_vvar")
ORIGIN_VARIANTS = ("hvar_vvar_vorg", "hvar_vvar_odd_default", "hvar_vvar_odd_default_vorg")
VARIANTS = HEIGHT_VARIANTS + ORIGIN_VARIANTS
COMPARISONS = {"gvar": "gvar", "phantom_only": "gvar", "phantom_shift_91": "gvar",
               "vvar": "gvar", "hvar_vvar": "vvar", "hvar_vvar_vorg": "hvar_vvar",
               "hvar_vvar_odd_default": "hvar_vvar",
               "hvar_vvar_odd_default_vorg": "hvar_vvar_odd_default"}


def round_delta_away(value) -> int:
    """Nearest integer with exactly-half ties away from zero, on a rational."""
    value = exact(value)
    return math.floor(value + Fraction(1, 2)) if value >= 0 else -math.floor(-value + Fraction(1, 2))


def delta_predictions(y, upem: int) -> dict:
    y = exact(y)
    if upem not in UPMS or not -1 <= y <= 1:
        raise ValueError("unsupported UPEM or coordinate outside [-1, 1]")
    top_delta, bottom_delta = 60*y, -90*y
    top_integer, bottom_integer = round_delta_away(top_delta), round_delta_away(bottom_delta)
    height = 1000 + top_integer - bottom_integer
    em_code = math.floor(Fraction(height * 65536, upem))
    before_truncation = Fraction(em_code * upem, 65536)
    continuous_height = 1000 + 150*y
    return {
        "status": MODEL_STATUS,
        "scope": "Finite synthetic gvar-height candidate; neither a measurement correction nor a native-internals proof.",
        "rule": "H=1000+round_away(60*y)-round_away(-90*y); trunc(floor(H*65536/UPEM)*UPEM/65536)",
        "top_delta": rational(top_delta), "bottom_delta": rational(bottom_delta),
        "round_away_top": top_integer, "round_away_bottom": bottom_integer,
        "phantom_height_integer": height, "em16_16_integer": em_code,
        "before_final_truncation": rational(before_truncation),
        "prediction": int(before_truncation),
        "vvar_truncate_continuous": {
            "rule": "trunc(1000+150*y)", "continuous_height": rational(continuous_height),
            "prediction": int(continuous_height),
            "scope": "Separate metric-table-source hypothesis; not asserted for gvar-only fonts.",
        },
    }


def _is_odd(variant: str) -> bool:
    return variant in ("hvar_vvar_odd_default", "hvar_vvar_odd_default_vorg")


def _has_vorg(variant: str) -> bool:
    return variant in ("hvar_vvar_vorg", "hvar_vvar_odd_default_vorg")


def build_followup_fixture(upem: int, variant: str) -> TTFont:
    if variant not in VARIANTS:
        raise ValueError("unsupported follow-up fixture")
    font = build_fixture(upem, variant if variant in HEIGHT_VARIANTS else "hvar_vvar")
    if _is_odd(variant):
        width, bearing = font["hmtx"].metrics["witness"]
        font["hmtx"].metrics["witness"] = (width + 1, bearing)
    if _has_vorg(variant):
        table = newTable("VORG")
        table.majorVersion, table.minorVersion = 1, 0
        table.defaultVertOriginY, table.VOriginRecords = 911, {}
        font["VORG"] = table
    return font


def followup_expected(x, y, variant: str) -> dict:
    if variant not in VARIANTS:
        raise ValueError("unsupported follow-up fixture")
    result = expected_metrics(x, y, phantom_shift(variant), phantom_only=(variant == "phantom_only"))
    if _is_odd(variant):
        width = exact(result["advance_width"]) + 1
        result["advance_width"] = float(width)
        result["vertical_origin_x_current_half_width"] = float(width / 2)
        result["vertical_origin_x_default_half_width"] = 500.5
        result["basis"]["width"] = rational(width)
        result["horizontal_semantic_change"] = "Diagnostic counterfactual only: witness stored hmtx advance +1; variation deltas and geometry unchanged."
    return result


def followup_requests(upem: int, variant: str) -> list[dict]:
    ys = FOLLOWUP_Y if variant in HEIGHT_VARIANTS else ORIGIN_Y
    group = "fresh_height_discriminator" if variant in HEIGHT_VARIANTS else "vorg_storage_control"
    result = [{"id": f"followup-x{x:g}-y{y:g}", "axes": {"WDTH": x, "HGHT": y},
             "point_size": upem, "partition": "holdout", "case_group": group,
             "expected": followup_expected(x, y, variant),
             "hypotheses": rational_predictions(y, upem, phantom_shift(variant))}
            for x, y in itertools.product(FOLLOWUP_X, ys)]
    if variant in ("gvar", "vvar"):
        # Before any follow-up native run, add an exactly representable EM
        # normalization point. H=1125 remains 1125; a universal nondefault -1
        # explanation would predict 1124. The first 546 requests stay unchanged.
        y = EXACT_NORMALIZATION_Y
        result.append({"id": f"followup-x0-y{y:g}", "axes": {"WDTH": 0.0, "HGHT": y},
                       "point_size": upem, "partition": "holdout",
                       "case_group": "exact_normalization_grid_control",
                       "expected": followup_expected(0.0, y, variant),
                       "hypotheses": rational_predictions(y, upem, phantom_shift(variant))})
    return result


def build_suite(out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for upem in UPMS:
        tables_by_variant, storage_by_variant = {}, {}
        for variant in VARIANTS:
            fixture_id = f"followup-upem{upem}-{variant}"
            path = out_dir / (fixture_id + ".ttf")
            font = build_followup_fixture(upem, variant)
            font.save(path); font.close()
            with TTFont(path, recalcTimestamp=False) as reopened:
                tables = comparison_table_bytes(reopened)
                snapshot = storage_snapshot(reopened)
                snapshot["hhea"]["advanceWidthMax"] = reopened["hhea"].advanceWidthMax
                tables_by_variant[variant], storage_by_variant[variant] = tables, snapshot
                comparison_variant = COMPARISONS[variant]
                comparison_tables = tables_by_variant[comparison_variant]
                requests = followup_requests(upem, variant)
                default_width = 1001 if _is_odd(variant) else 1000
                entries.append({
                    "fixture_id": fixture_id, "path": path.name, "upem": upem,
                    "variant": variant, "phantom_shift": phantom_shift(variant),
                    "comparison_variant": comparison_variant,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "table_sha256": {str(tag): hashlib.sha256(reopened.reader[tag]).hexdigest()
                                     for tag in reopened.reader.keys()},
                    "changed_tables_vs_comparison": sorted(tag for tag in tables.keys() | comparison_tables.keys()
                                                           if tables.get(tag) != comparison_tables.get(tag)),
                    "changed_fields": changed_fields(storage_by_variant[comparison_variant], snapshot),
                    "storage": snapshot, "requests": requests,
                    "predictions_round_delta": {r["id"]: delta_predictions(r["axes"]["HGHT"], upem) for r in requests},
                    "origin_x_storage_hypotheses": {
                        "stored_advance_width": default_width,
                        "exact_stored_half": rational(Fraction(default_width, 2)),
                        "truncated_stored_half": int(Fraction(default_width, 2)),
                        "VORG_present": _has_vorg(variant),
                        "VORG_y": 911 if _has_vorg(variant) else None,
                        "scope": "VORG stores only Y. Any observed X dependence is a native behavioral inference; no X is written to VORG.",
                        "strict_reference_unchanged": "Continue comparing API origins against the continuous phantom/current-width model; save VORG alternatives separately.",
                    },
                    "table_comparison_rule": "Only mandatory head.checkSumAdjustment bytes 8:12 are neutralized.",
                })
    manifest = {
        "schema_version": 1, "source": "self_authored_geometry_no_Apple_data",
        "experiment": "B1 fresh-coordinate delta-rounding and VORG storage follow-up",
        "model_status": MODEL_STATUS, "inference_evidence_run": STAGE_ONE_RUN,
        "native_acceptance": "NOT_RUN", "original_font_acceptance": "NOT_ESTABLISHED",
        "measurement_correction_applied": False, "strict_budget_font_units": 1/32,
        "previous_candidates_preserved": True,
        "sampling": {"fresh_height_y": list(FOLLOWUP_Y), "width_x": list(FOLLOWUP_X),
                     "origin_control_y": list(ORIGIN_Y), "height_positions": 510, "origin_positions": 36,
                     "exact_normalization_y": EXACT_NORMALIZATION_Y, "exact_normalization_grid_positions": 4,
                     "additional_control_status": "Added before first follow-up native execution; no new native result used."},
        "entries": entries, "references": REFERENCES,
    }
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
                      "model_status": MODEL_STATUS, "native_acceptance": "NOT_RUN"}))


if __name__ == "__main__":
    main()
