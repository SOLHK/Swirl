"""Authored protocol/coordinate counterexamples, not Windows native evidence."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

from fontTools.ttLib import TTCollection

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from make_cff2_fixture import geometry, records
from test_coretext_extract import make_fixture
from verify_cff2_directwrite_geometry import compare


class DirectWriteGeometryValidationTests(unittest.TestCase):
    def test_screen_coordinates_require_explicit_y_inversion_and_matching_axes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'authored.ttc';make_fixture(path)
            with TTCollection(path) as original:
                for font in original.fonts:
                    for p in ({'WDTH':-1.,'wght':0.,'HGHT':1.},
                              {'WDTH':.25,'wght':-.5,'HGHT':.75}):
                        user={a.axisTag:a.defaultValue+p[a.axisTag]*(a.maxValue-a.defaultValue if
                            p[a.axisTag]>=0 else a.defaultValue-a.minValue) for a in font['fvar'].axes}
                        for gid,name in enumerate(font.getGlyphOrder()):
                            # Elevate through a CharString pen independently of
                            # the validator's coordinate-system adapter.
                            commands=records(font,name,[p],.25)[0]
                            for command in commands:
                                for i in range(2,len(command),2):command[i]=-command[i]
                            row={'record':'outline','coordinate_frame':'x_right_y_down_font_units',
                                 'glyph_id':gid,'upm':font['head'].unitsPerEm,'axes':user,'commands':commands}
                            self.assertTrue(compare(row,font)['passed'])
                            bad=copy.deepcopy(row);bad['coordinate_frame']='unknown'
                            with self.assertRaisesRegex(ValueError,'frame_not_proven'):compare(bad,font)
                            if commands:
                                bad=copy.deepcopy(row)
                                for command in bad['commands']:
                                    for i in range(1,len(command),2):command[i]+=.125
                                self.assertFalse(compare(bad,font)['passed'])

    def test_missing_path_and_invalid_numeric_input_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'authored.ttc';make_fixture(path)
            with TTCollection(path) as original:
                font=original.fonts[0]
                row={'record':'outline','coordinate_frame':'x_right_y_down_font_units',
                     'glyph_id':2,'upm':1000,'axes':{'WDTH':500.,'wght':400.,'HGHT':500.},'commands':[]}
                self.assertFalse(compare(row,font)['passed'])
                row['axes']['WDTH']=float('nan')
                with self.assertRaisesRegex(ValueError,'invalid_native_outline_axis_value'):compare(row,font)
                row['axes']['WDTH']=500.;row['axes']['wdth']=500.
                with self.assertRaisesRegex(ValueError,'axis_set_changed'):compare(row,font)
