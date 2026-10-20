"""Original analytic regressions for integer gvar residual quantization.

The rectangle and continuous tent function below are authored for these tests.
No native process, Apple font, source outline or cached reference is used.
"""
import copy
import itertools
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.recordingPen import RecordingPointPen
from fontTools.ttLib import TTFont, newTable
from fontTools.varLib.models import VariationModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import rebuild
from metric_variations import add_metric_variations


AXES = {"WDTH": (1, 500, 1000), "wght": (100, 400, 900), "HGHT": (1, 500, 1000)}
RECTANGLE = ((-63, 32), (-9, 32), (-9, 95), (-63, 95))


def tent(value):
    return max(0.0, 1.0 - abs(2.0 * value - 1.0))


def native_record(location, origin_offset=0.0):
    x, weight = location.get("WDTH", 0.0), location.get("wght", 0.0)
    displacement = x - 0.99 * tent(x) * tent(weight)
    points = [(a + displacement + origin_offset, b + displacement + origin_offset)
              for a, b in RECTANGLE]
    return {
        "commands": [["moveTo", *points[0]],
                     *[["lineTo", *point] for point in points[1:]], ["closePath"]],
        "advance_width": 600.0, "advance_height": 1000.0,
        "lsb": points[0][0], "horizontal_origin_x": 0.0,
        "vertical_origin_x": 300.0, "vertical_origin_y": 880.0, "error": None,
    }


def samples(origin_offset=0.0):
    training = [dict(zip(AXES, values))
                for values in itertools.product((-1.0, 0.0, 1.0), repeat=3)]
    training.append({"WDTH": 0.5, "wght": 0.5, "HGHT": 0.0})
    holdouts = [dict(zip(AXES, values)) for values in (
        (0.25, 0.25, -0.75), (0.375, 0.625, 0.125),
        (0.75, 0.75, 0.625), (0.125, 0.875, -0.375),
        (-0.375, 0.125, 0.875), (0.9375, 0.0625, -0.125),
    )]
    return ([native_record(p, origin_offset) for p in training],
            [native_record(p, origin_offset) for p in holdouts], training, holdouts)


def reconstruct(data):
    training, heldout, locations, checks = data
    return rebuild.reconstruct_glyph(training, heldout, locations, checks,
                                     AXES, (600, -63), (1000, 785))


def font_from_reconstruction(result):
    glyph, variations, horizontal, vertical, _ = result
    builder = FontBuilder(1000, isTTF=True)
    name = ".notdef"
    builder.setupGlyphOrder([name])
    builder.setupCharacterMap({})
    builder.setupGlyf({name: copy.deepcopy(glyph)})
    builder.setupHorizontalMetrics({name: horizontal})
    builder.setupHorizontalHeader(ascent=880, descent=-120)
    builder.setupVerticalMetrics({name: vertical})
    builder.setupVerticalHeader(ascent=500, descent=-500)
    builder.setupNameTable({"familyName": "Swirl Residual Arithmetic Fixture",
                            "styleName": "Regular", "uniqueFontIdentifier": "SwirlResidualArithmetic",
                            "fullName": "Swirl Residual Arithmetic Fixture Regular",
                            "psName": "SwirlResidualArithmetic-Regular"})
    builder.setupOS2(sTypoAscender=880, sTypoDescender=-120,
                    usWinAscent=880, usWinDescent=120)
    builder.setupPost()
    builder.setupMaxp()
    builder.setupFvar([(tag, *bounds, tag) for tag, bounds in AXES.items()], [])
    builder.font["gvar"] = newTable("gvar")
    builder.font["gvar"].version = 1
    builder.font["gvar"].reserved = 0
    builder.font["gvar"].variations = {name: copy.deepcopy(variations)}
    add_metric_variations(builder.font)
    builder.font.recalcTimestamp = False
    return builder.font


class GvarResidualQuantizationTests(unittest.TestCase):
    def test_one_residual_quantization_preserves_an_expressible_adaptive_peak(self):
        data = samples()
        training, _, locations, _ = data
        # Reproduce the old double rounding independently on the rectangle's
        # points. It is a baseline witness, never the expected source geometry.
        points = [np.asarray([command[1:] for command in row["commands"][:-1]], float)
                  for row in training]
        model = VariationModel(locations, axisOrder=list(AXES))
        old_deltas = model.getDeltas([np.floor(p + 0.5) for p in points],
                                    round=lambda value: np.floor(value + 0.5))
        old_errors = [float(np.max(np.linalg.norm(
            model.interpolateFromDeltas(location, old_deltas) - point, axis=1)))
            for location, point in zip(locations, points)]
        self.assertAlmostEqual(max(old_errors), math.sqrt(2.0) * 0.99, places=10)

        glyph, tuples, _, _, evidence = reconstruct(data)
        self.assertEqual(evidence["failures"], [])
        self.assertAlmostEqual(evidence["max_outline_error_bound_units"],
                               math.sqrt(2.0) * 0.01, places=10)
        self.assertEqual(evidence["max_metric_error_units"], 0.0)
        self.assertFalse(evidence["continuous_space_proof"])
        self.assertTrue(all(value == int(value) for p in glyph.coordinates for value in p))
        self.assertTrue(all(value == int(value)
                            for variation in tuples for p in variation.coordinates for value in p))

    def test_negative_default_half_coordinates_keep_opentype_rounding(self):
        result = reconstruct(samples(origin_offset=-0.5))
        glyph, _, _, _, evidence = result
        # -63.5 rounds to -63, not -64; 31.5 rounds to 32.
        self.assertEqual(list(glyph.coordinates), list(RECTANGLE))
        self.assertEqual(evidence["failures"], [])
        self.assertAlmostEqual(evidence["default_quantization_error"]["max_point_error_units"],
                               math.sqrt(0.5), places=12)
        self.assertLessEqual(evidence["max_outline_error_bound_units"], 1.0)

    def test_native_records_and_unrounded_reference_vectors_remain_unchanged(self):
        data = samples()
        original_records = copy.deepcopy(data[:2])
        captured = []
        append_phantoms = rebuild.with_phantoms

        def remember_reference(*args, **kwargs):
            result = append_phantoms(*args, **kwargs)
            captured.append((result, result.copy()))
            return result

        with mock.patch.object(rebuild, "with_phantoms", side_effect=remember_reference):
            result = reconstruct(data)
        self.assertEqual(data[:2], original_records)
        self.assertEqual(result[-1]["failures"], [])
        self.assertEqual(len(captured), len(data[0]) + len(data[1]))
        for actual, expected in captured:
            np.testing.assert_array_equal(actual, expected)

    def test_serialized_font_retains_the_same_analytic_error(self):
        data = samples()
        result = reconstruct(data)
        font = font_from_reconstruction(result)
        try:
            with tempfile.TemporaryDirectory(prefix="original-gvar-residual-") as tmp:
                path = Path(tmp) / "original-residual-fixture.ttf"
                font.save(path)
                with TTFont(path, recalcTimestamp=False) as reopened:
                    verified = rebuild.verify_serialized_face(font, reopened)
                    self.assertEqual(verified["status"], "PASS")
                    errors = []
                    # Use the independent fontTools glyph-set rendering path,
                    # after serialization, at every master and unseen holdout.
                    for location in data[2] + data[3]:
                        user = {tag: default + location.get(tag, 0.0)
                                * ((default-low) if location.get(tag, 0.0) < 0 else (high-default))
                                for tag, (low, default, high) in AXES.items()}
                        pen = RecordingPointPen()
                        reopened.getGlyphSet(location=user)[".notdef"].drawPoints(pen)
                        observed = [entry[1][0] for entry in pen.value if entry[0] == "addPoint"]
                        reference = [command[1:] for command in native_record(location)["commands"][:-1]]
                        self.assertEqual(len(observed), len(reference))
                        errors.append(max(math.dist(a, b) for a, b in zip(observed, reference)))
                    self.assertAlmostEqual(max(errors), math.sqrt(2.0) * 0.01, places=10)
                    self.assertEqual(reopened["hmtx"].metrics[".notdef"][0], 600)
                    self.assertEqual(reopened["vmtx"].metrics[".notdef"][0], 1000)
        finally:
            font.close()


if __name__ == "__main__":
    unittest.main()
