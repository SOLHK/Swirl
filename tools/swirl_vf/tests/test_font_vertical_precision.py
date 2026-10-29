"""Font-file controls: physical units, independent holdouts and retained failures."""
from fractions import Fraction
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from fontTools.ttLib import TTFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import font_vertical_precision as precision
import experiment_vertical_gpos as fixture

try:
    import uharfbuzz
except ImportError:
    uharfbuzz = None


class FontVerticalPrecisionTables(unittest.TestCase):
    def test_exact_coefficients_and_original_fixed_origin_survive_serialization(self):
        for kind in ('even', 'odd_width', 'odd_delta'):
            for upem in precision.SOURCE_UPEMS:
                with self.subTest(kind=kind, upem=upem):
                    source, candidate, symbols, evidence = precision.build_control(kind, upem, 8)
                    self.assertEqual(evidence['glyphs'], 8)
                    self.assertFalse(evidence['raw_native_API_equality_asserted'])
                    font = TTFont(io.BytesIO(candidate))
                    self.assertEqual(font['head'].unitsPerEm, upem*8)
                    # Independent serialized GPOS equation at unseen positions;
                    # divide by the real grid scale to retain SOURCE units.
                    for point in precision.HOLDOUTS:
                        shifts = fixture.table_adjustments(candidate, symbols, point)
                        for s in symbols:
                            expected = Fraction(fixture.analytic_width(s, point))/2 - s.width//2
                            self.assertAlmostEqual(shifts[s.name]/8, float(expected), places=10)
                    self.assertEqual(precision.verify_physical_tables(source, candidate, 8), evidence)

    def test_physical_verifier_rejects_outline_advance_and_mapping_substitution(self):
        source, candidate, _, _ = precision.build_control('odd_delta')
        for field in ('outline', 'advance', 'cmap'):
            font = TTFont(io.BytesIO(candidate))
            if field == 'outline':
                glyph = font['glyf']['han']
                x, y = glyph.coordinates[0]; glyph.coordinates[0] = (x+1, y)
            elif field == 'advance':
                width, lsb = font['hmtx'].metrics['han']; font['hmtx'].metrics['han'] = (width+1, lsb)
            else:
                font['cmap'].getBestCmap()[0x4E2D] = 'latinA'
            with self.subTest(field=field), self.assertRaises(ValueError):
                precision.verify_physical_tables(source, fixture.serialize(font), 8)

    def test_invalid_scale_types_and_OpenType_UPEM_overflow_fail_before_output(self):
        for upem, multiplier in ((1000, True), (1000, 8.), (1000, 1), (1000, -2),
                                  (1144, 16), (1000, 18), (True, 8), (1000., 8)):
            with self.subTest(upem=upem, multiplier=multiplier), self.assertRaises(ValueError):
                precision.build_control('even', upem, multiplier)

    def test_serialization_coordinate_overflow_never_publishes_a_candidate(self):
        data, symbols = fixture.original_fixture()
        font = TTFont(io.BytesIO(data))
        glyph = font['glyf']['han']
        x, y = glyph.coordinates[1]; glyph.coordinates[1] = (32000, y)
        extreme_authored = fixture.serialize(font)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'candidate'
            with patch.object(fixture, 'original_fixture', return_value=(extreme_authored, symbols)):
                with self.assertRaises((ValueError, OverflowError, struct.error)):
                    precision.write_control(output)
            self.assertFalse(output.exists())

    def test_holdouts_are_frozen_distinct_from_preceding_experiment(self):
        self.assertEqual(len(precision.HOLDOUTS), 9)
        self.assertFalse(set(precision.HOLDOUTS) & set(fixture.POINTS))
        self.assertEqual(precision.LIMIT, Fraction(1, 32))
        for point in precision.HOLDOUTS:
            self.assertTrue(all(-1 <= v <= 1 and v*16384 == int(v*16384) for v in point))


@unittest.skipIf(uharfbuzz is None, 'optional uharfbuzz unavailable; layout NOT_RUN')
class FontVerticalPrecisionShaping(unittest.TestCase):
    def test_actual_HarfBuzz_all_authored_kinds_and_six_UPEM_families(self):
        for kind in ('even', 'odd_width', 'odd_delta'):
            for upem in precision.SOURCE_UPEMS:
                with self.subTest(kind=kind, upem=upem):
                    measured = precision.measure_control(kind, upem, 8)
                    counts, errors = measured['counts'], measured['maximum_error_source_font_units']
                    self.assertEqual(counts['layout_glyphs'], 72)
                    self.assertEqual(counts['horizontal_identity_checks'], 18)
                    self.assertEqual(counts['scaled_above_1_over_32'], 0)
                    self.assertLessEqual(errors['scaled_layout'], 1/32)
                    self.assertGreater(counts['unscaled_above_1_over_32'], 0)
                    self.assertGreater(counts['raw_metric_changes'], 0)
                    self.assertGreater(errors['retained_raw_advance_change'], 1/32)
                    self.assertFalse(measured['universal_layout_acceptance'])
                    for platform in ('CoreText', 'DirectWrite', 'Windows11', 'Qt_Swirl', 'original_conversion'):
                        self.assertEqual(measured[platform], 'NOT_RUN')
                    if kind == 'even':
                        self.assertEqual(measured['unscaled_fractional_encoder_rejections_retained'], [])
                    else:
                        self.assertTrue(measured['unscaled_fractional_encoder_rejections_retained'])

    def test_saved_control_is_reopenable_and_previous_output_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/'fresh'
            result = precision.write_control(output, 'odd_width', 1144, 8)
            self.assertEqual(json.loads((output/'summary.json').read_text()), result)
            source = (output/'authored-source.ttf').read_bytes()
            candidate = (output/'authored-scaled-gpos.ttf').read_bytes()
            self.assertEqual(precision.verify_physical_tables(source, candidate, 8)['glyphs'], 8)
            before = {p.name: p.read_bytes() for p in output.iterdir()}
            with self.assertRaisesRegex(ValueError, 'fresh_control_output_required'):
                precision.write_control(output, 'even')
            self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})


if __name__ == '__main__':
    unittest.main()
