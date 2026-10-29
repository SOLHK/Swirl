"""Pure authored HVF model conversion, strict failures retained."""
import io
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

import numpy as np
from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
from batch_geometry import ContourSource, GeometryBatch
from hvf import HVGL, UnsupportedRendering
from hvf_glyph_model import LIMIT, build_glyph_model
from rebuild import normalized_grid
from rebuild_c1_fixture import make_face
from test_hvf import shape, table

TAGS = ('WDTH', 'wght', 'HGHT')
TRAINING = normalized_grid(TAGS)
HOLDOUTS = [dict(zip(TAGS, q)) for q in ((.25, -.5, .375), (-.125, .75, -.5), (.5, .5, .5))]
METRIC = {'advance_width': 600, 'advance_height': 1000, 'lsb': 0,
          'horizontal_origin_x': 0, 'vertical_origin_x': 300, 'vertical_origin_y': 900}


def metrics():
    return [METRIC.copy() for _ in TRAINING + HOLDOUTS]


def model(raw=None, multiplier=1, records=None):
    return build_glyph_model(HVGL(table([shape(axes=3) if raw is None else raw])),
        0, TAGS, TRAINING, HOLDOUTS, metrics() if records is None else records,
        source_upem=1000, multiplier=multiplier)


class HVFGlyphModelTests(unittest.TestCase):
    def test_existing_C1_builds_real_quadratic_glyph_tuples_and_table_phantoms(self):
        glyph, tuples, horizontal, vertical, report = model(multiplier=8)
        self.assertEqual(glyph.numberOfContours, 1)
        self.assertEqual(list(glyph.endPtsOfContours), [6])
        self.assertEqual(list(glyph.flags), [0x41, 0, 1, 0, 1, 0, 1])
        self.assertEqual(len(tuples), 2)
        self.assertEqual([tuple.axes for tuple in tuples],
                         [{'WDTH': (-1., -1., 0.)}, {'WDTH': (0., 1., 1.)}])
        self.assertEqual(horizontal, (4800, 0))
        self.assertEqual(vertical, (8000, 6400))
        self.assertTrue(report['strict_sample_check_passed'])
        self.assertEqual(report['max_point_error_source_units'], 0)
        self.assertEqual(report['max_metric_error_source_units'], 0)
        self.assertEqual(report['source_contours'], [{'part_index': 0, 'tree_part_offset': 0,
            'source_path_index': 0, 'source_segment_start': 0}])
        self.assertEqual(report['metrics_provenance'], 'CALLER_SUPPLIED_TABLE_RECORDS_NOT_NATIVE')
        self.assertTrue(report['HVF_DAG_flattened'])
        self.assertFalse(report['original_component_structure_preserved'])
        self.assertFalse(report['production_accepted'])

    def test_quantization_failure_is_returned_then_precision16_fixes_authored_grid(self):
        raw = bytearray(shape(axes=3))
        struct.pack_into('<d', raw, 16, 1/16)  # authored on-curve coordinate
        failed = model(bytes(raw), multiplier=8)[-1]
        self.assertEqual(failed['status'], 'FAIL_STRICT_EXPERIMENTAL_SAMPLES')
        self.assertGreater(failed['max_point_error_source_units'], LIMIT)
        self.assertTrue(failed['target_design_unit_evidence']['failures'])
        glyph, _, _, _, passed = model(bytes(raw), multiplier=16)
        self.assertEqual(glyph.coordinates[0][0] / 16, 1/16)
        self.assertEqual(passed['strict_limit_source_font_units'], LIMIT)
        self.assertTrue(passed['strict_sample_check_passed'])
        self.assertFalse(passed['continuous_space_proof'])
        self.assertFalse(passed['font_only_equivalence_accepted'])

    def test_result_serializes_as_standard_glyf_gvar_and_preserves_coefficients(self):
        glyph, tuples, horizontal, vertical, report = model(multiplier=8)
        host = make_face(0)
        host['head'].unitsPerEm = report['target_units_per_em']
        host['glyf']['A'] = glyph
        host['gvar'].variations['A'] = tuples
        host['hmtx'].metrics['A'] = horizontal
        host['vmtx'].metrics['A'] = vertical
        stream = io.BytesIO(); host.save(stream)
        with TTFont(io.BytesIO(stream.getvalue())) as decoded:
            self.assertEqual(list(decoded['glyf']['A'].coordinates), list(glyph.coordinates))
            for wanted, actual in zip(tuples, decoded['gvar'].variations['A']):
                self.assertEqual(wanted.axes, actual.axes)
                self.assertEqual(wanted.coordinates, actual.coordinates)
            self.assertEqual(decoded['hmtx'].metrics['A'], horizontal)
            self.assertEqual(decoded['vmtx'].metrics['A'], vertical)

    def test_rejects_unsupported_blends_topology_and_fake_or_missing_metrics(self):
        for blend in (2, 3, 4):
            with self.subTest(blend=blend), self.assertRaises(UnsupportedRendering):
                model(shape(axes=3, blends=(blend, 1, 1)))
        bad = GeometryBatch([np.zeros((len(TRAINING + HOLDOUTS), 5, 2))],
                            [ContourSource(0, 0, 0, 0)], len(TRAINING + HOLDOUTS))
        with patch('hvf_glyph_model.BatchGeometry.render', return_value=bad):
            with self.assertRaisesRegex(ValueError, 'point_topology'): model()
        for value in (None, float('nan'), True):
            records = metrics(); records[0]['vertical_origin_y'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'metric_records'):
                model(records=records)
        for multiplier in (0, True, 17):
            with self.subTest(multiplier=multiplier), self.assertRaisesRegex(ValueError, 'precision_grid'):
                model(multiplier=multiplier)


if __name__ == '__main__':
    unittest.main()
