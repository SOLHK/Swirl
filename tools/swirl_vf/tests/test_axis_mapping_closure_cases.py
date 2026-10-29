"""Authored font-like controls for archive-preserving closure observations."""
from copy import deepcopy
import itertools
import math
from pathlib import Path
import random
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "platform"))
import axis_mapping_closure_cases as closure
from calibrate_avar_metrics import requests_for


TAGS = ("WDTH", "wght", "HGHT")
RANGES = {"WDTH": (200., 500., 900.), "wght": (100., 499., 900.),
          "HGHT": (100., 500., 1000.)}


class AuthoredFont(dict):
    def __init__(self, ranges=RANGES, order=TAGS):
        axes = [SimpleNamespace(axisTag=tag, minValue=ranges[tag][0],
                                defaultValue=ranges[tag][1], maxValue=ranges[tag][2])
                for tag in order]
        super().__init__(fvar=SimpleNamespace(axes=axes))
        # Original synthetic raw records: duplicate inputs are intentional.
        # Nothing here is copied from the source font or a native observation.
        maps = {tag: [(-16384, -16384), (0, 0), (4096, 8192),
                      (4096, 4096), (16384, 16384)] for tag in order}
        raw = struct.pack(">4H", 1, 0, 0, len(order))
        for tag in order:
            raw += struct.pack(">H", len(maps[tag]))
            raw += b"".join(struct.pack(">hh", *pair) for pair in maps[tag])
        self.reader = {"avar": raw}


def fonts(ranges=RANGES):
    return [AuthoredFont(ranges) for _ in range(32)]


def by_label(rows):
    return {label: row for row in rows for label in row["labels"]}


def minimal_archive(source):
    return [{"request_id": str(face), "face_index": face,
             "location": {a.axisTag: a.defaultValue for a in font["fvar"].axes},
             "glyph_ids": [5, 12, 56, 169]} for face, font in enumerate(source)]


class AxisMappingClosureCaseTests(unittest.TestCase):
    def test_calls_original_request_generator_once_and_retains_every_archived_row(self):
        source = fonts()
        before = deepcopy(source)
        expected = requests_for(source)
        with patch.object(closure, "requests_for", wraps=requests_for) as generator:
            cases = closure.closure_cases(source)
        generator.assert_called_once_with(source)
        self.assertEqual(tuple(cases), tuple(range(32)))
        self.assertEqual(source, before)
        self.assertEqual([f.reader for f in source], [f.reader for f in before])
        reconstructed = []
        for face, rows in cases.items():
            archived = [row for row in rows if "archive_global_request_id" in row]
            wanted = [q for q in expected if q["face_index"] == face]
            self.assertEqual(rows[:len(wanted)], archived)
            self.assertEqual(len(archived), len(wanted))
            for index, (actual, original) in enumerate(zip(archived, wanted)):
                self.assertEqual(actual["archive_id"], original["request_id"])
                self.assertEqual(actual["archive_global_request_id"], original["request_id"])
                self.assertEqual(actual["archive_position_index"], index)
                self.assertEqual(actual["location"], original["location"])
                self.assertEqual(tuple(actual["location"]), tuple(original["location"]))
                self.assertIsNot(actual["location"], original["location"])
                self.assertEqual(actual["label"], "archive_" + original["request_id"])
                reconstructed.append((actual["archive_global_request_id"], face, actual["location"]))
            for row in rows:
                self.assertEqual(row["label"], row["labels"][0])
                self.assertEqual(row["cohort"], row["cohorts"][0])
                self.assertEqual(len(row["labels"]), len(set(row["labels"])))
                self.assertEqual(len(row["cohorts"]), len(set(row["cohorts"])))
                self.assertNotIn("glyph_ids", row)
        self.assertEqual(reconstructed, [(q["request_id"], q["face_index"], q["location"]) for q in expected])

    def test_archived_duplicates_survive_and_new_aliases_attach_to_first_occurrence(self):
        # Width's default equals its minimum, so the unchanged archive itself
        # emits repeated coordinates. Those are separate original observations.
        source = fonts({**RANGES, "WDTH": (200., 200., 900.)})
        original = requests_for(source)
        cases = closure.closure_cases(source)
        for face, rows in cases.items():
            archive = [row for row in rows if "archive_id" in row]
            wanted = [q for q in original if q["face_index"] == face]
            self.assertEqual(len(archive), len(wanted))
            points = [tuple(row["location"][tag] for tag in TAGS) for row in archive]
            self.assertLess(len(set(points)), len(points))
            defaults = {a.axisTag: a.defaultValue for a in source[face]["fvar"].axes}
            matches = [row for row in archive if row["location"] == defaults]
            self.assertEqual(len(matches), 2)
            self.assertIn("default", matches[0]["labels"])
            self.assertNotIn("default", matches[1]["labels"])
            self.assertIn("baseline", matches[0]["cohorts"])
            self.assertIn("corners", matches[0]["cohorts"])
            self.assertNotEqual(matches[0]["archive_id"], matches[1]["archive_id"])
            new = rows[len(archive):]
            new_points = [tuple(row["location"][tag] for tag in TAGS) for row in new]
            self.assertEqual(len(new_points), len(set(new_points)))
            self.assertFalse(set(new_points) & set(points))

    def test_fresh_eight_triples_use_the_declared_new_seed_for_every_face(self):
        source = fonts()
        cases = closure.closure_cases(source)
        self.assertEqual(cases, closure.closure_cases(source))
        archive = requests_for(source)
        seen = set()
        for face, rows in cases.items():
            labels = by_label(rows)
            fresh = [labels[f"fresh_triple_{i}"] for i in range(8)]
            self.assertEqual(len({id(row) for row in fresh}), 8)
            rng = random.Random(20961020 + face)
            expected = [{tag: rng.uniform(RANGES[tag][0], RANGES[tag][2]) for tag in TAGS}
                        for _ in range(8)]
            old_rng = random.Random(20861020 + face)
            old = {tuple(old_rng.uniform(RANGES[tag][0], RANGES[tag][2]) for tag in TAGS)
                   for _ in range(6)}
            old.update(tuple(q["location"][tag] for tag in TAGS) for q in archive if q["face_index"] == face)
            for row, wanted in zip(fresh, expected):
                self.assertEqual(row["location"], wanted)
                self.assertIn("fresh_random_triples", row["cohorts"])
                self.assertNotIn("archive_id", row)
                point = tuple(row["location"][tag] for tag in TAGS)
                self.assertNotIn(point, old)
                self.assertNotIn(point, seen)
                seen.add(point)
                self.assertTrue(all(row["location"][tag] != RANGES[tag][1] for tag in TAGS))
        self.assertEqual(len(seen), 256)

    def test_all_faces_have_defaults_corners_and_both_direct_hvf_weight_controls(self):
        cases = closure.closure_cases(fonts())
        for rows in cases.values():
            labels = by_label(rows)
            self.assertEqual(labels["default"]["location"], {tag: RANGES[tag][1] for tag in TAGS})
            corners = [row["location"] for label, row in labels.items() if label.startswith("corner_")]
            self.assertEqual(len(corners), 27)
            self.assertEqual({tuple(p[tag] for tag in TAGS) for p in corners},
                             set(itertools.product(*(RANGES[tag] for tag in TAGS))))
            for label, weight in (("weight_300_control_299.9817", 299.9817),
                                  ("weight_400_boundary_400.01", 400.01)):
                self.assertEqual(labels[label]["location"], {"WDTH": 500., "wght": weight, "HGHT": 500.})
            mixed = [row["location"] for label, row in labels.items() if label.startswith("mixed_axes_")]
            self.assertEqual({p["wght"] for p in mixed},
                             {299.9817, 300.01, 399.96, 400.01, 400.04, 400.041, 500.01})
            self.assertTrue(all(p["WDTH"] == 600.5859375 and p["HGHT"] == 250. for p in mixed))
            self.assertEqual(labels["historical_wdth_readback"]["location"],
                {"WDTH": 600.5859375, "wght": 368.22259521484375, "HGHT": 975.7080078125})

    def test_every_original_range_and_axis_order_are_used_without_archive_reordering(self):
        source = fonts()
        special = {"WDTH": (150., 525., 850.), "wght": (120., 475., 880.), "HGHT": (50., 575., 950.)}
        source[17] = AuthoredFont(special, ("HGHT", "wght", "WDTH"))
        rows = closure.closure_cases(source)[17]
        labels = by_label(rows)
        self.assertEqual(tuple(rows[0]["location"]), ("HGHT", "wght", "WDTH"))
        for tag, (low, default, high) in special.items():
            for delta in (.0001, .01, .06):
                for side, direction in (("below", -1), ("above", 1)):
                    point = labels[f"{tag}_default_{side}_{delta:g}"]["location"]
                    self.assertEqual(point[tag], default + direction * delta)
                    self.assertTrue(all(point[other] == special[other][1] for other in TAGS if other != tag))
            for side, delta in (("below", -.0001), ("exact", 0.), ("above", .0001)):
                self.assertEqual(labels[f"{tag}_midpoint_{side}"]["location"][tag], (low + high) / 2 + delta)
        rng = random.Random(20961020 + 17)
        self.assertEqual(labels["fresh_triple_0"]["location"],
                         {tag: rng.uniform(special[tag][0], special[tag][2]) for tag in TAGS})

    def test_out_of_range_supplemental_points_are_omitted_never_clamped(self):
        narrow = {"WDTH": (10., 10., 10.01), "wght": (20., 20.005, 20.01),
                  "HGHT": (30., 30.01, 30.01)}
        cases = closure.closure_cases(fonts(narrow))
        for rows in cases.values():
            labels = by_label(rows)
            self.assertNotIn("WDTH_default_below_0.0001", labels)
            self.assertNotIn("HGHT_default_above_0.0001", labels)
            self.assertNotIn("wght_default_above_0.06", labels)
            self.assertFalse(any(c in row["cohorts"] for row in rows
                                 for c in ("300_controls", "400_boundaries", "mixed_axes")))
            for row in rows:
                self.assertTrue(all(narrow[tag][0] <= value <= narrow[tag][2]
                                    for tag, value in row["location"].items()))

    def test_invalid_face_sets_axis_tags_and_ranges_fail_before_archive_generation(self):
        bad_sources = [None, [], fonts()[:31], fonts() + [AuthoredFont()], {i: AuthoredFont() for i in range(32)}]
        for altered_axes in ([], [SimpleNamespace(axisTag="wght")],
                fonts()[0]["fvar"].axes + [SimpleNamespace(axisTag="wght")]):
            source = fonts(); source[31]["fvar"].axes = altered_axes
            bad_sources.append(source)
        source = fonts(); source[4]["fvar"].axes[0].axisTag = "wdth"; bad_sources.append(source)
        source = fonts(); del source[8]["fvar"]; bad_sources.append(source)
        for bad in ((0, 0, 0), (2, 1, 0), (0, 3, 2), (0, math.nan, 2),
                    (0, 1, math.inf), (0, True, 2), (0, "1", 2), (0, 1, 10**400),
                    (-1e308, 0, 1e308)):
            source = fonts(); source[1]["fvar"].axes[1] = SimpleNamespace(
                axisTag="wght", minValue=bad[0], defaultValue=bad[1], maxValue=bad[2])
            bad_sources.append(source)
        source = fonts(); del source[0]["fvar"].axes[2].maxValue; bad_sources.append(source)
        with patch.object(closure, "requests_for", side_effect=AssertionError("invalid input reached archive")):
            for index, source in enumerate(bad_sources):
                with self.subTest(index=index), self.assertRaises(ValueError):
                    closure.closure_cases(source)

    def test_malformed_archive_identity_order_locations_and_missing_faces_fail_closed(self):
        source = fonts()
        original = minimal_archive(source)
        invalid = [[], tuple(original), original[:-1]]
        for field, value in (("request_id", 0), ("request_id", "wrong"),
                             ("face_index", False), ("face_index", 32),
                             ("glyph_ids", [5, 12, 56]), ("location", {"wght": 499.})):
            rows = deepcopy(original); rows[0][field] = value; invalid.append(rows)
        for value in (math.nan, math.inf, True, 10**400, 99., "499"):
            rows = deepcopy(original); rows[0]["location"]["wght"] = value; invalid.append(rows)
        rows = deepcopy(original); rows[0]["private_payload"] = [12345, 67890]; invalid.append(rows)
        rows = deepcopy(original); rows[2]["face_index"] = 0; invalid.append(rows)
        rows = deepcopy(original); rows[1]["request_id"] = "0"; invalid.append(rows)
        rows = deepcopy(original); rows[0]["location"]["wdth"] = 500.; invalid.append(rows)
        for index, rows in enumerate(invalid):
            with self.subTest(index=index), patch.object(closure, "requests_for", return_value=rows):
                with self.assertRaises(ValueError):
                    closure.closure_cases(source)

    def test_generated_aliases_and_output_mutation_cannot_change_archived_requests(self):
        source = fonts()
        archive = minimal_archive(source)
        before = deepcopy(archive)
        with patch.object(closure, "requests_for", return_value=archive):
            cases = closure.closure_cases(source)
        self.assertEqual(archive, before)
        self.assertIn("default", cases[0][0]["labels"])
        cases[0][0]["location"]["wght"] = -123.
        cases[0][0]["labels"].append("authored_mutation")
        self.assertEqual(archive, before)
        self.assertNotIn("authored_mutation", cases[1][0]["labels"])


if __name__ == "__main__":
    unittest.main()
