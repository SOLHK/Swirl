"""Rebase a standard design-q glyph font into a legal endpoint-r basis.

Uses fontTools' existing partial instancer to transform actual glyph/metric/
layout regions and coefficients, including supports whose old peak lies beyond
the used source interval. Merely renaming such regions gives wrong results.
Integer coefficient rounding is possible: no lossless/native/source acceptance
is granted, no production gate is changed, and no file is written here.

Reference: https://fonttools.readthedocs.io/en/latest/varLib/instancer.html
fontTools is MIT licensed; the public API is reused without copied code.
"""
from __future__ import annotations

import fontTools
import copy
from fontTools.varLib.instancer import instantiateVariableFont

from audit_font import raw_avar
from design_axis_basis import basis_from_axis, build_rebased_avar
from target_axis_mapping import SourceAxis


CUSTOM_TAGS = {'WDTH': 'XWDT', 'wght': 'XWGT', 'HGHT': 'XHGT'}
IDENTITY = {-1.: -1., 0.: 0., 1.: 1.}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _anchor_value(axis, basis, value):
    # Original named-instance coordinates cannot be recovered uniquely from
    # a stepped q mapping. Only these three known anchors are unambiguous.
    anchors = {basis.q_min / 16384: axis.minimum, 0.: axis.default,
               basis.q_max / 16384: axis.maximum}
    require(type(value) in (int, float) and value in anchors,
            'nonanchor_metadata_requires_original_source_coordinates')
    return anchors[value]


def _restore_metadata(font, axes, bases):
    by_custom = {CUSTOM_TAGS[axis.tag]: (axis, basis) for axis, basis in zip(axes, bases)}
    for instance in font['fvar'].instances:
        require(set(instance.coordinates) == set(by_custom), 'named_instance_axis_set_changed')
        instance.coordinates = {by_custom[tag][0].tag: _anchor_value(*by_custom[tag], value)
                                for tag, value in instance.coordinates.items()}
    if 'STAT' not in font:
        return
    stat = font['STAT'].table
    records = getattr(getattr(stat, 'DesignAxisRecord', None), 'Axis', [])
    require(all(record.AxisTag in by_custom for record in records), 'unsupported_STAT_axis')
    axis_values = getattr(getattr(stat, 'AxisValueArray', None), 'AxisValue', [])
    for value in axis_values:
        if value.Format == 4:
            items = [(row.AxisIndex, row, ('Value',)) for row in value.AxisValueRecord]
        else:
            fields = {1: ('Value',), 2: ('NominalValue', 'RangeMinValue', 'RangeMaxValue'),
                      3: ('Value', 'LinkedValue')}
            require(value.Format in fields, 'unsupported_STAT_value_format')
            items = [(value.AxisIndex, value, fields[value.Format])]
        for index, record, fields in items:
            require(type(index) is int and 0 <= index < len(records), 'invalid_STAT_axis_index')
            axis, basis = by_custom[records[index].AxisTag]
            for field in fields:
                setattr(record, field, _anchor_value(axis, basis, getattr(record, field)))
    for record in records:
        record.AxisTag = by_custom[record.AxisTag][0].tag


def rebase_design_font(font, source_axes):
    """Return a distinct TTFont candidate and a non-acceptance report."""
    require(type(source_axes) in (tuple, list) and len(source_axes) == 3
            and all(isinstance(axis, SourceAxis) for axis in source_axes)
            and {axis.tag for axis in source_axes} == set(CUSTOM_TAGS), 'three_raw_source_axes_required')
    require(not any(str(tag).lower() in ('hvgl', 'hvpm') for tag in font.keys()),
            'standard_q_font_required_no_proprietary_tables')
    require(all(tag in font for tag in ('glyf', 'gvar', 'fvar', 'avar', 'head', 'hmtx', 'maxp', 'cmap')),
            'standard_q_variable_font_tables_required')
    custom_order = [CUSTOM_TAGS[axis.tag] for axis in source_axes]
    require([axis.axisTag for axis in font['fvar'].axes] == custom_order
            and all((axis.minValue, axis.defaultValue, axis.maxValue) == (-1., 0., 1.)
                    for axis in font['fvar'].axes), 'custom_q_axes_order_or_range_invalid')
    if font.reader is not None:
        raw = raw_avar(font.reader['avar'], custom_order)
        require(raw['major'] == 1 and raw['minor'] == 0 and raw['reserved'] == 0
                and raw['axis_count'] == 3 and raw['trailing_bytes'] == 0
                and raw['standard_record_conformance_pass']
                and all(all(row['from_f2dot14'] == row['to_f2dot14'] for row in axis['records'])
                        for axis in raw['axes']), 'input_q_avar_not_identity')
    require(font['avar'].majorVersion == 1 and font['avar'].minorVersion == 0
            and set(font['avar'].segments) == set(custom_order)
            and all(segment == IDENTITY for segment in font['avar'].segments.values()),
            'input_q_avar_not_identity')
    bases = tuple(basis_from_axis(axis) for axis in source_axes)
    # The instancer filters out named instances outside the restricted range.
    # Validate their original coordinates before that filtering can hide an
    # unsupported metadata mapping. Only metadata is copied, not glyph data.
    metadata = {'fvar': copy.deepcopy(font['fvar'])}
    if 'STAT' in font:
        metadata['STAT'] = copy.deepcopy(font['STAT'])
    _restore_metadata(metadata, source_axes, bases)
    avar, mapping_report = build_rebased_avar(source_axes)
    limits = {tag: (basis.q_min / 16384, 0., basis.q_max / 16384)
              for tag, basis in zip(custom_order, bases)}
    order = font.getGlyphOrder()
    cmap = font['cmap'].compile(font)
    rebased = instantiateVariableFont(font, limits, inplace=False, optimize=False)
    require(rebased.getGlyphOrder() == order and rebased['maxp'].numGlyphs == font['maxp'].numGlyphs
            and rebased['cmap'].compile(rebased) == cmap, 'instancer_changed_glyph_identity_or_cmap')
    _restore_metadata(rebased, source_axes, bases)
    rename = {CUSTOM_TAGS[axis.tag]: axis.tag for axis in source_axes}
    for original, output in zip(source_axes, rebased['fvar'].axes):
        output.axisTag = original.tag
        output.minValue, output.defaultValue, output.maxValue = original.minimum, original.default, original.maximum
    for variations in rebased['gvar'].variations.values():
        for variation in variations:
            require(set(variation.axes) <= set(rename), 'unknown_gvar_axis_after_instancing')
            variation.axes = {rename[tag]: support for tag, support in variation.axes.items()}
    if 'cvar' in rebased:
        for variation in rebased['cvar'].variations:
            require(set(variation.axes) <= set(rename), 'unknown_cvar_axis_after_instancing')
            variation.axes = {rename[tag]: support for tag, support in variation.axes.items()}
    rebased['avar'] = avar
    report = {
        'status': 'STANDARD_Q_FONT_REBASED_CANDIDATE_ONLY', 'font_only': True,
        'algorithm': 'fontTools.varLib.instancer.instantiateVariableFont',
        'fonttools_version': fontTools.__version__, 'inplace': False, 'optimize': False,
        'source_q_limits': {tag: list(values) for tag, values in limits.items()},
        'glyph_count': len(order), 'glyph_order_and_cmap_preserved': True,
        'variation_tables_processed': [tag for tag in ('gvar', 'cvar', 'HVAR', 'VVAR', 'MVAR', 'GDEF', 'GPOS', 'GSUB')
                                       if tag in font],
        'coordinate_mapping_certificate': mapping_report,
        'coefficient_rounding_possible': True, 'lossless_conversion': False,
        'strict_native_candidate_gate': 'UNACCEPTED', 'original_source_font_tested': False,
        'native_glyph_test': 'NOT_RUN', 'Windows11': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN',
        'source_user_mapping_accepted': False, 'target_mapping_accepted': False,
        'font_conversion_accepted': False, 'font_only_equivalence_accepted': False,
    }
    return rebased, report
