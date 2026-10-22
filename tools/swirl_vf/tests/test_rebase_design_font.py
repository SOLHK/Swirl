"""Authored q-space glyphs: real fontTools model reparameterization checks."""
import copy
import io
from pathlib import Path
import sys
import unittest

from fontTools.ttLib import TTFont, newTable
from fontTools.varLib.instancer import instantiateVariableFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from metric_variations import add_metric_variations
from rebuild_c1_fixture import make_face
from rebase_design_font import CUSTOM_TAGS, rebase_design_font, rebase_design_font_precision8
from target_axis_mapping import SourceAxis


IDENTITY = ((-16384, -16384), (0, 0), (16384, 16384))
HALF = ((-16384, -16384), (-16384, -8192), (0, 0), (16384, 8192), (16384, 16384))


def source_axes():
    return (SourceAxis('WDTH', 1., 500., 1000., IDENTITY),
            SourceAxis('wght', 100., 500., 900., HALF),
            SourceAxis('HGHT', 1., 500., 1000., IDENTITY))


def q_font(weight_delta=20):
    font = make_face(0)
    for axis in font['fvar'].axes:
        axis.axisTag = CUSTOM_TAGS[axis.axisTag]
        axis.minValue, axis.defaultValue, axis.maxValue = -1., 0., 1.
    font['fvar'].instances = []
    del font['STAT']
    font['avar'].segments = {tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in CUSTOM_TAGS.values()}
    for variations in font['gvar'].variations.values():
        for variation in variations:
            if 'wght' in variation.axes and weight_delta != 20:
                variation.coordinates = [(round(x * weight_delta / 20), y) for x, y in variation.coordinates]
            variation.axes = {CUSTOM_TAGS[tag]: region for tag, region in variation.axes.items()}
    # Regenerate both metric stores from the authored, actually changed phantoms.
    del font['HVAR']
    del font['VVAR']
    add_metric_variations(font)
    return font


def serialize(font):
    output = io.BytesIO()
    font.save(output)
    return output.getvalue()


def static_at(font, location):
    return instantiateVariableFont(font, location, inplace=False, optimize=False)


class RebaseDesignFontTests(unittest.TestCase):
    def test_precision8_fixes_serialized_odd_half_coefficients_in_physical_units(self):
        from fontTools.varLib.models import supportScalar
        from fontTools.varLib.varStore import VarStoreInstancer
        original = q_font(weight_delta=1)
        original.recalcTimestamp = False
        before = serialize(original)
        candidate, report = rebase_design_font_precision8(original, source_axes())
        self.assertEqual(serialize(original), before)
        self.assertEqual(candidate['head'].unitsPerEm, original['head'].unitsPerEm * 8)
        for weight in (-.5, -.25, -.125, 0., .125, .25, .5):
            source_location = {'XWDT': .375, 'XWGT': weight, 'XHGT': -.25}
            target_location = {'WDTH': .375, 'wght': weight * 2, 'HGHT': -.25}
            for table, field in (('HVAR', 'AdvWidthMap'), ('VVAR', 'AdvHeightMap')):
                a, b = original[table].table, candidate[table].table
                src = VarStoreInstancer(a.VarStore, original['fvar'].axes, source_location)
                dst = VarStoreInstancer(b.VarStore, candidate['fvar'].axes, target_location)
                for name in original.getGlyphOrder():
                    self.assertEqual(src[getattr(a, field).mapping[name]],
                                     dst[getattr(b, field).mapping[name]] / 8)
            # Compare actual serialized gvar coefficients at independent mixed
            # positions. A static instance would round the source .5 first.
            def deltas(font, location, scale):
                count = len(font['gvar'].variations['A'][0].coordinates)
                total = [[0., 0.] for _ in range(count)]
                for variation in font['gvar'].variations['A']:
                    scalar = supportScalar(location, variation.axes) / scale
                    for point, coordinate in zip(total, variation.coordinates):
                        self.assertIsNotNone(coordinate)
                        for axis in (0, 1): point[axis] += scalar * coordinate[axis]
                return total
            self.assertEqual(deltas(original, source_location, 1),
                             deltas(candidate, target_location, 8))
        self.assertTrue(report['scale_before_restriction'])
        self.assertTrue(report['serialized_candidate_reopened'])
        self.assertFalse(report['application_compensation'])
        self.assertFalse(report['font_conversion_accepted'])
        self.assertEqual(report['physical_error_bound'], 'NOT_ESTABLISHED')

    def test_precision8_HarfBuzz_model_accuracy_and_raw_grid_difference_are_separate(self):
        import uharfbuzz as hb
        from fontTools.varLib.varStore import VarStoreInstancer
        original = q_font(weight_delta=1)
        candidate, _ = rebase_design_font_precision8(original, source_axes())
        retained_metric_failures, maximum_raw_difference = 0, 0.
        for weight in (-.5, -.25, -.125, 0., .125, .25, .5):
            reference = hb.Font(hb.Face(serialize(original)))
            target = hb.Font(hb.Face(serialize(candidate)))
            for font in (reference, target):
                hb.ot_font_set_funcs(font)
                font.scale = (64000, 64000)  # same physical output scale
            reference.set_variations({'XWDT': .375, 'XWGT': weight, 'XHGT': -.25})
            target.set_variations({'WDTH': 687.5, 'wght': 500 + 800*weight, 'HGHT': 375.25})
            hvar = original['HVAR'].table
            model = VarStoreInstancer(hvar.VarStore, original['fvar'].axes,
                        {'XWDT': .375, 'XWGT': weight, 'XHGT': -.25})
            for gid, name in enumerate(original.getGlyphOrder()):
                expected = original['hmtx'].metrics[name][0] + model[hvar.AdvWidthMap.mapping[name]]
                self.assertEqual(target.get_glyph_h_advance(gid), expected * 64)
                difference = abs(target.get_glyph_h_advance(gid) - reference.get_glyph_h_advance(gid)) / 64
                retained_metric_failures += difference > 1/32
                maximum_raw_difference = max(maximum_raw_difference, difference)
        # The same physical output scale exposes native source-grid rounding;
        # improving the data model must not relabel raw API parity as passed.
        self.assertEqual(retained_metric_failures, 42)
        self.assertEqual(maximum_raw_difference, 3/8)

    def test_precision8_three_sixteenths_is_still_not_a_universal_error_bound(self):
        from fontTools.varLib.varStore import VarStoreInstancer
        original = q_font(weight_delta=1)
        three_sixteenths = ((-16384, -16384), (-16384, -3072), (0, 0),
                            (16384, 3072), (16384, 16384))
        axes = tuple(SourceAxis(axis.tag, axis.minimum, axis.default, axis.maximum,
                      three_sixteenths if axis.tag == 'wght' else axis.records) for axis in source_axes())
        candidate, report = rebase_design_font_precision8(original, axes)
        a, b = original['HVAR'].table, candidate['HVAR'].table
        src = VarStoreInstancer(a.VarStore, original['fvar'].axes, {'XWGT': 3/16})
        dst = VarStoreInstancer(b.VarStore, candidate['fvar'].axes, {'wght': 1.})
        expected = src[a.AdvWidthMap.mapping['A']]
        actual = dst[b.AdvWidthMap.mapping['A']] / 8
        self.assertEqual(expected, 3/16)
        self.assertEqual(actual, 1/4)
        self.assertEqual(abs(expected - actual), 1/16)
        self.assertGreater(abs(expected - actual), 1/32)
        self.assertFalse(report['font_only_equivalence_accepted'])
        self.assertFalse(report['lossless_conversion'])

    def test_precision8_all_six_source_UPM_families_remain_legal(self):
        for upem in (1000, 1028, 1064, 1100, 1128, 1144):
            with self.subTest(upem=upem):
                original = q_font(weight_delta=1)
                original['head'].unitsPerEm = upem
                candidate, report = rebase_design_font_precision8(original, source_axes())
                self.assertEqual(candidate['head'].unitsPerEm, upem * 8)
                self.assertEqual(report['source_units_per_em'], upem)
                self.assertEqual(candidate['hmtx'].metrics['A'],
                                 tuple(v*8 for v in original['hmtx'].metrics['A']))

    def test_precision8_rejects_UPM_geometry_and_variation_field_overflow(self):
        for case in ('UPM', 'glyf', 'gvar'):
            original = q_font(weight_delta=5000 if case == 'gvar' else 1)
            if case == 'UPM': original['head'].unitsPerEm = 3000
            if case == 'glyf': original['glyf']['A'].coordinates[1] = (10000, 600)
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, 'precision8_'):
                rebase_design_font_precision8(original, source_axes())

    def test_precision8_rejects_unscaled_unsupported_tables_and_lazy_hint_programs(self):
        for tag in ('VORG', 'cvt ', 'morx'):
            original = q_font(weight_delta=1)
            original[tag] = newTable(tag)
            with self.subTest(table=tag), self.assertRaisesRegex(ValueError, 'precision8_unsupported_table'):
                rebase_design_font_precision8(original, source_axes())
        from fontTools.ttLib.tables.ttProgram import Program
        original = q_font(weight_delta=1)
        original['glyf']['A'].program = Program()
        original['glyf']['A'].program.fromBytecode([0x00])
        lazy = TTFont(io.BytesIO(serialize(original)), lazy=True, recalcTimestamp=False)
        with self.assertRaisesRegex(ValueError, 'precision8_hint_program_not_supported'):
            rebase_design_font_precision8(lazy, source_axes())

    def test_all_three_clipped_axes_preserve_mixed_gvar_and_VVAR_endpoints(self):
        import itertools
        original = q_font()
        axes = tuple(SourceAxis(axis.tag, axis.minimum, axis.default, axis.maximum, HALF)
                     for axis in source_axes())
        candidate, _ = rebase_design_font(original, axes)
        for signs in itertools.product((-1, 1), repeat=3):
            source_location = {CUSTOM_TAGS[axis.tag]: sign * .5 for axis, sign in zip(axes, signs)}
            target_location = {axis.tag: axis.minimum if sign < 0 else axis.maximum
                               for axis, sign in zip(axes, signs)}
            expected, actual = static_at(original, source_location), static_at(candidate, target_location)
            self.assertEqual(actual['hmtx'].metrics, expected['hmtx'].metrics)
            self.assertEqual(actual['vmtx'].metrics, expected['vmtx'].metrics)
            self.assertEqual(list(actual['glyf']['A'].getCoordinates(actual['glyf'])[0]),
                             list(expected['glyf']['A'].getCoordinates(expected['glyf'])[0]))

    def test_actual_HarfBuzz_GDEF_store_is_rebased_with_its_GPOS_reference(self):
        import uharfbuzz as hb
        from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
        from fontTools.ttLib.tables import otTables
        from fontTools.varLib.builder import buildVarDevTable
        from fontTools.varLib.varStore import OnlineVarStoreBuilder
        original = q_font()
        addOpenTypeFeaturesFromString(original,
            'languagesystem DFLT dflt; feature kern { pos A <0 0 -20 0>; } kern;')
        store = OnlineVarStoreBuilder(list(CUSTOM_TAGS.values()))
        store.setSupports([{'XWGT': (0, 1, 1)}])
        index = store.storeDeltas([20])
        original['GDEF'] = newTable('GDEF')
        original['GDEF'].table = otTables.GDEF()
        for field in ('GlyphClassDef', 'AttachList', 'LigCaretList', 'MarkAttachClassDef', 'MarkGlyphSetsDef'):
            setattr(original['GDEF'].table, field, None)
        original['GDEF'].table.Version = 0x00010003
        original['GDEF'].table.VarStore = store.finish()
        positioning = original['GPOS'].table.LookupList.Lookup[0].SubTable[0]
        positioning.Value.XAdvDevice = buildVarDevTable(index)
        positioning.ValueFormat |= 0x40
        candidate, report = rebase_design_font(original, source_axes())
        advances = []
        for font, location in ((original, {'XWDT': 0., 'XWGT': .5, 'XHGT': 0.}),
                               (candidate, {'WDTH': 500., 'wght': 900., 'HGHT': 500.})):
            native = hb.Font(hb.Face(serialize(font)))
            hb.ot_font_set_funcs(native)
            native.scale = (64000, 64000)
            native.set_variations(location)
            values = []
            for kern in (False, True):
                buffer = hb.Buffer()
                buffer.add_str('A')
                buffer.guess_segment_properties()
                hb.shape(native, buffer, {'kern': kern})
                self.assertEqual([info.codepoint for info in buffer.glyph_infos], [font.getGlyphID('A')])
                values.append(buffer.glyph_positions[0].x_advance)
            advances.append(values)
        self.assertEqual(advances[0], advances[1])
        self.assertEqual(advances[0][1] - advances[0][0], -10 * 64)
        self.assertIn('GDEF', report['variation_tables_processed'])
        self.assertIn('GPOS', report['variation_tables_processed'])

    def test_actual_HarfBuzz_native_glyph_and_HVAR_endpoint_are_preserved(self):
        import uharfbuzz as hb
        original = q_font()
        candidate, _ = rebase_design_font(original, source_axes())
        observations = []
        for font, location in ((original, {'XWDT': 0., 'XWGT': .5, 'XHGT': 0.}),
                               (candidate, {'WDTH': 500., 'wght': 900., 'HGHT': 500.})):
            native = hb.Font(hb.Face(serialize(font)))
            hb.ot_font_set_funcs(native)
            native.scale = (64000, 64000)
            native.set_variations(location)
            gid = font.getGlyphID('A')
            extents = native.get_glyph_extents(gid)
            observations.append((native.get_glyph_h_advance(gid),
                                 (extents.x_bearing, extents.y_bearing, extents.width, extents.height)))
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(observations[0][0], (original['hmtx'].metrics['A'][0] + 10) * 64)

    def test_real_glyph_and_metric_coefficients_are_rebased_instead_of_relabelled(self):
        original = q_font()
        before = serialize(original)
        candidate, report = rebase_design_font(original, source_axes())
        self.assertEqual(serialize(original), before)
        self.assertIsNot(candidate, original)
        self.assertEqual([a.axisTag for a in candidate['fvar'].axes], ['WDTH', 'wght', 'HGHT'])
        self.assertEqual([(a.minValue, a.defaultValue, a.maxValue) for a in candidate['fvar'].axes],
                         [(1, 500, 1000), (100, 500, 900), (1, 500, 1000)])
        for weight, user in ((-.5, 100.), (0., 500.), (.5, 900.)):
            expected = static_at(original, {'XWDT': 0., 'XWGT': weight, 'XHGT': 0.})
            actual = static_at(candidate, {'WDTH': 500., 'wght': user, 'HGHT': 500.})
            for name in original.getGlyphOrder():
                self.assertEqual(actual['hmtx'].metrics[name], expected['hmtx'].metrics[name])
                self.assertEqual(actual['vmtx'].metrics[name], expected['vmtx'].metrics[name])
                self.assertEqual(list(actual['glyf'][name].getCoordinates(actual['glyf'])[0]),
                                 list(expected['glyf'][name].getCoordinates(expected['glyf'])[0]))
        default_width = original['hmtx'].metrics['A'][0]
        endpoint = static_at(candidate, {'WDTH': 500., 'wght': 900., 'HGHT': 500.})
        self.assertEqual(endpoint['hmtx'].metrics['A'][0] - default_width, 10)
        # A naive support rename retains delta20 and produces twice this result.
        self.assertNotEqual(endpoint['hmtx'].metrics['A'][0] - default_width, 20)
        self.assertIn('HVAR', report['variation_tables_processed'])
        self.assertIn('VVAR', report['variation_tables_processed'])
        self.assertFalse(report['lossless_conversion'])
        self.assertTrue(report['coefficient_rounding_possible'])
        self.assertEqual(report['strict_native_candidate_gate'], 'UNACCEPTED')

    def test_odd_delta_half_is_not_relabelled_as_exact_preservation(self):
        original = q_font(weight_delta=1)
        candidate, report = rebase_design_font(original, source_axes())
        # The original HVAR float model has endpoint increment0.5. Restriction
        # rounds integer coefficients; serialize/reopen before measuring truth.
        reopened = TTFont(io.BytesIO(serialize(candidate)))
        try:
            from fontTools.varLib.varStore import VarStoreInstancer
            store = original['HVAR'].table
            original_advance = VarStoreInstancer(store.VarStore, original['fvar'].axes, {'XWGT': .5})
            index = store.AdvWidthMap.mapping['A']
            self.assertEqual(original_advance[index], .5)
            rebased_store = reopened['HVAR'].table
            target_advance = VarStoreInstancer(rebased_store.VarStore, reopened['fvar'].axes, {'wght': 1.})
            target_delta = target_advance[rebased_store.AdvWidthMap.mapping['A']]
            self.assertEqual(abs(target_delta - .5), .5)
            self.assertGreater(abs(target_delta - .5), 1 / 32)
            self.assertFalse(report['font_conversion_accepted'])
            self.assertFalse(report['font_only_equivalence_accepted'])
        finally:
            reopened.close()

    def test_input_proprietary_table_wrong_axes_and_nonidentity_mapping_are_rejected(self):
        for mutation in ('proprietary', 'range', 'avar'):
            font = q_font()
            if mutation == 'proprietary':
                font['hvgl'] = newTable('hvgl'); font['hvgl'].data = b'authored-invalid-proprietary-marker'
            if mutation == 'range': font['fvar'].axes[1].maxValue = 2.
            if mutation == 'avar': font['avar'].segments['XWGT'][.5] = .75
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                rebase_design_font(font, source_axes())

    def test_unsupported_named_instance_is_not_silently_dropped(self):
        font = q_font()
        from fontTools.ttLib.tables._f_v_a_r import NamedInstance
        instance = NamedInstance()
        instance.subfamilyNameID = 2
        instance.coordinates = {'XWDT': 0., 'XWGT': .25, 'XHGT': 0.}
        font['fvar'].instances = [instance]
        before = copy.deepcopy(instance.coordinates)
        with self.assertRaisesRegex(ValueError, 'nonanchor_metadata'):
            rebase_design_font(font, source_axes())
        self.assertEqual(font['fvar'].instances[0].coordinates, before)

    def test_default_metadata_anchors_and_STAT_tags_are_restored(self):
        font = q_font()
        from fontTools.ttLib.tables._f_v_a_r import NamedInstance
        from fontTools.otlLib.builder import buildStatTable
        instance = NamedInstance()
        instance.subfamilyNameID = 2
        instance.coordinates = {'XWDT': 0., 'XWGT': 0., 'XHGT': 0.}
        font['fvar'].instances = [instance]
        buildStatTable(font, [{'tag': tag, 'name': tag, 'values': [{'value': 0, 'name': 'Default'}]}
                              for tag in CUSTOM_TAGS.values()])
        candidate, _ = rebase_design_font(font, source_axes())
        self.assertEqual(candidate['fvar'].instances[0].coordinates,
                         {'WDTH': 500., 'wght': 500., 'HGHT': 500.})
        self.assertEqual([a.AxisTag for a in candidate['STAT'].table.DesignAxisRecord.Axis],
                         ['WDTH', 'wght', 'HGHT'])
        self.assertEqual([a.Value for a in candidate['STAT'].table.AxisValueArray.AxisValue], [500., 500., 500.])

    def test_instance_outside_restricted_interval_cannot_disappear_before_validation(self):
        from fontTools.ttLib.tables._f_v_a_r import NamedInstance
        font = q_font()
        instance = NamedInstance()
        instance.subfamilyNameID = 2
        instance.coordinates = {'XWDT': 0., 'XWGT': 1., 'XHGT': 0.}
        font['fvar'].instances = [instance]
        with self.assertRaisesRegex(ValueError, 'nonanchor_metadata'):
            rebase_design_font(font, source_axes())
        self.assertEqual(font['fvar'].instances[0].coordinates['XWGT'], 1.)


    def test_precision8_rejects_dimensionless_MVAR_caret_scaling(self):
        from fontTools.ttLib.tables import otTables
        from fontTools.ttLib.scaleUpem import scale_upem
        from fontTools.varLib.varStore import OnlineVarStoreBuilder, VarStoreInstancer
        original = q_font()
        original.recalcTimestamp = False
        original['hhea'].caretSlopeRise = 1
        original['hhea'].caretSlopeRun = 0
        builder = OnlineVarStoreBuilder([axis.axisTag for axis in original['fvar'].axes])
        builder.setSupports([{'XWGT': (0, 1, 1)}])
        index = builder.storeDeltas([2])
        table = newTable('MVAR')
        table.table = otTables.MVAR()
        table.table.Version = 0x10000
        table.table.Reserved = 0
        table.table.ValueRecordSize = 8
        table.table.ValueRecordCount = 1
        table.table.VarStore = builder.finish()
        record = otTables.MetricsValueRecord()
        record.ValueTag = 'hcrn'
        record.VarIdx = index
        record.MoreBytes = []
        table.table.ValueRecord = [record]
        original['MVAR'] = table
        before = serialize(original)

        def caret_ratio(font):
            store = font['MVAR'].table
            delta = VarStoreInstancer(store.VarStore, font['fvar'].axes,
                                     {'XWGT': .5})[store.ValueRecord[0].VarIdx]
            return font['hhea'].caretSlopeRise / (font['hhea'].caretSlopeRun + delta)

        # Independently demonstrate why a generic design-unit VarData scaler
        # cannot be admitted here: caret rise/run define a dimensionless ratio.
        # The base remains1/0 but the variation delta is incorrectly scaled8x.
        upstream = TTFont(io.BytesIO(before), recalcTimestamp=False)
        try:
            scale_upem(upstream, original['head'].unitsPerEm * 8)
            self.assertEqual(caret_ratio(original), 1.)
            self.assertEqual(caret_ratio(upstream), .125)
        finally:
            upstream.close()
        with self.assertRaisesRegex(ValueError, 'precision8_unsupported_table'):
            rebase_design_font_precision8(original, source_axes())
        self.assertEqual(serialize(original), before)


if __name__ == '__main__':
    unittest.main()
