"""Regress C1's retained GDEF/avar counterexample at the production boundary.

All fonts here are the existing self-authored analytic fixture. This does not
exercise an Apple font or establish native source equivalence. The indirect
GPOS reference follows C1's documented reproducer; no C1 engine is duplicated.
"""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTCollection, newTable
from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import buildVarDevTable
from fontTools.varLib.varStore import OnlineVarStoreBuilder, VarStoreInstancer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import rebuild
from test_rebuild import AXES, write_fixture
from test_rebuild_pipeline import OriginalAnalyticOracle


def layout_fixture(path, variable):
    write_fixture(path)
    with TTCollection(path) as collection:
        font = collection.fonts[0]
        avar = newTable('avar')
        avar.majorVersion, avar.minorVersion = 1, 0
        avar.segments = {tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in AXES}
        avar.segments['wght'][.5] = .25
        font['avar'] = avar
        addOpenTypeFeaturesFromString(font,
            'languagesystem DFLT dflt; feature kern { pos A <0 0 -20 0>; } kern;')
        gdef = newTable('GDEF')
        gdef.table = otTables.GDEF()
        gdef.table.Version = 0x00010003 if variable else 0x00010000
        for field in ('GlyphClassDef', 'AttachList', 'LigCaretList', 'MarkAttachClassDef',
                      'MarkGlyphSetsDef', 'VarStore'):
            setattr(gdef.table, field, None)
        if variable:
            store = OnlineVarStoreBuilder(list(AXES))
            store.setSupports([{'wght': (0, 1, 1)}])
            index = store.storeDeltas([100])
            gdef.table.VarStore = store.finish()
            positioning = font['GPOS'].table.LookupList.Lookup[0].SubTable[0]
            positioning.Value.XAdvDevice = buildVarDevTable(index)
            positioning.ValueFormat |= 0x40
        font['GDEF'] = gdef
        collection.save(path)


class LayoutAdmissionTests(unittest.TestCase):
    def test_indirect_gpos_store_is_rejected_before_glyph_sampling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output, report = root/'input.ttc', root/'Swirl-VF.ttc', root/'report.json'
            layout_fixture(source, variable=True)
            before = source.read_bytes()
            oracle = OriginalAnalyticOracle(source)
            with mock.patch.object(rebuild, 'NativeOracle', return_value=oracle), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(rebuild.ReconstructionError, 'GDEF variable layout'):
                    rebuild.run(source, root/'analytic-oracle', output, report)
            self.assertEqual(oracle.requests, [])
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), before)
            saved = json.loads(report.read_text())
            self.assertEqual(saved['status'], 'BLOCKED')
            self.assertFalse(saved['output_generated'])
            self.assertEqual(saved['faces'], [])
            self.assertEqual(oracle.close_count, 1)

    def test_static_gdef_is_retained_and_still_admitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output, report = root/'input.ttc', root/'Swirl-VF.ttc', root/'report.json'
            layout_fixture(source, variable=False)
            before = source.read_bytes()
            oracle = OriginalAnalyticOracle(source)
            with mock.patch.object(rebuild, 'NativeOracle', return_value=oracle), \
                    contextlib.redirect_stderr(io.StringIO()):
                result = rebuild.run(source, root/'analytic-oracle', output, report)
            self.assertTrue(result['output_generated'])
            self.assertEqual(source.read_bytes(), before)
            with TTCollection(source) as left, TTCollection(output) as right:
                for tag in ('GDEF', 'GPOS'):
                    self.assertEqual(left.fonts[0].reader[tag], right.fonts[0].reader[tag])

    def test_nonidentity_avar_changes_the_indirect_layout_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'input.ttc'
            layout_fixture(source, variable=True)
            with TTCollection(source) as collection:
                font = collection.fonts[0]
                device = font['GPOS'].table.LookupList.Lookup[0].SubTable[0].Value.XAdvDevice
                index = device.StartSize << 16 | device.EndSize
                # User wght700 normalizes to .5; the retained source avar maps
                # that to .25. Changing only avar doubles this GPOS delta.
                for coordinate, delta in ((.25, 25), (.5, 50)):
                    self.assertEqual(VarStoreInstancer(font['GDEF'].table.VarStore,
                        font['fvar'].axes, {'wght': coordinate})[index], delta)


if __name__ == '__main__':
    unittest.main()
