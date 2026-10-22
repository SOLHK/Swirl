"""Authored seven-glyph avar2 compatibility control, never a converter.

Keep the q-space glyph/metric model and UPM1000 unchanged. The existing nominal
grid staircase embeds integer q in r; a post-segment avar2 VarStore contracts
r back to q. This tests a font-file representation without application code.
Between-grid/original-source mapping and native compatibility are unverified.
Microsoft's published OpenType 1.9.1 avar page documents version 1 only. ISO OFF
edition 5 was published in July 2026; its final avar2 text was not inspected.

Primary design references; fontTools public builders reused, no copied code:
https://github.com/harfbuzz/boring-expansion-spec/blob/main/avar2.md
https://github.com/harfbuzz/harfbuzz/blob/14.6.0/src/hb-ot-var-avar-table.hh
https://github.com/fonttools/fonttools/blob/main/Lib/fontTools/ttLib/tables/_a_v_a_r.py
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys

from fontTools.ttLib.tables import otTables
from fontTools.varLib.builder import (buildVarRegionList, buildVarData,
                                     buildVarStore, buildDeltaSetIndexMap)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from design_axis_basis import basis_from_axis, build_rebased_avar
from rebase_design_font import CUSTOM_TAGS, _validate_standard_q
from rebuild_c1_fixture import BASE_ORDER

COMPATIBILITY = 'NOT_VERIFIED'
PRODUCTION_ACCEPTED = False


def make_avar2_control(source, axes):
    """Return a detached authored TTFont only; no file input/output or CLI."""
    _validate_standard_q(source, axes)
    profiles = [('WDTH', 1, 500, 1000), ('wght', 100, 500, 900), ('HGHT', 1, 500, 1000)]
    if (source['head'].unitsPerEm != 1000 or source.getGlyphOrder() != list(BASE_ORDER)
            or source['maxp'].numGlyphs != 7 or source['fvar'].instances or 'STAT' in source
            or source['name'].getDebugName(1) != 'C1 Original Geometry 00 SC'
            or [(axis.tag, axis.minimum, axis.default, axis.maximum) for axis in axes] != profiles
            or [(basis_from_axis(axis).q_min, basis_from_axis(axis).q_max) for axis in axes]
               != [(-16384, 16384), (-3072, 3072), (-16384, 16384)]):
        raise ValueError('authored_seven_glyph_UPM1000_three_sixteenths_control_required')
    result = copy.deepcopy(source)
    rename = {CUSTOM_TAGS[axis.tag]: axis.tag for axis in axes}
    for output, original in zip(result['fvar'].axes, axes):
        output.axisTag = original.tag
        output.minValue, output.defaultValue, output.maxValue = original.minimum, original.default, original.maximum
    for variations in result['gvar'].variations.values():
        for variation in variations:
            variation.axes = {rename[tag]: support for tag, support in variation.axes.items()}
    if 'cvar' in result:
        for variation in result['cvar'].variations:
            variation.axes = {rename[tag]: support for tag, support in variation.axes.items()}
    avar, _ = build_rebased_avar(axes)
    avar.majorVersion = 2
    avar.table = otTables.avar()
    avar.table.Reserved = 0
    tags = [axis.tag for axis in axes]
    regions = buildVarRegionList([{'wght': (-1., -1., 0.)}, {'wght': (0., 1., 1.)}], tags)
    rows = [[13312, -13312] if tag == 'wght' else [0, 0] for tag in tags]
    avar.table.VarStore = buildVarStore(regions, [buildVarData([0, 1], rows, optimize=False)])
    avar.table.VarIdxMap = buildDeltaSetIndexMap(list(range(len(tags))))
    result['avar'] = avar
    return result
