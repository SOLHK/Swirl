"""Independent HarfBuzz/serialization checks, not a native Windows verdict."""
import io,sys,unittest
from pathlib import Path
from fontTools.ttLib import TTFont
import uharfbuzz as hb
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
import probe_coupled_avar as probe
from experiment_vertical_gpos import requested_location


class CoupledAvarTests(unittest.TestCase):
    def test_coupling_is_discriminating_and_serializes_without_changing_other_tables(self):
        base,coupled=probe.build();a,b=TTFont(io.BytesIO(base)),TTFont(io.BytesIO(coupled))
        for tag in set(a.keys())-{'GlyphOrder','head'}:
            self.assertEqual(a.getTableData(tag),b.getTableData(tag))
        self.assertEqual(b['avar'].majorVersion,2)
        self.assertEqual(len(b.getGlyphOrder()),8)
        font=hb.Font(hb.Face(coupled));hb.ot_font_set_funcs(font);font.scale=(1000,1000)
        def width(font,gid):
            # get_glyph_extents rounds metrics; draw callbacks measure the
            # fractional CFF2 geometry that this capability test addresses.
            xs=[];draw=hb.DrawFuncs()
            draw.set_move_to_func(lambda x,y,*args:xs.append(x))
            draw.set_line_to_func(lambda x,y,*args:xs.append(x))
            font.draw_glyph(gid,draw)
            return max(xs)-min(xs)
        for q in probe.POINTS:
            font.set_variations(requested_location(q))
            for gid in (2,3):
                expected=(260-2*gid)*(1+(q[0]+q[2])/8)
                self.assertLessEqual(abs(width(font,gid)-expected),1/32)
        # If an engine ignores avar2 this point differs by 64 FUnits.
        font.set_variations(requested_location((-1.,0.,1.)))
        self.assertEqual(width(font,2),256)
        plain=hb.Font(hb.Face(base));hb.ot_font_set_funcs(plain);plain.scale=font.scale
        plain.set_variations(requested_location((-1.,0.,1.)))
        self.assertEqual(width(plain,2),192)


if __name__=='__main__':unittest.main()
