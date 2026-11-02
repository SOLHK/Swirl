"""Serialized GPOS equation and real HarfBuzz shaping, without native claims."""
import io
from pathlib import Path
import sys
import unittest

from fontTools.ttLib import TTFont
from fontTools.varLib.varStore import VarStoreInstancer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'platform'))
import experiment_vertical_advance as advance


class VerticalAdvanceTests(unittest.TestCase):
    def test_serialized_height_adjustment_preserves_all_original_metrics(self):
        original, symbols = advance.fixture.original_fixture()
        for route in advance.fixture.ROUTES:
            data = advance.candidate(original, symbols, route)
            with TTFont(io.BytesIO(data)) as font:
                sub = font['GPOS'].table.LookupList.Lookup[0].SubTable[0]
                self.assertEqual(sub.ValueFormat, 0x88)  # YAdvance + YAdvDevice only
                values = [sub.Value]*len(sub.Coverage.glyphs) if sub.Format==1 else sub.Value
                for point in advance.POINTS:
                    location = dict(zip((a[0] for a in advance.fixture.AXES),point))
                    store = VarStoreInstancer(font['GDEF'].table.VarStore,font['fvar'].axes,location)
                    for name,value in zip(sub.Coverage.glyphs,values):
                        device=value.YAdvDevice
                        actual=value.YAdvance + store[(device.StartSize<<16)|device.EndSize]
                        expected=advance.desired(symbols[font.getGlyphID(name)],point)
                        self.assertAlmostEqual(actual,expected,places=10)

    def test_actual_harfbuzz_vertical_layout_keeps_fractional_advance(self):
        try:
            import uharfbuzz
        except ImportError:
            self.skipTest('HarfBuzz unavailable; no native layout acceptance inferred')
        source,symbols=advance.fixture.original_fixture()
        result=advance.harfbuzz(source, {'vert':advance.candidate(source,symbols,'vert')}, symbols)
        active=result['groups']['vert/enabled/ttb']
        self.assertEqual(active['advance_change_minus_requested_model']['above_1_over_32'],0)
        self.assertGreater(active['advance_change']['max_abs_error'],100)
        self.assertEqual(result['groups']['vert/disabled/ttb']['advance_change']['max_abs_error'],0)
        self.assertEqual(result['groups']['vert/enabled/ltr']['advance_change']['max_abs_error'],0)
        for row in result['groups'].values():
            self.assertEqual(row['raw_metrics_change']['max_abs_error'],0)
