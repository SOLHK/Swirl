"""Authored nonlinear interpolation improves; strict failures stay visible."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from hvf import HVGL
from hvf_glyph_model import LIMIT, build_glyph_model
from hvf_model_nodes import tensor_training_grid
from rebuild import normalized_grid
from test_hvf import shape, table

TAGS = ('XWDT', 'XWGT', 'XHGT')
HOLDOUTS = [dict(zip(TAGS, (.25, .125, .375)))]


class HVFModelNodesTests(unittest.TestCase):
    def test_125_exact_nodes_preserve_existing_default_grid_and_frozen_holdouts(self):
        baseline = normalized_grid(TAGS)
        profile = tensor_training_grid(TAGS, forbidden_locations=HOLDOUTS)
        self.assertEqual(len(baseline), 27)
        self.assertEqual(len(profile), 125)
        self.assertEqual(profile[0], dict.fromkeys(TAGS, 0.))
        self.assertTrue(all(location in profile for location in baseline))
        self.assertTrue(all(value*16384 == int(value*16384)
                            for location in profile for value in location.values()))
        self.assertTrue(all(location not in profile for location in HOLDOUTS))
        self.assertEqual(normalized_grid(TAGS), baseline)

    def test_nonlinear_holdout_improves_without_erasing_default_quantization_failure(self):
        # Variable parallel factor times variable off-curve displacement gives
        # an authored quadratic in positive XWDT. No original font data enters.
        raw = bytearray(shape(axes=3, parallel=True, blends=(0, 1, 1)))
        struct.pack_into('<d', raw, 208, .5)  # positive factor delta
        struct.pack_into('<d', raw, 224, 0.)  # first off-control does not translate
        font = HVGL(table([bytes(raw)]))
        metric = {'advance_width': 600, 'advance_height': 1000, 'lsb': 0,
                  'horizontal_origin_x': 0, 'vertical_origin_x': 300, 'vertical_origin_y': 900}
        reports = []
        for training in (normalized_grid(TAGS), tensor_training_grid(TAGS)):
            records = [metric.copy() for _ in training+HOLDOUTS]
            reports.append(build_glyph_model(font, 0, TAGS, training, HOLDOUTS, records,
                source_upem=1000, multiplier=15)[-1])
        before, after = [report['target_design_unit_evidence'] for report in reports]
        self.assertLess(after['sample_maxima']['holdout']['max_outline_error_bound_units'],
                        before['sample_maxima']['holdout']['max_outline_error_bound_units'])
        self.assertEqual(after['default_quantization_error'], before['default_quantization_error'])
        self.assertGreater(after['default_quantization_error']['max_outline_error_bound_units']/15, LIMIT)
        self.assertEqual(reports[0]['max_metric_error_source_units'], reports[1]['max_metric_error_source_units'])
        for report in reports:
            self.assertEqual(report['status'], 'FAIL_STRICT_EXPERIMENTAL_SAMPLES')
            self.assertEqual(report['strict_limit_source_font_units'], LIMIT)
            self.assertFalse(report['production_accepted'])
            self.assertFalse(report['continuous_space_proof'])

    def test_holdout_collision_and_invalid_tag_sets_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'holdout_collides'):
            tensor_training_grid(TAGS, forbidden_locations=[dict.fromkeys(TAGS, .5)])
        for tags in ((), ('WDTH',)*2, ('longtag',), ('A', 'B', 'C', 'D')):
            with self.subTest(tags=tags), self.assertRaisesRegex(ValueError, 'axis_tags'):
                tensor_training_grid(tags)


if __name__ == '__main__':
    unittest.main()
