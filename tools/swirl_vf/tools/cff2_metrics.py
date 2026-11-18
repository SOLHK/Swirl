"""Encode CFF2 advance and vertical-origin metrics from verified TT phantoms.

Unlike TrueType VVAR, CFF2 uses VORG and VVAR.VOrgMap for the vertical origin Y.
The X origin remains a layout concern; this module never replaces it by width/2
and then claims equivalence to an independent native X origin.
"""
from __future__ import annotations

import copy
from collections import Counter

from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import buildVarIdxMap
from fontTools.varLib.varStore import OnlineVarStoreBuilder

from metric_variations import add_metric_variations, verify_metric_variations, require


def prepare_from_truetype(source):
    """Return a detached TT font with both TT metrics and additional CFF2 maps.

    Geometry conversion must follow before saving as CFF2. All input tables,
    including existing HVAR/VVAR, must describe the same validated gvar model.
    """
    font = copy.deepcopy(source)
    if 'HVAR' not in font and 'VVAR' not in font:
        add_metric_variations(font)
    else:
        verify_metric_variations(font)
    require('vmtx' in font and 'vhea' in font, 'explicit_vertical_metrics_required')
    tags = [axis.axisTag for axis in font['fvar'].axes]
    order = font.getGlyphOrder()
    store = OnlineVarStoreBuilder(tags)
    advances, origins, defaults = [], [], {}
    for name in order:
        glyph = font['glyf'][name]
        require(not glyph.isComposite(), 'expanded_geometry_required_for_metric_bridge')
        points, _ = font['glyf']._getCoordinatesAndControls(name, font['hmtx'].metrics, font['vmtx'].metrics)
        defaults[name] = int(points[-2][1])
        variations = font['gvar'].variations.get(name, [])
        store.setSupports([v.axes for v in variations])
        top = [(v.coordinates[-2] or (0, 0))[1] for v in variations]
        bottom = [(v.coordinates[-1] or (0, 0))[1] for v in variations]
        advances.append(store.storeDeltas([a-b for a, b in zip(top, bottom)]))
        origins.append(store.storeDeltas(top))
    table = otTables.VVAR()
    table.Version = 0x00010000
    table.VarStore = store.finish()
    table.AdvHeightMap = buildVarIdxMap(advances, order)
    table.VOrgMap = buildVarIdxMap(origins, order)
    table.TsbMap = table.BsbMap = None
    font['VVAR'] = newTable('VVAR'); font['VVAR'].table = table
    font['VORG'] = newTable('VORG')
    font['VORG'].majorVersion = 1; font['VORG'].minorVersion = 0
    font['VORG'].defaultVertOriginY = Counter(defaults.values()).most_common(1)[0][0]
    font['VORG'].VOriginRecords = {name: value for name, value in defaults.items()
        if value != font['VORG'].defaultVertOriginY}
    return font
