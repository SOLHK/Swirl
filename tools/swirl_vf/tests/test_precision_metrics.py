"""Authored metric records; source identity and per-tag units stay separate."""
import io
from pathlib import Path
import sys
import unittest

from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.ttLib.tables import otTables
from fontTools.varLib.varStore import OnlineVarStoreBuilder, VarStoreInstancer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(ROOT/'platform'))
from precision_metrics import (DESIGN_UNIT_MVAR_TAGS, DIMENSIONLESS_MVAR_TAGS,
    PPEM_MVAR_TAGS, PrecisionMetricError, scale_with_precision_metrics)
from experiment_vertical_gpos import original_fixture, serialize


def authored_font(deltas=None, *, vorg=True):
    font = TTFont(io.BytesIO(original_fixture()[0]), recalcTimestamp=False)
    for tag in ('hhea', 'vhea'):
        font[tag].caretSlopeRise = 1
        font[tag].caretSlopeRun = 0
        font[tag].caretOffset = 3 if tag == 'hhea' else -4
    if deltas is not None:
        builder = OnlineVarStoreBuilder([a.axisTag for a in font['fvar'].axes])
        builder.setSupports([{'wght': (0, 1, 1)}])
        records = []
        for tag, delta in sorted(deltas.items()):
            record = otTables.MetricsValueRecord()
            record.ValueTag = tag
            record.VarIdx = builder.storeDeltas([delta])
            record.MoreBytes = []
            records.append(record)
        wrapper = newTable('MVAR')
        table = wrapper.table = otTables.MVAR()
        table.Version, table.Reserved = 0x10000, 0
        table.ValueRecordSize, table.ValueRecordCount = 8, len(records)
        table.ValueRecord, table.VarStore = records, builder.finish()
        font['MVAR'] = wrapper
        if PPEM_MVAR_TAGS & set(deltas):
            gasp = newTable('gasp'); gasp.version = 1
            gasp.gaspRange = {**{10+i: 15 for i in range(10)}, 0xFFFF: 15}
            font['gasp'] = gasp
    if vorg:
        table = newTable('VORG')
        table.majorVersion, table.minorVersion = 1, 0
        table.defaultVertOriginY = 860
        table.VOriginRecords = {'latinA': 877, 'latinB': -14}
        font['VORG'] = table
    return font


def deltas_at(font, coordinate=.5):
    table = font['MVAR'].table
    instancer = VarStoreInstancer(table.VarStore, font['fvar'].axes,
                                 {'WDTH': 0, 'wght': coordinate, 'HGHT': 0})
    return {r.ValueTag: instancer[r.VarIdx] for r in table.ValueRecord}


class PrecisionMetricsTests(unittest.TestCase):
    def test_caret_ratio_counterexample_is_repaired_without_changing_source(self):
        font = authored_font({'hcrn': 2}, vorg=False)
        before = serialize(font)
        generic = TTFont(io.BytesIO(before), recalcTimestamp=False)
        scale_upem(generic, 8000)
        ratio = lambda f: f['hhea'].caretSlopeRise / (f['hhea'].caretSlopeRun+deltas_at(f)['hcrn'])
        self.assertEqual(ratio(font), 1.)
        self.assertEqual(ratio(generic), .125)  # Retain the original bad behavior.
        candidate = scale_with_precision_metrics(font, 8000)
        self.assertEqual(ratio(candidate), 1.)
        self.assertEqual(candidate['hhea'].caretSlopeRise, 1)
        self.assertEqual(candidate['hhea'].caretSlopeRun, 0)
        self.assertEqual(serialize(font), before)

    def test_all_standard_MVAR_tags_keep_their_declared_units(self):
        tags = DESIGN_UNIT_MVAR_TAGS | DIMENSIONLESS_MVAR_TAGS | PPEM_MVAR_TAGS
        font = authored_font({tag: 2 for tag in tags})
        before = serialize(font)
        candidate = scale_with_precision_metrics(font, 8000)
        measured = deltas_at(candidate)
        for tag in tags:
            self.assertEqual(measured[tag], 8 if tag in DESIGN_UNIT_MVAR_TAGS else 1, tag)
        for table in ('hhea', 'vhea'):
            self.assertEqual(candidate[table].caretSlopeRise, font[table].caretSlopeRise)
            self.assertEqual(candidate[table].caretSlopeRun, font[table].caretSlopeRun)
        self.assertEqual(candidate['hhea'].caretOffset, font['hhea'].caretOffset*8)
        self.assertEqual(candidate['vhea'].caretOffset, font['vhea'].caretOffset*8)
        self.assertEqual(candidate.getTableData('gasp'), font.getTableData('gasp'))
        self.assertEqual(candidate['OS/2'].sTypoAscender, font['OS/2'].sTypoAscender*8)
        self.assertEqual(serialize(font), before)

    def test_alias_row_is_split_between_design_units_and_caret_ratio(self):
        font = authored_font({'hasc': 2, 'hcrn': 2, 'hcrs': 2})
        records = font['MVAR'].table.ValueRecord
        self.assertEqual(len({r.VarIdx for r in records}), 1)
        before = serialize(font)
        candidate = scale_with_precision_metrics(font, 8000)
        records = {r.ValueTag: r.VarIdx for r in candidate['MVAR'].table.ValueRecord}
        self.assertNotEqual(records['hasc'], records['hcrn'])
        self.assertEqual(records['hcrn'], records['hcrs'])
        self.assertEqual(deltas_at(candidate), {'hasc': 8., 'hcrn': 1., 'hcrs': 1.})
        self.assertEqual(serialize(font), before)

    def test_VORG_default_and_every_override_scale_after_roundtrip(self):
        font = authored_font({'hasc': 2})
        before = serialize(font)
        candidate = scale_with_precision_metrics(font, 8000)
        self.assertEqual(candidate['VORG'].defaultVertOriginY, 6880)
        self.assertEqual(candidate['VORG'].VOriginRecords, {'latinA': 7016, 'latinB': -112})
        self.assertEqual(candidate['VORG']['han'], 6880)
        self.assertEqual(serialize(font), before)

    def test_unknown_private_and_unsupported_MVAR_versions_fail_with_source_unchanged(self):
        for tag in ('TEST', 'zzzz'):
            font = authored_font({tag: 2})
            before = serialize(font)
            with self.subTest(tag=tag), self.assertRaisesRegex(PrecisionMetricError, 'unknown_or_private'):
                scale_with_precision_metrics(font, 8000)
            self.assertEqual(serialize(font), before)
        font = authored_font({'hasc': 2})
        font['MVAR'].table.Version = 0x10001
        before = serialize(font)
        with self.assertRaisesRegex(PrecisionMetricError, 'unsupported_precision_MVAR'):
            scale_with_precision_metrics(font, 8000)
        self.assertEqual(serialize(font), before)

    def test_VORG_overflow_and_bad_version_fail_before_mutating_source(self):
        for field in ('default', 'record', 'version'):
            font = authored_font()
            if field == 'default':
                font['VORG'].defaultVertOriginY = 10000
            elif field == 'record':
                font['VORG'].VOriginRecords['latinA'] = -10000
            else:
                font['VORG'].minorVersion = 1
            before = serialize(font)
            with self.subTest(field=field), self.assertRaises(PrecisionMetricError):
                scale_with_precision_metrics(font, 8000)
            self.assertEqual(serialize(font), before)

    def test_missing_optional_tables_and_invalid_target_UPEMs(self):
        font = authored_font(vorg=False)
        candidate = scale_with_precision_metrics(font, 8000)
        self.assertNotIn('MVAR', candidate)
        self.assertNotIn('VORG', candidate)
        self.assertEqual(candidate.getTableData('fvar'), font.getTableData('fvar'))
        for value in (True, 8000., 15, 16385):
            with self.subTest(value=value), self.assertRaises(PrecisionMetricError):
                scale_with_precision_metrics(font, value)

    def test_gasp_requires_existing_nonterminal_range_and_infinity_sentinel(self):
        for case in ('missing', 'out_of_range', 'last_record', 'no_sentinel'):
            font = authored_font({'gsp9' if case == 'out_of_range' else 'gsp1': 2})
            if case == 'missing':
                del font['gasp']
            elif case in ('out_of_range', 'last_record'):
                font['gasp'].gaspRange = {10: 15, 0xFFFF: 15}
            else:
                font['gasp'].gaspRange = {10: 15, 20: 15}
            before = serialize(font)
            with self.subTest(case=case), self.assertRaisesRegex(PrecisionMetricError, 'precision_MVAR_gasp_'):
                scale_with_precision_metrics(font, 8000)
            self.assertEqual(serialize(font), before)

    def test_registered_MVAR_tag_needs_its_actual_base_table_and_field(self):
        font = authored_font({'hasc': 2})
        del font['OS/2']
        before = serialize(font)
        with self.assertRaisesRegex(PrecisionMetricError, 'precision_MVAR_target_missing:OS/2.sTypoAscender'):
            scale_with_precision_metrics(font, 8000)
        self.assertEqual(serialize(font), before)
        font = authored_font({'hcrn': 2})
        del font['hhea'].caretSlopeRun
        with self.assertRaisesRegex(PrecisionMetricError, 'precision_MVAR_target_missing:hhea.caretSlopeRun'):
            scale_with_precision_metrics(font, 8000)
        self.assertFalse(hasattr(font['hhea'], 'caretSlopeRun'))

    def test_invalid_variation_index_and_duplicate_tags_remain_rejected(self):
        font = authored_font({'hasc': 2})
        font['MVAR'].table.ValueRecord[0].VarIdx = 0xFFFF0000
        before = serialize(font)
        with self.assertRaisesRegex(PrecisionMetricError, 'outer_index'):
            scale_with_precision_metrics(font, 8000)
        self.assertEqual(serialize(font), before)
        font = authored_font({'hasc': 2, 'hcrn': 2})
        font['MVAR'].table.ValueRecord[1].ValueTag = 'hasc'
        before = serialize(font)
        with self.assertRaisesRegex(PrecisionMetricError, 'not_unique_sorted'):
            scale_with_precision_metrics(font, 8000)
        self.assertEqual(serialize(font), before)


if __name__ == '__main__':
    unittest.main()
