"""The conversion adapter must preserve native failures as visible evidence."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTCollection, newTable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from table_metric_oracle import adapt_record, adapted_metadata, identity_design_coordinates
from source_metrics import SourceMetrics
from test_coretext_extract import make_fixture


class TableMetricAdapterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'original-fixture.ttc'
        make_fixture(path)
        self.collection = TTCollection(path)
        self.addCleanup(self.collection.close)
        self.provider = SourceMetrics(self.collection.fonts[0])
        self.provenance = {'source_sha256': 'a' * 64, 'face_index': 0,
                           'policy': 'explicit_original_synthetic_design_coordinates'}

    def record(self, gid=2):
        return {'request_id': 'one', 'face_index': 0, 'glyph_id': gid,
                'location': {'WDTH': 1., 'wght': 100., 'HGHT': 1.},
                'reported_location': {'WDTH': 1., 'wght': 100., 'HGHT': 1.},
                'commands': [['moveTo', 80., 0.], ['lineTo', 300., 0.], ['closePath']],
                'bounds': [80., 0., 220., 420.], 'lsb': 80., 'error': None,
                'advance_width': 569.9920654296875, 'advance_height': 849.,
                'horizontal_origin_x': 0., 'horizontal_origin_y': 0.,
                'vertical_origin_x': 284.99603271484375, 'vertical_origin_y': 760.,
                'vertical_advance_vector': [849., 0.],
                'vertical_origin_derivation': 'native_API_translation'}

    def test_849_is_preserved_and_distinguished_from_850_table_input(self):
        raw = self.record()
        before = copy.deepcopy(raw)
        actual = adapt_record(self.provider, raw, {'WDTH': -1., 'wght': -1., 'HGHT': -1.}, self.provenance)
        self.assertEqual(raw, before)
        self.assertEqual(actual['advance_height'], 850)
        self.assertEqual(actual['raw_coretext_metrics']['advance_height'], 849)
        self.assertEqual(actual['raw_coretext_metric_error_font_units']['advance_height'], -1)
        for field in ('commands', 'bounds', 'lsb', 'location', 'reported_location', 'vertical_advance_vector'):
            self.assertEqual(actual[field], before[field])
        self.assertEqual(actual['metric_backend'], 'SourceTables')
        self.assertFalse(actual['source_metric_provenance']['native_API_values_replaced_in_evidence'])

    def test_blank_origin_keeps_raw_zero_without_losing_table_origin(self):
        raw = self.record(1)
        raw.update(location={'WDTH': 500., 'wght': 400., 'HGHT': 500.}, commands=[], bounds=[0, 0, 0, 0],
                   lsb=0, advance_width=400., advance_height=1000., vertical_origin_x=0., vertical_origin_y=0.)
        actual = adapt_record(self.provider, raw, {'WDTH': 0., 'wght': 0., 'HGHT': 0.}, self.provenance)
        self.assertEqual(actual['commands'], [])
        self.assertEqual((actual['vertical_origin_x'], actual['vertical_origin_y']), (200., 820.))
        self.assertEqual(actual['raw_coretext_metrics']['vertical_origin_y'], 0.)
        self.assertEqual(actual['raw_coretext_metric_error_font_units']['vertical_origin_y'], -820.)

    def test_native_failure_missing_metrics_and_second_adaptation_are_rejected(self):
        changes = [{'error': 'coretext_did_not_report_requested_axis_value:WDTH'},
                   {'advance_height': None}, {'advance_height': float('nan')}, {'advance_height': True},
                   {'type': 'request_error'}, {'raw_coretext_metrics': {}}]
        for change in changes:
            with self.assertRaises(ValueError):
                adapt_record(self.provider, {**self.record(), **change},
                             {'WDTH': -1., 'wght': -1., 'HGHT': -1.}, self.provenance)
        with self.assertRaisesRegex(ValueError, 'explicit coordinate policy'):
            adapt_record(self.provider, self.record(), {'WDTH': -1., 'wght': -1., 'HGHT': -1.}, {})
        with self.assertRaisesRegex(ValueError, 'explicit coordinate policy'):
            adapt_record(self.provider, self.record(), {'WDTH': -1., 'wght': -1., 'HGHT': -1.},
                         {**self.provenance, 'source_sha256': 'z' * 64})
        with self.assertRaisesRegex(ValueError, 'physical face'):
            adapt_record(self.provider, self.record(), {'WDTH': -1., 'wght': -1., 'HGHT': -1.},
                         {**self.provenance, 'face_index': 1})

    def test_identity_policy_requires_complete_original_user_coordinates(self):
        font = self.collection.fonts[0]
        point = {'WDTH': 631.25, 'wght': 523.75, 'HGHT': 711.125}
        before = dict(point)
        result = identity_design_coordinates(font, point)
        self.assertEqual(point, before)
        self.assertAlmostEqual(result['WDTH'], .2625)
        self.assertAlmostEqual(result['wght'], .2475)
        self.assertAlmostEqual(result['HGHT'], .42225)
        for bad in ({'WDTH': 631.25}, {**point, 'HGHT': 1001}, {**point, 'WDTH': float('nan')}):
            with self.assertRaises(ValueError):
                identity_design_coordinates(font, bad)

    def test_nonzero_stored_phantom_cannot_be_combined_with_shifted_native_path(self):
        font = self.collection.fonts[0]
        font['hmtx'].metrics['probe'] = (700, 99)
        # Stored xMin100 - lsb99 gives pp0=1. A native path measured with pen
        # origin0 is a different frame; copying its geometry is insufficient.
        with self.assertRaisesRegex(ValueError, 'coordinate origins differ'):
            adapt_record(SourceMetrics(font), self.record(),
                         {'WDTH': -1., 'wght': -1., 'HGHT': -1.}, self.provenance)

    def test_identity_policy_cannot_admit_HVGL_or_changed_avar(self):
        font = self.collection.fonts[0]
        point = {'WDTH': 500., 'wght': 400., 'HGHT': 500.}
        font['hvgl'] = newTable('hvgl')
        font['hvgl'].data = b''
        with self.assertRaisesRegex(ValueError, 'cannot accept Apple HVGL'):
            identity_design_coordinates(font, point)
        del font['hvgl']
        # Persist a different avar so the policy tests raw records, not only the
        # lossy, already-decompiled fontTools dictionary representation.
        font['avar'].segments['WDTH'][.5] = .75
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'different-avar.ttc'
            self.collection.save(output)
            with TTCollection(output) as different:
                with self.assertRaisesRegex(ValueError, 'nonidentity'):
                    identity_design_coordinates(different.fonts[0], point)

    def test_metadata_retains_native_policy_and_rejects_diagnostic_axis_bypass(self):
        native = {'type': 'metadata', 'backend': 'CoreText', 'source_sha256': 'a' * 64,
                  'metrics_policy': 'original_raw_API_policy',
                  'faces': [{'face_index': i, 'upm': upm, 'glyph_count': 3, 'status': 'identity_verified'}
                            for i, upm in enumerate((1000, 1128))]}
        before = copy.deepcopy(native)
        actual = adapted_metadata(native, 'a' * 64, self.collection.fonts)
        self.assertEqual(native, before)
        self.assertEqual(actual['outline_backend'], 'CoreText')
        self.assertEqual(actual['metric_backend'], 'SourceTables')
        self.assertEqual(actual['native_metrics_policy'], 'original_raw_API_policy')
        self.assertEqual(actual['strict_native_API_metric_acceptance'], 'NOT_ESTABLISHED_BY_THIS_ADAPTER')
        for change in [{'source_sha256': 'b' * 64}, {'diagnostic_readback_observation_only': True},
                       {'axis_observations_only': True}]:
            with self.assertRaises(ValueError):
                adapted_metadata({**native, **change}, 'a' * 64, self.collection.fonts)


if __name__ == '__main__':
    unittest.main()
