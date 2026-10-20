#!/usr/bin/env python3
"""Falsify design-before-readback truncation with a fresh frozen A3 cohort.

No observed readback is an input to a model. The same native protocol still
checks the independently declared T(T(x)) replay and reports every failure.
The safe original/replay comparison now records numeric error magnitudes as
well as complete-payload equality. No production source or guard is changed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from axis_a3_prereadback_cases import (
    ALL_MODELS, NEW_MODELS, MODEL_DESCRIPTIONS, FRESH_SEED,
    prereadback_cases, prereadback_mappings, prereadback_design_inputs,
)
from probe_axis_a3_arithmetic import run


STATUS = "COMPLETED_NATIVE_A3_PREREADBACK_DIAGNOSIS_NOT_ACCEPTANCE"
CONTEXT = {
    "hypothesis": "Design mapping may precede the final truncation visible in user-coordinate readback.",
    "prior_native_source_commit": "eda37d1c733cb1ced283583434e4123824a2147c",
    "prior_native_run_url": "https://github.com/SOLHK/Swirl/actions/runs/39404600942",
    "prior_report_sha256": "64483c46413e2ed0fe33731ef75dd22132a59a0da112bf791c0bff950da86f4d",
    "fixed_readback_and_replay_plan": "Existing declare_readback: T(T(x)); no new acceptance or readback rule.",
    "design_stage_values_frozen_before_native": True,
    "observed_readback_used_to_fit_design": False,
    "original_replay_numeric_differences_measured": True,
    "candidate_is_not_observed_CoreText_internal_state": True,
    "production_mapping_accepted": False,
    "continuous_space_accepted": False,
    "font_accepted": False,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output, case_factory=prereadback_cases,
        mapping_factory=prereadback_mappings, model_names=ALL_MODELS,
        new_model_names=NEW_MODELS, model_descriptions=MODEL_DESCRIPTIONS,
        fresh_seed=FRESH_SEED, status=STATUS, report_context=CONTEXT,
        compare_replay_geometry=True, design_input_factory=prereadback_design_inputs)
