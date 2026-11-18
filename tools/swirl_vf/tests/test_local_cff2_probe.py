import sys
from pathlib import Path
import unittest
import io
import tempfile
import numpy as np
from fontTools.ttLib import TTCollection, TTFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from probe_local_cff2_basis import native_plan, probe_models, geometry, prepare_from_truetype
from local_cff2_geometry import encode
from cff2_certificate import certify
from test_coretext_extract import make_fixture


class LocalNativePlanTests(unittest.TestCase):
    def test_fractional_native_plan_stays_in_declared_domain(self):
        profiles = [(1,500,1000),(100,400,900),(1,500,1000)]
        box = np.asarray([[.25,.26],[-.5,-.49],[-1.,-.99]])
        plan = native_plan(box,profiles,61173)
        self.assertEqual(plan,native_plan(box,profiles,61173))
        self.assertEqual(len(plan),len(set(plan)))
        self.assertGreaterEqual(len(plan),64)
        p=np.asarray([[(v-d)/(d-lo if v<d else hi-d) for v,(lo,d,hi) in zip(row,profiles)] for row in plan])
        self.assertTrue(((p>=box[:,0])&(p<=box[:,1])).all())
        self.assertTrue(np.equal(np.asarray(plan)*16,np.round(np.asarray(plan)*16)).all())

    def test_unrepresentable_box_is_rejected_without_substituting_a_point(self):
        with self.assertRaisesRegex(ValueError,'no_representable'):
            native_plan([[.0000001,.0000002]]*3,[(0,1,2)]*3,1)

    def test_blank_source_target_stays_empty_with_separate_authored_notdef(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source.ttc'; make_fixture(path)
            with TTCollection(path) as source:
                original = source.fonts[0]
                model = encode([np.array([-1.,0.,1.])]*3, np.zeros((3,3,3,0)), (),
                               ('WDTH','wght','HGHT'), basis='hierarchical')
                model.evidence['sampled_geometry_passed'] = True
                models = probe_models(original, model)
                self.assertIs(models['probe'], model)
                self.assertTrue(models['.notdef'].operators)
                candidate = geometry.install(prepare_from_truetype(original), models,
                                             experimental_local=True)
                data = io.BytesIO(); candidate.save(data)
            with TTFont(io.BytesIO(data.getvalue())) as saved:
                self.assertEqual(certify(saved,models)['glyphs'],3)
                for location in ({},{'WDTH':.25,'wght':-.75,'HGHT':1.}):
                    glyphs = saved.getGlyphSet(location=location, normalized=True)
                    self.assertEqual(geometry.source_commands(glyphs['probe']),[])
                    self.assertTrue(geometry.source_commands(glyphs['.notdef']))
