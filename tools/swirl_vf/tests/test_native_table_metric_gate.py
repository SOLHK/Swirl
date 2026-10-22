"""A separate table-metric gate cannot hide raw API or native outline errors."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTCollection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from source_metrics import SourceMetrics
from table_metric_oracle import adapt_record
from test_coretext_extract import make_fixture
from test_native_table_metrics import check_adapted_records, run


class NativeTableMetricGateTests(unittest.TestCase):
    def observations(self):
        request = {'request_id': 'original-minimum', 'face_index': 0, 'glyph_ids': [2],
                   'location': {'WDTH': 1., 'wght': 100., 'HGHT': 1.}}
        # Hand-defined minimum of the original fixture: no measured Apple data
        # and no invocation of the gate's analytic expectation generator.
        record = {'request_id': request['request_id'], 'face_index': 0, 'glyph_id': 2,
                  'location': dict(request['location']), 'reported_location': dict(request['location']),
                  'commands': [['moveTo', 80., 0.], ['lineTo', 260., 0.],
                               ['qCurveTo', 340., 210., 260., 420.], ['lineTo', 80., 420.], ['closePath']],
                  'bounds': [80., 0., 220., 420.], 'lsb': 80., 'error': None,
                  'advance_width': 570., 'advance_height': 849.,
                  'horizontal_origin_x': 0., 'horizontal_origin_y': 0.,
                  'vertical_origin_x': 285., 'vertical_origin_y': 760.}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'original.ttc'
            make_fixture(source)
            with TTCollection(source) as collection:
                converted = adapt_record(SourceMetrics(collection.fonts[0]), record,
                    {'WDTH': -1., 'wght': -1., 'HGHT': -1.},
                    {'policy': 'explicit_original_synthetic_endpoint', 'source_sha256': 'a'*64, 'face_index': 0})
        return [request], [record], [converted]

    def test_table_pass_keeps_visible_one_unit_native_API_failure(self):
        requests, raw, converted = self.observations()
        report = check_adapted_records(raw, converted, requests)
        self.assertEqual(report['glyph_records'], 1)
        self.assertEqual(report['maximum_analytic_error_by_field']['advance_height'], 0)
        self.assertEqual(report['maximum_retained_raw_API_error_by_field']['advance_height'], 1)
        self.assertFalse(report['raw_CoreText_API_gate_passed_by_this_check'])

    def test_changed_native_curve_cannot_pass_using_correct_metric_tables(self):
        requests, raw, converted = self.observations()
        for records in (raw, converted):
            records[0]['commands'][2][1] += 2
        with self.assertRaisesRegex(AssertionError, 'native analytic control-point error'):
            check_adapted_records(raw, converted, requests)

    def test_erasing_raw_error_or_dropping_a_record_is_rejected(self):
        requests, raw, converted = self.observations()
        changed = copy.deepcopy(converted)
        changed[0]['raw_coretext_metrics']['advance_height'] = 850
        with self.assertRaisesRegex(AssertionError, 'raw advance_height was altered'):
            check_adapted_records(raw, changed, requests)
        changed = copy.deepcopy(converted)
        changed[0]['raw_coretext_metric_error_font_units']['advance_height'] = 0
        with self.assertRaisesRegex(AssertionError, 'discrepancy concealed'):
            check_adapted_records(raw, changed, requests)
        with self.assertRaisesRegex(AssertionError, 'glyph count differs'):
            check_adapted_records(raw, [], requests)
        with self.assertRaisesRegex(AssertionError, 'glyph count differs'):
            check_adapted_records(raw + raw, converted, requests)

    @unittest.skipIf(sys.platform == 'darwin', 'native execution is an explicit CI integration gate')
    def test_unavailable_CoreText_is_not_native_reconstruction_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.assertEqual(run(output, require_native=True), 2)
            report = json.loads((output / 'native_table_metric_reconstruction.json').read_text())
            self.assertEqual(report['status'], 'NOT_RUN')
            self.assertFalse(report['original_strict_native_API_gate_modified'])
            self.assertEqual(report['native_original_font_acceptance'], 'NOT_RUN')
            self.assertFalse(report['font_artifact_retained'])


if __name__ == '__main__':
    unittest.main()
