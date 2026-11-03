"""Lossless sharing must preserve serialized/native arithmetic and limits."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTCollection,TTFont
from fontTools.misc.psCharStrings import T2CharString
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'tools'),str(Path(__file__).resolve().parents[1]/'platform')]
from cff2_structure import tokens,programs,bytecode
from cff2_structural_pool import candidates,rewrite,expand_local,compress
from probe_polynomial_clamp import build_control
from test_coretext_extract import make_fixture
from p7_validate_candidate import commands


class StructuralPoolTests(unittest.TestCase):
    def test_pattern_bytes_inside_fixed_numbers_are_not_instructions(self):
        data=b'\xff\x00\x8b\x8c\x10'+bytes((139,))*9+bytes((140,16))
        spans=list(candidates(data));self.assertTrue(all(a>=5 for a,b in spans))
        selected={data[5:]:0};changed,count=rewrite(data,selected)
        self.assertEqual(count,1);self.assertEqual(expand_local(changed,[data[5:]]),data)
        for bad in (b'\xff\x00',b'\x0c\x01',b'\xf7'):
            with self.assertRaises(ValueError):list(tokens(bad))

    def test_serialized_shared_local_helpers_keep_native_results_bit_identical(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'fixture.ttc';make_fixture(path)
            with TTCollection(path) as collection:font,_=build_control(collection.fonts[0],share_expressions=True)
            before=io.BytesIO();font.save(before)
            with TTFont(io.BytesIO(before.getvalue())) as font:
                original={(kind,str(key)):bytecode(cs) for kind,key,cs in programs(font)}
                proof=compress(font);self.assertGreater(proof['local_helpers'],0)
                after=io.BytesIO();font.save(after)
            self.assertLess(len(after.getvalue()),len(before.getvalue()))
            with TTFont(io.BytesIO(after.getvalue())) as saved:
                top=saved['CFF2'].cff.topDictIndex[0]
                helpers=[bytecode(cs) for cs in top.FDArray[0].Private.Subrs]
                for kind,key,cs in programs(saved):
                    if kind!='local':self.assertEqual(expand_local(bytecode(cs),helpers),original[kind,str(key)])
                engines=[hb.Font(hb.Face(data)) for data in (before.getvalue(),after.getvalue())]
                for engine in engines:hb.ot_font_set_funcs(engine);engine.scale=(64000,64000)
                for p in np.random.default_rng(2026110601).uniform(-1,1,(83,3)):
                    location={a.axisTag:a.defaultValue+q*(a.defaultValue-a.minValue if q<0 else a.maxValue-a.defaultValue)
                              for a,q in zip(saved['fvar'].axes,p)}
                    outlines=[]
                    for engine in engines:
                        engine.set_variations(location);buffer=hb.Buffer();buffer.add_str('A');buffer.guess_segment_properties();hb.shape(engine,buffer)
                        outlines.append(commands(engine,buffer.glyph_infos[0].codepoint))
                    self.assertEqual(outlines[0],outlines[1])
            with TTFont(io.BytesIO(before.getvalue())) as rejected:
                unchanged={(k,str(i)):bytecode(cs) for k,i,cs in programs(rejected)}
                with self.assertRaisesRegex(ValueError,'operation_limit'):compress(rejected,operation_limit=20)
                self.assertEqual(unchanged,{(k,str(i)):bytecode(cs) for k,i,cs in programs(rejected)})


if __name__=='__main__':unittest.main()
