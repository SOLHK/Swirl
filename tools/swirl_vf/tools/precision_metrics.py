"""Scale a candidate copy with tag-aware MVAR and complete VORG handling.

The fontTools UPEM scaler handles standard geometry/layout tables, but its
generic VarData visitor cannot distinguish MVAR design-unit deltas from caret
ratios or gasp PPEM values. A shared MVAR row may even serve both kinds. This
helper detaches MVAR before calling that scaler, restores a tag-aware copy,
and explicitly scales every VORG record as well as its default. It returns a
serialized, reopened copy; it never edits the source or grants acceptance.

References read before implementation:
https://learn.microsoft.com/en-us/typography/opentype/spec/mvar
https://learn.microsoft.com/en-us/typography/opentype/spec/vorg
https://fonttools.readthedocs.io/en/stable/ttLib/scaleUpem.html

This does not add VORG support to TrueType consumers: the specification tells
them to ignore VORG. The caller must separately establish supported tables,
axis/outline identity, and platform behavior for the candidate.
"""
from __future__ import annotations

import copy
import io
from fractions import Fraction

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.varLib.builder import buildVarData
from fontTools.varLib.mvar import MVAR_ENTRIES


DESIGN_UNIT_MVAR_TAGS = frozenset('''
    hasc hdsc hlgp hcla hcld vasc vdsc vlgp hcof vcof xhgt cpht
    sbxs sbys sbxo sbyo spxs spys spxo spyo strs stro unds undo
'''.split())
DIMENSIONLESS_MVAR_TAGS = frozenset(('hcrs', 'hcrn', 'vcrs', 'vcrn'))
PPEM_MVAR_TAGS = frozenset(f'gsp{i}' for i in range(10))
UNSCALED_MVAR_TAGS = DIMENSIONLESS_MVAR_TAGS | PPEM_MVAR_TAGS
NO_VARIATION_INDEX = 0xFFFFFFFF


class PrecisionMetricError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise PrecisionMetricError(message)


def _integer(value, minimum, maximum, message):
    _require(type(value) is int and minimum <= value <= maximum, message)


def _mvar_records(font):
    """Validate tag semantics and every referenced delta before any scaling."""
    if 'MVAR' not in font:
        return []
    table = font['MVAR'].table
    _require(table.Version == 0x00010000 and table.Reserved == 0
             and table.ValueRecordSize == 8, 'unsupported_precision_MVAR_header')
    records = table.ValueRecord
    _require(table.ValueRecordCount == len(records), 'precision_MVAR_record_count_differs')
    tags = [r.ValueTag for r in records]
    _require(tags == sorted(tags) and len(tags) == len(set(tags)), 'precision_MVAR_tags_not_unique_sorted')
    _require('fvar' in font, 'precision_MVAR_requires_fvar')
    axes = font['fvar'].axes
    _require(len({a.axisTag for a in axes}) == len(axes), 'precision_MVAR_duplicate_axis')
    store = table.VarStore
    if not records:
        return records
    _require(store is not None and store.Format == 1
             and store.VarRegionList.RegionAxisCount == len(axes), 'precision_MVAR_store_axis_count_differs')
    _require(store.VarDataCount == len(store.VarData)
             and store.VarRegionList.RegionCount == len(store.VarRegionList.Region),
             'precision_MVAR_store_count_differs')
    for record in records:
        _require(record.ValueTag in DESIGN_UNIT_MVAR_TAGS | UNSCALED_MVAR_TAGS,
                 f'unknown_or_private_precision_MVAR_tag:{record.ValueTag}')
        if record.ValueTag in PPEM_MVAR_TAGS:
            _require('gasp' in font, 'precision_MVAR_gasp_target_missing')
            gasp = font['gasp']
            _require(gasp.version in (0, 1), 'precision_MVAR_gasp_version_unsupported')
            ranges = sorted(gasp.gaspRange)
            _require(ranges and all(type(v) is int and 0 <= v <= 65535 for v in ranges)
                     and ranges[-1] == 65535, 'precision_MVAR_gasp_final_sentinel_missing')
            # The terminal 0xFFFF record means infinity and must never vary.
            # gsp0..gsp9 reference ordered array positions, not PPEM key values.
            _require(int(record.ValueTag[-1]) < len(ranges)-1,
                     'precision_MVAR_gasp_reference_outside_adjustable_ranges')
        else:
            target, field = MVAR_ENTRIES[record.ValueTag]
            _require(target in font and hasattr(font[target], field),
                     f'precision_MVAR_target_missing:{target}.{field}')
        _integer(record.VarIdx, 0, NO_VARIATION_INDEX, 'precision_MVAR_invalid_index')
        if record.VarIdx == NO_VARIATION_INDEX:
            continue
        outer, inner = record.VarIdx >> 16, record.VarIdx & 65535
        _require(outer < len(store.VarData), 'precision_MVAR_outer_index_out_of_range')
        data = store.VarData[outer]
        _require(data.ItemCount == len(data.Item) and inner < len(data.Item),
                 'precision_MVAR_inner_index_out_of_range')
        _require(data.VarRegionCount == len(data.VarRegionIndex)
                 and len(data.Item[inner]) == data.VarRegionCount
                 and all(type(i) is int and 0 <= i < len(store.VarRegionList.Region)
                         for i in data.VarRegionIndex), 'precision_MVAR_delta_region_count_differs')
        for delta in data.Item[inner]:
            _integer(delta, -(1 << 31), (1 << 31)-1, 'precision_MVAR_invalid_delta')
    return records


def _vorg_values(font, factor):
    if 'VORG' not in font:
        return None
    table = font['VORG']
    _require((table.majorVersion, table.minorVersion) == (1, 0), 'unsupported_precision_VORG_version')
    order = set(font.getGlyphOrder())
    _require(set(table.VOriginRecords) <= order, 'precision_VORG_unknown_glyph')
    values = [table.defaultVertOriginY, *table.VOriginRecords.values()]
    for value in values:
        _integer(value, -32768, 32767, 'precision_VORG_invalid_design_value')
        _integer(otRound(value*factor), -32768, 32767, 'precision_VORG_scaled_value_overflow')
    return (otRound(table.defaultVertOriginY*factor),
            {name: otRound(value*factor) for name, value in table.VOriginRecords.items()})


def _scaled_mvar(original, factor):
    result = copy.deepcopy(original)
    table, source_table = result.table, original.table
    scaled = {r.VarIdx for r in source_table.ValueRecord
              if r.ValueTag in DESIGN_UNIT_MVAR_TAGS and r.VarIdx != NO_VARIATION_INDEX}
    unchanged = {r.VarIdx for r in source_table.ValueRecord if r.ValueTag in UNSCALED_MVAR_TAGS}
    remap = {}
    for index in sorted(scaled):
        outer, inner = index >> 16, index & 65535
        data = table.VarStore.VarData[outer]
        row = [otRound(v*factor) for v in source_table.VarStore.VarData[outer].Item[inner]]
        for value in row:
            _integer(value, -(1 << 31), (1 << 31)-1, 'precision_MVAR_scaled_delta_overflow')
        if index in unchanged:
            # A single source row may feed both 'hasc' and 'hcrn'. Scaling that
            # row in place would change the caret ratio. Keep its old index and
            # allocate a separate design-unit row, remapping only those tags.
            if len(data.Item) < 65535:
                remap[index] = (outer << 16) | len(data.Item)
                data.Item.append(row)
            else:
                _require(len(table.VarStore.VarData) < 65535, 'precision_MVAR_no_room_for_split_row')
                remap[index] = len(table.VarStore.VarData) << 16
                table.VarStore.VarData.append(buildVarData(data.VarRegionIndex, [row], optimize=False))
        else:
            data.Item[inner] = row
    for record in table.ValueRecord:
        if record.ValueTag in DESIGN_UNIT_MVAR_TAGS:
            record.VarIdx = remap.get(record.VarIdx, record.VarIdx)
    if table.VarStore is not None:
        table.VarStore.VarDataCount = len(table.VarStore.VarData)
        for data in table.VarStore.VarData:
            data.ItemCount = len(data.Item)
            data.calculateNumShorts()
    return result


def scale_with_precision_metrics(source_font, new_upem):
    """Return a scaled, serialized/reopened TTFont copy; never publish or mutate.

    Known MVAR design-unit tags scale with UPEM. Caret slope rise/run and gasp
    PPEM deltas keep their original units. Unknown/private tags are rejected
    rather than assigned invented units. Fractional design values use the same
    OpenType rounding convention as fontTools.scale_upem.
    """
    _integer(new_upem, 16, 16384, 'precision_target_UPEM_out_of_range')
    old_upem = source_font['head'].unitsPerEm
    _integer(old_upem, 16, 16384, 'precision_source_UPEM_out_of_range')
    factor = Fraction(new_upem, old_upem)
    _mvar_records(source_font)
    vorg = _vorg_values(source_font, factor)
    original_mvar = source_font['MVAR'] if 'MVAR' in source_font else None
    mvar = _scaled_mvar(original_mvar, factor) if original_mvar is not None else None
    # Scale only a copy. The generic upstream VarData scaler never sees MVAR.
    candidate = copy.deepcopy(source_font)
    if 'MVAR' in candidate:
        del candidate['MVAR']
    scale_upem(candidate, new_upem)
    if mvar is not None:
        candidate['MVAR'] = mvar
    if vorg is not None:
        candidate['VORG'].defaultVertOriginY, candidate['VORG'].VOriginRecords = vorg
    # These values define dimensionless slope ratios, not design-grid lengths.
    for tag in ('hhea', 'vhea'):
        if tag in source_font:
            for field in ('caretSlopeRise', 'caretSlopeRun'):
                _require(getattr(candidate[tag], field) == getattr(source_font[tag], field),
                         'precision_base_caret_slope_changed')
    candidate.recalcTimestamp = False
    stream = io.BytesIO()
    candidate.save(stream)
    reopened = TTFont(io.BytesIO(stream.getvalue()), recalcTimestamp=False)
    _mvar_records(reopened)
    _require(reopened['head'].unitsPerEm == new_upem, 'precision_serialized_UPEM_differs')
    return reopened
