"""Reconstruction tests with independent, original analytic geometry."""
import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import TTFont, TTCollection, newTable
from fontTools.varLib.instancer import instantiateVariableFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from rebuild import (ReconstructionError, compatible_coordinates, normalized_grid,
                     heldout_locations, reconstruct_glyph, user_location, run,
                     verify_serialized_face, verify_collection_tables)

AXES = {"WDTH": (1, 500, 1000), "wght": (100, 500, 900), "HGHT": (1, 500, 1000)}


def analytic_record(location, *, nonlinear=False):
    x, w, y = (location.get(tag, 0) for tag in AXES)
    width = 400 + 80*x + 20*w + 12*x*y + (30*x*x if nonlinear else 0)
    height = 500 + 60*y + 10*w
    left = 20 + 5*w
    bottom = -20
    commands = [["moveTo",left,bottom], ["lineTo",left+width,bottom],
                ["lineTo",left+width,bottom+height], ["lineTo",left,bottom+height], ["closePath"]]
    advance = width + 100
    return {"commands": commands, "advance_width": advance, "advance_height": 1000,
            "lsb":left, "horizontal_origin_x":0, "vertical_origin_x":advance/2,
            "vertical_origin_y":880, "error":None}


def reconstructed(nonlinear=False):
    training = normalized_grid(list(AXES))
    checks = heldout_locations(list(AXES))
    records = [analytic_record(p, nonlinear=nonlinear) for p in training]
    heldout = [analytic_record(p, nonlinear=nonlinear) for p in checks]
    return reconstruct_glyph(records, heldout, training, checks, AXES, (500,20), (1000,400)), training, checks


def write_fixture(path, faces=1):
    (glyph, variations, hm, vm, evidence), _, _ = reconstructed()
    if evidence["failures"]:
        raise RuntimeError("analytic fixture unexpectedly failed")
    collection = TTCollection()
    for face in range(faces):
        builder = FontBuilder(1000, isTTF=True)
        names = [".notdef", "A", "uni4E2D"]
        builder.setupGlyphOrder(names)
        builder.setupCharacterMap({65:"A", 0x4E2D:"uni4E2D"})
        builder.setupGlyf({name:copy.deepcopy(glyph) for name in names})
        builder.setupHorizontalMetrics({name:hm for name in names})
        builder.setupHorizontalHeader(ascent=880, descent=-120)
        builder.setupVerticalMetrics({name:vm for name in names})
        builder.setupVerticalHeader(ascent=500, descent=-500)
        family = f"Swirl Synthetic Three Axis {face}"
        builder.setupNameTable({"familyName":family, "styleName":"Regular", "uniqueFontIdentifier":family,
                                "fullName":family, "psName":family.replace(' ','')})
        builder.setupOS2(sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120,
                         usWeightClass=500)
        builder.setupPost()
        builder.setupMaxp()
        builder.setupFvar([(tag,*bounds,tag) for tag,bounds in AXES.items()], [])
        from fontTools.otlLib.builder import buildStatTable
        buildStatTable(builder.font, [{"tag":"WDTH", "name":"Width", "values":[{"value":500,"name":"Normal","flags":2}]},
                                      {"tag":"wght", "name":"Weight", "values":[{"value":500,"name":"Medium","flags":2}]},
                                      {"tag":"HGHT", "name":"Height", "values":[{"value":500,"name":"Normal","flags":2}]}])
        builder.font["gvar"] = newTable("gvar")
        builder.font["gvar"].version = 1
        builder.font["gvar"].reserved = 0
        builder.font["gvar"].variations = {name:copy.deepcopy(variations) for name in names}
        builder.font.recalcTimestamp=False
        builder.font['head'].created = builder.font['head'].modified = 3800000000
        collection.fonts.append(builder.font)
    collection.save(path)


class RebuildTests(unittest.TestCase):
    def test_all_three_axis_corners_and_independent_holdouts(self):
        grid = normalized_grid(list(AXES))
        self.assertEqual(len(grid), 27)
        checks = heldout_locations(list(AXES))
        self.assertTrue(all(p not in grid for p in checks))
        self.assertEqual(grid[0], {tag:0 for tag in AXES})

    def test_original_user_coordinate_ranges_and_fractional_weights(self):
        location = user_location({"WDTH":-1, "wght":.00125, "HGHT":1}, AXES)
        self.assertEqual(location, {"WDTH":1, "wght":500.5, "HGHT":1000})

    def test_mixed_axis_term_preserved(self):
        (glyph, variations, hm, vm, evidence), _, _ = reconstructed()
        self.assertEqual(evidence["failures"], [])
        self.assertLess(evidence["max_point_error_units"], 1e-10)
        self.assertTrue(any(len(v.axes) > 1 for v in variations))
        self.assertEqual(hm, (500,20))
        self.assertEqual(vm, (1000,400))

    def test_unsampled_nonlinear_error_is_detected(self):
        (_, _, _, _, evidence), _, _ = reconstructed(nonlinear=True)
        self.assertTrue(evidence["failures"])
        self.assertGreater(evidence["max_point_error_units"], 7)

    def test_default_vertical_metrics_use_the_same_rounded_phantoms(self):
        record = analytic_record({})
        record.update(vertical_origin_y=880.6, advance_height=1000.2)
        glyph, _, _, vm, evidence = reconstruct_glyph(
            [record], [], [{tag: 0 for tag in AXES}], [], AXES, (500, 20), (1000, 400))
        # Independent rounding yields top=881 and bottom=-120. Rounding the
        # unrounded advance instead would store 1000 and move the bottom to -119.
        self.assertEqual(vm[0], 1001)
        self.assertEqual((glyph.yMax + vm[1], glyph.yMax + vm[1] - vm[0]), (881, -120))
        self.assertAlmostEqual(evidence["default_quantization_error"]["max_metric_error_units"], .8)

    def test_training_default_quantization_is_checked_without_holdouts(self):
        record = analytic_record({})
        for command in record["commands"]:
            for index in range(1, len(command)):
                command[index] += .49
        _, _, _, _, evidence = reconstruct_glyph(
            [record], [], [{tag: 0 for tag in AXES}], [], AXES,
            (500, 20), (1000, 400), outline_limit=.1)
        self.assertEqual(evidence["holdout_count"], 0)
        self.assertEqual(evidence["training_count"], 1)
        self.assertEqual(evidence["failures"][0]["sample_kind"], "training")
        self.assertGreater(evidence["default_quantization_error"]["max_point_error_units"], .69)

    def test_cubic_approximation_budget_is_charged_to_total_outline_bound(self):
        record = analytic_record({})
        record["commands"] = [["moveTo", 0, 0], ["curveTo", 100, 0, 200, 0, 300, 0],
                              ["lineTo", 300, 300], ["closePath"]]
        _, _, _, _, evidence = reconstruct_glyph(
            [record], [], [{tag: 0 for tag in AXES}], [], AXES,
            (500, 20), (1000, 400), outline_limit=.1, cubic_error=.2)
        self.assertEqual(evidence["max_point_error_units"], 0)
        self.assertEqual(evidence["max_outline_error_bound_units"], .2)
        self.assertTrue(evidence["failures"])

    def test_topology_change_is_not_hidden(self):
        a = analytic_record({}); b = copy.deepcopy(a)
        b["commands"][1] = ["qCurveTo",1,2,3,4]
        with self.assertRaises(ReconstructionError):
            compatible_coordinates([a,b])

    def test_joint_cubic_conversion_keeps_topology(self):
        a = analytic_record({}); b = copy.deepcopy(a)
        a["commands"][1] = ["curveTo",100,0,200,200,420,-20]
        b["commands"][1] = ["curveTo",105,0,201,210,430,-20]
        coords, flags, ends, cubics = compatible_coordinates([a,b])
        self.assertEqual(len(coords[0]), len(coords[1]))
        self.assertEqual(cubics,1)
        self.assertEqual(ends, [len(flags)-1])

    def test_vertical_origin_not_assumed(self):
        train = normalized_grid(list(AXES)); held=heldout_locations(list(AXES))
        records=[analytic_record(p) for p in train]
        records[0]["vertical_origin_x"] += 7
        with self.assertRaises(ReconstructionError):
            reconstruct_glyph(records,[analytic_record(p) for p in held],train,held,AXES,(500,20),(1000,400))

    def test_missing_native_metric_does_not_default_to_zero(self):
        train=normalized_grid(list(AXES)); held=heldout_locations(list(AXES))
        records=[analytic_record(p) for p in train]
        del records[0]["vertical_origin_y"]
        with self.assertRaises(ReconstructionError):
            reconstruct_glyph(records,[analytic_record(p) for p in held],train,held,AXES,(500,20),(1000,400))

    def test_serialize_and_instantiate_three_face_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"synthetic.ttc"
            write_fixture(p, faces=3)
            fonts=TTCollection(p).fonts
            self.assertEqual(len(fonts),3)
            loc={"WDTH":750,"wght":700,"HGHT":250.5}
            normalized={"WDTH":.5,"wght":.5,"HGHT":-.5}
            expected=analytic_record(normalized)
            for font in fonts:
                self.assertEqual([a.axisTag for a in font['fvar'].axes],list(AXES))
                static=instantiateVariableFont(font,loc,inplace=False)
                coordinates=np.asarray(static['glyf']['A'].coordinates)
                wanted=np.asarray([cmd[1:] for cmd in expected['commands'] if cmd[0]!='closePath'])
                np.testing.assert_allclose(coordinates,wanted,atol=.51)
                self.assertAlmostEqual(static['hmtx'].metrics['A'][0],expected['advance_width'],delta=.51)
                self.assertEqual(static['vmtx'].metrics['A'][0],1000)

    def test_serialized_coefficients_and_metric_phantoms_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.ttc"
            write_fixture(source)
            with TTFont(source, fontNumber=0) as reference:
                candidate = Path(tmp) / "face.ttf"
                reference.save(candidate)
                with TTFont(candidate) as actual:
                    result = verify_serialized_face(reference, actual)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["glyphs_checked"], 3)
            self.assertGreater(result["gvar_tuples_checked"], 0)

    def test_deliberately_mutated_serialized_gvar_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.ttc"
            write_fixture(source)
            changed = Path(tmp) / "changed.ttf"
            with TTFont(source, fontNumber=0) as mutant:
                variation = mutant["gvar"].variations["A"][0]
                x, y = variation.coordinates[0]
                variation.coordinates[0] = (x + 1, y)
                mutant.save(changed)
            with TTFont(source, fontNumber=0) as reference, TTFont(changed) as actual:
                with self.assertRaisesRegex(ReconstructionError, "gvar outline/phantom delta changed"):
                    verify_serialized_face(reference, actual)

    def test_deliberately_mutated_serialized_vertical_metric_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.ttc"
            write_fixture(source)
            changed = Path(tmp) / "changed.ttf"
            with TTFont(source, fontNumber=0) as mutant:
                advance, bearing = mutant["vmtx"].metrics["A"]
                mutant["vmtx"].metrics["A"] = (advance + 1, bearing)
                mutant.save(changed)
            with TTFont(source, fontNumber=0) as reference, TTFont(changed) as actual:
                with self.assertRaisesRegex(ReconstructionError, "default outline or metric phantom changed"):
                    verify_serialized_face(reference, actual)

    def test_ttc_shared_table_packing_and_deliberate_face_swap(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "source.ttc"
            write_fixture(source, faces=2)
            collection = TTCollection(source)
            paths = [folder / f"face-{i}.ttf" for i in range(2)]
            for face, path in zip(collection.fonts, paths):
                face.save(path)
            candidate = folder / "candidate.ttc"
            collection.save(candidate, shareTables=True)
            actual = TTCollection(candidate, lazy=True)
            self.assertEqual(verify_collection_tables(paths, actual)["status"], "PASS")
            actual.close()
            collection.fonts.reverse()
            collection.save(candidate, shareTables=True)
            actual = TTCollection(candidate, lazy=True)
            with self.assertRaisesRegex(ReconstructionError, "TTC face 0: name bytes changed"):
                verify_collection_tables(paths, actual)
            actual.close()
            collection.close()

    def test_missing_oracle_creates_no_final_font_and_keeps_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'source.ttc'; output=root/'Swirl-VF.ttc'; report=root/'report.json'
            write_fixture(source)
            before=source.read_bytes()
            with self.assertRaises(OSError):
                run(source,root/'missing-oracle',output,report)
            self.assertEqual(source.read_bytes(),before)
            self.assertFalse(output.exists())
            self.assertEqual(json.loads(report.read_text())['status'],'BLOCKED')


if __name__ == '__main__':
    unittest.main()
