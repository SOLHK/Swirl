"""Actual HarfBuzz outlines for an independently specified authored source."""
import itertools
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
import uharfbuzz as hb
from fontTools.ttLib import TTCollection
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'platform'),
             str(Path(__file__).resolve().parents[1]/'tools')]
from make_cff2_fixture import records, write_fixture, geometry, TAGS
from test_coretext_extract import make_fixture
from p7_validate_candidate import commands


def explicit_closures(source):
    """Add the implicit straight closing edge to the reference, without moving points."""
    result=[]; start=current=None
    for command in source:
        if command[0]=='moveTo':start=command[1:]
        if command[0]=='closePath':
            if current!=start:result.append(['lineTo',*start])
            start=current=None
        else:current=command[-2:]
        result.append(command)
    return result


class RampHarfBuzzTests(unittest.TestCase):
    def test_reopened_ramp_font_matches_independent_three_axis_source(self):
        self.verify_native('ramp')

    def test_reopened_compressed_hierarchical_font_matches_independent_source(self):
        self.verify_native('hierarchical')

    def verify_native(self, basis):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.ttc'; make_fixture(source)
            target=Path(tmp)/(basis+'.ttc');write_fixture(target,**{basis:True})
            points=np.r_[np.asarray(list(itertools.product((-1.,0.,1.),repeat=3))),
                         np.random.default_rng(885731).uniform(-1,1,(64,3))]
            blob=target.read_bytes(); observations=0
            with TTCollection(source) as original:
                for face,source_font in enumerate(original.fonts):
                    font=hb.Font(hb.Face(blob,face));hb.ot_font_set_funcs(font)
                    font.scale=(source_font['head'].unitsPerEm*64,)*2
                    for p in points:
                        user={a.axisTag:float(a.defaultValue+x*(a.defaultValue-a.minValue
                            if x<0 else a.maxValue-a.defaultValue)) for a,x in zip(source_font['fvar'].axes,p)}
                        font.set_variations(user)
                        for gid,name in enumerate(source_font.getGlyphOrder()):
                            expected=geometry.operands(explicit_closures(records(source_font,name,
                                [dict(zip(TAGS,map(float,p)))],.25,nonlinear=True)[0]))
                            actual=geometry.operands(commands(font,gid))
                            self.assertEqual(actual[0],expected[0])
                            error=np.linalg.norm(geometry.control_points(*actual)-
                                geometry.control_points(*expected),axis=1).max(initial=0)
                            self.assertLessEqual(error,1/32)
                            observations+=1
            self.assertEqual(observations,546)

    def test_reference_closure_adds_only_the_missing_straight_edge(self):
        curve=[['moveTo',0,0],['curveTo',1,2,3,4,0,0],['closePath']]
        self.assertEqual(explicit_closures(curve),curve)
        line=[['moveTo',0,0],['lineTo',1e-12,0],['closePath']]
        self.assertEqual(explicit_closures(line),line[:-1]+[['lineTo',0,0],['closePath']])
