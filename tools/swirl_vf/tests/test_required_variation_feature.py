"""Required GSUB routing must survive serialization and cannot replace another requirement."""
import io
from pathlib import Path
import sys,tempfile,unittest
from fontTools.ttLib import TTCollection,TTFont
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'tools'),str(Path(__file__).resolve().parents[1]/'platform')]
from required_variation_feature import require_feature
from probe_polynomial_clamp import build_control
from test_coretext_extract import make_fixture


class RequiredFeatureTests(unittest.TestCase):
    def test_required_index_roundtrip_and_conflicting_required_feature(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'fixture.ttc';make_fixture(path)
            with TTCollection(path) as fonts:font,_=build_control(fonts.fonts[0])
            require_feature(font);out=io.BytesIO();font.save(out)
            with TTFont(io.BytesIO(out.getvalue())) as saved:
                table=saved['GSUB'].table
                language=table.ScriptList.ScriptRecord[0].Script.DefaultLangSys
                self.assertEqual(table.FeatureList.FeatureRecord[language.ReqFeatureIndex].FeatureTag,'rvrn')
                self.assertNotIn(language.ReqFeatureIndex,language.FeatureIndex)
                language.ReqFeatureIndex=123
                with self.assertRaisesRegex(ValueError,'conflict'):require_feature(saved)
                self.assertEqual(language.ReqFeatureIndex,123)


if __name__=='__main__':unittest.main()
