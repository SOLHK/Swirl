"""The original-axis experiment must reject unauthenticated inputs pre-write."""
import json
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'platform'))
from p7_nominal_candidate import run, serialized_metric_candidate
from rebuild import sha256


class NominalCandidateInputTests(unittest.TestCase):
    def test_rebased_interior_support_encodes_before_strict_metric_derivation(self):
        from fontTools.ttLib.tables.TupleVariation import TupleVariation
        from metric_variations import add_metric_variations, verify_metric_variations, MetricVariationError
        from rebase_design_font import rebase_design_font
        from target_axis_mapping import SourceAxis
        from test_rebase_design_font import q_font, source_axes, serialize
        font = q_font()
        count = len(font['glyf']['A'].coordinates)
        font['gvar'].variations['A'].append(TupleVariation({'XWGT': (0., .5, 1.)},
            [(0, 0)]*count+[(0, 0), (12, 0), (0, 8), (0, 0)]))
        del font['HVAR']; del font['VVAR']
        add_metric_variations(font)
        source_bytes = serialize(font)
        axes = list(source_axes())
        axes[1] = SourceAxis('wght', 100., 500., 900.,
            ((-16384, -16384), (-16384, -12288), (0, 0), (16384, 12288), (16384, 16384)))
        candidate, _ = rebase_design_font(font, axes)
        unencoded = copy.deepcopy(candidate)
        del unencoded['HVAR']; del unencoded['VVAR']
        with self.assertRaisesRegex(MetricVariationError, 'not exactly representable in F2DOT14'):
            add_metric_variations(unencoded)
        encoded, audit = serialized_metric_candidate(candidate)
        self.assertGreater(audit['changed_support_coordinates'], 0)
        self.assertLessEqual(audit['maximum_normalized_support_encoding_error'], .5/16384)
        self.assertTrue(any(region.axes.get('wght', (0, 0, 0))[1] == 10923/16384
                            for region in encoded['gvar'].variations['A']))
        self.assertEqual(verify_metric_variations(encoded)['status'], 'PASS_EXACT_STANDARD_METRIC_COEFFICIENTS')
        self.assertFalse(audit['strict_font_acceptance'])
        self.assertEqual(serialize(font), source_bytes)

    def test_support_serialization_keeps_existing_packed_delta_overflow_guard(self):
        from test_rebase_design_font import q_font
        font = q_font()
        font['gvar'].variations['A'][0].coordinates[0] = (32768, 0)
        with self.assertRaisesRegex(ValueError, 'gvar_packed_delta_out_of_range'):
            serialized_metric_candidate(font)

    def test_reopening_default_only_gvar_slots_does_not_invent_variable_models(self):
        from metric_variations import verify_metric_variations
        from test_rebase_design_font import q_font
        font = q_font()
        order = font.getGlyphOrder()
        del font['gvar'].variations['space']
        encoded, audit = serialized_metric_candidate(font)
        self.assertEqual(encoded.getGlyphOrder(), order)
        self.assertEqual(encoded['gvar'].variations['space'], [])
        self.assertEqual(audit['changed_support_coordinates'], 0)
        self.assertEqual(verify_metric_variations(encoded)['status'], 'PASS_EXACT_STANDARD_METRIC_COEFFICIENTS')

    def test_wrong_original_is_rejected_before_output_or_font_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'authored-source'
            source.write_bytes(b'authored control, not an Apple font')
            output = root/'must-not-be-created'
            with patch('p7_nominal_candidate.TTCollection') as parse:
                with self.assertRaisesRegex(ValueError, 'exact_original_source_required'):
                    run(source, root, output)
            parse.assert_not_called()
            self.assertFalse(output.exists())

    def test_parent_byte_change_is_rejected_before_output_or_rebase(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'authored-source'
            source.write_bytes(b'authored control')
            candidate = root/'P7-Original-face0-EXPERIMENTAL.ttf'
            candidate.write_bytes(b'original authored candidate bytes')
            receipt = dict(source_sha256=sha256(source), production_accepted=False,
                           axis_models_partial=True, glyph_count=47102,
                           candidate_sha256=sha256(candidate))
            (root/'face-report.json').write_text(json.dumps(receipt))
            candidate.write_bytes(b'changed authored candidate bytes')
            output = root/'must-not-be-created'
            with patch('p7_nominal_candidate.EXPECTED', sha256(source)), \
                 patch('p7_nominal_candidate.rebase_design_font') as rebase:
                with self.assertRaisesRegex(ValueError, 'verified_private_P7_parent_required'):
                    run(source, root, output)
            rebase.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
