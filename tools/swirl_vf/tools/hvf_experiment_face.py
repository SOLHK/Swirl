"""Assemble a private, incomplete HVF design-q face without production admission.

Every source GID requires a real native default command record. Float geometry
is scaled before its first integer encoding. Optional variable models are
already scaled results of the existing glyph reconstructor. Table metrics are
explicitly not Apple native measurements; no original user mapping is granted.

Uses fontTools' public UPEM visitor (MIT), not a second reconstruction engine:
https://github.com/fonttools/fonttools/blob/4.61.1/Lib/fontTools/ttLib/scaleUpem.py
https://learn.microsoft.com/en-us/typography/opentype/spec/glyf
"""
from __future__ import annotations

import array
import copy
import hashlib
import json
import math

from fontTools.misc.roundTools import otRound
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphCoordinates
from fontTools.ttLib.tables.ttProgram import Program

from metric_variations import add_metric_variations
from rebuild import compatible_coordinates
from source_metrics import SourceMetrics


SOURCE_TAGS = ('WDTH', 'wght', 'HGHT')
Q_TAGS = ('XWDT', 'XWGT', 'XHGT')
LIMIT = 1 / 32
DROP = frozenset(('hvgl', 'hvpm', 'HVAR', 'VVAR', 'VORG', 'fvar', 'avar', 'STAT', 'DSIG'))
# The upstream visitor explicitly does not support AAT. These source tables
# are retained only as visibly unverified experiment inputs, never accepted.
UNVERIFIED = frozenset(('trak', 'cidg', 'meta'))
KNOWN = frozenset(('GlyphOrder', 'head', 'hhea', 'vhea', 'maxp', 'OS/2', 'post',
                   'hmtx', 'vmtx', 'cmap', 'name', 'GSUB', 'GPOS', 'GDEF', 'BASE', 'kern'))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def _table_bytes(font, tag):
    return font.reader[tag] if font.reader is not None and tag in font.reader else font.getTableData(tag)


def _layout_guard(font):
    """Flattened HVF paths cannot promise old point-index anchor semantics."""
    seen = set()

    def visit(value):
        if value is None or isinstance(value, (str, bytes, int, float)):
            return
        if id(value) in seen:
            return
        seen.add(id(value))
        require(len(seen) <= 2000000, 'experiment_layout_node_budget_exceeded')
        if isinstance(value, dict):
            children = value.values()
        elif isinstance(value, (list, tuple)):
            children = value
        else:
            if hasattr(value, 'ensureDecompiled'):
                value.ensureDecompiled(recurse=False)
            name = type(value).__name__
            if name in ('Anchor', 'CaretValue', 'BaseCoord'):
                require(getattr(value, 'Format', getattr(value, 'BaseCoordFormat', 0)) != 2,
                        'experiment_flattening_cannot_preserve_layout_point_indices')
            children = vars(value).values() if hasattr(value, '__dict__') else ()
        for child in children:
            visit(child)

    for tag in ('BASE', 'GDEF', 'GPOS', 'GSUB'):
        if tag in font:
            visit(font[tag])


def _glyph(coordinates, flags, ends):
    glyph = Glyph()
    glyph.numberOfContours = len(ends)
    glyph.coordinates = GlyphCoordinates(coordinates.tolist())
    glyph.flags = array.array('B', flags)
    if flags:
        glyph.flags[0] |= 0x40
    glyph.endPtsOfContours = list(ends)
    glyph.program = Program()
    glyph.program.fromBytecode([])
    glyph.recalcBounds(None)
    return glyph


def _integer_model(glyph, variations):
    require(not glyph.isComposite(), 'experiment_selected_model_must_be_expanded')
    require(not getattr(glyph, 'program', Program()).getBytecode(), 'experiment_hint_program_not_supported')
    points, ends, flags = glyph.getCoordinates(None)
    require(len(points) == len(flags) and (not points or ends and ends[-1] == len(points)-1),
            'experiment_selected_model_topology_invalid')
    for pair in points:
        require(all(type(v) in (int, float) and math.isfinite(v) and v == int(v)
                    and -32768 <= v <= 32767 for v in pair), 'experiment_glyf_coordinate_overflow')
    for variation in variations:
        require(set(variation.axes) <= set(Q_TAGS) and len(variation.coordinates) == len(points)+4,
                'experiment_selected_gvar_axis_or_point_count')
        for pair in variation.coordinates:
            require(pair is not None and len(pair) == 2 and all(type(v) in (int, float)
                    and math.isfinite(v) and v == int(v) and -32768 <= v <= 32767 for v in pair),
                    'experiment_gvar_signed16_delta_required')


def _rename(font):
    family = 'Swirl EXPERIMENTAL DEFAULT ONLY Q'
    identities = {1: family, 2: 'Incomplete', 3: 'SwirlExperimentalDefaultOnlyQ-Incomplete',
                  4: family+' Incomplete', 6: 'SwirlExperimentalDefaultOnlyQ-Incomplete',
                  16: family, 17: 'Incomplete', 18: family, 20: family.replace(' ', ''),
                  21: family, 22: 'Incomplete', 25: 'SwirlExperimentalDefaultOnlyQ'}
    for record in list(font['name'].names):
        if record.nameID in identities:
            font['name'].setName(identities[record.nameID], record.nameID,
                                 record.platformID, record.platEncID, record.langID)
    for name_id, text in identities.items():
        font['name'].setName(text, name_id, 3, 1, 0x409)


def assemble_experiment_face(source_font, native_default_records, selected_models=None, *, multiplier=15):
    """Return (detached TTFont, explicit incomplete-experiment manifest).

    Records must contain every source GID exactly once, in ascending order, as
    ``{'glyph_id': gid, 'commands': [...]}``. Empty *measured* outlines are valid;
    missing records are never replaced by empty glyphs. The caller must bind the
    native transcript, source file, face and code hashes outside this pure helper.
    """
    require(isinstance(source_font, TTFont), 'experiment_TTFont_source_required')
    require('hvgl' in source_font and 'glyf' not in source_font and 'VORG' in source_font,
            'experiment_HVGL_with_explicit_VORG_required')
    require(set(source_font.keys()) <= KNOWN | DROP | UNVERIFIED,
            'experiment_unsupported_table_semantics')
    require([a.axisTag for a in source_font['fvar'].axes] == list(SOURCE_TAGS),
            'experiment_source_axis_order_required')
    source_upem = source_font['head'].unitsPerEm
    require(type(multiplier) is int and multiplier >= 1 and type(source_upem) is int
            and 16 <= source_upem <= source_upem * multiplier <= 16384,
            'experiment_legal_integer_precision_grid_required')
    order = source_font.getGlyphOrder()
    require(order and order[0] == '.notdef' and len(set(order)) == len(order)
            and len(order) == source_font['maxp'].numGlyphs, 'experiment_source_GID_order_invalid')
    selected_models = {} if selected_models is None else selected_models
    require(type(selected_models) is dict and all(type(gid) is int and 0 <= gid < len(order)
                                                for gid in selected_models), 'experiment_selected_GID_invalid')
    _layout_guard(source_font)
    cmap_digest = hashlib.sha256(source_font['cmap'].compile(source_font)).hexdigest()
    unverified_bytes = {tag: _table_bytes(source_font, tag) for tag in UNVERIFIED if tag in source_font}
    unverified = {tag: hashlib.sha256(data).hexdigest() for tag, data in unverified_bytes.items()}
    provider = SourceMetrics(source_font)
    candidate = copy.deepcopy(source_font)
    removed = sorted(DROP & set(candidate.keys()))
    for tag in removed:
        del candidate[tag]
    for tag, data in unverified_bytes.items():
        candidate[tag] = DefaultTable(tag)
        candidate[tag].data = data
    candidate.setGlyphOrder(order)
    candidate['glyf'] = newTable('glyf')
    candidate['glyf'].glyphs, candidate['glyf'].glyphOrder = {}, list(order)
    candidate['loca'] = newTable('loca')
    candidate['gvar'] = newTable('gvar')
    candidate['gvar'].version, candidate['gvar'].reserved, candidate['gvar'].variations = 1, 0, {}
    candidate['fvar'] = newTable('fvar')
    candidate['fvar'].axes, candidate['fvar'].instances = [], []
    for tag in Q_TAGS:
        axis = Axis()
        axis.axisTag, axis.minValue, axis.defaultValue, axis.maxValue, axis.flags = tag, -1., 0., 1., 0
        axis.axisNameID = candidate['name'].addName('Experimental '+tag)
        candidate['fvar'].axes.append(axis)
    candidate['avar'] = newTable('avar')
    candidate['avar'].majorVersion, candidate['avar'].minorVersion = 1, 0
    candidate['avar'].segments = {tag: {-1.: -1., 0.: 0., 1.: 1.} for tag in Q_TAGS}
    # Compile this table alone: serializing the whole font here would round
    # native float coordinates before the UPEM visitor has scaled them.
    candidate['avar'].compile(candidate)
    defaults, selected_defaults = [], {}
    point_error = metric_error = 0.
    point_failures = empty_count = cubic_count = count = 0
    zero = dict.fromkeys(SOURCE_TAGS, 0.)
    for record in native_default_records:
        require(count < len(order) and type(record) is dict and type(record.get('glyph_id')) is int
                and record['glyph_id'] == count and record.get('error') is None and 'commands' in record,
                'experiment_complete_ordered_native_defaults_required')
        coords, flags, ends, cubics = compatible_coordinates([record])
        require(cubics == 0, 'experiment_native_cubic_default_requires_separate_error_budget')
        points = coords[0]
        name = order[count]
        glyph = _glyph(points, flags, ends)
        candidate['glyf'].glyphs[name] = glyph
        candidate['gvar'].variations[name] = []
        metrics = provider.at(count, zero)
        require(metrics['horizontal_origin_x'] == 0 and metrics['horizontal_origin_y'] == 0,
                'experiment_nonzero_source_horizontal_origin')
        width, height, top = (metrics[field] for field in
                              ('advance_width', 'advance_height', 'vertical_origin_y'))
        defaults.append((width, height, top))
        candidate['hmtx'].metrics[name] = (width, glyph.xMin)
        candidate['vmtx'].metrics[name] = (height, top-glyph.yMax)
        for x, y in points:
            error = math.hypot(otRound(x*multiplier)/multiplier-x, otRound(y*multiplier)/multiplier-y)
            point_error = max(point_error, error)
            point_failures += error > LIMIT
        metric_error = max(metric_error, *(abs(otRound(v*multiplier)/multiplier-v) for v in (width, height, top)))
        if count in selected_models:
            selected_defaults[count] = (points.copy(), list(flags), list(ends))
        empty_count += not len(points)
        cubic_count += cubics
        count += 1
    require(count == len(order), 'experiment_complete_ordered_native_defaults_required')
    scale_upem(candidate, source_upem * multiplier)
    require(candidate['head'].unitsPerEm == source_upem*multiplier, 'experiment_scaled_UPM_differs')
    for gid, name in enumerate(order):
        glyph = candidate['glyf'][name]
        glyph.recalcBounds(None)
        _integer_model(glyph, [])
        width, height, top = defaults[gid]
        hm, vm = (otRound(width*multiplier), glyph.xMin), (otRound(height*multiplier), otRound(top*multiplier)-glyph.yMax)
        require(0 <= hm[0] <= 65535 and 0 <= vm[0] <= 65535
                and -32768 <= hm[1] <= 32767 and -32768 <= vm[1] <= 32767,
                'experiment_scaled_default_metric_overflow')
        candidate['hmtx'].metrics[name], candidate['vmtx'].metrics[name] = hm, vm
    model_reports = []
    for gid, value in sorted(selected_models.items()):
        require(type(value) in (list, tuple) and len(value) == 5, 'experiment_selected_model_tuple_required')
        glyph, tuples, hm, vm, report = copy.deepcopy(value)
        require(type(report) is dict and report.get('glyph_id') == gid
                and report.get('source_units_per_em') == source_upem
                and report.get('target_units_per_em') == source_upem*multiplier
                and report.get('physical_grid_multiplier') == multiplier,
                'experiment_selected_model_scale_binding_invalid')
        _integer_model(glyph, tuples)
        require(type(hm) in (list, tuple) and type(vm) in (list, tuple) and len(hm) == len(vm) == 2
                and all(type(v) is int for v in (*hm, *vm)) and hm[1] == glyph.xMin
                and 0 <= hm[0] <= 65535 and 0 <= vm[0] <= 65535
                and -32768 <= hm[1] <= 32767 and -32768 <= vm[1] <= 32767,
                'experiment_selected_model_metric_invalid')
        points, flags, ends = selected_defaults[gid]
        selected_points = glyph.getCoordinates(None)[0]
        topology = (list(glyph.endPtsOfContours) == ends and len(selected_points) == len(points)
                    and [int(flag)&1 for flag in glyph.flags] == [int(flag)&1 for flag in flags])
        error = max((math.hypot(x/multiplier-a, y/multiplier-b)
                     for (x, y), (a, b) in zip(selected_points, points)), default=0.) if topology else None
        model_reports.append({'glyph_id': gid, 'report': report,
                              'default_topology_matches_native': topology,
                              'default_point_error_source_units': error})
        name = order[gid]
        candidate['glyf'].glyphs[name], candidate['gvar'].variations[name] = glyph, tuples
        candidate['hmtx'].metrics[name], candidate['vmtx'].metrics[name] = tuple(hm), tuple(vm)
    verification = add_metric_variations(candidate)
    _rename(candidate)
    candidate.recalcTimestamp = False
    require(candidate.getGlyphOrder() == order and candidate['maxp'].numGlyphs == len(order)
            and hashlib.sha256(candidate['cmap'].compile(candidate)).hexdigest() == cmap_digest,
            'experiment_original_GID_or_cmap_changed')
    for tag, digest in unverified.items():
        require(hashlib.sha256(candidate.getTableData(tag)).hexdigest() == digest,
                'experiment_unverified_retained_table_changed')
    manifest = {'status': 'EXPERIMENTAL_ORIGINAL_DEFAULT_FACE_WITH_PARTIAL_VARIABLE_MODELS_NOT_ACCEPTED',
        'source_units_per_em': source_upem, 'target_units_per_em': source_upem*multiplier,
        'physical_grid_multiplier': multiplier, 'glyph_count': count, 'native_default_records_consumed': count,
        'measured_empty_default_glyphs': empty_count, 'default_only_GIDs': count-len(selected_models),
        'selected_variable_GIDs': sorted(selected_models), 'axis_models_partial': True,
        'glyph_order_sha256': _digest(order), 'cmap_sha256': cmap_digest,
        'all_original_GID_slots_and_cmap_preserved': True, 'all_default_glyphs_have_native_records': True,
        'scale_before_first_integer_encoding': True, 'default_maximum_point_quantization_error_source_units': point_error,
        'default_points_above_1_32': point_failures, 'default_maximum_table_metric_quantization_error_source_units': metric_error,
        'removed_tables': removed, 'replaced_mapping': 'CUSTOM_NORMALIZED_DESIGN_Q_ONLY_NOT_ORIGINAL_USER_AXES',
        'table_scaling_backend': 'fontTools.ttLib.scaleUpem',
        'retained_unscaled_unverified_tables': {tag: {'sha256': digest, 'status': 'UNSCALED_UNVERIFIED'}
                                              for tag, digest in unverified.items()},
        'BASE_GDEF_GPOS_point_index_anchors': 'REFUSED_IF_PRESENT',
        'metrics_provenance': 'SOURCE_TABLE_DEFAULTS_NOT_APPLE_NATIVE_MEASUREMENTS',
        'vertical_origin_y_basis': 'SOURCE_VORG_ENCODED_IN_VMTX_AND_GVAR_PHANTOMS',
        'vertical_origin_x_native_validation': 'NOT_RUN', 'metric_variation_verification': verification,
        'HVF_composites_flattened': True, 'standard_component_relations_preserved': False,
        'selected_model_reports': model_reports, 'native_transcript_validation': 'CALLER_MUST_BIND',
        'strict_limit_source_font_units': LIMIT, 'strict_font_acceptance': False,
        'source_user_mapping_accepted': False, 'continuous_space_proof': False,
        'production_accepted': False, 'font_only_equivalence_accepted': False,
        'Windows11': 'NOT_RUN', 'Qt_Swirl': 'NOT_RUN'}
    return candidate, manifest
