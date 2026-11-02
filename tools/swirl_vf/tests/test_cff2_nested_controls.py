"""Independent equality checks for native nested-blend diagnostic controls."""
import copy
import io
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from fontTools.ttLib import TTCollection, TTFont

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'platform'),
               str(Path(__file__).resolve().parents[1] / 'tools')]
from make_cff2_fixture import write_fixture, GRID, HOLDOUTS
from diagnose_cff2_directwrite import nest_identity_blends
import cff2_geometry as geometry


class CFF2NestedControlTests(unittest.TestCase):
    def test_identity_nesting_preserves_serialized_geometry_and_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'authored.ttc'; write_fixture(path)
            with TTCollection(path) as collection:
                for source in collection.fonts:
                    for mode in ('nested_default', 'nested_delta', 'nested_delta_sparse'):
                        font = copy.deepcopy(source)
                        nest_identity_blends(font['CFF2'].cff.topDictIndex[0], mode)
                        stream = io.BytesIO(); font.save(stream)
                        with TTFont(io.BytesIO(stream.getvalue())) as actual:
                            for tag in ('fvar', 'avar', 'hmtx', 'vmtx', 'HVAR', 'VVAR', 'cmap'):
                                self.assertEqual(actual.getTableData(tag), source.getTableData(tag))
                            for p in GRID + HOLDOUTS:
                                for name in source.getGlyphOrder():
                                    a = geometry.operands(geometry.source_commands(actual.getGlyphSet(
                                        location=p, normalized=True)[name]))
                                    b = geometry.operands(geometry.source_commands(source.getGlyphSet(
                                        location=p, normalized=True)[name]))
                                    self.assertEqual(a[0], b[0])
                                    np.testing.assert_allclose(geometry.control_points(*a),
                                                               geometry.control_points(*b), rtol=0, atol=1e-10)

    def test_unknown_variant_does_not_mutate_charstrings(self):
        with self.assertRaisesRegex(ValueError, 'unknown_nested_identity_control'):
            nest_identity_blends(None, 'unsupported')
