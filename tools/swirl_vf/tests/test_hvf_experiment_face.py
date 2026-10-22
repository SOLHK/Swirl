"""Authored complete-default assembly; no original font or native claim."""
import copy
import io
from pathlib import Path
import sys
import unittest

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.TupleVariation import TupleVariation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'platform'))
sys.path.insert(0, str(ROOT/'tools'))
from rebuild_c1_fixture import make_face
from hvf_experiment_face import LIMIT, Q_TAGS, assemble_experiment_face
from metric_variations import verify_metric_variations
from rebuild import verify_serialized_face


def authored_source():
    font = make_face(0)
    records = []
    for gid, name in enumerate(font.getGlyphOrder()):
        pen = RecordingPen()
        font['glyf'][name].draw(pen, font['glyf'])
        commands = [[kind, *(v for point in points for v in point)] for kind, points in pen.value]
        records.append({'glyph_id': gid, 'commands': commands})
    for tag in ('glyf', 'loca', 'gvar'):
        del font[tag]
    font['hvgl'] = newTable('hvgl')
    font['hvgl'].data = b'authored HVF fixture marker; never a native decoder input'
    font['VORG'] = newTable('VORG')
    font['VORG'].majorVersion, font['VORG'].minorVersion = 1, 0
    font['VORG'].defaultVertOriginY = 901
    font['VORG'].VOriginRecords = {'curve': 905}
    return font, records


def authored_base(format_=1):
    table = newTable('BASE')
    table.table = otTables.BASE()
    table.table.Version = 0x00010000
    table.table.VertAxis = None
    axis = table.table.HorizAxis = otTables.Axis()
    axis.BaseTagList = otTables.BaseTagList()
    axis.BaseTagList.BaseTagCount, axis.BaseTagList.BaselineTag = 1, ['romn']
    axis.BaseScriptList = otTables.BaseScriptList()
    record = otTables.BaseScriptRecord()
    record.BaseScriptTag, record.BaseScript = 'DFLT', otTables.BaseScript()
    script = record.BaseScript
    script.DefaultMinMax, script.BaseLangSysCount, script.BaseLangSysRecord = None, 0, []
    script.BaseValues = otTables.BaseValues()
    script.BaseValues.DefaultIndex, script.BaseValues.BaseCoordCount = 0, 1
    coord = otTables.BaseCoord()
    coord.Format, coord.Coordinate = format_, 123
    if format_ == 2:
        coord.ReferenceGlyph, coord.BaseCoordPoint = 'A', 0
    script.BaseValues.BaseCoord = [coord]
    axis.BaseScriptList.BaseScriptCount, axis.BaseScriptList.BaseScriptRecord = 1, [record]
    return table


class HVFExperimentFaceTests(unittest.TestCase):
    def source(self):
        source, records = authored_source()
        self.addCleanup(source.close)
        return source, records

    def build(self, source, records, models=None, multiplier=15):
        font, manifest = assemble_experiment_face(source, iter(records), models, multiplier=multiplier)
        self.addCleanup(font.close)
        return font, manifest

    def test_all_default_GIDs_cmap_empty_measurements_and_reopened_models(self):
        source, records = self.source()
        old_order, old_cmap = source.getGlyphOrder(), source['cmap'].compile(source)
        font, report = self.build(source, records)
        self.assertEqual(font.getGlyphOrder(), old_order)
        self.assertEqual(font['cmap'].compile(font), old_cmap)
        self.assertEqual(report['native_default_records_consumed'], 7)
        self.assertEqual(report['measured_empty_default_glyphs'], 2)
        self.assertEqual(report['default_only_GIDs'], 7)
        self.assertEqual([axis.axisTag for axis in font['fvar'].axes], list(Q_TAGS))
        self.assertTrue(all((a.minValue, a.defaultValue, a.maxValue) == (-1, 0, 1) for a in font['fvar'].axes))
        self.assertEqual(font['fvar'].instances, [])
        self.assertIn('EXPERIMENTAL DEFAULT ONLY', font['name'].getDebugName(1))
        self.assertTrue(report['axis_models_partial'])
        self.assertFalse(report['strict_font_acceptance'])
        self.assertFalse(report['production_accepted'])
        self.assertFalse(report['standard_component_relations_preserved'])
        self.assertEqual(report['vertical_origin_x_native_validation'], 'NOT_RUN')
        self.assertEqual(set(report['removed_tables']), {'hvgl', 'VORG', 'HVAR', 'VVAR', 'fvar', 'avar', 'STAT'})
        data = io.BytesIO()
        font.save(data)
        with TTFont(io.BytesIO(data.getvalue())) as reopened:
            result = verify_serialized_face(font, reopened)
            self.assertEqual(result['glyphs_checked'], 7)
            self.assertEqual(reopened['cmap'].compile(reopened), old_cmap)
        self.assertIn('hvgl', source)
        self.assertNotIn('glyf', source)
        self.assertEqual(source['head'].unitsPerEm, 1000)

    def test_native_fractions_scale_before_first_round_and_strict_failure_is_retained(self):
        source, records = self.source()
        x, y = records[2]['commands'][0][1:]
        records[2]['commands'][0][1:] = [x+.49, y+.49]
        font, report = self.build(source, records)
        self.assertEqual(tuple(font['glyf']['A'].coordinates[0]), (round((x+.49)*15), round((y+.49)*15)))
        self.assertNotEqual(font['glyf']['A'].coordinates[0][0], round(x+.49)*15)
        self.assertGreater(report['default_maximum_point_quantization_error_source_units'], LIMIT)
        self.assertGreater(report['default_points_above_1_32'], 0)
        self.assertFalse(report['strict_font_acceptance'])

    def test_default_phantoms_keep_source_VORG_and_zero_horizontal_origin(self):
        source, records = self.source()
        font, _ = self.build(source, records)
        for name in source.getGlyphOrder():
            points, _ = font['glyf']._getCoordinatesAndControls(name, font['hmtx'].metrics, font['vmtx'].metrics)
            self.assertEqual(tuple(points[-4]), (0, 0))
            self.assertEqual(points[-3][0], source['hmtx'].metrics[name][0]*15)
            self.assertEqual(points[-2][1], source['VORG'][name]*15)
            self.assertEqual(points[-2][1]-points[-1][1], source['vmtx'].metrics[name][0]*15)

    def test_complete_order_is_required_no_blank_standins(self):
        source, records = self.source()
        cases = [records[:-1], records+[records[-1]], records[:2]+records[3:],
                 records[:2]+[records[1]]+records[3:], list(reversed(records))]
        for rows in cases:
            with self.subTest(ids=[r['glyph_id'] for r in rows]), self.assertRaisesRegex(ValueError, 'complete_ordered'):
                self.build(source, rows)

    def test_missing_commands_and_boolean_GID_are_rejected(self):
        source, records = self.source()
        for replacement in ({'glyph_id': 0}, {'glyph_id': False, 'commands': []}):
            rows = [replacement, *records[1:]]
            with self.subTest(record=replacement), self.assertRaisesRegex(ValueError, 'complete_ordered'):
                self.build(source, rows)

    def test_scaled_coordinates_and_metrics_cannot_overflow(self):
        source, records = self.source()
        records[2]['commands'][0][1] = 10000
        with self.assertRaisesRegex(ValueError, 'coordinate_overflow'):
            self.build(source, records)
        source2, records2 = self.source()
        source2['hmtx'].metrics['A'] = (60000, 12)
        with self.assertRaisesRegex(ValueError, 'metric_overflow'):
            self.build(source2, records2)

    def test_legal_grid_and_original_axis_order_are_enforced(self):
        source, records = self.source()
        for multiplier in (True, 0, 17):
            with self.subTest(multiplier=multiplier), self.assertRaisesRegex(ValueError, 'precision_grid'):
                self.build(source, records, multiplier=multiplier)
        source['fvar'].axes.reverse()
        with self.assertRaisesRegex(ValueError, 'axis_order'):
            self.build(source, records)

    def test_AAT_bytes_remain_explicitly_unscaled_unverified(self):
        source, records = self.source()
        for tag in ('trak', 'cidg'):
            from fontTools.ttLib.tables.DefaultTable import DefaultTable
            source[tag] = DefaultTable(tag)
            source[tag].data = b'opaque authored unsupported source semantics'
        font, report = self.build(source, records)
        for tag in ('trak', 'cidg'):
            self.assertEqual(font.getTableData(tag), source.getTableData(tag))
            self.assertEqual(report['retained_unscaled_unverified_tables'][tag]['status'], 'UNSCALED_UNVERIFIED')
        self.assertFalse(report['font_only_equivalence_accepted'])

    def test_static_BASE_coordinates_scale_but_point_index_coordinates_are_refused(self):
        source, records = self.source()
        source['BASE'] = authored_base()
        font, _ = self.build(source, records)
        coord = font['BASE'].table.HorizAxis.BaseScriptList.BaseScriptRecord[0].BaseScript.BaseValues.BaseCoord[0]
        self.assertEqual(coord.Coordinate, 123*15)
        source['BASE'] = authored_base(2)
        with self.assertRaisesRegex(ValueError, 'point_indices'):
            self.build(source, records)

    def test_unknown_table_and_hint_program_are_refused(self):
        for tag in ('ZZZZ', 'fpgm'):
            source, records = self.source()
            from fontTools.ttLib.tables.DefaultTable import DefaultTable
            source[tag] = DefaultTable(tag)
            source[tag].data = b'authored unsupported semantics'
            with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, 'unsupported_table_semantics'):
                self.build(source, records)

    def test_selected_scaled_models_regenerate_exact_HVAR_VVAR_without_accepting_failure(self):
        source, records = self.source()
        baseline, _ = self.build(source, records)
        glyph = copy.deepcopy(baseline['glyf']['A'])
        deltas = [(0, 0)]*len(glyph.coordinates)+[(0, 0), (30, 0), (0, 15), (0, -15)]
        variation = TupleVariation({'XWGT': (0, 1, 1)}, deltas)
        proof = {'glyph_id': 2, 'source_units_per_em': 1000, 'target_units_per_em': 15000,
                 'physical_grid_multiplier': 15, 'strict_sample_check_passed': False,
                 'status': 'FAIL_STRICT_EXPERIMENTAL_SAMPLES'}
        model = (glyph, [variation], baseline['hmtx'].metrics['A'], baseline['vmtx'].metrics['A'], proof)
        font, report = self.build(source, records, {2: model})
        self.assertEqual(report['selected_variable_GIDs'], [2])
        self.assertEqual(report['default_only_GIDs'], 6)
        self.assertEqual(len(font['gvar'].variations['A']), 1)
        self.assertEqual(verify_metric_variations(font)['status'], 'PASS_EXACT_STANDARD_METRIC_COEFFICIENTS')
        self.assertFalse(report['selected_model_reports'][0]['report']['strict_sample_check_passed'])
        self.assertFalse(report['production_accepted'])
        proof['physical_grid_multiplier'] = 14
        with self.assertRaisesRegex(ValueError, 'scale_binding'):
            self.build(source, records, {2: model})


if __name__ == '__main__':
    unittest.main()
