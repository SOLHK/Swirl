"""Write HVAR/VVAR directly from validated gvar phantom coefficients.

No Apple data or platform measurement corrections. This is an exact second
encoding of an already reconstructed TrueType model, not an HVF decoder.
Side-bearing maps are deliberately absent: changing bounding extrema need not
be linear over the same regions. gvar retains all points and vertical origins.
References: Microsoft OpenType HVAR, VVAR and gvar specifications.
"""
from __future__ import annotations

import math
from collections import defaultdict

from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import buildVarIdxMap
from fontTools.varLib.varStore import OnlineVarStoreBuilder


class MetricVariationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise MetricVariationError(message)


def _axes(font):
    require(all(tag in font for tag in ('head', 'glyf', 'gvar', 'hmtx', 'fvar')),
            'standard TrueType variable outline/metric tables are required')
    tags = [a.axisTag for a in font['fvar'].axes]
    require(bool(tags) and len(set(tags)) == len(tags), 'invalid variation axis list')
    return tags


def _support_key(support, tags):
    require(set(support) <= set(tags), 'gvar support contains an unknown axis')
    key = []
    for tag in tags:
        triple = tuple(support.get(tag, (0, 0, 0)))
        require(len(triple) == 3, 'invalid variation support tuple')
        require(all(isinstance(v, (int, float)) and math.isfinite(v)
                    and -1 <= v <= 1 and v * 16384 == int(v * 16384) for v in triple),
                'variation support is not exactly representable in F2DOT14')
        low, peak, high = triple
        require(low <= peak <= high, 'variation support is not ordered')
        require(triple == (0, 0, 0) or (peak != 0 and not low < 0 < high),
                'noncontributing or cross-zero variation support is not supported')
        key.append(triple)
    require(any(t != (0, 0, 0) for t in key), 'constant gvar tuple cannot encode a metric variation')
    return tuple(key)


def _clean(values):
    return {key: value for key, value in values.items() if value}


def _phantom_models(font, name, tags):
    glyph = font['glyf'][name]
    require(not glyph.isComposite(), 'metric writer requires expanded reconstruction glyphs')
    points, _, _ = glyph.getCoordinates(font['glyf'])
    base, _ = font['glyf']._getCoordinatesAndControls(
        name, font['hmtx'].metrics, font['vmtx'].metrics if 'vmtx' in font else None)
    require(base[-4][0] == 0, 'TrueType VF requires hmtx LSB equal to glyph xMin')
    models = {'HVAR': defaultdict(int), 'VVAR': defaultdict(int)}
    for variation in font['gvar'].variations.get(name, []):
        require(len(variation.coordinates) == len(points) + 4, 'gvar point count differs from glyf')
        key = _support_key(variation.axes, tags)
        phantoms = []
        for pair in variation.coordinates[-4:]:
            # An omitted phantom delta is zero, not a contour IUP candidate.
            pair = (0, 0) if pair is None else pair
            require(len(pair) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v)
                    and v == int(v) for v in pair), 'gvar phantom deltas must be finite integers')
            phantoms.append(tuple(int(v) for v in pair))
        require(phantoms[0][0] == 0, 'varied left phantom must remain at zero for TrueType VF')
        require(phantoms[0][1] == phantoms[1][1] == phantoms[2][0] == phantoms[3][0] == 0,
                'unexpected orthogonal phantom variation')
        models['HVAR'][key] += phantoms[1][0] - phantoms[0][0]
        models['VVAR'][key] += phantoms[2][1] - phantoms[3][1]
    return {tag: _clean(model) for tag, model in models.items()}


def add_metric_variations(font):
    """Add exact advance tables transactionally; never replace existing tables.

    Requires gvar coefficients that passed reconstruction/holdout checks. Does
    not alter gvar, the axis space, glyph order, metrics or any outline points.
    The required head.flags bit 1 is set only after proving the zero-origin
    invariant for every glyph and every tuple.
    """
    tags = _axes(font)
    require('HVAR' not in font and 'VVAR' not in font, 'remove/remap old metric tables explicitly first')
    kinds = ['HVAR'] + (['VVAR'] if 'vmtx' in font else [])
    order = font.getGlyphOrder()
    stores = {kind: OnlineVarStoreBuilder(tags) for kind in kinds}
    indices = {kind: [] for kind in kinds}
    for name in order:
        models = _phantom_models(font, name, tags)
        for kind in kinds:
            model = models[kind]
            supports = [{tag: triple for tag, triple in zip(tags, key) if triple != (0, 0, 0)}
                        for key in model]
            stores[kind].setSupports(supports)
            indices[kind].append(stores[kind].storeDeltas(list(model.values())))
    pending = {}
    for kind in kinds:
        table = getattr(otTables, kind)()
        table.Version = 0x00010000
        table.VarStore = stores[kind].finish()
        field = 'AdvWidthMap' if kind == 'HVAR' else 'AdvHeightMap'
        setattr(table, field, buildVarIdxMap(indices[kind], order))
        for field in (('LsbMap', 'RsbMap') if kind == 'HVAR' else ('TsbMap', 'BsbMap', 'VOrgMap')):
            setattr(table, field, None)
        wrapper = newTable(kind)
        wrapper.table = table
        pending[kind] = wrapper
    flags_before = font['head'].flags
    try:
        for kind, table in pending.items():
            font[kind] = table
        font['head'].flags |= 2
        return verify_metric_variations(font)
    except Exception:
        for kind in pending:
            if kind in font:
                del font[kind]
        font['head'].flags = flags_before
        raise


def _stored_model(font, kind, name, tags):
    table = font[kind].table
    require(table.Version == 0x00010000, 'unsupported metric variation version')
    mapping = getattr(table, 'AdvWidthMap' if kind == 'HVAR' else 'AdvHeightMap')
    index = font.getGlyphID(name) if mapping is None else mapping.mapping[name]
    for field in (('LsbMap', 'RsbMap') if kind == 'HVAR' else ('TsbMap', 'BsbMap', 'VOrgMap')):
        require(getattr(table, field) is None, f'unexpected {kind}.{field}')
    store = table.VarStore
    require(store.Format == 1 and store.VarRegionList.RegionAxisCount == len(tags),
            'metric store format/axis count differs')
    if index == 0xFFFFFFFF:
        return {}
    data = store.VarData[index >> 16]
    row = data.Item[index & 0xFFFF]
    require(len(row) == len(data.VarRegionIndex), 'metric row/region count differs')
    result = defaultdict(int)
    for region_index, value in zip(data.VarRegionIndex, row):
        region = store.VarRegionList.Region[region_index]
        require(len(region.VarRegionAxis) == len(tags), 'metric region axis count differs')
        support = {tag: (a.StartCoord, a.PeakCoord, a.EndCoord)
                   for tag, a in zip(tags, region.VarRegionAxis) if a.PeakCoord != 0}
        # Even zero coefficients must not hide malformed active regions.
        key = _support_key(support, tags)
        result[key] += value
    return _clean(result)


def verify_metric_variations(font):
    """Compare complete decoded coefficient maps, not only sampled instances.

    This proves equality of the two standard advance encodings everywhere in
    their shared normalized space. It proves nothing new about the HVF source
    between the independently measured source holdout locations.
    """
    tags = _axes(font)
    require(font['head'].flags & 2, 'TrueType VF head.flags bit 1 is missing')
    kinds = ['HVAR'] + (['VVAR'] if 'vmtx' in font else [])
    require(all(kind in font for kind in kinds), 'missing rebuilt metric variation table')
    checked = 0
    for name in font.getGlyphOrder():
        expected = _phantom_models(font, name, tags)
        for kind in kinds:
            actual = _stored_model(font, kind, name, tags)
            require(actual == expected[kind], f'{kind} advance coefficients differ from gvar for {name}')
            checked += 1
    return {'status': 'PASS_EXACT_STANDARD_METRIC_COEFFICIENTS', 'tables': kinds,
            'glyph_metric_models_checked': checked, 'glyph_count': len(font.getGlyphOrder()),
            'head_lsb_equals_xmin_flag': True,
            'side_bearings_and_vertical_origins': 'retained_gvar_not_approximated_as_extra_maps',
            'native_source_equivalence': 'NOT_ESTABLISHED_BY_THIS_CHECK'}
