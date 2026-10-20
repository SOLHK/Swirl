#!/usr/bin/env python3
"""Original variable GPOS experiment; no Apple font or production converter use.

This builds independent geometric symbols in memory, retaining their source
glyf/gvar, cmap, GSUB, horizontal and vertical metric table bytes when GPOS is
added. It measures the difference between OpenType metric APIs and actual
HarfBuzz shaping for vert/vrt2/vkrn routing. A feature tag has no intrinsic
writing-direction guard. Passing this experiment cannot establish DirectWrite,
CoreText, Qt or Windows 11 acceptance.

The exact encoder rejects fractional base values or half-deltas rather than
rounding them. Separately labelled counterexamples deliberately round only
GPOS values in independent synthetic fonts and retain the resulting failure.

References consulted before this independent implementation:
https://learn.microsoft.com/en-us/typography/opentype/spec/features_uz
https://learn.microsoft.com/en-us/typography/opentype/spec/gpos
https://learn.microsoft.com/en-us/typography/opentype/spec/otvarcommonformats
https://learn.microsoft.com/en-us/typography/opentype/spec/hvar
https://learn.microsoft.com/en-us/windows/win32/api/dwrite/nf-dwrite-idwritetextanalyzer-getglyphplacements
https://github.com/harfbuzz/harfbuzz/blob/12.3.2/src/hb-ot-shape.cc
https://github.com/harfbuzz/harfbuzz/blob/12.3.2/src/hb-ot-hmtx-table.hh
https://github.com/harfbuzz/harfbuzz/blob/12.3.2/src/hb-ot-font.cc
https://harfbuzz.github.io/harfbuzz-hb-font.html
https://fonttools.readthedocs.io/en/latest/varLib/builder.html
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass, replace
from fractions import Fraction
import hashlib
import io
import itertools
import json
import math
import os
from pathlib import Path

import fontTools
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.roundTools import otRound
from fontTools.otlLib.builder import buildLookup, buildSinglePosSubtable, buildValue
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib.builder import (
    buildDeltaSetIndexMap, buildVarData, buildVarDevTable, buildVarRegionList, buildVarStore,
)
from fontTools.varLib.varStore import VarStoreInstancer

UPM = 1000
SCALE = 64  # Output precision only; the font UPM, outlines and metrics are unchanged.
LIMIT = 1 / 32
RECONSTRUCTION_LIMIT = 1.0
AXES = (('WDTH', 1., 500., 1000.), ('wght', 100., 400., 900.), ('HGHT', 1., 500., 1000.))
ROUTES = ('vert', 'vrt2', 'vkrn')
PROTECTED = ('glyf', 'loca', 'gvar', 'hmtx', 'HVAR', 'vmtx', 'vhea', 'cmap', 'GSUB', 'fvar')
POINTS = tuple(itertools.product((-1., 0., 1.), repeat=3)) + (
    (.25, -.5, .75), (.201171875, .2475, .42225), (.123456789, -.987654321, .456789),
    (1/32768, 0., 0.), (-1/32768, 0., 0.),
)


@dataclass(frozen=True)
class Symbol:
    name: str
    width: int
    coefficients: tuple[int, int, int, int]  # WDTH, wght, HGHT, WDTH*wght


SYMBOLS = (
    Symbol('.notdef', 600, (40, 8, 4, 4)),
    Symbol('space', 400, (80, 16, 8, 4)),
    Symbol('han', 1000, (200, 40, 8, 12)),
    Symbol('han.hk', 920, (160, 32, 8, 16)),
    Symbol('han.vert', 840, (120, 24, 4, 8)),
    Symbol('han.hk.vert', 880, (136, 28, 12, 20)),
    Symbol('latinA', 620, (84, 20, 12, 8)),
    Symbol('latinB', 480, (54, 10, 6, 8)),
)

GSUB = '''
languagesystem DFLT dflt;
languagesystem latn dflt;
languagesystem hani dflt;
languagesystem hani ZHS;
languagesystem hani ZHH;
feature locl {
    script hani;
    language ZHH;
    sub han by han.hk;
} locl;
feature vert {
    sub han by han.vert;
    sub han.hk by han.hk.vert;
} vert;
feature vrt2 {
    sub han by han.vert;
    sub han.hk by han.hk.vert;
} vrt2;
'''


class UnrepresentableAdjustment(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValueError(message)


def requested_location(normalized):
    return {tag: default + value * (default-minimum if value < 0 else maximum-default)
            for (tag, minimum, default, maximum), value in zip(AXES, normalized)}


def analytic_width(symbol, normalized):
    x, y, z = normalized
    a, b, c, d = symbol.coefficients
    return symbol.width + a*x + b*y + c*z + d*x*y


def supports_and_deltas(symbols):
    supports, selectors = [], []
    for axis, (tag, *_values) in enumerate(AXES):
        for sign in (-1, 1):
            supports.append({tag: (-1, -1, 0) if sign < 0 else (0, 1, 1)})
            selectors.append((axis, sign))
    for x, y in itertools.product((-1, 1), repeat=2):
        supports.append({'WDTH': (-1, -1, 0) if x < 0 else (0, 1, 1),
                         'wght': (-1, -1, 0) if y < 0 else (0, 1, 1)})
        selectors.append((3, x*y))
    return supports, [[symbol.coefficients[axis]*sign for axis, sign in selectors] for symbol in symbols]


def serialize(font):
    stream = io.BytesIO()
    font.save(stream)
    return stream.getvalue()


def original_fixture(kind='even'):
    require(kind in ('even', 'odd_width', 'odd_delta'), 'unknown_original_fixture_kind')
    symbols = list(SYMBOLS)
    if kind == 'odd_width':
        symbols[-1] = replace(symbols[-1], width=333)
    elif kind == 'odd_delta':
        symbols[-1] = replace(symbols[-1], coefficients=(55, 9, 5, 7))
    builder = FontBuilder(UPM, isTTF=True)
    order = [s.name for s in symbols]
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({0x20: 'space', 0x4E2D: 'han', 0x41: 'latinA', 0x42: 'latinB'})
    outlines = {}
    for gid, name in enumerate(order):
        pen = TTGlyphPen(None)
        if name != 'space':
            # Independent geometric symbols, not drawings of existing glyphs.
            pen.moveTo((90+gid*7, 100))
            pen.lineTo((310+gid*11, 100))
            pen.lineTo((350+gid*5, 540+gid*9))
            pen.lineTo((130+gid*3, 650-gid*5))
            pen.closePath()
        outlines[name] = pen.glyph()
    builder.setupGlyf(outlines)
    builder.setupHorizontalMetrics({s.name: (s.width, outlines[s.name].xMin if s.name != 'space' else 0)
                                    for s in symbols})
    builder.setupHorizontalHeader(ascent=860, descent=-140)
    builder.setupVerticalMetrics({s.name: (1000, 860-(outlines[s.name].yMax if s.name != 'space' else 0))
                                  for s in symbols})
    builder.setupVerticalHeader(ascent=500, descent=-500)
    builder.setupNameTable({'familyName': 'Swirl Original GPOS Laboratory', 'styleName': 'Regular',
        'uniqueFontIdentifier': 'Swirl-Original-GPOS-Laboratory-' + kind,
        'fullName': 'Swirl Original GPOS Laboratory ' + kind,
        'psName': 'SwirlOriginalGPOSLaboratory-' + kind})
    builder.setupOS2(sTypoAscender=860, sTypoDescender=-140, usWinAscent=900, usWinDescent=200)
    builder.setupPost()
    builder.setupFvar([(tag, minimum, default, maximum, tag) for tag, minimum, default, maximum in AXES], [])
    # This experiment varies advances and GPOS only; the original outline is
    # deliberately static. TrueType metric variations must also be represented
    # in gvar phantom points, consistently with HVAR, so rasterizers and static
    # instancers that use gvar obtain the same advances. Only the right advance
    # phantom moves. No actual contour point or left origin moves.
    supports, rows = supports_and_deltas(symbols)
    variations = {}
    for symbol, row in zip(symbols, rows):
        count = len(outlines[symbol.name].getCoordinates(builder.font['glyf'])[0])
        variations[symbol.name] = []
        for support, delta in zip(supports, row):
            points = [(0, 0)]*(count+4)
            points[-3] = (delta, 0)
            variations[symbol.name].append(TupleVariation(support, points))
    builder.setupGvar(variations)
    font = builder.font
    font.recalcTimestamp = False
    font['head'].created = font['head'].modified = 2082844800
    hvar = newTable('HVAR')
    hvar.table = ot.HVAR()
    hvar.table.Version = 0x00010000
    hvar.table.VarStore = buildVarStore(buildVarRegionList(supports, [a[0] for a in AXES]),
                                      [buildVarData(list(range(len(supports))), rows, optimize=False)])
    hvar.table.AdvWidthMap = buildDeltaSetIndexMap(list(range(len(symbols))))
    hvar.table.LsbMap = hvar.table.RsbMap = None
    font['HVAR'] = hvar
    addOpenTypeFeaturesFromString(font, GSUB)
    return serialize(font), tuple(symbols)


def adjustment_values(symbols, *, diagnostic_rounding=False):
    supports, rows = supports_and_deltas(symbols)
    bases = [Fraction(s.width, 2) - s.width//2 for s in symbols]
    halves = [[Fraction(value, 2) for value in row] for row in rows]
    failures = []
    for s, base, deltas in zip(symbols, bases, halves):
        if base.denominator != 1:
            failures.append({'glyph': s.name, 'field': 'default_xPlacement', 'value': float(base)})
        for index, value in enumerate(deltas):
            if value.denominator != 1:
                failures.append({'glyph': s.name, 'field': f'variation_delta_{index}', 'value': float(value)})
    if failures and not diagnostic_rounding:
        raise UnrepresentableAdjustment(json.dumps(failures, sort_keys=True))
    convert = (lambda value: otRound(float(value))) if diagnostic_rounding else int
    return supports, [convert(v) for v in bases], [[convert(v) for v in row] for row in halves], failures


def add_adjustment(original, symbols, route, *, diagnostic_rounding=False):
    require(route in ROUTES, 'unsupported_feature_route')
    supports, bases, rows, failures = adjustment_values(symbols, diagnostic_rounding=diagnostic_rounding)
    font = TTFont(io.BytesIO(original), recalcTimestamp=False)
    require(font.getGlyphOrder() == [s.name for s in symbols] and 'GPOS' not in font,
            'only_the_independent_original_fixture_is_supported')
    protected = {tag: font.getTableData(tag) for tag in PROTECTED}
    gdef = newTable('GDEF')
    gdef.table = ot.GDEF()
    gdef.table.Version = 0x00010003
    gdef.table.GlyphClassDef = gdef.table.AttachList = gdef.table.LigCaretList = None
    gdef.table.MarkAttachClassDef = gdef.table.MarkGlyphSetsDef = None
    gdef.table.VarStore = buildVarStore(buildVarRegionList(supports, [a[0] for a in AXES]),
                                      [buildVarData(list(range(len(supports))), rows, optimize=False)])
    font['GDEF'] = gdef
    values = {s.name: buildValue({'XPlacement': bases[gid], 'XPlaDevice': buildVarDevTable(gid)})
              for gid, s in enumerate(symbols)}
    lookup = buildLookup([buildSinglePosSubtable(values, font.getReverseGlyphMap())], table='GPOS')
    table = ot.GPOS(); table.Version = 0x00010000
    table.LookupList = ot.LookupList(); table.LookupList.Lookup = [lookup]; table.LookupList.LookupCount = 1
    record = ot.FeatureRecord(); record.FeatureTag = route; record.Feature = ot.Feature()
    record.Feature.FeatureParams = None; record.Feature.LookupListIndex = [0]; record.Feature.LookupCount = 1
    table.FeatureList = ot.FeatureList(); table.FeatureList.FeatureRecord = [record]; table.FeatureList.FeatureCount = 1
    table.ScriptList = ot.ScriptList(); table.ScriptList.ScriptRecord = []
    for tag in ('DFLT', 'hani', 'latn'):
        sr = ot.ScriptRecord(); sr.ScriptTag = tag; sr.Script = ot.Script()
        lang = ot.LangSys(); lang.LookupOrder = None; lang.ReqFeatureIndex = 0xFFFF
        lang.FeatureIndex = [0]; lang.FeatureCount = 1
        sr.Script.DefaultLangSys = lang; sr.Script.LangSysRecord = []
        if tag == 'hani':
            for language in ('ZHH ', 'ZHS '):
                lr = ot.LangSysRecord(); lr.LangSysTag = language; lr.LangSys = copy.deepcopy(lang)
                sr.Script.LangSysRecord.append(lr)
        sr.Script.LangSysCount = len(sr.Script.LangSysRecord)
        table.ScriptList.ScriptRecord.append(sr)
    table.ScriptList.ScriptCount = len(table.ScriptList.ScriptRecord)
    font['GPOS'] = newTable('GPOS'); font['GPOS'].table = table
    candidate = serialize(font)
    reread = TTFont(io.BytesIO(candidate), recalcTimestamp=False)
    require(reread['head'].unitsPerEm == UPM and reread.getGlyphOrder() == font.getGlyphOrder()
            and all(reread.getTableData(tag) == data for tag, data in protected.items()),
            'GPOS_experiment_changed_original_outlines_metrics_mapping_or_GSUB')
    return candidate, failures


def table_adjustments(data, symbols, normalized):
    font = TTFont(io.BytesIO(data), recalcTimestamp=False)
    store = VarStoreInstancer(font['GDEF'].table.VarStore, font['fvar'].axes,
                             {axis[0]: value for axis, value in zip(AXES, normalized)})
    subtable = font['GPOS'].table.LookupList.Lookup[0].SubTable[0]
    values = ([subtable.Value]*len(subtable.Coverage.glyphs) if subtable.Format == 1 else subtable.Value)
    result = {}
    for glyph, value in zip(subtable.Coverage.glyphs, values):
        device = value.XPlaDevice
        require(device.DeltaFormat == 0x8000, 'GPOS_variation_index_missing')
        result[glyph] = value.XPlacement + store[(device.StartSize << 16) | device.EndSize]
    require(set(result) == {s.name for s in symbols}, 'GPOS_final_glyph_coverage_incomplete')
    return result


def shape(data, normalized, direction, language, features=None):
    import uharfbuzz as hb
    font = hb.Font(hb.Face(data))
    hb.ot_font_set_funcs(font)
    font.scale = (UPM*SCALE, UPM*SCALE)
    font.set_variations(requested_location(normalized))
    observed = list(font.get_var_coords_normalized())
    buffer = hb.Buffer(); buffer.add_str('中 AB')
    buffer.direction = direction; buffer.script = 'hani'; buffer.language = language
    hb.shape(font, buffer, features or {}, shapers=['ot'])
    rows = []
    for info, position in zip(buffer.glyph_infos, buffer.glyph_positions):
        origin = font.get_glyph_v_origin(info.codepoint)
        rows.append({'gid': info.codepoint, 'cluster': info.cluster,
                     'x_advance': position.x_advance/SCALE, 'y_advance': position.y_advance/SCALE,
                     'x_offset': position.x_offset/SCALE, 'y_offset': position.y_offset/SCALE,
                     'metric_width': font.get_glyph_h_advance(info.codepoint)/SCALE,
                     'metric_height': -font.get_glyph_v_advance(info.codepoint)/SCALE,
                     'metric_vertical_origin': [v/SCALE for v in origin]})
    return {'requested_normalized': list(normalized), 'observed_normalized': observed, 'glyphs': rows}


def feature_settings(route, policy):
    if policy == 'default':
        return {}
    if policy == 'disabled':
        return {route: 0}
    require(policy == 'enabled', 'unknown_feature_policy')
    # Registered vert and vrt2 should not operate simultaneously.
    return {route: 1, 'vert': 0} if route == 'vrt2' else {route: 1}


def add_stat(group, field, error, context):
    require(math.isfinite(error), 'nonfinite_GPOS_observation')
    stat = group.setdefault(field, {'checks': 0, 'max_abs_error': 0.,
        'above_1_over_32': 0, 'above_reconstruction_1_FUnit': 0, 'worst': None})
    stat['checks'] += 1
    stat['above_1_over_32'] += abs(error) > LIMIT
    stat['above_reconstruction_1_FUnit'] += abs(error) > RECONSTRUCTION_LIMIT
    if stat['worst'] is None or abs(error) > stat['max_abs_error']:
        stat['max_abs_error'] = abs(error)
        stat['worst'] = {**context, 'signed_error': error}


def compare_shaping(original, candidate, symbols, route, points=POINTS):
    result = {'policies': {}, 'shape_calls': 0, 'glyph_observations': 0,
              'normalized_coordinate_quantization_cases': 0,
              'source_layout_tables_identical': True, 'source_metric_APIs_identical': True,
              'table_equation': {}, 'regional_and_vertical_substitutions_checked': 0}
    for normalized in points:
        encoded = table_adjustments(candidate, symbols, normalized)
        for s in symbols:
            wanted = analytic_width(s, normalized)/2 - s.width//2
            add_stat(result['table_equation'], 'xPlacement_minus_required_compensation',
                     encoded[s.name]-wanted, {'glyph': s.name, 'normalized': list(normalized)})
        for policy, direction, language in itertools.product(('default', 'enabled', 'disabled'),
                                                              ('ltr', 'ttb'), ('zh-cn', 'zh-hk')):
            features = feature_settings(route, policy)
            before = shape(original, normalized, direction, language, features)
            after = shape(candidate, normalized, direction, language, features)
            result['shape_calls'] += 2
            require(before['observed_normalized'] == after['observed_normalized']
                    and len(before['glyphs']) == len(after['glyphs']) == 4, 'GPOS_changed_shape_instance_or_glyph_count')
            observed = after['observed_normalized']
            result['normalized_coordinate_quantization_cases'] += observed != list(normalized)
            table_values = table_adjustments(candidate, symbols, observed)
            vertical_substitution = bool(features.get('vert', direction == 'ttb') or features.get('vrt2', 0))
            wanted_first = (3 if language == 'zh-hk' else 2) + (2 if vertical_substitution else 0)
            require(after['glyphs'][0]['gid'] == wanted_first
                    and [g['gid'] for g in after['glyphs'][1:]] == [1, 6, 7],
                    'regional_or_vertical_GSUB_mapping_not_preserved')
            result['regional_and_vertical_substitutions_checked'] += 1
            stats = result['policies'].setdefault(policy, {}).setdefault(direction, {})
            for b, a in zip(before['glyphs'], after['glyphs']):
                gid = a['gid']; symbol = symbols[gid]
                require(gid == b['gid'] and a['cluster'] == b['cluster'], 'GPOS_changed_GSUB_or_clusters')
                require(all(a[k] == b[k] for k in ('metric_width', 'metric_height', 'metric_vertical_origin')),
                        'GPOS_changed_a_low_level_metric_API')
                context = {'route': route, 'policy': policy, 'direction': direction, 'language': language,
                    'glyph': symbol.name, 'requested_normalized': list(normalized),
                    'observed_normalized': observed, 'metric_width': a['metric_width'],
                    'low_level_vertical_origin': a['metric_vertical_origin'],
                    'before_x_offset': b['x_offset'], 'after_x_offset': a['x_offset'],
                    'table_xPlacement': table_values[symbol.name], 'wanted_fixed_origin': symbol.width//2}
                add_stat(stats, 'horizontal_metric_minus_analytic',
                         a['metric_width']-analytic_width(symbol, observed), context)
                for field in ('x_advance', 'y_advance', 'y_offset'):
                    add_stat(stats, field+'_change_from_source', a[field]-b[field], context)
                    require(a[field] == b[field], 'GPOS_changed_non_X_placement_or_advances')
                shift = a['x_offset']-b['x_offset']
                add_stat(stats, 'observed_X_placement_change', shift, context)
                add_stat(stats, 'observed_shift_minus_GPOS_table', shift-table_values[symbol.name], context)
                if direction == 'ttb':
                    add_stat(stats, 'source_X_offset_plus_half_observed_advance',
                             b['x_offset'] + b['metric_width']/2, context)
                    add_stat(stats, 'fixed_origin_layout_error', a['x_offset']+symbol.width//2, context)
                if direction == 'ltr' and policy == 'default':
                    require(after == before, 'default_horizontal_layout_changed_by_GPOS')
                if policy == 'disabled':
                    require(after == before, 'disabled_GPOS_still_changed_shaping')
                result['glyph_observations'] += 2
    return result


def run(output):
    output = Path(output).resolve()
    require(not output.exists(), 'new_report_path_required')
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'NOT_RUN', 'source_commit': os.environ.get('GITHUB_SHA'),
        'data_origin': 'independent_geometric_symbols_no_Apple_font_input',
        'fonttools_version': fontTools.__version__, 'font_binary_published': False,
        'source_or_production_modified': False, 'windows_11_acceptance': 'NOT_RUN',
        'DirectWrite_layout_acceptance': 'NOT_RUN', 'CoreText_layout_acceptance': 'NOT_RUN',
        'Qt_acceptance': 'NOT_RUN', 'exact_comparison_limit': LIMIT,
        'existing_reconstruction_comparison_limit': RECONSTRUCTION_LIMIT,
        'measurement_output_units_per_FUnit': SCALE, 'axes': [axis[0] for axis in AXES],
        'normalized_locations': len(POINTS), 'glyphs': len(SYMBOLS),
        'feature_routes': {}, 'fractional_encoding_counterexamples': {}}
    try:
        import uharfbuzz as hb
        report.update(uharfbuzz_version=hb.__version__, harfbuzz_version=hb.version_string(),
                      selected_shaper='ot')
        original, symbols = original_fixture()
        report['original_fixture_sha256'] = hashlib.sha256(original).hexdigest()
        for route in ROUTES:
            candidate, failures = add_adjustment(original, symbols, route)
            require(not failures, 'integer_fixture_became_unrepresentable')
            measured = compare_shaping(original, candidate, symbols, route)
            # Preserve completed measurements even when a subsequent invariant
            # fails. A failed precision budget must never erase its evidence.
            report['feature_routes'][route] = measured
            measured['candidate_sha256'] = hashlib.sha256(candidate).hexdigest()
            require(measured['table_equation']['xPlacement_minus_required_compensation']['max_abs_error'] < 1e-9,
                    'serialized_GPOS_table_equation_failed')
            for direction in ('ltr', 'ttb'):
                require(not measured['policies']['enabled'][direction]['observed_shift_minus_GPOS_table']['above_1_over_32'],
                        'explicitly_enabled_GPOS_did_not_match_serialized_values')
            for policy in ('default', 'enabled'):
                vertical = measured['policies'][policy]['ttb']
                measured[policy + '_vertical_feature_applied_consistently'] = not (
                    vertical['observed_shift_minus_GPOS_table']['above_1_over_32'])
                measured[policy + '_vertical_layout_within_exact_limit'] = not (
                    vertical['fixed_origin_layout_error']['above_1_over_32'])
                measured[policy + '_vertical_layout_within_reconstruction_limit'] = not (
                    vertical['fixed_origin_layout_error']['above_reconstruction_1_FUnit'])
            # The serialized compensation and its actual GPOS application are
            # tested separately above. HarfBuzz can round the source HVAR width
            # before constructing half-width origins; that remaining raw engine
            # error is retained against both budgets, not treated as an exact
            # native-layout pass. This experiment's representable fixture must
            # still fit the converter's separate existing 1-FUnit budget.
            require(measured['enabled_vertical_layout_within_reconstruction_limit'],
                    'explicit_vertical_GPOS_exceeded_existing_reconstruction_budget')
            measured['default_horizontal_unchanged'] = True
            measured['explicit_horizontal_feature_can_change_placement'] = bool(
                measured['policies']['enabled']['ltr']['observed_X_placement_change']['max_abs_error'])
        for kind in ('odd_width', 'odd_delta'):
            source, specs = original_fixture(kind)
            try:
                add_adjustment(source, specs, 'vert')
            except UnrepresentableAdjustment as error:
                refusal = json.loads(str(error))
            else:
                raise ValueError('fractional_exact_encoder_did_not_reject_unrepresentable_values')
            rounded, _ = add_adjustment(source, specs, 'vert', diagnostic_rounding=True)
            measured = compare_shaping(source, rounded, specs, 'vert')
            report['fractional_encoding_counterexamples'][kind] = {
                'exact_encoder_status': 'REJECTED_FRACTIONAL_VALUE', 'unrepresentable_values': refusal,
                'rounded_GPOS_only_for_measuring_the_counterexample': True,
                'source_outlines_metrics_GSUB_and_UPM_unchanged': True,
                'production_accepted': False, 'table_equation': measured['table_equation'],
                'explicit_vertical_layout': measured['policies']['enabled']['ttb']}
        report['interpretation'] = {
            'mechanism': 'GDEF ItemVariationStore plus GPOS SinglePos XPlacement can compensate '
                'half-current-advance minus the desired fixed origin when active.',
            'feature_selection': 'Observed default feature selection is HarfBuzz-version-specific. '
                'vert/vrt2 are registered as substitution features; routing GPOS through them here '
                'is an interoperability experiment, not a cross-client guarantee. vkrn is discretionary.',
            'fractional_values': 'At the fvar default, valid region scalars are 0 or 1; integer '
                'ValueRecord bases and integer ItemVariationStore deltas cannot supply a half-unit base. '
                'Rounded error is reported against both 1/32 and the separate existing 1-FUnit '
                'reconstruction budget. One missed precision budget does not imply the other failed.',
            'engine_metric_precision': 'The tested HarfBuzz 12.3.2 implementation rounds HVAR '
                'advance deltas to FUnits before applying the requested output scale, and derives '
                'vertical X origins from those observed advances. GPOS applies fractional variation '
                'values at the output scale. Both raw metric-minus-analytic and '
                'observed-GPOS-minus-encoded deltas are retained; a successful GPOS mechanism '
                'does not assert an exact fixed-origin layout pass.',
            'mapping': 'Every compensation uses the final GID after independent locl and vert/vrt2 '
                'substitutions; no glyph ID, source mapping, source outline or scalar metric is changed.',
            'scope': 'This does not test application default features, caret/line breaks, upright versus '
                'sideways text segmentation, Apple original reconstruction or any native Windows/CoreText layout.'}
        report['status'] = 'HARFBUZZ_GPOS_MECHANISM_MEASURED_WITH_COMPATIBILITY_AND_QUANTIZATION_LIMITS'
    except Exception as error:
        report['status'] = 'HARFBUZZ_GPOS_EXPERIMENT_FAILED'
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({'status': result['status'], 'HarfBuzz': result.get('harfbuzz_version'),
        'default_vertical_feature_routes': {tag: r['default_vertical_feature_applied_consistently']
                                           for tag, r in result['feature_routes'].items()}}))
