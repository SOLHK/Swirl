"""The Qt manifest must use source geometry, never echo its target output."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
from fontTools.ttLib import TTCollection
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'platform'),
             str(Path(__file__).resolve().parents[1]/'tools')]
from make_qt_cff2_manifest import write
import cff2_geometry as geometry
from piecewise_geometry import point_errors


class QtManifestTests(unittest.TestCase):
    def test_source_reference_identity_coordinate_transport_and_independent_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'control';manifest=write(folder);path=folder/'hierarchical.ttc'
            self.assertEqual(manifest,json.loads((folder/'manifest.json').read_text()))
            self.assertEqual(manifest['font_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            observations=0;maximum=0.
            with TTCollection(path) as c:
                for font,face in zip(c.fonts,manifest['faces']):
                    self.assertEqual(face['cff2_sha256'],hashlib.sha256(font.reader['CFF2']).hexdigest())
                    self.assertEqual(len(face['cases']),91)
                    locations=set()
                    for i,case in enumerate(face['cases']):
                        key=tuple(case['normalized'][a.axisTag] for a in font['fvar'].axes)
                        locations.add(key)
                        if i>=27:self.assertFalse(all(x*4==int(x*4) for x in key))
                        for a,x in zip(font['fvar'].axes,key):
                            user=case['user'][a.axisTag]
                            self.assertEqual((user-a.defaultValue)/(a.defaultValue-a.minValue if x<0
                                             else a.maxValue-a.defaultValue),x)
                        glyphs=font.getGlyphSet(location=case['normalized'],normalized=True)
                        for row in case['glyphs']:
                            name=font.getGlyphOrder()[row['gid']]
                            ops,actual=geometry.operands(geometry.source_commands(glyphs[name]))
                            wanted_ops,wanted=geometry.operands(row['commands'])
                            self.assertEqual(ops,wanted_ops)
                            error=float(point_errors(actual[None],wanted[None])[0])
                            self.assertLessEqual(error,1/32)
                            maximum=max(maximum,error);observations+=1
                    self.assertEqual(len(locations),91)
            self.assertEqual(observations,546)
            # A nonzero approximation difference demonstrates that the
            # reference is not copied from the compressed target's contours.
            self.assertGreater(maximum,1/65536)
