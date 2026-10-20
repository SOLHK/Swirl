"""Independent controls for narrow native observations, never acceptance rules."""
from copy import deepcopy
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
from probe_axis_counterexamples import (TAGS, TYPE_CASES, counterexample_cases,
                                       direct_checks, new_stats)


def original_like_ranges():
    return {face: {"WDTH": (1., 500., 1000.), "wght": (100., 500., 900.),
                   "HGHT": (1., 500., 1000.)} for face in range(32)}


class CounterexampleProbeTests(unittest.TestCase):
    def test_all_type_cases_and_fresh_holdouts_remain_distinct(self):
        ranges = original_like_ranges()
        before = deepcopy(ranges)
        cases = counterexample_cases(ranges)
        self.assertEqual(counterexample_cases(ranges), cases)
        self.assertEqual(ranges, before)
        keys = {(face, *(row["location"][tag] for tag in TAGS))
                for face, rows in cases.items() for row in rows}
        self.assertEqual(len(keys), sum(map(len, cases.values())))
        self.assertTrue(set(TYPE_CASES) <= keys)
        holdouts = [row for rows in cases.values() for row in rows if "fresh_holdouts" in row["cohorts"]]
        self.assertEqual(len(holdouts), 40)
        self.assertTrue(all(440 < row["location"]["wght"] < 495 for row in holdouts))
        for face, rows in cases.items():
            defaults = next(row for row in rows if "defaults" in row["cohorts"])
            self.assertEqual(defaults["location"], {tag: ranges[face][tag][1] for tag in TAGS})

    def test_narrow_samples_bracket_normalized16_steps_without_outcome_selection(self):
        cases = counterexample_cases(original_like_ranges())
        for face in (20, 24, 31):
            weights = {row["location"]["wght"] for row in cases[face] if "narrow_thresholds" in row["cohorts"]}
            for center in (300., 400.):
                for step in (-6, -3, -1, 1, 3, 6):
                    target = center + step * 400 / 65536
                    index = math.floor(target * 10000)
                    self.assertIn(index / 10000, weights)
                    self.assertIn((index + 1) / 10000, weights)
                    self.assertLess(index / 10000, target)
                    self.assertGreater((index + 1) / 10000, target)
            self.assertTrue(all(any(abs(w - center) <= .040001 for center in (300., 400.)) for w in weights))

    def test_invalid_source_ranges_are_rejected_instead_of_clipping_cases(self):
        for change in (lambda r: r.pop(31), lambda r: r[0].pop("HGHT"),
                       lambda r: r[0].__setitem__("wght", (100., 500., math.nan)),
                       lambda r: r[0].__setitem__("wght", (100., 500., 600.))):
            ranges = original_like_ranges()
            change(ranges)
            with self.assertRaises(ValueError):
                counterexample_cases(ranges)

    def test_three_way_diagnosis_keeps_strict_type_failures(self):
        design = dict.fromkeys(TAGS, 0.)
        rows = [{"cohorts": ["type_failures"], "location": dict.fromkeys(TAGS, 500.),
                 "global_model_design_coordinates": {"canonical_normalized16_truncate": design},
                 "HVAR_conditioned_design_coordinate": design}]
        events = [["begin_path"], ["move", 0., 0.], ["quad", 1.01e-10, 0., 0., 0.], ["close"], ["end_path"]]
        commands = [["moveTo", 0., 0.], ["qCurveTo", 1.01e-10, 0., 0., 0.], ["closePath"]]
        observations = [{gid: {"commands": commands} for gid in (5, 19177)}]
        renderer = SimpleNamespace(table=SimpleNamespace(part=lambda gid: SimpleNamespace(axis_count=3)),
            render=lambda *args: SimpleNamespace(paths=[np.array([[[0., 0.], [9.9e-11, 0.]]])]))
        report = {"direct_strict": {name: new_stats() for name in
            ("native_HVF_vs_CoreText", "portable_vs_native_HVF", "portable_vs_CoreText")}}
        with patch("probe_axis_counterexamples.hvf_events", return_value=events):
            direct_checks(Path("native"), Path("source"), 0, rows, observations, renderer, report)
        self.assertEqual(report["direct_strict"]["native_HVF_vs_CoreText"]["failures"], 0)
        self.assertEqual(report["direct_strict"]["portable_vs_native_HVF"]["failures"], 2)
        self.assertEqual(report["direct_strict"]["portable_vs_CoreText"]["failure_types"], {"segment_types_differ": 2})
        detail = rows[0]["direct_native_checks"][1]["raw_segment_diagnosis_not_acceptance"]["portable_vs_native_HVF"]
        self.assertLess(detail["maximum_parametric_difference_upper_bound"], 2e-12)
        self.assertEqual(detail["unchanged_strict_comparison"]["status"], "rejected")
        self.assertFalse(detail["mapping_accepted"])
        encoded = json.dumps(rows, allow_nan=False)
        self.assertNotIn('"commands"', encoded)
        self.assertNotIn('"events"', encoded)
        self.assertNotIn('"points"', encoded)


if __name__ == "__main__":
    unittest.main()
